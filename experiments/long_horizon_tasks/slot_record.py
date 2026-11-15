"""The long-horizon ladder's slot records: the one definition of what the launcher writes and the readout reads.

Plan docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md, D5 to D7 and Tasks 5 and 6. The launcher
(`ladder.py`) writes one JSON document, its export, in exactly this layout; the readout (`readout.py`) reads it
through `load`, which refuses anything that does not fit, naming the record, and skips nothing. Both load this module
by its path (the kit runs under `python -I`), and neither imports the other. Standard library only.

  label           the current configuration label, the SHA-256 of manifest.json (D7.6): 64 lowercase hex digits
  earlier_labels  [{"label", "ended_by": the ledger row that ended it}], one per earlier label (D6, D7.6)
  end             null while the tranche runs; else {"by": "schedule" | "ceiling" | "starts" | "stop", "cause"}:
                  the schedule ran out, the ceiling or the 240 starts ended it (ladder.json ceiling.ends), or a stop
                  of D7.7 did; "cause" names the stop and its ledger row, and is null for every other ending
  slots           the schedule's slots (D7.3): [{"slot": id, "task": a name of ladder.json tasks.list, "effort": one
                  of attempt.efforts, "round": 1 to schedule.rounds, "pilot": true for the pilot's three (D7.2)}];
                  one slot per (task, effort, round)
  starts          every start, and every pre-session failure, of every label: [{
                    "slot"            the id of a slot above: the join; a start that joins no slot is an error
                    "start"           the launcher's start number, unique
                    "label"           the configuration label it ran under: the current one or an earlier one
                    "row"             the row of D5 that classified its ending (classification.rows); row 16 awaits
                                      a ruling and is refused until the ruling gives the start its row
                    "reward"          the verifier's reward, 0 or 1, or null; read only for an observation, where
                                      null is 0 (D5), except after a normal ending, which is regraded first (D5)
                    "excluded"        null, or why an observation is excluded after all: "contaminated" (D6, the
                                      scan), "no reward after regrades" (D5, regrade case 1, an infrastructure
                                      failure), "indeterminate" (D5, regrade case 2)
                    "contamination"   the SHA-256 of each frozen term the launcher's scan found in the attempt's
                                      transcript at teardown (readout.contamination_scan: the SHA-256 of a term's
                                      UTF-8 bytes, or canary_sha256), never the term; [] when none; non-empty exactly
                                      when "excluded" is "contaminated"
                    "usd"             the settled priced cost of the start (D4)
                    "minutes"         the session's length
                    "tokens"          {"input", "output", "cache_read", "cache_write_5m", "cache_write_1h"}: integers
                    "graded"          null, or {"passed", "total"} sub-tests where the verifier reports them (D6)
                    "egress_refused"  {address: count} of refused connections (D3); excludes nothing
                  }]; a slot holds at most one start that is neither a cut nor a pre-session failure (D5: a slot is
                  run again only after those)
  allowance       null, or {"weekly_points": meter points of a weekly allowance the tranche used, summed from the
                  owner's readings, "readings": the ledger rows they come from} (D6, cost; enters no rule)

A start's class (observation, flagged or not; cut; infrastructure failure; stop; pre-session failure) is its row's
in ladder.json. An observation with "excluded" set is listed and enters no k or n.
"""

import hashlib
import re
from collections import Counter

TOKEN_KINDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
EXCLUSIONS = ("contaminated", "no reward after regrades", "indeterminate")
ENDS = ("schedule", "ceiling", "starts", "stop")
NUMBER = (int, float)
EXPORT = {"label": str, "earlier_labels": list, "end": (dict, type(None)), "slots": list, "starts": list,
          "allowance": (dict, type(None))}
SLOT = {"slot": str, "task": str, "effort": str, "round": int, "pilot": bool}
START = {"slot": str, "start": int, "label": str, "row": int, "reward": (int, float, type(None)),
         "excluded": (str, type(None)), "contamination": list, "usd": NUMBER, "minutes": NUMBER, "tokens": dict,
         "graded": (dict, type(None)), "egress_refused": dict}
SHA256 = re.compile(r"[0-9a-f]{64}")


class RecordError(ValueError):
    """A record that does not fit the layout; the message names it."""


def fields(obj, spec, where):
    """obj is a dict with exactly spec's keys, each of its type; a bool is never an int or a number."""
    if not isinstance(obj, dict) or set(obj) != set(spec):
        keys = sorted(obj) if isinstance(obj, dict) else type(obj).__name__
        raise RecordError(f"{where}: keys {keys} are not {sorted(spec)}")
    for key, kind in spec.items():
        kinds = kind if isinstance(kind, tuple) else (kind,)
        if not isinstance(obj[key], kinds) or (isinstance(obj[key], bool) and bool not in kinds):
            raise RecordError(f"{where}: {key} is {obj[key]!r}, not {' or '.join(k.__name__ for k in kinds)}")


