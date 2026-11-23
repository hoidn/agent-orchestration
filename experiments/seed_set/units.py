"""Per-unit checks of the seed-set runner: physical calls, provider incidents, the session audit, disabled resumes.

- `physical_calls`: call directories the shim recorded a prompt in (a call refused by `COMPARE_MAX_CALLS` has
  none and never reached a provider).
- `provider_incident`: why a failed run is a provider or apparatus incident (rate limit, overload,
  authentication, an API or connection error, a call refused by the cap), from its calls' stdout and stderr;
  None for a natural failure, which scores 0.
- `usage_limit`: the vendor's usage-limit answer in a unit's calls, or any other shape that may be one (fail closed,
  review3 X2: flagged `UNRECOGNISED`, for the operator to read the raw result). A unit cut by a usage limit is
  neither an incident nor an observation (coordinator ruling R1, 2026-11-14): starts close, and its slot runs
  again once. Paid extra usage (`PAID`) pauses the same way; a call that ended normally stays an observation, and
  one that did not cuts its unit (coordinator ruling on fix round 4).
- `audit_sessions`: every Claude session file anywhere in the unit's private home (each unit has its own home,
  so all of them belong to the unit). A session outside the unit tree's project store, more top-level sessions
  than physical calls, or an answer by another model fails the unit. Not seen: sessions written into the unit
  tree or its /tmp (the repository's own tests write session-shaped fixtures there, so they cannot be told
  apart), sessions in memory-only mounts such as /dev/shm, a CLI run with session persistence off, and direct API
  requests with the copied credential.
- `isolation_breach`: a session whose `system/init` event lists a tool outside `sandbox.CLAUDE_TOOLS` (an
  allowlist: an MCP, Artifact, agent or wake-up tool, or a built-in tool a CLI update added), any MCP server, a
  skill named `<source>:<skill>` (a plugin's or the account's) or a plugin that is not `@builtin`; a clean
  session under `sandbox.CLAUDE_SETTINGS` lists none (fixture `claude-2.1.330-isolated-init.json`). The account's
  synced skills appeared only in the continuations' init events of the first paid run, not in its first one, so
  the skill rule may miss them; the tool allowlist and the session audit's rule on MCP logs outside the session
  store do not depend on when the CLI lists what. The kit reads a call's stream only after it ends, so a breach
  is an incident of the settled unit, not a refusal before the session's first request.
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

from experiments.compare import sandbox, scan
from experiments.seed_set import reaper
from orchestrator.providers.pricing import priced as table_price
from orchestrator.providers.types import ProviderSessionMetadataMode
from orchestrator.providers.usage import usage_from_stdout

# The vendor's session- and usage-limit wordings, kept here only: an error line matching one is a possible usage limit
# (`usage_limit`) and a provider error (`provider_incident`).
LIMIT_WORDINGS = (r"hit your .*limit", r"usage limit", r"session limit", r"weekly limit")
LIMIT_TEXT = re.compile("|".join(LIMIT_WORDINGS), re.I)
UNRECOGNISED = "unrecognised limit shape"
# The rule that recognised a possible usage limit (`limit_rule`), named in its pause and in every refusal it causes.
RECORDED = "the recorded answer (api_error usage_limit_reached, status 429)"
STATUS_429 = "an error result with status 429"
REJECTED = "an error result beside a rejected rate_limit_event"
WORDING = "a limit wording in an error line of a call that did not succeed"
# Paid extra usage (final scoped check M1): the CLI's own rate_limit_event shows overage in use (`isUsingOverage` or
# `overageInUse` true), or a rejected limit with overage allowed. The long-horizon kit's `passthrough.PAID_USAGE`
# reads the API's headers and is broader (overage allowed on any answer). The call may end normally; it is billed
# past the subscription's allowance, so it pauses like a limit (and cuts a call that did not end normally).
PAID = "paid extra usage: a rate_limit_event with overage in use"
OVERAGE_ALLOWED = ("allowed", "allowed_warning")
OLDER_RESET = re.compile(r"usage limit reached\|(\d{9,11})\b", re.I)  # an older CLI: "...|<epoch seconds>"
PROVIDER_ERRORS = re.compile(
    r"\b(?:429|529|401|403)\b|rate.?limit|overloaded|unauthori[sz]ed|authenticat|invalid (?:api|x-api)"
    r"[ -]key|oauth|credit balance|quota|api error|connection error|econnreset|etimedout|eai_again|"
    r"refused by COMPARE_MAX_CALLS|" + "|".join(LIMIT_WORDINGS), re.I)
REFUSAL = """#!/bin/sh
echo "seed-set: $0 is disabled: the study never resumes a unit (a resume has no reservation and no call cap)" >&2
exit 64
"""


def forget_credentials(home):
    """Remove the provider credentials `prepare` copied into a unit's private home, once the unit has ended; return
    the paths removed."""
    removed = [path for path in Path(home).rglob("*") if path.name in (".credentials.json", "auth.json")
               and path.is_file()]
    for path in removed:
        path.unlink()
    return removed


def session_alive(pgid_file):
    """Whether the process group a launch's guard wrote to `pgid_file` (`reaper.guard`: the session's id, then its
    start time) still runs; False without the file, or when a live process has that pid but another start time (a
    stale file, n9: Linux reuses no pid while its process group lives, so that group is gone)."""
    if not Path(pgid_file).is_file() or not (recorded := Path(pgid_file).read_text().split()):
        return False  # no file, or an empty one: the guard died before it recorded a session
    sid, *started = map(int, recorded)
    if (leader := reaper.stat(sid)) is not None and started and leader[1] != started[0]:
        return False
    try:
        os.killpg(sid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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
    """The first provider or apparatus error line in the run's calls that did not succeed (`succeeded`), or None."""
    for call in calls(records):
        if succeeded(stream_events(call / "stdout.txt")):
            continue
        for name in ("stderr.txt", "stdout.txt"):
            path = call / name
            for line in error_lines(path.read_text(errors="replace"), name) if path.is_file() else []:
                if PROVIDER_ERRORS.search(line):
                    return f"call {call.name}: {line.strip()[:300]}"


