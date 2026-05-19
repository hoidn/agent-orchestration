"""Targeted tests for the internal Phase 1 v2.14 runtime semantics tranche."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _enable_v214_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    version_order = list(WorkflowLoader.VERSION_ORDER)
    if "2.14" not in version_order:
        version_order.append("2.14")
    monkeypatch.setattr(
        WorkflowLoader,
        "SUPPORTED_VERSIONS",
        WorkflowLoader.SUPPORTED_VERSIONS | {"2.14"},
    )
    monkeypatch.setattr(
        WorkflowLoader,
        "VERSION_ORDER",
        version_order,
    )


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return workflow_file


def _load_executor(
    workspace: Path,
    workflow: dict,
    *,
    bound_inputs: dict | None = None,
    run_id: str = "test-run",
) -> WorkflowExecutor:
    workflow_file = _write_workflow(workspace, workflow)
    loaded = WorkflowLoader(workspace).load(workflow_file)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize("workflow.yaml", bound_inputs=bound_inputs or {})
    return WorkflowExecutor(loaded, workspace, state_manager, retry_delay_ms=0)


def test_materialize_artifacts_writes_pointer_and_publishes_relpath_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """materialize_artifacts should expose the typed value, write its pointer, and publish it."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "approved-plan.md").write_text("# approved\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "materialize-input",
        "inputs": {
            "design_path": {
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            }
        },
        "artifacts": {
            "design": {
                "kind": "relpath",
                "type": "relpath",
                "pointer": "state/design_path.txt",
                "under": "docs/plans",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "MaterializeDesign",
                "id": "materialize_design",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "design_path",
                            "source": {"input": "design_path"},
                            "contract": {"inherit": "source"},
                            "pointer": {"path": "state/design_path.txt"},
                        }
                    ]
                },
                "publishes": [{"artifact": "design", "from": "design_path"}],
            }
        ],
    }

    executor = _load_executor(
        tmp_path,
        workflow,
        bound_inputs={"design_path": "docs/plans/approved-plan.md"},
    )
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["MaterializeDesign"]["artifacts"] == {
        "design_path": "docs/plans/approved-plan.md",
    }
    assert (tmp_path / "state" / "design_path.txt").read_text(encoding="utf-8") == "docs/plans/approved-plan.md\n"
    assert state["artifact_versions"]["design"][0]["value"] == "docs/plans/approved-plan.md"


def test_materialize_artifacts_publish_writes_canonical_top_level_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing a relpath materialization must maintain the canonical top-level pointer file."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "approved-plan.md").write_text("# approved\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "materialize-canonical-pointer",
        "inputs": {
            "design_path": {
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            }
        },
        "artifacts": {
            "design": {
                "kind": "relpath",
                "type": "relpath",
                "pointer": "state/canonical_design.txt",
                "under": "docs/plans",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "MaterializeDesign",
                "id": "materialize_design",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "design_path",
                            "source": {"input": "design_path"},
                            "contract": {"inherit": "source"},
                        }
                    ]
                },
                "publishes": [{"artifact": "design", "from": "design_path"}],
            }
        ],
    }

    executor = _load_executor(
        tmp_path,
        workflow,
        bound_inputs={"design_path": "docs/plans/approved-plan.md"},
    )
    state = executor.execute()

    assert state["status"] == "completed"
    assert (tmp_path / "state" / "canonical_design.txt").read_text(encoding="utf-8") == (
        "docs/plans/approved-plan.md\n"
    )
    assert state["artifact_versions"]["design"][0]["value"] == "docs/plans/approved-plan.md"


