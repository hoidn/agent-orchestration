from __future__ import annotations

from pathlib import Path
import base64
import importlib
import json
import subprocess

import pytest

from orchestrator.workflow.adjudication import EvaluatorOutputError
import orchestrator.workflow.trial.ledger as trial_ledger
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.trial.ledger import TrialLedgerError, load_trial_event_ledger
from tests.test_workflow_trial_runtime import _CellHarnesses, _execute, _runtime_fixture


def test_evidence_freeze_is_one_durable_event_after_the_exact_terminal_domain(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _CellHarnesses())
    before = load_trial_event_ledger(execution.ledger_path)

    frozen = trial_ledger.append_trial_evidence_freeze(
        execution.ledger_path,
        expected_head_digest=before.rows[-1].row_digest,
    )

    after = load_trial_event_ledger(execution.ledger_path)
    assert after.rows[-1] == frozen
    assert frozen.kind == "evidence_frozen"
    assert [row["cell"] for row in frozen.payload["cell_evidence"]] == [
        cell.record for cell in fixture["request"].cell_domain
    ]
    assert all(
        row["terminal_row_digest"]
        in {ledger_row.row_digest for ledger_row in before.rows}
        for row in frozen.payload["cell_evidence"]
    )

    with pytest.raises(TrialLedgerError, match="already frozen"):
        trial_ledger.append_trial_evidence_freeze(
            execution.ledger_path,
            expected_head_digest=frozen.row_digest,
        )


def test_ensure_trial_evidence_freeze_reuses_existing_row(tmp_path: Path) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _CellHarnesses())

    frozen = evaluation.ensure_trial_evidence_freeze(execution.ledger_path)
    frozen_bytes = execution.ledger_path.read_bytes()
    resumed = evaluation.ensure_trial_evidence_freeze(execution.ledger_path)

    assert resumed == frozen
    assert execution.ledger_path.read_bytes() == frozen_bytes
    assert sum(
        row.kind == "evidence_frozen"
        for row in load_trial_event_ledger(execution.ledger_path).rows
    ) == 1


def test_post_freeze_cell_resume_ignores_the_non_cell_freeze_row(tmp_path: Path) -> None:
    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _CellHarnesses())
    before = load_trial_event_ledger(execution.ledger_path)
    trial_ledger.append_trial_evidence_freeze(
        execution.ledger_path,
        expected_head_digest=before.rows[-1].row_digest,
    )

    decisions = tuple(
        trial_ledger.classify_trial_cell_resume(
            execution.ledger_path,
            request=fixture["request"],
            cell=cell,
        )
        for cell in fixture["request"].cell_domain
    )

    assert {decision.action for decision in decisions} == {"reuse"}
    assert "append_trial_evidence_freeze" in trial_ledger.__all__


def test_checks_then_packets_freeze_header_order_and_reject_packet_tamper(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _CellHarnesses())
    before = load_trial_event_ledger(execution.ledger_path)
    evidence = trial_ledger.append_trial_evidence_freeze(
        execution.ledger_path,
        expected_head_digest=before.rows[-1].row_digest,
    )
    cells = [cell.record for cell in fixture["request"].cell_domain]
    check_records = [
        {"cell": cell, "check_result_digests": []} for cell in cells
    ]

    checks_frozen = trial_ledger.append_trial_checks_freeze(
        execution.ledger_path,
        expected_head_digest=evidence.row_digest,
        request=fixture["request"],
    )
    assert checks_frozen.kind == "checks_frozen"
    assert checks_frozen.payload == {
        "cell_checks": check_records,
        "check_set_digest": canonical_sha256(check_records),
    }

    header_labels = [
        binding["opaque_label"]
        for binding in load_trial_event_ledger(execution.ledger_path)
        .rows[0]
        .payload["sealed_opaque_label_map"]["bindings"]
    ]
    packet_records = [
        {
            "cell": cell,
            "opaque_label": header_labels[index],
            "packet_digest": canonical_sha256(
                {"cell": cell, "opaque_label": header_labels[index]}
            ),
        }
        for index, cell in enumerate(cells)
    ]
    packets_frozen = trial_ledger.append_trial_packets_freeze(
        execution.ledger_path,
        expected_head_digest=checks_frozen.row_digest,
        cell_packets=packet_records,
    )
    assert packets_frozen.kind == "packets_frozen"
    assert packets_frozen.payload == {
        "cell_packets": packet_records,
        "packet_set_digest": canonical_sha256(packet_records),
    }

    other = _runtime_fixture(tmp_path / "other")
    other_execution = _execute(other, _CellHarnesses())
    other_before = load_trial_event_ledger(other_execution.ledger_path)
    other_evidence = trial_ledger.append_trial_evidence_freeze(
        other_execution.ledger_path,
        expected_head_digest=other_before.rows[-1].row_digest,
    )
    other_checks = trial_ledger.append_trial_checks_freeze(
        other_execution.ledger_path,
        expected_head_digest=other_evidence.row_digest,
        request=other["request"],
    )

    tampered_packets = [dict(record) for record in packet_records]
    tampered_packets[0]["opaque_label"] = header_labels[1]
    with pytest.raises(TrialLedgerError, match="header opaque label"):
        trial_ledger.append_trial_packets_freeze(
            other_execution.ledger_path,
            expected_head_digest=other_checks.row_digest,
            cell_packets=tampered_packets,
        )


def _freeze_trial_packets_for_attempts(tmp_path: Path):
    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _CellHarnesses())
    before = load_trial_event_ledger(execution.ledger_path)
    evidence = trial_ledger.append_trial_evidence_freeze(
        execution.ledger_path,
        expected_head_digest=before.rows[-1].row_digest,
    )
    cells = list(fixture["request"].cell_domain)
    checks = trial_ledger.append_trial_checks_freeze(
        execution.ledger_path,
        expected_head_digest=evidence.row_digest,
        request=fixture["request"],
    )
    bindings = load_trial_event_ledger(execution.ledger_path).rows[0].payload[
        "sealed_opaque_label_map"
    ]["bindings"]
    packets = [
        {
            "cell": cell.record,
            "opaque_label": binding["opaque_label"],
            "packet_digest": canonical_sha256(
                {"cell": cell.record, "label": binding["opaque_label"]}
            ),
        }
        for cell, binding in zip(cells, bindings, strict=True)
    ]
    packet_freeze = trial_ledger.append_trial_packets_freeze(
        execution.ledger_path,
        expected_head_digest=checks.row_digest,
        cell_packets=packets,
    )
    scorer = trial_ledger.append_trial_scorer_freeze(
        execution.ledger_path,
        expected_head_digest=packet_freeze.row_digest,
        scorer_identity_digest="sha256:" + "d" * 64,
        snapshot_digest="sha256:" + "e" * 64,
    )
    return execution.ledger_path, packets, scorer


def _settle_trial_evaluator_attempt(
    path: Path,
    allocation,
    *,
    status: str,
    score_row_content_digest: str | None,
):
    return trial_ledger.append_trial_evaluator_attempt_settlement(
        path,
        expected_head_digest=load_trial_event_ledger(path).rows[-1].row_digest,
        allocation_row_digest=allocation.row_digest,
        opaque_label=allocation.payload["opaque_label"],
        local_attempt=allocation.payload["local_attempt"],
        global_attempt=allocation.payload["global_attempt"],
        status=status,
        exit_code=0,
        duration_ms=7,
        token_usage={"variant": "UNKNOWN"},
        cost={"variant": "UNKNOWN"},
        stdout_digest="sha256:" + "1" * 64,
        stderr_digest="sha256:" + "2" * 64,
        output_digest=(
            None if status == "preparation_failed" else "sha256:" + "3" * 64
        ),
        score_row_content_digest=score_row_content_digest,
    )


def test_evaluator_attempt_ledger_replays_invalid_retry_scored_and_second_label(
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
    invalid = _settle_trial_evaluator_attempt(
        path,
        first,
        status="output_invalid",
        score_row_content_digest=None,
    )
    retry = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=invalid.row_digest,
        opaque_label=packets[0]["opaque_label"],
        local_attempt=2,
        global_attempt=2,
        packet_digest=packets[0]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=1_000_000_000,
    )
    first_score_digest = "sha256:" + "4" * 64
    _settle_trial_evaluator_attempt(
        path,
        retry,
        status="scored",
        score_row_content_digest=first_score_digest,
    )
    second = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=load_trial_event_ledger(path).rows[-1].row_digest,
        opaque_label=packets[1]["opaque_label"],
        local_attempt=1,
        global_attempt=3,
        packet_digest=packets[1]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=1_000_000_000,
    )
    second_score_digest = "sha256:" + "5" * 64
    second_settlement = _settle_trial_evaluator_attempt(
        path,
        second,
        status="scored",
        score_row_content_digest=second_score_digest,
    )
    score_digests = [first_score_digest, second_score_digest]
    for packet_index, packet in enumerate(packets[2:], start=2):
        allocation = trial_ledger.append_trial_evaluator_attempt_allocation(
            path,
            expected_head_digest=load_trial_event_ledger(path).rows[-1].row_digest,
            opaque_label=packet["opaque_label"],
            local_attempt=1,
            global_attempt=packet_index + 2,
            packet_digest=packet["packet_digest"],
            scorer_frozen_row_digest=scorer.row_digest,
            started_at_unix_ns=1_000_000_000,
        )
        score_digest = "sha256:" + format(packet_index + 4, "x") * 64
        score_digests.append(score_digest)
        second_settlement = _settle_trial_evaluator_attempt(
            path,
            allocation,
            status="scored",
            score_row_content_digest=score_digest,
        )

    replay = trial_ledger.replay_trial_evaluator_attempts(path)
    assert replay.charged_attempt_count == len(packets) + 1
    assert replay.active_allocations == ()
    assert [row.payload["global_attempt"] for row in replay.allocations] == list(
        range(1, len(packets) + 2)
    )
    assert [row.payload["status"] for row in replay.settlements] == [
        "output_invalid",
        *("scored" for _packet in packets),
    ]

    attempt_score_settlements = [
        row
        for row in replay.settlements
        if row.payload["score_row_content_digest"] is not None
    ]
    score_settlements = []
    for packet, attempt_settlement, score_digest in zip(
        packets,
        attempt_score_settlements,
        score_digests,
        strict=True,
    ):
        score_settlements.append(
            trial_ledger.append_trial_score_settlement(
                path,
                expected_head_digest=load_trial_event_ledger(path).rows[-1].row_digest,
                opaque_label=packet["opaque_label"],
                score_row_content_digest=score_digest,
                terminal_attempt_settlement_row_digest=attempt_settlement.row_digest,
            )
        )
    frozen = trial_ledger.append_trial_scores_freeze(
        path,
        expected_head_digest=score_settlements[-1].row_digest,
    )
    expected_scores = [
        {
            "opaque_label": packet["opaque_label"],
            "score_settlement_row_digest": settlement.row_digest,
            "score_row_content_digest": score_digest,
        }
        for packet, settlement, score_digest in zip(
            packets,
            score_settlements,
            score_digests,
            strict=True,
        )
    ]
    assert frozen.payload == {
        "scores": expected_scores,
        "score_set_digest": canonical_sha256(expected_scores),
    }


