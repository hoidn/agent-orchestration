"""The ladder probe (plan, "Probable calibration failures and the response to each": Ladder probe, If the whole
ladder misses, Bisection instead of the flat probe), on the redraw tranche's cap: 40 Haiku calls shared by every
probe run, flat or bisected, first or extension. The redraw tranche serves nothing else.

`probe` runs `direct` on Haiku once on the four probe tasks of each requested rung, which must be among the rungs
the current answer asks for; each run is settled as a candidate run is, then its final patch gets the hidden set
(behind the host guard) and, for an in-tree package, the self-check detector over its transcripts. `answer`
derives the next step from the ledger and the run records alone:

- phase `first`: the flat five (T1 to T5), or the bisection over T0 to T5 when the smoke check said so;
- a miss starts phase `extension`: all too easy bisects over T1w to T4w (T6 is dropped: the extension upward
  ends at T5), all too hard over T0 and T1 again, the latter only after `record-transcripts` recorded that the
  transcripts were read;
- a miss of the extension is a stop: every later start refuses.

An interrupted run (its runner stopped before settling it) and a provider incident are incidents, never task
failures (coordinator ruling on review2 M2/M3, 2026-11-12): `probe` first recovers every reserved probe run a
stopped runner left (settles it or files it as interrupted, then gives it its hidden check), and launches an
incident's task once more, reserved from the same redraw Haiku allowance; a task whose second run is an incident
too is excluded and listed. A rung is answered when each of its four probe tasks has a usable run or is excluded;
its passes are counted on four (`round(4 * passes / usable)`: 3 of 3 is 4, 2 of 3 is 3, 1 of 3 is 1; an assumption
recorded for the coordinator), and a rung with fewer than three usable runs stops the probe ("probe incomplete"),
with no task list. A run cut by a usage limit (coordinator ruling R1, 2026-11-14) is neither an incident nor a task
failure: it gets no hidden check, and its task runs once more from the same allowance (`RERUNS`), beside the one
relaunch an incident gets; a task cut again is excluded like an exhausted one.

`probe_readout` records the answer; a chosen or split answer draws the calibration tasks (`ladder.choose`) and,
when they are 20, writes them to `results/calibration-tasks.json` once, with its hash and the per-rung counts in
the ledger, which the calibration's starts require. The calibration runs at 20 tasks with the plan's frozen
thresholds or not at all (coordinator ruling, 2026-11-12): a draw short of 20 after fill and top-up (T4 and T5
together hold 11) records a stop, so no calibration call can start, and goes to the owner.
"""

import json
from fractions import Fraction
from pathlib import Path

from experiments.compare.repos import dump, load, sha256_file
from experiments.seed_set import host, ladder, rules, spend, units
from experiments.seed_set import study as runner
from experiments.seed_set.layout import CHOSEN, load_arms, study_runs, task_dir, task_rows


RELAUNCHES, MIN_USABLE, RERUNS = 1, 3, 1  # coordinator rulings on review2 M2/M3 and R1


def attempts(study, phase):
    """{task: [facts of each of its probe runs in `phase`]}."""
    found = {}
    for path in study_runs(study):
        facts = load(path)
        if facts["tranche"] == "redraw" and facts.get("step") == phase:
            found.setdefault(facts["task"], []).append(facts)
    return found


def usable(facts):
    return "hidden" in facts and "incident" not in facts and "cut" not in facts


def ended(facts):
    """A settled run that is no observation: an incident, or cut by a usage limit."""
    return "incident" in facts or "cut" in facts


def allowed(runs):
    """Starts a probe task may have: one, one relaunch after an incident, one re-run after a usage-limit cut."""
    return (1 + min(sum("incident" in f for f in runs), RELAUNCHES)
            + min(sum("cut" in f and "incident" not in f for f in runs), RERUNS))


def exhausted(runs):
    return not any(map(usable, runs)) and all(map(ended, runs)) and len(runs) >= allowed(runs)


