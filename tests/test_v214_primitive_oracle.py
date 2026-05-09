import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.golden_state import (
    _build_observation,
    _execute_workflow,
    _write_provider_scenario,
    load_expected_observation,
    run_fixture_workflow,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/v214_primitives"
BLOCKER_CLASSES = [
    "missing_resource",
    "unavailable_hardware",
    "roadmap_conflict",
    "external_dependency_outside_authority",
    "user_decision_required",
    "unrecoverable_after_fix_attempt",
]


def _write_fake_provider(workspace: Path) -> None:
    fake_provider_dest = workspace / "tests/fixtures/bin/fake_provider.py"
    fake_provider_dest.parent.mkdir(parents=True, exist_ok=True)
    fake_provider_dest.write_text(
        (ROOT / "tests/fixtures/bin/fake_provider.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _run_v214_workflow(
    *,
    workspace: Path,
    scenario_name: str,
    workflow: dict[str, Any],
) -> dict[str, Any]:
    shutil.copytree(FIXTURE_ROOT, workspace, dirs_exist_ok=True)
    _write_fake_provider(workspace)
    scenario_path = FIXTURE_ROOT / "scenarios" / f"{scenario_name}.json"
    if scenario_path.is_file():
        _write_provider_scenario(workspace, json.loads(scenario_path.read_text(encoding="utf-8")))
    else:
        _write_provider_scenario(workspace, {"mode": scenario_name})
    (workspace / "workflow.yaml").write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    state = _execute_workflow(workspace=workspace, workflow_relpath="workflow.yaml", inputs={})
    return _build_observation(workspace, state)


def _first_step_with_artifact(observation: dict[str, Any], artifact_name: str) -> dict[str, Any] | None:
    for step in observation["steps"].values():
        artifacts = step.get("artifacts", {})
        if artifact_name in artifacts:
            return step
    return None


def _first_failed_step(observation: dict[str, Any]) -> dict[str, Any] | None:
    for step in observation["steps"].values():
        if step.get("status") == "failed":
            return step
    return None


def _json_file(observation: dict[str, Any], relpath: str) -> dict[str, Any] | None:
    file_observation = observation["files"].get(relpath)
    if not isinstance(file_observation, dict):
        return None
    payload = file_observation.get("json")
    return payload if isinstance(payload, dict) else None


def _canonical_contract_violation(observation: dict[str, Any]) -> dict[str, Any] | None:
    failed = _first_failed_step(observation)
    if failed is None:
        return None
    error = failed.get("error")
    if not isinstance(error, dict):
        return {"type": None, "violations": []}
    violations = error.get("context", {}).get("violations", [])
    canonical_violations = []
    if isinstance(violations, list):
        for violation in violations:
            if not isinstance(violation, dict):
                continue
            context = violation.get("context", {})
            canonical_violations.append(
                {
                    "type": (
                        "invalid_enum_value"
                        if violation.get("type") == "variant_discriminant_invalid"
                        else violation.get("type")
                    ),
                    "message": violation.get("message"),
                    "value": context.get("value"),
                }
            )
    return {
        "type": "contract_violation" if error.get("type") == "target_missing" else error.get("type"),
        "violations": canonical_violations,
    }


def _snapshot_failure_code(observation: dict[str, Any]) -> str | None:
    error_payload = _json_file(observation, "state/oracle/snapshot_selection_error.json")
    if error_payload is not None:
        failure_class = error_payload.get("failure_class")
        if failure_class == "no_changed_candidates":
            return "snapshot_candidate_unchanged"
        if failure_class == "multiple_changed_candidates":
            return "snapshot_candidate_ambiguous"
        return str(failure_class) if failure_class is not None else None

    failed = _first_failed_step(observation)
    error = failed.get("error") if isinstance(failed, dict) else None
    if isinstance(error, dict):
        return error.get("type")
    return None


def _implementation_failure_code(observation: dict[str, Any]) -> str | None:
    failed = _first_failed_step(observation)
    if failed is None:
        return None
    error = failed.get("error")
    if isinstance(error, dict):
        error_type = error.get("type")
        if error_type in {"snapshot_candidate_unchanged", "snapshot_candidate_ambiguous"}:
            return str(error_type)
    if observation["status"] == "failed":
        has_execution = "artifacts/work/execution_report.md" in observation["files"]
        has_progress = "artifacts/work/progress_report.md" in observation["files"]
        if has_execution and has_progress:
            return "snapshot_candidate_ambiguous"
        if not has_execution and not has_progress:
            return "snapshot_candidate_unchanged"
    return None


def _summarize_materialization_success(observation: dict[str, Any]) -> dict[str, Any]:
    step = _first_step_with_artifact(observation, "plan_path")
    return {
        "status": observation["status"],
        "workflow_outputs": observation["workflow_outputs"],
        "plan_path": step["artifacts"].get("plan_path") if step is not None else None,
    }


def _summarize_snapshot_selection(observation: dict[str, Any]) -> dict[str, Any]:
    selected_payload = _json_file(observation, "state/oracle/snapshot_selection.json")
    failed = _first_failed_step(observation)
    error = failed.get("error") if isinstance(failed, dict) else None
    error_context = error.get("context", {}) if isinstance(error, dict) else {}
    selected_variant = None
    selected_path = None
    if selected_payload is not None:
        selected_variant = selected_payload.get("selected_variant")
        selected_path = (
            selected_payload.get("selected_path")
            or selected_payload.get("execution_report_path")
            or selected_payload.get("progress_report_path")
        )
    return {
        "status": observation["status"],
        "selected_variant": selected_variant or observation["workflow_outputs"].get("selected_variant"),
        "selected_path": selected_path,
        "candidate_keys": ["execution_report_path", "progress_report_path"],
        "failure_type": _snapshot_failure_code(observation),
    }


def _summarize_variant_proof(observation: dict[str, Any]) -> dict[str, Any]:
    failed = _first_failed_step(observation)
    error = failed.get("error") if isinstance(failed, dict) else None
    return {
        "status": observation["status"],
        "workflow_outputs": observation["workflow_outputs"],
        "bundle": _json_file(observation, "state/oracle/variant_bundle.json"),
        "access": _json_file(observation, "state/oracle/variant_access.json"),
        "access_error": _json_file(observation, "state/oracle/variant_access_error.json"),
        "failure_type": error.get("type") if isinstance(error, dict) else None,
    }


def _summarize_implementation_outcome(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": observation["status"],
        "workflow_outputs": observation["workflow_outputs"],
        "bundle": _json_file(observation, "state/oracle/implementation_state.json"),
        "failure_type": _implementation_failure_code(observation),
    }


def _materialization_success_v214_workflow() -> dict[str, Any]:
    return {
        "version": "2.14",
        "name": "v214-materialization-oracle-public",
        "outputs": {
            "plan_path": {
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
                "from": {"ref": "root.steps.MaterializePlan.artifacts.plan_path"},
            }
        },
        "steps": [
            {
                "name": "CreatePlan",
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "path = Path('docs/plans/oracle-plan.md')\n"
                        "path.parent.mkdir(parents=True, exist_ok=True)\n"
                        "path.write_text('# Oracle Plan\\n', encoding='utf-8')\n"
                    ),
                ],
            },
            {
                "name": "MaterializePlan",
                "id": "materialize_plan",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "plan_path",
                            "source": {"literal": "docs/plans/oracle-plan.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "docs/plans",
                                "must_exist_target": True,
                            },
                        }
                    ]
                },
            },
        ],
    }


