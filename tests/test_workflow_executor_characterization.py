"""Characterization tests for workflow executor seam behavior."""

import json
from pathlib import Path

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import NodeResultAddress
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.references import ReferenceResolutionError


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return workflow_file


def _load_workflow(workspace: Path, workflow: dict) -> dict:
    workflow_path = _write_workflow(workspace, workflow)
    return WorkflowLoader(workspace).load(workflow_path)


def _load_workflow_bundle(workspace: Path, workflow: dict):
    workflow_path = _write_workflow(workspace, workflow)
    return WorkflowLoader(workspace).load_bundle(workflow_path)


def _persisted_state(workspace: Path, run_id: str) -> dict:
    state_file = workspace / ".orchestrate" / "runs" / run_id / "state.json"
    return json.loads(state_file.read_text(encoding="utf-8"))


def _structured_finally_resume_workflow() -> dict:
    return {
        "version": "2.3",
        "name": "structured-finally-resume",
        "artifacts": {
            "decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }
        },
        "outputs": {
            "final_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
                "from": {
                    "ref": "root.steps.WriteDecision.artifacts.decision",
                },
            }
        },
        "steps": [
            {
                "name": "WriteDecision",
                "id": "write_decision",
                "set_scalar": {
                    "artifact": "decision",
                    "value": "APPROVE",
                },
            }
        ],
        "finally": {
            "id": "cleanup",
            "steps": [
                {
                    "name": "ObserveOutputsPending",
                    "id": "observe_outputs_pending",
                    "command": [
                        "bash",
                        "-lc",
                        "\n".join(
                            [
                                "python - <<'PY'",
                                "import json",
                                "from pathlib import Path",
                                "state = json.loads(Path('${run.root}/state.json').read_text(encoding='utf-8'))",
                                "assert state.get('workflow_outputs', {}) == {}, state.get('workflow_outputs')",
                                "Path('state').mkdir(exist_ok=True)",
                                "with Path('state/finalization.log').open('a', encoding='utf-8') as handle:",
                                "    handle.write('outputs-pending\\n')",
                                "PY",
                            ]
                        ),
                    ],
                },
                {
                    "name": "WriteCleanupMarker",
                    "id": "write_cleanup_marker",
                    "command": [
                        "bash",
                        "-lc",
                        "mkdir -p state && printf 'cleanup-complete\\n' >> state/finalization.log",
                    ],
                },
            ],
        },
    }


def test_executor_resume_partial_finalization_restarts_remaining_cleanup_step(tmp_path: Path):
    loaded = _load_workflow(tmp_path, _structured_finally_resume_workflow())
    run_id = "executor-finalization-resume"
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize("workflow.yaml")
    assert state_manager.state is not None

    (tmp_path / "state").mkdir(exist_ok=True)
    (tmp_path / "state" / "finalization.log").write_text("outputs-pending\n", encoding="utf-8")

    state_manager.state.status = "failed"
    state_manager.state.steps = {
        "WriteDecision": {
            "status": "completed",
            "exit_code": 0,
            "artifacts": {"decision": "APPROVE"},
        },
        "finally.ObserveOutputsPending": {
            "status": "completed",
            "exit_code": 0,
        },
        "finally.WriteCleanupMarker": {"status": "pending"},
    }
    state_manager.state.current_step = {
        "name": "finally.ObserveOutputsPending",
        "index": 1,
        "type": "command",
        "status": "running",
        "step_id": "root.finally.cleanup.observe_outputs_pending",
        "started_at": "2024-01-01T00:00:10Z",
        "last_heartbeat_at": "2024-01-01T00:00:11Z",
    }
    state_manager.state.finalization = {
        "block_id": "cleanup",
        "status": "running",
        "body_status": "completed",
        "current_index": None,
        "completed_indices": [0],
        "step_names": [
            "finally.ObserveOutputsPending",
            "finally.WriteCleanupMarker",
        ],
        "workflow_outputs_status": "pending",
    }
    state_manager.state.workflow_outputs = {}
    state_manager._write_state()

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute(resume=True)
    persisted = _persisted_state(tmp_path, run_id)

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"final_decision": "APPROVE"}
    assert state["steps"]["finally.ObserveOutputsPending"]["status"] == "completed"
    assert state["steps"]["finally.WriteCleanupMarker"]["status"] == "completed"
    assert (tmp_path / "state" / "finalization.log").read_text(encoding="utf-8").splitlines() == [
        "outputs-pending",
        "cleanup-complete",
    ]
    assert persisted["status"] == "completed"
    assert persisted.get("current_step") is None
    assert persisted["finalization"]["completed_indices"] == [0, 1]
    assert persisted["finalization"]["workflow_outputs_status"] == "completed"


