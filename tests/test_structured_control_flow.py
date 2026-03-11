"""Tests for structured if/else lowering and runtime semantics."""

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.surface_ast import freeze_mapping
from tests.workflow_bundle_helpers import (
    materialize_projection_body_steps,
    materialize_projection_finalization_steps,
)


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


def _structured_if_else_with_score_band() -> dict:
    return {
        "version": "2.8",
        "name": "structured-if-else-score-band",
        "artifacts": {
            "quality_score": {
                "kind": "scalar",
                "type": "float",
            },
            "route_action": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["SHIP", "REVIEW"],
            },
        },
        "steps": [
            {
                "name": "WriteScore",
                "id": "write_score",
                "set_scalar": {
                    "artifact": "quality_score",
                    "value": 0.91,
                },
            },
            {
                "name": "RouteScore",
                "id": "route_score",
                "if": {
                    "score": {
                        "ref": "root.steps.WriteScore.artifacts.quality_score",
                        "gte": 0.8,
                        "lt": 0.95,
                    }
                },
                "then": {
                    "id": "review_band",
                    "outputs": {
                        "route_action": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["SHIP", "REVIEW"],
                            "from": {
                                "ref": "self.steps.WriteReview.artifacts.route_action",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "WriteReview",
                            "id": "write_review",
                            "set_scalar": {
                                "artifact": "route_action",
                                "value": "REVIEW",
                            },
                        }
                    ],
                },
                "else": {
                    "id": "ship_band",
                    "outputs": {
                        "route_action": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["SHIP", "REVIEW"],
                            "from": {
                                "ref": "self.steps.WriteShip.artifacts.route_action",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "WriteShip",
                            "id": "write_ship",
                            "set_scalar": {
                                "artifact": "route_action",
                                "value": "SHIP",
                            },
                        }
                    ],
                },
            },
            {
                "name": "CheckScoreRoute",
                "id": "check_score_route",
                "assert": {
                    "compare": {
                        "left": {
                            "ref": "root.steps.RouteScore.artifacts.route_action",
                        },
                        "op": "eq",
                        "right": "REVIEW",
                    }
                },
            },
        ],
    }


def _route_review_match_statement() -> dict:
    return {
        "name": "RouteReviewDecision",
        "id": "route_review_decision",
        "match": {
            "ref": "root.steps.WriteDecision.artifacts.review_decision",
            "cases": {
                "APPROVE": {
                    "id": "approve_path",
                    "outputs": {
                        "route_action": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["SHIP", "FIX", "ESCALATE"],
                            "from": {
                                "ref": "self.steps.WriteApproved.artifacts.route_action",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "WriteApproved",
                            "id": "write_approved",
                            "set_scalar": {
                                "artifact": "route_action",
                                "value": "SHIP",
                            },
                        }
                    ],
                },
                "REVISE": {
                    "id": "revise_path",
                    "outputs": {
                        "route_action": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["SHIP", "FIX", "ESCALATE"],
                            "from": {
                                "ref": "self.steps.WriteRevision.artifacts.route_action",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "WriteRevision",
                            "id": "write_revision",
                            "set_scalar": {
                                "artifact": "route_action",
                                "value": "FIX",
                            },
                        }
                    ],
                },
                "BLOCKED": {
                    "id": "blocked_path",
                    "outputs": {
                        "route_action": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["SHIP", "FIX", "ESCALATE"],
                            "from": {
                                "ref": "self.steps.WriteBlocked.artifacts.route_action",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "WriteBlocked",
                            "id": "write_blocked",
                            "set_scalar": {
                                "artifact": "route_action",
                                "value": "ESCALATE",
                            },
                        }
                    ],
                },
            },
        },
    }


