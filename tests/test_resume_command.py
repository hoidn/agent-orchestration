"""Tests for the CLI resume command (AT-4)."""

import os
import json
import pytest
from pathlib import Path
import stat
import tempfile
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from types import MappingProxyType
from unittest.mock import patch, MagicMock
import hashlib

import orchestrator.workflow.loaded_bundle as loaded_bundle_helpers
import orchestrator.cli.commands.resume as resume_command
import orchestrator.workflow.executor as executor_module
from orchestrator.cli.main import main as cli_main
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.monitor.process import write_process_metadata
from orchestrator.state import StateManager
from tests.workflow_fixture_loader import WorkflowLoader
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow.loaded_bundle import workflow_managed_write_root_inputs
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.call_frame_state import _CallFrameStateManager
from orchestrator.workflow.executor_runtime import CallFrameStateManager
from orchestrator.workflow.resume_planner import ResumePlanner
from orchestrator.workflow.executable_ir import ExecutableNodeKind, WorkflowRegion
from orchestrator.workflow.state_projection import (
    CompatibilityNodeProjection,
    CompatibilityStepDefinition,
    WorkflowStateProjection,
)
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.workflow_lisp.wcc.route import LoweringRoute, workflow_lisp_context_with_lowering_schema
from tests.workflow_bundle_helpers import bundle_context_dict


LEXICAL_CHECKPOINT_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_shadow_points.orc")
LEXICAL_RESTORE_FIXTURE = Path("tests/fixtures/workflow_lisp/valid/lexical_checkpoint_restore_regions.orc")


def _persisted_tree_entries(run_root: Path) -> tuple[tuple[str, bytes, bytes], ...]:
    entries: list[tuple[str, bytes, bytes]] = []

    def visit(directory: Path, relative_directory: Path) -> None:
        with os.scandir(directory) as children:
            sorted_children = sorted(children, key=lambda child: child.name)
        for child in sorted_children:
            relative_path = relative_directory / child.name
            relative_text = relative_path.as_posix()
            mode = child.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                entries.append((relative_text, b"d", b""))
                visit(Path(child.path), relative_path)
            elif stat.S_ISREG(mode):
                entries.append((relative_text, b"f", Path(child.path).read_bytes()))
            elif stat.S_ISLNK(mode):
                entries.append((relative_text, b"l", os.readlink(child.path).encode("utf-8")))
            else:
                raise AssertionError(f"unsupported persisted run-tree entry type: {relative_text}")

    visit(run_root, Path())
    return tuple(sorted(entries, key=lambda entry: entry[0]))


def _persisted_tree_snapshot(run_root: Path) -> bytes:
    entries = _persisted_tree_entries(run_root)
    encoded = bytearray(b"orchestrator-persisted-tree-snapshot-v1\x00")
    encoded.extend(len(entries).to_bytes(8, "big"))
    for relative_path, entry_type, payload in entries:
        encoded_path = relative_path.encode("utf-8")
        encoded.extend(entry_type)
        encoded.extend(len(encoded_path).to_bytes(8, "big"))
        encoded.extend(encoded_path)
        encoded.extend(len(payload).to_bytes(8, "big"))
        encoded.extend(payload)
    return bytes(encoded)


def _persisted_tree_digest(snapshot: bytes) -> str:
    return f"sha256:{hashlib.sha256(snapshot).hexdigest()}"


def _seed_projection_integrity_root_resume(
    workspace: Path,
    *,
    run_id: str,
) -> tuple[Path, StateManager]:
    """Seed a checksum-compatible failed v2.0 run with a stale explicit current id."""
    workflow_path = workspace / "projection_integrity_root.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule projection_integrity_root)",
                "  (export orchestrate)",
                "  (defrecord ResumeSummary",
                "    (status String)",
                "    (ready Bool))",
                "  (defworkflow orchestrate",
                "    ((approved Bool)",
                "     (status String))",
                "    -> ResumeSummary",
                "    (record ResumeSummary",
                "      :status status",
                "      :ready approved)))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manager = StateManager(workspace, run_id=run_id)
    state = manager.initialize(workflow_path.name)
    state.status = "failed"
    state.steps = {
        "LegacyCompleted": {
            "status": "completed",
            "name": "LegacyCompleted",
            "step_id": "root.legacy_completed",
        }
    }
    state.step_visits = {"LegacyCompleted": 1}
    state.current_step = {
        "status": "running",
        "name": "RemovedStep",
        "index": 0,
        "step_id": "root.removed_step",
        "visit_count": 1,
    }
    state.call_frames = {
        "preserved-child-frame": {
            "call_frame_id": "preserved-child-frame",
            "call_step_id": "root.preserved_call",
            "status": "failed",
            "state": {
                "schema_version": StateManager.SCHEMA_VERSION,
                "steps": {},
                "call_frames": {},
            },
        }
    }
    manager._write_state()
    preserved_sidecar = manager.run_root / "call_frames" / "preserved" / "sidecar.json"
    preserved_sidecar.parent.mkdir(parents=True)
    preserved_sidecar.write_text(r"""{"preserved": true}
""", encoding="utf-8")
    return workflow_path, manager


def test_persisted_tree_snapshot_tracks_symlink_targets_and_empty_directories(temp_workspace):
    run_root = temp_workspace / "run-tree"
    run_root.mkdir()
    first_target = run_root / "target-a.txt"
    second_target = run_root / "target-b.txt"
    first_target.write_bytes(b"equal contents\n")
    second_target.write_bytes(b"equal contents\n")
    link = run_root / "current.txt"
    link.symlink_to(first_target.name)

    first_link_snapshot = _persisted_tree_snapshot(run_root)
    link.unlink()
    link.symlink_to(second_target.name)
    second_link_snapshot = _persisted_tree_snapshot(run_root)

    assert second_link_snapshot != first_link_snapshot
    assert _persisted_tree_digest(second_link_snapshot) != _persisted_tree_digest(first_link_snapshot)

    first_empty_directory = run_root / "empty-a"
    first_empty_directory.mkdir()
    first_directory_snapshot = _persisted_tree_snapshot(run_root)
    first_empty_directory.rename(run_root / "empty-b")
    second_directory_snapshot = _persisted_tree_snapshot(run_root)

    assert second_directory_snapshot != first_directory_snapshot
    assert _persisted_tree_digest(second_directory_snapshot) != _persisted_tree_digest(first_directory_snapshot)


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


def _allocation_field(allocation, field_name: str):
    if isinstance(allocation, dict):
        return allocation[field_name]
    return getattr(allocation, field_name)


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
            "review_loop": "workflows/library/repeat_until_review_fixture.yaml",
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


def _compile_frontend_loop_recur_bundle(workspace: Path):
    fixture = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid" / "loop_recur_minimal.orc"
    result = compile_stage3_module(
        fixture,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=workspace,
    )
    return result.validated_bundles["loop-recur-minimal"]


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


def _build_root_result_resume_workflow() -> dict:
    return {
        "version": "2.7",
        "name": "root-result-resume",
        "steps": [
            {
                "name": "WriteScalarRoot",
                "id": "write_scalar_root",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'true\\n' > state/scalar.json && printf 'scalar\\n' >> state/replay.log",
                ],
                "output_bundle": {
                    "path": "state/scalar.json",
                    "fields": [{"name": "__result__", "json_pointer": "", "type": "bool"}],
                },
            },
            {
                "name": "Gate",
                "id": "gate",
                "command": ["bash", "-lc", "test -f state/approved.txt"],
            },
        ],
    }


_ROOT_RESULT_BUNDLE_SCRIPTS = {
    "write_optional.py": (
        "import os, pathlib\n"
        'bundle = pathlib.Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        'bundle.write_text("null\\n", encoding="utf-8")\n'
        'with open("state/replay.log", "a", encoding="utf-8") as log:\n'
        '    log.write("optional\\n")\n'
    ),
    "write_list.py": (
        "import os, pathlib\n"
        'bundle = pathlib.Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        'bundle.write_text("[1, 2, 3]\\n", encoding="utf-8")\n'
        'with open("state/replay.log", "a", encoding="utf-8") as log:\n'
        '    log.write("list\\n")\n'
    ),
}


def _compile_root_result_collection_bundle(workspace: Path):
    (workspace / "state").mkdir(exist_ok=True)
    scripts = workspace / "scripts"
    scripts.mkdir(exist_ok=True)
    for name, source in _ROOT_RESULT_BUNDLE_SCRIPTS.items():
        (scripts / name).write_text(source, encoding="utf-8")
    work = workspace / "artifacts" / "work"
    work.mkdir(parents=True, exist_ok=True)
    (work / "report.md").write_text("report\n", encoding="utf-8")
    (work / "summary.json").write_text(r"""{}
""", encoding="utf-8")
    module_path = workspace / "root_result_collection_resume.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule root_result_collection_resume)",
                "  (export orchestrate)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defpath SummaryTarget",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (report WorkReport))",
                "  (defrecord HelperResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord SummaryValue",
                "    (status String)",
                "    (report WorkReport))",
                "  (defworkflow pure-helper",
                "    ((checks ChecksResult))",
                "    -> HelperResult",
                "    (record HelperResult",
                '      :status "ready"',
                "      :report checks.report))",
                "  (defworkflow orchestrate",
                "    ((report_path WorkReport)",
                "     (summary_target SummaryTarget))",
                "    -> List[Int]",
                "    (let* ((maybe (command-result write_optional",
                '             :argv ("python" "scripts/write_optional.py")',
                "             :returns Optional[Bool]))",
                "           (helper",
                "             (call pure-helper",
                "               :checks (record ChecksResult",
                "                         :report report_path)))",
                "           (summary_path",
                "             (materialize-view runtime-summary",
                "               :value (record SummaryValue",
                "                        :status helper.status",
                "                        :report helper.report)",
                "               :renderer canonical-json",
                "               :renderer-version 1",
                "               :target summary_target",
                "               :returns SummaryTarget)))",
                "      (command-result write_list",
                '        :argv ("python" "scripts/write_list.py")',
                "        :returns List[Int]))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            name: ExternalToolBinding(
                name=name,
                stable_command=("python", f"scripts/{name}.py"),
            )
            for name in ("write_optional", "write_list")
        },
        validate_shared=True,
        workspace_root=workspace,
    )
    bundle = next(
        validated
        for name, validated in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )
    return module_path, bundle


