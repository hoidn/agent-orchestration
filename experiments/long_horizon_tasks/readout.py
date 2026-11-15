"""The long-horizon readout (plan docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md, D6 and Task 6).

From the launcher's slot records to the readout of D6 and to `family.json` (the plan's step 7). Every rule and
threshold is read from `ladder.json` (its `readout`, `classification`, `attempt` and `schedule` groups). Every figure
is computed once, by `compute`, from the starts joined to the schedule's slots by slot id; `render` and `family` only
format what `compute` returned. Standard library only, so it runs under `python -I` like the rest of the kit.

The record read: one JSON document, the launcher's export. `load` refuses anything that does not fit it, naming the
record; nothing is skipped.

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

import argparse
import copy
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

KIT = Path(__file__).resolve().parent
LADDER_PATH = "experiments/long_horizon_tasks/ladder.json"
POOLED_LABELS = ("screened in", "floor", "above the band", "no observation")
DIGESTS = ("digest_4_1_0", "environment_image", "verifier_image", "overlay_digest")

TOKEN_KINDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
EXCLUSIONS = ("contaminated", "no reward after regrades", "indeterminate")
ENDS = ("schedule", "ceiling", "starts", "stop")
NUMBER = (int, float)
EXPORT = {"label": str, "earlier_labels": list, "end": (dict, type(None)), "slots": list, "starts": list,
          "allowance": (dict, type(None))}
SLOT = {"slot": str, "task": str, "effort": str, "round": int, "pilot": bool}
START = {"slot": str, "start": int, "label": str, "row": int, "reward": (int, float, type(None)),
         "excluded": (str, type(None)), "usd": NUMBER, "minutes": NUMBER, "tokens": dict,
         "graded": (dict, type(None)), "egress_refused": dict}


class ReadoutError(ValueError):
    """A record, a rule or a request the readout refuses; the message names it."""


def _binomial_cdf(k, n, p):
    """P(X <= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def _root(decreasing, target):
    """The p in [0, 1] where a function that decreases in p crosses target, by bisection to float precision."""
    low, high = 0.0, 1.0
    for _ in range(200):
        middle = (low + high) / 2
        low, high = (middle, high) if decreasing(middle) > target else (low, middle)
    return (low + high) / 2


def _upper(k, n, tail):
    """The p at which P(X <= k) falls to tail; 1 when k is n."""
    return 1.0 if k == n else _root(lambda p: _binomial_cdf(k, n, p), tail)


def interval(k, n, level):
    """The exact (Clopper-Pearson) two-sided interval for k successes of n at the given level (D6).

    The lower bound is one minus the upper bound of the n - k failures.
    """
    tail = (1 - level) / 2
    return 1.0 - _upper(n - k, n, tail), _upper(k, n, tail)


def cell_label(k, n, rule):
    """D6's label of one (task, effort) cell under ladder.json's readout.cell rule."""
    if n > rule["complete_n"]:
        raise ReadoutError(f"a cell holds more than {rule['complete_n']} observations ({n})")
    if n < rule["complete_n"]:
        return "incomplete"
    if k == rule["floor_k"]:
        return "floor"
    if k in rule["screened_in_k"]:
        return "screened in"
    if k >= rule["above_k_at_least"]:
        return "above"
    raise ReadoutError(f"readout.cell gives no label to {k} of {n}")


def pooled_label(K, n, rule):
    """D6's pooled label of a task, K successes of its n observations, under ladder.json's readout.pooled rule."""
    if n == 0:
        return "no observation"
    if K == rule["floor_K"]:
        return "floor"
    band = rule["screened_in"]
    # Open ruling R4: the ratio rule is applied at any n; D6 states it, and its phrase, at 15 attempts.
    inside = Fraction(band["from"]) <= Fraction(K, n) <= Fraction(band["to"])
    return "screened in" if inside else "above the band"


def band_effort(cells, rules):
    """D6's band effort of a screened-in task; cells maps each effort, in the ladder's order, to (k, n).

    Among the levels with at least one success, the one whose k/n is closest to readout.band_effort.closest_to,
    ties to the lower level. Refused for a task the pooled label does not screen in, which has none.
    """
    total = [sum(column) for column in zip(*cells.values())]
    if pooled_label(total[0], total[1], rules["pooled"]) != "screened in":
        raise ReadoutError(f"a band effort is defined for a screened-in task only; this one is not screened in: "
                           f"{cells}")
    rule = rules["band_effort"]
    target = Fraction(str(rule["closest_to"]))
    order = list(cells)
    effort = min((e for e, (k, n) in cells.items() if k >= 1),
                 key=lambda e: (abs(Fraction(cells[e][0], cells[e][1]) - target), order.index(e)))
    return {"effort": effort, "label": rule["label"], "flagged": cells[effort][0] >= rule["flagged_if_k_at_least"]}


def sign_flip_p(ds):
    """The exact one-sided p values of the sign-flip permutation test on sum(ds): (P(T <= t), P(T >= t)).

    Under the null each d_i keeps or flips its sign with probability 1/2; the distribution of T is counted exactly
    over all 2^m assignments, so a d_i of 0 leaves both p values unchanged.
    """
    counts = {0: 1}
    for d in ds:
        step = defaultdict(int)
        for total, count in counts.items():
            step[total + d] += count
            step[total - d] += count
        counts = step
    observed, assignments = sum(ds), 2 ** len(ds)
    below = sum(count for total, count in counts.items() if total <= observed)
    above = sum(count for total, count in counts.items() if total >= observed)
    return Fraction(below, assignments), Fraction(above, assignments)


def _difference(tasks, a, b):
    ds = [tasks[task]["successes"][a] - tasks[task]["successes"][b] for task in sorted(tasks)]
    below, above = sign_flip_p(ds)
    return {"sum": sum(ds), "p_below": below, "p_above": above}


def _verdict(differences, pooled, efforts, rule):
    """D6: falls, rises or not resolved, from the differences and the pooled successes over complete triples."""
    high_low, adjacent = rule["falls"]
    name = "-".join(high_low["d"])
    if differences[name]["sum"] < high_low["sum_below"] and differences[name]["p_below"] <= _p(high_low):
        return "falls"
    pairs = [f"{b}-{a}" for a, b in zip(efforts, efforts[1:])]
    if any(differences[p]["sum"] < adjacent["sum_below"] and differences[p]["p_below"] <= _p(adjacent) for p in pairs):
        return "falls"
    rises, name = rule["rises"], "-".join(rule["rises"]["d"])
    ordered = all(pooled[a] <= pooled[b] for a, b in zip(efforts, efforts[1:]))
    if ordered and differences[name]["sum"] > rises["sum_above"] and differences[name]["p_above"] <= _p(rises):
        return "rises"
    return rule["otherwise"]


def _p(rule):
    return Fraction(str(rule["p_at_most"]))


def fall_bound(tasks, low, high, rule):
    """D6's bound on the fall: the one-sided upper bound on the pooled fall from low to high, in points.

    A bootstrap over tasks (rule["resamples"] resamples drawn by random.Random(rule["seed"]), tasks in name order);
    the bound is the smallest resampled fall with at least rule["one_sided"] of the resamples at or below it. None
    when no task has a complete triple.
    """
    rows = [(tasks[task]["triples"], tasks[task]["successes"][low] - tasks[task]["successes"][high])
            for task in sorted(tasks)]
    if not rows:
        return None
    # Open ruling R5: D6 names no generator or quantile; these are random.Random(seed) and the ceil(0.95 R)-th fall.
    rng, resamples = random.Random(rule["seed"]), rule["resamples"]
    falls = []
    for _ in range(resamples):
        picks = [rows[rng.randrange(len(rows))] for _ in rows]
        falls.append(100 * sum(fall for _, fall in picks) / sum(triples for triples, _ in picks))
    return sorted(falls)[math.ceil(rule["one_sided"] * resamples) - 1]


def effort_test(tasks, efforts, rules):
    """D6's effort test over complete (task, round) triples.

    tasks maps each task with at least one complete triple to {"triples": t, "successes": {effort: s_i(e)}}. Returns
    the pooled successes, each difference's sum and exact one-sided p values, the verdict and the bound on the fall.
    """
    rule = rules["effort_test"]
    pairs = [tuple(rule["falls"][0]["d"])] + [(b, a) for a, b in zip(efforts, efforts[1:])]
    differences = {f"{a}-{b}": _difference(tasks, a, b) for a, b in pairs}
    pooled = {e: sum(task["successes"][e] for task in tasks.values()) for e in efforts}
    low, high = efforts[0], efforts[-1]
    return {"tasks": len(tasks), "triples": sum(task["triples"] for task in tasks.values()), "pooled": pooled,
            "differences": differences, "verdict": _verdict(differences, pooled, efforts, rule),
            "fall_bound": fall_bound(tasks, low, high, rules["fall_bound"])}


# ---- The record: load and join ------------------------------------------------------------------------------------

def _fields(obj, spec, where):
    """obj is a dict with exactly spec's keys, each of its type; a bool is never an int or a number."""
    if not isinstance(obj, dict) or set(obj) != set(spec):
        keys = sorted(obj) if isinstance(obj, dict) else type(obj).__name__
        raise ReadoutError(f"{where}: keys {keys} are not {sorted(spec)}")
    for key, kind in spec.items():
        kinds = kind if isinstance(kind, tuple) else (kind,)
        if not isinstance(obj[key], kinds) or (isinstance(obj[key], bool) and bool not in kinds):
            raise ReadoutError(f"{where}: {key} is {obj[key]!r}, not {' or '.join(k.__name__ for k in kinds)}")


def _hex_label(value, where):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ReadoutError(f"{where}: label {value!r} is not a SHA-256 (64 lowercase hex digits)")
    return value


def _labels(export):
    earlier = []
    for entry in export["earlier_labels"]:
        _fields(entry, {"label": str, "ended_by": str}, "an earlier label")
        earlier.append(_hex_label(entry["label"], "an earlier label"))
    labels = [_hex_label(export["label"], "the export")] + earlier
    if len(set(labels)) != len(labels):
        raise ReadoutError(f"a configuration label is given twice: {labels}")
    return set(labels)


def _end(end):
    if end is None:
        return
    _fields(end, {"by": str, "cause": (str, type(None))}, "end")
    if end["by"] not in ENDS:
        raise ReadoutError(f"end: by {end['by']!r} is not one of {ENDS}")
    if (end["by"] == "stop") != bool(end["cause"]):
        raise ReadoutError(f"end: a stop names its cause and ledger row, and no other ending has a cause: {end}")


def _slot(slot, ladder):
    where = f"slot {slot.get('slot')!r}" if isinstance(slot, dict) else "a slot"
    _fields(slot, SLOT, where)
    if slot["task"] not in {task["name"] for task in ladder["tasks"]["list"]}:
        raise ReadoutError(f"{where}: task {slot['task']!r} is not in ladder.json tasks.list")
    if slot["effort"] not in ladder["attempt"]["efforts"]:
        raise ReadoutError(f"{where}: effort {slot['effort']!r} is not one of {ladder['attempt']['efforts']}")
    if not 1 <= slot["round"] <= ladder["schedule"]["rounds"]:
        raise ReadoutError(f"{where}: round {slot['round']} is outside 1 to {ladder['schedule']['rounds']}")
    return slot


def _slots(slots, ladder):
    joined, cells = {}, set()
    for slot in slots:
        _slot(slot, ladder)
        cell = (slot["task"], slot["effort"], slot["round"])
        if slot["slot"] in joined or cell in cells:
            raise ReadoutError(f"slot {slot['slot']!r}: a slot id or a (task, effort, round) is given twice")
        joined[slot["slot"]] = slot
        cells.add(cell)
    return joined


def _usage(start, where):
    _fields(start["tokens"], dict.fromkeys(TOKEN_KINDS, int), f"{where}: tokens")
    if min(start["tokens"].values()) < 0 or start["usd"] < 0 or start["minutes"] < 0:
        raise ReadoutError(f"{where}: a negative usd, minutes or token count")
    graded = start["graded"]
    if graded is not None:
        _fields(graded, {"passed": int, "total": int}, f"{where}: graded")
        if not 0 <= graded["passed"] <= graded["total"]:
            raise ReadoutError(f"{where}: graded {graded} does not hold 0 <= passed <= total")
    refused = start["egress_refused"]
    if not all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in refused.values()):
        raise ReadoutError(f"{where}: egress_refused {refused} is not address -> a positive count")


