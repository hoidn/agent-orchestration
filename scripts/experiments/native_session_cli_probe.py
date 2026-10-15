from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from native_session_cli_process import Invocation, ProcessTracker
from native_session_cli_evidence import (
    NativeEvidence,
    _identity,
    inspect_claude_turn,
    inspect_codex_turn,
    inspect_native_user_turn,
    native_turn_open_at_append,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAX_INVOCATIONS = 8
MAX_TIMEOUT_SECONDS = 180


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_file(root: Path, path: Path, *, allow_missing: bool = False) -> Path:
    root = root.resolve(strict=True)
    if path.is_symlink():
        raise ValueError("session paths must not be symlinks")
    if allow_missing and not path.exists():
        resolved = path.parent.resolve(strict=True) / path.name
    else:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise ValueError("session path must be a regular file")
    if not _inside(resolved, root):
        raise ValueError("session path is outside its isolated home")
    return resolved


def backup_session_file(home: Path, path: Path, evidence_dir: Path, backup: Path) -> str:
    source = _safe_file(home, path)
    evidence_root = evidence_dir.resolve(strict=True)
    if backup.is_symlink() or backup.exists() or backup.parent.resolve(strict=True) != evidence_root:
        raise ValueError("backup must be a new file directly inside the private evidence directory")
    raw = source.read_bytes()
    backup.write_bytes(raw)
    backup.chmod(0o600)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def delete_session_file(home: Path, path: Path) -> None:
    _safe_file(home, path).unlink()


def restore_session_file(home: Path, path: Path, evidence_dir: Path, backup: Path) -> None:
    destination = _safe_file(home, path, allow_missing=True)
    evidence_root = evidence_dir.resolve(strict=True)
    source = _safe_file(evidence_root, backup)
    if destination.exists():
        destination.unlink()
    temporary = destination.with_name(destination.name + ".restore-tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("restore temporary path already exists")
    shutil.copyfile(source, temporary)
    temporary.chmod(0o600)
    os.replace(temporary, destination)


def _output_directory(value: str | None) -> Path:
    if value is None:
        result = Path(tempfile.mkdtemp(prefix="native-session-cli-probe-"))
    else:
        result = Path(value).expanduser()
        if result.is_symlink():
            raise ValueError("output directory must not be a symlink")
        parent = result.parent.resolve(strict=True)
        result = parent / result.name
        if _inside(result, REPOSITORY_ROOT):
            raise ValueError("output directory must be outside the repository")
        result.mkdir(mode=0o700)
    if _inside(result.resolve(), REPOSITORY_ROOT):
        raise ValueError("output directory must be outside the repository")
    result.chmod(0o700)
    return result


def _prepare(provider: str, model: str | None, output: Path) -> None:
    for name in ("workspace", "evidence", "provider-home", "schemas", "tmp"):
        (output / name).mkdir(mode=0o700)
    controls = output / "workspace" / ".probe-controls"
    controls.mkdir(mode=0o700)
    (output / "workspace" / "review.txt").write_text(
        "A disposable file for the native session CLI probe.\n", encoding="utf-8"
    )
    (output / "workspace" / "execution.txt").write_text("", encoding="utf-8")
    for version in (1, 2):
        schema = {
            "type": "object",
            "properties": {
                "schema": {"type": "integer", "const": version},
                "nonce": {"type": "string", "minLength": 1},
                ("reviewed" if version == 1 else "executed"): {"type": "boolean", "const": True},
            },
            "required": ["schema", "nonce", "reviewed" if version == 1 else "executed"],
            "additionalProperties": False,
        }
        (output / "schemas" / f"schema-{version}.json").write_text(
            json.dumps(schema, indent=2) + "\n", encoding="utf-8"
        )
    prepared = {
        "status": "PREPARED",
        "provider": provider,
        "model": model,
        "model_candidate": "gpt-6-luna" if provider == "codex" else "haiku",
        "effort": "low",
        "max_invocations": MAX_INVOCATIONS,
        "max_timeout_seconds": MAX_TIMEOUT_SECONDS,
        "real_execution": "NOT RUN; requires --execute, explicit model, and separate authorization",
        "artifacts": [
            "workspace/review.txt",
            "workspace/execution.txt",
            "schemas/schema-1.json",
            "schemas/schema-2.json",
        ],
    }
    (output / "prepared.json").write_text(
        json.dumps(prepared, indent=2) + "\n", encoding="utf-8"
    )


class ProbeStop(RuntimeError):
    pass


def _private_environment(
    provider: str, output: Path, invocation: int, nonce: str, session: str | None, executable: str,
    private_home: Path | None = None,
) -> dict[str, str]:
    private = private_home or output / "provider-home" / provider
    private.mkdir(mode=0o700, exist_ok=True)
    environment = {
        "PATH": str(Path(executable).resolve().parent) + os.pathsep + os.defpath,
        "HOME": str(output / "provider-home" / "home"),
        "TMPDIR": str(output / "tmp"),
        "LANG": "C.UTF-8",
        "NATIVE_SESSION_PROBE_INVOCATION": str(invocation),
        "NATIVE_SESSION_PROBE_CONTROLS": str(output / "workspace" / ".probe-controls"),
        "NATIVE_SESSION_PROBE_NONCE": nonce,
        "NATIVE_SESSION_PROBE_SESSION": session or "",
        "NATIVE_SESSION_PROBE_WRITE_PATH": str(output / "workspace" / "execution.txt"),
    }
    Path(environment["HOME"]).mkdir(mode=0o700, exist_ok=True)
    if provider == "codex":
        environment["CODEX_HOME"] = str(private)
    else:
        environment["CLAUDE_CONFIG_DIR"] = str(private)
    environment["NATIVE_SESSION_PROBE_PHASE"] = ""
    behavior = os.environ.get("NATIVE_SESSION_PROBE_FAKE_BEHAVIOR")
    if behavior:
        environment["NATIVE_SESSION_PROBE_FAKE_BEHAVIOR"] = behavior
    return environment


def _stage_auth(provider: str, destination_home: Path, destination: Path | None = None) -> Path:
    user_home = Path(os.environ.get("HOME", str(Path.home())))
    source = user_home / (".codex/auth.json" if provider == "codex" else ".claude/.credentials.json")
    if source.is_symlink() or not source.is_file():
        raise ProbeStop(f"the single expected {provider} credential file is unavailable or unsafe")
    if destination is None:
        destination = destination_home / ("auth.json" if provider == "codex" else ".credentials.json")
    shutil.copyfile(source, destination)
    destination.chmod(0o600)
    return destination


def _provider_executable(provider: str) -> tuple[str, bool]:
    override = os.environ.get(f"NATIVE_SESSION_PROBE_FAKE_{provider.upper()}")
    if override:
        path = Path(override)
        if not path.is_file() or path.is_symlink():
            raise ProbeStop("fake CLI override must name a regular executable file")
        return str(path.resolve()), True
    executable = shutil.which(provider)
    if executable is None:
        raise ProbeStop(f"{provider} CLI is not available on PATH")
    return executable, False


def _prompt(phase: str, nonce: str, output: Path, predecessor: str | None = None) -> str:
    workspace = output / "workspace"
    if phase == "review":
        instruction = f"Read review.txt without changing any workspace file. Return the required schema with nonce {nonce} and reviewed=true."
    elif phase == "write":
        instruction = f"Write exactly {nonce} to execution.txt. Return the required schema with nonce {nonce} and executed=true."
    elif phase == "interrupt":
        marker = workspace / ".probe-controls" / "entered-5"
        task = f"from pathlib import Path; import time; Path({str(marker)!r}).write_text({nonce!r}); time.sleep(180)"
        command = shlex.join([sys.executable, "-c", task])
        instruction = f"Use the shell tool to execute this command and keep it running until interrupted:\n```sh\n{command}\n```\nReturn the required schema with nonce {nonce} and executed=true only if the command finishes."
    else:
        controls = workspace / ".probe-controls"
        if phase == "overlap-hold":
            marker = controls / "entered-3"
            release = controls / "release-3"
            instruction = (
                f"This competing resume was submitted against recorded predecessor {predecessor}. "
                f"Use the available shell tool to write {nonce} to execution.txt, create marker {marker}, "
                f"then wait at most 45 seconds for {release} before returning the required schema with nonce {nonce} and executed=true."
            )
        else:
            instruction = (
                f"This competing resume was submitted against recorded predecessor {predecessor}. "
                f"Do not wait. Return the required schema with nonce {nonce} and executed=true."
            )
    return instruction


def _plain_claude_command(executable: str, model: str, session: str | None) -> list[str]:
    """The Claude session adapter's own fresh/resume argv (prompt goes on stdin, no --json-schema)."""
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))
    from orchestrator.providers.registry import ProviderRegistry

    support = ProviderRegistry().get("claude_unrestricted_workspace").session_support
    template = support.fresh_command if session is None else support.resume_command
    if template[0] != "claude":
        raise ProbeStop("the Claude session adapter command no longer starts with the claude executable")
    values = {"${model}": model, "${effort}": "low", "${SESSION_ID}": session}
    return [executable] + [values.get(token, token) for token in template[1:]]


