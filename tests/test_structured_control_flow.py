"""Tests for structured if/else lowering and runtime semantics."""

from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return workflow_file


def _route_review_statement() -> dict:
    return {
        "name": "RouteReview",
        "id": "route_review",
        "if": {
            "artifact_bool": {
                "ref": "root.steps.SetReady.artifacts.ready",
            }
        },
        "then": {
            "id": "approve_path",
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
        "else": {
            "id": "revise_path",
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
    }


def _structured_if_else_workflow(*, include_inserted_sibling: bool = False) -> dict:
    steps = [
        {
            "name": "SetReady",
            "id": "set_ready",
            "set_scalar": {
                "artifact": "ready",
                "value": True,
            },
        },
        _route_review_statement(),
        {
            "name": "CheckRouteDecision",
            "id": "check_route_decision",
            "assert": {
                "compare": {
                    "left": {
                        "ref": "root.steps.RouteReview.artifacts.review_decision",
                    },
                    "op": "eq",
                    "right": "APPROVE",
                }
            },
        },
    ]
    if include_inserted_sibling:
        steps.insert(
            1,
            {
                "name": "InsertedSibling",
                "id": "inserted_sibling",
                "command": ["bash", "-lc", "printf 'inserted\\n'"],
            },
        )

    return {
        "version": "2.2",
        "name": "structured-if-else",
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
        "steps": steps,
    }


def _structured_if_else_with_nested_loop_parent_scope() -> dict:
    return {
        "version": "2.2",
        "name": "structured-if-else-nested-loop-parent-scope",
        "artifacts": {
            "branch_flag": {
                "kind": "scalar",
                "type": "bool",
            },
            "loop_seen": {
                "kind": "scalar",
                "type": "bool",
            },
        },
        "steps": [
            {
                "name": "Route",
                "id": "route",
                "if": {
                    "compare": {
                        "left": 1,
                        "op": "eq",
                        "right": 1,
                    }
                },
                "then": {
                    "id": "approve_path",
                    "steps": [
                        {
                            "name": "SetBranchFlag",
                            "id": "set_branch_flag",
                            "set_scalar": {
                                "artifact": "branch_flag",
                                "value": True,
                            },
                        },
                        {
                            "name": "Loop",
                            "id": "loop",
                            "for_each": {
                                "items": ["one"],
                                "steps": [
                                    {
                                        "name": "MirrorBranchFlag",
                                        "id": "mirror_branch_flag",
                                        "when": {
                                            "artifact_bool": {
                                                "ref": "parent.steps.SetBranchFlag.artifacts.branch_flag",
                                            }
                                        },
                                        "set_scalar": {
                                            "artifact": "loop_seen",
                                            "value": True,
                                        },
                                    },
                                    {
                                        "name": "AssertBranchParent",
                                        "id": "assert_branch_parent",
                                        "assert": {
                                            "artifact_bool": {
                                                "ref": "parent.steps.SetBranchFlag.artifacts.branch_flag",
                                            }
                                        },
                                    },
                                    {
                                        "name": "AssertMirror",
                                        "id": "assert_mirror",
                                        "assert": {
                                            "artifact_bool": {
                                                "ref": "self.steps.MirrorBranchFlag.artifacts.loop_seen",
                                            }
                                        },
                                    },
                                ],
                            },
                        },
                    ],
                },
                "else": {
                    "id": "revise_path",
                    "steps": [
                        {
                            "name": "SetBranchFlag",
                            "id": "set_branch_flag",
                            "set_scalar": {
                                "artifact": "branch_flag",
                                "value": False,
                            },
                        }
                    ],
                },
            }
        ],
    }


def _structured_finally_workflow(
    *,
    include_inserted_sibling: bool = False,
    finalization_fails: bool = False,
    body_fails: bool = False,
    finally_id: str | None = "cleanup",
) -> dict:
    steps = [
        {
            "name": "WriteDecision",
            "id": "write_decision",
            "set_scalar": {
                "artifact": "decision",
                "value": "APPROVE",
            },
        }
    ]
    if include_inserted_sibling:
        steps.insert(
            0,
            {
                "name": "InsertedSibling",
                "id": "inserted_sibling",
                "command": ["bash", "-lc", "mkdir -p state && printf 'inserted\\n' >> state/body.log"],
            },
        )
    if body_fails:
        steps.append(
            {
                "name": "BodyGate",
                "id": "body_gate",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'body-failed\\n' >> state/finalization.log && exit 1",
                ],
            }
        )

    finalization_steps = [
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
        }
    ]
    if finalization_fails:
        finalization_steps.append(
            {
                "name": "FailCleanup",
                "id": "fail_cleanup",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'cleanup-failed\\n' >> state/finalization.log && exit 1",
                ],
            }
        )
    else:
        finalization_steps.append(
            {
                "name": "WriteCleanupMarker",
                "id": "write_cleanup_marker",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'cleanup-complete\\n' >> state/finalization.log",
                ],
            }
        )

    finally_block: dict | list[dict] = {"steps": finalization_steps}
    if finally_id is not None:
        finally_block["id"] = finally_id

    return {
        "version": "2.3",
        "name": "structured-finally",
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
        "steps": steps,
        "finally": finally_block,
    }


