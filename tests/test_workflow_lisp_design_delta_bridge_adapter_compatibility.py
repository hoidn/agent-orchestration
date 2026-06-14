from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
from orchestrator.workflow_lisp.command_boundaries import (
    CertifiedAdapterBinding,
    CertifiedAdapterInputField,
    TransitionBindingMetadata,
)
from tests.test_workflow_lisp_design_delta_drain_migration_feasibility import (
    _design_delta_work_item_command_boundaries,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGN_DELTA_PARENT_DRAIN_COMMANDS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.commands.json"
)
SHARED_BRIDGE_BINDING_NAMES = (
    "materialize_lisp_frontend_work_item_inputs",
    "project_lisp_frontend_selector_action",
)
UPDATE_RUN_STATE_SCRIPT = (
    REPO_ROOT / "workflows" / "library" / "scripts" / "update_lisp_frontend_run_state.py"
)
RECORD_BLOCKED_RECOVERY_OUTCOME_SCRIPT = (
    REPO_ROOT
    / "workflows"
    / "library"
    / "scripts"
    / "record_lisp_frontend_blocked_recovery_outcome.py"
)
# The live run-state bridge still accepts RECOVERED_IN_PROGRESS as temporary
# slack, but the narrowed certified-adapter surface intentionally stays on the
# promoted WorkItemSource members only.
WORK_ITEM_SOURCE_MEMBERS = ("BACKLOG_ITEM", "DESIGN_GAP")
BLOCKED_RECOVERY_ROUTE_MEMBERS = (
    "GAP_DESIGN_REVISION_REQUIRED",
    "TARGET_DESIGN_REVISION_REQUIRED",
    "PREREQUISITE_GAP_REQUIRED",
    "TERMINAL_BLOCKED",
)


def _load_design_delta_manifest_bindings() -> dict[str, CertifiedAdapterBinding]:
    payload = json.loads(DESIGN_DELTA_PARENT_DRAIN_COMMANDS.read_text(encoding="utf-8"))
    bindings = _parse_command_boundaries_manifest(
        payload,
        manifest_path=DESIGN_DELTA_PARENT_DRAIN_COMMANDS,
    )
    return {
        name: binding
        for name, binding in bindings.items()
        if isinstance(binding, CertifiedAdapterBinding)
    }


def _binding_contract_snapshot(binding: CertifiedAdapterBinding) -> dict[str, object]:
    return {
        "input_signature": tuple(
            (
                field.name,
                field.type_name,
                field.required,
                field.transport_key,
            )
            for field in binding.input_signature
        ),
        "output_type_name": binding.output_type_name,
        "behavior_class": binding.behavior_class,
        "invocation_protocol": binding.invocation_protocol,
        "transition_binding": _transition_binding_snapshot(binding.transition_binding),
    }


def _transition_binding_snapshot(
    binding: TransitionBindingMetadata | None,
) -> tuple[str, str, str, str] | None:
    if binding is None:
        return None
    return (
        binding.transition_name,
        binding.resource_kind,
        binding.contract_role,
        binding.backend_selector,
    )


def _assert_binding_contracts_match(
    *,
    binding_name: str,
    expected: CertifiedAdapterBinding,
    actual: CertifiedAdapterBinding,
) -> None:
    expected_snapshot = _binding_contract_snapshot(expected)
    actual_snapshot = _binding_contract_snapshot(actual)
    assert actual_snapshot == expected_snapshot, (
        f"{binding_name} manifest/test contract mismatch:\n"
        f"expected={expected_snapshot}\n"
        f"actual={actual_snapshot}"
    )