def results(study, phase):
    """({rung: passes on four} over the answered rungs of `phase`, {rung: figures}); a rung with fewer than three
    usable runs is answered as `incomplete` in its figures and has no passes."""
    rows, tried, passes, figures = task_rows(study), attempts(study, phase), {}, {}
    for rung in {f["rung"] for runs in tried.values() for f in runs}:
        tasks = ladder.probe_tasks(rows, rung)
        good = [next(filter(usable, tried.get(t, []))) for t in tasks if any(map(usable, tried.get(t, [])))]
        figures[rung] = rung_figures(tasks, tried, good)
        if len(good) + len(figures[rung]["excluded"]) == len(tasks) == ladder.PROBE_TASKS:
            passes |= counted_on_four(rung, figures[rung], len(good))
    return passes, figures


def rung_figures(tasks, tried, good):
    """A rung's probe figures: its runs, usable runs and their passes, incidents, cuts, excluded tasks, and the
    in-tree runs with how many ran the visible check themselves."""
    own = [f for f in good if f.get("self_check") is not None]
    return {"runs": sum(len(tried.get(t, [])) for t in tasks), "usable": len(good),
            "passes": sum(bool(f["hidden"]["passed"]) for f in good),
            "incidents": sum("incident" in f for t in tasks for f in tried.get(t, [])),
            "cuts": sum("cut" in f for t in tasks for f in tried.get(t, [])),
            "excluded": [t for t in tasks if exhausted(tried.get(t, []))], "in_tree_runs": len(own),
            "self_checked": sum(bool(f["self_check"]) for f in own)}


def counted_on_four(rung, figures, usable_runs):
    """{rung: passes on four} for an answered rung, {} for one with fewer than MIN_USABLE usable runs (marked
    `incomplete` in its figures); a rung with fewer than four usable runs says how it was counted."""
    if usable_runs < MIN_USABLE:
        figures["incomplete"] = True
        return {}
    passes = round(Fraction(ladder.PROBE_TASKS * figures["passes"], usable_runs))
    if usable_runs < ladder.PROBE_TASKS:
        figures["counted_on_four"] = (
            f"{figures['passes']} of {usable_runs} usable runs counted as {passes} of {ladder.PROBE_TASKS}: "
            "round(4 x passes / usable), for the choice of rung only, not a quality gate")
    return {rung: passes}


def incomplete(study, phase):
    return sorted(r for r, f in results(study, phase)[1].items() if f.get("incomplete"))


def self_check_share(figures):
    runs = sum(f["in_tree_runs"] for f in figures.values())
    return sum(f["self_checked"] for f in figures.values()) / runs if runs else None


def available(rows, rungs):
    return {rung: len(ladder.rung_tasks(rows, rung)) for rung in rungs}


def step_answer(passes, rungs, bisect):
    if bisect:
        return ladder.next_rung(passes, rungs)
    missing = [r for r in ladder.order(rungs) if rungs[r] >= ladder.PROBE_TASKS and r not in passes]
    return {"probe": missing} if missing else ladder.table(passes)


def answer(study):
    rows, entries = task_rows(study), spend.rows(study.ledger)
    bisect = bool((spend.latest(entries, "smoke") or {}).get("bisect"))
    first_rungs = available(rows, ladder.LADDER if bisect else ladder.FLAT)
    if not any(n >= ladder.PROBE_TASKS for n in first_rungs.values()):
        raise SystemExit("no rung has four tasks: the task list carries no ladder")
    if lost := incomplete(study, "first"):
        return {"phase": "first", "bisect": bisect, "stop": probe_incomplete(lost)}
    first = step_answer(results(study, "first")[0], first_rungs, bisect)
    if "miss" not in first:
        return {"phase": "first", "bisect": bisect, **first}
    if first["miss"] == "all_hard" and not spend.latest(entries, "transcripts"):
        return {"phase": "first", "bisect": bisect, **first, "await": "read the transcripts, then record-transcripts"}
    if lost := incomplete(study, "extension"):
        return {"phase": "extension", "first": first["miss"], "stop": probe_incomplete(lost)}
    rungs = available(rows, searched_rungs(study, {"first": first["miss"]}))
    then = ladder.next_rung(results(study, "extension")[0], rungs)
    if "miss" in then:
        return {"phase": "extension", "first": first["miss"], "stop": (
            f"the whole ladder missed ({first['miss']} on the probe, {then['miss']} on the extension probe): no "
            "calibration call; the finding goes to the owner (plan, If the whole ladder misses)")}
    return {"phase": "extension", "first": first["miss"], **then}


