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
- A Codex call (the shim's `provider.txt` says `CODEX`) is read from its `exec --json` events: success is a completed
  turn; its `error`, `turn.failed` and `error`-item messages are its error lines, each an incident when it did not
  succeed; a limit is read from those lines (429, a limit wording) and from the last `rate_limits` snapshot of the
  call's own rollout (matched by `thread_id`; a used-up window names the reset; credits held with a limit reached is
  `CODEX_PAID`, credits held without one is `credit_balance`, which closes the Codex starts: ruling L-R7). No Codex
  limit answer is recorded yet, so every Codex rule but `CODEX_PAID` is flagged `UNRECOGNISED`. Its session audit is
  `audit_rollouts` (its caller chooses it), its allowlist `CODEX_ITEMS`.
- `audit_sessions`: every Claude session file anywhere in the unit's private home (each unit has its own home,
  so all of them belong to the unit). A session outside the unit tree's project store, more top-level sessions
  than physical calls, or an answer by another model fails the unit. Not seen: sessions written into the unit
  tree or its /tmp (the repository's own tests write session-shaped fixtures there, so they cannot be told
  apart), sessions in memory-only mounts such as /dev/shm, a CLI run with session persistence off, and direct API
  requests with the copied credential. `nested_sessions` counts the session files below the store's top level,
  which the settlement records (the seed evaluation's nested-session switch).
- `isolation_breach`: a session whose `system/init` event lists a tool outside `sandbox.CLAUDE_TOOLS` (an
  allowlist: an MCP, Artifact, agent or wake-up tool, or a built-in tool a CLI update added), any MCP server, a
  skill named `<source>:<skill>` (a plugin's or the account's) or a plugin that is not `@builtin`; a clean
  session under `sandbox.CLAUDE_SETTINGS` lists none (fixture `claude-2.1.330-isolated-init.json`). The account's
  synced skills appeared only in the continuations' init events of the first paid run, not in its first one, so
  the skill rule may miss them. Connectors still `pending` at the first init event list no `mcp__*` tool there
  (2.1.327 fixture); the `mcp_servers` rule catches them, and the session audit's rule on MCP logs outside the
  session store does not depend on when the CLI lists what. The kit reads a call's stream only after it ends, so a breach
  is an incident of the settled unit, not a refusal before the session's first request.
- `disable_resume`: the harness's resume scripts carry no reservation and no call cap; the study never resumes,
  so they are replaced by a script that refuses.
- `priced`: a unit's metered usage priced by the frozen price table, for the spend guard's settlement
  (coordinator ruling R4); `cap_command` passes the unit's worst case to the runtime as `--max-cost-usd`.
- `login_expiry`, `require_login`: the access token's expiry, the only thing read from the login file a unit
  copies, and the refusal of a unit's start unless the token outlives the unit's wall-clock limit plus
  `EXPIRY_MARGIN_SEC` (coordinator ruling R16). For Codex (`codex_login_expiry`, ruling L-R3) also whether the file
  holds an API key or is not a ChatGPT login, either of which refuses.
- `remove_tree`: a unit's tree removed, read-only directories its agent's own tests left included, no link
  followed and nothing outside its root touched; it reports a tree it cannot remove instead of raising, so the
  settlement is not lost (ruling R16).
"""

import base64
import json
import os
import re
import shutil
import stat
import time
from datetime import datetime
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
CODEX = "codex"  # a call's provider as the shim records it (`calls/<n>/provider.txt`, "claude" or "codex")
# The `item.*` types a Codex call's `exec --json` output may carry (an allowlist, like `sandbox.CLAUDE_TOOLS`: an MCP
# tool call, a web search, a sub-agent's or collaboration item, an error item, or a type a CLI update added is a
# finding). Chosen from the types the harness's own Codex reader accepts (`session_transport`) plus the plan list;
# the paid Luna smoke corrects it from evidence.
CODEX_ITEMS = frozenset(("agent_message", "reasoning", "command_execution", "file_change", "todo_list"))
CODEX_REACHED = "a Codex session record whose rate_limits show a limit reached, in a call that did not succeed"
CODEX_PAID = "paid credits: a Codex session record with a credit balance held and a limit reached"
CODEX_CREDITS = "the ChatGPT account holds a credit balance (a Codex session record's rate_limits.credits.has_credits)"
PAID_RULES = (PAID, CODEX_PAID)  # paid extra usage: pauses even a call that ended normally, which stays scored
EXPIRY_MARGIN_SEC = 900  # a unit's preparation before its launch, and the CLI refreshing ahead of expiry (R16)
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


def login_file(provider="claude"):
    """The login file a unit copies, where the sandbox's `prepare_unit` finds it: for Claude CLAUDE_CONFIG_DIR or
    ~/.claude, `.credentials.json`; for Codex CODEX_HOME or ~/.codex, `auth.json`."""
    home = Path(os.environ.get("HOME") or Path.home())
    if provider == CODEX:
        return Path(os.environ.get("CODEX_HOME") or home / ".codex") / "auth.json"
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude") / ".credentials.json"


def login_expiry(path=None, provider="claude"):
    """Epoch seconds at which the access token in the login file (`login_file`) expires: for Claude
    `claudeAiOauth.expiresAt`, epoch milliseconds; for Codex `codex_login_expiry`. Only that number leaves this
    function, never the token, and no message holds the file's content. Fails closed (SystemExit) on a missing or
    unreadable file, a missing field, or a field that is not a number of a time the clock can name (NaN, infinite
    or past the calendar)."""
    path = Path(path or login_file(provider))
    if provider == CODEX:
        return codex_login_expiry(path)
    try:
        expires = json.loads(path.read_text())["claudeAiOauth"]["expiresAt"]
        expires = clock_time(expires, 1000)
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        raise SystemExit(f"{path}: no access-token expiry could be read (claudeAiOauth.expiresAt, epoch "
                         "milliseconds); no unit starts") from None
    return expires


def clock_time(value, per_second=1):
    """`value / per_second` as epoch seconds, if `value` is a number of a time the clock can name; else TypeError,
    ValueError, OverflowError or OSError."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("not a number")
    datetime.fromtimestamp(value / per_second)  # OverflowError, ValueError or OSError for a time it cannot name
    return value / per_second


def codex_login_expiry(path):
    """The Codex form of `login_expiry` (ruling L-R3): from the Codex CLI's `auth.json` (`OPENAI_API_KEY`, `auth_mode`,
    `tokens.access_token`) only whether an API key is set, whether it is a ChatGPT login, and the access token's JWT
    `exp` claim (the payload segment decoded, not verified). Refuses (SystemExit) an unreadable file, an API key, a
    login that is not ChatGPT's (an `auth_mode` that is not exactly "chatgpt", missing included, or no
    `tokens.access_token`), and a token whose
    expiry cannot be read. No message holds a token or any other value of the file."""
    try:
        login = json.loads(path.read_text())
    except (OSError, ValueError):
        login = None
    if not isinstance(login, dict):
        raise SystemExit(f"{path}: the Codex login file cannot be read; no unit starts")
    if login.get("OPENAI_API_KEY"):
        raise SystemExit(f"{path}: the Codex login holds an API key (OPENAI_API_KEY); the study runs on the ChatGPT "
                         "subscription login only, with no API key; no unit starts")
    tokens = login.get("tokens")
    if login.get("auth_mode") != "chatgpt" or not isinstance(tokens, dict) or not tokens.get("access_token"):
        raise SystemExit(f"{path}: not a ChatGPT login (auth_mode chatgpt with tokens.access_token); no unit starts")
    try:
        return clock_time(jwt_claims(tokens["access_token"])["exp"])
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError, OSError):
        raise SystemExit(f"{path}: no access-token expiry could be read (the JWT exp claim of tokens.access_token); "
                         "no unit starts") from None