def test_materialize_artifacts_substitutes_pointer_path_templates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """materialize_artifacts pointer paths should resolve runtime templates before writing."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "approved-plan.md").write_text("# approved\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "materialize-template-pointer",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
            },
            "design_path": {
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            },
        },
        "steps": [
            {
                "name": "MaterializeDesign",
                "id": "materialize_design",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "design_path",
                            "source": {"input": "design_path"},
                            "contract": {"inherit": "source"},
                            "pointer": {"path": "${inputs.state_root}/design_path.txt"},
                        }
                    ]
                },
            }
        ],
    }

    executor = _load_executor(
        tmp_path,
        workflow,
        bound_inputs={
            "state_root": "state/oracle",
            "design_path": "docs/plans/approved-plan.md",
        },
    )
    state = executor.execute()

    assert state["status"] == "completed"
    assert (tmp_path / "state" / "oracle" / "design_path.txt").read_text(encoding="utf-8") == (
        "docs/plans/approved-plan.md\n"
    )
    assert not (tmp_path / "${inputs.state_root}").exists()


def test_materialize_artifacts_publish_substitutes_registry_pointer_templates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing a materialized relpath should substitute artifact registry pointer templates too."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "approved-plan.md").write_text("# approved\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "materialize-template-publish-pointer",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
            },
            "design_path": {
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            },
        },
        "artifacts": {
            "design": {
                "kind": "relpath",
                "type": "relpath",
                "pointer": "${inputs.state_root}/design_path.txt",
                "under": "docs/plans",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "MaterializeDesign",
                "id": "materialize_design",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "design_path",
                            "source": {"input": "design_path"},
                            "contract": {"inherit": "source"},
                            "pointer": {"path": "${inputs.state_root}/design_path.txt"},
                        }
                    ]
                },
                "publishes": [{"artifact": "design", "from": "design_path"}],
            }
        ],
    }

    executor = _load_executor(
        tmp_path,
        workflow,
        bound_inputs={
            "state_root": "state/oracle",
            "design_path": "docs/plans/approved-plan.md",
        },
    )
    state = executor.execute()

    assert state["status"] == "completed"
    assert (tmp_path / "state" / "oracle" / "design_path.txt").read_text(encoding="utf-8") == (
        "docs/plans/approved-plan.md\n"
    )
    assert state["artifact_versions"]["design"][0]["value"] == "docs/plans/approved-plan.md"
    assert not (tmp_path / "${inputs.state_root}").exists()


def test_materialize_artifacts_input_values_write_the_same_pointers_as_long_form(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """input_values should expand to the same runtime behavior as long-form values."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "approved-plan.md").write_text("# approved\n", encoding="utf-8")
    (tmp_path / "docs" / "steering.md").write_text("# steering\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "materialize-input-values-runtime",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
            },
            "steering_path": {
                "type": "relpath",
                "under": "docs",
                "must_exist_target": True,
            },
            "design_path": {
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            },
        },
        "steps": [
            {
                "name": "MaterializeInputs",
                "id": "materialize_inputs",
                "materialize_artifacts": {
                    "input_values": [
                        {
                            "names": ["steering_path", "design_path"],
                            "contract": "inherit",
                            "pointer_template": "${inputs.state_root}/{name}.txt",
                        }
                    ]
                },
            }
        ],
    }

    executor = _load_executor(
        tmp_path,
        workflow,
        bound_inputs={
            "state_root": "state/oracle",
            "steering_path": "docs/steering.md",
            "design_path": "docs/plans/approved-plan.md",
        },
    )
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["MaterializeInputs"]["artifacts"] == {
        "steering_path": "docs/steering.md",
        "design_path": "docs/plans/approved-plan.md",
    }
    assert (tmp_path / "state" / "oracle" / "steering_path.txt").read_text(encoding="utf-8") == "docs/steering.md\n"
    assert (tmp_path / "state" / "oracle" / "design_path.txt").read_text(encoding="utf-8") == (
        "docs/plans/approved-plan.md\n"
    )
    assert not (tmp_path / "${inputs.state_root}").exists()


