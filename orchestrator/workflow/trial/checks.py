"""Deterministic post-freeze check execution for target-2.25 trials."""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.ledger import settled_result_binding_from_record

from .config import TrialRuntimeRequest
from .contracts import TrialCellKey
from .ledger import (
    TrialEventLedger,
    TrialLedgerRow,
    append_trial_check_settlement,
    append_trial_checks_freeze,
    load_trial_event_ledger,
    validate_trial_check_phase_authority,
)


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CHECK_KEYS = {"check_id", "command", "authority", "required", "timeout_ms"}
_AUTHORITY_ORDER = {"correctness": 0, "invariant": 1}


class TrialCheckError(ValueError):
    """A trial check contract or execution result is invalid."""


@dataclass(frozen=True, slots=True)
class TrialCheckResult:
    check_id: str
    authority: str
    required: bool
    status: str
    exit_code: int | None
    duration_ms: int
    output_digest: str
    output_bytes: str
    evidence_frozen_digest: str
    check_spec_digest: str
    stdout_bytes: bytes
    stderr_bytes: bytes
    stdout_truncated: bool
    stderr_truncated: bool

    @property
    def record(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "authority": self.authority,
            "required": self.required,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "output_digest": self.output_digest,
            "output_bytes": self.output_bytes,
        }

    @property
    def digest(self) -> str:
        return canonical_sha256(
            {
                "schema_version": "trial_check_result.v1",
                "evidence_frozen_digest": self.evidence_frozen_digest,
                "check_spec_digest": self.check_spec_digest,
                "result": self.record,
            }
        )


