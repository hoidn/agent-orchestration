"""Judge gate (V1-V4) and task gates (G1-G4) of the seed-set calibration (plan Step 2), as pure functions.

Input is a list of records, one per pooled clone and per unrated run, built by `pool_records` from the pools'
`results.json` (the harness's clone-id join) and nothing else:

    {"task", "pool": "first"|"retest", "role": "base"|"reference"|"candidate", "arm", "model", "run",
     "patch": sha256 of the pooled patch, "hidden": pass fraction or None, "scores": {judge: 0..8},
     "judged": {judge: sha256 of the patch that judge read}, "unbound": [judges whose rating was refused],
     "status": "rated"|"failed"|"excluded"|"incident", "reason"}

and per pool `{"task", "pool", "excluded_judges": {judge: reason}}`. A failed run (or a timeout) scores 0; an
excluded run (contaminated or a model-policy hit) and an incident (a run the harness could not collect) are
left out of every mean and count against G4. A rating whose judged digest differs from the pooled patch is
refused (left out of `scores`, listed in `unbound`, and an apparatus failure: `binding_failures`). Task lists are
in seed order. V1 and V2 count as `floor(fraction * tasks)`, which is the plan's 18 and 17 of the 20 tasks the
calibration always has (a draw short of 20 is a stop, `probing.probe_readout`); G1 needs 12 survivors.

Every comparison with a threshold is exact (coordinator ruling on B1, 2026-11-12): means, shares and rates are
`fractions.Fraction`s over whole-number scores and counts, and the thresholds are Fractions, so a value exactly at
a threshold (a G3 gap of exactly 0.5) meets it. Callers convert to float only for display (`readout.plain`).
"""

import math
from fractions import Fraction

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
JUDGES = (HAIKU, SONNET)  # cheapest first: the cheapest passing judge is used
POLICY = ("Fable model", "Forbidden model")
SURVIVOR = (Fraction(2), Fraction(13, 2))  # a task's Haiku mean, inclusive
SURVIVORS_MIN, SURVIVORS_MAX = 12, 16
V1_SHARE, V2_SHARE = Fraction(9, 10), Fraction(17, 20)  # 18 and 17 of 20 tasks
V1_REFERENCE, V1_BASE, CONTROL_GAP = 6, 1, 4
V3_MEAN, V3_LARGE, V4_PROBABILITY = Fraction(3, 4), Fraction(1, 10), Fraction(3, 4)
G2_RANGE, G3_GAP, G4_RATED, G4_EXCLUSIONS = (Fraction(5, 2), Fraction(13, 2)), Fraction(1, 2), Fraction(9, 10), 2
RATE_RANGE, RATE_GAP = (20, 80), 10  # hidden pass rate, percent: the tests-primary fallback and G3's switch


def mean(values):
    """The exact mean of whole-number scores (or of exact means)."""
    values = list(values)
    return Fraction(sum(values), len(values))


def required(share, n):
    return math.floor(share * n)


def anchor_role(label):
    """`<task>-base` is the untouched base, `<task>-upstream` the reference fix; any other anchor is refused."""
    roles = {"base": "base", "upstream": "reference"}
    suffix = label.rsplit("-", 1)[-1]
    if suffix not in roles:
        raise SystemExit(f"unexpected anchor {label!r}: a seed-set pool holds only <task>-base and <task>-upstream")
    return roles[suffix]


