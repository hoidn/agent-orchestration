from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import _fixed_resume_command_boundary_bindings, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import CertifiedAdapterBinding, ExternalToolBinding, build_command_boundary_environment


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_PLAN_GATE_FIXTURE = FIXTURES / "current235" / "valid" / "neurips_plan_gate_resume.orc"
VALID_SELECTED_ITEM_FIXTURE = FIXTURES / "valid" / "neurips_selected_item.orc"
INVALID_PLAN_GATE_FIXTURE = FIXTURES / "current235" / "invalid" / "neurips_plan_gate_resume_contract_invalid.orc"








def _command_boundaries():
    return build_command_boundary_environment(
        {
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            ),
            "resolve_wrong_plan_gate": ExternalToolBinding(
                name="resolve_wrong_plan_gate",
                stable_command=("python", "scripts/resolve_wrong_plan_gate.py"),
            ),
            "resolve_roadmap": ExternalToolBinding(
                name="resolve_roadmap",
                stable_command=("python", "scripts/resolve_roadmap.py"),
            ),
            "execute_implementation": ExternalToolBinding(
                name="execute_implementation",
                stable_command=("python", "scripts/execute_implementation.py"),
            ),
            "select_next_item": ExternalToolBinding(
                name="select_next_item",
                stable_command=("python", "scripts/select_next_item.py"),
            ),
            "execute_selected_item": ExternalToolBinding(
                name="execute_selected_item",
                stable_command=("python", "scripts/execute_selected_item.py"),
            ),
            "draft_gap_item": ExternalToolBinding(
                name="draft_gap_item",
                stable_command=("python", "scripts/draft_gap_item.py"),
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
            **_fixed_resume_command_boundary_bindings(),
            "load_canonical_phase_result__PlanGateResult": CertifiedAdapterBinding(
                name="load_canonical_phase_result__PlanGateResult",
                stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.load_canonical_phase_result"),
                input_contract={"type": "object"},
                output_type_name="PlanGateResult",
                effects=("structured_result",),
                path_safety={"kind": "workspace_relpath"},
                source_map_behavior="step",
                fixture_ids=("resume_state_load_PlanGateResult",),
                negative_fixture_ids=("resume_state_loader_schema_invalid",),
            ),
        }
    )


def test_stage7_resume_command_boundaries_include_certified_writer() -> None:
    bindings = _command_boundaries().bindings_by_name

    assert isinstance(bindings["write_reusable_phase_state_v1"], CertifiedAdapterBinding)
    assert bindings["write_reusable_phase_state_v1"].stable_command == (
        "python",
        "-m",
        "orchestrator.workflow_lisp.adapters.write_reusable_phase_state_v1",
    )




def _compile(
    path: Path,
    *,
    tmp_path: Path,
    validate_shared: bool = False,
):
    return compile_stage3_module(
        path,
        provider_externs={
            "providers.selector": "fake-selector",
            "providers.gap-drafter": "fake-gap-drafter",
        },
        prompt_externs={
            "prompts.selector": "prompts/implementation/execute.md",
            "prompts.gap-drafter": "prompts/implementation/review.md",
        },
        command_boundaries=_command_boundaries().bindings_by_name,
        validate_shared=validate_shared,
        workspace_root=tmp_path,

    )




def test_neurips_plan_gate_resume_typechecks_union_start_workflow_call(tmp_path: Path) -> None:
    typed = _compile(VALID_PLAN_GATE_FIXTURE, tmp_path=tmp_path, validate_shared=False).typed_workflows

    assert [workflow.definition.name for workflow in typed] == [
        "neurips_plan_gate_resume::plan-run",
        "neurips_plan_gate_resume::resume-plan-gate",
    ]






def test_neurips_plan_gate_resume_contract_invalid(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_PLAN_GATE_FIXTURE, tmp_path=tmp_path, validate_shared=False)

    assert excinfo.value.diagnostics[0].code == "resume_or_start_contract_invalid"
