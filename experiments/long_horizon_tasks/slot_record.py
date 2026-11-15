"""The long-horizon ladder's slot records: the one definition of what the launcher writes and the readout reads.

Plan docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md, D5 to D7 and Tasks 5 and 6. The launcher
(`ladder.py`) writes one JSON document, its export, in exactly this layout; the readout (`readout.py`) reads it
with `read` (no repeated key, no NaN or Infinity) and checks it with `load`, which refuses anything that does not
fit, naming the record, and skips nothing. Both load this module by its path (the kit runs under `python -I`), and
neither imports the other. Standard library only.

  label           the current configuration label, the SHA-256 of manifest.json (D7.6): 64 lowercase hex digits
  earlier_labels  [{"label", "ended_by": the ledger row that ended it}], one per earlier label (D6, D7.6)
  end             null while the tranche runs; else {"by": "schedule" | "ceiling" | "starts" | "stop", "cause"}:
                  the schedule ran out, the ceiling or the 240 starts ended it (ladder.json ceiling.ends; "starts"
                  only with exactly ceiling.starts starts), or a stop of D7.7 did; "cause" names the stop and its
                  ledger row, and is null for every other ending
  slots           the schedule's slots (D7.3): [{"slot": id, "task": a name of ladder.json tasks.list, "effort": one
                  of attempt.efforts, "round": 1 to schedule.rounds, "pilot": true for the pilot's three (D7.2): the
                  three efforts of round 1 of schedule.pilot.task or of a task of its fallback}]; one slot per
                  (task, effort, round)
  starts          every start, and every pre-session failure, of every label: [{
                    "slot"            the id of a slot above: the join; a start that joins no slot is an error
                    "start"           the launcher's start number: unique, from 1, increasing in the order of the starts
                    "label"           the configuration label it ran under: the current one or an earlier one
                    "row"             the row of D5 that classified its ending (classification.rows); row 16 awaits
                                      a ruling and is refused until the ruling gives the start its row
                    "class"           the class the launcher decided: the row's class, "stop" when the launcher
                                      stopped the tranche on this attempt (then "stop_cause" names why), or
                                      "infrastructure_failure" on an observation's row for regrade case 1, or on
                                      the pre-session row with a cost above 0 (a pre-session failure has none, D5:
                                      a "pre_session_failure" with a cost is refused)
                    "stop_cause"      null, or one of LAUNCHER_STOPS: a stop of D7.7 the launcher sees in an attempt
                                      whose row is not a stop row; required exactly then, and only where the cause
                                      can occur (LAUNCHER_STOPS: on a session's start, on the smoke's slot, or on any)
                    "reward"          the verifier's reward, 0 or 1, or null; read only for an observation, where
                                      it is only what a verifier gave: a counted observation has one, and one with
                                      none is regraded first (D5 case 1, after any ending; Task 7 ruling 3)
                    "excluded"        null, or the D5 regrade case that takes an observation out of k and n: "no
                                      reward after regrades" (regrade case 1: class "infrastructure_failure" on an
                                      observation's row, reward null; ladder.json and D5: still no reward file is an
                                      infrastructure failure) or "indeterminate" (regrade case 2: an observation
                                      with a reward of 0 that could not be regraded)
                    "contamination"   the SHA-256 of each frozen term the launcher's scan found in the attempt's
                                      transcript at teardown (readout.contamination_scan: the SHA-256 of a term's
                                      UTF-8 bytes, or canary_sha256), never the term; [] when none. On a start of any
                                      class; an observation with a hit is excluded, any other start keeps its class
                    "usd"             the settled priced cost of the start (D4), finite and not negative
                    "minutes"         the session's length, finite and not negative, or null: not recorded
                    "tokens"          {"input", "output", "cache_read", "cache_write_5m", "cache_write_1h"}: each an
                                      integer, or null: not recorded
                    "api_retry"       the number of api_retry events in the stream (D5: recorded per attempt), or
                                      null: not recorded
                    "graded"          null, or {"passed", "total"} sub-tests where the verifier reports them (D6)
                    "egress_refused"  {address: count} of refused connections (D3); excludes nothing
                  }]; per slot, in start order, a start follows only a cut or a pre-session failure, and nothing
                  follows the slot's third pre-session failure, counted in all (D5: relaunched at most twice, lost
                  after the third)
  open            the attempts still open when the export was written: [{"slot": a slot id above, "start": its start
                  number}]. They enter no count; the readout names how many there are (Task 8 part A m11)
  allowance       null, or {"weekly_points": meter points of a weekly allowance the tranche used, summed from the
                  owner's readings, finite and not negative, "readings": the ledger rows they come from} (D6)

A start's class (observation, flagged or not; cut; infrastructure failure; stop; pre-session failure) is its row's
in ladder.json unless the launcher stopped on it or it is regrade case 1; a stop is never scored. An observation with
"excluded" set, or with a contamination hit, is listed and enters no k or n; so is every start of another class. A figure that is null was
not recorded and is never read as zero: the readout leaves it out of its means and says how many it left out
(coordinator ruling, Task 5).

How the launcher's own records map to this layout (they differ from it in three places, feat/lh-launcher 0ff18eda):
regrade case 2 is excluded "indeterminate", reward 0, not a flag `indeterminate`; a row-16 ending is not exported
until the ruling has given it a row and the class that row has (the class "ruling" is refused); the stream's
api_retry count is "api_retry". Regrade case 1 is exported as the launcher records it, class
"infrastructure_failure" on its observation row (row 5 after a normal ending), with excluded "no reward after
regrades" naming the case (coordinator rulings, Task 5 and Task 7 ruling 3).
"""

