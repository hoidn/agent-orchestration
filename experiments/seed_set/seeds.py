"""The seed evaluation's report (seed-set plan, Step 3 and Step 4), as pure functions over records.

`report(records, pools, runs, judge, tasks, programs, judge_units, *, withheld)` takes:

- `records`: `gates.pool_records` over each summarized seed pool's results.json (pool kind `layout.SEED_POOL`; each
  clone's record keeps its clone id), plus one record of that kind per seed run no seed pool holds (a failed run or
  an incident, `study.unpooled_runs`' shape); an observed run of a summarized pool's task without a record refuses;
- `pools`: per seed pool, the info `gates.pool_records` returns with `"batches"`, the clone ids per batch of the
  pool's copied `mapping.json`, or `{"task", "pool", "incident"}` for a pool incident (a blinding hit among them);
- `runs`: {records path: study.json facts} (`readout.report`'s shape); only the seed evaluation's runs of `tasks`
  are read. Besides `study.settle`'s facts a settled run carries `priced` (its `settle` event: {"usd", "missing"}),
  `nested_sessions` (session files below the top level of its project store) and `tokens` (`metered_tokens` of its
  metering.json, None when unavailable);
- `judge`: the selected judge; `tasks`: the seed task list in its order (two batches planned per task);
- `programs`: {arm: {"source", "lines", "model", "effort", ...}} in `arms.json` order, every key of an arm's entry
  copied into its `seeds.json` entry (the caller adds the program hash);
- `judge_units`: the facts of every seed judge unit ({"calls", "priced"}), evaluation cost reported apart;
- `withheld`: the arms the visible-check checkpoint withheld, read by the caller from its recorded event; any other
  arm without an observed run refuses the report.

The order is `readout.report`'s: per-run measure-free figures first (outcomes, calls, tokens, priced USD at both
bounds, completion, distinctive share, nested share, the cut table, the visible check's rate); then the anchor checks
per batch (`gates.pool_anchor_failures` on the records of each batch) and the binding of every rating to the patch
its judge read (`gates.binding_failures`); then the control check (coordinator decision Q3: reference minus base
under `gates.CONTROL_GAP` by `judge`, a missing batch counted as under, no claim when the batches under pass
`BATCH_BOUND` of the planned batches). A failed check leaves measure-free figures only: no score, rate, re-roll or
selection figure. Otherwise per arm `q` (the mean over tasks of the per-task mean score; a task whose pool is
missing or an incident has no score), the hidden pass rate over its scored runs, retry's parity (`selection.parity`
on the parity tasks with a pool), the baselines (`selection.baselines` over the seed direct runs,
`readout.direct_runs`) with their `visible_fail_rate` beside the visible check's rate (`selection.visible_power`,
coordinator decision Q1), `selection.select_seeds`, the extension-eligible arms and the decision: only `direct`
passing gives `NO_WORKFLOW`, which is a readout outcome, not a stop. Exact figures are Fractions until `report`
returns (`readout.plain`).
"""

from fractions import Fraction

from experiments.orc_structural_search import metering
from experiments.seed_set import gates, readout, selection
from experiments.seed_set.layout import SEED_EVALUATION, SEED_POOL

BATCHES = 2  # judge batches planned per seed task (Step 3, "Judging")
BATCH_BOUND = Fraction(3, 32)  # "more than three of the 32 batches" as a proportion of the planned batches (Q3)
CUT_CODES = ("provider_timeout", "wall_clock_timeout")  # a run cut at its call limit or past its wall clock
NO_WORKFLOW = "no workflow qualified at this size"
NO_CLAIM = "no quality claim"
SETTLED = ("calls", "priced", "nested_sessions", "tokens")  # what an observed seed run must carry
LIMITS = (
    "The plan's size section: differences from direct under about 0.75 point, an ordering among the seeds and "
    "equality with direct cannot be shown.",
    "A seed with direct's quality and more calls is dominated by direct (`dominated_by_direct`); that is reported, "
    "not the selection test.",
    "The direct runs ran days before the workflow arms: a drift of the provider or the machine in between is inside "
    "every arm's difference from direct.",
    "A cut on a later call loses the whole run's patch: it scores 0 like a cut on the first call.",
    "Rules 2 and 3 compare an arm with direct on the tasks they share that have three usable direct runs, so "
    "retry's comparison rests on its six tasks.",
    "A task whose seed pool is missing or an incident has no score at all, its failed runs' zeros included: this "
    "slightly favours arms that fail often.",
)


