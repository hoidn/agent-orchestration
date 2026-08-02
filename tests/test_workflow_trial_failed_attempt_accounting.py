from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from threading import Lock

import pytest

import orchestrator.workflow.trial.runtime as trial_runtime_module
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.ledger import allocate_attempt
from orchestrator.workflow.run_ref.runtime import (
    RunRefLifecycleEvent,
    acknowledge_persisted_run_ref_lifecycle_event,
)
from orchestrator.workflow.trial.ledger import (
    TrialLedgerError,
    append_trial_e1_allocation_start,
    append_trial_e1_boundary,
    discard_incomplete_trial_cell,
    load_trial_event_ledger,
)
from orchestrator.workflow.trial.runtime import (
    TrialRuntimeDependencies,
    execute_trial_cells,
)
from tests.test_workflow_trial_ledger import _attempt_bindings, _initialized
from tests.test_workflow_trial_runtime import (
    _CellHarnesses,
    _InjectedCrash,
    _runtime_fixture,
)


class _IncrementingClock:
    def __init__(self, start: int, step: int) -> None:
        self._next = start
        self._step = step
        self._lock = Lock()

    def __call__(self) -> int:
        with self._lock:
            value = self._next
            self._next += self._step
            return value


class _ManualClock:
    def __init__(self, now_ns: int) -> None:
        self._now_ns = now_ns
        self._lock = Lock()

    def __call__(self) -> int:
        with self._lock:
            return self._now_ns

    def set(self, now_ns: int) -> None:
        with self._lock:
            self._now_ns = now_ns

    def advance(self, elapsed_ns: int) -> None:
        with self._lock:
            self._now_ns += elapsed_ns


def _execute(
    fixture,
    harnesses,
    *,
    monotonic_ns,
    wall_time_ns,
    crash_hook=lambda _boundary: None,
):
    return execute_trial_cells(
        fixture["request"],
        parent_state=fixture["parent_state"],
        parent_workspace=fixture["parent_workspace"],
        parent_run_root=fixture["parent_run_root"],
        run_ref_root=fixture["run_ref_root"],
        capsule_dir=fixture["capsule_dir"],
        sealed_opaque_labels=fixture["sealed"],
        dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=harnesses.factory,
            monotonic_ns=monotonic_ns,
            wall_time_ns=wall_time_ns,
            crash_hook=crash_hook,
        ),
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


