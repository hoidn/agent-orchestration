from pathlib import Path

import importlib

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows" / "examples"
PARAMETRIC_REVIEW_EXAMPLE = WORKFLOWS / "review_revise_parametric_design_docs.orc"
PARAMETRIC_REVIEW_PROMPT = (
    REPO_ROOT / "prompts" / "workflows" / "review_revise_parametric_design_docs" / "review.md"
)
PARAMETRIC_FIX_PROMPT = (
    REPO_ROOT / "prompts" / "workflows" / "review_revise_parametric_design_docs" / "fix.md"
)


def _write_module(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


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


def test_effectful_match_arm_normalization_orc_compiles_with_shared_validation(tmp_path: Path) -> None:
    result = compile_stage3_module(
        WORKFLOWS / "effectful_match_arm_normalization.orc",
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

    assert result.lowered_workflows[0].typed_workflow.definition.name == "run-effectful-match-arm-normalization"
    assert [step["name"] for step in lowered["steps"]] == [
        "run-effectful-match-arm-normalization__attempt",
        "run-effectful-match-arm-normalization__match_attempt",
    ]
    assert lowered["steps"][0]["provider"] == "test-provider"
    assert lowered["steps"][1]["match"]["cases"]["COMPLETED"]["steps"][0]["provider"] == "test-provider"
    assert lowered["steps"][1]["match"]["cases"]["BLOCKED"]["steps"][0]["provider"] == "test-provider"


def test_effectful_let_star_normalization_orc_compiles_with_shared_validation(tmp_path: Path) -> None:
    result = compile_stage3_module(
        WORKFLOWS / "effectful_let_star_normalization.orc",
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

    assert result.lowered_workflows[0].typed_workflow.definition.name == "run-effectful-let-star-normalization"
    assert [step.get("provider") if "provider" in step else "match" for step in lowered["steps"]] == [
        "test-provider",
        "match",
        "test-provider",
    ]
    assert lowered["steps"][1]["match"]["cases"]["COMPLETED"]["steps"][0]["provider"] == "test-provider"
    assert lowered["steps"][1]["match"]["cases"]["BLOCKED"]["steps"][0]["provider"] == "test-provider"


def test_same_file_record_call_binding_orc_compiles_with_shared_validation(tmp_path: Path) -> None:
    result = compile_stage3_module(
        WORKFLOWS / "same_file_record_call_binding.orc",
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = {
        workflow.typed_workflow.definition.name: workflow.authored_mapping
        for workflow in result.lowered_workflows
    }

    assert set(lowered) == {"build-checks", "run-same-file-record-call-binding"}
    assert lowered["run-same-file-record-call-binding"]["steps"][0]["with"]["input__report"] == {
        "ref": "inputs.report_path"
    }


def test_review_revise_parametric_design_docs_example_validates_with_prompt_bindings(tmp_path: Path) -> None:
    assert PARAMETRIC_REVIEW_PROMPT.is_file()
    assert PARAMETRIC_FIX_PROMPT.is_file()

    design_root = tmp_path / "docs" / "design"
    design_root.mkdir(parents=True)
    for name in (
        "workflow_lisp_review_revise_stdlib_parametric_integration.md",
        "workflow_lisp_structural_parametric_constraints.md",
        "workflow_lisp_compile_time_parametric_specialization.md",
    ):
        (design_root / name).write_text(f"# {name}\n", encoding="utf-8")

    checks_report = (
        tmp_path
        / "artifacts"
        / "work"
        / "LISP-MIGRATION-PARITY-DRAIN"
        / "review-revise-parametric-design-docs-checks.md"
    )
    checks_report.parent.mkdir(parents=True)
    checks_report.write_text("# Review checks\n", encoding="utf-8")

    compile_stage3_module(
        PARAMETRIC_REVIEW_EXAMPLE,
        provider_externs={
            "providers.design-docs.review": "codex",
            "providers.design-docs.fix": "codex",
        },
        prompt_externs={
            "prompts.design-docs.review": PARAMETRIC_REVIEW_PROMPT.relative_to(REPO_ROOT).as_posix(),
            "prompts.design-docs.fix": PARAMETRIC_FIX_PROMPT.relative_to(REPO_ROOT).as_posix(),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )


def test_generic_defproc_workflow_body_compiles_to_validated_bundle(tmp_path: Path) -> None:
    build_module = importlib.import_module("orchestrator.workflow_lisp.build")
    request_cls = getattr(build_module, "FrontendBuildRequest")
    module_path = _write_module(
        tmp_path / "generic" / "module.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule generic/module)",
                "  (export entry)",
                "  (defrecord WorkflowInput",
                "    (report String))",
                "  (defproc apply-runner",
                "    :forall (T)",
                "    ((runner ProcRef[T -> T])",
                "     (value T))",
                "    -> T",
                "    :effects ()",
                "    :lowering inline",
                "    (runner value))",
                "  (defproc echo-input",
                "    ((value WorkflowInput))",
                "    -> WorkflowInput",
                "    :effects ()",
                "    :lowering inline",
                "    (record WorkflowInput",
                "      :report value.report))",
                "  (defworkflow entry",
                "    ((input WorkflowInput))",
                "    -> WorkflowInput",
                "    (apply-runner (proc-ref echo-input) input)))",
            ]
        )
        + "\n",
    )

    result = build_module.build_frontend_bundle(
        request_cls(
            source_path=module_path,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            provider_externs_path=Path("tests/fixtures/workflow_lisp/cli/providers.json"),
            prompt_externs_path=Path("tests/fixtures/workflow_lisp/cli/prompts.json"),
            imported_workflow_bundles_path=None,
            command_boundaries_path=Path("tests/fixtures/workflow_lisp/cli/commands.json"),
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )

    assert result.selected_workflow_name == "generic/module::entry"
    assert result.validated_bundle.surface.name == "generic/module::entry"
    assert result.validated_bundle.provenance.frontend_kind == "workflow_lisp"
    assert result.artifact_paths["source_map"].is_file()
