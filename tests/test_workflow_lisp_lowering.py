"""Tests for Workflow Lisp MVP lowering to core workflow shape."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow_lisp.parser import WorkflowLispSyntaxError


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "expression_validation"
DEFINITION_FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "definitions"


def _fixture_path(name: str) -> Path:
    return FIXTURES / name


def _definition_fixture_path(name: str) -> Path:
    return DEFINITION_FIXTURES / name


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def _lowering_module():
    return importlib.import_module("orchestrator.workflow_lisp.lowering")


def test_lower_compiled_module_emits_provider_variant_output_contract(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_provider_command_result_expressions.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    provider_workflow = lowered["execute_attempt"]
    provider_step = provider_workflow["steps"][0]

    assert provider_workflow["version"] == "2.14"
    assert provider_workflow["outputs"] == {
        "attempt_variant": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
            "from": {"ref": "root.steps.ProviderResult.artifacts.attempt_variant"},
        },
    }
    assert provider_step["provider"] == "${inputs.execute_provider}"
    assert provider_step["input_file"] == "${inputs.execute_prompt}"
    assert provider_step["provider_params"]["workflow_lisp_inputs"] == ["${inputs.design_path}"]
    assert provider_step["variant_output"]["discriminant"] == {
        "name": "attempt_variant",
        "json_pointer": "/attempt_variant",
        "type": "enum",
        "allowed": ["COMPLETED", "BLOCKED"],
    }

    path = tmp_path / "execute_attempt.yaml"
    path.write_text(yaml.safe_dump(provider_workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "execute_attempt"


def test_lower_compiled_module_lowers_with_phase_wrapped_provider_result(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_with_phase_provider_result.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["execute_attempt"]
    step = workflow["steps"][0]

    assert workflow["outputs"] == {
        "attempt_variant": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
            "from": {"ref": "root.steps.ProviderResult.artifacts.attempt_variant"},
        },
    }
    assert step["provider"] == "${inputs.execute_provider}"
    assert step["input_file"] == "${inputs.execute_prompt}"
    assert step["provider_params"]["workflow_lisp_inputs"] == ["${inputs.phase_ctx}"]

    path = tmp_path / "execute_attempt.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "execute_attempt"


def test_lower_compiled_module_emits_command_output_bundle_contract(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_provider_command_result_expressions.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    command_workflow = lowered["run_checks"]
    command_step = command_workflow["steps"][0]

    assert command_workflow["outputs"] == {
        "path": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.CommandResult.artifacts.path"},
        },
        "status": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.CommandResult.artifacts.status"},
        },
    }
    assert command_step["command"] == ["python", "scripts/checks.py", "${inputs.design_path}"]
    assert command_step["output_bundle"] == {
        "path": "state/run_checks_result.json",
        "fields": [
            {"name": "path", "json_pointer": "/path", "type": "string"},
            {"name": "status", "json_pointer": "/status", "type": "string"},
        ],
    }

    path = tmp_path / "run_checks.yaml"
    path.write_text(yaml.safe_dump(command_workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "run_checks"


def test_lower_compiled_module_supports_provider_record_and_command_union_returns(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_provider_record_command_union_expressions.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    provider_workflow = lowered["execute_attempt"]
    provider_step = provider_workflow["steps"][0]
    assert provider_workflow["outputs"] == {
        "execution_report": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.ProviderResult.artifacts.execution_report"},
        },
        "status": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.ProviderResult.artifacts.status"},
        },
    }
    assert provider_step["output_bundle"] == {
        "path": "state/execute_attempt_result.json",
        "fields": [
            {"name": "execution_report", "json_pointer": "/execution_report", "type": "string"},
            {"name": "status", "json_pointer": "/status", "type": "string"},
        ],
    }

    command_workflow = lowered["run_checks"]
    command_step = command_workflow["steps"][0]
    assert command_workflow["outputs"] == {
        "check_outcome_variant": {
            "kind": "scalar",
            "type": "enum",
            "allowed": ["PASS", "FAIL"],
            "from": {"ref": "root.steps.CommandResult.artifacts.check_outcome_variant"},
        },
    }
    assert command_step["variant_output"]["discriminant"] == {
        "name": "check_outcome_variant",
        "json_pointer": "/check_outcome_variant",
        "type": "enum",
        "allowed": ["PASS", "FAIL"],
    }
    assert command_step["variant_output"]["variants"] == {
        "PASS": {
            "fields": [
                {"name": "path", "json_pointer": "/path", "type": "string"},
            ]
        },
        "FAIL": {
            "fields": [
                {"name": "error", "json_pointer": "/error", "type": "string"},
            ]
        },
    }

    provider_path = tmp_path / "execute_attempt.yaml"
    provider_path.write_text(yaml.safe_dump(provider_workflow), encoding="utf-8")
    loaded_provider = WorkflowLoader(tmp_path).load(provider_path)
    assert loaded_provider.surface.name == "execute_attempt"

    command_path = tmp_path / "run_checks.yaml"
    command_path.write_text(yaml.safe_dump(command_workflow), encoding="utf-8")
    loaded_command = WorkflowLoader(tmp_path).load(command_path)
    assert loaded_command.surface.name == "run_checks"


def test_lower_compiled_module_emits_float_contracts_for_inputs_outputs_and_bundle(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_provider_result_float_expression.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["run_metrics"]
    step = workflow["steps"][0]

    assert workflow["inputs"]["temperature"] == {"kind": "scalar", "type": "float"}
    assert workflow["outputs"] == {
        "score": {
            "kind": "scalar",
            "type": "float",
            "from": {"ref": "root.steps.ProviderResult.artifacts.score"},
        }
    }
    assert step["provider_params"]["workflow_lisp_inputs"] == ["${inputs.temperature}", "0.5"]
    assert step["output_bundle"] == {
        "path": "state/run_metrics_result.json",
        "fields": [
            {"name": "score", "json_pointer": "/score", "type": "float"},
        ],
    }

    path = tmp_path / "run_metrics.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "run_metrics"


def test_lower_compiled_module_supports_pathrel_input_and_output_contracts(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_pathrel_contracts.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["run_path"]
    step = workflow["steps"][0]

    assert workflow["inputs"]["report_path"] == {"type": "relpath"}
    assert workflow["outputs"] == {
        "path": {
            "type": "relpath",
            "from": {"ref": "root.steps.CommandResult.artifacts.path"},
        }
    }
    assert step["command"] == ["python", "scripts/emit_report.py", "${inputs.report_path}"]
    assert step["output_bundle"] == {
        "path": "state/run_path_result.json",
        "fields": [
            {"name": "path", "json_pointer": "/path", "type": "relpath"},
        ],
    }

    path = tmp_path / "run_path.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "run_path"


def test_lower_compiled_module_emits_call_step_for_root_call_expression(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_call_to_provider_workflow.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    callee_workflow = lowered["execute_attempt"]
    caller_workflow = lowered["run"]
    caller_step = caller_workflow["steps"][0]

    assert callee_workflow["outputs"]["execution_report"]["from"] == {
        "ref": "root.steps.ProviderResult.artifacts.execution_report"
    }
    assert caller_workflow["outputs"] == {
        "execution_report": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.CallResult.artifacts.execution_report"},
        },
        "status": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.CallResult.artifacts.status"},
        },
    }
    assert caller_workflow["imports"] == {"execute_attempt": "./execute_attempt.yaml"}
    assert caller_step == {
        "name": "CallResult",
        "id": "call_result",
        "call": "execute_attempt",
        "with": {
            "execute_provider": {"ref": "inputs.execute_provider"},
            "execute_prompt": {"ref": "inputs.execute_prompt"},
            "design_path": {"ref": "inputs.design_path"},
        },
    }

    callee_path = tmp_path / "execute_attempt.yaml"
    callee_path.write_text(yaml.safe_dump(callee_workflow), encoding="utf-8")
    loaded_callee = WorkflowLoader(tmp_path).load(callee_path)
    assert loaded_callee.surface.name == "execute_attempt"


def test_lower_compiled_module_lowers_local_defproc_and_callers(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _definition_fixture_path("valid_defprocs.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    procedure_workflow = lowered["build_plan"]
    caller_workflow = lowered["run_phase"]
    caller_step = caller_workflow["steps"][0]

    assert procedure_workflow["outputs"] == {
        "plan_path": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.RecordResult.artifacts.plan_path"},
        },
    }
    assert caller_workflow["imports"] == {"build_plan": "./build_plan.yaml"}
    assert caller_step == {
        "name": "CallResult",
        "id": "call_result",
        "call": "build_plan",
        "with": {
            "inputs__design_path": {"ref": "inputs.inputs__design_path"},
            "provider": {"ref": "inputs.provider"},
        },
    }

    procedure_path = tmp_path / "build_plan.yaml"
    procedure_path.write_text(yaml.safe_dump(procedure_workflow), encoding="utf-8")
    loaded_procedure = WorkflowLoader(tmp_path).load(procedure_path)
    assert loaded_procedure.surface.name == "build_plan"

    caller_path = tmp_path / "run_phase.yaml"
    caller_path.write_text(yaml.safe_dump(caller_workflow), encoding="utf-8")
    loaded_caller = WorkflowLoader(tmp_path).load(caller_path)
    assert loaded_caller.surface.name == "run_phase"


def test_lower_compiled_module_emits_call_step_for_zero_argument_call_expression(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_call_no_arguments.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    caller_workflow = lowered["run"]
    caller_step = caller_workflow["steps"][0]

    assert caller_workflow["imports"] == {"build_plan": "./build_plan.yaml"}
    assert caller_step == {
        "name": "CallResult",
        "id": "call_result",
        "call": "build_plan",
        "with": {},
    }

    callee_path = tmp_path / "build_plan.yaml"
    callee_path.write_text(yaml.safe_dump(lowered["build_plan"]), encoding="utf-8")
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(caller_workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "run"


def test_lower_compiled_module_expands_record_typed_call_binding_from_structured_input() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_call_record_typed_input_reference.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    caller_workflow = lowered["run"]
    caller_step = caller_workflow["steps"][0]

    assert caller_workflow["inputs"] == {
        "inputs__plan": {"type": "relpath"},
        "inputs__attempts": {"kind": "scalar", "type": "integer"},
    }
    assert caller_workflow["imports"] == {"run_checks": "./run_checks.yaml"}
    assert caller_step == {
        "name": "CallResult",
        "id": "call_result",
        "call": "run_checks",
        "with": {
            "inputs__plan": {"ref": "inputs.inputs__plan"},
            "inputs__attempts": {"ref": "inputs.inputs__attempts"},
        },
    }

    assert lowered["run_checks"]["inputs"] == {
        "inputs__plan": {"type": "relpath"},
        "inputs__attempts": {"kind": "scalar", "type": "integer"},
    }


def test_lower_compiled_module_emits_call_step_for_imported_call_with_explicit_returns(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_call_imported_with_returns.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["run"]
    call_step = workflow["steps"][0]

    assert workflow["outputs"] == {
        "result": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.CallResult.artifacts.result"},
        }
    }
    assert workflow["imports"] == {
        "remote/run_phase": "remote/workflows.yaml",
    }
    assert call_step == {
        "name": "CallResult",
        "id": "call_result",
        "call": "remote/run_phase",
        "with": {},
    }

    imported_path = tmp_path / "remote" / "workflows.yaml"
    imported_path.parent.mkdir(parents=True, exist_ok=True)
    imported_path.write_text(
        yaml.safe_dump(
                {
                    "version": "2.14",
                    "name": "run_phase",
                    "artifacts": {
                        "result": {
                            "kind": "scalar",
                            "type": "string",
                        }
                    },
                    "outputs": {
                        "result": {
                            "kind": "scalar",
                        "type": "string",
                        "from": {"ref": "root.steps.EmitResult.artifacts.result"},
                    }
                },
                "steps": [
                    {
                        "name": "EmitResult",
                        "id": "emit_result",
                        "set_scalar": {
                            "artifact": "result",
                            "value": "ok",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "run"


def test_lower_compiled_module_emits_call_step_for_imported_call_with_explicit_returns_and_arguments(
    tmp_path: Path,
) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_call_imported_with_returns_and_arguments.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["run"]
    call_step = workflow["steps"][0]

    assert workflow["outputs"] == {
        "result": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.CallResult.artifacts.result"},
        }
    }
    assert workflow["imports"] == {
        "remote/run_phase": "remote/workflows.yaml",
    }
    assert call_step == {
        "name": "CallResult",
        "id": "call_result",
        "call": "remote/run_phase",
        "with": {
            "design_path": {"ref": "inputs.design_path"},
        },
    }

    imported_path = tmp_path / "remote" / "workflows.yaml"
    imported_path.parent.mkdir(parents=True, exist_ok=True)
    imported_path.write_text(
        yaml.safe_dump(
                {
                    "version": "2.14",
                    "name": "run_phase",
                    "artifacts": {
                        "result": {
                            "kind": "scalar",
                            "type": "string",
                        }
                    },
                    "inputs": {
                        "design_path": {
                            "kind": "scalar",
                        "type": "string",
                    }
                },
                "outputs": {
                    "result": {
                        "kind": "scalar",
                        "type": "string",
                        "from": {"ref": "root.steps.EmitResult.artifacts.result"},
                    }
                },
                "steps": [
                    {
                        "name": "EmitResult",
                        "id": "emit_result",
                        "set_scalar": {
                            "artifact": "result",
                            "value": "ok",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "run"


def test_lower_compiled_module_emits_call_step_for_module_qualified_imported_call_with_explicit_returns(
    tmp_path: Path,
) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_call_imported_module_qualified_with_returns.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)
    workflow = lowered["run"]
    step = workflow["steps"][0]

    assert workflow["imports"] == {
        "remote/workflows/run_phase": "remote/workflows.yaml",
    }
    assert step == {
        "name": "CallResult",
        "id": "call_result",
        "call": "remote/workflows/run_phase",
        "with": {},
    }

    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")

    imported_path = tmp_path / "remote" / "workflows.yaml"
    imported_path.parent.mkdir(parents=True, exist_ok=True)
    imported_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.14",
                "name": "run_phase",
                "artifacts": {
                    "result": {
                        "kind": "scalar",
                        "type": "string",
                    }
                },
                "outputs": {
                    "result": {
                        "kind": "scalar",
                        "type": "string",
                        "from": {"ref": "root.steps.EmitResult.artifacts.result"},
                    }
                },
                "steps": [
                    {
                        "name": "EmitResult",
                        "id": "emit_result",
                        "set_scalar": {
                            "artifact": "result",
                            "value": "ok",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "run"


def test_lower_compiled_module_supports_record_root_expression(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_record_expression.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["build_plan"]
    assert workflow["outputs"] == {
        "path": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.RecordResult.artifacts.path"},
        },
        "status": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.RecordResult.artifacts.status"},
        },
    }
    assert workflow["steps"] == [
        {
            "name": "RecordResult",
            "id": "record_result",
            "materialize_artifacts": {
                "values": [
                    {
                        "name": "path",
                        "source": {"input": "candidate_path"},
                        "contract": {"inherit": "source"},
                    },
                    {
                        "name": "status",
                        "source": {"literal": "draft"},
                        "contract": {"type": "string"},
                    },
                ]
            },
        }
    ]

    path = tmp_path / "build_plan.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "build_plan"


def test_lower_compiled_module_records_result_node_source_span() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_provider_command_result_expressions.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    execute_attempt_result_span = lowered_module.source_map["execute_attempt"]["execute_attempt.result"]
    run_checks_result_span = lowered_module.source_map["run_checks"]["run_checks.result"]
    execute_attempt_step_span = lowered_module.source_map["execute_attempt"]["execute_attempt.step.ProviderResult"]
    run_checks_step_span = lowered_module.source_map["run_checks"]["run_checks.step.CommandResult"]

    assert execute_attempt_result_span.source_file == str(source_path)
    assert execute_attempt_result_span.line_start == 21
    assert execute_attempt_result_span.column_start == 3

    assert run_checks_result_span.source_file == str(source_path)
    assert run_checks_result_span.line_start == 30
    assert run_checks_result_span.column_start == 3

    assert execute_attempt_step_span.source_file == str(source_path)
    assert execute_attempt_step_span.line_start == 21
    assert execute_attempt_step_span.column_start == 3

    assert run_checks_step_span.source_file == str(source_path)
    assert run_checks_step_span.line_start == 30
    assert run_checks_step_span.column_start == 3


def test_lower_compiled_module_records_contract_and_boundary_node_source_spans() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_provider_command_result_expressions.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    execute_attempt_map = lowered_module.source_map["execute_attempt"]
    run_checks_map = lowered_module.source_map["run_checks"]

    assert execute_attempt_map["execute_attempt.input.execute_provider"].line_start == 16
    assert execute_attempt_map["execute_attempt.input.execute_prompt"].line_start == 17
    assert execute_attempt_map["execute_attempt.input.design_path"].line_start == 18
    assert execute_attempt_map["execute_attempt.output.attempt_variant"].line_start == 9
    assert (
        execute_attempt_map[
            "execute_attempt.step.ProviderResult.contract.variant_output.discriminant"
        ].line_start
        == 9
    )
    assert (
        execute_attempt_map[
            "execute_attempt.step.ProviderResult.contract.variant_output.variant.COMPLETED.field.execution_report"
        ].line_start
        == 11
    )
    assert (
        execute_attempt_map[
            "execute_attempt.step.ProviderResult.contract.variant_output.variant.BLOCKED.field.progress_report"
        ].line_start
        == 13
    )

    assert run_checks_map["run_checks.input.design_path"].line_start == 27
    assert run_checks_map["run_checks.output.path"].line_start == 6
    assert run_checks_map["run_checks.output.status"].line_start == 7
    assert run_checks_map["run_checks.step.CommandResult.contract.output_bundle.field.path"].line_start == 6
    assert run_checks_map["run_checks.step.CommandResult.contract.output_bundle.field.status"].line_start == 7


def test_lower_compiled_module_records_call_and_import_node_source_spans() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_call_to_provider_workflow.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    run_map = lowered_module.source_map["run"]

    assert run_map["run.step.CallResult.call"].line_start == 26
    assert run_map["run.step.CallResult.with.execute_provider"].line_start == 27
    assert run_map["run.step.CallResult.with.execute_prompt"].line_start == 28
    assert run_map["run.step.CallResult.with.design_path"].line_start == 29
    assert run_map["run.import.execute_attempt"].line_start == 26


def test_lower_compiled_module_records_expanded_record_call_binding_source_spans() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_call_record_typed_input_reference.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    run_map = lowered_module.source_map["run"]
    assert "run.step.CallResult.with.inputs" not in run_map
    assert run_map["run.step.CallResult.with.inputs__plan"].line_start == 26
    assert run_map["run.step.CallResult.with.inputs__attempts"].line_start == 26
    assert run_map["run.import.run_checks"].line_start == 25


def test_lower_compiled_module_supports_let_star_wrapped_root_execution_forms() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_let_star_root_execution.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    provider_step = lowered["execute_attempt"]["steps"][0]
    assert provider_step["provider"] == "${inputs.execute_provider}"
    assert provider_step["input_file"] == "${inputs.execute_prompt}"
    assert provider_step["provider_params"]["workflow_lisp_inputs"] == ["${inputs.design_path}"]

    command_step = lowered["run_checks"]["steps"][0]
    assert command_step["command"] == ["python", "scripts/checks.py", "${inputs.design_path}"]

    call_workflow = lowered["run"]
    call_step = call_workflow["steps"][0]
    assert call_workflow["imports"] == {"build_plan": "./build_plan.yaml"}
    assert call_step == {
        "name": "CallResult",
        "id": "call_result",
        "call": "build_plan",
        "with": {
            "design_path": {"ref": "inputs.design_path"},
            "attempts": 2,
        },
    }


def test_lower_compiled_module_supports_reference_root_expression(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_reference_root_expression.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)
    lowered = lowered_module.workflows

    workflow = lowered["read_name"]
    assert workflow["outputs"] == {
        "result": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.ScalarResult.artifacts.result"},
        }
    }
    assert workflow["steps"] == [
        {
            "name": "ScalarResult",
            "id": "scalar_result",
            "materialize_artifacts": {
                "values": [
                    {
                        "name": "result",
                        "source": {"input": "name"},
                        "contract": {"inherit": "source"},
                    }
                ]
            },
        }
    ]

    source_map = lowered_module.source_map["read_name"]
    assert source_map["read_name.output.result"].line_start == 8
    assert source_map["read_name.step.ScalarResult"].line_start == 9

    path = tmp_path / "read_name.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "read_name"


def test_lower_compiled_module_supports_nil_scalar_root_expression(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_nil_literal_expression.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["emit_null"]
    assert workflow["steps"] == [
        {
            "name": "ScalarResult",
            "id": "scalar_result",
            "materialize_artifacts": {
                "values": [
                    {
                        "name": "result",
                        "source": {"literal": None},
                        "contract": {"type": "string"},
                    }
                ]
            },
        }
    ]

    path = tmp_path / "emit_null.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "emit_null"


def test_lower_compiled_module_supports_match_root_execution_routes(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_match_root_execution_routes.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["route_plan"]
    assert workflow["outputs"] == {
        "path": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.MatchResult.artifacts.path"},
        },
        "status": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.MatchResult.artifacts.status"},
        },
    }

    subject_step, match_step = workflow["steps"]
    assert subject_step["name"] == "ProviderResult"
    assert subject_step["provider"] == "${inputs.execute_provider}"
    assert subject_step["input_file"] == "${inputs.execute_prompt}"

    assert match_step["name"] == "MatchResult"
    assert match_step["match"]["ref"] == "root.steps.ProviderResult.artifacts.attempt_variant"
    assert set(match_step["match"]["cases"]) == {"COMPLETED", "BLOCKED"}

    completed = match_step["match"]["cases"]["COMPLETED"]
    blocked = match_step["match"]["cases"]["BLOCKED"]

    assert completed["outputs"] == {
        "path": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "self.steps.CommandResult.artifacts.path"},
        },
        "status": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "self.steps.CommandResult.artifacts.status"},
        },
    }
    assert blocked["outputs"] == {
        "path": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "self.steps.CommandResult.artifacts.path"},
        },
        "status": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "self.steps.CommandResult.artifacts.status"},
        },
    }

    path = tmp_path / "route_plan.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "route_plan"


def test_lower_compiled_module_supports_match_root_scalar_routes(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_match_root_scalar_routes.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)
    lowered = lowered_module.workflows

    workflow = lowered["route_status"]
    assert workflow["outputs"] == {
        "result": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.MatchResult.artifacts.result"},
        },
    }

    subject_step, match_step = workflow["steps"]
    assert subject_step["name"] == "ProviderResult"
    assert match_step["name"] == "MatchResult"
    assert set(match_step["match"]["cases"]) == {"COMPLETED", "BLOCKED"}
    assert match_step["match"]["cases"]["COMPLETED"]["outputs"] == {
        "result": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "self.steps.ScalarResult.artifacts.result"},
        },
    }
    assert match_step["match"]["cases"]["BLOCKED"]["outputs"] == {
        "result": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "self.steps.ScalarResult.artifacts.result"},
        },
    }

    route_map = lowered_module.source_map["route_status"]
    assert route_map["route_status.step.MatchResult.case.COMPLETED.output.result"].line_start == 16
    assert route_map["route_status.step.MatchResult.case.BLOCKED.output.result"].line_start == 16

    path = tmp_path / "route_status.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "route_status"


def test_lower_compiled_module_supports_exhaustive_partial_match_root_execution_routes(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_match_root_execution_routes_partial.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["route_plan"]
    subject_step, match_step = workflow["steps"]

    assert subject_step["name"] == "ProviderResult"
    assert match_step["name"] == "MatchResult"
    assert set(match_step["match"]["cases"]) == {"COMPLETED", "BLOCKED"}

    path = tmp_path / "route_plan_partial.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "route_plan"


def test_lower_compiled_module_supports_non_exhaustive_partial_match_root_execution_routes(
    tmp_path: Path,
) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("invalid_match_root_execution_routes_partial_non_exhaustive.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["route_plan"]
    subject_step, match_step = workflow["steps"]

    assert subject_step["name"] == "ProviderResult"
    assert match_step["name"] == "MatchResult"
    assert set(match_step["match"]["cases"]) == {"COMPLETED", "BLOCKED"}
    blocked_case_steps = match_step["match"]["cases"]["BLOCKED"]["steps"]
    assert len(blocked_case_steps) == 1
    assert blocked_case_steps[0]["name"] == "UnhandledPartialBlocked"
    assert blocked_case_steps[0]["command"] == ["python", "-c", "import sys; sys.exit(66)"]

    path = tmp_path / "route_plan_partial_non_exhaustive.yaml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    loaded = WorkflowLoader(tmp_path).load(path)
    assert loaded.surface.name == "route_plan"


def test_lower_compiled_module_records_source_spans_for_generated_partial_match_fallback_case() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("invalid_match_root_execution_routes_partial_non_exhaustive.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    route_map = lowered_module.source_map["route_plan"]

    assert route_map["route_plan.step.MatchResult.match.case.BLOCKED"].line_start == 26
    assert route_map["route_plan.step.MatchResult.case.BLOCKED.output.path"].line_start == 6
    assert route_map["route_plan.step.MatchResult.case.BLOCKED.output.status"].line_start == 7
    assert (
        route_map[
            "route_plan.step.MatchResult.case.BLOCKED.step.UnhandledPartialBlocked.contract.output_bundle.field.path"
        ].line_start
        == 6
    )
    assert (
        route_map[
            "route_plan.step.MatchResult.case.BLOCKED.step.UnhandledPartialBlocked.contract.output_bundle.field.status"
        ].line_start
        == 7
    )


def test_lower_compiled_module_records_distinct_step_spans_for_root_match_lowering() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_match_root_execution_routes.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    route_plan_map = lowered_module.source_map["route_plan"]
    provider_step_span = route_plan_map["route_plan.step.ProviderResult"]
    match_step_span = route_plan_map["route_plan.step.MatchResult"]

    assert provider_step_span.source_file == str(source_path)
    assert provider_step_span.line_start == 22
    assert provider_step_span.column_start == 12

    assert match_step_span.source_file == str(source_path)
    assert match_step_span.line_start == 26
    assert match_step_span.column_start == 5


def test_lower_compiled_module_records_match_case_call_and_import_source_spans() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_match_root_call_routes.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    route_map = lowered_module.source_map["route_plan"]

    assert route_map["route_plan.step.MatchResult.case.COMPLETED.step.CallResult.call"].line_start == 55
    assert route_map["route_plan.step.MatchResult.case.COMPLETED.step.CallResult.with.design_path"].line_start == 56
    assert route_map["route_plan.step.MatchResult.case.BLOCKED.step.CallResult.call"].line_start == 58
    assert route_map["route_plan.step.MatchResult.case.BLOCKED.step.CallResult.with.design_path"].line_start == 59

    assert route_map["route_plan.import.build_completed"].line_start == 55
    assert route_map["route_plan.import.build_blocked"].line_start == 58


def test_lower_compiled_module_supports_match_case_call_bindings_from_variant_fields(tmp_path: Path) -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_match_root_call_routes_variant_binding.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["route_plan"]
    subject_step, match_step = workflow["steps"]

    assert subject_step["name"] == "ProviderResult"
    assert match_step["name"] == "MatchResult"

    completed_call = match_step["match"]["cases"]["COMPLETED"]["steps"][0]
    blocked_call = match_step["match"]["cases"]["BLOCKED"]["steps"][0]

    assert completed_call["with"] == {
        "design_path": {"ref": "parent.steps.ProviderResult.artifacts.execution_report"},
        "status": "completed",
    }
    assert blocked_call["with"] == {
        "design_path": {"ref": "parent.steps.ProviderResult.artifacts.progress_report"},
        "status": "blocked",
    }

    assert workflow["imports"] == {
        "build_completed": "./build_completed.yaml",
        "build_blocked": "./build_blocked.yaml",
    }


def test_lower_compiled_module_rejects_direct_match_binding_scalar_lowering() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("invalid_match_root_execution_routes_direct_variant_binding.orc")

    compiled = compiler.compile_workflow_module_file(source_path)

    with pytest.raises(WorkflowLispSyntaxError) as exc_info:
        lowering.lower_compiled_module_to_workflow_dicts(compiled)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "frontend_lowering_error"
    assert "cannot be lowered as one scalar value" in diagnostic.message
    assert diagnostic.enclosing_form_name == "match"
    assert diagnostic.generated_core_node_id == "route_plan.step.MatchResult.case.COMPLETED.result"


def test_lower_compiled_module_rejects_non_execution_root_match_subject_with_core_node_context() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_text = """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defunion Attempt
  (COMPLETED (execution_report String))
  (BLOCKED (progress_report String)))

