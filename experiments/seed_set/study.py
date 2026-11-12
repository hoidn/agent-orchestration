"""Seed-set calibration runner (plan `docs/plans/2026-11-11-seed-set-calibration-plan.md`, Steps 1d and 2).

  study.py candidates --tranche T --arm ARM TASK ...      prepare, launch (four at a time), collect, scan, visible
                                                          check, metering; then delete the run's agents' tree
  study.py pool --kind first|retest TASK ...              one blind pool per task: its runs and both anchors
  study.py judge --tranche T --kind first|retest TASK ... both judges one after another; verify-pool; judge scan
  study.py summarize --kind first|retest TASK ...         summarize.py (hidden tests); copy the pool's records to
                                                          results/pools/<task>-<kind>/; delete the pool's clones
  study.py readout                                        anchors first, then V1-V4, G1-G4 and the offline
                                                          re-roll baselines: results/calibration.json, readout.md
  study.py ledger                                         calls reserved and made, per tranche, kind and model

Every harness step is the harness's own (`prepare.run_arm`, `collect`, `scan`, `pool.pool`, `verify_pool`,
`scan_judge`, `summarize.summarize`, `evaluation.check_first_attempt`). Every provider start goes through
`spend.reserve` first (authorization variable, per-tranche caps, never a relaunch) and runs with
`COMPARE_MAX_CALLS` at its reservation and `COMPARE_CLAUDE_MODELS` at its exact model. Every number the readout
prints comes from the pools' `results.json` (copied under results/pools/) and the runs' own files; it refuses
quality numbers when an anchor check fails. Disk: at most four agents' trees and two pools with clones at once;
a run or a pool refuses to start under 20 GB free. Adjudicating scan hits stays a manual `prepare.py scan
--verdict` step: `pool` and `summarize` refuse unadjudicated hits.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from experiments.compare import pool as pooling, prepare, summarize as summary
from experiments.compare.repos import dump, load, sha256_file
from experiments.orc_structural_search import metering
from experiments.orc_structural_search.evaluation import check_first_attempt
from experiments.seed_set import gates, readout, selection, spend

PROGRAMS = Path("experiments/seed_set/programs")  # in the runtime checkout
BOUNDARIES = ("dev_check.py", "reset_clone.py")  # copied into the clone and excluded from its patch
INPUTS = ("task", "intent", "repo", "model", "effort")
EFFORT = "medium"
# runs per task and arm, per tranche (plan Step 2): the smoke runs every program once on the last reserve task
PLANNED = {"smoke": dict.fromkeys(("direct", "direct_sonnet", "retry_until_check", "implement_check_repair",
                                   "implement_review_revise"), 1),
           "calibration": {"direct": 4, "direct_sonnet": 1}, "redraw": {"direct": 4, "direct_sonnet": 1}}
RETESTS = {"smoke": 0, "calibration": 10, "redraw": 5}  # the first tasks of the tranche, in seed order
WIDTH, MAX_POOLS, MIN_FREE = 4, 2, 20 * 10**9
CALL_SEC, JUDGE_SEC, SLACK_SEC = 1200, 3600, 600  # the programs' and score_functional.orc's :timeout-sec
RUBRIC = {"workflow": "score_functional.orc", "entry": "score_functional::score", "criteria": ["quality"],
          "reference": None}


@dataclass(frozen=True)
class Study:
    runtime: Path
    work: Path
    pools: Path
    results: Path
    tasks_file: Path
    criterion: Path
    min_free: int = MIN_FREE

    @property
    def ledger(self):
        return self.results / "spend-ledger.jsonl"

    @property
    def programs(self):
        return self.runtime / PROGRAMS


def task_rows(study):
    return [json.loads(line) for line in study.tasks_file.read_text().splitlines()]


def task_dir(study, task):
    return study.tasks_file.parent / "tasks" / task


def tranche_tasks(rows, tranche):
    """The tasks a tranche may run, in seed order: the last reserve task for the smoke, the other reserve tasks
    for the redraw, the drawn tasks for the calibration."""
    reserve = [row["id"] for row in rows if row["set"] == "reserve"]
    return {"smoke": reserve[-1:], "redraw": reserve[:-1]}.get(
        tranche, [row["id"] for row in rows if row["set"] == "drawn"])


def require_tasks(study, tranche, tasks, kind="first"):
    allowed = tranche_tasks(task_rows(study), tranche)
    if kind == "retest":
        allowed = allowed[:RETESTS[tranche]]
    if not tasks or set(tasks) - set(allowed):
        raise SystemExit(f"{tranche} {kind} takes tasks among {allowed}, not {sorted(set(tasks) - set(allowed))}")
    return {row["id"]: row["commit"] for row in task_rows(study)}


def load_arms(study):
    """arms.json with every model one of the two exact IDs, effort medium and at most three calls."""
    arms = load(study.programs / "arms.json")
    for name, arm in arms.items():
        spend.check_model(arm["model"])
        if arm["effort"] != EFFORT or type(arm["max_calls"]) is not int or not 1 <= arm["max_calls"] <= 3:
            raise SystemExit(f"arms.json {name}: effort must be {EFFORT} and max_calls 1 to 3")
    return arms


def load_criterion(study):
    """The frozen judge-calibration criterion: both judges, the functional rubric, and no calibration purpose or
    block (summarize.py skips hidden tests for purpose "calibration")."""
    value = load(study.criterion)
    if (value.get("purpose") == "calibration" or "calibration" in value or value.get("rubric") != RUBRIC
            or sorted(value.get("judges", [])) != sorted(gates.JUDGES)):
        raise SystemExit(f"{study.criterion}: the judge-calibration criterion names both judges and the functional "
                         "rubric, without a calibration purpose or block")
    return value


def require_free(study, path):
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < study.min_free:
        raise SystemExit(f"stop: {free / 1e9:.1f} GB free under {path}, below {study.min_free / 1e9:.0f} GB")


def launch_env(model, calls):
    return {**os.environ, "COMPARE_CLAUDE_MODELS": model, "COMPARE_MAX_CALLS": str(calls),
            "PYTHONDONTWRITEBYTECODE": "1"}


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


def call_count(records):
    return len(list((Path(records) / "calls").glob("*")))


def study_runs(study):
    """study.json of every run the study reserved, in records order."""
    return sorted(study.work.glob("records/*/run-*/study.json"))


def started(study, tranche, task, arm):
    return sum((row["tranche"], row.get("task"), row.get("arm")) == (tranche, task, arm)
               for row in spend.rows(study.ledger))


def candidates(study, tranche, arm, tasks):
    """Launch the planned runs of `arm` not yet started on each task, four at a time."""
    spend.authorize(tranche)
    fixes = require_tasks(study, tranche, tasks)
    if arm not in PLANNED[tranche]:
        raise SystemExit(f"{tranche} runs {sorted(PLANNED[tranche])}, not {arm}")
    spec = load_arms(study)[arm]
    jobs = [task for task in tasks for _ in range(PLANNED[tranche][arm] - started(study, tranche, task, arm))]
    spend.check(study.ledger, tranche, "candidate", spec["model"], spec["max_calls"] * len(jobs))
    with ThreadPoolExecutor(WIDTH) as workers:
        done = list(workers.map(lambda task: one_run(study, tranche, arm, spec, task, fixes[task]), jobs))
    for records, facts in done:
        print(f"{records}: {facts.get('outcome') or facts.get('incident')}, {facts['calls']} calls")
    return done


def boundaries(study, cand):
    for name in BOUNDARIES:
        shutil.copyfile(study.programs / name, cand / name)
    with (cand / ".git" / "info" / "exclude").open("a") as exclude:
        exclude.write("".join(f"/{name}\n" for name in BOUNDARIES))


def one_run(study, tranche, arm, spec, task, fix):
    """Prepare one run, reserve it, launch it, settle it; return (records, the facts in its study.json)."""
    require_free(study, study.work)
    env, programs = launch_env(spec["model"], spec["max_calls"]), study.programs
    arm_spec = prepare.ArmSpec(programs / spec["source"], spec["entry"], programs, programs / "providers.json",
                               INPUTS, command_boundaries=programs / "commands.json")
    records = prepare.run_arm(task_dir(study, task), arm, study.work, study.runtime, spec=arm_spec,
                              sets=(f"model={spec['model']}", f"effort={spec['effort']}"), environment=env)
    record = load(records / "record.json")
    if record["claude_model"] != spec["model"]:
        shutil.rmtree(record["tree"])
        raise SystemExit(f"{records}: prepared for {record['claude_model']}, not {spec['model']}; nothing started")
    boundaries(study, Path(record["candidates"][0]))
    facts = {"tranche": tranche, "task": task, "arm": arm, "model": spec["model"], "effort": spec["effort"],
             "max_calls": spec["max_calls"]}
    dump(records / "study.json", facts)  # before the reservation: every reserved run has its facts file
    try:
        spend.reserve(study.ledger, tranche, "candidate", spec["model"], spec["max_calls"], records, task=task, arm=arm)
    except SystemExit:
        (records / "study.json").unlink()  # refused: nothing started, nothing left on disk
        shutil.rmtree(record["tree"])
        raise
    facts["exit"] = launch(records / "command.sh", env, records / "run.log", spec["max_calls"] * CALL_SEC + SLACK_SEC)
    facts |= settle(study, records, task_dir(study, task), fix, spec["max_calls"])
    dump(records / "study.json", facts)
    return records, facts


def settle(study, records, task, fix, cap):
    """Collect and scan the run, run the visible check on its final patch, record metering, keep the run state
    and delete the agents' tree. A run the harness cannot collect is an incident, recorded with its reason."""
    calls = call_count(records)
    if calls > cap:
        raise SystemExit(f"{records}: {calls} provider calls exceed the {cap} reserved; stop")
    record, out = load(records / "record.json"), {"calls": calls}
    try:
        collected = prepare.collect(records)
        out |= {"outcome": collected["outcome"], "scan_hits": len(prepare.scan(records, fix))}
    except SystemExit as error:
        out["incident"] = str(error)
    else:
        if "final" in collected["patches"]:
            out["visible"] = check_first_attempt(task, records / collected["patches"]["final"], study.runtime)
    receipt = metering.receipts(records, tree=Path(record["tree"]), since=record["created_at"],
                                home=Path(record["sandbox"]["home"]))
    dump(records / "metering.json", receipt)
    out["metering_complete"] = receipt["consumption"] != metering.UNAVAILABLE
    if Path(record["state_root"]).is_dir():
        shutil.copytree(record["state_root"], records / "state")
    shutil.rmtree(record["tree"])
    return out