def _command(
    provider: str,
    executable: str,
    model: str,
    output: Path,
    phase: str,
    nonce: str,
    session: str | None,
    predecessor: str | None,
    command_form: str = "schema",
) -> list[str]:
    if command_form == "plain":
        if provider != "claude":
            raise ProbeStop("the plain command form exists only for claude")
        return _plain_claude_command(executable, model, session)
    prompt = _prompt(phase, nonce, output, predecessor)
    schema = 1 if phase == "review" else 2
    schema_path = output / "schemas" / f"schema-{schema}.json"
    if provider == "codex":
        command = [executable, "exec"]
        if session is not None:
            command.extend(["resume", session])
        command.extend(
            [
                "--json",
                "--output-schema",
                str(schema_path),
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "-m",
                model,
                "-c",
                'sandbox_mode="workspace-write"',
                "-c",
                'approval_policy="never"',
                "-c",
                'model_reasoning_effort="low"',
                prompt,
            ]
        )
        return command
    command = [executable, "-p", prompt, "--output-format", "stream-json", "--verbose"]
    if session is not None:
        command.extend(["--resume", session])
    command.extend(
        [
            "--json-schema",
            json.dumps(json.loads(schema_path.read_text(encoding="utf-8"))),
            "--model",
            model,
            "--effort",
            "low",
            "--setting-sources",
            "",
            "--settings",
            '{"disableAllHooks":true}',
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--disable-slash-commands",
            "--tools",
            "Bash",
            "--allowedTools",
            "Bash",
            "--permission-mode",
            "acceptEdits",
        ]
    )
    return command


def _native_session_files(provider: str, private_home: Path) -> list[Path]:
    if provider == "codex":
        store = private_home / "sessions"
        return sorted(store.rglob("rollout-*.jsonl")) if store.is_dir() else []
    if provider == "claude":
        store = private_home / "projects"
        return sorted(store.rglob("*.jsonl")) if store.is_dir() else []
    raise ProbeStop(f"unsupported provider session store: {provider}")


def _session_file(provider: str, private_home: Path) -> Path:
    files = _native_session_files(provider, private_home)
    if len(files) != 1 or files[0].is_symlink() or not files[0].is_file():
        raise ProbeStop("isolated provider home does not contain exactly one native session file")
    return files[0]


