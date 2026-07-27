"""Bounded private process execution for the lean-pilot evaluator."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path


class _EvaluatorProcessError(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _wait_for_group_exit(
    process: subprocess.Popen[bytes],
    *,
    deadline: float,
) -> bool:
    while True:
        process.poll()
        if not _process_group_exists(process.pid):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.005, remaining))


def _signal_group(process_group_id: int, value: signal.Signals) -> None:
    try:
        os.killpg(process_group_id, value)
    except ProcessLookupError:
        pass
    except OSError as exc:
        raise _EvaluatorProcessError("quiescence") from exc


def _quiesce_process_group(
    process: subprocess.Popen[bytes],
    *,
    grace_milliseconds: int,
) -> bool:
    grace_seconds = grace_milliseconds / 1_000
    if not _process_group_exists(process.pid):
        process.poll()
        return True
    _signal_group(process.pid, signal.SIGTERM)
    if _wait_for_group_exit(
        process,
        deadline=time.monotonic() + grace_seconds,
    ):
        return True
    _signal_group(process.pid, signal.SIGKILL)
    return _wait_for_group_exit(
        process,
        deadline=time.monotonic() + grace_seconds,
    )


def _run_evaluator_process(
    *,
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
    timeout_milliseconds: int,
    quiescence_grace_milliseconds: int,
) -> subprocess.CompletedProcess[bytes]:
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        except OSError as exc:
            raise _EvaluatorProcessError("launch") from exc
        timed_out = False
        try:
            process.wait(timeout=timeout_milliseconds / 1_000)
        except subprocess.TimeoutExpired:
            timed_out = True
        if not _quiesce_process_group(
            process,
            grace_milliseconds=quiescence_grace_milliseconds,
        ):
            raise _EvaluatorProcessError("quiescence")
        stdout.seek(0)
        stderr.seek(0)
        result = subprocess.CompletedProcess(
            args=list(command),
            returncode=process.returncode,
            stdout=stdout.read(),
            stderr=stderr.read(),
        )
    if timed_out:
        raise _EvaluatorProcessError("timeout")
    return result
