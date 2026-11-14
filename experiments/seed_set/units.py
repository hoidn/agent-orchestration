"""Per-unit checks of the seed-set runner: physical calls, provider incidents, the session audit, disabled resumes.

- `physical_calls`: call directories the shim recorded a prompt in (a call refused by `COMPARE_MAX_CALLS` has
  none and never reached a provider).
- `provider_incident`: why a failed run is a provider or apparatus incident (rate limit, overload,
  authentication, an API or connection error, a call refused by the cap), from its calls' stdout and stderr;
  None for a natural failure, which scores 0.
- `usage_limit`: the vendor's usage-limit answer in a unit's calls. A unit cut by a usage limit is neither an
  incident nor an observation (coordinator ruling R1, 2026-11-14): starts close, and its slot runs again once.
- `audit_sessions`: every Claude session file anywhere in the unit's private home (each unit has its own home,
  so all of them belong to the unit). A session outside the unit tree's project store, more top-level sessions
  than physical calls, or an answer by another model fails the unit. Not seen: sessions written into the unit
  tree or its /tmp (the repository's own tests write session-shaped fixtures there, so they cannot be told
  apart), sessions in memory-only mounts such as /dev/shm, a CLI run with session persistence off, and direct API
  requests with the copied credential.
- `disable_resume`: the harness's resume scripts carry no reservation and no call cap; the study never resumes,
  so they are replaced by a script that refuses.
- `priced`: a unit's metered usage priced by the frozen price table, for the spend guard's settlement
  (coordinator ruling R4); `cap_command` passes the unit's worst case to the runtime as `--max-cost-usd`.
"""

import json
import os
import re
import shutil
from pathlib import Path

from experiments.compare import scan
from orchestrator.providers.pricing import priced as table_price
from orchestrator.providers.types import ProviderSessionMetadataMode
from orchestrator.providers.usage import usage_from_stdout

PROVIDER_ERRORS = re.compile(
    r"\b(?:429|529|401|403)\b|rate.?limit|usage limit|overloaded|unauthori[sz]ed|authenticat|invalid (?:api|x-api)"
    r"[ -]key|oauth|credit balance|quota|api error|connection error|econnreset|etimedout|eai_again|"
    r"refused by COMPARE_MAX_CALLS", re.I)
REFUSAL = """#!/bin/sh
echo "seed-set: $0 is disabled: the study never resumes a unit (a resume has no reservation and no call cap)" >&2
exit 64
"""


def forget_credentials(home):
    """Remove the provider credentials `prepare` copied into a unit's private home, once the unit has ended."""
    for path in Path(home).rglob("*"):
        if path.name in (".credentials.json", "auth.json") and path.is_file():
            path.unlink()


def copy_credentials(home):
    """The Claude credentials into a unit's private home, as the sandbox's `prepare_unit` copies them (from
    CLAUDE_CONFIG_DIR or ~/.claude), when the provider has a credentials file; `forget_credentials` removes them."""
    source = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path(os.environ.get("HOME") or Path.home()) / ".claude")
    source, destination = source / ".credentials.json", Path(home) / ".claude" / ".credentials.json"
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(source, destination)
        destination.chmod(0o600)


def calls(records):
    return sorted((Path(records) / "calls").glob("*"), key=lambda path: int(path.name))


def physical_calls(records):
    return sum((call / "prompt.txt").is_file() for call in calls(records))


def provider_incident(records):
    """The first provider or apparatus error line in the run's calls, or None."""
    for call in calls(records):
        for name in ("stderr.txt", "stdout.txt"):
            path = call / name
            for line in error_lines(path.read_text(errors="replace"), name) if path.is_file() else []:
                if PROVIDER_ERRORS.search(line):
                    return f"call {call.name}: {line.strip()[:300]}"


def usage_limit(records):
    """{"call", "reset", "text"} of the first call the vendor answered with a usage limit, or None. The class needs
    the stream-json result event's `api_error: usage_limit_reached` with `api_error_status: 429` (recorded in
    experiments/long_horizon_tasks/fixtures/token-usage-limit-NonZeroAgentExitCodeError.json); a 429 without it is a
    rate limit, an incident. `reset` is the `resetsAt` (epoch seconds) of the call's rejected `rate_limit_event`,
    None when the answer names none."""
    for call in calls(records):
        events = stream_events(call / "stdout.txt")
        ends = [e for e in events if e.get("type") == "result" and e.get("api_error") == "usage_limit_reached"
                and e.get("api_error_status") == 429]
        if ends:
            rejected = [e["rate_limit_info"] for e in events if e.get("type") == "rate_limit_event"
                        and isinstance(e.get("rate_limit_info"), dict) and e["rate_limit_info"].get("status") == "rejected"]
            reset = rejected[-1].get("resetsAt") if rejected else None
            return {"call": call.name, "reset": reset if type(reset) in (int, float) else None,
                    "text": str(ends[-1].get("result"))[:300]}
    return None


def stream_events(path):
    """The JSON objects among a call's stdout lines (the metered template prints stream-json); [] without one."""
    found = []
    for line in path.read_text(errors="replace").splitlines() if path.is_file() else []:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        found += [event] if isinstance(event, dict) else []
    return found


def error_lines(text, name):
    """The lines that can carry the provider's own error: all of stderr (the CLI's); of the stream-json stdout,
    lines that are not JSON and the text of a `result` event marked `is_error`, never the transcript's tool output,
    where a task's own text can name 401 or oauth (review2 minor 6)."""
    for line in text.splitlines():
        try:
            event = json.loads(line) if name == "stdout.txt" else None
        except ValueError:
            event = None
        if not isinstance(event, dict):
            yield line
        elif event.get("type") == "result" and event.get("is_error"):
            yield str(event.get("result"))
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


def priced(records, table, per_call):
    """{"usd", "calls": {call: usd}, "missing": [calls]} of a unit's physical calls (rounded to 1e-6 USD). A call is
    priced from the stream-json result event the metered template prints: the larger of its `modelUsage` at the
    table's ordinary rates and the CLI's reported `total_cost_usd` (the CLI applies a long-context rate per request,
    which the summed usage cannot). A call whose usage is missing, incomplete or unpriced counts at `per_call`, the
    worst case, and is listed in `missing`. A call the shim refused (no prompt) reached no provider and costs
    nothing."""
    found, missing = {}, []
    for call in calls(records):
        if not (call / "prompt.txt").is_file():
            continue
        cost = call_cost(call, table)
        if cost is None:
            missing.append(call.name)
        found[call.name] = round(per_call if cost is None else cost, 6)
    return {"usd": round(sum(found.values()), 6), "missing": missing, "calls": found}


def call_cost(call, table):
    stdout = call / "stdout.txt"
    usage = usage_from_stdout(ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value,
                              stdout.read_bytes() if stdout.is_file() else b"", model=None)
    if usage.get("status") != "reported" or usage.get("complete") is not True:
        return None
    value, reported = table_price(usage["rows"], table), usage.get("reported_cost_usd")
    return None if value is None else max(value, reported or 0)


def cap_command(script, usd):
    """Append the runtime's own spend cap, `--max-cost-usd`, to the harness's one-line run command."""
    text = Path(script).read_text()
    if text.count("\n") != 1 or " -m orchestrator run " not in text:
        raise SystemExit(f"{script} is not the harness's one-line run command; no cap can be passed")
    Path(script).write_text(f"{text.rstrip()} --max-cost-usd {usd:.6g}\n")


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
