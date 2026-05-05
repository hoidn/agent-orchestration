"""Managed-job runner used by provider shims."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from pathlib import Path

from .audit import append_event
from .backends import ManagedJobRequest, backend_for, backend_state, update_job_state
from .identity import compute_job_identity_hash
from .models import ManagedJobMetadata, ManagedJobPolicyEntry
from .pending_policy import read_pending_records
from .policy import ManagedJobPolicyError, load_policy
from .shims import UnsupportedShimInvocation, parse_shim_invocation
from .snapshot import file_sha256, materialize_snapshot


class ManagedJobRunnerError(RuntimeError):
    """Raised when managed-job routing fails closed."""


@dataclass(frozen=True)
class ManagedJobRunResult:
    """Result returned by the managed-job runner."""

    status: str
    job_identity_hash: str | None = None
    job_state_path: str | None = None


def _matches(entry_path: str, relpath: str) -> bool:
    return entry_path == relpath or fnmatch(relpath, entry_path)


def _target_relpath(argv: list[str]) -> str | None:
    if not argv:
        return None
    if argv[0] in {"python", "python3"}:
        for item in argv[1:]:
            if item in {"-m", "-c"}:
                return None
            if not item.startswith("-"):
                return Path(item).as_posix()
    if argv[0] == "torchrun":
        for item in argv[1:]:
            if item.endswith(".py") and not item.startswith("-"):
                return Path(item).as_posix()
    return None


def _matching_entries(entries: tuple[ManagedJobPolicyEntry, ...], relpath: str) -> list[ManagedJobPolicyEntry]:
    return [entry for entry in entries if _matches(entry.path, relpath)]


def _pending_decision(path: Path, relpath: str) -> str | None:
    for record in reversed(read_pending_records(path)):
        if record.get("path") == relpath and isinstance(record.get("decision"), str):
            return str(record["decision"])
    return None


def _run_local(argv: list[str], *, workspace: Path) -> ManagedJobRunResult:
    command = [sys.executable, *argv[1:]] if argv and argv[0] in {"python", "python3"} else argv
    completed = subprocess.run(command, cwd=workspace)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return ManagedJobRunResult(status="local")


def _hash_files(workspace: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for pattern in patterns:
        for path in sorted(item for item in workspace.glob(pattern) if item.is_file()):
            hashes[path.relative_to(workspace).as_posix()] = file_sha256(path)
    return hashes


def _source_hashes(workspace: Path, roots: tuple[str, ...]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for root in roots:
        path = workspace / root
        if path.is_file():
            hashes[Path(root).as_posix()] = file_sha256(path)
            continue
        if path.is_dir():
            for item in sorted(child for child in path.rglob("*") if child.is_file()):
                hashes[item.relative_to(workspace).as_posix()] = file_sha256(item)
    return hashes


def _policy_entry_hash(entry: ManagedJobPolicyEntry) -> str:
    import hashlib

    payload = json.dumps(asdict(entry), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _format_state_root(template: str, *, entry: ManagedJobPolicyEntry, job_identity_hash: str) -> Path:
    return Path(
        template.format(
            entry_id=entry.id,
            job_identity_hash=job_identity_hash,
        )
    )


def _resolve_managed_entry(
    *,
    entries: list[ManagedJobPolicyEntry],
    pending_decision: str | None,
) -> ManagedJobPolicyEntry | None:
    if len({entry.id for entry in entries}) > 1 or len(entries) > 1:
        raise ManagedJobRunnerError("conflicting managed-job policy entries")
    entry = entries[0] if entries else None
    if pending_decision == "unmanaged":
        return None
    if entry is None:
        return None
    if entry.mode in {"force_local", "unmanaged"}:
        return None
    return entry


def _validate_metadata(entry: ManagedJobPolicyEntry) -> ManagedJobMetadata:
    if entry.metadata is None:
        raise ManagedJobRunnerError("managed entry lacks complete job metadata")
    if not entry.metadata.state_root_template or not entry.metadata.verify_files:
        raise ManagedJobRunnerError("managed entry lacks verification metadata")
    return entry.metadata


def run_managed_job(
    argv: list[str],
    *,
    workspace: Path,
    policy_path: Path,
    audit_path: Path,
    state_root: Path,
    pending_policy_path: Path,
    backend: str,
) -> ManagedJobRunResult:
    """Classify and run one payload through local execution or managed backend."""

    del state_root
    workspace = workspace.resolve()
    try:
        policy = load_policy(policy_path, workspace=workspace)
    except ManagedJobPolicyError as exc:
        raise ManagedJobRunnerError(str(exc)) from exc

    relpath = _target_relpath(argv)
    if relpath is None:
        return _run_local(argv, workspace=workspace)

    entries = _matching_entries(policy.entries, relpath)
    pending = _pending_decision(pending_policy_path, relpath)
    entry = _resolve_managed_entry(entries=entries, pending_decision=pending)
    if entry is None:
        return _run_local(argv, workspace=workspace)
    metadata = _validate_metadata(entry)

    selected_backend = entry.backend or backend or policy.default_backend
    if selected_backend == "auto":
        selected_backend = backend if backend != "auto" else policy.default_backend
    if selected_backend == "auto":
        selected_backend = "local"

    snapshot_inputs = tuple(sorted(metadata.snapshot_roots))
    source_hashes = _source_hashes(workspace, metadata.snapshot_roots)
    config_hashes = _hash_files(workspace, metadata.config_globs)
    identity = compute_job_identity_hash(
        argv=argv,
        source_hashes=source_hashes,
        config_hashes=config_hashes,
        extractor_id=metadata.extractor or entry.id,
        extractor_version=metadata.extractor_version or "explicit",
        policy_entry_hash=_policy_entry_hash(entry),
        snapshot_inputs=snapshot_inputs,
    )
    job_root = workspace / _format_state_root(
        metadata.state_root_template,
        entry=entry,
        job_identity_hash=identity,
    )
    job_root.mkdir(parents=True, exist_ok=True)
    snapshot = materialize_snapshot(
        workspace=workspace,
        snapshot_root=job_root / "snapshot",
        roots=metadata.snapshot_roots,
        config_globs=metadata.config_globs,
    )
    job_state_path = job_root / "job_state.json"
    stdout_path = job_root / "stdout.log"
    stderr_path = job_root / "stderr.log"
    job_state = {
        "status": "SUBMITTED",
        "job_identity_hash": identity,
        "state_root": str(job_root),
        "argv": argv,
        "entry_id": entry.id,
        "snapshot": {"manifest": str(snapshot["manifest_path"])},
        "verify_files": list(metadata.verify_files),
        "source_hashes": source_hashes,
        "config_hashes": config_hashes,
    }
    job_state_path.write_text(json.dumps(job_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_event(
        audit_path,
        {
            "event": "job_submitted",
            "job_id": identity,
            "job_state_path": str(job_state_path),
        },
    )
    request = ManagedJobRequest(
        argv=argv,
        workspace=Path(str(snapshot["snapshot_workspace"])),
        job_state_path=job_state_path,
        job_identity_hash=identity,
        snapshot_manifest_path=Path(str(snapshot["manifest_path"])),
        snapshot_workspace=Path(str(snapshot["snapshot_workspace"])),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
    submission = backend_for(selected_backend).submit(request)
    terminal_status = {
        "completed": "COMPLETED",
        "failed": "FAILED",
        "submitted": "SUBMITTED",
    }.get(submission.status, "SUBMITTED")
    update_job_state(
        job_state_path,
        {
            "status": terminal_status,
            "backend": backend_state(submission),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        },
    )
    append_event(
        audit_path,
        {
            "event": "job_completed" if submission.status in {"completed", "submitted"} else "job_failed",
            "job_id": identity,
            "job_state_path": str(job_state_path),
        },
    )
    return ManagedJobRunResult(
        status=submission.status,
        job_identity_hash=identity,
        job_state_path=str(job_state_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shim", required=True)
    parser.add_argument("payload", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    payload = args.payload[1:] if args.payload and args.payload[0] == "--" else args.payload
    try:
        parsed = parse_shim_invocation(args.shim, payload)
        run_managed_job(
            parsed.payload_argv,
            workspace=Path.cwd(),
            policy_path=Path(_required_env("MANAGED_JOB_POLICY")),
            audit_path=Path(_required_env("MANAGED_JOB_AUDIT_PATH")),
            state_root=Path(_required_env("MANAGED_JOB_STATE_ROOT")),
            pending_policy_path=Path(_required_env("MANAGED_JOB_PENDING_POLICY")),
            backend=_required_env("MANAGED_JOB_BACKEND"),
        )
    except UnsupportedShimInvocation as exc:
        print(str(exc), file=sys.stderr)
        return 64
    except ManagedJobRunnerError as exc:
        print(str(exc), file=sys.stderr)
        return 65
    return 0


def _required_env(name: str) -> str:
    import os

    value = os.environ.get(name)
    if not value:
        raise ManagedJobRunnerError(f"missing required environment variable {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