def _normalized_checks(
    checks: Sequence[Mapping[str, Any]],
) -> tuple[tuple[int, dict[str, Any]], ...]:
    if isinstance(checks, (str, bytes)) or not isinstance(checks, Sequence):
        raise TypeError("trial checks must be a sequence")
    normalized: list[tuple[int, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, raw in enumerate(checks):
        if not isinstance(raw, Mapping) or set(raw) != _CHECK_KEYS:
            raise TrialCheckError("trial check has missing or extra fields")
        check = dict(raw)
        check_id = check["check_id"]
        command = check["command"]
        if not isinstance(check_id, str) or not check_id or check_id in seen:
            raise TrialCheckError("trial check ids must be unique non-empty strings")
        if (
            not isinstance(command, (list, tuple))
            or not command
            or any(not isinstance(item, str) or not item for item in command)
        ):
            raise TrialCheckError("trial check command must be literal argv")
        authority = check["authority"]
        if authority not in _AUTHORITY_ORDER:
            raise TrialCheckError("trial check authority is invalid")
        if type(check["required"]) is not bool:
            raise TrialCheckError("trial check required flag must be boolean")
        if type(check["timeout_ms"]) is not int or check["timeout_ms"] < 1:
            raise TrialCheckError("trial check timeout must be positive")
        check["command"] = list(command)
        seen.add(check_id)
        normalized.append((index, check))
    return tuple(
        sorted(
            normalized,
            key=lambda item: (_AUTHORITY_ORDER[item[1]["authority"]], item[0]),
        )
    )


def _raw_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _bounded_output(
    stdout: bytes,
    stderr: bytes,
    *,
    max_output_bytes: int,
) -> tuple[bytes, bytes, bool, bool, str, str]:
    kept_stdout = stdout[:max_output_bytes]
    kept_stderr = stderr[:max_output_bytes]
    stdout_truncated = len(kept_stdout) != len(stdout)
    stderr_truncated = len(kept_stderr) != len(stderr)
    identity = {
        "schema_version": "trial_check_output_identity.v1",
        "stdout_digest": _raw_digest(stdout),
        "stdout_size_bytes": len(stdout),
        "stderr_digest": _raw_digest(stderr),
        "stderr_size_bytes": len(stderr),
    }
    bounded = {
        "schema_version": "trial_check_output.v1",
        "stdout_base64": base64.b64encode(kept_stdout).decode("ascii"),
        "stderr_base64": base64.b64encode(kept_stderr).decode("ascii"),
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "stdout_size_bytes": len(stdout),
        "stderr_size_bytes": len(stderr),
    }
    return (
        kept_stdout,
        kept_stderr,
        stdout_truncated,
        stderr_truncated,
        canonical_sha256(identity),
        canonical_json_bytes(bounded).decode("utf-8"),
    )


def run_trial_checks(
    checks: Sequence[Mapping[str, Any]],
    *,
    cwd: Path,
    evidence_frozen_digest: str,
    max_output_bytes: int,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> tuple[TrialCheckResult, ...]:
    """Run one workspace's checks in deterministic authority/authored order."""

    workdir = Path(cwd)
    if not workdir.is_absolute() or workdir.resolve(strict=False) != workdir:
        raise TrialCheckError("trial check cwd must be canonical and absolute")
    if (
        not isinstance(evidence_frozen_digest, str)
        or _SHA256_RE.fullmatch(evidence_frozen_digest) is None
    ):
        raise TrialCheckError("trial check evidence freeze digest is invalid")
    if type(max_output_bytes) is not int or max_output_bytes < 1:
        raise TrialCheckError("trial check output bound must be positive")
    if not callable(runner) or not callable(monotonic_ns):
        raise TypeError("trial check execution dependencies must be callable")

    results: list[TrialCheckResult] = []
    for _authored_index, check in _normalized_checks(checks):
        started = monotonic_ns()
        try:
            completed = runner(
                list(check["command"]),
                cwd=workdir,
                shell=False,
                capture_output=True,
                timeout=check["timeout_ms"] / 1000,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            status = "TIMED_OUT"
            exit_code = None
            stdout = exc.output if isinstance(exc.output, bytes) else b""
            stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
        except OSError:
            status = "LAUNCH_FAILED"
            exit_code = None
            stdout = b""
            stderr = b""
        else:
            status = "COMPLETED"
            if type(completed.returncode) is not int:
                raise TrialCheckError("trial check return code must be an integer")
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        finished = monotonic_ns()
        if type(started) is not int or type(finished) is not int or finished < started:
            raise TrialCheckError("trial check monotonic clock is invalid")
        if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
            raise TrialCheckError("trial check runner must return byte output")
        bounded = _bounded_output(
            stdout,
            stderr,
            max_output_bytes=max_output_bytes,
        )
        results.append(
            TrialCheckResult(
                check_id=check["check_id"],
                authority=check["authority"],
                required=check["required"],
                status=status,
                exit_code=exit_code,
                duration_ms=(finished - started) // 1_000_000,
                output_digest=bounded[4],
                output_bytes=bounded[5],
                evidence_frozen_digest=evidence_frozen_digest,
                check_spec_digest=canonical_sha256(check),
                stdout_bytes=bounded[0],
                stderr_bytes=bounded[1],
                stdout_truncated=bounded[2],
                stderr_truncated=bounded[3],
            )
        )
    return tuple(results)


def _completed_cell_workspaces(
    ledger: TrialEventLedger,
) -> dict[TrialCellKey, Path]:
    rows_by_digest = {row.row_digest: row for row in ledger.rows}
    [freeze] = tuple(row for row in ledger.rows if row.kind == "evidence_frozen")
    workspaces: dict[TrialCellKey, Path] = {}
    try:
        for evidence in freeze.payload["cell_evidence"]:
            if evidence["status"] != "completed":
                continue
            cell = TrialCellKey(
                arm_id=evidence["cell"]["arm_id"],
                rep=evidence["cell"]["rep"],
            )
            committed = rows_by_digest[evidence["terminal_row_digest"]]
            settled = rows_by_digest[
                committed.payload["trial_settlement_row_digest"]
            ]
            prepared = rows_by_digest[settled.payload["prepared_trial_row_digest"]]
            binding = settled_result_binding_from_record(
                prepared.payload["settled_result"]
            )
            workspaces[cell] = binding.workspace_path
    except (KeyError, TypeError, ValueError) as exc:
        raise TrialCheckError(
            "trial completed-cell workspace authority is incomplete"
        ) from exc
    return workspaces


def _noop_crash_hook(_marker: str) -> None:
    return None


def ensure_trial_checks_frozen(
    path: Path,
    *,
    request: TrialRuntimeRequest,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
    crash_hook: Callable[[str], None] = _noop_crash_hook,
) -> TrialLedgerRow:
    """Resume the exact check prefix and freeze its derived per-cell authority."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("request must be exact TrialRuntimeRequest")
    if not callable(runner) or not callable(monotonic_ns) or not callable(crash_hook):
        raise TypeError("trial check execution dependencies must be callable")
    ledger = validate_trial_check_phase_authority(Path(path), request=request)
    frozen = tuple(row for row in ledger.rows if row.kind == "checks_frozen")
    if len(frozen) == 1:
        return frozen[0]
    if frozen:
        raise TrialCheckError("trial checks freeze authority is ambiguous")
    evidence = tuple(row for row in ledger.rows if row.kind == "evidence_frozen")
    if len(evidence) != 1:
        raise TrialCheckError("trial checks require one frozen evidence set")
    workspaces = _completed_cell_workspaces(ledger)
    ordered_checks = tuple(check for _index, check in _normalized_checks(
        request.static_config.evaluation["checks"]
    ))
    expected = tuple(
        (check, cell)
        for check in ordered_checks
        for cell in request.cell_domain
        if cell in workspaces
    )
    settled_count = sum(row.kind == "check_settled" for row in ledger.rows)
    if settled_count > len(expected):
        raise TrialCheckError("trial settled check domain exceeds static authority")
    max_output_bytes = request.static_config.evaluation["max_item_bytes"]
    for check, cell in expected[settled_count:]:
        [result] = run_trial_checks(
            (check,),
            cwd=workspaces[cell],
            evidence_frozen_digest=evidence[0].row_digest,
            max_output_bytes=max_output_bytes,
            runner=runner,
            monotonic_ns=monotonic_ns,
        )
        current = load_trial_event_ledger(Path(path))
        append_trial_check_settlement(
            Path(path),
            expected_head_digest=current.rows[-1].row_digest,
            request=request,
            cell=cell,
            result=result,
        )
        crash_hook("check_settled")
    current = load_trial_event_ledger(Path(path))
    result = append_trial_checks_freeze(
        Path(path),
        expected_head_digest=current.rows[-1].row_digest,
        request=request,
    )
    crash_hook("checks_frozen")
    return result


__all__ = [
    "TrialCheckError",
    "TrialCheckResult",
    "ensure_trial_checks_frozen",
    "run_trial_checks",
]
