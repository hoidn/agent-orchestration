from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil

import pytest

from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.ledger import (
    RUN_REF_ATTEMPT_LEDGER_SCHEMA,
    RunRefAttemptBindings,
    RunRefLedgerError,
    SettledRunRefResultBinding,
    RunRefVisitKey,
    advance_attempt,
    allocate_attempt,
    identify_incomplete_attempt,
    load_attempt_ledger,
    reconcile_pending_parent_commit,
    record_discarded_attempt,
    select_committed_reuse,
    settled_result_binding,
    settled_result_binding_from_record,
    validate_pending_parent_commit,
)


def _digest(marker: str) -> str:
    assert len(marker) == 1
    return "sha256:" + marker * 64


def _visit() -> RunRefVisitKey:
    return RunRefVisitKey(
        parent_run_id="parent-run",
        execution_frame_id="root",
        call_frame_id=None,
        step_id="root.run-ref",
        visit_count=1,
    )


def _allocated_bindings(tmp_path: Path, *, ordinal: int = 1) -> RunRefAttemptBindings:
    root = (tmp_path / "run-ref-root").resolve()
    return RunRefAttemptBindings(
        run_ref_root=root,
        workspace_path=(
            root
            / "runs"
            / "parent-run"
            / "root.run-ref"
            / str(ordinal)
            / "workspace"
        ),
        source_digest=_digest("1"),
        program_digest=_digest("2"),
        input_digest=_digest("3"),
        policy_digest=_digest("4"),
        step_config_digest=_digest("5"),
        capsule_or_compiler_digest=_digest("6"),
        child_run_id=f"parent-run--root.run-ref--{ordinal}",
        result_contract_digest=_digest("7"),
    )


def test_allocate_persists_one_strict_canonical_row(tmp_path: Path) -> None:
    path = tmp_path / "parent" / "run-ref-attempts.jsonl"

    allocated = allocate_attempt(
        path,
        visit=_visit(),
        bindings=_allocated_bindings(tmp_path),
        recorded_at="2026-08-01T12:00:00.000000Z",
    )

    assert allocated.attempt_ordinal == 1
    assert allocated.stage == "allocated"
    assert allocated.status == "in_progress"
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    row = json.loads(raw)
    assert raw == canonical_json_bytes(row) + b"\n"
    assert row["schema_version"] == RUN_REF_ATTEMPT_LEDGER_SCHEMA
    assert row["sequence"] == 1
    assert row["previous_row_digest"] is None
    assert row["row_digest"] == allocated.row_digest
    assert load_attempt_ledger(path).rows == (allocated,)


def test_attempt_advances_only_through_the_closed_crash_boundaries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "parent" / "run-ref-attempts.jsonl"
    visit = _visit()
    allocate_attempt(
        path,
        visit=visit,
        bindings=_allocated_bindings(tmp_path),
        recorded_at="2026-08-01T12:00:00.000000Z",
    )
    transitions = (
        (
            "materialized",
            {"verified_git_tree_id": "git-tree:" + "a" * 40},
        ),
        (
            "setup_completed",
            {
                "setup_evidence_digest": _digest("8"),
                "post_setup_baseline_digest": _digest("9"),
            },
        ),
        (
            "program_prepared",
            {"program_preparation_digest": _digest("a")},
        ),
        ("launched", {"child_launch_digest": _digest("b")}),
        (
            "child_completed",
            {
                "child_terminal_state_digest": _digest("c"),
                "result_payload_digest": _digest("d"),
            },
        ),
        (
            "delta_captured",
            {
                "workspace_delta_digest": _digest("e"),
                "accounting_digest": _digest("f"),
                "evidence_manifest_digest": _digest("0"),
            },
        ),
        ("completed_pending_parent_commit", {}),
    )

    for second, (stage, updates) in enumerate(transitions, start=1):
        row = advance_attempt(
            path,
            visit=visit,
            attempt_ordinal=1,
            stage=stage,
            binding_updates=updates,
            recorded_at=f"2026-08-01T12:00:{second:02d}.000000Z",
        )
        assert row.stage == stage

    ledger = load_attempt_ledger(path)
    assert [row.stage for row in ledger.rows] == [
        "allocated",
        "materialized",
        "setup_completed",
        "program_prepared",
        "launched",
        "child_completed",
        "delta_captured",
        "completed_pending_parent_commit",
    ]
    assert [row.status for row in ledger.rows] == [
        "in_progress",
        "in_progress",
        "in_progress",
        "in_progress",
        "in_progress",
        "in_progress",
        "in_progress",
        "pending_parent_commit",
    ]
    raw_rows = path.read_bytes().splitlines(keepends=True)
    assert len(raw_rows) == 8
    for raw, record in zip(raw_rows, ledger.rows, strict=True):
        assert raw == canonical_json_bytes(record.record) + b"\n"