def jwt_claims(token):
    """The claims of a JWT's payload segment, decoded and not verified."""
    segment = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    if not isinstance(claims, dict):
        raise TypeError("the payload is not an object")
    return claims


def expiry_text(expires, now=None):
    """`expires <ISO time>, in <N> minutes` for an expiry in epoch seconds."""
    left = expires - (time.time() if now is None else now)
    moment = datetime.fromtimestamp(expires).astimezone().isoformat(timespec="seconds")
    return f"expires {moment}, in {left // 60:.0f} minutes"


def require_login(seconds, now=None, provider="claude"):
    """Refuse a unit's start (SystemExit) unless the login's access token outlives `seconds` (the unit's wall-clock
    limit, at which its launch guard kills it) plus `EXPIRY_MARGIN_SEC` (ruling R16; for Codex, `provider` "codex",
    also unless it is a ChatGPT login with no API key, L-R3): a unit alive at the expiry fails when the owner's side
    refreshes first, or refreshes the token itself and rotates the owner's."""
    expires = login_expiry(provider=provider)
    if expires - (time.time() if now is None else now) < seconds + EXPIRY_MARGIN_SEC:
        raise SystemExit(f"the login's access token {expiry_text(expires, now)}; a unit needs "
                         f"{(seconds + EXPIRY_MARGIN_SEC) // 60:.0f} minutes. Nothing started: start again after "
                         "the owner's own session has refreshed the login")


