"""Tests for loading Workflow Lisp modules through WorkflowLoader."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from tests.workflow_bundle_helpers import thaw_surface_workflow


EXPR_FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "expression_validation"
DEFINITION_FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "definitions"


def _fixture_path(name: str) -> Path:
    return EXPR_FIXTURES / name


def _definition_fixture_path(name: str) -> Path:
    return DEFINITION_FIXTURES / name


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


def test_loader_resolves_orc_workflow_fragment_imports_for_defmodule_closure(tmp_path: Path) -> None:
    module_source = _definition_fixture_path("valid_module_exported_callable_closure.orc")
    module_copy = tmp_path / module_source.name
    module_copy.write_text(module_source.read_text(encoding="utf-8"), encoding="utf-8")

    wrapper = tmp_path / "wrapper.yaml"
    wrapper.write_text(
        """
version: "2.14"
name: wrapper
imports:
  run_public: "./valid_module_exported_callable_closure.orc#run_public"
inputs:
  prompt:
    kind: scalar
    type: string
outputs:
  status:
    kind: scalar
    type: string
    from:
      ref: root.steps.CallResult.artifacts.status
steps:
  - name: CallResult
    id: call_result
    call: run_public
    with:
      inputs__prompt:
        ref: inputs.prompt
""".strip()
        + "\n",
        encoding="utf-8",
    )

    loaded = WorkflowLoader(tmp_path).load(wrapper)
    imported_root = loaded.imports["run_public"]
    imported_private = imported_root.imports["private_helper"]
    imported_leaf = imported_private.imports["build_status"]

    assert imported_root.surface.name == "run_public"
    assert imported_private.surface.name == "private_helper"
    assert imported_leaf.surface.name == "build_status"
