"""Real Codex proof for the controlled session cancel/resume boundary."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any

import pytest

from orchestrator.providers import (
    ProviderExecutionControl,
    ProviderExecutionResult,
    ProviderExecutor,
    ProviderInvocation,
    ProviderParams,
    ProviderRegistry,
    ProviderSessionMode,
    ProviderSessionRequest,
)
from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e


_IDENTITY_TIMEOUT_SEC = 90.0
_EXECUTION_TIMEOUT_SEC = 180
_JOIN_TIMEOUT_SEC = 15.0
_CANCELLATION_GRACE_SEC = 5.0


def _start_controlled_execution(
    executor: ProviderExecutor,
    invocation: ProviderInvocation,
    control: ProviderExecutionControl,
    *,
    cwd: Path,
) -> tuple[threading.Thread, dict[str, Any]]:
    """Attach completion authority before allowing controlled execution."""
    completion: Future[ProviderExecutionResult] = Future()
    assert completion.set_running_or_notify_cancel() is True
    control.attach_execution_future(completion)
    outcome: dict[str, Any] = {}

    def _run() -> None:
        try:
            result = executor.execute(
                invocation,
                cwd=cwd,
                control=control,
            )
            outcome["result"] = result
            completion.set_result(result)
        except BaseException as exc:  # pragma: no cover - surfaced on join
            outcome["exception"] = exc
            completion.set_exception(exc)

    thread = threading.Thread(
        target=_run,
        name="e2e-codex-controlled-execution",
        daemon=True,
    )
    thread.start()
    return thread, outcome


def _wait_for_preterminal_identity(
    control: ProviderExecutionControl,
) -> str:
    deadline = time.monotonic() + _IDENTITY_TIMEOUT_SEC
    while time.monotonic() < deadline:
        snapshot = control.session_snapshot
        if snapshot is not None and snapshot.status in {"ambiguous", "invalid"}:
            pytest.fail(
                "Codex exposed an unusable preterminal session identity: "
                f"{snapshot.status}"
            )
        if (
            control.state == "BOUND"
            and snapshot is not None
            and snapshot.status == "unique"
            and len(snapshot.session_ids) == 1
            and not snapshot.terminal_seen
        ):
            return snapshot.session_ids[0]
        if control.terminal_result is not None:
            pytest.fail(
                "Codex completed before exposing one canonical preterminal "
                "session identity"
            )
        time.sleep(0.01)
    pytest.fail(
        "Codex did not expose one canonical preterminal session identity "
        f"within {_IDENTITY_TIMEOUT_SEC:.0f} seconds"
    )


def _join_execution(
    thread: threading.Thread,
    outcome: dict[str, Any],
    *,
    timeout: float,
) -> ProviderExecutionResult:
    thread.join(timeout=timeout)
    assert not thread.is_alive(), "controlled provider execution did not terminate"
    if "exception" in outcome:
        raise outcome["exception"]
    assert "result" in outcome, "controlled provider execution returned no result"
    result = outcome["result"]
    assert isinstance(result, ProviderExecutionResult)
    return result


def _cleanup_execution(
    control: ProviderExecutionControl | None,
    thread: threading.Thread | None,
) -> None:
    """Best-effort cancellation plus a hard fallback for assertion failures."""
    if control is None or thread is None:
        return

    terminal = control.terminal_result
    if thread.is_alive() or terminal is None:
        terminal = control.cancel_and_reap(grace=_CANCELLATION_GRACE_SEC)
    thread.join(timeout=_JOIN_TIMEOUT_SEC)

    if (
        terminal is not None
        and terminal.pgid is not None
        and not terminal.pgid_empty
    ):
        try:
            os.killpg(terminal.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        thread.join(timeout=_JOIN_TIMEOUT_SEC)

    assert not thread.is_alive(), (
        "controlled provider execution survived final cleanup"
    )
    if terminal is not None and terminal.pgid is not None:
        try:
            os.killpg(terminal.pgid, 0)
        except ProcessLookupError:
            return
        pytest.fail("controlled provider process group survived final cleanup")


@pytest.mark.e2e
def test_real_codex_thread_identity_cancel_and_resume(tmp_path: Path) -> None:
    """Cancel a real preterminal Codex turn, then resume its exact identity."""
    skip_if_no_e2e()
    skip_if_no_cli("codex")
    skip_if_no_cli("git")

    workspace = tmp_path / "codex-session-control"
    workspace.mkdir()
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=workspace,
        check=True,
        capture_output=True,
    )

    registry = ProviderRegistry()
    executor = ProviderExecutor(workspace, registry)
    fresh_control: ProviderExecutionControl | None = None
    fresh_thread: threading.Thread | None = None
    resume_control: ProviderExecutionControl | None = None
    resume_thread: threading.Thread | None = None

    try:
        fresh_invocation, fresh_error = executor.prepare_invocation(
            "codex",
            ProviderParams(),
            {},
            (
                "Work read-only in this repository. Before answering, use the "
                "shell to wait for thirty seconds. Then provide a brief draft. "
                "Do not create, edit, or delete any file."
            ),
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.FRESH,
            ),
            timeout_sec=_EXECUTION_TIMEOUT_SEC,
        )
        assert fresh_error is None
        assert fresh_invocation is not None
        assert fresh_invocation.command_variant == "fresh_command"

        fresh_control = ProviderExecutionControl()
        fresh_thread, fresh_outcome = _start_controlled_execution(
            executor,
            fresh_invocation,
            fresh_control,
            cwd=workspace,
        )
        session_id = _wait_for_preterminal_identity(fresh_control)

        cancelled = fresh_control.cancel_and_reap(
            grace=_CANCELLATION_GRACE_SEC,
        )
        fresh_result = _join_execution(
            fresh_thread,
            fresh_outcome,
            timeout=_JOIN_TIMEOUT_SEC,
        )

        assert cancelled.disposition == "cancelled"
        assert cancelled.term_sent is True
        assert cancelled.leader_reaped is True
        assert cancelled.pgid_empty is True
        assert cancelled.capture_threads_joined is True
        assert cancelled.execution_joined is True
        assert cancelled.final_identity_valid is True
        assert cancelled.proof_complete is True
        assert cancelled.final_session_snapshot is not None
        assert cancelled.final_session_snapshot.status == "unique"
        assert cancelled.final_session_snapshot.session_ids == (session_id,)
        assert cancelled.final_session_snapshot.terminal_seen is False
        assert fresh_result.classification == "cancelled_provisional"
        assert fresh_result.is_promotable is False
        assert fresh_result.provider_session is None

        resume_invocation, resume_error = executor.prepare_invocation(
            "codex",
            ProviderParams(),
            {},
            (
                "Correct the interrupted turn now. Do not repeat the delay. "
                "Return a brief, non-empty final answer without creating, "
                "editing, or deleting files."
            ),
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id=session_id,
            ),
            timeout_sec=_EXECUTION_TIMEOUT_SEC,
        )
        assert resume_error is None
        assert resume_invocation is not None
        assert resume_invocation.command_variant == "resume_command"
        assert session_id in resume_invocation.command

        resume_control = ProviderExecutionControl()
        resume_thread, resume_outcome = _start_controlled_execution(
            executor,
            resume_invocation,
            resume_control,
            cwd=workspace,
        )
        resume_result = _join_execution(
            resume_thread,
            resume_outcome,
            timeout=_EXECUTION_TIMEOUT_SEC + _JOIN_TIMEOUT_SEC,
        )
        resume_terminal = resume_control.terminal_result

        assert resume_terminal is not None
        assert resume_terminal.disposition == "natural_exit"
        assert resume_terminal.leader_reaped is True
        assert resume_terminal.pgid_empty is True
        assert resume_terminal.capture_threads_joined is True
        assert resume_terminal.execution_joined is True
        assert resume_terminal.final_identity_valid is True
        assert resume_terminal.proof_complete is True
        assert resume_terminal.final_session_snapshot is not None
        assert resume_terminal.final_session_snapshot.status == "unique"
        assert resume_terminal.final_session_snapshot.session_ids == (
            session_id,
        )
        assert resume_terminal.final_session_snapshot.terminal_seen is True
        assert resume_result.classification == "normal"
        assert resume_result.exit_code == 0
        assert resume_result.error is None
        assert resume_result.is_promotable is True
        assert resume_result.provider_session is not None
        assert resume_result.provider_session["session_id"] == session_id
        assert resume_result.stdout.strip()
        assert resume_result.provider_session["normalized_stdout"].strip()
        assert not (workspace / ".orchestrate").exists()
    finally:
        _cleanup_execution(resume_control, resume_thread)
        _cleanup_execution(fresh_control, fresh_thread)
