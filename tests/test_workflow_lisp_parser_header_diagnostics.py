"""Focused parser diagnostics tests for module-header generated node ids."""

from __future__ import annotations

import importlib

import pytest


def _parser_module():
    return importlib.import_module("orchestrator.workflow_lisp.parser")


def _diagnostic_from_error(error: BaseException):
    diagnostic = getattr(error, "diagnostic", None)
    assert diagnostic is not None
    return diagnostic


@pytest.mark.parametrize(
    ("source_text", "expected_code", "expected_generated_core_node_id"),
    [
        (
            """
(workflow-lisp
  (:language \"0.1\")
  (:language \"0.1\")
  (:target-dsl \"2.14\"))
""",
            "frontend_parse_error",
            "module.header.language",
        ),
        (
            """
(workflow-lisp
  (:language \"0.1\"))
""",
            "frontend_parse_error",
            "module.header.target_dsl",
        ),
        (
            """
(workflow-lisp
  (:language \"0.2\")
  (:target-dsl \"2.14\"))
""",
            "language_version_unsupported",
            "module.header.language",
        ),
        (
            """
(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.15\"))
""",
            "target_dsl_unsupported",
            "module.header.target_dsl",
        ),
    ],
)
def test_parse_workflow_module_text_assigns_generated_node_ids_for_header_diagnostics(
    source_text: str,
    expected_code: str,
    expected_generated_core_node_id: str,
) -> None:
    parser = _parser_module()

    with pytest.raises(Exception) as exc_info:
        parser.parse_workflow_module_text(
            source_text,
            source_path="inline_header_node_ids.orc",
        )

    diagnostic = _diagnostic_from_error(exc_info.value)
    assert diagnostic.code == expected_code
    assert diagnostic.enclosing_form_name == "workflow-lisp"
    assert diagnostic.generated_core_node_id == expected_generated_core_node_id
