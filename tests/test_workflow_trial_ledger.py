from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

import orchestrator.workflow.trial.ledger as trial_ledger_module
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.ledger import (
    RunRefAttemptBindings,
    RunRefVisitKey,
    advance_attempt,
    allocate_attempt,
    load_attempt_ledger,
    reconcile_pending_parent_commit,
    settled_result_binding,
)
from orchestrator.workflow.run_ref.runtime import (
    RunRefLifecycleAcknowledgement,
    RunRefLifecycleEvent,
    acknowledge_persisted_run_ref_lifecycle_event,
)
from orchestrator.workflow.executable_ir import derive_unbound_trial_step_config
from orchestrator.workflow.trial.config import build_trial_runtime_request
from orchestrator.workflow.trial.contracts import (
    TrialCellKey,
    build_sealed_opaque_label_map,
    derive_trial_cell_effect_scopes,
)
from orchestrator.workflow.trial.ledger import (
    TRIAL_EVENT_LEDGER_SCHEMA,
    TrialLedgerError,
    append_trial_cell_settlement,
    append_trial_e1_committed,
    append_trial_e1_boundary,
    classify_trial_cell_resume,
    discard_incomplete_trial_cell,
    initialize_trial_event_ledger,
    load_trial_event_ledger,
)
from tests.test_workflow_lisp_trial_lowering import (
    _build_transportable_trial,
    _trial_node,
)


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _write_rechained_trial_ledger(path: Path, original: bytes, mutate) -> None:
    rows = [json.loads(line) for line in original.splitlines()]
    mutate(rows)
    previous = None
    encoded: list[bytes] = []
    for row in rows:
        row["previous_row_digest"] = previous
        preimage = dict(row)
        preimage.pop("row_digest")
        row["row_digest"] = canonical_sha256(preimage)
        previous = row["row_digest"]
        encoded.append(canonical_json_bytes(row) + b"\n")
    path.write_bytes(b"".join(encoded))


def _trial_authority(tmp_path: Path):
    compile_root = tmp_path / "compile"
    compile_root.mkdir()
    result = _build_transportable_trial(
        compile_root,
        declarations="",
        type_name="String",
    )
    node = _trial_node(result)
    step_config = node.execution_config
    static = step_config.trial
    visit = RunRefVisitKey(
        parent_run_id="parent-run",
        execution_frame_id="root",
        call_frame_id=None,
        step_id="root.compare",
        visit_count=2,
    )
    request = build_trial_runtime_request(
        step_config=step_config,
        visit=visit,
        resolved_inputs_by_arm={
            "direct": {"payload": "fixed"},
            "orc": {"payload": "fixed"},
        },
    )
    return result, node, step_config, visit, request


def _initialized(tmp_path: Path):
    result, node, static, visit, request = _trial_authority(tmp_path)
    parent_run_root = (tmp_path / "parent-run-root").resolve()
    parent_run_root.mkdir()
    run_ref_root = (tmp_path / "run-ref-root").resolve()
    scopes = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
    )
    sealed = build_sealed_opaque_label_map(
        request.cell_domain,
        salt=b"fixed-test-salt" * 4,
    )
    header = initialize_trial_event_ledger(
        request=request,
        sealed_opaque_labels=sealed,
        cell_scopes=scopes,
        recorded_at="2026-08-02T12:00:00.000000Z",
    )
    return result, node, request, scopes, sealed, header


