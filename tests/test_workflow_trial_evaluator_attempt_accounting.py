from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow.adjudication import persist_scorer_snapshot
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.trial import ledger as trial_ledger
from orchestrator.workflow.trial.ledger import TrialLedgerError, load_trial_event_ledger
from tests.test_workflow_trial_evaluation import _durable_evaluator_fixture


class _Registry:
    def exists(self, name: str) -> bool:
        return name == "judge"

    def merge_params(self, name: str, params: dict[str, object]):
        assert name == "judge"
        return {"model": "fixed", **params}


class _Composer:
    def read_prompt_source(self, source, **_kwargs):
        return ("prompt" if "input_file" in source else "rubric"), None


class _SuccessExecutor:
    def __init__(self, labels: tuple[str, ...], *, duration_ms: int = 9) -> None:
        self.labels = labels
        self.duration_ms = duration_ms

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
            duration_ms=self.duration_ms,
        )


class _SyntheticFailureExecutor:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def prepare_invocation(self, *_args, **_kwargs):
        if self.mode == "preparation":
            return None, {"type": "fixture"}
        return "invocation", None

    def execute(self, _invocation, *, cwd):
        raise RuntimeError("fixture future failure")


class _SequenceClock:
    def __init__(self, *values: int) -> None:
        self.values = list(values)

    def __call__(self) -> int:
        assert self.values, "fixture wall clock exhausted"
        return self.values.pop(0)


def _arguments(tmp_path: Path, *, executor) -> tuple[dict[str, object], dict[str, object]]:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _durable_evaluator_fixture(tmp_path / "trial")
    packets = fixture["packets"]
    arguments: dict[str, object] = {
        "packets": packets,
        "trial_request_digest": fixture["runtime"]["request"].digest,
        "evaluation_digest": fixture["runtime"]["request"].evaluation_digest,
        "evidence_frozen_digest": fixture["evidence_frozen"].row_digest,
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
        "provider_executor": executor,
        "scorer_root": tmp_path / "scorer",
        "score_ledger_path": tmp_path / "scores.jsonl",
        "trial_event_ledger_path": fixture["ledger_path"],
        "evaluator_workspace": tmp_path / "evaluator",
        "max_evaluator_attempts": len(packets) + 1,
        "max_evaluator_concurrency": 1,
    }
    scorer, _prompt, _rubric = evaluation._resolve_scorer(
        scorer_config=arguments["scorer_config"],
        provider_registry=arguments["provider_registry"],
        prompt_composer=arguments["prompt_composer"],
    )
    persist_scorer_snapshot(scorer, arguments["scorer_root"])
    ledger = load_trial_event_ledger(fixture["ledger_path"])
    scorer_event = trial_ledger.append_trial_scorer_freeze(
        fixture["ledger_path"],
        expected_head_digest=ledger.rows[-1].row_digest,
        scorer_identity_digest=scorer["scorer_identity_digest"],
        snapshot_digest=canonical_sha256(scorer),
    )
    return {**fixture, "scorer_event": scorer_event}, arguments


