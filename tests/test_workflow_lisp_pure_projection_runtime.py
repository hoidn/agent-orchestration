from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.pure_expr import pure_expr_payload_digest
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
PURE_EXPR_LOOP_COUNTER = VALID_FIXTURES / "pure_expr_loop_counter.orc"
PURE_EXPR_SELECTOR_PROJECTION = VALID_FIXTURES / "pure_expr_selector_action_projection.orc"


def _write_yaml(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_authored_pure_projection_workflow(workspace: Path) -> Path:
    payload = {
        "pure_expr_schema_version": 1,
        "result_type": {
            "kind": "record",
            "name": "ProjectionOutput",
            "fields": [
                {"name": "status", "type": {"kind": "primitive", "name": "String"}},
            ],
        },
        "bindings": {
            "maybe_reason": {
                "type": {
                    "kind": "optional",
                    "item": {"kind": "primitive", "name": "String"},
                }
            }
        },
        "expr": {
            "kind": "record",
            "type": {
                "kind": "record",
                "name": "ProjectionOutput",
                "fields": [
                    {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                ],
            },
            "fields": [
                {
                    "name": "status",
                    "value": {
                        "kind": "op",
                        "operator": "or-else",
                        "args": [
                            {"kind": "binding", "name": "maybe_reason"},
                            {
                                "kind": "literal",
                                "type": {"kind": "primitive", "name": "String"},
                                "value": "fallback",
                            },
                        ],
                    },
                }
            ],
        },
    }
    return _write_yaml(
        workspace / "workflow.yaml",
        {
            "version": "2.14",
            "name": "pure-projection-runtime",
            "outputs": {
                "status": {
                    "kind": "scalar",
                    "type": "string",
                    "from": {"ref": "root.steps.Project.artifacts.return__status"},
                }
            },
            "steps": [
                {
                    "name": "Project",
                    "id": "project",
                    "output_bundle": {
                        "path": "state/pure_projection/project.json",
                        "fields": [
                            {
                                "name": "return__status",
                                "json_pointer": "/result/status",
                                "type": "string",
                            }
                        ],
                    },
                    "pure_projection": {
                        "payload": payload,
                        "binding_refs": {"maybe_reason": {"ref": "inputs.maybe_reason"}},
                        "payload_digest": pure_expr_payload_digest(payload),
                        "output_contracts": {
                            "return__status": {"kind": "scalar", "type": "string"},
                        },
                    },
                }
            ],
        },
    )


def _compile_pure_projection_bundle(tmp_path: Path):
    result = compile_stage3_entrypoint(
        PURE_EXPR_SELECTOR_PROJECTION,
        source_roots=(VALID_FIXTURES,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["pure_expr_selector_action_projection::orchestrate"]


def _compile_runtime_overflow_bundle(tmp_path: Path):
    module_path = tmp_path / "pure_expr_runtime_overflow.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule pure_expr_runtime_overflow)",
                "  (export project)",
                "  (defrecord OverflowResult",
                "    (count Int))",
                "  (defworkflow project",
                "    ((count Int))",
                "    -> OverflowResult",
                "    (record OverflowResult",
                "      :count (+ count 1))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return result.validated_bundles_by_name["pure_expr_runtime_overflow::project"]


def _resume_failed_single_step(state_manager: StateManager, *, step_name: str) -> None:
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {step_name: {"status": "failed", "exit_code": 1}}
    state_manager._write_state()


def _compiled_bundle_path(workspace: Path, state_manager: StateManager) -> Path:
    assert state_manager.state is not None
    relative_path = next(
        value
        for name, value in state_manager.state.bound_inputs.items()
        if name.startswith("__write_root__") and isinstance(value, str)
    )
    return workspace / relative_path


def test_loader_rejects_authored_pure_projection_step(tmp_path: Path) -> None:
    workflow_file = _write_authored_pure_projection_workflow(tmp_path)

    with pytest.raises(WorkflowValidationError) as excinfo:
        WorkflowLoader(tmp_path).load_bundle(workflow_file)

    assert "pure_projection is compiler-generated only" in str(excinfo.value)


def test_compile_stage3_entrypoint_emits_visible_pure_projection_step(tmp_path: Path) -> None:
    bundle = _compile_pure_projection_bundle(tmp_path)

    assert [step.kind.value for step in bundle.surface.steps] == ["pure_projection"]
    assert bundle.surface.steps[0].pure_projection["payload"]["pure_expr_schema_version"] == 1


def test_pure_projection_runtime_reuses_committed_bundle_on_resume(tmp_path: Path) -> None:
    loaded = _compile_pure_projection_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name
    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-runtime")
    state_manager.initialize(str(PURE_EXPR_SELECTOR_PROJECTION), bound_inputs={"approved": False, "status": "WAIT"})

    first = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    _resume_failed_single_step(state_manager, step_name=step_name)
    resumed = WorkflowExecutor(loaded, tmp_path, state_manager).execute(resume=True)

    assert first["steps"][step_name]["debug"]["pure_projection"]["reused_bundle"] is False
    assert resumed["steps"][step_name]["artifacts"] == {"return__status": "WAIT", "return__ready": False}
    assert resumed["steps"][step_name]["debug"]["pure_projection"]["reused_bundle"] is True


def test_pure_projection_runtime_fails_closed_when_resume_bundle_schema_changes(tmp_path: Path) -> None:
    loaded = _compile_pure_projection_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name
    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-schema")
    state_manager.initialize(str(PURE_EXPR_SELECTOR_PROJECTION), bound_inputs={"approved": True, "status": "WAIT"})

    WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    bundle_path = _compiled_bundle_path(tmp_path, state_manager)
    bundle_record = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_record["pure_expr_schema_version"] = 999
    bundle_path.write_text(json.dumps(bundle_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _resume_failed_single_step(state_manager, step_name=step_name)
    resumed = WorkflowExecutor(loaded, tmp_path, state_manager).execute(resume=True)

    assert resumed["steps"][step_name]["status"] == "failed"
    assert resumed["steps"][step_name]["error"]["type"] == "pure_projection_resume_schema_mismatch"


def test_pure_projection_runtime_surfaces_typed_evaluator_failure_codes(tmp_path: Path) -> None:
    loaded = _compile_runtime_overflow_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name
    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-overflow")
    state_manager.initialize(str(tmp_path / "pure_expr_runtime_overflow.orc"), bound_inputs={"count": 9223372036854775807})

    result = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    project = result["steps"][step_name]

    assert project["status"] == "failed"
    assert project["error"]["type"] == "pure_expr_overflow"


def test_compile_rejects_oversized_pure_projection_region(tmp_path: Path) -> None:
    field_count = 260
    record_fields = "\n".join(f"    (f{index} Int)" for index in range(field_count))
    base_fields = "\n".join(f"        :f{index} seed" for index in range(field_count))
    updated_fields = "\n".join(f"      :f{index} (+ seed 1)" for index in range(field_count))
    module_path = tmp_path / "oversized.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule oversized)",
                "  (export run)",
                "  (defrecord Box",
                record_fields,
                "  )",
                "  (defworkflow run",
                "    ((seed Int))",
                "    -> Box",
                "    (record-update",
                "      (record Box",
                base_fields,
                "      )",
                updated_fields,
                "    ))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            module_path,
            source_roots=(tmp_path,),
            provider_externs={},
            prompt_externs={},
            command_boundaries={},
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "pure_expr_payload_too_large"


def test_cli_dry_run_executes_loop_counter_fixture(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "run",
            str(PURE_EXPR_LOOP_COUNTER),
            "--entry-workflow",
            "run-counter",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