def test_projection_runtime_plan_includes_root_result_output_bundle_entries(tmp_path: Path):
    workflow_path = tmp_path / "root_result_resume.yaml"
    workflow_path.write_text(
        json.dumps(_build_root_result_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    entries = {
        (artifact.source_node_id, artifact.publication_mode, artifact.contract_name): artifact
        for artifact in bundle.runtime_plan.artifacts
    }
    root_entry = entries[("root.write_scalar_root", "output_bundle", "__result__")]
    assert root_entry.contract_kind == "bool"


def test_resume_root_result_collection_bundles_persist_and_resume_at_lexical_checkpoints(
    temp_workspace,
):
    run_id = "root-result-collection-resume"
    module_path, bundle = _compile_root_result_collection_bundle(temp_workspace)

    root_plan_entries = [
        artifact
        for artifact in bundle.runtime_plan.artifacts
        if artifact.contract_name == "__result__" and artifact.publication_mode == "output_bundle"
    ]
    assert len({entry.source_node_id for entry in root_plan_entries}) == 2
    assert all(
        isinstance(entry.contract_kind, str) and entry.contract_kind
        for entry in root_plan_entries
    )

    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize(
        str(module_path),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "report_path": "artifacts/work/report.md",
            "summary_target": "artifacts/work/summary.json",
        },
    )

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic materialize-view failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        first_run = WorkflowExecutor(bundle, temp_workspace, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first_run["status"] == "failed"
    first_artifacts = [payload.get("artifacts") for payload in first_run["steps"].values()]
    assert {"__result__": None} in first_artifacts

    resume_state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    resume_state_manager.load()
    resumed = WorkflowExecutor(bundle, temp_workspace, resume_state_manager, retry_delay_ms=0).execute(
        resume=True
    )

    assert resumed["status"] == "completed"
    resumed_artifacts = [payload.get("artifacts") for payload in resumed["steps"].values()]
    assert {"__result__": None} in resumed_artifacts
    assert {"__result__": [1, 2, 3]} in resumed_artifacts
    assert resumed["workflow_outputs"] == {"__result__": [1, 2, 3]}
    replay_log = temp_workspace / "state" / "replay.log"
    assert replay_log.read_text(encoding="utf-8").split() == ["optional", "list"]


def test_projection_runtime_plan_summarizes_artifacts_and_snapshots_from_executable_config(
    tmp_path: Path,
):
    workflow_path = tmp_path / "projection_runtime_plan_snapshot.yaml"
    workflow_path.write_text(
        json.dumps(_build_projection_runtime_plan_snapshot_workflow(), sort_keys=False),
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
    library_path = tmp_path / "workflows" / "library" / "repeat_until_review_fixture.yaml"
    library_path.parent.mkdir(parents=True, exist_ok=True)
    library_path.write_text(
        json.dumps(_build_repeat_until_call_resume_library_workflow(), sort_keys=False),
        encoding="utf-8",
    )
    workflow_path = tmp_path / "repeat_until_call_resume.yaml"
    workflow_path.write_text(
        json.dumps(_build_repeat_until_call_resume_workflow(), sort_keys=False),
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
    bundle = _compile_frontend_loop_recur_bundle(tmp_path)
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


def test_resume_planner_uses_lexical_checkpoint_default_for_eligible_wcc_route(
    tmp_path: Path,
) -> None:
    local_fixture = tmp_path / LEXICAL_RESTORE_FIXTURE.name
    local_fixture.write_text(
        LEXICAL_RESTORE_FIXTURE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    compile_result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        candidate
        for name, candidate in compile_result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )
    planner = ResumePlanner()
    state_manager = StateManager(workspace=tmp_path, run_id="planner-eligible-default")
    state_manager.initialize(
        str(local_fixture),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "report_path": "artifacts/work/report.md",
            "summary_target": "artifacts/work/summary.json",
        },
    )
    called = {"count": 0}

    def _select_restore_candidate(**_kwargs):
        called["count"] += 1
        return SimpleNamespace(
            kind="RESTORED",
            checkpoint_id="ckpt:loop",
            record_id="record:loop",
            source_map_origin_key="source:loop",
            diagnostics=(),
        )

    with patch(
        "orchestrator.workflow_lisp.lexical_checkpoint_restore.select_restore_candidate",
        side_effect=_select_restore_candidate,
    ):
        decision = planner.determine_default_resume_decision(
            {
                "context": bundle_context_dict(bundle),
                "steps": {},
            },
            runtime_plan=bundle.runtime_plan,
            state_manager=state_manager,
            executable_workflow=bundle.ir,
            loaded_workflow=bundle,
            projection=bundle.projection,
        )

    assert decision["mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert decision["restore_decision"] == "RESTORED"
    assert called["count"] == 1


def test_default_resume_report_identifies_validated_prior_boundary_selection() -> None:
    from orchestrator.workflow_lisp.lexical_checkpoint_default_resume import (
        build_runtime_default_resume_report,
    )

    report = build_runtime_default_resume_report(
        workflow_name="generic::workflow",
        decision={
            "route": {"lowering_schema_version": 2, "route_kind": "wcc_schema_2"},
            "required_evidence": {},
            "mode": "LEXICAL_CHECKPOINT_DEFAULT",
            "restore_decision": "RESTORED",
            "checkpoint_id": "checkpoint:prior",
            "record_id": "record:prior",
            "restart_node_id": "root.restart",
            "source_map_origin_key": "source:prior",
            "selection_reason": "validated_prior_boundary",
            "diagnostics": [],
        },
    )

    assert report["selection_reason"] == "validated_prior_boundary"
    assert (
        report["checked_workflows"][0]["decision"]["selection_reason"]
        == "validated_prior_boundary"
    )


def test_resume_planner_marks_legacy_orc_route_historical_compatible_without_lexical_restore(
    tmp_path: Path,
) -> None:
    local_fixture = tmp_path / LEXICAL_RESTORE_FIXTURE.name
    local_fixture.write_text(
        LEXICAL_RESTORE_FIXTURE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        local_fixture,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        candidate
        for name, candidate in result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )
    planner = ResumePlanner()
    state_manager = StateManager(workspace=tmp_path, run_id="planner-historical-default")
    state_manager.initialize(
        str(local_fixture),
        context=workflow_lisp_context_with_lowering_schema(
            bundle_context_dict(bundle),
            1,
        ),
        bound_inputs={
            "report_path": "artifacts/work/report.md",
            "summary_target": "artifacts/work/summary.json",
        },
    )

    with patch(
        "orchestrator.workflow_lisp.lexical_checkpoint_restore.select_restore_candidate",
        side_effect=AssertionError("historical route should not evaluate lexical restore"),
    ):
        decision = planner.determine_default_resume_decision(
            {
                "context": workflow_lisp_context_with_lowering_schema(
                    bundle_context_dict(bundle),
                    1,
                ),
                "steps": {},
            },
            runtime_plan=bundle.runtime_plan,
            state_manager=state_manager,
            executable_workflow=bundle.ir,
            loaded_workflow=bundle,
            projection=bundle.projection,
        )

    assert decision["mode"] == "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"
    assert decision["restore_decision"] is None


def test_resume_planner_marks_yaml_route_ineligible_without_lexical_restore(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "resume_ineligible.yaml"
    workflow_path.write_text(
        json.dumps(_build_structured_if_else_resume_workflow(), sort_keys=False),
        encoding="utf-8",
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    planner = ResumePlanner()
    state_manager = StateManager(workspace=tmp_path, run_id="planner-ineligible-default")
    state_manager.initialize(str(workflow_path), context=bundle_context_dict(bundle))

    with patch(
        "orchestrator.workflow_lisp.lexical_checkpoint_restore.select_restore_candidate",
        side_effect=AssertionError("ineligible route should not evaluate lexical restore"),
    ):
        decision = planner.determine_default_resume_decision(
            {
                "context": bundle_context_dict(bundle),
                "steps": {},
            },
            runtime_plan=bundle.runtime_plan,
            state_manager=state_manager,
            executable_workflow=bundle.ir,
            loaded_workflow=bundle,
            projection=bundle.projection,
        )

    assert decision["mode"] == "INELIGIBLE_STEP_GRANULAR"
    assert decision["restore_decision"] is None


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


@pytest.fixture
def sample_workflow(temp_workspace):
    """Create a minimal compiled-ORC resume fixture."""
    workflow_path = temp_workspace / "test_resume_workflow.orc"
    workflow_content = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.15")',
            "  (defmodule test_resume_workflow)",
            "  (export orchestrate)",
            "  (defrecord ResumeSummary",
            "    (status String)",
            "    (ready Bool))",
            "  (defworkflow orchestrate",
            "    ((approved Bool)",
            "     (status String))",
            "    -> ResumeSummary",
            "    (record ResumeSummary",
            "      :status status",
            "      :ready approved)))",
            "",
        ]
    )
    workflow_path.write_text(workflow_content)

    # Calculate checksum in StateManager format
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    return workflow_path, checksum


def test_persisted_orc_resume_rebuilds_compiled_bundle_dependency(
    temp_workspace,
):
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "workflow_lisp"
    source_root = fixture_root / "modules" / "valid" / "imported_bundle_mix"
    workflow_path = source_root / "neurips" / "entry.orc"
    cli_fixtures = fixture_root / "cli"
    imported_manifest = cli_fixtures / "imported_workflow_bundles.json"
    run_root = temp_workspace / ".orchestrate" / "runs" / "persisted-orc-yaml-dependency"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": StateManager.SCHEMA_VERSION,
                "run_id": "persisted-orc-yaml-dependency",
                "workflow_file": str(workflow_path),
                "status": "failed",
            }
        ),
        encoding="utf-8",
    )
    write_process_metadata(
        run_root,
        argv=(
            "python",
            "-m",
            "orchestrator",
            "run",
            str(workflow_path),
            "--source-root",
            str(source_root),
            "--entry-workflow",
            "orchestrate",
            "--provider-externs-file",
            str(cli_fixtures / "providers.json"),
            "--prompt-externs-file",
            str(cli_fixtures / "prompts.json"),
            "--imported-workflow-bundles-file",
            str(imported_manifest),
            "--command-boundaries-file",
            str(cli_fixtures / "commands.json"),
        ),
    )

    loaded = resume_command._load_resume_workflow_bundle(
        workflow_path=workflow_path,
        workspace_dir=temp_workspace,
        run_root=run_root,
    )

    assert loaded.bundle.surface.name.endswith("orchestrate")
    assert (
        loaded.bundle.imports["selector-run"].surface.name
        == "imported_selector::selector-run"
    )


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
        "bound_inputs": {
            "approved": False,
            "status": "pending",
        },
        "steps": {},
    }

    state_file = state_dir / "state.json"
    state_file.write_text(json.dumps(state, indent=2))

    return run_id, state_dir


