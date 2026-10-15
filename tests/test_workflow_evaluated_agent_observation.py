"""D6/R2: one read-only view per agent instance across its turns; ordinary calls keep one pane each; programs without
agents keep observation disabled; observation failures and crash/resume never change execution or dispatch."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from orchestrator.providers.observation import ProviderObservationError, ProviderObservationManager
from orchestrator.workflow.evaluated.agent_turns import AgentViews
from tests.agent_session_shims import install_agent_shims, shim_requests
from tests.test_provider_observation import _FakeObservationBackend
from tests.test_workflow_evaluated_agent_turns import PLAN, SOURCE, fixture, memo_of, turns
from tests.test_workflow_evaluated_invalidate import _cli

ROOT = Path(__file__).parents[1]

# Test-only driver: replaces the module-level backend factory in-process (the kill-point hook pattern). The fake backend
# hands out `%pane-N` targets and leaves the display files as the pane contents; `broken` raises on server start.
# With STOP_RECORD set it also dies (exit 75) right after appending that record for STOP_TURN.
OBSERVE = r'''import os, sys
from orchestrator.workflow.evaluated import agent_turns, attempts, runtime
from tests.test_provider_observation import _FakeObservationBackend
backend = _FakeObservationBackend()
if os.environ["OBSERVATION_BACKEND"] == "broken":
    backend.start_error = RuntimeError("no tmux here")
runtime.observation_backend = lambda: backend
if "STOP_RECORD" in os.environ:
    append = runtime.append_record
    def stop(path, record, **kwargs):
        entry = append(path, record, **kwargs)
        if record["record"] == os.environ["STOP_RECORD"] and os.environ["STOP_TURN"] in record.get("identity", ""):
            os._exit(75)
        return entry
    attempts.append_record = runtime.append_record = agent_turns.append_record = stop
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''

MIXED = SOURCE.replace(
    "(b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60)))",
    "(b2 (provider-result reviewer :prompt (execute :text a2.text) :timeout-sec 60))"
    " (plain (provider-result providers.codex :prompt (execute :text a2.text) :timeout-sec 60)))").replace("b2)))", "plain)))")


def _observed(root, backend, *argv, env=None):
    return subprocess.run([sys.executable, "-c", OBSERVE, *argv], cwd=root, capture_output=True, text=True, check=False,
                          env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1",
                               "OBSERVATION_BACKEND": backend, **(env or {})})


def _views(run_root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted((run_root / "provider-observation" / "display").glob("*.display"))}


def _install(tmp_path, monkeypatch, plan=PLAN):
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude", plan=plan)


def test_agent_views_open_one_handle_per_agent_with_turn_and_idle_boundaries(tmp_path) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    views = AgentViews(manager)
    first = views.handle_for("run / a", "run / t1", 1)
    views.idle("run / a")
    assert views.handle_for("run / a", "run / t2", 1) is first and views.handle_for("run / b", "run / u1", 1) is not first
    views.close()
    assert len(backend.open_calls) == 2 and first.transcript_path.read_bytes().count(b"--- turn") == 2
    assert b"--- idle ---" in first.transcript_path.read_bytes()


def test_agent_views_without_manager_or_with_broken_backend_return_no_handle(tmp_path) -> None:
    assert AgentViews(None).handle_for("run / a", "run / t1", 1) is None
    backend = _FakeObservationBackend()
    backend.open_error = ProviderObservationError("pane_allocation_failed")
    views = AgentViews(ProviderObservationManager(tmp_path, backend=backend))
    assert views.handle_for("run / a", "run / t1", 1) is None
    views.idle("run / a")
    views.close()


def test_each_agent_has_one_view_across_its_turns_and_ordinary_calls_keep_one_pane(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch, {"claude": PLAN["claude"], "codex": [*PLAN["codex"], {"mode": "success", "result": {"notes": ["plain"]}}]})
    run = _observed(tmp_path, "fake", "run", *fixture(tmp_path, MIXED))
    assert run.returncode == 0, run.stderr
    run_root, *_ = memo_of(tmp_path)
    views = _views(run_root)
    assert len(views) == 3                                  # designer view, reviewer view, one pane for `plain`
    agent_views = [v for v in views.values() if b"--- turn" in v]
    assert len(agent_views) == 2
    assert all(v.count(b"--- turn") == 2 and v.count(b"--- idle ---") == 2 for v in agent_views)
    assert len(shim_requests(tmp_path)) == 5
    assert "orc-observe-" in run.stderr                     # transient attach coordinates logged, never persisted


def test_agent_free_evaluated_run_keeps_observation_disabled(tmp_path, monkeypatch) -> None:
    """R2: a program without agents constructs no manager (2.35-2.37 behaviour unchanged)."""
    from tests.test_workflow_evaluated_providers import SOURCE as PLAIN_SOURCE, _fixture
    _fixture(tmp_path, PLAIN_SOURCE)
    monkeypatch.setenv("PATH", str(tmp_path / "bin") + os.pathsep + os.environ["PATH"])
    run = _observed(tmp_path, "fake", "run", "main.orc", "--source-root", str(tmp_path), "--provider-externs-file",
                    "providers.json", "--prompt-externs-file", "prompts.json", "--input", "message=typed input")
    assert run.returncode == 0, run.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    assert not (run_root / "provider-observation").exists()


def test_crash_and_resume_opens_new_views_without_redispatch(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch)
    stopped = _observed(tmp_path, "fake", "run", *fixture(tmp_path), env={"STOP_RECORD": "settled", "STOP_TURN": "/ b1"})
    assert stopped.returncode == 75, stopped.stderr
    run_root, *_ = memo_of(tmp_path)
    first = _views(run_root)
    assert len(first) == 2
    resumed = _observed(tmp_path, "fake", "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    after = _views(run_root)
    assert set(first) <= set(after) and len(after) == 4    # new views for the resumed process; old streams retained
    assert len(shim_requests(tmp_path)) == 4
    _r, _a, classes, memo = memo_of(tmp_path)
    assert all(v["attempt"] == 1 for v in turns(memo, classes).values())


def test_observation_failure_never_changes_execution(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch)
    run = _observed(tmp_path, "broken", "run", *fixture(tmp_path))
    assert run.returncode == 0, run.stderr
    _r, _a, classes, memo = memo_of(tmp_path)
    assert set(turns(memo, classes)) == {"a1", "b1", "a2", "b2"} and len(shim_requests(tmp_path)) == 4


def test_views_never_enter_memo_state_or_report(tmp_path, monkeypatch) -> None:
    _install(tmp_path, monkeypatch)
    assert _observed(tmp_path, "fake", "run", *fixture(tmp_path)).returncode == 0
    run_root, *_ = memo_of(tmp_path)
    assert _views(run_root)
    report = _cli(tmp_path, "report", "--run-id", run_root.name, "--format", "json")
    assert report.returncode == 0, report.stderr
    text = (run_root / "memo.jsonl").read_text() + (run_root / "state.json").read_text() + report.stdout
    assert "%pane" not in text and "orc-observe" not in text and "provider-observation" not in text