def _outcome(start, row, normal, where):
    """(counted, success): whether the start enters k and n, and whether it succeeded (None when not counted)."""
    reward, excluded = start["reward"], start["excluded"]
    if reward not in (0, 1, None):
        raise ReadoutError(f"{where}: reward {reward!r} is not 0, 1 or null")
    if excluded is not None and (row["class"] != "observation" or excluded not in EXCLUSIONS):
        raise ReadoutError(f"{where}: excluded {excluded!r}: only an observation is excluded, as one of {EXCLUSIONS}")
    if row["class"] != "observation" or excluded is not None:
        return False, None
    if reward is None and row["row"] == normal:
        raise ReadoutError(f"{where}: a normal ending with no reward is regraded first (D5): record the reward, or "
                           "exclude it as 'no reward after regrades'")
    return True, reward == 1


def _start(start, slots, labels, ladder):
    where = f"start {start.get('start')!r}" if isinstance(start, dict) else "a start"
    _fields(start, START, where)
    rows = {row["row"]: row for row in ladder["classification"]["rows"]}
    if start["slot"] not in slots:
        raise ReadoutError(f"{where}: slot {start['slot']!r} joins no slot of the schedule")
    if start["label"] not in labels:
        raise ReadoutError(f"{where}: label {start['label']!r} is neither the current label nor an earlier one")
    row = rows.get(start["row"])
    if row is None or row["class"] == "ruling":
        why = "awaits a recorded ruling (D5 row 16)" if row else "is no row of D5"
        raise ReadoutError(f"{where}: row {start['row']} {why}")
    _usage(start, where)
    normal = next(r["row"] for r in rows.values() if r["ending"] == "Normal")
    counted, success = _outcome(start, row, normal, where)
    slot = slots[start["slot"]]
    return start | {key: slot[key] for key in ("task", "effort", "round", "pilot")} | {
        "class": row["class"], "flagged": bool(row.get("flagged")), "ending": row["ending"], "counted": counted,
        "success": success}


