from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow.adjudication import (
    materialize_run_score_ledger,
    persist_scorer_snapshot,
)
from orchestrator.workflow.trial.ledger import TrialLedgerError
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.trial import checks as trial_checks
from orchestrator.workflow.trial import ledger as trial_ledger
from orchestrator.workflow.trial.ledger import load_trial_event_ledger
from tests.test_workflow_trial_runtime import _CellHarnesses, _execute, _runtime_fixture


class _Registry:
    def exists(self, name: str) -> bool:
        return name == "judge"

    def merge_params(self, name: str, params: dict[str, object]):
        assert name == "judge"
        return dict(params)


class _Composer:
    def read_prompt_source(self, source, **_kwargs):
        return ("prompt" if "input_file" in source else "rubric"), None


class _ForbiddenExecutor:
    def prepare_invocation(self, *_args, **_kwargs):
        raise AssertionError("provider preparation must not precede resume preflight")

    def execute(self, *_args, **_kwargs):
        raise AssertionError("provider launch must not precede resume preflight")


class _SuccessExecutor:
    def __init__(self, labels: tuple[str, ...]) -> None:
        self.labels = labels

    def prepare_invocation(self, _provider, _params, _context, **kwargs):
        [label] = [
            candidate
            for candidate in self.labels
            if candidate in kwargs["prompt_content"]
        ]
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


