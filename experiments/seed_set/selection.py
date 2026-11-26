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

Step 3's per-run rules read runs' `study.json` facts (`outcome`, `calls`, `visible`, `incident`, `cut`), plus
`excluded` (`pool.pool_runs`' reason a run is not pooled: contaminated or a model-policy hit) and, for parity, the
caller's `score` (the selected judge's, 0 for a failed run): `observed` (the runs that count), `completes` and
`completion` (rule 1), `visible_power` (the 20% rule), `parity` (rule 6), `distinctive` (rule 5). `rules` compares
an arm with direct on the tasks they share, `cost_basis` switches the cost to priced tokens on nested sessions,
and `extension_eligible` names an arm near rule 2's or rule 3's line.
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
    """The 20% rule after the direct stage (coordinator decision on what counts as "the visible check failed",
    as corrected after review): over the observed direct runs that completed and whose final patch the host visible
    check ran on and finished (a call-limit cut, a failed run without a patch and a check past its bound are in
    neither count), the share whose check did not pass. `launch` (parity runs and implement-check-repair start) when
    that rate is at least `VISIBLE_POWER`; under it they are withheld. The counts go with the rate, for a readout
    that shows `rerolls`' `visible_fail_rate` beside it."""
    ran = [r for r in observed(direct_runs) if completes(r) and "visible" in r and not r["visible"].get("timed_out")]
    if not ran:
        raise SystemExit("no direct run's patch was checked: the visible check's selecting power is undefined")
    failed = sum(r["visible"]["passed"] is not True for r in ran)
    rate = Fraction(failed, len(ran))
    return {"failed": failed, "checked": len(ran), "rate": rate, "launch": rate >= VISIBLE_POWER}


def parity(runs, baseline):
    """Rule 6, retry parity (coordinator decision on the parity's offline figure: `Q3` and `Q3_calls`). `runs` are
    the retry arm's run facts with their `score`; `baseline` is `baselines` over the seed evaluation's direct runs.
    Over the tasks of the observed retry runs: every one completes, and the mean over tasks of the per-task mean
    calls and score are within `PARITY_CALLS` and `PARITY_SCORE` of the mean `Q3_calls` and `Q3` of those tasks.
    Refuses when no retry run is observed or a task has no baseline (fewer than three usable direct runs)."""
    seen = observed(runs)
    tasks = list(dict.fromkeys(r["task"] for r in seen))
    if not tasks:
        raise SystemExit("retry parity needs an observed retry run")
    if missing := [t for t in tasks if t not in baseline["tasks"]]:
        raise SystemExit(f"retry parity: no offline baseline (three usable direct runs) for tasks {missing}")

    def live(key):
        return mean(mean(r[key] for r in seen if r["task"] == t) for t in tasks)

    out = {"completes": all(completes(r) for r in seen), "calls": live("calls"), "score": live("score"),
           "offline_calls": mean(baseline["tasks"][t]["Q3_calls"] for t in tasks),
           "offline_score": mean(baseline["tasks"][t]["Q3"] for t in tasks)}
    out["passed"] = out["completes"] and abs(out["calls"] - out["offline_calls"]) <= PARITY_CALLS \
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
    return min(3, max(1, math.floor(Fraction(calls) + Fraction(1, 2))))


def shared_tasks(arm, direct):
    """The tasks an arm shares with direct, in direct's order; refuses when there is none."""
    shared = [t for t in direct["tasks"] if t in arm["tasks"]]
    if not shared:
        raise SystemExit("an arm shares no task with direct: nothing to compare")
    return shared


def lines(name, arm, direct, rerolled):
    """(q, rule 2's line, q', rule 3's line) on shared tasks (coordinator decision on rules 2 and 3 for an arm run on
    fewer tasks than direct: compare on the tasks it shares with direct). Rule 2: the arm's mean against direct's,
    less `TAU_Q`, over the shared tasks. Rule 3 (None, None for retry, where it is vacuous): over the shared tasks
    that have a baseline in `rerolled["tasks"]` (`baselines` holds only tasks with three usable direct runs, so a
    task with fewer is left out of rule 3 alone), the arm's mean against `Q(k)` less `TAU_Q`, `Q(1)` being direct's
    mean; refuses when no shared task has a baseline."""
    shared = shared_tasks(arm, direct)
    q, line = mean(arm["tasks"][t] for t in shared), mean(direct["tasks"][t] for t in shared) - TAU_Q
    if name == RETRY:
        return q, line, None, None
    k, rolled = calls_k(arm["calls"]), [t for t in shared if t in rerolled["tasks"]]
    if not rolled:
        raise SystemExit(f"{name}: no shared task has three usable direct runs, so rule 3 has no baseline")
    offline = mean(direct["tasks"][t] if k == 1 else rerolled["tasks"][t][f"Q{k}"] for t in rolled)
    return q, line, mean(arm["tasks"][t] for t in rolled), offline - TAU_Q