def _structured_match_workflow(*, include_inserted_sibling: bool = False) -> dict:
    steps = [
        {
            "name": "WriteDecision",
            "id": "write_decision",
            "set_scalar": {
                "artifact": "review_decision",
                "value": "REVISE",
            },
        },
        _route_review_match_statement(),
        {
            "name": "CheckRouteAction",
            "id": "check_route_action",
            "assert": {
                "compare": {
                    "left": {
                        "ref": "root.steps.RouteReviewDecision.artifacts.route_action",
                    },
                    "op": "eq",
                    "right": "FIX",
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
        "version": "2.6",
        "name": "structured-match",
        "artifacts": {
            "review_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE", "BLOCKED"],
            },
            "route_action": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["SHIP", "FIX", "ESCALATE"],
            },
        },
        "steps": steps,
    }


def _structured_repeat_until_workflow(*, include_inserted_sibling: bool = False) -> dict:
    steps = [
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
                        "from": {
                            "ref": "self.steps.WriteDecision.artifacts.review_decision",
                        },
                    }
                },
                "condition": {
                    "compare": {
                        "left": {
                            "ref": "self.outputs.review_decision",
                        },
                        "op": "eq",
                        "right": "APPROVE",
                    }
                },
                "max_iterations": 4,
                "steps": [
                    {
                        "name": "WriteDecision",
                        "id": "write_decision",
                        "command": [
                            "bash",
                            "-lc",
                            "\n".join(
                                [
                                    "mkdir -p state",
                                    "count=$(cat state/repeat_count.txt 2>/dev/null || printf '0')",
                                    "count=$((count + 1))",
                                    "printf '%s\\n' \"$count\" > state/repeat_count.txt",
                                    "if [ \"$count\" -ge 3 ]; then",
                                    "  printf 'APPROVE\\n' > state/review_decision.txt",
                                    "else",
                                    "  printf 'REVISE\\n' > state/review_decision.txt",
                                    "fi",
                                    "printf 'iteration-%s\\n' \"$count\" >> state/history.log",
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
                    }
                ],
            },
        },
        {
            "name": "AssertApproved",
            "id": "assert_approved",
            "assert": {
                "compare": {
                    "left": {
                        "ref": "root.steps.ReviewLoop.artifacts.review_decision",
                    },
                    "op": "eq",
                    "right": "APPROVE",
                }
            },
        },
    ]
    if include_inserted_sibling:
        steps.insert(
            0,
            {
                "name": "InsertedSibling",
                "id": "inserted_sibling",
                "command": ["bash", "-lc", "mkdir -p state && printf 'inserted\\n' >> state/history.log"],
            },
        )

    return {
        "version": "2.7",
        "name": "structured-repeat-until",
        "steps": steps,
    }


