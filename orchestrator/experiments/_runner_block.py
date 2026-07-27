"""Block persistence and orchestration for the lean-pilot runner."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Mapping

from . import _runner_apparatus as apparatus
from . import _runner_execution as execution
from . import _runner_preflight as preflight_runner
from . import workspace
from ._runner_types import (
    ArmExecution,
    BlockAttempt,
    QuiescenceError,
    RunnerError,
    SharedContrastInvalidation,
    _Preflight,
    _PreparedArm,
)
from .contracts import canonical_json_bytes, canonical_sha256, validate_record


def _atomic_record(path: Path, record: dict[str, Any]) -> None:
    validate_record(record)
    data = canonical_json_bytes(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / (
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def _started_record(
    lock: Mapping[str, object],
    block_id: str,
    preflight: _Preflight,
) -> dict[str, Any]:
    return {
        "record_kind": "block_attempt.v1",
        "pilot_lock_digest": canonical_sha256(lock),
        "attempt_class": preflight.attempt_class,
        "sequence_index": preflight.sequence_index,
        "block_id": block_id,
        "status": "STARTED",
        "treatment_executions": [],
    }


def _allocate_workspaces(preflight: _Preflight, block_id: str) -> None:
    if not preflight.arms:
        raise RunnerError("lock contains no treatment arms")
    block_root = preflight.arms[0].command.workspace.parents[1]
    block_root.mkdir(parents=True, exist_ok=False)
    manifests = []
    for arm in preflight.arms:
        arm.command.workspace.parent.mkdir()
        manifest = workspace.materialize_git_archive(
            preflight.repo,
            preflight.commit,
            arm.command.workspace,
        )
        if manifest.digest != preflight.archive_digest:
            raise RunnerError(
                f"source archive digest mismatch while allocating {block_id}"
            )
        manifests.append(manifest)
        arm.command.runtime_root.mkdir(parents=True)
        apparatus.write_staged_assets(arm.staged_assets)
        environment = dict(arm.command.environment)
        for special in ("HOME", "TMPDIR"):
            value = environment.get(special)
            if value is not None:
                Path(value).mkdir(parents=True)
    if any(manifest != manifests[0] for manifest in manifests[1:]):
        raise RunnerError("allocated treatment workspaces are not byte-identical")


def _execute_arms(
    *,
    preflight: _Preflight,
    lock: Mapping[str, object],
    evidence_root: Path,
    groups: execution._ProcessGroups,
) -> tuple[ArmExecution, ...]:
    barrier = threading.Barrier(4)
    launch_times: dict[str, int] = {}
    launch_lock = threading.Lock()
    results: dict[str, ArmExecution] = {}
    failures: list[BaseException] = []
    result_lock = threading.Lock()

    def worker(arm: _PreparedArm) -> None:
        try:
            result = execution._run_arm(
                arm=arm,
                preflight=preflight,
                lock=lock,
                evidence_root=evidence_root,
                barrier=barrier,
                launch_times=launch_times,
                launch_lock=launch_lock,
                groups=groups,
            )
            with result_lock:
                results[arm.command.treatment_id] = result
        except BaseException as exc:
            with result_lock:
                failures.append(exc)
            barrier.abort()
            groups.terminate_all(preflight.quiescence_grace_milliseconds)

    threads = [
        threading.Thread(target=worker, args=(arm,), daemon=False)
        for arm in preflight.arms
    ]
    for thread in threads:
        thread.start()
    barrier_failure: threading.BrokenBarrierError | None = None
    try:
        barrier.wait()
    except threading.BrokenBarrierError as exc:
        barrier_failure = exc
    except BaseException:
        barrier.abort()
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        for thread in threads:
            thread.join()
        raise
    for thread in threads:
        thread.join()

    worker_failures = tuple(
        failure
        for failure in failures
        if not isinstance(failure, threading.BrokenBarrierError)
    )
    if worker_failures:
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        raise worker_failures[0]
    if barrier_failure is not None or failures:
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        raise SharedContrastInvalidation(
            "SHARED_LAUNCH_BARRIER_FAILED",
            "arm launch barrier broke",
        ) from barrier_failure
    if len(launch_times) != 3:
        raise RunnerError("not all arm launch workers reached the barrier")
    launch_values = tuple(launch_times.values())
    skew_milliseconds = (max(launch_values) - min(launch_values)) / 1_000_000
    if skew_milliseconds > preflight.maximum_start_skew_milliseconds:
        raise SharedContrastInvalidation(
            "SHARED_START_SKEW_EXCEEDED",
            "arm start skew exceeded the locked maximum",
        )
    return tuple(results[arm.command.treatment_id] for arm in preflight.arms)


def _terminal_record(
    started: dict[str, Any],
    *,
    status: str,
    executions: tuple[ArmExecution, ...] = (),
    reason_code: str | None = None,
) -> dict[str, Any]:
    record = dict(started)
    record["status"] = status
    record["treatment_executions"] = [
        execution_record.to_record() for execution_record in executions
    ]
    if reason_code is not None:
        record["reason_code"] = reason_code
    else:
        record.pop("reason_code", None)
    return record


def run_block(
    *,
    lock: Mapping[str, object],
    block_id: str,
    work_root: Path,
    evidence_root: Path,
) -> BlockAttempt:
    """Run one fresh locked three-treatment block and persist its attempt."""

    work_root = Path(work_root).resolve(strict=False)
    evidence_root = Path(evidence_root).resolve(strict=False)
    preflight = preflight_runner._preflight(
        lock=lock,
        block_id=block_id,
        work_root=work_root,
        evidence_root=evidence_root,
    )
    started = _started_record(lock, block_id, preflight)
    _atomic_record(preflight.record_path, started)
    groups = execution._ProcessGroups()

    try:
        _allocate_workspaces(preflight, block_id)
    except Exception:
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        invalid = _terminal_record(
            started,
            status="INVALID",
            reason_code="SHARED_ARCHIVE_ALLOCATION_FAILED",
        )
        _atomic_record(preflight.record_path, invalid)
        return BlockAttempt(record=invalid, path=preflight.record_path)

    try:
        executions = _execute_arms(
            preflight=preflight,
            lock=lock,
            evidence_root=evidence_root,
            groups=groups,
        )
        valid = _terminal_record(
            started,
            status="VALID",
            executions=executions,
        )
        _atomic_record(preflight.record_path, valid)
        return BlockAttempt(record=valid, path=preflight.record_path)
    except QuiescenceError:
        groups.terminate_all(preflight.quiescence_grace_milliseconds)
        raise
    except SharedContrastInvalidation as exc:
        if not groups.terminate_all(preflight.quiescence_grace_milliseconds):
            raise QuiescenceError(
                "one or more process groups remain after cleanup"
            ) from exc
        invalid = _terminal_record(
            started,
            status="INVALID",
            reason_code=exc.reason_code,
        )
        _atomic_record(preflight.record_path, invalid)
        return BlockAttempt(record=invalid, path=preflight.record_path)
    except Exception as exc:
        if not groups.terminate_all(preflight.quiescence_grace_milliseconds):
            raise QuiescenceError(
                "one or more process groups remain after cleanup"
            ) from exc
        aborted = _terminal_record(
            started,
            status="ABORTED",
            reason_code="CONTROLLER_EXCEPTION",
        )
        _atomic_record(preflight.record_path, aborted)
        return BlockAttempt(record=aborted, path=preflight.record_path)
