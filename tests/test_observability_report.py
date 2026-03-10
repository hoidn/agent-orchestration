"""Tests for deterministic workflow status reporting."""

from dataclasses import replace

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.observability.report import build_status_snapshot, render_status_markdown


def _sample_workflow():
    return {
        "version": "1.3",
        "name": "obs-test",
        "steps": [
            {
                "name": "Prep",
                "command": ["bash", "-lc", "echo prep"],
                "consumes": [{"artifact": "plan_doc", "as": "plan"}],
            },
            {
                "name": "DraftPlan",
                "provider": "codex",
                "expected_outputs": [
                    {"name": "plan_path", "path": "state/plan_path.txt", "type": "path"}
                ],
            },
        ],
    }


def test_snapshot_counts_and_infers_running_from_prompt_audit(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    logs = run_root / "logs"
    logs.mkdir(parents=True)
    (logs / "DraftPlan.prompt.txt").write_text("Resolved prompt content")

    state = {
        "run_id": "run1",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Prep": {
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 31,
                "output": "prep done",
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)

    assert snapshot["progress"]["total"] == 2
    assert snapshot["progress"]["completed"] == 1
    assert snapshot["progress"]["running"] == 1
    assert snapshot["progress"]["pending"] == 0

    steps = {s["name"]: s for s in snapshot["steps"]}
    assert steps["DraftPlan"]["status"] == "running"
    assert "Resolved prompt content" in steps["DraftPlan"]["input"]["prompt"]


def test_snapshot_contains_command_input_and_output_summary(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run2"
    (run_root / "logs").mkdir(parents=True)

    state = {
        "run_id": "run2",
        "status": "failed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Prep": {
                "status": "failed",
                "exit_code": 1,
                "duration_ms": 11,
                "output": "x" * 250,
                "artifacts": {"log_path": "artifacts/log.txt"},
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)
    prep = snapshot["steps"][0]

    assert prep["input"]["command"] == ["bash", "-lc", "echo prep"]
    assert prep["output"]["exit_code"] == 1
    assert prep["output"]["duration_ms"] == 11
    assert prep["output"]["artifacts"]["log_path"] == "artifacts/log.txt"
    assert len(prep["output"]["output_preview"]) < 250


def test_snapshot_surfaces_normalized_outcome_fields(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-outcome"
    (run_root / "logs").mkdir(parents=True)

    state = {
        "run_id": "run-outcome",
        "status": "failed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Prep": {
                "status": "failed",
                "exit_code": 3,
                "duration_ms": 0,
                "error": {"type": "assert_failed", "message": "Assertion failed"},
                "outcome": {
                    "status": "failed",
                    "phase": "execution",
                    "class": "assert_failed",
                    "retryable": False,
                },
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)
    prep = snapshot["steps"][0]

    assert prep["output"]["outcome"] == {
        "status": "failed",
        "phase": "execution",
        "class": "assert_failed",
        "retryable": False,
    }


def test_snapshot_marks_completed_for_each_summary_as_completed(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-loop"
    (run_root / "logs").mkdir(parents=True)

    workflow = {
        "version": "1.3",
        "name": "obs-loop",
        "steps": [
            {
                "name": "Loop",
                "for_each": {
                    "items": ["one", "two"],
                    "steps": [
                        {
                            "name": "Inner",
                            "command": ["bash", "-lc", "echo inner"],
                        }
                    ],
                },
            }
        ],
    }
    state = {
        "run_id": "run-loop",
        "status": "completed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Loop": [
                {"Inner": {"status": "completed", "exit_code": 0}},
                {"Inner": {"status": "completed", "exit_code": 0}},
            ]
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)

    assert snapshot["steps"][0]["status"] == "completed"
    assert snapshot["progress"]["running"] == 0
    assert snapshot["progress"]["completed"] == 1


def test_markdown_renderer_emits_human_readable_status(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run3"
    logs = run_root / "logs"
    logs.mkdir(parents=True)
    (logs / "DraftPlan.prompt.txt").write_text("Prompt body")

    state = {
        "run_id": "run3",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {},
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)
    md = render_status_markdown(snapshot)

    assert "# Workflow Status" in md
    assert "run3" in md
    assert "DraftPlan" in md
    assert "Prompt body" in md
    assert "Progress" in md


def test_snapshot_recognizes_call_steps(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "call-run"
    (run_root / "logs").mkdir(parents=True)

    workflow = {
        "version": "2.5",
        "name": "obs-call",
        "steps": [
            {
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            }
        ],
    }
    state = {
        "run_id": "call-run",
        "status": "completed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "RunReviewLoop": {
                "status": "completed",
                "exit_code": 0,
                "artifacts": {"approved": True},
                "debug": {
                    "call": {
                        "call_frame_id": "root.run_review_loop::visit::1",
                        "import_alias": "review_loop",
                        "workflow_file": "workflows/library/review_fix_loop.yaml",
                        "export_status": "completed",
                    }
                },
            }
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)

    assert snapshot["steps"][0]["kind"] == "call"
    assert snapshot["steps"][0]["output"]["call"]["call_frame_id"] == "root.run_review_loop::visit::1"


def test_snapshot_accepts_loaded_bundle_and_uses_projection_ordering(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "bundle-run"
    (run_root / "logs").mkdir(parents=True)

    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.10",
                "name": "bundle-report",
                "artifacts": {
                    "ready": {"kind": "scalar", "type": "bool"},
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
                                    "command": ["bash", "-lc", "printf 'approved\\n'"],
                                }
                            ],
                        },
                        "else": {
                            "id": "revise_path",
                            "steps": [
                                {
                                    "name": "WriteRevision",
                                    "id": "write_revision",
                                    "command": ["bash", "-lc", "printf 'revise\\n'"],
                                }
                            ],
                        },
                    },
                ],
                "finally": {
                    "id": "cleanup",
                    "steps": [
                        {
                            "name": "WriteCleanupMarker",
                            "id": "write_cleanup_marker",
                            "command": ["bash", "-lc", "printf 'cleanup\\n'"],
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    snapshot = build_status_snapshot(
        bundle,
        {
            "run_id": "bundle-run",
            "status": "running",
            "started_at": "2026-02-27T00:00:00+00:00",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "workflow_file": str(workflow_path),
            "steps": {
                "SetReady": {
                    "status": "completed",
                    "step_id": "root.set_ready",
                    "exit_code": 0,
                }
            },
        },
        run_root,
    )

    assert [step["name"] for step in snapshot["steps"]] == [
        bundle.projection.presentation_key_by_node_id[node_id]
        for node_id in bundle.ir.body_region + bundle.ir.finalization_region
    ]
    assert snapshot["steps"][1]["kind"] == "structured_if_branch"
    assert snapshot["steps"][-1]["kind"] == "finally"


def test_snapshot_uses_projection_execution_order_when_ir_and_projection_order_diverge(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "bundle-projection-order"
    (run_root / "logs").mkdir(parents=True)

    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.10",
                "name": "bundle-projection-order",
                "steps": [
                    {
                        "name": "WriteOne",
                        "id": "write_one",
                        "command": ["bash", "-lc", "printf 'one\\n'"],
                    },
                    {
                        "name": "WriteTwo",
                        "id": "write_two",
                        "command": ["bash", "-lc", "printf 'two\\n'"],
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    original_node_ids = tuple(bundle.ir.body_region)
    reversed_node_ids = tuple(reversed(original_node_ids))
    mutated_projection = replace(
        bundle.projection,
        node_id_by_compatibility_index={
            index: node_id for index, node_id in enumerate(reversed_node_ids)
        },
        compatibility_index_by_node_id={
            node_id: index for index, node_id in enumerate(reversed_node_ids)
        },
    )
    mutated_bundle = replace(bundle, projection=mutated_projection)

    snapshot = build_status_snapshot(
        mutated_bundle,
        {
            "run_id": "bundle-projection-order",
            "status": "running",
            "started_at": "2026-03-10T00:00:00+00:00",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "workflow_file": str(workflow_path),
            "steps": {},
        },
        run_root,
    )

    assert [step["name"] for step in snapshot["steps"]] == [
        mutated_bundle.projection.presentation_key_by_node_id[node_id]
        for node_id in mutated_bundle.projection.ordered_execution_node_ids()
    ]
    assert [step["name"] for step in snapshot["steps"]] != [
        mutated_bundle.projection.presentation_key_by_node_id[node_id]
        for node_id in original_node_ids
    ]


def test_snapshot_uses_ir_node_metadata_when_bundle_legacy_steps_are_missing(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "bundle-ir-metadata"
    (run_root / "logs").mkdir(parents=True)

    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.10",
                "name": "bundle-ir-metadata",
                "steps": [
                    {
                        "name": "GenerateReport",
                        "id": "generate_report",
                        "command": ["bash", "-lc", "echo report"],
                        "consumes": [{"artifact": "plan_doc", "as": "plan"}],
                        "expected_outputs": [
                            {
                                "name": "report_path",
                                "path": "state/report_path.txt",
                                "type": "string",
                            }
                        ],
                    }
                ],
                "finally": {
                    "id": "cleanup",
                    "steps": [
                        {
                            "name": "Cleanup",
                            "id": "cleanup_step",
                            "command": ["bash", "-lc", "echo cleanup"],
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    bundle.legacy_workflow["steps"] = []
    bundle.legacy_workflow["finally"]["steps"] = []

    snapshot = build_status_snapshot(
        bundle,
        {
            "run_id": "bundle-ir-metadata",
            "status": "running",
            "started_at": "2026-03-10T00:00:00+00:00",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "workflow_file": str(workflow_path),
            "steps": {
                "GenerateReport": {
                    "status": "completed",
                    "step_id": "root.generate_report",
                    "exit_code": 0,
                }
            },
        },
        run_root,
    )

    assert [step["name"] for step in snapshot["steps"]] == [
        bundle.projection.presentation_key_by_node_id[node_id]
        for node_id in bundle.ir.body_region + bundle.ir.finalization_region
    ]
    steps = {step["name"]: step for step in snapshot["steps"]}
    assert steps["GenerateReport"]["input"]["command"] == ["bash", "-lc", "echo report"]
    assert steps["GenerateReport"]["consumes"] == [{"artifact": "plan_doc", "as": "plan"}]
    assert steps["GenerateReport"]["expected_outputs"] == [
        {
            "name": "report_path",
            "path": "state/report_path.txt",
            "type": "string",
        }
    ]
    assert steps["finally.Cleanup"]["kind"] == "finally"


def test_snapshot_uses_projection_metadata_when_bundle_ir_raw_and_legacy_steps_are_missing(
    tmp_path: Path,
):
    run_root = tmp_path / ".orchestrate" / "runs" / "bundle-projection-metadata"
    (run_root / "logs").mkdir(parents=True)

    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.10",
                "name": "bundle-projection-metadata",
                "steps": [
                    {
                        "name": "GenerateReport",
                        "id": "generate_report",
                        "command": ["bash", "-lc", "echo report"],
                        "consumes": [{"artifact": "plan_doc", "as": "plan"}],
                        "expected_outputs": [
                            {
                                "name": "report_path",
                                "path": "state/report_path.txt",
                                "type": "string",
                            }
                        ],
                    }
                ],
                "finally": {
                    "id": "cleanup",
                    "steps": [
                        {
                            "name": "Cleanup",
                            "id": "cleanup_step",
                            "command": ["bash", "-lc", "echo cleanup"],
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    bundle.legacy_workflow["steps"] = []
    bundle.legacy_workflow["finally"]["steps"] = []
    mutated_nodes = {
        node_id: replace(node, raw=MappingProxyType({}))
        for node_id, node in bundle.ir.nodes.items()
    }
    mutated_bundle = replace(
        bundle,
        ir=replace(bundle.ir, nodes=MappingProxyType(mutated_nodes)),
    )

    snapshot = build_status_snapshot(
        mutated_bundle,
        {
            "run_id": "bundle-projection-metadata",
            "status": "running",
            "started_at": "2026-03-10T00:00:00+00:00",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "workflow_file": str(workflow_path),
            "steps": {
                "GenerateReport": {
                    "status": "completed",
                    "step_id": "root.generate_report",
                    "exit_code": 0,
                }
            },
        },
        run_root,
    )

    steps = {step["name"]: step for step in snapshot["steps"]}
    assert steps["GenerateReport"]["input"]["command"] == ["bash", "-lc", "echo report"]
    assert steps["GenerateReport"]["consumes"] == [{"artifact": "plan_doc", "as": "plan"}]
    assert steps["GenerateReport"]["expected_outputs"] == [
        {
            "name": "report_path",
            "path": "state/report_path.txt",
            "type": "string",
        }
    ]
    assert steps["finally.Cleanup"]["kind"] == "finally"


def test_snapshot_resolves_current_step_from_projection_step_id(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "bundle-current-step"
    (run_root / "logs").mkdir(parents=True)

    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.7",
                "name": "bundle-report-current-step",
                "artifacts": {
                    "ready": {"kind": "scalar", "type": "bool"},
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
                                    "command": ["bash", "-lc", "printf 'approved\\n'"],
                                }
                            ],
                        },
                        "else": {
                            "id": "revise_path",
                            "steps": [
                                {
                                    "name": "WriteRevision",
                                    "id": "write_revision",
                                    "command": ["bash", "-lc", "printf 'revise\\n'"],
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
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    snapshot = build_status_snapshot(
        bundle,
        {
            "run_id": "bundle-current-step",
            "status": "running",
            "started_at": "2026-02-27T00:00:00+00:00",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "workflow_file": str(workflow_path),
            "current_step": {
                "name": "SetReady",
                "index": 0,
                "status": "running",
                "step_id": "root.route_ready",
            },
            "steps": {
                "SetReady": {
                    "status": "completed",
                    "step_id": "root.set_ready",
                    "exit_code": 0,
                }
            },
        },
        run_root,
    )

    steps = {step["name"]: step for step in snapshot["steps"]}
    assert steps["SetReady"]["status"] == "completed"
    assert steps["RouteReady"]["status"] == "running"


def test_snapshot_recognizes_repeat_until_steps(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "repeat-run"
    (run_root / "logs").mkdir(parents=True)

    workflow = {
        "version": "2.7",
        "name": "obs-repeat",
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
                            "left": {"ref": "self.outputs.review_decision"},
                            "op": "eq",
                            "right": "APPROVE",
                        }
                    },
                    "max_iterations": 4,
                    "steps": [
                        {
                            "name": "WriteDecision",
                            "command": ["bash", "-lc", "echo APPROVE"],
                        }
                    ],
                },
            }
        ],
    }
    state = {
        "run_id": "repeat-run",
        "status": "completed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "ReviewLoop": {
                "status": "completed",
                "step_id": "root.review_loop",
                "artifacts": {"review_decision": "APPROVE"},
                "debug": {
                    "structured_repeat_until": {
                        "completed_iterations": [0, 1, 2],
                        "current_iteration": 2,
                        "condition_evaluated_for_iteration": 2,
                        "last_condition_result": True,
                    }
                },
            }
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)

    assert snapshot["steps"][0]["kind"] == "repeat_until"
    assert snapshot["steps"][0]["status"] == "completed"
    assert snapshot["steps"][0]["output"]["artifacts"] == {"review_decision": "APPROVE"}


def test_snapshot_exposes_repeat_until_debug_progress_and_markdown(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "repeat-progress-run"
    (run_root / "logs").mkdir(parents=True)

    workflow = {
        "version": "2.7",
        "name": "obs-repeat-progress",
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
                            "left": {"ref": "self.outputs.review_decision"},
                            "op": "eq",
                            "right": "APPROVE",
                        }
                    },
                    "max_iterations": 4,
                    "steps": [
                        {
                            "name": "WriteDecision",
                            "command": ["bash", "-lc", "echo REVISE"],
                        }
                    ],
                },
            }
        ],
    }
    state = {
        "run_id": "repeat-progress-run",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_file": "workflows/test.yaml",
        "current_step": {
            "name": "ReviewLoop",
            "status": "running",
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        },
        "steps": {
            "ReviewLoop": {
                "status": "running",
                "step_id": "root.review_loop",
                "artifacts": {"review_decision": "REVISE"},
                "debug": {
                    "structured_repeat_until": {
                        "body_id": "iteration_body",
                        "max_iterations": 4,
                        "completed_iterations": [0],
                        "current_iteration": 1,
                        "condition_evaluated_for_iteration": None,
                        "last_condition_result": None,
                    }
                },
            }
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)
    review_loop = snapshot["steps"][0]
    markdown = render_status_markdown(snapshot)

    assert review_loop["output"]["debug"]["structured_repeat_until"] == {
        "body_id": "iteration_body",
        "max_iterations": 4,
        "completed_iterations": [0],
        "current_iteration": 1,
        "condition_evaluated_for_iteration": None,
        "last_condition_result": None,
    }
    assert "structured_repeat_until" in markdown
    assert "current_iteration" in markdown
    assert "completed_iterations" in markdown


def test_snapshot_marks_stale_running_without_current_step_as_failed(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "stale-run"
    (run_root / "logs").mkdir(parents=True)

    stale_updated_at = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    state = {
        "run_id": "stale-run",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": stale_updated_at,
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Prep": {
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 31,
                "output": "prep done",
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)

    assert snapshot["run"]["status"] == "failed"
    assert snapshot["run"]["status_reason"] == "stale_running_without_current_step"


def test_snapshot_surfaces_provider_session_quarantine_and_metadata_paths(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-session"
    (run_root / "logs").mkdir(parents=True)
    metadata_path = run_root / "provider_sessions" / "root.askprovider__v1.json"
    transport_spool_path = run_root / "provider_sessions" / "root.askprovider__v1.transport.log"

    workflow = {
        "version": "2.10",
        "name": "obs-provider-session",
        "steps": [
            {
                "name": "AskProvider",
                "provider": "codex",
                "provider_session": {
                    "mode": "fresh",
                    "publish_artifact": "implementation_session_id",
                },
            }
        ],
    }
    state = {
        "run_id": "run-session",
        "status": "failed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "error": {
            "type": "provider_session_interrupted_visit_quarantined",
            "message": "An interrupted provider-session visit was quarantined.",
            "context": {
                "metadata_path": str(metadata_path),
                "transport_spool_path": str(transport_spool_path),
            },
        },
        "steps": {
            "AskProvider": {
                "status": "failed",
                "exit_code": 2,
                "debug": {
                    "provider_session": {
                        "mode": "fresh",
                        "session_id": "sess-123",
                        "metadata_path": str(metadata_path),
                        "publication_state": "suppressed_failure",
                    }
                },
            }
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)
    md = render_status_markdown(snapshot)

    assert snapshot["run"]["error"]["type"] == "provider_session_interrupted_visit_quarantined"
    assert snapshot["steps"][0]["output"]["provider_session"]["metadata_path"] == str(metadata_path)
    assert "provider_session_interrupted_visit_quarantined" in md
    assert str(metadata_path) in md


def test_snapshot_exposes_looped_resume_current_and_last_completed_visit_counts(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "looped-resume"
    (run_root / "logs").mkdir(parents=True)

    state = {
        "run_id": "looped-resume",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_file": "workflows/test.yaml",
        "step_visits": {"Prep": 2},
        "current_step": {
            "name": "Prep",
            "status": "running",
            "visit_count": 2,
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        },
        "steps": {
            "Prep": {
                "status": "completed",
                "visit_count": 1,
                "exit_code": 0,
                "duration_ms": 31,
                "output": "prep done",
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)
    prep = snapshot["steps"][0]

    assert snapshot["run"]["status"] == "running"
    assert prep["visit_count"] == 2
    assert prep["current_visit_count"] == 2


def test_snapshot_includes_finalization_progress_and_steps(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-finally"
    (run_root / "logs").mkdir(parents=True)

    workflow = {
        "version": "2.3",
        "name": "obs-finally",
        "steps": [
            {
                "name": "Body",
                "command": ["bash", "-lc", "echo body"],
            }
        ],
        "finally": {
            "token": "cleanup",
            "steps": [
                {
                    "name": "finally.ReleaseLock",
                    "command": ["bash", "-lc", "echo cleanup"],
                    "workflow_finalization": {"block_id": "cleanup"},
                }
            ],
        },
    }
    state = {
        "run_id": "run-finally",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_file": "workflows/test.yaml",
        "current_step": {
            "name": "finally.ReleaseLock",
            "status": "running",
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        },
        "finalization": {
            "block_id": "cleanup",
            "status": "running",
            "body_status": "completed",
            "current_index": 0,
            "completed_indices": [],
            "workflow_outputs_status": "pending",
        },
        "steps": {
            "Body": {
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 12,
            }
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)

    assert snapshot["run"]["finalization"]["status"] == "running"
    steps = {entry["name"]: entry for entry in snapshot["steps"]}
    assert steps["finally.ReleaseLock"]["kind"] == "finally"
    assert steps["finally.ReleaseLock"]["status"] == "running"


def test_snapshot_includes_structured_helper_node_kinds(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-structured"
    (run_root / "logs").mkdir(parents=True)

    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.6",
                "name": "obs-structured",
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
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    workflow = WorkflowLoader(tmp_path).load(workflow_path)

    state = {
        "run_id": "run-structured",
        "status": "running",
        "started_at": "2026-03-10T00:00:00+00:00",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_file": "workflow.yaml",
        "current_step": {
            "name": "RouteDecision.REVISE",
            "status": "running",
            "visit_count": 1,
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        },
        "steps": {
            "SetReady": {"status": "completed", "artifacts": {"ready": True}},
            "RouteReady.then": {"status": "completed"},
            "RouteReady.then.WriteApproved": {
                "status": "completed",
                "artifacts": {"decision": "APPROVE"},
            },
            "RouteReady.else": {"status": "skipped"},
            "RouteReady.else.WriteRevision": {"status": "skipped"},
            "RouteReady": {"status": "completed", "artifacts": {"decision": "APPROVE"}},
            "RouteDecision.APPROVE": {"status": "skipped"},
            "RouteDecision.APPROVE.EchoApproved": {"status": "skipped"},
            "RouteDecision.REVISE": {"status": "running"},
            "RouteDecision.REVISE.EchoRevision": {"status": "pending"},
            "RouteDecision": {"status": "pending"},
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)
    steps = {entry["name"]: entry for entry in snapshot["steps"]}

    assert steps["RouteReady.then"]["kind"] == "structured_if_branch"
    assert steps["RouteReady"]["kind"] == "structured_if_join"
    assert steps["RouteDecision.APPROVE"]["kind"] == "structured_match_case"
    assert steps["RouteDecision"]["kind"] == "structured_match_join"
    assert steps["RouteDecision.REVISE"]["status"] == "running"
    assert steps["RouteDecision.REVISE"]["current_visit_count"] == 1