def _write_repeat_until_call_library(workspace: Path) -> None:
    library_path = workspace / "workflows" / "library" / "repeat_until_review_loop.yaml"
    library_path.parent.mkdir(parents=True, exist_ok=True)
    library_path.write_text(
        yaml.safe_dump(
        {
            "version": "2.7",
            "name": "repeat-until-review-loop",
            "inputs": {
                "iteration": {
                    "kind": "scalar",
                    "type": "integer",
                },
                "write_root": {
                    "kind": "relpath",
                    "type": "relpath",
                }
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
                    "from": {
                        "ref": "root.steps.WriteReviewDecision.artifacts.review_decision",
                    },
                }
            },
            "steps": [
                {
                    "name": "WriteReviewDecision",
                    "id": "write_review_decision",
                    "command": [
                        "bash",
                        "-lc",
                        "\n".join(
                            [
                                "mkdir -p \"${inputs.write_root}\"",
                                "mkdir -p state/review-loop",
                                "count=\"${inputs.iteration}\"",
                                "if [ \"$count\" -ge 3 ]; then",
                                "  printf 'APPROVE\\n' > \"${inputs.write_root}/review_decision.txt\"",
                                "else",
                                "  printf 'REVISE\\n' > \"${inputs.write_root}/review_decision.txt\"",
                                "fi",
                                "printf 'iteration-%s\\n' \"$count\" >> state/review-loop/history.log",
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
                }
            ],
        },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _structured_repeat_until_with_call_and_match_workflow(
    *,
    include_inserted_sibling: bool = False,
) -> dict:
    steps = [
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
                        "from": {
                            "ref": "self.steps.RouteDecision.artifacts.review_decision",
                        },
                    }
                },
                "condition": {
                    "compare": {
                        "left": {
                            "ref": "self.outputs.review_decision",
                        },
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
                                    "printf '{\"write_root\":\"state/review-loop/iterations/%s\",\"iteration\":%s}\\n' \"$iteration\" \"$iteration\" > state/review-loop-inputs/current.json",
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
                                "REVISE": {
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
                            },
                        },
                    },
                ],
            },
        },
        {
            "name": "AssertApproved",
            "id": "assert_approved",
            "assert": {
                "compare": {
                    "left": {
                        "ref": "root.steps.ReviewLoop.artifacts.review_decision",
                    },
                    "op": "eq",
                    "right": "APPROVE",
                }
            },
        },
    ]
    if include_inserted_sibling:
        steps.insert(
            0,
            {
                "name": "InsertedSibling",
                "id": "inserted_sibling",
                "command": ["bash", "-lc", "mkdir -p state && printf 'inserted\\n' >> state/history.log"],
            },
        )

    return {
        "version": "2.7",
        "name": "structured-repeat-until-call-match",
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
        "steps": steps,
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


def _load_workflow(tmp_path: Path, workflow: dict):
    workflow_path = _write_workflow(tmp_path, workflow)
    return WorkflowLoader(tmp_path).load_bundle(workflow_path)


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

    steps_a = {step["name"]: step["step_id"] for step in materialize_projection_body_steps(loaded_a)}
    steps_b = {step["name"]: step["step_id"] for step in materialize_projection_body_steps(loaded_b)}

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


def test_if_else_executes_from_bound_guard_and_join_outputs_when_legacy_refs_are_corrupted(tmp_path: Path):
    workflow_path = _write_workflow(tmp_path, _structured_if_else_workflow())
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    route_review_node = bundle.ir.nodes["root.route_review"]
    corrupted_raw = {
        **dict(route_review_node.raw),
        "if": {
            "artifact_bool": {
                "ref": "root.steps.Missing.artifacts.ready",
            }
        },
        "then": {
            **dict(route_review_node.raw.get("then", {})),
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {
                        "ref": "root.steps.Missing.artifacts.review_decision",
                    },
                }
            },
        },
    }
    bundle = replace(
        bundle,
        ir=replace(
            bundle.ir,
            nodes=MappingProxyType({
                **bundle.ir.nodes,
                "root.route_review": replace(
                    route_review_node,
                    raw=freeze_mapping(corrupted_raw),
                ),
            }),
        ),
    )

    state_manager = StateManager(workspace=tmp_path, run_id="structured-bound-refs")
    state_manager.initialize("workflow.yaml")
    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(on_error="continue")

    assert state["status"] == "completed"
    assert state["steps"]["RouteReview.then.WriteApproved"]["status"] == "completed"
    assert state["steps"]["RouteReview.else.WriteRevision"]["status"] == "skipped"
    assert state["steps"]["RouteReview"]["artifacts"]["review_decision"] == "APPROVE"
    assert state["steps"]["CheckRouteDecision"]["status"] == "completed"


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


def test_if_else_can_branch_on_score_band_predicate(tmp_path: Path):
    state = _run_workflow(tmp_path, _structured_if_else_with_score_band())

    assert state["status"] == "completed"
    assert state["steps"]["RouteScore"]["artifacts"] == {"route_action": "REVIEW"}
    assert state["steps"]["CheckScoreRoute"]["status"] == "completed"


