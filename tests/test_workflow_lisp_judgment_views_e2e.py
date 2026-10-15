"""Deterministic runtime acceptance for the Q4 judgment-panel consumer."""

from __future__ import annotations

from pathlib import Path
import re




REPO_ROOT = Path(__file__).resolve().parents[1]
RETIRED_EXAMPLES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "retired_examples"
PANEL = RETIRED_EXAMPLES / "review_revise_design_docs_judgment_panel.orc"
PANEL_INPUTS = (
    RETIRED_EXAMPLES
    / "inputs"
    / "review_revise_design_docs_judgment_panel"
)
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "judgment_views"
    / "review_revise_design_docs_judgment_panel_case.json"
)
ENTRY = (
    "review_revise_design_docs_judgment_panel"
    "::review-revise-design-docs-judgment-panel"
)
SYNTHESIS_PROMPT = Path(
    "prompts/workflows/review_revise_design_docs/synthesize.md"
)
REPO_SYNTHESIS_PROMPT = (
    REPO_ROOT
    / "prompts"
    / "workflows"
    / "review_revise_design_docs"
    / "synthesize.md"
)
FIX_PROMPT = "prompts/workflows/review_revise_design_docs/fix.md"
SYNTHESIS_PATH = "artifacts/review/q4-panel/synthesis.md"
_TYPED_INPUT_HEADING = re.compile(
    r"^## Typed Prompt Input: (?P<name>[A-Za-z_][A-Za-z0-9_]*)$",
    re.MULTILINE,
)