def _load_workflow(tmp_path: Path, workflow: dict) -> dict:
    workflow_path = _write_workflow(tmp_path, workflow)
    return WorkflowLoader(tmp_path).load(workflow_path)


def _run_workflow(tmp_path: Path, workflow: dict) -> dict:
    workflow_path = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    return WorkflowExecutor(loaded, tmp_path, state_manager).execute(on_error="continue")


def test_if_else_lowered_step_ids_stay_stable_when_siblings_shift(tmp_path: Path):
    workflow_a = _structured_if_else_workflow()
    workflow_b = _structured_if_else_workflow(include_inserted_sibling=True)

    loaded_a = _load_workflow(tmp_path / "a", workflow_a)
    loaded_b = _load_workflow(tmp_path / "b", workflow_b)

    steps_a = {step["name"]: step["step_id"] for step in loaded_a["steps"]}
    steps_b = {step["name"]: step["step_id"] for step in loaded_b["steps"]}

    assert steps_a["RouteReview.then.WriteApproved"] == "root.route_review.approve_path.write_approved"
    assert steps_a["RouteReview.else.WriteRevision"] == "root.route_review.revise_path.write_revision"
    assert steps_a["RouteReview"] == "root.route_review"
    assert steps_b["RouteReview.then.WriteApproved"] == steps_a["RouteReview.then.WriteApproved"]
    assert steps_b["RouteReview.else.WriteRevision"] == steps_a["RouteReview.else.WriteRevision"]
    assert steps_b["RouteReview"] == steps_a["RouteReview"]


def test_if_else_branch_outputs_materialize_on_statement_and_skip_non_taken_branch(tmp_path: Path):
    state = _run_workflow(tmp_path, _structured_if_else_workflow())

    assert state["status"] == "completed"
    assert state["steps"]["RouteReview.then.WriteApproved"]["status"] == "completed"
    assert state["steps"]["RouteReview.else.WriteRevision"]["status"] == "skipped"
    assert state["steps"]["RouteReview"]["artifacts"]["review_decision"] == "APPROVE"
    assert state["steps"]["RouteReview"]["debug"]["structured_if"]["selected_branch"] == "then"
    assert state["steps"]["CheckRouteDecision"]["exit_code"] == 0


def test_if_else_branch_steps_are_not_visible_outside_statement(tmp_path: Path):
    workflow = _structured_if_else_workflow()
    workflow["steps"].append(
        {
            "name": "IllegalDirectBranchRead",
            "id": "illegal_direct_branch_read",
            "assert": {
                "compare": {
                    "left": {
                        "ref": "root.steps.WriteApproved.artifacts.review_decision",
                    },
                    "op": "eq",
                    "right": "APPROVE",
                }
            },
        }
    )

    workflow_path = _write_workflow(tmp_path, workflow)

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(workflow_path)

    assert any("WriteApproved" in str(err.message) for err in exc_info.value.errors)


def test_if_else_rejects_duplicate_branch_ids(tmp_path: Path):
    workflow = _structured_if_else_workflow()
    workflow["steps"][1]["then"]["id"] = "branch"
    workflow["steps"][1]["else"]["id"] = "branch"

    workflow_path = _write_workflow(tmp_path, workflow)

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(workflow_path)

    assert any("duplicate branch id 'branch'" in str(err.message) for err in exc_info.value.errors)


