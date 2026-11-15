"""The long-horizon readout (plan docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md, D6 and Task 6).

From the launcher's export to the readout of D6 and to `family.json` (the plan's step 7). The export's layout, and
the loader that refuses a record that does not fit it, are `slot_record.py`'s: one definition for the launcher and
the readout. Every rule and threshold is read from `ladder.json` (its `readout`, `classification`, `attempt` and
`schedule` groups). Every figure is computed once, by `compute`, from the starts joined to the schedule's slots by
slot id; `render` and `family` only format what `compute` returned. Standard library only, so it runs under
`python -I` like the rest of the kit.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import random
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

KIT = Path(__file__).resolve().parent
LADDER_PATH = "experiments/long_horizon_tasks/ladder.json"
POOLED_LABELS = ("screened in", "floor", "above the band")
NOT_SCREENED = "not screened"
DIGESTS = ("digest_4_1_0", "environment_image", "verifier_image", "overlay_digest")


def _kit(name):
    """A kit module by its path: under `python -I` the script's directory is not on the import path."""
    spec = importlib.util.spec_from_file_location(f"lh_{name}", KIT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


slot_record = _kit("slot_record")


class ReadoutError(ValueError):
    """A rule or a request the readout refuses; the message names it (a record that does not fit is a
    slot_record.RecordError)."""


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
    """D6's pooled label of a task, K successes of its n observations, under ladder.json's readout.pooled rule.

    The screen is applied only at the planned count, readout.pooled.at_n (coordinator ruling R4); with fewer the task
    is not screened, neither in nor out of the family.
    """
    if n != rule["at_n"]:
        return f"{NOT_SCREENED}: {n} of {rule['at_n']} attempts"
    if K == rule["floor_K"]:
        return "floor"
    band = rule["screened_in"]
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

    The method ladder.json freezes in readout.fall_bound (generator, order, resample_fall, quantile; ruling R5): a
    bootstrap over tasks, rule["resamples"] resamples drawn by random.Random(rule["seed"]) with the tasks in name
    order; the bound is the ceil(rule["one_sided"] x resamples)-th smallest resampled fall. None when no task has a
    complete triple.
    """
    rows = [(tasks[task]["triples"], tasks[task]["successes"][low] - tasks[task]["successes"][high])
            for task in sorted(tasks)]
    if not rows:
        return None
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


def _placement(cells, rules, place, drops):
    """Per task: the cells and the pooled count; when place, their labels and the band effort (D6), or the reason a
    dropped task was dropped (ruling R4)."""
    level = rules["interval"]["level"]
    placed = {}
    for task, by_effort in cells.items():
        K, n = sum(c["k"] for c in by_effort.values()), sum(c["n"] for c in by_effort.values())
        placed[task] = {"cells": by_effort, "pooled": {"K": K, "n": n, "interval": interval(K, n, level)},
                        "band_effort": None}
        if place:
            placed[task] = _placed(placed[task], rules, drops.get(task))
    return placed


def _placed(task, rules, dropped):
    pooled = task["pooled"] | {"label": pooled_label(task["pooled"]["K"], task["pooled"]["n"], rules["pooled"])}
    if dropped:
        pooled |= {"label": "dropped", "reason": dropped}
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
    return {"exclusions": [_entry(s) | {"reason": s["excluded"] or s["ending"], "contamination": s["contamination"]}
                           for s in starts if not s["counted"]],
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
            "mean_tokens": {kind: _mean([s["tokens"][kind] for s in observations])
                            for kind in slot_record.TOKEN_KINDS}}


def _level_cost(starts, effort, classes):
    """D6's cost of one effort level: means per observation; every start's cost over the level's successes."""
    observations = [s for s in starts if s["effort"] == effort and s["counted"]]
    started = [s for s in starts if s["effort"] == effort and classes[s["class"]]["starts"]]
    successes, usd = sum(s["success"] for s in observations), sum(s["usd"] for s in started)
    return {"observations": len(observations)} | _means(observations) | {
        "starts": len(started), "usd_all_starts": usd, "successes": successes,
        "usd_per_success": usd / successes if successes else None}


def _beats(other, effort, per_effort, triples, rule):
    """Whether other beats effort on the sign-flip test at readout.cost.dominated_p_at_most and has a lower mean
    cost (D6; coordinator ruling R3)."""
    difference = _difference(triples, other, effort)
    mine, theirs = per_effort[effort]["mean_usd"], per_effort[other]["mean_usd"]
    cheaper = None not in (mine, theirs) and theirs < mine
    return difference["sum"] > 0 and difference["p_above"] <= Fraction(str(rule["dominated_p_at_most"])) and cheaper


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
    rule = ladder["readout"]["cost"]
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


def _effort(triples, efforts, rules, place):
    """The effort test; after a stop only the bound on the fall, which D6 always reports and which places nothing
    (coordinator ruling R2, 2026-11-14), over the complete triples there are."""
    if place:
        return effort_test(triples, efforts, rules) | {"per_task": triples}
    return {"tasks": len(triples), "triples": sum(task["triples"] for task in triples.values()),
            "fall_bound": fall_bound(triples, efforts[0], efforts[-1], rules["fall_bound"]), "per_task": triples}


def _earlier(starts, export, tasks, efforts, level):
    """Per earlier label: its ledger row, its cells (k of n, no label) and its lists; they enter no rule (D6)."""
    earlier = []
    for entry in export["earlier_labels"]:
        own = [s for s in starts if s["label"] == entry["label"]]
        earlier.append(entry | {"cells": _counts(own, tasks, efforts, level), "listed": _listed(own, efforts)})
    return earlier


def _drops(dropped, tasks):
    """{task: reason} from the coordinator's drops (ruling R4): each names a task of the tranche once, with a reason."""
    reasons = {}
    for entry in dropped or []:
        slot_record.fields(entry, {"task": str, "reason": str}, "a dropped task")
        if entry["task"] not in tasks:
            raise ReadoutError(f"dropped task {entry['task']!r} is not a task of the tranche")
        if entry["task"] in reasons:
            raise ReadoutError(f"dropped task {entry['task']!r} is given twice")
        if not entry["reason"].strip():
            raise ReadoutError(f"dropped task {entry['task']!r} names no reason")
        reasons[entry["task"]] = entry["reason"]
    return reasons


def compute(ladder, export, standins=None, dropped=None):
    """Every figure of the readout, from the export's starts joined by slot id; rules read from ladder.json.

    dropped lists the tasks the coordinator dropped, each {"task", "reason"} with its ledger row (ruling R4).

    Every rule reads the current label's starts alone. A readout that ends in a stop places nothing: no cell or
    pooled label, no band effort, no effort verdict and no dominance (D6); it keeps the bound on the fall (R2).
    """
    criterion, rehearsal = _criterion(ladder, standins)
    starts = slot_record.load(export, criterion)
    efforts, rules = criterion["attempt"]["efforts"], criterion["readout"]
    in_tranche = {slot["task"] for slot in export["slots"]}
    tasks = [task["name"] for task in criterion["tasks"]["list"] if task["name"] in in_tranche]
    level = rules["interval"]["level"]
    current = [start for start in starts if start["label"] == export["label"]]
    triples = _triples(current, efforts)
    # D6: a readout that ends in a stop places nothing; it still reports the bound on the fall (ruling R2).
    place = export["end"] is None or export["end"]["by"] != "stop"
    return {"rehearsal": rehearsal, "configuration": _configuration(criterion), "label": export["label"],
            "end": export["end"], "stop": not place,
            "tasks": _placement(_counts(current, tasks, efforts, level), rules, place, _drops(dropped, tasks)),
            "effort": _effort(triples, efforts, rules, place),
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
        reason = f" ({pooled['reason']})" if "reason" in pooled else ""
        cells = [_labelled(placed["cells"][e]) for e in efforts] + [_labelled(pooled, "K") + screened + reason]
        lines.append(f"| {task} | " + " | ".join(cells) + f" | {'withheld' if result['stop'] else banded} |")
    return lines + [""]


def _fraction(p):
    return f"{p} ({float(p):.4f})"


def _bound_text(result):
    effort, rule, efforts = result["effort"], result["rules"]["fall_bound"], result["configuration"]["efforts"]
    method = (f"one-sided {rule['one_sided']:.0%} upper bound on the pooled fall from {efforts[0]} to {efforts[-1]}, "
              f"bootstrap over tasks, {rule['resamples']} resamples, seed {rule['seed']}")
    bound = "none: no complete triple" if effort["fall_bound"] is None else f"{effort['fall_bound']:.1f} points"
    return f"{bound} ({method})"


def _effort_section(result):
    effort, rule = result["effort"], result["rules"]["fall_bound"]
    lines = ["## Effort test (complete triples of the current label)", ""]
    if result["stop"]:
        if effort["triples"] == 0:
            return lines + ["There is no complete triple, so there is no bound on the fall; no placement is made. "
                            f"{result['rules']['stop_readout'].capitalize()} (D6).", ""]
        return lines + [f"Bound on the fall over {effort['triples']} complete triples; no placement is made: "
                        f"{_bound_text(result)}. {result['rules']['stop_readout'].capitalize()} (D6).", ""]
    lines += [f"Complete triples: {effort['triples']} over {effort['tasks']} tasks. Pooled successes: " +
              ", ".join(f"{e} {s} of {effort['triples']}" for e, s in effort["pooled"].items()) + ".", "",
              "| Difference | Sum of d_i | p, sum at or below | p, sum at or above |", "| --- | --- | --- | --- |"]
    for name, d in effort["differences"].items():
        lines.append(f"| {name} | {d['sum']} | {_fraction(d['p_below'])} | {_fraction(d['p_above'])} |")
    return lines + ["", f"**Verdict: {effort['verdict']}.** Bound on the fall: {_bound_text(result)}. {rule['rule']}",
                    ""]


def _excluded(entry):
    """Why a start enters no k or n; a contaminated one by the SHA-256 of each term found, never the term (D6)."""
    found = entry["contamination"]
    return entry["reason"] + (f" (terms by SHA-256: {', '.join(found)})" if found else "")


def _refused(entry):
    return ", ".join(f"{address}: {count}" for address, count in sorted(entry["refused"].items()))


def _entries(title, entries, why=None):
    lines = [f"### {title}", ""]
    for e in entries:
        lines.append(f"- start {e['start']}, {e['task']} {e['effort']} round {e['round']}, row {e['row']} "
                     f"({e['class']})" + (f": {why(e)}" if why else ""))
    return lines + (["- none"] if not entries else []) + [""]


def _listed_section(listed):
    return (["## Listed", ""] + _entries("Exclusions (enter no k or n)", listed["exclusions"], _excluded)
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
        lines += [""] + _entries("Exclusions under this label", earlier["listed"]["exclusions"], _excluded)
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


def _writable(result):
    """Why family.json cannot be written from this readout, or None (rulings R1 and R4)."""
    # Ruling R1: after a stop no family.json is written; the stop readout names the stop.
    if result["end"] is None or result["stop"]:
        state = "is in progress" if result["end"] is None else f"ended in a stop ({result['end']['cause']})"
        return f"family.json is written only from a complete readout that did not end in a stop; this one {state}"
    unscreened = [task for task, placed in result["tasks"].items()
                  if placed["pooled"]["label"].startswith(NOT_SCREENED)]
    if unscreened:
        return (f"family.json is written only when every task is screened at the planned count or recorded as dropped "
                f"for a stated reason (ruling R4); not screened: {', '.join(unscreened)}")
    return None


def family(result, criterion_sha256, tasks_doc):
    """family.json's content: the criterion's SHA-256, the configuration and its label, each task with its digests,
    counts and labels by effort and its band effort, grouped by pooled label (a dropped task with its reason), and the
    effort verdict with the bound.

    Only from a complete readout (the tranche ended) that did not end in a stop, with every task screened at the
    planned count or dropped. A pure function of its arguments.
    """
    refusal = _writable(result)
    if refusal:
        raise ReadoutError(refusal)
    digests = {t["name"].split("/", 1)[-1]: {key: t[key] for key in DIGESTS} for t in tasks_doc["tasks"]}
    grouped = {label: [] for label in (*POOLED_LABELS, "dropped")}
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
    dropped = json.loads(Path(args.dropped).read_text()) if args.dropped else None
    result = compute(json.loads(ladder_bytes), export, standins, dropped)
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
    parser.add_argument("--dropped", metavar="DROPS", help="a JSON list of the tasks the coordinator dropped, each "
                        "{\"task\", \"reason\"} naming its ledger row (ruling R4)")
    parser.add_argument("--family", metavar="PATH", help="where to write family.json")
    args = parser.parse_args(argv)
    try:
        _run(args)
    except (ReadoutError, slot_record.RecordError) as error:
        print(f"readout.py: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