def test_trial_runtime_identity_reuses_static_components_and_adds_only_request_facts(
    tmp_path: Path,
) -> None:
    _result, _node, step_config, visit, request = _trial_authority(tmp_path)
    static = step_config.trial
    changed_input = build_trial_runtime_request(
        step_config=step_config,
        visit=visit,
        resolved_inputs_by_arm={
            "direct": {"payload": "changed"},
            "orc": {"payload": "fixed"},
        },
    )
    changed_visit = build_trial_runtime_request(
        step_config=step_config,
        visit=replace(visit, visit_count=3),
        resolved_inputs_by_arm={
            "direct": {"payload": "fixed"},
            "orc": {"payload": "fixed"},
        },
    )
    unbound_step_config = derive_unbound_trial_step_config(static)
    unbound_request = build_trial_runtime_request(
        step_config=unbound_step_config,
        visit=visit,
        resolved_inputs_by_arm={
            "direct": {"payload": "fixed"},
            "orc": {"payload": "fixed"},
        },
    )

    assert request.static_config_digest == static.digest
    assert request.trial_step_config_digest == step_config.step_config_digest
    assert request.evaluation_digest == static.evaluation_digest
    assert request.budget_digest == static.budget_digest
    assert request.result_contract_digest == static.result_digest
    assert request.compiler_runtime_identity_digest == (
        static.compiler_runtime_identity_digest
    )
    assert request.digest != changed_input.digest != changed_visit.digest
    assert changed_input.static_config_digest == request.static_config_digest
    assert changed_input.evaluation_digest == request.evaluation_digest
    assert changed_input.budget_digest == request.budget_digest
    assert unbound_request.static_config_digest == request.static_config_digest
    assert unbound_request.evaluation_digest == request.evaluation_digest
    assert unbound_request.budget_digest == request.budget_digest
    assert unbound_request.result_contract_digest == request.result_contract_digest
    assert unbound_request.trial_step_config_digest != request.trial_step_config_digest
    assert (
        unbound_request.arm_run_ref_authorities
        != request.arm_run_ref_authorities
    )
    assert unbound_request.digest != request.digest
    parent_root = (tmp_path / "identity-parent").resolve()
    run_ref_root = (tmp_path / "identity-run-ref").resolve()
    bound_scopes = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=parent_root,
        run_ref_root=run_ref_root,
    )
    unbound_scopes = derive_trial_cell_effect_scopes(
        request=unbound_request,
        parent_run_root=parent_root,
        run_ref_root=run_ref_root,
    )
    assert [scope.effect_instance_digest for scope in bound_scopes] != [
        scope.effect_instance_digest for scope in unbound_scopes
    ]
    assert [scope.run_ref_step_config_digest for scope in bound_scopes] != [
        scope.run_ref_step_config_digest for scope in unbound_scopes
    ]
    assert [cell.record for cell in request.cell_domain] == [
        {"arm_id": "direct", "rep": 1},
        {"arm_id": "direct", "rep": 2},
        {"arm_id": "orc", "rep": 1},
        {"arm_id": "orc", "rep": 2},
    ]
    encoded = canonical_json_bytes(request.record)
    for forbidden in (
        b"workspace_path",
        b"run_ref_root",
        b"recorded_at",
        b"opaque",
        b"provider_output",
        b"completion_order",
    ):
        assert forbidden not in encoded


def test_sealed_labels_are_an_exact_opaque_bijection(tmp_path: Path) -> None:
    _result, _node, _static, _visit, request = _trial_authority(tmp_path)
    sealed = build_sealed_opaque_label_map(
        request.cell_domain,
        salt=b"fixed-test-salt" * 4,
    )

    assert tuple(binding.cell for binding in sealed.bindings) == request.cell_domain
    assert len({binding.opaque_label for binding in sealed.bindings}) == 4
    assert all(binding.opaque_label.startswith("opaque-") for binding in sealed.bindings)
    assert all(
        binding.cell.arm_id not in binding.opaque_label
        for binding in sealed.bindings
    )
    assert sealed.digest == canonical_sha256(sealed.record)

    with pytest.raises(ValueError, match="bijection"):
        build_sealed_opaque_label_map(
            request.cell_domain,
            labels=("opaque-" + "0" * 64,) * 4,
        )


