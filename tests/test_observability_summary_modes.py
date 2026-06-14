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
        self.prepare_contexts = []
        self.prepare_kwargs = []

    def prepare_invocation(self, *args, **kwargs):
        self.prepare_contexts.append(kwargs.get("context"))
        self.prepare_kwargs.append(kwargs)
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


def test_summary_observer_default_timeout_allows_longer_generated_summaries(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-default-timeout"
    provider_executor = _FakeProviderExecutor()
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=provider_executor,
        provider_name="summary_provider",
        mode="sync",
    )

    observer.emit("StepA", {"step": "StepA", "status": "completed"})

    assert provider_executor.prepare_kwargs[0]["timeout_sec"] == 300


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


def test_phase_performance_provider_summary_uses_kind_specific_files(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-profile"
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=_FakeProviderExecutor(result=_FakeProviderResult(stdout=b"profile summary")),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
        profile="phase-performance",
    )

    observer.emit(
        "ExecuteImplementation",
        {"step": {"name": "ExecuteImplementation", "summary_kind": "provider", "output": {"status": "completed"}}},
        summary_kind="provider",
    )

    assert (run_root / "summaries" / "ExecuteImplementation.provider.snapshot.json").exists()
    assert (run_root / "summaries" / "ExecuteImplementation.provider.summary.md").read_text() == "profile summary\n"


def test_summary_observer_uses_visit_identity_for_distinct_files(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-visit-identity"
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=_FakeProviderExecutor(result=_FakeProviderResult(stdout=b"profile summary")),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
        profile="phase-performance",
    )

    observer.emit(
        "ReviewImplementation",
        {
            "step": {
                "name": "ReviewImplementation",
                "summary_kind": "provider",
                "output": {
                    "status": "completed",
                    "step_id": "root.review_loop#0.review_implementation",
                    "visit_count": 1,
                },
            }
        },
        summary_kind="provider",
    )
    observer.emit(
        "ReviewImplementation",
        {
            "step": {
                "name": "ReviewImplementation",
                "summary_kind": "provider",
                "output": {
                    "status": "completed",
                    "step_id": "root.review_loop#1.review_implementation",
                    "visit_count": 1,
                },
            }
        },
        summary_kind="provider",
    )

    index = json.loads((run_root / "summaries" / "index.json").read_text(encoding="utf-8"))
    entries = index["entries"]
    assert len(entries) == 2
    assert entries[0]["summary_path"] != entries[1]["summary_path"]
    assert entries[0]["step_id"] == "root.review_loop#0.review_implementation"
    assert entries[1]["step_id"] == "root.review_loop#1.review_implementation"
    assert entries[0]["visit_count"] == 1
    for entry in entries:
        assert (run_root / entry["summary_path"]).exists()


def test_summary_observer_writes_index_entries(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-index"
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=_FakeProviderExecutor(),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
        profile="phase-performance",
    )

    observer.emit(
        "PlanPhase",
        {"step": {"name": "PlanPhase", "summary_kind": "phase", "output": {"status": "completed"}}},
        summary_kind="phase",
    )

    index = json.loads((run_root / "summaries" / "index.json").read_text())
    assert index["schema"] == "orchestrator_summary_index/v1"
    assert index["entries"][0]["step_name"] == "PlanPhase"
    assert index["entries"][0]["kind"] == "phase"
    assert index["entries"][0]["profile"] == "phase-performance"
    assert index["entries"][0]["summary_path"] == "summaries/PlanPhase.phase.summary.md"