(defrecord Envelope
  (attempt Attempt))

(defworkflow route_plan ((execute_provider Provider) (execute_prompt Prompt) (design_path String)) -> String
  (let* ((attempt
           (provider-result execute_provider
             :prompt execute_prompt
             :inputs (design_path)
             :returns Attempt))
         (envelope
           (record Envelope
             :attempt attempt)))
  (match envelope.attempt
    ((COMPLETED completed) "done")
    ((BLOCKED blocked) "blocked"))))
"""

    compiled = compiler.compile_workflow_module_text(
        source_text,
        source_path=str(Path("inline-non-execution-match-subject.orc")),
    )

    with pytest.raises(WorkflowLispSyntaxError) as exc_info:
        lowering.lower_compiled_module_to_workflow_dicts(compiled)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "frontend_lowering_error"
    assert "match subjects must be execution expressions rooted at" in diagnostic.message
    assert diagnostic.enclosing_form_name == "match"
    assert diagnostic.generated_core_node_id == "route_plan.result"


def test_lower_compiled_module_rejects_union_field_inside_record_typed_input_with_core_node_context() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_text = """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defunion Attempt
  (COMPLETED (execution_report String))
  (BLOCKED (progress_report String)))

(defrecord Inputs
  (attempt Attempt))

(defworkflow run_phase ((inputs Inputs)) -> String
  "ok")
