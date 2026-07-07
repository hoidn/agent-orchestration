from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow.surface_ast import SurfaceStep
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.source_map import build_source_map_document
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURES / "modules"
VALID_MODULE_ROOT = MODULE_FIXTURES / "valid" / "generic_stdlib_composition"
VALID_ENTRY_FIXTURE = VALID_MODULE_ROOT / "generic_stdlib_composition" / "entry.orc"
INVALID_MODULE_ROOT = MODULE_FIXTURES / "invalid" / "generic_stdlib_composition_unqualified_transition"
INVALID_ENTRY_FIXTURE = (
    INVALID_MODULE_ROOT / "generic_stdlib_composition_unqualified_transition" / "entry.orc"
)
CAPABILITY_UNDECLARED_FIXTURE = FIXTURES / "invalid" / "generic_stdlib_composition_capability_undeclared.orc"
CONSTRAINT_ORDERING_FIXTURE = FIXTURES / "invalid" / "generic_stdlib_composition_constraint_ordering.orc"
NON_EXHAUSTIVE_FIXTURE = FIXTURES / "invalid" / "generic_stdlib_composition_non_exhaustive.orc"


def _assert_diagnostic_code(excinfo: pytest.ExceptionInfo[LispFrontendCompileError], code: str) -> None:
    assert excinfo.value.diagnostics[0].code == code


def _compile_entry_fixture(path: Path, *, source_root: Path, tmp_path: Path, validate_shared: bool = True):
    return compile_stage3_entrypoint(
        path,
        source_roots=(source_root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=validate_shared,
        workspace_root=tmp_path,
        lowering_route=None,
    )


def _compile_module_fixture(path: Path, *, tmp_path: Path):
    return compile_stage3_module(
        path,
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )


def _bound_runtime_inputs(bundle, workspace: Path) -> dict[str, object]:
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    public_inputs = {
        input_name: contract
        for input_name, contract in runtime_inputs.items()
        if not input_name.startswith("__write_root__")
    }
    return bind_workflow_inputs(public_inputs, {}, workspace)


def _default_state_value(type_payload: dict[str, object]) -> object:
    kind = type_payload.get("kind")
    if kind == "primitive":
        primitive_name = type_payload.get("name")
        if primitive_name == "String":
            return ""
        if primitive_name == "Bool":
            return False
        if primitive_name == "Int":
            return 0
        if primitive_name == "Float":
            return 0.0
        if primitive_name == "Json":
            return {}
    if kind == "record":
        return {
            str(field["name"]): _default_state_value(dict(field["type"]))
            for field in type_payload.get("fields", ())
        }
    if kind == "list":
        return []
    if kind == "map":
        return {}
    if kind == "optional":
        return None
    raise AssertionError(f"unsupported test seed type: {type_payload!r}")


def _iter_surface_steps(steps: tuple[SurfaceStep, ...]) -> tuple[SurfaceStep, ...]:
    collected: list[SurfaceStep] = []

    def visit(step: SurfaceStep) -> None:
        collected.append(step)
        for branch_step in step.then_branch or ():
            visit(branch_step)
        for branch_step in step.else_branch or ():
            visit(branch_step)
        for branch_step in step.for_each_steps or ():
            visit(branch_step)
        for case in step.match_cases.values():
            for case_step in case.steps:
                visit(case_step)

    for step in steps:
        visit(step)
    return tuple(collected)


def _seed_native_resource_states(bundle, workspace: Path) -> None:
    for step in _iter_surface_steps(bundle.surface.steps):
        declaration = step.resource_transition.get("declaration")
        resource = step.resource_transition.get("resource")
        if declaration is None or resource is None:
            continue
        if declaration.resource.backing.kind != "native":
            continue
        state_path = workspace / str(resource["state_path"])
        if state_path.exists():
            continue
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "transition_schema_version": 1,
                    "resource_id": resource["resource_id"],
                    "resource_kind": resource["resource_kind"],
                    "state_version": "native:0:seed",
                    "state": _default_state_value(dict(declaration.resource.state_type)),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def _execute_bundle(bundle, *, workflow_path: Path, workspace: Path, run_id: str) -> dict[str, object]:
    _seed_native_resource_states(bundle, workspace)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bound_runtime_inputs(bundle, workspace),
    )
    return WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(on_error="stop")