def test_executor_for_each_nested_scalar_steps_materialize_artifacts_per_iteration(tmp_path: Path):
    workflow = {
        "version": "1.7",
        "name": "loop-nested-scalars",
        "artifacts": {
            "failed_count": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "steps": [
            {
                "name": "ProcessItems",
                "for_each": {
                    "items": ["alpha", "beta"],
                    "steps": [
                        {
                            "name": "InitializeCount",
                            "set_scalar": {
                                "artifact": "failed_count",
                                "value": 0,
                            },
                            "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
                        },
                        {
                            "name": "IncrementCount",
                            "increment_scalar": {
                                "artifact": "failed_count",
                                "by": 1,
                            },
                            "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
                        },
                    ],
                },
            }
        ],
    }

    loaded = _load_workflow(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id="loop-nested-scalars")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "loop-nested-scalars")

    assert state["status"] == "completed"
    assert state["steps"]["ProcessItems"][0]["InitializeCount"]["artifacts"] == {"failed_count": 0}
    assert state["steps"]["ProcessItems"][0]["IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert state["steps"]["ProcessItems"][1]["InitializeCount"]["artifacts"] == {"failed_count": 0}
    assert state["steps"]["ProcessItems"][1]["IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert state["steps"]["ProcessItems[0].IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert state["steps"]["ProcessItems[1].IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert persisted["steps"]["ProcessItems"][0]["IncrementCount"]["artifacts"] == {"failed_count": 1}
    assert persisted["steps"]["ProcessItems"][1]["IncrementCount"]["artifacts"] == {"failed_count": 1}
    versions = persisted["artifact_versions"]["failed_count"]
    assert [entry["producer"] for entry in versions] == [
        "InitializeCount",
        "IncrementCount",
        "InitializeCount",
        "IncrementCount",
    ]


def test_executor_for_each_nested_provider_pre_execution_failures_normalize_outcomes(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "loop-provider-pre-execution",
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
                "name": "ProcessItems",
                "for_each": {
                    "items": ["only"],
                    "steps": [
                        {
                            "name": "UseProvider",
                            "provider": "write_file",
                            "provider_params": {
                                "value": "${context.missing_value}",
                            },
                        }
                    ],
                },
            }
        ],
    }

    loaded = _load_workflow(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id="loop-provider-pre-execution")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute(on_error="continue")
    persisted = _persisted_state(tmp_path, "loop-provider-pre-execution")
    result = state["steps"]["ProcessItems"][0]["UseProvider"]

    assert result["status"] == "failed"
    assert result["error"]["type"] == "substitution_error"
    assert result["outcome"] == {
        "status": "failed",
        "phase": "pre_execution",
        "class": "pre_execution_failed",
        "retryable": False,
    }
    assert persisted["steps"]["ProcessItems"][0]["UseProvider"]["outcome"] == result["outcome"]
    assert not (tmp_path / "state" / "provider-ran.txt").exists()


def test_executor_top_level_provider_step_persists_result_shape_and_clears_current_step(tmp_path: Path):
    workflow = {
        "version": "1.4",
        "name": "top-level-provider-characterization",
        "providers": {
            "echoer": {
                "command": ["bash", "-lc", "printf ok"],
            }
        },
        "steps": [
            {
                "name": "AskProvider",
                "provider": "echoer",
            }
        ],
    }

    loaded = _load_workflow(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id="top-level-provider-characterization")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "top-level-provider-characterization")

    assert state["status"] == "completed"
    assert state.get("current_step") is None
    assert state["steps"]["AskProvider"] == {
        "status": "completed",
        "name": "AskProvider",
        "step_id": "root.askprovider",
        "exit_code": 0,
        "duration_ms": state["steps"]["AskProvider"]["duration_ms"],
        "output": "ok",
        "truncated": False,
        "skipped": False,
        "outcome": {
            "status": "completed",
            "phase": "execution",
            "class": "completed",
            "retryable": False,
        },
        "visit_count": 1,
    }
    assert persisted["status"] == "completed"
    assert persisted.get("current_step") is None


