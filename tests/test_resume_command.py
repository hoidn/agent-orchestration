"""Tests for the CLI resume command (AT-4)."""

import os
import json
import pytest
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import shutil
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import hashlib
import yaml

import orchestrator.workflow.loaded_bundle as loaded_bundle_helpers
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.monitor.process import write_process_metadata
from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow.loaded_bundle import workflow_managed_write_root_inputs
from orchestrator.workflow.identity import iteration_step_id
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.resume_planner import ResumePlanner
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict, materialize_projection_body_steps


def _workflow_runtime_context_inputs(bundle):
    helper = getattr(
        loaded_bundle_helpers,
        "workflow_runtime_context_inputs",
        lambda _: (),
    )
    return helper(bundle)


def _workflow_boundary_projection(bundle):
    helper = getattr(loaded_bundle_helpers, "workflow_boundary_projection")
    return helper(bundle)


def _workflow_generated_path_allocations(bundle):
    helper = getattr(loaded_bundle_helpers, "workflow_generated_path_allocations")
    return helper(bundle)


def _allocation_field(allocation, field_name: str):
    if isinstance(allocation, dict):
        return allocation[field_name]
    return getattr(allocation, field_name)


def _build_resume_loop_workflow() -> dict:
    return {
        "version": "1.1",
        "name": "Resume Loop Workflow",
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


def _build_structured_if_else_resume_workflow() -> dict:
    return {
        "version": "2.2",
        "name": "Resume Structured If Else Workflow",
        "artifacts": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
            },
            "route_result": {
                "kind": "scalar",
                "type": "bool",
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
                        "route_result": {
                            "kind": "scalar",
                            "type": "bool",
                            "from": {
                                "ref": "self.steps.SetRouteResult.artifacts.route_result",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "WriteHistory",
                            "id": "write_history",
                            "command": [
                                "bash",
                                "-lc",
                                "mkdir -p state && printf 'write-one\\n' >> state/history.log",
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
                                        "  printf 'gate-failed\\n' >> state/history.log",
                                        "  exit 1",
                                        "fi",
                                        "printf 'gate-passed\\n' >> state/history.log",
                                    ]
                                ),
                            ],
                        },
                        {
                            "name": "SetRouteResult",
                            "id": "set_route_result",
                            "set_scalar": {
                                "artifact": "route_result",
                                "value": True,
                            },
                        },
                    ],
                },
                "else": {
                    "id": "revise_path",
                    "outputs": {
                        "route_result": {
                            "kind": "scalar",
                            "type": "bool",
                            "from": {
                                "ref": "self.steps.SetRouteResult.artifacts.route_result",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "SetRouteResult",
                            "id": "set_route_result",
                            "set_scalar": {
                                "artifact": "route_result",
                                "value": False,
                            },
                        }
                    ],
                },
            },
            {
                "name": "VerifyRouteResult",
                "id": "verify_route_result",
                "command": [
                    "bash",
                    "-lc",
                    "test \"${steps.RouteReview.artifacts.route_result}\" = true && "
                    "[ \"$(grep -c '^write-one$' state/history.log)\" -eq 1 ]",
                ],
            },
        ],
    }


def _build_structured_finally_resume_workflow() -> dict:
    return {
        "version": "2.3",
        "name": "Resume Structured Finally Workflow",
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


def _build_repeat_until_resume_workflow() -> dict:
    return {
        "version": "2.7",
        "name": "Resume Repeat Until Workflow",
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
                        "left": {
                            "ref": "root.steps.ReviewLoop.artifacts.review_decision",
                        },
                        "op": "eq",
                        "right": "APPROVE",
                    }
                },
            },
        ],
    }


def _build_finally_resume_workflow() -> dict:
    return {
        "version": "2.3",
        "name": "Resume Finally Workflow",
        "steps": [
            {
                "name": "WriteBodyHistory",
                "id": "write_body_history",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'body\\n' >> state/history.log",
                ],
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


def _build_call_resume_library_workflow() -> dict:
    return {
        "version": "2.5",
        "name": "resume-review-loop",
        "inputs": {
            "write_root": {
                "kind": "relpath",
                "type": "relpath",
            }
        },
        "artifacts": {
            "approved": {
                "kind": "scalar",
                "type": "bool",
            }
        },
        "outputs": {
            "approved": {
                "kind": "scalar",
                "type": "bool",
                "from": {
                    "ref": "root.steps.SetApproved.artifacts.approved",
                },
            }
        },
        "steps": [
            {
                "name": "WriteHistory",
                "id": "write_history",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "mkdir -p \"${inputs.write_root}\"",
                            "printf 'child-one\\n' >> \"${inputs.write_root}/history.log\"",
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
                            "mkdir -p \"${inputs.write_root}\"",
                            "if [ ! -f state/resume_ready.txt ]; then",
                            "  printf 'gate-failed\\n' >> \"${inputs.write_root}/history.log\"",
                            "  exit 1",
                            "fi",
                            "printf 'gate-passed\\n' >> \"${inputs.write_root}/history.log\"",
                        ]
                    ),
                ],
            },
            {
                "name": "SetApproved",
                "id": "set_approved",
                "set_scalar": {
                    "artifact": "approved",
                    "value": True,
                },
            },
        ],
    }


def _build_call_resume_caller_workflow() -> dict:
    return {
        "version": "2.5",
        "name": "resume-call-workflow",
        "imports": {
            "review_loop": "workflows/library/review_fix_loop.yaml",
        },
        "steps": [
            {
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "write_root": "state/review-loop",
                },
            },
            {
                "name": "VerifyApproved",
                "id": "verify_approved",
                "assert": {
                    "artifact_bool": {
                        "ref": "root.steps.RunReviewLoop.artifacts.approved",
                    }
                },
            },
        ],
    }


def _build_since_last_consume_resume_workflow() -> dict:
    return {
        "version": "2.14",
        "name": "resume-since-last-consume-workflow",
        "artifacts": {
            "review_feedback": {
                "kind": "scalar",
                "type": "string",
            }
        },
        "steps": [
            {
                "name": "PublishReview",
                "id": "publish_review",
                "set_scalar": {
                    "artifact": "review_feedback",
                    "value": "revise the implementation",
                },
                "publishes": [{"artifact": "review_feedback", "from": "review_feedback"}],
            },
            {
                "name": "FixImplementation",
                "id": "fix_implementation",
                "consumes": [
                    {
                        "artifact": "review_feedback",
                        "policy": "latest_successful",
                        "freshness": "since_last_consume",
                    }
                ],
                "consume_bundle": {"path": "state/fix_bundle.json"},
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "mkdir -p state",
                            "if [ ! -f state/resume_ready.txt ]; then",
                            "  printf 'attempted\\n' >> state/history.log",
                            "  exit 1",
                            "fi",
                            "cat state/fix_bundle.json > state/consumed.json",
                            "printf 'resumed\\n' >> state/history.log",
                        ]
                    ),
                ],
            },
        ],
    }


def _build_repeat_until_call_resume_library_workflow() -> dict:
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
                    "ref": "root.steps.WriteDecision.artifacts.review_decision",
                },
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
        "name": "repeat-until-call-resume-workflow",
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
                "name": "VerifyApproval",
                "id": "verify_approval",
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
        ],
    }


def _write_frontend_loop_recur_workflow(workspace: Path) -> Path:
    fixture = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid" / "loop_recur_minimal.orc"
    result = compile_stage3_module(
        fixture,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=workspace,
    )
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "loop-recur-minimal"
    )
    workflow_path = workspace / "loop_recur_minimal.yaml"
    workflow_path.write_text(yaml.safe_dump(lowered.authored_mapping, sort_keys=False), encoding="utf-8")
    return workflow_path