def _seed_orc_resume_schema_state(
    workspace: Path,
    *,
    run_id: str,
    lowering_schema: int | None,
    status: str = "completed",
) -> Path:
    workflow_path = workspace / "schema_resume.orc"
    workflow_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\") (defenum Status READY))\n"
    workflow_path.write_text(workflow_text, encoding="utf-8")
    checksum = f"sha256:{hashlib.sha256(workflow_text.encode()).hexdigest()}"
    run_root = workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    context = {}
    if lowering_schema is not None:
        context = workflow_lisp_context_with_lowering_schema(context, lowering_schema)
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": status,
        "context": context,
        "bound_inputs": {},
        "workflow_outputs": {},
        "finalization": {},
        "steps": {},
        "for_each": {},
        "repeat_until": {},
        "call_frames": {},
        "artifact_versions": {},
        "artifact_consumes": {},
        "private_artifact_versions": {},
        "private_artifact_consumes": {},
        "transition_count": 0,
        "step_visits": {},
    }
    (run_root / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return workflow_path


@pytest.mark.parametrize("schema", [1, 2])
def test_workflow_lisp_lowering_schema_same_schema_completed_resume_passes_gate(
    temp_workspace,
    capsys,
    schema: int,
) -> None:
    run_id = f"schema-{schema}-same"
    _seed_orc_resume_schema_state(temp_workspace, run_id=run_id, lowering_schema=schema)
    audit_fixture = temp_workspace / f"schema_{schema}_audit_fixture.yaml"
    audit_fixture.write_text(
        json.dumps(
            {
                "version": "2.0",
                "name": f"schema-{schema}-audit-fixture",
                "steps": [
                    {
                        "name": "NoEffect",
                        "id": "no_effect",
                        "command": ["bash", "-lc", "true"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    bundle = resume_command.ResumeWorkflowBundle(
        bundle=WorkflowLoader(temp_workspace).load_bundle(audit_fixture),
        lowering_schema_version=schema,
    )

    with patch("os.getcwd", return_value=str(temp_workspace)), patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        return_value=bundle,
    ):
        result = resume_workflow(run_id=run_id, force_restart=False)

    captured = capsys.readouterr()
    assert result == 0
    assert "already completed successfully" in captured.out
    assert "workflow_lisp_lowering_schema_mismatch" not in captured.err


@pytest.mark.parametrize(
    ("persisted_schema", "candidate_schema"),
    [(1, 2), (2, 1)],
)
def test_workflow_lisp_lowering_schema_cross_schema_resume_fails_closed(
    temp_workspace,
    capsys,
    persisted_schema: int,
    candidate_schema: int,
) -> None:
    run_id = f"schema-{persisted_schema}-candidate-{candidate_schema}"
    _seed_orc_resume_schema_state(temp_workspace, run_id=run_id, lowering_schema=persisted_schema)
    bundle = resume_command.ResumeWorkflowBundle(
        bundle=SimpleNamespace(),
        lowering_schema_version=candidate_schema,
    )

    with patch("os.getcwd", return_value=str(temp_workspace)), patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        return_value=bundle,
    ):
        result = resume_workflow(run_id=run_id, force_restart=False)

    captured = capsys.readouterr()
    assert result == 1
    assert "workflow_lisp_lowering_schema_mismatch" in captured.err
    assert "persisted lowering schema" in captured.err
    assert "candidate lowering schema" in captured.err
    assert "--force-restart" in captured.err


def test_at4_resume_nonexistent_run(temp_workspace):
    """Test resuming a run that doesn't exist."""
    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id="nonexistent-run",
            repair=False,
            force_restart=False
        )

    assert result == 1  # Should fail


def test_resume_rejects_pre_task6_schema_state(temp_workspace, capsys):
    """Task 6 should reject resume from pre-identity-schema state without an upgrader."""
    workflow_path = temp_workspace / "old_schema_source.orc"
    workflow_source = (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.14")\n'
        "  (defworkflow old-schema () -> Bool true))\n"
    )
    workflow_path.write_text(workflow_source, encoding="utf-8")
    checksum = f"sha256:{hashlib.sha256(workflow_source.encode()).hexdigest()}"
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


def test_repeat_until_resume_clears_stale_failed_nested_call_result_while_child_reruns(
    temp_workspace,
):
    """Resume should not leave a stale failed nested-call step visible while the child call is active."""
    run_id = "repeat-until-call-running-resume"
    library_path = temp_workspace / "workflows" / "library" / "repeat_until_review_fixture.yaml"
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
        json.dumps(library_workflow, sort_keys=False),
        encoding="utf-8",
    )

    workflow_path = temp_workspace / "repeat_until_call_resume.yaml"
    workflow_path.write_text(
        json.dumps(_build_repeat_until_call_resume_workflow(), sort_keys=False),
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


def test_workflow_lisp_resume_ignores_shadow_checkpoint_sidecars(temp_workspace):
    workflow_path = temp_workspace / "lexical_checkpoint_resume_sidecars.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lexical_checkpoint_resume_sidecars)",
                "  (export orchestrate)",
                "  (defpath WorkReport",
                '    :kind relpath',
                '    :under "artifacts/work"',
                '    :must-exist true)',
                "  (defpath SummaryTarget",
                '    :kind relpath',
                '    :under "artifacts/work"',
                '    :must-exist true)',
                "  (defrecord ChecksResult",
                "    (report WorkReport))",
                "  (defrecord HelperResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord SummaryValue",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord Output",
                "    (summary_path SummaryTarget))",
                "  (defworkflow pure-helper",
                "    ((checks ChecksResult))",
                "    -> HelperResult",
                "    (record HelperResult",
                '      :status "ready"',
                "      :report checks.report))",
                "  (defworkflow orchestrate",
                "    ((report_path WorkReport)",
                "     (summary_target SummaryTarget))",
                "    -> Output",
                "    (let* ((helper",
                "             (call pure-helper",
                "               :checks (record ChecksResult",
                "                         :report report_path)))",
                "           (summary_path",
                "             (materialize-view runtime-summary",
                "               :value (record SummaryValue",
                "                        :status helper.status",
                "                        :report helper.report)",
                "               :renderer canonical-json",
                "               :renderer-version 1",
                "               :target summary_target",
                "               :returns SummaryTarget)))",
                "      (record Output",
                "        :summary_path summary_path)))",
                ")",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    compile_result = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(temp_workspace,),
        validate_shared=True,
        workspace_root=temp_workspace,
    )
    bundle = next(
        validated
        for name, validated in compile_result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )

    report_path = temp_workspace / "artifacts" / "work" / "report.md"
    summary_path = temp_workspace / "artifacts" / "work" / "summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("report\n", encoding="utf-8")
    summary_path.write_text(r"""{}
""", encoding="utf-8")

    run_id = "workflow-lisp-shadow-sidecar-resume"
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "report_path": "artifacts/work/report.md",
            "summary_target": "artifacts/work/summary.json",
        },
    )

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic materialize-view failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        first_run = WorkflowExecutor(bundle, temp_workspace, state_manager).execute()

    assert first_run["status"] == "failed"
    shadow_root = temp_workspace / ".orchestrate" / "runs" / run_id / "workflow_lisp" / "checkpoints"
    call_checkpoint_id = next(
        point.checkpoint_id
        for point in bundle.runtime_plan.lexical_checkpoint_points
        if point.details.get("step_kind") == "call"
    )
    sidecars = list((shadow_root / "records" / call_checkpoint_id).rglob("*.json"))
    sidecars.append(shadow_root / "index" / f"{call_checkpoint_id}.json")
    assert sidecars
    for sidecar_path in sidecars:
        sidecar_path.write_text("{not-json}\n", encoding="utf-8")

    with patch('os.getcwd', return_value=str(temp_workspace)), patch(
        'orchestrator.cli.commands.resume._load_resume_workflow_bundle',
        return_value=bundle,
    ):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    loaded_state = StateManager(temp_workspace, run_id=run_id).load()
    assert loaded_state.status == "completed"
    assert loaded_state.steps["lexical_checkpoint_resume_sidecars::orchestrate__materialize-view__runtime-summary"]["status"] == "completed"


def test_workflow_lisp_lexical_checkpoint_resume_restores_private_checkpoint_regions(temp_workspace):
    workflow_path = temp_workspace / LEXICAL_RESTORE_FIXTURE.name
    workflow_path.write_text(LEXICAL_RESTORE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    bundle = next(
        validated
        for name, validated in compile_stage3_entrypoint(
            workflow_path,
            source_roots=(temp_workspace,),
            validate_shared=True,
            workspace_root=temp_workspace,
        ).validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )

    report_path = temp_workspace / "artifacts" / "work" / "report.md"
    summary_path = temp_workspace / "artifacts" / "work" / "summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("report\n", encoding="utf-8")
    summary_path.write_text(r"""{}
""", encoding="utf-8")

    run_id = "workflow-lisp-restore-sidecar-resume"
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "report_path": "artifacts/work/report.md",
            "summary_target": "artifacts/work/summary.json",
        },
    )

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic restore-boundary failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        first_run = WorkflowExecutor(bundle, temp_workspace, state_manager).execute()

    assert first_run["status"] == "failed"
    state = state_manager.load()
    step_id = "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary"
    execution_index = bundle.projection.execution_index_for_step_id(step_id)
    state.current_step = {
        "name": "lexical_checkpoint_restore_regions::orchestrate__materialize-view__runtime-summary",
        "index": execution_index if isinstance(execution_index, int) else 14,
        "step_id": step_id,
        "status": "running",
    }
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__summary_status", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__selected_label__match_decision", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__selected_report__match_decision", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__loop_result__result", None)
    state_manager.state = state
    state_manager._write_state()

    with patch('os.getcwd', return_value=str(temp_workspace)), patch(
        'orchestrator.cli.commands.resume._load_resume_workflow_bundle',
        return_value=bundle,
    ):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    restore_report = state_manager.workflow_lisp_checkpoint_restore_report_path()
    payload = json.loads(restore_report.read_text(encoding="utf-8"))
    assert payload["decision_kind"] == "RESTORED"
    assert payload["policy_decision"] == "REGENERATE"
    assert payload["restored_bindings"] >= 3
    assert payload["restored_loop_frames"] >= 1
    loaded_state = state_manager.load()
    summary_step = loaded_state.steps["lexical_checkpoint_restore_regions::orchestrate__materialize-view__runtime-summary"]
    assert summary_step["status"] == "completed"