"""

    compiled = compiler.compile_workflow_module_text(
        source_text,
        source_path=str(Path("inline-record-input-union-field.orc")),
    )

    with pytest.raises(WorkflowLispSyntaxError) as exc_info:
        lowering.lower_compiled_module_to_workflow_dicts(compiled)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "frontend_lowering_error"
    assert "Record-typed workflow input fields may not contain union-typed fields" in diagnostic.message
    assert "inputs.attempt" in diagnostic.message
    assert diagnostic.enclosing_form_name == "defworkflow"
    assert diagnostic.generated_core_node_id == "run_phase.input.inputs__attempt"


def test_lower_compiled_module_rejects_union_typed_workflow_input_with_core_node_context() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_text = """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defunion Attempt
  (COMPLETED (execution_report String))
  (BLOCKED (progress_report String)))

(defworkflow run_phase ((attempt Attempt)) -> String
  "ok")
"""

    compiled = compiler.compile_workflow_module_text(
        source_text,
        source_path=str(Path("inline-union-typed-workflow-input.orc")),
    )

    with pytest.raises(WorkflowLispSyntaxError) as exc_info:
        lowering.lower_compiled_module_to_workflow_dicts(compiled)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "frontend_lowering_error"
    assert "Unsupported workflow input type for MVP lowering: Attempt" in diagnostic.message
    assert diagnostic.enclosing_form_name == "defworkflow"
    assert diagnostic.generated_core_node_id == "run_phase.input.attempt"


def test_lower_compiled_module_reports_core_node_for_nested_union_contract_error() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_text = """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defunion Inner
  (LEFT (value String))
  (RIGHT (value String)))

