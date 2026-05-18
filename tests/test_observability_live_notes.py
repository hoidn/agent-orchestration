"""Tests for runtime live notes over provider transport output."""

import json
from pathlib import Path

from orchestrator.observability.live_notes import LiveAgentNoteObserver


class _FakeProviderResult:
    def __init__(self, stdout=b"live note\n", exit_code=0, error=None):
        self.stdout = stdout
        self.stderr = b""
        self.exit_code = exit_code
        self.duration_ms = 1
        self.error = error


class _FakeProviderExecutor:
    def __init__(self):
        self.prepare_calls = 0

    def prepare_invocation(self, *args, **kwargs):
        self.prepare_calls += 1
        return object(), None

    def execute(self, invocation):
        return _FakeProviderResult()


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