def test_executor_provider_session_fresh_clears_current_step_after_atomic_publication(tmp_path: Path):
    session_script = "\n".join(
        [
            "python - <<'PY'",
            "print('{\"type\":\"session.started\",\"session_id\":\"sess-123\"}')",
            "print('{\"type\":\"assistant.message\",\"role\":\"assistant\",\"text\":\"hello\"}')",
            "print('{\"type\":\"response.completed\",\"session_id\":\"sess-123\"}')",
            "PY",
        ]
    )
    workflow = {
        "version": "2.10",
        "name": "provider-session-characterization",
        "providers": {
            "echoer": {
                "command": ["bash", "-lc", session_script],
                "input_mode": "stdin",
                "session_support": {
                    "metadata_mode": "codex_exec_jsonl_stdout",
                    "fresh_command": ["bash", "-lc", session_script],
                    "resume_command": ["bash", "-lc", session_script + " # ${SESSION_ID}"],
                },
            }
        },
        "artifacts": {
            "implementation_session_id": {
                "kind": "scalar",
                "type": "string",
            },
        },
        "steps": [
            {
                "name": "AskProvider",
                "provider": "echoer",
                "provider_session": {
                    "mode": "fresh",
                    "publish_artifact": "implementation_session_id",
                },
            }
        ],
    }

    loaded = _load_workflow(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id="provider-session-characterization")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "provider-session-characterization")

    assert state["status"] == "completed"
    assert state.get("current_step") is None
    assert state["steps"]["AskProvider"]["artifacts"] == {"implementation_session_id": "sess-123"}
    assert persisted.get("current_step") is None
    assert persisted["artifact_versions"]["implementation_session_id"][0]["value"] == "sess-123"
    assert persisted["steps"]["AskProvider"]["outcome"] == {
        "status": "completed",
        "phase": "execution",
        "class": "completed",
        "retryable": False,
    }


def test_executor_on_error_continue_routes_through_later_top_level_step_and_finishes_completed(tmp_path: Path):
    workflow = {
        "version": "1.4",
        "name": "top-level-routing-characterization",
        "steps": [
            {
                "name": "FailFirst",
                "command": ["bash", "-lc", "exit 7"],
            },
            {
                "name": "RunSecond",
                "command": ["bash", "-lc", "mkdir -p state && printf ran > state/second.txt"],
            },
        ],
    }

    loaded = _load_workflow(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id="top-level-routing-characterization")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute(on_error="continue")
    persisted = _persisted_state(tmp_path, "top-level-routing-characterization")

    assert state["status"] == "completed"
    assert state.get("current_step") is None
    assert state["transition_count"] == 1
    assert state["steps"]["FailFirst"]["status"] == "failed"
    assert state["steps"]["FailFirst"]["outcome"] == {
        "status": "failed",
        "phase": "execution",
        "class": "command_failed",
        "retryable": False,
    }
    assert state["steps"]["RunSecond"]["status"] == "completed"
    assert (tmp_path / "state" / "second.txt").read_text(encoding="utf-8") == "ran"
    assert persisted["status"] == "completed"
    assert persisted.get("current_step") is None
    assert persisted["step_visits"] == {"FailFirst": 1, "RunSecond": 1}


def test_executor_uses_projection_order_and_presentation_names_over_legacy_adapter_drift(
    tmp_path: Path,
):
    workflow = {
        "version": "2.7",
        "name": "projection-executor-order",
        "steps": [
            {
                "name": "WriteOne",
                "id": "write_one",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'one\\n' >> state/history.log",
                ],
            },
            {
                "name": "WriteTwo",
                "id": "write_two",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'two\\n' >> state/history.log",
                ],
            },
        ],
    }

    bundle = _load_workflow_bundle(tmp_path, workflow)
    legacy_steps = bundle.legacy_workflow["steps"]
    legacy_steps[0]["name"] = "LegacyWriteOne"
    legacy_steps[1]["name"] = "LegacyWriteTwo"
    bundle.legacy_workflow["steps"] = [legacy_steps[1], legacy_steps[0]]

    state_manager = StateManager(workspace=tmp_path, run_id="projection-executor-order")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "projection-executor-order")

    assert state["status"] == "completed"
    assert (tmp_path / "state" / "history.log").read_text(encoding="utf-8").splitlines() == [
        "one",
        "two",
    ]
    assert "WriteOne" in state["steps"]
    assert "WriteTwo" in state["steps"]
    assert "LegacyWriteOne" not in state["steps"]
    assert "LegacyWriteTwo" not in state["steps"]
    assert persisted["step_visits"] == {"WriteOne": 1, "WriteTwo": 1}