def test_summary_observer_updates_root_hub_for_call_frame_summary(tmp_path: Path):
    aggregate_root = tmp_path / ".orchestrate" / "runs" / "run-hub"
    frame_root = aggregate_root / "call_frames" / "root.some_call__visit__1"
    observer = SummaryObserver(
        run_root=frame_root,
        aggregate_run_root=aggregate_root,
        provider_executor=_FakeProviderExecutor(result=_FakeProviderResult(stdout=b"nested summary")),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
        profile="phase-performance",
    )

    observer.emit(
        "NestedProvider",
        {"step": {"name": "NestedProvider", "summary_kind": "provider", "output": {"status": "completed"}}},
        summary_kind="provider",
    )

    root_index = json.loads((aggregate_root / "summaries" / "index.json").read_text())
    assert root_index["schema"] == "orchestrator_summary_index/v1"
    assert root_index["run_root"] == str(aggregate_root)
    assert root_index["entries"][0]["step_name"] == "NestedProvider"
    assert root_index["entries"][0]["frame_root"] == "call_frames/root.some_call__visit__1"
    assert (
        root_index["entries"][0]["summary_path"]
        == "call_frames/root.some_call__visit__1/summaries/NestedProvider.provider.summary.md"
    )

    readme = (aggregate_root / "summaries" / "README.md").read_text()
    assert "NestedProvider" in readme
    assert "../call_frames/root.some_call__visit__1/summaries/NestedProvider.provider.summary.md" in readme

    run_summary = (aggregate_root / "summaries" / "run-summary.md").read_text()
    assert "NestedProvider" in run_summary
    assert "provider" in run_summary

    local_index = json.loads((frame_root / "summaries" / "index.json").read_text())
    assert local_index["entries"][0]["summary_path"] == "summaries/NestedProvider.provider.summary.md"


def test_root_hub_links_summary_error_when_generation_fails(tmp_path: Path):
    aggregate_root = tmp_path / ".orchestrate" / "runs" / "run-hub-error"
    frame_root = aggregate_root / "call_frames" / "frame"
    failed = _FakeProviderResult(
        exit_code=9,
        stdout=b"",
        stderr=b"summary failed",
        error={"type": "execution_error", "message": "summary failed"},
    )
    observer = SummaryObserver(
        run_root=frame_root,
        aggregate_run_root=aggregate_root,
        provider_executor=_FakeProviderExecutor(result=failed),
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
        profile="phase-performance",
    )

    observer.emit(
        "NestedProvider",
        {"step": {"name": "NestedProvider", "summary_kind": "provider", "output": {"status": "completed"}}},
        summary_kind="provider",
    )

    root_index = json.loads((aggregate_root / "summaries" / "index.json").read_text())
    assert root_index["entries"][0]["summary_path"] is None
    assert (
        root_index["entries"][0]["error_path"]
        == "call_frames/frame/summaries/NestedProvider.provider.error.json"
    )
    readme = (aggregate_root / "summaries" / "README.md").read_text()
    assert "[summary error](../call_frames/frame/summaries/NestedProvider.provider.error.json)" in readme


def test_summary_observer_passes_invocation_context_to_provider(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-context"
    provider_executor = _FakeProviderExecutor()
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=provider_executor,
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
        invocation_context={"context": {"workflow_model": "gpt-5.2", "workflow_effort": "high"}},
    )

    observer.emit("StepA", {"step": {"name": "StepA", "output": {"status": "completed"}}})

    assert provider_executor.prepare_contexts == [
        {"context": {"workflow_model": "gpt-5.2", "workflow_effort": "high"}}
    ]


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


