from pathlib import Path
import hashlib

import json



REPO_ROOT = Path(__file__).resolve().parents[1]
RETIRED_EXAMPLES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "retired_examples"
PARAMETRIC_REVIEW_EXAMPLE = RETIRED_EXAMPLES / "review_revise_parametric_design_docs.orc"
PARAMETRIC_REVIEW_PROMPT = (
    REPO_ROOT / "prompts" / "workflows" / "review_revise_parametric_design_docs" / "review.md"
)
PARAMETRIC_FIX_PROMPT = (
    REPO_ROOT / "prompts" / "workflows" / "review_revise_parametric_design_docs" / "fix.md"
)
DESIGN_DOCS_REVIEW_EXAMPLE = RETIRED_EXAMPLES / "review_revise_design_docs.orc"
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
    RETIRED_EXAMPLES / "review_revise_design_docs_judgment_panel.orc"
)
DESIGN_DOCS_JUDGMENT_PANEL_INPUTS = (
    RETIRED_EXAMPLES
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




def test_kiss_backlog_item_historical_source_preserves_phase_shape(tmp_path: Path) -> None:
    workflow_source = (RETIRED_EXAMPLES / "kiss_backlog_item.orc").read_text(encoding="utf-8")
    assert "(import std/phase :only" in workflow_source
    assert ":review-provider" not in workflow_source
    assert ":fix-provider" not in workflow_source
    assert ":review-prompt" not in workflow_source
    assert ":fix-prompt" not in workflow_source
    assert ":returns ReviewLoopResult" not in workflow_source

    assert hashlib.sha256((RETIRED_EXAMPLES / "kiss_backlog_item.orc").read_bytes()).hexdigest() == "8a0c73b37207b759c5c8f012d623b439f1316b95cda562d5d659918cf946d698"














def test_review_revise_parametric_design_docs_example_remains_one_off_source_shape() -> None:
    assert PARAMETRIC_REVIEW_PROMPT.is_file()
    assert PARAMETRIC_FIX_PROMPT.is_file()

    workflow_source = PARAMETRIC_REVIEW_EXAMPLE.read_text(encoding="utf-8")
    assert "workflow_lisp_review_revise_stdlib_parametric_integration.md" in workflow_source
    assert "workflow_lisp_structural_parametric_constraints.md" in workflow_source
    assert "workflow_lisp_compile_time_parametric_specialization.md" in workflow_source


def test_review_revise_design_docs_historical_source_preserves_parameterized_context_docs(tmp_path: Path) -> None:
    assert not DESIGN_DOCS_REVIEW_PROMPT.exists()
    assert DESIGN_DOCS_FIX_PROMPT.is_file()

    workflow_source = DESIGN_DOCS_REVIEW_EXAMPLE.read_text(encoding="utf-8")
    assert "workflow_lisp_structural_parametric_constraints.md" not in workflow_source
    assert "workflow_lisp_compile_time_parametric_specialization.md" not in workflow_source
    assert "workflow_lisp_review_revise_stdlib_parametric_integration.md" not in workflow_source

    assert '(review_report_target_path :path :out ReviewReportTargetPath)' in workflow_source
    assert '-> ReviewDecision' in workflow_source
    assert hashlib.sha256(DESIGN_DOCS_REVIEW_EXAMPLE.read_bytes()).hexdigest() == "8784501577c4f162f584a2ae17d1644a6bc4ea0c8bfbd18cdb0c1b7fd24a0598"



def test_review_revise_design_docs_historical_exports_and_importer_are_preserved() -> None:
    source = DESIGN_DOCS_REVIEW_EXAMPLE.read_text()
    assert '(export review-revise-design-docs DesignDocPath ReviewReportTargetPath WorkReportPath review-design-doc)' in source
    importer = DESIGN_DOCS_EXPORT_IMPORT_FIXTURE.read_text()
    assert '(import review_revise_design_docs :only' in importer
    assert hashlib.sha256(DESIGN_DOCS_EXPORT_IMPORT_FIXTURE.read_bytes()).hexdigest() == "55c64417dd8de3a02df98aec3b122417e6eb8abf9defe58b8abac08aad56480d"


def test_review_revise_design_docs_historical_judgment_panel_keeps_assets_and_lens_contract(
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

    assert hashlib.sha256(DESIGN_DOCS_JUDGMENT_PANEL_EXAMPLE.read_bytes()).hexdigest() == "f119326c7fa45d8ad5ffb60ea4d674395cf6212335b534d37479ae4d7727f8a6"
