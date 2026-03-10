"""Integration tests for v1.2 artifact publish/consume dataflow guarantees."""

import json
from pathlib import Path

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow))
    return workflow_file


def _run_workflow(tmp_path: Path, workflow: dict, on_error: str = "stop") -> tuple[dict, dict]:
    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    final_state = executor.execute(on_error=on_error)
    persisted = state_manager.load().to_dict()
    return final_state, persisted


def _artifact_registry() -> dict:
    return {
        "execution_log": {
            "pointer": "state/execution_log_path.txt",
            "type": "relpath",
            "under": "artifacts/work",
            "must_exist_target": True,
        }
    }


def _scalar_artifact_registry() -> dict:
    return {
        "failed_count": {
            "kind": "scalar",
            "type": "integer",
        }
    }


def _string_scalar_artifact_registry() -> dict:
    return {
        "session_id": {
            "kind": "scalar",
            "type": "string",
        }
    }


def _publish_step(name: str, target_relpath: str) -> dict:
    return {
        "name": name,
        "command": [
            "bash",
            "-lc",
            (
                "mkdir -p state artifacts/work && "
                f"printf '{target_relpath}\\n' > state/execution_log_path.txt && "
                f"printf '{name} log\\n' > {target_relpath}"
            ),
        ],
        "expected_outputs": [
            {
                "name": "execution_log_path",
                "path": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ],
        "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
    }


def _publish_scalar_step(name: str, value: int) -> dict:
    return {
        "name": name,
        "command": [
            "bash",
            "-lc",
            (
                "mkdir -p state && "
                f"printf '{value}\\n' > state/failed_count.txt"
            ),
        ],
        "expected_outputs": [
            {
                "name": "failed_count",
                "path": "state/failed_count.txt",
                "type": "integer",
            }
        ],
        "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
    }


def test_publish_records_artifact_version_on_success(tmp_path: Path):
    """Successful publish records artifact version metadata in run state."""
    workflow = {
        "version": "1.2",
        "name": "publish-ledger",
        "artifacts": _artifact_registry(),
        "steps": [
            _publish_step("ExecutePlan", "artifacts/work/latest-execution-log.md"),
        ],
    }

    _final, persisted = _run_workflow(tmp_path, workflow)
    versions = persisted.get("artifact_versions", {}).get("execution_log", [])

    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["producer"] == "ExecutePlan"
    assert versions[0]["value"] == "artifacts/work/latest-execution-log.md"


def test_scalar_bookkeeping_publish_advances_lineage_via_publishes_from(tmp_path: Path):
    """Scalar bookkeeping steps publish through the normal lineage ledger only."""
    workflow = {
        "version": "1.7",
        "name": "scalar-lineage",
        "artifacts": _scalar_artifact_registry(),
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
                    "by": 2,
                },
                "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
            },
            {
                "name": "ReadCount",
                "consumes": [
                    {
                        "artifact": "failed_count",
                        "producers": ["InitializeCount", "IncrementCount"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "consume_bundle": {"path": "state/failed_count_bundle.json"},
                "command": ["bash", "-lc", "cat state/failed_count_bundle.json"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow)

    assert json.loads(state["steps"]["ReadCount"]["output"]) == {"failed_count": 2}
    versions = persisted.get("artifact_versions", {}).get("failed_count", [])
    assert [entry["producer"] for entry in versions] == ["InitializeCount", "IncrementCount"]
    assert [entry["value"] for entry in versions] == [0, 2]


def test_string_scalar_bookkeeping_preserves_exact_values_across_lineage(tmp_path: Path):
    """String scalar artifacts publish and consume exact values without trimming."""
    workflow = {
        "version": "2.10",
        "name": "string-lineage",
        "artifacts": _string_scalar_artifact_registry(),
        "steps": [
            {
                "name": "InitializeSession",
                "set_scalar": {
                    "artifact": "session_id",
                    "value": "  sess-001  ",
                },
                "publishes": [{"artifact": "session_id", "from": "session_id"}],
            },
            {
                "name": "ReadSession",
                "consumes": [
                    {
                        "artifact": "session_id",
                        "producers": ["InitializeSession"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "consume_bundle": {"path": "state/session_bundle.json"},
                "command": ["bash", "-lc", "cat state/session_bundle.json"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow)

    assert json.loads(state["steps"]["ReadSession"]["output"]) == {"session_id": "  sess-001  "}
    versions = persisted.get("artifact_versions", {}).get("session_id", [])
    assert [entry["value"] for entry in versions] == ["  sess-001  "]


def test_provider_session_resume_excludes_reserved_session_handle_from_consume_bundle(tmp_path: Path):
    """Resume consume bundles omit the reserved session handle by default."""
    session_script = "\n".join(
        [
            "python - <<'PY'",
            "import json",
            "from pathlib import Path",
            "print(json.dumps({\"type\": \"session.started\", \"session_id\": \"sess-123\"}))",
            "print(json.dumps({\"type\": \"assistant.message\", \"role\": \"assistant\", \"text\": Path(\"state/resume_bundle.json\").read_text(encoding=\"utf-8\")}))",
            "print(json.dumps({\"type\": \"response.completed\", \"session_id\": \"sess-123\"}))",
            "PY",
        ]
    )
    workflow = {
        "version": "2.10",
        "name": "provider-session-bundle",
        "providers": {
            "mock_provider": {
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
            "session_id": {
                "kind": "scalar",
                "type": "string",
            },
            "review_feedback": {
                "kind": "scalar",
                "type": "string",
            },
        },
        "steps": [
            {
                "name": "PublishSession",
                "set_scalar": {
                    "artifact": "session_id",
                    "value": "sess-123",
                },
                "publishes": [{"artifact": "session_id", "from": "session_id"}],
            },
            {
                "name": "PublishFeedback",
                "set_scalar": {
                    "artifact": "review_feedback",
                    "value": "Address the latest comments.",
                },
                "publishes": [{"artifact": "review_feedback", "from": "review_feedback"}],
            },
            {
                "name": "ResumeImplementation",
                "provider": "mock_provider",
                "consumes": [
                    {
                        "artifact": "session_id",
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                    {
                        "artifact": "review_feedback",
                        "policy": "latest_successful",
                    },
                ],
                "consume_bundle": {"path": "state/resume_bundle.json"},
                "provider_session": {
                    "mode": "resume",
                    "session_id_from": "session_id",
                },
            },
        ],
    }

    state, _persisted = _run_workflow(tmp_path, workflow)

    assert json.loads(state["steps"]["ResumeImplementation"]["output"]) == {
        "review_feedback": "Address the latest comments.",
    }


def test_provider_session_fresh_publishes_runtime_owned_session_handle(tmp_path: Path):
    """Fresh session steps publish the captured session handle into normal scalar lineage."""
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
        "name": "provider-session-fresh-lineage",
        "providers": {
            "mock_provider": {
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
                "name": "StartImplementation",
                "provider": "mock_provider",
                "provider_session": {
                    "mode": "fresh",
                    "publish_artifact": "implementation_session_id",
                },
            },
            {
                "name": "ReadSession",
                "consumes": [
                    {
                        "artifact": "implementation_session_id",
                        "producers": ["StartImplementation"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "consume_bundle": {"path": "state/session_bundle.json"},
                "command": ["bash", "-lc", "cat state/session_bundle.json"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow)

    assert state["steps"]["StartImplementation"]["artifacts"] == {
        "implementation_session_id": "sess-123"
    }
    assert json.loads(state["steps"]["ReadSession"]["output"]) == {
        "implementation_session_id": "sess-123"
    }
    versions = persisted.get("artifact_versions", {}).get("implementation_session_id", [])
    assert len(versions) == 1
    assert versions[0]["producer_name"] == "StartImplementation"
    assert versions[0]["value"] == "sess-123"


def test_consume_latest_successful_prefers_fixissues_over_executeplan(tmp_path: Path):
    """Consumer selects latest published version even if pointer file was clobbered."""
    workflow = {
        "version": "1.2",
        "name": "consume-latest",
        "artifacts": _artifact_registry(),
        "steps": [
            _publish_step("ExecutePlan", "artifacts/work/exec-plan.md"),
            _publish_step("FixIssues", "artifacts/work/fix-pass.md"),
            {
                "name": "ClobberPointer",
                "command": [
                    "bash",
                    "-lc",
                    "printf 'artifacts/work/exec-plan.md\\n' > state/execution_log_path.txt",
                ],
            },
            {
                "name": "ReviewImplVsPlan",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan", "FixIssues"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "command": ["bash", "-lc", "cat state/execution_log_path.txt"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow)
    review_output = state["steps"]["ReviewImplVsPlan"]["output"].strip()

    assert review_output == "artifacts/work/fix-pass.md"
    consumes = persisted.get("artifact_consumes", {}).get("ReviewImplVsPlan", {})
    assert consumes.get("execution_log") == 2


def test_v14_consume_relpath_is_read_only_for_pointer_file(tmp_path: Path):
    """v1.4 consume preflight must not overwrite relpath pointer files."""
    workflow = {
        "version": "1.4",
        "name": "consume-read-only-pointer",
        "artifacts": _artifact_registry(),
        "steps": [
            _publish_step("ExecutePlan", "artifacts/work/exec-plan.md"),
            {
                "name": "PrepareFixPointer",
                "command": [
                    "bash",
                    "-lc",
                    "printf 'artifacts/work/c2-fix.md\\n' > state/execution_log_path.txt",
                ],
            },
            {
                "name": "FixIssues",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "command": ["bash", "-lc", "cat state/execution_log_path.txt"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow)
    fix_output = state["steps"]["FixIssues"]["output"].strip()

    # v1.4: consume resolution should not clobber the step-owned pointer file.
    assert fix_output == "artifacts/work/c2-fix.md"
    consumes = persisted.get("artifact_consumes", {}).get("FixIssues", {})
    assert consumes.get("execution_log") == 1


def test_consume_since_last_consume_fails_when_stale(tmp_path: Path):
    """since_last_consume requires a new publication before the next consume."""
    workflow = {
        "version": "1.2",
        "name": "consume-stale",
        "artifacts": _artifact_registry(),
        "steps": [
            _publish_step("ExecutePlan", "artifacts/work/exec-plan.md"),
            {
                "name": "ReviewA",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "since_last_consume",
                    }
                ],
                "command": ["bash", "-lc", "echo review-a"],
            },
            {
                "name": "ReviewB",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "since_last_consume",
                    }
                ],
                "command": ["bash", "-lc", "echo review-b"],
            },
        ],
    }

    state, _persisted = _run_workflow(tmp_path, workflow, on_error="continue")
    review_b = state["steps"]["ReviewB"]

    assert review_b["exit_code"] == 2
    assert review_b["error"]["type"] == "contract_violation"


def test_since_last_consume_is_scoped_to_consumer_step(tmp_path: Path):
    """A different consumer step should be allowed to consume the current version once."""
    workflow = {
        "version": "1.4",
        "name": "consume-freshness-step-scope",
        "artifacts": _artifact_registry(),
        "steps": [
            _publish_step("ReviewImplVsPlan", "artifacts/work/c0-review.md"),
            {
                "name": "ReviewPlanLevelIssues",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ReviewImplVsPlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "command": ["bash", "-lc", "echo plan-review"],
            },
            {
                "name": "FixIssues",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ReviewImplVsPlan"],
                        "policy": "latest_successful",
                        "freshness": "since_last_consume",
                    }
                ],
                "command": ["bash", "-lc", "echo fix-issues"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow, on_error="continue")

    assert state["steps"]["ReviewPlanLevelIssues"]["exit_code"] == 0
    assert state["steps"]["FixIssues"]["exit_code"] == 0
    consumes = persisted.get("artifact_consumes", {}).get("FixIssues", {})
    assert consumes.get("execution_log") == 1


@pytest.mark.parametrize("version", ["1.5", "1.6", "1.7", "1.8"])
def test_post_v14_since_last_consume_stays_scoped_to_consumer_step(tmp_path: Path, version: str):
    """Post-v1.4 additive releases keep step-scoped freshness on name-keyed state."""
    workflow = {
        "version": version,
        "name": f"consume-freshness-step-scope-{version}",
        "artifacts": _artifact_registry(),
        "steps": [
            _publish_step("ReviewImplVsPlan", "artifacts/work/c0-review.md"),
            {
                "name": "ReviewPlanLevelIssues",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ReviewImplVsPlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "command": ["bash", "-lc", "echo plan-review"],
            },
            {
                "name": "FixIssues",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ReviewImplVsPlan"],
                        "policy": "latest_successful",
                        "freshness": "since_last_consume",
                    }
                ],
                "command": ["bash", "-lc", "echo fix-issues"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow, on_error="continue")

    assert state["steps"]["ReviewPlanLevelIssues"]["exit_code"] == 0
    assert state["steps"]["FixIssues"]["exit_code"] == 0
    consumes = persisted.get("artifact_consumes", {}).get("FixIssues", {})
    assert consumes.get("execution_log") == 1


@pytest.mark.parametrize("version", ["2.0", "2.1"])
def test_v2_since_last_consume_is_scoped_to_consumer_step(tmp_path: Path, version: str):
    """Qualified-identity releases keep step-scoped freshness tracking."""
    workflow = {
        "version": version,
        "name": f"consume-freshness-step-scope-v{version.replace('.', '_')}",
        "artifacts": _artifact_registry(),
        "steps": [
            {
                **_publish_step("ReviewImplVsPlan", "artifacts/work/c0-review.md"),
                "id": "review_impl_vs_plan",
            },
            {
                "name": "ReviewPlanLevelIssues",
                "id": "review_plan_level_issues",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ReviewImplVsPlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "command": ["bash", "-lc", "echo plan-review"],
            },
            {
                "name": "FixIssues",
                "id": "fix_issues",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ReviewImplVsPlan"],
                        "policy": "latest_successful",
                        "freshness": "since_last_consume",
                    }
                ],
                "command": ["bash", "-lc", "echo fix-issues"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow, on_error="continue")

    assert state["steps"]["ReviewPlanLevelIssues"]["exit_code"] == 0
    assert state["steps"]["FixIssues"]["exit_code"] == 0
    consumes = persisted.get("artifact_consumes", {}).get("root.fix_issues", {})
    assert consumes.get("execution_log") == 1


def test_consume_missing_producer_output_fails_with_contract_violation(tmp_path: Path):
    """Consumer fails with contract_violation when producer did not publish a successful version."""
    workflow = {
        "version": "1.2",
        "name": "consume-missing",
        "artifacts": _artifact_registry(),
        "steps": [
            {
                "name": "ExecutePlan",
                "command": ["bash", "-lc", "exit 1"],
                "expected_outputs": [
                    {
                        "name": "execution_log_path",
                        "path": "state/execution_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "required": False,
                    }
                ],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewImplVsPlan",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "command": ["bash", "-lc", "echo should-not-run"],
            },
        ],
    }

    state, _persisted = _run_workflow(tmp_path, workflow, on_error="continue")
    review = state["steps"]["ReviewImplVsPlan"]

    assert review["exit_code"] == 2
    assert review["error"]["type"] == "contract_violation"


def test_scalar_publish_records_typed_value(tmp_path: Path):
    """Scalar artifact publish stores typed value (integer) in publication ledger."""
    workflow = {
        "version": "1.2",
        "name": "scalar-publish-ledger",
        "artifacts": _scalar_artifact_registry(),
        "steps": [
            _publish_scalar_step("RunChecks", 3),
        ],
    }

    _final, persisted = _run_workflow(tmp_path, workflow)
    versions = persisted.get("artifact_versions", {}).get("failed_count", [])

    assert len(versions) == 1
    assert versions[0]["version"] == 1
    assert versions[0]["producer"] == "RunChecks"
    assert versions[0]["value"] == 3
    assert isinstance(versions[0]["value"], int)


def test_scalar_consume_enforces_freshness(tmp_path: Path):
    """Scalar consumes honor since_last_consume freshness using published versions."""
    workflow = {
        "version": "1.2",
        "name": "scalar-consume-freshness",
        "artifacts": _scalar_artifact_registry(),
        "steps": [
            _publish_scalar_step("RunChecks", 2),
            {
                "name": "ReviewA",
                "consumes": [
                    {
                        "artifact": "failed_count",
                        "producers": ["RunChecks"],
                        "policy": "latest_successful",
                        "freshness": "since_last_consume",
                    }
                ],
                "command": ["bash", "-lc", "echo review-a"],
            },
            {
                "name": "ReviewB",
                "consumes": [
                    {
                        "artifact": "failed_count",
                        "producers": ["RunChecks"],
                        "policy": "latest_successful",
                        "freshness": "since_last_consume",
                    }
                ],
                "command": ["bash", "-lc", "echo review-b"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow, on_error="continue")
    review_a = state["steps"]["ReviewA"]
    review_b = state["steps"]["ReviewB"]

    assert review_a["exit_code"] == 0
    assert review_b["exit_code"] == 2
    assert review_b["error"]["type"] == "contract_violation"
    assert review_b["error"]["context"]["reason"] == "stale_artifact"

    consumes = persisted.get("artifact_consumes", {}).get("ReviewA", {})
    assert consumes.get("failed_count") == 1


def test_for_each_nested_publish_records_artifact_versions(tmp_path: Path):
    """Nested loop steps that publish must record artifact versions for downstream consumers."""
    workflow = {
        "version": "1.2",
        "name": "for-each-publish-dataflow",
        "artifacts": _artifact_registry(),
        "steps": [
            {
                "name": "LoopPublish",
                "for_each": {
                    "items": ["one"],
                    "steps": [
                        {
                            "name": "ProduceInLoop",
                            "command": [
                                "bash",
                                "-lc",
                                (
                                    "mkdir -p state artifacts/work && "
                                    "printf 'artifacts/work/from-loop.md\\n' > state/execution_log_path.txt && "
                                    "printf 'from loop\\n' > artifacts/work/from-loop.md"
                                ),
                            ],
                            "expected_outputs": [
                                {
                                    "name": "execution_log_path",
                                    "path": "state/execution_log_path.txt",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ],
                            "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
                        }
                    ],
                },
            },
            {
                "name": "ReviewAfterLoop",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ProduceInLoop"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "command": ["bash", "-lc", "cat state/execution_log_path.txt"],
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow, on_error="continue")

    assert state["steps"]["ReviewAfterLoop"]["exit_code"] == 0
    assert state["steps"]["ReviewAfterLoop"]["output"].strip() == "artifacts/work/from-loop.md"

    versions = persisted.get("artifact_versions", {}).get("execution_log", [])
    assert len(versions) == 1
    assert versions[0]["producer"] == "ProduceInLoop"


def test_for_each_v2_qualified_lineage_uses_iteration_step_ids(tmp_path: Path):
    """v2.0 for-each lineage should key producers/consumers by qualified internal step ids."""
    workflow = {
        "version": "2.0",
        "name": "for-each-qualified-lineage",
        "artifacts": _artifact_registry(),
        "steps": [
            {
                "name": "LoopPublish",
                "id": "loop_publish",
                "for_each": {
                    "items": ["one", "two"],
                    "steps": [
                        {
                            "name": "ProduceInLoop",
                            "id": "produce_in_loop",
                            "command": [
                                "bash",
                                "-lc",
                                (
                                    "mkdir -p state artifacts/work && "
                                    "printf 'artifacts/work/from-loop-${item}.md\\n' > state/execution_log_path.txt && "
                                    "printf 'from ${item}\\n' > artifacts/work/from-loop-${item}.md"
                                ),
                            ],
                            "expected_outputs": [
                                {
                                    "name": "execution_log_path",
                                    "path": "state/execution_log_path.txt",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ],
                            "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
                        },
                        {
                            "name": "ReviewInLoop",
                            "id": "review_in_loop",
                            "consumes": [
                                {
                                    "artifact": "execution_log",
                                    "policy": "latest_successful",
                                    "freshness": "since_last_consume",
                                }
                            ],
                            "command": ["bash", "-lc", "cat state/execution_log_path.txt"],
                        },
                    ],
                },
            },
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow, on_error="continue")

    assert state["steps"]["LoopPublish[0].ReviewInLoop"]["exit_code"] == 0
    assert state["steps"]["LoopPublish[1].ReviewInLoop"]["exit_code"] == 0

    versions = persisted.get("artifact_versions", {}).get("execution_log", [])
    assert [entry["producer"] for entry in versions] == [
        "root.loop_publish#0.produce_in_loop",
        "root.loop_publish#1.produce_in_loop",
    ]

    consumes = persisted.get("artifact_consumes", {})
    assert consumes["root.loop_publish#0.review_in_loop"]["execution_log"] == 1
    assert consumes["root.loop_publish#1.review_in_loop"]["execution_log"] == 2


def test_for_each_nested_consume_enforces_contracts(tmp_path: Path):
    """Nested loop steps should enforce consume freshness constraints per iteration."""
    workflow = {
        "version": "1.2",
        "name": "for-each-consume-dataflow",
        "artifacts": _artifact_registry(),
        "steps": [
            _publish_step("ExecutePlan", "artifacts/work/exec-plan.md"),
            {
                "name": "LoopReview",
                "for_each": {
                    "items": ["one", "two"],
                    "steps": [
                        {
                            "name": "ReviewInLoop",
                            "consumes": [
                                {
                                    "artifact": "execution_log",
                                    "producers": ["ExecutePlan"],
                                    "policy": "latest_successful",
                                    "freshness": "since_last_consume",
                                }
                            ],
                            "command": ["bash", "-lc", "echo run-review"],
                        }
                    ],
                },
            }
        ],
    }

    state, _persisted = _run_workflow(tmp_path, workflow, on_error="continue")
    review_0 = state["steps"]["LoopReview[0].ReviewInLoop"]
    review_1 = state["steps"]["LoopReview[1].ReviewInLoop"]

    assert review_0["exit_code"] == 0
    assert review_1["exit_code"] == 2
    assert review_1["error"]["type"] == "contract_violation"
    assert review_1["error"]["context"]["reason"] == "stale_artifact"


def test_enum_registry_allowed_is_enforced_at_publish_boundary(tmp_path: Path):
    """Registry enum constraints must reject published values outside allowed set."""
    workflow = {
        "version": "1.2",
        "name": "enum-registry-enforcement",
        "artifacts": {
            "review_decision": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["APPROVE"],
            }
        },
        "steps": [
            {
                "name": "WriteDecision",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'REVISE\\n' > state/review_decision.txt",
                ],
                "expected_outputs": [
                    {
                        "name": "review_decision",
                        "path": "state/review_decision.txt",
                        "type": "enum",
                        "allowed": ["APPROVE", "REVISE"],
                    }
                ],
                "publishes": [{"artifact": "review_decision", "from": "review_decision"}],
            }
        ],
    }

    state, persisted = _run_workflow(tmp_path, workflow, on_error="continue")
    decision_step = state["steps"]["WriteDecision"]

    assert decision_step["exit_code"] == 2
    assert decision_step["error"]["type"] == "contract_violation"
    assert decision_step["error"]["context"]["reason"] == "invalid_enum_value"
    assert persisted.get("artifact_versions", {}).get("review_decision", []) == []


def test_v13_consume_bundle_writes_resolved_artifacts_json(tmp_path: Path):
    """consume_bundle writes resolved consumed artifacts to a single JSON file."""
    workflow = {
        "version": "1.3",
        "name": "consume-bundle-write",
        "artifacts": _artifact_registry(),
        "steps": [
            _publish_step("ExecutePlan", "artifacts/work/latest-execution-log.md"),
            {
                "name": "ReviewImplVsPlan",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "consume_bundle": {
                    "path": "state/consumes/review_impl_vs_plan.json",
                },
                "command": ["bash", "-lc", "cat state/consumes/review_impl_vs_plan.json"],
            },
        ],
    }

    state, _persisted = _run_workflow(tmp_path, workflow)
    review = state["steps"]["ReviewImplVsPlan"]

    assert review["exit_code"] == 0
    bundle = json.loads((tmp_path / "state" / "consumes" / "review_impl_vs_plan.json").read_text())
    assert bundle == {
        "execution_log": "artifacts/work/latest-execution-log.md",
    }


def test_v13_consume_bundle_include_writes_subset_only(tmp_path: Path):
    """consume_bundle.include limits materialized JSON keys to selected artifacts."""
    artifacts_registry = _artifact_registry()
    artifacts_registry.update(_scalar_artifact_registry())
    workflow = {
        "version": "1.3",
        "name": "consume-bundle-include-subset",
        "artifacts": artifacts_registry,
        "steps": [
            _publish_step("ExecutePlan", "artifacts/work/latest-execution-log.md"),
            _publish_scalar_step("RunChecks", 3),
            {
                "name": "ReviewImplVsPlan",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                    {
                        "artifact": "failed_count",
                        "producers": ["RunChecks"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                ],
                "consume_bundle": {
                    "path": "state/consumes/review_impl_vs_plan.json",
                    "include": ["execution_log"],
                },
                "command": ["bash", "-lc", "cat state/consumes/review_impl_vs_plan.json"],
            },
        ],
    }

    state, _persisted = _run_workflow(tmp_path, workflow)
    review = state["steps"]["ReviewImplVsPlan"]

    assert review["exit_code"] == 0
    bundle = json.loads((tmp_path / "state" / "consumes" / "review_impl_vs_plan.json").read_text())
    assert bundle == {
        "execution_log": "artifacts/work/latest-execution-log.md",
    }


def test_v13_consume_bundle_not_written_when_consume_contract_fails(tmp_path: Path):
    """consume_bundle file is not written when consume preflight fails."""
    workflow = {
        "version": "1.3",
        "name": "consume-bundle-no-write-on-failure",
        "artifacts": _artifact_registry(),
        "steps": [
            {
                "name": "ReviewImplVsPlan",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    }
                ],
                "consume_bundle": {
                    "path": "state/consumes/review_impl_vs_plan.json",
                },
                "command": ["bash", "-lc", "echo should-not-run"],
            },
        ],
    }

    state, _persisted = _run_workflow(tmp_path, workflow, on_error="continue")
    review = state["steps"]["ReviewImplVsPlan"]

    assert review["exit_code"] == 2
    assert review["error"]["type"] == "contract_violation"
    assert not (tmp_path / "state" / "consumes" / "review_impl_vs_plan.json").exists()