(defunion Attempt
  (COMPLETED (payload Inner))
  (BLOCKED (reason String)))

(defworkflow run_phase ((execute_provider Provider) (execute_prompt Prompt)) -> Attempt
  (provider-result execute_provider
    :prompt execute_prompt
    :inputs ()
    :returns Attempt))
"""

    compiled = compiler.compile_workflow_module_text(
        source_text,
        source_path=str(Path("inline-nested-union-contract.orc")),
    )

    with pytest.raises(WorkflowLispSyntaxError) as exc_info:
        lowering.lower_compiled_module_to_workflow_dicts(compiled)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.code == "frontend_lowering_error"
    assert "output contracts support only scalar/enum/defpath field types" in diagnostic.message
    assert diagnostic.generated_core_node_id == "run_phase.result"


def test_lower_compiled_module_records_match_subject_and_case_contract_source_spans() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_match_root_execution_routes.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    route_map = lowered_module.source_map["route_plan"]

    assert route_map["route_plan.step.ProviderResult.contract.variant_output.discriminant"].line_start == 9
    assert (
        route_map[
            "route_plan.step.ProviderResult.contract.variant_output.variant.COMPLETED.field.execution_report"
        ].line_start
        == 11
    )
    assert (
        route_map[
            "route_plan.step.ProviderResult.contract.variant_output.variant.BLOCKED.field.progress_report"
        ].line_start
        == 13
    )

    assert (
        route_map[
            "route_plan.step.MatchResult.case.COMPLETED.step.CommandResult.contract.output_bundle.field.path"
        ].line_start
        == 6
    )
    assert (
        route_map[
            "route_plan.step.MatchResult.case.COMPLETED.step.CommandResult.contract.output_bundle.field.status"
        ].line_start
        == 7
    )
    assert (
        route_map[
            "route_plan.step.MatchResult.case.BLOCKED.step.CommandResult.contract.output_bundle.field.path"
        ].line_start
        == 6
    )
    assert (
        route_map[
            "route_plan.step.MatchResult.case.BLOCKED.step.CommandResult.contract.output_bundle.field.status"
        ].line_start
        == 7
    )


def test_lower_compiled_module_records_match_routing_source_spans() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_match_root_execution_routes.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    route_map = lowered_module.source_map["route_plan"]

    assert route_map["route_plan.step.MatchResult.match.ref"].line_start == 26
    assert route_map["route_plan.step.MatchResult.match.case.COMPLETED"].line_start == 27
    assert route_map["route_plan.step.MatchResult.match.case.BLOCKED"].line_start == 31


def test_lower_compiled_module_records_match_case_output_source_spans() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_match_root_execution_routes.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered_module = lowering.lower_compiled_module(compiled)

    route_map = lowered_module.source_map["route_plan"]

    assert route_map["route_plan.step.MatchResult.case.COMPLETED.output.path"].line_start == 6
    assert route_map["route_plan.step.MatchResult.case.COMPLETED.output.status"].line_start == 7
    assert route_map["route_plan.step.MatchResult.case.BLOCKED.output.path"].line_start == 6
    assert route_map["route_plan.step.MatchResult.case.BLOCKED.output.status"].line_start == 7


def test_lower_compiled_module_supports_record_typed_workflow_inputs() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = Path(__file__).parent / "fixtures" / "workflow_lisp" / "definitions" / "valid_module_imports_exports.orc"

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["run_phase"]
    assert workflow["inputs"] == {
        "inputs__plan": {"type": "relpath"},
    }


def test_lower_compiled_module_flattens_record_typed_input_field_accesses() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_path = _fixture_path("valid_record_typed_inputs_lowering.orc")

    compiled = compiler.compile_workflow_module_file(source_path)
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["run_checks"]
    step = workflow["steps"][0]

    assert workflow["inputs"] == {
        "inputs__plan": {"type": "relpath"},
        "inputs__attempts": {"kind": "scalar", "type": "integer"},
    }
    assert step["command"] == [
        "python",
        "scripts/checks.py",
        "${inputs.inputs__plan}",
        "${inputs.inputs__attempts}",
    ]


def test_lower_compiled_module_supports_provider_and_prompt_record_outputs() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_text = """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defrecord PromptEnvelope
  (provider Provider)
  (prompt Prompt))