def pool_records(task, pool, results, patch_sha, models, judged):
    """Records of one pool's results.json: every clone, and every pooled run without a clone (failed or excluded).
    `patch_sha` maps clone id to the pooled patch's sha256; `models` maps arm to its bound model; `judged` maps
    judge to {clone id: sha256 of the patch it read}, which must equal the pooled patch for the rating to count."""
    records, rated = [], set()
    for cid, clone in results["clones"].items():
        role = anchor_role(clone["labels"][0]) if clone["arm"] == "anchor" else "candidate"
        rated.add(clone["run"])
        records.append({"task": task, "pool": pool, "role": role, "arm": clone["arm"], "model": models.get(clone["arm"]),
                        "run": clone["run"], "patch": patch_sha[cid], "hidden": clone["hidden"],
                        **bound_scores(clone["ratings"], judged, cid, patch_sha[cid]), "status": "rated", "reason": None})
    for row in results["runs"]:
        if row["run"] not in rated:
            records.append({"task": task, "pool": pool, "role": "candidate", "arm": row["arm"],
                            "model": models.get(row["arm"]), "run": row["run"], "patch": None, "hidden": None,
                            "scores": {}, "status": "excluded" if row["excluded"] else "failed",
                            "reason": row["excluded"] or (row["failure"] or {}).get("code")})
    return records, {"task": task, "pool": pool, "excluded_judges": dict(results["excluded_judges"])}


def bound_scores(ratings, judged, cid, patch):
    """{"scores", "judged", "unbound"}: a rating counts only when its judge read the pooled patch `patch`."""
    bound = {judge: judged.get(judge, {}).get(cid) for judge in ratings}
    return {"scores": {judge: rating["quality"] for judge, rating in ratings.items() if bound[judge] == patch},
            "judged": bound, "unbound": sorted(judge for judge, sha in bound.items() if sha != patch)}


def score(record, judge):
    """A candidate's score by `judge`: its rating, 0 for a failed run, None when left out."""
    if record["status"] == "failed":
        return 0
    return record["scores"].get(judge) if record["status"] == "rated" else None


def hidden_pass(record):
    return record["status"] == "rated" and record["hidden"] == 1


def _first(records, task=None, role=None):
    return [r for r in records if r["pool"] == "first" and (task is None or r["task"] == task)
            and (role is None or r["role"] == role)]


def anchors(records, task, judge):
    found = {r["role"]: r["scores"].get(judge) for r in _first(records, task) if r["role"] != "candidate"}
    return found.get("base"), found.get("reference")


# --- judge gate --------------------------------------------------------------------------------------------

def v1_controls(records, judge, tasks):
    """Reference minus base >= 4 on 90% of tasks; mean reference >= 6; mean base <= 1. A missing control fails
    its task and is listed."""
    pairs = {t: anchors(records, t, judge) for t in tasks}
    present = {t: p for t, p in pairs.items() if None not in p}
    met = sum(ref - base >= CONTROL_GAP for base, ref in present.values())
    refs, bases = [p[1] for p in present.values()], [p[0] for p in present.values()]
    out = {"met": met, "of": len(tasks), "need": required(V1_SHARE, len(tasks)),
           "missing": sorted(set(tasks) - set(present)),
           "mean_reference": mean(refs) if refs else None, "mean_base": mean(bases) if bases else None}
    return out | {"passed": bool(refs) and met >= out["need"] and out["mean_reference"] >= V1_REFERENCE
                  and out["mean_base"] <= V1_BASE}


def v2_reference_rank(records, judge, tasks):
    """The reference scores at least the mean of its batch's rated candidates on 85% of tasks."""
    met, missing = 0, []
    for task in tasks:
        _, ref = anchors(records, task, judge)
        rated = [r["scores"].get(judge) for r in _first(records, task, "candidate") if r["status"] == "rated"]
        if ref is None or not rated or None in rated:
            missing.append(task)
        else:
            met += ref >= mean(rated)
    need = required(V2_SHARE, len(tasks))
    return {"met": met, "of": len(tasks), "need": need, "missing": missing, "passed": met >= need}


