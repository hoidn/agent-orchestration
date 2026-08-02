from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow.adjudication import (
    materialize_run_score_ledger,
    persist_scorer_snapshot,
)
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.trial import ledger as trial_ledger
from orchestrator.workflow.trial.ledger import TrialLedgerError, load_trial_event_ledger
from tests.test_workflow_trial_evaluation import (
    _durable_evaluator_fixture,
    _freeze_trial_packets_for_attempts,
    _settle_trial_evaluator_attempt,
)


class _Registry:
    def exists(self, name: str) -> bool:
        return name == "judge"

    def merge_params(self, name: str, params: dict[str, object]):
        assert name == "judge"
        return dict(params)


class _Composer:
    def read_prompt_source(self, source, **_kwargs):
        return ("prompt" if "input_file" in source else "rubric"), None


class _RecordingSuccessExecutor:
    def __init__(self, labels: tuple[str, ...]) -> None:
        self.labels = labels
        self.calls: list[str] = []

    def prepare_invocation(self, _provider, _params, _context, **kwargs):
        [label] = [
            candidate
            for candidate in self.labels
            if candidate in kwargs["prompt_content"]
        ]
        self.calls.append(label)
        return label, None

    def execute(self, label, *, cwd):
        from orchestrator.providers.executor import ProviderExecutionResult

        return ProviderExecutionResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "candidate_id": label,
                    "score": 0.75,
                    "summary": "supported",
                    "citations": ["task_spec"],
                }
            ).encode(),
            stderr=b"",
            duration_ms=5,
        )


class _ForbiddenExecutor:
    def prepare_invocation(self, *_args, **_kwargs):
        raise AssertionError("provider launch must not precede resume preflight")

    def execute(self, *_args, **_kwargs):
        raise AssertionError("provider launch must not precede resume preflight")


