from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from orchestrator.runtime_observability import (
    close_executor_session,
    compute_active_runtime,
    format_duration,
    open_executor_session,
    record_compiled_frontend_provenance,
    reconcile_open_sessions,
)
from orchestrator.monitor.process import write_process_metadata
from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.surface_ast import WorkflowProvenance


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_compute_active_runtime_sums_closed_sessions():
    state = {
        "runtime_observability": {
            "schema_version": 1,
            "executor_sessions": [
                {
                    "session_id": "exec-0001",
                    "started_at": "2026-04-29T10:00:00Z",
                    "ended_at": "2026-04-29T10:20:00Z",
                    "status": "completed",
                    "duration_ms": 1_200_000,
                }
            ],
        }
    }

    snapshot = compute_active_runtime(state, now=dt("2026-04-29T12:00:00Z"))

    assert snapshot["active_runtime_ms"] == 1_200_000
    assert snapshot["active_runtime"] == "20m 0s"
    assert snapshot["executor_session_count"] == 1


def test_compute_active_runtime_excludes_gap_between_sessions():
    state = {
        "runtime_observability": {
            "schema_version": 1,
            "executor_sessions": [
                {
                    "session_id": "exec-0001",
                    "started_at": "2026-04-29T10:00:00Z",
                    "ended_at": "2026-04-29T10:20:00Z",
                    "status": "failed",
                    "duration_ms": 1_200_000,
                },
                {
                    "session_id": "exec-0002",
                    "started_at": "2026-04-29T22:15:00Z",
                    "ended_at": None,
                    "status": "running",
                    "duration_ms": None,
                    "pid": 123,
                },
            ],
        }
    }

    snapshot = compute_active_runtime(
        state,
        now=dt("2026-04-29T22:20:00Z"),
        process_is_live=lambda session: True,
    )

    assert snapshot["active_runtime_ms"] == 1_500_000
    assert snapshot["active_runtime"] == "25m 0s"
    assert snapshot["excluded_suspended_ms"] == 42_900_000
    assert snapshot["suspended_gap_excluded"] == "11h 55m 0s"


def test_compute_active_runtime_missing_field_is_unknown():
    snapshot = compute_active_runtime({}, now=dt("2026-04-29T12:00:00Z"))

    assert snapshot["active_runtime_ms"] is None
    assert snapshot["active_runtime"] is None
    assert snapshot["executor_session_count"] == 0


def test_format_duration_uses_compact_units():
    assert format_duration(None) is None
    assert format_duration(4_000) == "4s"
    assert format_duration(65_000) == "1m 5s"
    assert format_duration(3_665_000) == "1h 1m 5s"


def test_open_and_close_executor_sessions_are_idempotent():
    state = {"updated_at": "2026-04-29T10:00:00Z"}

    session_id = open_executor_session(
        state,
        entrypoint="run",
        pid=123,
        process_start_time="proc-start",
        now=dt("2026-04-29T10:00:00Z"),
    )
    close_executor_session(
        state,
        session_id=session_id,
        status="completed",
        now=dt("2026-04-29T10:05:00Z"),
    )
    close_executor_session(
        state,
        session_id=session_id,
        status="failed",
        now=dt("2026-04-29T10:10:00Z"),
    )

    session = state["runtime_observability"]["executor_sessions"][0]
    assert session["session_id"] == "exec-0001"
    assert session["entrypoint"] == "run"
    assert session["status"] == "completed"
    assert session["duration_ms"] == 300_000


def test_reconcile_open_sessions_marks_dead_session_abandoned():
    state = {
        "updated_at": "2026-04-29T10:07:00Z",
        "runtime_observability": {
            "schema_version": 1,
            "executor_sessions": [
                {
                    "session_id": "exec-0001",
                    "entrypoint": "run",
                    "pid": 123,
                    "process_start_time": "old-proc",
                    "started_at": "2026-04-29T10:00:00Z",
                    "ended_at": None,
                    "status": "running",
                    "duration_ms": None,
                }
            ],
        },
    }

    reconcile_open_sessions(state, process_is_live=lambda session: False)

    session = state["runtime_observability"]["executor_sessions"][0]
    assert session["status"] == "abandoned"
    assert session["ended_at"] == "2026-04-29T10:07:00+00:00"
    assert session["duration_ms"] == 420_000


