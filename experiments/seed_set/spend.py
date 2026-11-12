"""Spend guard of the seed-set study (plan `docs/plans/2026-11-11-seed-set-calibration-plan.md`, Budget and Ledger).

Every provider start of the study goes through `reserve` before its process is launched:

- the tranche must be authorized in the plan's ledger (`CAPS`; the seed evaluation and its extension are not,
  and refuse whatever the environment says) and named exactly by `$SEED_SET_AUTHORIZED_TRANCHE`;
- the model must be one of the two exact Claude IDs (no fallback, no alias, never Fable);
- the unit (a candidate run's records directory, or `<pool>#<judge>`) must not be in the ledger already: a unit
  is launched once, never retried or relaunched;
- the calls reserved so far for (tranche, kind, model) plus this unit's maximum must stay within the cap.

The row is appended and fsynced under an exclusive lock before the caller launches, so a crash after the append
cannot lose a start, and two study processes cannot both take the last call. A unit reserves its maximum calls,
which the caller also passes to the shims as `COMPARE_MAX_CALLS`, so physical calls never exceed reserved ones.
Standard library only.
"""

import fcntl
import json
import os
import time
from pathlib import Path

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
MODELS = (HAIKU, SONNET)
AUTHORIZATION = "SEED_SET_AUTHORIZED_TRANCHE"
# Provider calls per tranche, kind and model, as the plan's Budget table and its 2026-11-11 ledger rows authorize
# them. Allowance does not move between tranches (smoke + calibration = 90/21 candidates, 31/31 judges).
CAPS = {
    "smoke": {"candidate": {HAIKU: 10, SONNET: 1}, "judge": {HAIKU: 1, SONNET: 1}},
    "calibration": {"candidate": {HAIKU: 80, SONNET: 20}, "judge": {HAIKU: 30, SONNET: 30}},
    "redraw": {"candidate": {HAIKU: 40, SONNET: 10}, "judge": {HAIKU: 15, SONNET: 15}},
}
# Named in the plan, not authorized: they need a new owner approval recorded in the plan's ledger and here.
UNAUTHORIZED = ("seed_evaluation", "extension")
KINDS = ("candidate", "judge")


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
    path = Path(ledger)
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def reserved(entries, tranche, kind, model):
    return sum(row["calls"] for row in entries
               if (row["tranche"], row["kind"], row["model"]) == (tranche, kind, model))


def remaining(entries, tranche, kind, model):
    if kind not in KINDS:
        raise SystemExit(f"unknown kind {kind!r}")
    check_model(model)
    return CAPS[tranche][kind].get(model, 0) - reserved(entries, tranche, kind, model)


def check(ledger, tranche, kind, model, calls, environ=None):
    """Refuse a planned batch of `calls` that would not fit the cap; writes nothing."""
    authorize(tranche, environ)
    left = remaining(rows(ledger), tranche, kind, model)
    if calls > left:
        raise SystemExit(f"{tranche} {kind} {model}: {calls} calls planned but {left} of the cap remain")


def reserve(ledger, tranche, kind, model, calls, unit, environ=None, **facts):
    """Append one start of `unit` with its maximum `calls`, fsynced, before the caller launches; return the row."""
    authorize(tranche, environ)
    check_model(model)
    if type(calls) is not int or calls < 1:
        raise SystemExit(f"a start reserves a positive whole number of calls, not {calls!r}")
    path = Path(ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        entries = [json.loads(line) for line in stream.read().splitlines()]
        if any(row["unit"] == str(unit) for row in entries):
            raise SystemExit(f"{unit} was already started; a unit is never retried or relaunched")
        left = remaining(entries, tranche, kind, model)
        if calls > left:
            raise SystemExit(f"{tranche} {kind} {model}: cap reached ({left} calls left, {calls} needed for {unit})")
        row = {"seq": len(entries) + 1, "time": time.time(), "tranche": tranche, "kind": kind, "model": model,
               "calls": calls, "unit": str(unit), **facts}
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return row


def totals(ledger):
    """{tranche: {kind: {model: {"reserved", "cap"}}}} over every authorized tranche."""
    entries = rows(ledger)
    return {tranche: {kind: {model: {"reserved": reserved(entries, tranche, kind, model), "cap": cap}
                             for model, cap in caps.items()} for kind, caps in kinds.items()}
            for tranche, kinds in CAPS.items()}