def probe_incomplete(rungs):
    return (f"probe incomplete: {rungs} kept fewer than {MIN_USABLE} usable runs of {ladder.PROBE_TASKS} after one "
            "relaunch of each incident; no task list, no calibration call; a stop to report to the owner")


def searched_rungs(study, now):
    """The extension's rungs: the easy or the hard extension, by the first probe's miss."""
    return ladder.EASY_EXTENSION if now.get("first") == "all_easy" else ladder.HARD_EXTENSION


def phase_rungs(study, now):
    """The rungs of the answer's phase: the extension's, or the first probe's (flat five, or T0 to T5 bisected)."""
    if now["phase"] == "extension":
        return searched_rungs(study, now)
    return ladder.LADDER if now.get("bisect") else ladder.FLAT


@runner.exclusive  # one study command at a time: a second runner would settle the first one's live runs
def probe(study, rungs=None):
    """Recover what a stopped runner left, then probe the requested rungs (default: the ones the answer asks for
    next): each probe task without a usable run, once, and once more after an incident. A step the redraw
    allowance cannot hold is a stop (review3 minor 8)."""
    spend.authorize("redraw")
    rules.enforce(study, "redraw")
    recover(study)
    rules.enforce(study, "redraw")  # a recovered incident may fire the stop rule
    now = answer(study)
    if "await" in now or "probe" not in now:
        raise SystemExit(f"nothing to probe now: {now}")
    rungs = rungs or now["probe"]
    if set(rungs) - set(now["probe"]):
        raise SystemExit(f"the probe takes {now['probe']} next, not {rungs}")
    rows, spec = task_rows(study), load_arms(study)["direct"]
    fixes, tried = ladder.fix_commits(rows), attempts(study, now["phase"])
    starts = spend.starts(spend.rows(study.ledger))
    def started(task):
        return sum((row["tranche"], row.get("task"), row.get("step")) == ("redraw", task, now["phase"])
                   for row in starts)
    def due(task):  # never started, or every start an incident or a cut with a start left
        n, runs = started(task), tried.get(task, [])
        return n == len(runs) and all(map(ended, runs)) and n < allowed(runs)
    jobs = [(task, rung) for rung in rungs for task in ladder.probe_tasks(rows, rung) if due(task)]
    if (need := spec["max_calls"] * len(jobs)) > (left := spend.remaining(starts, "redraw", "candidate", spec["model"])):
        rules.stop(study, f"the redraw allowance cannot hold the probe step: {need} calls due, {left} left")
    spend.check(study.ledger, "redraw", "candidate", spec["model"], need)
    return runner.run_jobs(jobs, lambda job: probe_run(
        study, spec, *job, fixes[job[0]], now["phase"], limit=started(job[0]) + 1))


def recover(study):
    """Every reserved probe run a stopped runner left: settled (its tree still there) or filed as interrupted, then
    given its hidden check; a run never reserved is removed. Refuses while a launched session still runs."""
    reserved = {row["unit"] for row in spend.starts(spend.rows(study.ledger)) if row["tranche"] == "redraw"}
    fixes = ladder.fix_commits(task_rows(study))
    for path in study_runs(study):
        records, facts = path.parent, load(path)
        if facts["tranche"] != "redraw" or "hidden" in facts or ended(facts):
            continue
        if str(records) not in reserved:  # died between its facts file and its reservation: nothing started
            path.unlink()
            continue
        if units.session_alive(records / "run.pgid"):
            raise SystemExit(f"{records}: its session is still running; wait for it")
        if "calls" not in facts:
            facts = settle_left(study, records, facts, fixes[facts["task"]])
            dump(path, facts)
        if not ended(facts):
            probe_check(study, records, facts)
        print(f"{records}: recovered, {facts.get('incident') or facts.get('outcome')}")


def settle_left(study, records, facts, fix):
    """The facts of a reserved probe run its runner never settled: settled while its tree is there, else an
    incident (interrupted before the settlement, or during the launch)."""
    tree = load(records / "record.json").get("tree")
    facts = (runner.finish(study, records, facts, fix) if tree and Path(tree).exists()
             else facts | {"incident": "interrupted: the runner stopped before the run was settled"})
    if "exit" not in facts and facts.get("outcome") != "completed":
        facts.setdefault("incident", "interrupted: the runner stopped during the launch")
    return facts