def test_resume_command_writes_default_resume_report_for_eligible_workflow_lisp_route(
    temp_workspace,
) -> None:
    workflow_path = temp_workspace / LEXICAL_RESTORE_FIXTURE.name
    workflow_path.write_text(LEXICAL_RESTORE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    bundle = next(
        validated
        for name, validated in compile_stage3_entrypoint(
            workflow_path,
            source_roots=(temp_workspace,),
            validate_shared=True,
            workspace_root=temp_workspace,
        ).validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )

    report_path = temp_workspace / "artifacts" / "work" / "report.md"
    summary_path = temp_workspace / "artifacts" / "work" / "summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("report\n", encoding="utf-8")
    summary_path.write_text(r"""{}
""", encoding="utf-8")

    run_id = "workflow-lisp-default-resume-eligible"
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "report_path": "artifacts/work/report.md",
            "summary_target": "artifacts/work/summary.json",
        },
    )

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic restore-boundary failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        first_run = WorkflowExecutor(bundle, temp_workspace, state_manager).execute()

    assert first_run["status"] == "failed"
    state = state_manager.load()
    step_id = "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary"
    execution_index = bundle.projection.execution_index_for_step_id(step_id)
    state.current_step = {
        "name": "lexical_checkpoint_restore_regions::orchestrate__materialize-view__runtime-summary",
        "index": execution_index if isinstance(execution_index, int) else 14,
        "step_id": step_id,
        "status": "running",
    }
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__summary_status", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__selected_label__match_decision", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__selected_report__match_decision", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__loop_result__result", None)
    state_manager.state = state
    state_manager._write_state()

    with patch('os.getcwd', return_value=str(temp_workspace)), patch(
        'orchestrator.cli.commands.resume._load_resume_workflow_bundle',
        return_value=bundle,
    ):
        result = resume_workflow(run_id=run_id, repair=False, force_restart=False)

    assert result == 0
    payload = json.loads(
        state_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema_version"] == "workflow_lisp_checkpoint_default_resume_report.v1"
    assert payload["default_modes"][0]["mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert payload["default_modes"][0]["restore_decision"] == "RESTORED"
    assert payload["checked_workflows"][0]["decision"]["restore_decision"] == "RESTORED"


def test_resume_command_reuses_planner_restore_decision_for_eligible_workflow_lisp_route(
    temp_workspace,
) -> None:
    workflow_path = temp_workspace / LEXICAL_RESTORE_FIXTURE.name
    workflow_path.write_text(LEXICAL_RESTORE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    bundle = next(
        validated
        for name, validated in compile_stage3_entrypoint(
            workflow_path,
            source_roots=(temp_workspace,),
            validate_shared=True,
            workspace_root=temp_workspace,
        ).validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )

    report_path = temp_workspace / "artifacts" / "work" / "report.md"
    summary_path = temp_workspace / "artifacts" / "work" / "summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("report\n", encoding="utf-8")
    summary_path.write_text(r"""{}
""", encoding="utf-8")

    run_id = "workflow-lisp-default-resume-single-restore-decision"
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
        bound_inputs={
            "report_path": "artifacts/work/report.md",
            "summary_target": "artifacts/work/summary.json",
        },
    )

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic restore-boundary failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        first_run = WorkflowExecutor(bundle, temp_workspace, state_manager).execute()

    assert first_run["status"] == "failed"
    state = state_manager.load()
    step_id = "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary"
    execution_index = bundle.projection.execution_index_for_step_id(step_id)
    state.current_step = {
        "name": "lexical_checkpoint_restore_regions::orchestrate__materialize-view__runtime-summary",
        "index": execution_index if isinstance(execution_index, int) else 14,
        "step_id": step_id,
        "status": "running",
    }
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__summary_status", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__selected_label__match_decision", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__selected_report__match_decision", None)
    state.steps.pop("lexical_checkpoint_restore_regions::orchestrate__loop_result__result", None)
    state_manager.state = state
    state_manager._write_state()

    call_count = {"value": 0}
    from orchestrator.workflow_lisp.lexical_checkpoint_restore import (
        select_restore_candidate as real_select_restore_candidate,
    )

    def _select_restore_candidate(**_kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return real_select_restore_candidate(**_kwargs)
        return SimpleNamespace(
            kind="INVALID",
            checkpoint_id="ckpt:loop",
            record_id="record:loop",
            source_map_origin_key="source:loop",
            diagnostics=("lexical_restore_value_digest_mismatch",),
        )

    with patch("os.getcwd", return_value=str(temp_workspace)), patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        return_value=bundle,
    ), patch(
        "orchestrator.workflow_lisp.lexical_checkpoint_restore.select_restore_candidate",
        side_effect=_select_restore_candidate,
    ):
        result = resume_workflow(run_id=run_id, repair=False, force_restart=False)

    assert result == 0
    assert call_count["value"] == 1
    default_resume_payload = json.loads(
        state_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )
    restore_payload = json.loads(
        state_manager.workflow_lisp_checkpoint_restore_report_path().read_text(
            encoding="utf-8"
        )
    )
    assert default_resume_payload["default_modes"][0]["restore_decision"] == "RESTORED"
    assert restore_payload["decision_kind"] == "RESTORED"


def test_resume_command_writes_default_resume_report_for_historical_legacy_route(
    temp_workspace,
) -> None:
    workflow_path = temp_workspace / LEXICAL_RESTORE_FIXTURE.name
    workflow_path.write_text(LEXICAL_RESTORE_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    compile_result = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(temp_workspace,),
        validate_shared=True,
        workspace_root=temp_workspace,
    )
    bundle = next(
        validated
        for name, validated in compile_result.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )

    report_path = temp_workspace / "artifacts" / "work" / "report.md"
    summary_path = temp_workspace / "artifacts" / "work" / "summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("report\n", encoding="utf-8")
    summary_path.write_text(r"""{}
""", encoding="utf-8")

    run_id = "workflow-lisp-default-resume-historical"
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize(
        str(workflow_path),
        context=workflow_lisp_context_with_lowering_schema(
            bundle_context_dict(bundle),
            1,
        ),
        bound_inputs={
            "report_path": "artifacts/work/report.md",
            "summary_target": "artifacts/work/summary.json",
        },
    )

    real_render_view = WorkflowExecutor._execute_materialize_view.__globals__["render_view"]
    fail_once = {"armed": True}

    def _fail_render_once(*args, **kwargs):
        if fail_once["armed"]:
            fail_once["armed"] = False
            raise RuntimeError("synthetic historical failure")
        return real_render_view(*args, **kwargs)

    with patch("orchestrator.workflow.executor.render_view", side_effect=_fail_render_once):
        first_run = WorkflowExecutor(bundle, temp_workspace, state_manager).execute()

    assert first_run["status"] == "failed"
    state = state_manager.load()
    step_id = "root.lexical_checkpoint_restore_regions_orchestrate__materialize_view__runtime_summary"
    execution_index = bundle.projection.execution_index_for_step_id(step_id)
    state.current_step = {
        "name": "lexical_checkpoint_restore_regions::orchestrate__materialize-view__runtime-summary",
        "index": execution_index if isinstance(execution_index, int) else 14,
        "step_id": step_id,
        "status": "running",
    }
    state_manager.state = state
    state_manager._write_state()
    with patch('os.getcwd', return_value=str(temp_workspace)), patch(
        'orchestrator.cli.commands.resume._load_resume_workflow_bundle',
        return_value=bundle,
    ):
        result = resume_workflow(run_id=run_id, repair=False, force_restart=False)

    assert result == 0
    payload = json.loads(
        state_manager.workflow_lisp_checkpoint_default_resume_report_path().read_text(
            encoding="utf-8"
        )
    )
    assert payload["schema_version"] == "workflow_lisp_checkpoint_default_resume_report.v1"
    assert payload["default_modes"][0]["mode"] == "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"
    assert payload["historical_compatibility"][0]["mode"] == "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"
    assert payload["checked_workflows"][0]["decision"]["restore_decision"] is None


@patch('orchestrator.cli.commands.resume.WorkflowExecutor')
def test_resume_preserves_bound_inputs_in_loaded_state(
    mock_executor,
    temp_workspace,
    sample_workflow,
):
    """Persisted workflow-signature inputs should remain available after resume reload."""
    workflow_path, checksum = sample_workflow
    compiled = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(temp_workspace,),
        validate_shared=True,
        workspace_root=temp_workspace,
    )
    bundle = next(
        candidate
        for name, candidate in compiled.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )
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
        "context": bundle_context_dict(bundle),
        "bound_inputs": {
            "approved": False,
            "status": "pending",
        },
        "steps": {},
    }, indent=2))

    mock_executor.return_value.execute.return_value = {"status": "completed"}

    with patch('os.getcwd', return_value=str(temp_workspace)), patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        return_value=bundle,
    ):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    state_manager = mock_executor.call_args.kwargs["state_manager"]
    assert state_manager.state is not None
    assert state_manager.state.bound_inputs == {
        "approved": False,
        "status": "pending",
    }


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


