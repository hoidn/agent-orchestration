"""Integration tests for runtime step lifecycle state updates."""

import importlib
import hashlib
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from tests.workflow_bundle_helpers import historical_workflow_lisp_bundle_context


REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
PURE_EXPR_SELECTOR_PROJECTION = VALID_FIXTURES / "pure_expr_selector_action_projection.orc"


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow), encoding="utf-8")
    return workflow_file


def _sticky_projection_error(
    offending_value: str = "root.removed",
) -> dict:
    return {
        "type": "resume_projection_integrity_error",
        "message": "Resume projection integrity audit failed: out_of_scope_step_id",
        "context": {
            "diagnostic_schema": "resume_projection_integrity_error.v1",
            "reason": "out_of_scope_step_id",
            "scope_path": [
                {"kind": "root", "workflow_file": "workflow.yaml"},
                {"kind": "call_frame", "frame_id": "root.invoke::visit::1"},
            ],
            "field": "current_step.step_id",
            "offending_value": offending_value,
            "expected_owner": {
                "workflow_file": "child.yaml",
                "workflow_checksum": "sha256:" + ("1" * 64),
                "projection_scope": "call_frame",
            },
            "candidate_count": 0,
            "call_boundary_step_id": None,
        },
    }


def _sticky_projection_result(
    error: dict | None = None,
) -> dict:
    return {
        "status": "failed",
        "exit_code": 2,
        "duration_ms": 0,
        "error": error or _sticky_projection_error(),
    }


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


def _materialize_view_bundle(tmp_path: Path):
    lowering_module = importlib.import_module("orchestrator.workflow.lowering")
    surface_ast = importlib.import_module("orchestrator.workflow.surface_ast")

    workflow = surface_ast.SurfaceWorkflow(
        version="2.14",
        name="materialize-view-lifecycle",
        steps=(
            surface_ast.SurfaceStep(
                name="MaterializeView",
                step_id="materialize_view",
                kind=surface_ast.SurfaceStepKind.MATERIALIZE_VIEW,
                common=surface_ast.SurfaceStepCommonConfig(),
                materialize_view={
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "view_renderer_schema_version": 1,
                    "value_type": {
                        "kind": "record",
                        "name": "SummaryValue",
                        "fields": [
                            {"name": "status", "type": {"kind": "primitive", "name": "String"}},
                        ],
                    },
                    "value_document": {"status": "DONE"},
                    "target_path": "artifacts/work/materialized-summary.json",
                    "target_allocation_id": None,
                    "authority_class": "materialized_view",
                    "output_contracts": {
                        "return": {
                            "kind": "relpath",
                            "type": "relpath",
                            "under": "artifacts/work",
                            "must_exist_target": True,
                        }
                    },
                },
            ),
        ),
        provenance=surface_ast.WorkflowProvenance(
            workflow_path=tmp_path / "generated.yaml",
            source_root=tmp_path,
        ),
    )
    return lowering_module.build_loaded_workflow_bundle(workflow, imports={})