(defworkflow emit_prompt ((provider Provider) (prompt Prompt)) -> PromptEnvelope
  (record PromptEnvelope
    :provider provider
    :prompt prompt))
"""

    compiled = compiler.compile_workflow_module_text(
        source_text,
        source_path=str(Path("inline-provider-prompt-lowering.orc")),
    )
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)
    workflow = lowered["emit_prompt"]

    assert workflow["inputs"] == {
        "provider": {"kind": "scalar", "type": "string"},
        "prompt": {"kind": "scalar", "type": "string"},
    }
    assert workflow["outputs"] == {
        "provider": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.RecordResult.artifacts.provider"},
        },
        "prompt": {
            "kind": "scalar",
            "type": "string",
            "from": {"ref": "root.steps.RecordResult.artifacts.prompt"},
        },
    }


def test_lower_compiled_module_supports_phase_target_root_expression() -> None:
    compiler = _compiler_module()
    lowering = _lowering_module()
    source_text = """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defworkflow emit_target ((phase_ctx PathRel)) -> PathRel
  (with-phase phase_ctx implementation
    (phase-target phase_ctx progress-report)))
"""

    compiled = compiler.compile_workflow_module_text(
        source_text,
        source_path=str(Path("inline-phase-target-lowering.orc")),
    )
    lowered = lowering.lower_compiled_module_to_workflow_dicts(compiled)

    workflow = lowered["emit_target"]
    assert workflow["outputs"] == {
        "result": {
            "type": "relpath",
            "from": {"ref": "root.steps.ScalarResult.artifacts.result"},
        }
    }
    assert workflow["steps"] == [
        {
            "name": "ScalarResult",
            "id": "scalar_result",
            "materialize_artifacts": {
                "values": [
                    {
                        "name": "result",
                        "source": {"literal": "${inputs.phase_ctx}/implementation/progress-report"},
                        "contract": {"type": "relpath"},
                    }
                ]
            },
        }
    ]