def test_default_resume_root_checksum_mismatch_is_pre_executor_and_byte_immutable(
    temp_workspace,
    capsys,
):
    run_id = "workflow-lisp-root-checksum-mismatch"
    workflow_path = temp_workspace / "root_checksum_mismatch.orc"
    original_source = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.14")',
            "  (defmodule root_checksum_mismatch)",
            "  (export orchestrate)",
            "  (defrecord ResumeSummary",
            "    (status String)",
            "    (ready Bool))",
            "  (defworkflow orchestrate",
            "    ((approved Bool)",
            "     (status String))",
            "    -> ResumeSummary",
            "    (record ResumeSummary",
            "      :status status",
            "      :ready approved)))",
            "",
        ]
    )
    workflow_path.write_text(original_source, encoding="utf-8")

    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state = state_manager.initialize(str(workflow_path))
    state.status = "failed"
    state.steps = {
        "legacy-step": {
            "status": "completed",
            "step_id": "root.legacy_step",
            "exit_code": 0,
        }
    }
    state.call_frames = {
        "call-frame:legacy": {
            "call_frame_id": "call-frame:legacy",
            "call_step_id": "root.legacy_call",
            "status": "failed",
            "state": {"steps": {"child-step": {"status": "completed"}}},
        }
    }
    state_manager._write_state()

    run_root = state_manager.run_root
    seeded_files = {
        "workflow_lisp/checkpoints/index/ckpt:legacy.json": b'{"records":["record:legacy"]}\n',
        "workflow_lisp/checkpoints/records/ckpt:legacy/record:legacy.json": b'{"status":"completed"}\n',
        "artifacts/legacy-report.md": b"legacy report\n",
        "adjudication/root/root.legacy_step/1/candidate_scores.jsonl": b'{"candidate_id":"legacy"}\n',
        "sidecars/legacy-session.json": b'{"status":"interrupted"}\n',
    }
    for relative_path, contents in seeded_files.items():
        path = run_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    before_entries = _persisted_tree_entries(run_root)
    before_snapshot = _persisted_tree_snapshot(run_root)
    before_digest = _persisted_tree_digest(before_snapshot)
    assert {path for path, _entry_type, _payload in before_entries}.issuperset(
        {
            "state.json",
            *seeded_files,
        }
    )

    workflow_path.write_text(original_source + "; changed root source\n", encoding="utf-8")
    persisted_root_checksum = state.workflow_checksum
    changed_root_checksum = state_manager.calculate_checksum(workflow_path)
    root_checksum_calls = []
    validate_root_checksum = StateManager.validate_checksum

    def record_root_checksum_validation(manager, workflow_file):
        accepted = validate_root_checksum(manager, workflow_file)
        root_checksum_calls.append(
            {
                "run_id": manager.run_id,
                "workflow_file": Path(workflow_file).resolve(),
                "persisted_checksum": manager.state.workflow_checksum,
                "current_checksum": manager.calculate_checksum(workflow_file),
                "accepted": accepted,
            }
        )
        return accepted

    def unexpected_runtime_call(*_args, **_kwargs):
        raise AssertionError("checksum mismatch reached an executor, provider, or command boundary")

    with patch("os.getcwd", return_value=str(temp_workspace)), patch.object(
        StateManager,
        "validate_checksum",
        new=record_root_checksum_validation,
    ), patch(
        "orchestrator.cli.commands.resume.WorkflowExecutor",
        side_effect=unexpected_runtime_call,
    ) as executor_constructor, patch.object(
        WorkflowExecutor,
        "_execute_provider_with_context",
        side_effect=unexpected_runtime_call,
    ) as provider_entrypoint, patch.object(
        WorkflowExecutor,
        "_execute_command_with_context",
        side_effect=unexpected_runtime_call,
    ) as command_entrypoint:
        result = resume_workflow(run_id=run_id, repair=False, force_restart=False)

    captured = capsys.readouterr()
    after_entries = _persisted_tree_entries(run_root)
    after_snapshot = _persisted_tree_snapshot(run_root)
    after_digest = _persisted_tree_digest(after_snapshot)

    assert result == 1
    assert "checksum" in captured.err.lower()
    assert root_checksum_calls == [
        {
            "run_id": run_id,
            "workflow_file": workflow_path.resolve(),
            "persisted_checksum": persisted_root_checksum,
            "current_checksum": changed_root_checksum,
            "accepted": False,
        }
    ]
    assert changed_root_checksum != persisted_root_checksum
    executor_constructor.assert_not_called()
    provider_entrypoint.assert_not_called()
    command_entrypoint.assert_not_called()
    assert after_entries == before_entries
    assert after_snapshot == before_snapshot
    assert after_digest == before_digest


@pytest.mark.parametrize(
    ("resume_kwargs", "expected_observability"),
    [
        ({}, None),
        (
            {"summary_mode": "sync", "summary_provider": "projection-summary"},
            {
                "step_summaries": {
                    "enabled": True,
                    "mode": "sync",
                    "provider": "projection-summary",
                    "timeout_sec": 300,
                    "max_input_chars": 12000,
                    "best_effort": True,
                }
            },
        ),
    ],
)
def test_projection_resume_root_cli_audit_precedes_override_session_process_and_executor(
    temp_workspace: Path,
    resume_kwargs: dict,
    expected_observability: dict | None,
) -> None:
    """Reject a stale root identity before every mutable resume boundary."""
    run_id = (
        "projection-root-override"
        if resume_kwargs
        else "projection-root-default"
    )
    _workflow_path, manager = _seed_projection_integrity_root_resume(
        temp_workspace,
        run_id=run_id,
    )
    assert manager.state is not None
    manager.state.error = {
        "type": resume_command.PROVIDER_SESSION_QUARANTINE_ERROR,
        "message": "stale quarantine must not preempt root projection audit",
        "context": {
            "metadata_path": "provider_sessions/private.json",
            "transport_spool_path": "provider_sessions/private.log",
        },
    }
    manager._write_state()
    before_state = json.loads(manager.state_file.read_text(encoding="utf-8"))
    before_entries = _persisted_tree_entries(manager.run_root)
    before_snapshot = _persisted_tree_snapshot(manager.run_root)
    events: list[str] = []

    original_state_write = StateManager._write_state
    original_bundle_load = resume_command._load_resume_workflow_bundle
    original_checksum = StateManager.validate_checksum
    from orchestrator.workflow.resume_projection_integrity import (
        audit_scope as real_audit_scope,
    )

    def record_state_write(state_manager):
        if (
            expected_observability is not None
            and "observability.persist" not in events
            and "bundle.load" not in events
            and state_manager.state is not None
            and state_manager.state.observability == expected_observability
            and state_manager.state.runtime_observability is None
        ):
            events.append("observability.persist")
        return original_state_write(state_manager)

    def record_bundle_load(**kwargs):
        events.append("bundle.load")
        return original_bundle_load(**kwargs)

    def record_checksum(state_manager, workflow_file):
        events.append("root_checksum.validate")
        return original_checksum(state_manager, workflow_file)

    def record_audit(bundle, state, scope_path):
        events.append("root_projection.audit")
        return real_audit_scope(bundle, state, scope_path)

    def unexpected_mutation(*_args, **_kwargs):
        raise AssertionError("projection integrity failure reached a mutable resume boundary")

    with patch("os.getcwd", return_value=str(temp_workspace)), patch.object(
        StateManager,
        "_write_state",
        record_state_write,
    ), patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        new=record_bundle_load,
    ), patch.object(
        StateManager,
        "validate_checksum",
        record_checksum,
    ), patch.object(
        resume_command,
        "audit_scope",
        new=record_audit,
        create=True,
    ), patch(
        "orchestrator.cli.commands.resume.open_executor_session",
        side_effect=unexpected_mutation,
    ) as open_session, patch(
        "orchestrator.cli.commands.resume.write_process_metadata",
        side_effect=unexpected_mutation,
    ) as process_metadata, patch(
        "orchestrator.cli.commands.resume.WorkflowExecutor",
        side_effect=unexpected_mutation,
    ) as executor_constructor, patch.object(
        WorkflowExecutor,
        "_execute_prologue",
        side_effect=unexpected_mutation,
    ) as prologue, patch.object(
        StateManager,
        "backup_state",
        side_effect=unexpected_mutation,
    ) as backup_state, patch(
        "orchestrator.cli.commands.resume._merge_observability_overrides",
        side_effect=unexpected_mutation,
    ) as merge_overrides, patch(
        "orchestrator.workflow_lisp.procedure_identity_retirement.load_retirement_evidence",
        side_effect=unexpected_mutation,
        create=True,
    ) as evidence_reader, patch.object(
        ResumePlanner,
        "detect_interrupted_provider_session_visit",
        side_effect=unexpected_mutation,
    ) as quarantine_planner, patch.object(
        ResumePlanner,
        "determine_restart_node_id",
        side_effect=unexpected_mutation,
    ) as restart_planner, patch.object(
        WorkflowExecutor,
        "_execute_provider_with_context",
        side_effect=unexpected_mutation,
    ) as provider_effect, patch.object(
        WorkflowExecutor,
        "_execute_command_with_context",
        side_effect=unexpected_mutation,
    ) as command_effect:
        result = resume_workflow(run_id=run_id, **resume_kwargs)

    after_state = json.loads(manager.state_file.read_text(encoding="utf-8"))
    after_entries = _persisted_tree_entries(manager.run_root)
    after_snapshot = _persisted_tree_snapshot(manager.run_root)

    assert result == 1
    assert events == [
        "bundle.load",
        "root_checksum.validate",
        "root_projection.audit",
    ]
    open_session.assert_not_called()
    process_metadata.assert_not_called()
    executor_constructor.assert_not_called()
    prologue.assert_not_called()
    backup_state.assert_not_called()
    merge_overrides.assert_not_called()
    evidence_reader.assert_not_called()
    quarantine_planner.assert_not_called()
    restart_planner.assert_not_called()
    provider_effect.assert_not_called()
    command_effect.assert_not_called()
    assert before_snapshot != after_snapshot
    assert before_entries != after_entries
    assert after_state["status"] == "failed"
    assert after_state["error"]["type"] == "resume_projection_integrity_error"
    assert after_state["error"]["context"]["reason"] == "unclaimed_explicit_step_row"
    assert after_state["updated_at"] != before_state["updated_at"]
    assert after_state["steps"] == before_state["steps"]
    assert after_state["step_visits"] == before_state["step_visits"]
    assert after_state["current_step"] == before_state["current_step"]
    assert after_state["call_frames"] == before_state["call_frames"]
    assert after_state.get("observability") == before_state.get("observability")
    assert "runtime_observability" not in after_state
    assert not (manager.run_root / "monitor_process.json").exists()
    assert (
        manager.run_root / "call_frames" / "preserved" / "sidecar.json"
    ).read_text(encoding="utf-8") == r"""{"preserved": true}
"""
    assert not (manager.run_root / "provider_sessions").exists()
    assert not (temp_workspace / "state" / "effect.txt").exists()