def usage_limit(records, cutting=False):
    """{"call", "rule", "reset", "text", "raw"} of the first call the vendor may have answered with a usage limit, or
    None; with "flag": `UNRECOGNISED` unless `rule` is `PAID` or `RECORDED` (the stream-json result event's `api_error:
    usage_limit_reached` with `api_error_status: 429`, experiments/long_horizon_tasks/fixtures/
    token-usage-limit-NonZeroAgentExitCodeError.json). `rule` is the rule that fired (`limit_rule`) and `text` the
    line it read (the last error result's text; for `WORDING`, the matched error line). `reset` is the `resetsAt`
    (epoch seconds) of the call's last rejected `rate_limit_event` that names one, else the epoch an older CLI's
    wording names (`Claude AI usage limit reached|<epoch>`), None when the answer names none; `raw` is the call's
    directory. Without `cutting`, the first call with paid extra usage comes before any earlier call, so the pause
    names it and only `resume-after-limit` reopens (review 4 M1). With `cutting`, only a limit that cuts its unit:
    paid extra usage on a call that ended normally is passed over (that call is an observation, and only pauses;
    coordinator ruling on fix round 4)."""
    found = []
    for call in calls(records):
        events = stream_events(call / "stdout.txt")
        if (rule := limit_rule(call, events)) and not (cutting and rule == PAID and succeeded(events)):
            found.append(limit_facts(call, events, rule))
    paid = [] if cutting else [facts for facts in found if facts["rule"] == PAID]
    return next(iter(paid + found), None)


def limit_facts(call, events, rule):
    """The facts `usage_limit` returns for a call where `rule` fired."""
    rejected = [e["rate_limit_info"] for e in events if rejected_event(e)]
    named = next((info["resetsAt"] for info in reversed(rejected) if type(info.get("resetsAt")) in (int, float)), None)
    errors = [e for e in events if e.get("type") == "result" and e.get("is_error")]
    text = next(limit_lines(call), "") if rule == WORDING or not errors else errors[-1].get("result")
    return {"call": call.name, "rule": rule, "reset": older_reset(call) if named is None else named,
            "text": str(text)[:300], "raw": str(call)} | ({} if rule in (RECORDED, PAID) else {"flag": UNRECOGNISED})


def older_reset(call):
    """The reset epoch an older CLI's wording names in the call's error lines, or None."""
    return next((int(found.group(1)) for line in limit_lines(call) if (found := OLDER_RESET.search(line))), None)


def limit_rule(call, events):
    """`PAID` for paid extra usage (`paid_usage`, whether or not the call succeeded); `RECORDED` for the vendor's
    recorded answer; else, each flagged `UNRECOGNISED` by `usage_limit`: `STATUS_429` for an error result with
    status 429 (a number or a string), `REJECTED` for an error result beside a rejected `rate_limit_event`,
    `WORDING` for a call that did not succeed with an error line in a limit wording that no other named status
    explains; else None. A model's or a tool's text is never read (`error_lines`)."""
    if any(map(paid_usage, events)):
        return PAID
    results = [e for e in events if e.get("type") == "result"]
    if recorded_answer(results):
        return RECORDED
    errors = [e for e in results if e.get("is_error")]
    statuses = error_statuses(errors)
    if "429" in statuses:
        return STATUS_429
    if errors and any(map(rejected_event, events)):
        return REJECTED
    return WORDING if worded_failure(call, events, statuses) else None