def test_cell_scopes_are_strict_disjoint_children_and_reject_aliases(
    tmp_path: Path,
) -> None:
    _result, _node, _static, _visit, request = _trial_authority(tmp_path)
    parent = (tmp_path / "parent").resolve()
    parent.mkdir()
    external = (tmp_path / "external").resolve()
    scopes = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=parent,
        run_ref_root=external,
    )

    assert len(scopes) == 4
    assert len({scope.effect_instance_root for scope in scopes}) == 4
    assert len({scope.run_ref_root for scope in scopes}) == 1
    assert len({scope.workspace_namespace for scope in scopes}) == 4
    assert all(scope.effect_instance_root.is_relative_to(parent / "trials") for scope in scopes)
    assert all(scope.run_ref_root.is_relative_to(external) for scope in scopes)
    assert all(scope.ledger_path == scope.effect_instance_root / "run-ref-attempts.jsonl" for scope in scopes)

    alias = tmp_path / "parent-alias"
    alias.symlink_to(parent, target_is_directory=True)
    with pytest.raises(ValueError, match="canonical|alias"):
        derive_trial_cell_effect_scopes(
            request=request,
            parent_run_root=alias,
            run_ref_root=external,
        )
    with pytest.raises(ValueError, match="canonical"):
        derive_trial_cell_effect_scopes(
            request=request,
            parent_run_root=parent / ".." / "parent",
            run_ref_root=external,
        )
    for overlapping_root in (
        parent,
        scopes[0].trial_root,
        scopes[0].trial_root / "external-workspaces",
    ):
        with pytest.raises(ValueError, match="overlap"):
            derive_trial_cell_effect_scopes(
                request=request,
                parent_run_root=parent,
                run_ref_root=overlapping_root,
            )


def test_trial_header_is_canonical_closed_and_hash_chained(tmp_path: Path) -> None:
    _result, _node, request, scopes, sealed, header = _initialized(tmp_path)
    ledger = load_trial_event_ledger(header.path)

    assert header.path == scopes[0].trial_root / "trial-events.jsonl"
    assert len(ledger.rows) == 1
    row = ledger.rows[0]
    assert row.kind == "header"
    assert row.record["schema_version"] == TRIAL_EVENT_LEDGER_SCHEMA
    assert row.record["previous_row_digest"] is None
    assert row.payload["trial_static_config_digest"] == request.static_config_digest
    assert row.payload["trial_step_config_digest"] == request.trial_step_config_digest
    assert row.payload["arm_run_ref_authorities"] == [
        dict(binding)
        for binding in request.arm_run_ref_authorities
    ]
    assert row.payload["trial_request_digest"] == request.digest
    assert row.payload["evaluation_digest"] == request.evaluation_digest
    assert row.payload["budget_digest"] == request.budget_digest
    assert row.payload["sealed_opaque_label_map_digest"] == sealed.digest
    assert row.payload["sealed_opaque_label_map"] == sealed.record
    assert header.path.read_bytes() == canonical_json_bytes(row.record) + b"\n"

    original = json.loads(header.path.read_bytes())
    variants = []
    missing = dict(original)
    missing["payload"] = dict(missing["payload"])
    missing["payload"].pop("budget_digest")
    variants.append(missing)
    extra = dict(original)
    extra["payload"] = {**extra["payload"], "memo_key": _digest("1")}
    variants.append(extra)
    tampered_map = dict(original)
    tampered_map["payload"] = dict(tampered_map["payload"])
    tampered_map["payload"]["sealed_opaque_label_map"] = json.loads(
        canonical_json_bytes(
            tampered_map["payload"]["sealed_opaque_label_map"]
        )
    )
    tampered_map["payload"]["sealed_opaque_label_map"]["bindings"][0][
        "opaque_label"
    ] = "opaque-" + "0" * 64
    variants.append(tampered_map)
    for candidate in variants:
        header.path.write_bytes(canonical_json_bytes(candidate) + b"\n")
        with pytest.raises(TrialLedgerError):
            load_trial_event_ledger(header.path)


def _attempt_bindings(scope, *, ordinal: int = 1) -> RunRefAttemptBindings:
    workspace = (
        scope.run_ref_root
        / "effect-instances"
        / scope.effect_instance_digest.removeprefix("sha256:")
        / "runs"
        / str(ordinal)
        / "workspace"
    )
    return RunRefAttemptBindings(
        run_ref_root=scope.run_ref_root,
        workspace_path=workspace,
        source_digest=_digest("1"),
        program_digest=_digest("2"),
        input_digest=_digest("3"),
        policy_digest=_digest("4"),
        step_config_digest=scope.run_ref_step_config_digest,
        capsule_or_compiler_digest=_digest("6"),
        child_run_id=f"trial-cell-{scope.cell_index}-{ordinal}",
        result_contract_digest=scope.result_contract_digest,
    )


