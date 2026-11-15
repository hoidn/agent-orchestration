"""Spend guard of the seed-set study (plan `docs/plans/2026-11-11-seed-set-calibration-plan.md`, Budget and Ledger).

The ledger is one append-only file at a fixed place, `~/.local/state/seed-set/spend-ledger.jsonl` (`LEDGER`),
whatever paths the runner is given, so another results directory or a deleted results tree cannot reset a cap.
It holds starts and events. Every provider start goes through `reserve` before its process is launched:

- the tranche must be authorized in the plan's ledger (`CAPS`; the seed evaluation and its extension are not,
  and refuse whatever the environment says) and named exactly by `$SEED_SET_AUTHORIZED_TRANCHE`;
- no `stop` event may be in the ledger (a stop rule fired: nothing more starts), and no `pause` event after the
  last `resume` (a usage limit, or a unit settled above its worst case, closed all starts: `resume_after_limit`
  reopens them after the vendor's named reset, with the owner's meter reading; coordinator ruling R2, 2026-11-14);
- the model must be one of the two exact Claude IDs (no fallback, no alias, never Fable);
- the unit (a candidate run's records directory, or `<pool>#<judge>`) must not be in the ledger already: a unit
  is launched once, never retried or relaunched;
- the calls reserved so far for (tranche, kind, model) plus this unit's maximum must stay within the cap, and with
  `limit`, the starts so far for (tranche, task, arm, step) must stay under it (the plan's runs per task and
  arm; a probe step runs a task once);
- the tranche's committed priced total plus this unit's worst case (its calls times the model's per-call worst
  case) must stay within the tranche's priced ceiling (coordinator ruling R4, 2026-11-14; both figures are the
  criterion's, `layout.spend_terms`). Committed is each settled unit's metered price (its `settle` event, metered
  tokens times the frozen price table, `units.priced`) and each other start's worst case.

Rows are appended and fsynced under an exclusive lock, so a crash after the append cannot lose a start and two
study processes cannot both take the last call or the last planned run; `rows` reads under a shared lock, so a
reader never sees a row half written, and parses after releasing it. A unit reserves its maximum calls, which
the caller passes to the shims as `COMPARE_MAX_CALLS`: that bounds the recorded provider launches, not a CLI an
agent starts by absolute path inside the sandbox (the runner's session audit covers those). Events (`freeze`,
`smoke`, `decision`, `stop`, `pause`) are appended by `record`; the latest of each kind governs. Standard library
only.
"""

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
MODELS = (HAIKU, SONNET)
AUTHORIZATION = "SEED_SET_AUTHORIZED_TRANCHE"
LEDGER = Path("~/.local/state/seed-set/spend-ledger.jsonl")  # expanded against $HOME when used
# Provider calls per tranche, kind and model, as the plan's Budget table and its 2026-11-11 ledger rows authorize
# them. Allowance does not move between tranches (smoke + calibration = 90/21 candidates, 31/31 judges).
CAPS = {
    "smoke": {"candidate": {HAIKU: 10, SONNET: 1}, "judge": {HAIKU: 1, SONNET: 1}},
    "calibration": {"candidate": {HAIKU: 80, SONNET: 20}, "judge": {HAIKU: 30, SONNET: 30}},
    # the redraw serves the ladder probe only: Haiku direct runs, no Sonnet run, no judge (coordinator, review2 M4)
    "redraw": {"candidate": {HAIKU: 40, SONNET: 0}, "judge": {HAIKU: 0, SONNET: 0}},
}
# Named in the plan, not authorized: they need a new owner approval recorded in the plan's ledger and here.
UNAUTHORIZED = ("seed_evaluation", "extension")
KINDS = ("candidate", "judge")


def ledger_path():
    return LEDGER.expanduser()


def check_model(model):
    """Refuse anything but the two exact Claude IDs the study binds."""
    if model not in MODELS:
        raise SystemExit(f"model {model!r} is not one of the study's exact IDs {MODELS}; no fallback, never Fable")


