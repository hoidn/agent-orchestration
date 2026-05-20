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


def test_loader_loads_selected_orc_workflow_fragment_for_multi_workflow_module(tmp_path: Path) -> None:
    source_path = _fixture_path("valid_provider_command_result_expressions.orc")

    loaded = WorkflowLoader(tmp_path).load(f"{source_path}#run_checks")
    surface = thaw_surface_workflow(loaded)

    assert surface["name"] == "run_checks"
    assert surface["version"] == "2.14"
    assert surface["steps"][0]["name"] == "CommandResult"


def test_loader_rejects_unknown_orc_workflow_fragment_for_multi_workflow_module(tmp_path: Path) -> None:
    source_path = _fixture_path("valid_provider_command_result_expressions.orc")

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(f"{source_path}#missing_workflow")

    assert exc_info.value.exit_code == 2
    assert any(
        "Workflow Lisp module fragment references unknown workflow 'missing_workflow'"
        in str(error.message)
        for error in exc_info.value.errors
    )


def test_loader_orc_compile_errors_include_generated_node_and_form_context(tmp_path: Path) -> None:
    source_path = _fixture_path("invalid_variant_field_unproved.orc")

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(source_path)

    assert any(
        "generated_node=bad.field.execution_report" in str(error.message)
        and "form=field.access" in str(error.message)
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


def test_loader_reports_module_not_found_for_missing_orc_import(tmp_path: Path) -> None:
    wrapper = tmp_path / "wrapper.yaml"
    wrapper.write_text(
        """
version: "2.14"
name: wrapper
imports:
  missing: "./missing_module.orc#run_phase"
inputs:
  prompt:
    kind: scalar
    type: string
outputs:
  status:
    kind: scalar
    type: string
    from:
      ref: root.steps.CallMissing.artifacts.status
steps:
  - name: CallMissing
    id: call_missing
    call: missing
    with:
      inputs__prompt:
        ref: inputs.prompt
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(wrapper)

    assert any("[module_not_found]" in str(error.message) for error in exc_info.value.errors)


def test_loader_reports_module_cycle_for_cyclic_orc_fragment_imports(tmp_path: Path) -> None:
    source_path = tmp_path / "cyclic_module.orc"
    source_path.write_text(
        """
(defmodule cyclic.module
  (:language workflow-lisp "0.1")
  (:target-dsl "2.14")

  (export
    run_a
    run_b)

  (defworkflow run_a ((prompt String)) -> String
    (call run_b :prompt prompt))

  (defworkflow run_b ((prompt String)) -> String
    (call run_a :prompt prompt)))
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(f"{source_path}#run_a")

    messages = [str(error.message) for error in exc_info.value.errors]
    assert any("[module_cycle]" in message for message in messages)
    assert any("cyclic_module.orc#run_a" in message for message in messages)


def test_loader_records_frontend_source_map_for_orc_workflow_fragment(tmp_path: Path) -> None:
    source_path = _fixture_path("valid_provider_command_result_expressions.orc")

    loaded = WorkflowLoader(tmp_path).load(f"{source_path}#run_checks")
    frontend_source_map = loaded.provenance.frontend_source_map

    assert "run_checks.result" in frontend_source_map
    result_span = frontend_source_map["run_checks.result"]
    assert getattr(result_span, "source_file", None) == str(source_path)
    assert getattr(result_span, "line_start", 0) > 0


def test_loader_leaves_frontend_source_map_empty_for_yaml_workflows(tmp_path: Path) -> None:
    workflow_path = tmp_path / "simple.yaml"
    workflow_path.write_text(
        """
version: "2.14"
name: simple
inputs:
  report_path:
    type: relpath
outputs:
  path:
    type: relpath
    from:
      ref: root.steps.CommandResult.artifacts.path
steps:
  - name: CommandResult
    command:
      - python
      - scripts/emit_report.py
      - ${inputs.report_path}
    output_bundle:
      path: state/run_path_result.json
      fields:
        - name: path
          json_pointer: /path
          type: relpath
""".strip()
        + "\n",
        encoding="utf-8",
    )

    loaded = WorkflowLoader(tmp_path).load(workflow_path)

    assert loaded.provenance.frontend_source_map == {}