def _append_active_allocation(
    fixture: dict[str, object],
    arguments: dict[str, object],
    *,
    started_at_unix_ns: int,
):
    [packet, *_rest] = arguments["packets"]
    scorer_event = fixture["scorer_event"]
    return trial_ledger.append_trial_evaluator_attempt_allocation(
        fixture["ledger_path"],
        expected_head_digest=scorer_event.row_digest,
        opaque_label=packet["evaluation_id"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=canonical_sha256(packet),
        scorer_frozen_row_digest=scorer_event.row_digest,
        started_at_unix_ns=started_at_unix_ns,
    )


def _write_rechained(path: Path, mutate) -> None:
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    mutate(rows)
    previous = None
    encoded = []
    for sequence, row in enumerate(rows, start=1):
        row["sequence"] = sequence
        row["previous_row_digest"] = previous
        preimage = dict(row)
        preimage.pop("row_digest")
        row["row_digest"] = canonical_sha256(preimage)
        previous = row["row_digest"]
        encoded.append(canonical_json_bytes(row) + b"\n")
    path.write_bytes(b"".join(encoded))


def test_orphan_allocation_charges_wall_elapsed_and_normal_provider_duration(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    executor = _SuccessExecutor((), duration_ms=9)
    fixture, arguments = _arguments(
        tmp_path,
        executor=executor,
    )
    executor.labels = tuple(packet["evaluation_id"] for packet in fixture["packets"])
    active = _append_active_allocation(
        fixture,
        arguments,
        started_at_unix_ns=1_000_000_000,
    )
    arguments["wall_time_ns"] = lambda: 1_012_500_000

    evaluation.evaluate_trial_packets(**arguments)

    replay = trial_ledger.replay_trial_evaluator_attempts(fixture["ledger_path"])
    settlements = {
        row.payload["allocation_row_digest"]: row for row in replay.settlements
    }
    assert settlements[active.row_digest].payload["status"] == "provider_failed"
    assert settlements[active.row_digest].payload["duration_ms"] == 12
    normal_settlements = [
        settlements[allocation.row_digest]
        for allocation in replay.allocations
        if allocation.row_digest != active.row_digest
        and settlements[allocation.row_digest].payload["status"] == "scored"
    ]
    assert len(normal_settlements) == len(arguments["packets"])
    assert all(
        settlement.payload["duration_ms"] == 9
        for settlement in normal_settlements
    )


def test_orphan_reconciliation_rejects_backwards_clock_without_mutation(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(
        tmp_path,
        executor=_SuccessExecutor(()),
    )
    _append_active_allocation(
        fixture,
        arguments,
        started_at_unix_ns=1_000_000_000,
    )
    event_path = fixture["ledger_path"]
    before = event_path.read_bytes()
    arguments["wall_time_ns"] = lambda: 999_999_999

    with pytest.raises(
        evaluation.TrialEvaluationError,
        match="clock moved backwards",
    ):
        evaluation.evaluate_trial_packets(**arguments)

    assert event_path.read_bytes() == before


@pytest.mark.parametrize("mode", ["preparation", "future"])
def test_synthetic_attempt_failure_uses_allocation_to_current_wall_elapsed(
    tmp_path: Path,
    mode: str,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture, arguments = _arguments(
        tmp_path,
        executor=_SyntheticFailureExecutor(mode),
    )
    arguments["max_evaluator_attempts"] = 1
    arguments["wall_time_ns"] = _SequenceClock(
        1_000_000_000,
        1_006_999_999,
    )

    evaluation.evaluate_trial_packets(**arguments)

    replay = trial_ledger.replay_trial_evaluator_attempts(fixture["ledger_path"])
    [allocation] = replay.allocations
    [settlement] = replay.settlements
    assert allocation.payload["started_at_unix_ns"] == 1_000_000_000
    assert settlement.payload["status"] == (
        "preparation_failed" if mode == "preparation" else "provider_failed"
    )
    assert settlement.payload["duration_ms"] == 6


@pytest.mark.parametrize("mutation", ["missing", "negative"])
def test_evaluator_allocation_start_clock_is_closed_and_nonnegative(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture, arguments = _arguments(
        tmp_path,
        executor=_SuccessExecutor(()),
    )
    _append_active_allocation(
        fixture,
        arguments,
        started_at_unix_ns=1_000_000_000,
    )
    event_path = fixture["ledger_path"]

    def mutate(rows):
        allocation = next(
            row for row in rows if row["kind"] == "evaluator_attempt_allocated"
        )
        if mutation == "missing":
            allocation["payload"].pop("started_at_unix_ns")
        else:
            allocation["payload"]["started_at_unix_ns"] = -1

    _write_rechained(event_path, mutate)

    with pytest.raises(TrialLedgerError):
        load_trial_event_ledger(event_path)