def _single_jsonl(workspace: Path) -> Path:
    matches = sorted(path for path in workspace.rglob("*.jsonl") if path.is_file())
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize(
    ("workflow_name", "expected_status", "expected_message"),
    [
        ("run-outcome", "APPROVED", "accepted"),
        ("run-outcome-wrapped", "BLOCKED", "blocked"),
        ("run-outcome-inline", "APPROVED", "inline"),
    ],
)
def test_imported_generic_stdlib_positive_route_compiles_with_effects_source_maps_and_runtime_erasure(
    tmp_path: Path,
    *,
    workflow_name: str,
    expected_status: str,
    expected_message: str,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_MODULE_ROOT, tmp_path=tmp_path)

    assert result.entry_result.lowering_schema_version == 2
    assert {
        "generic_stdlib_composition/entry::run-outcome",
        "generic_stdlib_composition/entry::run-outcome-wrapped",
        "generic_stdlib_composition/entry::run-outcome-inline",
    } <= set(result.validated_bundles_by_name)

    specialized = next(
        procedure
        for procedure in result.entry_result.typed_procedures
        if getattr(procedure.specialization, "base_name", "") == "generic_stdlib_composition/helper::run-generic"
    )
    serialized_bundle = json.dumps(
        workflow_executable_ir_to_json(
            result.validated_bundles_by_name[f"generic_stdlib_composition/entry::{workflow_name}"].ir
        ),
        sort_keys=True,
    )
    serialized_semantic = json.dumps(
        workflow_semantic_ir_to_json(
            result.validated_bundles_by_name[f"generic_stdlib_composition/entry::{workflow_name}"].semantic_ir
        ),
        sort_keys=True,
    )
    source_map_text = json.dumps(
        asdict(
            build_source_map_document(
                result,
                selected_name=f"generic_stdlib_composition/entry::{workflow_name}",
                display_name_resolver=lambda name: name,
            )
        ),
        sort_keys=True,
    )
    effect_kinds = {
        effect.effect_kind
        for effect in result.validated_bundles_by_name[
            f"generic_stdlib_composition/entry::{workflow_name}"
        ].semantic_ir.effects.values()
    }

    assert specialized.signature.type_params == ()
    assert type(specialized.signature.return_type_ref).__name__ != "TypeParamRef"
    assert effect_kinds >= {"resource_transition", "materialize_view"}
    assert "generic_stdlib_composition/helper.orc" in source_map_text
    assert "generic_stdlib_composition/entry.orc" in source_map_text
    assert "run-generic" in source_map_text
    assert "lowering_route" not in source_map_text
    for payload in (serialized_bundle, serialized_semantic, source_map_text):
        assert "TypeParamRef" not in payload
        assert "has-union-variant" not in payload
        assert "ProcRef[" not in payload
    state = _execute_bundle(
        result.validated_bundles_by_name[f"generic_stdlib_composition/entry::{workflow_name}"],
        workflow_path=VALID_ENTRY_FIXTURE,
        workspace=tmp_path,
        run_id=f"g5a-{workflow_name}",
    )
    rendered_summary = tmp_path / state["workflow_outputs"]["return__summary_path"]
    audit_rows = [
        json.loads(line)
        for line in _single_jsonl(tmp_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["return__status"] == expected_status
    assert rendered_summary.read_bytes() == json.dumps(
        {"message": expected_message, "status": expected_status},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    assert audit_rows[-1]["outcome_code"] == "committed"


@pytest.mark.parametrize(
    ("workflow_name", "expected_status"),
    [
        ("run-outcome", "APPROVED"),
        ("run-outcome-wrapped", "BLOCKED"),
    ],
)
def test_imported_generic_stdlib_runtime_replay_keeps_materialized_view_bytes_stable(
    tmp_path: Path,
    *,
    workflow_name: str,
    expected_status: str,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_MODULE_ROOT, tmp_path=tmp_path)
    bundle = result.validated_bundles_by_name[f"generic_stdlib_composition/entry::{workflow_name}"]

    first_workspace = tmp_path / "first"
    second_workspace = tmp_path / "second"
    first_workspace.mkdir()
    second_workspace.mkdir()

    first = _execute_bundle(
        bundle,
        workflow_path=VALID_ENTRY_FIXTURE,
        workspace=first_workspace,
        run_id=f"{workflow_name}-first",
    )
    second = _execute_bundle(
        bundle,
        workflow_path=VALID_ENTRY_FIXTURE,
        workspace=second_workspace,
        run_id=f"{workflow_name}-second",
    )

    first_bytes = (first_workspace / first["workflow_outputs"]["return__summary_path"]).read_bytes()
    second_bytes = (second_workspace / second["workflow_outputs"]["return__summary_path"]).read_bytes()

    assert first["workflow_outputs"]["return__status"] == expected_status
    assert second["workflow_outputs"]["return__status"] == expected_status
    assert first_bytes == second_bytes


def test_compile_stage3_entrypoint_rejects_unqualified_macro_emitted_transition_reference(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(INVALID_ENTRY_FIXTURE, source_root=INVALID_MODULE_ROOT, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "transition_unknown")


def test_compile_stage3_rejects_parametric_capability_undeclared(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(CAPABILITY_UNDECLARED_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_capability_undeclared")


def test_compile_stage3_preserves_constraint_failure_before_instantiated_body_typecheck(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(CONSTRAINT_ORDERING_FIXTURE, tmp_path=tmp_path)

    _assert_diagnostic_code(excinfo, "parametric_constraint_unsatisfied")
    assert "APPROVED" in excinfo.value.diagnostics[0].message


def test_compile_stage3_rechecks_instantiated_generic_match_exhaustiveness(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_module_fixture(NON_EXHAUSTIVE_FIXTURE, tmp_path=tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    call_line = next(
        line_number
        for line_number, line in enumerate(NON_EXHAUSTIVE_FIXTURE.read_text(encoding="utf-8").splitlines(), 1)
        if "(status-from-outcome" in line
    )
    _assert_diagnostic_code(excinfo, "union_match_non_exhaustive")
    assert diagnostic.span.start.path == str(NON_EXHAUSTIVE_FIXTURE)
    assert any(
        "instantiated from" in note and f"{NON_EXHAUSTIVE_FIXTURE}:{call_line}:" in note
        for note in diagnostic.notes
    )
