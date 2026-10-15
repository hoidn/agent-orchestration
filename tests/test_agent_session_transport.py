"""Fresh, resume, overlap, interruption and locator loss through the real executor and store adapters."""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from orchestrator.providers.control import ProviderExecutionControl
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.native_store import native_store_adapter
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderParams, ProviderSessionMode, ProviderSessionRequest
from tests.agent_session_shims import install_agent_shims, shim_requests

TEMPLATES = {"codex": "codex", "claude": "claude_unrestricted_workspace"}


def _executor(root: Path) -> ProviderExecutor:
    return ProviderExecutor(root, ProviderRegistry(), provider_observation_enabled=False)


def _run(root, tool, request, result_path, timeout=20):
    executor = _executor(root)
    invocation, error = executor.prepare_invocation(provider_name=TEMPLATES[tool], params=ProviderParams(params={}, input_file=None),
        context={}, prompt_content=f"turn for {result_path}", session_request=request,
        env={"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(result_path)}, secrets=None, timeout_sec=timeout,
        provider_call_policy={"model": "m", "effort": "low"}, provider_session_dir=None, provider_session_identity=None)
    assert error is None, error
    return invocation, executor.execute(invocation, cwd=root, stream_output=False, session_runtime=None)


@pytest.mark.parametrize("tool", ["codex", "claude"])
def test_fresh_then_resume_advance_one_native_store(tmp_path, monkeypatch, tool) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={tool: [{"mode": "success", "result": {"ok": True}}] * 2})
    invocation, first = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r1.json")
    assert invocation.command_variant == "fresh_command" and first.exit_code == 0, first.error
    sid = first.provider_session["session_id"]
    adapter = native_store_adapter(invocation.metadata_mode)
    path = adapter.locate(sid).path
    head1 = adapter.head(path)
    assert head1.open_turn is False and adapter.completed_turn(path, after=None, prompt_marker="r1.json") is not None
    invocation2, second = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id=sid), tmp_path / "r2.json")
    assert invocation2.command_variant == "resume_command" and second.exit_code == 0, second.error
    assert second.provider_session["session_id"] == sid
    head2 = adapter.head(path)
    assert head2.position.end_line > head1.position.end_line
    assert adapter.completed_turn(path, after=head1.position, prompt_marker="r2.json").position == head2.position
    assert [r["session"] for r in shim_requests(tmp_path)] == [sid, sid]
    assert json.loads((tmp_path / "r2.json").read_text()) == {"ok": True}


@pytest.mark.parametrize("tool", ["codex", "claude"])
def test_overlapping_external_append_moves_the_head_before_our_turn(tmp_path, monkeypatch, tool) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={tool: [{"mode": "success", "result": {}}, {"mode": "overlap", "result": {}}]})
    invocation, first = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r1.json")
    sid = first.provider_session["session_id"]
    adapter = native_store_adapter(invocation.metadata_mode)
    path = adapter.locate(sid).path
    before = adapter.head(path).position
    _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id=sid), tmp_path / "r2.json")
    # two completed turns follow `before`: the exact-completion test rejects the append as not uniquely bound
    assert adapter.completed_turn(path, after=before, prompt_marker="r2.json") is None
    assert adapter.head(path).position.end_line > before.end_line


@pytest.mark.parametrize("tool", ["codex", "claude"])
def test_interrupted_turn_leaves_an_open_head_and_no_terminal(tmp_path, monkeypatch, tool) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={tool: [{"mode": "interrupted", "result": {}}]})
    invocation, result = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r1.json")
    assert result.exit_code != 0 and result.provider_session is None
    sid = shim_requests(tmp_path)[0]["session"]
    adapter = native_store_adapter(invocation.metadata_mode)
    head = adapter.head(adapter.locate(sid).path)
    assert head.open_turn is True and head.position is None
    assert not (tmp_path / "r1.json").exists()


@pytest.mark.parametrize("tool", ["codex", "claude"])
def test_lost_locator_is_rejected_by_the_native_cli_and_absent_from_the_store(tmp_path, monkeypatch, tool) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={tool: [{"mode": "lose-locator", "result": {}}]})
    sid = "00000000-0000-4000-8000-000000000000"
    invocation, result = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id=sid), tmp_path / "r.json")
    assert result.exit_code == 1 and result.provider_session is None
    assert native_store_adapter(invocation.metadata_mode).locate(sid).path is None


@pytest.mark.parametrize("mode, store_written", [("timeout", False), ("complete-then-hang", True)])
def test_timeout_reaps_the_process_tree_and_the_store_tells_the_two_cases_apart(tmp_path, monkeypatch, mode, store_written) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={"codex": [{"mode": mode, "result": {"ok": True}}]})
    invocation, result = _run(tmp_path, "codex", ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r.json", timeout=2)
    assert result.exit_code == 124 and result.error["type"] == "timeout"
    adapter = native_store_adapter(invocation.metadata_mode)
    requests = shim_requests(tmp_path)
    assert bool(requests) is store_written
    if store_written:
        head = adapter.head(adapter.locate(requests[0]["session"]).path)
        assert head.open_turn is False and head.position is not None and (tmp_path / "r.json").exists()


def test_nonzero_before_append_leaves_no_native_trace_and_linger_leaves_a_child(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={"codex": [{"mode": "nonzero-before-append", "result": {}}, {"mode": "linger", "result": {"ok": True}}]})
    _i, first = _run(tmp_path, "codex", ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r1.json")
    assert first.exit_code == 9 and not (tmp_path / "codex").exists() and shim_requests(tmp_path) == []
    control = ProviderExecutionControl()
    executor = _executor(tmp_path)
    invocation, error = executor.prepare_invocation(provider_name="codex", params=ProviderParams(params={}, input_file=None), context={},
        prompt_content="p", session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        env={"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(tmp_path / "r2.json")}, secrets=None, timeout_sec=20,
        provider_call_policy={"model": "m", "effort": "low"}, provider_session_dir=None, provider_session_identity=None)
    assert error is None
    with ThreadPoolExecutor(max_workers=1) as pool:     # the supervision coordinator's submit-then-attach pattern
        future = pool.submit(executor.execute, invocation, cwd=tmp_path, stream_output=False, session_runtime=None, control=control)
        control.attach_execution_future(future)
        second = future.result(timeout=120)
    terminal = control.cancel_and_reap(grace=0.5)
    # The CLI completed, but its forked grandchild outlived it: the executor records the lingering group, reaps it
    # and refuses the boundary rather than reporting a clean natural exit.
    assert second.error["type"] == "provider_cancellation_boundary_failed"
    assert terminal.natural_exit_with_lingering_group is True and terminal.pgid_empty is True
    with pytest.raises(ProcessLookupError):
        os.killpg(terminal.pgid, 0)