def test_variant_output_shared_fields_are_available_without_variant_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared tagged-union fields should not require variant proof to consume downstream."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "approved-plan.md").write_text("# approved\n", encoding="utf-8")
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "execution_report.md").write_text("# report\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "variant-shared-fields-runtime",
        "steps": [
            {
                "name": "EmitVariantBundle",
                "id": "emit_variant_bundle",
                "command": [
                    "python",
                    "-c",
                    (
                        "import json\n"
                        "from pathlib import Path\n"
                        "path = Path('state/variant_bundle.json')\n"
                        "path.parent.mkdir(parents=True, exist_ok=True)\n"
                        "path.write_text(json.dumps({"
                        "'implementation_state': 'COMPLETED', "
                        "'plan_path': 'docs/plans/approved-plan.md', "
                        "'execution_report_path': 'artifacts/work/execution_report.md'"
                        "}) + '\\n', encoding='utf-8')\n"
                    ),
                ],
                "variant_output": {
                    "path": "state/variant_bundle.json",
                    "discriminant": {
                        "name": "implementation_state",
                        "json_pointer": "/implementation_state",
                        "type": "enum",
                        "allowed": ["COMPLETED", "BLOCKED"],
                    },
                    "shared_fields": [
                        {
                            "name": "plan_path",
                            "json_pointer": "/plan_path",
                            "type": "relpath",
                            "under": "docs/plans",
                            "must_exist_target": True,
                        }
                    ],
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
                },
            },
            {
                "name": "MaterializePlanPath",
                "id": "materialize_plan_path",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "plan_path_copy",
                            "source": {"ref": "root.steps.EmitVariantBundle.artifacts.plan_path"},
                            "contract": {
                                "type": "relpath",
                                "under": "docs/plans",
                                "must_exist_target": True,
                            },
                            "pointer": {"path": "state/plan_path_copy.txt"},
                        }
                    ]
                },
            },
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["MaterializePlanPath"]["artifacts"] == {
        "plan_path_copy": "docs/plans/approved-plan.md",
    }
    assert (tmp_path / "state" / "plan_path_copy.txt").read_text(encoding="utf-8") == (
        "docs/plans/approved-plan.md\n"
    )


def test_pre_snapshot_and_select_variant_output_choose_the_single_changed_implementation_state_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pre_snapshot plus select_variant_output should select and commit the single changed candidate."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "snapshot-select",
        "steps": [
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
                "name": "ExecuteImplementation",
                "id": "execute_implementation",
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
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "path = Path('artifacts/work/execution_report.md')\n"
                        "path.parent.mkdir(parents=True, exist_ok=True)\n"
                        "path.write_text('# Execution Report\\n', encoding='utf-8')\n"
                    ),
                ],
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
                            "ref": "root.steps.ExecuteImplementation.snapshots.implementation_outcome_before",
                        },
                    },
                },
            },
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["ExecuteImplementation"]["snapshots"]["implementation_outcome_before"]["schema"] == "snapshot_diff/v1"
    assert state["steps"]["SelectImplementationOutcome"]["artifacts"] == {
        "implementation_state": "COMPLETED",
        "execution_report_path": "artifacts/work/execution_report.md",
    }
    bundle = json.loads((tmp_path / "state" / "implementation_state.json").read_text(encoding="utf-8"))
    assert bundle == {
        "implementation_state": "COMPLETED",
        "execution_report_path": "artifacts/work/execution_report.md",
    }


def test_select_variant_output_substitutes_bundle_path_templates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """select_variant_output should resolve its bundle path template before committing output."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "snapshot-select-template-path",
        "inputs": {
            "state_root": {
                "type": "relpath",
                "under": "state",
            }
        },
        "steps": [
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
                        },
                        {
                            "name": "progress_report_target_path",
                            "source": {"literal": "artifacts/work/progress_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                        },
                    ]
                },
            },
            {
                "name": "ExecuteImplementation",
                "id": "execute_implementation",
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
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "path = Path('artifacts/work/execution_report.md')\n"
                        "path.parent.mkdir(parents=True, exist_ok=True)\n"
                        "path.write_text('# Execution Report\\n', encoding='utf-8')\n"
                    ),
                ],
            },
            {
                "name": "SelectImplementationOutcome",
                "id": "select_implementation_outcome",
                "select_variant_output": {
                    "path": "${inputs.state_root}/implementation_state.json",
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
                            "ref": "root.steps.ExecuteImplementation.snapshots.implementation_outcome_before",
                        },
                    },
                },
            },
        ],
    }

    executor = _load_executor(
        tmp_path,
        workflow,
        bound_inputs={"state_root": "state/oracle"},
    )
    state = executor.execute()

    assert state["status"] == "completed"
    assert (tmp_path / "state" / "oracle" / "implementation_state.json").is_file()
    assert not (tmp_path / "${inputs.state_root}").exists()


def test_select_variant_output_rejects_runtime_snapshot_metadata_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """select_variant_output must reject snapshot state that is not snapshot_diff/sha256."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "snapshot-metadata-mismatch",
        "steps": [
            {
                "name": "MaterializeTargets",
                "id": "materialize_targets",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "placeholder_path",
                            "source": {"literal": "artifacts/work/execution_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                        }
                    ]
                },
            },
            {
                "name": "CaptureBefore",
                "id": "capture_before",
                "pre_snapshot": {
                    "name": "before",
                    "digest": "sha256",
                    "candidates": {
                        "COMPLETED": {
                            "ref": "root.steps.MaterializeTargets.artifacts.placeholder_path",
                        }
                    },
                },
                "command": ["echo", "ok"],
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
                        "allowed": ["COMPLETED"],
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
                        }
                    },
                    "evidence": {
                        "mode": "snapshot_diff",
                        "snapshot": {
                            "ref": "root.steps.CaptureBefore.snapshots.before",
                        },
                    },
                },
            }
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    state = executor.state_manager.load().to_dict()
    state["steps"] = {
        "CaptureBefore": {
            "snapshots": {
                "before": {
                    "schema": "snapshot_diff/v1",
                    "digest": "md5",
                    "captured_at": "pre_step",
                    "candidate_keys": ["COMPLETED"],
                    "candidates": {
                        "COMPLETED": {
                            "path": "artifacts/work/execution_report.md",
                            "exists": False,
                            "size": None,
                            "sha256": None,
                            "mtime_ns": None,
                        }
                    },
                }
            }
        }
    }

    result = executor._execute_select_variant_output(workflow["steps"][2], state)

    assert result["status"] == "failed"
    assert result["error"]["type"] == "snapshot_ref_not_snapshot_diff"


