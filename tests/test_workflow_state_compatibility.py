"""Characterization tests for persisted workflow compatibility surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from tests.workflow_bundle_helpers import materialize_projection_body_steps


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _persisted_state(workspace: Path, run_id: str) -> dict:
    state_path = workspace / ".orchestrate" / "runs" / run_id / "state.json"
    return json.loads(state_path.read_text(encoding="utf-8"))


def _build_repeat_until_resume_workflow() -> dict:
    return {
        "version": "2.7",
        "name": "resume-repeat-until",
        "steps": [
            {
                "name": "ReviewLoop",
                "id": "review_loop",
                "repeat_until": {
                    "id": "iteration_body",
                    "outputs": {
                        "review_decision": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                            "from": {"ref": "self.steps.WriteDecision.artifacts.review_decision"},
                        }
                    },
                    "condition": {
                        "compare": {
                            "left": {"ref": "self.outputs.review_decision"},
                            "op": "eq",
                            "right": "APPROVE",
                        }
                    },
                    "max_iterations": 4,
                    "steps": [
                        {
                            "name": "WriteBodyHistory",
                            "id": "write_body_history",
                            "command": [
                                "bash",
                                "-lc",
                                "\n".join(
                                    [
                                        "mkdir -p state",
                                        "count=$(cat state/review_count.txt 2>/dev/null || printf '0')",
                                        "count=$((count + 1))",
                                        "printf '%s\\n' \"$count\" > state/review_count.txt",
                                        "printf 'body-%s\\n' \"$count\" >> state/history.log",
                                    ]
                                ),
                            ],
                        },
                        {
                            "name": "ResumeGate",
                            "id": "resume_gate",
                            "command": [
                                "bash",
                                "-lc",
                                "\n".join(
                                    [
                                        "mkdir -p state",
                                        "count=$(cat state/review_count.txt)",
                                        "if [ \"$count\" -ge 2 ] && [ ! -f state/resume_ready.txt ]; then",
                                        "  printf 'gate-failed-%s\\n' \"$count\" >> state/history.log",
                                        "  exit 1",
                                        "fi",
                                        "printf 'gate-passed-%s\\n' \"$count\" >> state/history.log",
                                    ]
                                ),
                            ],
                        },
                        {
                            "name": "WriteDecision",
                            "id": "write_decision",
                            "command": [
                                "bash",
                                "-lc",
                                "\n".join(
                                    [
                                        "mkdir -p state",
                                        "count=$(cat state/review_count.txt)",
                                        "if [ \"$count\" -ge 2 ]; then",
                                        "  printf 'APPROVE\\n' > state/review_decision.txt",
                                        "else",
                                        "  printf 'REVISE\\n' > state/review_decision.txt",
                                        "fi",
                                    ]
                                ),
                            ],
                            "expected_outputs": [
                                {
                                    "name": "review_decision",
                                    "path": "state/review_decision.txt",
                                    "type": "enum",
                                    "allowed": ["APPROVE", "REVISE"],
                                }
                            ],
                        },
                    ],
                },
            },
            {
                "name": "VerifyApproval",
                "id": "verify_approval",
                "assert": {
                    "compare": {
                        "left": {"ref": "root.steps.ReviewLoop.artifacts.review_decision"},
                        "op": "eq",
                        "right": "APPROVE",
                    }
                },
            },
        ],
    }


def _build_repeat_until_call_library_workflow() -> dict:
    return {
        "version": "2.7",
        "name": "repeat-until-call-review-loop",
        "inputs": {
            "iteration": {
                "kind": "scalar",
                "type": "integer",
            },
            "write_root": {
                "kind": "relpath",
                "type": "relpath",
            },
        },
        "artifacts": {
            "review_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }
        },
        "outputs": {
            "review_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
                "from": {"ref": "root.steps.WriteDecision.artifacts.review_decision"},
            }
        },
        "steps": [
            {
                "name": "WriteBodyHistory",
                "id": "write_body_history",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "mkdir -p \"${inputs.write_root}\"",
                            "mkdir -p state/review-loop",
                            "count=\"${inputs.iteration}\"",
                            "printf 'body-%s\\n' \"$count\" >> state/review-loop/history.log",
                        ]
                    ),
                ],
            },
            {
                "name": "ResumeGate",
                "id": "resume_gate",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "count=\"${inputs.iteration}\"",
                            "if [ \"$count\" -ge 2 ] && [ ! -f state/resume_ready.txt ]; then",
                            "  printf 'gate-failed-%s\\n' \"$count\" >> state/review-loop/history.log",
                            "  exit 1",
                            "fi",
                            "printf 'gate-passed-%s\\n' \"$count\" >> state/review-loop/history.log",
                        ]
                    ),
                ],
            },
            {
                "name": "WriteDecision",
                "id": "write_decision",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "mkdir -p \"${inputs.write_root}\"",
                            "count=\"${inputs.iteration}\"",
                            "if [ \"$count\" -ge 2 ]; then",
                            "  printf 'APPROVE\\n' > \"${inputs.write_root}/review_decision.txt\"",
                            "else",
                            "  printf 'REVISE\\n' > \"${inputs.write_root}/review_decision.txt\"",
                            "fi",
                        ]
                    ),
                ],
                "expected_outputs": [
                    {
                        "name": "review_decision",
                        "path": "${inputs.write_root}/review_decision.txt",
                        "type": "enum",
                        "allowed": ["APPROVE", "REVISE"],
                    }
                ],
            },
        ],
    }


def _build_repeat_until_call_resume_workflow() -> dict:
    return {
        "version": "2.7",
        "name": "repeat-until-call-resume",
        "imports": {
            "review_loop": "workflows/library/repeat_until_review_loop.yaml",
        },
        "artifacts": {
            "review_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }
        },
        "steps": [
            {
                "name": "ReviewLoop",
                "id": "review_loop",
                "repeat_until": {
                    "id": "iteration_body",
                    "outputs": {
                        "review_decision": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                            "from": {"ref": "self.steps.RouteDecision.artifacts.review_decision"},
                        }
                    },
                    "condition": {
                        "compare": {
                            "left": {"ref": "self.outputs.review_decision"},
                            "op": "eq",
                            "right": "APPROVE",
                        }
                    },
                    "max_iterations": 4,
                    "steps": [
                        {
                            "name": "PrepareCallInputs",
                            "id": "prepare_call_inputs",
                            "command": [
                                "bash",
                                "-lc",
                                "\n".join(
                                    [
                                        "mkdir -p state/review-loop-inputs",
                                        "iteration=$(( ${loop.index} + 1 ))",
                                        (
                                            "printf '{\"write_root\":\"state/review-loop/iterations/%s\","
                                            "\"iteration\":%s}\\n' \"$iteration\" \"$iteration\" "
                                            "> state/review-loop-inputs/current.json"
                                        ),
                                    ]
                                ),
                            ],
                            "output_bundle": {
                                "path": "state/review-loop-inputs/current.json",
                                "fields": [
                                    {
                                        "name": "write_root",
                                        "json_pointer": "/write_root",
                                        "type": "relpath",
                                    },
                                    {
                                        "name": "iteration",
                                        "json_pointer": "/iteration",
                                        "type": "integer",
                                    },
                                ],
                            },
                        },
                        {
                            "name": "RunReviewLoop",
                            "id": "run_review_loop",
                            "call": "review_loop",
                            "with": {
                                "iteration": {
                                    "ref": "self.steps.PrepareCallInputs.artifacts.iteration",
                                },
                                "write_root": {
                                    "ref": "self.steps.PrepareCallInputs.artifacts.write_root",
                                },
                            },
                        },
                        {
                            "name": "RouteDecision",
                            "id": "route_decision",
                            "match": {
                                "ref": "self.steps.RunReviewLoop.artifacts.review_decision",
                                "cases": {
                                    "APPROVE": {
                                        "id": "approve_path",
                                        "outputs": {
                                            "review_decision": {
                                                "kind": "scalar",
                                                "type": "enum",
                                                "allowed": ["APPROVE", "REVISE"],
                                                "from": {
                                                    "ref": (
                                                        "self.steps.WriteApproved.artifacts.review_decision"
                                                    ),
                                                },
                                            }
                                        },
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
                                    },
                                    "REVISE": {
                                        "id": "revise_path",
                                        "outputs": {
                                            "review_decision": {
                                                "kind": "scalar",
                                                "type": "enum",
                                                "allowed": ["APPROVE", "REVISE"],
                                                "from": {
                                                    "ref": (
                                                        "self.steps.WriteRevision.artifacts.review_decision"
                                                    ),
                                                },
                                            }
                                        },
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
                                    },
                                },
                            },
                        },
                    ],
                },
            },
            {
                "name": "VerifyApproval",
                "id": "verify_approval",
                "assert": {
                    "compare": {
                        "left": {"ref": "root.steps.ReviewLoop.artifacts.review_decision"},
                        "op": "eq",
                        "right": "APPROVE",
                    }
                },
            },
        ],
    }


def _build_finalization_resume_workflow() -> dict:
    return {
        "version": "2.3",
        "name": "resume-finalization",
        "steps": [
            {
                "name": "WriteBodyHistory",
                "id": "write_body_history",
                "command": ["bash", "-lc", "mkdir -p state && printf 'body\\n' >> state/history.log"],
            }
        ],
        "finally": {
            "id": "cleanup",
            "steps": [
                {
                    "name": "WriteCleanupOne",
                    "id": "write_cleanup_one",
                    "command": [
                        "bash",
                        "-lc",
                        "mkdir -p state && printf 'cleanup-one\\n' >> state/history.log",
                    ],
                },
                {
                    "name": "ResumeGate",
                    "id": "resume_gate",
                    "command": [
                        "bash",
                        "-lc",
                        "\n".join(
                            [
                                "mkdir -p state",
                                "if [ ! -f state/resume_ready.txt ]; then",
                                "  printf 'cleanup-gate-failed\\n' >> state/history.log",
                                "  exit 1",
                                "fi",
                                "printf 'cleanup-gate-passed\\n' >> state/history.log",
                            ]
                        ),
                    ],
                },
                {
                    "name": "WriteCleanupTwo",
                    "id": "write_cleanup_two",
                    "command": [
                        "bash",
                        "-lc",
                        "mkdir -p state && printf 'cleanup-two\\n' >> state/history.log",
                    ],
                },
            ],
        },
    }


def _build_structured_current_step_index_workflow() -> dict:
    return {
        "version": "2.6",
        "name": "structured-current-step-index",
        "artifacts": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
            },
            "decision": {
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
                    "outputs": {
                        "decision": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                            "from": {
                                "ref": "self.steps.WriteApproved.artifacts.decision",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "WriteApproved",
                            "id": "write_approved",
                            "set_scalar": {
                                "artifact": "decision",
                                "value": "APPROVE",
                            },
                        }
                    ],
                },
                "else": {
                    "id": "revise_path",
                    "outputs": {
                        "decision": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                            "from": {
                                "ref": "self.steps.WriteRevision.artifacts.decision",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "WriteRevision",
                            "id": "write_revision",
                            "set_scalar": {
                                "artifact": "decision",
                                "value": "REVISE",
                            },
                        }
                    ],
                },
            },
            {
                "name": "RouteDecision",
                "id": "route_decision",
                "match": {
                    "ref": "root.steps.RouteReady.artifacts.decision",
                    "cases": {
                        "APPROVE": {
                            "id": "approve_path",
                            "steps": [
                                {
                                    "name": "EchoApproved",
                                    "id": "echo_approved",
                                    "command": ["bash", "-lc", "printf 'approved\\n'"],
                                }
                            ],
                        },
                        "REVISE": {
                            "id": "revise_path",
                            "steps": [
                                {
                                    "name": "EchoRevision",
                                    "id": "echo_revision",
                                    "command": ["bash", "-lc", "printf 'revise\\n'"],
                                }
                            ],
                        },
                    },
                },
            },
        ],
    }


def test_structured_helper_steps_persist_current_step_indices_from_lowered_order(tmp_path: Path):
    workflow_path = _write_yaml(
        tmp_path / "structured_current_step_index.yaml",
        _build_structured_current_step_index_workflow(),
    )
    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    body_steps = materialize_projection_body_steps(workflow)
    expected_indices = {
        step["name"]: index
        for index, step in enumerate(body_steps)
    }

    recorded_current_steps = []

    class RecordingStateManager(StateManager):
        def start_step(
            self,
            step_name: str,
            step_index: int,
            step_type: str,
            step_id: str | None = None,
            visit_count: int | None = None,
        ):
            super().start_step(
                step_name,
                step_index,
                step_type,
                step_id=step_id,
                visit_count=visit_count,
            )
            assert self.state is not None
            recorded_current_steps.append(dict(self.state.current_step or {}))

    state_manager = RecordingStateManager(workspace=tmp_path, run_id="structured-current-step-index")
    state_manager.initialize("structured_current_step_index.yaml")

    state = WorkflowExecutor(workflow, tmp_path, state_manager).execute(on_error="stop")

    assert state["status"] == "completed"

    recorded_by_name = {entry["name"]: entry for entry in recorded_current_steps}
    assert recorded_by_name["RouteReady.then"]["index"] == expected_indices["RouteReady.then"]
    assert recorded_by_name["RouteReady.then.WriteApproved"]["index"] == (
        expected_indices["RouteReady.then.WriteApproved"]
    )
    assert recorded_by_name["RouteReady"]["index"] == expected_indices["RouteReady"]
    assert recorded_by_name["RouteDecision.APPROVE"]["index"] == expected_indices["RouteDecision.APPROVE"]
    assert recorded_by_name["RouteDecision.APPROVE.EchoApproved"]["index"] == (
        expected_indices["RouteDecision.APPROVE.EchoApproved"]
    )
    assert recorded_by_name["RouteDecision"]["index"] == expected_indices["RouteDecision"]


def test_repeat_until_failure_persists_loop_frame_current_step_and_transition_surfaces(tmp_path: Path):
    workflow_path = _write_yaml(tmp_path / "repeat_until_resume.yaml", _build_repeat_until_resume_workflow())
    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(workspace=tmp_path, run_id="repeat-until-state")
    state_manager.initialize("repeat_until_resume.yaml")

    state = WorkflowExecutor(workflow, tmp_path, state_manager).execute(on_error="stop")
    persisted = _persisted_state(tmp_path, "repeat-until-state")

    assert state["status"] == "failed"
    assert persisted["status"] == "failed"
    assert persisted.get("current_step") is None
    assert persisted["repeat_until"]["ReviewLoop"]["current_iteration"] == 1
    assert persisted["repeat_until"]["ReviewLoop"]["completed_iterations"] == [0]
    assert persisted["repeat_until"]["ReviewLoop"]["condition_evaluated_for_iteration"] is None
    assert persisted["repeat_until"]["ReviewLoop"]["last_condition_result"] is None
    assert persisted["steps"]["ReviewLoop"]["step_id"] == "root.review_loop"
    assert persisted["steps"]["ReviewLoop[1].ResumeGate"]["step_id"] == (
        "root.review_loop#1.iteration_body.resume_gate"
    )
    assert persisted["steps"]["ReviewLoop[1].ResumeGate"]["status"] == "failed"
    assert persisted["steps"]["ReviewLoop[0].WriteDecision"]["step_id"] == (
        "root.review_loop#0.iteration_body.write_decision"
    )
    assert persisted["steps"]["ReviewLoop"]["debug"]["structured_repeat_until"] == {
        "body_id": "iteration_body",
        "max_iterations": 4,
        "current_iteration": 1,
        "completed_iterations": [0],
        "condition_evaluated_for_iteration": None,
        "last_condition_result": None,
    }
    assert persisted["transition_count"] == 0
    assert persisted["step_visits"] == {"ReviewLoop": 1}


def test_repeat_until_call_resume_preserves_call_frame_checkpoint_surfaces(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "repeat_until_review_loop.yaml",
        _build_repeat_until_call_library_workflow(),
    )
    workflow_path = _write_yaml(
        tmp_path / "repeat_until_call_resume.yaml",
        _build_repeat_until_call_resume_workflow(),
    )
    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(workspace=tmp_path, run_id="repeat-until-call-state")
    state_manager.initialize("repeat_until_call_resume.yaml")

    first_run = WorkflowExecutor(workflow, tmp_path, state_manager).execute(on_error="stop")
    failed_state = _persisted_state(tmp_path, "repeat-until-call-state")

    assert first_run["status"] == "failed"
    assert failed_state.get("current_step") is None
    assert failed_state["steps"]["ReviewLoop[1].RunReviewLoop"]["step_id"] == (
        "root.review_loop#1.iteration_body.run_review_loop"
    )
    assert failed_state["steps"]["ReviewLoop[1].RunReviewLoop"]["status"] == "failed"
    assert len(failed_state["call_frames"]) == 2
    failed_frame = next(
        frame
        for frame in failed_state["call_frames"].values()
        if frame["call_step_id"] == "root.review_loop#1.iteration_body.run_review_loop"
    )
    assert failed_frame["status"] == "failed"
    assert failed_frame["export_status"] == "suppressed"
    assert failed_frame["current_step"] is None
    assert failed_frame["state"]["steps"]["WriteBodyHistory"]["status"] == "completed"
    assert failed_frame["state"]["steps"]["ResumeGate"]["status"] == "failed"
    assert failed_frame["state"]["transition_count"] == 1
    failed_transition_count = failed_state["transition_count"]
    assert failed_transition_count == 0

    (tmp_path / "state" / "resume_ready.txt").write_text("ready\n", encoding="utf-8")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = resume_workflow(
            run_id="repeat-until-call-state",
            repair=False,
            force_restart=False,
        )

    resumed_state = _persisted_state(tmp_path, "repeat-until-call-state")

    assert result == 0
    assert resumed_state["status"] == "completed"
    assert resumed_state.get("current_step") is None
    assert resumed_state["transition_count"] == failed_transition_count + 1
    assert len(resumed_state["call_frames"]) == 2
    resumed_frame = next(
        frame
        for frame in resumed_state["call_frames"].values()
        if frame["call_step_id"] == "root.review_loop#1.iteration_body.run_review_loop"
    )
    assert resumed_frame["status"] == "completed"
    assert resumed_frame["export_status"] == "completed"
    assert resumed_frame["state"]["steps"]["ResumeGate"]["status"] == "completed"
    assert resumed_frame["state"]["transition_count"] == 2
    assert resumed_state["steps"]["ReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert resumed_state["step_visits"] == {"ReviewLoop": 2, "VerifyApproval": 1}


def test_finalization_resume_preserves_completed_indices_and_clears_current_step(tmp_path: Path):
    workflow_path = _write_yaml(tmp_path / "resume_finally.yaml", _build_finalization_resume_workflow())
    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(workspace=tmp_path, run_id="finalization-state")
    state_manager.initialize("resume_finally.yaml")

    first_run = WorkflowExecutor(workflow, tmp_path, state_manager).execute(on_error="stop")
    failed_state = _persisted_state(tmp_path, "finalization-state")

    assert first_run["status"] == "failed"
    assert failed_state.get("current_step") is None
    assert failed_state["steps"]["finally.ResumeGate"]["step_id"] == "root.finally.cleanup.resume_gate"
    assert failed_state["finalization"]["status"] == "failed"
    assert failed_state["finalization"]["current_index"] == 1
    assert failed_state["finalization"]["completed_indices"] == [0]
    assert failed_state["finalization"]["failure"]["step"] == "finally.ResumeGate"
    assert failed_state["transition_count"] == 2

    (tmp_path / "state" / "resume_ready.txt").write_text("ready\n", encoding="utf-8")
    with patch("os.getcwd", return_value=str(tmp_path)):
        result = resume_workflow(
            run_id="finalization-state",
            repair=False,
            force_restart=False,
        )

    resumed_state = _persisted_state(tmp_path, "finalization-state")

    assert result == 0
    assert resumed_state["status"] == "completed"
    assert resumed_state.get("current_step") is None
    assert resumed_state["finalization"]["status"] == "completed"
    assert resumed_state["finalization"]["current_index"] is None
    assert resumed_state["finalization"]["completed_indices"] == [0, 1, 2]
    assert resumed_state["transition_count"] == 3
