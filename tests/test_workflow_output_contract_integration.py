"""Integration tests for expected_outputs enforcement in workflow execution."""

from types import SimpleNamespace
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow))
    return workflow_file


def test_command_step_fails_when_expected_output_missing(tmp_path: Path):
    """Missing expected output file converts a successful step into contract_violation."""
    workflow = {
        "version": "1.1.1",
        "name": "contract-missing",
        "steps": [{
            "name": "DraftPlan",
            "command": ["bash", "-lc", "echo done"],
            "expected_outputs": [{
                "name": "plan_pointer",
                "path": "state/plan_pointer.txt",
                "type": "relpath",
                "under": "docs/plans",
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(on_error="continue")

    result = state["steps"]["DraftPlan"]
    assert result["exit_code"] == 2
    assert result["status"] == "failed"
    assert result["error"]["type"] == "contract_violation"


def test_workflow_signature_binds_inputs_and_exports_outputs(tmp_path: Path):
    """v2.1 workflows should expose bound inputs and export validated workflow outputs."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    (tmp_path / "docs" / "tasks" / "task-a.md").write_text("# task\n")

    workflow = {
        "version": "2.1",
        "name": "workflow-signature-success",
        "inputs": {
            "task_path": {
                "kind": "relpath",
                "type": "relpath",
                "under": "docs/tasks",
                "must_exist_target": True,
            },
            "max_cycles": {
                "kind": "scalar",
                "type": "integer",
            },
        },
        "outputs": {
            "report_path": {
                "kind": "relpath",
                "type": "relpath",
                "under": "artifacts/reports",
                "must_exist_target": True,
                "from": {"ref": "root.steps.GenerateReport.artifacts.report_path"},
            },
            "cycles_used": {
                "kind": "scalar",
                "type": "integer",
                "from": {"ref": "root.steps.GenerateReport.artifacts.cycles_used"},
            },
        },
        "steps": [{
            "name": "GenerateReport",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state artifacts/reports && "
                "cp \"${inputs.task_path}\" artifacts/reports/report.md && "
                "printf 'artifacts/reports/report.md\\n' > state/report_path.txt && "
                "printf '%s\\n' \"${inputs.max_cycles}\" > state/cycles_used.txt",
            ],
            "expected_outputs": [
                {
                    "name": "report_path",
                    "path": "state/report_path.txt",
                    "type": "relpath",
                    "under": "artifacts/reports",
                    "must_exist_target": True,
                },
                {
                    "name": "cycles_used",
                    "path": "state/cycles_used.txt",
                    "type": "integer",
                },
            ],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(
        "workflow.yaml",
        bound_inputs={
            "task_path": "docs/tasks/task-a.md",
            "max_cycles": 4,
        },
    )

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["bound_inputs"] == {
        "task_path": "docs/tasks/task-a.md",
        "max_cycles": 4,
    }
    assert state["workflow_outputs"] == {
        "report_path": "artifacts/reports/report.md",
        "cycles_used": 4,
    }


def test_workflow_signature_relpath_boundaries_work_without_explicit_kind(tmp_path: Path):
    """Workflow signatures should accept relpath inputs/outputs with type: relpath alone."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    (tmp_path / "docs" / "tasks" / "task-a.md").write_text("# task\n")

    workflow = {
        "version": "2.1",
        "name": "workflow-signature-style-success",
        "inputs": {
            "task_path": {
                "type": "relpath",
                "under": "docs/tasks",
                "must_exist_target": True,
            },
        },
        "outputs": {
            "report_path": {
                "type": "relpath",
                "under": "artifacts/reports",
                "must_exist_target": True,
                "from": {"ref": "root.steps.GenerateReport.artifacts.report_path"},
            },
        },
        "steps": [{
            "name": "GenerateReport",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state artifacts/reports && "
                "cp \"${inputs.task_path}\" artifacts/reports/report.md && "
                "printf 'artifacts/reports/report.md\\n' > state/report_path.txt",
            ],
            "expected_outputs": [
                {
                    "name": "report_path",
                    "path": "state/report_path.txt",
                    "type": "relpath",
                    "under": "artifacts/reports",
                    "must_exist_target": True,
                },
            ],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(
        "workflow.yaml",
        bound_inputs={
            "task_path": "docs/tasks/task-a.md",
        },
    )

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "report_path": "artifacts/reports/report.md",
    }


def test_workflow_signature_preserves_exact_string_inputs_and_outputs(tmp_path: Path):
    """v2.10 workflow signatures preserve exact string scalar values end-to-end."""
    workflow = {
        "version": "2.10",
        "name": "workflow-signature-string-success",
        "inputs": {
            "resume_note": {
                "kind": "scalar",
                "type": "string",
            },
        },
        "outputs": {
            "resume_note": {
                "kind": "scalar",
                "type": "string",
                "from": {"ref": "root.steps.GenerateNote.artifacts.resume_note"},
            },
        },
        "steps": [{
            "name": "GenerateNote",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state && printf '%s' \"${inputs.resume_note}\" > state/resume_note.txt",
            ],
            "expected_outputs": [
                {
                    "name": "resume_note",
                    "path": "state/resume_note.txt",
                    "type": "string",
                },
            ],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(
        "workflow.yaml",
        bound_inputs={
            "resume_note": "  keep exact whitespace  ",
        },
    )

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["bound_inputs"] == {
        "resume_note": "  keep exact whitespace  ",
    }
    assert state["workflow_outputs"] == {
        "resume_note": "  keep exact whitespace  ",
    }


def test_workflow_input_binding_uses_typed_contract_definition_without_contract_raw_payloads(
    tmp_path: Path,
):
    """Workflow input binding should use typed contract definitions, not root raw fallback."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    (tmp_path / "docs" / "tasks" / "task-a.md").write_text("# task\n", encoding="utf-8")

    workflow = {
        "version": "2.1",
        "name": "workflow-signature-bound-input-contract",
        "inputs": {
            "task_path": {
                "kind": "relpath",
                "type": "relpath",
                "under": "docs/tasks",
                "must_exist_target": True,
            },
        },
        "steps": [{
            "name": "Noop",
            "command": ["bash", "-lc", "true"],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load_bundle(workflow_file)
    assert not hasattr(loaded.surface.inputs["task_path"], "raw")

    bound_inputs = bind_workflow_inputs(
        workflow_input_contracts(loaded),
        {"task_path": "docs/tasks/task-a.md"},
        tmp_path,
    )

    assert bound_inputs == {
        "task_path": "docs/tasks/task-a.md",
    }


def test_workflow_output_export_uses_bound_ir_contracts_when_legacy_refs_are_corrupted(tmp_path: Path):
    """Workflow output export should follow lowered IR bindings, not mutated legacy refs."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    (tmp_path / "docs" / "tasks" / "task-a.md").write_text("# task\n")

    workflow = {
        "version": "2.1",
        "name": "workflow-signature-bound-output-export",
        "inputs": {
            "task_path": {
                "kind": "relpath",
                "type": "relpath",
                "under": "docs/tasks",
                "must_exist_target": True,
            },
        },
        "outputs": {
            "report_path": {
                "kind": "relpath",
                "type": "relpath",
                "under": "artifacts/reports",
                "must_exist_target": True,
                "from": {"ref": "root.steps.GenerateReport.artifacts.report_path"},
            },
        },
        "steps": [{
            "name": "GenerateReport",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state artifacts/reports && "
                "cp \"${inputs.task_path}\" artifacts/reports/report.md && "
                "printf 'artifacts/reports/report.md\\n' > state/report_path.txt",
            ],
            "expected_outputs": [
                {
                    "name": "report_path",
                    "path": "state/report_path.txt",
                    "type": "relpath",
                    "under": "artifacts/reports",
                    "must_exist_target": True,
                },
            ],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)
    assert not hasattr(loaded.surface.outputs["report_path"], "raw")

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(
        "workflow.yaml",
        bound_inputs={
            "task_path": "docs/tasks/task-a.md",
        },
    )

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "report_path": "artifacts/reports/report.md",
    }


def test_workflow_output_export_uses_typed_contract_definition_without_ir_contract_raw_payloads(
    tmp_path: Path,
):
    """Workflow output export should validate against typed IR contracts, not root raw fallback."""
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    (tmp_path / "docs" / "tasks" / "task-a.md").write_text("# task\n", encoding="utf-8")

    workflow = {
        "version": "2.1",
        "name": "workflow-signature-bound-output-contract",
        "inputs": {
            "task_path": {
                "kind": "relpath",
                "type": "relpath",
                "under": "docs/tasks",
                "must_exist_target": True,
            },
        },
        "outputs": {
            "report_path": {
                "kind": "relpath",
                "type": "relpath",
                "under": "artifacts/reports",
                "must_exist_target": True,
                "from": {"ref": "root.steps.GenerateReport.artifacts.report_path"},
            },
        },
        "steps": [{
            "name": "GenerateReport",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state artifacts/reports && "
                "cp \"${inputs.task_path}\" artifacts/reports/report.md && "
                "printf 'artifacts/reports/report.md\\n' > state/report_path.txt",
            ],
            "expected_outputs": [
                {
                    "name": "report_path",
                    "path": "state/report_path.txt",
                    "type": "relpath",
                    "under": "artifacts/reports",
                    "must_exist_target": True,
                },
            ],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    assert not hasattr(loaded.ir.outputs["report_path"], "raw")
    assert not hasattr(loaded.surface.outputs["report_path"], "raw")

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize(
        "workflow.yaml",
        bound_inputs={
            "task_path": "docs/tasks/task-a.md",
        },
    )

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "report_path": "artifacts/reports/report.md",
    }


def test_workflow_output_export_fails_when_export_contract_is_invalid(tmp_path: Path):
    """Workflow output export should fail the run when the exported value violates its contract."""
    workflow = {
        "version": "2.1",
        "name": "workflow-signature-invalid-export",
        "outputs": {
            "report_path": {
                "kind": "relpath",
                "type": "relpath",
                "under": "artifacts/reports",
                "from": {"ref": "root.steps.GenerateReport.artifacts.report_path"},
            },
        },
        "steps": [{
            "name": "GenerateReport",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state docs/export && "
                "printf '# report\\n' > docs/export/outside.md && "
                "printf 'docs/export/outside.md\\n' > state/report_path.txt",
            ],
            "expected_outputs": [
                {
                    "name": "report_path",
                    "path": "state/report_path.txt",
                    "type": "relpath",
                }
            ],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["status"] == "failed"
    assert state["error"]["type"] == "contract_violation"
    assert state["error"]["context"]["scope"] == "workflow_outputs"


def test_command_step_persists_artifacts_when_contract_is_valid(tmp_path: Path):
    """Validated artifacts are persisted under steps.<name>.artifacts."""
    workflow = {
        "version": "1.1.1",
        "name": "contract-valid",
        "steps": [{
            "name": "DraftPlan",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state docs/plans && "
                "printf 'docs/plans/plan-a.md\\n' > state/plan_pointer.txt && "
                "printf '# plan\\n' > docs/plans/plan-a.md",
            ],
            "expected_outputs": [{
                "name": "plan_pointer",
                "path": "state/plan_pointer.txt",
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()
    result = state["steps"]["DraftPlan"]

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert result["artifacts"] == {"plan_pointer": "docs/plans/plan-a.md"}

    persisted = state_manager.load().to_dict()["steps"]["DraftPlan"]
    assert persisted["artifacts"] == {"plan_pointer": "docs/plans/plan-a.md"}


def test_command_step_can_disable_artifact_persistence_in_state(tmp_path: Path):
    """expected_outputs can be validated without duplicating artifact values in state.json."""
    workflow = {
        "version": "1.1.1",
        "name": "contract-valid-no-persist",
        "steps": [{
            "name": "SelectBacklogItem",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state docs/backlog && "
                "printf 'docs/backlog/item-001.md\\n' > state/backlog_item_path.txt && "
                "printf '# item\\n' > docs/backlog/item-001.md",
            ],
            "persist_artifacts_in_state": False,
            "expected_outputs": [{
                "name": "backlog_item_path",
                "path": "state/backlog_item_path.txt",
                "type": "relpath",
                "under": "docs/backlog",
                "must_exist_target": True,
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()
    result = state["steps"]["SelectBacklogItem"]

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert "artifacts" not in result

    persisted = state_manager.load().to_dict()["steps"]["SelectBacklogItem"]
    assert "artifacts" not in persisted


def test_provider_step_persists_artifacts_when_contract_is_valid(tmp_path: Path):
    """Provider steps are also gated by expected_outputs and persist artifacts."""
    workflow = {
        "version": "1.1.1",
        "name": "provider-contract-valid",
        "steps": [{
            "name": "Review",
            "provider": "codex",
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    executor.provider_executor.prepare_invocation = lambda *args, **kwargs: (SimpleNamespace(), None)

    def _fake_execute(_invocation, **_kwargs):
        (tmp_path / "state").mkdir(exist_ok=True)
        (tmp_path / "state" / "review_decision.txt").write_text("APPROVE\n")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.execute = _fake_execute

    state = executor.execute()
    result = state["steps"]["Review"]

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert result["artifacts"] == {"review_decision": "APPROVE"}


def test_provider_failure_preserves_original_error_and_skips_contract(tmp_path: Path):
    """Provider execution failures must not be replaced by contract_violation errors."""
    workflow = {
        "version": "1.1.1",
        "name": "provider-contract-failure-preserve",
        "steps": [{
            "name": "Review",
            "provider": "codex",
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    executor.provider_executor.prepare_invocation = lambda *args, **kwargs: (SimpleNamespace(), None)

    def _failing_execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=1,
            stdout=b"provider failed",
            stderr=b"boom",
            duration_ms=1,
            error={"type": "execution_failed", "message": "Provider execution failed"},
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.execute = _failing_execute

    state = executor.execute(on_error="continue")
    result = state["steps"]["Review"]

    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert result["error"]["type"] == "execution_failed"
    assert "artifacts" not in result
    assert result["error"]["type"] != "contract_violation"


def test_command_step_persists_artifacts_from_output_bundle(tmp_path: Path):
    """v1.3 output_bundle fields are validated and persisted as step artifacts."""
    workflow = {
        "version": "1.3",
        "name": "bundle-command-valid",
        "steps": [{
            "name": "AssessExecutionCompletion",
            "command": [
                "bash",
                "-lc",
                "mkdir -p artifacts/work docs/plans && "
                "printf '# plan\\n' > docs/plans/plan-a.md && "
                "printf '{\"plan_path\":\"docs/plans/plan-a.md\",\"failed_count\":0}\\n' > artifacts/work/summary.json",
            ],
            "output_bundle": {
                "path": "artifacts/work/summary.json",
                "fields": [
                    {
                        "name": "plan_path",
                        "json_pointer": "/plan_path",
                        "type": "relpath",
                        "under": "docs/plans",
                        "must_exist_target": True,
                    },
                    {
                        "name": "failed_count",
                        "json_pointer": "/failed_count",
                        "type": "integer",
                    },
                ],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()
    result = state["steps"]["AssessExecutionCompletion"]

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert result["artifacts"] == {
        "plan_path": "docs/plans/plan-a.md",
        "failed_count": 0,
    }


def test_repeat_until_output_bundle_path_resolves_loop_index(tmp_path: Path):
    """repeat_until body output_bundle paths can use loop variables."""
    workflow = {
        "version": "2.7",
        "name": "repeat-until-output-bundle-loop-path",
        "steps": [
            {
                "name": "ReviewLoop",
                "id": "review_loop",
                "repeat_until": {
                    "id": "iteration_body",
                    "max_iterations": 2,
                    "outputs": {
                        "loop_decision": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["DONE", "AGAIN"],
                            "from": {
                                "ref": "self.steps.WriteBundle.artifacts.loop_decision",
                            },
                        },
                    },
                    "condition": {
                        "compare": {
                            "left": {
                                "ref": "self.outputs.loop_decision",
                            },
                            "op": "eq",
                            "right": "DONE",
                        },
                    },
                    "steps": [
                        {
                            "name": "WriteBundle",
                            "id": "write_bundle",
                            "command": [
                                "bash",
                                "-lc",
                                "mkdir -p state/repeat/${loop.index} && "
                                "printf '{\"loop_decision\":\"DONE\"}\\n' "
                                "> state/repeat/${loop.index}/summary.json",
                            ],
                            "output_bundle": {
                                "path": "state/repeat/${loop.index}/summary.json",
                                "fields": [
                                    {
                                        "name": "loop_decision",
                                        "json_pointer": "/loop_decision",
                                        "type": "enum",
                                        "allowed": ["DONE", "AGAIN"],
                                    },
                                ],
                            },
                        },
                    ],
                },
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["ReviewLoop"]["artifacts"] == {"loop_decision": "DONE"}
    assert state["steps"]["ReviewLoop[0].WriteBundle"]["artifacts"] == {
        "loop_decision": "DONE",
    }


def test_command_step_output_bundle_contract_violation_sets_exit_2(tmp_path: Path):
    """Missing output_bundle file converts successful command to contract_violation."""
    workflow = {
        "version": "1.3",
        "name": "bundle-command-missing",
        "steps": [{
            "name": "AssessExecutionCompletion",
            "command": ["bash", "-lc", "echo done"],
            "output_bundle": {
                "path": "artifacts/work/summary.json",
                "fields": [{
                    "name": "status",
                    "json_pointer": "/status",
                    "type": "enum",
                    "allowed": ["COMPLETE", "INCOMPLETE", "BLOCKED"],
                }],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(on_error="continue")
    result = state["steps"]["AssessExecutionCompletion"]

    assert result["exit_code"] == 2
    assert result["status"] == "failed"
    assert result["error"]["type"] == "contract_violation"


def test_provider_step_persists_artifacts_from_output_bundle(tmp_path: Path):
    """Provider steps can satisfy deterministic contracts via output_bundle in v1.3."""
    workflow = {
        "version": "1.3",
        "name": "bundle-provider-valid",
        "steps": [{
            "name": "Review",
            "provider": "codex",
            "output_bundle": {
                "path": "artifacts/work/review.json",
                "fields": [{
                    "name": "review_decision",
                    "json_pointer": "/review_decision",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    executor.provider_executor.prepare_invocation = lambda *args, **kwargs: (SimpleNamespace(), None)

    def _fake_execute(_invocation, **_kwargs):
        (tmp_path / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
        (tmp_path / "artifacts" / "work" / "review.json").write_text('{"review_decision":"APPROVE"}\n')
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.execute = _fake_execute

    state = executor.execute()
    result = state["steps"]["Review"]

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert result["artifacts"] == {"review_decision": "APPROVE"}


def test_nonzero_exit_skips_output_bundle_validation(tmp_path: Path):
    """Failed process exit should preserve original failure and skip bundle validation."""
    workflow = {
        "version": "1.3",
        "name": "bundle-skip-on-failure",
        "steps": [{
            "name": "AssessExecutionCompletion",
            "command": ["bash", "-lc", "echo fail && exit 1"],
            "output_bundle": {
                "path": "artifacts/work/summary.json",
                "fields": [{
                    "name": "status",
                    "json_pointer": "/status",
                    "type": "enum",
                    "allowed": ["COMPLETE", "INCOMPLETE", "BLOCKED"],
                }],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(on_error="continue")
    result = state["steps"]["AssessExecutionCompletion"]

    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert "artifacts" not in result
    assert result.get("error", {}).get("type") != "contract_violation"
