from __future__ import annotations

from pathlib import Path
import json
import subprocess

import pytest

from orchestrator.workflow.executable_ir import TrialStepConfig
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.trial import checks as trial_checks
import orchestrator.workflow.trial.ledger as trial_ledger
from orchestrator.workflow.trial.config import (
    build_trial_runtime_request,
    build_trial_static_config,
)
from orchestrator.workflow.trial.contracts import (
    build_sealed_opaque_label_map,
    derive_trial_cell_effect_scopes,
)
from orchestrator.workflow.trial.ledger import (
    TrialLedgerError,
    append_trial_evidence_freeze,
    load_trial_event_ledger,
)
from tests.test_workflow_trial_runtime import (
    _CellHarnesses,
    _execute,
    _runtime_fixture,
)


def _fixture_with_checks(tmp_path: Path, checks):
    fixture = _runtime_fixture(tmp_path)
    current = fixture["request"]
    evaluation = current.static_config.evaluation
    evaluation["checks"] = list(checks)
    static = build_trial_static_config(
        compiler_runtime_identity_digest=(
            current.static_config.compiler_runtime_identity_digest
        ),
        site_digest=current.static_config.site_digest,
        arms=current.static_config.arms,
        reps=current.static_config.reps,
        max_concurrency=current.static_config.max_concurrency,
        evaluation=evaluation,
        budget=current.static_config.budget,
        result_descriptor=current.static_config.result_descriptor,
        result_digest=current.static_config.result_digest,
    )
    step = TrialStepConfig(
        common=current.step_config.common,
        trial=static,
        arms=current.step_config.arms,
    )
    request = build_trial_runtime_request(
        step_config=step,
        visit=current.visit,
        resolved_inputs_by_arm=current.resolved_inputs_by_arm,
    )
    fixture["request"] = request
    fixture["scopes"] = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=fixture["parent_run_root"],
        run_ref_root=fixture["run_ref_root"],
    )
    fixture["sealed"] = build_sealed_opaque_label_map(
        request.cell_domain,
        salt=b"task-eight-check-authority-salt-v1",
    )
    return fixture


def _freeze_terminal_cells(fixture, harnesses):
    execution = _execute(fixture, harnesses)
    before = load_trial_event_ledger(execution.ledger_path)
    evidence = append_trial_evidence_freeze(
        execution.ledger_path,
        expected_head_digest=before.rows[-1].row_digest,
    )
    return execution, evidence


def _rewrite_trial_ledger(path: Path, mutate) -> None:
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


def test_check_phase_uses_global_authority_and_authored_cell_order(
    tmp_path: Path,
) -> None:
    checks = (
        {
            "check_id": "invariant-a",
            "command": ["probe", "invariant-a"],
            "authority": "invariant",
            "required": False,
            "timeout_ms": 1000,
        },
        {
            "check_id": "correct-a",
            "command": ["probe", "correct-a"],
            "authority": "correctness",
            "required": True,
            "timeout_ms": 1000,
        },
        {
            "check_id": "correct-b",
            "command": ["probe", "correct-b"],
            "authority": "correctness",
            "required": False,
            "timeout_ms": 1000,
        },
    )
    fixture = _fixture_with_checks(tmp_path, checks)
    failed_cell = fixture["request"].cell_domain[1]
    execution, evidence = _freeze_terminal_cells(
        fixture,
        _CellHarnesses(failing={failed_cell}),
    )
    completed = tuple(
        outcome
        for outcome in execution.outcomes
        if outcome.status == "completed"
    )
    calls: list[tuple[tuple[str, ...], Path, bool]] = []
    clock_value = 0

    def clock() -> int:
        nonlocal clock_value
        clock_value += 1_000_000
        return clock_value

    def runner(argv, *, cwd, shell, **_kwargs):
        calls.append((tuple(argv), Path(cwd), shell))
        return subprocess.CompletedProcess(argv, 0, stdout=b"ok", stderr=b"")

    frozen = trial_checks.ensure_trial_checks_frozen(
        execution.ledger_path,
        request=fixture["request"],
        runner=runner,
        monotonic_ns=clock,
    )

    ordered_check_ids = ("correct-a", "correct-b", "invariant-a")
    assert calls == [
        (("probe", check_id), outcome.settled_result.workspace_path, False)
        for check_id in ordered_check_ids
        for outcome in completed
    ]
    ledger = load_trial_event_ledger(execution.ledger_path)
    check_rows = tuple(row for row in ledger.rows if row.kind == "check_settled")
    assert len(check_rows) == len(ordered_check_ids) * len(completed)
    assert frozen == ledger.rows[-1]
    assert frozen.kind == "checks_frozen"
    for row in check_rows:
        payload = row.payload
        assert payload["evidence_frozen_row_digest"] == evidence.row_digest
        assert payload["check_id"] == payload["check_result"]["check_id"]
        assert payload["check_result_digest"] == canonical_sha256(
            {
                "schema_version": "trial_check_result.v1",
                "evidence_frozen_digest": evidence.row_digest,
                "check_spec_digest": payload["check_spec_digest"],
                "result": payload["check_result"],
            }
        )
    frozen_by_cell = {
        (row["cell"]["arm_id"], row["cell"]["rep"]): row[
            "check_result_digests"
        ]
        for row in frozen.payload["cell_checks"]
    }
    assert frozen_by_cell[(failed_cell.arm_id, failed_cell.rep)] == []
    assert all(
        len(frozen_by_cell[(outcome.cell.arm_id, outcome.cell.rep)]) == 3
        for outcome in completed
    )
    assert any(
        row.payload["check_result"]["required"] is False
        for row in check_rows
    )


