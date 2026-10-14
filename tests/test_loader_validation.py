"""Tests for loader DSL validation per specs/dsl.md and acceptance tests."""

import ast
from pathlib import Path
import re

import pytest


def _resume_projection_integrity_module_ast() -> ast.Module:
    module_path = (
        Path(__file__).parents[1]
        / "orchestrator"
        / "workflow"
        / "resume_projection_integrity.py"
    )
    return ast.parse(
        module_path.read_text(encoding="utf-8"),
        filename=str(module_path),
    )


def _receipt_or_persisted_audit_cache_findings(
    tree: ast.AST,
) -> tuple[str, ...]:
    findings: set[str] = set()

    def record(kind: str, value: str | None) -> None:
        if not value:
            return
        lowered = value.lower()
        words = set(re.findall(r"[a-z0-9]+", lowered))
        is_receipt = "receipt" in lowered
        is_projection_audit_cache = "cache" in words and (
            "audit" in words
            or {"resume", "projection"}.issubset(words)
            or {"projection", "integrity"}.issubset(words)
        )
        if is_receipt or is_projection_audit_cache:
            findings.add(f"{kind}:{value}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            record("identifier", node.id)
        elif isinstance(node, ast.Attribute):
            record("attribute", node.attr)
        elif isinstance(node, ast.arg):
            record("argument", node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            record("definition", node.name)
        elif isinstance(node, ast.alias):
            record("import", node.name)
            record("import-alias", node.asname)
        elif isinstance(node, ast.keyword):
            record("keyword", node.arg)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) and isinstance(
                node.slice.value,
                str,
            ):
                record("key", node.slice.value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            record("string", node.value)

    return tuple(sorted(findings))


@pytest.mark.parametrize(
    ("source", "expected_finding"),
    (
        pytest.param(
            "projection_audit_receipt = None",
            "projection_audit_receipt",
            id="assignment-target",
        ),
        pytest.param(
            "def audit(state):\n    return state.audit_receipt\n",
            "audit_receipt",
            id="attribute",
        ),
        pytest.param(
            "def audit(state):\n    return state['persisted_audit_cache']\n",
            "persisted_audit_cache",
            id="subscript-key",
        ),
        pytest.param(
            "CACHE_KIND = 'resume_projection_integrity_cache'",
            "resume_projection_integrity_cache",
            id="relevant-string-constant",
        ),
    ),
)
def test_resume_projection_receipt_cache_guard_rejects_mutation_snippets(
    source: str,
    expected_finding: str,
) -> None:
    findings = _receipt_or_persisted_audit_cache_findings(ast.parse(source))

    assert any(expected_finding in finding for finding in findings)


def test_resume_projection_receipt_cache_guard_allows_generic_cache_symbols() -> None:
    tree = ast.parse(
        "@cache\n"
        "def classify(cache_key='cache miss'):\n"
        "    local_cache = {'result': cache_key}\n"
        "    return local_cache['result']\n"
    )

    assert _receipt_or_persisted_audit_cache_findings(tree) == ()


def test_resume_projection_integrity_module_has_no_receipt_or_persisted_audit_cache() -> None:
    tree = _resume_projection_integrity_module_ast()

    assert _receipt_or_persisted_audit_cache_findings(tree) == ()