def test_select_variant_output_rejects_sidecar_snapshot_without_recorded_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume-time sidecar snapshots must carry a recorded hash for integrity verification."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "snapshot-sidecar-missing-hash",
        "steps": [
            {
                "name": "MaterializeTargets",
                "id": "materialize_targets",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "placeholder_path",
                            "source": {"literal": "artifacts/work/execution_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                        }
                    ]
                },
            },
            {
                "name": "CaptureBefore",
                "id": "capture_before",
                "pre_snapshot": {
                    "name": "before",
                    "digest": "sha256",
                    "candidates": {
                        "COMPLETED": {
                            "ref": "root.steps.MaterializeTargets.artifacts.placeholder_path",
                        }
                    },
                },
                "command": ["echo", "ok"],
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
                        "allowed": ["COMPLETED"],
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
                        }
                    },
                    "evidence": {
                        "mode": "snapshot_diff",
                        "snapshot": {
                            "ref": "root.steps.CaptureBefore.snapshots.before",
                        },
                    },
                },
            }
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    sidecar_dir = executor.state_manager.run_root / "snapshots" / "capture_before"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar_rel = "snapshots/capture_before/before.json"
    (executor.state_manager.run_root / sidecar_rel).write_text(
        json.dumps(
            {
                "schema": "snapshot_diff/v1",
                "digest": "sha256",
                "captured_at": "pre_step",
                "candidate_keys": ["COMPLETED"],
                "candidates": {
                    "COMPLETED": {
                        "path": "artifacts/work/execution_report.md",
                        "exists": False,
                        "size": None,
                        "sha256": None,
                        "mtime_ns": None,
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    state = executor.state_manager.load().to_dict()
    state["steps"] = {
        "CaptureBefore": {
            "snapshots": {
                "before": {
                    "schema": "snapshot_diff/v1",
                    "digest": "sha256",
                    "captured_at": "pre_step",
                    "candidate_keys": ["COMPLETED"],
                    "sidecar": sidecar_rel,
                }
            }
        }
    }

    result = executor._execute_select_variant_output(workflow["steps"][2], state)

    assert result["status"] == "failed"
    assert result["error"]["type"] == "snapshot_state_missing"
    assert "hash" in result["error"]["message"].lower()


def test_select_variant_output_rejects_malformed_sidecar_snapshot_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume-time malformed sidecar payloads must fail through the designed snapshot error surface."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "snapshot-sidecar-invalid-json",
        "steps": [
            {
                "name": "MaterializeTargets",
                "id": "materialize_targets",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "placeholder_path",
                            "source": {"literal": "artifacts/work/execution_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                        }
                    ]
                },
            },
            {
                "name": "CaptureBefore",
                "id": "capture_before",
                "pre_snapshot": {
                    "name": "before",
                    "digest": "sha256",
                    "candidates": {
                        "COMPLETED": {
                            "ref": "root.steps.MaterializeTargets.artifacts.placeholder_path",
                        }
                    },
                },
                "command": ["echo", "ok"],
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
                        "allowed": ["COMPLETED"],
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
                        }
                    },
                    "evidence": {
                        "mode": "snapshot_diff",
                        "snapshot": {
                            "ref": "root.steps.CaptureBefore.snapshots.before",
                        },
                    },
                },
            }
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    sidecar_dir = executor.state_manager.run_root / "snapshots" / "capture_before"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar_rel = "snapshots/capture_before/before.json"
    payload = "{not-valid-json\n"
    (executor.state_manager.run_root / sidecar_rel).write_text(payload, encoding="utf-8")

    state = executor.state_manager.load().to_dict()
    state["steps"] = {
        "CaptureBefore": {
            "snapshots": {
                "before": {
                    "schema": "snapshot_diff/v1",
                    "digest": "sha256",
                    "captured_at": "pre_step",
                    "candidate_keys": ["COMPLETED"],
                    "sidecar": sidecar_rel,
                    "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                }
            }
        }
    }

    result = executor._execute_select_variant_output(workflow["steps"][2], state)

    assert result["status"] == "failed"
    assert result["error"]["type"] == "snapshot_state_missing"
    assert "json" in result["error"]["message"].lower()


def test_select_variant_output_rejects_directory_sidecar_snapshot_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume-time snapshot sidecars must resolve to files, not directories."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "snapshot-sidecar-directory",
        "steps": [
            {
                "name": "MaterializeTargets",
                "id": "materialize_targets",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "placeholder_path",
                            "source": {"literal": "artifacts/work/execution_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                        }
                    ]
                },
            },
            {
                "name": "CaptureBefore",
                "id": "capture_before",
                "pre_snapshot": {
                    "name": "before",
                    "digest": "sha256",
                    "candidates": {
                        "COMPLETED": {
                            "ref": "root.steps.MaterializeTargets.artifacts.placeholder_path",
                        }
                    },
                },
                "command": ["echo", "ok"],
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
                        "allowed": ["COMPLETED"],
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
                        }
                    },
                    "evidence": {
                        "mode": "snapshot_diff",
                        "snapshot": {
                            "ref": "root.steps.CaptureBefore.snapshots.before",
                        },
                    },
                },
            }
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    sidecar_rel = "snapshots/capture_before/before.json"
    (executor.state_manager.run_root / sidecar_rel).mkdir(parents=True, exist_ok=True)

    state = executor.state_manager.load().to_dict()
    state["steps"] = {
        "CaptureBefore": {
            "snapshots": {
                "before": {
                    "schema": "snapshot_diff/v1",
                    "digest": "sha256",
                    "captured_at": "pre_step",
                    "candidate_keys": ["COMPLETED"],
                    "sidecar": sidecar_rel,
                    "sha256": "unused",
                }
            }
        }
    }

    result = executor._execute_select_variant_output(workflow["steps"][2], state)

    assert result["status"] == "failed"
    assert result["error"]["type"] == "snapshot_state_missing"
    assert "file" in result["error"]["message"].lower() or "directory" in result["error"]["message"].lower()