def _sparse_score_resume_fixture(
    tmp_path: Path,
) -> tuple[object, dict[str, object], dict[str, object], dict[str, object]]:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _durable_evaluator_fixture(tmp_path / "trial")
    packets = fixture["packets"]
    scorer_config = {
        "provider": "judge",
        "provider_params": {},
        "evaluator_prompt_source": {"input_file": "prompt.txt"},
        "rubric_source": {"asset_file": "rubric.md"},
        "evidence_limits": {"max_item_bytes": 1024, "max_packet_bytes": 4096},
        "evidence_confidentiality": "same_trust_boundary",
    }
    scorer, _prompt, _rubric = evaluation._resolve_scorer(
        scorer_config=scorer_config,
        provider_registry=_Registry(),
        prompt_composer=_Composer(),
    )
    scorer_root = tmp_path / "scorer"
    persist_scorer_snapshot(scorer, scorer_root)
    ledger = load_trial_event_ledger(fixture["ledger_path"])
    scorer_event = trial_ledger.append_trial_scorer_freeze(
        fixture["ledger_path"],
        expected_head_digest=ledger.rows[-1].row_digest,
        scorer_identity_digest=scorer["scorer_identity_digest"],
        snapshot_digest=canonical_sha256(scorer),
    )

    first_packet, second_packet, *_rest = packets
    first_allocation = trial_ledger.append_trial_evaluator_attempt_allocation(
        fixture["ledger_path"],
        expected_head_digest=scorer_event.row_digest,
        opaque_label=first_packet["evaluation_id"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=canonical_sha256(first_packet),
        scorer_frozen_row_digest=scorer_event.row_digest,
        started_at_unix_ns=1_000_000_000,
    )
    first_settlement = trial_ledger.append_trial_evaluator_attempt_settlement(
        fixture["ledger_path"],
        expected_head_digest=first_allocation.row_digest,
        allocation_row_digest=first_allocation.row_digest,
        opaque_label=first_packet["evaluation_id"],
        local_attempt=1,
        global_attempt=1,
        status="provider_failed",
        exit_code=1,
        duration_ms=7,
        token_usage={"variant": "UNKNOWN"},
        cost={"variant": "UNKNOWN"},
        stdout_digest=None,
        stderr_digest=None,
        output_digest=None,
        score_row_content_digest=None,
    )
    second_allocation = trial_ledger.append_trial_evaluator_attempt_allocation(
        fixture["ledger_path"],
        expected_head_digest=first_settlement.row_digest,
        opaque_label=second_packet["evaluation_id"],
        local_attempt=1,
        global_attempt=2,
        packet_digest=canonical_sha256(second_packet),
        scorer_frozen_row_digest=scorer_event.row_digest,
        started_at_unix_ns=2_000_000_000,
    )
    second_score = evaluation._score_row(
        trial_request_digest=fixture["runtime"]["request"].digest,
        evaluation_digest=fixture["runtime"]["request"].evaluation_digest,
        evidence_frozen_digest=fixture["evidence_frozen"].row_digest,
        packet=second_packet,
        scorer_identity_digest=scorer["scorer_identity_digest"],
        parsed={
            "candidate_id": second_packet["evaluation_id"],
            "score": 0.75,
            "summary": "persisted before its event settlement",
            "citations": ["task_spec"],
        },
        charged_attempts=(
            {
                "attempt": 1,
                "global_attempt": 2,
                "status": "scored",
                "exit_code": 0,
                "duration_ms": 5,
            },
        ),
        failure=None,
    )
    score_path = tmp_path / "scores.jsonl"
    materialize_run_score_ledger((second_score,), score_path)
    arguments: dict[str, object] = {
        "packets": packets,
        "trial_request_digest": fixture["runtime"]["request"].digest,
        "evaluation_digest": fixture["runtime"]["request"].evaluation_digest,
        "evidence_frozen_digest": fixture["evidence_frozen"].row_digest,
        "scorer_config": scorer_config,
        "provider_registry": _Registry(),
        "prompt_composer": _Composer(),
        "provider_executor": _ForbiddenExecutor(),
        "scorer_root": scorer_root,
        "score_ledger_path": score_path,
        "trial_event_ledger_path": fixture["ledger_path"],
        "evaluator_workspace": tmp_path / "evaluator",
        "max_evaluator_attempts": len(packets) + 1,
        "max_evaluator_concurrency": 1,
    }
    return evaluation, fixture, arguments, {
        "first_packet": first_packet,
        "second_packet": second_packet,
        "second_allocation": second_allocation,
        "second_score": second_score,
    }


def test_sparse_partial_score_domain_resumes_then_final_load_is_complete(
    tmp_path: Path,
) -> None:
    evaluation, fixture, arguments, crash = _sparse_score_resume_fixture(tmp_path)
    score_path = arguments["score_ledger_path"]
    assert isinstance(score_path, Path)

    with pytest.raises(TrialLedgerError, match="global attempt domain"):
        trial_ledger.load_trial_score_rows(score_path)
    assert trial_ledger.load_trial_score_rows(
        score_path,
        validation_mode="partial",
    ) == [crash["second_score"]]

    labels = tuple(packet["evaluation_id"] for packet in arguments["packets"])
    executor = _RecordingSuccessExecutor(labels)
    result = evaluation.evaluate_trial_packets(
        **{**arguments, "provider_executor": executor}
    )

    assert crash["second_packet"]["evaluation_id"] not in executor.calls
    assert crash["first_packet"]["evaluation_id"] in executor.calls
    assert result.rows == tuple(trial_ledger.load_trial_score_rows(score_path))
    replay = trial_ledger.replay_trial_evaluator_attempts(fixture["ledger_path"])
    second_settlement = next(
        row
        for row in replay.settlements
        if row.payload["allocation_row_digest"]
        == crash["second_allocation"].row_digest
    )
    assert second_settlement.payload["status"] == "scored"
    assert second_settlement.payload["score_row_content_digest"] == crash[
        "second_score"
    ]["row_content_digest"]


def test_sparse_partial_score_attempt_mismatch_fails_before_any_mutation(
    tmp_path: Path,
) -> None:
    evaluation, fixture, arguments, crash = _sparse_score_resume_fixture(tmp_path)
    score_path = arguments["score_ledger_path"]
    scorer_path = arguments["scorer_root"] / "metadata.json"
    assert isinstance(score_path, Path)
    assert isinstance(scorer_path, Path)
    tampered = dict(crash["second_score"])
    tampered["charged_attempts"] = [dict(tampered["charged_attempts"][0])]
    tampered["charged_attempts"][0]["global_attempt"] = 3
    content = dict(tampered)
    content.pop("row_content_digest")
    tampered["row_content_digest"] = canonical_sha256(content)
    materialize_run_score_ledger((tampered,), score_path)
    event_bytes = fixture["ledger_path"].read_bytes()
    score_bytes = score_path.read_bytes()
    scorer_bytes = scorer_path.read_bytes()

    with pytest.raises(
        evaluation.TrialEvaluationError,
        match="persisted trial score attempt authority disagrees",
    ):
        evaluation.evaluate_trial_packets(**arguments)

    assert fixture["ledger_path"].read_bytes() == event_bytes
    assert score_path.read_bytes() == score_bytes
    assert scorer_path.read_bytes() == scorer_bytes
    assert not arguments["evaluator_workspace"].exists()


def test_partial_score_domain_still_rejects_duplicate_global_attempts(
    tmp_path: Path,
) -> None:
    _evaluation, _fixture, arguments, crash = _sparse_score_resume_fixture(tmp_path)
    duplicate = dict(crash["second_score"])
    duplicate["evaluation_label"] = "opaque-" + "f" * 64
    identity = {
        "schema_version": "trial_score_identity.v1",
        "trial_request_digest": duplicate["trial_request_digest"],
        "evaluation_digest": duplicate["evaluation_digest"],
        "evidence_frozen_digest": duplicate["evidence_frozen_digest"],
        "evaluation_label": duplicate["evaluation_label"],
        "evaluation_packet_digest": duplicate["evaluation_packet_digest"],
        "scorer_identity_digest": duplicate["scorer_identity_digest"],
    }
    duplicate["score_run_key"] = canonical_sha256(identity)
    content = dict(duplicate)
    content.pop("row_content_digest")
    duplicate["row_content_digest"] = canonical_sha256(content)
    score_path = arguments["score_ledger_path"]
    assert isinstance(score_path, Path)
    materialize_run_score_ledger((crash["second_score"], duplicate), score_path)

    with pytest.raises(TrialLedgerError, match="global attempt domain"):
        trial_ledger.load_trial_score_rows(score_path, validation_mode="partial")


def test_score_settlement_must_reference_latest_same_label_attempt(
    tmp_path: Path,
) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)
    first = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=scorer.row_digest,
        opaque_label=packets[0]["opaque_label"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=packets[0]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=1_000_000_000,
    )
    first_failed = _settle_trial_evaluator_attempt(
        path,
        first,
        status="provider_failed",
        score_row_content_digest=None,
    )
    second = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=first_failed.row_digest,
        opaque_label=packets[0]["opaque_label"],
        local_attempt=2,
        global_attempt=2,
        packet_digest=packets[0]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=2_000_000_000,
    )
    second_failed = _settle_trial_evaluator_attempt(
        path,
        second,
        status="provider_failed",
        score_row_content_digest=None,
    )

    with pytest.raises(TrialLedgerError, match="latest evaluator attempt"):
        trial_ledger.append_trial_score_settlement(
            path,
            expected_head_digest=second_failed.row_digest,
            opaque_label=packets[0]["opaque_label"],
            score_row_content_digest="sha256:" + "a" * 64,
            terminal_attempt_settlement_row_digest=first_failed.row_digest,
        )