def metered_tokens(receipt):
    """A run's metered tokens from its metering.json (`metering.receipts`): the providers' token sums, or None when
    the consumption is unavailable: the run facts' `tokens` that `report` reads, which `study.settle` records with
    this function."""
    found = receipt["consumption"]
    if found == metering.UNAVAILABLE:
        return None
    return sum(found[cli]["tokens"] for cli in ("claude", "codex") if found[cli]["calls"])


def batch_records(records, pool):
    """The records of each of a summarized seed pool's batches, grouped by the clone ids of its mapping.json."""
    by_clone = {r["clone"]: r for r in records if (r["task"], r["pool"]) == (pool["task"], pool["pool"])
                and r.get("clone")}  # an unpooled run's record has no clone
    return [[by_clone[cid] for cid in batch if cid in by_clone] for batch in pool["batches"]]


def anchor_failures(records, pools, judge):
    """Per batch of every summarized seed pool, `gates.pool_anchor_failures` (one base and one reference, the base
    unchanged, hidden tests failing the base and passing the reference, `judge` rating both), then every rating
    bound to another patch than the pooled one."""
    failures = []
    for pool in pools:
        if "incident" not in pool:
            for i, here in enumerate(batch_records(records, pool)):
                failures += gates.pool_anchor_failures({**pool, "pool": f"{pool['pool']}#{i}"}, here, (judge,))
    return failures + gates.binding_failures(records)


def controls(records, pools, judge, tasks):
    """The control check (Q3): `BATCHES` batches planned per task; a batch is under when its reference minus base by
    `judge` falls under `gates.CONTROL_GAP` or is missing (a pool incident, a pool never summarized, the second batch
    of a pool with one usable run). Passes while the batches under are at most `BATCH_BOUND` of the planned ones."""
    have = {p["task"]: p for p in pools if "incident" not in p}
    under = []
    for task in tasks:
        batches = batch_records(records, have[task]) if task in have else []
        for i in range(BATCHES):
            anchors = {r["role"]: r["scores"].get(judge) for r in (batches[i] if i < len(batches) else [])}
            base, ref = anchors.get("base"), anchors.get("reference")
            if None in (base, ref) or ref - base < gates.CONTROL_GAP:
                under.append(f"{task}#{i}")
    planned = BATCHES * len(tasks)
    return {"batches": planned, "under": len(under), "under_batches": under,
            "passed": len(under) <= BATCH_BOUND * planned}


def missing_pools(pools, tasks):
    """{task: why} for every seed task whose pool is an incident or was never summarized: its runs have no score."""
    have = {p["task"]: p for p in pools}
    return {t: have[t]["incident"] if t in have else "not summarized" for t in tasks
            if t not in have or "incident" in have[t]}


def seed_runs(runs, tasks):
    """The run facts of the seed evaluation's runs of `tasks`: no other tranche's run is read."""
    return {path: facts for path, facts in runs.items() if facts["tranche"] == SEED_EVALUATION
            and facts["task"] in tasks}


def record_of(by_run, path, facts, lost):
    """The record of run `path`, or None. Refuses an observed run (neither an incident nor a usage-limit cut) of a
    task whose pool was summarized (not in `lost`) when no record holds it: its score, a 0 for a failed run, would
    otherwise vanish from its task's mean."""
    record = by_run.get(path)
    if record is None and facts["task"] not in lost and selection.observed([facts]):
        raise SystemExit(f"{path}: an observed seed run that no record holds (neither pooled nor recorded as "
                         "unpooled); its score is unknown")
    return record