def _run_adapter_script(
    *,
    script_path: Path,
    payload: dict[str, object],
    bundle_path: Path,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = str(bundle_path)
    return subprocess.run(
        [sys.executable, str(script_path), json.dumps(payload)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _update_run_state_payload(tmp_path: Path, *, work_item_source: str) -> tuple[dict[str, object], Path, Path]:
    state_path = tmp_path / "state" / "run_state.json"
    summary_path = tmp_path / "artifacts" / "work" / "summary.json"
    payload = {
        "run_state_path": str(state_path),
        "work_item_id": "item-1",
        "work_item_source": work_item_source,
        "reason": "complete",
        "item_summary_target_path": str(summary_path),
        "item_summary_pointer_path": str(tmp_path / "artifacts" / "work" / "summary.pointer"),
        "drain_status_path": str(tmp_path / "state" / "drain_status.txt"),
    }
    return payload, state_path, summary_path


def _blocked_recovery_payload(
    tmp_path: Path,
    *,
    work_item_source: str,
    recovery_route: str,
) -> tuple[dict[str, object], Path, Path]:
    state_path = tmp_path / "state" / "run_state.json"
    summary_path = tmp_path / "artifacts" / "work" / "blocked_summary.json"
    payload = {
        "run_state_path": str(state_path),
        "work_item_id": "item-1",
        "work_item_source": work_item_source,
        "recovery_route": recovery_route,
        "reason": "missing_resource",
        "target_design_review_decision": "APPROVE",
        "terminal_action": "block" if recovery_route == "TERMINAL_BLOCKED" else "continue",
        "summary_path": str(summary_path),
        "summary_pointer_path": str(tmp_path / "artifacts" / "work" / "blocked_summary.pointer"),
        "drain_status_path": str(tmp_path / "state" / "drain_status.txt"),
        "progress_report_path": str(tmp_path / "artifacts" / "work" / "progress.md"),
        "implementation_state_path": str(tmp_path / "artifacts" / "work" / "implementation_state.json"),
        "architecture_bundle_path": str(tmp_path / "artifacts" / "work" / "architecture_bundle.json"),
        "plan_path": str(tmp_path / "docs" / "plan.md"),
    }
    return payload, state_path, summary_path


def test_design_delta_shared_work_item_bridge_contracts_match_checked_in_manifest() -> None:
    manifest_bindings = _load_design_delta_manifest_bindings()
    feasibility_bindings = _design_delta_work_item_command_boundaries()

    for binding_name in SHARED_BRIDGE_BINDING_NAMES:
        _assert_binding_contracts_match(
            binding_name=binding_name,
            expected=feasibility_bindings[binding_name],
            actual=manifest_bindings[binding_name],
        )


def test_design_delta_shared_work_item_recorder_coherence_guard_detects_seeded_divergence() -> None:
    manifest_bindings = _load_design_delta_manifest_bindings()
    binding_name = "materialize_lisp_frontend_work_item_inputs"
    manifest_binding = manifest_bindings[binding_name]
    divergent_binding = replace(
        manifest_binding,
        input_signature=tuple(
            replace(field, type_name="DefinitelyNotTheManifestType")
            if field.name == "selection_bundle_path"
            else field
            for field in manifest_binding.input_signature
        ),
    )

    with pytest.raises(AssertionError, match=f"{binding_name} manifest/test contract mismatch"):
        _assert_binding_contracts_match(
            binding_name=binding_name,
            expected=divergent_binding,
            actual=manifest_binding,
        )


@pytest.mark.parametrize(
    ("work_item_source", "completed_key"),
    (
        ("BACKLOG_ITEM", "completed_items"),
        ("DESIGN_GAP", "completed_design_gaps"),
    ),
)
def test_update_lisp_frontend_run_state_adapter_accepts_work_item_source_members(
    tmp_path: Path,
    work_item_source: str,
    completed_key: str,
) -> None:
    payload, state_path, summary_path = _update_run_state_payload(
        tmp_path,
        work_item_source=work_item_source,
    )
    bundle_path = tmp_path / "artifacts" / "work" / "update_bundle.json"

    result = _run_adapter_script(
        script_path=UPDATE_RUN_STATE_SCRIPT,
        payload=payload,
        bundle_path=bundle_path,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(bundle_path.read_text(encoding="utf-8")) == {"summary": str(summary_path)}
    assert json.loads(summary_path.read_text(encoding="utf-8"))["work_item_source"] == work_item_source
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload[completed_key] == ["item-1"]


def test_update_lisp_frontend_run_state_adapter_rejects_out_of_domain_work_item_source(
    tmp_path: Path,
) -> None:
    payload, _, _ = _update_run_state_payload(tmp_path, work_item_source="NOT_A_SOURCE")
    bundle_path = tmp_path / "artifacts" / "work" / "update_bundle.json"

    result = _run_adapter_script(
        script_path=UPDATE_RUN_STATE_SCRIPT,
        payload=payload,
        bundle_path=bundle_path,
    )

    assert result.returncode != 0
    assert "Unexpected work_item_source: NOT_A_SOURCE" in result.stderr


@pytest.mark.parametrize("work_item_source", WORK_ITEM_SOURCE_MEMBERS)
def test_record_blocked_recovery_outcome_adapter_accepts_work_item_source_members(
    tmp_path: Path,
    work_item_source: str,
) -> None:
    payload, state_path, summary_path = _blocked_recovery_payload(
        tmp_path,
        work_item_source=work_item_source,
        recovery_route="TERMINAL_BLOCKED",
    )
    bundle_path = tmp_path / "artifacts" / "work" / "blocked_recovery_bundle.json"

    result = _run_adapter_script(
        script_path=RECORD_BLOCKED_RECOVERY_OUTCOME_SCRIPT,
        payload=payload,
        bundle_path=bundle_path,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(bundle_path.read_text(encoding="utf-8")) == {"summary": str(summary_path)}
    assert json.loads(summary_path.read_text(encoding="utf-8"))["work_item_source"] == work_item_source
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    blocked_key = "blocked_design_gaps" if work_item_source == "DESIGN_GAP" else "blocked_items"
    assert state_payload[blocked_key]["item-1"]["recovery_route"] == "TERMINAL_BLOCKED"


@pytest.mark.parametrize("recovery_route", BLOCKED_RECOVERY_ROUTE_MEMBERS)
def test_record_blocked_recovery_outcome_adapter_accepts_blocked_recovery_route_members(
    tmp_path: Path,
    recovery_route: str,
) -> None:
    payload, state_path, summary_path = _blocked_recovery_payload(
        tmp_path,
        work_item_source="BACKLOG_ITEM",
        recovery_route=recovery_route,
    )
    bundle_path = tmp_path / "artifacts" / "work" / "blocked_recovery_bundle.json"

    result = _run_adapter_script(
        script_path=RECORD_BLOCKED_RECOVERY_OUTCOME_SCRIPT,
        payload=payload,
        bundle_path=bundle_path,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(bundle_path.read_text(encoding="utf-8")) == {"summary": str(summary_path)}
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["blocked_items"]["item-1"]["recovery_route"] == recovery_route


def test_record_blocked_recovery_outcome_adapter_rejects_out_of_domain_work_item_source(
    tmp_path: Path,
) -> None:
    payload, _, _ = _blocked_recovery_payload(
        tmp_path,
        work_item_source="NOT_A_SOURCE",
        recovery_route="TERMINAL_BLOCKED",
    )
    bundle_path = tmp_path / "artifacts" / "work" / "blocked_recovery_bundle.json"

    result = _run_adapter_script(
        script_path=RECORD_BLOCKED_RECOVERY_OUTCOME_SCRIPT,
        payload=payload,
        bundle_path=bundle_path,
    )

    assert result.returncode != 0
    assert "invalid choice: 'NOT_A_SOURCE'" in result.stderr


def test_record_blocked_recovery_outcome_adapter_rejects_out_of_domain_recovery_route(
    tmp_path: Path,
) -> None:
    payload, _, _ = _blocked_recovery_payload(
        tmp_path,
        work_item_source="BACKLOG_ITEM",
        recovery_route="NOT_A_ROUTE",
    )
    bundle_path = tmp_path / "artifacts" / "work" / "blocked_recovery_bundle.json"

    result = _run_adapter_script(
        script_path=RECORD_BLOCKED_RECOVERY_OUTCOME_SCRIPT,
        payload=payload,
        bundle_path=bundle_path,
    )

    assert result.returncode != 0
    assert "Unexpected recovery route: NOT_A_ROUTE" in result.stderr