def _once(starts):
    numbers = Counter(start["start"] for start in starts)
    if any(count > 1 for count in numbers.values()):
        raise ReadoutError(f"a start number is given twice: {sorted(n for n, c in numbers.items() if c > 1)}")
    final = Counter(s["slot"] for s in starts if s["class"] not in ("cut", "pre_session_failure"))
    twice = sorted(slot for slot, count in final.items() if count > 1)
    if twice:
        raise ReadoutError(f"slots {twice} hold more than one start that is not a cut or a pre-session failure: a "
                           "slot is never run again after any other ending (D5)")


def load(export, ladder):
    """The export's starts, each joined to its slot by slot id and to its D5 row, or a ReadoutError naming why not."""
    _fields(export, EXPORT, "the export")
    labels = _labels(export)
    _end(export["end"])
    slots = _slots(export["slots"], ladder)
    starts = [_start(start, slots, labels, ladder) for start in export["starts"]]
    _once(starts)
    if export["allowance"] is not None:
        _fields(export["allowance"], {"weekly_points": NUMBER, "readings": str}, "allowance")
    return starts


# ---- The criterion: pending readout fields and a rehearsal's stand-ins --------------------------------------------

def _criterion(ladder, standins):
    """(the criterion the readout applies, whether it is a rehearsal).

    A final readout (standins None) is refused while ladder.json marks a readout field pending. A rehearsal takes a
    stand-in for every pending readout field, and for nothing else.
    """
    pending = [p["field"] for p in ladder["pending"] if p["field"].startswith("readout.")]
    if standins is None:
        if pending:
            raise ReadoutError(f"ladder.json marks readout fields pending: {', '.join(pending)}; a final readout "
                               "waits for them (a rehearsal names stand-ins with --rehearsal)")
        return ladder, False
    missing, extra = sorted(set(pending) - set(standins)), sorted(set(standins) - set(pending))
    if missing or extra:
        raise ReadoutError(f"a rehearsal gives a stand-in for each pending readout field; missing {missing}, "
                           f"not pending {extra}")
    criterion = copy.deepcopy(ladder)
    for field, value in standins.items():
        *path, key = field.split(".")
        target = criterion
        for part in path:
            target = target[part]
        target[key] = value
    return criterion, True