def _materialization_missing_target_v214_workflow() -> dict[str, Any]:
    return {
        "version": "2.14",
        "name": "v214-materialization-missing-target-public",
        "steps": [
            {
                "name": "EmitMissingTargetBundle",
                "id": "emit_missing_target_bundle",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "plan_path",
                            "source": {"literal": "docs/plans/missing-plan.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "docs/plans",
                                "must_exist_target": True,
                            },
                        }
                    ]
                },
            }
        ],
    }


def _snapshot_selection_v214_workflow() -> dict[str, Any]:
    return {
        "version": "2.14",
        "name": "v214-snapshot-selection-oracle-public",
        "outputs": {
            "selected_variant": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["COMPLETED", "BLOCKED"],
                "from": {"ref": "root.steps.SelectChangedCandidate.artifacts.selected_variant"},
            }
        },
        "steps": [
            {
                "name": "MaterializeCandidateTargets",
                "id": "materialize_candidate_targets",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "execution_report_path",
                            "source": {"literal": "artifacts/work/execution_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                        },
                        {
                            "name": "progress_report_path",
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
                "name": "InitializeCandidateSnapshot",
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "root = Path('artifacts/work')\n"
                        "root.mkdir(parents=True, exist_ok=True)\n"
                        "(root / 'execution_report.md').write_text('baseline execution report\\n', encoding='utf-8')\n"
                        "(root / 'progress_report.md').write_text('baseline progress report\\n', encoding='utf-8')\n"
                    ),
                ],
            },
            {
                "name": "MutateCandidateSnapshot",
                "id": "mutate_candidate_snapshot",
                "pre_snapshot": {
                    "name": "snapshot_before",
                    "digest": "sha256",
                    "candidates": {
                        "COMPLETED": {
                            "ref": "root.steps.MaterializeCandidateTargets.artifacts.execution_report_path",
                        },
                        "BLOCKED": {
                            "ref": "root.steps.MaterializeCandidateTargets.artifacts.progress_report_path",
                        },
                    },
                },
                "command": [
                    "python",
                    "-c",
                    (
                        "import json\n"
                        "from pathlib import Path\n"
                        "scenario = json.loads(Path('state/fake_provider_scenario.json').read_text(encoding='utf-8'))\n"
                        "mode = scenario['mode']\n"
                        "execution_path = Path('artifacts/work/execution_report.md')\n"
                        "progress_path = Path('artifacts/work/progress_report.md')\n"
                        "if mode in {'single_changed', 'multi_change'}:\n"
                        "    execution_path.write_text('updated execution report\\n', encoding='utf-8')\n"
                        "if mode == 'multi_change':\n"
                        "    progress_path.write_text('updated progress report\\n', encoding='utf-8')\n"
                    ),
                ],
            },
            {
                "name": "SelectChangedCandidate",
                "id": "select_changed_candidate",
                "select_variant_output": {
                    "path": "state/oracle/snapshot_selection.json",
                    "discriminant": {
                        "name": "selected_variant",
                        "json_pointer": "/selected_variant",
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
                            "ref": "root.steps.MutateCandidateSnapshot.snapshots.snapshot_before",
                        },
                    },
                },
            },
        ],
    }


