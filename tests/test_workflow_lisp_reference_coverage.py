"""The language reference has an entry for every form and names only codes the compiler has."""

import re
from pathlib import Path

from orchestrator.contracts.closed_program.targets import CURRENT_TARGET_DSL_VERSION
from orchestrator.workflow_lisp.form_registry import RETIRED_FORMS, registered_form_heads

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "design" / "workflow_lisp_frontend_specification.md"

# Backticked snake_case names in the reference that are not diagnostics. May only shrink.
NOT_DIAGNOSTICS = {
    "call_policy_bindings": "provider template field (22.4)",
    "introduced_by_expansion_id": "syntax provenance field (section 6)",
    "materialize_view": "removed runtime step family (18.1, 20)",
    "materialized_value_view": "removed generated-path role (18.1)",
    "on_exhausted": "loop step field (13.1)",
    "pure_projection": "stale: no such step in the code; still named in section 12 (T4d)",
    "requires_variant": "runtime guard field (8.5, 11)",
    "target_param": "call-policy binding field (22.4)",
}

# Codes the reference names that `orchestrator/` no longer has; their sentences are being
# removed or corrected. May only shrink; empty since T4b and T4c.
CODES_NOT_IN_CODE: dict[str, str] = {}


def _language_parts() -> str:
    text = SPEC.read_text(encoding="utf-8")
    return text[text.index("\n## Part I.") : text.index("\n## Part VIII.")]


def _entries(text: str) -> set[str]:
    """Heads backticked in a heading, or in the first cell of a Form Index or Removed forms row."""
    index = text[text.index("\n## Form Index") : text.index("\n## 4. ")]
    lines = [line for line in text.splitlines() if line.startswith("#")]
    lines += [line.split("|")[1] for line in index.splitlines() if line.startswith("| ")]
    return {name for line in lines for name in re.findall(r"`([^`\s]+)`", line)}


def _orchestrator_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "orchestrator").rglob("*.py"))


def test_every_registered_and_retired_form_has_an_entry() -> None:
    heads = set(registered_form_heads(target_dsl_version=CURRENT_TARGET_DSL_VERSION)) | set(RETIRED_FORMS)

    assert sorted(heads - _entries(_language_parts())) == []


def test_a_table_row_outside_the_form_index_is_not_an_entry() -> None:
    text = "\n## Form Index\n| Head |\n| `cond` | x |\n\n## 4. Files\n| `print` | incidental |\n### 9 `if`\n"

    assert _entries(text) == {"cond", "if"}


def test_every_named_code_is_a_string_literal_in_the_code() -> None:
    text = _language_parts()
    named = set(re.findall(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`", text))
    source = _orchestrator_source()
    missing = {name for name in named if f'"{name}"' not in source and f"'{name}'" not in source}

    listed = set(NOT_DIAGNOSTICS) | set(CODES_NOT_IN_CODE)

    assert sorted(missing - listed) == []
    assert sorted(listed - missing) == []  # a listed name still in the reference and still absent
