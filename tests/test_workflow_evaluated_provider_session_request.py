"""The evaluated provider launcher forwards a session request and observation handle without changing ordinary calls."""
from __future__ import annotations

from concurrent.futures import Future

import pytest

from orchestrator.providers.control import ProviderExecutionControl
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderSessionMode, ProviderSessionRequest
from orchestrator.workflow.evaluated.effect_inputs import _provider_delivery_name
from orchestrator.workflow.evaluated.providers import ResolvedProviderInput, launch_provider, provider_delivery_name_for_template
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.agent_session_shims import install_agent_shims, shim_requests

NODE = {"k": "perform", "class": "provider", "provider": "codex", "prompt": {"template": "t", "fills": []},
        "inputs": [], "dependencies": None, "policy": {}, "contract": {"kind": "output_bundle", "payload": {}},
        "result": {"kind": "record", "name": "R", "fields": [{"name": "ok", "type": {"kind": "primitive", "name": "Bool"}}]}}


def _resolved(text="prompt body") -> ResolvedProviderInput:
    return ResolvedProviderInput(prompt=text, policy={"model": "m", "effort": "low", "timeout_sec": 20}, input_parts={}, expected_outputs=[])


def _spy(monkeypatch):
    calls = []
    prepare = ProviderExecutor.prepare_invocation

    def spy(self, *args, **kwargs):
        calls.append(kwargs)
        return prepare(self, *args, **kwargs)
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", spy)
    return calls


def _launch(root, monkeypatch, **extra):
    install_agent_shims(root / "bin", monkeypatch, codex_home=root / "codex", claude_home=root / "claude",
                        plan={"codex": [{"mode": "success", "result": {"ok": True}}]})
    (root / "attempt").mkdir()
    attempt_files = WorkspaceFiles(root / "attempt")
    workspace_files = WorkspaceFiles(root)
    try:
        return launch_provider(NODE, _resolved(), "workflow:main::run / x",
            executor=ProviderExecutor(root, ProviderRegistry(), provider_observation_enabled=False),
            attempt_files=attempt_files, workspace_files=workspace_files, result_path="attempt/result.json", **extra)
    finally:
        attempt_files.close()
        workspace_files.close()


def test_ordinary_launch_keeps_session_request_none_and_base_command(tmp_path, monkeypatch) -> None:
    calls = _spy(monkeypatch)
    execution = _launch(tmp_path, monkeypatch)
    assert calls[0]["session_request"] is None and calls[0]["provider_session_dir"] is None
    assert execution.exit_code == 0 and execution.provider_session is None
    assert "--json" not in shim_requests(tmp_path)[0]["argv"]


def test_session_launch_selects_fresh_command_and_exposes_the_session(tmp_path, monkeypatch) -> None:
    calls = _spy(monkeypatch)
    execution = _launch(tmp_path, monkeypatch, session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH))
    assert calls[0]["session_request"].mode is ProviderSessionMode.FRESH
    assert execution.provider_session["session_id"] == shim_requests(tmp_path)[0]["session"]
    assert "--json" in shim_requests(tmp_path)[0]["argv"]
    assert (tmp_path / "attempt" / "prompt.txt").exists() and (tmp_path / "attempt" / "stdout.txt").exists()


def test_control_is_forwarded_and_binds_the_child_process_group(tmp_path, monkeypatch) -> None:
    # The control freezes its terminal result only once the caller's attached execution Future completes.
    control, completion = ProviderExecutionControl(), Future()
    completion.set_running_or_notify_cancel()
    control.attach_execution_future(completion)
    execution = _launch(tmp_path, monkeypatch, session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH), control=control)
    completion.set_result(execution)
    assert execution.exit_code == 0 and control.terminal_result is not None and control.terminal_result.pgid is not None


def test_preopened_observation_handle_receives_display_and_is_not_finalized(tmp_path, monkeypatch) -> None:
    class Handle:
        def __init__(self):
            self.chunks, self.finalized, self.health = [], 0, 0

        def append_display(self, data):
            self.chunks.append(data)

        def check_health(self):
            self.health += 1

        def finalize(self):
            self.finalized += 1
    handle = Handle()
    _launch(tmp_path, monkeypatch, session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH), observation_handle=handle)
    assert b"".join(handle.chunks) != b"" and handle.finalized == 0


@pytest.mark.parametrize("name", ["codex", "claude_unrestricted_workspace", "omp"])
def test_delivery_name_is_structural_and_matches_the_ordinary_path(name) -> None:
    ordinary = _provider_delivery_name({"provider": name}, None, "id")
    assert provider_delivery_name_for_template(ProviderRegistry().get(name)) == ordinary
