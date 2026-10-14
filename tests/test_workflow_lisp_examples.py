from pathlib import Path

import json

from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    compile_stage3_module as _compile_stage3_module,
)


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
JUDGMENT_VIEWS_FIXTURES = (
    REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "judgment_views"
)
WORKFLOW_LISP_FIXTURES = JUDGMENT_VIEWS_FIXTURES.parent
DESIGN_DOCS_EXPORT_IMPORT_FIXTURE = (
    JUDGMENT_VIEWS_FIXTURES
    / "review_revise_design_docs_export_import.orc"
)
FROZEN_DESIGN_DOCS_TARGET_2_21_CONTROL = (
    WORKFLOW_LISP_FIXTURES
    / "prompt_calculus"
    / "review_revise_design_docs_target_2_21.orc"
)
DESIGN_DOCS_JUDGMENT_PANEL_EXAMPLE = (
    WORKFLOWS / "review_revise_design_docs_judgment_panel.orc"
)
DESIGN_DOCS_JUDGMENT_PANEL_INPUTS = (
    WORKFLOWS
    / "inputs"
    / "review_revise_design_docs_judgment_panel"
)
DESIGN_DOCS_JUDGMENT_PANEL_SYNTHESIS_PROMPT = (
    REPO_ROOT
    / "prompts"
    / "workflows"
    / "review_revise_design_docs"
    / "synthesize.md"
)


def compile_stage3_module(*args, **kwargs):
    kwargs.setdefault("lowering_route", "legacy")
    return _compile_stage3_module(*args, **kwargs)




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














def test_review_revise_parametric_design_docs_example_remains_one_off_source_shape() -> None:
    assert PARAMETRIC_REVIEW_PROMPT.is_file()
    assert PARAMETRIC_FIX_PROMPT.is_file()

    workflow_source = PARAMETRIC_REVIEW_EXAMPLE.read_text(encoding="utf-8")
    assert "workflow_lisp_review_revise_stdlib_parametric_integration.md" in workflow_source
    assert "workflow_lisp_structural_parametric_constraints.md" in workflow_source
    assert "workflow_lisp_compile_time_parametric_specialization.md" in workflow_source


def test_review_revise_design_docs_example_validates_with_parameterized_context_docs(tmp_path: Path) -> None:
    assert not DESIGN_DOCS_REVIEW_PROMPT.exists()
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
            "prompts.design-docs.fix": DESIGN_DOCS_FIX_PROMPT.relative_to(REPO_ROOT).as_posix(),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.module.target_dsl_version == "2.23"
    review_prompt = result.prompt_catalog.resolve("review-design-doc")
    review_output_slot = next(
        slot
        for slot in review_prompt.slots
        if slot.declaration.name == "review_report_target_path"
    )
    assert review_output_slot.declaration.kind.value == "path"
    assert review_output_slot.declaration.output_role.value == (
        "required_string_file"
    )
    assert review_output_slot.declaration.refinement_type_name == (
        "ReviewReportTargetPath"
    )
    assert review_prompt.declaration.return_spec is not None
    assert review_prompt.declaration.return_spec.type_name == "ReviewDecision"



def test_review_revise_design_docs_exports_compile_for_same_target_importer(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        DESIGN_DOCS_EXPORT_IMPORT_FIXTURE,
        source_roots=(WORKFLOW_LISP_FIXTURES, WORKFLOWS),
        provider_externs={
            "providers.design-docs.review": "codex",
            "providers.design-docs.fix": "codex",
        },
        prompt_externs={
            "prompts.design-docs.fix": DESIGN_DOCS_FIX_PROMPT.relative_to(
                REPO_ROOT
            ).as_posix(),
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    imported = result.compiled_results_by_name["review_revise_design_docs"]
    assert result.entry_result.module.target_dsl_version == "2.23"
    assert imported.module.target_dsl_version == "2.23"
    assert tuple(imported.module.exports) == (
        "review-revise-design-docs",
        "DesignDocPath",
        "ReviewReportTargetPath",
        "WorkReportPath",
        "review-design-doc",
    )
    assert (
        result.graph.modules_by_name["review_revise_design_docs"].path
        == DESIGN_DOCS_REVIEW_EXAMPLE
    )
    assert FROZEN_DESIGN_DOCS_TARGET_2_21_CONTROL not in {
        source.path for source in result.graph.modules_by_name.values()
    }


def test_review_revise_design_docs_judgment_panel_compiles_from_current_owner(
    tmp_path: Path,
) -> None:
    providers_path = (
        DESIGN_DOCS_JUDGMENT_PANEL_INPUTS / "providers.json"
    )
    prompts_path = (
        DESIGN_DOCS_JUDGMENT_PANEL_INPUTS / "prompts.json"
    )
    inputs_path = (
        DESIGN_DOCS_JUDGMENT_PANEL_INPUTS / "panel_inputs.json"
    )
    assert DESIGN_DOCS_JUDGMENT_PANEL_EXAMPLE.is_file()
    assert providers_path.is_file()
    assert prompts_path.is_file()
    assert inputs_path.is_file()
    assert DESIGN_DOCS_JUDGMENT_PANEL_SYNTHESIS_PROMPT.is_file()
    provider_externs = json.loads(
        providers_path.read_text(encoding="utf-8")
    )
    prompt_externs = json.loads(
        prompts_path.read_text(encoding="utf-8")
    )
    checked_inputs = json.loads(
        inputs_path.read_text(encoding="utf-8")
    )
    lens_ids = checked_inputs["lens_ids"]
    assert len(lens_ids) == 3
    assert len(set(lens_ids)) == len(lens_ids)
    assert all(
        isinstance(lens, str)
        and lens
        and not lens.startswith("/")
        and ".." not in lens.split("/")
        for lens in lens_ids
    )

    result = compile_stage3_entrypoint(
        DESIGN_DOCS_JUDGMENT_PANEL_EXAMPLE,
        source_roots=(WORKFLOWS,),
        entry_workflow=(
            "review-revise-design-docs-judgment-panel"
        ),
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )

    imported = result.compiled_results_by_name[
        "review_revise_design_docs"
    ]
    assert result.entry_result.module.target_dsl_version == "2.23"
    assert imported.module.target_dsl_version == "2.23"
    assert (
        result.graph.modules_by_name[
            "review_revise_design_docs"
        ].path
        == DESIGN_DOCS_REVIEW_EXAMPLE
    )
    assert FROZEN_DESIGN_DOCS_TARGET_2_21_CONTROL not in {
        source.path for source in result.graph.modules_by_name.values()
    }