def _append_event(header, scope, event, acknowledgement):
    return append_trial_e1_boundary(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        cell=scope.cell,
        event=event,
        acknowledgement=acknowledgement,
        recorded_at="2026-08-02T12:00:01.000000Z",
    )


def _append_allocation(header, scope):
    bindings = _attempt_bindings(scope)
    applied = allocate_attempt(
        scope.ledger_path,
        visit=header.request.visit,
        bindings=bindings,
        recorded_at="2026-08-02T12:00:00.000000Z",
    )
    event = RunRefLifecycleEvent.build(
        sequence=1,
        event_kind="allocation",
        stage="allocated",
        visit=header.request.visit,
        attempt_ordinal=1,
        effect_instance_root=scope.effect_instance_root,
        payload={"bindings": bindings.record},
    )
    acknowledgement = acknowledge_persisted_run_ref_lifecycle_event(
        event,
        expected_row_digest=applied.row_digest,
    )
    row = _append_event(header, scope, event, acknowledgement)
    return row, bindings, event, acknowledgement


_TRANSITIONS = (
    ("materialized", {"verified_git_tree_id": "git-tree:" + "a" * 40}),
    (
        "setup_completed",
        {
            "setup_evidence_digest": _digest("7"),
            "post_setup_baseline_digest": _digest("8"),
        },
    ),
    ("program_prepared", {"program_preparation_digest": _digest("9")}),
    ("launched", {"child_launch_digest": _digest("a")}),
    (
        "child_completed",
        {
            "child_terminal_state_digest": _digest("b"),
            "result_payload_digest": _digest("c"),
        },
    ),
    (
        "delta_captured",
        {
            "workspace_delta_digest": _digest("d"),
            "accounting_digest": _digest("e"),
            "evidence_manifest_digest": _digest("f"),
        },
    ),
    ("completed_pending_parent_commit", {}),
)


def _append_to_pending(header, scope):
    _append_allocation(header, scope)
    pending = None
    for sequence, (stage, updates) in enumerate(_TRANSITIONS, start=2):
        pending = advance_attempt(
            scope.ledger_path,
            visit=header.request.visit,
            attempt_ordinal=1,
            stage=stage,
            binding_updates=updates,
            recorded_at=f"2026-08-02T12:00:{sequence:02d}.000000Z",
        )
        event = RunRefLifecycleEvent.build(
            sequence=sequence,
            event_kind=(
                "prepared"
                if stage == "completed_pending_parent_commit"
                else "progress"
            ),
            stage=stage,
            visit=header.request.visit,
            attempt_ordinal=1,
            effect_instance_root=scope.effect_instance_root,
            payload=(
                {
                    "binding_updates": {},
                    "result_envelope_digest": _digest("1"),
                    "artifact_projection_digest": _digest("2"),
                    "evidence_manifest_digest": _digest("f"),
                }
                if stage == "completed_pending_parent_commit"
                else {"binding_updates": updates}
            ),
        )
        acknowledgement = acknowledge_persisted_run_ref_lifecycle_event(
            event,
            expected_row_digest=pending.row_digest,
        )
        if stage == "completed_pending_parent_commit":
            _append_event(header, scope, event, acknowledgement)
    assert pending is not None
    return pending


def test_cross_cell_lifecycle_authority_rejects_without_mutation(
    tmp_path: Path,
) -> None:
    _result, _node, _request, scopes, _sealed, header = _initialized(tmp_path)
    first, second = scopes[:2]
    _row, _bindings, event, acknowledgement = _append_allocation(header, first)
    before = header.path.read_bytes()

    with pytest.raises(TrialLedgerError, match="cross-cell|scope"):
        append_trial_e1_boundary(
            header.path,
            expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
            cell=second.cell,
            event=event,
            acknowledgement=acknowledgement,
        )

    assert header.path.read_bytes() == before

    changed_request = build_trial_runtime_request(
        step_config=header.request.step_config,
        visit=header.request.visit,
        resolved_inputs_by_arm={
            "direct": {"payload": "changed"},
            "orc": {"payload": "fixed"},
        },
    )
    with pytest.raises(TrialLedgerError, match="current runtime request"):
        classify_trial_cell_resume(
            header.path,
            request=changed_request,
            cell=first.cell,
        )
    assert header.path.read_bytes() == before

    first.ledger_path.unlink()
    with pytest.raises(TrialLedgerError, match="missing|unreadable"):
        classify_trial_cell_resume(
            header.path,
            request=header.request,
            cell=first.cell,
        )
    assert header.path.read_bytes() == before