def live_pools(study):
    return [path for path in study.pools.glob("*/*") if (path / "clones").exists()]


def build_pools(study, tranche, kind, tasks):
    """One pool per task from all its collected runs; both anchors join the batch (pool.pool)."""
    require_tasks(study, tranche, tasks, kind)
    load_criterion(study)
    for task in tasks:
        out = study.pools / task / kind
        if out.exists():
            raise SystemExit(f"{out} exists; a pool is built once")
        require_free(study, study.pools)
        if len(live_pools(study)) >= MAX_POOLS:
            raise SystemExit(f"two pools still hold clones ({live_pools(study)}); summarize one first")
        runs = [path.parent for path in study_runs(study)
                if load(path)["task"] == task and "outcome" in load(path)]
        if not runs:
            raise SystemExit(f"{task}: no collected run to pool")
        out.parent.mkdir(parents=True, exist_ok=True)
        pooling.pool(task_dir(study, task), study.criterion, out, list(gates.JUDGES), runs)


def judge(study, tranche, kind, tasks):
    """Each pool's judges one after another, each reserved before launch; verify-pool and scan after each."""
    spend.authorize(tranche)
    fixes = require_tasks(study, tranche, tasks, kind)
    for task in tasks:
        out = study.pools / task / kind
        batches = len(load(out / "records" / "mapping.json")["batches"])
        for model in gates.JUDGES:
            unit = f"{out}#{model}"
            if any(row["unit"] == unit for row in spend.rows(study.ledger)):
                print(f"{unit}: already started, not relaunched")
                continue
            pooling.verify_pool(out)
            spend.reserve(study.ledger, tranche, "judge", model, batches, unit, task=task, pool=kind)
            records = out / "records"
            facts = {"exit": launch(records / f"score-{model}.sh", launch_env(model, batches),
                                    records / f"judge-{model}.log", batches * JUDGE_SEC + SLACK_SEC)}
            facts["calls"] = call_count(records / "judges" / model)
            if facts["calls"] > batches:
                raise SystemExit(f"{unit}: {facts['calls']} provider calls exceed the {batches} reserved; stop")
            try:
                pooling.verify_pool(out)
                facts["verify_pool"] = "clean"
            except SystemExit as error:  # the clones are restored; the change is evidence for adjudication
                facts["verify_pool"] = str(error)
            facts["scan_hits"] = len(pooling.scan_judge(out, model, fixes[task]))
            dump(records / f"study-{model}.json", facts)
            print(f"{unit}: exit {facts['exit']}, {facts['calls']} calls, {facts['scan_hits']} scan hits")