import hashlib
import json
import math
import re

TOKEN_KINDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
EXCLUSIONS = ("no reward after regrades", "indeterminate")
ENDS = ("schedule", "ceiling", "starts", "stop")
# The stops of D7.7 the launcher sees in an attempt's own files whatever its D5 row, each with where it can occur:
# "a session" (a start that is not a pre-session failure: the init event, the stream and the subagent files come
# from a session), "the smoke's slot" (D7.1, smoke_cell) or "any start": token_scan.py reads every teardown's files,
# and the runtime check reads the containers of any start that had a session or containers, which a pre-session
# failure can have. A scan that could not finish is a stop, since it cannot show that nothing leaked (coordinator
# ruling, Task 5). A launch refused before the harness ran is no start: it is not exported and has no cause here.
LAUNCHER_STOPS = {"an init event with another tool list": "a session",
                  "an init event with another CLI version": "a session",
                  "an init event with another credential source": "a session",
                  "a sign of paid extra usage in the session's stream": "a session",
                  "a subagent file": "a session",
                  "a match of token_scan.py": "any start",
                  "an incomplete scan of token_scan.py": "any start",
                  "a match of the runtime check in the attempt's containers": "any start",
                  "an incomplete scan of the runtime check in the attempt's containers": "any start",
                  "a failed smoke check": "the smoke's slot"}
AGAIN_AFTER = ("cut", "pre_session_failure")  # D5: the only classes whose slot is run again
NUMBER = (int, float)
EXPORT = {"label": str, "earlier_labels": list, "end": (dict, type(None)), "slots": list, "starts": list,
          "allowance": (dict, type(None)), "open": list}
SLOT = {"slot": str, "task": str, "effort": str, "round": int, "pilot": bool}
START = {"slot": str, "start": int, "label": str, "row": int, "class": str, "stop_cause": (str, type(None)),
         "reward": (int, float, type(None)), "excluded": (str, type(None)), "contamination": list, "usd": NUMBER,
         "minutes": (*NUMBER, type(None)), "tokens": dict, "api_retry": (int, type(None)), "graded": (dict, type(None)),
         "egress_refused": dict}
SHA256 = re.compile(r"[0-9a-f]{64}")


class RecordError(ValueError):
    """A record that does not fit the layout; the message names it."""


def _unique(pairs):
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise RecordError(f"a JSON object repeats the keys {repeated}: a repeated key is never resolved silently")
    return dict(pairs)


def _no_constant(name):
    raise RecordError(f"the JSON holds {name}: a figure must be a finite number")


def read(path):
    """The JSON document at path, refusing a repeated key and NaN or Infinity (Python's json would take them)."""
    return json.loads(path.read_text(), object_pairs_hook=_unique, parse_constant=_no_constant)


def fields(obj, spec, where):
    """obj is a dict with exactly spec's keys, each of its type; a bool is never an int or a number."""
    if not isinstance(obj, dict) or set(obj) != set(spec):
        keys = sorted(obj) if isinstance(obj, dict) else type(obj).__name__
        raise RecordError(f"{where}: keys {keys} are not {sorted(spec)}")
    for key, kind in spec.items():
        kinds = kind if isinstance(kind, tuple) else (kind,)
        if not isinstance(obj[key], kinds) or (isinstance(obj[key], bool) and bool not in kinds):
            raise RecordError(f"{where}: {key} is {obj[key]!r}, not {' or '.join(k.__name__ for k in kinds)}")


