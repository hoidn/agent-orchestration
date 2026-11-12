"""Per-unit checks of the seed-set runner: physical calls, provider incidents, the session audit, disabled resumes.

- `physical_calls`: call directories the shim recorded a prompt in (a call refused by `COMPARE_MAX_CALLS` has
  none and never reached a provider).
- `provider_incident`: why a failed run is a provider or apparatus incident (rate limit, overload,
  authentication, an API or connection error, a call refused by the cap), from its calls' stdout and stderr;
  None for a natural failure, which scores 0.
- `audit_sessions`: every Claude session file anywhere in the unit's private home (each unit has its own home,
  so all of them belong to the unit). A session outside the unit tree's project store, more top-level sessions
  than physical calls, or an answer by another model fails the unit. Not seen: sessions written into the unit
  tree or its /tmp (the repository's own tests write session-shaped fixtures there, so they cannot be told
  apart), sessions in memory-only mounts such as /dev/shm, a CLI run with session persistence off, and direct API
  requests with the copied credential.
- `disable_resume`: the harness's resume scripts carry no reservation and no call cap; the study never resumes,
  so they are replaced by a script that refuses.
"""

import json
import re
from pathlib import Path

from experiments.compare import scan

PROVIDER_ERRORS = re.compile(
    r"\b(?:429|529|401|403)\b|rate.?limit|usage limit|overloaded|unauthori[sz]ed|authenticat|invalid (?:api|x-api)"
    r"[ -]key|oauth|credit balance|quota|api error|connection error|econnreset|etimedout|eai_again|"
    r"refused by COMPARE_MAX_CALLS", re.I)
REFUSAL = """#!/bin/sh
echo "seed-set: $0 is disabled: the study never resumes a unit (a resume has no reservation and no call cap)" >&2
exit 64
"""


def calls(records):
    return sorted((Path(records) / "calls").glob("*"), key=lambda path: int(path.name))


def physical_calls(records):
    return sum((call / "prompt.txt").is_file() for call in calls(records))


def provider_incident(records):
    """The first provider or apparatus error line in the run's calls, or None."""
    for call in calls(records):
        for name in ("stderr.txt", "stdout.txt"):
            path = call / name
            for line in path.read_text(errors="replace").splitlines() if path.is_file() else []:
                if PROVIDER_ERRORS.search(line):
                    return f"call {call.name}: {line.strip()[:300]}"
    return None


def _session(path):
    try:
        with path.open(errors="replace") as stream:
            row = json.loads(stream.readline())
    except (OSError, ValueError):
        return False
    return isinstance(row, dict) and ("sessionId" in row or row.get("type") in ("assistant", "user", "summary"))


def audit_sessions(home, tree, made, model):
    """(failure reason or None, policy hit or None, session files) for one unit's private home."""
    sessions = sorted(path for path in Path(home).rglob("*.jsonl") if _session(path))
    projects = Path(home) / ".claude" / "projects"
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(tree))
    scoped = [p for p in sessions if p.is_relative_to(projects) and len(p.relative_to(projects).parts) >= 2
              and (p.relative_to(projects).parts[0] == slug or p.relative_to(projects).parts[0].startswith(slug + "-"))]
    top = [p for p in scoped if len(p.relative_to(projects).parts) == 2]
    try:
        hits = list(scan.model_hits(sessions, model))
    except SystemExit as error:
        return f"unreadable session: {error}", None, sessions
    policy = scan.model_policy(hits)
    if policy:
        return f"a session answered by another model: {hits[0]['text']}", policy, sessions
    if len(scoped) != len(sessions):
        return f"sessions outside the unit tree's store: {[str(p) for p in sessions if p not in scoped]}", None, sessions
    if len(top) > made:
        return f"{len(top)} sessions for {made} recorded calls", None, sessions
    return None, None, sessions


def disable_resume(*scripts):
    for script in scripts:
        Path(script).write_text(REFUSAL)


def cli_cost(home):
    """The cost a Claude CLI reported in its session transcripts under `home` (`costUSD` or `total_cost_usd`
    fields), or None when it reported none: the study's `claude -p` text output carries no cost line."""
    found = []
    for path in Path(home).glob(".claude/projects/**/*.jsonl"):
        for line in path.read_text(errors="replace").splitlines():
            found += [float(v) for v in re.findall(r'"(?:costUSD|total_cost_usd)":\s*([0-9.]+)', line)]
    return sum(found) if found else None
