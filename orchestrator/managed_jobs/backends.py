"""Backend interfaces for managed-job submission."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ManagedJobRequest:
    """Backend submission request for one managed job."""

    argv: list[str]
    workspace: Path
    job_state_path: Path
    job_identity_hash: str
    snapshot_manifest_path: Path
    snapshot_workspace: Path
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True)
class ManagedJobSubmission:
    """Backend submission result."""

    status: str
    backend: str
    returncode: int | None = None
    scheduler_id: str | None = None
    script_path: Path | None = None


class ManagedJobBackend(Protocol):
    """Minimal backend protocol."""

    def submit(self, request: ManagedJobRequest) -> ManagedJobSubmission:
        ...


def _executable_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] in {"python", "python3"}:
        return [sys.executable, *argv[1:]]
    return argv


class LocalBackend:
    """Run the managed payload as a local subprocess in the snapshot workspace."""

    def submit(self, request: ManagedJobRequest) -> ManagedJobSubmission:
        request.stdout_path.parent.mkdir(parents=True, exist_ok=True)
        request.stderr_path.parent.mkdir(parents=True, exist_ok=True)
        with request.stdout_path.open("wb") as stdout, request.stderr_path.open("wb") as stderr:
            completed = subprocess.run(
                _executable_argv(request.argv),
                cwd=request.workspace,
                stdout=stdout,
                stderr=stderr,
            )
        return ManagedJobSubmission(
            status="completed" if completed.returncode == 0 else "failed",
            backend="local",
            returncode=completed.returncode,
        )


class SlurmBackend:
    """Generate a snapshot-bound Slurm script without requiring a live cluster."""

    def submit(self, request: ManagedJobRequest) -> ManagedJobSubmission:
        scheduler_id = f"dry-run-{uuid.uuid4().hex[:12]}"
        script_path = request.job_state_path.parent / "submit.slurm"
        script_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    f"JOB_IDENTITY_HASH={shlex.quote(request.job_identity_hash)}",
                    f"SNAPSHOT_MANIFEST={shlex.quote(str(request.snapshot_manifest_path))}",
                    f"echo \"$JOB_IDENTITY_HASH\" >/dev/null",
                    f"test -f {shlex.quote(str(request.snapshot_manifest_path))}",
                    f"cd {shlex.quote(str(request.snapshot_workspace))}",
                    " ".join(shlex.quote(part) for part in _executable_argv(request.argv)),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        script_path.chmod(script_path.stat().st_mode | 0o755)
        return ManagedJobSubmission(
            status="submitted",
            backend="slurm",
            scheduler_id=scheduler_id,
            script_path=script_path,
        )


def backend_for(name: str) -> ManagedJobBackend:
    """Return a backend implementation by name."""

    if name in {"auto", "local"}:
        return LocalBackend()
    if name == "slurm":
        return SlurmBackend()
    raise ValueError(f"unsupported managed-job backend '{name}'")


def backend_state(submission: ManagedJobSubmission) -> dict[str, object]:
    """Serialize backend result into job state."""

    payload: dict[str, object] = {"name": submission.backend, "status": submission.status}
    if submission.returncode is not None:
        payload["returncode"] = submission.returncode
    if submission.scheduler_id is not None:
        payload["scheduler_id"] = submission.scheduler_id
    if submission.script_path is not None:
        payload["script_path"] = str(submission.script_path)
    return payload


def update_job_state(path: Path, updates: dict[str, object]) -> dict[str, object]:
    """Merge updates into a JSON job-state file."""

    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(payload, dict):
        payload = {}
    payload.update(updates)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