def test_repeat_until_body_provider_writes_summary_hub_entry(tmp_path: Path):
    workflow_file = tmp_path / "workflow.yaml"
    workflow_file.write_text(
        """
version: "2.14"
name: repeat-provider-summary
providers:
  worker:
    command:
      - bash
      - -lc
      - >-
        mkdir -p state artifacts/work &&
        printf '{"status":"DONE","report":"artifacts/work/report.md"}\\n' > state/result.json &&
        printf 'report\\n' > artifacts/work/report.md
    input_mode: stdin
  summary:
    command: ["bash", "-lc", "cat >/dev/null; printf 'loop provider summary\\n'"]
    input_mode: stdin
steps:
  - name: ReviewLoop
    repeat_until:
      id: iteration
      max_iterations: 2
      outputs:
        status:
          kind: scalar
          type: enum
          allowed: ["CONTINUE", "DONE"]
          from:
            ref: self.steps.RunOnce.artifacts.status
        report:
          type: relpath
          under: artifacts/work
          must_exist_target: true
          from:
            ref: self.steps.RunOnce.artifacts.report
      condition:
        compare:
          left:
            ref: self.outputs.status
          op: eq
          right: DONE
      steps:
        - name: RunOnce
          provider: worker
          output_bundle:
            path: state/result.json
            fields:
              - name: status
                json_pointer: /status
                type: enum
                allowed: ["CONTINUE", "DONE"]
              - name: report
                json_pointer: /report
                type: relpath
                under: artifacts/work
                must_exist_target: true
""".strip()
        + "\n"
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_file)
    state_manager = StateManager(tmp_path, run_id="run-repeat-summary")
    state_manager.initialize("workflow.yaml", {})

    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=tmp_path,
        state_manager=state_manager,
        debug=False,
        observability={
            "step_summaries": {
                "enabled": True,
                "mode": "sync",
                "provider": "summary",
                "timeout_sec": 30,
                "best_effort": True,
                "max_input_chars": 12000,
                "profile": "phase-performance",
            }
        },
    )

    final_state = executor.execute(on_error="stop")

    assert final_state["steps"]["ReviewLoop"]["status"] == "completed"
    index = json.loads((state_manager.run_root / "summaries" / "index.json").read_text(encoding="utf-8"))
    provider_entries = [entry for entry in index["entries"] if entry["kind"] == "provider"]
    assert len(provider_entries) == 1
    provider_entry = provider_entries[0]
    assert provider_entry["step_name"] == "RunOnce"
    assert provider_entry["step_id"] == "root.reviewloop#0.iteration.runonce"
    assert str(provider_entry["summary_path"]).startswith(
        "summaries/RunOnce.provider.root.reviewloop_0.iteration.runonce"
    )
    assert str(provider_entry["summary_path"]).endswith(".summary.md")


def test_summary_observer_writes_provider_free_typed_terminal_entry(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-typed-terminal"
    provider_executor = _FakeProviderExecutor()
    observer = SummaryObserver(
        run_root=run_root,
        provider_executor=provider_executor,
        provider_name="summary_provider",
        mode="sync",
        timeout_sec=30,
        best_effort=True,
        max_input_chars=12000,
        profile="phase-performance",
    )

    payload = {
        "schema_id": "workflow_lisp_observability_summary.v1",
        "authority": "observability_only",
        "paths": {
            "json": "summaries/typed-terminal-summary.json",
            "markdown": "summaries/typed-terminal-summary.md",
            "report": "summaries/observability_summary_report.json",
        },
        "terminal_value": {"status": "BLOCKED"},
    }
    report = {
        "schema_id": "workflow_lisp_observability_summary_report.v1",
        "status": "pass",
        "diagnostics": {"errors": [], "warnings": []},
    }

    observer.emit_typed_terminal_summary(payload=payload, markdown="typed terminal summary\n", report=report)

    index = json.loads((run_root / "summaries" / "index.json").read_text(encoding="utf-8"))
    entry = index["entries"][0]
    assert entry["step_name"] == "workflow-terminal"
    assert entry["kind"] == "typed_terminal"
    assert entry["profile"] == "workflow-lisp-c2"
    assert entry["authority"] == "observability_only"
    assert entry["summary_path"] == "summaries/typed-terminal-summary.md"
    assert entry["report_path"] == "summaries/observability_summary_report.json"
    assert (run_root / "summaries" / "README.md").exists()
    assert (run_root / "summaries" / "run-summary.md").exists()
    assert provider_executor.prepare_kwargs == []
