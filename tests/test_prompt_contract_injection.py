"""Tests for deterministic output-contract prompt injection on provider steps."""

from pathlib import Path
from types import SimpleNamespace

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow))
    return workflow_file


def test_provider_expected_outputs_appends_contract_block_to_prompt(tmp_path: Path):
    """Provider steps append a deterministic output contract block by default."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review this patch.\n")

    workflow = {
        "version": "1.1.1",
        "name": "prompt-contract-default",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
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

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert "Output Contract" in captured["prompt"]
    assert "name: review_decision" in captured["prompt"]
    assert "path: state/review_decision.txt" in captured["prompt"]
    assert "type: enum" in captured["prompt"]


def test_output_contract_block_includes_guidance_fields(tmp_path: Path):
    """Output contract prompt suffix includes optional guidance annotations."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review this patch.\n")

    workflow = {
        "version": "1.1.1",
        "name": "prompt-contract-guidance",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
                "description": "Final review decision token.",
                "format_hint": "Uppercase single token.",
                "example": "APPROVE",
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
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

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert "description: Final review decision token." in captured["prompt"]
    assert "format_hint: Uppercase single token." in captured["prompt"]
    assert "example: APPROVE" in captured["prompt"]


def test_inject_output_contract_false_disables_prompt_suffix(tmp_path: Path):
    """Provider steps can disable output contract prompt suffix with inject_output_contract: false."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review this patch.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.1.1",
        "name": "prompt-contract-opt-out",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
            "inject_output_contract": False,
            "expected_outputs": [{
                "name": "review_decision",
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
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

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0
    assert captured["prompt"] == original_prompt
    assert "Output Contract" not in captured["prompt"]


def test_command_steps_ignore_inject_output_contract(tmp_path: Path):
    """inject_output_contract has no effect on command steps."""
    workflow = {
        "version": "1.1.1",
        "name": "command-ignore-inject-flag",
        "steps": [{
            "name": "DraftPlan",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state docs/plans && "
                "printf 'docs/plans/plan-a.md\\n' > state/plan_pointer.txt && "
                "printf '# plan\\n' > docs/plans/plan-a.md",
            ],
            "inject_output_contract": False,
            "expected_outputs": [{
                "name": "plan_path",
                "path": "state/plan_pointer.txt",
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["steps"]["DraftPlan"]["exit_code"] == 0
    assert state["steps"]["DraftPlan"]["artifacts"] == {"plan_path": "docs/plans/plan-a.md"}


def test_provider_consumes_appends_consumed_artifacts_block_by_default(tmp_path: Path):
    """Provider steps inject consumed artifacts block by default for v1.2 consumes."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "consumes-injection-default",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log"
                    ),
                ],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    expected_prefix = (
        "## Consumed Artifacts\n"
        "- execution_log: artifacts/work/execute.log\n"
        "Read these files before acting.\n"
    )
    assert captured["prompt"].startswith(expected_prefix)
    assert original_prompt in captured["prompt"]


def test_inject_consumes_false_disables_consumes_block(tmp_path: Path):
    """inject_consumes:false keeps provider prompt unchanged."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "consumes-injection-opt-out",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log"
                    ),
                ],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
                "inject_consumes": False,
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert captured["prompt"] == original_prompt


def test_consumes_injection_position_append_places_block_after_prompt(tmp_path: Path):
    """consumes_injection_position:append adds block after prompt body."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "consumes-injection-append",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log"
                    ),
                ],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
                "consumes_injection_position": "append",
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    expected_suffix = (
        "## Consumed Artifacts\n"
        "- execution_log: artifacts/work/execute.log\n"
        "Read these files before acting.\n"
    )
    assert captured["prompt"].startswith(original_prompt)
    assert captured["prompt"].endswith(expected_suffix)


def test_prompt_consumes_injects_only_selected_artifacts(tmp_path: Path):
    """prompt_consumes limits injected consumed-artifact lines to the selected subset."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "prompt-consumes-subset",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            "check_log": {
                "pointer": "state/check_log_path.txt",
                "type": "relpath",
                "under": "artifacts/checks",
                "must_exist_target": True,
            },
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work artifacts/checks && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'artifacts/checks/checks.log\\n' > state/check_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log && "
                        "printf 'checks\\n' > artifacts/checks/checks.log"
                    ),
                ],
                "expected_outputs": [
                    {
                        "name": "execution_log_path",
                        "path": "state/execution_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "check_log_path",
                        "path": "state/check_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/checks",
                        "must_exist_target": True,
                    },
                ],
                "publishes": [
                    {"artifact": "execution_log", "from": "execution_log_path"},
                    {"artifact": "check_log", "from": "check_log_path"},
                ],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                    {
                        "artifact": "check_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                ],
                "prompt_consumes": ["execution_log"],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert "- execution_log: artifacts/work/execute.log" in captured["prompt"]
    assert "- check_log: artifacts/checks/checks.log" not in captured["prompt"]


def test_prompt_consumes_includes_guidance_fields_for_selected_artifacts(tmp_path: Path):
    """Consumes injection includes optional guidance annotations for selected artifacts."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "prompt-consumes-guidance",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            "check_log": {
                "pointer": "state/check_log_path.txt",
                "type": "relpath",
                "under": "artifacts/checks",
                "must_exist_target": True,
            },
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work artifacts/checks && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'artifacts/checks/checks.log\\n' > state/check_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log && "
                        "printf 'checks\\n' > artifacts/checks/checks.log"
                    ),
                ],
                "expected_outputs": [
                    {
                        "name": "execution_log_path",
                        "path": "state/execution_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "check_log_path",
                        "path": "state/check_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/checks",
                        "must_exist_target": True,
                    },
                ],
                "publishes": [
                    {"artifact": "execution_log", "from": "execution_log_path"},
                    {"artifact": "check_log", "from": "check_log_path"},
                ],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                        "description": "Primary execution log for implementation work.",
                        "format_hint": "Workspace-relative .log path.",
                        "example": "artifacts/work/latest-execution.log",
                    },
                    {
                        "artifact": "check_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                        "description": "Targeted checks log.",
                    },
                ],
                "prompt_consumes": ["execution_log"],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert "- execution_log: artifacts/work/execute.log" in captured["prompt"]
    assert "description: Primary execution log for implementation work." in captured["prompt"]
    assert "format_hint: Workspace-relative .log path." in captured["prompt"]
    assert "example: artifacts/work/latest-execution.log" in captured["prompt"]
    assert "description: Targeted checks log." not in captured["prompt"]