def v3_retest(records, judge, retest_tasks):
    """Retest clones matched to their first judgment by (task, role, run record, patch hash), never by position:
    mean absolute difference <= 0.75 and at most 10% of clones differing by 2 or more, over every clone as the plan
    says (anchors included); the candidate-only mean is reported beside it. A task whose two pools do not hold the
    same clones, or whose pool is an incident, is missing and listed; V3 is computed over the rest (G4 bounds how
    many pools a judge may lose)."""
    first = {(r["task"], r["role"], r["run"], r["patch"]): r["scores"].get(judge)
             for r in records if r["pool"] == "first" and r["status"] == "rated"}
    diffs, candidate, missing = [], [], []
    for task in retest_tasks:
        again = [r for r in records if r["pool"] == "retest" and r["task"] == task and r["status"] == "rated"]
        if not again or len(again) != sum(key[0] == task for key in first):
            missing.append(task)
        if not any(key[0] == task for key in first):  # the first pool is an incident or missing
            continue
        for r in again:
            key = (r["task"], r["role"], r["run"], r["patch"])
            if key not in first:
                raise SystemExit(f"retest clone of {task} ({r['role']}, {r['run']}) matches no first judgment: "
                                 "the two pools do not hold the same records")
            pair = (first[key], r["scores"].get(judge))
            if None in pair:
                missing.append(task)
            else:
                diffs.append(abs(pair[0] - pair[1]))
                candidate += [abs(pair[0] - pair[1])] if r["role"] == "candidate" else []
    out = {"clones": len(diffs), "missing": sorted(set(missing)), "mean_abs": mean(diffs) if diffs else None,
           "large_fraction": Fraction(sum(d >= 2 for d in diffs), len(diffs)) if diffs else None,
           "candidate_mean_abs": mean(candidate) if candidate else None}
    return out | {"passed": bool(diffs) and out["mean_abs"] <= V3_MEAN and out["large_fraction"] <= V3_LARGE}


def v4_agreement(records, judge, tasks, minimum=15):
    """P(a hidden-passing candidate outscores a hidden-failing one), ties half, >= 0.75; not assessed (and not
    blocking) with fewer than `minimum` in either class. The ten largest disagreements are listed for reading."""
    rated = [r for r in records if r["pool"] == "first" and r["task"] in tasks and r["role"] == "candidate"
             and r["status"] == "rated" and r["hidden"] is not None and r["scores"].get(judge) is not None]
    passing = [r["scores"][judge] for r in rated if r["hidden"] == 1]
    failing = [r["scores"][judge] for r in rated if r["hidden"] < 1]
    worst = sorted(rated, key=lambda r: -abs(r["scores"][judge] / 8 - r["hidden"]))[:10]
    out = {"passing": len(passing), "failing": len(failing),
           "disagreements": [{"task": r["task"], "run": r["run"], "score": r["scores"][judge], "hidden": r["hidden"]}
                             for r in worst]}
    if len(passing) < minimum or len(failing) < minimum:
        return out | {"assessed": False, "probability": None, "passed": None}
    half_wins = sum(2 if p > f else 1 if p == f else 0 for p in passing for f in failing)  # a tie counts half
    probability = Fraction(half_wins, 2 * len(passing) * len(failing))
    return out | {"assessed": True, "probability": probability, "passed": probability >= V4_PROBABILITY}


def judge_gate(records, judge, tasks, retest_tasks):
    checks = {"V1": v1_controls(records, judge, tasks), "V2": v2_reference_rank(records, judge, tasks),
              "V3": v3_retest(records, judge, retest_tasks), "V4": v4_agreement(records, judge, tasks)}
    return checks | {"passed": all(checks[k]["passed"] for k in ("V1", "V2", "V3")) and checks["V4"]["passed"] is not False}


# --- task gates --------------------------------------------------------------------------------------------

def task_table(records, judge, tasks):
    """Per task: Haiku and Sonnet mean scores by `judge` and hidden passes, with left-out runs listed."""
    table = {}
    for task in tasks:
        row = {"left_out": []}
        for name, model in (("haiku", HAIKU), ("sonnet", SONNET)):
            runs = [r for r in _first(records, task, "candidate") if r["model"] == model]
            scored = [(score(r, judge), hidden_pass(r)) for r in runs]
            row["left_out"] += [r["run"] for r, (s, _) in zip(runs, scored) if s is None]
            kept = [(s, p) for s, p in scored if s is not None]
            row[name] = mean(s for s, _ in kept) if kept else None
            row[f"{name}_passes"], row[f"{name}_runs"] = sum(p for _, p in kept), len(kept)
        low, high = SURVIVOR
        row["survivor"] = row["haiku"] is not None and low <= row["haiku"] <= high
        table[task] = row
    return table


