"""Seed-set calibration runner (plan `docs/plans/2026-11-11-seed-set-calibration-plan.md`, Steps 1d and 2).

  study.py record-freeze                                  hashes of criterion.json, judge-calibration.json and the
                                                          runtime commit into the ledger (needed before any start)
  study.py probe [--rung R ...]                           the ladder probe (`probing.py`, redraw cap): direct on
                                                          Haiku once on four tasks of each rung the answer asks for
  study.py probe-readout                                  the probe figures and the answer: the next rung, the 20
                                                          chosen calibration tasks (written once), or the stop
  study.py record-transcripts --fault yes|no --note N [RUN ...]  after an all-too-hard probe: transcripts read
  study.py early-look                                     the early judge look on the first three chosen tasks
  study.py candidates --tranche T --arm ARM TASK ...      prepare, launch (four at a time), collect, scan, session
                                                          audit, visible check, metering; delete the agents' tree
  study.py settle RECORDS ...                             settle runs whose runner was interrupted
  study.py pool --tranche T --kind first|retest TASK ...  one blind pool per task: its usable runs and both anchors
  study.py judge --tranche T --kind first|retest TASK ... both judges one after another; verify-pool; scan; audit
  study.py summarize --kind first|retest TASK ...         summarize.py behind the no-provider stubs; records kept in
                                                          results/pools/<task>-<kind>/ (or its incident); clones gone
  study.py smoke-check                                    the smoke's mechanical checklist, pass or fail, in the ledger
  study.py readout                                        anchors first, then V1-V4, G1-G4, incidents, baselines
  study.py ledger                                         calls reserved and made, and the events

Every harness step is the harness's own. Every provider start passes `rules.enforce` (freeze, smoke pass, chosen
tasks, a sound ledger, no stop) and `spend.reserve` (authorization, caps, planned runs per task and arm, never
a relaunch), and runs with `COMPARE_MAX_CALLS` at its reservation and `COMPARE_CLAUDE_MODELS` at its exact model;
the harness's resume scripts are disabled (the study never resumes). Candidate code runs on the host only behind
`host.guarded`. A forbidden-model answer, three contaminated tasks or too many incidents record a stop. The spend
ledger is `~/.local/state/seed-set/spend-ledger.jsonl` whatever the paths given. Scan hits are adjudicated by hand
(`prepare.py scan --verdict`); a pool that cannot be summarized (a failed judge, a wrong rating count, a task
without a usable run) is recorded as an incident and costs only its task.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from experiments.compare import pool as pooling, prepare, scan, summarize as summary
from experiments.compare.repos import dump, load, sha256_file
from experiments.orc_structural_search import metering
from experiments.seed_set import blinding, gates, host, readout, rules, selection, spend, units
from experiments.seed_set.layout import (
    PLANNED, RETESTS, Study, chosen, load_arms, load_criterion, require_free, require_tasks, study_runs,
    task_dir, task_rows, tranche_tasks,
)

BOUNDARIES = ("dev_check.py", "reset_clone.py")  # copied into the clone and excluded from its patch
INPUTS = ("task", "intent", "repo", "model", "effort")
WIDTH, FIRST_WAVE, MAX_POOLS = 4, 2, 2  # a tranche's first wave runs two at a time
CALL_SEC, JUDGE_SEC, SLACK_SEC = 1200, 3600, 600  # the programs' and score_functional.orc's :timeout-sec


def launch_env(model, calls, withheld=None):
    """The launch environment. `withheld` (a check-withheld run's staged test files) is named for dev_check.py,
    which runs on the host as a command boundary and inherits the controller's environment; the agents' sandbox
    clears its environment, so an agent never sees the path."""
    env = {**os.environ, "COMPARE_CLAUDE_MODELS": model, "COMPARE_MAX_CALLS": str(calls),
           "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("SEED_SET_WITHHELD", None)
    return env | ({"SEED_SET_WITHHELD": str(withheld)} if withheld else {})


def stage_withheld(package, records):
    """A check-withheld package's `withheld/` copied into the run's records directory: outside the agents' tree and
    the sandbox, and a copy, so code the check runs on the host cannot alter the frozen package. None for an
    in-tree package. The programs give the dev-check step no timeout (dev-check.json's 600 s apply inside the
    check, which restores the tree; a test holds this), so the orchestrator never SIGKILLs a check that placed
    the files."""
    source = Path(package) / "withheld"
    return shutil.copytree(source, Path(records) / "withheld") if source.is_dir() else None


def waves(jobs, started):
    """The jobs in launch waves: a tranche's first wave (no run of it started yet) two at a time."""
    return [(FIRST_WAVE, jobs[:FIRST_WAVE]), (WIDTH, jobs[FIRST_WAVE:])] if not started else [(WIDTH, jobs)]


def run_jobs(study, tranche, jobs, one):
    started = any(load(path)["tranche"] == tranche for path in study_runs(study))
    done = []
    for width, wave in waves(jobs, started):
        with ThreadPoolExecutor(width) as workers:
            done += list(workers.map(one, wave))
    for records, facts in done:
        print(f"{records}: {facts.get('incident') or facts.get('outcome')}, {facts['calls']} calls")
    return done


def launch(command, env, log, timeout):
    """Run `bash command` in its own session; return its exit status, or "timeout" after killing the session."""
    with open(log, "x") as out:
        process = subprocess.Popen(["bash", str(command)], env=env, stdout=out, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return "timeout"
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            raise


def candidates(study, tranche, arm, tasks):
    """Launch the planned runs of `arm` not yet started on each task, four at a time (the first wave two)."""
    spend.authorize(tranche)
    if tranche == "redraw":
        raise SystemExit("the redraw cap serves the ladder probe only: use `probe`")
    tasks = list(dict.fromkeys(tasks))
    fixes = require_tasks(study, tranche, tasks)
    if arm not in PLANNED[tranche]:
        raise SystemExit(f"{tranche} runs {sorted(PLANNED[tranche])}, not {arm}")
    rules.enforce(study, tranche)
    spec, entries = load_arms(study)[arm], spend.starts(spend.rows(study.ledger))
    def started(task, where):
        return sum((row["tranche"], row.get("task"), row.get("arm")) == (where, task, arm) for row in entries)

    # a probe run of a chosen package (the same id is the same form) is the first of its Haiku direct runs
    limits = {task: PLANNED[tranche][arm] - (started(task, "redraw") if tranche == "calibration" else 0)
              for task in tasks}
    jobs = [task for task in tasks for _ in range(limits[task] - started(task, tranche))]
    spend.check(study.ledger, tranche, "candidate", spec["model"], spec["max_calls"] * len(jobs))
    return run_jobs(study, tranche, jobs, lambda task: one_run(study, tranche, arm, spec, task, fixes[task],
                                                               limit=limits[task]))


def boundaries(study, cand):
    for name in BOUNDARIES:
        shutil.copyfile(study.programs / name, cand / name)
    with (cand / ".git" / "info" / "exclude").open("a") as exclude:
        exclude.write("".join(f"/{name}\n" for name in BOUNDARIES))


def one_run(study, tranche, arm, spec, task, fix, limit, **extra):
    """Prepare one run, reserve it (at most `limit` starts of its tranche, task, arm and step), launch it, settle
    it; return (records, the facts in its study.json). `extra` facts (a probe's step and rung) join them."""
    require_free(study, study.work)
    env, programs = launch_env(spec["model"], spec["max_calls"]), study.programs
    arm_spec = prepare.ArmSpec(programs / spec["source"], spec["entry"], programs, programs / "providers.json",
                               INPUTS, command_boundaries=programs / "commands.json")
    records = prepare.run_arm(task_dir(study, task), arm, study.work, study.runtime, spec=arm_spec,
                              sets=(f"model={spec['model']}", f"effort={spec['effort']}"), environment=env)
    units.disable_resume(records / "resume.sh")
    record = load(records / "record.json")
    if record["claude_model"] != spec["model"]:
        shutil.rmtree(record["tree"])
        raise SystemExit(f"{records}: prepared for {record['claude_model']}, not {spec['model']}; nothing started")
    boundaries(study, Path(record["candidates"][0]))
    env = launch_env(spec["model"], spec["max_calls"], stage_withheld(task_dir(study, task), records))
    facts = {"tranche": tranche, "task": task, "arm": arm, "model": spec["model"], "effort": spec["effort"],
             "max_calls": spec["max_calls"], **extra}
    dump(records / "study.json", facts)  # before the reservation: every reserved run has its facts file
    try:
        spend.reserve(study.ledger, tranche, "candidate", spec["model"], spec["max_calls"], records,
                      limit=limit, task=task, arm=arm, **extra)
    except SystemExit:
        (records / "study.json").unlink()  # refused: nothing started, nothing left on disk
        shutil.rmtree(record["tree"])
        raise
    facts["exit"] = launch(records / "command.sh", env, records / "run.log", spec["max_calls"] * CALL_SEC + SLACK_SEC)
    dump(records / "study.json", facts)
    return records, finish(study, records, facts, fix)


def finish(study, records, facts, fix):
    facts |= settle(study, records, task_dir(study, facts["task"]), fix, facts["max_calls"], facts["model"],
                    facts.get("exit"))
    dump(records / "study.json", facts)
    for reason in rules.stop_reasons(study):
        rules.stop(study, reason)
    return facts


def settle(study, records, task, fix, cap, model, status):
    """Collect and scan the run, audit its sessions, run the visible check on its final patch behind the guard,
    record metering, keep the run state and delete the agents' tree. A run the harness cannot collect, a provider
    error and a failed session audit are incidents; a run that outlived its wall clock is a natural failure."""
    made, record = units.physical_calls(records), load(records / "record.json")
    if made > cap:
        raise SystemExit(f"{records}: {made} provider calls exceed the {cap} reserved; stop")
    out = {"calls": made}
    try:
        collected = prepare.collect(records)
        out |= {"outcome": collected["outcome"], "failure": collected["failure"],
                "scan_hits": len(prepare.scan(records, fix))}
    except SystemExit as error:
        out |= ({"outcome": "failed", "failure": {"code": "wall_clock_timeout"}} if status == "timeout"
                else {"incident": str(error)})
    if out.get("outcome") == "failed" and (why := units.provider_incident(records)):
        out["incident"] = f"provider: {why}"
    reason, policy, sessions = units.audit_sessions(record["sandbox"]["home"], record["tree"], made, model)
    out["sessions"] = len(sessions)
    if policy:
        rules.stop(study, f"forbidden model in {records}: {policy}")
    if reason:
        out["incident"] = f"session audit: {reason}"
    if out.get("outcome") == "completed" and "final" in collected["patches"]:
        out["final_patch"] = str(records / collected["patches"]["final"])
        out["visible"] = host.visible_check(task, Path(out["final_patch"]), study.runtime)
    receipt = metering.receipts(records, tree=Path(record["tree"]), since=record["created_at"],
                                home=Path(record["sandbox"]["home"]))
    dump(records / "metering.json", receipt)
    out["metering_complete"] = receipt["consumption"] != metering.UNAVAILABLE
    if Path(record["state_root"]).is_dir():
        shutil.copytree(record["state_root"], records / "state")
    shutil.rmtree(record["tree"])
    return out


def settle_runs(study, runs):
    """Settle runs whose runner stopped after launching them (their study.json has no settled facts)."""
    fixes = {row["id"]: row["commit"] for row in task_rows(study)}
    for records in map(Path, runs):
        facts = load(records / "study.json")
        if "calls" in facts or not Path(load(records / "record.json")["tree"]).exists():
            raise SystemExit(f"{records} is already settled")
        print(f"{records}: {finish(study, records, facts, fixes[facts['task']]).get('outcome')}")


def live_pools(study):
    return [path for path in study.pools.glob("*/*") if (path / "clones").exists()]


def pool_incident(study, task, kind, reason, failed_judges=()):
    dest = study.results / "pools" / f"{task}-{kind}"
    dest.mkdir(parents=True)
    dump(dest / "incident.json", {"reason": reason, "failed_judges": list(failed_judges)})
    print(f"POOL INCIDENT {task}/{kind}: {reason}")


def build_pools(study, tranche, kind, tasks):
    """One pool per task from its collected, scanned runs that are not incidents; both anchors join the batch."""
    require_tasks(study, tranche, tasks, kind)
    load_criterion(study)
    for task in dict.fromkeys(tasks):
        out = study.pools / task / kind
        if out.exists():
            raise SystemExit(f"{out} exists; a pool is built once")
        require_free(study, study.pools)
        if len(live_pools(study)) >= MAX_POOLS:
            raise SystemExit(f"two pools still hold clones ({live_pools(study)}); summarize one first")
        runs = [path.parent for path in study_runs(study) if (facts := load(path))["task"] == task
                and "scan_hits" in facts and "incident" not in facts]
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            pooling.pool(task_dir(study, task), study.criterion, out, list(gates.JUDGES), runs)
        except SystemExit as error:  # e.g. every run failed: the task's runs still count, its anchors are missing
            shutil.rmtree(out, ignore_errors=True)
            pool_incident(study, task, kind, f"not pooled: {error}")
            continue
        units.disable_resume(*(out / "records").glob("resume-*.sh"))
        hits = blinding.scan_pool(out, task_dir(study, task), blinding.identity_tokens(study, load_arms(study), runs))
        dump(out / "records" / "identity-scan.json", {"hits": hits})
        if hits:  # refused before any judge call; nothing is scrubbed
            pool_incident(study, task, kind, f"arm-identifying text in judged content: {hits[:3]}")
            (out / "clones").chmod(0o755)
            shutil.rmtree(out)


def judge(study, tranche, kind, tasks):
    """Each pool's judges one after another, each reserved before launch; verify-pool, scan and audit after each."""
    spend.authorize(tranche)
    fixes = require_tasks(study, tranche, tasks, kind)
    rules.enforce(study, tranche)
    rules.require_early_look(study, tranche, kind, tasks)
    for task in dict.fromkeys(tasks):
        out = study.pools / task / kind
        if not out.exists():
            print(f"{out}: no pool (see its incident), no judge")
            continue
        mapping = load(out / "records" / "mapping.json")
        for model in gates.JUDGES:
            if any(row.get("unit") == f"{out}#{model}" for row in spend.rows(study.ledger)):
                print(f"{out}#{model}: already started, not relaunched")
                continue
            one_judge(study, tranche, kind, task, out, mapping, model, fixes[task])


def one_judge(study, tranche, kind, task, out, mapping, model, fix):
    batches, records = len(mapping["batches"]), out / "records"
    pooling.verify_pool(out)
    judged = blinding.judged_patches(out, mapping)  # what this judge reads, bound to its ratings in the readout
    spend.reserve(study.ledger, tranche, "judge", model, batches, f"{out}#{model}", task=task, pool=kind)
    start = time.time()
    facts = {"judged_patches": judged, "exit": launch(records / f"score-{model}.sh", launch_env(model, batches),
                            records / f"judge-{model}.log", batches * JUDGE_SEC + SLACK_SEC)}
    facts |= {"wall_clock_sec": time.time() - start, "calls": units.physical_calls(records / "judges" / model)}
    if facts["calls"] > batches:
        raise SystemExit(f"{out}#{model}: {facts['calls']} provider calls exceed the {batches} reserved; stop")
    try:
        pooling.verify_pool(out)
        facts["verify_pool"] = "clean"
    except SystemExit as error:  # the clones are restored; the change is evidence for adjudication
        facts["verify_pool"] = str(error)
    hits = pooling.scan_judge(out, model, fix)
    facts["scan_hits"], info = len(hits), mapping["judges"][model]
    if scan.model_policy(hits):
        rules.stop(study, f"forbidden model in judge {model} of {out}")
    home, tree = info["sandbox"]["home"], out / "judges" / info["dir"]
    reason, policy, sessions = units.audit_sessions(home, tree, facts["calls"], model)
    facts["sessions"] = len(sessions)
    if policy:
        rules.stop(study, f"forbidden model in judge {model} of {out}: {policy}")
    if reason:
        facts["incident"] = f"session audit: {reason}"
    dump(records / "judges" / model / "metering.json",
         metering.receipts(records / "judges" / model, tree=tree, since=mapping["created_at"], home=Path(home)))
    dump(records / f"study-{model}.json", facts)
    print(f"{out}#{model}: exit {facts['exit']}, {facts['calls']} calls, {facts['scan_hits']} scan hits")


def failed_judges(out, criterion):
    """The judges whose scoring run summarize.py would refuse (missing, incomplete or misaligned ratings)."""
    mapping, sha = load(out / "records" / "mapping.json"), sha256_file(criterion)
    failed = []
    for name, info in mapping["judges"].items():
        facts = out / "records" / f"study-{name}.json"
        try:
            if facts.is_file() and "incident" in load(facts):
                raise SystemExit(load(facts)["incident"])
            summary.join(*summary.scoring_run(out, name, info, sha), mapping["batches"], summary.criteria_of(mapping),
                         summary.reference_paths(out, mapping))
        except (SystemExit, OSError, KeyError, ValueError, TypeError):
            failed.append(name)
    return failed


def summarize_pools(study, kind, tasks):
    """summarize.py per pool behind the guard, then keep its records and delete its clones. A pool it refuses is an
    incident naming the judges that failed; only its task loses its numbers."""
    load_criterion(study)
    for task in dict.fromkeys(tasks):
        out = study.pools / task / kind
        dest = study.results / "pools" / f"{task}-{kind}"
        if dest.exists():
            raise SystemExit(f"{dest} exists; a pool is summarized once")
        failed = failed_judges(out, study.criterion)
        try:
            if failed:
                raise SystemExit(f"judge run failed: {failed}")
            host.summarize(out, study.criterion)
        except SystemExit as error:
            pool_incident(study, task, kind, str(error), failed)
            shutil.copyfile(out / "records" / "mapping.json", dest / "mapping.json")
        else:
            dest.mkdir(parents=True)
            for path in [out / "records" / n for n in ("results.json", "results.md", "mapping.json",
                                                       "identity-scan.json")] + sorted((out / "records").glob("study-*.json")):
                shutil.copyfile(path, dest / path.name)
            shutil.copytree(out / "records" / "patches", dest / "patches")
        (out / "clones").chmod(0o755)
        shutil.rmtree(out / "clones")


def judged_of(directory):
    """{judge: {clone id: sha256 of the patch it read}} from a summarized pool's study-<judge>.json files."""
    return {path.stem.removeprefix("study-"): load(path).get("judged_patches", {})
            for path in directory.glob("study-*.json")}


def load_records(study, models, tasks):
    """Records of every summarized pool (results.json and its pooled patches) with each pool incident, plus every
    run that no first pool holds: a natural failure (a failed outcome or a timeout) or an incident."""
    records, pools, facts = [], [], {str(path.parent): load(path) for path in study_runs(study)}
    for directory in sorted((study.results / "pools").glob("*-*")):
        task, kind = directory.name.rsplit("-", 1)
        if (directory / "incident.json").is_file():
            incident = load(directory / "incident.json")
            pools.append({"task": task, "pool": kind, "incident": incident["reason"],
                          "excluded_judges": dict.fromkeys(incident["failed_judges"], "judge_failed")})
            continue
        results = load(directory / "results.json")
        hashes = {cid: sha256_file(directory / "patches" / f"{cid}.diff") for cid in results["clones"]}
        found, info = gates.pool_records(task, kind, results, hashes, models, judged_of(directory))
        records += found
        pools.append(info)
    pooled = {r["run"] for r in records if r["pool"] == "first"}
    for run, row in facts.items():
        if run not in pooled and row["tranche"] != "smoke" and row["task"] in tasks:
            failed = "incident" not in row and (row.get("outcome") == "failed" or row.get("exit") == "timeout")
            records.append({"task": row["task"], "pool": "first", "role": "candidate", "arm": row["arm"],
                            "model": row["model"], "run": run, "patch": None, "hidden": None, "scores": {},
                            "status": "failed" if failed else "incident", "reason": row.get("incident")})
    return records, pools


def write_readout(study):
    arms = load_arms(study)
    models = {name: arm["model"] for name, arm in arms.items()}
    programs = {name: {"source": arm["source"], "lines": selection.program_lines(study.programs / arm["source"])}
                for name, arm in arms.items()}
    tasks = tranche_tasks(study, "calibration")
    retests, rungs = tasks[:RETESTS["calibration"]], sorted({task["rung"] for task in chosen(study)})
    records, pools = load_records(study, models, tasks)
    runs = {str(path.parent): load(path) | {"wall_clock_sec": load(path.parent / "record.json").get(
        "wall_clock_sec")} for path in study_runs(study)}
    runs = {run: facts for run, facts in runs.items() if facts["task"] in tasks}  # probe runs of other tasks out
    report = readout.report(records, pools, tasks, retests, rungs, runs, spend.totals(study.ledger), programs,
                            rules.planned_runs(study, "calibration"))
    study.results.mkdir(parents=True, exist_ok=True)
    dump(study.results / "calibration.json", report)
    (study.results / "readout.md").write_text(readout.markdown(report))
    if report["calibration"]:
        decision = report["calibration"]["decision"]
        spend.record(study.ledger, "decision", decision=decision)
        if decision.startswith("stop"):
            rules.stop(study, f"readout: {decision}")
    print(readout.markdown(report), end="")
    return report


def ledger_report(study):
    """Reserved and physical calls per tranche, kind and model, and the events; a breach refuses."""
    rules.audit_ledger(study)
    entries, made = spend.rows(study.ledger), {}
    for row in spend.starts(entries):
        pool, _, model = row["unit"].partition("#")
        key = (row["tranche"], row["kind"], row["model"])
        made[key] = made.get(key, 0) + units.physical_calls(Path(pool) / "records" / "judges" / model if model
                                                            else row["unit"])
    totals = spend.totals(study.ledger)
    for (tranche, kind, model), calls in made.items():
        totals[tranche][kind][model]["made"] = calls
    totals["events"] = [row for row in entries if row["kind"] == "event"]
    print(json.dumps(totals, indent=2))
    return totals


def parser():
    top = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    top.add_argument("--runtime", type=Path, default=Path("/home/ollie/seedset-rt"))
    top.add_argument("--work", type=Path, default=Path("/home/ollie/seedset-work"))
    top.add_argument("--pools", type=Path, default=Path("/home/ollie/seedset-pools"))
    top.add_argument("--results", type=Path, help="default: <runtime>/experiments/seed_set/results")
    top.add_argument("--task-list", type=Path, help="default: <runtime>/experiments/seed_set/tasks.jsonl")
    top.add_argument("--criterion", type=Path, help="default: <runtime>/experiments/seed_set/judge-calibration.json")
    sub = top.add_subparsers(dest="command", required=True)
    for name in ("candidates", "pool", "judge", "summarize"):
        command = sub.add_parser(name)
        if name in ("candidates", "pool", "judge"):
            command.add_argument("--tranche", required=True)
        if name == "candidates":
            command.add_argument("--arm", required=True)
        else:
            command.add_argument("--kind", choices=("first", "retest"), required=True)
        command.add_argument("tasks", nargs="+")
    sub.add_parser("settle").add_argument("runs", nargs="+", help="records directories")
    for name in ("record-freeze", "smoke-check", "probe-readout", "early-look", "readout", "ledger"):
        sub.add_parser(name)
    sub.add_parser("probe").add_argument("--rung", action="append", help="repeatable; default: the readout's next")
    transcripts = sub.add_parser("record-transcripts")
    transcripts.add_argument("--fault", choices=("yes", "no"), required=True)
    transcripts.add_argument("--note", required=True)
    transcripts.add_argument("runs", nargs="*", help="records directories of runs a fault failed: incidents")
    return top


def study_of(a):
    runtime, seed_set = a.runtime.resolve(), a.runtime.resolve() / "experiments" / "seed_set"
    return Study(runtime, a.work.resolve(), a.pools.resolve(), (a.results or seed_set / "results").resolve(),
                 (a.task_list or seed_set / "tasks.jsonl").resolve(),
                 (a.criterion or seed_set / "judge-calibration.json").resolve(), spend.ledger_path().parent)


def main(argv=None):
    from experiments.seed_set import probing  # it builds on this module's launch steps
    a = parser().parse_args(argv)
    study = study_of(a)
    commands = {
        "candidates": lambda: candidates(study, a.tranche, a.arm, a.tasks),
        "settle": lambda: settle_runs(study, a.runs),
        "pool": lambda: build_pools(study, a.tranche, a.kind, a.tasks),
        "judge": lambda: judge(study, a.tranche, a.kind, a.tasks),
        "summarize": lambda: summarize_pools(study, a.kind, a.tasks),
        "record-freeze": lambda: print(json.dumps(rules.record_freeze(study))),
        "smoke-check": lambda: print(json.dumps(rules.smoke_check(study), indent=2)),
        "probe": lambda: probing.probe(study, a.rung),
        "probe-readout": lambda: print(json.dumps(probing.probe_readout(study), indent=2)),
        "record-transcripts": lambda: print(json.dumps(probing.record_transcripts(study, a.fault == "yes", a.note,
                                                                                  a.runs))),
        "early-look": lambda: print(json.dumps(rules.early_look(study), indent=2)),
        "readout": lambda: write_readout(study),
        "ledger": lambda: ledger_report(study),
    }
    commands[a.command]()


if __name__ == "__main__":
    main()
