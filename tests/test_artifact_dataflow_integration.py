"""Integration tests for v1.2 artifact publish/consume dataflow guarantees."""

from pathlib import Path

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
