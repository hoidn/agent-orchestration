"""The long-horizon readout (plan docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md, D6 and Task 6).

Standard library only, so it runs under `python -I` like the rest of the kit.
"""

import math
import random
from collections import defaultdict
from fractions import Fraction


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
    return "screened in" if k in rule["screened_in_k"] else "above"


def pooled_label(K, n, rule):
    """D6's pooled label of a task, K successes of its n observations, under ladder.json's readout.pooled rule."""
    if n == 0:
        return "no observation"
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
        raise ReadoutError(f"a band effort is defined only for a screened-in task; this one is not screened in: {cells}")
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