def test_resume_matrix_incomplete_pending_commit_and_exact_reuse(
    tmp_path: Path,
) -> None:
    _result, _node, _request, scopes, _sealed, header = _initialized(tmp_path)
    scope = scopes[0]
    unseen = classify_trial_cell_resume(
        header.path,
        request=header.request,
        cell=scopes[1].cell,
    )
    assert unseen.action == "allocate_fresh"
    assert unseen.attempt_ordinal == 0
    assert unseen.next_attempt_ordinal == 1
    pending = _append_to_pending(header, scope)

    incomplete = classify_trial_cell_resume(
        header.path,
        request=header.request,
        cell=scope.cell,
    )
    assert incomplete.action == "discard_incomplete"
    assert incomplete.attempt_ordinal == 1
    assert incomplete.next_attempt_ordinal == 2

    settlement = append_trial_cell_settlement(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        cell=scope.cell,
        settled_result=settled_result_binding(pending),
        outcome_digest=_digest("3"),
        evidence_digest=_digest("f"),
        recorded_at="2026-08-02T12:00:10.000000Z",
    )
    reconcile = classify_trial_cell_resume(
        header.path,
        request=header.request,
        cell=scope.cell,
    )
    assert reconcile.action == "reconcile_pending_e1_commit"
    assert reconcile.trial_settlement_row_digest == settlement.row_digest

    committed = reconcile_pending_parent_commit(
        scope.ledger_path,
        settled_result=settled_result_binding(pending),
        current_step_config_digest=scope.run_ref_step_config_digest,
        validate_bound_authority=lambda _row: None,
        recorded_at="2026-08-02T12:00:20.000000Z",
    )
    append_trial_e1_committed(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        cell=scope.cell,
        committed_authority=committed,
        recorded_at="2026-08-02T12:00:21.000000Z",
    )
    reusable = classify_trial_cell_resume(
        header.path,
        request=header.request,
        cell=scope.cell,
    )
    assert reusable.action == "reuse"
    assert reusable.attempt_ordinal == 1
    assert reusable.next_attempt_ordinal is None


def test_recanonicalized_cross_row_reference_tampering_fails_closed(
    tmp_path: Path,
) -> None:
    _result, _node, _request, scopes, _sealed, header = _initialized(tmp_path)
    scope = scopes[0]
    pending = _append_to_pending(header, scope)
    settlement = append_trial_cell_settlement(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        cell=scope.cell,
        settled_result=settled_result_binding(pending),
        outcome_digest=_digest("3"),
        evidence_digest=_digest("f"),
        recorded_at="2026-08-02T12:00:10.000000Z",
    )
    committed = reconcile_pending_parent_commit(
        scope.ledger_path,
        settled_result=settled_result_binding(pending),
        current_step_config_digest=scope.run_ref_step_config_digest,
        validate_bound_authority=lambda _row: None,
        recorded_at="2026-08-02T12:00:20.000000Z",
    )
    append_trial_e1_committed(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        cell=scope.cell,
        committed_authority=committed,
        recorded_at="2026-08-02T12:00:21.000000Z",
    )
    original = header.path.read_bytes()

    mutations = (
        lambda rows: rows[0]["payload"]["arm_run_ref_authorities"].reverse(),
        lambda rows: rows[1]["payload"].__setitem__(
            "run_ref_step_config_digest", _digest("0")
        ),
        lambda rows: rows[1]["payload"].__setitem__(
            "result_contract_digest", _digest("0")
        ),
        lambda rows: rows[2]["payload"].__setitem__("attempt_ordinal", 2),
        lambda rows: rows[3]["payload"].__setitem__(
            "prepared_trial_row_digest", _digest("0")
        ),
        lambda rows: rows[4]["payload"].__setitem__(
            "trial_settlement_row_digest", _digest("0")
        ),
    )
    for mutate in mutations:
        _write_rechained_trial_ledger(header.path, original, mutate)
        with pytest.raises(TrialLedgerError):
            load_trial_event_ledger(header.path)
    header.path.write_bytes(original)
    assert load_trial_event_ledger(header.path).rows[-1].payload[
        "trial_settlement_row_digest"
    ] == settlement.row_digest