def cost_basis(arm, direct):
    """The summary key an arm's cost compares on with direct's: "tokens" (priced tokens per run) alone when nested
    sessions are in over `NESTED` of either arm's runs (`nested`, a share), else "calls" (plan Step 3, "Quality and
    cost"). Calls stay admissible only while every arm runs one model at one effort; no arm in this study's scope
    differs, so nothing here checks it."""
    return "tokens" if max(Fraction(arm["nested"]), Fraction(direct["nested"])) > NESTED else "calls"


def rules(name, arm, direct, rerolled):
    """Rules 1-7 for one arm against direct (the module docstring; `select_seeds` names the summary's keys). Rule 4
    holds on calls and, where both are metered, priced tokens; on tokens alone when `cost_basis` says so, which
    refuses an arm without metered tokens."""
    q, line, q_rolled, rolled_line = lines(name, arm, direct, rerolled)
    basis = cost_basis(arm, direct)
    if basis == "tokens" and (arm["tokens"] is None or direct["tokens"] is None):
        raise SystemExit(f"{name}: nested sessions make cost compare in tokens, and an arm has no metered tokens")

    def within(key):
        return arm[key] is None or direct[key] is None or Fraction(arm[key]) <= COST_LIMIT * Fraction(direct[key])

    return {
        "1_completes": Fraction(arm["completed"]) >= COMPLETION,
        "2_quality": q >= line,
        "3_reroll": rolled_line is None or q_rolled >= rolled_line,
        "4_cost": within("tokens") and (basis == "tokens" or within("calls")),
        "5_distinctive": Fraction(arm.get("distinctive") or 0) >= DISTINCTIVE,
        "6_parity": name != RETRY or arm.get("parity") is True,
        "7_lines": arm["lines"] < MAX_PROGRAM_LINES,
    }


def extension_eligible(name, arm, direct, rerolled):
    """Step 3's reserved extension: an arm whose mean is within `EXTENSION` (0.25 point, either side) of rule 2's
    line or rule 3's, each on that rule's tasks (`lines`)."""
    q, line, q_rolled, rolled_line = lines(name, arm, direct, rerolled)
    return abs(q - line) <= EXTENSION or (rolled_line is not None and abs(q_rolled - rolled_line) <= EXTENSION)


def select_seeds(arms, rerolled):
    """`arms` maps name to {"tasks": {task: mean score}, "completed", "calls", "tokens" or None, "nested",
    "distinctive", "parity", "lines"} (shares from `completion`, `distinctive` and `share`; "nested" the share of
    observed runs with a nested session); "direct" is the reference and always in the set (plan), its line count
    reported. `rerolled` is `baselines` over the direct runs. Returns the seeds and every arm's report: its rules,
    the difference from direct on the shared tasks with its interval, the cost basis, the dominance test against
    direct on that basis (in floats) and whether the reserved extension applies."""
    direct = arms["direct"]
    reports, seeds = {"direct": {"lines": direct["lines"]}}, ["direct"]
    for name, arm in arms.items():
        if name == "direct":
            continue
        shared = shared_tasks(arm, direct)
        differences = [arm["tasks"][t] - direct["tasks"][t] for t in shared]
        low, high = bootstrap(differences)
        checked, basis = rules(name, arm, direct, rerolled), cost_basis(arm, direct)
        quality = {"quality": float(mean(arm["tasks"][t] for t in shared)), "cost": float(arm[basis])}
        reference = {"quality": float(mean(direct["tasks"][t] for t in shared)), "cost": float(direct[basis])}
        reports[name] = {"rules": checked, "lines": arm["lines"], "difference": mean(differences), "interval": [low, high],
                         "spans_tolerance": low < -TAU_Q < high, "cost_basis": basis,
                         "dominated_by_direct": dominates(reference, quality, float(TAU_Q), TAU_C),
                         "extension_eligible": extension_eligible(name, arm, direct, rerolled)}
        if all(checked.values()):
            seeds.append(name)
    return {"seeds": seeds, "arms": reports}
