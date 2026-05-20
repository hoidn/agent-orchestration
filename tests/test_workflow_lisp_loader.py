"""Tests for loading Workflow Lisp modules through WorkflowLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from tests.workflow_bundle_helpers import thaw_surface_workflow


EXPR_FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "expression_validation"


def _fixture_path(name: str) -> Path:
    return EXPR_FIXTURES / name


def test_loader_loads_single_workflow_orc_module(tmp_path: Path) -> None:
    source_path = _fixture_path("valid_pathrel_contracts.orc")

    loaded = WorkflowLoader(tmp_path).load(source_path)
    surface = thaw_surface_workflow(loaded)

    assert surface["name"] == "run_path"
    assert surface["version"] == "2.14"
    assert surface["outputs"]["path"]["type"] == "relpath"
    assert surface["steps"][0]["name"] == "CommandResult"


def test_loader_rejects_orc_module_with_multiple_lowered_workflows(tmp_path: Path) -> None:
    source_path = _fixture_path("valid_provider_command_result_expressions.orc")

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(source_path)

    assert exc_info.value.exit_code == 2
    assert any(
        "Workflow Lisp module must lower to exactly one workflow for direct loading" in str(error.message)
        for error in exc_info.value.errors
    )