def authorize(tranche, environ=None):
    """Refuse a tranche the plan does not authorize, or one the environment does not name exactly."""
    environ = os.environ if environ is None else environ
    if tranche in UNAUTHORIZED:
        raise SystemExit(f"tranche {tranche!r} is not authorized: the plan's ledger records no owner approval for it")
    if tranche not in CAPS:
        raise SystemExit(f"unknown tranche {tranche!r}; authorized tranches: {sorted(CAPS)}")
    if environ.get(AUTHORIZATION) != tranche:
        raise SystemExit(f"provider spend refused: set {AUTHORIZATION}={tranche} to start {tranche} calls")


def rows(ledger):
    """The ledger's rows: its text read under a shared lock (an append, under the exclusive lock, is never seen half
    written) and parsed once the lock is released, so a reader holds it only while it reads (re-review n7)."""
    path = Path(ledger)
    if not path.exists():
        return []
    with path.open() as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        text = stream.read()
    return [json.loads(line) for line in text.splitlines()]


def starts(entries):
    return [row for row in entries if row["kind"] in KINDS]


def latest(entries, event):
    """The last event row of kind `event`, or None."""
    found = [row for row in entries if row["kind"] == "event" and row["event"] == event]
    return found[-1] if found else None


def reserved(entries, tranche, kind, model):
    return sum(row["calls"] for row in starts(entries)
               if (row["tranche"], row["kind"], row["model"]) == (tranche, kind, model))


def remaining(entries, tranche, kind, model):
    if kind not in KINDS:
        raise SystemExit(f"unknown kind {kind!r}")
    check_model(model)
    return CAPS[tranche][kind].get(model, 0) - reserved(entries, tranche, kind, model)


def open_pauses(entries):
    """The `pause` events after the last `resume` that no `not_a_limit` decision withdrew: while one is open,
    nothing starts."""
    events = [row for row in entries if row["kind"] == "event" and row["event"] in ("pause", "resume")]
    resumed = max((k for k, row in enumerate(events) if row["event"] == "resume"), default=-1)
    withdrawn = {row["pause"] for row in entries if row["kind"] == "event" and row["event"] == "not_a_limit"}
    return [row for row in events[resumed + 1:] if row["seq"] not in withdrawn]


def refuse_closed(entries):
    """Refuse a start after a stop, or while a usage limit has closed starts."""
    stop = latest(entries, "stop")
    if stop:
        raise SystemExit(f"the study is stopped ({stop['reason']}); nothing more starts")
    if pauses := open_pauses(entries):
        raise SystemExit(closed_by(pauses[0]))


def closed_by(pause):
    """What the operator reads while `pause` closes starts: the unit, the reset, and for a usage limit its flag, the
    rule that fired, the line it read, how to record that the raw result shows no limit (re-review n3), and the way
    out for a unit a killed runner left unsettled (fix round 3, coordinator ruling 2)."""
    unit, limit = pause.get("unit"), bool(pause.get("rule"))
    fired = f"; {pause['flag']}" if pause.get("flag") else ""
    fired += f"; rule: {pause['rule']}, on {pause.get('text')!r}" if limit else ""
    return (f"starts are closed by {pause.get('reason') or 'a usage limit'} ({unit}, resets {when(pause.get('reset'))}"
            f"{fired}): read the raw result ({pause.get('raw') or unit}), then `resume-after-limit` after the reset, "
            "with the owner's meter reading" + (f"; if it shows no usage limit, `not-a-limit {unit} --reason R` "
                                                f"records that once the unit is settled ({UNSETTLED})"
                                                if limit and pause.get("flag") else ""))


UNSETTLED = ("a run its killed runner left unsettled: `settle` it first; a probe run, which only `probe` settles and "
             "`probe` refuses while starts are closed: `resume-after-limit` after the reset, then `probe` settles it "
             "as a cut run")