def remove_tree(path, root):
    """Remove a unit's tree under `root`, read-only directories its agent's own tests left included: each directory
    gets u+rwx before it is entered, and no symbolic link is followed (`os.walk` lists a linked directory without
    entering it, and it is skipped; `shutil.rmtree` unlinks links). A tree that is a link, or that does not resolve
    under `root`, is not touched. None once removed, else why the tree is left."""
    path = Path(path)
    if path.is_symlink() or not path.resolve().is_relative_to(Path(root).resolve()):
        return f"{path} is a symbolic link or not under {root}: not touched"
    try:
        os.chmod(path, os.lstat(path).st_mode | stat.S_IRWXU)
        for parent, directories, _ in os.walk(path):
            for name in directories:
                if not os.path.islink(child := os.path.join(parent, name)):
                    os.chmod(child, os.lstat(child).st_mode | stat.S_IRWXU)
        shutil.rmtree(path)
    except OSError as error:
        return f"{type(error).__name__}: {error}"
    return None


def copy_credentials(home):
    """The Claude credentials into a unit's private home, as the sandbox's `prepare_unit` copies them (from
    `login_file`), when the provider has a credentials file; `forget_credentials` removes them."""
    source, destination = login_file(), Path(home) / ".claude" / ".credentials.json"
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(source, destination)
        destination.chmod(0o600)


def calls(records):
    return sorted((Path(records) / "calls").glob("*"), key=lambda path: int(path.name))


def physical_calls(records):
    return sum((call / "prompt.txt").is_file() for call in calls(records))


def provider(call):
    """The CLI the shim recorded for a call (`provider.txt`: "claude" or `CODEX`). The shim writes it first, before
    the call's argv and prompt, so a call directory without it never reached a provider ("claude": nothing to
    read); a physical call (a prompt) without it, or a file naming another CLI, refuses (SystemExit)."""
    path = call / "provider.txt"
    if not path.is_file() and not (call / "prompt.txt").is_file():
        return "claude"
    name = path.read_text().strip() if path.is_file() else None
    if name not in ("claude", CODEX):
        raise SystemExit(f"{call}: the shim's provider record is {name!r}, not claude or codex; nothing is read")
    return name


def provider_incident(records):
    """The first provider or apparatus error line in the run's calls that did not succeed (`succeeded`), or None. Of
    a Codex call every error line of its stdout counts (an `error` or `turn.failed` event is the CLI's own), and of
    its stderr the lines in a provider-error wording, as for Claude."""
    for call in calls(records):
        if succeeded(stream_events(call / "stdout.txt"), provider(call)):
            continue
        for name, line in call_errors(call):
            if PROVIDER_ERRORS.search(line) or (provider(call) == CODEX and name == "stdout.txt"):
                return f"call {call.name}: {line.strip()[:300]}"