def _invalid_bundle_v214_workflow() -> dict[str, Any]:
    return {
        "version": "2.14",
        "name": "v214-invalid-bundle-oracle-public",
        "steps": [
            {
                "name": "EmitInvalidBundle",
                "command": [
                    "python",
                    "-c",
                    (
                        "import json\n"
                        "from pathlib import Path\n"
                        "Path('state').mkdir(parents=True, exist_ok=True)\n"
                        "Path('state/invalid_selection.json').write_text("
                        "json.dumps({'selection_status': 'MAYBE'}, indent=2) + '\\n', encoding='utf-8')\n"
                    ),
                ],
                "variant_output": {
                    "path": "state/invalid_selection.json",
                    "discriminant": {
                        "name": "selection_status",
                        "json_pointer": "/selection_status",
                        "type": "enum",
                        "allowed": ["SELECTED", "DONE", "BLOCKED"],
                    },
                    "variants": {
                        "SELECTED": {"fields": []},
                        "DONE": {"fields": []},
                        "BLOCKED": {"fields": []},
                    },
                },
            }
        ],
    }


def _variant_proof_v214_workflow() -> dict[str, Any]:
    return {
        "version": "2.14",
        "name": "v214-variant-proof-oracle-public",
        "outputs": {
            "selected_variant": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["COMPLETED"],
                "from": {"ref": "root.steps.RecordVariantAccess.artifacts.selected_variant"},
            }
        },
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
                        "scenario = json.loads(Path('state/fake_provider_scenario.json').read_text(encoding='utf-8'))\n"
                        "artifacts_root = Path('artifacts/work')\n"
                        "artifacts_root.mkdir(parents=True, exist_ok=True)\n"
                        "state_root = Path('state/oracle')\n"
                        "state_root.mkdir(parents=True, exist_ok=True)\n"
                        "if scenario['mode'] == 'variant_proof_accept':\n"
                        "    execution_path = artifacts_root / 'execution_report.md'\n"
                        "    execution_path.write_text('# Execution Report\\n', encoding='utf-8')\n"
                        "    payload = {\n"
                        "        'implementation_state': 'COMPLETED',\n"
                        "        'execution_report_path': execution_path.as_posix(),\n"
                        "    }\n"
                        "else:\n"
                        "    progress_path = artifacts_root / 'progress_report.md'\n"
                        "    progress_path.write_text('# Blocked Progress Report\\n\\nBlocker Class: missing_resource\\n', encoding='utf-8')\n"
                        "    payload = {\n"
                        "        'implementation_state': 'BLOCKED',\n"
                        "        'progress_report_path': progress_path.as_posix(),\n"
                        "        'blocker_class': 'missing_resource',\n"
                        "    }\n"
                        "(state_root / 'variant_bundle.json').write_text(json.dumps(payload, indent=2) + '\\n', encoding='utf-8')\n"
                    ),
                ],
                "variant_output": {
                    "path": "state/oracle/variant_bundle.json",
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
                                },
                                {
                                    "name": "blocker_class",
                                    "json_pointer": "/blocker_class",
                                    "type": "enum",
                                    "allowed": BLOCKER_CLASSES,
                                },
                            ]
                        },
                    },
                },
            },
            {
                "name": "RecordVariantAccess",
                "when": {
                    "compare": {
                        "left": {"ref": "self.steps.EmitVariantBundle.artifacts.implementation_state"},
                        "op": "eq",
                        "right": "COMPLETED",
                    }
                },
                "requires_variant": {
                    "step": "EmitVariantBundle",
                    "value": "COMPLETED",
                },
                "command": [
                    "python",
                    "-c",
                    (
                        "import json\n"
                        "from pathlib import Path\n"
                        "payload = {\n"
                        "    'selected_variant': 'COMPLETED',\n"
                        "    'requested_field': 'execution_report_path',\n"
                        "    'accessed_path': Path(__import__('sys').argv[1]).as_posix(),\n"
                        "}\n"
                        "path = Path('state/oracle/variant_access.json')\n"
                        "path.parent.mkdir(parents=True, exist_ok=True)\n"
                        "path.write_text(json.dumps(payload, indent=2) + '\\n', encoding='utf-8')\n"
                    ),
                    "${steps.EmitVariantBundle.artifacts.execution_report_path}",
                ],
                "output_bundle": {
                    "path": "state/oracle/variant_access.json",
                    "fields": [
                        {
                            "name": "selected_variant",
                            "json_pointer": "/selected_variant",
                            "type": "enum",
                            "allowed": ["COMPLETED"],
                        },
                        {
                            "name": "accessed_path",
                            "json_pointer": "/accessed_path",
                            "type": "relpath",
                            "under": "artifacts/work",
                            "must_exist_target": True,
                        },
                    ],
                },
            },
            {
                "name": "RecordVariantAccessError",
                "when": {
                    "compare": {
                        "left": {"ref": "self.steps.EmitVariantBundle.artifacts.implementation_state"},
                        "op": "eq",
                        "right": "BLOCKED",
                    }
                },
                "command": [
                    "python",
                    "-c",
                    (
                        "import json\n"
                        "from pathlib import Path\n"
                        "payload = {\n"
                        "    'failure_class': 'variant_unavailable',\n"
                        "    'selected_variant': 'BLOCKED',\n"
                        "    'required_variant': 'COMPLETED',\n"
                        "    'requested_field': 'execution_report_path',\n"
                        "}\n"
                        "path = Path('state/oracle/variant_access_error.json')\n"
                        "path.parent.mkdir(parents=True, exist_ok=True)\n"
                        "path.write_text(json.dumps(payload, indent=2) + '\\n', encoding='utf-8')\n"
                        "raise SystemExit('variant_unavailable: execution_report_path requires COMPLETED, got BLOCKED')\n"
                    ),
                ],
            },
        ],
    }


