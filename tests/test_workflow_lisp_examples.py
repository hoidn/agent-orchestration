from pathlib import Path

from orchestrator.workflow_lisp.compiler import compile_stage3_module


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows" / "examples"


def test_kiss_backlog_item_orc_compiles_to_typed_phase_stack(tmp_path: Path) -> None:
    result = compile_stage3_module(
        WORKFLOWS / "kiss_backlog_item.orc",
        provider_externs={
            "providers.plan": "fake-plan",
            "providers.plan-review": "fake-plan-review",
            "providers.plan-fix": "fake-plan-fix",
            "providers.implementation": "fake-implementation",
            "providers.implementation-review": "fake-implementation-review",
            "providers.implementation-fix": "fake-implementation-fix",
        },
        prompt_externs={
            "prompts.plan.draft": "workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md",
            "prompts.plan.review": "workflows/library/prompts/design_plan_impl_stack_v2_call/review_plan.md",
            "prompts.plan.fix": "workflows/library/prompts/design_plan_impl_stack_v2_call/revise_plan.md",
            "prompts.implementation.execute": (
                "workflows/library/prompts/design_plan_impl_stack_v2_call/implement_plan.md"
            ),
            "prompts.implementation.review": (
                "workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md"
            ),
            "prompts.implementation.fix": (
                "workflows/library/prompts/design_plan_impl_stack_v2_call/fix_implementation.md"
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered_by_name = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
    }

    assert set(lowered_by_name) == {
        "draft-plan-phase",
        "review-plan-phase",
        "review-implementation-phase",
        "run-approved-plan",
        "run-backlog-item",
    }
    assert lowered_by_name["run-backlog-item"]["version"] == "2.14"

    plan_review_steps = [
        step
        for step in lowered_by_name["review-plan-phase"]["steps"]
        if "repeat_until" in step
    ]
    implementation_review_steps = [
        step
        for step in lowered_by_name["review-implementation-phase"]["steps"]
        if "repeat_until" in step
    ]

    assert lowered_by_name["draft-plan-phase"]["steps"][0]["provider"] == "fake-plan"
    implementation_steps = [
        step
        for step in lowered_by_name["run-approved-plan"]["steps"]
        if step.get("provider") == "fake-implementation"
    ]
    assert len(implementation_steps) == 1
    assert "execute-implementation-phase" in implementation_steps[0]["name"]
    assert len(plan_review_steps) == 1
    assert len(implementation_review_steps) == 1
    assert "return__summary_path" in lowered_by_name["run-backlog-item"]["outputs"]

    review_plan_call = next(
        step
        for step in lowered_by_name["run-backlog-item"]["steps"]
        if step.get("call") == "review-plan-phase"
    )
    review_impl_call = next(
        step
        for step in lowered_by_name["run-approved-plan"]["steps"]
        if step.get("call") == "review-implementation-phase"
    )

    assert any(name.startswith("__write_root__") for name in review_plan_call["with"])
    assert any(name.startswith("__write_root__") for name in review_impl_call["with"])
    assert all(
        str(value).startswith(".orchestrate/workflow_lisp/calls/")
        for name, value in review_plan_call["with"].items()
        if name.startswith("__write_root__")
    )


def test_with_phase_composed_binding_orc_compiles_to_typed_phase_stack(tmp_path: Path) -> None:
    result = compile_stage3_module(
        WORKFLOWS / "with_phase_composed_binding.orc",
        provider_externs={
            "providers.execute": "test-provider",
        },
        prompt_externs={
            "prompts.implementation.execute": (
                "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = result.lowered_workflows[0].authored_mapping

    assert result.lowered_workflows[0].typed_workflow.definition.name == "run-with-phase-composed-binding"
    assert [step["name"] for step in lowered["steps"]] == [
        "MaterializeImplementationAttemptPromptInputs",
        "run-with-phase-composed-binding__phase-result",
        "run-with-phase-composed-binding__match_phase-result",
    ]
    assert lowered["steps"][1]["provider"] == "test-provider"