# ---- compute: every figure, once ------------------------------------------------------------------------------------

def _counts(starts, tasks, efforts, level):
    """{task: {effort: {"k", "n", "interval"}}} over the counted starts given."""
    cells = {task: {effort: [0, 0] for effort in efforts} for task in tasks}
    for start in starts:
        if start["counted"]:
            cell = cells[start["task"]][start["effort"]]
            cell[0] += start["success"]
            cell[1] += 1
    return {task: {e: {"k": k, "n": n, "interval": interval(k, n, level)} for e, (k, n) in by.items()}
            for task, by in cells.items()}


def _placement(cells, rules, place):
    """Per task: the cells and the pooled count; when place, their labels and the band effort (D6)."""
    level = rules["interval"]["level"]
    placed = {}
    for task, by_effort in cells.items():
        K, n = sum(c["k"] for c in by_effort.values()), sum(c["n"] for c in by_effort.values())
        placed[task] = {"cells": by_effort, "pooled": {"K": K, "n": n, "interval": interval(K, n, level)},
                        "band_effort": None}
        if place:
            placed[task] = _placed(placed[task], rules)
    return placed


def _placed(task, rules):
    pooled = task["pooled"] | {"label": pooled_label(task["pooled"]["K"], task["pooled"]["n"], rules["pooled"])}
    cells = {e: c | {"label": cell_label(c["k"], c["n"], rules["cell"])} for e, c in task["cells"].items()}
    band = None
    if pooled["label"] == "screened in":
        band = band_effort({e: (c["k"], c["n"]) for e, c in cells.items()}, rules)
    return {"cells": cells, "pooled": pooled, "band_effort": band}


def _triples(starts, efforts):
    """Per task with a complete (task, round) triple: {"triples": t, "successes": {effort: s_i(e)}} (D6)."""
    rounds = defaultdict(dict)
    for start in starts:
        if start["counted"]:
            rounds[start["task"], start["round"]][start["effort"]] = int(start["success"])
    tasks = {}
    for (task, _), triple in sorted(rounds.items()):
        if len(triple) == len(efforts):
            entry = tasks.setdefault(task, {"triples": 0, "successes": dict.fromkeys(efforts, 0)})
            entry["triples"] += 1
            for effort in efforts:
                entry["successes"][effort] += triple[effort]
    return tasks