def test_match_lowered_step_ids_stay_stable_when_siblings_shift(tmp_path: Path):
    workflow_a = _structured_match_workflow()
    workflow_b = _structured_match_workflow(include_inserted_sibling=True)

    loaded_a = _load_workflow(tmp_path / "a", workflow_a)
    loaded_b = _load_workflow(tmp_path / "b", workflow_b)

    steps_a = {step["name"]: step["step_id"] for step in materialize_projection_body_steps(loaded_a)}
    steps_b = {step["name"]: step["step_id"] for step in materialize_projection_body_steps(loaded_b)}

    assert steps_a["RouteReviewDecision.APPROVE.WriteApproved"] == (
        "root.route_review_decision.approve_path.write_approved"
    )
    assert steps_a["RouteReviewDecision.REVISE.WriteRevision"] == (
        "root.route_review_decision.revise_path.write_revision"
    )
    assert steps_a["RouteReviewDecision.BLOCKED.WriteBlocked"] == (
        "root.route_review_decision.blocked_path.write_blocked"
    )
    assert steps_a["RouteReviewDecision"] == "root.route_review_decision"
    assert steps_b["RouteReviewDecision.APPROVE.WriteApproved"] == (
        steps_a["RouteReviewDecision.APPROVE.WriteApproved"]
    )
    assert steps_b["RouteReviewDecision.REVISE.WriteRevision"] == (
        steps_a["RouteReviewDecision.REVISE.WriteRevision"]
    )
    assert steps_b["RouteReviewDecision.BLOCKED.WriteBlocked"] == (
        steps_a["RouteReviewDecision.BLOCKED.WriteBlocked"]
    )
    assert steps_b["RouteReviewDecision"] == steps_a["RouteReviewDecision"]


def test_match_case_outputs_materialize_on_statement_and_skip_non_selected_cases(tmp_path: Path):
    state = _run_workflow(tmp_path, _structured_match_workflow())

    assert state["status"] == "completed"
    assert state["steps"]["RouteReviewDecision.APPROVE.WriteApproved"]["status"] == "skipped"
    assert state["steps"]["RouteReviewDecision.REVISE.WriteRevision"]["status"] == "completed"
    assert state["steps"]["RouteReviewDecision.BLOCKED.WriteBlocked"]["status"] == "skipped"
    assert state["steps"]["RouteReviewDecision"]["artifacts"]["route_action"] == "FIX"
    assert state["steps"]["RouteReviewDecision"]["debug"]["structured_match"]["selected_case"] == "REVISE"
    assert state["steps"]["CheckRouteAction"]["exit_code"] == 0


def test_repeat_until_body_step_ids_stay_stable_when_siblings_shift(tmp_path: Path):
    workflow_a = _structured_repeat_until_workflow()
    workflow_b = _structured_repeat_until_workflow(include_inserted_sibling=True)

    loaded_a = _load_workflow(tmp_path / "a", workflow_a)
    loaded_b = _load_workflow(tmp_path / "b", workflow_b)

    steps_a = {step["name"]: step for step in materialize_projection_body_steps(loaded_a)}
    steps_b = {step["name"]: step for step in materialize_projection_body_steps(loaded_b)}

    body_a = {
        step["name"]: step["step_id"]
        for step in steps_a["ReviewLoop"]["repeat_until"]["steps"]
    }
    body_b = {
        step["name"]: step["step_id"]
        for step in steps_b["ReviewLoop"]["repeat_until"]["steps"]
    }

    assert steps_a["ReviewLoop"]["step_id"] == "root.review_loop"
    assert body_a["WriteDecision"] == "root.review_loop.iteration_body.write_decision"
    assert steps_b["ReviewLoop"]["step_id"] == steps_a["ReviewLoop"]["step_id"]
    assert body_b["WriteDecision"] == body_a["WriteDecision"]


def test_repeat_until_materializes_loop_frame_outputs_and_iteration_results(tmp_path: Path):
    state = _run_workflow(tmp_path, _structured_repeat_until_workflow())

    assert state["status"] == "completed"
    assert state["steps"]["ReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert state["steps"]["ReviewLoop"]["debug"]["structured_repeat_until"]["completed_iterations"] == [
        0,
        1,
        2,
    ]
    assert state["steps"]["ReviewLoop[0].WriteDecision"]["artifacts"]["review_decision"] == "REVISE"
    assert state["steps"]["ReviewLoop[1].WriteDecision"]["artifacts"]["review_decision"] == "REVISE"
    assert state["steps"]["ReviewLoop[2].WriteDecision"]["artifacts"]["review_decision"] == "APPROVE"