def _build_projection_runtime_plan_snapshot_workflow() -> dict:
    return {
        "version": "2.14",
        "name": "projection-runtime-plan-snapshot-workflow",
        "artifacts": {
            "review_feedback": {
                "kind": "scalar",
                "type": "string",
            }
        },
        "steps": [
            {
                "name": "PublishReview",
                "id": "publish_review",
                "set_scalar": {
                    "artifact": "review_feedback",
                    "value": "revise the implementation",
                },
                "publishes": [{"artifact": "review_feedback", "from": "review_feedback"}],
            },
            {
                "name": "MaterializeTargets",
                "id": "materialize_targets",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "execution_report_target_path",
                            "source": {"literal": "artifacts/work/execution_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                            "pointer": {"path": "state/execution_report_target_path.txt"},
                            "ensure_parent": True,
                        },
                        {
                            "name": "progress_report_target_path",
                            "source": {"literal": "artifacts/work/progress_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                            "pointer": {"path": "state/progress_report_target_path.txt"},
                            "ensure_parent": True,
                        },
                    ]
                },
            },
            {
                "name": "PrepareResultBundle",
                "id": "prepare_result_bundle",
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "path = Path('state/implementation_bundle.json')\n"
                        "path.parent.mkdir(parents=True, exist_ok=True)\n"
                        "path.write_text('{\"implementation_state\":\"COMPLETED\"}\\n', encoding='utf-8')\n"
                    ),
                ],
                "output_bundle": {
                    "path": "state/implementation_bundle.json",
                    "fields": [
                        {
                            "name": "implementation_state",
                            "json_pointer": "/implementation_state",
                            "type": "enum",
                            "allowed": ["COMPLETED", "BLOCKED"],
                        }
                    ],
                },
                "pre_snapshot": {
                    "name": "implementation_outcome_before",
                    "digest": "sha256",
                    "candidates": {
                        "COMPLETED": {
                            "ref": "root.steps.MaterializeTargets.artifacts.execution_report_target_path",
                        },
                        "BLOCKED": {
                            "ref": "root.steps.MaterializeTargets.artifacts.progress_report_target_path",
                        },
                    },
                },
            },
            {
                "name": "SelectImplementationOutcome",
                "id": "select_implementation_outcome",
                "select_variant_output": {
                    "path": "state/implementation_state.json",
                    "discriminant": {
                        "name": "implementation_state",
                        "json_pointer": "/implementation_state",
                        "type": "enum",
                        "allowed": ["COMPLETED", "BLOCKED"],
                    },
                    "variants": {
                        "COMPLETED": {
                            "fields": [
                                {
                                    "name": "execution_report_path",
                                    "json_pointer": "/execution_report_path",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                        "BLOCKED": {
                            "fields": [
                                {
                                    "name": "progress_report_path",
                                    "json_pointer": "/progress_report_path",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                    },
                    "evidence": {
                        "mode": "snapshot_diff",
                        "snapshot": {
                            "ref": "root.steps.PrepareResultBundle.snapshots.implementation_outcome_before",
                        },
                    },
                },
            },
        ],
    }


def _seed_resume_loop_state(workspace: Path, *, run_id: str) -> tuple[Path, StateManager]:
    workflow_path = workspace / "resume_loop.yaml"
    workflow_path.write_text(yaml.safe_dump(_build_resume_loop_workflow(), sort_keys=False))

    state_dir = workspace / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "review_count.txt").write_text("1\n")
    (state_dir / "cycle.txt").write_text("1\n")
    (state_dir / "decision.txt").write_text("REVISE\n")
    (state_dir / "history.log").write_text("review-1\nfix\nincrement-1\n")

    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize("resume_loop.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {
        "ReviewImplementation": {"status": "completed", "exit_code": 0},
        "ImplementationReviewGate": {"status": "failed", "exit_code": 1},
        "ImplementationCycleGate": {"status": "completed", "exit_code": 0},
        "FixImplementation": {"status": "completed", "exit_code": 0},
        "IncrementImplementationCycle": {"status": "completed", "exit_code": 0},
    }
    state_manager._write_state()
    return workflow_path, state_manager


def _seed_structured_if_else_failure(workspace: Path, *, run_id: str) -> tuple[Path, StateManager]:
    workflow_path = workspace / "structured_if_else_resume.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_structured_if_else_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize("structured_if_else_resume.yaml")
    workflow = WorkflowLoader(workspace).load(workflow_path)
    state = WorkflowExecutor(workflow, workspace, state_manager).execute(on_error="stop")

    assert state["status"] == "failed"
    return workflow_path, state_manager


def _seed_repeat_until_failure(workspace: Path, *, run_id: str) -> tuple[Path, StateManager]:
    workflow_path = workspace / "repeat_until_resume.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_repeat_until_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize("repeat_until_resume.yaml")
    workflow = WorkflowLoader(workspace).load(workflow_path)
    state = WorkflowExecutor(workflow, workspace, state_manager).execute(on_error="stop")

    assert state["status"] == "failed"
    return workflow_path, state_manager


def test_projection_runtime_plan_summarizes_artifacts_and_snapshots_from_executable_config(
    tmp_path: Path,
):
    workflow_path = tmp_path / "projection_runtime_plan_snapshot.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_projection_runtime_plan_snapshot_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    runtime_plan = bundle.runtime_plan

    publication_modes = {
        (artifact.source_node_id, artifact.publication_mode, artifact.contract_name)
        for artifact in runtime_plan.artifacts
    }
    snapshot_modes = {
        (snapshot.owner_node_id, snapshot.operation_kind, snapshot.selection_relevant)
        for snapshot in runtime_plan.snapshots
    }

    assert ("root.publish_review", "publishes", "review_feedback") in publication_modes
    assert (
        "root.prepare_result_bundle",
        "output_bundle",
        "implementation_state",
    ) in publication_modes
    assert (
        "root.materialize_targets",
        "materialize_artifacts",
        False,
    ) in snapshot_modes
    assert (
        "root.prepare_result_bundle",
        "pre_snapshot",
        True,
    ) in snapshot_modes
    assert (
        "root.select_implementation_outcome",
        "select_variant_output",
        True,
    ) in snapshot_modes


def test_repeat_until_runtime_plan_checkpoint_metadata_preserves_projection_resume_authority(
    tmp_path: Path,
):
    library_path = tmp_path / "workflows" / "library" / "repeat_until_review_loop.yaml"
    library_path.parent.mkdir(parents=True, exist_ok=True)
    library_path.write_text(
        yaml.safe_dump(_build_repeat_until_call_resume_library_workflow(), sort_keys=False),
        encoding="utf-8",
    )
    workflow_path = tmp_path / "repeat_until_call_resume.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_repeat_until_call_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    runtime_plan = bundle.runtime_plan
    planner = ResumePlanner()

    call_checkpoint = next(
        checkpoint
        for checkpoint in runtime_plan.resume_checkpoints
        if checkpoint.node_id == "root.review_loop.iteration_body.run_review_loop"
    )
    frame_checkpoint = next(
        checkpoint
        for checkpoint in runtime_plan.resume_checkpoints
        if checkpoint.node_id == "root.review_loop"
    )
    restart_index = planner.determine_restart_index(
        {
            "steps": {},
            "current_step": {
                "name": "ReviewLoop",
                "status": "running",
                "step_id": "root.review_loop",
            },
        },
        projection=bundle.projection,
    )

    assert call_checkpoint.checkpoint_kind == "call_boundary"
    assert call_checkpoint.runtime_step_id_mode == "qualified_iteration"
    assert call_checkpoint.iteration_owner_node_id == "root.review_loop"
    assert call_checkpoint.iteration_step_id_suffix == "iteration_body.run_review_loop"
    assert frame_checkpoint.checkpoint_kind == "repeat_until_frame"
    assert frame_checkpoint.presentation_key == bundle.projection.repeat_until_frame_key("root.review_loop")
    assert restart_index == bundle.projection.compatibility_index_by_node_id["root.review_loop"]


def test_frontend_generated_loop_recur_runtime_plan_preserves_repeat_until_resume_authority(
    tmp_path: Path,
):
    workflow_path = _write_frontend_loop_recur_workflow(tmp_path)

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    runtime_plan = bundle.runtime_plan
    planner = ResumePlanner()

    frame_checkpoint = next(
        checkpoint
        for checkpoint in runtime_plan.resume_checkpoints
        if checkpoint.node_id == "root.loop_recur_minimal__loop"
    )
    restart_index = planner.determine_restart_index(
        {
            "steps": {},
            "current_step": {
                "name": "loop-recur-minimal__loop",
                "status": "running",
                "step_id": "root.loop_recur_minimal__loop",
            },
        },
        projection=bundle.projection,
    )

    assert frame_checkpoint.checkpoint_kind == "repeat_until_frame"
    assert frame_checkpoint.presentation_key == bundle.projection.repeat_until_frame_key(
        "root.loop_recur_minimal__loop"
    )
    assert restart_index == bundle.projection.compatibility_index_by_node_id["root.loop_recur_minimal__loop"]


def _seed_repeat_until_call_failure(workspace: Path, *, run_id: str) -> tuple[Path, StateManager]:
    library_path = workspace / "workflows" / "library" / "repeat_until_review_loop.yaml"
    library_path.parent.mkdir(parents=True, exist_ok=True)
    library_path.write_text(
        yaml.safe_dump(_build_repeat_until_call_resume_library_workflow(), sort_keys=False),
        encoding="utf-8",
    )
    workflow_path = workspace / "repeat_until_call_resume.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_repeat_until_call_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize("repeat_until_call_resume.yaml")
    workflow = WorkflowLoader(workspace).load(workflow_path)
    state = WorkflowExecutor(workflow, workspace, state_manager).execute(on_error="stop")

    assert state["status"] == "failed"
    return workflow_path, state_manager


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


@pytest.fixture
def sample_workflow(temp_workspace):
    """Create a sample workflow file."""
    workflow_path = temp_workspace / "test_workflow.yaml"
    workflow_content = """
version: "1.1"
name: Test Resume Workflow
steps:
  - name: Step1
    command: ["echo", "Hello from Step1"]
    output_capture: text
  - name: Step2
    command: ["echo", "Hello from Step2"]
    output_capture: text
  - name: Step3
    command: ["echo", "Hello from Step3"]
    output_capture: text
"""
    workflow_path.write_text(workflow_content)

    # Calculate checksum in StateManager format
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    return workflow_path, checksum


@pytest.fixture
def partial_run_state(temp_workspace, sample_workflow):
    """Create a partial run state with Step1 completed."""
    workflow_path, checksum = sample_workflow
    run_id = "test-run-123"

    # Create state directory
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    # Create state.json
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "Step1": {
                "status": "completed",
                "exit_code": 0,
                "output": "Hello from Step1",
                "started_at": "2024-01-01T00:00:01Z",
                "completed_at": "2024-01-01T00:00:02Z",
                "duration_ms": 1000
            }
        }
    }

    state_file = state_dir / "state.json"
    state_file.write_text(json.dumps(state, indent=2))

    return run_id, state_dir


def test_at4_resume_nonexistent_run(temp_workspace):
    """Test resuming a run that doesn't exist."""
    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id="nonexistent-run",
            repair=False,
            force_restart=False
        )

    assert result == 1  # Should fail


def test_resume_rejects_pre_task6_schema_state(temp_workspace, sample_workflow, capsys):
    """Task 6 should reject resume from pre-identity-schema state without an upgrader."""
    workflow_path, checksum = sample_workflow
    run_id = "old-schema-run"
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": "1.1.1",
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0},
        },
    }, indent=2))

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    captured = capsys.readouterr()
    assert result == 1
    assert "schema version" in captured.err
    assert "1.1.1" in captured.err


def test_structured_if_else_smoke_resume_does_not_replay_completed_lowered_steps(temp_workspace):
    """Resume should not replay completed lowered branch work inside structured if/else."""
    run_id = "if-else-resume-run"
    _seed_structured_if_else_failure(temp_workspace, run_id=run_id)

    history_path = temp_workspace / "state" / "history.log"
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "write-one",
        "gate-failed",
    ]

    (temp_workspace / "state" / "resume_ready.txt").write_text("ready\n", encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "write-one",
        "gate-failed",
        "gate-passed",
    ]

    loaded_state = StateManager(temp_workspace, run_id=run_id).load()
    assert loaded_state.status == "completed"
    assert loaded_state.steps["RouteReview.then.WriteHistory"]["status"] == "completed"
    assert loaded_state.steps["RouteReview.then.ResumeGate"]["status"] == "completed"
    assert loaded_state.steps["RouteReview"]["artifacts"] == {"route_result": True}


def test_resume_fails_closed_on_projection_current_step_integrity_mismatch(temp_workspace, capsys):
    """Resume should reject corrupted current_step compatibility fields when step_id disagrees."""
    run_id = "if-else-resume-integrity-error"
    workflow_path, state_manager = _seed_structured_if_else_failure(temp_workspace, run_id=run_id)
    bundle = WorkflowLoader(temp_workspace).load_bundle(workflow_path)

    loaded_state = state_manager.load()
    loaded_state.status = "failed"
    loaded_state.current_step = {
        "name": "SetReady",
        "index": 0,
        "type": "structured_if_join",
        "status": "running",
        "step_id": "root.route_review",
    }
    state_manager._write_state()

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 1
    persisted_state = state_manager.load().to_dict()
    error = persisted_state["error"]

    assert persisted_state["status"] == "failed"
    assert error["type"] == "resume_state_integrity_error"
    assert error["context"]["step_id"] == "root.route_review"
    assert error["context"]["field"] == "name"
    assert error["context"]["expected"] == bundle.projection.presentation_key_by_node_id["root.route_review"]
    assert error["context"]["actual"] == "SetReady"

    captured = capsys.readouterr()
    assert "current_step.name" in captured.err