def _entry(start):
    return {key: start[key] for key in ("start", "slot", "task", "effort", "round", "row", "class", "ending")}


def _listed(starts, efforts):
    """D6's lists: every start that enters no k or n, with its class and why; every flagged observation; the
    attempts cut by a usage limit, counted per effort; the pilot's attempts, marked (D7.2); the refused
    connections of each attempt (D3, D6), which exclude nothing."""
    cuts = Counter(s["effort"] for s in starts if s["class"] == "cut")
    return {"exclusions": [_entry(s) | {"reason": s["excluded"] or s["ending"]} for s in starts if not s["counted"]],
            "flags": [_entry(s) for s in starts if s["counted"] and s["flagged"]],
            "cuts": {e: cuts[e] for e in efforts}, "pilot": [_entry(s) for s in starts if s["pilot"]],
            "egress": _egress(starts)}


def _egress(starts):
    return [_entry(s) | {"refused": s["egress_refused"]} for s in starts if s["egress_refused"]]


def _mean(values):
    return sum(values) / len(values) if values else None


def _means(observations):
    return {"mean_usd": _mean([s["usd"] for s in observations]),
            "mean_minutes": _mean([s["minutes"] for s in observations]),
            "mean_tokens": {kind: _mean([s["tokens"][kind] for s in observations]) for kind in TOKEN_KINDS}}


def _level_cost(starts, effort, classes):
    """D6's cost of one effort level: means per observation; every start's cost over the level's successes."""
    observations = [s for s in starts if s["effort"] == effort and s["counted"]]
    started = [s for s in starts if s["effort"] == effort and classes[s["class"]]["starts"]]
    successes, usd = sum(s["success"] for s in observations), sum(s["usd"] for s in started)
    return {"observations": len(observations)} | _means(observations) | {
        "starts": len(started), "usd_all_starts": usd, "successes": successes,
        "usd_per_success": usd / successes if successes else None}


def _beats(other, effort, per_effort, triples, rule):
    """Whether other beats effort on the sign-flip test at p <= 0.05 and has a lower mean cost (D6)."""
    # Open ruling R3: ladder.json states this threshold in prose only; effort_test.rises.p_at_most is the same 0.05.
    difference = _difference(triples, other, effort)
    mine, theirs = per_effort[effort]["mean_usd"], per_effort[other]["mean_usd"]
    cheaper = None not in (mine, theirs) and theirs < mine
    return difference["sum"] > 0 and difference["p_above"] <= _p(rule["rises"]) and cheaper


def _dominated(effort, per_effort, triples, rule):
    """D6: an effort level is named dominated only by a level that beats it; otherwise "not resolved"."""
    for other in per_effort:
        if other != effort and _beats(other, effort, per_effort, triples, rule):
            return {"verdict": "dominated", "by": other}
    return {"verdict": "not resolved", "by": None}


def _cost(starts, efforts, triples, ladder, place):
    """D6's cost per effort; the dominance verdicts only when the readout places (not after a stop)."""
    classes = ladder["classification"]["classes"]
    per_effort = {e: _level_cost(starts, e, classes) for e in efforts}
    rule = ladder["readout"]["effort_test"]
    return {"per_effort": per_effort,
            "dominated": {e: _dominated(e, per_effort, triples, rule) for e in efforts} if place else None}


def _graded(starts, tasks, efforts, verifiers):
    """D6's graded outcome, per task and effort: sub-tests passed and total, where the task's verifier reports them."""
    graded = {}
    for task in tasks:
        if task not in (verifiers or {}):
            graded[task] = "pass or fail only"
            continue
        graded[task] = {}
        for effort in efforts:
            reported = [s["graded"] for s in starts if (s["task"], s["effort"]) == (task, effort) and s["counted"]
                        and s["graded"] is not None]
            graded[task][effort] = {"passed": sum(g["passed"] for g in reported),
                                    "total": sum(g["total"] for g in reported), "observations": len(reported)}
    return graded


def _allowance(allowance, starts):
    """D6: the share of a weekly allowance the tranche used, in all and per priced dollar (every start, every label)."""
    if allowance is None:
        return None
    usd = sum(s["usd"] for s in starts)
    return allowance | {"usd": usd, "points_per_usd": allowance["weekly_points"] / usd if usd else None}


def _configuration(ladder):
    """The configuration the readout names (D2, D6): model, efforts, CLI, tools, harness, network."""
    attempt, harness = ladder["attempt"], ladder["harness"]
    return {"model": attempt["model"], "efforts": attempt["efforts"], "cli_version": attempt["cli_version"],
            "tools": attempt["init_event"]["tools"], "harbor": harness["harbor"],
            "podman_compose": harness["podman_compose"], "network": ladder["network"]["agent_phase"]}


