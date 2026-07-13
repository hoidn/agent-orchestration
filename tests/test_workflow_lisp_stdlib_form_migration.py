"""Evidence suite for G6 hook-redundancy and G8 deletion gating."""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
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


def _retired_backlog_drain_structure_sites(package_root: Path) -> list[str]:
    sanctioned_residue = {
        package_root / "form_registry.py",
        package_root / "stdlib_contracts.py",
    }
    frozen_evidence_and_inventory = {
        package_root / "build_design_delta.py",
        package_root / "migration_parity.py",
        package_root / "post_wcc_inventory.py",
        package_root / "transition_authoring.py",
    }
    forbidden_nodes: list[str] = []

    def retired_key(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        if re.search(r"backlog[-_]drain", value, flags=re.IGNORECASE):
            return value
        return None

    def record_string_key(source_path: Path, node: ast.AST, kind: str, value: object) -> None:
        key = retired_key(value)
        if key is not None:
            forbidden_nodes.append(
                f"{source_path.relative_to(package_root)}:{node.lineno}:{kind}:{key}"
            )

    def comparison_key_values(node: ast.AST):
        if isinstance(node, ast.Constant):
            yield node.value
        elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for element in node.elts:
                yield from comparison_key_values(element)
        elif isinstance(node, ast.Dict):
            for key_node in node.keys:
                if key_node is not None:
                    yield from comparison_key_values(key_node)

    for source_path in sorted(package_root.rglob("*.py")):
        if source_path in sanctioned_residue:
            continue
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            names: tuple[str, ...] = ()
            if isinstance(node, (ast.Name, ast.Attribute)):
                names = (node.id if isinstance(node, ast.Name) else node.attr,)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = (node.name,)
            elif isinstance(node, ast.arg):
                names = (node.arg,)
            for name in names:
                if "backlog_drain" in name or "BacklogDrain" in name:
                    forbidden_nodes.append(
                        f"{source_path.relative_to(package_root)}:{node.lineno}:{name}"
                    )
            if source_path in frozen_evidence_and_inventory:
                continue
            if isinstance(node, ast.Compare):
                for operand in (node.left, *node.comparators):
                    for value in comparison_key_values(operand):
                        record_string_key(source_path, node, "comparison-key", value)
            elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                record_string_key(source_path, node, "subscript-key", node.slice.value)
            elif isinstance(node, ast.Dict):
                for key_node in node.keys:
                    if isinstance(key_node, ast.Constant):
                        record_string_key(source_path, node, "dict-key", key_node.value)
            elif isinstance(node, ast.MatchValue) and isinstance(node.value, ast.Constant):
                record_string_key(source_path, node, "match-key", node.value.value)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"get", "pop", "setdefault"}
            ):
                if node.args and isinstance(node.args[0], ast.Constant):
                    record_string_key(source_path, node, "call-key", node.args[0].value)

    return sorted(
        forbidden_nodes,
        key=lambda site: (site.split(":", 2)[0], int(site.split(":", 2)[1]), site),
    )


def test_retired_backlog_drain_has_no_name_keyed_compiler_structure() -> None:
    package_root = Path(__file__).parents[1] / "orchestrator" / "workflow_lisp"

    assert _retired_backlog_drain_structure_sites(package_root) == []


def test_retired_backlog_drain_guard_rejects_string_keyed_dispatch(tmp_path: Path) -> None:
    package_root = tmp_path / "orchestrator" / "workflow_lisp"
    package_root.mkdir(parents=True)
    (package_root / "mutated_dispatch.py").write_text(
        "def dispatch(head, handlers):\n"
        "    if head == 'backlog_drain':\n"
        "        return handlers['backlog-drain']\n"
        "    dispatch_table = {'backlog_drain': handlers['default']}\n"
        "    if head in ('backlog_drain',):\n"
        "        return handlers.get('backlog-drain')\n"
        "    if describe('backlog-drain') == head:\n"
        "        return handlers.setdefault('description', 'backlog-drain compatibility')\n"
        "    return dispatch_table\n",
        encoding="utf-8",
    )

    sites = _retired_backlog_drain_structure_sites(package_root)

    assert sites == [
        "mutated_dispatch.py:2:comparison-key:backlog_drain",
        "mutated_dispatch.py:3:subscript-key:backlog-drain",
        "mutated_dispatch.py:4:dict-key:backlog_drain",
        "mutated_dispatch.py:5:comparison-key:backlog_drain",
        "mutated_dispatch.py:6:call-key:backlog-drain",
    ]