def _native_snapshot(source: Path, private_home: Path, output: Path, label: str) -> Path:
    resolved_home = private_home.resolve(strict=True)
    if source.is_symlink() or not source.is_file():
        raise ProbeStop("native session file is missing or unsafe")
    resolved = source.resolve(strict=True)
    if not _inside(resolved, resolved_home):
        raise ProbeStop("native session file escaped the isolated provider home")
    target = output / "evidence" / f"native-{label}.jsonl"
    raw = resolved.read_bytes()
    with target.open("xb") as stream:
        stream.write(raw)
    target.chmod(0o600)
    return target


def _workspace_snapshot(workspace: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(workspace.rglob("*")):
        if path.is_symlink():
            snapshot[str(path.relative_to(workspace))] = "SYMLINK"
        elif path.is_file():
            snapshot[str(path.relative_to(workspace))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def _write_observations(output: Path, report: dict[str, object]) -> None:
    (output / "observations.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


def _exact_result(evidence: NativeEvidence, schema: int, nonce: str) -> bool:
    result = evidence.result
    key = "reviewed" if schema == 1 else "executed"
    return (
        evidence.status == "OBSERVED"
        and isinstance(result, dict)
        and set(result) == {"schema", "nonce", key}
        and type(result.get("schema")) is int
        and result.get("schema") == schema
        and result.get("nonce") == nonce
        and result.get(key) is True
    )


def _invoke(
    tracker: ProcessTracker,
    report: dict[str, object],
    *,
    ordinal: int,
    phase: str,
    provider: str,
    executable: str,
    fake: bool,
    model: str,
    output: Path,
    timeout: float,
    session: str | None,
    predecessor: str | None,
    allow_overlap: bool = False,
    private_home: Path | None = None,
    launch_metadata: dict[str, object] | None = None,
    command_form: str = "schema",
) -> tuple[Invocation, dict[str, object]]:
    count = report.get("invocation_count")
    limit = report.get("max_invocations", MAX_INVOCATIONS)
    if type(count) is not int or count >= limit or ordinal != count + 1:
        raise ProbeStop("model invocation limit or fixed ordinal sequence would be exceeded")
    nonce = uuid.uuid4().hex
    command = _command(provider, executable, model, output, phase, nonce, session, predecessor, command_form)
    environment = _private_environment(provider, output, ordinal, nonce, session, executable, private_home)
    environment["NATIVE_SESSION_PROBE_PHASE"] = phase
    if fake:
        for key in ("NATIVE_SESSION_PROBE_FAKE_BEHAVIOR",):
            if key in os.environ:
                environment[key] = os.environ[key]
    row: dict[str, object] = {
        "ordinal": ordinal,
        "phase": phase,
        "nonce": nonce,
        "session_id": session,
        "predecessor_turn_id": predecessor,
        "command": command,
        "synthetic_cli": fake,
        "not_run": False,
        "launch_attempted": False,
        "status": "INCONCLUSIVE",
        "quiescent": False,
        "raw_sha256": "",
        "native_refs": [],
    }
    if launch_metadata:
        row.update(launch_metadata)
    rows = report["invocations"]
    assert isinstance(rows, list)
    stdout_path = output / "evidence" / f"invocation-{ordinal}.stdout.log"
    stderr_path = output / "evidence" / f"invocation-{ordinal}.stderr.log"
    stdin_path = Path(os.devnull)
    if command_form == "plain":  # the adapter sends the prompt on stdin
        stdin_path = output / "evidence" / f"invocation-{ordinal}.stdin.txt"
        stdin_path.write_text(_prompt(phase, nonce, output, predecessor), encoding="utf-8")
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr, stdin_path.open("rb") as stdin:
        rows.append(row)
        # Count an attempt even when process creation itself fails; never retry it.
        report["invocation_count"] = ordinal
        row["launch_attempted"] = True
        invocation = tracker.launch(
            ordinal,
            command,
            cwd=output / "workspace",
            env=environment,
            stdout=stdout.fileno(),
            stderr=stderr.fileno(),
            allow_overlap=allow_overlap,
            stdin=stdin.fileno(),
        )
        row["started_monotonic"] = invocation.started
        row["deadline_monotonic"] = invocation.started + timeout
    return invocation, row


def _evidence_for(provider: str, path: Path, nonce: str, session: str | None, predecessor: str | None) -> NativeEvidence:
    if provider == "codex":
        return inspect_codex_turn(path, nonce=nonce, expected_session=session, predecessor_turn=predecessor)
    return inspect_claude_turn(path, nonce=nonce, expected_session=session, predecessor_turn=predecessor)


def _finish_row(tracker: ProcessTracker, invocation: Invocation, row: dict[str, object], timeout: float) -> None:
    tracker.finish(invocation, timeout)
    _process_row(invocation, row, tracker)


def _process_row(invocation: Invocation, row: dict[str, object], tracker: ProcessTracker) -> None:
    row["returncode"] = invocation.returncode
    row["quiescent"] = invocation.quiescent
    row["timed_out"] = invocation.timed_out
    row["tracking_ok"] = invocation.tracking_ok
    row["unexpected_descendants"] = invocation.unexpected_descendants
    row["ambiguous_adoption"] = tracker.ambiguous_adoption
    row["leader_pid"] = invocation.process.pid
    row["leader_start_time"] = invocation.leader_start_time
    row["tracked_processes"] = [{"pid": pid, "start_time": started} for pid, started in sorted(invocation.tracked.items())]
    row["tracking_failures"] = list(tracker.tracking_failures)
    row["duration_seconds"] = round(time.monotonic() - invocation.started, 3)
    row["stop_requested_monotonic"] = invocation.stop_requested
    row["provider_stopped_monotonic"] = invocation.provider_stopped
    row["cleanup_duration_seconds"] = round(invocation.cleanup_completed - (invocation.stop_requested or invocation.provider_stopped or invocation.started), 3) if invocation.cleanup_completed is not None else None
    if invocation.timed_out:
        row["deadline_cancellation"] = True


def _record_native(row: dict[str, object], evidence: NativeEvidence, snapshot: Path) -> None:
    row["status"] = evidence.status
    row["reason"] = evidence.reason
    row["turn_id"] = evidence.turn_id
    row["session_id"] = evidence.session_id
    row["raw_sha256"] = evidence.raw_sha256
    row["native_refs"] = list(evidence.refs)
    row["raw_file"] = str(snapshot)


def _read_cli_version(
    tracker: ProcessTracker, provider: str, executable: str, fake: bool, args: argparse.Namespace,
    output: Path, report: dict[str, object],
) -> None:
    environment = _private_environment(provider, output, 0, "version", None, executable)
    environment["NATIVE_SESSION_PROBE_PHASE"] = "version"
    stdout_path = output / "evidence" / "cli-version.stdout.log"
    stderr_path = output / "evidence" / "cli-version.stderr.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        invocation = tracker.launch(
            0, [executable, "--version"], cwd=output / "workspace", env=environment,
            stdout=stdout.fileno(), stderr=stderr.fileno(),
        )
        tracker.finish(invocation, min(args.timeout_seconds, 10.0))
    version = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
    report["cli_version"] = {"command": [executable, "--version"], "output": version, "synthetic_cli": fake}
    if invocation.returncode != 0 or not invocation.quiescent or not version:
        raise ProbeStop("bounded CLI version check failed or left a child process")


def _remaining_invocations(reason: str, after: int = 0) -> list[dict[str, object]]:
    return [
        {"ordinal": ordinal, "not_run": True, "status": "INCONCLUSIVE", "reason": reason}
        for ordinal in range(after + 1, MAX_INVOCATIONS + 1)
    ]


def _user_append(provider: str, path: Path, nonce: str, session: str) -> NativeEvidence:
    return inspect_native_user_turn(provider, path, nonce=nonce, expected_session=session)


def _run_recovery_tail(
    args: argparse.Namespace,
    output: Path,
    tracker: ProcessTracker,
    report: dict[str, object],
    executable: str,
    fake: bool,
    provider_home: Path,
    session_id: str,
    predecessor: str,
    exclusivity_gate: dict[str, object],
) -> None:
    """Admit the original gated campaign without upgrading its qualification."""
    if exclusivity_gate.get("status") != "OBSERVED":
        raise ProbeStop("recovery tail requires an observed exclusivity gate")
    _observe_recovery_tail(
        args, output, tracker, report, executable, fake, provider_home, session_id, predecessor,
    )


def _observe_recovery_tail(
    args: argparse.Namespace,
    output: Path,
    tracker: ProcessTracker,
    report: dict[str, object],
    executable: str,
    fake: bool,
    provider_home: Path,
    session_id: str,
    predecessor: str | None,
) -> None:
    """Collect separately authorized diagnostics; this does not qualify continuation."""
    native = _session_file(args.provider, provider_home)
    before5 = _native_snapshot(native, provider_home, output, "before-interruption")
    before_hash = hashlib.sha256(before5.read_bytes()).hexdigest()
    invocation5, row5 = _invoke(
        tracker, report, ordinal=5, phase="interrupt", provider=args.provider, executable=executable,
        fake=fake, model=args.model, output=output, timeout=args.timeout_seconds,
        session=session_id, predecessor=predecessor,
    )
    marker = output / "workspace" / ".probe-controls" / "entered-5"
    deadline = min(invocation5.started + args.timeout_seconds, time.monotonic() + 60)
    while time.monotonic() < deadline and not marker.exists() and invocation5.process.poll() is None:
        tracker.refresh()
        time.sleep(0.02)
    row5["interruption_marker_observed"] = False
    if marker.exists() and marker.read_text(encoding="utf-8") == row5["nonce"] and invocation5.process.poll() is None:
        row5["interruption_marker_observed"] = True
        tracker.cancel(invocation5)
    else:
        _finish_row(tracker, invocation5, row5, args.timeout_seconds)
        row5["interruption_marker_observed"] = False
    _process_row(invocation5, row5, tracker)
    if not invocation5.quiescent:
        row5["reason"] = "interruption marker or proven process-tree quiescence is missing"
        report["gates"]["interruption_recovery"] = {"status": "INCONCLUSIVE", "reason": row5["reason"]}
        report["remaining_invocations"] = _remaining_invocations(
            "invocation 5 did not stop quiescently", report["invocation_count"]
        )
        return
    if not row5["interruption_marker_observed"]:
        report["gates"]["interruption_recovery"] = {
            "status": "INCONCLUSIVE", "reason": "invocation 5 was quiescent but interruption was not established",
        }
    after5 = _native_snapshot(native, provider_home, output, "after-interruption")
    after_hash = hashlib.sha256(after5.read_bytes()).hexdigest()
    row5["raw_file"] = str(after5)
    row5["raw_sha256"] = "sha256:" + after_hash
    row5["native_state_before_sha256"] = "sha256:" + before_hash
    row5["native_state_unchanged"] = before_hash == after_hash
    row5["status"] = "INCONCLUSIVE"
    row5["reason"] = (
        "synthetic fake interruption reached quiescence; native interrupted-turn semantics remain provider evidence"
        if fake
        else "interruption reached quiescence; native interrupted-turn semantics remain provider evidence"
    )

    invocation6, row6 = _invoke(
        tracker, report, ordinal=6, phase="recovery", provider=args.provider, executable=executable,
        fake=fake, model=args.model, output=output, timeout=args.timeout_seconds,
        session=session_id, predecessor=predecessor,
    )
    _finish_row(tracker, invocation6, row6, args.timeout_seconds)
    if not invocation6.quiescent:
        raise ProbeStop("recovery attempt did not prove process-tree quiescence")
    snapshot6 = _native_snapshot(native, provider_home, output, "06-recovery")
    evidence6 = _evidence_for(args.provider, snapshot6, str(row6["nonce"]), session_id, predecessor)
    _record_native(row6, evidence6, snapshot6)
    recovered = (
        row6["returncode"] == 0
        and row6["quiescent"]
        and _exact_result(evidence6, 2, str(row6["nonce"]))
    )
    if not recovered or not row5["interruption_marker_observed"]:
        report["gates"]["interruption_recovery"] = {"status": "INCONCLUSIVE", "reason": "resume after interruption did not establish exact current native completion"}
    else:
        report["gates"]["interruption_recovery"] = {
            "status": "OBSERVED",
            "reason": "one resume after proven quiescence produced a native exact current completion",
            "synthetic_cli": fake,
        }
    diagnostic_predecessor = evidence6.turn_id if recovered else None
    backup = output / "evidence" / "session-before-delete.jsonl"
    backup_hash = backup_session_file(provider_home, native, output / "evidence", backup)
    delete_session_file(provider_home, native)
    deleted_before_launch = not native.exists()
    row7: dict[str, object] | None = None
    invocation7: Invocation | None = None
    try:
        invocation7, row7 = _invoke(
            tracker, report, ordinal=7, phase="lost-session", provider=args.provider, executable=executable,
            fake=fake, model=args.model, output=output, timeout=args.timeout_seconds,
            session=session_id, predecessor=diagnostic_predecessor,
            launch_metadata={"deleted_session_before_launch": deleted_before_launch},
        )
        _finish_row(tracker, invocation7, row7, args.timeout_seconds)
        if not invocation7.quiescent:
            raise ProbeStop("session-loss attempt did not prove process-tree quiescence")
        row7["session_backup_sha256"] = backup_hash
        row7["native_attempts"] = []
        candidates7 = _native_session_files(args.provider, provider_home)
        row7["replacement_or_fallback_seen"] = bool(candidates7)
        for index, candidate in enumerate(candidates7):
            snapshot7 = _native_snapshot(candidate, provider_home, output, f"07-lost-session-attempt-{index}")
            attempt7 = _evidence_for(args.provider, snapshot7, str(row7["nonce"]), session_id, diagnostic_predecessor)
            _record_native(row7, attempt7, snapshot7)
            row7["native_attempts"].append({"native_file": str(candidate), "raw_file": str(snapshot7), "raw_sha256": attempt7.raw_sha256, "status": attempt7.status})
        row7["status"] = "INCONCLUSIVE"
        row7["reason"] = "a recreated or replacement session does not establish safe native continuation"
    finally:
        if invocation7 is not None and invocation7.quiescent:
            restore_session_file(provider_home, native, output / "evidence", backup)
        else:
            report["session_restore_pending"] = {"backup_file": str(backup), "backup_sha256": backup_hash, "reason": "native restoration withheld until writer quiescence is proven"}
    restored_hash = "sha256:" + hashlib.sha256(native.read_bytes()).hexdigest()
    if restored_hash != backup_hash:
        raise ProbeStop("exact native-session restore after deletion did not match its backup")
    assert row7 is not None
    row7["restored_sha256"] = restored_hash
    row7["restored_before_alternate_home"] = True

    alternate_home = output / "provider-home" / f"alternate-{args.provider}"
    alternate_home.mkdir(mode=0o700)
    alternate_auth = alternate_home / ("auth.json" if args.provider == "codex" else ".credentials.json")
    try:
        _stage_auth(args.provider, alternate_home, alternate_auth)
        visible_before = _native_session_files(args.provider, alternate_home)
        original_before = _native_snapshot(native, provider_home, output, "08-original-before")
        original_before_hash = "sha256:" + hashlib.sha256(original_before.read_bytes()).hexdigest()
        original_files_before = _native_session_files(args.provider, provider_home)
        invocation8, row8 = _invoke(
            tracker, report, ordinal=8, phase="alternate-home", provider=args.provider,
            executable=executable, fake=fake, model=args.model, output=output,
            timeout=args.timeout_seconds, session=session_id, predecessor=diagnostic_predecessor,
            private_home=alternate_home,
        )
        _finish_row(tracker, invocation8, row8, args.timeout_seconds)
        if not invocation8.quiescent:
            raise ProbeStop("alternate-home attempt did not prove process-tree quiescence")
        original_after = _native_snapshot(native, provider_home, output, "08-original-after")
        original_after_hash = "sha256:" + hashlib.sha256(original_after.read_bytes()).hexdigest()
        row8["original_home_before_raw_file"] = str(original_before)
        row8["original_home_after_raw_file"] = str(original_after)
        row8["original_home_before_sha256"] = original_before_hash
        row8["original_home_after_sha256"] = original_after_hash
        row8["original_home_changed"] = original_before_hash != original_after_hash or original_files_before != _native_session_files(args.provider, provider_home)
        row8["original_native_files_visible_before_launch"] = bool(visible_before)
        candidates = _native_session_files(args.provider, alternate_home)
        if len(candidates) == 1:
            snapshot8 = _native_snapshot(candidates[0], alternate_home, output, "08-alternate-home")
            evidence8 = _evidence_for(args.provider, snapshot8, str(row8["nonce"]), session_id, diagnostic_predecessor)
            _record_native(row8, evidence8, snapshot8)
        row8["status"] = "INCONCLUSIVE"
        row8["reason"] = "the alternate home contained no original native file before resume; any new session does not prove original-session isolation"
        row8["staged_alternate_auth_removed"] = True
        report["gates"]["session_loss"] = {"status": "INCONCLUSIVE", "reason": "one deletion attempt was captured and the original native file was restored byte-for-byte"}
        report["gates"]["alternate_home"] = {"status": "NOT_OBSERVED" if row8["original_home_changed"] else "INCONCLUSIVE", "reason": "alternate-home invocation changed the first home's native store" if row8["original_home_changed"] else row8["reason"]}
        report["remaining_invocations"] = []
    finally:
        try:
            alternate_auth.unlink()
        except FileNotFoundError:
            pass


def _stdout_session(stdout_path: Path) -> tuple[str | None, list[str]]:
    """The one session id the stream-json stdout names, and the event kinds in order."""
    sessions: set[str] = set()
    kinds: list[str] = []
    for line in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            kinds.append("<non-json>")
            continue
        if isinstance(event, dict):
            kinds.append(f"{event.get('type')}/{event.get('subtype')}" if "subtype" in event else str(event.get("type")))
            if _identity(event.get("session_id")):
                sessions.add(event["session_id"])
    return (sessions.pop() if len(sessions) == 1 else None), kinds


def _plain_native_file(provider_home: Path, session_id: str) -> Path:
    matches = sorted((provider_home / "projects").rglob(f"{session_id}.jsonl"))
    if len(matches) != 1:
        raise ProbeStop("the isolated home does not hold exactly one native file for the stdout session")
    return matches[0]


PLAIN_PHASES = ("review", "write", "review")  # fresh -> resume -> resume


def _run_plain_campaign(args: argparse.Namespace, output: Path) -> int:
    """Claude plain stream-json form (the session adapter's argv): bounded calls, native snapshot after each."""
    provider_home = output / "provider-home" / "claude"
    report: dict[str, object] = {
        "provider": "claude", "model": args.model, "command_form": "plain", "synthetic_cli": False,
        "invocation_count": 0, "max_invocations": args.max_calls, "timeout_seconds": args.timeout_seconds,
        "invocations": [], "status": "RUNNING",
    }
    auth_copy: Path | None = None
    tracker: ProcessTracker | None = None
    try:
        executable, fake = _provider_executable("claude")
        report["synthetic_cli"] = fake
        provider_home.mkdir(mode=0o700, exist_ok=True)
        tracker = ProcessTracker()
        _read_cli_version(tracker, "claude", executable, fake, args, output, report)
        if not fake:  # a synthetic CLI runs against an empty private home; real credentials are never opened
            auth_copy = _stage_auth("claude", provider_home, provider_home / ".credentials.json")
        session_id: str | None = None
        for ordinal, phase in enumerate(PLAIN_PHASES[: args.max_calls], start=1):
            invocation, row = _invoke(
                tracker, report, ordinal=ordinal, phase=phase, provider="claude", executable=executable,
                fake=fake, model=args.model, output=output, timeout=args.timeout_seconds,
                session=session_id, predecessor=None, command_form="plain",
            )
            _finish_row(tracker, invocation, row, args.timeout_seconds)
            stdout_session, row["stdout_event_kinds"] = _stdout_session(output / "evidence" / f"invocation-{ordinal}.stdout.log")
            row["stdout_session_id"] = stdout_session
            if row["returncode"] != 0 or not row["quiescent"] or stdout_session is None or session_id not in {None, stdout_session}:
                report["status"] = "STOPPED_INCONCLUSIVE"
                row["reason"] = "nonzero exit, missing quiescence, or no single stable stdout session id"
                return 0
            session_id = stdout_session
            row["native_files"] = sorted(str(path.relative_to(provider_home)) for path in (provider_home / "projects").rglob("*.jsonl"))
            snapshot = _native_snapshot(_plain_native_file(provider_home, session_id), provider_home, output, f"{ordinal:02d}-{phase}")
            row["raw_file"] = str(snapshot)
            row["raw_sha256"] = "sha256:" + hashlib.sha256(snapshot.read_bytes()).hexdigest()
        report["status"] = "PLAIN_CAMPAIGN_COMPLETE"
        return 0
    except (OSError, ProbeStop, RuntimeError, ValueError) as error:
        report["status"] = "STOPPED_ERROR"
        report["error"] = str(error)
        return 1
    finally:
        try:
            if tracker is not None:
                tracker.close()
        finally:
            if auth_copy is not None:
                auth_copy.unlink(missing_ok=True)
                report["staged_auth_removed"] = True
            _write_observations(output, report)


def _run_campaign(args: argparse.Namespace, output: Path) -> int:
    if args.command_form == "plain":
        return _run_plain_campaign(args, output)
    provider = args.provider
    provider_home = output / "provider-home" / provider
    report: dict[str, object] = {
        "provider": provider,
        "model": args.model,
        "synthetic_cli": False,
        "invocation_count": 0,
        "max_invocations": args.max_calls,
        "timeout_seconds": args.timeout_seconds,
        "invocations": [],
        "gates": {},
        "remaining_invocations": _remaining_invocations("campaign has not reached this stage"),
        "status": "RUNNING",
    }
    auth_copy: Path | None = None
    tracker: ProcessTracker | None = None
    private_session: Path | None = None
    session_id: str | None = None
    predecessor: str | None = None
    native_head: Path | None = None
    try:
        executable, fake = _provider_executable(provider)
        report["synthetic_cli"] = fake
        provider_home.mkdir(mode=0o700, exist_ok=True)
        tracker = ProcessTracker()
        _read_cli_version(tracker, provider, executable, fake, args, output, report)
        auth_copy = provider_home / ("auth.json" if provider == "codex" else ".credentials.json")
        _stage_auth(provider, provider_home, auth_copy)
        workspace = output / "workspace"
        before_review = _workspace_snapshot(workspace)

        invocation1, row1 = _invoke(
            tracker, report, ordinal=1, phase="review", provider=provider, executable=executable,
            fake=fake, model=args.model, output=output, timeout=args.timeout_seconds,
            session=None, predecessor=None,
        )
        _finish_row(tracker, invocation1, row1, args.timeout_seconds)
        private_session = provider_home
        private_native = _session_file(provider, private_session)
        snapshot1 = _native_snapshot(private_native, private_session, output, "01-review")
        evidence1 = _evidence_for(provider, snapshot1, str(row1["nonce"]), None, None)
        _record_native(row1, evidence1, snapshot1)
        session_id = evidence1.session_id
        after_review = _workspace_snapshot(workspace)
        review_unchanged = before_review == after_review
        row1["workspace_unchanged"] = review_unchanged
        if (
            row1["returncode"] != 0
            or not row1["quiescent"]
            or not _exact_result(evidence1, 1, str(row1["nonce"]))
            or not review_unchanged
            or session_id is None
        ):
            report["gates"] = {"exact_completion": {"status": "INCONCLUSIVE", "reason": "invocation 1 lacked complete native review proof or changed the workspace"}}
            report["remaining_invocations"] = _remaining_invocations(
                "exact-completion gate after invocation 1 did not pass", report["invocation_count"]
            )
            report["status"] = "STOPPED_INCONCLUSIVE"
            return 1 if row1["returncode"] != 0 or not row1["quiescent"] else 0
        predecessor = evidence1.turn_id

        invocation2, row2 = _invoke(
            tracker, report, ordinal=2, phase="write", provider=provider, executable=executable,
            fake=fake, model=args.model, output=output, timeout=args.timeout_seconds,
            session=session_id, predecessor=predecessor,
        )
        _finish_row(tracker, invocation2, row2, args.timeout_seconds)
        snapshot2 = _native_snapshot(private_native, provider_home, output, "02-write")
        evidence2 = _evidence_for(provider, snapshot2, str(row2["nonce"]), session_id, predecessor)
        _record_native(row2, evidence2, snapshot2)
        expected_workspace = dict(after_review)
        expected_workspace["execution.txt"] = hashlib.sha256(str(row2["nonce"]).encode("utf-8")).hexdigest()
        write_exact = (workspace / "execution.txt").read_text(encoding="utf-8") == row2["nonce"]
        row2["workspace_exact_write"] = write_exact and _workspace_snapshot(workspace) == expected_workspace
        exact_first_two = (
            row2["returncode"] == 0
            and row2["quiescent"]
            and _exact_result(evidence2, 2, str(row2["nonce"]))
            and row2["workspace_exact_write"] is True
        )
        if not exact_first_two:
            report["gates"] = {"exact_completion": {"status": "INCONCLUSIVE", "reason": "invocations 1–2 did not bind schema, nonce, result, predecessor and exact workspace write"}}
            report["remaining_invocations"] = _remaining_invocations(
                "exact-completion gate after invocation 2 did not pass", report["invocation_count"]
            )
            report["status"] = "STOPPED_INCONCLUSIVE"
            return 1 if row2["returncode"] != 0 or not row2["quiescent"] else 0
        report["gates"] = {"exact_completion": {"status": "OBSERVED", "reason": "native current turn, schema change, nonce and exact workspace write are bound"}}
        predecessor = evidence2.turn_id
        assert predecessor is not None

        controls = workspace / ".probe-controls"
        invocation3, row3 = _invoke(
            tracker, report, ordinal=3, phase="overlap-hold", provider=provider, executable=executable,
            fake=fake, model=args.model, output=output, timeout=args.timeout_seconds,
            session=session_id, predecessor=predecessor,
        )
        marker = controls / "entered-3"
        wait_until = min(invocation3.started + args.timeout_seconds, time.monotonic() + 60)
        append3: NativeEvidence | None = None
        while time.monotonic() < wait_until:
            tracker.refresh()
            if private_native.exists():
                append3 = _user_append(provider, private_native, str(row3["nonce"]), session_id)
            if marker.exists() and append3 is not None and append3.turn_id and invocation3.process.poll() is None:
                break
            if invocation3.process.poll() is not None:
                break
            time.sleep(0.02)
        if not (marker.exists() and append3 is not None and append3.turn_id and invocation3.process.poll() is None):
            if invocation3.process.poll() is None:
                tracker.cancel(invocation3)
                _process_row(invocation3, row3, tracker)
            else:
                _finish_row(tracker, invocation3, row3, args.timeout_seconds)
            row3["reason"] = "invocation 3 did not prove a live native user append behind the tool marker"
            report["gates"]["exclusive_continuation"] = {"status": "INCONCLUSIVE", "reason": row3["reason"]}
            report["remaining_invocations"] = _remaining_invocations(
                "concurrency overlap was not established", report["invocation_count"]
            )
            report["status"] = "STOPPED_INCONCLUSIVE"
            return 0
        row3["append_turn_id"] = append3.turn_id
        row3["append_native_refs"] = list(append3.refs)
        row3["append_raw_sha256"] = append3.raw_sha256

        invocation4, row4 = _invoke(
            tracker, report, ordinal=4, phase="overlap-attempt", provider=provider, executable=executable,
            fake=fake, model=args.model, output=output, timeout=args.timeout_seconds,
            session=session_id, predecessor=predecessor, allow_overlap=True,
        )
        append4: NativeEvidence | None = None
        overlap_deadline = min(
            invocation3.started + args.timeout_seconds,
            invocation4.started + args.timeout_seconds,
        )
        overlap_observed = False
        while time.monotonic() < overlap_deadline:
            tracker.refresh()
            if private_native.exists():
                append4 = _user_append(provider, private_native, str(row4["nonce"]), session_id)
            if append4 is not None and append4.turn_id:
                overlap_observed = (
                    invocation3.process.poll() is None
                    and time.monotonic() < invocation3.started + args.timeout_seconds
                )
                break
            if invocation4.process.poll() is not None:
                break
            time.sleep(0.02)
        if invocation3.process.poll() is None and time.monotonic() >= invocation3.started + args.timeout_seconds:
            invocation3.timed_out = True
            tracker.cancel(invocation3)
            row3["deadline_cancellation"] = True
        native_overlap = False
        if append4 is not None and append4.turn_id:
            concurrent_snapshot = _native_snapshot(private_native, provider_home, output, "03-04-overlap")
            append3 = _user_append(provider, concurrent_snapshot, str(row3["nonce"]), session_id)
            append4 = _user_append(provider, concurrent_snapshot, str(row4["nonce"]), session_id)
            native_overlap = native_turn_open_at_append(provider, concurrent_snapshot, append3, append4)
            row3["append_turn_id"] = append3.turn_id
            row3["append_native_refs"] = list(append3.refs)
            row3["append_raw_sha256"] = append3.raw_sha256
            row4["append_turn_id"] = append4.turn_id
            row4["append_native_refs"] = list(append4.refs)
            row4["append_raw_sha256"] = append4.raw_sha256
            row3["overlap_raw_file"] = str(concurrent_snapshot)
            row4["overlap_raw_file"] = str(concurrent_snapshot)
        (controls / "release-3").write_text("release", encoding="utf-8")
        _finish_row(tracker, invocation4, row4, args.timeout_seconds)
        _finish_row(tracker, invocation3, row3, args.timeout_seconds)
        same_session = (
            append3 is not None
            and append4 is not None
            and append3.status == append4.status == "INCONCLUSIVE"
            and append3.session_id == append4.session_id == session_id
        )
        same_recorded_predecessor = row3["predecessor_turn_id"] == row4["predecessor_turn_id"] == predecessor
        distinct_turns = append3 is not None and append4 is not None and append3.turn_id != append4.turn_id
        if same_session and same_recorded_predecessor and distinct_turns and overlap_observed and native_overlap:
            gate = {
                "status": "NOT_OBSERVED",
                "reason": "two native user appends occurred while the first native turn remained incomplete and its CLI/tool marker established live overlap",
                "native_refs": list(append3.refs + append4.refs),
                "raw_sha256": append4.raw_sha256,
            }
        else:
            gate = {
                "status": "INCONCLUSIVE",
                "reason": "no recognized native contention/fencing proof or adverse overlapping append was established; nonzero exit and ordered success do not prove exclusivity",
            }
        report["gates"]["exclusive_continuation"] = gate
        if gate["status"] == "OBSERVED":
            head_snapshot = _native_snapshot(private_native, provider_home, output, "before-recovery-tail")
            current_head = _evidence_for(provider, head_snapshot, str(row3["nonce"]), session_id, predecessor)
            if not invocation3.quiescent or not _exact_result(current_head, 2, str(row3["nonce"])):
                raise ProbeStop("exclusive continuation lacks an exact completed current head for recovery")
            _run_recovery_tail(
                args, output, tracker, report, executable, fake, provider_home,
                session_id, current_head.turn_id, gate,
            )
            report["status"] = "CAMPAIGN_COMPLETE_WITH_UNQUALIFIED_TAIL"
            return 0
        report["remaining_invocations"] = _remaining_invocations(
            "exclusive-continuation gate was not OBSERVED; later live scenarios were not run",
            report["invocation_count"],
        )
        report["status"] = "STOPPED_AT_EXCLUSIVITY_GATE"
        return 0 if gate["status"] in {"NOT_OBSERVED", "INCONCLUSIVE"} else 1
    except (OSError, ProbeStop, RuntimeError, ValueError) as error:
        report["status"] = "STOPPED_ERROR"
        report["error"] = str(error)
        report["remaining_invocations"] = _remaining_invocations(str(error), report["invocation_count"])
        return 1
    finally:
        try:
            if tracker is not None:
                tracker.close()
        except (OSError, RuntimeError) as error:
            report["status"] = "STOPPED_ERROR"
            report["process_tracker_cleanup_error"] = str(error)
        finally:
            if auth_copy is not None:
                try:
                    auth_copy.unlink()
                    report["staged_auth_removed"] = True
                except FileNotFoundError:
                    report["staged_auth_removed"] = True
            _write_observations(output, report)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare or explicitly execute a native session CLI probe.")
    parser.add_argument("--provider", choices=("codex", "claude"), required=True)
    parser.add_argument("--model", help="Required together with --execute; never selected automatically for execution.")
    parser.add_argument("--execute", action="store_true", help="Launch a real provider campaign; preparation is the default.")
    parser.add_argument("--output-dir", help="Private artifact directory outside the repository.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=MAX_TIMEOUT_SECONDS,
        help=f"Per-invocation timeout in (0, {MAX_TIMEOUT_SECONDS}] seconds.",
    )
    parser.add_argument(
        "--command-form", choices=("schema", "plain"), default="schema",
        help="schema: the recorded --json-schema campaign; plain: the Claude session adapter's own argv, prompt on stdin.",
    )
    parser.add_argument(
        "--max-calls", type=int, default=MAX_INVOCATIONS,
        help=f"Bound on model invocations in [1, {MAX_INVOCATIONS}]; the campaign never exceeds it.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.execute and not args.model:
        parser.error("--execute requires an explicit --model")
    if (
        not math.isfinite(args.timeout_seconds)
        or args.timeout_seconds <= 0
        or args.timeout_seconds > MAX_TIMEOUT_SECONDS
    ):
        parser.error(f"--timeout-seconds must be in (0, {MAX_TIMEOUT_SECONDS}]")
    if not 1 <= args.max_calls <= MAX_INVOCATIONS:
        parser.error(f"--max-calls must be in [1, {MAX_INVOCATIONS}]")
    if args.command_form == "plain" and args.provider != "claude":
        parser.error("--command-form plain exists only for --provider claude")
    try:
        output = _output_directory(args.output_dir)
        _prepare(args.provider, args.model, output)
        if args.execute:
            return _run_campaign(args, output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Prepared artifacts: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