def test_evaluator_allocation_without_settlement_is_reloaded_and_charged(
    tmp_path: Path,
) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)
    allocation = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=scorer.row_digest,
        opaque_label=packets[0]["opaque_label"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=packets[0]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=1_000_000_000,
    )

    replay = trial_ledger.replay_trial_evaluator_attempts(path)

    assert replay.charged_attempt_count == 1
    assert replay.allocations == (allocation,)
    assert replay.active_allocations == (allocation,)
    assert replay.settlements == ()
    with pytest.raises(TrialLedgerError, match="active evaluator attempt"):
        trial_ledger.append_trial_evaluator_attempt_allocation(
            path,
            expected_head_digest=allocation.row_digest,
            opaque_label=packets[0]["opaque_label"],
            local_attempt=2,
            global_attempt=2,
            packet_digest=packets[0]["packet_digest"],
            scorer_frozen_row_digest=scorer.row_digest,
            started_at_unix_ns=1_000_000_000,
        )


@pytest.mark.parametrize(
    ("label_index", "local_attempt", "global_attempt", "match"),
    [
        (0, 2, 1, "local attempt"),
        (0, 1, 2, "global attempt"),
        (1, 2, 1, "local attempt"),
    ],
)
def test_evaluator_attempt_allocation_rejects_gapped_local_or_global_ordinals(
    tmp_path: Path,
    label_index: int,
    local_attempt: int,
    global_attempt: int,
    match: str,
) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)

    with pytest.raises(TrialLedgerError, match=match):
        trial_ledger.append_trial_evaluator_attempt_allocation(
            path,
            expected_head_digest=scorer.row_digest,
            opaque_label=packets[label_index]["opaque_label"],
            local_attempt=local_attempt,
            global_attempt=global_attempt,
            packet_digest=packets[label_index]["packet_digest"],
            scorer_frozen_row_digest=scorer.row_digest,
            started_at_unix_ns=1_000_000_000,
        )


def test_evaluator_attempts_reject_wrong_domain_packet_scorer_and_settlement_ref(
    tmp_path: Path,
) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)
    common = {
        "path": path,
        "expected_head_digest": scorer.row_digest,
        "opaque_label": packets[0]["opaque_label"],
        "local_attempt": 1,
        "global_attempt": 1,
        "packet_digest": packets[0]["packet_digest"],
        "scorer_frozen_row_digest": scorer.row_digest,
        "started_at_unix_ns": 1_000_000_000,
    }
    for changed, match in (
        ({"opaque_label": "opaque-" + "f" * 64}, "packet domain"),
        ({"packet_digest": "sha256:" + "f" * 64}, "packet digest"),
        ({"scorer_frozen_row_digest": "sha256:" + "f" * 64}, "scorer"),
    ):
        with pytest.raises(TrialLedgerError, match=match):
            trial_ledger.append_trial_evaluator_attempt_allocation(
                **{**common, **changed}
            )

    allocation = trial_ledger.append_trial_evaluator_attempt_allocation(**common)
    with pytest.raises(TrialLedgerError, match="allocation row"):
        trial_ledger.append_trial_evaluator_attempt_settlement(
            path,
            expected_head_digest=allocation.row_digest,
            allocation_row_digest="sha256:" + "f" * 64,
            opaque_label=allocation.payload["opaque_label"],
            local_attempt=1,
            global_attempt=1,
            status="provider_failed",
            exit_code=1,
            duration_ms=4,
            token_usage={"variant": "UNKNOWN"},
            cost={"variant": "UNKNOWN"},
            stdout_digest="sha256:" + "1" * 64,
            stderr_digest="sha256:" + "2" * 64,
            output_digest=None,
            score_row_content_digest=None,
        )


def test_scores_freeze_rejects_active_or_missing_score_rows(tmp_path: Path) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)
    active = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=scorer.row_digest,
        opaque_label=packets[0]["opaque_label"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=packets[0]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=1_000_000_000,
    )
    with pytest.raises(TrialLedgerError, match="active evaluator attempt"):
        trial_ledger.append_trial_scores_freeze(
            path,
            expected_head_digest=active.row_digest,
        )

    settled = _settle_trial_evaluator_attempt(
        path,
        active,
        status="output_invalid",
        score_row_content_digest=None,
    )
    with pytest.raises(TrialLedgerError, match="score settlement"):
        trial_ledger.append_trial_scores_freeze(
            path,
            expected_head_digest=settled.row_digest,
        )


def test_score_settlement_records_explicit_zero_attempt_exhaustion(
    tmp_path: Path,
) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)
    settlements = []
    for index, packet in enumerate(packets, start=1):
        score_digest = "sha256:" + format(index, "x") * 64
        settlements.append(
            trial_ledger.append_trial_score_settlement(
                path,
                expected_head_digest=load_trial_event_ledger(path).rows[-1].row_digest,
                opaque_label=packet["opaque_label"],
                score_row_content_digest=score_digest,
                terminal_attempt_settlement_row_digest=None,
            )
        )

    assert settlements[0].kind == "score_settled"
    assert settlements[0].payload == {
        "opaque_label": packets[0]["opaque_label"],
        "score_row_content_digest": "sha256:" + "1" * 64,
        "terminal_attempt_settlement_row_digest": None,
    }
    frozen = trial_ledger.append_trial_scores_freeze(
        path,
        expected_head_digest=settlements[-1].row_digest,
    )
    assert frozen.payload["scores"] == [
        {
            "opaque_label": packet["opaque_label"],
            "score_settlement_row_digest": settlement.row_digest,
            "score_row_content_digest": settlement.payload[
                "score_row_content_digest"
            ],
        }
        for packet, settlement in zip(packets, settlements, strict=True)
    ]


def test_score_settlement_rejects_duplicate_wrong_reference_and_domain(
    tmp_path: Path,
) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)
    allocation = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=scorer.row_digest,
        opaque_label=packets[0]["opaque_label"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=packets[0]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=1_000_000_000,
    )
    score_digest = "sha256:" + "7" * 64
    attempt_settlement = _settle_trial_evaluator_attempt(
        path,
        allocation,
        status="scored",
        score_row_content_digest=score_digest,
    )
    common = {
        "path": path,
        "expected_head_digest": attempt_settlement.row_digest,
        "opaque_label": packets[0]["opaque_label"],
        "score_row_content_digest": score_digest,
        "terminal_attempt_settlement_row_digest": attempt_settlement.row_digest,
    }
    for changed, match in (
        ({"opaque_label": "opaque-" + "f" * 64}, "packet domain"),
        ({"opaque_label": packets[1]["opaque_label"]}, "attempt domain"),
        ({"score_row_content_digest": "sha256:" + "8" * 64}, "score authority"),
        (
            {"terminal_attempt_settlement_row_digest": "sha256:" + "9" * 64},
            "reference is unknown",
        ),
    ):
        with pytest.raises(TrialLedgerError, match=match):
            trial_ledger.append_trial_score_settlement(**{**common, **changed})

    settled = trial_ledger.append_trial_score_settlement(**common)
    with pytest.raises(TrialLedgerError, match="already has a score settlement"):
        trial_ledger.append_trial_score_settlement(
            **{**common, "expected_head_digest": settled.row_digest}
        )


def test_score_settlement_without_attempt_reference_rejects_attempted_label(
    tmp_path: Path,
) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)
    allocation = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=scorer.row_digest,
        opaque_label=packets[0]["opaque_label"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=packets[0]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=1_000_000_000,
    )

    with pytest.raises(TrialLedgerError, match="zero-attempt"):
        trial_ledger.append_trial_score_settlement(
            path,
            expected_head_digest=allocation.row_digest,
            opaque_label=packets[0]["opaque_label"],
            score_row_content_digest="sha256:" + "a" * 64,
            terminal_attempt_settlement_row_digest=None,
        )


def test_score_settlement_binds_exhausted_attempt_without_score_authority(
    tmp_path: Path,
) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)
    allocation = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=scorer.row_digest,
        opaque_label=packets[0]["opaque_label"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=packets[0]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=1_000_000_000,
    )
    attempt_settlement = _settle_trial_evaluator_attempt(
        path,
        allocation,
        status="output_invalid",
        score_row_content_digest=None,
    )

    score_settlement = trial_ledger.append_trial_score_settlement(
        path,
        expected_head_digest=attempt_settlement.row_digest,
        opaque_label=packets[0]["opaque_label"],
        score_row_content_digest="sha256:" + "a" * 64,
        terminal_attempt_settlement_row_digest=attempt_settlement.row_digest,
    )

    assert score_settlement.payload["terminal_attempt_settlement_row_digest"] == (
        attempt_settlement.row_digest
    )


def test_evaluator_attempt_ledger_rejects_duplicate_settlement_and_tampered_row(
    tmp_path: Path,
) -> None:
    path, packets, scorer = _freeze_trial_packets_for_attempts(tmp_path)
    allocation = trial_ledger.append_trial_evaluator_attempt_allocation(
        path,
        expected_head_digest=scorer.row_digest,
        opaque_label=packets[0]["opaque_label"],
        local_attempt=1,
        global_attempt=1,
        packet_digest=packets[0]["packet_digest"],
        scorer_frozen_row_digest=scorer.row_digest,
        started_at_unix_ns=1_000_000_000,
    )
    settlement = _settle_trial_evaluator_attempt(
        path,
        allocation,
        status="provider_failed",
        score_row_content_digest=None,
    )
    with pytest.raises(TrialLedgerError, match="already settled"):
        _settle_trial_evaluator_attempt(
            path,
            allocation,
            status="provider_failed",
            score_row_content_digest=None,
        )

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[-1]["payload"]["global_attempt"] = 99
    path.write_text(
        "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows)
        + "\n"
    )
    with pytest.raises(TrialLedgerError, match="row digest"):
        load_trial_event_ledger(path)


