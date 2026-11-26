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
`fractions.Fraction` means, every figure compared with a line must be an int or a Fraction (`exact` refuses a float;
priced USD, a measurement, is taken at its exact value), and `TAU_Q`, `COST_LIMIT`,
`COMPLETION` and `DISTINCTIVE` are Fractions, so a figure exactly at a line meets it. `bootstrap` and the
dominance test stay in floats (display only; `pareto.dominates` takes int or float tolerances); callers convert
Fractions to floats for JSON and display (`readout.plain`).

Step 3's per-run rules read runs' `study.json` facts (`outcome`, `calls`, `visible`, `incident`, `cut`), plus
`excluded` (`pool.pool_runs`' reason a run is not pooled: contaminated or a model-policy hit) and, for parity, the
caller's `score` (the selected judge's, 0 for a failed run): `observed` (the runs that count), `completes` and
`completion` (rule 1), `visible_power` (the 20% rule), `parity` (rule 6), `distinctive` (rule 5). `rules` compares
an arm with direct on the tasks they share that have a baseline (`compared`), `cost_basis` switches the cost from
calls to priced tokens on nested sessions or a difference of model or effort, and `extension_eligible` names an arm
near rule 2's or rule 3's line.
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
VISIBLE_POWER, NESTED, EXTENSION = Fraction(1, 5), Fraction(1, 10), Fraction(1, 4)
PARITY_CALLS, PARITY_SCORE = Fraction(1, 2), Fraction(3, 2)
RETRY = "retry_until_check"
# the physical call at which each workflow's distinctive step runs, read from its program: retry's second attempt
# and implement-check-repair's first repair are its second call; implement-review-revise's revision is its third
DISTINCTIVE_CALLS = {RETRY: 2, "implement_check_repair": 2, "implement_review_revise": 3}
MAX_PROGRAM_LINES = 50  # a seed program has fewer physical lines than this
COMMON_TYPES = ("Change", "CheckReport", "Outcome")  # all common.orc may define: the seeds' shared interface


def program_lines(path):
    """Physical lines of a program file: every line, blank and comment lines included."""
    return len(Path(path).read_bytes().splitlines())


def common_definitions(path):
    """The names common.orc defines with a `def...` form (its module name aside)."""
    return sorted(re.findall(r"\(def(?!module)\w+\s+([^\s()]+)", Path(path).read_text()))


def exact(value, field):
    """`value` when it is an int or a Fraction; anything else (a float) is refused, naming `field`, since a figure
    compared with a line must be exact."""
    if not isinstance(value, (int, Fraction)):
        raise SystemExit(f"{field} is {value!r}: a figure compared with a threshold must be an int or a Fraction")
    return value


def mean(values, field="a mean's input"):
    """The exact mean of whole numbers or Fractions (`gates.mean`); a float is refused (`exact`)."""
    return gates.mean(exact(v, field) for v in values)


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


def observed(runs):
    """The runs that count toward a share: neither an incident, nor cut by a usage limit (no observation, ruling
    R1), nor excluded from pooling as contaminated or a model-policy hit."""
    return [r for r in runs if "incident" not in r and "cut" not in r and not r.get("excluded")]


def completes(facts):
    """Rule 1's and parity's "complete" (coordinator decision on what completes): the program ran to its end
    (outcome `completed`, a `BLOCKED` result included); a run cut at its call limit or past its wall clock
    (outcome `failed`) does not."""
    return facts["outcome"] == "completed"


def share(runs, test):
    """The exact share of the observed `runs` for which `test(facts)` holds; refuses when none is observed."""
    seen = observed(runs)
    if not seen:
        raise SystemExit("no observed run: the share is undefined")
    return Fraction(sum(bool(test(r)) for r in seen), len(seen))


def completion(runs):
    """Rule 1's figure: the share of an arm's observed runs that complete (a call-limit cut stays in, failed)."""
    return share(runs, completes)


def distinctive(name, runs):
    """Rule 5's figure: the share of arm `name`'s observed runs whose physical calls reached its distinctive step
    (`DISTINCTIVE_CALLS`); a run cut on that call counts, since its call count includes it."""
    return share(runs, lambda r: r["calls"] >= DISTINCTIVE_CALLS[name])