def _earlier(starts, export, tasks, efforts, level):
    """Per earlier label: its ledger row, its cells (k of n, no label) and its lists; they enter no rule (D6)."""
    earlier = []
    for entry in export["earlier_labels"]:
        own = [s for s in starts if s["label"] == entry["label"]]
        earlier.append(entry | {"cells": _counts(own, tasks, efforts, level), "listed": _listed(own, efforts)})
    return earlier


def compute(ladder, export, standins=None):
    """Every figure of the readout, from the export's starts joined by slot id; rules read from ladder.json.

    Every rule reads the current label's starts alone. A readout that ends in a stop places nothing: no cell or
    pooled label, no band effort, no effort test and no dominance (D6).
    """
    criterion, rehearsal = _criterion(ladder, standins)
    starts = load(export, criterion)
    efforts, rules = criterion["attempt"]["efforts"], criterion["readout"]
    in_tranche = {slot["task"] for slot in export["slots"]}
    tasks = [task["name"] for task in criterion["tasks"]["list"] if task["name"] in in_tranche]
    level = rules["interval"]["level"]
    current = [start for start in starts if start["label"] == export["label"]]
    triples = _triples(current, efforts)
    # Open ruling R2: "prints no placement" is read as withholding the bound on the fall, which D6 "always" reports.
    place = export["end"] is None or export["end"]["by"] != "stop"
    return {"rehearsal": rehearsal, "configuration": _configuration(criterion), "label": export["label"],
            "end": export["end"], "stop": not place,
            "tasks": _placement(_counts(current, tasks, efforts, level), rules, place),
            "effort": effort_test(triples, efforts, rules) | {"per_task": triples} if place else None,
            "listed": _listed(current, efforts), "earlier": _earlier(starts, export, tasks, efforts, level),
            "rules": {"fall_bound": rules["fall_bound"], "interval": rules["interval"],
                      "stop_readout": rules["stop_readout"]},
            "cost": _cost(current, efforts, triples, criterion, place),
            "graded": _graded(current, tasks, efforts, rules["graded_outcome"]["verifiers"]),
            "allowance": _allowance(export["allowance"], starts)}


# ---- render: the readout as text, formatting compute's figures only ------------------------------------------------

def _percent(value):
    return f"{100 * value:.1f}"


def _count(cell, k="k", n="n"):
    lower, upper = cell["interval"]
    return f"{cell[k]} of {cell[n]} ({_percent(lower)}–{_percent(upper)}%)"


def _labelled(cell, k="k"):
    return f"{_count(cell, k)} {cell['label']}" if "label" in cell else _count(cell, k)


def _header(result):
    configuration, end = result["configuration"], result["end"]
    network = configuration["network"]
    lines = ["# Long-horizon readout" + (" (REHEARSAL)" if result["rehearsal"] else ""), ""]
    if result["rehearsal"]:
        lines += ["**REHEARSAL: stand-in values for the pending readout fields; nothing here is a result.**", ""]
    ended = "in progress (no family.json)" if end is None else end["by"] + (f": {end['cause']}" if end["cause"] else "")
    lines += [f"- Configuration (D2): `{configuration['model']}` at {', '.join(configuration['efforts'])}; CLI "
              f"{configuration['cli_version']}; tools {', '.join(configuration['tools'])}; Harbor "
              f"{configuration['harbor']}, podman-compose {configuration['podman_compose']}; agent network "
              f"{network['network_mode']}, hosts {', '.join(network['allowed_hosts'] or ['(pending)'])}",
              f"- Configuration label: `{result['label']}`", f"- Tranche: {ended}", ""]
    return lines


def _tasks_table(result):
    efforts = result["configuration"]["efforts"]
    shown, level = "no placement after a stop" if result["stop"] else "label", result["rules"]["interval"]["level"]
    lines = [f"## Tasks (current label; k of n, exact {level:.0%} interval, {shown})", "",
             "| Task | " + " | ".join(efforts) + " | Pooled | Band effort |", "|" + " --- |" * (len(efforts) + 3)]
    for task, placed in result["tasks"].items():
        pooled, band = placed["pooled"], placed["band_effort"]
        screened = f", screened at {pooled['n']} attempts" if pooled.get("label") == "screened in" else ""
        banded = "none" if band is None else f"{band['effort']}, {band['label']}" + (
            ", flagged" if band["flagged"] else "")
        cells = [_labelled(placed["cells"][e]) for e in efforts] + [_labelled(pooled, "K") + screened]
        lines.append(f"| {task} | " + " | ".join(cells) + f" | {'withheld' if result['stop'] else banded} |")
    return lines + [""]


def _fraction(p):
    return f"{p} ({float(p):.4f})"


