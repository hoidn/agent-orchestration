"""The seed-set calibration readout: `report` (a JSON-ready dict) and `markdown` (results/readout.md).

`report` takes the gate records (`gates.pool_records` over the pools' results.json), the runs' study.json facts
keyed by records path, and the spend totals. Anchors are checked first; when any check fails the report holds
measure-free figures only (runs, outcomes, calls, wall clock, visible-check passes, spend) and no score.
"""

from statistics import mean

from experiments.seed_set import gates, selection


def measure_free(runs):
    """Per tranche and arm: runs, outcomes, incidents, physical calls, mean wall clock, visible passes, metering."""
    table = {}
    for facts in runs.values():
        row = table.setdefault(f"{facts['tranche']}/{facts['arm']}", {
            "runs": 0, "completed": 0, "failed": 0, "incidents": 0, "calls": 0, "visible_passed": 0,
            "metering_complete": 0, "wall_clock": []})
        row["runs"] += 1
        row["calls"] += facts.get("calls", 0)
        row["incidents"] += "incident" in facts
        if facts.get("outcome") in ("completed", "failed"):
            row[facts["outcome"]] += 1
        row["visible_passed"] += bool((facts.get("visible") or {}).get("passed"))
        row["metering_complete"] += bool(facts.get("metering_complete"))
        if facts.get("wall_clock_sec") is not None:
            row["wall_clock"].append(facts["wall_clock_sec"])
    for row in table.values():
        times = row.pop("wall_clock")
        row["wall_clock_mean_sec"] = mean(times) if times else None
    return table


def direct_runs(records, runs, judge, tasks):
    """Per task, its first-pool Haiku direct runs as (score by `judge`, visible check passed)."""
    per_task = {}
    for r in records:
        if r["pool"] == "first" and r["task"] in tasks and r["arm"] == "direct" and gates.score(r, judge) is not None:
            visible = (runs.get(r["run"], {}).get("visible") or {}).get("passed") is True
            per_task.setdefault(r["task"], []).append((gates.score(r, judge), visible))
    return {task: rows for task, rows in per_task.items() if len(rows) >= 3}


def report(records, pools, tasks, retests, redrawn, runs, totals):
    out = {"tasks": tasks, "retest_tasks": retests, "redrawn": redrawn, "spend": totals,
           "measure_free": measure_free(runs), "anchor_failures": gates.anchor_failures(records, pools, tasks),
           "calibration": None, "baselines": None}
    if out["anchor_failures"]:
        return out
    out["calibration"] = gates.calibration(records, pools, tasks, retests, redrawn)
    judge = out["calibration"]["selected"]
    per_task = direct_runs(records, runs, judge, tasks) if judge else {}
    out["baselines"] = selection.baselines(per_task) if per_task else None
    return out


def fmt(value):
    if value is None:
        return "-"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def spend_lines(totals):
    return ["| tranche | kind | model | reserved | cap |", "| --- | --- | --- | --- | --- |"] + [
        f"| {tranche} | {kind} | {model} | {row['reserved']} | {row['cap']} |"
        for tranche, kinds in totals.items() for kind, models in kinds.items() for model, row in models.items()]


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


def markdown(r):
    lines = ["# Seed-set calibration readout", "",
             f"Tasks: {len(r['tasks'])} ({'with' if r['redrawn'] else 'no'} redraw); retest: {len(r['retest_tasks'])}.",
             "", "## Runs (measure-free)", "",
             "| tranche/arm | runs | completed | failed | incidents | calls | wall clock s | visible passed | metered |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {name} | {row['runs']} | {row['completed']} | {row['failed']} | {row['incidents']} | {row['calls']} | "
              f"{fmt(row['wall_clock_mean_sec'])} | {row['visible_passed']} | {row['metering_complete']} |"
              for name, row in r["measure_free"].items()]
    lines += ["", "## Spend", ""] + spend_lines(r["spend"]) + ["", "## Anchors", ""]
    if r["anchor_failures"]:
        return "\n".join(lines + [f"- {f}" for f in r["anchor_failures"]]
                         + ["", "An anchor check failed: no quality number is reported."]) + "\n"
    lines += ["Every pool holds an unchanged base and the reference fix, both rated; hidden tests fail the base and "
              "pass the reference.", "", "## Judge gate", ""] + judge_lines(r["calibration"]["judges"])
    c = r["calibration"]
    lines += ["", f"Selected judge: {c['selected'] or 'none'}"
              + (f" ({c['insensitive']} treated as insensitive on G3)" if c["insensitive"] else "") + ".", ""]
    if c["selected"]:
        lines += ["## Calibration table", ""] + task_lines(c["table"]) + ["", "## Task gates", ""]
        lines += gate_lines(c["gates"]) + ["", f"Survivors (at most 16, seed order): {', '.join(c['survivors'])}."]
    else:
        lines += [f"Hidden-test fallback: {c['tests_primary']}."]
    b = r["baselines"]
    if b:
        lines += ["", "## Offline re-roll baselines (Haiku direct runs)", "",
                  f"Q1 {fmt(b['Q1'])}; Q2 {fmt(b['Q2'])} at {fmt(b['Q2_calls'])} calls; Q3 {fmt(b['Q3'])} at "
                  f"{fmt(b['Q3_calls'])} calls; random-of-3 {fmt(b['random_of_3'])}; any-of-3 {fmt(b['any_of_3'])}; "
                  f"visible check failed in {fmt(b['visible_fail_rate'])} of direct runs."]
    lines += ["", f"Decision: {c['decision']}.", "",
              "Limits: the plan's size section; 12 to 16 tasks support differences of about a point, not an ordering."]
    return "\n".join(lines) + "\n"