def _amount(value, what, where):
    if not math.isfinite(value) or value < 0:
        raise RecordError(f"{where}: {what} {value!r} is not a finite number at or above 0")


def _hex_label(value, where):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise RecordError(f"{where}: label {value!r} is not a SHA-256 (64 lowercase hex digits)")
    return value


def _labels(export):
    earlier = []
    for entry in export["earlier_labels"]:
        fields(entry, {"label": str, "ended_by": str}, "an earlier label")
        if not entry["ended_by"].strip():
            raise RecordError("an earlier label: ended_by names no ledger row")
        earlier.append(_hex_label(entry["label"], "an earlier label"))
    labels = [_hex_label(export["label"], "the export")] + earlier
    if len(set(labels)) != len(labels):
        raise RecordError(f"a configuration label is given twice: {labels}")
    return set(labels)


def _end(end, starts, ladder):
    if end is None:
        return
    fields(end, {"by": str, "cause": (str, type(None))}, "end")
    if end["by"] not in ENDS:
        raise RecordError(f"end: by {end['by']!r} is not one of {ENDS}")
    if (end["by"] == "stop") != bool((end["cause"] or "").strip()):
        raise RecordError(f"end: a stop names its cause and ledger row, and no other ending has a cause: {end}")
    counted = sum(1 for s in starts if ladder["classification"]["classes"][s["class"]]["starts"])
    if end["by"] == "starts" and counted != ladder["ceiling"]["starts"]:
        raise RecordError(f"end: by 'starts' with {counted} starts, not {ladder['ceiling']['starts']}")


def _slot(slot, ladder):
    where = f"slot {slot.get('slot')!r}" if isinstance(slot, dict) else "a slot"
    fields(slot, SLOT, where)
    if slot["task"] not in {task["name"] for task in ladder["tasks"]["list"]}:
        raise RecordError(f"{where}: task {slot['task']!r} is not in ladder.json tasks.list")
    if slot["effort"] not in ladder["attempt"]["efforts"]:
        raise RecordError(f"{where}: effort {slot['effort']!r} is not one of {ladder['attempt']['efforts']}")
    if not 1 <= slot["round"] <= ladder["schedule"]["rounds"]:
        raise RecordError(f"{where}: round {slot['round']} is outside 1 to {ladder['schedule']['rounds']}")
    return slot


def _pilot(slots, ladder):
    """The slots marked pilot are none, or the three efforts of round 1 of the pilot task or a fallback (D7.2)."""
    marked = {(s["task"], s["effort"], s["round"]) for s in slots.values() if s["pilot"]}
    pilot = ladder["schedule"]["pilot"]
    allowed = [{(task, effort, 1) for effort in ladder["attempt"]["efforts"]}
               for task in [pilot["task"], *pilot["fallback"]]]
    if marked and marked not in allowed:
        raise RecordError(f"the slots marked pilot, {sorted(marked)}, are not the three efforts of round 1 of "
                          f"{pilot['task']} or of a task of schedule.pilot.fallback")


def _slots(slots, ladder):
    joined, cells = {}, set()
    for slot in slots:
        _slot(slot, ladder)
        cell = (slot["task"], slot["effort"], slot["round"])
        if slot["slot"] in joined or cell in cells:
            raise RecordError(f"slot {slot['slot']!r}: a slot id or a (task, effort, round) is given twice")
        joined[slot["slot"]] = slot
        cells.add(cell)
    _pilot(joined, ladder)
    return joined


def _usage(start, where):
    fields(start["tokens"], dict.fromkeys(TOKEN_KINDS, (int, type(None))), f"{where}: tokens")
    if min([n for n in (*start["tokens"].values(), start["api_retry"]) if n is not None], default=0) < 0:
        raise RecordError(f"{where}: a negative token or api_retry count")
    _amount(start["usd"], "usd", where)
    if start["minutes"] is not None:
        _amount(start["minutes"], "minutes", where)
    graded = start["graded"]
    if graded is not None:
        fields(graded, {"passed": int, "total": int}, f"{where}: graded")
        if not 0 <= graded["passed"] <= graded["total"]:
            raise RecordError(f"{where}: graded {graded} does not hold 0 <= passed <= total")
    refused = start["egress_refused"]
    if not all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in refused.values()):
        raise RecordError(f"{where}: egress_refused {refused} is not address -> a positive count")


