"""The long-horizon readout (plan docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md, D6 and Task 6).

Standard library only, so it runs under `python -I` like the rest of the kit.
"""

import math


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
