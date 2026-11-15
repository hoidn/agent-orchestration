"""The seed-set calibration readout: `report` (a JSON-ready dict) and `markdown` (results/readout.md).

`report` takes the gate records (`gates.pool_records` over the pools' results.json), the runs' study.json facts
keyed by records path, and the spend totals. Anchors and the binding of every rating to the patch its judge read
are checked first; when any check fails the report holds measure-free figures only (runs, outcomes, calls, wall
clock, visible-check passes, spend) and no score. A decision that is a stop keeps measure-free figures and the
reason only: which judge checks and gates failed, as pass or fail, with no mean, score, rate or re-roll figure
(coordinator ruling on M7, 2026-11-12). `LIMITS` are stated on every readout. Exact gate values (Fractions) are
floats in the report (`plain`).
"""

from fractions import Fraction
from statistics import mean

from experiments.seed_set import gates, ladder, selection

LIMITS = (  # stated on every readout, one line each; recorded, not changed (coordinator rulings, 2026-11-12)
    "The plan's size section: 12 to 16 tasks support differences of about a point, not an ordering.",
    "A candidate can reach the network (the sandbox does not unshare it; whether the repository is public is "
    "unverified); the contamination scan matches the fix's commit hash, not its content.",
    "The visible check runs the candidate's code on the host, outside the sandbox, so that code could read the "
    "runtime checkout (the hidden tests among it); the scan of patches and transcripts for hidden names is the control.",
    "The per-run time limit does not include time spent in checks; a run cut short is a natural failure and is "
    "never pooled.",
    "A candidate patch that legitimately adds a token of the arm-identity scan costs its whole task: the pool is "
    "refused, not scrubbed.",
    "The check-withheld check on the study's own path was rehearsed only through a single run on a separate "
    "ledger, and no planned calibration arm runs it.",
    "G2 and G3 average over the tasks where both arms have a score, and V4 over the rated candidates; a run that "
    "failed or was never pooled is not among the plan's 100 natural candidates.",
    "A check-withheld run whose patch creates or edits the withheld test's path fails the host visible check (its "
    "patch does not apply to the in-tree view); this touches the visible-check figures only, not the gates.",
    "A T5 choice is always a stop: T4 and T5 hold 11 tasks together, short of the 20 the frozen thresholds need.",
    "A probe rung that kept 3 usable runs of 4 has its passes counted on four as round(4 x passes / 3) (the probe "
    "readout states the raw counts); this chooses the rung only and is not a quality gate.",
    "T2 is a short commit message plus the names of the files to change (a recorded deviation: with the message "
    "alone every T2 statement falls under the plan's 80-character floor); T2 differs from T1 by the commits "
    "selected (up to two files and 60 lines, against one file and 20), not by the form of the statement.",
)


def measure_free(runs):
    """Per tranche and arm: runs, outcomes, incidents, usage-limit cuts, physical calls, mean wall clock, visible
    passes and visible checks past their bound (neither a pass nor a failure; re-review N2), metering."""
    table = {}
    for facts in runs.values():
        row = table.setdefault(f"{facts['tranche']}/{facts['arm']}", {
            "runs": 0, "completed": 0, "failed": 0, "incidents": 0, "cut": 0, "calls": 0, "visible_passed": 0,
            "visible_timed_out": 0, "metering_complete": 0, "wall_clock": []})
        row["runs"] += 1
        row["calls"] += facts.get("calls", 0)
        row["incidents"] += "incident" in facts
        row["cut"] += "cut" in facts
        if facts.get("outcome") in ("completed", "failed") and "cut" not in facts:  # a cut is no outcome (R1)
            row[facts["outcome"]] += 1
        row["visible_passed"] += bool((facts.get("visible") or {}).get("passed"))
        row["visible_timed_out"] += bool((facts.get("visible") or {}).get("timed_out"))
        row["metering_complete"] += bool(facts.get("metering_complete"))
        if facts.get("wall_clock_sec") is not None:
            row["wall_clock"].append(facts["wall_clock_sec"])
    for row in table.values():
        times = row.pop("wall_clock")
        row["wall_clock_mean_sec"] = mean(times) if times else None
    return table