def call_errors(call):
    """(file name, line) of the call's provider error lines (`error_lines`), stderr first."""
    for name in ("stderr.txt", "stdout.txt"):
        path = call / name
        yield from ((name, line) for line in (error_lines(path.read_text(errors="replace"), name, provider(call))
                                              if path.is_file() else []))


def usage_limit(records, cutting=False, home=None):
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
    coordinator ruling on fix round 4). A Codex call (`codex_limit_rule`) also reads the last `rate_limits` snapshot of
    its own rollout in the unit's private home `home`, when given (`call_snapshot`); its used-up windows name the
    reset. `PAID_RULES` are the paid-usage rules."""
    found, by_thread = [], threads(home) if home else {}
    for call in calls(records):
        events, codex = stream_events(call / "stdout.txt"), provider(call) == CODEX
        rule = codex_limit_rule(call, events, by_thread) if codex else limit_rule(call, events)
        if rule and not (cutting and rule in PAID_RULES and succeeded(events, provider(call))):
            found.append(codex_limit_facts(call, events, rule, by_thread) if codex else limit_facts(call, events, rule))
    paid = [] if cutting else [facts for facts in found if facts["rule"] in PAID_RULES]
    return next(iter(paid + found), None)


def limit_facts(call, events, rule):
    """The facts `usage_limit` returns for a call where `rule` fired."""
    rejected = [e["rate_limit_info"] for e in events if rejected_event(e)]
    named = next((info["resetsAt"] for info in reversed(rejected) if type(info.get("resetsAt")) in (int, float)), None)
    errors = [e for e in events if e.get("type") == "result" and e.get("is_error")]
    text = next(limit_lines(call), "") if rule == WORDING or not errors else errors[-1].get("result")
    return {"call": call.name, "rule": rule, "reset": older_reset(call) if named is None else named,
            "text": str(text)[:300], "raw": str(call)} | ({} if rule in (RECORDED, PAID) else {"flag": UNRECOGNISED})


def codex_limit_facts(call, events, rule, by_thread):
    """`limit_facts` of a Codex call: the reset from its own session record's snapshot (`window_reset`), the text
    its first limit line, else its last error line."""
    lines = [line for _, line in call_errors(call)]
    text = next(limit_lines(call), None) or (lines[-1] if lines else "")
    return {"call": call.name, "rule": rule, "reset": window_reset(call_snapshot(events, by_thread)),
            "text": str(text)[:300], "raw": str(call)} | ({} if rule == CODEX_PAID else {"flag": UNRECOGNISED})


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


def codex_limit_rule(call, events, by_thread):
    """A Codex call's limit rule, read with the snapshot of its own rollout (`call_snapshot`), each but `CODEX_PAID`
    flagged `UNRECOGNISED` (no recorded Codex limit answer exists yet): `CODEX_PAID` when credits are held
    (`held`) and a limit is reached (`reached`), whether or not the call succeeded; else, for a call that did not
    succeed, `CODEX_REACHED` when a limit is reached, `STATUS_429` for an error line naming status 429, `WORDING` for
    one in a limit wording; else None. Credits held without a reached limit are no limit: `credit_balance` names
    them, the runner then closes the Codex starts only (ruling L-R7), and the call is scored as what it is."""
    snapshot = call_snapshot(events, by_thread)
    if held(snapshot) and reached(snapshot):
        return CODEX_PAID
    if succeeded(events, CODEX):
        return None
    if reached(snapshot):
        return CODEX_REACHED
    lines = [line for _, line in call_errors(call)]
    if any(re.search(r"\b429\b", line) for line in lines):
        return STATUS_429
    return WORDING if any(LIMIT_TEXT.search(line) for line in lines) else None


def rollouts(home):
    """The Codex session records (`rollout-*.jsonl`) anywhere under a unit's private home, oldest name first."""
    return sorted((path for path in Path(home).rglob("rollout-*.jsonl") if path.is_file()), key=lambda path: path.name)