def _effort_section(result):
    effort, rule = result["effort"], result["rules"]["fall_bound"]
    if effort is None:
        return ["## Effort test (complete triples of the current label)", "",
                f"Withheld: {result['rules']['stop_readout']} (D6).", ""]
    lines = ["## Effort test (complete triples of the current label)", "",
             f"Complete triples: {effort['triples']} over {effort['tasks']} tasks. Pooled successes: " +
             ", ".join(f"{e} {s} of {effort['triples']}" for e, s in effort["pooled"].items()) + ".", "",
             "| Difference | Sum of d_i | p, sum at or below | p, sum at or above |", "| --- | --- | --- | --- |"]
    for name, d in effort["differences"].items():
        lines.append(f"| {name} | {d['sum']} | {_fraction(d['p_below'])} | {_fraction(d['p_above'])} |")
    bound = "none: no complete triple" if effort["fall_bound"] is None else f"{effort['fall_bound']:.1f} points"
    return lines + ["", f"**Verdict: {effort['verdict']}.** Bound on the fall (one-sided {rule['one_sided']:.0%} "
                        f"upper bound on the pooled fall from {result['configuration']['efforts'][0]} to "
                        f"{result['configuration']['efforts'][-1]}, bootstrap over tasks, {rule['resamples']} "
                        f"resamples, seed {rule['seed']}): {bound}. {rule['rule']}", ""]


def _refused(entry):
    return ", ".join(f"{address}: {count}" for address, count in sorted(entry["refused"].items()))


def _entries(title, entries, why=None):
    lines = [f"### {title}", ""]
    for e in entries:
        lines.append(f"- start {e['start']}, {e['task']} {e['effort']} round {e['round']}, row {e['row']} "
                     f"({e['class']})" + (f": {why(e)}" if why else ""))
    return lines + (["- none"] if not entries else []) + [""]


def _listed_section(listed):
    return (["## Listed", ""] + _entries("Exclusions (enter no k or n)", listed["exclusions"], lambda e: e["reason"])
            + _entries("Flagged observations", listed["flags"], lambda e: e["ending"])
            + ["### Cut by a usage limit, per effort", "", ", ".join(f"{e} {n}" for e, n in listed["cuts"].items()),
               ""] + _entries("The pilot's attempts (they ran first)", listed["pilot"])
            + _entries("Refused connections (they exclude nothing)", listed["egress"], _refused))


def _earlier_section(result):
    efforts = result["configuration"]["efforts"]
    lines = ["## Earlier configuration labels (printed apart; they enter no rule)", ""]
    for earlier in result["earlier"]:
        lines += [f"Label `{earlier['label']}`, ended by: {earlier['ended_by']}", "",
                  "| Task | " + " | ".join(efforts) + " |", "|" + " --- |" * (len(efforts) + 1)]
        lines += [f"| {task} | " + " | ".join(_count(cells[e]) for e in efforts) + " |"
                  for task, cells in earlier["cells"].items()]
        lines += [""] + _entries("Exclusions under this label", earlier["listed"]["exclusions"], lambda e: e["reason"])
    return lines + (["- none", ""] if not result["earlier"] else [])


def _money(value, unit="USD "):
    return "none" if value is None else f"{unit}{value:.2f}"


def _cost_section(result):
    lines = ["## Cost per effort (current label)", "",
             "| Effort | Observations | Mean priced cost | Mean minutes | Mean tokens by kind | Starts | Cost of "
             "every start | Successes | Cost per success | Dominated |", "|" + " --- |" * 10]
    for effort, c in result["cost"]["per_effort"].items():
        tokens = ", ".join(f"{k} {'none' if v is None else round(v)}" for k, v in c["mean_tokens"].items())
        dominated = (result["cost"]["dominated"] or {}).get(effort)
        verdict = "withheld" if dominated is None else dominated["verdict"] + (
            f" by {dominated['by']}" if dominated["by"] else "")
        lines.append(f"| {effort} | {c['observations']} | {_money(c['mean_usd'])} | "
                     f"{_money(c['mean_minutes'], '')} | {tokens} | {c['starts']} | {_money(c['usd_all_starts'])} | "
                     f"{c['successes']} | {_money(c['usd_per_success'])} | {verdict} |")
    return lines + [""]


def _graded_section(result):
    lines = ["## Graded outcome (secondary; printed beside k of n, it enters no rule)", ""]
    for task, graded in result["graded"].items():
        if isinstance(graded, str):
            lines.append(f"- {task}: {graded}")
            continue
        lines.append(f"- {task}: " + "; ".join(f"{e} {g['passed']} of {g['total']} sub-tests over "
                                               f"{g['observations']} observations" for e, g in graded.items()))
    return lines + [""]