def _implementation_outcome_v214_workflow() -> dict[str, Any]:
    return {
        "version": "2.14",
        "name": "v214-implementation-outcome-oracle-public",
        "providers": {
            "fake": {
                "command": ["python", "tests/fixtures/bin/fake_provider.py"],
                "input_mode": "stdin",
            }
        },
        "outputs": {
            "implementation_state": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["COMPLETED", "BLOCKED"],
                "from": {"ref": "root.steps.SelectImplementationOutcome.artifacts.implementation_state"},
            }
        },
        "steps": [
            {
                "name": "InitializeTargets",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state/oracle artifacts/work && printf '1\\n' > state/oracle/phase_started_at_ns.txt",
                ],
                "expected_outputs": [
                    {
                        "name": "phase_started_at_ns",
                        "path": "state/oracle/phase_started_at_ns.txt",
                        "type": "integer",
                    }
                ],
            },
            {
                "name": "MaterializeOutcomeTargets",
                "id": "materialize_outcome_targets",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "execution_report_path",
                            "source": {"literal": "artifacts/work/execution_report.md"},
                            "contract": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": False,
                            },
                        },
                        {
                            "name": "progress_report_path",
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
                "provider": "fake",
                "input_file": "implementation_oracle/prompt.md",
                "pre_snapshot": {
                    "name": "implementation_outcome_before",
                    "digest": "sha256",
                    "candidates": {
                        "COMPLETED": {
                            "ref": "root.steps.MaterializeOutcomeTargets.artifacts.execution_report_path",
                        },
                        "BLOCKED": {
                            "ref": "root.steps.MaterializeOutcomeTargets.artifacts.progress_report_path",
                        },
                    },
                },
            },
            {
                "name": "SelectImplementationOutcome",
                "id": "select_implementation_outcome",
                "select_variant_output": {
                    "path": "state/oracle/implementation_state.json",
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
                                },
                                {
                                    "name": "blocker_class",
                                    "json_pointer": "/blocker_class",
                                    "type": "enum",
                                    "allowed": BLOCKER_CLASSES,
                                },
                            ]
                        },
                    },
                    "evidence": {
                        "mode": "snapshot_diff",
                        "snapshot": {
                            "ref": "root.steps.ExecuteImplementation.snapshots.implementation_outcome_before",
                        },
                    },
                    "extract": {
                        "from": "candidate_path",
                        "line_prefix": "Blocker Class:",
                        "strip": ["`", "-", "#"],
                    },
                },
            },
        ],
    }