def test_projection_resume_root_direct_executor_rechecks_checksum_and_audit_before_prologue(
    temp_workspace: Path,
) -> None:
    """Direct root resume rejects stale identity before prologue."""
    workflow_path, manager = _seed_projection_integrity_root_resume(
        temp_workspace,
        run_id="projection-root-direct",
    )
    compiled = compile_stage3_entrypoint(
        workflow_path,
        source_roots=(temp_workspace,),
        validate_shared=True,
        workspace_root=temp_workspace,
    )
    bundle = next(
        candidate
        for name, candidate in compiled.validated_bundles_by_name.items()
        if name == "orchestrate" or name.endswith("::orchestrate")
    )
    before_state = json.loads(manager.state_file.read_text(encoding="utf-8"))
    events: list[str] = []
    original_checksum = manager.calculate_checksum
    from orchestrator.workflow.resume_projection_integrity import (
        audit_scope as real_audit_scope,
    )

    def record_checksum(path):
        events.append("root_checksum.calculate")
        return original_checksum(path)

    def record_audit(loaded_bundle, state, scope_path):
        events.append("root_projection.audit")
        return real_audit_scope(loaded_bundle, state, scope_path)

    with patch.object(
        manager,
        "calculate_checksum",
        side_effect=record_checksum,
    ), patch.object(
        executor_module,
        "audit_scope",
        new=record_audit,
        create=True,
    ), patch.object(
        WorkflowExecutor,
        "_execute_prologue",
        side_effect=AssertionError("root guard must reject before prologue"),
    ) as prologue:
        result = WorkflowExecutor(bundle, temp_workspace, manager).execute(resume=True)

    after_state = json.loads(manager.state_file.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert events == ["root_checksum.calculate", "root_projection.audit"]
    prologue.assert_not_called()
    assert after_state["error"]["type"] == "resume_projection_integrity_error"
    assert after_state["updated_at"] != before_state["updated_at"]
    assert after_state["steps"] == before_state["steps"]
    assert after_state["step_visits"] == before_state["step_visits"]
    assert after_state["current_step"] == before_state["current_step"]
    assert after_state["call_frames"] == before_state["call_frames"]
    assert "runtime_observability" not in after_state
    assert not (manager.run_root / "monitor_process.json").exists()
    assert not (manager.run_root / "provider_sessions").exists()


def test_projection_resume_child_executor_skips_root_guard_structurally(
    temp_workspace: Path,
) -> None:
    workflow_path = temp_workspace / "projection_child.yaml"
    workflow_path.write_text(
        json.dumps(
            {
                "version": "2.0",
                "name": "projection-child",
                "steps": [
                    {
                        "name": "NoEffect",
                        "id": "no_effect",
                        "command": ["bash", "-lc", "true"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    bundle = WorkflowLoader(temp_workspace).load_bundle(workflow_path)
    parent = StateManager(temp_workspace, run_id="projection-child-structural")
    parent.initialize(workflow_path.name)
    child_manager = _CallFrameStateManager(
        parent_manager=parent,
        workflow=bundle,
        frame_id="root.invoke_child::visit::1",
        call_step_name="InvokeChild",
        call_step_id="root.invoke_child",
        import_alias="child",
        bound_inputs={},
    )
    assert isinstance(child_manager, CallFrameStateManager)
    child_manager.state.status = "failed"
    child_manager.state.steps = {
        "Legacy": {
            "status": "completed",
            "step_id": "root.removed_child_step",
        }
    }
    child_manager._write_state()
    expected = child_manager.state.to_dict()

    with patch.object(
        child_manager,
        "calculate_checksum",
        side_effect=AssertionError("child executor must skip root checksum guard"),
    ) as checksum, patch.object(
        executor_module,
        "audit_scope",
        side_effect=AssertionError("child executor must skip root projection guard"),
        create=True,
    ) as audit, patch.object(
        WorkflowExecutor,
        "_execute_prologue",
        return_value=expected,
    ) as prologue:
        result = WorkflowExecutor(
            bundle,
            temp_workspace,
            child_manager,
        ).execute(resume=True)

    assert result == expected
    checksum.assert_not_called()
    audit.assert_not_called()
    prologue.assert_called_once()


def test_projection_resume_post_cli_identity_race_uses_three_field_delta_and_closes_session(
    temp_workspace: Path,
) -> None:
    run_id = "projection-post-cli-race"
    workflow_path = temp_workspace / "projection_post_cli_race.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule projection_post_cli_race)",
                "  (export orchestrate)",
                "  (defrecord ResumeSummary",
                "    (status String)",
                "    (ready Bool))",
                "  (defworkflow orchestrate",
                "    ((approved Bool)",
                "     (status String))",
                "    -> ResumeSummary",
                "    (record ResumeSummary",
                "      :status status",
                "      :ready approved)))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manager = StateManager(temp_workspace, run_id=run_id)
    state = manager.initialize(workflow_path.name)
    state.status = "failed"
    manager._write_state()
    before_state = json.loads(manager.state_file.read_text(encoding="utf-8"))
    original_init = WorkflowExecutor.__init__

    def mutate_after_cli_preflight(executor, *args, **kwargs):
        original_init(executor, *args, **kwargs)
        raced_manager = executor.state_manager
        raced_manager.state.steps["Legacy"] = {
            "status": "completed",
            "step_id": "root.removed_after_preflight",
        }
        raced_manager._write_state()

    with patch("os.getcwd", return_value=str(temp_workspace)), patch.object(
        WorkflowExecutor,
        "__init__",
        mutate_after_cli_preflight,
    ), patch.object(
        WorkflowExecutor,
        "_execute_prologue",
        side_effect=AssertionError("post-CLI race must reject before prologue"),
    ) as prologue:
        result = resume_workflow(run_id=run_id)

    after_state = json.loads(manager.state_file.read_text(encoding="utf-8"))
    assert result == 1
    prologue.assert_not_called()
    assert after_state["status"] == "failed"
    assert after_state["error"]["type"] == "resume_projection_integrity_error"
    assert after_state["error"]["context"]["offending_value"] == "root.removed_after_preflight"
    assert after_state["updated_at"] != before_state["updated_at"]
    assert after_state.get("current_step") == before_state.get("current_step")
    assert after_state["step_visits"] == before_state.get("step_visits", {})
    assert after_state["call_frames"] == before_state.get("call_frames", {})
    assert after_state["steps"] == {
        "Legacy": {
            "status": "completed",
            "step_id": "root.removed_after_preflight",
        }
    }
    sessions = after_state["runtime_observability"]["executor_sessions"]
    assert len(sessions) == 1
    assert sessions[0]["status"] == "failed"
    assert sessions[0]["ended_at"]
    assert (manager.run_root / "monitor_process.json").is_file()


@pytest.mark.parametrize(
    ("reason", "persisted_checksum", "workflow_path_mode"),
    [
        ("workflow_modified", "sha256:" + ("0" * 64), "current"),
        ("missing_recorded_checksum", "", "current"),
        ("missing_workflow_path", "sha256:" + ("0" * 64), "missing"),
        ("workflow_unavailable", "sha256:" + ("0" * 64), "unavailable"),
    ],
)
def test_projection_resume_root_executor_checksum_mismatch_envelope(
    temp_workspace: Path,
    reason: str,
    persisted_checksum: str,
    workflow_path_mode: str,
) -> None:
    workflow_path = temp_workspace / f"checksum_{reason}.yaml"
    workflow_path.write_text(
        json.dumps(
            {
                "version": "2.0",
                "name": f"checksum-{reason}",
                "steps": [
                    {
                        "name": "NoEffect",
                        "id": "no_effect",
                        "command": ["bash", "-lc", "true"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manager = StateManager(temp_workspace, run_id=f"checksum-{reason}")
    state = manager.initialize(workflow_path.name)
    state.status = "failed"
    state.workflow_checksum = persisted_checksum
    state.steps = {"Preserved": {"status": "completed"}}
    manager._write_state()
    bundle = WorkflowLoader(temp_workspace).load_bundle(workflow_path)
    if workflow_path_mode == "missing":
        bundle = replace(
            bundle,
            provenance=replace(bundle.provenance, workflow_path=None),
        )
        expected_workflow_file = None
        expected_current_checksum = None
    elif workflow_path_mode == "unavailable":
        unavailable_path = temp_workspace / "removed.yaml"
        bundle = replace(
            bundle,
            provenance=replace(bundle.provenance, workflow_path=unavailable_path),
        )
        expected_workflow_file = str(unavailable_path)
        expected_current_checksum = None
    else:
        expected_workflow_file = str(workflow_path)
        expected_current_checksum = manager.calculate_checksum(workflow_path)
    before_state = json.loads(manager.state_file.read_text(encoding="utf-8"))

    with patch.object(
        executor_module,
        "audit_scope",
        side_effect=AssertionError("checksum mismatch must precede projection audit"),
        create=True,
    ) as audit, patch.object(
        WorkflowExecutor,
        "_execute_prologue",
        side_effect=AssertionError("checksum mismatch must precede prologue"),
    ) as prologue:
        result = WorkflowExecutor(bundle, temp_workspace, manager).execute(resume=True)

    after_state = json.loads(manager.state_file.read_text(encoding="utf-8"))
    audit.assert_not_called()
    prologue.assert_not_called()
    assert result["status"] == "failed"
    assert after_state["error"] == {
        "type": "workflow_checksum_mismatch",
        "message": "Workflow has been modified since the run started",
        "context": {
            "workflow_file": expected_workflow_file,
            "persisted_checksum": (
                persisted_checksum if persisted_checksum.startswith("sha256:") else None
            ),
            "current_checksum": expected_current_checksum,
            "reason": reason,
        },
    }
    assert after_state["updated_at"] != before_state["updated_at"]
    for key in (
        "current_step",
        "steps",
        "step_visits",
        "for_each",
        "repeat_until",
        "call_frames",
        "artifacts",
        "workflow_outputs",
    ):
        assert after_state.get(key) == before_state.get(key)


def _seed_public_omitted_step_id_state(
    workspace: Path,
    *,
    run_id: str,
    row_shape: str,
) -> tuple[StateManager, str]:
    workflow_path = workspace / f"public_omitted_{row_shape}.yaml"
    workflow_path.write_text(
        json.dumps(
            {
                "version": "2.0",
                "name": f"public-omitted-{row_shape}",
                "steps": [
                    {
                        "name": "GenerateList",
                        "id": "generate_list",
                        "command": ["bash", "-lc", "printf 'item\\n'"],
                        "output_capture": "lines",
                    },
                    {
                        "name": "ProcessItems",
                        "id": "process_items",
                        "for_each": {
                            "items_from": "steps.GenerateList.lines",
                            "steps": [
                                {
                                    "name": "ProcessItem",
                                    "id": "process_item",
                                    "command": ["bash", "-lc", "true"],
                                }
                            ],
                        },
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    manager = StateManager(workspace, run_id=run_id)
    state = manager.initialize(workflow_path.name)
    state.status = "completed"
    if row_shape == "supported_running_loop_result":
        presentation_key = "ProcessItems[0].ProcessItem"
        state.steps = {
            presentation_key: {
                "status": "running",
                "name": presentation_key,
            }
        }
        state.for_each = {
            "ProcessItems": {
                "items": ["item"],
                "completed_indices": [],
                "current_index": 0,
            }
        }
    else:
        presentation_key = "GenerateList"
        state.steps = {
            presentation_key: {
                "status": row_shape,
                "name": presentation_key,
            }
        }
    manager._write_state()
    return manager, presentation_key


@pytest.mark.parametrize(
    "entrypoint",
    ["resume_workflow", "default_cli"],
)
@pytest.mark.parametrize(
    "row_shape",
    ["completed", "skipped", "failed", "supported_running_loop_result"],
)
def test_public_resume_supported_omitted_step_id_is_not_backfilled(
    temp_workspace: Path,
    entrypoint: str,
    row_shape: str,
) -> None:
    run_id = f"public-omitted-{entrypoint}-{row_shape}"
    manager, presentation_key = _seed_public_omitted_step_id_state(
        temp_workspace,
        run_id=run_id,
        row_shape=row_shape,
    )
    before = json.loads(manager.state_file.read_text(encoding="utf-8"))
    assert "step_id" not in before["steps"][presentation_key]

    with patch("os.getcwd", return_value=str(temp_workspace)):
        if entrypoint == "resume_workflow":
            result = resume_workflow(run_id=run_id)
        else:
            result = cli_main(["resume", run_id])

    after = json.loads(manager.state_file.read_text(encoding="utf-8"))
    assert result == 0
    assert after == before
    assert after["status"] == "completed"
    assert "step_id" not in after["steps"][presentation_key]


@pytest.mark.parametrize(
    ("workflow_version", "schema_version", "with_reusable_call"),
    [
        ("2.0", "1.1.1", False),
        ("2.5", "2.0", True),
    ],
)
def test_projection_resume_schema_boundary_rejects_pre_v2_and_pre_2_1_call_state(
    temp_workspace: Path,
    workflow_version: str,
    schema_version: str,
    with_reusable_call: bool,
    capsys,
) -> None:
    """`resume_workflow` rejects both historical schema boundaries pre-bundle."""
    run_id = f"projection-schema-{schema_version.replace('.', '-')}"
    child_path = temp_workspace / "projection_schema_child.orc"
    child_path.write_text(
        (
            "(workflow-lisp\n"
            '  (:language "0.1")\n'
            f'  (:target-dsl "{workflow_version}")\n'
            "  (defmodule projection-schema-child))\n"
        ),
        encoding="utf-8",
    )
    workflow_path = temp_workspace / "projection_schema_root.orc"
    workflow_path.write_text(
        (
            "(workflow-lisp\n"
            '  (:language "0.1")\n'
            f'  (:target-dsl "{workflow_version}")\n'
            "  (defmodule projection-schema-root))\n"
        ),
        encoding="utf-8",
    )
    manager = StateManager(temp_workspace, run_id=run_id)
    state = manager.initialize(workflow_path.name)
    state.schema_version = schema_version
    state.status = "failed"
    if with_reusable_call:
        state.call_frames = {
            "root.invoke_child::visit::1": {
                "call_frame_id": "root.invoke_child::visit::1",
                "call_step_id": "root.invoke_child",
                "import_alias": "child",
                "status": "failed",
                "state": {"schema_version": schema_version},
            }
        }
    manager._write_state()
    before = _persisted_tree_snapshot(manager.run_root)

    with patch("os.getcwd", return_value=str(temp_workspace)), patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        side_effect=AssertionError("schema rejection must precede bundle load"),
    ), patch(
        "orchestrator.cli.commands.resume.WorkflowExecutor",
        side_effect=AssertionError("schema rejection must precede executor construction"),
    ):
        result = resume_workflow(run_id=run_id)

    captured = capsys.readouterr()
    assert result == 1
    assert "schema version" in captured.err
    assert schema_version in captured.err
    assert _persisted_tree_snapshot(manager.run_root) == before


def test_at4_resume_with_checksum_mismatch(temp_workspace, partial_run_state):
    """Test resume when workflow has been modified."""
    run_id, state_dir = partial_run_state

    # Modify the workflow file
    workflow_path = Path(json.loads((state_dir / "state.json").read_text())["workflow_file"])
    workflow_path.write_text(
        workflow_path.read_text(encoding="utf-8") + "; modified workflow\n",
        encoding="utf-8",
    )

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
    workflow_path = temp_workspace / "typed_input_workflow.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule typed_input_workflow)",
                "  (export orchestrate)",
                "  (defrecord RestartSummary",
                "    (max_cycles Int))",
                "  (defworkflow orchestrate",
                "    ((max_cycles Int))",
                "    -> RestartSummary",
                "    (record RestartSummary",
                "      :max_cycles max_cycles)))",
                "",
            ]
        ),
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
        'orchestrator.cli.commands.resume._load_resume_workflow_bundle',
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
                "  (import std/phase :only (with-phase))",
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
        lowering_route=LoweringRoute.LEGACY,
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
        'orchestrator.cli.commands.resume._load_resume_workflow_bundle',
        return_value=resume_command.ResumeWorkflowBundle(
            bundle=compatibility_projection_stripped,
            lowering_schema_version=None,
        ),
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
        'orchestrator.cli.commands.resume._load_resume_workflow_bundle',
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
    workflow_path = temp_workspace / "control_flow_resume.orc"
    workflow_content = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.15")',
            "  (defmodule control_flow_resume)",
            "  (export orchestrate)",
            "  (defrecord ResumeSummary",
            "    (status String)",
            "    (ready Bool))",
            "  (defworkflow orchestrate",
            "    ((approved Bool)",
            "     (status String))",
            "    -> ResumeSummary",
            "    (record ResumeSummary",
            "      :status status",
            "      :ready approved)))",
            "",
        ]
    )
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
        "bound_inputs": {
            "approved": False,
            "status": "pending",
        },
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
    workflow_path = temp_workspace / "custom_state_dir_resume.orc"
    workflow_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule custom_state_dir_resume)",
                "  (export orchestrate)",
                "  (defrecord ResumeSummary",
                "    (status String)",
                "    (ready Bool))",
                "  (defworkflow orchestrate",
                "    ((approved Bool)",
                "     (status String))",
                "    -> ResumeSummary",
                "    (record ResumeSummary",
                "      :status status",
                "      :ready approved)))",
                "",
            ]
        )
    )

    custom_runs_root = temp_workspace / "external-runs"
    run_id = "custom-state-dir-run"
    state_manager = StateManager(
        workspace=temp_workspace,
        run_id=run_id,
        state_dir=custom_runs_root,
    )
    state_manager.initialize(
        "custom_state_dir_resume.orc",
        bound_inputs={"approved": False, "status": "pending"},
    )
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {}
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


def test_resume_defaults_retry_settings_before_executor(temp_workspace):
    """Resume normalizes retry defaults before constructing the executor."""
    workflow_path = temp_workspace / "retry_defaults_resume.orc"
    workflow_content = "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.15")',
            "  (defmodule retry_defaults_resume)",
            "  (export orchestrate)",
            "  (defrecord ResumeSummary",
            "    (status String)",
            "    (ready Bool))",
            "  (defworkflow orchestrate",
            "    ((approved Bool)",
            "     (status String))",
            "    -> ResumeSummary",
            "    (record ResumeSummary",
            "      :status status",
            "      :ready approved)))",
            "",
        ]
    )
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
        "bound_inputs": {
            "approved": False,
            "status": "pending",
        },
        "steps": {},
    }, indent=2))

    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {},
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
    state["steps"]["Step1"] = {"status": "completed", "exit_code": 0}
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


def _provider_supervision_resume_projection(
    report_kind: str = ExecutableNodeKind.PROVIDER_SUPERVISION.value,
) -> WorkflowStateProjection:
    entry = CompatibilityNodeProjection(
        node_id="root.live",
        step_id="root.live",
        presentation_key="Live",
        display_name="Live",
        region=WorkflowRegion.BODY,
        compatibility_index=0,
        step_definition=CompatibilityStepDefinition(
            report_kind=report_kind,
        ),
    )
    return WorkflowStateProjection(
        entries_by_node_id=MappingProxyType({"root.live": entry}),
        node_id_by_compatibility_index=MappingProxyType({0: "root.live"}),
        compatibility_index_by_node_id=MappingProxyType({"root.live": 0}),
        presentation_key_by_node_id=MappingProxyType({"root.live": "Live"}),
        node_id_by_step_id=MappingProxyType({"root.live": "root.live"}),
    )


def _provider_supervision_resume_executor(
    workspace: Path,
    *,
    run_id: str,
) -> tuple[WorkflowExecutor, StateManager]:
    from orchestrator.workflow.lowering import build_loaded_workflow_bundle
    from orchestrator.workflow.surface_ast import (
        SurfaceStep,
        SurfaceStepCommonConfig,
        SurfaceStepKind,
        SurfaceWorkflow,
        WorkflowProvenance,
    )
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )

    workflow_path = workspace / f"{run_id}.orc"
    workflow_path.write_text(
        "; generated interrupted provider-supervision workflow\n",
        encoding="utf-8",
    )
    surface = SurfaceWorkflow(
        version="2.15",
        name="generated-live",
        steps=(
            SurfaceStep(
                name="Live",
                step_id="root.live",
                kind=SurfaceStepKind.PROVIDER_SUPERVISION,
                common=SurfaceStepCommonConfig(timeout_sec=60),
                provider_supervision=_provider_supervision_config(),
            ),
        ),
        provenance=WorkflowProvenance(
            workflow_path=workflow_path,
            source_root=workspace,
            frontend_kind="workflow_lisp",
        ),
    )
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(workflow_path.name)
    return (
        WorkflowExecutor(
            build_loaded_workflow_bundle(surface, imports={}),
            workspace,
            manager,
            step_heartbeat_interval_sec=0,
        ),
        manager,
    )


@pytest.mark.parametrize(
    ("persisted_result", "expected_kind"),
    [
        (
            {
                "status": "completed",
                "step_id": "root.live",
                "visit_count": 1,
                "output": "older visit",
            },
            "quarantine",
        ),
        (
            {
                "status": "completed",
                "step_id": "root.live",
                "visit_count": 2,
                "output": "exact current visit",
            },
            None,
        ),
        (
            {
                "status": "completed",
                "step_id": "root.other",
                "visit_count": 2,
                "output": "different terminal identity",
            },
            "quarantine",
        ),
    ],
)
def test_provider_supervision_resume_guard_requires_exact_visit_terminal_result(
    persisted_result: dict,
    expected_kind: str | None,
) -> None:
    state = {
        "status": "running",
        "steps": {"Live": persisted_result},
        "current_step": {
            "name": "Live",
            "index": 0,
            "type": ExecutableNodeKind.PROVIDER_SUPERVISION.value,
            "status": "running",
            "step_id": "root.live",
            "visit_count": 2,
        },
    }

    guard = ResumePlanner().detect_interrupted_provider_supervision_visit(
        state,
        projection=_provider_supervision_resume_projection(),
    )

    assert (guard or {}).get("kind") == expected_kind


@pytest.mark.parametrize("terminal_visit_count", [True, 1.0, 0, -1])
def test_provider_supervision_resume_guard_rejects_malformed_terminal_result_visit(
    terminal_visit_count: object,
) -> None:
    state = {
        "status": "running",
        "steps": {
            "Live": {
                "status": "completed",
                "step_id": "root.live",
                "visit_count": terminal_visit_count,
            },
        },
        "current_step": {
            "name": "Live",
            "index": 0,
            "type": ExecutableNodeKind.PROVIDER_SUPERVISION.value,
            "status": "running",
            "step_id": "root.live",
            "visit_count": 1,
        },
    }

    guard = ResumePlanner().detect_interrupted_provider_supervision_visit(
        state,
        projection=_provider_supervision_resume_projection(),
    )

    assert (guard or {}).get("kind") == "quarantine"


@pytest.mark.parametrize("current_visit_count", [True, 1.0, 0, -1])
def test_provider_supervision_resume_guard_rejects_invalid_current_visit(
    current_visit_count: object,
) -> None:
    state = {
        "status": "running",
        "steps": {},
        "current_step": {
            "name": "Live",
            "index": 0,
            "type": ExecutableNodeKind.PROVIDER_SUPERVISION.value,
            "status": "running",
            "step_id": "root.live",
            "visit_count": current_visit_count,
        },
    }

    guard = ResumePlanner().detect_interrupted_provider_supervision_visit(
        state,
        projection=_provider_supervision_resume_projection(),
    )

    assert (guard or {}).get("kind") == "integrity_error"


@pytest.mark.parametrize(
    ("current_type", "projected_kind"),
    [
        (
            ExecutableNodeKind.PROVIDER_SUPERVISION.value,
            ExecutableNodeKind.PROVIDER.value,
        ),
        (
            ExecutableNodeKind.PROVIDER.value,
            ExecutableNodeKind.PROVIDER_SUPERVISION.value,
        ),
    ],
)
def test_provider_supervision_resume_guard_requires_exact_projected_node_type(
    current_type: str,
    projected_kind: str,
) -> None:
    state = {
        "status": "running",
        "steps": {},
        "current_step": {
            "name": "Live",
            "index": 0,
            "type": current_type,
            "status": "running",
            "step_id": "root.live",
            "visit_count": 2,
        },
    }

    guard = ResumePlanner().detect_interrupted_provider_supervision_visit(
        state,
        projection=_provider_supervision_resume_projection(projected_kind),
    )

    assert (guard or {}).get("kind") == "integrity_error"


def test_provider_supervision_resume_guard_rejects_missing_projection_entry() -> None:
    state = {
        "status": "running",
        "steps": {},
        "current_step": {
            "name": "Missing Live",
            "index": 1,
            "type": ExecutableNodeKind.PROVIDER_SUPERVISION.value,
            "status": "running",
            "step_id": "root.missing-live",
            "visit_count": 1,
        },
    }

    guard = ResumePlanner().detect_interrupted_provider_supervision_visit(
        state,
        projection=_provider_supervision_resume_projection(),
    )

    assert (guard or {}).get("kind") == "integrity_error"


def test_provider_supervision_quarantine_atomically_clears_exact_visit_and_preserves_older_result(
    temp_workspace: Path,
) -> None:
    manager = StateManager(
        temp_workspace,
        run_id="provider-supervision-interrupted-visit",
    )
    (temp_workspace / "workflow.orc").write_text(
        "; provider-supervision quarantine fixture\n",
        encoding="utf-8",
    )
    manager.initialize("workflow.orc")
    older_result = {
        "status": "completed",
        "step_id": "root.live",
        "visit_count": 1,
        "output": "older visit remains authoritative",
    }
    assert manager.state is not None
    manager.state.status = "running"
    manager.state.steps = {"Live": dict(older_result)}
    manager.state.step_visits = {"Live": 2}
    manager.state.current_step = {
        "name": "Live",
        "index": 0,
        "type": ExecutableNodeKind.PROVIDER_SUPERVISION.value,
        "status": "running",
        "step_id": "root.live",
        "visit_count": 2,
    }
    manager._write_state()
    metadata_path = (
        manager.run_root
        / "provider-supervision"
        / "root.live"
        / "visits"
        / "2"
        / "metadata.json"
    )
    manager.write_runtime_sidecar_json(
        metadata_path,
        {
            "step_name": "Live",
            "step_id": "root.live",
            "visit_count": 2,
            "status": "running",
            "publication_state": "pending",
        },
    )
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    executor.state_manager = manager

    result = executor._quarantine_provider_supervision_resume_guard(
        manager.load().to_dict(),
        {
            "kind": "quarantine",
            "step_name": "Live",
            "step_id": "root.live",
            "visit_count": 2,
        },
    )

    persisted = manager.load()
    assert result["status"] == "failed"
    assert persisted.status == "failed"
    assert persisted.current_step is None
    assert persisted.steps["Live"] == older_result
    assert persisted.error["type"] == (
        "provider_supervision_interrupted_visit_quarantined"
    )
    assert persisted.error["context"]["step_id"] == "root.live"
    assert persisted.error["context"]["visit_count"] == 2
    assert persisted.error["context"]["metadata_path"] == str(metadata_path)
    metadata = manager.read_runtime_sidecar_json(metadata_path)
    assert metadata is not None
    assert metadata["status"] == "interrupted"
    assert metadata["publication_state"] == "quarantined_interrupted_visit"

    repeated = ResumePlanner().detect_interrupted_provider_supervision_visit(
        persisted.to_dict(),
        projection=_provider_supervision_resume_projection(),
    )
    assert repeated == {
        "kind": "existing_quarantine",
        "error": persisted.error,
    }


def test_direct_resume_quarantines_before_restart_or_launch_and_stays_sticky(
    temp_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, manager = _provider_supervision_resume_executor(
        temp_workspace,
        run_id="provider-supervision-direct-interruption",
    )
    older_result = {
        "status": "completed",
        "step_id": "root.live",
        "visit_count": 1,
        "output": "older visit remains authoritative",
    }
    assert manager.state is not None
    manager.state.status = "running"
    manager.state.steps = {"Live": dict(older_result)}
    manager.state.step_visits = {"Live": 2}
    manager.state.current_step = {
        "name": "Live",
        "index": 0,
        "type": ExecutableNodeKind.PROVIDER_SUPERVISION.value,
        "status": "running",
        "step_id": "root.live",
        "visit_count": 2,
    }
    manager._write_state()
    metadata_path = (
        manager.run_root
        / "provider-supervision"
        / "root.live"
        / "visits"
        / "2"
        / "metadata.json"
    )
    manager.write_runtime_sidecar_json(
        metadata_path,
        {
            "step_name": "Live",
            "step_id": "root.live",
            "visit_count": 2,
            "status": "running",
            "publication_state": "pending",
        },
    )
    restart_calls: list[str] = []
    provider_calls: list[str] = []

    def unexpected_restart(*_args, **_kwargs):
        restart_calls.append("restart")
        raise AssertionError("quarantine must precede restart planning")

    def unexpected_provider(*_args, **_kwargs):
        provider_calls.append("provider")
        raise AssertionError("ordinary resume must not launch a provider")

    monkeypatch.setattr(
        executor.resume_planner,
        "determine_restart_node_id",
        unexpected_restart,
    )
    monkeypatch.setattr(
        executor,
        "_execute_provider_supervision",
        unexpected_provider,
    )

    first = executor.execute(resume=True)
    after_first = manager.load()
    first_error = json.loads(json.dumps(after_first.error))

    assert first["status"] == "failed"
    assert first_error["type"] == (
        "provider_supervision_interrupted_visit_quarantined"
    )
    assert after_first.current_step is None
    assert after_first.step_visits == {"Live": 2}
    assert after_first.steps["Live"] == older_result
    assert restart_calls == []
    assert provider_calls == []

    second = executor.execute(resume=True)
    after_second = manager.load()

    assert second["status"] == "failed"
    assert after_second.error == first_error
    assert after_second.current_step is None
    assert after_second.step_visits == {"Live": 2}
    assert after_second.steps["Live"] == older_result
    assert restart_calls == []
    assert provider_calls == []


def test_resume_cli_sticky_provider_supervision_quarantine_fails_before_executor(
    temp_workspace: Path,
    sample_workflow,
) -> None:
    workflow_path, _checksum = sample_workflow
    run_id = "provider-supervision-sticky-quarantine"
    manager = StateManager(temp_workspace, run_id=run_id)
    manager.initialize(str(workflow_path))
    assert manager.state is not None
    manager.state.status = "failed"
    manager.state.error = {
        "type": "provider_supervision_interrupted_visit_quarantined",
        "message": "An interrupted provider-supervision visit was quarantined.",
        "context": {
            "step_name": "Live",
            "step_id": "root.live",
            "visit_count": 2,
            "metadata_path": "provider-supervision/root.live/visits/2/metadata.json",
        },
    }
    manager._write_state()

    with patch("os.getcwd", return_value=str(temp_workspace)), patch(
        "orchestrator.cli.commands.resume.WorkflowExecutor",
        side_effect=AssertionError("sticky quarantine must precede provider launch"),
    ) as executor:
        result = resume_workflow(run_id=run_id, force_restart=False)

    assert result == 1
    executor.assert_not_called()