def test_check_phase_resume_skips_the_valid_settled_prefix(tmp_path: Path) -> None:
    checks = (
        {
            "check_id": "correct",
            "command": ["probe", "correct"],
            "authority": "correctness",
            "required": True,
            "timeout_ms": 1000,
        },
        {
            "check_id": "invariant",
            "command": ["probe", "invariant"],
            "authority": "invariant",
            "required": False,
            "timeout_ms": 1000,
        },
    )
    fixture = _fixture_with_checks(tmp_path, checks)
    execution, _evidence = _freeze_terminal_cells(fixture, _CellHarnesses())
    first_calls: list[tuple[str, Path]] = []
    settled = 0

    def first_runner(argv, *, cwd, **_kwargs):
        first_calls.append((argv[1], Path(cwd)))
        return subprocess.CompletedProcess(argv, 0, stdout=b"first", stderr=b"")

    def crash_after_two(marker: str) -> None:
        nonlocal settled
        if marker == "check_settled":
            settled += 1
            if settled == 2:
                raise RuntimeError("injected check crash")

    try:
        trial_checks.ensure_trial_checks_frozen(
            execution.ledger_path,
            request=fixture["request"],
            runner=first_runner,
            monotonic_ns=iter(range(0, 100_000_000, 1_000_000)).__next__,
            crash_hook=crash_after_two,
        )
    except RuntimeError as exc:
        assert str(exc) == "injected check crash"
    else:  # pragma: no cover - the assertion documents the injected boundary
        raise AssertionError("check crash was not injected")

    interrupted = load_trial_event_ledger(execution.ledger_path)
    prefix = tuple(row for row in interrupted.rows if row.kind == "check_settled")
    assert len(prefix) == 2
    assert [name for name, _cwd in first_calls] == ["correct", "correct"]

    resumed_calls: list[tuple[str, Path]] = []

    def resumed_runner(argv, *, cwd, **_kwargs):
        resumed_calls.append((argv[1], Path(cwd)))
        return subprocess.CompletedProcess(argv, 0, stdout=b"resumed", stderr=b"")

    frozen = trial_checks.ensure_trial_checks_frozen(
        execution.ledger_path,
        request=fixture["request"],
        runner=resumed_runner,
        monotonic_ns=iter(range(0, 100_000_000, 1_000_000)).__next__,
    )

    completed = tuple(
        outcome
        for outcome in execution.outcomes
        if outcome.status == "completed"
    )
    assert resumed_calls == [
        (check_id, outcome.settled_result.workspace_path)
        for check_id in ("correct", "invariant")
        for outcome in completed
    ][2:]
    final_ledger = load_trial_event_ledger(execution.ledger_path)
    assert tuple(
        row for row in final_ledger.rows if row.kind == "check_settled"
    )[:2] == prefix
    assert frozen == final_ledger.rows[-1]
    frozen_bytes = execution.ledger_path.read_bytes()
    no_calls: list[object] = []
    assert (
        trial_checks.ensure_trial_checks_frozen(
            execution.ledger_path,
            request=fixture["request"],
            runner=lambda *_args, **_kwargs: no_calls.append(object()),
        )
        == frozen
    )
    assert no_calls == []
    assert execution.ledger_path.read_bytes() == frozen_bytes


def test_check_result_rejects_rechained_noncanonical_bounded_output(
    tmp_path: Path,
) -> None:
    fixture = _fixture_with_checks(
        tmp_path,
        (
            {
                "check_id": "correct",
                "command": ["probe", "correct"],
                "authority": "correctness",
                "required": True,
                "timeout_ms": 1000,
            },
        ),
    )
    execution, _evidence = _freeze_terminal_cells(fixture, _CellHarnesses())

    with pytest.raises(RuntimeError, match="injected"):
        trial_checks.ensure_trial_checks_frozen(
            execution.ledger_path,
            request=fixture["request"],
            runner=lambda argv, **_kwargs: subprocess.CompletedProcess(
                argv,
                0,
                stdout=b"bounded",
                stderr=b"",
            ),
            crash_hook=lambda marker: (
                (_ for _ in ()).throw(RuntimeError("injected"))
                if marker == "check_settled"
                else None
            ),
        )

    def corrupt(rows) -> None:
        row = next(row for row in rows if row["kind"] == "check_settled")
        payload = row["payload"]
        payload["check_result"]["output_bytes"] = "not-json"
        payload["check_result_digest"] = canonical_sha256(
            {
                "schema_version": "trial_check_result.v1",
                "evidence_frozen_digest": payload["evidence_frozen_row_digest"],
                "check_spec_digest": payload["check_spec_digest"],
                "result": payload["check_result"],
            }
        )

    _rewrite_trial_ledger(execution.ledger_path, corrupt)

    with pytest.raises(TrialLedgerError, match="output bytes"):
        load_trial_event_ledger(execution.ledger_path)


