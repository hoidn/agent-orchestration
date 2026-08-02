from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.trial.ledger import (
    TrialLedgerError,
    append_trial_parent_commit,
    load_trial_event_ledger,
)
from tests.test_workflow_trial_adjudication import (
    _Executor,
    _blinded_cell_harnesses,
    _dependencies,
)
from tests.test_workflow_trial_runtime import _execute, _runtime_fixture


def _terminal_trial(tmp_path: Path):
    from orchestrator.workflow.trial.adjudication import evaluate_trial_execution

    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _blinded_cell_harnesses())
    dependencies, _check_calls = _dependencies(_Executor())
    adjudicated = evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=dependencies,
    )
    envelope = {
        "outcomes": list(adjudicated.authored_outcomes),
        "verdict": adjudicated.verdict,
        "verdict_artifact": adjudicated.verdict_artifact.relpath,
    }
    return fixture, execution, adjudicated, envelope


def _prepare_terminal_trial(tmp_path: Path):
    from orchestrator.workflow.trial.settlement import prepare_trial_parent_settlement

    fixture, execution, adjudicated, envelope = _terminal_trial(tmp_path)
    publication = load_trial_event_ledger(execution.ledger_path).rows[-1]
    prepared = prepare_trial_parent_settlement(
        execution.ledger_path,
        request=fixture["request"],
        parent_workspace=fixture["parent_workspace"],
        result_envelope=envelope,
        recorded_at=publication.recorded_at,
    )
    return fixture, execution, adjudicated, envelope, prepared


def _parent_artifacts(adjudicated) -> dict[str, object]:
    return {"verdict": adjudicated.verdict_artifact.relpath}


def _parent_state(
    fixture,
    envelope: dict[str, object],
    artifacts: dict[str, object],
    *,
    current_step: object = None,
) -> dict[str, object]:
    request = fixture["request"]
    step_name = "compare"
    return {
        "run_id": request.visit.parent_run_id,
        "current_step": current_step,
        "steps": {
            step_name: {
                "status": "completed",
                "name": step_name,
                "step_id": request.visit.step_id,
                "visit_count": request.visit.visit_count,
                "trial": envelope,
                "artifacts": artifacts,
            }
        },
    }


def _write_parent_state(path: Path, state: dict[str, object]) -> None:
    path.write_bytes(canonical_json_bytes(state) + b"\n")


def _read_parent_state(path: Path):
    def read() -> dict[str, object]:
        return json.loads(path.read_bytes())

    return read


def _write_rechained_rows(path: Path, rows: list[dict[str, object]]) -> None:
    previous = None
    encoded: list[bytes] = []
    for sequence, row in enumerate(rows, start=1):
        row["sequence"] = sequence
        row["previous_row_digest"] = previous
        preimage = dict(row)
        preimage.pop("row_digest", None)
        row["row_digest"] = canonical_sha256(preimage)
        previous = row["row_digest"]
        encoded.append(canonical_json_bytes(row) + b"\n")
    path.write_bytes(b"".join(encoded))