def direct_runs(records, runs, judge, tasks):
    """Per task, its first-pool Haiku direct runs as (score by `judge`, visible check passed); a run whose visible
    check ran past its bound is left out (re-review N2)."""
    per_task = {}
    for r in records:
        visible = runs.get(r["run"], {}).get("visible") or {}
        if r["pool"] == "first" and r["task"] in tasks and r["arm"] == "direct" and gates.score(r, judge) is not None \
                and not visible.get("timed_out"):
            per_task.setdefault(r["task"], []).append((gates.score(r, judge), visible.get("passed") is True))
    return {task: rows for task, rows in per_task.items() if len(rows) >= 3}


def unusual_runs(runs, tasks):
    """Every gated run that did not complete cleanly: its outcome, failure code, incident reason and usage-limit cut
    (no incident: coordinator ruling R1)."""
    return [{"run": run, "task": f["task"], "arm": f["arm"], "outcome": f.get("outcome"),
             "failure": (f.get("failure") or {}).get("code"), "incident": f.get("incident"),
             "cut": (f.get("cut") or {}).get("text")}
            for run, f in runs.items() if f["task"] in tasks and (f.get("outcome") != "completed" or "incident" in f)]


def v4_note(calibration):
    """The plain statement the decision carries when the selected judge's V4 was not assessed."""
    judge = calibration["selected"]
    v4 = calibration["judges"][judge]["V4"] if judge else None
    if not v4 or v4["assessed"]:
        return None
    return (f"V4 (agreement with the hidden tests) was not assessed for {judge}: fewer than 15 candidates in a "
            "hidden-test class; the judge was not checked against the tests and passed its gate on V1-V3 alone "
            "(coordinator ruling)")


def rungs(counts):
    """The drawn set per rung in words: tier, form and count (`T3w` is T3 in the check-withheld form)."""
    words = [f"{n.rstrip('w')} {ladder.tier_form(n)[1]} {k}" for n, k in counts.items()]
    return ", ".join(words) if words else "no chosen rung"


def report(records, pools, tasks, retests, rungs, runs, totals, programs, planned):
    """`programs` maps each arm to its program's {"source", "lines"}; `planned` counts the gated tranches' runs."""
    out = {"tasks": tasks, "retest_tasks": retests, "rungs": rungs, "spend": totals, "programs": programs,
           "measure_free": measure_free(runs),
           "anchor_failures": gates.anchor_failures(records, pools, tasks) + gates.binding_failures(records),
           "missing_pools": gates.missing_pools(pools, tasks, retests), "unusual_runs": unusual_runs(runs, tasks),
           "calibration": None, "baselines": None}
    if out["anchor_failures"]:
        return out
    out["calibration"] = calibration = gates.calibration(records, pools, tasks, retests)
    incidents = sum(1 for row in out["unusual_runs"] if row["incident"])
    if incidents * 10 > planned:  # over 10%, exactly
        calibration["decision"] = f"stop: {incidents} of {planned} planned runs are incidents, over 10%"
    calibration["v4_note"] = v4_note(calibration)
    if calibration["decision"].startswith("stop"):
        out["calibration"] = stopped(calibration)
        return plain(out)
    per_task = direct_runs(records, runs, calibration["selected"], tasks)
    out["baselines"] = selection.baselines(per_task) if per_task else None
    return plain(out)


def stopped(calibration):
    """What a stop reports of the calibration: the decision and which checks passed, and no figure."""
    checks = {judge: {k: c[k]["passed"] for k in ("V1", "V2", "V3", "V4")} | {"passed": c["passed"]}
              for judge, c in calibration["judges"].items()}
    return {"stopped": True, "decision": calibration["decision"], "selected": calibration["selected"],
            "insensitive": calibration["insensitive"], "v4_note": calibration["v4_note"], "judge_checks": checks,
            "gate_checks": {g: v["passed"] for g, v in calibration.get("gates", {}).items()}}