def _reseal(row: dict[str, object]) -> bytes:
    payload = dict(row)
    payload.pop("row_digest", None)
    row["row_digest"] = canonical_sha256(payload)
    return canonical_json_bytes(row) + b"\n"


def test_loader_rejects_malformed_truncated_noncanonical_and_tampered_rows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.jsonl"
    allocate_attempt(
        path,
        visit=_visit(),
        bindings=_allocated_bindings(tmp_path),
        recorded_at="2026-08-01T12:00:00.000000Z",
    )
    canonical = path.read_bytes()
    parsed = json.loads(canonical)
    variants = (
        b"{\n",
        canonical[:-1],
        json.dumps(parsed, indent=2).encode("utf-8") + b"\n",
        canonical.replace(b'"sequence":1', b'"sequence":2'),
        canonical.replace(
            b'{"attempt_ordinal":1,',
            b'{"attempt_ordinal":1,"attempt_ordinal":1,',
        ),
    )

    for payload in variants:
        path.write_bytes(payload)
        with pytest.raises(RunRefLedgerError):
            load_attempt_ledger(path)


def test_loader_rejects_resealed_stage_skip_and_ambiguous_allocation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.jsonl"
    allocate_attempt(
        path,
        visit=_visit(),
        bindings=_allocated_bindings(tmp_path),
        recorded_at="2026-08-01T12:00:00.000000Z",
    )
    allocated = json.loads(path.read_bytes())

    skipped = json.loads(canonical_json_bytes(allocated))
    skipped["stage"] = "materialized"
    skipped["bindings"]["verified_git_tree_id"] = "git-tree:" + "a" * 40
    path.write_bytes(_reseal(skipped))
    with pytest.raises(RunRefLedgerError, match="predecessor"):
        load_attempt_ledger(path)

    first = _reseal(allocated)
    duplicate = json.loads(canonical_json_bytes(allocated))
    duplicate["sequence"] = 2
    duplicate["previous_row_digest"] = allocated["row_digest"]
    duplicate["recorded_at"] = "2026-08-01T12:00:01.000000Z"
    path.write_bytes(first + _reseal(duplicate))
    with pytest.raises(RunRefLedgerError, match="allocation"):
        load_attempt_ledger(path)