def test_if_else_nested_for_each_parent_scope_resolves_branch_steps(tmp_path: Path):
    state = _run_workflow(tmp_path, _structured_if_else_with_nested_loop_parent_scope())

    assert state["status"] == "completed"
    assert state["steps"]["Route.then.Loop[0].MirrorBranchFlag"]["status"] == "completed"
    assert state["steps"]["Route.then.Loop[0].MirrorBranchFlag"]["artifacts"] == {"loop_seen": True}
    assert state["steps"]["Route.then.Loop[0].AssertBranchParent"]["status"] == "completed"
    assert state["steps"]["Route.then.Loop[0].AssertMirror"]["status"] == "completed"


def test_finally_step_ids_stay_stable_when_body_siblings_shift(tmp_path: Path):
    workflow_a = _structured_finally_workflow()
    workflow_b = _structured_finally_workflow(include_inserted_sibling=True)

    loaded_a = _load_workflow(tmp_path / "a", workflow_a)
    loaded_b = _load_workflow(tmp_path / "b", workflow_b)

    steps_a = {
        step["name"]: step["step_id"]
        for step in loaded_a["steps"] + loaded_a["finally"]["steps"]
    }
    steps_b = {
        step["name"]: step["step_id"]
        for step in loaded_b["steps"] + loaded_b["finally"]["steps"]
    }

    assert steps_a["finally.ObserveOutputsPending"] == "root.finally.cleanup.observe_outputs_pending"
    assert steps_a["finally.WriteCleanupMarker"] == "root.finally.cleanup.write_cleanup_marker"
    assert steps_b["finally.ObserveOutputsPending"] == steps_a["finally.ObserveOutputsPending"]
    assert steps_b["finally.WriteCleanupMarker"] == steps_a["finally.WriteCleanupMarker"]


def test_finally_rejects_invalid_block_id(tmp_path: Path):
    workflow = _structured_finally_workflow(finally_id="9cleanup")
    workflow_path = _write_workflow(tmp_path, workflow)

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(workflow_path)

    assert any("finally.id must match" in str(err.message) for err in exc_info.value.errors)


def test_finally_runs_after_success_and_defers_workflow_outputs_until_cleanup_completes(tmp_path: Path):
    state = _run_workflow(tmp_path, _structured_finally_workflow())

    assert state["status"] == "completed"
    assert state["steps"]["WriteDecision"]["status"] == "completed"
    assert state["steps"]["finally.ObserveOutputsPending"]["status"] == "completed"
    assert state["steps"]["finally.WriteCleanupMarker"]["status"] == "completed"
    assert state["workflow_outputs"] == {"final_decision": "APPROVE"}
    assert state["finalization"]["status"] == "completed"
    assert state["finalization"]["workflow_outputs_status"] == "completed"
    assert (tmp_path / "state" / "finalization.log").read_text(encoding="utf-8").splitlines() == [
        "outputs-pending",
        "cleanup-complete",
    ]


def test_finally_failure_after_body_success_sets_dedicated_failure_and_suppresses_outputs(tmp_path: Path):
    state = _run_workflow(tmp_path, _structured_finally_workflow(finalization_fails=True))

    assert state["status"] == "failed"
    assert state["steps"]["WriteDecision"]["status"] == "completed"
    assert state["steps"]["finally.FailCleanup"]["status"] == "failed"
    assert state["workflow_outputs"] == {}
    assert state["error"]["type"] == "finalization_failed"
    assert state["finalization"]["status"] == "failed"
    assert state["finalization"]["workflow_outputs_status"] == "suppressed"


def test_finally_preserves_primary_body_failure_when_cleanup_also_fails(tmp_path: Path):
    workflow = _structured_finally_workflow(body_fails=True, finalization_fails=True)
    workflow_path = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute()

    assert state["status"] == "failed"
    assert state["steps"]["BodyGate"]["status"] == "failed"
    assert state["steps"]["finally.FailCleanup"]["status"] == "failed"
    assert state["workflow_outputs"] == {}
    assert state["finalization"]["body_status"] == "failed"
    assert state["finalization"]["failure"]["step"] == "finally.FailCleanup"
    assert not state.get("error") or state["error"]["type"] != "finalization_failed"