def test_launched_failure_persists_measured_elapsed_and_resume_reuses_exact_row(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    failed_cell = fixture["request"].cell_domain[0]
    harnesses = _CellHarnesses(failing={failed_cell})
    monotonic = _IncrementingClock(1_000_000_000, 3_000_000)
    wall = _IncrementingClock(2_000_000_000, 5_000_000)

    first = _execute(
        fixture,
        harnesses,
        monotonic_ns=monotonic,
        wall_time_ns=wall,
    )
    ledger = load_trial_event_ledger(first.ledger_path)
    allocation = next(
        row
        for row in ledger.rows
        if row.kind == "cell_allocated" and row.payload["cell"] == failed_cell.record
    )
    failure = next(
        row
        for row in ledger.rows
        if row.kind == "cell_failed" and row.payload["cell"] == failed_cell.record
    )
    assert allocation.payload["started_at_unix_ns"] == 2_005_000_000
    assert allocation.payload["started_monotonic_ns"] >= 0
    assert failure.payload["started_monotonic_ns"] == allocation.payload[
        "started_monotonic_ns"
    ]
    assert failure.payload["terminal_monotonic_ns"] >= failure.payload[
        "started_monotonic_ns"
    ]
    assert failure.payload["elapsed_ms"] == (
        failure.payload["terminal_monotonic_ns"]
        - failure.payload["started_monotonic_ns"]
    ) // 1_000_000
    original = first.ledger_path.read_bytes()

    resumed = _execute(
        fixture,
        harnesses,
        monotonic_ns=monotonic,
        wall_time_ns=wall,
    )
    assert resumed.ledger_path.read_bytes() == original

    _write_rechained(
        first.ledger_path,
        lambda rows: next(
            row
            for row in rows
            if row["kind"] == "cell_failed"
            and row["payload"]["cell"] == failed_cell.record
        )["payload"].__setitem__("elapsed_ms", failure.payload["elapsed_ms"] + 1),
    )
    with pytest.raises(TrialLedgerError, match="elapsed|timing"):
        load_trial_event_ledger(first.ledger_path)


@pytest.mark.parametrize("failed", [False, True])
def test_start_only_crash_reuses_exact_durable_start_for_driver_and_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed: bool,
) -> None:
    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    cell = fixture["request"].cell_domain[0]
    harnesses = _CellHarnesses(failing={cell} if failed else set())
    monotonic = _ManualClock(1_000_000)
    wall = _ManualClock(2_000_000_000)
    original_factory = harnesses.factory
    original_driver = trial_runtime_module.drive_run_ref_lifecycle
    original_persist = trial_runtime_module.persist_run_ref_lifecycle_event
    driver_starts: dict[Path, list[int]] = {}
    crashed = False

    def timed_factory(candidate, request):
        dependencies = original_factory(candidate, request)
        launch = dependencies.launch_child

        def timed_launch(child):
            monotonic.advance(5_000_000)
            return launch(child)

        return replace(dependencies, launch_child=timed_launch)

    def observing_driver(request, **kwargs):
        allocation = kwargs["allocation"]
        driver_starts.setdefault(allocation.effect_instance_root, []).append(
            kwargs["started_monotonic_ns"]
        )
        return original_driver(request, **kwargs)

    def crash_before_e1_persist(request, event):
        nonlocal crashed
        if not crashed and event.stage == "allocated":
            crashed = True
            raise _InjectedCrash("after_trial_start_before_e1_allocation")
        return original_persist(request, event)

    harnesses.factory = timed_factory
    monkeypatch.setattr(
        trial_runtime_module,
        "drive_run_ref_lifecycle",
        observing_driver,
    )
    monkeypatch.setattr(
        trial_runtime_module,
        "persist_run_ref_lifecycle_event",
        crash_before_e1_persist,
    )

    with pytest.raises(_InjectedCrash, match="after_trial_start"):
        _execute(
            fixture,
            harnesses,
            monotonic_ns=monotonic,
            wall_time_ns=wall,
        )

    ledger_path = fixture["scopes"][0].trial_root / "trial-events.jsonl"
    first_rows = load_trial_event_ledger(ledger_path).rows
    original_start = next(
        row
        for row in first_rows
        if row.kind == "cell_allocation_started"
        and row.payload["cell"] == cell.record
    )
    assert original_start.payload["started_at_unix_ns"] == 2_000_000_000
    assert original_start.payload["started_monotonic_ns"] == 1_000_000
    assert not fixture["scopes"][0].ledger_path.exists()

    monotonic.set(21_000_000)
    wall.set(3_000_000_000)
    monkeypatch.setattr(
        trial_runtime_module,
        "persist_run_ref_lifecycle_event",
        original_persist,
    )
    execution = _execute(
        fixture,
        harnesses,
        monotonic_ns=monotonic,
        wall_time_ns=wall,
    )

    rows = load_trial_event_ledger(ledger_path).rows
    starts = [
        row
        for row in rows
        if row.kind == "cell_allocation_started"
        and row.payload["cell"] == cell.record
    ]
    assert [row.row_digest for row in starts] == [original_start.row_digest]
    assert driver_starts[fixture["scopes"][0].effect_instance_root] == [
        1_000_000,
        1_000_000,
    ]
    if failed:
        failure = next(
            row
            for row in rows
            if row.kind == "cell_failed" and row.payload["cell"] == cell.record
        )
        assert failure.payload["started_monotonic_ns"] == 1_000_000
        assert failure.payload["terminal_monotonic_ns"] == 26_000_000
        assert failure.payload["elapsed_ms"] == 25
    else:
        outcome = next(value for value in execution.outcomes if value.cell == cell)
        assert outcome.envelope["accounting"]["elapsed_ms"] == 25