def test_trial_checks_use_authority_then_authored_order_and_literal_argv(
    tmp_path: Path,
) -> None:
    checks_module = importlib.import_module("orchestrator.workflow.trial.checks")
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def runner(argv, **kwargs):
        calls.append((tuple(argv), dict(kwargs)))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=b"complete stdout",
            stderr=b"complete stderr",
        )

    checks = (
        {
            "check_id": "invariant-a",
            "command": ["python", "invariant.py"],
            "authority": "invariant",
            "required": False,
            "timeout_ms": 2_000,
        },
        {
            "check_id": "correctness-a",
            "command": ["python", "-m", "pytest", "tests/a.py"],
            "authority": "correctness",
            "required": True,
            "timeout_ms": 1_000,
        },
        {
            "check_id": "correctness-b",
            "command": ["python", "check_b.py"],
            "authority": "correctness",
            "required": True,
            "timeout_ms": 1_500,
        },
    )
    cwd = tmp_path.resolve()

    results = checks_module.run_trial_checks(
        checks,
        cwd=cwd,
        evidence_frozen_digest="sha256:" + "a" * 64,
        max_output_bytes=64,
        runner=runner,
    )

    assert [result.check_id for result in results] == [
        "correctness-a",
        "correctness-b",
        "invariant-a",
    ]
    assert [argv for argv, _kwargs in calls] == [
        ("python", "-m", "pytest", "tests/a.py"),
        ("python", "check_b.py"),
        ("python", "invariant.py"),
    ]
    assert all(kwargs["cwd"] == cwd for _argv, kwargs in calls)
    assert all(kwargs["shell"] is False for _argv, kwargs in calls)


def test_trial_check_output_keeps_complete_digests_and_bounds_each_stream(
    tmp_path: Path,
) -> None:
    checks_module = importlib.import_module("orchestrator.workflow.trial.checks")
    check = {
        "check_id": "correctness",
        "command": ["python", "check.py"],
        "authority": "correctness",
        "required": True,
        "timeout_ms": 1_000,
    }

    def runner(argv, **_kwargs):
        return subprocess.CompletedProcess(
            argv,
            3,
            stdout=b"abcdef",
            stderr=b"WXYZ12",
        )

    [result] = checks_module.run_trial_checks(
        (check,),
        cwd=tmp_path.resolve(),
        evidence_frozen_digest="sha256:" + "b" * 64,
        max_output_bytes=4,
        runner=runner,
    )

    assert result.status == "COMPLETED"
    assert result.exit_code == 3
    assert result.stdout_bytes == b"abcd"
    assert result.stderr_bytes == b"WXYZ"
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True
    output = json.loads(result.output_bytes)
    assert base64.b64decode(output["stdout_base64"]) == b"abcd"
    assert base64.b64decode(output["stderr_base64"]) == b"WXYZ"
    assert output["stdout_size_bytes"] == 6
    assert output["stderr_size_bytes"] == 6
    assert result.output_digest == canonical_sha256(
        {
            "schema_version": "trial_check_output_identity.v1",
            "stdout_digest": (
                "sha256:bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721"
            ),
            "stdout_size_bytes": 6,
            "stderr_digest": (
                "sha256:b3a064d811e98ff021b90e2b06f2f71f606c53016abc342902b9dc7641c55b71"
            ),
            "stderr_size_bytes": 6,
        }
    )


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_stdout"),
    [
        (
            subprocess.TimeoutExpired(
                ["python", "check.py"],
                1.0,
                output=b"timeout-out",
                stderr=b"timeout-err",
            ),
            "TIMED_OUT",
            b"timeout",
        ),
        (OSError("fixture launch failed"), "LAUNCH_FAILED", b""),
    ],
)
def test_trial_check_timeout_and_launch_failure_are_closed_results(
    tmp_path: Path,
    error: BaseException,
    expected_status: str,
    expected_stdout: bytes,
) -> None:
    checks_module = importlib.import_module("orchestrator.workflow.trial.checks")

    def runner(_argv, **_kwargs):
        raise error

    [result] = checks_module.run_trial_checks(
        (
            {
                "check_id": "correctness",
                "command": ["python", "check.py"],
                "authority": "correctness",
                "required": True,
                "timeout_ms": 1_000,
            },
        ),
        cwd=tmp_path.resolve(),
        evidence_frozen_digest="sha256:" + "c" * 64,
        max_output_bytes=7,
        runner=runner,
    )

    assert result.status == expected_status
    assert result.exit_code is None
    assert result.stdout_bytes == expected_stdout
    assert result.output_digest.startswith("sha256:")
    assert set(result.record) == {
        "check_id",
        "authority",
        "required",
        "status",
        "exit_code",
        "duration_ms",
        "output_digest",
        "output_bytes",
    }


def test_trial_packet_is_closed_blinded_and_citable() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    opaque_label = "opaque-" + "1" * 64

    packet = packets.build_trial_evaluation_packet(
        opaque_label=opaque_label,
        observation_include=(
            "task_spec",
            "validated_result",
            "workspace_delta",
            "check_results",
            "declared_artifacts",
            "failure_evidence",
        ),
        observations={
            "task_spec": {"objective": "judge the bounded evidence"},
            "validated_result": {"approved": True},
            "workspace_delta": {
                "changed_files": [{"path": "src/example.py"}],
                "deleted_files": [],
                "untracked_files": [],
                "normalized_diff": {
                    "entries": [
                        {"path": "src/example.py", "text": "+return True\n"}
                    ],
                    "truncated": False,
                },
                "declared_artifacts": [
                    {"name": "report", "path": "artifacts/report.md"}
                ],
            },
            "check_results": [{"check_id": "unit", "status": "COMPLETED"}],
            "declared_artifacts": [
                {"name": "report", "path": "artifacts/report.md"}
            ],
        },
        sealed_identity_values=(
            "TREATMENT-A",
            "secret-workflow.orc",
            "secret-provider-model",
        ),
        max_item_bytes=4096,
        max_packet_bytes=16384,
    )

    assert packet == {
        "schema": "trial.evaluation_packet.v1",
        "evaluation_id": opaque_label,
        "items": [
            {"id": name, "kind": name, "value": packet["items"][index]["value"]}
            for index, name in enumerate(
                (
                    "task_spec",
                    "validated_result",
                    "workspace_delta",
                    "check_results",
                    "declared_artifacts",
                )
            )
        ],
        "citable_item_ids": [
            "task_spec",
            "validated_result",
            "workspace_delta",
            "check_results",
            "declared_artifacts",
        ],
    }
    encoded = json.dumps(
        packet,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert "TREATMENT-A" not in encoded
    assert "secret-workflow.orc" not in encoded
    assert "secret-provider-model" not in encoded
    assert ".orchestrate" not in encoded


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"observation_include": ("task_spec", "task_spec")}, "trial_packet_policy_invalid"),
        (
            {
                "observations": {
                    "task_spec": {"objective": "judge"},
                    "provider_identity": "provider-a",
                }
            },
            "trial_packet_policy_invalid",
        ),
        (
            {"observations": {"task_spec": {"objective": "SECRET-ARM"}}},
            "trial_blinding_policy_invalid",
        ),
        (
            {
                "observations": {
                    "task_spec": {"state": ".orchestrate/runs/one/state.json"}
                }
            },
            "trial_blinding_policy_invalid",
        ),
        (
            {"observations": {"task_spec": {"score": float("nan")}}},
            "trial_packet_policy_invalid",
        ),
        ({"max_item_bytes": 100, "max_packet_bytes": 99}, "trial_packet_limit_invalid"),
    ],
)
def test_trial_packet_rejects_malformed_excluded_and_duplicate_evidence(
    change: dict[str, object],
    code: str,
) -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    arguments: dict[str, object] = {
        "opaque_label": "opaque-" + "2" * 64,
        "observation_include": ("task_spec",),
        "observations": {"task_spec": {"objective": "judge"}},
        "sealed_identity_values": ("SECRET-ARM", "secret-provider"),
        "max_item_bytes": 1024,
        "max_packet_bytes": 4096,
    }
    arguments.update(change)

    with pytest.raises(packets.TrialPacketError) as exc_info:
        packets.build_trial_evaluation_packet(**arguments)

    assert exc_info.value.code == code