@pytest.mark.parametrize(
    ("scenario_name", "expected_name"),
    [
        ("completed", "completed.json"),
        ("blocked", "blocked.json"),
        ("both_reports", "both_reports.json"),
        ("neither_report", "neither_report.json"),
    ],
)
def test_implementation_outcome_oracles(tmp_path: Path, scenario_name: str, expected_name: str) -> None:
    del expected_name
    legacy = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / f"legacy-{scenario_name}",
        workflow_relpath="implementation_oracle/workflow.yaml",
        scenario_name=scenario_name,
    )
    v214 = _run_v214_workflow(
        workspace=tmp_path / f"v214-{scenario_name}",
        scenario_name=scenario_name,
        workflow=_implementation_outcome_v214_workflow(),
    )
    assert _summarize_implementation_outcome(legacy) == _summarize_implementation_outcome(v214)


@pytest.mark.parametrize(
    ("scenario_name", "expected_name"),
    [
        ("review_approve", "review_approve.json"),
        ("review_revise", "review_revise.json"),
    ],
)
def test_review_decision_oracles(tmp_path: Path, scenario_name: str, expected_name: str) -> None:
    observation = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / scenario_name,
        workflow_relpath="review_oracle/workflow.yaml",
        scenario_name=scenario_name,
    )

    assert observation == load_expected_observation(FIXTURE_ROOT / "review_oracle" / "expected" / expected_name)


