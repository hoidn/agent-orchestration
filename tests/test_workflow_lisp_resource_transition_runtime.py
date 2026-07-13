from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.core_ast import build_core_workflow_ast, workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.lowering import lower_surface_workflow
from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow.state_layout import (
    GeneratedPathAllocationRequest,
    GeneratedPathPrivacy,
    GeneratedPathResumeScope,
    GeneratedPathSemanticRole,
    StateLayout,
)
from orchestrator.workflow.surface_ast import (
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
)
from orchestrator.workflow.transition_contract import validate_transition_declaration


REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGN_DELTA_RUNTIME_TRANSITION_FIXTURE = (
    REPO_ROOT
    / "workflows"
    / "library"
    / "lisp_frontend_design_delta"
    / "runtime_transition_fixture.orc"
)
DESIGN_DELTA_MIGRATION_INPUTS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
)


def _write_yaml(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _transition_declaration():
    return validate_transition_declaration(
        {
            "transition_schema_version": 1,
            "resource": {
                "resource_kind": "drain_run_state",
                "state_type": {
                    "kind": "record",
                    "name": "DrainRunState",
                    "fields": [
                        {"name": "drain_status", "type": {"kind": "primitive", "name": "String"}},
                        {"name": "history", "type": {"kind": "list", "item": {"kind": "primitive", "name": "Json"}}},
                    ],
                },
                "backing": {"kind": "state_layout"},
            },
            "transition": {
                "name": "drain/write_status",
                "request_type": {
                    "kind": "record",
                    "name": "DrainStatusRequest",
                    "fields": [
                        {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                    ],
                },
                "result_type": {
                    "kind": "record",
                    "name": "DrainStatusResult",
                    "fields": [
                        {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                    ],
                },
                "preconditions": [
                    {
                        "pure_expr_schema_version": 1,
                        "result_type": {"kind": "primitive", "name": "Bool"},
                        "bindings": {
                            "state": {
                                "type": {
                                    "kind": "record",
                                    "name": "DrainRunState",
                                    "fields": [
                                        {"name": "drain_status", "type": {"kind": "primitive", "name": "String"}},
                                        {"name": "history", "type": {"kind": "list", "item": {"kind": "primitive", "name": "Json"}}},
                                    ],
                                }
                            },
                            "request": {
                                "type": {
                                    "kind": "record",
                                    "name": "DrainStatusRequest",
                                    "fields": [
                                        {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                                    ],
                                }
                            },
                        },
                        "expr": {
                            "kind": "op",
                            "operator": "!=",
                            "args": [
                                {
                                    "kind": "field_access",
                                    "base": {"kind": "binding", "name": "request"},
                                    "field": "status",
                                },
                                {
                                    "kind": "literal",
                                    "type": {"kind": "primitive", "name": "String"},
                                    "value": "",
                                },
                            ],
                        },
                    }
                ],
                "updates": [
                    {
                        "op": "set_field",
                        "target": "drain_status",
                        "value": {
                            "pure_expr_schema_version": 1,
                            "result_type": {"kind": "primitive", "name": "String"},
                            "bindings": {
                                "state": {
                                    "type": {
                                        "kind": "record",
                                        "name": "DrainRunState",
                                        "fields": [
                                            {"name": "drain_status", "type": {"kind": "primitive", "name": "String"}},
                                            {"name": "history", "type": {"kind": "list", "item": {"kind": "primitive", "name": "Json"}}},
                                        ],
                                    }
                                },
                                "request": {
                                    "type": {
                                        "kind": "record",
                                        "name": "DrainStatusRequest",
                                        "fields": [
                                            {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                                        ],
                                    }
                                },
                            },
                            "expr": {
                                "kind": "field_access",
                                "base": {"kind": "binding", "name": "request"},
                                "field": "status",
                            },
                        },
                    }
                ],
                "write_set": ["drain_status"],
                "idempotency_fields": ["status"],
                "result_projection": {
                    "pure_expr_schema_version": 1,
                    "result_type": {
                        "kind": "record",
                        "name": "DrainStatusResult",
                        "fields": [
                            {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                        ],
                    },
                    "bindings": {
                        "state": {
                            "type": {
                                "kind": "record",
                                "name": "DrainRunState",
                                "fields": [
                                    {"name": "drain_status", "type": {"kind": "primitive", "name": "String"}},
                                    {"name": "history", "type": {"kind": "list", "item": {"kind": "primitive", "name": "Json"}}},
                                ],
                            }
                        },
                        "request": {
                            "type": {
                                "kind": "record",
                                "name": "DrainStatusRequest",
                                "fields": [
                                    {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                                ],
                            }
                        },
                    },
                    "expr": {
                        "kind": "record",
                        "type": {
                            "kind": "record",
                            "name": "DrainStatusResult",
                            "fields": [
                                {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                            ],
                        },
                        "fields": [
                            {
                                "name": "status",
                                "value": {
                                    "kind": "field_access",
                                    "base": {"kind": "binding", "name": "request"},
                                    "field": "status",
                                },
                            }
                        ],
                    },
                },
                "audit_projection": {
                    "pure_expr_schema_version": 1,
                    "result_type": {
                        "kind": "record",
                        "name": "DrainStatusAudit",
                        "fields": [
                            {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                        ],
                    },
                    "bindings": {
                        "state": {
                            "type": {
                                "kind": "record",
                                "name": "DrainRunState",
                                "fields": [
                                    {"name": "drain_status", "type": {"kind": "primitive", "name": "String"}},
                                    {"name": "history", "type": {"kind": "list", "item": {"kind": "primitive", "name": "Json"}}},
                                ],
                            }
                        },
                        "request": {
                            "type": {
                                "kind": "record",
                                "name": "DrainStatusRequest",
                                "fields": [
                                    {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                                ],
                            }
                        },
                    },
                    "expr": {
                        "kind": "record",
                        "type": {
                            "kind": "record",
                            "name": "DrainStatusAudit",
                            "fields": [
                                {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                            ],
                        },
                        "fields": [
                            {
                                "name": "status",
                                "value": {
                                    "kind": "field_access",
                                    "base": {"kind": "binding", "name": "request"},
                                    "field": "status",
                                },
                            }
                        ],
                    },
                },
                "conflict_policy": "fail_closed",
                "backend": {"kind": "runtime_native"},
            },
        }
    )


def _generated_surface_workflow(
    tmp_path: Path,
    *,
    include_state_layout_allocations: bool = False,
) -> SurfaceWorkflow:
    declaration = _transition_declaration()
    generated_path_allocations = ()
    if include_state_layout_allocations:
        generated_path_allocations = (
            StateLayout.allocate(
                GeneratedPathAllocationRequest(
                    owner="resource_transition",
                    workflow_name="resource-transition-runtime",
                    semantic_role=GeneratedPathSemanticRole.RESOURCE_STATE,
                    privacy=GeneratedPathPrivacy.PRIVATE_GENERATED,
                    resume_scope=GeneratedPathResumeScope.RUN,
                    stable_identity="drain_run_state",
                    projection_hints={"relative_path": "state/transition/state.json"},
                )
            ),
            StateLayout.allocate(
                GeneratedPathAllocationRequest(
                    owner="resource_transition",
                    workflow_name="resource-transition-runtime",
                    semantic_role=GeneratedPathSemanticRole.TRANSITION_AUDIT,
                    privacy=GeneratedPathPrivacy.PRIVATE_GENERATED,
                    resume_scope=GeneratedPathResumeScope.RUN,
                    stable_identity="drain_run_state_audit",
                    projection_hints={"relative_path": "state/transition/audit.jsonl"},
                )
            ),
        )
    step = SurfaceStep(
        name="Transition",
        step_id="transition",
        kind=SurfaceStepKind.RESOURCE_TRANSITION,
        common=SurfaceStepCommonConfig(
            output_bundle={
                "path": "state/transition/result.json",
                "fields": [{"name": "return__status", "json_pointer": "/result/status", "type": "string"}],
            }
        ),
        resource_transition={
            "declaration": declaration,
            "resource": {
                "resource_id": "drain-run-1",
                "resource_kind": "drain_run_state",
                "state_path": "state/transition/state.json",
                "audit_path": "state/transition/audit.jsonl",
            },
            "request_bindings": {"status": "BLOCKED"},
        },
    )
    return SurfaceWorkflow(
        version="2.14",
        name="resource-transition-runtime",
        steps=(step,),
        provenance=WorkflowProvenance(
            workflow_path=tmp_path / "generated.yaml",
            source_root=tmp_path,
            generated_path_allocations=generated_path_allocations,
        ),
    )


def _write_native_resource_state(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "transition_schema_version": 1,
                "resource_id": "drain-run-1",
                "resource_kind": "drain_run_state",
                "state_version": "native:0:seed",
                "state": {
                    "drain_status": "READY",
                    "history": [],
                },
                "provenance": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _run_design_delta_runtime_transition_fixture_cli(
    tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    run_state_path = tmp_path / "state" / "run_state.json"
    summary_path = tmp_path / "artifacts" / "work" / "drain_summary.json"
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    run_state_path.write_text(
        json.dumps(
            {
                "schema": "lisp_frontend_autonomous_drain_run_state/v1",
                "completed_items": [],
                "completed_design_gaps": [],
                "blocked_items": {},
                "blocked_design_gaps": {},
                "history": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps({"status": "BLOCKED", "reason": "runtime_native_fixture"})
        + "\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "run",
            str(DESIGN_DELTA_RUNTIME_TRANSITION_FIXTURE),
            "--entry-workflow",
            "run-runtime-transition-fixture",
            "--source-root",
            str(REPO_ROOT / "workflows" / "library"),
            "--provider-externs-file",
            str(DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.providers.json"),
            "--prompt-externs-file",
            str(DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.prompts.json"),
            "--command-boundaries-file",
            str(DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.commands.json"),
            "--input",
            "summary_path=artifacts/work/drain_summary.json",
            "--state-dir",
            str(tmp_path / "orchestrator-state"),
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                [str(REPO_ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_loader_rejects_authored_resource_transition_step(tmp_path: Path) -> None:
    workflow_file = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.14",
            "name": "authored-resource-transition",
            "steps": [
                {
                    "name": "Transition",
                    "id": "transition",
                    "resource_transition": {
                        "declaration": {},
                        "resource": {},
                        "request_bindings": {},
                    },
                }
            ],
        },
    )

    with pytest.raises(WorkflowValidationError) as excinfo:
        WorkflowLoader(tmp_path).load_bundle(workflow_file)

    assert "resource_transition is compiler-generated only" in str(excinfo.value)


def test_generated_resource_transition_step_serializes_into_core_ast(tmp_path: Path) -> None:
    workflow = _generated_surface_workflow(tmp_path)
    core_ast = build_core_workflow_ast(workflow, imports={}, provenance=workflow.provenance)

    executable, _projection = lower_surface_workflow(workflow)
    node = next(iter(executable.nodes.values()))
    runtime_step = RuntimeStep(node=node, name="Transition", step_id="transition")
    core_ast_json = workflow_core_ast_to_json(core_ast)

    assert node.kind is ExecutableNodeKind.RESOURCE_TRANSITION
    assert runtime_step["resource_transition"]["declaration"].transition.name == "drain/write_status"
    assert core_ast_json["body"][0]["kind"] == "resource_transition"


def test_generated_resource_transition_bundle_emits_semantic_effect_and_state_layout_roles(
    tmp_path: Path,
) -> None:
    workflow = _generated_surface_workflow(tmp_path, include_state_layout_allocations=True)
    bundle = build_loaded_workflow_bundle(workflow, imports={})

    effect = next(
        entry
        for entry in bundle.semantic_ir.effects.values()
        if entry.effect_kind == "resource_transition"
    )
    layout_kinds = {
        entry.layout_kind
        for entry in bundle.semantic_ir.state_layout.values()
    }

    assert effect.details["transition_kind"] == "resource_transition_runtime"
    assert effect.details["transition_name"] == "drain/write_status"
    assert effect.details["resource_kind"] == "drain_run_state"
    assert effect.details["backend_kind"] == "runtime_native"
    assert "resource_state" in layout_kinds
    assert "transition_audit" in layout_kinds


def test_executor_runs_generated_resource_transition_step(tmp_path: Path) -> None:
    workflow = _generated_surface_workflow(tmp_path)
    bundle = build_loaded_workflow_bundle(workflow, imports={})
    workflow.provenance.workflow_path.write_text("generated: true\n", encoding="utf-8")
    state_path = tmp_path / "state" / "transition" / "state.json"
    audit_path = tmp_path / "state" / "transition" / "audit.jsonl"
    _write_native_resource_state(state_path)

    state_manager = StateManager(workspace=tmp_path, run_id="resource-transition-runtime")
    state_manager.initialize("generated.yaml")

    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    step_result = state["steps"]["Transition"]
    persisted_state = json.loads(state_path.read_text(encoding="utf-8"))
    audit_rows = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert state["status"] == "completed"
    assert step_result["status"] == "completed"
    assert step_result["artifacts"]["return__status"] == "BLOCKED"
    assert step_result["debug"]["resource_transition"]["backend"] == "runtime_native"
    assert step_result["debug"]["resource_transition"]["version"].startswith("native:1:")
    assert persisted_state["state"]["drain_status"] == "BLOCKED"
    assert audit_rows[-1]["outcome_code"] == "committed"
    assert audit_rows[-1]["resource_kind"] == "drain_run_state"


def test_design_delta_runtime_transition_fixture_runs_via_real_cli(
    tmp_path: Path,
) -> None:
    result = _run_design_delta_runtime_transition_fixture_cli(tmp_path)

    assert result.returncode == 0, result.stderr
    native_state_paths = sorted(
        (tmp_path / "state" / "workflow_lisp").rglob("drain-run-state-state.json")
    )
    assert len(native_state_paths) == 1, native_state_paths
    run_state = json.loads(native_state_paths[0].read_text(encoding="utf-8"))["state"]
    assert run_state["drain_status"] == "BLOCKED"
    assert run_state["drain_status_reason"] == "runtime_native_fixture"
    assert run_state["drain_status_summary"] == "artifacts/work/drain_summary.json"