def worded_failure(call, events, statuses):
    """A call that did not succeed with an error line in a limit wording, and no named status, which would be
    something else."""
    return not succeeded(events) and not statuses and next(limit_lines(call), None) is not None


def succeeded(events):
    """Whether the call ended with a result event and no error result. A warning such a call printed is neither a
    usage limit nor a provider error (re-review N1); a call with an error result, or with no result event at all
    (a crash, a kill, a refusal by the shim), did not succeed."""
    results = [e for e in events if e.get("type") == "result"]
    return bool(results) and not any(e.get("is_error") for e in results)


def recorded_answer(results):
    """Whether a result event is the vendor's recorded usage-limit answer."""
    return any(e.get("api_error") == "usage_limit_reached" and e.get("api_error_status") == 429 for e in results)


def error_statuses(errors):
    """The API statuses the error results name, as strings (a status may be printed as a number or a string)."""
    return {str(e["api_error_status"]) for e in errors if e.get("api_error_status") is not None}


def rejected_event(event):
    info = event.get("rate_limit_info") if event.get("type") == "rate_limit_event" else None
    return isinstance(info, dict) and info.get("status") == "rejected"


def paid_usage(event):
    """Whether a rate_limit_event shows overage in use (`isUsingOverage` or `overageInUse` true), or a rejected limit
    with overage allowed."""
    info = event.get("rate_limit_info") if event.get("type") == "rate_limit_event" else None
    if not isinstance(info, dict):
        return False
    in_use = any(str(info.get(key)).lower() == "true" for key in ("isUsingOverage", "overageInUse"))
    return in_use or (info.get("status") == "rejected" and info.get("overageStatus") in OVERAGE_ALLOWED)


def limit_lines(call):
    """The call's provider error lines (`error_lines`) in a usage-limit wording."""
    for name in ("stderr.txt", "stdout.txt"):
        path = call / name
        yield from (line for line in (error_lines(path.read_text(errors="replace"), name) if path.is_file() else [])
                    if LIMIT_TEXT.search(line))


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
    """The lines that can carry the provider's own error: all of stderr (the CLI's); of the stream-json stdout, the
    plain lines and the text of a `result` event marked `is_error`. Never the transcript's tool output or model
    text, where a task's own text can name 401 or oauth (review2 minor 6), and never a stream event cut mid-write
    (a line that starts with `{` and is not JSON: a SIGKILL during a write leaves one; re-review N1)."""
    for line in text.splitlines():
        if name != "stdout.txt" or not line.lstrip().startswith("{"):
            yield line
            continue
        event = json_object(line)
        if event.get("type") == "result" and event.get("is_error"):
            yield str(event.get("result"))


def json_object(line):
    """The JSON object a stream line holds, or {} for a line cut mid-write."""
    try:
        event = json.loads(line)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


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


def isolation_breach(records):
    """Why a unit's sessions were not isolated (the first `system/init` event of its calls that lists one), or None."""
    for call in calls(records):
        for event in stream_events(call / "stdout.txt"):
            if (event.get("type"), event.get("subtype")) == ("system", "init") and (found := foreign(event)):
                return f"call {call.name}: the session was given {found[:5]} ({len(found)} in all)"
    return None


def foreign(init):
    """What an init event lists beyond a clean session's: a tool outside `sandbox.CLAUDE_TOOLS`, any MCP server, a
    skill named `<source>:<skill>`, a plugin that is not `@builtin`."""
    tools = [name for name in init.get("tools") or [] if name not in sandbox.CLAUDE_TOOLS]
    servers = [server.get("name") for server in init.get("mcp_servers") or [] if isinstance(server, dict)]
    skills = [name for name in init.get("skills") or [] if ":" in str(name)]
    plugins = [plugin.get("source") for plugin in init.get("plugins") or []
               if isinstance(plugin, dict) and not str(plugin.get("source")).endswith("@builtin")]
    return tools + servers + skills + plugins


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
    if usage.get("status") != "reported" or usage.get("complete") is not True or not usage.get("rows"):
        return None  # no usage row names a model: the worst case (review3 minor 4)
    value, reported = table_price(usage["rows"], table), usage.get("reported_cost_usd")
    return None if value is None else max(value, reported or 0)


def cap_command(script, usd):
    """End the harness's one-line run command with the runtime's own spend cap, `--max-cost-usd` (replacing the cap
    an earlier, refused start of the same judge wrote)."""
    text = Path(script).read_text()
    if text.count("\n") != 1 or " -m orchestrator run " not in text:
        raise SystemExit(f"{script} is not the harness's one-line run command; no cap can be passed")
    Path(script).write_text(re.sub(r" --max-cost-usd \S+$", "", text.rstrip()) + f" --max-cost-usd {usd:.6g}\n")


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