def frozen_term_digests(ladder):
    """The SHA-256 of every frozen contamination term (UTF-8) and the canary's SHA-256 (D6); empty while pending."""
    scan = ladder["readout"]["contamination_scan"]
    digests = {hashlib.sha256(term.encode()).hexdigest() for term in scan["terms"] or []}
    return digests | ({scan["canary_sha256"]} if scan["canary_sha256"] else set())


def _contamination(start, known, where):
    unknown = [d for d in start["contamination"] if not isinstance(d, str) or d not in known]
    if unknown:
        raise RecordError(f"{where}: contamination {unknown} names no frozen term's SHA-256 (D6)")


def smoke_cell(ladder):
    """The smoke's (task, effort, round) (D7.1): schedule.smoke's task, or, when it did not qualify, the first
    qualified task in tasks.list order (tasks.json's) that is not load-sensitive; None when no task qualifies."""
    smoke, tasks = ladder["schedule"]["smoke"], ladder["tasks"]
    qualified = tasks["qualified"]
    if qualified is None or smoke["task"] in qualified:
        return smoke["task"], smoke["effort"], 1
    task = next((t["name"] for t in tasks["list"]
                 if t["name"] in qualified and t["name"] not in (tasks["load_sensitive"] or [])), None)
    return task and (task, smoke["effort"], 1)


def _stop_seen(cause, row, slot, ladder):
    """Whether a launcher stop with this cause can occur on a start of this row and slot (LAUNCHER_STOPS)."""
    seen = LAUNCHER_STOPS.get(cause)
    if seen == "the smoke's slot":
        return (slot["task"], slot["effort"], slot["round"]) == smoke_cell(ladder)
    return seen == "any start" or (seen == "a session" and row["class"] != "pre_session_failure")


def _class(start, row, slot, ladder, where):
    """The launcher's class, checked against the row: the row's class; an infrastructure failure on an
    observation's row marked as regrade case 1 (_exclusion checks the case), or on the pre-session row with a cost
    (so it was no pre-session failure, which has none: D5, rulings on Task 8 part A m12 and re-review R-B1); or a
    stop with a launcher cause where that cause can occur (D5, D7.7). A pre-session failure with a cost is refused."""
    cls, cause = start["class"], start["stop_cause"]
    case_1 = cls == "infrastructure_failure" and row["class"] == "observation" and start["excluded"] == EXCLUSIONS[0]
    metered = cls == "infrastructure_failure" and row["class"] == "pre_session_failure" and start["usd"] > 0
    free = cls != "pre_session_failure" or start["usd"] == 0  # re-review R-B1: a pre-session failure has no cost
    if (cause is None and free and (cls == row["class"] or case_1 or metered)) or (cls == "stop" != row["class"]
                                                                and _stop_seen(cause, row, slot, ladder)):
        return cls
    raise RecordError(f"{where}: class {cls!r} with stop_cause {cause!r} does not fit row {row['row']} "
                      f"({row['class']}) on slot {slot['slot']!r}: the class is the row's, 'infrastructure_failure' "
                      f"for regrade case 1 on an observation's row or with a cost on the pre-session row (a "
                      f"pre-session failure has none), or 'stop' with a cause of LAUNCHER_STOPS where it can occur, "
                      f"{LAUNCHER_STOPS}")


def _exclusion(start, cls, observed, where):
    """An exclusion fits its D5 regrade case: case 1, an observation's ending still with no reward after its
    regrades, is an infrastructure failure (ladder.json, D5, Task 7 ruling 3); case 2, a reward of 0 that could not
    be regraded, an observation."""
    excluded, reward = start["excluded"], start["reward"]
    if excluded not in EXCLUSIONS:
        raise RecordError(f"{where}: excluded {excluded!r} is not one of {EXCLUSIONS}")
    case_1 = (excluded == EXCLUSIONS[0] and cls == "infrastructure_failure" and start["row"] in observed
              and reward is None)
    case_2 = excluded == EXCLUSIONS[1] and cls == "observation" and reward == 0
    if not (case_1 or case_2):
        raise RecordError(f"{where}: excluded {excluded!r} with class {cls!r} does not fit its D5 case (case 1: an "
                          f"infrastructure failure on an observation's row, reward null; case 2: an observation, "
                          f"reward 0); row {start['row']}, reward {reward!r}")