def test_state_round_trips_runtime_observability(tmp_path: Path):
    workflow = tmp_path / "workflow.yaml"
    workflow.write_text("version: '1.0'\nname: test\nsteps: []\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="runtime-state")
    state = manager.initialize("workflow.yaml")

    state.runtime_observability = {
        "schema_version": 1,
        "executor_sessions": [{"session_id": "exec-0001", "status": "completed"}],
    }
    manager._write_state()

    loaded = StateManager(tmp_path, run_id="runtime-state").load()

    assert loaded.runtime_observability == state.runtime_observability


def test_record_compiled_frontend_provenance_persists_bridge_fields():
    state = {}

    record_compiled_frontend_provenance(
        state,
        WorkflowProvenance(
            workflow_path=Path("/tmp/workflow.orc"),
            source_root=Path("/tmp"),
            frontend_kind="workflow_lisp",
            frontend_build_root=Path("/tmp/.orchestrate/build/abc123"),
            frontend_source_trace_path=Path("/tmp/.orchestrate/build/abc123/source_map.json"),
            frontend_entry_workflow="orchestrate",
            frontend_source_map_schema_version="workflow_lisp_source_map.v1",
            frontend_source_map_coverage={
                "frontend_ast": "covered",
                "lowered_surface": "covered",
                "shared_validation_subjects": "covered",
                "executable_ir": "covered",
                "runtime_logs": "covered",
                "core_workflow_ast": "covered",
                "semantic_ir": "covered",
            },
        ),
    )

    assert state["runtime_observability"]["compiled_frontend"] == {
        "frontend_kind": "workflow_lisp",
        "frontend_build_root": "/tmp/.orchestrate/build/abc123/",
        "frontend_source_trace_path": "/tmp/.orchestrate/build/abc123/source_map.json",
        "frontend_entry_workflow": "orchestrate",
        "source_map_schema_version": "workflow_lisp_source_map.v1",
        "source_map_coverage": {
            "frontend_ast": "covered",
            "lowered_surface": "covered",
            "shared_validation_subjects": "covered",
            "executable_ir": "covered",
            "runtime_logs": "covered",
            "core_workflow_ast": "covered",
            "semantic_ir": "covered",
        },
    }


def test_compiled_frontend_source_context_prefers_executable_node_lineage_over_step_ids(tmp_path: Path):
    source_map = tmp_path / "source_map.json"
    source_map.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_source_map.v1",
                "coverage": {
                "frontend_ast": "covered",
                "lowered_surface": "covered",
                "shared_validation_subjects": "covered",
                "executable_ir": "covered",
                "runtime_logs": "covered",
                "core_workflow_ast": "covered",
                "semantic_ir": "covered",
            },
                "workflows": {
                    "pkg/entry::run": {
                        "display_name": "run",
                        "selected_entry_workflow": True,
                        "workflow_name": "pkg/entry::run",
                        "workflow_origin": {
                            "origin_key": "pkg/entry::run::workflow::pkg/entry::run",
                            "entity_kind": "workflow",
                            "workflow_name": "pkg/entry::run",
                            "path": "workflow.orc",
                            "line": 1,
                            "column": 1,
                            "end_line": 1,
                            "end_column": 5,
                            "form_path": ["workflow-lisp", "defworkflow", "run"],
                            "module_name": "pkg/entry",
                            "expansion_stack": [],
                            "notes": [],
                            "generated_name_origin": "pkg/entry::run",
                        },
                        "step_ids": {
                            "run__command": {
                                "origin_key": "pkg/entry::run::step_id::run__command",
                                "entity_kind": "step_id",
                                "workflow_name": "pkg/entry::run",
                                "path": "step.orc",
                                "line": 10,
                                "column": 3,
                                "end_line": 10,
                                "end_column": 7,
                                "form_path": ["workflow-lisp", "defworkflow", "run", "command-result"],
                                "module_name": "pkg/entry",
                                "expansion_stack": [],
                                "notes": [],
                                "generated_name_origin": "run__command",
                            }
                        },
                        "generated_inputs": {},
                        "generated_outputs": {},
                        "generated_paths": {},
                        "generated_internal_inputs": {},
                        "command_boundaries": [],
                        "validation_subjects": [],
                        "executable_nodes": [
                            {
                                "node_id": "root.run__command",
                                "step_id": "run__command",
                                "kind": "command",
                                "region": "body",
                                "origin_key": "pkg/entry::run::workflow::pkg/entry::run",
                                "presentation_name": "run__command",
                            }
                        ],
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    provenance = WorkflowProvenance(
        workflow_path=tmp_path / "workflow.orc",
        source_root=tmp_path,
        frontend_kind="workflow_lisp",
        frontend_build_root=tmp_path,
        frontend_source_trace_path=source_map,
        frontend_entry_workflow="pkg/entry::run",
    )
    executor._compiled_frontend_kind = "workflow_lisp"
    executor._compiled_frontend_step_origins = executor._load_compiled_frontend_step_origins(provenance)
    executor._compiled_frontend_node_origins = executor._load_compiled_frontend_node_origins(provenance)

    origin = executor._compiled_frontend_origin_for_step(
        "run__command",
        "run__command",
        node_id="root.run__command",
    )

    assert origin["path"] == "workflow.orc"


def test_compiled_frontend_source_context_logs_certified_adapter_metadata(tmp_path: Path, caplog):
    source_map = tmp_path / "source_map.json"
    source_map.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_source_map.v1",
                "coverage": {
                    "frontend_ast": "covered",
                    "lowered_surface": "covered",
                    "shared_validation_subjects": "covered",
                    "executable_ir": "covered",
                    "runtime_logs": "covered",
                    "core_workflow_ast": "covered",
                    "semantic_ir": "covered",
                },
                "workflows": {
                    "pkg/entry::run": {
                        "display_name": "run",
                        "selected_entry_workflow": True,
                        "workflow_name": "pkg/entry::run",
                        "workflow_origin": {
                            "origin_key": "pkg/entry::run::workflow::pkg/entry::run",
                            "entity_kind": "workflow",
                            "workflow_name": "pkg/entry::run",
                            "path": "workflow.orc",
                            "line": 1,
                            "column": 1,
                            "end_line": 1,
                            "end_column": 5,
                            "form_path": ["workflow-lisp", "defworkflow", "run"],
                            "module_name": "pkg/entry",
                            "expansion_stack": [],
                            "notes": [],
                            "generated_name_origin": "pkg/entry::run",
                        },
                        "step_ids": {
                            "run__adapter": {
                                "origin_key": "pkg/entry::run::step_id::run__adapter",
                                "entity_kind": "step_id",
                                "workflow_name": "pkg/entry::run",
                                "path": "adapter.orc",
                                "line": 7,
                                "column": 3,
                                "end_line": 7,
                                "end_column": 9,
                                "form_path": ["workflow-lisp", "defworkflow", "run", "command-result"],
                                "module_name": "pkg/entry",
                                "expansion_stack": [],
                                "notes": [],
                                "generated_name_origin": "run__adapter",
                            }
                        },
                        "generated_inputs": {},
                        "generated_outputs": {},
                        "generated_paths": {},
                        "generated_internal_inputs": {},
                        "command_boundaries": [
                            {
                                "step_id": "run__adapter",
                                "command_name": "apply_resource_transition",
                                "boundary_kind": "certified_adapter",
                                "origin_key": "pkg/entry::run::step_id::run__adapter",
                                "adapter_name": "apply_resource_transition",
                                "source_map_behavior": "step",
                            }
                        ],
                        "validation_subjects": [],
                        "executable_nodes": [],
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    provenance = WorkflowProvenance(
        workflow_path=tmp_path / "workflow.orc",
        source_root=tmp_path,
        frontend_kind="workflow_lisp",
        frontend_build_root=tmp_path,
        frontend_source_trace_path=source_map,
        frontend_entry_workflow="pkg/entry::run",
    )
    executor._compiled_frontend_kind = "workflow_lisp"
    executor._compiled_frontend_node_origins = executor._load_compiled_frontend_node_origins(provenance)
    executor._compiled_frontend_step_origins = executor._load_compiled_frontend_step_origins(provenance)
    executor._compiled_frontend_command_boundaries = executor._load_compiled_frontend_command_boundaries(provenance)

    with caplog.at_level("INFO", logger="orchestrator.workflow.executor"):
        executor._emit_compiled_frontend_step_display("run__adapter", "run__adapter")

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "certified adapter: apply_resource_transition" in messages
    assert "source-map behavior: step" in messages


def test_executor_uses_bundle_runtime_plan_for_top_level_ordering(tmp_path: Path):
    workflow = tmp_path / "workflow.yaml"
    workflow.write_text(
        "\n".join(
            [
                "version: '2.7'",
                "name: runtime-plan-ordering",
                "steps:",
                "  - name: First",
                "    id: first",
                "    command: ['bash', '-lc', 'printf first\\\\n']",
                "  - name: Second",
                "    id: second",
                "    command: ['bash', '-lc', 'printf second\\\\n']",
                "finally:",
                "  id: cleanup",
                "  steps:",
                "    - name: Cleanup",
                "      id: cleanup_marker",
                "      command: ['bash', '-lc', 'printf cleanup\\\\n']",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow)
    state_manager = StateManager(tmp_path, run_id="runtime-plan-ordering")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(bundle, tmp_path, state_manager)

    assert executor._step_node_ids == list(bundle.runtime_plan.ordered_node_ids)


def test_compiled_frontend_source_context_can_use_runtime_plan_command_hints(tmp_path: Path, caplog):
    source_map = tmp_path / "source_map.json"
    source_map.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_source_map.v1",
                "coverage": {
                    "frontend_ast": "covered",
                    "lowered_surface": "covered",
                    "shared_validation_subjects": "covered",
                    "executable_ir": "covered",
                    "runtime_logs": "covered",
                    "core_workflow_ast": "covered",
                    "semantic_ir": "covered",
                },
                "workflows": {
                    "pkg/entry::run": {
                        "display_name": "run",
                        "selected_entry_workflow": True,
                        "workflow_name": "pkg/entry::run",
                        "workflow_origin": {
                            "origin_key": "pkg/entry::run::workflow::pkg/entry::run",
                            "entity_kind": "workflow",
                            "workflow_name": "pkg/entry::run",
                            "path": "workflow.orc",
                            "line": 1,
                            "column": 1,
                            "end_line": 1,
                            "end_column": 5,
                            "form_path": ["workflow-lisp", "defworkflow", "run"],
                            "module_name": "pkg/entry",
                            "expansion_stack": [],
                            "notes": [],
                            "generated_name_origin": "pkg/entry::run",
                        },
                        "step_ids": {
                            "run__adapter": {
                                "origin_key": "pkg/entry::run::step_id::run__adapter",
                                "entity_kind": "step_id",
                                "workflow_name": "pkg/entry::run",
                                "path": "adapter.orc",
                                "line": 7,
                                "column": 3,
                                "end_line": 7,
                                "end_column": 9,
                                "form_path": ["workflow-lisp", "defworkflow", "run", "command-result"],
                                "module_name": "pkg/entry",
                                "expansion_stack": [],
                                "notes": [],
                                "generated_name_origin": "run__adapter",
                            }
                        },
                        "generated_inputs": {},
                        "generated_outputs": {},
                        "generated_paths": {},
                        "generated_internal_inputs": {},
                        "command_boundaries": [],
                        "validation_subjects": [],
                        "executable_nodes": [
                            {
                                "node_id": "root.run__adapter",
                                "step_id": "run__adapter",
                                "kind": "command",
                                "region": "body",
                                "origin_key": "pkg/entry::run::step_id::run__adapter",
                                "presentation_name": "run__adapter",
                            }
                        ],
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    provenance = WorkflowProvenance(
        workflow_path=tmp_path / "workflow.orc",
        source_root=tmp_path,
        frontend_kind="workflow_lisp",
        frontend_build_root=tmp_path,
        frontend_source_trace_path=source_map,
        frontend_entry_workflow="pkg/entry::run",
    )
    executor._compiled_frontend_kind = "workflow_lisp"
    executor._compiled_frontend_node_origins = executor._load_compiled_frontend_node_origins(provenance)
    executor._compiled_frontend_step_origins = executor._load_compiled_frontend_step_origins(provenance)
    executor._compiled_frontend_command_boundaries = {}
    executor.runtime_plan = SimpleNamespace(
        nodes={
            "root.run__adapter": SimpleNamespace(
                node_id="root.run__adapter",
                step_id="run__adapter",
                presentation_key="run__adapter",
                display_name="run__adapter",
                command_boundary_kind="certified_adapter",
                command_boundary_name="apply_resource_transition",
            )
        }
    )

    with caplog.at_level("INFO", logger="orchestrator.workflow.executor"):
        executor._emit_compiled_frontend_step_display(
            "run__adapter",
            "run__adapter",
            node_id="root.run__adapter",
        )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "source: adapter.orc:7:3" in messages
    assert "certified adapter: apply_resource_transition" in messages


def test_compiled_frontend_source_trace_payload_reads_sidecar_once(tmp_path: Path, monkeypatch):
    source_map = tmp_path / "source_map.json"
    source_map.write_text(
        json.dumps(
            {
                "schema_version": "workflow_lisp_source_map.v1",
                "coverage": {
                    "frontend_ast": "covered",
                    "lowered_surface": "covered",
                    "shared_validation_subjects": "covered",
                    "executable_ir": "covered",
                    "runtime_logs": "covered",
                    "core_workflow_ast": "covered",
                    "semantic_ir": "covered",
                },
                "workflows": {
                    "pkg/entry::run": {
                        "display_name": "run",
                        "selected_entry_workflow": True,
                        "workflow_name": "pkg/entry::run",
                        "workflow_origin": {
                            "origin_key": "pkg/entry::run::workflow::pkg/entry::run",
                            "entity_kind": "workflow",
                            "workflow_name": "pkg/entry::run",
                            "path": "workflow.orc",
                            "line": 1,
                            "column": 1,
                            "end_line": 1,
                            "end_column": 5,
                            "form_path": ["workflow-lisp", "defworkflow", "run"],
                            "module_name": "pkg/entry",
                            "expansion_stack": [],
                            "notes": [],
                            "generated_name_origin": "pkg/entry::run",
                        },
                        "step_ids": {
                            "run__command": {
                                "origin_key": "pkg/entry::run::step_id::run__command",
                                "entity_kind": "step_id",
                                "workflow_name": "pkg/entry::run",
                                "path": "step.orc",
                                "line": 10,
                                "column": 3,
                                "end_line": 10,
                                "end_column": 7,
                                "form_path": ["workflow-lisp", "defworkflow", "run", "command-result"],
                                "module_name": "pkg/entry",
                                "expansion_stack": [],
                                "notes": [],
                                "generated_name_origin": "run__command",
                            }
                        },
                        "generated_inputs": {},
                        "generated_outputs": {},
                        "generated_paths": {},
                        "generated_internal_inputs": {},
                        "command_boundaries": [
                            {
                                "step_id": "run__command",
                                "command_name": "run_checks",
                                "boundary_kind": "external_tool",
                                "origin_key": "pkg/entry::run::step_id::run__command",
                            }
                        ],
                        "validation_subjects": [],
                        "executable_nodes": [
                            {
                                "node_id": "root.run__command",
                                "step_id": "run__command",
                                "kind": "command",
                                "region": "body",
                                "origin_key": "pkg/entry::run::step_id::run__command",
                                "presentation_name": "run__command",
                            }
                        ],
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    original_read_text = Path.read_text
    read_count = 0

    def counting_read_text(path: Path, *args, **kwargs):
        nonlocal read_count
        if path == source_map:
            read_count += 1
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    provenance = WorkflowProvenance(
        workflow_path=tmp_path / "workflow.orc",
        source_root=tmp_path,
        frontend_kind="workflow_lisp",
        frontend_build_root=tmp_path,
        frontend_source_trace_path=source_map,
        frontend_entry_workflow="pkg/entry::run",
    )

    executor._load_compiled_frontend_step_origins(provenance)
    executor._load_compiled_frontend_node_origins(provenance)
    executor._load_compiled_frontend_command_boundaries(provenance)

    assert read_count == 1


def test_old_state_without_runtime_observability_still_loads(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "old-state"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": StateManager.SCHEMA_VERSION,
                "run_id": "old-state",
                "workflow_file": "workflow.yaml",
                "workflow_checksum": "sha256:test",
                "started_at": "2026-04-29T10:00:00Z",
                "updated_at": "2026-04-29T10:00:00Z",
                "status": "running",
                "context": {},
                "bound_inputs": {},
                "workflow_outputs": {},
                "finalization": {},
                "steps": {},
                "for_each": {},
                "repeat_until": {},
                "call_frames": {},
                "artifact_versions": {},
                "artifact_consumes": {},
                "transition_count": 0,
                "step_visits": {},
            }
        ),
        encoding="utf-8",
    )

    loaded = StateManager(tmp_path, run_id="old-state").load()

    assert loaded.runtime_observability is None


def test_process_metadata_can_record_executor_session_id(tmp_path: Path):
    path = write_process_metadata(tmp_path, executor_session_id="exec-0001")

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["executor_session_id"] == "exec-0001"
