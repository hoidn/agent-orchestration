from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    _fixed_resume_command_boundary_bindings,
    _validate_definition_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.workflows import (
    CertifiedAdapterBinding,
    ExternEnvironment,
    ExternalToolBinding,
    PromptExtern,
    ProviderExtern,
    build_command_boundary_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
VALID_PLAN_GATE_FIXTURE = FIXTURES / "valid" / "neurips_plan_gate_resume.orc"
VALID_SELECTED_ITEM_FIXTURE = FIXTURES / "valid" / "neurips_selected_item.orc"
INVALID_PLAN_GATE_FIXTURE = FIXTURES / "invalid" / "neurips_plan_gate_resume_contract_invalid.orc"


def _build_syntax_module(path: Path):
    return build_syntax_module(read_sexpr_file(path))


def _compile_definition_module(path: Path):
    syntax_module = _build_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _extern_environment() -> ExternEnvironment:
    return ExternEnvironment(
        bindings_by_name={
            "providers.selector": ProviderExtern(
                name="providers.selector",
                provider_id="fake-selector",
            ),
            "prompts.selector": PromptExtern(
                name="prompts.selector",
                asset_file="prompts/implementation/execute.md",
            ),
            "providers.gap-drafter": ProviderExtern(
                name="providers.gap-drafter",
                provider_id="fake-gap-drafter",
            ),
            "prompts.gap-drafter": PromptExtern(
                name="prompts.gap-drafter",
                asset_file="prompts/implementation/review.md",
            ),
        }
    )


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


def _typecheck_fixture(path: Path):
    module = _compile_definition_module(path)
    type_env = FrontendTypeEnvironment.from_module(module)
    syntax_module = _build_syntax_module(path)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    return typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        extern_environment=_extern_environment(),
        command_boundary_environment=_command_boundaries(),
    )


def _compile(
    path: Path,
    *,
    tmp_path: Path,
    validate_shared: bool = False,
    lowering_route: str | None = None,
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
        lowering_route=lowering_route,
    )


def _iter_nested_steps(steps):
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        yield step
        repeat = step.get("repeat_until")
        if isinstance(repeat, dict):
            yield from _iter_nested_steps(repeat.get("steps"))
        match = step.get("match")
        if isinstance(match, dict):
            for case in (match.get("cases") or {}).values():
                if isinstance(case, dict):
                    yield from _iter_nested_steps(case.get("steps"))


def test_neurips_plan_gate_resume_typechecks_union_start_workflow_call(tmp_path: Path) -> None:
    typed = _compile(VALID_PLAN_GATE_FIXTURE, tmp_path=tmp_path, validate_shared=False).typed_workflows

    assert [workflow.definition.name for workflow in typed] == [
        "neurips_plan_gate_resume::plan-run",
        "neurips_plan_gate_resume::resume-plan-gate",
    ]


def test_neurips_plan_gate_resume_lowers_and_validates(tmp_path: Path) -> None:
    result = _compile(VALID_PLAN_GATE_FIXTURE, tmp_path=tmp_path, validate_shared=True)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "neurips_plan_gate_resume::resume-plan-gate"
    )
    branch_step = next(
        step
        for step in authored["steps"]
        if step.get("name") == "neurips_plan_gate_resume::resume-plan-gate__result"
    )
    start_steps = branch_step["match"]["cases"]["START"]["steps"]

    assert any(
        step.get("call") == "neurips_plan_gate_resume::plan-run"
        for step in _iter_nested_steps(start_steps)
    )
    assert tuple(result.validated_bundles) == (
        "neurips_plan_gate_resume::plan-run",
        "neurips_plan_gate_resume::resume-plan-gate",
    )


def test_neurips_selected_item_compiles_and_validates(tmp_path: Path) -> None:
    result = _compile(VALID_SELECTED_ITEM_FIXTURE, tmp_path=tmp_path, validate_shared=True)
    authored = next(
        workflow.authored_mapping
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "run-selected-item"
    )
    nested_steps = list(_iter_nested_steps(authored["steps"]))

    assert any(step.get("call") == "roadmap-sync" for step in nested_steps)
    assert any(step.get("call") == "implementation-run" for step in nested_steps)
    assert any(
        step.get("command", [])[:3] == ["python", "-m", "orchestrator.workflow_lisp.adapters.apply_resource_transition"]
        for step in nested_steps
    )


def test_neurips_plan_gate_resume_contract_invalid(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(INVALID_PLAN_GATE_FIXTURE, tmp_path=tmp_path, validate_shared=False)

    assert excinfo.value.diagnostics[0].code == "resume_or_start_contract_invalid"
