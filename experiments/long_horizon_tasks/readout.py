"""The long-horizon readout (plan docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md, D6 and Task 6).

Standard library only, so it runs under `python -I` like the rest of the kit.
"""

import math
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
