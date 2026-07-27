"""Process, raw-result, check, and arm execution for the lean-pilot runner."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Mapping

from . import _runner_apparatus as apparatus
from . import _runner_quiescence as quiescence
from . import workspace
from ._runner_types import (
    ArmCommand,
    ArmExecution,
    QuiescenceError,
    RunnerError,
    _Preflight,
    _PreparedArm,
    _RawResult,
)
from .contracts import canonical_json_bytes


_RAW_RESULT_FIELDS = {
    "terminal_outcome",
    "provider_call_count",
    "token_counts",
    "cost",
}
_RAW_TERMINAL_OUTCOMES = {
    "COMPLETED",
    "BLOCKED",
    "EXHAUSTED",
    "PROTOCOL_FAILURE",
}


class _ProcessGroups:
    def __init__(
        self,
        *,
        ledger_path: Path,
        pilot_lock_digest: str,
        block_id: str,
    ) -> None:
        self._lock = threading.Lock()
        self._groups: set[int] = set()
        self._in_flight_spawns: set[str] = set()
        self._persisted_groups: set[int] = set()
        self._persisted_spawns: set[str] = set()
        self._next_spawn_index = 0
        self._ledger_path = ledger_path
        self._pilot_lock_digest = pilot_lock_digest
        self._block_id = block_id
        quiescence.initialize_process_group_ledger(
            path=ledger_path,
            pilot_lock_digest=pilot_lock_digest,
            block_id=block_id,
        )

    def _persist(self) -> None:
        quiescence.replace_process_group_ledger(
            path=self._ledger_path,
            pilot_lock_digest=self._pilot_lock_digest,
            block_id=self._block_id,
            expected_process_group_ids=tuple(self._persisted_groups),
            expected_in_flight_spawn_ids=tuple(self._persisted_spawns),
            process_group_ids=tuple(self._groups),
            in_flight_spawn_ids=tuple(self._in_flight_spawns),
        )
        self._persisted_groups = set(self._groups)
        self._persisted_spawns = set(self._in_flight_spawns)

    def begin_spawn(self) -> str:
        with self._lock:
            self._next_spawn_index += 1
            spawn_id = f"spawn-{self._next_spawn_index:08d}"
            self._in_flight_spawns.add(spawn_id)
            self._persist()
            return spawn_id

    def register_spawn(
        self,
        spawn_id: str,
        process_group_id: int,
    ) -> None:
        with self._lock:
            if spawn_id not in self._in_flight_spawns:
                raise QuiescenceError("process spawn marker is not active")
            self._groups.add(process_group_id)
            self._in_flight_spawns.remove(spawn_id)
            self._persist()

    def cancel_spawn(self, spawn_id: str) -> None:
        with self._lock:
            if spawn_id not in self._in_flight_spawns:
                raise QuiescenceError("process spawn marker is not active")
            self._in_flight_spawns.remove(spawn_id)
            self._persist()

    def discard(self, process_group_id: int) -> None:
        with self._lock:
            self._groups.discard(process_group_id)
            self._persist()

    def terminate_all(self, grace_milliseconds: int) -> bool:
        with self._lock:
            groups = tuple(self._groups)
        all_quiescent = True
        for process_group_id in groups:
            if _terminate_process_group(process_group_id, grace_milliseconds):
                self.discard(process_group_id)
            else:
                all_quiescent = False
        return all_quiescent


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(
    process_group_id: int,
    grace_milliseconds: int,
) -> bool:
    if not _process_group_exists(process_group_id):
        return True
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + (grace_milliseconds / 1_000)
    while time.monotonic() < deadline:
        if not _process_group_exists(process_group_id):
            return True
        time.sleep(0.005)
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        return True
    final_deadline = time.monotonic() + 1.0
    while time.monotonic() < final_deadline:
        if not _process_group_exists(process_group_id):
            return True
        time.sleep(0.005)
    return False


def _quiesce_process(
    process: subprocess.Popen[bytes],
    grace_milliseconds: int,
) -> None:
    _terminate_process_group(process.pid, grace_milliseconds)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired as exc:
        raise QuiescenceError(
            f"process {process.pid} could not be reaped after termination"
        ) from exc
    if _process_group_exists(process.pid):
        raise QuiescenceError(
            f"process group {process.pid} remains after termination and reap"
        )


def _raw_result(
    data: bytes,
    *,
    currency: str,
) -> _RawResult:
    value = apparatus.strict_json_bytes(data, label="arm raw result")
    if not isinstance(value, dict) or set(value) != _RAW_RESULT_FIELDS:
        raise RunnerError("arm raw result has unknown or missing fields")
    terminal_outcome = value["terminal_outcome"]
    if (
        not isinstance(terminal_outcome, str)
        or terminal_outcome not in _RAW_TERMINAL_OUTCOMES
    ):
        raise RunnerError("arm raw result terminal_outcome is invalid")
    count = value["provider_call_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise RunnerError("arm raw result provider_call_count is invalid")

    token_counts = value["token_counts"]
    if token_counts != "UNKNOWN":
        if (
            not isinstance(token_counts, dict)
            or set(token_counts) != {"input", "output"}
            or any(
                isinstance(item, bool) or not isinstance(item, int) or item < 0
                for item in token_counts.values()
            )
        ):
            raise RunnerError("arm raw result token_counts is invalid")

    cost = value["cost"]
    if cost != "UNKNOWN":
        if (
            not isinstance(cost, dict)
            or set(cost) != {"cost_microunits", "currency"}
            or isinstance(cost["cost_microunits"], bool)
            or not isinstance(cost["cost_microunits"], int)
            or cost["cost_microunits"] < 0
            or cost["currency"] != currency
        ):
            raise RunnerError("arm raw result cost is invalid")
    return _RawResult(
        terminal_outcome=terminal_outcome,
        provider_call_count=count,
        token_counts=token_counts,
        cost=cost,
    )


def _environment_metadata(
    command: ArmCommand,
    credential_names: tuple[str, ...],
) -> dict[str, object]:
    names = {key for key, _value in command.environment}
    return {
        "environment_key_presence": [
            {"name": name, "present": name in names}
            for name in sorted(names)
        ],
        "credential_key_presence": [
            {"name": name, "present": name in names}
            for name in sorted(credential_names)
        ],
    }


def _write_evidence(path: Path, value: bytes | object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, bytes) else canonical_json_bytes(value)
    path.write_bytes(data)


def _run_check(
    *,
    argv: tuple[str, ...],
    timeout_milliseconds: int,
    workspace_root: Path,
    environment: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    grace_milliseconds: int,
    groups: _ProcessGroups,
) -> bool:
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        spawn_id = groups.begin_spawn()
        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except OSError:
            groups.cancel_spawn(spawn_id)
            return False
        groups.register_spawn(spawn_id, process.pid)
        quiescent = False
        try:
            try:
                return_code = process.wait(timeout=timeout_milliseconds / 1_000)
            except subprocess.TimeoutExpired:
                return_code = None
            _quiesce_process(process, grace_milliseconds)
            quiescent = True
            return return_code == 0
        finally:
            if quiescent:
                groups.discard(process.pid)


def _run_arm(
    *,
    arm: _PreparedArm,
    preflight: _Preflight,
    lock: Mapping[str, object],
    evidence_root: Path,
    barrier: threading.Barrier,
    launch_times: dict[str, int],
    launch_lock: threading.Lock,
    groups: _ProcessGroups,
) -> ArmExecution:
    command = arm.command
    evidence_directory = (
        evidence_root
        / preflight.record_path.parent.name
        / command.opaque_arm_label
    )
    stdout_path = evidence_directory / "stdout.txt"
    stderr_path = evidence_directory / "stderr.txt"
    raw_evidence_path = evidence_directory / "raw-result.json"
    environment_path = evidence_directory / "environment.json"
    check_stdout_path = evidence_directory / "check-stdout.txt"
    check_stderr_path = evidence_directory / "check-stderr.txt"
    evidence_directory.mkdir(parents=True, exist_ok=True)
    _write_evidence(
        environment_path,
        _environment_metadata(command, arm.credential_names),
    )
    environment = dict(command.environment)

    started = time.monotonic_ns()
    lifecycle = "COMPLETED"
    process: subprocess.Popen[bytes] | None = None
    return_code: int | None = None
    timed_out = False
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        barrier.wait()
        spawn_id = groups.begin_spawn()
        with launch_lock:
            launch_times[command.opaque_arm_label] = time.monotonic_ns()
        try:
            process = subprocess.Popen(
                command.argv,
                cwd=command.workspace,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except OSError:
            groups.cancel_spawn(spawn_id)
            lifecycle = "LAUNCH_FAILURE"
        if process is not None:
            groups.register_spawn(spawn_id, process.pid)
            quiescent = False
            try:
                try:
                    return_code = process.wait(
                        timeout=command.timeout_milliseconds / 1_000
                    )
                except subprocess.TimeoutExpired:
                    timed_out = True
                _quiesce_process(process, preflight.quiescence_grace_milliseconds)
                quiescent = True
            finally:
                if quiescent:
                    groups.discard(process.pid)

    raw_bytes = b""
    if command.result_path.exists() and command.result_path.is_file():
        raw_bytes = command.result_path.read_bytes()
    _write_evidence(raw_evidence_path, raw_bytes)

    raw = _RawResult(
        terminal_outcome="PROTOCOL_FAILURE",
        provider_call_count=0,
        token_counts="UNKNOWN",
        cost="UNKNOWN",
    )
    raw_valid = False
    if raw_bytes:
        try:
            provider_policy = lock["provider_policy"]
            if not isinstance(provider_policy, Mapping):
                raise RunnerError("provider policy is malformed")
            currency = provider_policy["currency"]
            if not isinstance(currency, str):
                raise RunnerError("provider currency is malformed")
            raw = _raw_result(raw_bytes, currency=currency)
            raw_valid = True
        except RunnerError:
            raw_valid = False

    if timed_out:
        lifecycle = "TIMEOUT"
    elif lifecycle != "LAUNCH_FAILURE" and return_code != 0:
        lifecycle = "NONZERO_EXIT"
    elif lifecycle == "COMPLETED" and not raw_valid:
        lifecycle = "PROTOCOL_FAILURE"
    elif lifecycle == "COMPLETED":
        lifecycle = raw.terminal_outcome

    treatment = next(
        item
        for item in lock["treatments"]
        if item["treatment_id"] == command.treatment_id
    )
    bounds = treatment["provider_call_bounds"]
    if (
        raw_valid
        and not timed_out
        and return_code == 0
        and isinstance(bounds, Mapping)
        and (
            raw.provider_call_count < bounds["minimum"]
            or raw.provider_call_count > bounds["maximum"]
        )
    ):
        lifecycle = "PROTOCOL_FAILURE"

    check_passed = _run_check(
        argv=preflight.visible_check_argv,
        timeout_milliseconds=preflight.visible_check_timeout_milliseconds,
        workspace_root=command.workspace,
        environment=environment,
        stdout_path=check_stdout_path,
        stderr_path=check_stderr_path,
        grace_milliseconds=preflight.quiescence_grace_milliseconds,
        groups=groups,
    )
    if lifecycle == "COMPLETED" and not check_passed:
        lifecycle = "CHECK_FAILURE"

    product = workspace.freeze_product(command.workspace, preflight.exclusions)
    elapsed = max(0, (time.monotonic_ns() - started) // 1_000_000)
    references = tuple(
        path.relative_to(evidence_root).as_posix()
        for path in (
            stdout_path,
            stderr_path,
            raw_evidence_path,
            environment_path,
            check_stdout_path,
            check_stderr_path,
        )
    )
    return ArmExecution(
        opaque_arm_label=command.opaque_arm_label,
        treatment_id=command.treatment_id,
        command_digest=command.command_digest,
        lifecycle_outcome=lifecycle,
        product_frozen=True,
        product_manifest_digest=product.digest,
        provider_call_count=raw.provider_call_count if raw_valid else 0,
        elapsed_milliseconds=elapsed,
        evidence_references=references,
        token_counts=raw.token_counts if raw_valid else "UNKNOWN",
        cost=raw.cost if raw_valid else "UNKNOWN",
    )