def visible_power(direct_runs):
    """The 20% rule after the direct stage (coordinator decision on what counts as "the visible check failed"):
    over the observed direct runs that completed and whose final patch the host visible check ran on and finished
    (a call-limit cut, a failed run without a patch and a check past its bound are in neither count), the share whose
    check did not pass. `launch` (parity runs and implement-check-repair start) when that rate is at least
    `VISIBLE_POWER`; under it they are withheld. The counts go with the rate."""
    ran = [r for r in observed(direct_runs) if completes(r) and "visible" in r and not r["visible"].get("timed_out")]
    if not ran:
        raise SystemExit("no direct run's patch was checked: the visible check's selecting power is undefined")
    failed = sum(r["visible"]["passed"] is not True for r in ran)
    rate = Fraction(failed, len(ran))
    return {"failed": failed, "checked": len(ran), "rate": rate, "launch": rate >= VISIBLE_POWER}


def parity(runs, baseline):
    """Rule 6, retry parity (coordinator decision on the parity's offline figure: `Q3` and `Q3_calls`). `runs` are
    the retry arm's run facts with their `score`; `baseline` is `baselines` over the seed evaluation's direct runs.
    Over the tasks of the observed retry runs: every one completes, every task has a baseline (three usable direct
    runs), and the mean over tasks of the per-task mean calls and score are within `PARITY_CALLS` and
    `PARITY_SCORE` of the mean `Q3_calls` and `Q3` of those tasks. A task without a baseline fails the rule and is
    listed in `no_baseline`; with no observed run on a task that has one, the figures are None and the rule fails."""
    seen = observed(runs)
    tasks = list(dict.fromkeys(r["task"] for r in seen))
    rated = [t for t in tasks if t in baseline["tasks"]]
    out = {"no_baseline": [t for t in tasks if t not in baseline["tasks"]], "completes": all(map(completes, seen)),
           "calls": None, "score": None, "offline_calls": None, "offline_score": None, "passed": False}
    if not rated:
        return out

    def live(key):
        return mean((mean((r[key] for r in seen if r["task"] == t), key) for t in rated), key)

    out |= {"calls": live("calls"), "score": live("score"),
            "offline_calls": mean(baseline["tasks"][t]["Q3_calls"] for t in rated),
            "offline_score": mean(baseline["tasks"][t]["Q3"] for t in rated)}
    out["passed"] = not out["no_baseline"] and out["completes"] \
        and abs(out["calls"] - out["offline_calls"]) <= PARITY_CALLS \
        and abs(out["score"] - out["offline_score"]) <= PARITY_SCORE
    return out


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
    return min(3, max(1, math.floor(exact(calls, "calls") + Fraction(1, 2))))


def compared(arm, direct, rerolled):
    """(tasks, left out): rules 2 and 3 compare an arm with direct on the tasks they share that have a baseline in
    `rerolled["tasks"]`, i.e. at least three usable direct runs (coordinator decision on rules 2 and 3 for an arm run
    on fewer tasks than direct); a shared task without one is left out of both rules and listed."""
    shared = [t for t in direct["tasks"] if t in arm["tasks"]]
    return [t for t in shared if t in rerolled["tasks"]], [t for t in shared if t not in rerolled["tasks"]]


def lines(name, arm, direct, rerolled):
    """(q, rule 2's line, rule 3's line) over the `compared` tasks: q the arm's mean, rule 2's line direct's mean less
    `TAU_Q`, rule 3's `Q(k)` less `TAU_Q` (`Q(1)` is direct's mean; None for retry, where rule 3 is vacuous). All
    None when no task is compared."""
    tasks, _ = compared(arm, direct, rerolled)
    if not tasks:
        return None, None, None
    q, q_direct = mean((arm["tasks"][t] for t in tasks), "tasks"), mean((direct["tasks"][t] for t in tasks), "tasks")
    k = calls_k(arm["calls"])
    if name == RETRY:
        return q, q_direct - TAU_Q, None
    offline = q_direct if k == 1 else mean(rerolled["tasks"][t][f"Q{k}"] for t in tasks)
    return q, q_direct - TAU_Q, offline - TAU_Q


def cost_basis(arm, direct):
    """The summary key the arm's cost compares on with direct's (plan Step 3, "Quality and cost"): "calls" (mean
    provider calls per run), or "priced_worst" (priced tokens per run, a cut call at the per-call worst case, so a
    cut's consumption counts) when nested sessions are in over `NESTED` of either arm's runs (a comparison uses both
    arms' calls, and a nested session's calls are uncounted) or the two arms differ in model or effort (calls are a
    cost only at one model and one effort)."""
    nested = max(exact(arm["nested"], "nested"), exact(direct["nested"], "nested"))
    same = (arm["model"], arm["effort"]) == (direct["model"], direct["effort"])
    return "calls" if same and nested <= NESTED else "priced_worst"