def scored_runs(records, runs, judge, tasks, pools):
    """{arm: [facts with "run", "score", "hidden_pass" and "excluded"]} of the seed evaluation's runs of `tasks`:
    the score by `judge` (`gates.score`: 0 for a failed run, None when left out or when its task's pool is missing
    or an incident), `excluded` the pool's reason for leaving it out as contaminated or a model-policy hit
    (`record_of` refuses an observed run no record holds)."""
    lost = missing_pools(pools, tasks)
    by_run = {r["run"]: r for r in records if r["pool"] == SEED_POOL and r["role"] == "candidate"}
    out = {}
    for path, facts in seed_runs(runs, tasks).items():
        record = record_of(by_run, path, facts, lost)
        scored = record is not None and facts["task"] not in lost
        out.setdefault(facts["arm"], []).append(facts | {
            "run": path, "score": gates.score(record, judge) if scored else None,
            "hidden_pass": scored and gates.hidden_pass(record),
            "excluded": record["reason"] if record and record["status"] == "excluded" else None})
    return out


def left_out(arm_runs, lost):
    """Every run without a score, with why: an incident, a usage-limit cut, an exclusion, a missing pool, or a
    rating refused."""
    rows = []
    for name, runs in arm_runs.items():
        for r in runs:
            if r["score"] is None:
                why = r.get("incident") or ("cut by a usage limit" if "cut" in r else None) or r["excluded"] \
                    or (f"pool: {lost[r['task']]}" if r["task"] in lost else "no bound rating")
                rows.append({"run": r["run"], "task": r["task"], "arm": name, "why": why})
    return rows


def require_settled(runs):
    """Refuse an observed seed run that lacks a settled fact the report reads (`SETTLED`)."""
    for r in selection.observed(runs):
        if missing := [key for key in SETTLED if key not in r]:
            raise SystemExit(f"{r['run']}: no {missing} in its facts; settle it before the seed report")


def cut_table(seen):
    """The observed runs cut at their call limit or past their wall clock: their count and share, how many by the
    call they were cut on (a cut run's last call is its physical call count), and their priced USD apart."""
    cut = [r for r in seen if (r.get("failure") or {}).get("code") in CUT_CODES]
    by_call = {}
    for r in cut:
        by_call[r["calls"]] = by_call.get(r["calls"], 0) + 1
    return {"runs": len(cut), "rate": Fraction(len(cut), len(seen)), "by_call": dict(sorted(by_call.items())),
            "priced_usd": sum((selection.usd(r["priced"]["usd"]) for r in cut), Fraction(0))}


def costs(name, runs):
    """An arm's measure-free figures over its observed runs (Q18's denominator, `selection.observed`): mean calls
    `c`, mean metered tokens over the runs that have them, priced USD per run at both bounds (Q7: every run, a cut
    call at its worst case; and the runs with no missing usage only, None when none), completion (rule 1, Q13), the
    distinctive share (rule 5; None for direct), the share with a nested session, and the cut table."""
    seen = selection.observed(runs)
    tokens = [r["tokens"] for r in seen if r["tokens"] is not None]
    metered = [selection.usd(r["priced"]["usd"]) for r in seen if not r["priced"]["missing"]]
    return {"runs": len(seen), "calls": selection.mean((r["calls"] for r in seen), "calls"),
            "tokens": selection.mean(tokens, "tokens") if tokens else None, "tokens_runs": len(tokens),
            "priced_worst": selection.mean(selection.usd(r["priced"]["usd"]) for r in seen),
            "priced_metered": selection.mean(metered) if metered else None, "priced_metered_runs": len(metered),
            "completed": selection.completion(runs),
            "distinctive": selection.distinctive(name, runs) if name in selection.DISTINCTIVE_CALLS else None,
            "nested": selection.share(runs, lambda r: r["nested_sessions"] > 0), "cut": cut_table(seen)}


