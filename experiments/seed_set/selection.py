"""Offline re-roll baselines and the frozen seed selection rule of the seed-set plan (Step 3), as pure functions.

`rerolls` takes one task's direct runs as (judged score, visible check passed) pairs, a failed run being (0,
False), and averages over every ordered triple of them: `Q1` is the direct mean; `Qk` (k = 2, 3) retries until
the visible check passes, at most k attempts, keeping the passing attempt or else the k-th (best-of-k by the
visible check has the same quality at k calls); `random_of_3` keeps a random one; `any_of_3` the best judged one
(an upper bound). `select_seeds` applies rules 1-6 to per-arm summaries and reports each arm's difference from
direct with a 90% bootstrap interval over tasks and the driver's dominance test against direct. Rule 7 (owner,
2026-11-11) bounds a seed's size: its program file has fewer than `MAX_PROGRAM_LINES` physical lines, every line
counted (code, comments, blank lines); the shared `common.orc` is exempt but frozen (`common_definitions`).

Every comparison with a threshold is exact (coordinator decision on floats in this module: exact Fractions, as the
kit's ruling on B1, 2026-11-12, requires): `rerolls` and `baselines` take whole-number scores and return
`fractions.Fraction` means, `rules` reads its summaries' figures at their exact values, and `TAU_Q`, `COST_LIMIT`,
`COMPLETION` and `DISTINCTIVE` are Fractions, so a figure exactly at a line meets it. `bootstrap` and the
dominance test stay in floats (display only; `pareto.dominates` takes int or float tolerances); callers convert
Fractions to floats for JSON and display (`readout.plain`).
"""

import math
import random
import re
from fractions import Fraction
from itertools import permutations
from pathlib import Path
from statistics import mean as float_mean

from experiments.orc_structural_search.pareto import dominates
from experiments.seed_set import gates

TAU_Q, TAU_C = Fraction(1, 2), 0.10  # TAU_C only enters the dominance test, which is in floats
COST_LIMIT, COMPLETION, DISTINCTIVE = Fraction(3), Fraction(95, 100), Fraction(1, 5)
RETRY = "retry_until_check"
MAX_PROGRAM_LINES = 50  # a seed program has fewer physical lines than this
COMMON_TYPES = ("Change", "CheckReport", "Outcome")  # all common.orc may define: the seeds' shared interface


def program_lines(path):
    """Physical lines of a program file: every line, blank and comment lines included."""
    return len(Path(path).read_bytes().splitlines())


def common_definitions(path):
    """The names common.orc defines with a `def...` form (its module name aside)."""
    return sorted(re.findall(r"\(def(?!module)\w+\s+([^\s()]+)", Path(path).read_text()))


def mean(values):
    """The exact mean of whole numbers, Fractions or floats (a float at its exact binary value)."""
    return gates.mean(Fraction(v) for v in values)


def _retry(triple, k):
    for attempt, (value, passed) in enumerate(triple[:k], 1):
        if passed:
            return value, attempt
    return triple[k - 1][0], k


def rerolls(runs):
    """One task's re-roll baselines from its direct runs, (whole-number judged score, visible check passed) pairs:
    exact Fraction means over every ordered triple (the module docstring)."""
    if len(runs) < 3:
        raise SystemExit(f"re-roll baselines need at least three direct runs per task, not {len(runs)}")
    triples = list(permutations(runs, 3))
    out = {"Q1": mean(value for value, _ in runs), "Q1_calls": 1,
           "visible_fail_rate": Fraction(sum(not passed for _, passed in runs), len(runs)),
           "random_of_3": mean(mean(value for value, _ in t) for t in triples),
           "any_of_3": mean(max(value for value, _ in t) for t in triples)}
    for k in (2, 3):
        picked = [_retry(t, k) for t in triples]
        out[f"Q{k}"], out[f"Q{k}_calls"] = mean(v for v, _ in picked), mean(c for _, c in picked)
    return out


def baselines(per_task):
    """Means over tasks of each task's `rerolls`; `per_task` maps task to its direct (score, visible) runs."""
    rows = {task: rerolls(runs) for task, runs in per_task.items()}
    return {"tasks": rows, **{key: mean(row[key] for row in rows.values()) for key in next(iter(rows.values()))}}


def bootstrap(differences, resamples=10000, seed=20261111, level=0.90):
    """Percentile interval of the mean of per-task differences, resampling tasks with replacement; in floats
    (display only), exact differences converted first."""
    differences = [float(d) for d in differences]
    rng, n = random.Random(seed), len(differences)
    means = sorted(float_mean(rng.choices(differences, k=n)) for _ in range(resamples))
    tail = (1 - level) / 2
    return means[math.floor(tail * resamples)], means[math.ceil((1 - tail) * resamples) - 1]


def calls_k(calls):
    """An arm's mean calls rounded to 1, 2 or 3, halves up."""
    return min(3, max(1, math.floor(Fraction(calls) + Fraction(1, 2))))


def rules(name, arm, direct, rerolled):
    q, q_direct = mean(arm["tasks"].values()), mean(direct["tasks"].values())
    k = calls_k(arm["calls"])
    tokens = arm.get("tokens") is None or direct.get("tokens") is None or \
        Fraction(arm["tokens"]) <= COST_LIMIT * Fraction(direct["tokens"])
    return {
        "1_completes": Fraction(arm["completed"]) >= COMPLETION,
        "2_quality": q >= q_direct - TAU_Q,
        "3_reroll": name == RETRY or q >= (q_direct if k == 1 else rerolled[f"Q{k}"]) - TAU_Q,
        "4_cost": Fraction(arm["calls"]) <= COST_LIMIT * Fraction(direct["calls"]) and tokens,
        "5_distinctive": Fraction(arm.get("distinctive") or 0) >= DISTINCTIVE,
        "6_parity": name != RETRY or arm.get("parity") is True,
        "7_lines": arm["lines"] < MAX_PROGRAM_LINES,
    }


def select_seeds(arms, rerolled):
    """`arms` maps name to {"tasks": {task: mean score}, "completed", "calls", "tokens" or None, "distinctive",
    "parity", "lines"}; "direct" is the reference and always in the set (plan), its line count reported. Returns
    the seeds and every arm's report."""
    direct = arms["direct"]
    reports, seeds = {"direct": {"lines": direct["lines"]}}, ["direct"]
    for name, arm in arms.items():
        if name == "direct":
            continue
        shared = sorted(set(arm["tasks"]) & set(direct["tasks"]))
        differences = [arm["tasks"][t] - direct["tasks"][t] for t in shared]
        low, high = bootstrap(differences)
        checked = rules(name, arm, direct, rerolled)
        quality = {"quality": float(mean(arm["tasks"].values())), "cost": float(arm["calls"])}
        reference = {"quality": float(mean(direct["tasks"].values())), "cost": float(direct["calls"])}
        reports[name] = {"rules": checked, "lines": arm["lines"], "difference": mean(differences), "interval": [low, high],
                         "spans_tolerance": low < -TAU_Q < high,
                         "dominated_by_direct": dominates(reference, quality, float(TAU_Q), TAU_C)}
        if all(checked.values()):
            seeds.append(name)
    return {"seeds": seeds, "arms": reports}