def test_repeat_until_uses_bound_outputs_and_condition_when_legacy_refs_are_corrupted(tmp_path: Path):
    workflow_path = _write_workflow(tmp_path, _structured_repeat_until_workflow())
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    review_loop_node = bundle.ir.nodes["root.review_loop"]
    corrupted_raw = {
        **dict(review_loop_node.raw),
        "repeat_until": {
            **dict(review_loop_node.raw.get("repeat_until", {})),
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {
                        "ref": "self.steps.Missing.artifacts.review_decision",
                    },
                }
            },
            "condition": {
                "compare": {
                    "left": {
                        "ref": "root.steps.Missing.artifacts.review_decision",
                    },
                    "op": "eq",
                    "right": "APPROVE",
                }
            },
        },
    }
    bundle = replace(
        bundle,
        ir=replace(
            bundle.ir,
            nodes=MappingProxyType({
                **bundle.ir.nodes,
                "root.review_loop": replace(
                    review_loop_node,
                    raw=freeze_mapping(corrupted_raw),
                ),
            }),
        ),
    )

    state_manager = StateManager(workspace=tmp_path, run_id="repeat-until-bound-refs")
    state_manager.initialize("workflow.yaml")
    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(on_error="continue")

    assert state["status"] == "completed"
    assert state["steps"]["ReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert state["steps"]["ReviewLoop[2].WriteDecision"]["artifacts"]["review_decision"] == "APPROVE"
    assert state["steps"]["ReviewLoop[0].WriteDecision"]["step_id"] == (
        "root.review_loop#0.iteration_body.write_decision"
    )
    assert state["steps"]["ReviewLoop[2].WriteDecision"]["step_id"] == (
        "root.review_loop#2.iteration_body.write_decision"
    )
    assert state["steps"]["AssertApproved"]["status"] == "completed"
    assert (tmp_path / "state" / "history.log").read_text(encoding="utf-8").splitlines() == [
        "iteration-1",
        "iteration-2",
        "iteration-3",
    ]


def test_repeat_until_uses_typed_output_contract_definition_without_ir_contract_raw_payloads(
    tmp_path: Path,
):
    workflow_path = _write_workflow(tmp_path, _structured_repeat_until_workflow())
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    review_loop_node = bundle.ir.nodes["root.review_loop"]
    assert not hasattr(review_loop_node.output_contracts["review_decision"], "raw")

    corrupted_raw = {
        **dict(review_loop_node.raw),
        "repeat_until": {
            **dict(review_loop_node.raw.get("repeat_until", {})),
            "outputs": {
                **dict(review_loop_node.raw.get("repeat_until", {}).get("outputs", {})),
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["BLOCKED"],
                    "from": {
                        "ref": "self.steps.WriteDecision.artifacts.review_decision",
                    },
                },
            },
        },
    }
    bundle = replace(
        bundle,
        ir=replace(
            bundle.ir,
            nodes=MappingProxyType({
                **bundle.ir.nodes,
                "root.review_loop": replace(
                    review_loop_node,
                    raw=freeze_mapping(corrupted_raw),
                ),
            }),
        ),
    )

    state_manager = StateManager(workspace=tmp_path, run_id="repeat-until-bound-contract")
    state_manager.initialize("workflow.yaml")
    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(on_error="continue")

    assert state["status"] == "completed"
    assert state["steps"]["ReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert state["steps"]["AssertApproved"]["status"] == "completed"


def test_repeat_until_nested_call_and_match_step_ids_stay_stable_when_siblings_shift(tmp_path: Path):
    _write_repeat_until_call_library(tmp_path / "a")
    _write_repeat_until_call_library(tmp_path / "b")
    workflow_a = _structured_repeat_until_with_call_and_match_workflow()
    workflow_b = _structured_repeat_until_with_call_and_match_workflow(include_inserted_sibling=True)

    loaded_a = _load_workflow(tmp_path / "a", workflow_a)
    loaded_b = _load_workflow(tmp_path / "b", workflow_b)

    steps_a = {step["name"]: step for step in materialize_projection_body_steps(loaded_a)}
    steps_b = {step["name"]: step for step in materialize_projection_body_steps(loaded_b)}

    body_a = {
        step["name"]: step["step_id"]
        for step in steps_a["ReviewLoop"]["repeat_until"]["steps"]
    }
    body_b = {
        step["name"]: step["step_id"]
        for step in steps_b["ReviewLoop"]["repeat_until"]["steps"]
    }

    assert steps_a["ReviewLoop"]["step_id"] == "root.review_loop"
    assert body_a["RunReviewLoop"] == "root.review_loop.iteration_body.run_review_loop"
    assert body_a["RouteDecision.APPROVE"] == "root.review_loop.iteration_body.route_decision.approve_path"
    assert (
        body_a["RouteDecision.APPROVE.WriteApproved"]
        == "root.review_loop.iteration_body.route_decision.approve_path.write_approved"
    )
    assert body_a["RouteDecision.REVISE"] == "root.review_loop.iteration_body.route_decision.revise_path"
    assert body_a["RouteDecision"] == "root.review_loop.iteration_body.route_decision"
    assert steps_b["ReviewLoop"]["step_id"] == steps_a["ReviewLoop"]["step_id"]
    assert body_b == body_a


def test_repeat_until_executes_nested_call_and_match_with_iteration_scoped_call_frames(tmp_path: Path):
    _write_repeat_until_call_library(tmp_path)
    state = _run_workflow(tmp_path, _structured_repeat_until_with_call_and_match_workflow())

    assert state["status"] == "completed"
    assert state["steps"]["ReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert state["steps"]["ReviewLoop[0].RunReviewLoop"]["artifacts"] == {"review_decision": "REVISE"}
    assert state["steps"]["ReviewLoop[0].RouteDecision.REVISE.WriteRevision"]["status"] == "completed"
    assert state["steps"]["ReviewLoop[0].RouteDecision.APPROVE.WriteApproved"]["status"] == "skipped"
    assert state["steps"]["ReviewLoop[2].RunReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert state["steps"]["ReviewLoop[2].RouteDecision.APPROVE.WriteApproved"]["status"] == "completed"
    assert state["steps"]["ReviewLoop[2].RouteDecision"]["artifacts"] == {"review_decision": "APPROVE"}
    assert state["steps"]["ReviewLoop[0].RunReviewLoop"]["step_id"] == (
        "root.review_loop#0.iteration_body.run_review_loop"
    )
    assert state["steps"]["ReviewLoop[2].RouteDecision"]["step_id"] == (
        "root.review_loop#2.iteration_body.route_decision"
    )
    assert len(state.get("call_frames", {})) == 3
    assert sorted(frame["call_step_id"] for frame in state["call_frames"].values()) == [
        "root.review_loop#0.iteration_body.run_review_loop",
        "root.review_loop#1.iteration_body.run_review_loop",
        "root.review_loop#2.iteration_body.run_review_loop",
    ]
    assert (tmp_path / "state" / "review-loop" / "history.log").read_text(encoding="utf-8").splitlines() == [
        "iteration-1",
        "iteration-2",
        "iteration-3",
    ]


def test_finally_step_ids_stay_stable_when_body_siblings_shift(tmp_path: Path):
    workflow_a = _structured_finally_workflow()
    workflow_b = _structured_finally_workflow(include_inserted_sibling=True)

    loaded_a = _load_workflow(tmp_path / "a", workflow_a)
    loaded_b = _load_workflow(tmp_path / "b", workflow_b)

    steps_a = {
        step["name"]: step["step_id"]
        for step in materialize_projection_body_steps(loaded_a) + materialize_projection_finalization_steps(loaded_a)
    }
    steps_b = {
        step["name"]: step["step_id"]
        for step in materialize_projection_body_steps(loaded_b) + materialize_projection_finalization_steps(loaded_b)
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