def quality(name, runs, rerolled):
    """An arm's judged figures: per task the mean score of its observed scored runs, `q` over those tasks (None when
    none), the hidden pass rate over those runs, and for retry the parity check (Q4, `parity`)."""
    scored = [r for r in selection.observed(runs) if r["score"] is not None]
    tasks = {}
    for r in scored:
        tasks.setdefault(r["task"], []).append(r["score"])
    per_task = {t: selection.mean(values, "score") for t, values in tasks.items()}
    return {"tasks": per_task, "q": selection.mean(per_task.values()) if per_task else None,
            "hidden": Fraction(sum(r["hidden_pass"] for r in scored), len(scored)) if scored else None,
            "parity": parity(runs, scored, rerolled) if name == selection.RETRY else None}


def parity(runs, scored, rerolled):
    """`selection.parity` with its means over the `scored` runs' tasks and "every run completes" over every observed
    run (Q4, Q13), a run of a task whose pool is missing or an incident included."""
    out = selection.parity(scored, rerolled)
    done = all(map(selection.completes, selection.observed(runs)))
    return out | {"completes": done, "passed": out["passed"] and done}


def summary(arm, program):
    """An arm's summary (its `costs` and `quality` merged) in the exact keys `selection.select_seeds` and
    `selection.rules` read."""
    keys = ("tasks", "completed", "calls", "priced_worst", "priced_metered", "nested", "distinctive")
    return {key: arm[key] for key in keys} | {"model": program["model"], "effort": program["effort"],
                                              "parity": arm["parity"]["passed"] if arm["parity"] else None,
                                              "lines": program["lines"]}


def judge_cost(units):
    """The judge units' physical calls and priced USD, with the units settled with missing usage."""
    return {"units": len(units), "calls": sum(u["calls"] for u in units),
            "priced_usd": round(sum(u["priced"]["usd"] for u in units), 6),
            "missing_usage": sum(bool(u["priced"]["missing"]) for u in units)}


def require_ran(arm_runs, programs, withheld):
    """The arms with observed runs, in `programs` order. Refuses when direct has none, or when another arm has none
    and is not among `withheld` (the arms the visible-check checkpoint withheld): a report before every arm has run
    would read a missing arm as a failed one."""
    ran = [name for name in programs if selection.observed(arm_runs.get(name, []))]
    if "direct" not in ran:
        raise SystemExit("no observed seed direct run: the seed evaluation has no reference")
    if absent := [name for name in programs if name not in ran and name not in withheld]:
        raise SystemExit(f"arms {absent} have no observed run and were not withheld: the seed report waits for them")
    return ran


def report(records, pools, runs, judge, tasks, programs, judge_units, *, withheld):
    """The seed report (the module docstring); a JSON-ready dict. `withheld` names the arms the visible-check
    checkpoint withheld, as its recorded event says; every other arm of `programs` must have observed runs. The
    visible check's rate (`selection.visible_power`) must be defined, as the checkpoint needs it."""
    arm_runs = scored_runs(records, runs, judge, tasks, pools)
    ran = require_ran(arm_runs, programs, withheld)
    for rows in arm_runs.values():
        require_settled(rows)
    mine = seed_runs(runs, tasks)
    out = {"tasks": tasks, "judge": judge, "measure_free": readout.measure_free(mine),
           "unusual_runs": readout.unusual_runs(mine, tasks), "missing_pools": missing_pools(pools, tasks),
           "withheld": [name for name in programs if name not in ran],
           "arms": {name: costs(name, arm_runs[name]) for name in ran},
           "visible_power": selection.visible_power(arm_runs["direct"]), "judge_cost": judge_cost(judge_units),
           "anchor_failures": anchor_failures(records, pools, judge), "controls": None, "left_out": None,
           "baselines": None, "selection": None, "extension_eligible": None}
    if out["anchor_failures"]:
        return readout.plain(out | {"decision": f"{NO_CLAIM}: an anchor or binding check failed"})
    out["controls"] = checked = controls(records, pools, judge, tasks)
    if not checked["passed"]:
        return readout.plain(out | {"decision": f"{NO_CLAIM}: {checked['under']} of {checked['batches']} batches "
                                                f"have reference minus base under {gates.CONTROL_GAP}"})
    return readout.plain(out | judged(records, runs, judge, tasks, pools, programs, arm_runs, out))