def _mean_of(table, key):
    values = [row[key] for row in table.values() if row[key] is not None]
    return mean(values) if values else None


def _rate(table, model):
    runs = sum(row[f"{model}_runs"] for row in table.values())
    return Fraction(100 * sum(row[f"{model}_passes"] for row in table.values()), runs) if runs else None


def policy_hits(records, pools):
    hits = [r["run"] for r in records if r["reason"] and r["reason"].startswith(POLICY)]
    return hits + [f"{p['task']}/{p['pool']}#{j}" for p in pools for j, why in p["excluded_judges"].items()
                   if why.startswith(POLICY)]


def task_gates(records, pools, judge, tasks):
    """G1-G4 on `judge`'s scores, with the hidden-test figure beside each."""
    table = task_table(records, judge, tasks)
    paired = {t: row for t, row in table.items() if row["haiku"] is not None and row["sonnet"] is not None}
    haiku, sonnet = _mean_of(paired, "haiku"), _mean_of(paired, "sonnet")
    rate_h, rate_s = _rate(table, "haiku"), _rate(table, "sonnet")
    survivors = [t for t in tasks if table[t]["survivor"]]
    runs = [r for r in records if r["pool"] == "first" and r["task"] in tasks and r["role"] == "candidate"]
    rated = sum(r["status"] == "rated" and r["scores"].get(judge) is not None for r in runs)
    excluded = {j: sum(j in p["excluded_judges"] for p in pools if p["task"] in tasks) for j in JUDGES}
    gates = {
        "G1": {"survivors": len(survivors), "need": SURVIVORS_MIN, "passed": len(survivors) >= SURVIVORS_MIN},
        "G2": {"haiku_mean": haiku, "haiku_pass_rate": rate_h, "tasks": len(paired),
               "passed": haiku is not None and G2_RANGE[0] <= haiku <= G2_RANGE[1]},
        "G3": {"gap": None if None in (haiku, sonnet) else sonnet - haiku,
               "pass_rate_gap": None if None in (rate_h, rate_s) else rate_s - rate_h},
        "G4": {"rated_fraction": Fraction(rated, len(runs)) if runs else None, "policy_hits": policy_hits(records, pools),
               "judge_exclusions": excluded},
    }
    gates["G3"]["passed"] = gates["G3"]["gap"] is not None and gates["G3"]["gap"] >= G3_GAP
    g4 = gates["G4"]
    g4["passed"] = (bool(runs) and g4["rated_fraction"] >= G4_RATED and not g4["policy_hits"]
                    and max(excluded.values()) <= G4_EXCLUSIONS)
    return {"table": table, "survivors": survivors[:SURVIVORS_MAX], "gates": gates}


def tests_primary(table):
    """The plan's fallback when no judge passes: hidden-test pass rate as the measure."""
    rate_h, rate_s = _rate(table, "haiku"), _rate(table, "sonnet")
    return {"survivors": [t for t, row in table.items() if 1 <= row["haiku_passes"] <= 3],
            "haiku_pass_rate": rate_h, "sonnet_minus_haiku": None if None in (rate_h, rate_s) else rate_s - rate_h,
            "haiku_rate_ok": rate_h is not None and RATE_RANGE[0] <= rate_h <= RATE_RANGE[1],
            "gap_ok": None not in (rate_h, rate_s) and rate_s - rate_h >= RATE_GAP}