def summarize_pools(study, kind, tasks):
    """summarize.py per pool (hidden tests on every clone), then keep its records and delete its clones."""
    load_criterion(study)
    for task in tasks:
        out = study.pools / task / kind
        dest = study.results / "pools" / f"{task}-{kind}"
        if dest.exists():
            raise SystemExit(f"{dest} exists; a pool is summarized once")
        summary.summarize(out, study.criterion)
        dest.mkdir(parents=True)
        for name in ("results.json", "results.md", "mapping.json"):
            shutil.copyfile(out / "records" / name, dest / name)
        shutil.copytree(out / "records" / "patches", dest / "patches")
        (out / "clones").chmod(0o755)
        shutil.rmtree(out / "clones")


def load_records(study, models):
    """Records of every summarized pool (results.json and its pooled patches), plus every reserved run that no
    first pool holds: failed (a failed outcome or a timeout) or an incident."""
    records, pools = [], []
    for directory in sorted((study.results / "pools").glob("*-*")):
        task, kind = directory.name.rsplit("-", 1)
        results = load(directory / "results.json")
        hashes = {cid: sha256_file(directory / "patches" / f"{cid}.diff") for cid in results["clones"]}
        found, info = gates.pool_records(task, kind, results, hashes, models)
        records += found
        pools.append(info)
    pooled = {r["run"] for r in records if r["pool"] == "first"}
    for path in study_runs(study):
        facts, run = load(path), str(path.parent.resolve())
        if run not in pooled:
            failed = facts.get("outcome") == "failed" or facts.get("exit") == "timeout"
            records.append({"task": facts["task"], "pool": "first", "role": "candidate", "arm": facts["arm"],
                            "model": facts["model"], "run": run, "patch": None, "hidden": None, "scores": {},
                            "status": "failed" if failed else "incident", "reason": facts.get("incident")})
    return records, pools