def limit_pause(entries, unit):
    """The open pause a recognised usage limit of `unit` wrote (it names its rule); refuses without one."""
    pause = next((row for row in open_pauses(entries) if row.get("unit") == str(unit) and row.get("rule")), None)
    if pause is None:
        raise SystemExit(f"no open usage-limit pause of {unit}: nothing to record (a pause by a unit settled above its "
                         "worst case reopens by `resume-after-limit` only)")
    return pause


def not_a_limit(ledger, unit, reason):
    """Record the operator's decision that the open usage-limit pause of `unit` was no usage limit, with the reason
    (re-review n3): that pause no longer closes starts (`open_pauses`). Returns the row."""
    with locked(ledger) as (stream, entries):
        pause = limit_pause(entries, unit)
        return _append(stream, entries, {"kind": "event", "event": "not_a_limit", "unit": str(unit),
                                         "pause": pause["seq"], "reason": reason})


def when(epoch):
    return "at an unnamed time" if epoch is None else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def resume_after_limit(ledger, reset, five_hour, weekly, read_at, now=None):
    """Reopen the starts a usage limit closed (coordinator ruling R2): `reset` (epoch seconds) is the reset the
    vendor's answer named, and the owner's meter reading is the five-hour and weekly meters in percent, read at
    `read_at`. Refuses with no open pause, before the latest reset named (by `reset` or by an open pause), and for
    a reading that is not a percentage or was not taken between that reset and now. Returns the `resume` row."""
    now = time.time() if now is None else now
    with locked(ledger) as (stream, entries):
        pauses = open_pauses(entries)
        if not pauses:
            raise SystemExit("no start is closed by a usage limit: nothing to resume")
        named = max([reset, *(row["reset"] for row in pauses if row.get("reset") is not None)])
        require_reset_after_hit(pauses, reset)
        if now < named:
            raise SystemExit(f"the usage limit resets {when(named)}, it is {when(now)}: nothing reopens before the "
                             "reset")
        require_reading(named, five_hour, weekly, read_at, now)
        return _append(stream, entries, {"kind": "event", "event": "resume", "reset": named, "pauses": [
            row["seq"] for row in pauses], "reading": {"five_hour_pct": five_hour, "weekly_pct": weekly,
                                                      "read_at": read_at}})


def require_reset_after_hit(pauses, reset):
    """When no open pause named its reset, the typed one must come after the limit was hit (review3 minor 10)."""
    hit = max(row["time"] for row in pauses)
    if all(row.get("reset") is None for row in pauses) and reset < hit:
        raise SystemExit(f"no open pause named its reset: the reset typed ({when(reset)}) must come after the limit "
                         f"was hit ({when(hit)})")


def require_reading(named, five_hour, weekly, read_at, now):
    """The owner's meter reading: two percentages below 100, read between the reset and now."""
    if not all(type(v) in (int, float) and 0 <= v < 100 for v in (five_hour, weekly)):
        raise SystemExit(f"the owner's meter reading is two percentages below 100 (a meter at 100 percent: its "
                         f"limit still holds), not {five_hour!r} and {weekly!r}")
    if not named <= read_at <= now:
        raise SystemExit(f"the owner's meter reading must be taken after the reset ({when(named)}) and not later "
                         f"than now, not {when(read_at)}")


def check(ledger, tranche, kind, model, calls, environ=None):
    """Refuse a planned batch of `calls` that would not fit the cap; writes nothing."""
    authorize(tranche, environ)
    entries = rows(ledger)
    refuse_closed(entries)
    left = remaining(entries, tranche, kind, model)
    if calls > left:
        raise SystemExit(f"{tranche} {kind} {model}: {calls} calls planned but {left} of the cap remain")