def rollout_id(path):
    """The session id a rollout's first row (`session_meta.payload.id`) names, or None."""
    with path.open(errors="replace") as handle:
        payload = json_object(handle.readline()).get("payload")
    return payload.get("id") if isinstance(payload, dict) else None


def threads(home):
    """{session id: rollout} of the rollouts under `home`."""
    return {rollout_id(path): path for path in rollouts(home)}


def call_thread(events):
    """The `thread_id` of a Codex call's `thread.started` event, or None."""
    return next((e["thread_id"] for e in events if e.get("type") == "thread.started" and e.get("thread_id")), None)


def call_snapshot(events, by_thread):
    """The last `rate_limits` snapshot of the call's own rollout (matched by `call_thread`), or {}."""
    path = by_thread.get(call_thread(events))
    return next(iter(reversed(list(snapshots(path)))), {}) if path else {}


def snapshots(path):
    """The `rate_limits` objects of a rollout's `token_count` events, in order; a line cut mid-write is skipped."""
    for line in path.read_text(errors="replace").splitlines():
        payload = json_object(line).get("payload")
        if isinstance(payload, dict) and payload.get("type") == "token_count" and isinstance(
                payload.get("rate_limits"), dict):
            yield payload["rate_limits"]


def held(snapshot):
    """Whether a `rate_limits` snapshot shows a credit balance held (`credits.has_credits` true)."""
    credits = snapshot.get("credits")
    return isinstance(credits, dict) and credits.get("has_credits") is True


def credit_balance(home):
    """`CODEX_CREDITS` when any `rate_limits` snapshot of a rollout under `home` shows credits held, else None. The
    plan's default requires credits off on the ChatGPT account: the study closes the Codex starts (ruling L-R7)."""
    return CODEX_CREDITS if any(held(snapshot) for path in rollouts(home) for snapshot in snapshots(path)) else None


def used_up(snapshot):
    """The snapshot's windows (`primary`, `secondary`) whose `used_percent` is at least 100."""
    return [window for window in (snapshot.get("primary"), snapshot.get("secondary")) if isinstance(window, dict)
            and type(window.get("used_percent")) in (int, float) and window["used_percent"] >= 100]


def reached(snapshot):
    """Whether a `rate_limits` snapshot names a reached limit (`rate_limit_reached_type`) or a used-up window."""
    return bool(snapshot.get("rate_limit_reached_type") or used_up(snapshot))


def window_reset(snapshot):
    """The latest `resets_at` (epoch seconds) of the snapshot's used-up windows, or None."""
    return max((window["resets_at"] for window in used_up(snapshot) if type(window.get("resets_at")) is int),
               default=None)


def worded_failure(call, events, statuses):
    """A call that did not succeed with an error line in a limit wording, and no named status, which would be
    something else."""
    return not succeeded(events) and not statuses and next(limit_lines(call), None) is not None


def succeeded(events, provider="claude"):
    """Whether the call ended with a result event and no error result. A warning such a call printed is neither a
    usage limit nor a provider error (re-review N1); a call with an error result, or with no result event at all
    (a crash, a kill, a refusal by the shim), did not succeed. A Codex call (`exec --json`) succeeded when its turn
    completed (`turn.completed`) and none failed (`turn.failed`)."""
    if provider == CODEX:
        kinds = [e.get("type") for e in events]
        return "turn.completed" in kinds and "turn.failed" not in kinds
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
    yield from (line for _, line in call_errors(call) if LIMIT_TEXT.search(line))


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


def error_lines(text, name, provider="claude"):
    """The lines that can carry the provider's own error: all of stderr (the CLI's); of the stream-json stdout, the
    plain lines and the text of a `result` event marked `is_error`; of a Codex call's `exec --json` stdout, the
    plain lines and the CLI's own error messages (`codex_error`). Never the transcript's tool output or model
    text, where a task's own text can name 401 or oauth (review2 minor 6), and never a stream event cut mid-write
    (a line that starts with `{` and is not JSON: a SIGKILL during a write leaves one; re-review N1)."""
    for line in text.splitlines():
        if name != "stdout.txt" or not line.lstrip().startswith("{"):
            yield line
            continue
        event = json_object(line)
        if provider == CODEX:
            yield from codex_error(event)
        elif event.get("type") == "result" and event.get("is_error"):
            yield str(event.get("result"))