def within_cost(value, reference):
    """Rule 4's limit on one cost figure (vacuous when either side has none); priced USD is a measurement and is
    taken at its exact value."""
    return value is None or reference is None or Fraction(value) <= COST_LIMIT * Fraction(reference)


def rules(name, arm, direct, rerolled):
    """Rules 1-7 for one arm against direct (the module docstring; `select_seeds` names the summary's keys). Rule 4's
    priced half holds at both bounds (coordinator decision on priced tokens with cut calls): `priced_worst` and
    `priced_metered` (metered runs only), each where both arms have it; its calls half applies on the "calls" basis
    only. On a priced basis an arm without `priced_worst` is refused."""
    q, line, rolled_line = lines(name, arm, direct, rerolled)
    basis = cost_basis(arm, direct)
    if basis != "calls" and None in (arm["priced_worst"], direct["priced_worst"]):
        raise SystemExit(f"{name}: its cost compares on priced tokens, and an arm has no priced figure")
    calls = basis != "calls" or exact(arm["calls"], "calls") <= COST_LIMIT * exact(direct["calls"], "calls")
    return {
        "1_completes": exact(arm["completed"], "completed") >= COMPLETION,
        "2_quality": q is not None and q >= line,
        "3_reroll": name == RETRY or (q is not None and q >= rolled_line),
        "4_cost": calls and all(within_cost(arm[key], direct[key]) for key in ("priced_worst", "priced_metered")),
        "5_distinctive": exact(arm["distinctive"], "distinctive") >= DISTINCTIVE,
        "6_parity": name != RETRY or arm.get("parity") is True,
        "7_lines": arm["lines"] < MAX_PROGRAM_LINES,
    }


def extension_eligible(name, arm, direct, rerolled):
    """Step 3's reserved extension: an arm whose mean is within `EXTENSION` (0.25 point, either side) of rule 2's
    line or rule 3's, on the `compared` tasks."""
    q, line, rolled_line = lines(name, arm, direct, rerolled)
    return q is not None and any(m is not None and abs(q - m) <= EXTENSION for m in (line, rolled_line))


def select_seeds(arms, rerolled):
    """`arms` maps name to {"tasks": {task: mean score}, "completed", "calls", "priced_worst", "priced_metered"
    (USD per run, None where not priced), "nested", "model", "effort", "distinctive", "parity", "lines"} (shares
    from `completion`, `distinctive` and `share`; "nested" the share of observed runs with a nested session); "direct"
    is the reference and always in the set (plan), its line count reported. `rerolled` is `baselines` over the
    direct runs. Returns the seeds and every arm's report: its rules, the `compared` tasks left out, the difference
    from direct on the compared tasks with its interval (None when none is compared), the cost basis, the dominance
    test against direct on that basis (in floats) and whether the reserved extension applies."""
    direct = arms["direct"]
    reports, seeds = {"direct": {"lines": direct["lines"]}}, ["direct"]
    for name, arm in arms.items():
        if name == "direct":
            continue
        tasks, left_out = compared(arm, direct, rerolled)
        checked, basis = rules(name, arm, direct, rerolled), cost_basis(arm, direct)
        reports[name] = {"rules": checked, "lines": arm["lines"], "left_out": left_out, "cost_basis": basis,
                         "difference": None, "interval": None, "spans_tolerance": None, "dominated_by_direct": None,
                         "extension_eligible": extension_eligible(name, arm, direct, rerolled)}
        if tasks:
            differences = [arm["tasks"][t] - direct["tasks"][t] for t in tasks]
            low, high = bootstrap(differences)
            quality = {"quality": float(mean(arm["tasks"][t] for t in tasks)), "cost": float(arm[basis])}
            reference = {"quality": float(mean(direct["tasks"][t] for t in tasks)), "cost": float(direct[basis])}
            reports[name] |= {"difference": mean(differences), "interval": [low, high],
                              "spans_tolerance": low < -TAU_Q < high,  # float against Fraction: Python compares exactly
                              "dominated_by_direct": dominates(reference, quality, float(TAU_Q), TAU_C)}
        if all(checked.values()):
            seeds.append(name)
    return {"seeds": seeds, "arms": reports}