def test_coherent_check_substitution_fails_before_runner_or_mutation(
    tmp_path: Path,
) -> None:
    fixture = _fixture_with_checks(
        tmp_path,
        (
            {
                "check_id": "correct",
                "command": ["probe", "correct"],
                "authority": "correctness",
                "required": True,
                "timeout_ms": 1000,
            },
        ),
    )
    execution, _evidence = _freeze_terminal_cells(fixture, _CellHarnesses())
    with pytest.raises(RuntimeError, match="injected"):
        trial_checks.ensure_trial_checks_frozen(
            execution.ledger_path,
            request=fixture["request"],
            runner=lambda argv, **_kwargs: subprocess.CompletedProcess(
                argv, 0, stdout=b"ok", stderr=b""
            ),
            crash_hook=lambda marker: (
                (_ for _ in ()).throw(RuntimeError("injected"))
                if marker == "check_settled"
                else None
            ),
        )

    def substitute(rows) -> None:
        row = next(row for row in rows if row["kind"] == "check_settled")
        payload = row["payload"]
        payload["check_id"] = "forged"
        payload["check_spec_digest"] = canonical_sha256(
            {
                "check_id": "forged",
                "command": ["probe", "forged"],
                "authority": "correctness",
                "required": True,
                "timeout_ms": 1000,
            }
        )
        payload["check_result"]["check_id"] = "forged"
        payload["check_result_digest"] = canonical_sha256(
            {
                "schema_version": "trial_check_result.v1",
                "evidence_frozen_digest": payload["evidence_frozen_row_digest"],
                "check_spec_digest": payload["check_spec_digest"],
                "result": payload["check_result"],
            }
        )

    _rewrite_trial_ledger(execution.ledger_path, substitute)
    load_trial_event_ledger(execution.ledger_path)
    before = execution.ledger_path.read_bytes()
    calls: list[object] = []
    with pytest.raises(TrialLedgerError, match="current static authority"):
        trial_checks.ensure_trial_checks_frozen(
            execution.ledger_path,
            request=fixture["request"],
            runner=lambda *_args, **_kwargs: calls.append(object()),
        )
    assert calls == []
    assert execution.ledger_path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["missing", "reordered"])
def test_missing_or_reordered_check_prefix_fails_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = _fixture_with_checks(
        tmp_path,
        (
            {
                "check_id": "correct",
                "command": ["probe", "correct"],
                "authority": "correctness",
                "required": True,
                "timeout_ms": 1000,
            },
        ),
    )
    execution, _evidence = _freeze_terminal_cells(fixture, _CellHarnesses())
    settled = 0

    def crash_after_two(marker: str) -> None:
        nonlocal settled
        if marker == "check_settled":
            settled += 1
            if settled == 2:
                raise RuntimeError("injected")

    with pytest.raises(RuntimeError, match="injected"):
        trial_checks.ensure_trial_checks_frozen(
            execution.ledger_path,
            request=fixture["request"],
            runner=lambda argv, **_kwargs: subprocess.CompletedProcess(
                argv, 0, stdout=b"ok", stderr=b""
            ),
            crash_hook=crash_after_two,
        )

    def break_prefix(rows) -> None:
        indices = [
            index for index, row in enumerate(rows) if row["kind"] == "check_settled"
        ]
        assert len(indices) == 2
        if mutation == "missing":
            rows.pop(indices[0])
        else:
            first, second = indices
            rows[first]["payload"], rows[second]["payload"] = (
                rows[second]["payload"],
                rows[first]["payload"],
            )

    _rewrite_trial_ledger(execution.ledger_path, break_prefix)
    with pytest.raises(TrialLedgerError, match="authored cell order"):
        load_trial_event_ledger(execution.ledger_path)


def test_checks_freeze_cannot_omit_configured_authority(tmp_path: Path) -> None:
    fixture = _fixture_with_checks(
        tmp_path,
        (
            {
                "check_id": "correct",
                "command": ["probe", "correct"],
                "authority": "correctness",
                "required": True,
                "timeout_ms": 1000,
            },
        ),
    )
    execution, evidence = _freeze_terminal_cells(fixture, _CellHarnesses())

    with pytest.raises(TrialLedgerError, match="omits current static"):
        trial_ledger.append_trial_checks_freeze(
            execution.ledger_path,
            expected_head_digest=evidence.row_digest,
            request=fixture["request"],
        )