def judged(records, runs, judge, tasks, pools, programs, arm_runs, out):
    """The report's judged part, once every check passed: per-arm quality, the baselines, the selection and the
    decision."""
    lost = missing_pools(pools, tasks)
    kept = [r for r in records if r["task"] not in lost]
    per_task = readout.direct_runs(kept, runs, judge, tasks, pool=SEED_POOL)
    rerolled = selection.baselines(per_task) if per_task else {"tasks": {}}
    arms = {name: out["arms"][name] | quality(name, arm_runs[name], rerolled) for name in out["arms"]}
    chosen = selection.select_seeds({name: summary(arms[name], programs[name]) for name in arms}, rerolled)
    seeds, power = chosen["seeds"], out["visible_power"]
    return {"arms": arms, "baselines": rerolled, "selection": chosen, "left_out": left_out(arm_runs, lost),
            "visible_power": power | {"visible_fail_rate": rerolled.get("visible_fail_rate")},
            "extension_eligible": [n for n, rep in chosen["arms"].items() if rep.get("extension_eligible")],
            "decision": NO_WORKFLOW if seeds == ["direct"] else "seeds: " + ", ".join(seeds)}


def seeds_json(result, programs):
    """`seeds.json` from a `report` result: the judge, the tasks, the decision, the stop that prevented a seed set
    (None when one was selected), the visible check's rate, and per selected program its `programs` entry with `q`,
    `c`, its difference from direct and the interval (none for direct). The caller adds the run's hashes."""
    chosen = (result["selection"] or {}).get("seeds", [])
    stop = None if len(chosen) > 1 else result["decision"]
    entries = []
    for name in chosen:
        rep, arm = result["selection"]["arms"][name], result["arms"][name]
        entries.append({"arm": name, **programs[name], "q": arm["q"], "c": arm["calls"],
                        "difference": rep.get("difference"), "interval": rep.get("interval")})
    return {"judge": result["judge"], "tasks": result["tasks"], "decision": result["decision"], "stop": stop,
            "visible_power": result["visible_power"], "seeds": entries}


# --- the readout's seed section ----------------------------------------------------------------------------

fmt = readout.fmt


def cost_lines(arms):
    """The measure-free arm table: observed runs, completion, calls, tokens, priced USD at both bounds, the
    distinctive and nested shares, and the runs cut at the call limit by call position with their priced USD."""
    lines = ["| arm | runs | completed | calls | tokens (runs) | priced USD worst | priced USD metered (runs) | "
             "distinctive | nested | cut at the call limit: runs by call, USD |", "| --- " * 10 + "|"]
    for name, a in arms.items():
        cut = a["cut"]
        lines.append(f"| {name} | {a['runs']} | {fmt(a['completed'])} | {fmt(a['calls'])} | {fmt(a['tokens'])} "
                     f"({a['tokens_runs']}) | {fmt(a['priced_worst'])} | {fmt(a['priced_metered'])} "
                     f"({a['priced_metered_runs']}) | {fmt(a['distinctive'])} | {fmt(a['nested'])} | {cut['runs']}: "
                     f"{cut['by_call'] or '-'}, {fmt(cut['priced_usd'])} |")
    return lines


def arm_lines(result):
    """The judged arm table: q, hidden pass rate, difference from direct with its 90% interval, and the rules."""
    lines = ["| arm | q | hidden pass rate | difference from direct | 90% interval | dominated by direct | rules "
             "failed | seed |", "| --- " * 8 + "|"]
    for name, a in result["arms"].items():
        rep = result["selection"]["arms"][name]
        interval = rep.get("interval")
        failed = [rule for rule, ok in rep.get("rules", {}).items() if not ok]
        lines.append(f"| {name} | {fmt(a['q'])} | {fmt(a['hidden'])} | {fmt(rep.get('difference'))} | "
                     f"{'-' if not interval else f'{interval[0]:.2f} to {interval[1]:.2f}'} | "
                     f"{fmt(rep.get('dominated_by_direct'))} | {', '.join(failed) or '-'} | "
                     f"{name in result['selection']['seeds']} |")
    return lines