def calibration_tasks(study):
    """(tasks, retest tasks, redrawn): the drawn tasks and any redraw tasks, in seed order."""
    rows = task_rows(study)
    drawn = tranche_tasks(rows, "calibration")
    used = {load(path)["task"] for path in study_runs(study) if load(path)["tranche"] == "redraw"}
    redraw = [task for task in tranche_tasks(rows, "redraw") if task in used]
    return drawn + redraw, drawn[:RETESTS["calibration"]] + redraw[:RETESTS["redraw"]], bool(redraw)


def write_readout(study):
    arms = load_arms(study)
    models = {name: arm["model"] for name, arm in arms.items()}
    programs = {name: {"source": arm["source"], "lines": selection.program_lines(study.programs / arm["source"])}
                for name, arm in arms.items()}
    tasks, retests, redrawn = calibration_tasks(study)
    records, pools = load_records(study, models)
    runs = {str(path.parent.resolve()): load(path) | {"wall_clock_sec": load(path.parent / "record.json").get(
        "wall_clock_sec")} for path in study_runs(study)}
    report = readout.report(records, pools, tasks, retests, redrawn, runs, spend.totals(study.ledger), programs)
    study.results.mkdir(parents=True, exist_ok=True)
    dump(study.results / "calibration.json", report)
    (study.results / "readout.md").write_text(readout.markdown(report))
    print(readout.markdown(report), end="")
    return report


def ledger_report(study):
    """Reserved and physical calls per tranche, kind and model; a physical count above a reservation is a breach."""
    made = {}
    for row in spend.rows(study.ledger):
        pool, _, model = row["unit"].partition("#")
        calls = call_count(Path(pool) / "records" / "judges" / model if model else row["unit"])
        key = (row["tranche"], row["kind"], row["model"])
        made[key] = made.get(key, 0) + calls
        if calls > row["calls"]:
            raise SystemExit(f"{row['unit']}: {calls} calls made, {row['calls']} reserved")
    totals = spend.totals(study.ledger)
    for (tranche, kind, model), calls in made.items():
        totals[tranche][kind][model]["made"] = calls
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
    sub.add_parser("readout")
    sub.add_parser("ledger")
    return top


def study_of(a):
    runtime, seed_set = a.runtime.resolve(), a.runtime.resolve() / "experiments" / "seed_set"
    return Study(runtime, a.work.resolve(), a.pools.resolve(), (a.results or seed_set / "results").resolve(),
                 (a.task_list or seed_set / "tasks.jsonl").resolve(),
                 (a.criterion or seed_set / "judge-calibration.json").resolve())


def main(argv=None):
    a = parser().parse_args(argv)
    study = study_of(a)
    if a.command == "candidates":
        candidates(study, a.tranche, a.arm, a.tasks)
    elif a.command == "pool":
        build_pools(study, a.tranche, a.kind, a.tasks)
    elif a.command == "judge":
        judge(study, a.tranche, a.kind, a.tasks)
    elif a.command == "summarize":
        summarize_pools(study, a.kind, a.tasks)
    elif a.command == "readout":
        write_readout(study)
    else:
        ledger_report(study)


if __name__ == "__main__":
    main()