def _arguments(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    packets_module = importlib.import_module("orchestrator.workflow.trial.packets")
    fixture = _runtime_fixture(tmp_path / "trial")
    execution = _execute(fixture, _CellHarnesses())
    ledger_path = execution.ledger_path
    terminal = load_trial_event_ledger(ledger_path)
    evidence_frozen = trial_ledger.append_trial_evidence_freeze(
        ledger_path,
        expected_head_digest=terminal.rows[-1].row_digest,
    )
    checks_frozen = trial_checks.ensure_trial_checks_frozen(
        ledger_path,
        request=fixture["request"],
    )
    bindings = load_trial_event_ledger(ledger_path).rows[0].payload[
        "sealed_opaque_label_map"
    ]["bindings"]
    packets = tuple(
        packets_module.build_trial_evaluation_packet(
            opaque_label=binding["opaque_label"],
            observation_include=("task_spec",),
            observations={"task_spec": {"objective": "judge the frozen result"}},
            sealed_identity_values=("SECRET-ARM",),
            max_item_bytes=1024,
            max_packet_bytes=4096,
        )
        for binding in bindings
    )
    packet_records = [
        {
            "cell": cell.record,
            "opaque_label": binding["opaque_label"],
            "packet_digest": canonical_sha256(packet),
        }
        for cell, binding, packet in zip(
            fixture["request"].cell_domain, bindings, packets, strict=True
        )
    ]
    packets_frozen = trial_ledger.append_trial_packets_freeze(
        ledger_path,
        expected_head_digest=checks_frozen.row_digest,
        cell_packets=packet_records,
    )
    fixture.update(
        execution=execution,
        ledger_path=ledger_path,
        evidence_frozen=evidence_frozen,
        checks_frozen=checks_frozen,
        packets=packets,
        packets_frozen=packets_frozen,
    )
    return fixture, {
        "packets": packets,
        "trial_request_digest": fixture["request"].digest,
        "evaluation_digest": fixture["request"].evaluation_digest,
        "evidence_frozen_digest": evidence_frozen.row_digest,
        "scorer_config": {
            "provider": "judge",
            "provider_params": {},
            "evaluator_prompt_source": {"input_file": "prompt.txt"},
            "rubric_source": {"asset_file": "rubric.md"},
            "evidence_limits": {"max_item_bytes": 1024, "max_packet_bytes": 4096},
            "evidence_confidentiality": "same_trust_boundary",
        },
        "provider_registry": _Registry(),
        "prompt_composer": _Composer(),
        "provider_executor": _ForbiddenExecutor(),
        "scorer_root": tmp_path / "scorer",
        "score_ledger_path": tmp_path / "scores.jsonl",
        "trial_event_ledger_path": fixture["ledger_path"],
        "evaluator_workspace": tmp_path / "evaluator",
        "max_evaluator_attempts": len(packets),
        "max_evaluator_concurrency": 1,
    }


def test_tampered_score_ledger_fails_before_scorer_or_event_mutation(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(tmp_path)
    score_path = arguments["score_ledger_path"]
    assert isinstance(score_path, Path)
    score_path.write_text("{}\n", encoding="utf-8")
    event_bytes = fixture["ledger_path"].read_bytes()

    with pytest.raises(TrialLedgerError, match="missing or extra fields"):
        evaluation.evaluate_trial_packets(**arguments)

    assert fixture["ledger_path"].read_bytes() == event_bytes
    assert not arguments["scorer_root"].exists()
    assert score_path.read_bytes() == b"{}\n"
    assert not arguments["evaluator_workspace"].exists()


def test_malformed_score_ledger_fails_before_scorer_or_event_mutation(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(tmp_path)
    score_path = arguments["score_ledger_path"]
    assert isinstance(score_path, Path)
    score_path.write_bytes(b"{not-json\n")
    event_bytes = fixture["ledger_path"].read_bytes()

    with pytest.raises(json.JSONDecodeError):
        evaluation.evaluate_trial_packets(**arguments)

    assert fixture["ledger_path"].read_bytes() == event_bytes
    assert not arguments["scorer_root"].exists()
    assert score_path.read_bytes() == b"{not-json\n"
    assert not arguments["evaluator_workspace"].exists()


def test_unreadable_score_ledger_fails_before_scorer_or_event_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(tmp_path)
    score_path = arguments["score_ledger_path"]
    assert isinstance(score_path, Path)
    score_path.write_bytes(b"unreadable sentinel\n")
    event_bytes = fixture["ledger_path"].read_bytes()
    original_read_text = Path.read_text

    def read_text(path: Path, *args, **kwargs):
        if path == score_path:
            raise PermissionError("score ledger is unreadable")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    with pytest.raises(PermissionError, match="score ledger is unreadable"):
        evaluation.evaluate_trial_packets(**arguments)

    assert fixture["ledger_path"].read_bytes() == event_bytes
    assert not arguments["scorer_root"].exists()
    assert score_path.read_bytes() == b"unreadable sentinel\n"
    assert not arguments["evaluator_workspace"].exists()


def test_mismatched_scorer_event_fails_before_scorer_snapshot_mutation(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(tmp_path)
    ledger = load_trial_event_ledger(fixture["ledger_path"])
    trial_ledger.append_trial_scorer_freeze(
        fixture["ledger_path"],
        expected_head_digest=ledger.rows[-1].row_digest,
        scorer_identity_digest="sha256:" + "a" * 64,
        snapshot_digest="sha256:" + "b" * 64,
    )
    event_bytes = fixture["ledger_path"].read_bytes()

    with pytest.raises(
        evaluation.TrialEvaluationError,
        match="persisted trial scorer event disagrees",
    ):
        evaluation.evaluate_trial_packets(**arguments)

    assert fixture["ledger_path"].read_bytes() == event_bytes
    assert not arguments["scorer_root"].exists()
    assert not arguments["score_ledger_path"].exists()
    assert not arguments["evaluator_workspace"].exists()


def test_exact_scorer_event_without_prior_snapshot_fails_before_recreation(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(tmp_path)
    scorer, _prompt, _rubric = evaluation._resolve_scorer(
        scorer_config=arguments["scorer_config"],
        provider_registry=arguments["provider_registry"],
        prompt_composer=arguments["prompt_composer"],
    )
    ledger = load_trial_event_ledger(fixture["ledger_path"])
    trial_ledger.append_trial_scorer_freeze(
        fixture["ledger_path"],
        expected_head_digest=ledger.rows[-1].row_digest,
        scorer_identity_digest=scorer["scorer_identity_digest"],
        snapshot_digest=canonical_sha256(scorer),
    )
    event_bytes = fixture["ledger_path"].read_bytes()

    with pytest.raises(
        evaluation.TrialEvaluationError,
        match="persisted trial scorer snapshot is missing",
    ):
        evaluation.evaluate_trial_packets(**arguments)

    assert fixture["ledger_path"].read_bytes() == event_bytes
    assert not arguments["scorer_root"].exists()
    assert not arguments["score_ledger_path"].exists()
    assert not arguments["evaluator_workspace"].exists()


def test_clean_evaluation_and_exact_resume_preserve_all_durable_bytes(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(tmp_path)
    labels = tuple(packet["evaluation_id"] for packet in arguments["packets"])

    first = evaluation.evaluate_trial_packets(
        **{**arguments, "provider_executor": _SuccessExecutor(labels)}
    )
    event_bytes = fixture["ledger_path"].read_bytes()
    score_path = arguments["score_ledger_path"]
    scorer_path = arguments["scorer_root"] / "metadata.json"
    assert isinstance(score_path, Path)
    score_bytes = score_path.read_bytes()
    scorer_bytes = scorer_path.read_bytes()

    resumed = evaluation.evaluate_trial_packets(**arguments)

    assert resumed.rows == first.rows
    assert fixture["ledger_path"].read_bytes() == event_bytes
    assert score_path.read_bytes() == score_bytes
    assert scorer_path.read_bytes() == scorer_bytes


def test_mismatched_score_event_fails_before_any_resume_mutation(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(tmp_path)
    labels = tuple(packet["evaluation_id"] for packet in arguments["packets"])
    first = evaluation.evaluate_trial_packets(
        **{**arguments, "provider_executor": _SuccessExecutor(labels)}
    )
    rows = [dict(row) for row in first.rows]
    rows[0]["summary"] = "tampered but internally digest-consistent"
    content = dict(rows[0])
    content.pop("row_content_digest")
    rows[0]["row_content_digest"] = canonical_sha256(content)
    score_path = arguments["score_ledger_path"]
    assert isinstance(score_path, Path)
    materialize_run_score_ledger(rows, score_path)
    event_bytes = fixture["ledger_path"].read_bytes()
    score_bytes = score_path.read_bytes()
    scorer_path = arguments["scorer_root"] / "metadata.json"
    scorer_bytes = scorer_path.read_bytes()

    with pytest.raises(
        evaluation.TrialEvaluationError,
        match="persisted trial score event disagrees",
    ):
        evaluation.evaluate_trial_packets(**arguments)

    assert fixture["ledger_path"].read_bytes() == event_bytes
    assert score_path.read_bytes() == score_bytes
    assert scorer_path.read_bytes() == scorer_bytes


def test_score_attempt_authority_fails_before_active_allocation_reconciliation(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(tmp_path)
    scorer, _prompt, _rubric = evaluation._resolve_scorer(
        scorer_config=arguments["scorer_config"],
        provider_registry=arguments["provider_registry"],
        prompt_composer=arguments["prompt_composer"],
    )
    scorer_root = arguments["scorer_root"]
    assert isinstance(scorer_root, Path)
    scorer_path = persist_scorer_snapshot(scorer, scorer_root)
    ledger = load_trial_event_ledger(fixture["ledger_path"])
    scorer_event = trial_ledger.append_trial_scorer_freeze(
        fixture["ledger_path"],
        expected_head_digest=ledger.rows[-1].row_digest,
        scorer_identity_digest=scorer["scorer_identity_digest"],
        snapshot_digest=canonical_sha256(scorer),
    )
    [packet, *_rest] = arguments["packets"]
    allocation = trial_ledger.append_trial_evaluator_attempt_allocation(
        fixture["ledger_path"],
        expected_head_digest=scorer_event.row_digest,
        opaque_label=packet["evaluation_id"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=canonical_sha256(packet),
        scorer_frozen_row_digest=scorer_event.row_digest,
        started_at_unix_ns=1_000_000_000,
    )
    attempts = [
        {
            "attempt": 1,
            "global_attempt": 1,
            "status": "output_invalid",
            "exit_code": 0,
            "duration_ms": 3,
            "token_usage": {"variant": "UNKNOWN"},
            "cost": {"variant": "UNKNOWN"},
        },
        {
            "attempt": 2,
            "global_attempt": 2,
            "status": "scored",
            "exit_code": 0,
            "duration_ms": 4,
            "token_usage": {"variant": "UNKNOWN"},
            "cost": {"variant": "UNKNOWN"},
        },
    ]
    row = evaluation._score_row(
        trial_request_digest=arguments["trial_request_digest"],
        evaluation_digest=arguments["evaluation_digest"],
        evidence_frozen_digest=arguments["evidence_frozen_digest"],
        packet=packet,
        scorer_identity_digest=scorer["scorer_identity_digest"],
        parsed={
            "candidate_id": packet["evaluation_id"],
            "score": 0.75,
            "summary": "internally valid but event-inconsistent",
            "citations": ["task_spec"],
        },
        charged_attempts=attempts,
        failure=None,
    )
    score_path = arguments["score_ledger_path"]
    assert isinstance(score_path, Path)
    materialize_run_score_ledger((row,), score_path)
    event_bytes = fixture["ledger_path"].read_bytes()
    score_bytes = score_path.read_bytes()
    scorer_bytes = scorer_path.read_bytes()

    with pytest.raises(
        evaluation.TrialEvaluationError,
        match="persisted trial score attempt authority disagrees",
    ):
        evaluation.evaluate_trial_packets(**arguments)

    assert allocation.row_digest in event_bytes.decode("utf-8")
    assert fixture["ledger_path"].read_bytes() == event_bytes
    assert score_path.read_bytes() == score_bytes
    assert scorer_path.read_bytes() == scorer_bytes
