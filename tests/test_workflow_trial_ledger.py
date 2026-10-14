from __future__ import annotations

from pathlib import Path

from dataclasses import replace
import json
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.executable_ir import (
    StepCommonConfig, TrialStepConfig, TrialArmStepConfig, RunRefStepConfig,
    RunRefBundleCapsuleBinding, derive_unbound_trial_step_config,
)
from orchestrator.workflow.trial.config import build_trial_runtime_request, decode_trial_static_config
from orchestrator.workflow.trial.contracts import derive_trial_cell_effect_scopes
from orchestrator.workflow.trial.ledger import (
    TRIAL_EVENT_LEDGER_SCHEMA, TrialLedgerError, load_trial_event_ledger,
)

import pytest

from orchestrator.workflow.run_ref.contracts import (
    canonical_sha256,
)
from orchestrator.workflow.trial.contracts import (
    TrialCellKey,
    build_sealed_opaque_label_map,
)


def test_sealed_labels_are_an_exact_opaque_bijection(tmp_path: Path) -> None:
    cell_domain = tuple(TrialCellKey(arm_id, rep) for arm_id in ("direct", "revised") for rep in (1, 2))
    sealed = build_sealed_opaque_label_map(
        cell_domain,
        salt=b"fixed-test-salt" * 4,
    )

    assert tuple(binding.cell for binding in sealed.bindings) == cell_domain
    assert len({binding.opaque_label for binding in sealed.bindings}) == 4
    assert all(binding.opaque_label.startswith("opaque-") for binding in sealed.bindings)
    assert all(
        binding.cell.arm_id not in binding.opaque_label
        for binding in sealed.bindings
    )
    assert sealed.digest == canonical_sha256(sealed.record)

    with pytest.raises(ValueError, match="bijection"):
        build_sealed_opaque_label_map(
            cell_domain,
            labels=("opaque-" + "0" * 64,) * 4,
        )

def _captured_trial_config(captured):
    # Exact static config and bound capsule identities captured at 23eb9c97.
    static = decode_trial_static_config(captured["static_config_json"].encode())
    return TrialStepConfig(
        common=StepCommonConfig(), trial=static,
        arms=tuple(TrialArmStepConfig(
            arm_id=arm.arm_id,
            run_ref=RunRefStepConfig(
                common=StepCommonConfig(), run_ref=arm.run_ref,
                capsule_binding=RunRefBundleCapsuleBinding(
                    capsule_digest=captured["capsule_digests"][arm.arm_id]),
            ),
        ) for arm in static.arms),
    )


def _historical_trial_request():
    captured = json.loads((Path(__file__).parent / "fixtures" / "historical_trial_header.json").read_text())
    config = _captured_trial_config(captured)
    visit = RunRefVisitKey("parent-run", "root", None, "root.compare", 2)
    request = build_trial_runtime_request(
        step_config=config, visit=visit,
        resolved_inputs_by_arm={"direct": {"payload": "fixed"}, "orc": {"payload": "fixed"}},
    )
    return config, visit, request


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def test_trial_runtime_identity_reuses_static_components_and_adds_only_request_facts(
    tmp_path: Path,
) -> None:
    step_config, visit, request = _historical_trial_request()
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



def test_cell_scopes_are_strict_disjoint_children_and_reject_aliases(
    tmp_path: Path,
) -> None:
    _config, _visit, request = _historical_trial_request()
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
    captured = json.loads((Path(__file__).parent / "fixtures" / "historical_trial_header.json").read_text().replace("@WORKSPACE@", str(tmp_path)))
    expected = captured["expected"]
    path = Path(expected["trial_root"]) / "trial-events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_bytes(canonical_json_bytes(captured["record"]) + b"\n")
    ledger = load_trial_event_ledger(path)

    assert path == Path(expected["trial_root"]) / "trial-events.jsonl"
    assert len(ledger.rows) == 1
    row = ledger.rows[0]
    assert row.kind == "header"
    assert row.record["schema_version"] == TRIAL_EVENT_LEDGER_SCHEMA
    assert row.record["previous_row_digest"] is None
    assert row.payload["trial_static_config_digest"] == expected["static_config_digest"]
    assert row.payload["trial_step_config_digest"] == expected["trial_step_config_digest"]
    assert row.payload["arm_run_ref_authorities"] == [
        dict(binding)
        for binding in expected["arm_run_ref_authorities"]
    ]
    assert row.payload["trial_request_digest"] == expected["digest"]
    assert row.payload["evaluation_digest"] == expected["evaluation_digest"]
    assert row.payload["budget_digest"] == expected["budget_digest"]
    assert row.payload["sealed_opaque_label_map_digest"] == expected["sealed_digest"]
    assert row.payload["sealed_opaque_label_map"] == expected["sealed_record"]
    assert path.read_bytes() == canonical_json_bytes(row.record) + b"\n"

    original = json.loads(path.read_bytes())
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
        path.write_bytes(canonical_json_bytes(candidate) + b"\n")
        with pytest.raises(TrialLedgerError):
            load_trial_event_ledger(path)