def test_executor_resolves_goto_against_projection_when_legacy_target_name_drifts(tmp_path: Path):
    workflow = {
        "version": "2.7",
        "name": "projection-executor-goto",
        "steps": [
            {
                "name": "Start",
                "id": "start",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'start\\n' >> state/history.log",
                ],
                "on": {
                    "success": {
                        "goto": "Final",
                    }
                },
            },
            {
                "name": "Skipped",
                "id": "skipped",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'skipped\\n' >> state/history.log",
                ],
            },
            {
                "name": "Final",
                "id": "final",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'final\\n' >> state/history.log",
                ],
            },
        ],
    }

    bundle = _load_workflow_bundle(tmp_path, workflow)
    bundle.legacy_workflow["steps"][2]["name"] = "LegacyFinal"

    state_manager = StateManager(workspace=tmp_path, run_id="projection-executor-goto")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "projection-executor-goto")

    assert state["status"] == "completed"
    assert (tmp_path / "state" / "history.log").read_text(encoding="utf-8").splitlines() == [
        "start",
        "final",
    ]
    assert "Final" in state["steps"]
    assert "LegacyFinal" not in state["steps"]
    assert "Skipped" not in state["steps"]
    assert persisted["step_visits"] == {"Start": 1, "Final": 1}


def test_executor_uses_ir_raw_step_payloads_when_legacy_adapter_payloads_drift(tmp_path: Path):
    workflow = {
        "version": "2.7",
        "name": "projection-executor-raw-payload",
        "steps": [
            {
                "name": "Start",
                "id": "start",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'start\\n' >> state/history.log",
                ],
                "on": {
                    "success": {
                        "goto": "Final",
                    }
                },
            },
            {
                "name": "Skipped",
                "id": "skipped",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'skipped\\n' >> state/history.log",
                ],
            },
            {
                "name": "Final",
                "id": "final",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'final\\n' >> state/history.log",
                ],
            },
        ],
    }

    bundle = _load_workflow_bundle(tmp_path, workflow)
    legacy_steps = bundle.legacy_workflow["steps"]
    legacy_steps[0]["command"] = [
        "bash",
        "-lc",
        "mkdir -p state && printf 'legacy-start\\n' >> state/history.log",
    ]
    legacy_steps[0]["on"] = {"success": {"goto": "LegacyFinal"}}
    legacy_steps[1]["command"] = [
        "bash",
        "-lc",
        "mkdir -p state && printf 'legacy-skipped\\n' >> state/history.log",
    ]
    legacy_steps[2]["name"] = "LegacyFinal"
    legacy_steps[2]["command"] = [
        "bash",
        "-lc",
        "mkdir -p state && printf 'legacy-final\\n' >> state/history.log",
    ]

    state_manager = StateManager(workspace=tmp_path, run_id="projection-executor-raw-payload")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "projection-executor-raw-payload")

    assert state["status"] == "completed"
    assert (tmp_path / "state" / "history.log").read_text(encoding="utf-8").splitlines() == [
        "start",
        "final",
    ]
    assert "LegacyFinal" not in state["steps"]
    assert "Skipped" not in state["steps"]
    assert persisted["step_visits"] == {"Start": 1, "Final": 1}