def test_repeat_until_smoke_resume_restarts_unfinished_iteration_without_replaying_completed_nested_steps(
    temp_workspace,
):
    """Resume should continue a failed repeat_until iteration from the first unfinished nested step."""
    run_id = "repeat-until-resume-run"
    _seed_repeat_until_failure(temp_workspace, run_id=run_id)

    history_path = temp_workspace / "state" / "history.log"
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "body-1",
        "gate-passed-1",
        "body-2",
        "gate-failed-2",
    ]

    (temp_workspace / "state" / "resume_ready.txt").write_text("ready\n", encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "body-1",
        "gate-passed-1",
        "body-2",
        "gate-failed-2",
        "gate-passed-2",
    ]

    loaded_state = StateManager(temp_workspace, run_id=run_id).load()
    assert loaded_state.status == "completed"
    assert loaded_state.steps["ReviewLoop[1].WriteBodyHistory"]["status"] == "completed"
    assert loaded_state.steps["ReviewLoop[1].ResumeGate"]["status"] == "completed"
    assert loaded_state.steps["ReviewLoop[1].WriteDecision"]["artifacts"] == {
        "review_decision": "APPROVE"
    }
    assert loaded_state.steps["ReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}


def test_repeat_until_resume_advances_past_already_evaluated_condition_without_replaying_iteration(
    temp_workspace,
):
    """Resume should advance to the next iteration when the prior iteration body and condition already settled."""
    run_id = "repeat-until-condition-resume-run"
    workflow_path = temp_workspace / "repeat_until_resume.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_repeat_until_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )
    workflow = WorkflowLoader(temp_workspace).load(workflow_path)
    repeat_step = materialize_projection_body_steps(workflow)[0]
    body_steps = repeat_step["repeat_until"]["steps"]

    state_dir = temp_workspace / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "review_count.txt").write_text("1\n", encoding="utf-8")
    (state_dir / "review_decision.txt").write_text("REVISE\n", encoding="utf-8")
    (state_dir / "history.log").write_text("body-1\ngate-passed-1\n", encoding="utf-8")
    (state_dir / "resume_ready.txt").write_text("ready\n", encoding="utf-8")

    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize("repeat_until_resume.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.step_visits = {"ReviewLoop": 1}
    state_manager.state.current_step = {
        "name": "ReviewLoop",
        "index": 0,
        "type": "repeat_until",
        "status": "running",
        "started_at": state_manager.state.started_at,
        "last_heartbeat_at": state_manager.state.updated_at,
        "step_id": repeat_step["step_id"],
        "visit_count": 1,
    }
    state_manager.state.steps = {
        "ReviewLoop": {
            "status": "running",
            "name": "ReviewLoop",
            "step_id": repeat_step["step_id"],
            "artifacts": {"review_decision": "REVISE"},
            "debug": {
                "structured_repeat_until": {
                    "completed_iterations": [],
                    "current_iteration": 0,
                    "condition_evaluated_for_iteration": 0,
                    "last_condition_result": False,
                }
            },
        },
        "ReviewLoop[0].WriteBodyHistory": {
            "status": "completed",
            "name": "WriteBodyHistory",
            "step_id": iteration_step_id(repeat_step["step_id"], 0, body_steps[0], 0),
            "exit_code": 0,
        },
        "ReviewLoop[0].ResumeGate": {
            "status": "completed",
            "name": "ResumeGate",
            "step_id": iteration_step_id(repeat_step["step_id"], 0, body_steps[1], 1),
            "exit_code": 0,
        },
        "ReviewLoop[0].WriteDecision": {
            "status": "completed",
            "name": "WriteDecision",
            "step_id": iteration_step_id(repeat_step["step_id"], 0, body_steps[2], 2),
            "exit_code": 0,
            "artifacts": {"review_decision": "REVISE"},
        },
    }
    state_manager.state.repeat_until = {
        "ReviewLoop": {
            "current_iteration": 0,
            "completed_iterations": [],
            "condition_evaluated_for_iteration": 0,
            "last_condition_result": False,
        }
    }
    state_manager._write_state()

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert (state_dir / "history.log").read_text(encoding="utf-8").splitlines() == [
        "body-1",
        "gate-passed-1",
        "body-2",
        "gate-passed-2",
    ]

    loaded_state = StateManager(temp_workspace, run_id=run_id).load()
    assert loaded_state.status == "completed"
    assert loaded_state.steps["ReviewLoop[1].WriteBodyHistory"]["status"] == "completed"
    assert loaded_state.steps["ReviewLoop[1].ResumeGate"]["status"] == "completed"
    assert loaded_state.steps["ReviewLoop[1].WriteDecision"]["artifacts"] == {
        "review_decision": "APPROVE"
    }
    assert loaded_state.steps["ReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}


def test_repeat_until_resume_preserves_nested_call_frames_and_lowered_match_progress(temp_workspace):
    """Resume should continue a repeat_until call body without replaying finished child-call work."""
    run_id = "repeat-until-call-resume-run"
    _seed_repeat_until_call_failure(temp_workspace, run_id=run_id)

    history_path = temp_workspace / "state" / "review-loop" / "history.log"
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "body-1",
        "gate-passed-1",
        "body-2",
        "gate-failed-2",
    ]

    (temp_workspace / "state" / "resume_ready.txt").write_text("ready\n", encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "body-1",
        "gate-passed-1",
        "body-2",
        "gate-failed-2",
        "gate-passed-2",
    ]

    loaded_state = StateManager(temp_workspace, run_id=run_id).load()
    assert loaded_state.status == "completed"
    assert loaded_state.steps["ReviewLoop[0].RunReviewLoop"]["artifacts"] == {"review_decision": "REVISE"}
    assert loaded_state.steps["ReviewLoop[0].RouteDecision.REVISE.WriteRevision"]["status"] == "completed"
    assert loaded_state.steps["ReviewLoop[1].RunReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert loaded_state.steps["ReviewLoop[1].RouteDecision.APPROVE.WriteApproved"]["status"] == "completed"
    assert loaded_state.steps["ReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert len(loaded_state.call_frames) == 2
    assert sorted(frame["call_step_id"] for frame in loaded_state.call_frames.values()) == [
        "root.review_loop#0.iteration_body.run_review_loop",
        "root.review_loop#1.iteration_body.run_review_loop",
    ]


def test_repeat_until_resume_clears_stale_failed_nested_call_result_while_child_reruns(
    temp_workspace,
):
    """Resume should not leave a stale failed nested-call step visible while the child call is active."""
    run_id = "repeat-until-call-running-resume"
    library_path = temp_workspace / "workflows" / "library" / "repeat_until_review_loop.yaml"
    library_workflow = _build_repeat_until_call_resume_library_workflow()
    library_workflow["steps"][2]["command"] = [
        "bash",
        "-lc",
        "\n".join(
            [
                "mkdir -p \"${inputs.write_root}\"",
                "count=\"${inputs.iteration}\"",
                "printf 'write-decision-running-%s\\n' \"$count\" >> state/review-loop/history.log",
                "while [ ! -f state/allow_finish.txt ]; do sleep 0.05; done",
                "if [ \"$count\" -ge 2 ]; then",
                "  printf 'APPROVE\\n' > \"${inputs.write_root}/review_decision.txt\"",
                "else",
                "  printf 'REVISE\\n' > \"${inputs.write_root}/review_decision.txt\"",
                "fi",
            ]
        ),
    ]
    library_path.parent.mkdir(parents=True, exist_ok=True)
    library_path.write_text(
        yaml.safe_dump(library_workflow, sort_keys=False),
        encoding="utf-8",
    )

    workflow_path = temp_workspace / "repeat_until_call_resume.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_repeat_until_call_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    state_dir = temp_workspace / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "allow_finish.txt").write_text("ready\n", encoding="utf-8")

    workflow = WorkflowLoader(temp_workspace).load(workflow_path)
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize("repeat_until_call_resume.yaml")

    first_run = WorkflowExecutor(workflow, temp_workspace, state_manager).execute(on_error="stop")
    assert first_run["status"] == "failed"

    (state_dir / "allow_finish.txt").unlink()
    (state_dir / "resume_ready.txt").write_text("ready\n", encoding="utf-8")

    resume_result: dict[str, object] = {}

    def _resume() -> None:
        try:
            resumed_workflow = WorkflowLoader(temp_workspace).load(workflow_path)
            resume_result["state"] = WorkflowExecutor(
                resumed_workflow,
                temp_workspace,
                StateManager(workspace=temp_workspace, run_id=run_id),
            ).execute(on_error="stop", resume=True)
        except BaseException as exc:  # pragma: no cover - surfaced below
            resume_result["error"] = exc

    thread = threading.Thread(target=_resume, daemon=True)
    thread.start()

    deadline = time.time() + 10
    observed_state = None
    while time.time() < deadline:
        observed_state = json.loads(
            (temp_workspace / ".orchestrate" / "runs" / run_id / "state.json").read_text(
                encoding="utf-8"
            )
        )
        child_frame = next(
            (
                frame
                for frame in observed_state.get("call_frames", {}).values()
                if frame.get("call_step_id") == "root.review_loop#1.iteration_body.run_review_loop"
            ),
            None,
        )
        child_current = child_frame.get("current_step") if isinstance(child_frame, dict) else None
        if isinstance(child_current, dict) and child_current.get("name") == "WriteDecision":
            break
        time.sleep(0.05)
    else:
        (state_dir / "allow_finish.txt").write_text("ready\n", encoding="utf-8")
        thread.join(timeout=10)
        pytest.fail("resume never reached the rerunning child WriteDecision step")

    assert observed_state is not None
    rerun_entry = observed_state["steps"].get("ReviewLoop[1].RunReviewLoop")
    assert rerun_entry is None or rerun_entry["status"] != "failed"

    (state_dir / "allow_finish.txt").write_text("ready\n", encoding="utf-8")
    thread.join(timeout=10)

    if "error" in resume_result:
        raise resume_result["error"]  # type: ignore[misc]
    assert not thread.is_alive()
    assert isinstance(resume_result.get("state"), dict)
    assert resume_result["state"]["status"] == "completed"
    loaded_state = StateManager(temp_workspace, run_id=run_id).load()
    second_frame = next(
        frame
        for frame in loaded_state.call_frames.values()
        if frame["call_step_id"] == "root.review_loop#1.iteration_body.run_review_loop"
    )
    assert second_frame["state"]["steps"]["WriteBodyHistory"]["status"] == "completed"
    assert second_frame["state"]["steps"]["ResumeGate"]["status"] == "completed"
    assert second_frame["state"]["steps"]["WriteDecision"]["status"] == "completed"


def test_finally_smoke_resume_restarts_at_first_unfinished_cleanup_step(temp_workspace):
    """Resume should continue finalization from the first unfinished cleanup step."""
    workflow_path = temp_workspace / "resume_finally.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_finally_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    loader = WorkflowLoader(temp_workspace)
    loaded = loader.load(workflow_path)

    state_manager = StateManager(workspace=temp_workspace, run_id="finally-resume-run")
    state_manager.initialize("resume_finally.yaml")
    first_run = WorkflowExecutor(loaded, temp_workspace, state_manager).execute()

    history_path = temp_workspace / "state" / "history.log"
    assert first_run["status"] == "failed"
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "body",
        "cleanup-one",
        "cleanup-gate-failed",
    ]

    (temp_workspace / "state" / "resume_ready.txt").write_text("ready\n", encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id="finally-resume-run",
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "body",
        "cleanup-one",
        "cleanup-gate-failed",
        "cleanup-gate-passed",
        "cleanup-two",
    ]

    loaded_state = StateManager(temp_workspace, run_id="finally-resume-run").load()
    assert loaded_state.status == "completed"
    assert loaded_state.steps["WriteBodyHistory"]["status"] == "completed"
    assert loaded_state.steps["finally.WriteCleanupOne"]["status"] == "completed"
    assert loaded_state.steps["finally.ResumeGate"]["status"] == "completed"
    assert loaded_state.steps["finally.WriteCleanupTwo"]["status"] == "completed"


def test_call_subworkflow_smoke_resume_preserves_completed_nested_steps(temp_workspace):
    run_id = "call-subworkflow-resume-run"
    library_path = temp_workspace / "workflows" / "library" / "review_fix_loop.yaml"
    library_path.parent.mkdir(parents=True, exist_ok=True)
    library_path.write_text(
        yaml.safe_dump(_build_call_resume_library_workflow(), sort_keys=False),
        encoding="utf-8",
    )
    workflow_path = temp_workspace / "resume_call_workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_call_resume_caller_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    loader = WorkflowLoader(temp_workspace)
    loaded = loader.load(workflow_path)
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize(str(workflow_path), context=bundle_context_dict(loaded))

    first_run = WorkflowExecutor(loaded, temp_workspace, state_manager).execute()

    history_path = temp_workspace / "state" / "review-loop" / "history.log"
    assert first_run["status"] == "failed"
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "child-one",
        "gate-failed",
    ]

    (temp_workspace / "state" / "resume_ready.txt").write_text("ready\n", encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "child-one",
        "gate-failed",
        "gate-passed",
    ]

    loaded_state = StateManager(temp_workspace, run_id=run_id).load()
    assert loaded_state.status == "completed"
    assert loaded_state.steps["RunReviewLoop"]["artifacts"] == {"approved": True}
    assert loaded_state.steps["VerifyApproved"]["status"] == "completed"
    assert len(loaded_state.call_frames) == 1
    frame = next(iter(loaded_state.call_frames.values()))
    assert frame["status"] == "completed"
    assert frame["export_status"] == "completed"
    assert frame["state"]["steps"]["WriteHistory"]["status"] == "completed"
    assert frame["state"]["steps"]["ResumeGate"]["status"] == "completed"
    assert frame["state"]["steps"]["SetApproved"]["status"] == "completed"


def test_call_subworkflow_resume_rejects_imported_workflow_checksum_mismatch(temp_workspace):
    run_id = "call-subworkflow-checksum-run"
    library_path = temp_workspace / "workflows" / "library" / "review_fix_loop.yaml"
    library_path.parent.mkdir(parents=True, exist_ok=True)
    library_path.write_text(
        yaml.safe_dump(_build_call_resume_library_workflow(), sort_keys=False),
        encoding="utf-8",
    )
    workflow_path = temp_workspace / "resume_call_workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_call_resume_caller_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    loader = WorkflowLoader(temp_workspace)
    loaded = loader.load(workflow_path)
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize(str(workflow_path), context=bundle_context_dict(loaded))

    first_run = WorkflowExecutor(loaded, temp_workspace, state_manager).execute()

    history_path = temp_workspace / "state" / "review-loop" / "history.log"
    assert first_run["status"] == "failed"
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "child-one",
        "gate-failed",
    ]

    (temp_workspace / "state" / "resume_ready.txt").write_text("ready\n", encoding="utf-8")
    library_path.write_text(
        library_path.read_text(encoding="utf-8") + "\n# checksum-change\n",
        encoding="utf-8",
    )

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 1
    assert history_path.read_text(encoding="utf-8").splitlines() == [
        "child-one",
        "gate-failed",
    ]

    loaded_state = StateManager(temp_workspace, run_id=run_id).load()
    assert loaded_state.status == "failed"
    assert len(loaded_state.call_frames) == 1
    frame = next(iter(loaded_state.call_frames.values()))
    assert frame["status"] == "failed"
    assert frame["state"]["steps"]["WriteHistory"]["status"] == "completed"
    assert frame["state"]["steps"]["ResumeGate"]["status"] == "failed"
    assert "SetApproved" not in frame["state"]["steps"]