def test_missing_prompt_consumes_injects_all_consumed_artifacts(tmp_path: Path):
    """Without prompt_consumes, consumes injection remains backward compatible (all artifacts)."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "prompt-consumes-back-compat",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            },
            "check_log": {
                "pointer": "state/check_log_path.txt",
                "type": "relpath",
                "under": "artifacts/checks",
                "must_exist_target": True,
            },
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work artifacts/checks && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'artifacts/checks/checks.log\\n' > state/check_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log && "
                        "printf 'checks\\n' > artifacts/checks/checks.log"
                    ),
                ],
                "expected_outputs": [
                    {
                        "name": "execution_log_path",
                        "path": "state/execution_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                    {
                        "name": "check_log_path",
                        "path": "state/check_log_path.txt",
                        "type": "relpath",
                        "under": "artifacts/checks",
                        "must_exist_target": True,
                    },
                ],
                "publishes": [
                    {"artifact": "execution_log", "from": "execution_log_path"},
                    {"artifact": "check_log", "from": "check_log_path"},
                ],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [
                    {
                        "artifact": "execution_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                    {
                        "artifact": "check_log",
                        "producers": ["ExecutePlan"],
                        "policy": "latest_successful",
                        "freshness": "any",
                    },
                ],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert "- execution_log: artifacts/work/execute.log" in captured["prompt"]
    assert "- check_log: artifacts/checks/checks.log" in captured["prompt"]


def test_prompt_consumes_empty_list_injects_no_consumed_artifacts_block(tmp_path: Path):
    """prompt_consumes: [] suppresses consumes prompt injection."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review implementation against plan.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "prompt-consumes-empty",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "execution_log": {
                "pointer": "state/execution_log_path.txt",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        },
        "steps": [
            {
                "name": "ExecutePlan",
                "command": [
                    "bash",
                    "-lc",
                    (
                        "mkdir -p state artifacts/work && "
                        "printf 'artifacts/work/execute.log\\n' > state/execution_log_path.txt && "
                        "printf 'execute\\n' > artifacts/work/execute.log"
                    ),
                ],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }],
                "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
                "prompt_consumes": [],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert captured["prompt"] == original_prompt


def test_provider_execute_falls_back_when_stream_output_kwarg_unsupported(tmp_path: Path):
    """Workflow executor should support custom execute(invocation) call shape without kwargs."""
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review implementation.\n")

    workflow = {
        "version": "1.1.1",
        "name": "provider-exec-compat",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "steps": [{
            "name": "Review",
            "provider": "mock_provider",
            "input_file": "prompts/review.md",
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    def _prepare_invocation(*args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt="Review implementation.\n"), None

    def _execute_without_kwargs(_invocation):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute_without_kwargs

    state = executor.execute()
    assert state["steps"]["Review"]["exit_code"] == 0


def test_provider_prompt_injection_renders_scalar_consumed_value(tmp_path: Path):
    """Scalar consumed artifacts render their values in provider prompt injection."""
    (tmp_path / "prompts").mkdir()
    original_prompt = "Review check outcomes.\n"
    (tmp_path / "prompts" / "review.md").write_text(original_prompt)

    workflow = {
        "version": "1.2",
        "name": "consumes-scalar-prompt-render",
        "providers": {
            "mock_provider": {
                "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                "input_mode": "stdin",
            }
        },
        "artifacts": {
            "failed_count": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "steps": [
            {
                "name": "RunChecks",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf '3\\n' > state/failed_count.txt",
                ],
                "expected_outputs": [{
                    "name": "failed_count",
                    "path": "state/failed_count.txt",
                    "type": "integer",
                }],
                "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
            },
            {
                "name": "ReviewPlan",
                "provider": "mock_provider",
                "input_file": "prompts/review.md",
                "consumes": [{
                    "artifact": "failed_count",
                    "producers": ["RunChecks"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    captured = {"prompt": ""}

    def _prepare_invocation(*args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content") or ""
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"]), None

    def _execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.prepare_invocation = _prepare_invocation
    executor.provider_executor.execute = _execute

    state = executor.execute()
    assert state["steps"]["ReviewPlan"]["exit_code"] == 0
    assert "- failed_count: 3" in captured["prompt"]
