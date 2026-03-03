"""Tests for summary observer async/sync runtime modes."""

import json
import time
from pathlib import Path

from orchestrator.loader import WorkflowLoader
from orchestrator.observability.summary import SummaryObserver
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


class _FakeProviderResult:
    def __init__(self, exit_code=0, stdout=b"summary", stderr=b"", duration_ms=1, error=None):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration_ms = duration_ms
        self.error = error


class _FakeProviderExecutor:
    def __init__(self, delay_sec=0.0, result=None):
        self.delay_sec = delay_sec
        self.result = result or _FakeProviderResult()
        self.last_prepare_kwargs = None

    def prepare_invocation(self, *args, **kwargs):
        self.last_prepare_kwargs = kwargs
        return object(), None

    def execute(self, invocation):
        if self.delay_sec:
            time.sleep(self.delay_sec)
        return self.result


def _wait_for(path: Path, timeout_sec: float = 2.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return False


def test_summary_observer_async_dispatch_non_blocking(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-async"
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=_FakeProviderExecutor(delay_sec=0.2),
        provider_name="summary_provider",
        mode="async",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
    )

    start = time.time()
    observer.emit("StepA", {"step": "StepA", "status": "completed"})
    elapsed = time.time() - start

    assert elapsed < 0.1
    assert _wait_for(run_root / "summaries" / "StepA.summary.md")


def test_summary_observer_sync_is_deterministic_and_blocking(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-sync"
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=_FakeProviderExecutor(delay_sec=0.15),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
    )

    start = time.time()
    observer.emit("StepA", {"step": "StepA", "status": "completed"})
    elapsed = time.time() - start

    assert elapsed >= 0.12
    assert (run_root / "summaries" / "StepA.summary.md").exists()


def test_summary_observer_failure_writes_error_and_does_not_raise_when_best_effort(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-fail"
    failed = _FakeProviderResult(
        exit_code=9,
        stdout=b"",
        stderr=b"boom",
        error={"type": "execution_error", "message": "boom", "context": {}},
    )
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=_FakeProviderExecutor(result=failed),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
    )

    observer.emit("StepA", {"step": "StepA", "status": "completed"})

    error_file = run_root / "summaries" / "StepA.error.json"
    assert error_file.exists()
    payload = json.loads(error_file.read_text())
    assert payload["exit_code"] == 9


def test_summary_observer_timeout_writes_error_for_both_modes(tmp_path: Path):
    timeout_result = _FakeProviderResult(
        exit_code=124,
        stdout=b"",
        stderr=b"",
        error={"type": "timeout", "message": "timed out", "context": {"timeout_sec": 1}},
    )

    run_root_async = tmp_path / ".orchestrate" / "runs" / "run-timeout-async"
    async_observer = SummaryObserver(
        run_root=run_root_async,
        provider_executor=_FakeProviderExecutor(result=timeout_result),
        provider_name="summary_provider",
        mode="async",
        timeout_sec=1,
        best_effort=True,
        max_input_chars=12000,
    )
    async_observer.emit("StepA", {"step": "StepA", "status": "completed"})
    assert _wait_for(run_root_async / "summaries" / "StepA.error.json")

    run_root_sync = tmp_path / ".orchestrate" / "runs" / "run-timeout-sync"
    sync_observer = SummaryObserver(
        run_root=run_root_sync,
        provider_executor=_FakeProviderExecutor(result=timeout_result),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=1,
        best_effort=True,
        max_input_chars=12000,
    )
    sync_observer.emit("StepA", {"step": "StepA", "status": "completed"})
    assert (run_root_sync / "summaries" / "StepA.error.json").exists()


def test_summary_failures_do_not_change_step_result_and_dataflow_state(tmp_path: Path):
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "1.3"
name: summary-failure-safe
providers:
  bad_summary:
    command: ["bash", "-lc", "exit 9"]
    input_mode: "argv"
steps:
  - name: StepA
    command: ["bash", "-lc", "echo hello"]
    output_capture: text
""".strip()
        + "\n"
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-summary-safe")
    state_manager.initialize("workflow.yaml", {})

    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=tmp_path,
        state_manager=state_manager,
        debug=False,
        observability={
            "step_summaries": {
                "enabled": True,
                "mode": "async",
                "provider": "bad_summary",
                "timeout_sec": 30,
                "best_effort": True,
                "max_input_chars": 12000,
            }
        },
    )

    final_state = executor.execute(on_error="stop")

    assert final_state["steps"]["StepA"]["status"] == "completed"
    assert final_state["steps"]["StepA"]["exit_code"] == 0
    assert final_state["artifact_versions"] == {}
    assert final_state["artifact_consumes"] == {}
    assert _wait_for(state_manager.run_root / "summaries" / "StepA.error.json")


def test_summary_prompt_requests_detailed_structured_output(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-prompt-shape"
    fake_executor = _FakeProviderExecutor()
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=fake_executor,
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=200,
    )

    observer.emit(
        "ProviderStep",
        {
            "run_id": "run-prompt-shape",
            "workflow": "demo",
            "step": {
                "name": "ProviderStep",
                "type": "provider",
                "input": {"provider": "codex", "prompt": "Do work"},
                "output": {
                    "status": "completed",
                    "exit_code": 0,
                    "duration_ms": 42,
                    "artifacts": {
                        "execution_session_log_path": "artifacts/work/latest-execution-session-log.md"
                    },
                },
            },
            "padding": "x" * 300,
        },
    )

    assert fake_executor.last_prepare_kwargs is not None
    prompt = fake_executor.last_prepare_kwargs["prompt_content"]
    assert "post-mortem for one workflow step" in prompt
    assert "Do not use markdown tables." in prompt
    assert "Distinguish facts from inferences." in prompt
    assert "### Outcome and Plan Conformance" in prompt
    assert "### Mistakes and Failure Modes" in prompt
    assert "### Recovery and Adaptation" in prompt
    assert "### Stalls and Blockers" in prompt
    assert "### Evidence and Confidence" in prompt
    assert "### Recommended Next Actions" in prompt
    assert "Assess whether the step conformed to declared intent/plan" in prompt
    assert "Explain recovery attempts and whether they actually resolved issues." in prompt
    assert "Snapshot truncated: yes" in prompt
    assert "```json" in prompt