def test_unstarted_deadline_failure_persists_zero_without_timing_endpoints(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(
        tmp_path,
        arm_timeout_ms=1,
        trial_timeout_ms=1,
        max_concurrency=1,
    )
    monotonic = _IncrementingClock(10_000_000, 2_000_000)
    execution = _execute(
        fixture,
        _CellHarnesses(),
        monotonic_ns=monotonic,
        wall_time_ns=_IncrementingClock(20_000_000, 1_000_000),
    )

    rows = load_trial_event_ledger(execution.ledger_path).rows
    assert not any(row.kind == "cell_allocated" for row in rows)
    failures = [row for row in rows if row.kind == "cell_failed"]
    assert failures
    assert all(
        row.payload["elapsed_ms"] == 0
        and row.payload["started_monotonic_ns"] is None
        and row.payload["terminal_monotonic_ns"] is None
        for row in failures
    )


def test_discard_uses_explicit_wall_facts_and_rejects_clock_regression(
    tmp_path: Path,
) -> None:
    _result, _node, _request, scopes, _sealed, header = _initialized(tmp_path)
    scope = scopes[0]
    bindings = _attempt_bindings(scope)
    event = RunRefLifecycleEvent.build(
        sequence=1,
        event_kind="allocation",
        stage="allocated",
        visit=header.request.visit,
        attempt_ordinal=1,
        effect_instance_root=scope.effect_instance_root,
        payload={"bindings": bindings.record},
    )
    append_trial_e1_allocation_start(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        cell=scope.cell,
        event=event,
        started_at_unix_ns=1_000_000_000,
        started_monotonic_ns=7_000_000,
        recorded_at="2026-08-02T12:00:00.000000Z",
    )
    authority = allocate_attempt(
        scope.ledger_path,
        visit=header.request.visit,
        bindings=bindings,
        recorded_at="2026-08-02T12:00:00.000000Z",
    )
    acknowledgement = acknowledge_persisted_run_ref_lifecycle_event(
        event,
        expected_row_digest=authority.row_digest,
    )
    append_trial_e1_boundary(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        cell=scope.cell,
        event=event,
        acknowledgement=acknowledgement,
        recorded_at="2026-08-02T12:00:01.000000Z",
    )
    bindings.workspace_path.mkdir(parents=True)
    before = header.path.read_bytes()

    with pytest.raises(TrialLedgerError, match="clock moved backwards"):
        discard_incomplete_trial_cell(
            header.path,
            expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
            request=header.request,
            cell=scope.cell,
            current_step_config_digest=scope.run_ref_step_config_digest,
            reconciliation_wall_time_ns=999_999_999,
        )
    assert header.path.read_bytes() == before
    assert bindings.workspace_path.exists()

    disposition = discard_incomplete_trial_cell(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        request=header.request,
        cell=scope.cell,
        current_step_config_digest=scope.run_ref_step_config_digest,
        reconciliation_wall_time_ns=1_007_999_999,
        recorded_at="2026-08-02T12:00:10.000000Z",
    )
    ledger = load_trial_event_ledger(header.path)
    discarded = next(
        row for row in ledger.rows if row.row_digest == disposition.trial_row_digest
    )
    assert discarded.payload["reconciled_at_unix_ns"] == 1_007_999_999
    assert discarded.payload["elapsed_ms"] == 7

    original = header.path.read_bytes()
    _write_rechained(
        header.path,
        lambda rows: next(row for row in rows if row["kind"] == "cell_discarded")[
            "payload"
        ].__setitem__("elapsed_ms", 8),
    )
    with pytest.raises(TrialLedgerError, match="elapsed|timing"):
        load_trial_event_ledger(header.path)
    header.path.write_bytes(original)

    _write_rechained(
        header.path,
        lambda rows: next(row for row in rows if row["kind"] == "cell_allocated")[
            "payload"
        ].pop("started_at_unix_ns"),
    )
    with pytest.raises(TrialLedgerError):
        load_trial_event_ledger(header.path)


def test_orphan_e1_allocation_reuses_its_durable_start_for_discard(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    harnesses = _CellHarnesses()

    def crash_after_e1_allocation(boundary: str) -> None:
        if boundary == "after_e1_allocation_before_trial_allocation":
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash):
        _execute(
            fixture,
            harnesses,
            monotonic_ns=lambda: 100,
            wall_time_ns=lambda: 100,
            crash_hook=crash_after_e1_allocation,
        )

    execution = _execute(
        fixture,
        harnesses,
        monotonic_ns=lambda: 2_000_000,
        wall_time_ns=lambda: 2_000_000,
    )
    rows = load_trial_event_ledger(execution.ledger_path).rows
    first_cell = fixture["request"].cell_domain[0]
    first_attempt = next(
        row
        for row in rows
        if row.kind == "cell_allocated"
        and row.payload["cell"] == first_cell.record
        and row.payload["attempt_ordinal"] == 1
    )
    discarded = next(
        row
        for row in rows
        if row.kind == "cell_discarded"
        and row.payload["cell"] == first_cell.record
        and row.payload["attempt_ordinal"] == 1
    )

    assert first_attempt.payload["started_at_unix_ns"] == 100
    assert discarded.payload["reconciled_at_unix_ns"] == 2_000_000
    assert discarded.payload["elapsed_ms"] == 1


def test_orphan_e1_allocation_rejects_tampered_start_binding_without_mutation(
    tmp_path: Path,
) -> None:
    fixture = _runtime_fixture(tmp_path, max_concurrency=1)
    harnesses = _CellHarnesses()

    def crash_after_e1_allocation(boundary: str) -> None:
        if boundary == "after_e1_allocation_before_trial_allocation":
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash):
        _execute(
            fixture,
            harnesses,
            monotonic_ns=lambda: 100,
            wall_time_ns=lambda: 100,
            crash_hook=crash_after_e1_allocation,
        )
    ledger_path = fixture["scopes"][0].trial_root / "trial-events.jsonl"
    _write_rechained(
        ledger_path,
        lambda rows: next(
            row for row in rows if row["kind"] == "cell_allocation_started"
        )["payload"].__setitem__(
            "e1_allocation_event_digest",
            "sha256:" + "0" * 64,
        ),
    )
    before = ledger_path.read_bytes()

    with pytest.raises(TrialLedgerError, match="start authority disagrees"):
        _execute(
            fixture,
            harnesses,
            monotonic_ns=lambda: 2_000_000,
            wall_time_ns=lambda: 2_000_000,
        )

    assert ledger_path.read_bytes() == before
    assert harnesses.launches == []
