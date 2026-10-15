"""Claude plain stream-json command form for the native session probe (Task 6a).

The plain form runs the Claude session adapter's own argv (the `claude_unrestricted_workspace`
`session_support` commands), prompt on stdin, no `--json-schema`. `run_plain_campaign` receives the
probe module so it reuses `_invoke`, quiescence tracking and snapshots without a circular import.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType

from native_session_cli_evidence import _identity

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLAIN_PHASES = ("review", "write", "review")  # fresh -> resume -> resume


def plain_claude_command(executable: str, model: str, session: str | None) -> list[str]:
    """The Claude session adapter's own fresh/resume argv, read from the provider registry."""
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))
    from orchestrator.providers.registry import ProviderRegistry

    support = ProviderRegistry().get("claude_unrestricted_workspace").session_support
    template = support.fresh_command if session is None else support.resume_command
    if template[0] != "claude":
        raise ValueError("the Claude session adapter command no longer starts with the claude executable")
    values = {"${model}": model, "${effort}": "low", "${SESSION_ID}": session}
    return [executable] + [values.get(token, token) for token in template[1:]]


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
        raise ValueError("the isolated home does not hold exactly one native file for the stdout session")
    return matches[0]


def run_plain_campaign(probe: ModuleType, args: argparse.Namespace, output: Path) -> int:
    """Bounded plain-form calls with a native snapshot after each; credentials staged only for a real CLI."""
    provider_home = output / "provider-home" / "claude"
    report: dict[str, object] = {
        "provider": "claude", "model": args.model, "command_form": "plain", "synthetic_cli": False,
        "invocation_count": 0, "max_invocations": args.max_calls, "timeout_seconds": args.timeout_seconds,
        "invocations": [], "status": "RUNNING",
    }
    auth_copy: Path | None = None
    tracker = None
    try:
        executable, fake = probe._provider_executable("claude")
        report["synthetic_cli"] = fake
        provider_home.mkdir(mode=0o700, exist_ok=True)
        tracker = probe.ProcessTracker()
        probe._read_cli_version(tracker, "claude", executable, fake, args, output, report)
        auth_copy = provider_home / ".credentials.json"
        if not probe._campaign_auth("claude", fake, provider_home, auth_copy):
            auth_copy = None
        session_id: str | None = None
        for ordinal, phase in enumerate(PLAIN_PHASES[: args.max_calls], start=1):
            invocation, row = probe._invoke(
                tracker, report, ordinal=ordinal, phase=phase, provider="claude", executable=executable,
                fake=fake, model=args.model, output=output, timeout=args.timeout_seconds,
                session=session_id, predecessor=None, command_form="plain",
            )
            probe._finish_row(tracker, invocation, row, args.timeout_seconds)
            stdout_session, row["stdout_event_kinds"] = _stdout_session(output / "evidence" / f"invocation-{ordinal}.stdout.log")
            row["stdout_session_id"] = stdout_session
            if row["returncode"] != 0 or not row["quiescent"] or stdout_session is None or session_id not in {None, stdout_session}:
                report["status"] = "STOPPED_INCONCLUSIVE"
                row["reason"] = "nonzero exit, missing quiescence, or no single stable stdout session id"
                return 0
            session_id = stdout_session
            row["native_files"] = sorted(str(path.relative_to(provider_home)) for path in (provider_home / "projects").rglob("*.jsonl"))
            snapshot = probe._native_snapshot(_plain_native_file(provider_home, session_id), provider_home, output, f"{ordinal:02d}-{phase}")
            row["raw_file"] = str(snapshot)
            row["raw_sha256"] = "sha256:" + hashlib.sha256(snapshot.read_bytes()).hexdigest()
        report["status"] = "PLAIN_CAMPAIGN_COMPLETE"
        return 0
    except (OSError, probe.ProbeStop, RuntimeError, ValueError) as error:
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
            probe._write_observations(output, report)
