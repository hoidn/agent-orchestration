from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.source_map import build_source_map_document
from tests.workflow_bundle_helpers import bundle_context_dict


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "modules"
VALID_ROOT = (
    FIXTURES / "valid" / "nested_loop_match_continue_carriage" / "nested_loop_match_continue_carriage"
)
VALID_ENTRY_FIXTURE = VALID_ROOT / "entry.orc"
WORKFLOW_NAME = "entry::run-carriage"

INVALID_FIXTURES: dict[str, tuple[Path, Path, str]] = {
    "branch_local_ref_leak": (
        FIXTURES
        / "invalid"
        / "nested_loop_match_continue_branch_local_ref_leak"
        / "nested_loop_match_continue_branch_local_ref_leak",
        FIXTURES
        / "invalid"
        / "nested_loop_match_continue_branch_local_ref_leak"
        / "nested_loop_match_continue_branch_local_ref_leak"
        / "entry.orc",
        "name_unknown",
    ),
    "proof_reset": (
        FIXTURES
        / "invalid"
        / "nested_loop_match_continue_proof_reset"
        / "nested_loop_match_continue_proof_reset",
        FIXTURES
        / "invalid"
        / "nested_loop_match_continue_proof_reset"
        / "nested_loop_match_continue_proof_reset"
        / "entry.orc",
        "variant_ref_unproved",
    ),
}


def _compile_entry_fixture(path: Path, *, source_root: Path, tmp_path: Path):
    return compile_stage3_entrypoint(
        path,
        source_roots=(source_root,),
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


def _execute_bundle(bundle, *, workflow_path: Path, workspace: Path, run_id: str) -> dict[str, object]:
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        workflow_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=_bound_runtime_inputs(bundle, workspace),
    )
    return WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(on_error="stop")


def _walk_steps(steps: list[dict[str, object]]):
    for step in steps:
        yield step
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            nested = repeat_until.get("steps", [])
            if isinstance(nested, list):
                yield from _walk_steps(nested)
        match_block = step.get("match")
        if isinstance(match_block, dict):
            cases = match_block.get("cases", {})
            if isinstance(cases, dict):
                for case in cases.values():
                    if isinstance(case, dict):
                        nested = case.get("steps", [])
                        if isinstance(nested, list):
                            yield from _walk_steps(nested)


def test_positive_nested_loop_match_continue_carriage_compiles_on_wcc_schema2_and_executes(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)

    assert result.entry_result.lowering_schema_version == 2
    assert WORKFLOW_NAME in result.validated_bundles_by_name

    bundle = result.validated_bundles_by_name[WORKFLOW_NAME]
    state = _execute_bundle(
        bundle,
        workflow_path=VALID_ENTRY_FIXTURE,
        workspace=tmp_path,
        run_id="g5c1-nested-loop-match-continue-carriage-positive",
    )

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["return__carried_run_id"] == "gap-1-carried"
    assert state["workflow_outputs"]["return__selected_id"] == "selected-2"


def test_positive_nested_loop_match_continue_carriage_materializes_branch_local_values_onto_repeat_until_outputs(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)
    lowered = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == WORKFLOW_NAME
    )
    repeat_step = next(step for step in lowered.authored_mapping["steps"] if "repeat_until" in step)
    outputs = repeat_step["repeat_until"]["outputs"]
    carried_output = outputs["state__carried_run_id"]
    carried_ref = carried_output["from"]["ref"]
    authored_payload = json.dumps(repeat_step, sort_keys=True)

    assert carried_ref.startswith("self.steps.")
    assert carried_ref.endswith(".artifacts.state__carried_run_id")
    assert "continued" not in carried_ref
    assert "gap_decision" not in carried_ref
    assert "state__carried_run_id" in authored_payload


def test_positive_nested_loop_match_continue_carriage_is_name_neutral(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)
    source_map_document = asdict(
        build_source_map_document(
            result,
            selected_name=WORKFLOW_NAME,
            display_name_resolver=lambda name: name,
        )
    )
    workflow = source_map_document["workflows"][WORKFLOW_NAME]
    source_map_payload = json.dumps(source_map_document, sort_keys=True)
    lowered = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == WORKFLOW_NAME
    )
    lowered_payload = json.dumps(lowered.authored_mapping, sort_keys=True)

    assert "std/drain" not in source_map_payload
    assert "backlog-drain" not in source_map_payload
    assert "helper.orc" in source_map_payload
    assert "entry.orc" in source_map_payload
    assert "run-carriage" in source_map_payload
    assert "draft-gap" in source_map_payload
    assert "continue" in source_map_payload
    assert any(node["step_kind"] == "match" for node in workflow["core_nodes"])
    assert any(node["kind"] == "match_join" for node in workflow["executable_nodes"])
    assert any(
        node["kind"] == "match_case_marker" and node["presentation_name"].endswith(".GAP")
        for node in workflow["executable_nodes"]
    )
    assert any(node["kind"] == "repeat_until_frame" for node in workflow["executable_nodes"])
    assert "repeat_until" in lowered_payload


def test_branch_local_ref_leak_fails_without_loop_frame_materialization(
    tmp_path: Path,
) -> None:
    source_root, path, expected_code = INVALID_FIXTURES["branch_local_ref_leak"]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(path, source_root=source_root, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == expected_code


def test_proof_reset_requires_rematch_for_carried_union_value(
    tmp_path: Path,
) -> None:
    source_root, path, expected_code = INVALID_FIXTURES["proof_reset"]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(path, source_root=source_root, tmp_path=tmp_path)

    assert excinfo.value.diagnostics[0].code == expected_code