def calibration(records, pools, tasks, retest_tasks):
    """The judge gate for both judges, the selected judge, its task gates and the decision."""
    judges = {judge: judge_gate(records, judge, tasks, retest_tasks) for judge in JUDGES}
    passing = [judge for judge in JUDGES if judges[judge]["passed"]]
    if not passing:
        table = task_table(records, HAIKU, tasks)  # scores unused: only hidden-test figures are read
        return {"judges": judges, "selected": None, "insensitive": None, "tests_primary": tests_primary(table),
                "decision": "stop: no judge passed its gate; hidden-test pass rate is primary; stop for the owner"}
    selected, insensitive = passing[0], None
    result = task_gates(records, pools, selected, tasks)
    g3 = result["gates"]["G3"]
    if not g3["passed"] and (g3["pass_rate_gap"] or 0) >= RATE_GAP and len(passing) > 1:
        insensitive, selected = selected, passing[1]
        result = task_gates(records, pools, selected, tasks)
    gates = result["gates"]
    if not gates["G4"]["passed"]:
        decision = "stop: G4 failed"
    elif all(gates[g]["passed"] for g in ("G1", "G2", "G3")):
        decision = "qualified"
    else:
        decision = "stop: a gate fails and the ladder probe was the one redraw; no quality claim"
    return {"judges": judges, "selected": selected, "insensitive": insensitive, **result, "decision": decision}


def anchor_failures(records, pools, tasks, judges=JUDGES):
    """Apparatus checks read before any quality number: per pool exactly one base and one reference, the base
    pooled as an unchanged clone, the reference failing no hidden node and the base failing one, one reference
    patch per task across its pools, and an integer rating of both by every judge not excluded there."""
    failures = []
    for pool in pools:
        if pool["task"] in tasks and "incident" not in pool:
            here = [r for r in records if (r["task"], r["pool"]) == (pool["task"], pool["pool"])]
            failures += pool_anchor_failures(pool, here, judges)
    for task in tasks:
        refs = {r["patch"] for r in records if r["task"] == task and r["role"] == "reference"}
        if len(refs) > 1:
            failures.append(f"{task}: its pools hold different reference patches")
    return failures


def binding_failures(records):
    """Ratings refused because the patch their judge read is not the pooled patch: no quality number is reported."""
    return [f"{r['task']}/{r['pool']}: the {r['role']} of run {r['run']} was rated by {judge} on another patch"
            for r in records for judge in r.get("unbound", [])]


def missing_pools(pools, tasks, retest_tasks):
    """Gated pools that are incidents or were never summarized: their tasks count as missing in the gates."""
    have = {(p["task"], p["pool"]): p for p in pools}
    wanted = [(t, "first") for t in tasks] + [(t, "retest") for t in retest_tasks]
    return {f"{t}/{k}": have[t, k]["incident"] if (t, k) in have else "not summarized"
            for t, k in wanted if (t, k) not in have or "incident" in have[t, k]}


def pool_anchor_failures(pool, here, judges):
    """The anchor checks of one pool's records `here`."""
    found = {role: [r for r in here if r["role"] == role] for role in ("base", "reference")}
    name = f"{pool['task']}/{pool['pool']}"
    if any(len(rows) != 1 for rows in found.values()):
        return [f"{name}: {len(found['base'])} base and {len(found['reference'])} reference anchors"]
    base, ref = found["base"][0], found["reference"][0]
    failures = [f"{name}: the base anchor is not an unchanged clone"] if base["patch"] != EMPTY_SHA else []
    if ref["patch"] == EMPTY_SHA:
        failures.append(f"{name}: the reference anchor is empty")
    if ref["hidden"] != 1 or base["hidden"] is None or base["hidden"] >= 1:
        failures.append(f"{name}: hidden tests give reference {ref['hidden']} and base {base['hidden']}")
    return failures + [f"{name}: {judge} did not rate both anchors" for judge in judges
                       if judge not in pool["excluded_judges"]
                       and any(type(r["scores"].get(judge)) is not int for r in (base, ref))]


EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # sha256 of no bytes