def test_long_running_step_updates_current_step_heartbeat(tmp_path: Path):
    workflow = {
        "version": "1.1.1",
        "name": "runtime-step-lifecycle",
        "steps": [
            {
                "name": "LongCommand",
                "command": ["bash", "-lc", "python -c 'import time; time.sleep(0.6)'"],
            }
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(
        loaded,
        tmp_path,
        state_manager,
        step_heartbeat_interval_sec=0.1,
    )

    worker = threading.Thread(target=executor.execute)
    worker.start()

    state_file = tmp_path / ".orchestrate" / "runs" / "test-run" / "state.json"
    deadline = time.time() + 5
    running_snapshot = None
    while time.time() < deadline:
        if state_file.exists():
            snapshot = json.loads(state_file.read_text(encoding="utf-8"))
            current = snapshot.get("current_step")
            if isinstance(current, dict) and current.get("name") == "LongCommand":
                running_snapshot = snapshot
                break
        time.sleep(0.02)

    assert running_snapshot is not None
    first_heartbeat = running_snapshot["current_step"]["last_heartbeat_at"]

    time.sleep(0.25)
    second_snapshot = json.loads(state_file.read_text(encoding="utf-8"))
    assert second_snapshot.get("current_step", {}).get("name") == "LongCommand"
    assert second_snapshot["current_step"]["last_heartbeat_at"] != first_heartbeat

    worker.join(timeout=5)
    assert not worker.is_alive()

    final_snapshot = json.loads(state_file.read_text(encoding="utf-8"))
    assert final_snapshot.get("current_step") is None
    assert final_snapshot["steps"]["LongCommand"]["status"] == "completed"


def test_resumed_long_running_step_marks_run_running(tmp_path: Path):
    workflow = {
        "version": "1.1.1",
        "name": "resume-running-status",
        "steps": [
            {
                "name": "LongCommand",
                "command": ["bash", "-lc", "python -c 'import time; time.sleep(0.6)'"],
            }
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="resume-running-status")
    state_manager.initialize("workflow.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.workflow_checksum = f"sha256:{hashlib.sha256(workflow_file.read_bytes()).hexdigest()}"
    state_manager.state.steps = {
        "LongCommand": {"status": "failed", "exit_code": 1},
    }
    state_manager._write_state()

    executor = WorkflowExecutor(
        loaded,
        tmp_path,
        state_manager,
        step_heartbeat_interval_sec=0.1,
    )

    worker = threading.Thread(target=lambda: executor.execute(resume=True))
    worker.start()

    state_file = tmp_path / ".orchestrate" / "runs" / "resume-running-status" / "state.json"
    deadline = time.time() + 5
    running_snapshot = None
    while time.time() < deadline:
        if state_file.exists():
            snapshot = json.loads(state_file.read_text(encoding="utf-8"))
            current = snapshot.get("current_step")
            if isinstance(current, dict) and current.get("name") == "LongCommand":
                running_snapshot = snapshot
                break
        time.sleep(0.02)

    assert running_snapshot is not None
    assert running_snapshot["status"] == "running"

    worker.join(timeout=5)
    assert not worker.is_alive()


def test_assert_gate_persists_failed_outcome(tmp_path: Path):
    workflow = {
        "version": "1.5",
        "name": "assert-lifecycle",
        "steps": [
            {
                "name": "Gate",
                "assert": {
                    "equals": {
                        "left": "APPROVE",
                        "right": "REVISE",
                    }
                },
                "on": {"failure": {"goto": "_end"}},
            }
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="assert-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    gate = state["steps"]["Gate"]
    assert gate["status"] == "failed"
    assert gate["exit_code"] == 3
    assert gate["outcome"] == {
        "status": "failed",
        "phase": "execution",
        "class": "assert_failed",
        "retryable": False,
    }


def test_provider_pre_execution_failures_normalize_before_typed_routing(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "provider-pre-execution-lifecycle",
        "providers": {
            "write_file": {
                "command": [
                    "bash",
                    "-lc",
                    "printf '%s' \"${value}\" > state/provider-ran.txt",
                ]
            }
        },
        "steps": [
            {
                "name": "UseProvider",
                "provider": "write_file",
                "provider_params": {
                    "value": "${context.missing_value}",
                },
                "on": {"failure": {"goto": "CheckFailure"}},
            },
            {
                "name": "CheckFailure",
                "assert": {
                    "all_of": [
                        {
                            "compare": {
                                "left": {"ref": "root.steps.UseProvider.outcome.phase"},
                                "op": "eq",
                                "right": "pre_execution",
                            }
                        },
                        {
                            "compare": {
                                "left": {"ref": "root.steps.UseProvider.outcome.class"},
                                "op": "eq",
                                "right": "pre_execution_failed",
                            }
                        },
                    ]
                },
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="provider-pre-execution-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(on_error="continue")

    provider_step = state["steps"]["UseProvider"]
    assert provider_step["status"] == "failed"
    assert provider_step["error"]["type"] == "substitution_error"
    assert provider_step["outcome"] == {
        "status": "failed",
        "phase": "pre_execution",
        "class": "pre_execution_failed",
        "retryable": False,
    }
    assert not (tmp_path / "state" / "provider-ran.txt").exists()
    assert state["steps"]["CheckFailure"]["status"] == "completed"


def test_set_scalar_persists_local_artifacts_in_step_state(tmp_path: Path):
    workflow = {
        "version": "1.7",
        "name": "set-scalar-lifecycle",
        "artifacts": {
            "failed_count": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "steps": [
            {
                "name": "InitializeCount",
                "set_scalar": {
                    "artifact": "failed_count",
                    "value": 1,
                },
            }
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="set-scalar-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["steps"]["InitializeCount"]["status"] == "completed"
    assert state["steps"]["InitializeCount"]["artifacts"] == {"failed_count": 1}


def test_pure_projection_resume_reuses_committed_bundle(tmp_path: Path):
    loaded = _compile_pure_projection_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name

    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-resume")
    state_manager.initialize(
        str(PURE_EXPR_SELECTOR_PROJECTION),
        context=historical_workflow_lisp_bundle_context(loaded),
        bound_inputs={"approved": False, "status": "WAIT"},
    )

    first = WorkflowExecutor(loaded, tmp_path, state_manager).execute()

    assert first["steps"][step_name]["debug"]["pure_projection"]["reused_bundle"] is False

    state_manager.state.status = "failed"
    state_manager.state.steps = {step_name: {"status": "failed", "exit_code": 1}}
    state_manager._write_state()

    resumed = WorkflowExecutor(loaded, tmp_path, state_manager).execute(resume=True)
    default_resume_report = json.loads(
        state_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )

    assert resumed["steps"][step_name]["status"] == "completed"
    assert resumed["steps"][step_name]["artifacts"] == {"return__status": "WAIT", "return__ready": False}
    assert resumed["steps"][step_name]["debug"]["pure_projection"]["reused_bundle"] is True
    assert (
        default_resume_report["default_modes"][0]["mode"]
        == "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"
    )


def test_pure_projection_resume_fails_closed_on_schema_mismatch(tmp_path: Path):
    loaded = _compile_pure_projection_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name

    state_manager = StateManager(workspace=tmp_path, run_id="pure-projection-schema-mismatch")
    state_manager.initialize(
        str(PURE_EXPR_SELECTOR_PROJECTION),
        context=historical_workflow_lisp_bundle_context(loaded),
        bound_inputs={"approved": True, "status": "WAIT"},
    )

    WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    bundle_path = tmp_path / next(
        value
        for name, value in state_manager.state.bound_inputs.items()
        if name.startswith("__write_root__") and isinstance(value, str)
    )
    bundle_record = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_record["pure_expr_schema_version"] = 999
    bundle_path.write_text(json.dumps(bundle_record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    state_manager.state.status = "failed"
    state_manager.state.steps = {step_name: {"status": "failed", "exit_code": 1}}
    state_manager._write_state()

    resumed = WorkflowExecutor(loaded, tmp_path, state_manager).execute(resume=True)
    project = resumed["steps"][step_name]
    default_resume_report = json.loads(
        state_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )

    assert project["status"] == "failed"
    assert project["error"]["type"] == "pure_projection_resume_schema_mismatch"
    assert (
        default_resume_report["default_modes"][0]["mode"]
        == "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"
    )


def test_materialize_view_resume_reuses_committed_view(tmp_path: Path):
    loaded = _materialize_view_bundle(tmp_path)
    step_name = loaded.surface.steps[0].name
    loaded.surface.provenance.workflow_path.write_text("generated: true\n", encoding="utf-8")

    state_manager = StateManager(workspace=tmp_path, run_id="materialize-view-resume")
    state_manager.initialize("generated.yaml")

    first = WorkflowExecutor(loaded, tmp_path, state_manager).execute()

    assert first["steps"][step_name]["debug"]["materialize_view"]["reused_view"] is False

    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {step_name: {"status": "failed", "exit_code": 1}}
    state_manager._write_state()

    resumed = WorkflowExecutor(loaded, tmp_path, state_manager).execute(resume=True)

    assert resumed["steps"][step_name]["status"] == "completed"
    assert resumed["steps"][step_name]["artifacts"] == {"return": "artifacts/work/materialized-summary.json"}
    assert resumed["steps"][step_name]["debug"]["materialize_view"]["reused_view"] is True


def test_resume_skips_only_until_restart_point_not_after_loop_back(tmp_path: Path):
    workflow = {
        "version": "1.1",
        "name": "resume-loop-runtime",
        "steps": [
            {
                "name": "ReviewImplementation",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "count=$(cat state/review_count.txt 2>/dev/null || printf '0')",
                            "count=$((count + 1))",
                            "printf '%s\\n' \"$count\" > state/review_count.txt",
                            "if [ \"$count\" -ge 2 ]; then",
                            "  printf 'APPROVE\\n' > state/decision.txt",
                            "else",
                            "  printf 'REVISE\\n' > state/decision.txt",
                            "fi",
                            "printf 'review-%s\\n' \"$count\" >> state/history.log",
                        ]
                    ),
                ],
            },
            {
                "name": "ImplementationReviewGate",
                "command": ["bash", "-lc", "test \"$(cat state/decision.txt)\" = APPROVE"],
                "on": {"success": {"goto": "_end"}, "failure": {"goto": "ImplementationCycleGate"}},
            },
            {
                "name": "ImplementationCycleGate",
                "command": ["bash", "-lc", "test \"$(cat state/cycle.txt)\" -lt 20"],
                "on": {"success": {"goto": "FixImplementation"}, "failure": {"goto": "MaxImplementationCyclesExceeded"}},
            },
            {
                "name": "FixImplementation",
                "command": ["bash", "-lc", "printf 'fix\\n' >> state/history.log"],
                "on": {"success": {"goto": "IncrementImplementationCycle"}},
            },
            {
                "name": "IncrementImplementationCycle",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "count=$(cat state/cycle.txt 2>/dev/null || printf '0')",
                            "count=$((count + 1))",
                            "printf '%s\\n' \"$count\" > state/cycle.txt",
                            "printf 'increment-%s\\n' \"$count\" >> state/history.log",
                        ]
                    ),
                ],
                "on": {"success": {"goto": "ReviewImplementation"}},
            },
            {
                "name": "MaxImplementationCyclesExceeded",
                "command": ["bash", "-lc", "printf 'maxed\\n' >> state/history.log && exit 1"],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "review_count.txt").write_text("1\n")
    (state_dir / "cycle.txt").write_text("1\n")
    (state_dir / "decision.txt").write_text("REVISE\n")
    (state_dir / "history.log").write_text("review-1\nfix\nincrement-1\n")

    state_manager = StateManager(workspace=tmp_path, run_id="resume-loop-runtime")
    state_manager.initialize("workflow.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.workflow_checksum = f"sha256:{hashlib.sha256(workflow_file.read_bytes()).hexdigest()}"
    state_manager.state.steps = {
        "ReviewImplementation": {"status": "completed", "exit_code": 0, "visit_count": 1},
        "ImplementationReviewGate": {"status": "failed", "exit_code": 1, "visit_count": 1},
        "ImplementationCycleGate": {"status": "completed", "exit_code": 0, "visit_count": 1},
        "FixImplementation": {"status": "completed", "exit_code": 0, "visit_count": 1},
        "IncrementImplementationCycle": {"status": "completed", "exit_code": 0, "visit_count": 1},
    }
    state_manager.state.step_visits = {
        "ReviewImplementation": 1,
        "ImplementationReviewGate": 1,
        "ImplementationCycleGate": 1,
        "FixImplementation": 1,
        "IncrementImplementationCycle": 1,
    }
    state_manager._write_state()
    state_manager.load()

    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(resume=True)

    assert state["status"] == "completed"
    assert (state_dir / "review_count.txt").read_text() == "2\n"
    history = (state_dir / "history.log").read_text()
    assert "review-2\n" in history
    assert "maxed\n" not in history


def test_resume_restart_index_skips_completed_top_level_for_each(tmp_path: Path):
    workflow = {
        "version": "1.1",
        "name": "resume-foreach-restart",
        "steps": [
            {"name": "Generate", "command": ["bash", "-lc", "printf 'generate\\n' >> state/history.log"]},
            {
                "name": "Loop",
                "for_each": {
                    "items": ["a", "b"],
                    "steps": [
                        {
                            "name": "Inner",
                            "command": ["bash", "-lc", "printf 'inner-${item}\\n' >> state/history.log"],
                        }
                    ],
                },
            },
            {"name": "After", "command": ["bash", "-lc", "printf 'after\\n' >> state/history.log"]},
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="resume-foreach-run")
    state_manager.initialize("workflow.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.workflow_checksum = f"sha256:{hashlib.sha256(workflow_file.read_bytes()).hexdigest()}"
    state_manager.state.steps = {
        "Generate": {"status": "completed", "exit_code": 0},
        "Loop": [{"status": "completed"}, {"status": "completed"}],
        "Loop[0].Inner": {"status": "completed", "exit_code": 0},
        "Loop[1].Inner": {"status": "completed", "exit_code": 0},
        "After": {"status": "failed", "exit_code": 1},
    }
    state_manager._write_state()

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    restart_index = executor._determine_resume_restart_index(state_manager.load().to_dict())

    assert restart_index == 2


def test_looped_resume_exposes_active_visit_count(tmp_path: Path):
    workflow = {
        "version": "1.1",
        "name": "resume-visit-observability",
        "steps": [
            {
                "name": "ReviewImplementation",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "count=$(cat state/review_count.txt 2>/dev/null || printf '0')",
                            "count=$((count + 1))",
                            "printf '%s\\n' \"$count\" > state/review_count.txt",
                            "if [ \"$count\" -ge 2 ]; then",
                            "  printf 'APPROVE\\n' > state/decision.txt",
                            "else",
                            "  printf 'REVISE\\n' > state/decision.txt",
                            "fi",
                            "python -c 'import time; time.sleep(0.6)'",
                            "printf 'review-%s\\n' \"$count\" >> state/history.log",
                        ]
                    ),
                ],
            },
            {
                "name": "ImplementationReviewGate",
                "command": ["bash", "-lc", "test \"$(cat state/decision.txt)\" = APPROVE"],
                "on": {"success": {"goto": "_end"}, "failure": {"goto": "ImplementationCycleGate"}},
            },
            {
                "name": "ImplementationCycleGate",
                "command": ["bash", "-lc", "test \"$(cat state/cycle.txt)\" -lt 20"],
                "on": {"success": {"goto": "FixImplementation"}, "failure": {"goto": "MaxImplementationCyclesExceeded"}},
            },
            {
                "name": "FixImplementation",
                "command": ["bash", "-lc", "printf 'fix\\n' >> state/history.log"],
                "on": {"success": {"goto": "IncrementImplementationCycle"}},
            },
            {
                "name": "IncrementImplementationCycle",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "count=$(cat state/cycle.txt 2>/dev/null || printf '0')",
                            "count=$((count + 1))",
                            "printf '%s\\n' \"$count\" > state/cycle.txt",
                            "printf 'increment-%s\\n' \"$count\" >> state/history.log",
                        ]
                    ),
                ],
                "on": {"success": {"goto": "ReviewImplementation"}},
            },
            {
                "name": "MaxImplementationCyclesExceeded",
                "command": ["bash", "-lc", "printf 'maxed\\n' >> state/history.log && exit 1"],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "review_count.txt").write_text("1\n")
    (state_dir / "cycle.txt").write_text("1\n")
    (state_dir / "decision.txt").write_text("REVISE\n")
    (state_dir / "history.log").write_text("review-1\nfix\nincrement-1\n")

    state_manager = StateManager(workspace=tmp_path, run_id="resume-visit-observability")
    state_manager.initialize("workflow.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.workflow_checksum = f"sha256:{hashlib.sha256(workflow_file.read_bytes()).hexdigest()}"
    state_manager.state.steps = {
        "ReviewImplementation": {"status": "completed", "exit_code": 0, "visit_count": 1},
        "ImplementationReviewGate": {"status": "failed", "exit_code": 1, "visit_count": 1},
        "ImplementationCycleGate": {"status": "completed", "exit_code": 0, "visit_count": 1},
        "FixImplementation": {"status": "completed", "exit_code": 0, "visit_count": 1},
        "IncrementImplementationCycle": {"status": "completed", "exit_code": 0, "visit_count": 1},
    }
    state_manager.state.step_visits = {
        "ReviewImplementation": 1,
        "ImplementationReviewGate": 1,
        "ImplementationCycleGate": 1,
        "FixImplementation": 1,
        "IncrementImplementationCycle": 1,
    }
    state_manager._write_state()

    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)
    executor = WorkflowExecutor(
        loaded,
        tmp_path,
        state_manager,
        step_heartbeat_interval_sec=0.1,
    )

    worker = threading.Thread(target=lambda: executor.execute(resume=True))
    worker.start()

    state_file = tmp_path / ".orchestrate" / "runs" / "resume-visit-observability" / "state.json"
    deadline = time.time() + 5
    running_snapshot = None
    while time.time() < deadline:
        if state_file.exists():
            snapshot = json.loads(state_file.read_text(encoding="utf-8"))
            current = snapshot.get("current_step")
            if isinstance(current, dict) and current.get("name") == "ReviewImplementation":
                running_snapshot = snapshot
                break
        time.sleep(0.02)

    assert running_snapshot is not None
    assert running_snapshot["current_step"]["visit_count"] == 2
    assert running_snapshot["steps"]["ReviewImplementation"]["visit_count"] == 1

    worker.join(timeout=5)
    assert not worker.is_alive()


@pytest.mark.parametrize("route_kind", ["failure", "success", "always"])
def test_projection_error_bypasses_failure_success_always_and_on_error_continue(
    tmp_path: Path,
    route_kind: str,
) -> None:
    workflow = {
        "version": "2.0",
        "name": f"sticky-route-{route_kind}",
        "steps": [
            {
                "name": "Invoke",
                "id": "invoke",
                "command": ["bash", "-lc", "true"],
                "on": {route_kind: {"goto": "Routed"}},
            },
            {
                "name": "Routed",
                "id": "routed",
                "command": ["bash", "-lc", "true"],
            },
        ],
    }
    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    manager = StateManager(
        workspace=tmp_path,
        run_id=f"sticky-route-{route_kind}",
    )
    manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, manager)
    state = manager.load().to_dict()
    state["steps"]["Invoke"] = _sticky_projection_result()
    step = loaded.surface.steps[0]

    with patch.object(
        executor,
        "_typed_on_goto_transfer",
        side_effect=AssertionError("sticky result reached authored routing"),
    ) as authored_routes:
        next_step = executor._handle_control_flow(
            step,
            state,
            "Invoke",
            0,
            "continue",
            current_node_id="root.invoke",
        )

    assert next_step == "_stop"
    assert state["error"] == _sticky_projection_error()
    assert manager.load().error == _sticky_projection_error()
    authored_routes.assert_not_called()


@pytest.mark.parametrize("loop_kind", ["for_each", "repeat_until"])
def test_projection_error_exits_for_each_and_repeat_until_without_next_iteration(
    tmp_path: Path,
    loop_kind: str,
) -> None:
    child_path = tmp_path / "child.yaml"
    child_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.7" if loop_kind == "repeat_until" else "2.5",
                "name": "sticky-loop-child",
                "artifacts": {"ready": {"kind": "scalar", "type": "bool"}},
                "outputs": {
                    "ready": {
                        "kind": "scalar",
                        "type": "bool",
                        "from": {"ref": "root.steps.Ready.artifacts.ready"},
                    }
                },
                "steps": [
                    {
                        "name": "Ready",
                        "id": "ready",
                        "set_scalar": {"artifact": "ready", "value": True},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loop_body = [
        {
            "name": "Invoke",
            "id": "invoke",
            "call": "child",
        }
    ]
    loop_step = {
        "name": "Loop",
        "id": "loop",
    }
    if loop_kind == "for_each":
        loop_step["for_each"] = {
            "items": [1, 2],
            "as": "item",
            "steps": loop_body,
        }
    else:
        loop_step["repeat_until"] = {
            "id": "body",
            "max_iterations": 3,
            "outputs": {
                "ready": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "self.steps.Invoke.artifacts.ready"},
                }
            },
            "condition": {"artifact_bool": {"ref": "self.outputs.ready"}},
            "steps": loop_body,
        }
    workflow_file = _write_workflow(
        tmp_path,
        {
            "version": "2.7" if loop_kind == "repeat_until" else "2.5",
            "name": f"sticky-{loop_kind}",
            "imports": {"child": "child.yaml"},
            "steps": [loop_step],
        },
    )
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    manager = StateManager(
        workspace=tmp_path,
        run_id=f"sticky-{loop_kind}",
    )
    manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, manager)
    call_count = 0

    def fail_call(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return _sticky_projection_result()

    with patch.object(executor, "_execute_call", side_effect=fail_call):
        result = executor.execute(on_error="continue")

    persisted = manager.load().to_dict()
    assert call_count == 1
    assert result["status"] == "failed"
    assert result["error"] == _sticky_projection_error()
    assert persisted["error"] == _sticky_projection_error()
    assert persisted["steps"]["Loop[0].Invoke"]["error"] == _sticky_projection_error()
    if loop_kind == "for_each":
        assert "Loop[1].Invoke" not in persisted["steps"]
        assert persisted["for_each"]["Loop"]["completed_indices"] == []
        assert persisted["for_each"]["Loop"]["current_index"] == 0
    else:
        assert persisted["steps"]["Loop"]["error"] == _sticky_projection_error()
        assert persisted["repeat_until"]["Loop"]["current_iteration"] == 0


def test_projection_error_finalization_failure_is_supplemental(
    tmp_path: Path,
) -> None:
    child_path = tmp_path / "child.yaml"
    child_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.5",
                "name": "sticky-finalization-child",
                "steps": [
                    {
                        "name": "Noop",
                        "id": "noop",
                        "command": ["bash", "-lc", "true"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    workflow_file = _write_workflow(
        tmp_path,
        {
            "version": "2.5",
            "name": "sticky-finalization",
            "imports": {"child": "child.yaml"},
            "steps": [
                {
                    "name": "Invoke",
                    "id": "invoke",
                    "call": "child",
                }
            ],
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "FailCleanup",
                        "id": "fail_cleanup",
                        "command": [
                            "bash",
                            "-lc",
                            "mkdir -p state && printf cleanup > state/cleanup-ran && exit 1",
                        ],
                    }
                ],
            },
        },
    )
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    manager = StateManager(
        workspace=tmp_path,
        run_id="sticky-finalization",
    )
    manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, manager)

    with patch.object(
        executor,
        "_execute_call",
        return_value=_sticky_projection_result(),
    ):
        result = executor.execute()

    persisted = manager.load().to_dict()
    assert (tmp_path / "state" / "cleanup-ran").read_text(encoding="utf-8") == "cleanup"
    assert result["status"] == "failed"
    assert result["error"] == _sticky_projection_error()
    assert persisted["error"] == _sticky_projection_error()
    assert persisted["steps"]["Invoke"]["error"] == _sticky_projection_error()
    assert persisted["finalization"]["status"] == "failed"
    assert persisted["finalization"]["failure"]["step"] == "finally.FailCleanup"
    assert persisted["finalization"]["failure"]["error"] is None
    assert persisted["steps"]["finally.FailCleanup"]["exit_code"] == 1


def test_projection_error_finalization_sticky_failure_is_supplemental(
    tmp_path: Path,
) -> None:
    child_path = tmp_path / "child.yaml"
    child_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.5",
                "name": "sticky-finalization-precedence-child",
                "steps": [
                    {
                        "name": "Noop",
                        "id": "noop",
                        "command": ["bash", "-lc", "true"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    workflow_file = _write_workflow(
        tmp_path,
        {
            "version": "2.5",
            "name": "sticky-finalization-precedence",
            "imports": {"child": "child.yaml"},
            "steps": [
                {
                    "name": "InvokeBody",
                    "id": "invoke_body",
                    "call": "child",
                }
            ],
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "InvokeCleanup",
                        "id": "invoke_cleanup",
                        "command": ["bash", "-lc", "true"],
                    }
                ],
            },
        },
    )
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    manager = StateManager(
        workspace=tmp_path,
        run_id="sticky-finalization-precedence",
    )
    manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, manager)
    body_error = _sticky_projection_error("root.removed_body")
    cleanup_error = _sticky_projection_error("root.removed_cleanup")

    with patch.object(
        executor,
        "_execute_call",
        return_value=_sticky_projection_result(body_error),
    ), patch.object(
        executor,
        "_execute_command",
        return_value=_sticky_projection_result(cleanup_error),
    ):
        result = executor.execute()

    persisted = manager.load().to_dict()
    assert result["status"] == "failed"
    assert result["error"] == body_error
    assert persisted["error"] == body_error
    assert persisted["steps"]["InvokeBody"]["error"] == body_error
    assert persisted["steps"]["finally.InvokeCleanup"]["error"] == cleanup_error
    assert persisted["finalization"]["status"] == "failed"
    assert persisted["finalization"]["failure"] == {
        "step": "finally.InvokeCleanup",
        "step_id": "root.finally.cleanup.invoke_cleanup",
        "error": cleanup_error,
    }


def test_projection_error_in_finalization_promotes_without_prior_sticky_error(
    tmp_path: Path,
) -> None:
    workflow_file = _write_workflow(
        tmp_path,
        {
            "version": "2.5",
            "name": "sticky-finalization-only",
            "steps": [
                {
                    "name": "CompleteBody",
                    "id": "complete_body",
                    "command": ["bash", "-lc", "true"],
                }
            ],
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "InvokeCleanup",
                        "id": "invoke_cleanup",
                        "command": ["bash", "-lc", "true"],
                    }
                ],
            },
        },
    )
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    manager = StateManager(
        workspace=tmp_path,
        run_id="sticky-finalization-only",
    )
    manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, manager)
    cleanup_error = _sticky_projection_error("root.removed_cleanup")

    with patch.object(
        executor,
        "_execute_command",
        side_effect=[
            {"status": "completed", "exit_code": 0, "duration_ms": 0},
            _sticky_projection_result(cleanup_error),
        ],
    ):
        result = executor.execute()

    persisted = manager.load().to_dict()
    assert result["status"] == "failed"
    assert result["error"] == cleanup_error
    assert persisted["error"] == cleanup_error
    assert persisted["finalization"]["failure"]["error"] == cleanup_error