def test_incomplete_discard_removes_exact_workspace_and_allocates_fresh_ordinal(
    tmp_path: Path,
) -> None:
    _result, _node, _request, scopes, _sealed, header = _initialized(tmp_path)
    scope = scopes[0]
    pending = _append_to_pending(header, scope)
    workspace = pending.bindings.workspace_path
    workspace.mkdir(parents=True)
    (workspace / "incident.txt").write_text("incomplete\n", encoding="utf-8")

    disposition = discard_incomplete_trial_cell(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        request=header.request,
        cell=scope.cell,
        current_step_config_digest=scope.run_ref_step_config_digest,
        recorded_at="2026-08-02T12:00:10.000000Z",
    )

    assert disposition.next_attempt_ordinal == 2
    assert not workspace.exists()
    e1 = load_attempt_ledger(scope.ledger_path)
    assert e1.rows[-1].status == "discarded"
    original = header.path.read_bytes()
    for field, value in (
        ("attempt_ordinal", 2),
        ("e1_incomplete_row_digest", _digest("0")),
    ):
        _write_rechained_trial_ledger(
            header.path,
            original,
            lambda rows, field=field, value=value: rows[-1]["payload"].__setitem__(
                field,
                value,
            ),
        )
        with pytest.raises(TrialLedgerError):
            load_trial_event_ledger(header.path)
    header.path.write_bytes(original)
    _write_rechained_trial_ledger(
        header.path,
        original,
        lambda rows: rows[-1]["payload"].__setitem__(
            "e1_discarded_row_digest",
            _digest("0"),
        ),
    )
    assert load_trial_event_ledger(header.path).rows[-1].kind == "cell_discarded"
    with pytest.raises(TrialLedgerError, match="discarded cell authority"):
        classify_trial_cell_resume(
            header.path,
            request=header.request,
            cell=scope.cell,
        )
    header.path.write_bytes(original)
    e1_bytes = scope.ledger_path.read_bytes()
    scope.ledger_path.unlink()
    with pytest.raises(TrialLedgerError, match="missing|unreadable"):
        classify_trial_cell_resume(
            header.path,
            request=header.request,
            cell=scope.cell,
        )
    scope.ledger_path.write_bytes(e1_bytes)
    awaiting_fresh = classify_trial_cell_resume(
        header.path,
        request=header.request,
        cell=scope.cell,
    )
    assert awaiting_fresh.action == "allocate_fresh"
    assert awaiting_fresh.attempt_ordinal == 1
    assert awaiting_fresh.next_attempt_ordinal == 2
    fresh = allocate_attempt(
        scope.ledger_path,
        visit=header.request.visit,
        bindings=_attempt_bindings(scope, ordinal=2),
        recorded_at="2026-08-02T12:00:11.000000Z",
    )
    assert fresh.attempt_ordinal == 2
    fresh_event = RunRefLifecycleEvent.build(
        sequence=1,
        event_kind="allocation",
        stage="allocated",
        visit=header.request.visit,
        attempt_ordinal=2,
        effect_instance_root=scope.effect_instance_root,
        payload={"bindings": fresh.bindings.record},
    )
    fresh_ack = acknowledge_persisted_run_ref_lifecycle_event(
        fresh_event,
        expected_row_digest=fresh.row_digest,
    )
    append_trial_e1_boundary(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        cell=scope.cell,
        event=fresh_event,
        acknowledgement=fresh_ack,
        recorded_at="2026-08-02T12:00:12.000000Z",
    )
    retry = classify_trial_cell_resume(
        header.path,
        request=header.request,
        cell=scope.cell,
    )
    assert retry.action == "discard_incomplete"
    assert retry.attempt_ordinal == 2
    assert retry.next_attempt_ordinal == 3