def test_advance_rejects_skipped_or_premature_binding_stages(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.jsonl"
    allocate_attempt(
        path,
        visit=_visit(),
        bindings=_allocated_bindings(tmp_path),
        recorded_at="2026-08-01T12:00:00.000000Z",
    )

    with pytest.raises(RunRefLedgerError, match="binding updates"):
        advance_attempt(
            path,
            visit=_visit(),
            attempt_ordinal=1,
            stage="materialized",
            binding_updates={
                "verified_git_tree_id": "git-tree:" + "a" * 40,
                "setup_evidence_digest": _digest("8"),
            },
        )
    with pytest.raises(RunRefLedgerError, match="transition"):
        advance_attempt(
            path,
            visit=_visit(),
            attempt_ordinal=1,
            stage="setup_completed",
            binding_updates={
                "setup_evidence_digest": _digest("8"),
                "post_setup_baseline_digest": _digest("9"),
            },
        )


def _advance_to_pending(path: Path, tmp_path: Path):
    visit = _visit()
    allocate_attempt(
        path,
        visit=visit,
        bindings=_allocated_bindings(tmp_path),
        recorded_at="2026-08-01T12:00:00.000000Z",
    )
    transitions = (
        ("materialized", {"verified_git_tree_id": "git-tree:" + "a" * 40}),
        (
            "setup_completed",
            {
                "setup_evidence_digest": _digest("8"),
                "post_setup_baseline_digest": _digest("9"),
            },
        ),
        ("program_prepared", {"program_preparation_digest": _digest("a")}),
        ("launched", {"child_launch_digest": _digest("b")}),
        (
            "child_completed",
            {
                "child_terminal_state_digest": _digest("c"),
                "result_payload_digest": _digest("d"),
            },
        ),
        (
            "delta_captured",
            {
                "workspace_delta_digest": _digest("e"),
                "accounting_digest": _digest("f"),
                "evidence_manifest_digest": _digest("0"),
            },
        ),
        ("completed_pending_parent_commit", {}),
    )
    pending = None
    for second, (stage, updates) in enumerate(transitions, start=1):
        pending = advance_attempt(
            path,
            visit=visit,
            attempt_ordinal=1,
            stage=stage,
            binding_updates=updates,
            recorded_at=f"2026-08-01T12:00:{second:02d}.000000Z",
        )
    assert pending is not None
    return pending


def test_pending_row_reconciles_only_from_exact_settled_parent_binding(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.jsonl"
    pending = _advance_to_pending(path, tmp_path)
    settled = settled_result_binding(pending)
    decoded = settled_result_binding_from_record(settled.record)
    assert decoded == settled
    observed: list[str] = []

    committed = reconcile_pending_parent_commit(
        path,
        settled_result=decoded,
        current_step_config_digest=_digest("5"),
        validate_bound_authority=lambda row: observed.append(row.row_digest),
        recorded_at="2026-08-01T12:00:08.000000Z",
    )

    assert committed.stage == "committed"
    assert committed.status == "committed"
    assert observed == [pending.row_digest]
    reused = select_committed_reuse(
        path,
        settled_result=settled,
        current_step_config_digest=_digest("5"),
        validate_bound_authority=lambda row: observed.append(row.row_digest),
    )
    assert reused == committed
    assert observed == [pending.row_digest, committed.row_digest]


def test_pending_parent_commit_guard_accepts_only_the_exact_latest_pending_row(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.jsonl"
    pending = _advance_to_pending(path, tmp_path)
    settled = settled_result_binding(pending)
    before = path.read_bytes()

    assert validate_pending_parent_commit(
        path,
        visit=pending.visit,
        attempt_ordinal=pending.attempt_ordinal,
        current_step_config_digest=_digest("5"),
        settled_result=settled,
    ) is True

    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("expected_visit", "attempt_ordinal", "config_digest", "binding_update"),
    (
        (replace(_visit(), step_id="root.other"), 1, _digest("5"), {}),
        (_visit(), 2, _digest("5"), {}),
        (_visit(), 1, _digest("6"), {}),
        (
            _visit(),
            1,
            _digest("5"),
            {"result_payload_digest": _digest("1")},
        ),
    ),
)
def test_pending_parent_commit_guard_rejects_identity_config_or_binding_drift(
    tmp_path: Path,
    expected_visit: RunRefVisitKey,
    attempt_ordinal: int,
    config_digest: str,
    binding_update: dict[str, str],
) -> None:
    path = tmp_path / "attempts.jsonl"
    pending = _advance_to_pending(path, tmp_path)
    settled = replace(settled_result_binding(pending), **binding_update)
    before = path.read_bytes()

    with pytest.raises(RunRefLedgerError):
        validate_pending_parent_commit(
            path,
            visit=expected_visit,
            attempt_ordinal=attempt_ordinal,
            current_step_config_digest=config_digest,
            settled_result=settled,
        )

    assert path.read_bytes() == before


def test_pending_parent_commit_guard_rejects_missing_or_nonpending_attempt(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.jsonl"
    pending_path = tmp_path / "attempts.jsonl"
    pending = _advance_to_pending(pending_path, tmp_path)
    settled = settled_result_binding(pending)

    with pytest.raises(RunRefLedgerError, match="pending"):
        validate_pending_parent_commit(
            missing,
            visit=pending.visit,
            attempt_ordinal=pending.attempt_ordinal,
            current_step_config_digest=_digest("5"),
            settled_result=settled,
        )

    reconcile_pending_parent_commit(
        pending_path,
        settled_result=settled,
        current_step_config_digest=_digest("5"),
        validate_bound_authority=lambda _row: None,
        recorded_at="2026-08-01T12:00:08.000000Z",
    )
    before = pending_path.read_bytes()
    with pytest.raises(RunRefLedgerError, match="latest.*pending"):
        validate_pending_parent_commit(
            pending_path,
            visit=pending.visit,
            attempt_ordinal=pending.attempt_ordinal,
            current_step_config_digest=_digest("5"),
            settled_result=settled,
        )
    assert pending_path.read_bytes() == before


def test_pending_parent_commit_guard_rejects_an_extra_ambiguous_pending_row(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.jsonl"
    pending = _advance_to_pending(path, tmp_path)
    settled = settled_result_binding(pending)
    duplicate = json.loads(path.read_bytes().splitlines()[-1])
    duplicate["sequence"] += 1
    duplicate["previous_row_digest"] = pending.row_digest
    duplicate["recorded_at"] = "2026-08-01T12:00:08.000000Z"
    path.write_bytes(path.read_bytes() + _reseal(duplicate))
    before = path.read_bytes()

    with pytest.raises(RunRefLedgerError):
        validate_pending_parent_commit(
            path,
            visit=pending.visit,
            attempt_ordinal=pending.attempt_ordinal,
            current_step_config_digest=_digest("5"),
            settled_result=settled,
        )

    assert path.read_bytes() == before


def test_parent_binding_drift_and_external_authority_failure_never_commit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.jsonl"
    pending = _advance_to_pending(path, tmp_path)
    settled = settled_result_binding(pending)

    with pytest.raises(RunRefLedgerError, match="settled parent"):
        reconcile_pending_parent_commit(
            path,
            settled_result=replace(
                settled,
                evidence_manifest_digest=_digest("1"),
            ),
            current_step_config_digest=_digest("5"),
            validate_bound_authority=lambda _row: None,
        )

    def reject_authority(_row) -> None:
        raise ValueError("evidence changed")

    with pytest.raises(ValueError, match="evidence changed"):
        reconcile_pending_parent_commit(
            path,
            settled_result=settled,
            current_step_config_digest=_digest("5"),
            validate_bound_authority=reject_authority,
        )
    assert load_attempt_ledger(path).rows[-1] == pending


def test_incomplete_attempt_discards_only_after_exact_workspace_deletion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "attempts.jsonl"
    visit = _visit()
    first_bindings = _allocated_bindings(tmp_path)
    first = allocate_attempt(
        path,
        visit=visit,
        bindings=first_bindings,
        recorded_at="2026-08-01T12:00:00.000000Z",
    )
    assert identify_incomplete_attempt(
        path,
        visit=visit,
        current_step_config_digest=_digest("5"),
    ) == first

    first.bindings.workspace_path.mkdir(parents=True)
    with pytest.raises(RunRefLedgerError, match="still exists"):
        record_discarded_attempt(
            path,
            visit=visit,
            attempt_ordinal=1,
            workspace_path=first.bindings.workspace_path,
            disposition_digest=_digest("a"),
        )
    shutil.rmtree(first.bindings.workspace_path)
    discarded = record_discarded_attempt(
        path,
        visit=visit,
        attempt_ordinal=1,
        workspace_path=first.bindings.workspace_path,
        disposition_digest=_digest("a"),
        recorded_at="2026-08-01T12:00:01.000000Z",
    )
    assert discarded.stage == "allocated"
    assert discarded.status == "discarded"
    assert identify_incomplete_attempt(
        path,
        visit=visit,
        current_step_config_digest=_digest("5"),
    ) is None

    second = allocate_attempt(
        path,
        visit=visit,
        bindings=_allocated_bindings(tmp_path, ordinal=2),
        recorded_at="2026-08-01T12:00:02.000000Z",
    )
    assert second.attempt_ordinal == 2


def test_settled_parent_binding_decoder_is_closed(tmp_path: Path) -> None:
    path = tmp_path / "attempts.jsonl"
    settled = settled_result_binding(_advance_to_pending(path, tmp_path))
    extra = {**settled.record, "unexpected": True}

    with pytest.raises(RunRefLedgerError, match="fields"):
        settled_result_binding_from_record(extra)
    assert isinstance(settled, SettledRunRefResultBinding)