def _allowance_section(result):
    allowance = result["allowance"]
    lines = ["## Allowance (a report tied to this account's plan; it enters no rule)", ""]
    if allowance is None:
        return lines + ["No meter readings in the export.", ""]
    per = "none" if allowance["points_per_usd"] is None else f"{allowance['points_per_usd']:.3f}"
    return lines + [f"{allowance['weekly_points']} points of a weekly allowance in all, over "
                    f"{_money(allowance['usd'])} of priced usage: {per} points per priced dollar "
                    f"(readings: {allowance['readings']}).", ""]


def render(result):
    """The readout as Markdown, from compute's result alone."""
    return "\n".join(_header(result) + _tasks_table(result) + _effort_section(result) + _cost_section(result)
                     + _graded_section(result) + _listed_section(result["listed"]) + _earlier_section(result)
                     + _allowance_section(result))


# ---- family.json (the plan's step 7): from compute's result alone -------------------------------------------------

def _plain(value):
    """compute's values as JSON: exact p values as fractions written out ("1/64"), tuples as lists."""
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value) if isinstance(value, Fraction) else value


def family(result, criterion_sha256, tasks_doc):
    """family.json's content: the criterion's SHA-256, the configuration and its label, each task with its digests,
    counts and labels by effort and its band effort, grouped by pooled label, and the effort verdict with the bound.

    Only from a complete readout (the tranche ended) that did not end in a stop. A pure function of its arguments.
    """
    # Open ruling R1: the plan's headline has family.json name "the stop that prevented it"; the brief writes none.
    if result["end"] is None or result["stop"]:
        state = "is in progress" if result["end"] is None else f"ended in a stop ({result['end']['cause']})"
        raise ReadoutError(f"family.json is written only from a complete readout that did not end in a stop; this "
                           f"one {state}")
    digests = {t["name"].split("/", 1)[-1]: {key: t[key] for key in DIGESTS} for t in tasks_doc["tasks"]}
    grouped = {label: [] for label in POOLED_LABELS}
    for task, placed in result["tasks"].items():
        if task not in digests:
            raise ReadoutError(f"family.json: task {task!r} has no digests in tasks.json")
        grouped[placed["pooled"]["label"]].append({"task": task, "digests": digests[task]} | placed)
    effort = {key: value for key, value in result["effort"].items() if key != "per_task"}
    return _plain({"rehearsal": result["rehearsal"], "criterion_sha256": criterion_sha256, "label": result["label"],
                   "configuration": result["configuration"], "end": result["end"]["by"], "tasks": grouped,
                   "effort": effort, "fall_bound_rule": result["rules"]["fall_bound"]["rule"]})


def family_bytes(content):
    """family.json's bytes: sorted keys, so the same records give the same bytes."""
    return (json.dumps(content, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


# ---- The command --------------------------------------------------------------------------------------------------

def _sha256_of(data):
    return hashlib.sha256(data).hexdigest()


def bound(ladder_bytes, manifest_bytes, label):
    """A final readout applies the criterion of its label: the label is the manifest's SHA-256 (D7.6), and the
    manifest holds the SHA-256 of the ladder.json read. None, or a ReadoutError naming which does not hold."""
    if _sha256_of(manifest_bytes) != label:
        raise ReadoutError(f"the label is not this manifest's SHA-256: {label} against {_sha256_of(manifest_bytes)}")
    recorded = json.loads(manifest_bytes)["files"].get(LADDER_PATH)
    if recorded != _sha256_of(ladder_bytes):
        raise ReadoutError(f"ladder.json is not the manifest's: {_sha256_of(ladder_bytes)} against {recorded}")


def _run(args):
    """Refuses before printing or writing anything: a pending field, a record, the label's criterion, family.json."""
    ladder_bytes, export = (KIT / "ladder.json").read_bytes(), json.loads(Path(args.export).read_text())
    standins = json.loads(Path(args.rehearsal).read_text()) if args.rehearsal else None
    result = compute(json.loads(ladder_bytes), export, standins)
    if standins is None:
        bound(ladder_bytes, (KIT / "manifest.json").read_bytes(), result["label"])
    content = family(result, _sha256_of(ladder_bytes), json.loads((KIT / "tasks.json").read_text())) if (
        args.family) else None
    print(render(result))
    if content is not None:
        Path(args.family).write_bytes(family_bytes(content))


def main(argv):
    parser = argparse.ArgumentParser(description="The long-horizon readout (plan D6): prints the readout as "
                                     "Markdown; with --family, writes family.json from a complete, non-stop readout.")
    parser.add_argument("export", help="the launcher's export (the record shape in this module's docstring)")
    parser.add_argument("--rehearsal", metavar="STAND_INS", help="a JSON object of stand-in values for every "
                        "pending readout field; stamps every output as a rehearsal")
    parser.add_argument("--family", metavar="PATH", help="where to write family.json")
    args = parser.parse_args(argv)
    try:
        _run(args)
    except ReadoutError as error:
        print(f"readout.py: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