def test_executor_uses_non_counting_ir_transfer_metadata_for_typed_call_return(tmp_path: Path):
    child_path = tmp_path / "workflows" / "library" / "child.yaml"
    child_path.parent.mkdir(parents=True, exist_ok=True)
    child_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.7",
                "name": "child",
                "steps": [
                    {
                        "name": "WriteChild",
                        "id": "write_child",
                        "command": ["bash", "-lc", "printf 'child\\n' > state/child.log"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    bundle = _load_workflow_bundle(
        tmp_path,
        {
            "version": "2.7",
            "name": "typed-call-return-transition",
            "imports": {
                "child": "workflows/library/child.yaml",
            },
            "steps": [
                {
                    "name": "RunChild",
                    "id": "run_child",
                    "call": "child",
                },
                {
                    "name": "AfterChild",
                    "id": "after_child",
                    "command": ["bash", "-lc", "printf 'after\\n' > state/after.log"],
                },
            ],
        },
    )
    state_manager = StateManager(workspace=tmp_path, run_id="typed-call-return-transition")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager)
    call_node = bundle.ir.nodes["root.run_child"]
    state = {"transition_count": 0}

    next_step_index, next_node_id, terminal_status, should_break = executor._advance_after_top_level_route(
        current_index=0,
        current_node_id=call_node.node_id,
        next_step=None,
        terminal_status="completed",
        state=state,
    )

    assert next_step_index is None
    assert next_node_id == "root.after_child"
    assert terminal_status == "completed"
    assert should_break is False
    assert state["transition_count"] == 0


def test_executor_uses_projection_names_for_finalization_bookkeeping_when_legacy_names_drift(
    tmp_path: Path,
):
    workflow = {
        "version": "2.7",
        "name": "projection-finalization-names",
        "steps": [
            {
                "name": "Start",
                "id": "start",
                "command": ["bash", "-lc", "mkdir -p state && printf 'start\\n' > state/run.log"],
            }
        ],
        "finally": {
            "id": "cleanup",
            "steps": [
                {
                    "name": "WriteCleanupMarker",
                    "id": "write_cleanup_marker",
                    "command": [
                        "bash",
                        "-lc",
                        "mkdir -p state && printf 'cleanup\\n' >> state/run.log",
                    ],
                }
            ],
        },
    }

    bundle = _load_workflow_bundle(tmp_path, workflow)
    bundle.legacy_workflow["finally"]["steps"][0]["name"] = "LegacyCleanup"

    state_manager = StateManager(workspace=tmp_path, run_id="projection-finalization-names")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "projection-finalization-names")
    cleanup_node_id = bundle.ir.finalization_region[0]
    cleanup_name = bundle.projection.presentation_key_by_node_id[cleanup_node_id]

    assert state["status"] == "completed"
    assert cleanup_name in state["steps"]
    assert "LegacyCleanup" not in state["steps"]
    assert state["finalization"]["step_names"] == [cleanup_name]
    assert persisted["finalization"]["step_names"] == [cleanup_name]


def test_executor_bound_address_resolution_fails_closed_without_projection_owned_lookup(
    tmp_path: Path,
):
    workflow = {
        "version": "2.7",
        "name": "projection-bound-addresses",
        "artifacts": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
            }
        },
        "steps": [
            {
                "name": "SetReady",
                "id": "set_ready",
                "set_scalar": {
                    "artifact": "ready",
                    "value": True,
                },
            }
        ],
    }

    bundle = _load_workflow_bundle(tmp_path, workflow)
    state_manager = StateManager(workspace=tmp_path, run_id="projection-bound-addresses")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(bundle, tmp_path, state_manager)

    with pytest.raises(ReferenceResolutionError, match="unavailable"):
        executor._resolve_runtime_value(
            NodeResultAddress(
                node_id="root.set_ready",
                field="artifacts",
                member="ready",
            ),
            {
                "steps": {
                    "AliasKey": {
                        "status": "completed",
                        "step_id": "root.set_ready",
                        "artifacts": {"ready": True},
                    }
                }
            },
        )