def test_resume_retries_since_last_consume_step_after_failed_attempt(temp_workspace):
    run_id = "since-last-consume-resume-run"
    workflow_path = temp_workspace / "resume_since_last_consume.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_since_last_consume_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    loader = WorkflowLoader(temp_workspace)
    loaded = loader.load(workflow_path)
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize(str(workflow_path), context=bundle_context_dict(loaded))

    first_run = WorkflowExecutor(loaded, temp_workspace, state_manager).execute()

    history_path = temp_workspace / "state" / "history.log"
    assert first_run["status"] == "failed"
    assert history_path.read_text(encoding="utf-8").splitlines() == ["attempted"]

    (temp_workspace / "state" / "resume_ready.txt").write_text("ready\n", encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert history_path.read_text(encoding="utf-8").splitlines() == ["attempted", "resumed"]
    assert json.loads((temp_workspace / "state" / "consumed.json").read_text(encoding="utf-8")) == {
        "review_feedback": "revise the implementation",
    }

    loaded_state = StateManager(temp_workspace, run_id=run_id).load()
    assert loaded_state.status == "completed"
    assert loaded_state.steps["FixImplementation"]["status"] == "completed"


@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
@patch('orchestrator.cli.commands.resume.WorkflowLoader')
def test_resume_preserves_bound_inputs_in_loaded_state(mock_loader, mock_executor, temp_workspace, sample_workflow):
    """Persisted workflow-signature inputs should remain available after resume reload."""
    workflow_path, checksum = sample_workflow
    run_id = "bound-inputs-run"
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "bound_inputs": {"max_cycles": 5},
        "steps": {},
    }, indent=2))

    mock_loader.return_value.load.return_value = {
        "version": "2.1",
        "name": "resume-signature",
        "inputs": {
            "max_cycles": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "steps": [],
    }
    mock_executor.return_value.execute.return_value = {"status": "completed"}

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    state_manager = mock_executor.call_args.kwargs["state_manager"]
    assert state_manager.state is not None
    assert state_manager.state.bound_inputs == {"max_cycles": 5}


def test_at4_resume_completed_run(temp_workspace, sample_workflow):
    """Test resuming a run that has already completed."""
    workflow_path, checksum = sample_workflow
    run_id = "completed-run"

    # Create completed state
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "completed",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0},
            "Step2": {"status": "completed", "exit_code": 0},
            "Step3": {"status": "completed", "exit_code": 0}
        }
    }

    (state_dir / "state.json").write_text(json.dumps(state, indent=2))

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False
        )

    assert result == 0  # Should succeed immediately


def test_at4_resume_with_checksum_mismatch(temp_workspace, partial_run_state):
    """Test resume when workflow has been modified."""
    run_id, state_dir = partial_run_state

    # Modify the workflow file
    workflow_path = Path(json.loads((state_dir / "state.json").read_text())["workflow_file"])
    workflow_path.write_text("""
version: "1.1"
name: Modified Workflow
steps:
  - name: Step1
    command: ["echo", "Modified"]
""")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False
        )

    assert result == 1  # Should fail due to checksum mismatch


def test_at4_resume_force_restart(temp_workspace, partial_run_state):
    """Test force restart ignores existing state."""
    run_id, state_dir = partial_run_state

    # Mock the WorkflowExecutor to verify it starts fresh
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'Step1': {'status': 'completed'},
                'Step2': {'status': 'completed'},
                'Step3': {'status': 'completed'}
            }
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=True
            )

        # AT-68: Verify executor was called with resume=False for force_restart
        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs.get('resume') == False

    assert result == 0