def _hex_label(value, where):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise RecordError(f"{where}: label {value!r} is not a SHA-256 (64 lowercase hex digits)")
    return value


def _labels(export):
    earlier = []
    for entry in export["earlier_labels"]:
        fields(entry, {"label": str, "ended_by": str}, "an earlier label")
        earlier.append(_hex_label(entry["label"], "an earlier label"))
    labels = [_hex_label(export["label"], "the export")] + earlier
    if len(set(labels)) != len(labels):
        raise RecordError(f"a configuration label is given twice: {labels}")
    return set(labels)


def _end(end):
    if end is None:
        return
    fields(end, {"by": str, "cause": (str, type(None))}, "end")
    if end["by"] not in ENDS:
        raise RecordError(f"end: by {end['by']!r} is not one of {ENDS}")
    if (end["by"] == "stop") != bool(end["cause"]):
        raise RecordError(f"end: a stop names its cause and ledger row, and no other ending has a cause: {end}")


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


def _slots(slots, ladder):
    joined, cells = {}, set()
    for slot in slots:
        _slot(slot, ladder)
        cell = (slot["task"], slot["effort"], slot["round"])
        if slot["slot"] in joined or cell in cells:
            raise RecordError(f"slot {slot['slot']!r}: a slot id or a (task, effort, round) is given twice")
        joined[slot["slot"]] = slot
        cells.add(cell)
    return joined


def _usage(start, where):
    fields(start["tokens"], dict.fromkeys(TOKEN_KINDS, int), f"{where}: tokens")
    if min(start["tokens"].values()) < 0 or start["usd"] < 0 or start["minutes"] < 0:
        raise RecordError(f"{where}: a negative usd, minutes or token count")
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
    found = start["contamination"]
    if (start["excluded"] == "contaminated") != bool(found):
        raise RecordError(f"{where}: contamination {found} and excluded {start['excluded']!r} disagree: a start is "
                          "excluded as contaminated exactly when the scan found a term")
    unknown = [d for d in found if not isinstance(d, str) or d not in known]
    if unknown:
        raise RecordError(f"{where}: contamination {unknown} names no frozen term's SHA-256 (D6)")


def _outcome(start, row, normal, where):
    """(counted, success): whether the start enters k and n, and whether it succeeded (None when not counted)."""
    reward, excluded = start["reward"], start["excluded"]
    if reward not in (0, 1, None):
        raise RecordError(f"{where}: reward {reward!r} is not 0, 1 or null")
    if excluded is not None and (row["class"] != "observation" or excluded not in EXCLUSIONS):
        raise RecordError(f"{where}: excluded {excluded!r}: only an observation is excluded, as one of {EXCLUSIONS}")
    if row["class"] != "observation" or excluded is not None:
        return False, None
    if reward is None and row["row"] == normal:
        raise RecordError(f"{where}: a normal ending with no reward is regraded first (D5): record the reward, or "
                          "exclude it as 'no reward after regrades'")
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
    _usage(start, where)
    _contamination(start, frozen_term_digests(ladder), where)
    normal = next(r["row"] for r in rows.values() if r["ending"] == "Normal")
    counted, success = _outcome(start, row, normal, where)
    slot = slots[start["slot"]]
    return start | {key: slot[key] for key in ("task", "effort", "round", "pilot")} | {
        "class": row["class"], "flagged": bool(row.get("flagged")), "ending": row["ending"], "counted": counted,
        "success": success}


def _once(starts):
    numbers = Counter(start["start"] for start in starts)
    if any(count > 1 for count in numbers.values()):
        raise RecordError(f"a start number is given twice: {sorted(n for n, c in numbers.items() if c > 1)}")
    final = Counter(s["slot"] for s in starts if s["class"] not in ("cut", "pre_session_failure"))
    twice = sorted(slot for slot, count in final.items() if count > 1)
    if twice:
        raise RecordError(f"slots {twice} hold more than one start that is not a cut or a pre-session failure: a "
                          "slot is never run again after any other ending (D5)")


def load(export, ladder):
    """The export's starts, each joined to its slot by slot id and to its D5 row, or a RecordError naming why not.

    Each start comes back with its slot's task, effort, round and pilot mark, its row's class, flag and ending, and
    whether it is counted in k and n (an observation not excluded) and its success.
    """
    fields(export, EXPORT, "the export")
    labels = _labels(export)
    _end(export["end"])
    slots = _slots(export["slots"], ladder)
    starts = [_start(start, slots, labels, ladder) for start in export["starts"]]
    _once(starts)
    if export["allowance"] is not None:
        fields(export["allowance"], {"weekly_points": NUMBER, "readings": str}, "allowance")
    return starts
