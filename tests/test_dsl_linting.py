"""Tests for advisory DSL linting and normalization hints."""


import pytest

from orchestrator.workflow.linting import lint_workflow


def test_lint_requires_loaded_workflow_bundle() -> None:
    with pytest.raises(TypeError, match="LoadedWorkflowBundle"):
        lint_workflow({"steps": []})