def test_executor_uses_typed_if_nodes_when_legacy_helper_keys_are_removed(tmp_path: Path):
    workflow = {
        "version": "2.7",
        "name": "projection-if-helpers",
        "artifacts": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
            },
            "review_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            },
        },
        "steps": [
            {
                "name": "SetReady",
                "id": "set_ready",
                "set_scalar": {
                    "artifact": "ready",
                    "value": True,
                },
            },
            {
                "name": "RouteReady",
                "id": "route_ready",
                "if": {
                    "artifact_bool": {
                        "ref": "root.steps.SetReady.artifacts.ready",
                    }
                },
                "then": {
                    "id": "approve_path",
                    "steps": [
                        {
                            "name": "WriteApproved",
                            "id": "write_approved",
                            "set_scalar": {
                                "artifact": "review_decision",
                                "value": "APPROVE",
                            },
                        }
                    ],
                    "outputs": {
                        "review_decision": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                            "from": {
                                "ref": "self.steps.WriteApproved.artifacts.review_decision",
                            },
                        }
                    },
                },
                "else": {
                    "id": "revise_path",
                    "steps": [
                        {
                            "name": "WriteRevision",
                            "id": "write_revision",
                            "set_scalar": {
                                "artifact": "review_decision",
                                "value": "REVISE",
                            },
                        }
                    ],
                    "outputs": {
                        "review_decision": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                            "from": {
                                "ref": "self.steps.WriteRevision.artifacts.review_decision",
                            },
                        }
                    },
                },
            },
        ],
    }

    bundle = _load_workflow_bundle(tmp_path, workflow)
    for step in bundle.legacy_workflow["steps"]:
        if step.get("step_id") in {"root.route_ready.approve_path", "root.route_ready.revise_path"}:
            step.pop("structured_if_branch", None)
        if step.get("step_id") == "root.route_ready":
            step.pop("structured_if_join", None)

    state_manager = StateManager(workspace=tmp_path, run_id="projection-if-helpers")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "projection-if-helpers")

    assert state["status"] == "completed"
    assert state["steps"]["RouteReady.then.WriteApproved"]["status"] == "completed"
    assert state["steps"]["RouteReady.else.WriteRevision"]["status"] == "skipped"
    assert state["steps"]["RouteReady"]["artifacts"] == {"review_decision": "APPROVE"}
    assert persisted["steps"]["RouteReady.else.WriteRevision"]["status"] == "skipped"
    assert persisted["steps"]["RouteReady"]["artifacts"] == {"review_decision": "APPROVE"}


def test_executor_uses_typed_match_nodes_when_legacy_helper_keys_are_removed(tmp_path: Path):
    workflow = {
        "version": "2.7",
        "name": "projection-match-helpers",
        "artifacts": {
            "decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            },
            "route_action": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["DONE", "FIX"],
            },
        },
        "steps": [
            {
                "name": "SetDecision",
                "id": "set_decision",
                "set_scalar": {
                    "artifact": "decision",
                    "value": "REVISE",
                },
            },
            {
                "name": "RouteDecision",
                "id": "route_decision",
                "match": {
                    "ref": "root.steps.SetDecision.artifacts.decision",
                    "cases": {
                        "APPROVE": {
                            "id": "approve_path",
                            "steps": [
                                {
                                    "name": "WriteDone",
                                    "id": "write_done",
                                    "set_scalar": {
                                        "artifact": "route_action",
                                        "value": "DONE",
                                    },
                                }
                            ],
                            "outputs": {
                                "route_action": {
                                    "kind": "scalar",
                                    "type": "enum",
                                    "allowed": ["DONE", "FIX"],
                                    "from": {
                                        "ref": "self.steps.WriteDone.artifacts.route_action",
                                    },
                                }
                            },
                        },
                        "REVISE": {
                            "id": "revise_path",
                            "steps": [
                                {
                                    "name": "WriteFix",
                                    "id": "write_fix",
                                    "set_scalar": {
                                        "artifact": "route_action",
                                        "value": "FIX",
                                    },
                                }
                            ],
                            "outputs": {
                                "route_action": {
                                    "kind": "scalar",
                                    "type": "enum",
                                    "allowed": ["DONE", "FIX"],
                                    "from": {
                                        "ref": "self.steps.WriteFix.artifacts.route_action",
                                    },
                                }
                            },
                        },
                    },
                },
            },
        ],
    }

    bundle = _load_workflow_bundle(tmp_path, workflow)
    for step in bundle.legacy_workflow["steps"]:
        if step.get("step_id") in {"root.route_decision.approve_path", "root.route_decision.revise_path"}:
            step.pop("structured_match_case", None)
        if step.get("step_id") == "root.route_decision":
            step.pop("structured_match_join", None)

    state_manager = StateManager(workspace=tmp_path, run_id="projection-match-helpers")
    state_manager.initialize("workflow.yaml")

    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    persisted = _persisted_state(tmp_path, "projection-match-helpers")

    assert state["status"] == "completed"
    assert state["steps"]["RouteDecision.APPROVE.WriteDone"]["status"] == "skipped"
    assert state["steps"]["RouteDecision.REVISE.WriteFix"]["status"] == "completed"
    assert state["steps"]["RouteDecision"]["artifacts"] == {"route_action": "FIX"}
    assert persisted["steps"]["RouteDecision"]["artifacts"] == {"route_action": "FIX"}