def test_outer_prepare_and_parent_commit_bind_exact_terminal_authority(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.settlement import (
        commit_trial_parent_settlement,
        prepare_trial_parent_settlement,
    )

    fixture, execution, adjudicated, envelope = _terminal_trial(tmp_path)
    ledger = load_trial_event_ledger(execution.ledger_path)
    publication = ledger.rows[-1]

    prepared = prepare_trial_parent_settlement(
        execution.ledger_path,
        request=fixture["request"],
        parent_workspace=fixture["parent_workspace"],
        result_envelope=envelope,
        recorded_at=publication.recorded_at,
    )

    assert prepared.row.kind == "trial_prepared"
    assert prepared.row.payload == {
        "verdict_publication_row_digest": publication.row_digest,
        "result_contract_digest": fixture["request"].result_contract_digest,
        "result_envelope_digest": canonical_sha256(envelope),
        "authored_outcomes_digest": canonical_sha256(envelope["outcomes"]),
        "verdict_digest": canonical_sha256(adjudicated.verdict),
        "verdict_artifact_digest": adjudicated.verdict_artifact.record[
            "artifact_digest"
        ],
        "verdict_artifact_relpath": adjudicated.verdict_artifact.relpath,
        "budget_digest": fixture["request"].budget_digest,
        "budget_accounting_digest": canonical_sha256(
            adjudicated.verdict["budget_accounting"]
        ),
    }

    artifacts = _parent_artifacts(adjudicated)
    state_path = tmp_path / "parent-state.json"
    settled_state = _parent_state(fixture, envelope, artifacts)
    settled_state.pop("current_step")
    _write_parent_state(
        state_path,
        settled_state,
    )
    committed = commit_trial_parent_settlement(
        execution.ledger_path,
        request=fixture["request"],
        prepared=prepared,
        step_name="compare",
        expected_artifacts=artifacts,
        read_parent_state=_read_parent_state(state_path),
        recorded_at=prepared.row.recorded_at,
    )

    assert committed.kind == "trial_parent_committed"
    assert committed.payload["trial_prepared_row_digest"] == prepared.row.row_digest
    assert committed.payload["result_envelope_digest"] == canonical_sha256(envelope)
    assert committed.payload["parent_state_settlement_digest"] == canonical_sha256(
        {
            "schema_version": "trial_parent_state_settlement.v1",
            "parent_run_id": fixture["request"].visit.parent_run_id,
            "execution_frame_id": fixture["request"].visit.execution_frame_id,
            "call_frame_id": fixture["request"].visit.call_frame_id,
            "step_name": "compare",
            "step_id": fixture["request"].visit.step_id,
            "visit_count": fixture["request"].visit.visit_count,
            "status": "completed",
            "result_envelope_digest": canonical_sha256(envelope),
            "artifacts_digest": canonical_sha256(artifacts),
            "current_step_cleared": True,
        }
    )
    assert [
        row.kind
        for row in load_trial_event_ledger(execution.ledger_path).rows[-3:]
    ] == ["verdict_published", "trial_prepared", "trial_parent_committed"]


def test_crash_after_prepare_reuses_exact_row_without_repeating_trial_effects(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.adjudication import evaluate_trial_execution
    from orchestrator.workflow.trial.settlement import prepare_trial_parent_settlement

    fixture, execution, adjudicated, envelope, prepared = _prepare_terminal_trial(
        tmp_path
    )
    frozen_bytes = execution.ledger_path.read_bytes()
    resumed = prepare_trial_parent_settlement(
        execution.ledger_path,
        request=fixture["request"],
        parent_workspace=fixture["parent_workspace"],
        result_envelope=envelope,
    )
    assert resumed == prepared
    assert execution.ledger_path.read_bytes() == frozen_bytes

    forbidden = _Executor(forbidden=True)
    dependencies, check_calls = _dependencies(forbidden)
    replayed = evaluate_trial_execution(
        fixture["request"],
        execution,
        parent_workspace=fixture["parent_workspace"],
        dependencies=dependencies,
    )
    assert replayed.verdict == adjudicated.verdict
    assert check_calls == []
    assert execution.ledger_path.read_bytes() == frozen_bytes


def test_parent_commit_reconciliation_rereads_exact_result_and_state_binding(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.settlement import (
        TrialSettlementError,
        commit_trial_parent_settlement,
    )

    fixture, execution, adjudicated, envelope, prepared = _prepare_terminal_trial(
        tmp_path
    )
    artifacts = _parent_artifacts(adjudicated)
    state_path = tmp_path / "parent-state.json"
    unsettled = _parent_state(
        fixture,
        envelope,
        artifacts,
        current_step={"name": "compare", "status": "running"},
    )
    unsettled["steps"] = {}
    _write_parent_state(state_path, unsettled)
    reads = 0

    def read_parent_state():
        nonlocal reads
        reads += 1
        return json.loads(state_path.read_bytes())

    before = execution.ledger_path.read_bytes()
    with pytest.raises(TrialSettlementError, match="parent trial state is not settled"):
        commit_trial_parent_settlement(
            execution.ledger_path,
            request=fixture["request"],
            prepared=prepared,
            step_name="compare",
            expected_artifacts=artifacts,
            read_parent_state=read_parent_state,
        )
    assert reads == 1
    assert execution.ledger_path.read_bytes() == before

    _write_parent_state(
        state_path,
        _parent_state(fixture, envelope, artifacts),
    )
    committed = commit_trial_parent_settlement(
        execution.ledger_path,
        request=fixture["request"],
        prepared=prepared,
        step_name="compare",
        expected_artifacts=artifacts,
        read_parent_state=read_parent_state,
        recorded_at=prepared.row.recorded_at,
    )
    assert reads == 2
    committed_bytes = execution.ledger_path.read_bytes()
    assert (
        commit_trial_parent_settlement(
            execution.ledger_path,
            request=fixture["request"],
            prepared=prepared,
            step_name="compare",
            expected_artifacts=artifacts,
            read_parent_state=read_parent_state,
        )
        == committed
    )
    assert reads == 3
    assert execution.ledger_path.read_bytes() == committed_bytes

    changed = _parent_state(fixture, envelope, artifacts)
    changed["steps"]["compare"]["trial"] = {
        **envelope,
        "verdict": {
            **envelope["verdict"],
            "selected_arm": "not-the-persisted-result",
        },
    }
    _write_parent_state(state_path, changed)
    with pytest.raises(TrialSettlementError, match="parent trial result disagrees"):
        commit_trial_parent_settlement(
            execution.ledger_path,
            request=fixture["request"],
            prepared=prepared,
            step_name="compare",
            expected_artifacts=artifacts,
            read_parent_state=read_parent_state,
        )
    assert reads == 4
    assert execution.ledger_path.read_bytes() == committed_bytes

    changed = _parent_state(fixture, envelope, {"verdict": "wrong-path"})
    _write_parent_state(state_path, changed)
    with pytest.raises(TrialSettlementError, match="parent trial artifacts disagree"):
        commit_trial_parent_settlement(
            execution.ledger_path,
            request=fixture["request"],
            prepared=prepared,
            step_name="compare",
            expected_artifacts=artifacts,
            read_parent_state=read_parent_state,
        )
    assert reads == 5
    assert execution.ledger_path.read_bytes() == committed_bytes


def test_outer_settlement_rejects_missing_and_wrong_order_authority(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.settlement import (
        TrialSettlementError,
        prepare_trial_parent_settlement,
    )

    fixture = _runtime_fixture(tmp_path)
    execution = _execute(fixture, _blinded_cell_harnesses())
    with pytest.raises(TrialSettlementError, match="verdict published.*missing"):
        prepare_trial_parent_settlement(
            execution.ledger_path,
            request=fixture["request"],
            parent_workspace=fixture["parent_workspace"],
            result_envelope={},
        )

    fixture, execution, _adjudicated, envelope = _terminal_trial(
        tmp_path / "wrong-order"
    )
    ledger = load_trial_event_ledger(execution.ledger_path)
    before = execution.ledger_path.read_bytes()
    with pytest.raises(TrialLedgerError, match="terminal verdict publication"):
        append_trial_parent_commit(
            execution.ledger_path,
            expected_head_digest=ledger.rows[-1].row_digest,
            trial_prepared_row_digest=canonical_sha256("absent"),
            result_envelope_digest=canonical_sha256(envelope),
            parent_state_settlement_digest=canonical_sha256("parent-state"),
            recorded_at=ledger.rows[-1].recorded_at,
        )
    assert execution.ledger_path.read_bytes() == before


def test_prepare_rejects_tampered_result_or_artifact_without_appending(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.settlement import (
        TrialSettlementError,
        prepare_trial_parent_settlement,
    )

    fixture, execution, adjudicated, envelope = _terminal_trial(tmp_path)
    before = execution.ledger_path.read_bytes()
    changed = dict(envelope)
    changed["verdict"] = {
        **envelope["verdict"],
        "selected_arm": "not-the-settled-verdict",
    }
    with pytest.raises(TrialSettlementError, match="terminal result"):
        prepare_trial_parent_settlement(
            execution.ledger_path,
            request=fixture["request"],
            parent_workspace=fixture["parent_workspace"],
            result_envelope=changed,
        )
    assert execution.ledger_path.read_bytes() == before

    artifact_before = adjudicated.verdict_artifact.path.read_bytes()
    artifact_record = json.loads(artifact_before)
    artifact_record["verdict"]["ranking"].reverse()
    adjudicated.verdict_artifact.path.write_bytes(
        canonical_json_bytes(artifact_record) + b"\n"
    )
    with pytest.raises(TrialSettlementError, match="artifact authority disagrees"):
        prepare_trial_parent_settlement(
            execution.ledger_path,
            request=fixture["request"],
            parent_workspace=fixture["parent_workspace"],
            result_envelope=envelope,
        )
    assert execution.ledger_path.read_bytes() == before


def test_loader_rejects_tampered_or_duplicate_outer_authority(
    tmp_path: Path,
) -> None:
    _fixture, execution, _adjudicated, _envelope, prepared = _prepare_terminal_trial(
        tmp_path
    )
    original_rows = [
        json.loads(line) for line in execution.ledger_path.read_bytes().splitlines()
    ]

    tampered = [dict(row) for row in original_rows]
    tampered[-1] = {
        **tampered[-1],
        "payload": {
            **tampered[-1]["payload"],
            "result_contract_digest": canonical_sha256("wrong-contract"),
        },
    }
    _write_rechained_rows(execution.ledger_path, tampered)
    with pytest.raises(TrialLedgerError, match="preparation authority disagrees"):
        load_trial_event_ledger(execution.ledger_path)

    outcomes_tampered = [dict(row) for row in original_rows]
    outcomes_tampered[-1] = {
        **outcomes_tampered[-1],
        "payload": {
            **outcomes_tampered[-1]["payload"],
            "authored_outcomes_digest": canonical_sha256("wrong-outcomes"),
        },
    }
    _write_rechained_rows(execution.ledger_path, outcomes_tampered)
    with pytest.raises(TrialLedgerError, match="authored outcomes.*disagrees"):
        load_trial_event_ledger(execution.ledger_path)

    duplicate = [dict(row) for row in original_rows]
    duplicate.append(
        {
            **prepared.row.record,
            "recorded_at": prepared.row.recorded_at,
        }
    )
    _write_rechained_rows(execution.ledger_path, duplicate)
    with pytest.raises(TrialLedgerError, match="parent commit must immediately follow"):
        load_trial_event_ledger(execution.ledger_path)


def test_noncanonical_ledger_path_is_rejected_before_prepare_mutation(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.trial.settlement import prepare_trial_parent_settlement

    fixture, execution, _adjudicated, envelope = _terminal_trial(tmp_path)
    before = execution.ledger_path.read_bytes()
    relative = Path(os.path.relpath(execution.ledger_path, Path.cwd()))

    with pytest.raises(ValueError, match="ledger path must be canonical"):
        prepare_trial_parent_settlement(
            relative,
            request=fixture["request"],
            parent_workspace=fixture["parent_workspace"],
            result_envelope=envelope,
        )
    assert execution.ledger_path.read_bytes() == before