@contextmanager
def locked(ledger):
    """The ledger opened for appending under an exclusive lock, with its rows read under that lock."""
    path = Path(ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        yield stream, [json.loads(line) for line in stream.read().splitlines()]


def _append(stream, entries, row):
    row = {"seq": len(entries) + 1, "time": time.time(), **row}
    stream.write(json.dumps(row, sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())
    return row


def reserve(ledger, tranche, kind, model, calls, unit, environ=None, limit=None, *, price, **facts):
    """Append one start of `unit` with its maximum `calls`, fsynced, before the caller launches; return the row.
    With `limit`, refuse a start beyond `limit` starts of the same (tranche, task, arm, step). `price` is (the
    tranche's priced ceiling, the model's per-call worst case), both in USD."""
    ceiling, per_call = price
    authorize(tranche, environ)
    check_model(model)
    if type(calls) is not int or calls < 1:
        raise SystemExit(f"a start reserves a positive whole number of calls, not {calls!r}")
    with locked(ledger) as (stream, entries):
        refuse_closed(entries)
        if any(row.get("unit") == str(unit) for row in entries):
            raise SystemExit(f"{unit} was already started; a unit is never retried or relaunched")
        if limit is not None and sum((row["tranche"], row.get("task"), row.get("arm"), row.get("step")) == (
                tranche, facts.get("task"), facts.get("arm"), facts.get("step")) for row in starts(entries)) >= limit:
            raise SystemExit(f"{tranche} {facts.get('arm')} on {facts.get('task')}: all {limit} planned runs started")
        left = remaining(entries, tranche, kind, model)
        if calls > left:
            raise SystemExit(f"{tranche} {kind} {model}: cap reached ({left} calls left, {calls} needed for {unit})")
        worst, committed = round(calls * per_call, 6), committed_usd(entries, tranche)
        if round(committed + worst, 6) > ceiling:
            raise SystemExit(f"{tranche}: the priced ceiling of USD {ceiling:g} would be passed (USD {committed:g} "
                             f"committed, USD {worst:g} worst case for {unit})")
        return _append(stream, entries, {"tranche": tranche, "kind": kind, "model": model, "calls": calls,
                                         "usd_reserved": worst, "unit": str(unit), **facts})


def settled(entries):
    """{unit: its latest `settle` event}: the unit's metered price once it ended."""
    return {row["unit"]: row for row in entries if row["kind"] == "event" and row["event"] == "settle"}


def committed_usd(entries, tranche):
    """The tranche's priced total: each settled start at its metered price, every other start at its worst case."""
    done = settled(entries)
    return round(sum(done[row["unit"]]["usd"] if row["unit"] in done else row["usd_reserved"]
                     for row in starts(entries) if row["tranche"] == tranche), 6)


def priced(ledger):
    """{tranche: committed, settled and open USD, and the units settled with calls whose usage was missing}."""
    entries = rows(ledger)
    done, out = settled(entries), {}
    for tranche in CAPS:
        mine = [row for row in starts(entries) if row["tranche"] == tranche]
        settled_usd = round(sum(done[row["unit"]]["usd"] for row in mine if row["unit"] in done), 6)
        open_usd = round(sum(row["usd_reserved"] for row in mine if row["unit"] not in done), 6)
        out[tranche] = {"committed_usd": round(settled_usd + open_usd, 6), "settled_usd": settled_usd,
                        "open_usd": open_usd, "missing_usage": [row["unit"] for row in mine
                                                                if done.get(row["unit"], {}).get("missing")],
                        "over_reserved": [row["unit"] for row in mine if done.get(row["unit"], {}).get("over_reserved")]}
    return out


def record(ledger, event, **facts):
    """Append an event row (freeze, smoke, decision, stop, pause, settle) under the lock; return it."""
    with locked(ledger) as (stream, entries):
        return _append(stream, entries, {"kind": "event", "event": event, **facts})


def totals(ledger):
    """{tranche: {kind: {model: {"reserved", "cap"}}}} over every authorized tranche."""
    entries = rows(ledger)
    return {tranche: {kind: {model: {"reserved": reserved(entries, tranche, kind, model), "cap": cap}
                             for model, cap in caps.items()} for kind, caps in kinds.items()}
            for tranche, kinds in CAPS.items()}