def _outcome(start, cls, observed, where):
    """(counted, success): whether the start enters k and n, and whether it succeeded (None when not counted)."""
    reward = start["reward"]
    if reward not in (0, 1, None):
        raise RecordError(f"{where}: reward {reward!r} is not 0, 1 or null")
    if start["excluded"] is not None:
        _exclusion(start, cls, observed, where)
    if cls != "observation" or start["excluded"] is not None or start["contamination"]:
        return False, None
    if reward is None:
        raise RecordError(f"{where}: an observation with no reward is regraded first (D5, Task 7 ruling 3): record "
                          "the reward, or exclude it as 'no reward after regrades'")
    return True, reward == 1


def _start(start, slots, labels, ladder):
    where = f"start {start.get('start')!r}" if isinstance(start, dict) else "a start"
    fields(start, START, where)
    rows = {row["row"]: row for row in ladder["classification"]["rows"]}
    if start["slot"] not in slots:
        raise RecordError(f"{where}: slot {start['slot']!r} joins no slot of the schedule")
    if start["label"] not in labels:
        raise RecordError(f"{where}: label {start['label']!r} is neither the current label nor an earlier one")
    row = rows.get(start["row"])
    if row is None or row["class"] == "ruling":
        why = "awaits a recorded ruling (D5 row 16)" if row else "is no row of D5"
        raise RecordError(f"{where}: row {start['row']} {why}")
    slot = slots[start["slot"]]
    cls = _class(start, row, slot, ladder, where)
    _usage(start, where)
    _contamination(start, frozen_term_digests(ladder), where)
    observed = {r["row"] for r in rows.values() if r["class"] == "observation"}
    counted, success = _outcome(start, cls, observed, where)
    return start | {key: slot[key] for key in ("task", "effort", "round", "pilot")} | {
        "flagged": bool(row.get("flagged")) and cls == "observation", "ending": row["ending"], "counted": counted,
        "success": success}


def _sequence(slot, starts):
    """A slot's starts in start order: each follows a cut or a pre-session failure, and none follows the slot's
    third pre-session failure, counted in all (D5)."""
    failures = 0
    for before, after in zip(starts, starts[1:]):
        failures += before["class"] == "pre_session_failure"
        if before["class"] not in AGAIN_AFTER:
            raise RecordError(f"slot {slot!r}: start {after['start']} follows start {before['start']}, a "
                              f"{before['class']}: a slot is run again only after a cut or a pre-session failure (D5)")
        if failures == 3:
            raise RecordError(f"slot {slot!r}: start {after['start']} follows the slot's third pre-session failure: "
                              "it is relaunched at most twice and lost after the third (D5)")


def _once(starts):
    numbers = [start["start"] for start in starts]
    if min(numbers, default=1) < 1:
        raise RecordError(f"a start number below 1: {sorted(n for n in numbers if n < 1)}")
    if len(set(numbers)) != len(numbers):
        raise RecordError(f"a start number is given twice: {sorted({n for n in numbers if numbers.count(n) > 1})}")
    by_slot = {}
    for start in sorted(starts, key=lambda s: s["start"]):
        by_slot.setdefault(start["slot"], []).append(start)
    for slot, own in by_slot.items():
        _sequence(slot, own)


def load(export, ladder):
    """The export's starts, each joined to its slot by slot id and to its D5 row, or a RecordError naming why not.

    Each start comes back with its slot's task, effort, round and pilot mark, its row's flag and ending, and whether
    it is counted in k and n (an observation, not excluded and with no contamination hit) and its success.
    """
    fields(export, EXPORT, "the export")
    labels = _labels(export)
    slots = _slots(export["slots"], ladder)
    starts = [_start(start, slots, labels, ladder) for start in export["starts"]]
    _once(starts)
    for entry in export["open"]:
        fields(entry, {"slot": str, "start": int}, "an open attempt")
        if entry["slot"] not in slots:
            raise RecordError(f"an open attempt: slot {entry['slot']!r} joins no slot of the schedule")
    _end(export["end"], starts, ladder)
    if export["allowance"] is not None:
        fields(export["allowance"], {"weekly_points": NUMBER, "readings": str}, "allowance")
        _amount(export["allowance"]["weekly_points"], "weekly_points", "allowance")
    return starts