def judged_lines(result):
    """A claim's lines: the control check, the judged arm table, the seed baselines, retry parity, the comparisons
    whose interval spans the tolerance, the extension-eligible arms and the runs left out."""
    b, chosen = result["baselines"], result["selection"]
    spans = [n for n, rep in chosen["arms"].items() if rep.get("spans_tolerance")]
    lines = ["", f"Controls: {result['controls']['under']} of {result['controls']['batches']} batches under "
             f"{gates.CONTROL_GAP}.", ""] + arm_lines(result) + [""]
    if b.get("tasks"):
        lines.append(f"Offline re-roll baselines (seed direct runs, {len(b['tasks'])} tasks): Q1 {fmt(b['Q1'])}; "
                     f"Q2 {fmt(b['Q2'])} at {fmt(b['Q2_calls'])} calls; Q3 {fmt(b['Q3'])} at {fmt(b['Q3_calls'])} "
                     f"calls; random-of-3 {fmt(b['random_of_3'])}; any-of-3 {fmt(b['any_of_3'])}.")
    parity = (result["arms"].get(selection.RETRY) or {}).get("parity")
    if parity:
        lines.append(f"Retry parity: calls {fmt(parity['calls'])} against {fmt(parity['offline_calls'])}, score "
                     f"{fmt(parity['score'])} against {fmt(parity['offline_score'])}, every run completes "
                     f"{parity['completes']}, tasks without a baseline {parity['no_baseline'] or 'none'}: "
                     f"{parity['passed']}.")
    lines += [f"Comparisons whose interval spans the tolerance of {float(selection.TAU_Q)}: {spans or 'none'}.",
              f"Extension-eligible arms (within 0.25 point of rule 2's or rule 3's line): "
              f"{result['extension_eligible'] or 'none'}."]
    return lines + [f"Left out and not scored: {len(result['left_out'])}."] + [
        f"- {row['task']} {row['arm']} {row['run']}: {row['why']}" for row in result["left_out"]]


def markdown(result):
    """The readout's seed section: measure-free figures, the anchors, then the judged arm table and the rule
    applied, or the reason no quality figure is given; its limits last."""
    power, judge = result["visible_power"], result["judge_cost"]
    lines = ["## Seed evaluation", "", f"Judge: {result['judge']}; tasks: {len(result['tasks'])}; arms withheld at "
             f"the visible-check checkpoint: {result['withheld'] or 'none'}.", ""] + cost_lines(result["arms"]) + [""]
    lines.append(f"Visible check failed in {power['failed']} of {power['checked']} checked direct runs "
                 f"({fmt(power['rate'])}); the parity and implement-check-repair arms launch: {power['launch']}.")
    if "visible_fail_rate" in power:
        lines.append(f"Mean over the baseline tasks of each task's share of direct runs whose visible check did not "
                     f"pass: {fmt(power['visible_fail_rate'])}.")
    lines += [] if power["launch"] else ["The check has no selecting power on this set."]
    lines += [f"Judge cost, apart from the candidates': {judge['calls']} calls in {judge['units']} units, priced USD "
              f"{judge['priced_usd']:g} ({judge['missing_usage']} units with missing usage).",
              f"Seed pools missing or incidents: {result['missing_pools'] or 'none'}.", "", "### Anchors", ""]
    if result["anchor_failures"]:
        lines += [f"- {f}" for f in result["anchor_failures"]] + ["", "No quality figure is reported."]
    elif not result["controls"]["passed"]:
        lines += [f"Controls: {result['controls']['under']} of {result['controls']['batches']} batches under "
                  f"{gates.CONTROL_GAP}, over the bound; no quality figure is reported."]
    else:
        lines += ["Every batch holds an unchanged base and the reference fix, both rated."] + judged_lines(result)
    lines += ["", f"Decision: {result['decision']}.", "", "### Limits", ""]
    return "\n".join(lines + [f"- {line}" for line in LIMITS]) + "\n"