def codex_error(event):
    """The message of a Codex `exec --json` `error` event, of a `turn.failed` event's `error`, or of an `error` item;
    nothing for any other event."""
    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    failure = event.get("error") if isinstance(event.get("error"), dict) else {}
    if event.get("type") == "error":
        yield str(event.get("message"))
    elif event.get("type") == "turn.failed":
        yield str(failure.get("message"))
    elif str(event.get("type")).startswith("item.") and item.get("type") == "error":
        yield str(item.get("message"))


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
    """(failure reason or None, policy hit or None, session files) for one unit's private home (a Claude unit; a
    Codex unit's is `audit_rollouts`, which its caller chooses)."""
    sessions = claude_sessions(home)
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


def nested_sessions(home, sessions):
    """How many of a unit's session files (`audit_sessions`' or `audit_rollouts`' third value) lie below the top
    level of its private home's Claude project store (`.claude/projects/<project>/<deeper>/...`: a session an agent
    started inside its own, such as a subagent's). A Codex rollout lies outside the store and counts none, so a
    Codex unit's 0 means "no Claude session below the top level", not a measured count of nested Codex sessions."""
    projects = Path(home) / ".claude" / "projects"
    return sum(path.is_relative_to(projects) and len(path.relative_to(projects).parts) > 2 for path in sessions)


def claude_sessions(home):
    """Every Claude session file (`_session`) anywhere under a unit's private home, in path order."""
    return sorted(path for path in Path(home).rglob("*.jsonl") if _session(path))


def audit_rollouts(home, tree, records, made, model, effort):
    """`audit_sessions` for a Codex unit, over every rollout under its private home (`rollouts`), the only record
    of a Codex call's model and effort: a `turn_context` model other than `model` is a policy hit
    (`scan.model_hits`); a session whose `session_meta` working directory is not under `tree`, one without a
    `turn_context` or with one that does not name the model and `effort`, a session without an id, more rollouts
    than `made` calls, or a call of `records` that started a thread or completed a turn and has no rollout of its
    `thread_id` (a completed call without a thread id among them) fails the unit (`rollout_reason`). So does any
    Claude session file in the home (`claude_sessions`: the unit denies Claude), whose answering model is read as a
    rollout's is."""
    paths, claude = rollouts(home), claude_sessions(home)
    try:
        hits = list(scan.model_hits([*paths, *claude], model))  # SystemExit on a line that is not JSON
    except SystemExit as error:
        return f"unreadable session: {error}", None, paths
    if policy := scan.model_policy(hits):
        return f"a session answered by another model: {hits[0]['text']}", policy, paths
    if claude:
        return f"Claude sessions in a Codex unit: {[str(path) for path in claude]}", None, paths
    return rollout_reason(paths, tree, records, made, effort), None, paths


def rollout_reason(paths, tree, records, made, effort):
    """Why a Codex unit's readable rollouts fail `audit_rollouts` beyond the model, or None."""
    if outside := [str(path) for path in paths if not Path(scan.codex_cwd(path)).is_relative_to(tree)]:
        return f"sessions outside the unit tree: {outside}"
    if unnamed := [str(path) for path in paths if not (rollout_id(path) and named_contexts(path, effort))]:
        return f"sessions without an id or a turn_context naming the model and effort {effort}: {unnamed}"
    if len(paths) > made:
        return f"{len(paths)} sessions for {made} recorded calls"
    if unmatched := unmatched_calls(records, {rollout_id(path) for path in paths}):
        return f"calls {unmatched} have no session record of their thread"
    return None


def named_contexts(path, effort):
    """Whether a rollout has a `turn_context` and each names a model and `effort`."""
    rows = [json_object(line) for line in path.read_text(errors="replace").splitlines()]
    contexts = [row.get("payload") for row in rows if row.get("type") == "turn_context"]
    return bool(contexts) and all(isinstance(context, dict) and isinstance(context.get("model"), str)
                                  and context.get("effort") == effort for context in contexts)