def test_materialization_contract_oracles(tmp_path: Path) -> None:
    legacy = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / "legacy-materialization",
        workflow_relpath="materialization_oracle/workflow.yaml",
        scenario_name="materialization_ok",
    )
    v214 = _run_v214_workflow(
        workspace=tmp_path / "v214-materialization",
        scenario_name="materialization_ok",
        workflow=_materialization_success_v214_workflow(),
    )
    assert _summarize_materialization_success(legacy) == _summarize_materialization_success(v214)


def test_invalid_bundle_no_commit_oracle(tmp_path: Path) -> None:
    legacy = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / "legacy-invalid-bundle",
        workflow_relpath="invalid_bundle_oracle/workflow.yaml",
        scenario_name="invalid_bundle",
    )
    v214 = _run_v214_workflow(
        workspace=tmp_path / "v214-invalid-bundle",
        scenario_name="invalid_bundle",
        workflow=_invalid_bundle_v214_workflow(),
    )
    assert _canonical_contract_violation(legacy) == _canonical_contract_violation(v214)


def test_missing_required_target_materialization_failure(tmp_path: Path) -> None:
    legacy = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / "legacy-missing-target",
        workflow_relpath="materialization_missing_target_oracle/workflow.yaml",
        scenario_name="missing_target",
    )
    v214 = _run_v214_workflow(
        workspace=tmp_path / "v214-missing-target",
        scenario_name="missing_target",
        workflow=_materialization_missing_target_v214_workflow(),
    )
    assert _canonical_contract_violation(legacy) == _canonical_contract_violation(v214)


@pytest.mark.parametrize(
    ("scenario_name", "expected_name"),
    [
        ("stricter_contract", "stricter_contract.json"),
        ("weaker_contract", "weaker_contract.json"),
    ],
)
def test_contract_refinement_oracles(tmp_path: Path, scenario_name: str, expected_name: str) -> None:
    observation = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / scenario_name,
        workflow_relpath="contract_refinement_oracle/workflow.yaml",
        scenario_name=scenario_name,
    )

    assert observation == load_expected_observation(
        FIXTURE_ROOT / "contract_refinement_oracle" / "expected" / expected_name
    )


@pytest.mark.parametrize(
    ("scenario_name", "expected_name"),
    [
        ("single_changed", "single_changed.json"),
        ("no_change", "no_change.json"),
        ("multi_change", "multi_change.json"),
    ],
)
def test_snapshot_selection_oracles(tmp_path: Path, scenario_name: str, expected_name: str) -> None:
    del expected_name
    legacy = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / f"legacy-{scenario_name}",
        workflow_relpath="snapshot_selection_oracle/workflow.yaml",
        scenario_name=scenario_name,
    )
    v214 = _run_v214_workflow(
        workspace=tmp_path / f"v214-{scenario_name}",
        scenario_name=scenario_name,
        workflow=_snapshot_selection_v214_workflow(),
    )
    assert _summarize_snapshot_selection(legacy) == _summarize_snapshot_selection(v214)


@pytest.mark.parametrize(
    ("scenario_name", "expected_name"),
    [
        ("variant_proof_accept", "variant_proof_accept.json"),
        ("variant_proof_reject", "variant_proof_reject.json"),
    ],
)
def test_variant_proof_oracles(tmp_path: Path, scenario_name: str, expected_name: str) -> None:
    del expected_name
    legacy = run_fixture_workflow(
        fixture_root=FIXTURE_ROOT,
        workspace=tmp_path / f"legacy-{scenario_name}",
        workflow_relpath="variant_proof_oracle/workflow.yaml",
        scenario_name=scenario_name,
    )
    v214 = _run_v214_workflow(
        workspace=tmp_path / f"v214-{scenario_name}",
        scenario_name=scenario_name,
        workflow=_variant_proof_v214_workflow(),
    )
    assert _summarize_variant_proof(legacy) == _summarize_variant_proof(v214)
