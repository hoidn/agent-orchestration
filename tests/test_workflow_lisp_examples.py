from pathlib import Path

import importlib

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.compiler import compile_stage3_module as _compile_stage3_module
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
DESIGN_DOCS_REVIEW_EXAMPLE = WORKFLOWS / "review_revise_design_docs.orc"
DESIGN_DOCS_REVIEW_PROMPT = (
    REPO_ROOT / "prompts" / "workflows" / "review_revise_design_docs" / "review.md"
)
DESIGN_DOCS_FIX_PROMPT = (
    REPO_ROOT / "prompts" / "workflows" / "review_revise_design_docs" / "fix.md"
)


def compile_stage3_module(*args, **kwargs):
    kwargs.setdefault("lowering_route", "legacy")
    return _compile_stage3_module(*args, **kwargs)


def _write_module(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_kiss_backlog_item_orc_compiles_to_typed_phase_stack(tmp_path: Path) -> None:
    workflow_source = (WORKFLOWS / "kiss_backlog_item.orc").read_text(encoding="utf-8")
    assert "(import std/phase :only" in workflow_source
    assert ":review-provider" not in workflow_source
    assert ":fix-provider" not in workflow_source
    assert ":review-prompt" not in workflow_source
    assert ":fix-prompt" not in workflow_source
    assert ":returns ReviewLoopResult" not in workflow_source

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

    assert "kiss_backlog_item::run-backlog-item" in lowered_by_name
    lowered = lowered_by_name["kiss_backlog_item::run-backlog-item"]
    assert lowered["version"] == "2.14"
    assert "return__summary_path" in lowered["outputs"]

    def walk_steps(steps):
        for step in steps:
            yield step
            if "repeat_until" in step:
                yield from walk_steps(step["repeat_until"].get("steps", []))
            if "match" in step:
                for case in step["match"].get("cases", {}).values():
                    yield from walk_steps(case.get("steps", []))

    all_steps = [
        step
        for workflow in result.lowered_workflows
        for step in walk_steps(workflow.authored_mapping["steps"])
    ]
    assert sum(1 for step in all_steps if "repeat_until" in step) == 2
    assert {step.get("provider") for step in all_steps if step.get("provider")} == {
        "fake-plan",
        "fake-plan-review",
        "fake-plan-fix",
        "fake-implementation",
        "fake-implementation-review",
        "fake-implementation-fix",
    }


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


def test_review_revise_parametric_design_docs_example_remains_one_off_source_shape() -> None:
    assert PARAMETRIC_REVIEW_PROMPT.is_file()
    assert PARAMETRIC_FIX_PROMPT.is_file()

    workflow_source = PARAMETRIC_REVIEW_EXAMPLE.read_text(encoding="utf-8")
    assert "workflow_lisp_review_revise_stdlib_parametric_integration.md" in workflow_source
    assert "workflow_lisp_structural_parametric_constraints.md" in workflow_source
    assert "workflow_lisp_compile_time_parametric_specialization.md" in workflow_source


def test_review_revise_design_docs_example_validates_with_parameterized_context_docs(tmp_path: Path) -> None:
    assert DESIGN_DOCS_REVIEW_PROMPT.is_file()
    assert DESIGN_DOCS_FIX_PROMPT.is_file()

    workflow_source = DESIGN_DOCS_REVIEW_EXAMPLE.read_text(encoding="utf-8")
    assert "workflow_lisp_structural_parametric_constraints.md" not in workflow_source
    assert "workflow_lisp_compile_time_parametric_specialization.md" not in workflow_source
    assert "workflow_lisp_review_revise_stdlib_parametric_integration.md" not in workflow_source

    result = _compile_stage3_module(
        DESIGN_DOCS_REVIEW_EXAMPLE,
        provider_externs={
            "providers.design-docs.review": "codex",
            "providers.design-docs.fix": "codex",
        },
        prompt_externs={
            "prompts.design-docs.review": DESIGN_DOCS_REVIEW_PROMPT.relative_to(REPO_ROOT).as_posix(),
            "prompts.design-docs.fix": DESIGN_DOCS_FIX_PROMPT.relative_to(REPO_ROOT).as_posix(),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "review_revise_design_docs::review-revise-design-docs"
    )
    assert lowered.typed_workflow.definition.name == "review_revise_design_docs::review-revise-design-docs"
    assert lowered.private_artifact_ids == ("context_docs",)
    context_docs_contract = lowered.authored_mapping["inputs"]["context_docs"]
    assert context_docs_contract == {
        "kind": "collection",
        "type": "list",
        "items": {
            "type": "relpath",
            "under": "docs/design",
            "must_exist_target": True,
        },
    }
    assert "pointer" not in lowered.authored_mapping["artifacts"]["context_docs"]
    assert "pointer" not in lowered.authored_mapping["artifacts"]["review_focus"]


def test_review_revise_design_docs_runtime_private_collection_lane(tmp_path: Path) -> None:
    result = _compile_stage3_module(
        DESIGN_DOCS_REVIEW_EXAMPLE,
        provider_externs={
            "providers.design-docs.review": "codex",
            "providers.design-docs.fix": "codex",
        },
        prompt_externs={
            "prompts.design-docs.review": DESIGN_DOCS_REVIEW_PROMPT.relative_to(REPO_ROOT).as_posix(),
            "prompts.design-docs.fix": DESIGN_DOCS_FIX_PROMPT.relative_to(REPO_ROOT).as_posix(),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    workflow_name = "review_revise_design_docs::review-revise-design-docs"
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == workflow_name
    )
    lowered_mapping = lowered.authored_mapping
    bundle = result.validated_bundles[workflow_name]
    (tmp_path / "workflow.yaml").write_text("version: '2.14'\nsteps: []\n", encoding="utf-8")
    state_manager = StateManager(workspace=tmp_path, run_id="private-lane-runtime")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager)

    state = {
        "artifact_versions": {
            "target_doc": [{
                "version": 1,
                "value": "docs/design/target.md",
                "producer": "root.seed",
                "producer_name": "Seed",
                "step_index": 0,
            }],
            "review_focus": [{
                "version": 1,
                "value": "Review the runtime migration foundation.",
                "producer": "root.seed",
                "producer_name": "Seed",
                "step_index": 0,
            }],
            "checks_report": [{
                "version": 1,
                "value": "artifacts/work/checks.md",
                "producer": "root.seed",
                "producer_name": "Seed",
                "step_index": 0,
            }],
            "review_report_target_path": [{
                "version": 1,
                "value": "artifacts/review/review.md",
                "producer": "root.seed",
                "producer_name": "Seed",
                "step_index": 0,
            }],
            "revision_report_target_path": [{
                "version": 1,
                "value": "artifacts/review/revision.md",
                "producer": "root.seed",
                "producer_name": "Seed",
                "step_index": 0,
            }],
            "items_path": [{
                "version": 1,
                "value": "artifacts/work/findings.json",
                "producer": "root.seed",
                "producer_name": "Seed",
                "step_index": 0,
            }],
        },
        "private_artifact_versions": {
            "context_docs": [{
                "version": 1,
                "value": ["state-layout.md"],
                "producer": "root.collect_context",
                "producer_name": "CollectContext",
                "step_index": 0,
                "catalog_ref": "context_docs",
            }],
        },
    }
    (tmp_path / "docs" / "design").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "design" / "state-layout.md").write_text("# state layout\n", encoding="utf-8")

    def _walk_steps(steps):
        for step in steps:
            yield step
            if "repeat_until" in step:
                yield from _walk_steps(step["repeat_until"].get("steps", []))
            if "match" in step:
                for case in step["match"].get("cases", {}).values():
                    yield from _walk_steps(case.get("steps", []))
            if "for_each" in step:
                yield from _walk_steps(step["for_each"].get("steps", []))

    review_step = next(
        step
        for step in _walk_steps(lowered_mapping["steps"])
        if step.get("provider") == "codex"
        and any(consume.get("artifact") == "context_docs" for consume in step.get("consumes", []))
    )

    error = executor.dataflow_manager.enforce_consumes_contract(
        review_step,
        review_step["name"],
        state,
        runtime_step_id=executor._step_id(review_step),
    )

    assert error is None
    assert "context_docs" not in state["artifact_versions"]
    assert state["artifact_versions"]["target_doc"][0]["value"] == "docs/design/target.md"
    assert state["_resolved_consumes"][executor._step_id(review_step)]["context_docs"] == [
        "docs/design/state-layout.md",
    ]


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
            lowering_route="legacy",
        )
    )

    assert result.selected_workflow_name == "generic/module::entry"
    assert result.validated_bundle.surface.name == "generic/module::entry"
    assert result.validated_bundle.provenance.frontend_kind == "workflow_lisp"
    assert result.artifact_paths["source_map"].is_file()
