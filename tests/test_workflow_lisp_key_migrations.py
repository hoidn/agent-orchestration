from __future__ import annotations

import json
from pathlib import Path

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_input_contracts
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows"
EXAMPLES = WORKFLOWS / "examples"
MIGRATION_INPUTS = EXAMPLES / "inputs" / "workflow_lisp_migrations"


def _load_json(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_cycle_guard_demo_orc_compiles_with_bounded_loop(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
    }

    assert set(lowered) == {"cycle-guard-demo"}
    mapping = lowered["cycle-guard-demo"]
    assert mapping["version"] == "2.14"
    assert len(mapping["steps"]) == 1
    assert mapping["steps"][0]["command"][:2] == ["python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"]
    hidden_inputs = [name for name in mapping["inputs"] if name.startswith("__write_root__")]
    assert len(hidden_inputs) == 1
    assert mapping["outputs"]["return__terminal_status"]["type"] == "string"
    assert mapping["outputs"]["return__guard_cycles"]["type"] == "integer"


def test_cycle_guard_demo_orc_runtime_materializes_output_bundle(tmp_path: Path) -> None:
    result = compile_stage3_module(
        EXAMPLES / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    bundle = result.validated_bundles["cycle-guard-demo"]
    hidden_inputs = tuple(
        name for name in workflow_input_contracts(bundle) if isinstance(name, str) and name.startswith("__write_root__")
    )
    assert len(hidden_inputs) == 1
    hidden_input_name = hidden_inputs[0]

    adapter_source = REPO_ROOT / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest = tmp_path / "scripts" / "workflow_lisp_migrations" / "emit_cycle_guard_summary.py"
    adapter_dest.parent.mkdir(parents=True, exist_ok=True)
    adapter_dest.write_text(adapter_source.read_text(encoding="utf-8"), encoding="utf-8")

    output_bundle_relpath = "state/cycle-guard-result.json"
    state_manager = StateManager(workspace=tmp_path, run_id="cycle-guard-orc-runtime")
    state_manager.initialize(
        (EXAMPLES / "cycle_guard_demo.orc").as_posix(),
        bound_inputs={
            "terminal_status": "FAILED_CLOSED_BY_GUARD",
            "guard_cycles": 2,
            hidden_input_name: output_bundle_relpath,
        },
    )
    state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute()

    assert state["status"] == "completed"
    bundle_path = tmp_path / output_bundle_relpath
    assert bundle_path.is_file()
    assert json.loads(bundle_path.read_text(encoding="utf-8")) == {
        "terminal_status": "FAILED_CLOSED_BY_GUARD",
        "guard_cycles": 2,
    }


def test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts(tmp_path: Path) -> None:
    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")

    result = compile_stage3_module(
        EXAMPLES / "design_plan_impl_review_stack_v2_call.orc",
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
    }

    assert set(lowered) == {
        "tracked-design-phase",
        "tracked-plan-phase",
        "design-plan-impl-implementation-phase",
        "design-plan-impl-review-stack",
    }

    assert lowered["tracked-design-phase"]["steps"][0]["provider"] == "codex"
    assert lowered["tracked-plan-phase"]["steps"][0]["provider"] == "codex"
    assert lowered["design-plan-impl-implementation-phase"]["steps"][0]["provider"] == "codex"

    stack_outputs = lowered["design-plan-impl-review-stack"]["outputs"]
    output_names = {name.removeprefix("return__") for name in stack_outputs}
    assert output_names == {
        "design_path",
        "design_review_report_path",
        "design_review_decision",
        "plan_path",
        "plan_review_report_path",
        "plan_review_decision",
        "execution_report_path",
        "implementation_review_report_path",
        "implementation_review_decision",
    }


def test_library_orc_variants_compile_independently(tmp_path: Path) -> None:
    provider_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json")
    prompt_externs = _load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json")

    library_targets = [
        WORKFLOWS / "library" / "tracked_design_phase.orc",
        WORKFLOWS / "library" / "tracked_plan_phase.orc",
        WORKFLOWS / "library" / "design_plan_impl_implementation_phase.orc",
    ]

    expected = {
        "tracked_design_phase.orc": "tracked-design-phase",
        "tracked_plan_phase.orc": "tracked-plan-phase",
        "design_plan_impl_implementation_phase.orc": "design-plan-impl-implementation-phase",
    }

    for target in library_targets:
        result = compile_stage3_module(
            target,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            command_boundaries={},
            validate_shared=True,
            workspace_root=tmp_path,
        )
        lowered_names = {workflow.typed_workflow.definition.name for workflow in result.lowered_workflows}
        assert lowered_names == {expected[target.name]}