@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
def test_resume_force_restart_revalidates_persisted_bound_inputs(
    mock_executor,
    temp_workspace,
    capsys,
):
    """Force restart must rebind persisted inputs against the current workflow contracts."""
    workflow_path = temp_workspace / "typed_input_workflow.yaml"
    workflow_path.write_text(
        """
version: "2.1"
name: Force Restart Input Validation
inputs:
  max_cycles:
    kind: scalar
    type: integer
steps:
  - name: Finish
    command: ["bash", "-lc", "printf 'done\\n'"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    checksum = f"sha256:{hashlib.sha256(workflow_path.read_bytes()).hexdigest()}"

    run_id = "force-restart-invalid-inputs"
    run_root = temp_workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": StateManager.SCHEMA_VERSION,
                "run_id": run_id,
                "workflow_file": str(workflow_path),
                "workflow_checksum": checksum,
                "started_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:01:00Z",
                "status": "failed",
                "context": {},
                "bound_inputs": {"max_cycles": "not-an-integer"},
                "steps": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=True,
        )

    assert result == 2
    assert mock_executor.called is False
    assert "Workflow input binding failed" in capsys.readouterr().err
    assert sorted(path.name for path in (temp_workspace / ".orchestrate" / "runs").iterdir()) == [run_id]


@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
def test_resume_force_restart_rebinds_only_public_inputs_for_managed_orc_inputs(
    mock_executor,
    temp_workspace,
):
    workflow_path = temp_workspace / "cycle_guard_demo.orc"
    workflow_path.write_text("(workflow-lisp)\n", encoding="utf-8")

    bundle = compile_stage3_module(
        Path(__file__).resolve().parent.parent / "workflows" / "examples" / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=temp_workspace,
    ).validated_bundles["cycle-guard-demo"]
    hidden_input_name = workflow_managed_write_root_inputs(bundle)[0]

    run_id = "force-restart-managed-orc-inputs"
    run_root = temp_workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": StateManager.SCHEMA_VERSION,
                "run_id": run_id,
                "workflow_file": str(workflow_path),
                "workflow_checksum": "sha256:placeholder",
                "started_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:01:00Z",
                "status": "failed",
                "context": {},
                "bound_inputs": {
                    "terminal_status": "FAILED_CLOSED_BY_GUARD",
                    "guard_cycles": 2,
                    hidden_input_name: 7,
                },
                "steps": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    mock_executor.return_value.execute.return_value = {
        "status": "completed",
        "steps": {},
    }

    with patch('os.getcwd', return_value=str(temp_workspace)), patch(
        'orchestrator.cli.commands.resume.WorkflowLoader.load_bundle',
        return_value=bundle,
    ), patch('uuid.uuid4', return_value=SimpleNamespace(hex="fresh-force-restart-run")):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=True,
        )

    assert result == 0
    new_state = json.loads(
        (
            temp_workspace
            / ".orchestrate"
            / "runs"
            / "fresh-force-restart-run"
            / "state.json"
        ).read_text(encoding="utf-8")
    )
    assert new_state["bound_inputs"] == {
        "terminal_status": "FAILED_CLOSED_BY_GUARD",
        "guard_cycles": 2,
    }


def test_entry_managed_write_root_bindings_are_run_isolated_and_resume_stable(temp_workspace) -> None:
    bundle = compile_stage3_module(
        Path(__file__).resolve().parent.parent / "workflows" / "examples" / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=temp_workspace,
    ).validated_bundles["cycle-guard-demo"]
    managed_input_name = workflow_managed_write_root_inputs(bundle)[0]
    allocation = next(
        item
        for item in bundle.provenance.generated_path_allocations
        if _allocation_field(item, "semantic_role") == "entrypoint_managed_write_root"
        and _allocation_field(item, "generated_input_name") == managed_input_name
    )

    first_executor = WorkflowExecutor(
        bundle,
        temp_workspace,
        StateManager(workspace=temp_workspace, run_id="allocator-resume-run"),
    )
    second_executor = WorkflowExecutor(
        bundle,
        temp_workspace,
        StateManager(workspace=temp_workspace, run_id="allocator-resume-run"),
    )

    assert _allocation_field(allocation, "privacy") == "private_generated"
    assert _allocation_field(allocation, "resume_scope") == "run"
    assert first_executor._entry_managed_write_root_bindings() == second_executor._entry_managed_write_root_bindings()


def test_entry_managed_write_root_paths_do_not_collide_across_runs(temp_workspace) -> None:
    bundle = compile_stage3_module(
        Path(__file__).resolve().parent.parent / "workflows" / "examples" / "cycle_guard_demo.orc",
        command_boundaries={
            "emit_cycle_guard_summary": ExternalToolBinding(
                name="emit_cycle_guard_summary",
                stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
            )
        },
        validate_shared=True,
        workspace_root=temp_workspace,
    ).validated_bundles["cycle-guard-demo"]
    managed_input_name = workflow_managed_write_root_inputs(bundle)[0]
    allocation = next(
        item
        for item in bundle.provenance.generated_path_allocations
        if _allocation_field(item, "semantic_role") == "entrypoint_managed_write_root"
        and _allocation_field(item, "generated_input_name") == managed_input_name
    )

    first_bindings = WorkflowExecutor(
        bundle,
        temp_workspace,
        StateManager(workspace=temp_workspace, run_id="allocator-run-one"),
    )._entry_managed_write_root_bindings()
    second_bindings = WorkflowExecutor(
        bundle,
        temp_workspace,
        StateManager(workspace=temp_workspace, run_id="allocator-run-two"),
    )._entry_managed_write_root_bindings()

    assert _allocation_field(allocation, "privacy") == "private_generated"
    assert _allocation_field(allocation, "stable_identity")
    assert first_bindings[managed_input_name] != second_bindings[managed_input_name]


@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
def test_resume_force_restart_rebinds_only_public_inputs_for_promoted_entry_hidden_context(
    mock_executor,
    temp_workspace,
):
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "workflow_lisp"
        / "valid"
        / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    )
    workflow_path = temp_workspace / "phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc"
    workflow_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    bundle = compile_stage3_entrypoint(
        fixture,
        source_roots=(fixture.parent,),
        command_boundaries={
            "resolve_plan_gate": ExternalToolBinding(
                name="resolve_plan_gate",
                stable_command=("python", "scripts/resolve_plan_gate.py"),
            )
        },
        validate_shared=True,
        workspace_root=temp_workspace,
    ).entry_result.validated_bundles[
        "phase_stdlib_resume_or_start_promoted_entry_bootstrap::promoted-entry-resume-plan-gate-wrapper"
    ]
    hidden_context_inputs = _workflow_runtime_context_inputs(bundle)
    assert hidden_context_inputs

    for relative_path in (
        Path("docs/design/selected-item-design.md"),
        Path("docs/plans/selected-item-plan.md"),
        Path("artifacts/work/selected-item-execution.md"),
    ):
        target = temp_workspace / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("seed\n", encoding="utf-8")

    run_id = "force-restart-runtime-context-orc-inputs"
    run_root = temp_workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": StateManager.SCHEMA_VERSION,
                "run_id": run_id,
                "workflow_file": str(workflow_path),
                "workflow_checksum": "sha256:placeholder",
                "started_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:01:00Z",
                "status": "failed",
                "context": {},
                "bound_inputs": {
                    "inputs__resume_from": "state/selected-item/plan-gate.json",
                    "inputs__design": "docs/design/selected-item-design.md",
                    "inputs__plan": "docs/plans/selected-item-plan.md",
                    "inputs__report_path": "artifacts/work/selected-item-execution.md",
                    **{name: f"stale-{index}" for index, name in enumerate(hidden_context_inputs)},
                },
                "steps": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    mock_executor.return_value.execute.return_value = {
        "status": "completed",
        "steps": {},
    }

    with patch('os.getcwd', return_value=str(temp_workspace)), patch(
        'orchestrator.cli.commands.resume._load_resume_workflow_bundle',
        return_value=bundle,
    ), patch('uuid.uuid4', return_value=SimpleNamespace(hex="fresh-force-restart-context-run")):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=True,
        )

    assert result == 0
    new_state = json.loads(
        (
            temp_workspace
            / ".orchestrate"
            / "runs"
            / "fresh-force-restart-context-run"
            / "state.json"
        ).read_text(encoding="utf-8")
    )
    assert new_state["bound_inputs"] == {
        "inputs__resume_from": "state/selected-item/plan-gate.json",
        "inputs__design": "docs/design/selected-item-design.md",
        "inputs__plan": "docs/plans/selected-item-plan.md",
        "inputs__report_path": "artifacts/work/selected-item-execution.md",
    }


@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
def test_resume_force_restart_uses_typed_boundary_projection_when_runtime_context_tuple_is_absent(
    mock_executor,
    temp_workspace,
):
    workflow_path = temp_workspace / "private_exec_context_phase_entry.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule private_exec_context_phase_entry)",
                "  (export entry run-phase)",
                "  (defrecord RunCtx",
                "    (run-id RunId)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord PhaseCtx",
                "    (run RunCtx)",
                "    (phase-name Symbol)",
                "    (state-root Path.state-root)",
                "    (artifact-root Path.artifact-root))",
                "  (defrecord Result",
                "    (label String)",
                "    (phase_name Symbol))",
                "  (defworkflow entry",
                "    ((label String))",
                "    -> Result",
                "    (call run-phase",
                "      :label label))",
                "  (defworkflow run-phase",
                "    ((phase-ctx PhaseCtx)",
                "     (label String))",
                "    -> Result",
                "    (with-phase phase-ctx plan-gate-wrapper",
                "      (record Result",
                "        :label label",
                "        :phase_name phase-ctx.phase-name)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    bundle = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(temp_workspace,),
        validate_shared=True,
        workspace_root=temp_workspace,
    ).entry_result.validated_bundles[
        "private_exec_context_phase_entry::entry"
    ]
    boundary = _workflow_boundary_projection(bundle)
    hidden_context_inputs = tuple(boundary.private_runtime_context_bindings[0].generated_input_names)
    assert hidden_context_inputs

    compatibility_projection_stripped = replace(
        bundle,
        provenance=replace(bundle.provenance, runtime_context_inputs=()),
    )
    stripped_boundary = _workflow_boundary_projection(compatibility_projection_stripped)
    assert tuple(stripped_boundary.private_runtime_context_bindings[0].generated_input_names) == hidden_context_inputs

    run_id = "force-restart-typed-private-context"
    run_root = temp_workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": StateManager.SCHEMA_VERSION,
                "run_id": run_id,
                "workflow_file": str(workflow_path),
                "workflow_checksum": "sha256:placeholder",
                "started_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:01:00Z",
                "status": "failed",
                "context": {},
                "bound_inputs": {
                    "label": "selected-item",
                    **{name: f"stale-{index}" for index, name in enumerate(hidden_context_inputs)},
                },
                "steps": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_process_metadata(
        run_root,
        pid=12345,
        process_start_time="start-token",
        argv=[
            "python",
            "-m",
            "orchestrator",
            "run",
            workflow_path.as_posix(),
            "--source-root",
            temp_workspace.as_posix(),
            "--entry-workflow",
            "entry",
        ],
    )

    mock_executor.return_value.execute.return_value = {
        "status": "completed",
        "steps": {},
    }

    with patch('os.getcwd', return_value=str(temp_workspace)), patch(
        'orchestrator.cli.commands.resume.WorkflowLoader.load_bundle',
        return_value=compatibility_projection_stripped,
    ), patch('uuid.uuid4', return_value=SimpleNamespace(hex="typed-private-context-restart")):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=True,
        )

    assert result == 0
    new_state = json.loads(
        (
            temp_workspace
            / ".orchestrate"
            / "runs"
            / "typed-private-context-restart"
            / "state.json"
        ).read_text(encoding="utf-8")
    )
    assert all(name not in new_state["bound_inputs"] for name in hidden_context_inputs)
    assert new_state["bound_inputs"] == {
        "label": "selected-item",
    }


@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
def test_resume_force_restart_strips_stale_managed_inputs_after_workflow_rename(
    mock_executor,
    temp_workspace,
):
    original_source = (
        Path(__file__).resolve().parent.parent
        / "workflows"
        / "examples"
        / "cycle_guard_demo.orc"
    ).read_text(encoding="utf-8")
    renamed_source = (
        original_source
        .replace("(defmodule cycle_guard_demo)", "(defmodule cycle_guard_demo_renamed)")
        .replace("(export cycle-guard-demo)", "(export cycle-guard-demo-renamed)")
        .replace("(defworkflow cycle-guard-demo", "(defworkflow cycle-guard-demo-renamed")
    )
    workflow_path = temp_workspace / "cycle_guard_demo_renamed.orc"
    workflow_path.write_text(renamed_source, encoding="utf-8")

    command_boundaries = {
        "emit_cycle_guard_summary": ExternalToolBinding(
            name="emit_cycle_guard_summary",
            stable_command=("python", "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py"),
        )
    }
    stale_bundle = compile_stage3_module(
        Path(__file__).resolve().parent.parent / "workflows" / "examples" / "cycle_guard_demo.orc",
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=temp_workspace,
    ).validated_bundles["cycle-guard-demo"]
    renamed_bundle = compile_stage3_module(
        workflow_path,
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=temp_workspace,
    ).validated_bundles["cycle-guard-demo-renamed"]
    stale_hidden_input_name = workflow_managed_write_root_inputs(stale_bundle)[0]
    renamed_hidden_input_name = workflow_managed_write_root_inputs(renamed_bundle)[0]

    assert stale_hidden_input_name != renamed_hidden_input_name

    run_id = "force-restart-stale-managed-orc-inputs"
    run_root = temp_workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": StateManager.SCHEMA_VERSION,
                "run_id": run_id,
                "workflow_file": str(workflow_path),
                "workflow_checksum": "sha256:placeholder",
                "started_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:01:00Z",
                "status": "failed",
                "context": {},
                "bound_inputs": {
                    "terminal_status": "FAILED_CLOSED_BY_GUARD",
                    "guard_cycles": 2,
                    stale_hidden_input_name: 7,
                },
                "steps": {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    mock_executor.return_value.execute.return_value = {
        "status": "completed",
        "steps": {},
    }

    with patch('os.getcwd', return_value=str(temp_workspace)), patch(
        'orchestrator.cli.commands.resume.WorkflowLoader.load_bundle',
        return_value=renamed_bundle,
    ), patch('uuid.uuid4', return_value=SimpleNamespace(hex="fresh-force-restart-renamed-run")):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=True,
        )

    assert result == 0
    new_state = json.loads(
        (
            temp_workspace
            / ".orchestrate"
            / "runs"
            / "fresh-force-restart-renamed-run"
            / "state.json"
        ).read_text(encoding="utf-8")
    )
    assert new_state["bound_inputs"] == {
        "terminal_status": "FAILED_CLOSED_BY_GUARD",
        "guard_cycles": 2,
    }


def test_at4_resume_corrupted_state_with_repair(temp_workspace, sample_workflow):
    """Test repairing from backup when state is corrupted."""
    workflow_path, checksum = sample_workflow
    run_id = "corrupted-run"

    # Create state directory with backup
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    # Create valid backup
    valid_state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0}
        }
    }

    backup_file = state_dir / "state.json.step_Step1.bak"
    backup_file.write_text(json.dumps(valid_state, indent=2))

    # Create corrupted state file
    (state_dir / "state.json").write_text("{ corrupted json")

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {}
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=True,
                force_restart=False
            )

    assert result == 0  # Should succeed after repair

    # Verify state was repaired
    state_content = json.loads((state_dir / "state.json").read_text())
    assert state_content["steps"]["Step1"]["status"] == "completed"


def test_at4_resume_partial_for_each_loop(temp_workspace):
    """Test resuming a partially completed for-each loop."""
    # Create workflow with for-each loop
    workflow_path = temp_workspace / "loop_workflow.yaml"
    workflow_content = """
version: "1.1"
name: Loop Workflow
steps:
  - name: GenerateList
    command: ["echo", "item1\\nitem2\\nitem3"]
    output_capture: lines
  - name: ProcessItems
    for_each:
      items_from: "steps.GenerateList.lines"
      steps:
        - name: ProcessItem
          command: ["echo", "Processing ${item}"]
          output_capture: text
"""
    workflow_path.write_text(workflow_content)
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "loop-run"
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    # Create state with partial loop completion
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "GenerateList": {
                "status": "completed",
                "exit_code": 0,
                "lines": ["item1", "item2", "item3"]
            },
            "ProcessItems[0].ProcessItem": {
                "status": "completed",
                "exit_code": 0,
                "output": "Processing item1"
            }
            # item2 and item3 not yet processed
        }
    }

    (state_dir / "state.json").write_text(json.dumps(state, indent=2))

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'GenerateList': {'status': 'completed'},
                'ProcessItems': [
                    {'status': 'completed'},
                    {'status': 'completed'},
                    {'status': 'completed'}
                ]
            }
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=False
            )

        # Verify executor was called with resume=True
        assert mock_executor.execute.call_args.kwargs.get('resume') == True

    assert result == 0


def test_resume_partial_for_each_loop_skips_completed_iterations_using_bookkeeping(temp_workspace):
    """Resume should continue from the first incomplete loop iteration without replaying completed work."""
    workflow = {
        "version": "1.1",
        "name": "Loop Resume Workflow",
        "steps": [
            {
                "name": "GenerateList",
                "command": ["bash", "-lc", "printf 'item1\\nitem2\\nitem3\\n'"],
                "output_capture": "lines",
            },
            {
                "name": "ProcessItems",
                "for_each": {
                    "items_from": "steps.GenerateList.lines",
                    "steps": [
                        {
                            "name": "ProcessItem",
                            "command": [
                                "bash",
                                "-lc",
                                "mkdir -p state && printf '%s\\n' \"${item}\" >> state/processed.log",
                            ],
                        }
                    ],
                },
            },
        ],
    }

    workflow_path = temp_workspace / "loop_resume_workflow.yaml"
    workflow_text = yaml.safe_dump(workflow, sort_keys=False)
    workflow_path.write_text(workflow_text)
    checksum = f"sha256:{hashlib.sha256(workflow_text.encode()).hexdigest()}"

    state_dir = temp_workspace / "state"
    state_dir.mkdir()
    (state_dir / "processed.log").write_text("item1\n")

    run_id = "loop-resume-real"
    run_root = temp_workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": "loop_resume_workflow.yaml",
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "steps": {
            "GenerateList": {
                "status": "completed",
                "exit_code": 0,
                "lines": ["item1", "item2", "item3"],
            },
            "ProcessItems[0].ProcessItem": {
                "status": "completed",
                "exit_code": 0,
                "output": "item1",
            },
        },
        "for_each": {
            "ProcessItems": {
                "items": ["item1", "item2", "item3"],
                "completed_indices": [0],
                "current_index": 1,
            }
        },
    }
    (run_root / "state.json").write_text(json.dumps(state, indent=2))

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert (state_dir / "processed.log").read_text().splitlines() == ["item1", "item2", "item3"]

    resumed = json.loads((run_root / "state.json").read_text())
    assert resumed["for_each"]["ProcessItems"]["completed_indices"] == [0, 1, 2]
    assert resumed["for_each"]["ProcessItems"]["current_index"] is None
    assert len(resumed["steps"]["ProcessItems"]) == 3
    assert resumed["steps"]["ProcessItems[1].ProcessItem"]["status"] == "completed"
    assert resumed["steps"]["ProcessItems[2].ProcessItem"]["status"] == "completed"


def test_resume_partial_for_each_loop_uses_incremental_summary_bookkeeping(temp_workspace):
    """Resume must not treat a partial loop summary as terminal when bookkeeping shows pending iterations."""
    workflow = {
        "version": "1.1",
        "name": "Loop Resume Workflow",
        "steps": [
            {
                "name": "GenerateList",
                "command": ["bash", "-lc", "printf 'item1\\nitem2\\nitem3\\n'"],
                "output_capture": "lines",
            },
            {
                "name": "ProcessItems",
                "for_each": {
                    "items_from": "steps.GenerateList.lines",
                    "steps": [
                        {
                            "name": "ProcessItem",
                            "command": [
                                "bash",
                                "-lc",
                                "mkdir -p state && printf '%s\\n' \"${item}\" >> state/processed.log",
                            ],
                        }
                    ],
                },
            },
        ],
    }

    workflow_path = temp_workspace / "loop_resume_workflow.yaml"
    workflow_text = yaml.safe_dump(workflow, sort_keys=False)
    workflow_path.write_text(workflow_text)
    checksum = f"sha256:{hashlib.sha256(workflow_text.encode()).hexdigest()}"

    state_dir = temp_workspace / "state"
    state_dir.mkdir()
    (state_dir / "processed.log").write_text("item1\n")

    run_id = "loop-resume-incremental-summary"
    run_root = temp_workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": "loop_resume_workflow.yaml",
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "steps": {
            "GenerateList": {
                "status": "completed",
                "exit_code": 0,
                "lines": ["item1", "item2", "item3"],
            },
            "ProcessItems": [
                {
                    "ProcessItem": {
                        "status": "completed",
                        "exit_code": 0,
                        "output": "item1",
                    }
                }
            ],
            "ProcessItems[0].ProcessItem": {
                "status": "completed",
                "exit_code": 0,
                "output": "item1",
            },
        },
        "for_each": {
            "ProcessItems": {
                "items": ["item1", "item2", "item3"],
                "completed_indices": [0],
                "current_index": 1,
            }
        },
        "current_step": {
            "name": "ProcessItems",
            "index": 1,
            "status": "running",
            "started_at": "2024-01-01T00:00:30Z",
        },
    }
    (run_root / "state.json").write_text(json.dumps(state, indent=2))

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert (state_dir / "processed.log").read_text().splitlines() == ["item1", "item2", "item3"]

    resumed = json.loads((run_root / "state.json").read_text())
    assert resumed["for_each"]["ProcessItems"]["completed_indices"] == [0, 1, 2]
    assert resumed["for_each"]["ProcessItems"]["current_index"] is None
    assert len(resumed["steps"]["ProcessItems"]) == 3
    assert resumed["steps"]["ProcessItems[1].ProcessItem"]["status"] == "completed"
    assert resumed["steps"]["ProcessItems[2].ProcessItem"]["status"] == "completed"


def test_resume_revisits_top_level_review_step_after_fix_loop(temp_workspace):
    """Resume should only skip to the restart point, not skip revisited loop steps forever."""
    run_id = "resume-loop-run"
    _seed_resume_loop_state(temp_workspace, run_id=run_id)

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert (temp_workspace / "state" / "review_count.txt").read_text() == "2\n"
    assert (temp_workspace / "state" / "decision.txt").read_text() == "APPROVE\n"
    history = (temp_workspace / "state" / "history.log").read_text()
    assert "review-2\n" in history
    assert "maxed\n" not in history


def test_resume_clears_current_step_after_looped_completion(temp_workspace):
    """Resumed completion should clear any stale current_step metadata."""
    run_id = "resume-loop-current-step"
    _, state_manager = _seed_resume_loop_state(temp_workspace, run_id=run_id)
    assert state_manager.state is not None
    state_manager.state.current_step = {
        "name": "ImplementationReviewGate",
        "index": 1,
        "type": "command",
        "status": "running",
        "started_at": "2024-01-01T00:00:10Z",
        "last_heartbeat_at": "2024-01-01T00:00:11Z",
    }
    state_manager._write_state()

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    payload = json.loads(
        (temp_workspace / ".orchestrate" / "runs" / run_id / "state.json").read_text()
    )
    assert payload["status"] == "completed"
    assert payload.get("current_step") is None


def test_resume_ignores_stale_running_current_step_for_completed_side_effecting_step(temp_workspace):
    """Resume should not rerun a completed side-effecting step just because current_step is stale."""
    workflow_path = temp_workspace / "stale_current_step.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "1.1",
                "name": "stale-current-step",
                "steps": [
                    {
                        "name": "FixImplementation",
                        "command": ["bash", "-lc", "printf 'fix\\n' >> state/history.log"],
                    },
                    {
                        "name": "NextStep",
                        "command": ["bash", "-lc", "printf 'next\\n' >> state/history.log"],
                    },
                ],
            },
            sort_keys=False,
        )
    )

    state_dir = temp_workspace / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "history.log").write_text("fix\n")

    run_id = "stale-current-step-run"
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize("stale_current_step.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {
        "FixImplementation": {"status": "completed", "exit_code": 0},
        "NextStep": {"status": "pending"},
    }
    state_manager.state.current_step = {
        "name": "FixImplementation",
        "index": 0,
        "type": "command",
        "status": "running",
        "started_at": "2024-01-01T00:00:10Z",
        "last_heartbeat_at": "2024-01-01T00:00:11Z",
    }
    state_manager._write_state()

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert (state_dir / "history.log").read_text() == "fix\nnext\n"


def test_resume_continues_partial_finalization_without_rerunning_completed_cleanup(temp_workspace):
    workflow_path = temp_workspace / "structured_finally_resume.yaml"
    workflow_path.write_text(
        yaml.safe_dump(_build_structured_finally_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    state_dir = temp_workspace / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "finalization.log").write_text("outputs-pending\n", encoding="utf-8")

    run_id = "structured-finally-resume-run"
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize("structured_finally_resume.yaml")
    assert state_manager.state is not None
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

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    payload = json.loads(
        (temp_workspace / ".orchestrate" / "runs" / run_id / "state.json").read_text()
    )
    assert payload["status"] == "completed"
    assert payload["workflow_outputs"] == {"final_decision": "APPROVE"}
    assert payload["finalization"]["completed_indices"] == [0, 1]
    assert payload["finalization"]["workflow_outputs_status"] == "completed"
    assert payload.get("current_step") is None
    assert (state_dir / "finalization.log").read_text(encoding="utf-8").splitlines() == [
        "outputs-pending",
        "cleanup-complete",
    ]


def test_at4_resume_with_retry_parameters(temp_workspace, partial_run_state):
    """Test resume with custom retry parameters."""
    run_id, state_dir = partial_run_state

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {}
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=False,
                max_retries=5,
                retry_delay_ms=2000
            )

        # Verify executor was initialized with retry parameters
        MockExecutor.assert_called_once()
        call_kwargs = MockExecutor.call_args.kwargs
        assert call_kwargs.get('max_retries') == 5
        assert call_kwargs.get('retry_delay_ms') == 2000

    assert result == 0


def test_resume_preserves_control_flow_counters(temp_workspace):
    """Resume keeps persisted cycle-guard counters available to the executor."""
    workflow_path = temp_workspace / "control_flow_resume.yaml"
    workflow_content = """
version: "1.8"
name: Control Flow Resume Workflow
max_transitions: 5
steps:
  - name: Step1
    max_visits: 3
    command: ["echo", "Hello from Step1"]
  - name: Step2
    command: ["echo", "Hello from Step2"]
"""
    workflow_path.write_text(workflow_content)
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "control-flow-run"
    state_dir = temp_workspace / ".orchestrate" / "runs" / run_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0},
        },
        "transition_count": 1,
        "step_visits": {"Step1": 1},
    }, indent=2))

    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'Step1': {'status': 'completed'},
                'Step2': {'status': 'completed'},
            },
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(run_id=run_id)

        state_manager = MockExecutor.call_args.kwargs['state_manager']
        assert state_manager.state.transition_count == 1
        assert state_manager.state.step_visits == {"Step1": 1}

    assert result == 0


def test_resume_uses_custom_state_dir_override(temp_workspace):
    """Resume should locate and reopen runs stored under a custom runs root."""
    workflow_path = temp_workspace / "custom_state_dir_resume.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "1.1",
                "name": "Custom State Dir Resume Workflow",
                "steps": [
                    {
                        "name": "Step1",
                        "command": ["bash", "-lc", "printf 'one\\n' >> state/history.log"],
                    },
                    {
                        "name": "Step2",
                        "command": ["bash", "-lc", "printf 'two\\n' >> state/history.log"],
                    },
                ],
            },
            sort_keys=False,
        )
    )

    custom_runs_root = temp_workspace / "external-runs"
    run_id = "custom-state-dir-run"
    state_manager = StateManager(
        workspace=temp_workspace,
        run_id=run_id,
        state_dir=custom_runs_root,
    )
    state_manager.initialize("custom_state_dir_resume.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {
        "Step1": {"status": "completed", "exit_code": 0},
        "Step2": {"status": "pending"},
    }
    state_manager._write_state()

    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'Step1': {'status': 'completed', 'exit_code': 0},
                'Step2': {'status': 'completed', 'exit_code': 0},
            },
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                state_dir=str(custom_runs_root),
            )

        constructor_kwargs = MockExecutor.call_args.kwargs
        resumed_state_manager = constructor_kwargs['state_manager']
        assert resumed_state_manager.runs_root == custom_runs_root.resolve()
        assert resumed_state_manager.run_root == custom_runs_root.resolve() / run_id

    assert result == 0


def test_resume_defaults_retry_settings_for_provider_steps(temp_workspace):
    """Resume normalizes retry defaults before constructing the executor."""
    workflow_path = temp_workspace / "provider_resume.yaml"
    workflow_content = """
version: "1.1"
name: Provider Resume Workflow
providers:
  test_provider:
    command: ["echo", "${PROMPT}"]
steps:
  - name: ProviderStep
    provider: test_provider
"""
    workflow_path.write_text(workflow_content)
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "provider-resume-run"
    state_dir = temp_workspace / ".orchestrate" / "runs" / run_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "steps": {
            "ProviderStep": {"status": "failed", "exit_code": 1},
        },
    }, indent=2))

    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'ProviderStep': {'status': 'completed', 'exit_code': 0},
            },
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(run_id=run_id)

        constructor_kwargs = MockExecutor.call_args.kwargs
        assert constructor_kwargs['max_retries'] == 1
        assert constructor_kwargs['retry_delay_ms'] == 1000

        execute_kwargs = mock_executor.execute.call_args.kwargs
        assert execute_kwargs['max_retries'] == 1
        assert execute_kwargs['retry_delay_ms'] == 1000

    assert result == 0


def test_at4_resume_displays_progress_information(temp_workspace, partial_run_state, capsys):
    """Test that resume command displays progress information."""
    run_id, state_dir = partial_run_state

    # Add more steps to state
    state = json.loads((state_dir / "state.json").read_text())
    state["steps"]["Step2"] = {"status": "failed", "exit_code": 1}
    (state_dir / "state.json").write_text(json.dumps(state, indent=2))

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {}
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=False
            )

    captured = capsys.readouterr()
    assert "Resuming run test-run-123" in captured.out
    assert "Completed steps: Step1" in captured.out
    assert "Pending steps: Step2" in captured.out


def test_resume_quarantines_interrupted_provider_session_visit(temp_workspace, capsys):
    """Interrupted provider-session visits are quarantined instead of replayed."""
    workflow_path = temp_workspace / "provider_session_resume.yaml"
    workflow_content = """
version: "2.10"
name: provider-session-resume
providers:
  codex_session:
    command: ["bash", "-lc", "echo should-not-run"]
    input_mode: "stdin"
    session_support:
      metadata_mode: codex_exec_jsonl_stdout
      fresh_command: ["bash", "-lc", "echo should-not-run"]
      resume_command: ["bash", "-lc", "echo should-not-run ${SESSION_ID}"]
artifacts:
  implementation_session_id:
    kind: scalar
    type: string
steps:
  - name: StartImplementation
    id: start_implementation
    provider: codex_session
    provider_session:
      mode: fresh
      publish_artifact: implementation_session_id
"""
    workflow_path.write_text(workflow_content, encoding="utf-8")
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "provider-session-quarantine-run"
    state_dir = temp_workspace / ".orchestrate" / "runs" / run_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "running",
        "context": {},
        "steps": {
            "StartImplementation": {
                "status": "completed",
                "step_id": "root.start_implementation",
                "visit_count": 1,
                "exit_code": 0,
                "artifacts": {
                    "implementation_session_id": "sess-old",
                },
            },
        },
        "current_step": {
            "name": "StartImplementation",
            "index": 0,
            "type": "provider",
            "status": "running",
            "step_id": "root.start_implementation",
            "visit_count": 2,
            "started_at": "2024-01-01T00:02:00Z",
            "last_heartbeat_at": "2024-01-01T00:02:00Z",
        },
        "artifact_versions": {
            "implementation_session_id": [
                {
                    "version": 1,
                    "value": "sess-old",
                    "producer": "root.start_implementation",
                    "producer_name": "StartImplementation",
                    "step_index": 0,
                }
            ]
        },
        "artifact_consumes": {},
        "transition_count": 0,
        "step_visits": {"StartImplementation": 2},
    }, indent=2), encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(run_id=run_id)

    assert result == 1
    persisted_state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    error = persisted_state["error"]
    metadata_path = Path(error["context"]["metadata_path"])
    transport_spool_path = Path(error["context"]["transport_spool_path"])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert persisted_state["status"] == "failed"
    assert persisted_state.get("current_step") is None
    assert persisted_state["steps"]["StartImplementation"]["visit_count"] == 1
    assert error["type"] == "provider_session_interrupted_visit_quarantined"
    assert error["context"]["visit_count"] == 2
    assert error["context"]["metadata_synthesized"] is True
    assert metadata["step_status"] == "interrupted"
    assert metadata["publication_state"] == "quarantined_interrupted_visit"
    assert metadata["metadata_synthesized"] is True
    assert transport_spool_path.exists()

    captured = capsys.readouterr()
    assert "interrupted provider-session visit was quarantined" in captured.err


def test_resume_quarantines_interrupted_provider_session_visit_without_current_step_name(
    temp_workspace,
    capsys,
):
    """Interrupted provider-session visits still quarantine when only durable identity survives."""
    workflow_path = temp_workspace / "provider_session_resume_missing_name.yaml"
    workflow_content = """
version: "2.10"
name: provider-session-resume-missing-name
providers:
  codex_session:
    command: ["bash", "-lc", "echo should-not-run"]
    input_mode: "stdin"
    session_support:
      metadata_mode: codex_exec_jsonl_stdout
      fresh_command: ["bash", "-lc", "echo should-not-run"]
      resume_command: ["bash", "-lc", "echo should-not-run ${SESSION_ID}"]
artifacts:
  implementation_session_id:
    kind: scalar
    type: string
steps:
  - name: StartImplementation
    id: start_implementation
    provider: codex_session
    provider_session:
      mode: fresh
      publish_artifact: implementation_session_id
"""
    workflow_path.write_text(workflow_content, encoding="utf-8")
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "provider-session-quarantine-missing-name"
    state_dir = temp_workspace / ".orchestrate" / "runs" / run_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "running",
        "context": {},
        "steps": {
            "StartImplementation": {
                "status": "completed",
                "step_id": "root.start_implementation",
                "visit_count": 1,
                "exit_code": 0,
                "artifacts": {
                    "implementation_session_id": "sess-old",
                },
            },
        },
        "current_step": {
            "index": 0,
            "type": "provider",
            "status": "running",
            "step_id": "root.start_implementation",
            "visit_count": 2,
            "started_at": "2024-01-01T00:02:00Z",
            "last_heartbeat_at": "2024-01-01T00:02:00Z",
        },
        "artifact_versions": {
            "implementation_session_id": [
                {
                    "version": 1,
                    "value": "sess-old",
                    "producer": "root.start_implementation",
                    "producer_name": "StartImplementation",
                    "step_index": 0,
                }
            ]
        },
        "artifact_consumes": {},
        "transition_count": 0,
        "step_visits": {"StartImplementation": 2},
    }, indent=2), encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(run_id=run_id)

    assert result == 1
    persisted_state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    error = persisted_state["error"]
    metadata_path = Path(error["context"]["metadata_path"])
    transport_spool_path = Path(error["context"]["transport_spool_path"])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert persisted_state["status"] == "failed"
    assert persisted_state.get("current_step") is None
    assert persisted_state["steps"]["StartImplementation"]["visit_count"] == 1
    assert error["type"] == "provider_session_interrupted_visit_quarantined"
    assert error["context"]["step_name"] == "StartImplementation"
    assert error["context"]["visit_count"] == 2
    assert error["context"]["metadata_synthesized"] is True
    assert metadata["step_status"] == "interrupted"
    assert metadata["publication_state"] == "quarantined_interrupted_visit"
    assert metadata["metadata_synthesized"] is True
    assert transport_spool_path.exists()

    captured = capsys.readouterr()
    assert "interrupted provider-session visit was quarantined" in captured.err


def test_resume_quarantines_live_provider_session_with_retained_partial_spool(temp_workspace, capsys):
    """Resume quarantine retains the bytes captured before a live provider-session run was interrupted."""
    workflow_path = temp_workspace / "provider_session_resume_live.yaml"
    session_script = "\n".join(
        [
            "python -u - <<'PY'",
            "import sys, time",
            "sys.stdout.write('{\"type\":\"session.started\",\"session_id\":\"sess-live\"}\\n')",
            "sys.stdout.flush()",
            "sys.stdout.write('{\"type\":\"assistant.message\",\"role\":\"assistant\",\"text\":\"partial\"}\\n')",
            "sys.stdout.flush()",
            "time.sleep(30)",
            "sys.stdout.write('{\"type\":\"response.completed\",\"session_id\":\"sess-live\"}\\n')",
            "sys.stdout.flush()",
            "PY",
        ]
    )
    workflow_content = {
        "version": "2.10",
        "name": "provider-session-live-resume",
        "providers": {
            "codex_session": {
                "command": ["bash", "-lc", session_script],
                "input_mode": "stdin",
                "session_support": {
                    "metadata_mode": "codex_exec_jsonl_stdout",
                    "fresh_command": ["bash", "-lc", session_script],
                    "resume_command": ["bash", "-lc", "echo should-not-run ${SESSION_ID}"],
                },
            }
        },
        "artifacts": {
            "implementation_session_id": {
                "kind": "scalar",
                "type": "string",
            }
        },
        "steps": [
            {
                "name": "StartImplementation",
                "id": "start_implementation",
                "provider": "codex_session",
                "provider_session": {
                    "mode": "fresh",
                    "publish_artifact": "implementation_session_id",
                },
            }
        ],
    }
    workflow_path.write_text(yaml.safe_dump(workflow_content, sort_keys=False), encoding="utf-8")

    runs_root = temp_workspace / ".orchestrate" / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

    run_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "run",
            workflow_path.name,
            "--state-dir",
            str(runs_root),
        ],
        cwd=temp_workspace,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    run_id = None
    state_file = None
    transport_spool_path = None
    deadline = time.time() + 15
    while time.time() < deadline:
        run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
        if run_dirs:
            run_id = run_dirs[0].name
            state_file = run_dirs[0] / "state.json"
            transport_candidates = list((run_dirs[0] / "provider_sessions").glob("*.transport.log"))
            if state_file.exists():
                snapshot = json.loads(state_file.read_text(encoding="utf-8"))
                current_step = snapshot.get("current_step")
                if (
                    isinstance(current_step, dict)
                    and current_step.get("name") == "StartImplementation"
                    and transport_candidates
                ):
                    candidate = transport_candidates[0]
                    if candidate.exists() and candidate.stat().st_size > 0:
                        if "partial" in candidate.read_text(encoding="utf-8"):
                            transport_spool_path = candidate
                            break
        time.sleep(0.05)

    assert run_id is not None
    assert state_file is not None and state_file.exists()
    assert transport_spool_path is not None and transport_spool_path.exists()

    os.killpg(run_process.pid, signal.SIGTERM)
    try:
        run_process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(run_process.pid, signal.SIGKILL)
        run_process.communicate(timeout=5)

    partial_spool = transport_spool_path.read_text(encoding="utf-8")
    assert "session.started" in partial_spool
    assert "partial" in partial_spool
    assert "response.completed" not in partial_spool

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(run_id=run_id, state_dir=str(runs_root))

    assert result == 1
    persisted_state = json.loads(state_file.read_text(encoding="utf-8"))
    error = persisted_state["error"]
    metadata_path = Path(error["context"]["metadata_path"])
    retained_spool_path = Path(error["context"]["transport_spool_path"])
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert persisted_state["status"] == "failed"
    assert error["type"] == "provider_session_interrupted_visit_quarantined"
    assert error["context"]["metadata_synthesized"] is False
    assert retained_spool_path == transport_spool_path
    assert retained_spool_path.read_text(encoding="utf-8") == partial_spool
    assert metadata["step_status"] == "interrupted"
    assert metadata["publication_state"] == "quarantined_interrupted_visit"
    assert metadata["captured_transport_bytes"] > 0
    assert metadata["metadata_synthesized"] is False

    captured = capsys.readouterr()
    assert "interrupted provider-session visit was quarantined" in captured.err


def test_resume_refuses_to_clear_existing_provider_session_quarantine(temp_workspace, capsys):
    """Persisted quarantine markers fail fast on later resume attempts."""
    workflow_path = temp_workspace / "provider_session_resume.yaml"
    workflow_content = """
version: "2.10"
name: provider-session-resume
steps:
  - name: StartImplementation
    provider: codex
    provider_session:
      mode: fresh
      publish_artifact: implementation_session_id
artifacts:
  implementation_session_id:
    kind: scalar
    type: string
"""
    workflow_path.write_text(workflow_content, encoding="utf-8")
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "provider-session-quarantine-existing"
    state_dir = temp_workspace / ".orchestrate" / "runs" / run_id
    state_dir.mkdir(parents=True)
    metadata_path = state_dir / "provider_sessions" / "root.startimplementation__v1.json"
    transport_spool_path = state_dir / "provider_sessions" / "root.startimplementation__v1.transport.log"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text("{}", encoding="utf-8")
    transport_spool_path.write_text("", encoding="utf-8")
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "steps": {},
        "error": {
            "type": "provider_session_interrupted_visit_quarantined",
            "message": "An interrupted provider-session visit was quarantined.",
            "context": {
                "step_name": "StartImplementation",
                "step_id": "root.startimplementation",
                "visit_count": 1,
                "metadata_path": str(metadata_path),
                "transport_spool_path": str(transport_spool_path),
                "metadata_synthesized": False,
            },
        },
        "artifact_versions": {},
        "artifact_consumes": {},
        "transition_count": 0,
        "step_visits": {"StartImplementation": 1},
    }, indent=2), encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(run_id=run_id)

    assert result == 1
    captured = capsys.readouterr()
    assert "interrupted provider-session visit was quarantined" in captured.err