def test_discarded_e1_without_trial_disposition_reconciles_without_rerun(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _result, _node, _request, scopes, _sealed, header = _initialized(tmp_path)
    scope = scopes[0]
    pending = _append_to_pending(header, scope)
    workspace = pending.bindings.workspace_path
    workspace.mkdir(parents=True)
    (workspace / "incident.txt").write_text("incomplete\n", encoding="utf-8")
    original_append = trial_ledger_module._append

    def crash_before_trial_disposition(*_args, **_kwargs):
        raise RuntimeError("crash_before_trial_disposition")

    monkeypatch.setattr(
        trial_ledger_module,
        "_append",
        crash_before_trial_disposition,
    )
    with pytest.raises(RuntimeError, match="crash_before_trial_disposition"):
        discard_incomplete_trial_cell(
            header.path,
            expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
            request=header.request,
            cell=scope.cell,
            current_step_config_digest=scope.run_ref_step_config_digest,
            recorded_at="2026-08-02T12:00:10.000000Z",
        )
    monkeypatch.setattr(trial_ledger_module, "_append", original_append)

    assert not workspace.exists()
    assert load_attempt_ledger(scope.ledger_path).rows[-1].status == "discarded"
    decision = classify_trial_cell_resume(
        header.path,
        request=header.request,
        cell=scope.cell,
    )
    assert decision.action == "reconcile_discarded_e1"
    assert decision.attempt_ordinal == 1
    assert decision.next_attempt_ordinal == 2

    recovered = discard_incomplete_trial_cell(
        header.path,
        expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
        request=header.request,
        cell=scope.cell,
        current_step_config_digest=scope.run_ref_step_config_digest,
        recorded_at="2026-08-02T12:00:11.000000Z",
    )
    assert recovered.attempt_ordinal == 1
    assert recovered.next_attempt_ordinal == 2
    assert load_attempt_ledger(scope.ledger_path).rows[-1].status == "discarded"
    assert load_trial_event_ledger(header.path).rows[-1].kind == "cell_discarded"


def test_tamper_missing_ambiguity_and_cross_cell_settlement_fail_closed(
    tmp_path: Path,
) -> None:
    _result, _node, _request, scopes, _sealed, header = _initialized(tmp_path)
    first, second = scopes[:2]
    pending = _append_to_pending(header, first)
    before = header.path.read_bytes()

    with pytest.raises(TrialLedgerError, match="cross-cell"):
        append_trial_cell_settlement(
            header.path,
            expected_head_digest=load_trial_event_ledger(header.path).rows[-1].row_digest,
            cell=second.cell,
            settled_result=settled_result_binding(pending),
            outcome_digest=_digest("3"),
            evidence_digest=_digest("f"),
        )
    assert header.path.read_bytes() == before


def test_latest_e1_state_is_never_inferred_from_a_foreign_visit(
    tmp_path: Path,
) -> None:
    _result, _node, _request, scopes, _sealed, header = _initialized(tmp_path)
    scope = scopes[0]
    _append_to_pending(header, scope)
    before = header.path.read_bytes()
    foreign_visit = replace(header.request.visit, step_id="root.foreign")
    foreign_bindings = replace(
        _attempt_bindings(scope),
        workspace_path=scope.workspace_namespace / "foreign" / "workspace",
        child_run_id="foreign-run-ref-child",
    )
    allocate_attempt(
        scope.ledger_path,
        visit=foreign_visit,
        bindings=foreign_bindings,
        recorded_at="2026-08-02T12:00:10.000000Z",
    )

    with pytest.raises(TrialLedgerError, match="cross-cell visit"):
        classify_trial_cell_resume(
            header.path,
            request=header.request,
            cell=scope.cell,
        )
    assert header.path.read_bytes() == before
