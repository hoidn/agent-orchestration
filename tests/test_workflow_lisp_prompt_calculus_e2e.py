"""Real-consumer Q2 acceptance coverage with frozen target-2.20 Q1 controls."""

from __future__ import annotations

from pathlib import Path




REPO_ROOT = Path(__file__).resolve().parents[1]
RETIRED_EXAMPLES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "retired_examples"
CONSUMER = RETIRED_EXAMPLES / "review_revise_design_docs.orc"
JUDGMENT_PANEL = RETIRED_EXAMPLES / "review_revise_design_docs_judgment_panel.orc"
JUDGMENT_PANEL_INPUTS = (
    RETIRED_EXAMPLES
    / "inputs"
    / "review_revise_design_docs_judgment_panel"
)
JUDGMENT_PANEL_SYNTHESIS_PROMPT = (
    REPO_ROOT
    / "prompts"
    / "workflows"
    / "review_revise_design_docs"
    / "synthesize.md"
)
Q1_RESUME_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "prompt_q1_target_2_20_resume.orc"
)
Q2_COMPOSED_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "prompt_calculus"
    / "review_revise_design_docs_target_2_21.orc"
)
CONSUMER_INPUTS = (
    RETIRED_EXAMPLES
    / "inputs"
    / "review_revise_design_docs"
)
LEGACY_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "prompt_calculus"
    / "review_revise_design_docs_pre_migration"
)
FIX_PROMPT = "prompts/workflows/review_revise_design_docs/fix.md"
PROVIDERS = {
    "providers.design-docs.review": "codex",
    "providers.design-docs.fix": "codex_gpt55",
}
FROZEN_Q1_FRAGMENT_IDENTITY = (
    "sha256:306ceeaa45d96de5f7a90387d8958e9d6348eb79b2cec8f19a6874c1fa78b5e7"
)
FROZEN_Q1_CARRIER_SHA256 = (
    "a8081747d726424be0b6858d2d9cfec47b1dcf123b12aa91c1c8bd656440cf8f"
)
FROZEN_Q2_SOURCE_SHA256 = (
    "157211801379b7290c7881d8e37b82da14a3ee66eb0fdfd135a4dba1277fb743"
)
PRE_Q4_SOURCE_SIZE = 8_079
Q4_SOURCE_SIZE = 8_149
PRE_Q4_SOURCE_SHA256 = (
    "89176c15dcaf29b5212441ad4776593d919880784fe0f531c9034b8a177640d7"
)
Q4_SOURCE_SHA256 = (
    "8784501577c4f162f584a2ae17d1644a6bc4ea0c8bfbd18cdb0c1b7fd24a0598"
)
PRE_Q4_EXPORT_DECLARATION = b"  (export review-revise-design-docs)\n"
Q4_EXPORT_DECLARATION = (
    b"  (export review-revise-design-docs DesignDocPath "
    b"ReviewReportTargetPath WorkReportPath review-design-doc)\n"
)




























































def test_prompt_core_generic_machinery_contains_no_consumer_identity() -> None:
    forbidden = (
        "review_revise_design_docs",
        "review-design-docs",
        "review-design-doc",
        "providers.design-docs.review",
        "prompts.design-docs.review",
        "prompts/workflows/review_revise_design_docs/review.md",
        "review_report_target_path",
        "prompt_q1_target_2_20_resume",
    )
    generic_roots = (
        REPO_ROOT / "orchestrator" / "contracts",
        REPO_ROOT / "orchestrator" / "workflow",
        REPO_ROOT / "orchestrator" / "workflow_lisp",
        REPO_ROOT / "orchestrator" / "providers",
    )
    offenders: list[str] = []
    for root in generic_roots:
        for path in sorted(root.rglob("*.py")):
            content = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in content:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{token}"
                    )
    assert offenders == []
