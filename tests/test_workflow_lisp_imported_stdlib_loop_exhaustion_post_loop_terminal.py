from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow.surface_ast import SurfaceStep
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "modules"
VALID_ROOT = FIXTURES / "valid" / "imported_stdlib_loop_exhaustion_post_loop_terminal"
VALID_ENTRY_FIXTURE = VALID_ROOT / "entry.orc"

INVALID_FIXTURES: dict[str, tuple[Path, Path, str]] = {
    "direct_resource_transition": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_resource_transition",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_resource_transition" / "entry.orc",
        "loop_recur_contract_invalid",
    ),
    "direct_materialize_view": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_materialize_view",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_materialize_view" / "entry.orc",
        "loop_recur_contract_invalid",
    ),
    "direct_command_result": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_command_result",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_direct_command_result" / "entry.orc",
        "loop_recur_contract_invalid",
    ),
    "effectful_on_exhausted_helper": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_effectful_on_exhausted_helper",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_effectful_on_exhausted_helper" / "entry.orc",
        "loop_recur_contract_invalid",
    ),
    "view_authority_finalizer": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_view_authority_finalizer",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_view_authority_finalizer" / "entry.orc",
        "materialized_view_used_as_semantic_authority",
    ),
    "unproved_variant_payload": (
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_unproved_variant_payload",
        FIXTURES / "invalid" / "imported_stdlib_loop_exhaustion_unproved_variant_payload" / "entry.orc",
        "variant_ref_unproved",
    ),
}

SUMMARY_PATH = "artifacts/work/imported-stdlib-loop-exhaustion-summary.json"
RUN_STATE_PATH = "state/imported-stdlib-loop-exhaustion-run-state.json"


def _command_boundaries() -> dict[str, ExternalToolBinding]:
    return {
        "run_checks": ExternalToolBinding(
            name="run_checks",
            stable_command=("python", "scripts/run_checks.py"),
        )
    }


def _compile_entry_fixture(
    path: Path,
    *,
    source_root: Path,
    tmp_path: Path,
    command_boundaries: dict[str, ExternalToolBinding] | None = None,
):
    return compile_stage3_entrypoint(
        path,
        source_roots=(source_root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries=command_boundaries or {},
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
    if kind == "record":
        return {
            str(field["name"]): _default_state_value(dict(field["type"]))
            for field in type_payload.get("fields", ())
        }
    if kind == "path":
        return ""
    if kind == "enum":
        allowed = type_payload.get("allowed", ())
        if isinstance(allowed, list) and allowed:
            return allowed[0]
    raise AssertionError(f"unsupported state seed type: {type_payload!r}")


def _seed_native_resource_states(bundles, workspace: Path) -> None:
    for bundle in bundles:
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


def _execute_bundle(bundle, *, workflow_path: Path, workspace: Path, run_id: str, related_bundles=()) -> dict[str, object]:
    _seed_native_resource_states((bundle, *tuple(related_bundles)), workspace)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bound_runtime_inputs(bundle, workspace),
    )
    return WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(on_error="stop")


def _iter_authored_steps(steps: list[dict[str, object]]):
    for step in steps:
        yield step
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            yield from _iter_authored_steps(repeat_until.get("steps", []))
        match_stmt = step.get("match")
        if isinstance(match_stmt, dict):
            for case in match_stmt.get("cases", {}).values():
                yield from _iter_authored_steps(case.get("steps", []))


def test_positive_imported_stdlib_loop_exhaustion_post_loop_terminal_route_compiles_and_executes(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)

    assert result.entry_result.lowering_schema_version == 2
    workflow_name = "entry::run-drain-like"
    assert workflow_name in result.validated_bundles_by_name

    bundle = result.validated_bundles_by_name[workflow_name]
    effect_kinds = {
        effect.effect_kind
        for validated_bundle in result.validated_bundles_by_name.values()
        for effect in validated_bundle.semantic_ir.effects.values()
    }
    lowered = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == workflow_name
    )
    authored = lowered.authored_mapping
    repeat_index, repeat_step = next(
        (index, step)
        for index, step in enumerate(authored["steps"])
        if "repeat_until" in step
    )
    on_exhausted = repeat_step["repeat_until"]["on_exhausted"]
    source_map_text = json.dumps(
        asdict(
            build_source_map_document(
                result,
                selected_name=workflow_name,
                display_name_resolver=lambda name: name,
            )
        ),
        sort_keys=True,
    )
    semantic_ir_text = json.dumps(
        {
            name: workflow_semantic_ir_to_json(validated_bundle.semantic_ir)
            for name, validated_bundle in result.validated_bundles_by_name.items()
        },
        sort_keys=True,
    )

    assert effect_kinds >= {"resource_transition", "materialize_view"}
    assert set(on_exhausted) == {"outputs"}
    assert on_exhausted["outputs"]
    assert all(not isinstance(value, dict) or set(value) == {"ref"} for value in on_exhausted["outputs"].values())

    steps_after_repeat = list(_iter_authored_steps(authored["steps"][repeat_index + 1 :]))
    assert any(step.get("call") == "std_drain_exhaustion::finalize-terminal" for step in steps_after_repeat)
    assert "std_drain_exhaustion.orc" in source_map_text
    assert "entry.orc" in source_map_text
    assert "emit-run-drain-like" in source_map_text
    assert "finalize-terminal" in source_map_text
    assert "resource_transition" in semantic_ir_text
    assert "materialize_view" in semantic_ir_text

    (tmp_path / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
    (tmp_path / SUMMARY_PATH).write_text("seed\n", encoding="utf-8")
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / RUN_STATE_PATH).write_text("{}\n", encoding="utf-8")

    state = _execute_bundle(
        bundle,
        workflow_path=VALID_ENTRY_FIXTURE,
        workspace=tmp_path,
        run_id="g5d-imported-stdlib-loop-exhaustion-post-loop-terminal",
        related_bundles=tuple(
            validated_bundle
            for name, validated_bundle in result.validated_bundles_by_name.items()
            if name != workflow_name
        ),
    )
    summary_payload = json.loads((tmp_path / SUMMARY_PATH).read_text(encoding="utf-8"))

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["return__variant"] == "EXHAUSTED"
    assert state["workflow_outputs"]["return__items_processed"] == 1
    assert (
        state["workflow_outputs"]["return__progress_report_path"]
        == "artifacts/work/imported-stdlib-loop-exhaustion-summary.json"
    )
    assert state["workflow_outputs"]["return__blocker_class"] == "unrecoverable_after_fix_attempt"
    assert summary_payload == {
        "blocker_class": "unrecoverable_after_fix_attempt",
        "items_processed": 1,
        "run_state": "state/imported-stdlib-loop-exhaustion-run-state.json",
        "variant": "EXHAUSTED",
    }


@pytest.mark.parametrize("fixture_key", tuple(INVALID_FIXTURES))
def test_invalid_imported_stdlib_loop_exhaustion_routes_fail_with_owner_layer_diagnostics(
    tmp_path: Path,
    *,
    fixture_key: str,
) -> None:
    source_root, path, expected_code = INVALID_FIXTURES[fixture_key]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(
            path,
            source_root=source_root,
            tmp_path=tmp_path,
            command_boundaries=_command_boundaries()
            if fixture_key in {"direct_command_result", "view_authority_finalizer"}
            else None,
        )

    assert excinfo.value.diagnostics[0].code == expected_code