def _form_registry_module():
    return importlib.import_module("orchestrator.workflow_lisp.form_registry")


def _control_dispatch_module():
    return importlib.import_module("orchestrator.workflow_lisp.lowering.control_dispatch")


def _command_boundary_environment(
    *,
    gap_output_type_name: str = "GapResult",
    selector_output_type_name: str = "SelectionResult",
) -> CommandBoundaryEnvironment:
    return build_command_boundary_environment(
        {
            "select_next_item": CertifiedAdapterBinding(
                name="select_next_item",
                stable_command=("python", "scripts/select_next_item.py"),
                input_contract={"type": "object"},
                output_type_name=selector_output_type_name,
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


def _compile_inline_module(source: str, *, module_name: str, tmp_path: Path, lowering_route: str | None = None):
    module_path = (tmp_path / Path(*module_name.split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    return compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        command_boundaries=_command_boundary_environment().bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
    )


def test_intrinsic_form_route_accounting_api_starts_empty_and_is_deterministic() -> None:
    dispatch = _control_dispatch_module()

    reset_counts = getattr(dispatch, "reset_intrinsic_form_lowering_counts", None)
    read_counts = getattr(dispatch, "intrinsic_form_lowering_counts", None)

    assert callable(reset_counts)
    assert callable(read_counts)

    reset_counts()
    assert read_counts() == {}


def test_g8_marks_resource_registry_head_as_compatibility_only() -> None:
    registry = _form_registry_module()

    spec = registry.get_form_spec("finalize-selected-item")

    assert spec is not None
    assert spec.macro_bindable is True
    assert "compatibility_route_only" in spec.feature_tags


def test_retired_backlog_drain_registry_uses_imported_stdlib_classification() -> None:
    registry = _form_registry_module()

    spec = registry.get_form_spec("backlog-drain")

    assert spec is not None
    assert spec.kind is registry.FormKind.STDLIB_EXTENSION
    assert spec.elaboration_route is None
    assert spec.macro_bindable is True
    assert spec.remove_by is None
    assert "compatibility_route_only" not in spec.feature_tags
    assert registry.get_form_spec("backlog-drain-callable-boundary") is None


def test_retired_backlog_drain_g8_evidence_constants_match() -> None:
    build_design_delta = importlib.import_module(
        "orchestrator.workflow_lisp.build_design_delta"
    )
    migration_parity = importlib.import_module(
        "orchestrator.workflow_lisp.migration_parity"
    )

    expected = ("with-phase", "backlog-drain")
    assert build_design_delta.DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS == expected
    assert migration_parity.DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS == expected


def test_retired_backlog_drain_callable_boundary_is_not_exported(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_inline_module(
            """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule retired_callable_boundary_import)
  (import std/drain :only (backlog-drain-callable-boundary)))""",
            module_name="retired_callable_boundary_import",
            tmp_path=tmp_path,
        )

    assert [diagnostic.code for diagnostic in excinfo.value.diagnostics] == [
        "module_export_missing"
    ]


def test_g8_marks_public_with_phase_registry_head_as_compatibility_only() -> None:
    registry = _form_registry_module()

    spec = registry.get_form_spec("with-phase")

    assert spec is not None
    assert spec.macro_bindable is True
    assert "compatibility_route_only" in spec.feature_tags


def test_imported_stdlib_with_phase_still_compiles_without_intrinsic_accounting(
    tmp_path: Path,
) -> None:
    dispatch = _control_dispatch_module()
    reset_counts = getattr(dispatch, "reset_intrinsic_form_lowering_counts", None)
    read_counts = getattr(dispatch, "intrinsic_form_lowering_counts", None)

    assert callable(reset_counts)
    assert callable(read_counts)

    reset_counts()
    result = _compile_inline_module(
        """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_with_phase_fixture)
  (import std/context :only (PhaseCtx))
  (import std/phase :only (with-phase))
  (export run-phase)
  (defrecord Result
    (phase_name Symbol)
    (state_root Path.state-root))
  (defworkflow run-phase
    ((phase-ctx PhaseCtx))
    -> Result
    (with-phase phase-ctx imported-phase
      (record Result
        :phase_name phase-ctx.phase-name
        :state_root phase-ctx.state-root))))""",
        module_name="imported_with_phase_fixture",
        tmp_path=tmp_path,
    )

    assert result.entry_result.typed_workflows
    assert read_counts() == {}


def test_bare_with_phase_uses_compatibility_intrinsic_accounting(tmp_path: Path) -> None:
    dispatch = _control_dispatch_module()
    reset_counts = getattr(dispatch, "reset_intrinsic_form_lowering_counts", None)
    read_counts = getattr(dispatch, "intrinsic_form_lowering_counts", None)

    assert callable(reset_counts)
    assert callable(read_counts)

    reset_counts()
    result = _compile_inline_module(
        """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule bare_with_phase_fixture)
  (import std/context :only (PhaseCtx))
  (export run-phase)
  (defrecord Result
    (phase_name Symbol)
    (state_root Path.state-root))
  (defworkflow run-phase
    ((phase-ctx PhaseCtx))
    -> Result
    (with-phase phase-ctx imported-phase
      (record Result
        :phase_name phase-ctx.phase-name
        :state_root phase-ctx.state-root))))""",
        module_name="bare_with_phase_fixture",
        tmp_path=tmp_path,
        lowering_route="legacy",
    )

    assert result.entry_result.typed_workflows
    assert read_counts().get("with-phase") == 1


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


def test_finalize_selected_item_stdlib_vector_compiles_on_promoted_route(tmp_path: Path) -> None:
    result = _compile_module_fixture(RESOURCE_STDLIB_FIXTURE, tmp_path=tmp_path / "resource_finalize_selected_item")

    assert result.entry_result.typed_workflows


def test_backlog_drain_stdlib_vector_compiles_on_promoted_route(tmp_path: Path) -> None:
    result = _compile_module_fixture(DRAIN_STDLIB_FIXTURE, tmp_path=tmp_path / "drain_backlog_drain")

    assert result.entry_result.typed_workflows


def test_legacy_resource_fixture_uses_compatibility_intrinsic_accounting(tmp_path: Path) -> None:
    dispatch = _control_dispatch_module()
    reset_counts = getattr(dispatch, "reset_intrinsic_form_lowering_counts", None)
    read_counts = getattr(dispatch, "intrinsic_form_lowering_counts", None)

    assert callable(reset_counts)
    assert callable(read_counts)

    reset_counts()
    result = compile_stage3_module(
        RESOURCE_INTRINSIC_FIXTURE,
        command_boundaries=_command_boundary_environment().bindings_by_name,
        validate_shared=False,
        workspace_root=tmp_path / RESOURCE_INTRINSIC_FIXTURE.stem,
        lowering_route="legacy",
    )

    assert result.typed_workflows
    assert read_counts().get("finalize-selected-item") == 1


@pytest.mark.parametrize(
    "stdlib_fixture",
    (
        RESOURCE_STDLIB_FIXTURE,
        DRAIN_STDLIB_FIXTURE,
    ),
)
def test_stdlib_vectors_still_compile_on_promoted_route_after_g8_deletion(
    tmp_path: Path,
    stdlib_fixture: Path,
) -> None:
    result = _compile_module_fixture(stdlib_fixture, tmp_path=tmp_path / stdlib_fixture.stem)

    assert result.entry_result.typed_workflows
