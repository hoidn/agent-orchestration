"""Tests for runtime live notes over provider transport output."""

import json
from pathlib import Path

from orchestrator.observability.live_notes import LiveAgentNoteObserver


class _FakeProviderResult:
    def __init__(self, stdout=b"live note\n", stderr=b"", exit_code=0, error=None):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.duration_ms = 1
        self.error = error


class _FakeProviderExecutor:
    def __init__(self, result=None):
        self.prepare_calls = 0
        self.prompts = []
        self.result = result or _FakeProviderResult()

    def prepare_invocation(self, *args, **kwargs):
        self.prepare_calls += 1
        self.prompts.append(kwargs.get("prompt_content"))
        return object(), None

    def execute(self, invocation):
        return self.result


def test_live_agent_note_observer_writes_markdown_and_metadata(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-live"
    transport = run_root / "provider_sessions" / "root.step__v1.transport.log"
    transport.parent.mkdir(parents=True)
    transport.write_text(
        '{"type":"assistant.message","text":"working on the implementation"}\n',
        encoding="utf-8",
    )
    provider_executor = _FakeProviderExecutor()
    observer = LiveAgentNoteObserver(
        aggregate_run_root=run_root,
        provider_executor=provider_executor,
        provider_name="cheap_summary",
        interval_sec=60,
        timeout_sec=10,
        max_tail_chars=200,
        source="transport",
    )

    wrote = observer.emit_once(
        step_name="ExecuteImplementation",
        step_id="root.step",
        visit_count=1,
        transport_spool_path=transport,
    )

    summaries = run_root / "summaries"
    metadata = json.loads((summaries / "live-current-step.json").read_text(encoding="utf-8"))
    assert wrote is True
    assert (summaries / "live-current-step.md").read_text(encoding="utf-8") == "live note\n"
    assert metadata["schema"] == "orchestrator_live_agent_note/v1"
    assert metadata["step_name"] == "ExecuteImplementation"
    assert metadata["step_id"] == "root.step"
    assert metadata["visit_count"] == 1
    assert metadata["provider"] == "cheap_summary"
    assert metadata["source_transport_path"] == "provider_sessions/root.step__v1.transport.log"
    assert str(run_root) not in json.dumps(metadata)
    assert provider_executor.prepare_calls == 1


def test_live_agent_note_observer_clears_stale_error_after_success(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-live"
    transport = run_root / "provider_sessions" / "root.step__v1.transport.log"
    summaries = run_root / "summaries"
    transport.parent.mkdir(parents=True)
    summaries.mkdir(parents=True)
    transport.write_text("provider recovered and is writing a note\n", encoding="utf-8")
    (summaries / "live-current-step.error.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note_error/v1",
                "step_name": "ExecuteImplementation",
                "step_id": "root.step",
                "visit_count": 1,
                "provider": "claude_haiku_summary",
                "stage": "execute",
                "error": {"message": "live note provider exited 1"},
            }
        ),
        encoding="utf-8",
    )
    observer = LiveAgentNoteObserver(
        aggregate_run_root=run_root,
        provider_executor=_FakeProviderExecutor(),
        provider_name="claude_haiku_summary",
        interval_sec=60,
        timeout_sec=10,
        max_tail_chars=200,
        source="transport",
    )

    wrote = observer.emit_once(
        step_name="ExecuteImplementation",
        step_id="root.step",
        visit_count=1,
        transport_spool_path=transport,
    )

    assert wrote is True
    assert not (summaries / "live-current-step.error.json").exists()


def test_live_agent_note_observer_uses_tmux_tail_when_available(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-live"
    transport = run_root / "provider_sessions" / "root.step__v1.transport.log"
    transport.parent.mkdir(parents=True)
    transport.write_text(
        '{"type":"assistant.message","text":"transport fallback text"}\n',
        encoding="utf-8",
    )
    provider_executor = _FakeProviderExecutor()
    observer = LiveAgentNoteObserver(
        aggregate_run_root=run_root,
        provider_executor=provider_executor,
        provider_name="claude_haiku_summary",
        interval_sec=60,
        timeout_sec=10,
        max_tail_chars=200,
        tmux_capture=lambda max_chars: "tmux pane says currently editing docs\n",
    )

    wrote = observer.emit_once(
        step_name="ExecuteImplementation",
        step_id="root.step",
        visit_count=1,
        transport_spool_path=transport,
    )

    metadata = json.loads((run_root / "summaries" / "live-current-step.json").read_text(encoding="utf-8"))
    assert wrote is True
    assert metadata["provider"] == "claude_haiku_summary"
    assert metadata["source_kind"] == "tmux_pane"
    assert "source_transport_path" not in metadata
    assert "tmux pane says currently editing docs" in provider_executor.prompts[0]
    assert "transport fallback text" not in provider_executor.prompts[0]


def test_live_agent_note_observer_records_provider_failure_stderr(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-live"
    transport = run_root / "provider_sessions" / "root.step__v1.transport.log"
    transport.parent.mkdir(parents=True)
    transport.write_text("provider is still thinking\n", encoding="utf-8")
    provider_executor = _FakeProviderExecutor(
        _FakeProviderResult(
            stdout=b"",
            stderr=b"You've hit your limit \xc2\xb7 resets 2:50am (America/Los_Angeles)\n",
            exit_code=1,
        )
    )
    observer = LiveAgentNoteObserver(
        aggregate_run_root=run_root,
        provider_executor=provider_executor,
        provider_name="claude_haiku_summary",
        interval_sec=60,
        timeout_sec=10,
        max_tail_chars=200,
        source="transport",
    )

    wrote = observer.emit_once(
        step_name="ExecuteImplementation",
        step_id="root.step",
        visit_count=1,
        transport_spool_path=transport,
    )

    payload = json.loads((run_root / "summaries" / "live-current-step.error.json").read_text(encoding="utf-8"))
    assert wrote is False
    assert payload["stage"] == "execute"
    assert payload["error"]["message"] == "live note provider exited 1"
    assert payload["error"]["exit_code"] == 1
    assert "You've hit your limit" in payload["error"]["stderr"]