def probe_run(study, spec, task, rung, fix, phase, limit=1):
    records, facts = runner.one_run(study, "redraw", "direct", spec, task, fix, limit=limit, step=phase, rung=rung)
    return records, facts if ended(facts) else probe_check(study, records, facts)


def probe_check(study, records, facts):
    """The probe's own figures for a settled run: its hidden set behind the host guard (a set past its bound makes
    the run an incident) and, in-tree, the self-check detector over its transcripts."""
    package = task_dir(study, facts["task"])
    final = facts.get("final_patch")
    facts["hidden"] = (host.hidden_check(package, Path(final), study.runtime, study.host_temp)
                       if facts.get("outcome") == "completed" and final
                       else {"passed": False, "failing": ["no completed final patch"]})
    if facts["hidden"].get("timed_out"):  # neither a pass nor a failure: an incident, relaunched once (re-review N2)
        facts["incident"] = f"host check: {facts['hidden']['timed_out']}"
    home = load(records / "record.json")["sandbox"]["home"]
    facts["self_check"] = (None if (package / "withheld").is_dir()
                           else ladder.self_checked(home, ladder.visible_targets(package)))
    dump(records / "study.json", facts)
    return facts


def probe_readout(study):
    """The probe figures and the answer, recorded; a chosen or split answer writes the 20 tasks once, with the drawn
    set's count per rung. A draw short of 20 is a stop: no list, nothing more starts, the owner is told."""
    now, (first, first_figures), (extension, extension_figures) = (
        answer(study), results(study, "first"), results(study, "extension"))
    share = self_check_share(first_figures)
    out = {"answer": now, "first": first_figures, "extension": extension_figures, "self_check_share": share,
           "counted_on_four": {f"{phase}/{rung}": f["counted_on_four"] for phase, figures in
                               (("first", first_figures), ("extension", extension_figures))
                               for rung, f in figures.items() if "counted_on_four" in f}}
    path, facts = study.results / CHOSEN, {}
    if ("chosen" in now or "split" in now) and not path.is_file():
        draw(study, now, extension if now["phase"] == "extension" else first, share, out)
    if path.is_file():
        out["chosen"], facts = load(path)["tasks"], {"chosen_sha256": sha256_file(path)}
        out["drawn"] = ladder.rung_counts([task["rung"] for task in out["chosen"]])
    spend.record(study.ledger, "probe_readout", answer=now, drawn=out.get("drawn"), **facts)
    if now.get("stop") or out.get("stop"):
        rules.stop(study, now.get("stop") or out["stop"])
    study.results.mkdir(parents=True, exist_ok=True)
    dump(study.results / "probe-readout.json", out)
    print(json.dumps({**now, "drawn": out.get("drawn"), **({"counted_on_four": out["counted_on_four"]}
                                                           if out["counted_on_four"] else {})}))
    return out


def draw(study, now, passes, share, out):
    """Draw the calibration's tasks into `out`; write them when they are 20, else name the stop in `out`."""
    picked = ladder.choose(task_rows(study), now, passes, share, phase_rungs(study, now))
    out["drawn"] = ladder.rung_counts([rung for _, rung in picked])
    if len(picked) < ladder.CALIBRATION_TASKS:
        out["stop"] = (f"the ladder is too short at {out['drawn']}: {len(picked)} tasks after fill and top-up, the "
                       "plan needs 20 at its frozen thresholds; no calibration call; a stop to report to the owner")
        return
    study.results.mkdir(parents=True, exist_ok=True)
    dump(study.results / CHOSEN, {"tasks": [{"id": task, "rung": rung} for task, rung in picked], **out})


def record_transcripts(study, fault, note, runs):
    """After an all-too-hard probe: the transcripts were read; runs a fault failed become incidents."""
    now = answer(study)
    if "await" not in now:
        raise SystemExit(f"no transcript reading is awaited: {now}")
    for records in map(Path, runs):
        facts = load(records / "study.json")
        if (facts["tranche"], facts.get("step")) != ("redraw", "first"):
            raise SystemExit(f"{records} is not a run of the ladder probe")
        dump(records / "study.json", facts | {"incident": f"apparatus fault: {note}"})
    row = spend.record(study.ledger, "transcripts", fault_found=fault, note=note, incidents=[str(r) for r in runs])
    for reason in rules.stop_reasons(study):
        rules.stop(study, reason)
    return row
