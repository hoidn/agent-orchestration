"""Evidence suite for G6 hook-redundancy and G8 deletion gating."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    CommandBoundaryEnvironment,
    build_command_boundary_environment,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_FIXTURES = FIXTURES / "valid"
PHASE_SCOPE_STDLIB_FIXTURE = VALID_FIXTURES / "phase_scope_stdlib_targets.orc"
RESOURCE_STDLIB_FIXTURE = VALID_FIXTURES / "resource_stdlib_finalize_selected_item_stdlib.orc"
DRAIN_STDLIB_FIXTURE = VALID_FIXTURES / "drain_stdlib_backlog_drain_stdlib.orc"
RESOURCE_INTRINSIC_FIXTURE = VALID_FIXTURES / "resource_stdlib_finalize_selected_item.orc"
DRAIN_INTRINSIC_FIXTURE = VALID_FIXTURES / "drain_stdlib_backlog_drain.orc"


def _form_registry_module():
    return importlib.import_module("orchestrator.workflow_lisp.form_registry")


def _control_dispatch_module():
    return importlib.import_module("orchestrator.workflow_lisp.lowering.control_dispatch")


def _command_boundary_environment(*, gap_output_type_name: str = "GapResult") -> CommandBoundaryEnvironment:
    return build_command_boundary_environment(
        {
            "select_next_item": CertifiedAdapterBinding(
                name="select_next_item",
                stable_command=("python", "scripts/select_next_item.py"),
                input_contract={"type": "object"},
                output_type_name="SelectionResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("select_next_item_ok",),
                negative_fixture_ids=("select_next_item_bad",),
            ),
            "execute_selected_item": CertifiedAdapterBinding(
                name="execute_selected_item",
                stable_command=("python", "scripts/execute_selected_item.py"),
                input_contract={"type": "object"},
                output_type_name="SelectedItemResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("execute_selected_item_ok",),
                negative_fixture_ids=("execute_selected_item_bad",),
            ),
            "draft_gap_item": CertifiedAdapterBinding(
                name="draft_gap_item",
                stable_command=("python", "scripts/draft_gap_item.py"),
                input_contract={"type": "object"},
                output_type_name=gap_output_type_name,
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("draft_gap_item_ok",),
                negative_fixture_ids=("draft_gap_item_bad",),
            ),
            "resolve_plan_gate": CertifiedAdapterBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
                input_contract={"type": "object"},
                output_type_name="PlanGateResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("resolve_plan_gate_ok",),
                negative_fixture_ids=("resolve_plan_gate_bad",),
            ),
            "resolve_roadmap_sync": CertifiedAdapterBinding(
                name="resolve_roadmap_sync",
                stable_command=("python", "scripts/resolve_roadmap_sync.py"),
                input_contract={"type": "object"},
                output_type_name="RoadmapSyncResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("resolve_roadmap_sync_ok",),
                negative_fixture_ids=("resolve_roadmap_sync_bad",),
            ),
            "execute_implementation": CertifiedAdapterBinding(
                name="execute_implementation",
                stable_command=("python", "scripts/execute_implementation.py"),
                input_contract={"type": "object"},
                output_type_name="ImplementationResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("execute_implementation_ok",),
                negative_fixture_ids=("execute_implementation_bad",),
            ),
            "apply_resource_transition": CertifiedAdapterBinding(
                name="apply_resource_transition",
                stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.apply_resource_transition"),
                input_contract={"type": "object"},
                output_type_name="ResourceTransitionResult",
                effects=("resource_transition", "ledger_update"),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("resource_transition_ok",),
                negative_fixture_ids=("resource_transition_bad",),
            ),
        }
    )


def _compile_module_fixture(path: Path, *, tmp_path: Path):
    source = path.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None, f"fixture is missing defmodule: {path}"
    resolved_module_name = module_match.group(1)
    module_path = (tmp_path / Path(*resolved_module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries=_command_boundary_environment().bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
    )


def test_intrinsic_form_route_accounting_api_starts_empty_and_is_deterministic() -> None:
    dispatch = _control_dispatch_module()

    reset_counts = getattr(dispatch, "reset_intrinsic_form_lowering_counts", None)
    read_counts = getattr(dispatch, "intrinsic_form_lowering_counts", None)

    assert callable(reset_counts)
    assert callable(read_counts)

    reset_counts()
    assert read_counts() == {}


def test_bridge_form_registry_metadata_keeps_intrinsics_macro_bindable_for_stdlib_shadowing() -> None:
    registry = _form_registry_module()

    expected = {
        "with-phase": "std/phase",
        "finalize-selected-item": "std/resource",
        "backlog-drain": "std/drain",
    }

    for form_name, owner_module in expected.items():
        spec = registry.get_form_spec(form_name)

        assert spec is not None
        assert spec.kind.value == "temp_compiler_intrinsic"
        assert spec.macro_bindable is True
        assert getattr(spec, "stdlib_owner_module", None) == owner_module
        assert "G8" in (getattr(spec, "compatibility_route", "") or "")


def test_imported_binding_precedence_prefers_stdlib_form_routes_over_intrinsic_heads(tmp_path: Path) -> None:
    dispatch = _control_dispatch_module()
    reset_counts = getattr(dispatch, "reset_intrinsic_form_lowering_counts", None)
    read_counts = getattr(dispatch, "intrinsic_form_lowering_counts", None)

    assert callable(reset_counts)
    assert callable(read_counts)

    reset_counts()
    _compile_module_fixture(PHASE_SCOPE_STDLIB_FIXTURE, tmp_path=tmp_path / "phase")
    _compile_module_fixture(RESOURCE_STDLIB_FIXTURE, tmp_path=tmp_path / "resource")
    _compile_module_fixture(DRAIN_STDLIB_FIXTURE, tmp_path=tmp_path / "drain")

    assert read_counts() == {}


def test_intrinsic_route_accounting_records_legacy_finalize_and_drain_hits(tmp_path: Path) -> None:
    dispatch = _control_dispatch_module()
    reset_counts = getattr(dispatch, "reset_intrinsic_form_lowering_counts", None)
    read_counts = getattr(dispatch, "intrinsic_form_lowering_counts", None)

    assert callable(reset_counts)
    assert callable(read_counts)

    reset_counts()
    compile_stage3_module(
        RESOURCE_INTRINSIC_FIXTURE,
        command_boundaries=_command_boundary_environment().bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path / "intrinsic-resource",
        lowering_route="legacy",
    )
    compile_stage3_module(
        DRAIN_INTRINSIC_FIXTURE,
        command_boundaries=_command_boundary_environment(gap_output_type_name="GapDraftResult").bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path / "intrinsic-drain",
        lowering_route="legacy",
    )

    counts = read_counts()
    assert counts["finalize-selected-item"] > 0
    assert counts["backlog-drain"] > 0


@pytest.mark.parametrize(
    ("intrinsic_fixture", "stdlib_fixture"),
    (
        (RESOURCE_INTRINSIC_FIXTURE, RESOURCE_STDLIB_FIXTURE),
        (DRAIN_INTRINSIC_FIXTURE, DRAIN_STDLIB_FIXTURE),
    ),
)
def test_dual_route_vectors_preserve_typed_return_shapes(
    tmp_path: Path,
    intrinsic_fixture: Path,
    stdlib_fixture: Path,
) -> None:
    intrinsic = compile_stage3_module(
        intrinsic_fixture,
        command_boundaries=_command_boundary_environment(
            gap_output_type_name="GapDraftResult" if intrinsic_fixture == DRAIN_INTRINSIC_FIXTURE else "GapResult"
        ).bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path / "intrinsic",
        lowering_route="legacy",
    )
    stdlib = _compile_module_fixture(stdlib_fixture, tmp_path=tmp_path / "stdlib")

    intrinsic_names = sorted(workflow.definition.return_type.name for workflow in intrinsic.entry_result.typed_workflows)
    stdlib_names = sorted(workflow.definition.return_type.name for workflow in stdlib.entry_result.typed_workflows)

    assert stdlib_names == intrinsic_names