def test_select_variant_output_rejects_non_mapping_sidecar_snapshot_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume-time snapshot sidecar payloads must decode to snapshot mappings."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "snapshot-sidecar-wrong-type",
        "steps": [
            {
                "name": "MaterializeTargets",
                "id": "materialize_targets",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "placeholder_path",
                            "source": {"literal": "artifacts/work/execution_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                        }
                    ]
                },
            },
            {
                "name": "CaptureBefore",
                "id": "capture_before",
                "pre_snapshot": {
                    "name": "before",
                    "digest": "sha256",
                    "candidates": {
                        "COMPLETED": {
                            "ref": "root.steps.MaterializeTargets.artifacts.placeholder_path",
                        }
                    },
                },
                "command": ["echo", "ok"],
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
                        "allowed": ["COMPLETED"],
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
                        }
                    },
                    "evidence": {
                        "mode": "snapshot_diff",
                        "snapshot": {
                            "ref": "root.steps.CaptureBefore.snapshots.before",
                        },
                    },
                },
            }
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    sidecar_dir = executor.state_manager.run_root / "snapshots" / "capture_before"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar_rel = "snapshots/capture_before/before.json"
    payload = "[]\n"
    (executor.state_manager.run_root / sidecar_rel).write_text(payload, encoding="utf-8")

    state = executor.state_manager.load().to_dict()
    state["steps"] = {
        "CaptureBefore": {
            "snapshots": {
                "before": {
                    "schema": "snapshot_diff/v1",
                    "digest": "sha256",
                    "captured_at": "pre_step",
                    "candidate_keys": ["COMPLETED"],
                    "sidecar": sidecar_rel,
                    "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                }
            }
        }
    }

    result = executor._execute_select_variant_output(workflow["steps"][2], state)

    assert result["status"] == "failed"
    assert result["error"]["type"] == "snapshot_state_missing"
    assert "object" in result["error"]["message"].lower() or "mapping" in result["error"]["message"].lower()


def test_select_variant_output_rejects_sidecar_snapshot_path_outside_run_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resume-time snapshot sidecars must stay under the orchestrator-managed run root."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "snapshot-sidecar-escapes-run-root",
        "steps": [
            {
                "name": "MaterializeTargets",
                "id": "materialize_targets",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "placeholder_path",
                            "source": {"literal": "artifacts/work/execution_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                        }
                    ]
                },
            },
            {
                "name": "CaptureBefore",
                "id": "capture_before",
                "pre_snapshot": {
                    "name": "before",
                    "digest": "sha256",
                    "candidates": {
                        "COMPLETED": {
                            "ref": "root.steps.MaterializeTargets.artifacts.placeholder_path",
                        }
                    },
                },
                "command": ["echo", "ok"],
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
                        "allowed": ["COMPLETED"],
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
                        }
                    },
                    "evidence": {
                        "mode": "snapshot_diff",
                        "snapshot": {
                            "ref": "root.steps.CaptureBefore.snapshots.before",
                        },
                    },
                },
            }
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    escaped_sidecar = "../../../outside.json"
    external_sidecar = tmp_path / "outside.json"
    payload = (
        json.dumps(
            {
                "schema": "snapshot_diff/v1",
                "digest": "sha256",
                "captured_at": "pre_step",
                "candidate_keys": ["COMPLETED"],
                "candidates": {
                    "COMPLETED": {
                        "path": "artifacts/work/execution_report.md",
                        "exists": False,
                        "size": None,
                        "sha256": None,
                        "mtime_ns": None,
                    }
                },
            }
        )
        + "\n"
    )
    external_sidecar.write_text(payload, encoding="utf-8")

    state = executor.state_manager.load().to_dict()
    state["steps"] = {
        "CaptureBefore": {
            "snapshots": {
                "before": {
                    "schema": "snapshot_diff/v1",
                    "digest": "sha256",
                    "captured_at": "pre_step",
                    "candidate_keys": ["COMPLETED"],
                    "sidecar": escaped_sidecar,
                    "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                }
            }
        }
    }

    result = executor._execute_select_variant_output(workflow["steps"][2], state)

    assert result["status"] == "failed"
    assert result["error"]["type"] == "snapshot_state_missing"
    assert "unsafe" in result["error"]["message"].lower()


def test_select_variant_output_rejects_ambiguous_snapshot_and_skips_bundle_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """select_variant_output should fail on multiple changed candidates without committing its bundle."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "snapshot-ambiguous",
        "steps": [
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
                        },
                    ]
                },
            },
            {
                "name": "ExecuteImplementation",
                "id": "execute_implementation",
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
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "root = Path('artifacts/work')\n"
                        "root.mkdir(parents=True, exist_ok=True)\n"
                        "(root / 'execution_report.md').write_text('# Execution Report\\n', encoding='utf-8')\n"
                        "(root / 'progress_report.md').write_text('# Progress Report\\n', encoding='utf-8')\n"
                    ),
                ],
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
                            "ref": "root.steps.ExecuteImplementation.snapshots.implementation_outcome_before",
                        },
                    },
                },
            },
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    state = executor.execute(on_error="continue")

    select_result = state["steps"]["SelectImplementationOutcome"]
    assert select_result["status"] == "failed"
    assert select_result["error"]["type"] == "snapshot_candidate_ambiguous"
    assert not (tmp_path / "state" / "implementation_state.json").exists()


def test_requires_variant_blocks_execution_when_selected_variant_does_not_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """requires_variant should stop the step before execution when the producer selected a different variant."""
    _enable_v214_loader(monkeypatch)

    workflow = {
        "version": "2.14",
        "name": "requires-variant-guard",
        "steps": [
            {
                "name": "EmitVariantBundle",
                "id": "emit_variant_bundle",
                "command": [
                    "python",
                    "-c",
                    (
                        "import json\n"
                        "from pathlib import Path\n"
                        "Path('artifacts/work').mkdir(parents=True, exist_ok=True)\n"
                        "Path('artifacts/work/progress_report.md').write_text('# blocked\\n', encoding='utf-8')\n"
                        "Path('state').mkdir(parents=True, exist_ok=True)\n"
                        "Path('state/variant_bundle.json').write_text(json.dumps({"
                        "'implementation_state': 'BLOCKED', "
                        "'progress_report_path': 'artifacts/work/progress_report.md'"
                        "}) + '\\n', encoding='utf-8')\n"
                    ),
                ],
                "variant_output": {
                    "path": "state/variant_bundle.json",
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
                },
            },
            {
                "name": "UseCompletedArtifact",
                "id": "use_completed_artifact",
                "requires_variant": {
                    "step": "EmitVariantBundle",
                    "value": "COMPLETED",
                },
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "Path('state').mkdir(parents=True, exist_ok=True)\n"
                        "Path('state/should_not_exist.txt').write_text('executed\\n', encoding='utf-8')\n"
                    ),
                ],
            },
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    state = executor.execute(on_error="continue")

    guarded = state["steps"]["UseCompletedArtifact"]
    assert guarded["status"] == "failed"
    assert guarded["error"]["type"] == "variant_unavailable"
    assert guarded["error"]["context"]["required_variant"] == "COMPLETED"
    assert guarded["error"]["context"]["selected_variant"] == "BLOCKED"
    assert not (tmp_path / "state" / "should_not_exist.txt").exists()


def test_adjudicated_provider_keeps_variant_output_contract_for_prompt_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adjudicated-provider prompt assembly must preserve variant_output instead of downgrading to output_bundle."""
    _enable_v214_loader(monkeypatch)
    (tmp_path / "prompt.md").write_text("Draft the implementation artifact.\n", encoding="utf-8")
    (tmp_path / "evaluator.md").write_text("Return strict JSON.\n", encoding="utf-8")

    workflow = {
        "version": "2.14",
        "name": "adjudicated-variant-prompt",
        "providers": {
            "candidate_a": {
                "command": ["bash", "-lc", "cat >/dev/null; echo candidate"],
                "input_mode": "stdin",
            },
            "evaluator": {
                "command": ["bash", "-lc", "cat >/dev/null; echo '{\"candidate_id\": \"a\", \"score\": 1.0}'"],
                "input_mode": "stdin",
            },
        },
        "steps": [
            {
                "name": "Draft",
                "id": "draft",
                "adjudicated_provider": {
                    "candidates": [{"id": "a", "provider": "candidate_a"}],
                    "evaluator": {
                        "provider": "evaluator",
                        "input_file": "evaluator.md",
                        "evidence_confidentiality": "same_trust_boundary",
                    },
                    "selection": {"tie_break": "candidate_order"},
                },
                "input_file": "prompt.md",
                "variant_output": {
                    "path": "state/variant_bundle.json",
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
                },
            }
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    captured: dict[str, object] = {}

    def _capture_output_contract_step(
        step: dict,
        context: dict,
        state: dict,
        *,
        workspace: Path | None = None,
        output_contract_step: dict | None = None,
        runtime_step_id: str | None = None,
    ) -> tuple[str | None, dict | None]:
        captured["output_contract_step"] = output_contract_step
        return None, {
            "status": "failed",
            "exit_code": 2,
            "error": {
                "type": "prompt_capture_stop",
                "message": "stop after capturing output contract step",
            },
        }

    executor._compose_provider_prompt_for_step = _capture_output_contract_step  # type: ignore[method-assign]

    state = executor.execute(on_error="continue")

    assert state["steps"]["Draft"]["status"] == "failed"
    output_contract_step = captured["output_contract_step"]
    assert isinstance(output_contract_step, dict)
    assert "variant_output" in output_contract_step
    assert "output_bundle" not in output_contract_step
    assert output_contract_step["variant_output"]["path"] == "state/variant_bundle.json"
