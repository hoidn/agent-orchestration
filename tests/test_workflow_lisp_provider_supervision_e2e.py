"""Public compile/run acceptance for Workflow Lisp provider supervision."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Mapping

import pytest

from orchestrator.providers import InputMode
from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.providers.types import ProviderInvocation


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "workflow_lisp" / "provider_supervision"
)
FIXTURE_FILES = (
    "provider_supervision_continue.orc",
    "providers.json",
    "prompts.json",
    "worker.md",
    "supervisor.md",
)
TARGET_2_16_DIGESTS_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "provider_peer_group"
    / "v1_2_16_artifact_digests.json"
)




class _ObservationHandle:
    def __init__(self, *, target: str, socket_path: Path) -> None:
        self.target = target
        self.socket_path = socket_path
        self.finalized = False

    def check_health(self) -> bool:
        return not self.finalized

    def finalize(self) -> None:
        self.finalized = True


class _ObservationManager:
    def __init__(self, _run_root: Path) -> None:
        self._index = 0
        self.handles: list[_ObservationHandle] = []
        self.closed = False

    def next_invocation_id(self) -> str:
        self._index += 1
        return f"invocation-{self._index}"

    def open_observation(
        self,
        *,
        invocation_id: str,
        member_id: str,
        turn_id: str,
    ) -> _ObservationHandle:
        del invocation_id
        handle = _ObservationHandle(
            target=f"pane:{member_id}:{turn_id}",
            socket_path=Path("/tmp/provider-supervision-e2e.sock"),
        )
        self.handles.append(handle)
        return handle

    def close(self) -> None:
        self.closed = True




@dataclass
class _FakeProviderRuntime:
    managers: list[_ObservationManager] = field(default_factory=list)
    prepared: list[ProviderInvocation] = field(default_factory=list)
    executed: list[ProviderInvocation] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)














def _install_fake_provider_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payloads: Mapping[str, str] | None = None,
) -> _FakeProviderRuntime:
    runtime = _FakeProviderRuntime()
    turn_payloads = {
        "worker_fresh": '"fresh-value"',
        "supervisor_directive": '{"variant":"CONTINUE"}',
        **dict(payloads or {}),
    }

    def manager_factory(run_root: Path) -> _ObservationManager:
        manager = _ObservationManager(run_root)
        runtime.managers.append(manager)
        return manager

    def prepare_invocation(
        _self: ProviderExecutor,
        *,
        provider_name: str,
        prompt_content: str,
        env: dict[str, str],
        session_request: object,
        timeout_sec: int,
        **_kwargs: object,
    ) -> tuple[ProviderInvocation, None]:
        invocation = ProviderInvocation(
            command=["fake-provider", provider_name],
            input_mode=InputMode.STDIN,
            prompt=prompt_content,
            env=env,
            timeout_sec=timeout_sec,
            session_request=session_request,
        )
        with runtime.lock:
            runtime.prepared.append(invocation)
        return invocation, None

    def execute_provider(
        _self: ProviderExecutor,
        invocation: ProviderInvocation,
        **_kwargs: object,
    ) -> ProviderExecutionResult:
        with runtime.lock:
            runtime.executed.append(invocation)
        supervision = invocation.metadata["provider_supervision"]
        output_path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        output_path.write_text(
            turn_payloads[supervision["turn_role"]],
            encoding="utf-8",
        )
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"observability only",
            stderr=b"",
            duration_ms=1,
        )

    monkeypatch.setattr(
        "orchestrator.workflow.executor.ProviderObservationManager",
        manager_factory,
    )
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare_invocation)
    monkeypatch.setattr(ProviderExecutor, "execute", execute_provider)
    return runtime