def test_trial_packet_enforces_item_then_complete_packet_canonical_byte_caps() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    arguments = {
        "opaque_label": "opaque-" + "3" * 64,
        "observation_include": ("task_spec", "check_results"),
        "observations": {
            "task_spec": {"objective": "x" * 64},
            "check_results": [{"check_id": "unit", "status": "COMPLETED"}],
        },
        "sealed_identity_values": ("SECRET-ARM",),
    }
    with pytest.raises(packets.TrialPacketError) as item_exc:
        packets.build_trial_evaluation_packet(
            **arguments,
            max_item_bytes=32,
            max_packet_bytes=4096,
        )
    assert item_exc.value.code == "trial_packet_limit_invalid"

    uncapped = packets.build_trial_evaluation_packet(
        **arguments,
        max_item_bytes=1024,
        max_packet_bytes=4096,
    )
    packet_size = len(
        json.dumps(
            uncapped,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    with pytest.raises(packets.TrialPacketError) as packet_exc:
        packets.build_trial_evaluation_packet(
            **arguments,
            max_item_bytes=1024,
            max_packet_bytes=packet_size - 1,
        )
    assert packet_exc.value.code == "trial_packet_limit_invalid"


def test_trial_packet_rejects_fixed_identity_metadata_even_if_not_sealed_by_value() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")

    with pytest.raises(packets.TrialPacketError) as exc_info:
        packets.build_trial_evaluation_packet(
            opaque_label="opaque-" + "4" * 64,
            observation_include=("validated_result",),
            observations={
                "validated_result": {
                    "approved": True,
                    "provider_model": "identity-not-listed-by-caller",
                }
            },
            sealed_identity_values=("SECRET-ARM",),
            max_item_bytes=1024,
            max_packet_bytes=4096,
        )

    assert exc_info.value.code == "trial_blinding_policy_invalid"


def test_trial_evaluator_output_is_exact_and_citations_resolve_in_its_packet() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    packet = packets.build_trial_evaluation_packet(
        opaque_label="opaque-" + "5" * 64,
        observation_include=("task_spec", "check_results"),
        observations={
            "task_spec": {"objective": "judge"},
            "check_results": [{"check_id": "unit", "status": "COMPLETED"}],
        },
        sealed_identity_values=("SECRET-ARM",),
        max_item_bytes=1024,
        max_packet_bytes=4096,
    )

    parsed = packets.parse_trial_evaluator_output(
        json.dumps(
            {
                "candidate_id": packet["evaluation_id"],
                "score": 0.75,
                "summary": "bounded evidence supports the result",
                "citations": ["task_spec", "check_results"],
            }
        ),
        packet=packet,
    )

    assert parsed == {
        "candidate_id": packet["evaluation_id"],
        "score": 0.75,
        "summary": "bounded evidence supports the result",
        "citations": ["task_spec", "check_results"],
    }


def test_trial_packet_rejects_an_uncitable_empty_evidence_set() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")

    with pytest.raises(packets.TrialPacketError) as exc_info:
        packets.build_trial_evaluation_packet(
            opaque_label="opaque-" + "6" * 64,
            observation_include=(),
            observations={},
            sealed_identity_values=("SECRET-ARM",),
            max_item_bytes=1024,
            max_packet_bytes=4096,
        )

    assert exc_info.value.code == "trial_packet_citation_invalid"


def test_trial_scorer_identity_binds_trial_schemas_and_all_resolved_policy() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    scoring = importlib.import_module("orchestrator.workflow.adjudication.scoring")
    scorer = {
        "evaluator_provider": "judge",
        "evaluator_params": {"model": "fixed", "temperature": 0},
        "evaluator_prompt_source_kind": "asset",
        "evaluator_prompt_source": "prompts/judge.md",
        "evaluator_prompt_hash": "sha256:" + "1" * 64,
        "rubric_source_kind": "asset",
        "rubric_source": "rubrics/quality.md",
        "rubric_hash": "sha256:" + "2" * 64,
        "evidence_limits": {"max_item_bytes": 1024, "max_packet_bytes": 4096},
        "evidence_confidentiality": "same_trust_boundary",
    }

    identity = packets.trial_scorer_identity_hash(scorer)

    assert identity.startswith("sha256:")
    assert identity != scoring.scorer_identity_hash(scorer)
    for changed in (
        {**scorer, "evaluator_provider": "other"},
        {**scorer, "evaluator_prompt_hash": "sha256:" + "3" * 64},
        {**scorer, "rubric_hash": "sha256:" + "4" * 64},
        {
            **scorer,
            "evidence_limits": {"max_item_bytes": 1024, "max_packet_bytes": 8192},
        },
        {**scorer, "evidence_confidentiality": "different"},
    ):
        assert packets.trial_scorer_identity_hash(changed) != identity


def test_production_trial_scorer_uses_only_the_versioned_platform_instruction(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _runtime_fixture(tmp_path)
    request = fixture["request"]
    resolved = request.static_config.evaluation
    scorer_config = evaluation.build_trial_scorer_config(request)

    assert scorer_config == {
        "provider": resolved["provider"],
        "provider_params": {},
        "evaluator_prompt_source": {
            "platform_instruction": evaluation.TRIAL_EVALUATOR_INSTRUCTION_ID,
        },
        "rubric_source": {"asset_file": resolved["rubric_asset"]},
        "evidence_limits": {
            "max_item_bytes": resolved["max_item_bytes"],
            "max_packet_bytes": resolved["max_packet_bytes"],
        },
        "evidence_confidentiality": "same_trust_boundary",
    }

    class Registry:
        def exists(self, name: str) -> bool:
            return name == resolved["provider"]

        def merge_params(self, name: str, params: dict[str, object]):
            assert name == resolved["provider"]
            assert params == {}
            return {"model": "registry-owned"}

    class Composer:
        def __init__(self) -> None:
            self.calls: list[tuple[dict[str, str], str]] = []

        def read_prompt_source(self, step, *, step_name, contract_violation_result):
            self.calls.append((dict(step), step_name))
            return "resolved rubric", None

    composer = Composer()
    scorer, instruction, rubric = evaluation._resolve_scorer(
        scorer_config=scorer_config,
        provider_registry=Registry(),
        prompt_composer=composer,
    )

    assert instruction == evaluation.TRIAL_EVALUATOR_INSTRUCTION
    assert rubric == "resolved rubric"
    assert composer.calls == [
        ({"asset_file": resolved["rubric_asset"]}, "trial_evaluator_rubric")
    ]
    assert scorer["evaluator_prompt_source_kind"] == "platform_instruction"
    assert (
        scorer["evaluator_prompt_source"]
        == evaluation.TRIAL_EVALUATOR_INSTRUCTION_ID
    )

    with pytest.raises(
        evaluation.TrialEvaluationError,
        match="platform instruction is invalid",
    ):
        evaluation._resolve_scorer(
            scorer_config={
                **scorer_config,
                "evaluator_prompt_source": {
                    "platform_instruction": "trial_evaluator_instruction.v2",
                },
            },
            provider_registry=Registry(),
            prompt_composer=composer,
        )


@pytest.mark.parametrize(
    "document",
    [
        [],
        {
            "candidate_id": "opaque-placeholder",
            "score": 0.5,
            "summary": "ok",
        },
        {
            "candidate_id": "opaque-placeholder",
            "score": 0.5,
            "summary": "ok",
            "citations": [],
            "extra": True,
        },
        {
            "candidate_id": "opaque-wrong",
            "score": 0.5,
            "summary": "ok",
            "citations": [],
        },
        {
            "candidate_id": "opaque-placeholder",
            "score": True,
            "summary": "ok",
            "citations": [],
        },
        {
            "candidate_id": "opaque-placeholder",
            "score": 1.01,
            "summary": "ok",
            "citations": [],
        },
        {
            "candidate_id": "opaque-placeholder",
            "score": 0.5,
            "summary": "  ",
            "citations": [],
        },
        {
            "candidate_id": "opaque-placeholder",
            "score": 0.5,
            "summary": "ok",
            "citations": "task_spec",
        },
    ],
)
def test_trial_evaluator_output_rejects_nonclosed_or_invalid_score_objects(
    document: object,
) -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    packet = packets.build_trial_evaluation_packet(
        opaque_label="opaque-" + "7" * 64,
        observation_include=("task_spec",),
        observations={"task_spec": {"objective": "judge"}},
        sealed_identity_values=("SECRET-ARM",),
        max_item_bytes=1024,
        max_packet_bytes=4096,
    )
    if isinstance(document, dict) and document.get("candidate_id") == "opaque-placeholder":
        document = {**document, "candidate_id": packet["evaluation_id"]}

    with pytest.raises(EvaluatorOutputError):
        packets.parse_trial_evaluator_output(json.dumps(document), packet=packet)


def test_trial_evaluator_output_rejects_duplicate_fields_and_cross_packet_citation() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    packet = packets.build_trial_evaluation_packet(
        opaque_label="opaque-" + "8" * 64,
        observation_include=("task_spec",),
        observations={"task_spec": {"objective": "judge"}},
        sealed_identity_values=("SECRET-ARM",),
        max_item_bytes=1024,
        max_packet_bytes=4096,
    )
    duplicate = (
        '{"candidate_id":"'
        + packet["evaluation_id"]
        + '","score":0.1,"score":0.9,"summary":"ok","citations":[]}'
    )
    with pytest.raises(EvaluatorOutputError, match="duplicate"):
        packets.parse_trial_evaluator_output(duplicate, packet=packet)

    with pytest.raises(packets.TrialPacketError) as exc_info:
        packets.parse_trial_evaluator_output(
            json.dumps(
                {
                    "candidate_id": packet["evaluation_id"],
                    "score": 0.5,
                    "summary": "cites evidence from another packet",
                    "citations": ["failure_evidence"],
                }
            ),
            packet=packet,
        )
    assert exc_info.value.code == "trial_packet_citation_invalid"


def test_trial_packet_validation_rejects_duplicate_or_forged_citable_ids() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    packet = packets.build_trial_evaluation_packet(
        opaque_label="opaque-" + "9" * 64,
        observation_include=("task_spec",),
        observations={"task_spec": {"objective": "judge"}},
        sealed_identity_values=("SECRET-ARM",),
        max_item_bytes=1024,
        max_packet_bytes=4096,
    )
    duplicate = {
        **packet,
        "items": [packet["items"][0], packet["items"][0]],
        "citable_item_ids": ["task_spec", "task_spec"],
    }
    with pytest.raises(packets.TrialPacketError) as duplicate_exc:
        packets.validate_trial_evaluation_packet(duplicate)
    assert duplicate_exc.value.code == "trial_packet_policy_invalid"

    forged = {**packet, "citable_item_ids": ["failure_evidence"]}
    with pytest.raises(packets.TrialPacketError) as forged_exc:
        packets.validate_trial_evaluation_packet(forged)
    assert forged_exc.value.code == "trial_packet_citation_invalid"


@pytest.mark.parametrize("path", ["../escape.py", "/absolute.py", "a/../escape.py", "a\\b.py"])
def test_trial_packet_rejects_non_normalized_workspace_evidence_paths(path: str) -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")

    with pytest.raises(packets.TrialPacketError) as exc_info:
        packets.build_trial_evaluation_packet(
            opaque_label="opaque-" + "a" * 64,
            observation_include=("workspace_delta",),
            observations={
                "workspace_delta": {
                    "changed_files": [{"path": path}],
                    "deleted_files": [],
                    "untracked_files": [],
                    "normalized_diff": {"entries": [], "truncated": False},
                    "declared_artifacts": [],
                }
            },
            sealed_identity_values=("SECRET-ARM",),
            max_item_bytes=1024,
            max_packet_bytes=4096,
        )

    assert exc_info.value.code == "trial_packet_policy_invalid"


def test_trial_packet_rejects_workspace_base_source_identity() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")

    with pytest.raises(packets.TrialPacketError) as exc_info:
        packets.build_trial_evaluation_packet(
            opaque_label="opaque-" + "b" * 64,
            observation_include=("workspace_delta",),
            observations={
                "workspace_delta": {
                    "base": {
                        "normalized_locator": "https://example.invalid/private.git",
                        "resolved_commit_sha": "1" * 40,
                    },
                    "changed_files": [],
                    "deleted_files": [],
                    "untracked_files": [],
                    "normalized_diff": {"entries": [], "truncated": False},
                    "declared_artifacts": [],
                }
            },
            sealed_identity_values=("SECRET-ARM",),
            max_item_bytes=2048,
            max_packet_bytes=4096,
        )

    assert exc_info.value.code == "trial_blinding_policy_invalid"


def test_trial_packet_blinding_compares_semantic_strings_not_json_escapes() -> None:
    packets = importlib.import_module("orchestrator.workflow.trial.packets")
    sealed = 'SECRET"ARM'

    with pytest.raises(packets.TrialPacketError) as exc_info:
        packets.build_trial_evaluation_packet(
            opaque_label="opaque-" + "c" * 64,
            observation_include=("task_spec",),
            observations={"task_spec": {"objective": f"evaluate {sealed} now"}},
            sealed_identity_values=(sealed,),
            max_item_bytes=1024,
            max_packet_bytes=4096,
        )

    assert exc_info.value.code == "trial_blinding_policy_invalid"


def _durable_evaluator_fixture(tmp_path: Path):
    packets_module = importlib.import_module("orchestrator.workflow.trial.packets")
    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _CellHarnesses())
    ledger_path = execution.ledger_path
    terminal = load_trial_event_ledger(ledger_path)
    evidence_frozen = trial_ledger.append_trial_evidence_freeze(
        ledger_path,
        expected_head_digest=terminal.rows[-1].row_digest,
    )
    cells = tuple(fixture["request"].cell_domain)
    checks_frozen = trial_ledger.append_trial_checks_freeze(
        ledger_path,
        expected_head_digest=evidence_frozen.row_digest,
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
        for cell, binding, packet in zip(cells, bindings, packets, strict=True)
    ]
    packets_frozen = trial_ledger.append_trial_packets_freeze(
        ledger_path,
        expected_head_digest=checks_frozen.row_digest,
        cell_packets=packet_records,
    )
    return {
        "runtime": fixture,
        "execution": execution,
        "ledger_path": ledger_path,
        "evidence_frozen": evidence_frozen,
        "checks_frozen": checks_frozen,
        "packets": packets,
        "packets_frozen": packets_frozen,
    }


def test_trial_evaluator_retries_invalid_output_and_persists_closed_score_row(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _durable_evaluator_fixture(tmp_path / "trial")
    packets = fixture["packets"]
    labels = tuple(packet["evaluation_id"] for packet in packets)

    class Registry:
        def exists(self, name: str) -> bool:
            return name == "judge"

        def merge_params(self, name: str, params: dict[str, object]):
            assert name == "judge"
            return {"model": "fixed", **params}

    class Composer:
        def read_prompt_source(self, step, *, step_name, contract_violation_result):
            assert step_name in {"trial_evaluator_prompt", "trial_evaluator_rubric"}
            return ("judge exactly" if "input_file" in step else "quality rubric"), None

    class Executor:
        def __init__(self) -> None:
            self.prepared: list[object] = []
            self.attempts: dict[str, int] = {}

        def prepare_invocation(self, provider_name, params, context, **kwargs):
            assert provider_name == "judge"
            assert params.params == {"model": "fixed", "temperature": 0}
            assert context == {}
            self.prepared.append(kwargs["prompt_content"])
            [label] = [
                label for label in labels if label in kwargs["prompt_content"]
            ]
            return label, None

        def execute(self, label, *, cwd):
            from orchestrator.providers.executor import ProviderExecutionResult

            self.attempts[label] = self.attempts.get(label, 0) + 1
            if label == labels[0] and self.attempts[label] == 1:
                stdout = b'{"candidate_id":"wrong","score":0.1,"summary":"bad","citations":[]}'
            else:
                stdout = json.dumps(
                    {
                        "candidate_id": label,
                        "score": 0.8,
                        "summary": "supported",
                        "citations": ["task_spec"],
                    }
                ).encode()
            return ProviderExecutionResult(
                exit_code=0,
                stdout=stdout,
                stderr=b"",
                duration_ms=11,
            )

    score_path = tmp_path / "scores.jsonl"
    result = evaluation.evaluate_trial_packets(
        packets=packets,
        trial_request_digest=fixture["runtime"]["request"].digest,
        evaluation_digest=fixture["runtime"]["request"].evaluation_digest,
        evidence_frozen_digest=fixture["evidence_frozen"].row_digest,
        scorer_config={
            "provider": "judge",
            "provider_params": {"temperature": 0},
            "evaluator_prompt_source": {"input_file": "prompts/trial.txt"},
            "rubric_source": {"asset_file": "rubrics/quality.md"},
            "evidence_limits": {"max_item_bytes": 1024, "max_packet_bytes": 4096},
            "evidence_confidentiality": "same_trust_boundary",
        },
        provider_registry=Registry(),
        prompt_composer=Composer(),
        provider_executor=Executor(),
        scorer_root=tmp_path / "scorer",
        score_ledger_path=score_path,
        trial_event_ledger_path=fixture["ledger_path"],
        evaluator_workspace=tmp_path / "evaluator",
        max_evaluator_attempts=len(packets) + 1,
        max_evaluator_concurrency=1,
    )

    assert result.rows == tuple(trial_ledger.load_trial_score_rows(score_path))
    assert len(result.rows) == len(packets)
    expected_score_fields = {
        "row_schema",
        "score_run_key",
        "row_content_digest",
        "trial_request_digest",
        "evaluation_digest",
        "evidence_frozen_digest",
        "evaluation_label",
        "evaluation_packet_digest",
        "scorer_identity_digest",
        "score_status",
        "score",
        "summary",
        "citations",
        "attempt_count",
        "charged_attempts",
        "failure",
    }
    assert all(set(row) == expected_score_fields for row in result.rows)
    assert all(row["row_schema"] == "trial.score.v1" for row in result.rows)
    assert all(row["score_status"] == "scored" for row in result.rows)
    assert all(row["score"] == 0.8 for row in result.rows)
    assert result.rows[0]["attempt_count"] == 2
    assert [attempt["status"] for attempt in result.rows[0]["charged_attempts"]] == [
        "output_invalid",
        "scored",
    ]
    assert [row["attempt_count"] for row in result.rows[1:]] == [1] * (
        len(packets) - 1
    )
    assert all(
        attempt["cost"] == {"variant": "UNKNOWN"}
        and attempt["token_usage"] == {"variant": "UNKNOWN"}
        for row in result.rows
        for attempt in row["charged_attempts"]
    )
    ledger = load_trial_event_ledger(fixture["ledger_path"])
    kinds = [row.kind for row in ledger.rows]
    assert kinds.count("scorer_frozen") == 1
    assert kinds.count("evaluator_attempt_allocated") == len(packets) + 1
    assert kinds.count("evaluator_attempt_settled") == len(packets) + 1
    assert kinds.count("score_settled") == len(packets)
    assert kinds.count("scores_frozen") == 1
    assert trial_ledger.replay_trial_evaluator_attempts(
        fixture["ledger_path"]
    ).charged_attempt_count == len(packets) + 1


def test_trial_evaluator_uses_global_concurrency_and_round_robin_attempt_budget(
    tmp_path: Path,
) -> None:
    from threading import Event, Lock

    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _durable_evaluator_fixture(tmp_path / "trial")
    packets = fixture["packets"]
    labels = tuple(packet["evaluation_id"] for packet in packets)

    class Registry:
        def exists(self, _name):
            return True

        def merge_params(self, _name, params):
            return dict(params)

    class Composer:
        def read_prompt_source(self, step, **_kwargs):
            return ("prompt" if "input_file" in step else "rubric"), None

    class Executor:
        def __init__(self) -> None:
            self.lock = Lock()
            self.two_active = Event()
            self.active = 0
            self.max_active = 0
            self.launch_order: list[str] = []
            self.attempts: dict[str, int] = {}

        def prepare_invocation(self, _provider, _params, _context, **kwargs):
            [label] = [label for label in labels if label in kwargs["prompt_content"]]
            return label, None

        def execute(self, label, *, cwd):
            from orchestrator.providers.executor import ProviderExecutionResult

            with self.lock:
                self.launch_order.append(label)
                self.attempts[label] = self.attempts.get(label, 0) + 1
                attempt = self.attempts[label]
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                if self.active == 2:
                    self.two_active.set()
            self.two_active.wait(timeout=0.25)
            if label == labels[0] and attempt == 1:
                stdout = b"not-json"
            else:
                stdout = json.dumps(
                    {
                        "candidate_id": label,
                        "score": 0.5,
                        "summary": "ok",
                        "citations": ["task_spec"],
                    }
                ).encode()
            with self.lock:
                self.active -= 1
            return ProviderExecutionResult(0, stdout, b"", 7)

    executor = Executor()
    result = evaluation.evaluate_trial_packets(
        packets=packets,
        trial_request_digest=fixture["runtime"]["request"].digest,
        evaluation_digest=fixture["runtime"]["request"].evaluation_digest,
        evidence_frozen_digest=fixture["evidence_frozen"].row_digest,
        scorer_config={
            "provider": "judge",
            "provider_params": {},
            "evaluator_prompt_source": {"input_file": "prompt.txt"},
            "rubric_source": {"asset_file": "rubric.md"},
            "evidence_limits": {"max_item_bytes": 1024, "max_packet_bytes": 4096},
            "evidence_confidentiality": "same_trust_boundary",
        },
        provider_registry=Registry(),
        prompt_composer=Composer(),
        provider_executor=executor,
        scorer_root=tmp_path / "scorer",
        score_ledger_path=tmp_path / "scores.jsonl",
        trial_event_ledger_path=fixture["ledger_path"],
        evaluator_workspace=tmp_path / "work",
        max_evaluator_attempts=len(packets) + 1,
        max_evaluator_concurrency=2,
    )

    assert executor.max_active == 2
    assert executor.launch_order == [*labels, labels[0]]
    assert [row["score_status"] for row in result.rows] == ["scored"] * len(packets)
    assert [row["attempt_count"] for row in result.rows] == [
        2,
        *([1] * (len(packets) - 1)),
    ]


def test_trial_evaluator_resume_reuses_commit_and_late_output_cannot_replace_it(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _durable_evaluator_fixture(tmp_path / "trial")
    packets = fixture["packets"]
    labels = tuple(packet["evaluation_id"] for packet in packets)

    class Registry:
        def exists(self, _name):
            return True

        def merge_params(self, _name, params):
            return dict(params)

    class Composer:
        def read_prompt_source(self, step, **_kwargs):
            return ("prompt" if "input_file" in step else "rubric"), None

    class FirstExecutor:
        def prepare_invocation(self, *_args, **kwargs):
            [label] = [
                label for label in labels if label in kwargs["prompt_content"]
            ]
            return label, None

        def execute(self, label, *, cwd):
            from orchestrator.providers.executor import ProviderExecutionResult

            return ProviderExecutionResult(
                0,
                json.dumps(
                    {
                        "candidate_id": label,
                        "score": 0.6,
                        "summary": "settled once",
                        "citations": ["task_spec"],
                    }
                ).encode(),
                b"",
                5,
            )

    arguments = {
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
        "provider_registry": Registry(),
        "prompt_composer": Composer(),
        "scorer_root": tmp_path / "scorer",
        "score_ledger_path": tmp_path / "scores.jsonl",
        "trial_event_ledger_path": fixture["ledger_path"],
        "evaluator_workspace": tmp_path / "work",
        "max_evaluator_attempts": len(packets),
        "max_evaluator_concurrency": 1,
    }
    first = evaluation.evaluate_trial_packets(
        **arguments,
        provider_executor=FirstExecutor(),
    )
    before_scores = (tmp_path / "scores.jsonl").read_bytes()
    before_ledger = fixture["ledger_path"].read_bytes()

    class LateExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def prepare_invocation(self, *_args, **_kwargs):
            self.calls += 1
            return object(), None

        def execute(self, *_args, **_kwargs):
            from orchestrator.providers.executor import ProviderExecutionResult

            self.calls += 1
            return ProviderExecutionResult(
                0,
                json.dumps(
                    {
                        "candidate_id": labels[0],
                        "score": 0.1,
                        "summary": "late conflicting output",
                        "citations": ["task_spec"],
                    }
                ).encode(),
                b"",
                99,
            )

    late = LateExecutor()
    resumed = evaluation.evaluate_trial_packets(
        **arguments,
        provider_executor=late,
    )

    assert late.calls == 0
    assert resumed.rows == first.rows
    assert (tmp_path / "scores.jsonl").read_bytes() == before_scores
    assert fixture["ledger_path"].read_bytes() == before_ledger


def test_evaluator_exhaustion_settles_pending_but_finishes_and_charges_inflight(
    tmp_path: Path,
) -> None:
    from threading import Event, Lock

    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _durable_evaluator_fixture(tmp_path / "trial")
    packets = fixture["packets"]
    labels = tuple(packet["evaluation_id"] for packet in packets)
    clock = {"now": 0}

    class Registry:
        def exists(self, _name):
            return True

        def merge_params(self, _name, params):
            return dict(params)

    class Composer:
        def read_prompt_source(self, step, **_kwargs):
            return ("prompt" if "input_file" in step else "rubric"), None

    class Executor:
        def __init__(self) -> None:
            self.lock = Lock()
            self.both_started = Event()
            self.active = 0

        def prepare_invocation(self, _provider, _params, _context, **kwargs):
            [label] = [label for label in labels if label in kwargs["prompt_content"]]
            return label, None

        def execute(self, label, *, cwd):
            from orchestrator.providers.executor import ProviderExecutionResult

            with self.lock:
                self.active += 1
                if self.active == 2:
                    clock["now"] = 11
                    self.both_started.set()
            self.both_started.wait(timeout=0.25)
            return ProviderExecutionResult(
                0,
                json.dumps(
                    {
                        "candidate_id": label,
                        "score": 0.7,
                        "summary": "inflight completed",
                        "citations": ["task_spec"],
                    }
                ).encode(),
                b"",
                13,
            )

    result = evaluation.evaluate_trial_packets(
        packets=packets,
        trial_request_digest=fixture["runtime"]["request"].digest,
        evaluation_digest=fixture["runtime"]["request"].evaluation_digest,
        evidence_frozen_digest=fixture["evidence_frozen"].row_digest,
        scorer_config={
            "provider": "judge",
            "provider_params": {},
            "evaluator_prompt_source": {"input_file": "prompt.txt"},
            "rubric_source": {"asset_file": "rubric.md"},
            "evidence_limits": {"max_item_bytes": 1024, "max_packet_bytes": 4096},
            "evidence_confidentiality": "same_trust_boundary",
        },
        provider_registry=Registry(),
        prompt_composer=Composer(),
        provider_executor=Executor(),
        scorer_root=tmp_path / "scorer",
        score_ledger_path=tmp_path / "scores.jsonl",
        trial_event_ledger_path=fixture["ledger_path"],
        evaluator_workspace=tmp_path / "work",
        max_evaluator_attempts=2,
        max_evaluator_concurrency=2,
        deadline_unix_ns=10,
        wall_time_ns=lambda: clock["now"],
    )

    assert [row["score_status"] for row in result.rows] == [
        "scored",
        "scored",
        "evaluation_failed",
        "evaluation_failed",
    ]
    assert [row["attempt_count"] for row in result.rows] == [1, 1, 0, 0]
    assert all(
        row["failure"]["code"] == "trial_evaluator_deadline_exhausted"
        for row in result.rows[2:]
    )
    assert sorted(
        attempt["global_attempt"]
        for row in result.rows
        for attempt in row["charged_attempts"]
    ) == [1, 2]


def test_evaluator_rechecks_deadline_before_each_batch_allocation_and_resumes_stably(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _durable_evaluator_fixture(tmp_path / "trial")
    packets = fixture["packets"]
    labels = tuple(packet["evaluation_id"] for packet in packets)
    clock = {"now": 0}

    class Registry:
        def exists(self, _name):
            return True

        def merge_params(self, _name, params):
            return dict(params)

    class Composer:
        def read_prompt_source(self, step, **_kwargs):
            return ("prompt" if "input_file" in step else "rubric"), None

    class Executor:
        def __init__(self) -> None:
            self.prepared: list[str] = []
            self.launched: list[str] = []

        def prepare_invocation(self, _provider, _params, _context, **kwargs):
            [label] = [label for label in labels if label in kwargs["prompt_content"]]
            self.prepared.append(label)
            if label == labels[0]:
                clock["now"] = 11
            return label, None

        def execute(self, label, *, cwd):
            from orchestrator.providers.executor import ProviderExecutionResult

            self.launched.append(label)
            return ProviderExecutionResult(
                0,
                json.dumps(
                    {
                        "candidate_id": label,
                        "score": 0.7,
                        "summary": "allocated before deadline",
                        "citations": ["task_spec"],
                    }
                ).encode(),
                b"",
                13,
            )

    executor = Executor()
    arguments = {
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
        "provider_registry": Registry(),
        "prompt_composer": Composer(),
        "scorer_root": tmp_path / "scorer",
        "score_ledger_path": tmp_path / "scores.jsonl",
        "trial_event_ledger_path": fixture["ledger_path"],
        "evaluator_workspace": tmp_path / "work",
        "max_evaluator_attempts": 2,
        "max_evaluator_concurrency": 2,
        "deadline_unix_ns": 10,
        "wall_time_ns": lambda: clock["now"],
    }

    first = evaluation.evaluate_trial_packets(
        **arguments,
        provider_executor=executor,
    )

    assert executor.prepared == [labels[0]]
    assert executor.launched == [labels[0]]
    assert [row["score_status"] for row in first.rows] == [
        "scored",
        "evaluation_failed",
        "evaluation_failed",
        "evaluation_failed",
    ]
    assert [row["attempt_count"] for row in first.rows] == [1, 0, 0, 0]
    assert all(
        row["failure"]["code"] == "trial_evaluator_deadline_exhausted"
        for row in first.rows[1:]
    )
    allocations = [
        row
        for row in load_trial_event_ledger(fixture["ledger_path"]).rows
        if row.kind == "evaluator_attempt_allocated"
    ]
    assert [row.payload["opaque_label"] for row in allocations] == [labels[0]]

    before_scores = (tmp_path / "scores.jsonl").read_bytes()
    before_ledger = fixture["ledger_path"].read_bytes()

    class LateExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def prepare_invocation(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("settled deadline outcome was reevaluated")

        def execute(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("settled deadline outcome was relaunched")

    late = LateExecutor()
    resumed = evaluation.evaluate_trial_packets(
        **arguments,
        provider_executor=late,
    )

    assert late.calls == 0
    assert resumed.rows == first.rows
    assert (tmp_path / "scores.jsonl").read_bytes() == before_scores
    assert fixture["ledger_path"].read_bytes() == before_ledger


def test_trial_evaluator_never_enters_legacy_candidate_selection_or_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    fixture = _durable_evaluator_fixture(tmp_path / "trial")
    packets = fixture["packets"]
    labels = tuple(packet["evaluation_id"] for packet in packets)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("trial evaluation entered a legacy candidate surface")

    legacy_scoring = importlib.import_module("orchestrator.workflow.adjudication.scoring")
    legacy_evidence = importlib.import_module("orchestrator.workflow.adjudication.evidence")
    legacy_ledger = importlib.import_module("orchestrator.workflow.adjudication.ledger")
    legacy_promotion = importlib.import_module("orchestrator.workflow.adjudication.promotion")
    legacy_paths = importlib.import_module("orchestrator.workflow.adjudication.paths")
    legacy_runner = importlib.import_module("orchestrator.workflow.adjudication_runner")
    monkeypatch.setattr(legacy_scoring, "select_candidate", forbidden)
    monkeypatch.setattr(legacy_evidence, "build_evaluation_packet", forbidden)
    monkeypatch.setattr(legacy_ledger, "generate_score_ledger_rows", forbidden)
    monkeypatch.setattr(legacy_promotion, "promote_candidate_outputs", forbidden)
    monkeypatch.setattr(legacy_paths, "candidate_paths", forbidden)
    monkeypatch.setattr(
        legacy_runner.AdjudicationRunner,
        "execute_adjudicated_provider_with_context",
        forbidden,
    )

    class Registry:
        def exists(self, _name):
            return True

        def merge_params(self, _name, params):
            return dict(params)

    class Composer:
        def read_prompt_source(self, step, **_kwargs):
            return ("prompt" if "input_file" in step else "rubric"), None

    class Executor:
        def prepare_invocation(self, *_args, **kwargs):
            [label] = [
                label for label in labels if label in kwargs["prompt_content"]
            ]
            return label, None

        def execute(self, label, *, cwd):
            from orchestrator.providers.executor import ProviderExecutionResult

            return ProviderExecutionResult(
                0,
                json.dumps(
                    {
                        "candidate_id": label,
                        "score": 0.9,
                        "summary": "independent score",
                        "citations": ["task_spec"],
                    }
                ).encode(),
                b"",
                3,
            )

    rows = evaluation.evaluate_trial_packets(
        packets=packets,
        trial_request_digest=fixture["runtime"]["request"].digest,
        evaluation_digest=fixture["runtime"]["request"].evaluation_digest,
        evidence_frozen_digest=fixture["evidence_frozen"].row_digest,
        scorer_config={
            "provider": "judge",
            "provider_params": {},
            "evaluator_prompt_source": {"input_file": "prompt.txt"},
            "rubric_source": {"asset_file": "rubric.md"},
            "evidence_limits": {"max_item_bytes": 1024, "max_packet_bytes": 4096},
            "evidence_confidentiality": "same_trust_boundary",
        },
        provider_registry=Registry(),
        prompt_composer=Composer(),
        provider_executor=Executor(),
        scorer_root=tmp_path / "scorer",
        score_ledger_path=tmp_path / "scores.jsonl",
        trial_event_ledger_path=fixture["ledger_path"],
        evaluator_workspace=tmp_path / "work",
        max_evaluator_attempts=len(packets),
        max_evaluator_concurrency=1,
    ).rows

    assert [row["score_status"] for row in rows] == ["scored"] * len(packets)


def test_trial_verdict_uses_complete_medians_and_the_rank_two_alternative() -> None:
    verdict = importlib.import_module("orchestrator.workflow.trial.verdict")
    contracts = importlib.import_module("orchestrator.workflow.trial.contracts")
    cells = tuple(
        contracts.TrialCellKey(arm_id=arm_id, rep=rep)
        for arm_id in ("direct", "orc", "coordinator")
        for rep in range(1, 4)
    )
    labels = tuple(f"opaque-{index:064x}" for index in range(1, 10))
    sealed = contracts.build_sealed_opaque_label_map(cells, labels=labels)
    scores = {
        "direct": (0.35, 0.40, 0.45),
        "orc": (0.88, 0.90, 0.92),
        "coordinator": (0.84, 0.86, 0.88),
    }
    rows = tuple(
        {
            "evaluation_label": label,
            "score_status": "scored",
            "score": scores[cell.arm_id][cell.rep - 1],
                "charged_attempts": [
                    {
                        "duration_ms": 1,
                        "token_usage": {"variant": "UNKNOWN"},
                        "cost": {
                            "variant": "KNOWN",
                            "amount": 0.01,
                        "currency": "USD",
                    }
                }
            ],
        }
        for cell, label in zip(cells, labels, strict=True)
    )
    outcomes = tuple(
        {
            "cell": cell.record,
            "outcome": "COMPLETED",
            "child_attempts": 1,
            "elapsed_ms": 10,
            "token_usage": "UNKNOWN",
            "cost": {
                "variant": "KNOWN",
                "amount": 0.10,
                "currency": "USD",
            },
        }
        for cell in cells
    )

    result = verdict.aggregate_trial_verdict(
        authored_arm_order=("direct", "orc", "coordinator"),
        reps=3,
        cell_outcomes=outcomes,
        score_rows=rows,
        sealed_label_map=sealed,
        success_rule={
            "min_abs_improvement": 0.10,
            "max_cost_ratio": 1.5,
            "min_cost_reduction": 0.20,
        },
    )

    assert result["aggregate_scores"] == [
        {"arm_id": "direct", "score": 0.4, "completed_count": 3, "failed_count": 0},
        {"arm_id": "orc", "score": 0.9, "completed_count": 3, "failed_count": 0},
        {
            "arm_id": "coordinator",
            "score": 0.86,
            "completed_count": 3,
            "failed_count": 0,
        },
    ]
    assert result["ranking"] == ["orc", "coordinator", "direct"]
    assert result["selected_arm"] is None
    assert result["success_rule_disposition"] == "no_material_advantage"


def test_trial_score_row_content_digest_rejects_a_tampered_settled_score(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    adjudication_ledger = importlib.import_module(
        "orchestrator.workflow.adjudication.ledger"
    )
    row = evaluation._score_row(
        trial_request_digest="sha256:" + "1" * 64,
        evaluation_digest="sha256:" + "2" * 64,
        evidence_frozen_digest="sha256:" + "3" * 64,
        packet={
            "evaluation_id": "opaque-" + "4" * 64,
            "citable_item_ids": ["task_spec"],
        },
        scorer_identity_digest="sha256:" + "5" * 64,
        parsed={"score": 0.75, "summary": "settled", "citations": ["task_spec"]},
        charged_attempts=(
            {
                "attempt": 1,
                "global_attempt": 1,
                "status": "scored",
                "exit_code": 0,
                "duration_ms": 2,
            },
        ),
        failure=None,
    )
    assert row["row_content_digest"] == canonical_sha256(
        {key: value for key, value in row.items() if key != "row_content_digest"}
    )
    path = tmp_path / "scores.jsonl"
    adjudication_ledger.materialize_run_score_ledger((row,), path)
    tampered = dict(row)
    tampered["score"] = 0.25
    adjudication_ledger.materialize_run_score_ledger((tampered,), path)

    with pytest.raises(TrialLedgerError, match="content digest"):
        trial_ledger.load_trial_score_rows(path)


def test_trial_score_ledger_rejects_duplicate_or_gapped_global_attempts(
    tmp_path: Path,
) -> None:
    evaluation = importlib.import_module("orchestrator.workflow.trial.evaluation")
    adjudication_ledger = importlib.import_module(
        "orchestrator.workflow.adjudication.ledger"
    )

    def row(label_digit: str, global_attempt: int):
        return evaluation._score_row(
            trial_request_digest="sha256:" + "1" * 64,
            evaluation_digest="sha256:" + "2" * 64,
            evidence_frozen_digest="sha256:" + "3" * 64,
            packet={
                "evaluation_id": "opaque-" + label_digit * 64,
                "citable_item_ids": ["task_spec"],
            },
            scorer_identity_digest="sha256:" + "5" * 64,
            parsed={"score": 0.75, "summary": "settled", "citations": ["task_spec"]},
            charged_attempts=(
                {
                    "attempt": 1,
                    "global_attempt": global_attempt,
                    "status": "scored",
                    "exit_code": 0,
                    "duration_ms": 2,
                },
            ),
            failure=None,
        )

    path = tmp_path / "scores.jsonl"
    for second_global in (1, 3):
        adjudication_ledger.materialize_run_score_ledger(
            (row("6", 1), row("7", second_global)), path
        )
        with pytest.raises(TrialLedgerError, match="global attempt domain"):
            trial_ledger.load_trial_score_rows(path)


@pytest.mark.parametrize(
    (
        "leader_score",
        "alternative_score",
        "leader_cost",
        "alternative_cost",
        "expected_disposition",
        "expected_selected",
    ),
    [
        (0.90, 0.80, (0.10, "USD"), (0.10, "USD"), "superior", "leader"),
        (0.90, 0.80, (0.0, "USD"), (0.0, "USD"), "superior", "leader"),
        (0.90, 0.80, (0.10, "USD"), (0.0, "USD"), "no_material_advantage", None),
        (
            0.81,
            0.80,
            (0.05, "USD"),
            (0.10, "USD"),
            "non_inferior_lower_cost",
            "leader",
        ),
        (0.90, 0.80, None, (0.10, "USD"), "cost_unknown", None),
        (0.90, 0.80, (0.10, "USD"), (0.10, "EUR"), "cost_incomparable", None),
    ],
)
def test_trial_verdict_cost_and_disposition_boundaries(
    leader_score: float,
    alternative_score: float,
    leader_cost: tuple[float, str] | None,
    alternative_cost: tuple[float, str] | None,
    expected_disposition: str,
    expected_selected: str | None,
) -> None:
    verdict = importlib.import_module("orchestrator.workflow.trial.verdict")
    contracts = importlib.import_module("orchestrator.workflow.trial.contracts")
    cells = (
        contracts.TrialCellKey("alternative", 1),
        contracts.TrialCellKey("leader", 1),
    )
    labels = ("opaque-" + "8" * 64, "opaque-" + "9" * 64)
    sealed = contracts.build_sealed_opaque_label_map(cells, labels=labels)

    def cost(value: tuple[float, str] | None):
        if value is None:
            return {"variant": "UNKNOWN"}
        amount, currency = value
        return {"variant": "KNOWN", "amount": amount, "currency": currency}

    result = verdict.aggregate_trial_verdict(
        authored_arm_order=("alternative", "leader"),
        reps=1,
        cell_outcomes=(
            {
                "cell": cells[0].record,
                "outcome": "COMPLETED",
                "child_attempts": 1,
                "elapsed_ms": 1,
                "token_usage": "UNKNOWN",
                "cost": cost(alternative_cost),
            },
            {
                "cell": cells[1].record,
                "outcome": "COMPLETED",
                "child_attempts": 1,
                "elapsed_ms": 1,
                "token_usage": "UNKNOWN",
                "cost": cost(leader_cost),
            },
        ),
        score_rows=(
                {
                    "evaluation_label": labels[0],
                    "score_status": "scored",
                    "score": alternative_score,
                    "charged_attempts": [
                        {
                            "duration_ms": 1,
                            "token_usage": {"variant": "UNKNOWN"},
                            "cost": (
                                cost((0.0, alternative_cost[1]))
                                if alternative_cost
                                else cost(None)
                            ),
                        }
                    ],
                },
                {
                    "evaluation_label": labels[1],
                    "score_status": "scored",
                    "score": leader_score,
                    "charged_attempts": [
                        {
                            "duration_ms": 1,
                            "token_usage": {"variant": "UNKNOWN"},
                            "cost": (
                                cost((0.0, leader_cost[1]))
                                if leader_cost
                                else cost(None)
                            ),
                        }
                    ],
                },
        ),
        sealed_label_map=sealed,
        success_rule={
            "min_abs_improvement": 0.10,
            "max_cost_ratio": 1.5,
            "min_cost_reduction": 0.20,
        },
    )

    assert result["success_rule_disposition"] == expected_disposition
    assert result["selected_arm"] == expected_selected


def test_trial_verdict_artifact_is_canonical_digest_bound_and_trial_rooted(
    tmp_path: Path,
) -> None:
    verdict_module = importlib.import_module("orchestrator.workflow.trial.verdict")
    verdict = {
        "authored_arm_order": ["direct", "orc"],
        "per_repetition": [
            {"arm_id": "direct", "rep": 1, "outcome": "FAILED", "score": 0.2},
            {"arm_id": "orc", "rep": 1, "outcome": "COMPLETED", "score": 0.8},
        ],
        "aggregate_scores": [
            {"arm_id": "direct", "score": 0.2, "completed_count": 0, "failed_count": 1},
            {"arm_id": "orc", "score": 0.8, "completed_count": 1, "failed_count": 0},
        ],
        "ranking": ["orc", "direct"],
        "selected_arm": "orc",
        "success_rule_disposition": "superior",
        "budget_accounting": {
            "cell_count": 2,
            "completed_count": 1,
            "failed_count": 1,
            "child_attempts": 2,
            "evaluator_attempts": 2,
            "elapsed_ms": 20,
            "token_usage": {"variant": "UNKNOWN"},
            "cost": {"variant": "UNKNOWN"},
        },
    }
    authored_outcomes = [
        {"arm_id": "direct", "rep": 1, "outcome": "FAILED"},
        {"arm_id": "orc", "rep": 1, "outcome": "COMPLETED"},
    ]
    score_rows = [
        {"evaluation_label": "opaque-" + digit * 64, "score": score}
        for digit, score in (("a", 0.2), ("b", 0.8))
    ]

    artifact = verdict_module.persist_trial_verdict_artifact(
        workspace=tmp_path.resolve(),
        trial_request_digest="sha256:" + "1" * 64,
        evaluation_digest="sha256:" + "2" * 64,
        evidence_frozen_digest="sha256:" + "3" * 64,
        checks_frozen_digest="sha256:" + "4" * 64,
        score_rows=score_rows,
        scorer_identity_digest="sha256:" + "5" * 64,
        sealed_label_map_digest="sha256:" + "6" * 64,
        authored_outcomes=authored_outcomes,
        verdict=verdict,
    )
    first_bytes = artifact.path.read_bytes()
    resumed = verdict_module.persist_trial_verdict_artifact(
        workspace=tmp_path.resolve(),
        trial_request_digest="sha256:" + "1" * 64,
        evaluation_digest="sha256:" + "2" * 64,
        evidence_frozen_digest="sha256:" + "3" * 64,
        checks_frozen_digest="sha256:" + "4" * 64,
        score_rows=score_rows,
        scorer_identity_digest="sha256:" + "5" * 64,
        sealed_label_map_digest="sha256:" + "6" * 64,
        authored_outcomes=authored_outcomes,
        verdict=verdict,
    )

    assert artifact.relpath.startswith("artifacts/trials/")
    assert artifact.path == tmp_path.resolve() / artifact.relpath
    assert resumed.path == artifact.path
    assert resumed.record == artifact.record
    assert resumed.path.read_bytes() == first_bytes
    assert artifact.path.read_bytes() == (
        json.dumps(artifact.record, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )
    assert artifact.record["score_digest"] == canonical_sha256(score_rows)
    assert artifact.record["verdict_digest"] == canonical_sha256(verdict)
    assert artifact.record["artifact_digest"] == canonical_sha256(
        {
            key: value
            for key, value in artifact.record.items()
            if key != "artifact_digest"
        }
    )

    tampered_bytes = b'{"tampered":true}\n'
    artifact.path.write_bytes(tampered_bytes)
    with pytest.raises(verdict_module.TrialVerdictError, match="artifact disagrees"):
        verdict_module.persist_trial_verdict_artifact(
            workspace=tmp_path.resolve(),
            trial_request_digest="sha256:" + "1" * 64,
            evaluation_digest="sha256:" + "2" * 64,
            evidence_frozen_digest="sha256:" + "3" * 64,
            checks_frozen_digest="sha256:" + "4" * 64,
            score_rows=score_rows,
            scorer_identity_digest="sha256:" + "5" * 64,
            sealed_label_map_digest="sha256:" + "6" * 64,
            authored_outcomes=authored_outcomes,
            verdict=verdict,
        )
    assert artifact.path.read_bytes() == tampered_bytes


def _freeze_trial_scores_for_terminal_chain(tmp_path: Path):
    path, packets, _scorer = _freeze_trial_packets_for_attempts(tmp_path)
    settlements = []
    for index, packet in enumerate(packets, start=1):
        settlements.append(
            trial_ledger.append_trial_score_settlement(
                path,
                expected_head_digest=load_trial_event_ledger(path).rows[-1].row_digest,
                opaque_label=packet["opaque_label"],
                score_row_content_digest=(
                    "sha256:" + format(index, "x") * 64
                ),
                terminal_attempt_settlement_row_digest=None,
            )
        )
    scores = trial_ledger.append_trial_scores_freeze(
        path,
        expected_head_digest=settlements[-1].row_digest,
    )
    return path, scores


def test_trial_terminal_event_chain_is_closed_digest_bound_and_exported(
    tmp_path: Path,
) -> None:
    path, scores = _freeze_trial_scores_for_terminal_chain(tmp_path)
    header = load_trial_event_ledger(path).rows[0]
    final_outcomes_digest = "sha256:" + "a" * 64

    aggregation = trial_ledger.append_trial_aggregation_freeze(
        path,
        expected_head_digest=scores.row_digest,
        scores_frozen_row_digest=scores.row_digest,
        sealed_opaque_label_map_digest=header.payload[
            "sealed_opaque_label_map_digest"
        ],
        final_outcomes_digest=final_outcomes_digest,
    )
    assert aggregation.kind == "aggregation_frozen"
    assert aggregation.payload == {
        "scores_frozen_row_digest": scores.row_digest,
        "sealed_opaque_label_map_digest": header.payload[
            "sealed_opaque_label_map_digest"
        ],
        "final_outcomes_digest": final_outcomes_digest,
        "aggregation_input_digest": canonical_sha256(
            {
                "scores_frozen_row_digest": scores.row_digest,
                "sealed_opaque_label_map_digest": header.payload[
                    "sealed_opaque_label_map_digest"
                ],
                "final_outcomes_digest": final_outcomes_digest,
                "evaluation_digest": header.payload["evaluation_digest"],
                "score_set_digest": scores.payload["score_set_digest"],
            }
        ),
    }

    verdict_digest = "sha256:" + "b" * 64
    settled = trial_ledger.append_trial_verdict_settlement(
        path,
        expected_head_digest=aggregation.row_digest,
        aggregation_frozen_row_digest=aggregation.row_digest,
        verdict_digest=verdict_digest,
    )
    assert settled.kind == "verdict_settled"
    assert settled.payload == {
        "aggregation_frozen_row_digest": aggregation.row_digest,
        "verdict_digest": verdict_digest,
    }

    published = trial_ledger.append_trial_verdict_publication(
        path,
        expected_head_digest=settled.row_digest,
        verdict_settled_row_digest=settled.row_digest,
        verdict_artifact_digest="sha256:" + "c" * 64,
        verdict_artifact_relpath="artifacts/trials/verdict.json",
    )
    assert published.kind == "verdict_published"
    assert published.payload == {
        "verdict_settled_row_digest": settled.row_digest,
        "verdict_artifact_digest": "sha256:" + "c" * 64,
        "verdict_artifact_relpath": "artifacts/trials/verdict.json",
    }
    assert [row.kind for row in load_trial_event_ledger(path).rows[-4:]] == [
        "scores_frozen",
        "aggregation_frozen",
        "verdict_settled",
        "verdict_published",
    ]
    assert {
        "append_trial_aggregation_freeze",
        "append_trial_verdict_settlement",
        "append_trial_verdict_publication",
    } <= set(trial_ledger.__all__)


def test_trial_terminal_event_chain_rejects_missing_wrong_or_tampered_authority(
    tmp_path: Path,
) -> None:
    path, scores = _freeze_trial_scores_for_terminal_chain(tmp_path)
    header = load_trial_event_ledger(path).rows[0]
    final_outcomes_digest = "sha256:" + "a" * 64

    with pytest.raises(TrialLedgerError, match="aggregation freeze"):
        trial_ledger.append_trial_verdict_settlement(
            path,
            expected_head_digest=scores.row_digest,
            aggregation_frozen_row_digest="sha256:" + "d" * 64,
            verdict_digest="sha256:" + "b" * 64,
        )
    for changed, match in (
        ({"scores_frozen_row_digest": "sha256:" + "d" * 64}, "score freeze"),
        (
            {"sealed_opaque_label_map_digest": "sha256:" + "e" * 64},
            "opaque-label map",
        ),
    ):
        with pytest.raises(TrialLedgerError, match=match):
            arguments = {
                "path": path,
                "expected_head_digest": scores.row_digest,
                "scores_frozen_row_digest": scores.row_digest,
                "sealed_opaque_label_map_digest": header.payload[
                    "sealed_opaque_label_map_digest"
                ],
                "final_outcomes_digest": final_outcomes_digest,
            }
            arguments.update(changed)
            trial_ledger.append_trial_aggregation_freeze(**arguments)

    with pytest.raises(TrialLedgerError, match="aggregation-input digest"):
        trial_ledger._append(
            path,
            expected_head_digest=scores.row_digest,
            kind="aggregation_frozen",
            payload={
                "scores_frozen_row_digest": scores.row_digest,
                "sealed_opaque_label_map_digest": header.payload[
                    "sealed_opaque_label_map_digest"
                ],
                "final_outcomes_digest": final_outcomes_digest,
                "aggregation_input_digest": "sha256:" + "f" * 64,
            },
            recorded_at=None,
        )

    aggregation = trial_ledger.append_trial_aggregation_freeze(
        path,
        expected_head_digest=scores.row_digest,
        scores_frozen_row_digest=scores.row_digest,
        sealed_opaque_label_map_digest=header.payload[
            "sealed_opaque_label_map_digest"
        ],
        final_outcomes_digest=final_outcomes_digest,
    )
    with pytest.raises(TrialLedgerError, match="aggregation freeze"):
        trial_ledger.append_trial_verdict_settlement(
            path,
            expected_head_digest=aggregation.row_digest,
            aggregation_frozen_row_digest="sha256:" + "d" * 64,
            verdict_digest="sha256:" + "b" * 64,
        )


@pytest.mark.parametrize(
    "relpath",
    [
        "artifacts/trials",
        "artifacts/trials/../verdict.json",
        "artifacts/trials\\verdict.json",
        "/artifacts/trials/verdict.json",
        "other/artifacts/trials/verdict.json",
    ],
)
def test_trial_verdict_publication_requires_normalized_strict_trial_artifact_path(
    tmp_path: Path,
    relpath: str,
) -> None:
    path, scores = _freeze_trial_scores_for_terminal_chain(tmp_path)
    header = load_trial_event_ledger(path).rows[0]
    aggregation = trial_ledger.append_trial_aggregation_freeze(
        path,
        expected_head_digest=scores.row_digest,
        scores_frozen_row_digest=scores.row_digest,
        sealed_opaque_label_map_digest=header.payload[
            "sealed_opaque_label_map_digest"
        ],
        final_outcomes_digest="sha256:" + "a" * 64,
    )
    settled = trial_ledger.append_trial_verdict_settlement(
        path,
        expected_head_digest=aggregation.row_digest,
        aggregation_frozen_row_digest=aggregation.row_digest,
        verdict_digest="sha256:" + "b" * 64,
    )

    with pytest.raises(TrialLedgerError, match="artifact path"):
        trial_ledger.append_trial_verdict_publication(
            path,
            expected_head_digest=settled.row_digest,
            verdict_settled_row_digest=settled.row_digest,
            verdict_artifact_digest="sha256:" + "c" * 64,
            verdict_artifact_relpath=relpath,
        )


def test_trial_verdict_publication_is_terminal_for_evaluator_and_score_events(
    tmp_path: Path,
) -> None:
    path, scores = _freeze_trial_scores_for_terminal_chain(tmp_path)
    header = load_trial_event_ledger(path).rows[0]
    aggregation = trial_ledger.append_trial_aggregation_freeze(
        path,
        expected_head_digest=scores.row_digest,
        scores_frozen_row_digest=scores.row_digest,
        sealed_opaque_label_map_digest=header.payload[
            "sealed_opaque_label_map_digest"
        ],
        final_outcomes_digest="sha256:" + "a" * 64,
    )
    settled = trial_ledger.append_trial_verdict_settlement(
        path,
        expected_head_digest=aggregation.row_digest,
        aggregation_frozen_row_digest=aggregation.row_digest,
        verdict_digest="sha256:" + "b" * 64,
    )
    published = trial_ledger.append_trial_verdict_publication(
        path,
        expected_head_digest=settled.row_digest,
        verdict_settled_row_digest=settled.row_digest,
        verdict_artifact_digest="sha256:" + "c" * 64,
        verdict_artifact_relpath="artifacts/trials/verdict.json",
    )
    packet = next(
        row for row in load_trial_event_ledger(path).rows if row.kind == "packets_frozen"
    ).payload["cell_packets"][0]
    scorer = next(
        row for row in load_trial_event_ledger(path).rows if row.kind == "scorer_frozen"
    )

    with pytest.raises(TrialLedgerError, match="terminal verdict publication"):
        trial_ledger.append_trial_evaluator_attempt_allocation(
            path,
            expected_head_digest=published.row_digest,
            opaque_label=packet["opaque_label"],
            local_attempt=1,
            global_attempt=1,
            packet_digest=packet["packet_digest"],
            scorer_frozen_row_digest=scorer.row_digest,
            started_at_unix_ns=1_000_000_000,
        )
    with pytest.raises(TrialLedgerError, match="terminal verdict publication"):
        trial_ledger.append_trial_score_settlement(
            path,
            expected_head_digest=published.row_digest,
            opaque_label=packet["opaque_label"],
            score_row_content_digest="sha256:" + "d" * 64,
            terminal_attempt_settlement_row_digest=None,
        )