def plain(value):
    """`value` with every Fraction as a float, for JSON and display."""
    if isinstance(value, Fraction):
        return float(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def fmt(value):
    if value is None:
        return "-"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def spend_lines(totals):
    return ["| tranche | kind | model | reserved | cap |", "| --- | --- | --- | --- | --- |"] + [
        f"| {tranche} | {kind} | {model} | {row['reserved']} | {row['cap']} |"
        for tranche, kinds in totals.items() for kind, models in kinds.items() for model, row in models.items()]


def priced_lines(priced):
    """Priced tokens per tranche (metered tokens times the frozen price table; ruling R4): committed, settled, and
    open at its worst case, with the units settled at the worst case for missing usage."""
    if not priced:
        return []
    return ["", "| tranche | priced USD committed | settled | open at worst case | units with missing usage |",
            "| --- | --- | --- | --- | --- |"] + [
        f"| {t} | {p['committed_usd']:g} | {p['settled_usd']:g} | {p['open_usd']:g} | {len(p['missing_usage'])} |"
        for t, p in priced.items()]


def judge_lines(judges):
    lines = ["| judge | V1 controls | V2 reference rank | V3 retest | V4 agreement | passed |",
             "| --- | --- | --- | --- | --- | --- |"]
    for name, c in judges.items():
        v1, v2, v3, v4 = (c[k] for k in ("V1", "V2", "V3", "V4"))
        lines.append(f"| {name} | {v1['met']}/{v1['of']} (need {v1['need']}), ref {fmt(v1['mean_reference'])}, "
                     f"base {fmt(v1['mean_base'])}: {v1['passed']} | {v2['met']}/{v2['of']} (need {v2['need']}): "
                     f"{v2['passed']} | {v3['clones']} clones, mean {fmt(v3['mean_abs'])}, >=2 "
                     f"{fmt(v3['large_fraction'])}: {v3['passed']} | "
                     f"{fmt(v4['probability']) if v4['assessed'] else 'not assessed'} ({v4['passing']} pass, "
                     f"{v4['failing']} fail): {v4['passed']} | {c['passed']} |")
    return lines


def task_lines(table):
    lines = ["| task | Haiku mean | Sonnet mean | Haiku hidden passes | survivor |", "| --- | --- | --- | --- | --- |"]
    return lines + [f"| {task} | {fmt(row['haiku'])} | {fmt(row['sonnet'])} | {row['haiku_passes']}/"
                    f"{row['haiku_runs']} | {row['survivor']} |" for task, row in table.items()]


def gate_lines(gates_):
    g1, g2, g3, g4 = (gates_[k] for k in ("G1", "G2", "G3", "G4"))
    return [f"- G1 survivors: {g1['survivors']} (need {g1['need']}): {g1['passed']}",
            f"- G2 Haiku mean: {fmt(g2['haiku_mean'])} (hidden pass rate {fmt(g2['haiku_pass_rate'])}%): {g2['passed']}",
            f"- G3 Sonnet minus Haiku: {fmt(g3['gap'])} (pass-rate gap {fmt(g3['pass_rate_gap'])} points): "
            f"{g3['passed']}",
            f"- G4 rated {fmt(g4['rated_fraction'])}, policy hits {len(g4['policy_hits'])}, judge exclusions "
            f"{g4['judge_exclusions']}: {g4['passed']}"]


def judged_lines(c, b):
    """A qualified calibration (a selected judge, every gate passed): the judge gate, the calibration table, the
    task gates and the re-roll baselines."""
    lines = ["## Judge gate", ""] + judge_lines(c["judges"])
    lines += ["", f"Selected judge: {c['selected'] or 'none'}"
              + (f" ({c['insensitive']} treated as insensitive on G3)" if c["insensitive"] else "") + ".", ""]
    lines += ["## Calibration table", ""] + task_lines(c["table"]) + ["", "## Task gates", ""]
    lines += gate_lines(c["gates"]) + ["", f"Survivors (at most 16, seed order): {', '.join(c['survivors'])}."]
    unscored = [t for t, row in c["table"].items() if row["haiku"] is None or row["sonnet"] is None]
    lines += [f"Tasks without both arms scored by {c['selected']} (left out of G2/G3): {unscored or 'none'}."]
    if b:
        lines += ["", "## Offline re-roll baselines (Haiku direct runs)", "",
                  f"Q1 {fmt(b['Q1'])}; Q2 {fmt(b['Q2'])} at {fmt(b['Q2_calls'])} calls; Q3 {fmt(b['Q3'])} at "
                  f"{fmt(b['Q3_calls'])} calls; random-of-3 {fmt(b['random_of_3'])}; any-of-3 {fmt(b['any_of_3'])}; "
                  f"visible check failed in {fmt(b['visible_fail_rate'])} of direct runs."]
    decision = c["decision"] + (f"; {c['v4_note']}" if c.get("v4_note") else "")
    return lines + ["", f"Decision: {decision}."]


def stop_lines(c):
    """A stop's reason: the decision and which checks failed, as pass or fail only."""
    lines = ["## Why the study stopped (no quality figure is reported)", ""]
    lines += [f"- {judge}: " + ", ".join(f"{k} {v}" for k, v in checks.items()) for judge, checks in
              c["judge_checks"].items()]
    lines += [f"- Selected judge: {c['selected'] or 'none'}"
              + (f" ({c['insensitive']} treated as insensitive on G3)" if c["insensitive"] else "")]
    lines += ["- Task gates on the selected judge: " + ", ".join(f"{g} {v}" for g, v in c["gate_checks"].items())
              ] if c["gate_checks"] else []
    decision = c["decision"] + (f"; {c['v4_note']}" if c.get("v4_note") else "")
    return lines + ["", f"Decision: {decision}."]


def limit_lines():
    return ["", "## Limits", ""] + [f"- {line}" for line in LIMITS]


def markdown(r):
    lines = ["# Seed-set calibration readout", "",
             f"Tasks: {len(r['tasks'])} ({rungs(r['rungs'])}); retest: {len(r['retest_tasks'])}.",
             "", "## Runs (measure-free)", "",
             "| tranche/arm | runs | completed | failed | incidents | cut by a usage limit | calls | wall clock s | "
             "visible passed | visible check past its bound | metered |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {name} | {row['runs']} | {row['completed']} | {row['failed']} | {row['incidents']} | {row['cut']} | "
              f"{row['calls']} | {fmt(row['wall_clock_mean_sec'])} | {row['visible_passed']} | "
              f"{row['visible_timed_out']} | {row['metering_complete']} |"
              for name, row in r["measure_free"].items()]
    lines += ["", f"## Programs (fewer than {selection.MAX_PROGRAM_LINES} lines; common.orc exempt)", "",
              "| arm | program | lines | within the limit |", "| --- | --- | --- | --- |"]
    lines += [f"| {arm} | {p['source']} | {p['lines']} | {p['lines'] < selection.MAX_PROGRAM_LINES} |"
              for arm, p in r["programs"].items()]
    lines += ["", "## Spend", ""] + spend_lines(r["spend"]) + priced_lines(r.get("priced_usd") or {})
    lines += ["", f"## Pools missing or incidents ({len(r['missing_pools'])}): their tasks count as missing", ""]
    lines += [f"- {name}: {why}" for name, why in r["missing_pools"].items()]
    lines += ["", f"## Runs that did not complete cleanly ({len(r['unusual_runs'])})", ""]
    lines += [f"- {u['task']} {u['arm']}: {u['outcome']}, failure {u['failure']}, incident {u['incident']}"
              + (f", cut by a usage limit ({u['cut']})" if u["cut"] else "")
              for u in r["unusual_runs"]] + ["", "## Anchors", ""]
    if r["anchor_failures"]:
        return "\n".join(lines + [f"- {f}" for f in r["anchor_failures"]]
                         + ["", "An anchor check failed: no quality number is reported."] + limit_lines()) + "\n"
    lines += ["Every pool holds an unchanged base and the reference fix, both rated; hidden tests fail the base and "
              "pass the reference.", ""]
    c = r["calibration"]
    lines += stop_lines(c) if c.get("stopped") else judged_lines(c, r["baselines"])
    return "\n".join(lines + limit_lines()) + "\n"
