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

`probe_readout` records the answer; a chosen or split answer draws the calibration tasks (`ladder.choose`) and,
when they are 20, writes them to `results/calibration-tasks.json` once, with its hash and the per-rung counts in
the ledger, which the calibration's starts require. The calibration runs at 20 tasks with the plan's frozen
thresholds or not at all (coordinator ruling, 2026-11-12): a draw short of 20 after fill and top-up (T4 and T5
together hold 11) records a stop, so no calibration call can start, and goes to the owner.
"""

import json
from pathlib import Path

from experiments.compare.repos import dump, load, sha256_file
from experiments.seed_set import host, ladder, rules, spend
from experiments.seed_set import study as runner
from experiments.seed_set.layout import CHOSEN, load_arms, study_runs, task_dir, task_rows




def results(study, phase):
    """({rung: passes} over rungs whose four probe tasks all have a checked run in `phase`, {rung: figures})."""
    rows, runs = task_rows(study), {}
    for path in study_runs(study):
        facts = load(path)
        if facts["tranche"] == "redraw" and facts.get("step") == phase and "hidden" in facts:
            runs.setdefault(facts["rung"], []).append(facts)
    passes, figures = {}, {}
    for rung, found in runs.items():
        own = [f for f in found if f.get("self_check") is not None]
        figures[rung] = {"runs": len(found), "passes": sum(bool(f["hidden"]["passed"]) for f in found),
                         "incidents": sum("incident" in f for f in found), "in_tree_runs": len(own),
                         "self_checked": sum(bool(f["self_check"]) for f in own)}
        if len(found) >= ladder.PROBE_TASKS == len(ladder.probe_tasks(rows, rung)):
            passes[rung] = figures[rung]["passes"]
    return passes, figures


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
    first = step_answer(results(study, "first")[0], first_rungs, bisect)
    if "miss" not in first:
        return {"phase": "first", "bisect": bisect, **first}
    if first["miss"] == "all_hard" and not spend.latest(entries, "transcripts"):
        return {"phase": "first", "bisect": bisect, **first, "await": "read the transcripts, then record-transcripts"}
    rungs = available(rows, searched_rungs(study, {"first": first["miss"]}))
    then = ladder.next_rung(results(study, "extension")[0], rungs)
    if "miss" in then:
        return {"phase": "extension", "first": first["miss"], "stop": (
            f"the whole ladder missed ({first['miss']} on the probe, {then['miss']} on the extension probe): no "
            "calibration call; the finding goes to the owner (plan, If the whole ladder misses)")}
    return {"phase": "extension", "first": first["miss"], **then}


def searched_rungs(study, now):
    """The extension's rungs: the easy or the hard extension, by the first probe's miss."""
    return ladder.EASY_EXTENSION if now.get("first") == "all_easy" else ladder.HARD_EXTENSION


def phase_rungs(study, now):
    """The rungs of the answer's phase: the extension's, or the first probe's (flat five, or T0 to T5 bisected)."""
    if now["phase"] == "extension":
        return searched_rungs(study, now)
    return ladder.LADDER if now.get("bisect") else ladder.FLAT


def probe(study, rungs=None):
    """Probe the requested rungs (default: the ones the answer asks for next)."""
    spend.authorize("redraw")
    rules.enforce(study, "redraw")
    now = answer(study)
    if "await" in now or "probe" not in now:
        raise SystemExit(f"nothing to probe now: {now}")
    rungs = rungs or now["probe"]
    if set(rungs) - set(now["probe"]):
        raise SystemExit(f"the probe takes {now['probe']} next, not {rungs}")
    rows, spec = task_rows(study), load_arms(study)["direct"]
    fixes, entries = ladder.fix_commits(task_rows(study)), spend.starts(spend.rows(study.ledger))
    jobs = [(task, rung) for rung in rungs for task in ladder.probe_tasks(rows, rung) if not any(
        (row["tranche"], row.get("task"), row.get("step")) == ("redraw", task, now["phase"]) for row in entries)]
    spend.check(study.ledger, "redraw", "candidate", spec["model"], spec["max_calls"] * len(jobs))
    return runner.run_jobs(study, "redraw", jobs, lambda job: probe_run(study, spec, *job, fixes[job[0]],
                                                                        now["phase"]))


def probe_run(study, spec, task, rung, fix, phase):
    records, facts = runner.one_run(study, "redraw", "direct", spec, task, fix, limit=1, step=phase, rung=rung)
    package = task_dir(study, task)
    final = facts.get("final_patch")
    facts["hidden"] = (host.hidden_check(package, Path(final), study.runtime) if facts.get("outcome") == "completed"
                       and final else {"passed": False, "failing": ["no completed final patch"]})
    home = load(records / "record.json")["sandbox"]["home"]
    facts["self_check"] = (None if (package / "withheld").is_dir()
                           else ladder.self_checked(home, ladder.visible_targets(package)))
    dump(records / "study.json", facts)
    return records, facts


def probe_readout(study):
    """The probe figures and the answer, recorded; a chosen or split answer writes the 20 tasks once, with the drawn
    set's count per rung. A draw short of 20 is a stop: no list, nothing more starts, the owner is told."""
    now, (first, first_figures), (extension, extension_figures) = (
        answer(study), results(study, "first"), results(study, "extension"))
    share = self_check_share(first_figures)
    out = {"answer": now, "first": first_figures, "extension": extension_figures, "self_check_share": share}
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
    print(json.dumps({**now, "drawn": out.get("drawn")}))
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