def unmatched_calls(records, ids):
    """The Codex calls of `records` whose output has a `thread.started` or a `turn.completed` (a failed call that
    started a thread too) and whose `thread_id` is not in `ids` (a call without one never is: `rollout_reason`
    refuses a rollout without an id first)."""
    found = []
    for call in calls(records):
        events = stream_events(call / "stdout.txt") if provider(call) == CODEX else []
        if any(e.get("type") in ("thread.started", "turn.completed") for e in events) and call_thread(events) not in ids:
            found.append(call.name)
    return found


def isolation_breach(records):
    """Why a unit's sessions were not isolated (the first `system/init` event of its calls that lists one, or of a
    Codex call, which prints no init event, its `item.*` types outside `CODEX_ITEMS`, an `error` item named as one),
    or None."""
    for call in calls(records):
        events = stream_events(call / "stdout.txt")
        if provider(call) == CODEX and (found := sorted(codex_items(events) - CODEX_ITEMS)):
            note = " (an error item: the CLI's own message, for the paid smoke to judge)" if "error" in found else ""
            return f"call {call.name}: the session was given {found[:5]} ({len(found)} in all){note}"
        for event in events:
            if (event.get("type"), event.get("subtype")) == ("system", "init") and (found := foreign(event)):
                return f"call {call.name}: the session was given {found[:5]} ({len(found)} in all)"
    return None


def codex_items(events):
    """The item types of a Codex call's `item.started`, `item.updated` and `item.completed` events."""
    return {str(event["item"].get("type")) for event in events
            if str(event.get("type")).startswith("item.") and isinstance(event.get("item"), dict)}


def foreign(init):
    """What an init event lists beyond a clean session's: a tool outside `sandbox.CLAUDE_TOOLS`, any MCP server, a
    skill named `<source>:<skill>`, a plugin that is not `@builtin`."""
    tools = [name for name in init.get("tools") or [] if name not in sandbox.CLAUDE_TOOLS]
    servers = [server.get("name") for server in init.get("mcp_servers") or [] if isinstance(server, dict)]
    skills = [name for name in init.get("skills") or [] if ":" in str(name)]
    plugins = [plugin.get("source") for plugin in init.get("plugins") or []
               if isinstance(plugin, dict) and not str(plugin.get("source")).endswith("@builtin")]
    return tools + servers + skills + plugins


def priced(records, table, per_call, model=None):
    """{"usd", "calls": {call: usd}, "missing": [calls]} of a unit's physical calls (rounded to 1e-6 USD). A call is
    priced from the stream-json result event the metered template prints: the larger of its `modelUsage` at the
    table's ordinary rates and the CLI's reported `total_cost_usd` (the CLI applies a long-context rate per request,
    which the summed usage cannot). A call whose usage is missing, incomplete or unpriced counts at `per_call`, the
    worst case, and is listed in `missing`. A call the shim refused (no prompt) reached no provider and costs
    nothing. A Codex call is priced from its last `turn.completed` usage (`exec --json`) as the unit's declared
    `model`, at the ordinary rates (Codex reports no cost; one row sums the turn's requests); without `model`, or
    without a completed turn (a killed or failed call), at `per_call`. Codex usage is priced at the ordinary rates
    from the summed turn, so a request above 272K input tokens is under-priced; the Luna smoke's ledger row must
    state this."""
    found, missing = {}, []
    for call in calls(records):
        if not (call / "prompt.txt").is_file():
            continue
        cost = call_cost(call, table, model)
        if cost is None:
            missing.append(call.name)
        found[call.name] = round(per_call if cost is None else cost, 6)
    return {"usd": round(sum(found.values()), 6), "missing": missing, "calls": found}


def call_cost(call, table, model=None):
    stdout, codex = call / "stdout.txt", provider(call) == CODEX
    mode = ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT if codex else \
        ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT
    usage = usage_from_stdout(mode.value, stdout.read_bytes() if stdout.is_file() else b"",
                              model=model if codex else None)
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
