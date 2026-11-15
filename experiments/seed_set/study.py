"""Seed-set calibration runner (plan `docs/plans/2026-11-11-seed-set-calibration-plan.md`, Steps 1d and 2).

  study.py record-freeze [--reason R]                     the freeze's identity into the ledger (needed before any
                                                          start; `rules.frozen_identity`); after a start, a reason
  study.py probe [--rung R ...]                           the ladder probe (`probing.py`, redraw cap): direct on
                                                          Haiku once on four tasks of each rung the answer asks for
  study.py probe-readout                                  the probe figures and the answer: the next rung, the 20
                                                          chosen calibration tasks (written once), or the stop
  study.py record-transcripts --fault yes|no --note N [RUN ...]  after an all-too-hard probe: transcripts read
  study.py early-look                                     the early judge look on the first three chosen tasks
  study.py candidates --tranche T --arm ARM TASK ...      prepare, launch (two at a time), collect, scan, session
                                                          audit, visible check, metering; delete the agents' tree
  study.py settle RECORDS ...                             settle runs whose runner was interrupted (not probe
                                                          runs: rerunning `probe` recovers those)
  study.py pool --tranche T --kind first|retest TASK ...  one blind pool per task: its usable runs and both anchors
                                                          (once more, from the same records, after a usage limit)
  study.py judge --tranche T --kind first|retest TASK ... both judges one after another; verify-pool; scan; audit
  study.py summarize --kind first|retest TASK ...         summarize.py behind the no-provider stubs; records kept in
                                                          results/pools/<task>-<kind>/ (or its incident); clones gone
  study.py smoke-check                                    the smoke's mechanical checklist, pass or fail, in the ledger
  study.py readout                                        anchors first, then V1-V4, G1-G4, incidents, baselines
  study.py ledger                                         calls reserved and made, and the events
  study.py resume-after-limit --reset T --five-hour P --weekly P --read-at T   reopen starts a usage limit closed
  study.py not-a-limit UNIT --reason R                    the raw result shows no usage limit: the unit is what the
                                                          rules make it (an incident or a failure), its pause goes

`candidates`, `settle`, `pool`, `judge`, `summarize` and `probe` run one at a time per study (`study.lock` beside the
ledger, so ruling R3's two units in flight hold across processes), and each starts by removing every credential
copy in the work and pool roots' private homes that no live unit holds, printing the paths (review3 X5). A
launched unit's whole process tree dies with its launcher however the launcher ends (`reaper.py`).

Run every command from the frozen runtime (`cd <runtime> && PYTHONPATH=$PWD python -m experiments.seed_set.study
--runtime $PWD ...`): the freeze refuses study or harness modules loaded from anywhere else, and a task list
outside the runtime. Every harness step is the harness's own. Every provider start passes `rules.enforce` (freeze, smoke pass, chosen
tasks, a sound ledger, no stop) and `spend.reserve` (authorization, caps, planned runs per task and arm, never
a relaunch), and runs with `COMPARE_MAX_CALLS` at its reservation and `COMPARE_CLAUDE_MODELS` at its exact model;
the harness's resume scripts are disabled (the study never resumes). Candidate code runs on the host only behind
`host.guarded`. A forbidden-model answer, three contaminated tasks or too many incidents record a stop. The spend
ledger is `~/.local/state/seed-set/spend-ledger.jsonl` whatever the paths given. Scan hits are adjudicated by hand
(`prepare.py scan --verdict`); a pool that cannot be summarized (a failed judge, a wrong rating count, a task
without a usable run) is recorded as an incident and costs only its task.

A usage limit (coordinator rulings R1 and R2, 2026-11-14) is neither an incident nor an observation. The unit it
cuts is recorded `cut`, never pooled, never scored and not counted by the incident stop; a `pause` event closes
every start at once (calls in flight finish or are cut) until `resume-after-limit`. Each planned slot whose run was
cut runs again once, as a new unit and from the same cap; a pool with a cut judge is rebuilt once from the same
run records (`<kind>.2`) and judged again by both judges.

Spend in priced tokens (rulings R4 and R5): candidates and judges run the metered template (`programs/providers.json`
and the study's own `programs/judge.providers.json`). Before a start the unit's Claude CLI must be the criterion's
pinned path and version, and `spend.reserve` refuses a start whose worst case would pass the tranche's priced
ceiling; the unit's worst case, times the table's highest tier over its ordinary rate for the model (the runtime
counts every call at the highest tier; review3 X3), goes to the runtime as `--max-cost-usd`. When it ends, its
metered usage priced by the frozen table settles it (a `settle` event).
"""

import argparse
import fcntl
import functools
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from experiments.compare import pool as pooling, prepare, scan, summarize as summary
from experiments.compare.repos import dump, load, sha256_file
from experiments.orc_structural_search import metering
from orchestrator.providers.pricing import load_price_table
from experiments.seed_set import blinding, gates, host, ladder, layout, reaper, readout, rules, selection, spend, units
from experiments.seed_set.layout import (
    PLANNED, RETESTS, WIDTH, Study, chosen, load_arms, load_criterion, require_tasks, study_runs,
    task_dir, task_rows, tranche_tasks,
)

BOUNDARIES = ("dev_check.py", "reset_clone.py")  # copied into the clone and excluded from its patch
JUDGE_PROVIDERS = "judge.providers.json"  # the judges' metered template (ruling R4), beside the programs
INPUTS = ("task", "intent", "repo", "model", "effort")
MAX_POOLS = 2
CALL_SEC, JUDGE_SEC, SLACK_SEC = 1200, 3600, 600  # the programs' and score_functional.orc's :timeout-sec


def launch_env(model, calls, home=None, withheld=None):
    """The environment of a unit's preparation (`home` None: HOME stays, since `prepare` copies the provider's
    credentials from it into the unit's private home) or its launch (`home`, a new empty directory, replaces HOME,
    and CLAUDE_CONFIG_DIR and CODEX_HOME go: the orchestrator and the host-side boundaries it runs, such as
    dev_check.py's pytest of candidate code, see no credentials; review2 minor 2). Neither carries the spend
    switch. `withheld` (a check-withheld run's staged test files) is named for dev_check.py; the agents' sandbox
    clears its environment, so an agent never sees the path."""
    env = {**os.environ, "COMPARE_CLAUDE_MODELS": model, "COMPARE_MAX_CALLS": str(calls)}
    for name in ("SEED_SET_WITHHELD", "PYTHONDONTWRITEBYTECODE", spend.AUTHORIZATION) + (("CLAUDE_CONFIG_DIR", "CODEX_HOME") if home else ()):
        env.pop(name, None)
    if home:
        Path(home).mkdir()
        env["HOME"] = str(home)
    return env | ({"SEED_SET_WITHHELD": str(withheld)} if withheld else {})


def stage_withheld(package, records):
    """A check-withheld package's `withheld/` copied into the run's records directory: outside the agents' tree and
    the sandbox, and a copy, so code the check runs on the host cannot alter the frozen package. None for an
    in-tree package. The programs give the dev-check step no timeout (dev-check.json's 600 s apply inside the
    check, which restores the tree; a test holds this), so the orchestrator never SIGKILLs a check that placed
    the files."""
    source = Path(package) / "withheld"
    return shutil.copytree(source, Path(records) / "withheld") if source.is_dir() else None


def run_jobs(jobs, one):
    with ThreadPoolExecutor(WIDTH) as workers:
        done = list(workers.map(one, jobs))
    for records, facts in done:
        what = facts.get("incident") or ("cut by a usage limit" if "cut" in facts else facts.get("outcome"))
        print(f"{records}: {what}, {facts['calls']} calls")
    return done


def launch(command, env, log, timeout):
    """Run `bash command` under its guard (`reaper.run`), which starts it in a session of its own, writes that
    session's id and start time to `<log>.pgid`, and kills the unit's whole tree, its provider calls' own sessions
    and sandboxes and every orphan included, when the command ends (what is left of it), at the timeout, and
    whenever the launcher ends without the command having ended (an exception, a kill). Return the command's exit
    status, "timeout", or a status saying the guard itself was killed (the launcher then killed the tree)."""
    with open(log, "x") as out:
        return reaper.run(["bash", str(command)], Path(log).with_suffix(".pgid"), timeout, env=env, stdout=out,
                          stderr=subprocess.STDOUT)


@contextmanager
def command_lock(study):
    """One study command that starts, prepares or settles units at a time (coordinator ruling R3 across processes:
    two commands at once would put four units in flight; review3 minor 2)."""
    study.state.mkdir(parents=True, exist_ok=True)
    with open(study.state / "study.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(f"another study command is running on this study ({study.state / 'study.lock'})") from None
        yield


def exclusive(command):
    """A command under `command_lock` that starts by removing the credential copies no live unit holds and the
    host-side checks' temporary directories no live command holds (fix round 3, ruling 3)."""
    @functools.wraps(command)
    def run(study, *args, **kwargs):
        with command_lock(study):
            sweep_credentials(study)
            for path in host.sweep(study.host_temp):
                print(f"removed a host-side check's temporary directory no live command holds: {path}")
            return command(study, *args, **kwargs)
    return run


def sweep_credentials(study):
    """Remove every credential copy in the work root's and the pools' private homes that no live unit holds (a
    launcher killed with SIGKILL runs no `finally`; review3 X5) and print each path removed, never its content."""
    live = {Path(home).resolve() for home in live_homes(study)}
    for home in [*study.work.glob(".private-homes/*"), *study.pools.glob("*/*/.private-homes/*")]:
        for path in [] if home.resolve() in live else units.forget_credentials(home):
            print(f"removed a credential copy no live unit holds: {path}")


def live_homes(study):
    """The private homes of the candidate runs and judges whose launched session still runs."""
    homes = [load(path.parent / "record.json")["sandbox"]["home"] for path in study_runs(study)
             if units.session_alive(path.parent / "run.pgid")]
    for mapping in study.pools.glob("*/*/records/mapping.json"):
        homes += [info["sandbox"]["home"] for judge, info in load(mapping)["judges"].items()
                  if units.session_alive(mapping.parent / f"judge-{judge}.pgid")]
    return homes


@exclusive
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
    planned, limits = slot_limits(study, entries, tranche, arm, tasks)
    jobs = due_jobs(entries, tranche, arm, spec, planned, limits)
    return run_jobs(jobs, lambda task: one_run(study, tranche, arm, spec, task, fixes[task], limit=limits[task]))


def slot_limits(study, entries, tranche, arm, tasks):
    """({task: planned starts of `arm`}, {task: the starts it may have}). A probe run of a chosen package (the same
    id is the same form) that is not an incident is the first of its Haiku direct runs; a planned slot cut by a
    usage limit runs once more, except in the smoke (a cut fails the smoke)."""
    facts = {str(path.parent): load(path) for path in study_runs(study)}
    probed = [f for f in facts.values() if f["tranche"] == "redraw" and "incident" not in f and "cut" not in f]
    planned = {task: PLANNED[tranche][arm] - (sum(f["task"] == task and f["arm"] == arm for f in probed)
                                              if tranche == "calibration" else 0) for task in tasks}
    limits = {task: n + (cut_reruns(entries, facts, tranche, task, arm, n) if tranche != "smoke" else 0)
              for task, n in planned.items()}
    return planned, limits


def due_jobs(entries, tranche, arm, spec, planned, limits):
    """The starts due, one task per start: every planned slot not started (refused unless the cap holds them all),
    then the re-runs of cut slots that the cap's room still holds; a re-run beyond it is left out and its task keeps
    the runs it has (review3 minor 8)."""
    started = {task: sum((row["tranche"], row.get("task"), row.get("arm")) == (tranche, task, arm) for row in entries)
               for task in planned}
    first = [task for task, n in planned.items() for _ in range(max(n - started[task], 0))]
    again = [task for task in planned for _ in range(limits[task] - max(planned[task], started[task]))]
    left = spend.remaining(entries, tranche, "candidate", spec["model"])
    if spec["max_calls"] * len(first) > left:
        raise SystemExit(f"{tranche} candidate {spec['model']}: {spec['max_calls'] * len(first)} calls planned but "
                         f"{left} of the cap remain")
    room = (left - spec["max_calls"] * len(first)) // spec["max_calls"]
    for task in again[room:]:
        print(f"{tranche} {arm} on {task}: no room in the cap to run a cut slot again; the task keeps the runs it has")
    return first + again[:room]


def cut_reruns(entries, facts, tranche, task, arm, planned):
    """How many of the first `planned` starts of (tranche, task, arm) a usage limit cut: each such slot runs again
    once (a re-run comes after them, so a cut re-run adds none). `facts` maps a unit to its study.json."""
    units_ = [row["unit"] for row in entries if (row["tranche"], row.get("task"), row.get("arm")) == (tranche, task, arm)]
    return sum("cut" in facts.get(unit, {}) for unit in units_[:planned])


def boundaries(study, cand):
    for name in BOUNDARIES:
        shutil.copyfile(study.programs / name, cand / name)
    with (cand / ".git" / "info" / "exclude").open("a") as exclude:
        exclude.write("".join(f"/{name}\n" for name in BOUNDARIES))


def one_run(study, tranche, arm, spec, task, fix, limit, **extra):
    """Prepare one run, reserve it (at most `limit` starts of its tranche, task, arm and step), launch it, settle
    it; return (records, the facts in its study.json). `extra` facts (a probe's step and rung) join them."""
    spend.refuse_closed(spend.rows(study.ledger))  # after a usage limit or a stop, no clone is built for nothing
    rules.require_free(study, study.work)
    env, programs = launch_env(spec["model"], spec["max_calls"]), study.programs
    arm_spec = prepare.ArmSpec(programs / spec["source"], spec["entry"], programs, programs / "providers.json",
                               INPUTS, command_boundaries=programs / "commands.json")
    records = prepare.run_arm(task_dir(study, task), arm, study.work, study.runtime, spec=arm_spec,
                              sets=(f"model={spec['model']}", f"effort={spec['effort']}"), environment=env)
    units.disable_resume(records / "resume.sh")
    record = load(records / "record.json")
    if record["claude_model"] != spec["model"]:
        shutil.rmtree(record["tree"])
        units.forget_credentials(record["sandbox"]["home"])
        raise SystemExit(f"{records}: prepared for {record['claude_model']}, not {spec['model']}; nothing started")
    try:  # the unit's copied credentials go however it ends (review2 minor 7, coordinator ruling)
        return records, start_run(study, tranche, arm, spec, task, fix, limit, records, record, extra)
    finally:
        units.forget_credentials(record["sandbox"]["home"])


def start_run(study, tranche, arm, spec, task, fix, limit, records, record, extra):
    boundaries(study, Path(record["candidates"][0]))
    env = launch_env(spec["model"], spec["max_calls"], records / "host-home",
                     withheld=stage_withheld(task_dir(study, task), records))
    facts = {"tranche": tranche, "task": task, "arm": arm, "model": spec["model"], "effort": spec["effort"],
             "max_calls": spec["max_calls"], **extra}
    dump(records / "study.json", facts)  # before the reservation: every reserved run has its facts file
    try:
        rules.require_order(study, tranche)  # per unit: an edit in the middle of a batch refuses (review3 minor 6)
        ceiling, per_call, pin = layout.spend_terms(study, tranche, spec["model"])
        cli = rules.check_cli(record["sandbox"]["declaration"], pin)
        units.cap_command(records / "command.sh", spec["max_calls"] * per_call * rules.tier_ratio(study, spec["model"]))
        spend.reserve(study.ledger, tranche, "candidate", spec["model"], spec["max_calls"], records,
                      limit=limit, price=(ceiling, per_call), task=task, arm=arm, cli=cli, **extra)
    except SystemExit:
        (records / "study.json").unlink()  # refused: nothing started, nothing left on disk
        shutil.rmtree(record["tree"])
        raise
    facts["exit"] = launch(records / "command.sh", env, records / "run.log", spec["max_calls"] * CALL_SEC + SLACK_SEC)
    pause_on_limit(study, records, str(records))  # before the settlement's collect, scan and check (review3 minor 1)
    dump(records / "study.json", facts)
    return finish(study, records, facts, fix)


def finish(study, records, facts, fix):
    facts |= settle(study, records, task_dir(study, facts["task"]), fix, facts["max_calls"], facts["model"],
                    facts.get("exit"))
    facts["priced"] = settle_price(study, str(records), records, facts["tranche"], facts["model"])
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
    out = provider_end(study, records, str(records), out)
    reason, policy, sessions = units.audit_sessions(record["sandbox"]["home"], record["tree"], made, model)
    out["sessions"] = len(sessions)
    if policy:
        rules.stop(study, f"forbidden model in {records}: {policy}")
    if reason:  # a failed audit is an incident, cut or not
        out = {key: value for key, value in out.items() if key != "cut"} | {"incident": f"session audit: {reason}"}
    if out.get("outcome") == "completed" and "final" in collected["patches"]:
        out["final_patch"] = str(records / collected["patches"]["final"])
        out["visible"] = host.visible_check(task, Path(out["final_patch"]), study.runtime, study.host_temp)
    receipt = metering.receipts(records, tree=Path(record["tree"]), since=record["created_at"],
                                home=Path(record["sandbox"]["home"]))
    dump(records / "metering.json", receipt)
    out["metering_complete"] = receipt["consumption"] != metering.UNAVAILABLE
    if Path(record["state_root"]).is_dir():
        shutil.copytree(record["state_root"], records / "state")
    shutil.rmtree(record["tree"])
    units.forget_credentials(record["sandbox"]["home"])  # the transcripts stay for the audits (review2 minor 7)
    return out


def settle_price(study, unit, calls_root, tranche, model):
    """The unit's metered usage priced by the runtime's frozen price table, recorded as its `settle` event. A price
    above the unit's reserved worst case is flagged and closes every start with a `pause` (review3 minor 3): the
    per-call worst case was too low, and the tranche's priced total may pass its ceiling by the excess."""
    per_call = layout.spend_terms(study, tranche, model)[1]
    priced = units.priced(calls_root, load_price_table(study.runtime / rules.PRICE_TABLE), per_call)
    reserved = next((row["usd_reserved"] for row in spend.starts(spend.rows(study.ledger)) if row["unit"] == unit),
                    None)
    over = reserved is not None and priced["usd"] > reserved
    spend.record(study.ledger, "settle", unit=unit, **priced, **({"over_reserved": True} if over else {}))
    if over:
        spend.record(study.ledger, "pause", unit=unit, reset=None, reason=f"a unit settled above its worst case "
                     f"(USD {priced['usd']:g} against USD {reserved:g})")
    return priced


def pause_on_limit(study, calls_root, unit):
    """The unit's usage limit (`units.usage_limit`, flagged when its shape is not the recorded one) or None; its
    `pause` event, which closes every start at once, is recorded once per unit."""
    limit = units.usage_limit(calls_root)
    if limit and not any(row.get("event") == "pause" and row.get("unit") == unit for row in spend.rows(study.ledger)):
        spend.record(study.ledger, "pause", unit=unit, **limit)
    return limit


def provider_end(study, calls_root, unit, out):
    """The provider's own ending of a unit: a usage limit cuts it (not an incident, not an observation) and closes
    every start (`pause_on_limit`); paid extra usage on calls that ended normally only closes them, and the unit
    stays an observation; the incident a cut sets aside is kept in the cut, for `not_a_limit`. Any other
    provider error ends a failed unit as an incident (`provider_error`)."""
    if pause_on_limit(study, calls_root, unit):
        if not (limit := units.usage_limit(calls_root, cutting=True)):  # paid extra usage on normal ends: paused only
            return provider_error(calls_root, out)
        aside = {"incident": out["incident"]} if "incident" in out else {}
        return {key: value for key, value in out.items() if key != "incident"} | {"cut": limit | aside}
    return provider_error(calls_root, out)


def provider_error(calls_root, out):
    """A failed run whose calls show a provider error (`units.provider_incident`) is an incident."""
    if out.get("outcome") == "failed" and "incident" not in out and (why := units.provider_incident(calls_root)):
        out["incident"] = f"provider: {why}"
    return out


@exclusive
def not_a_limit(study, unit, reason):
    """The operator's decision, after reading the raw result, that a usage-limit pause was no usage limit
    (re-review n3). The settled unit is no longer `cut` but what the rules then make it: the incident its cut set
    aside, an incident when it failed with a provider error, else what its outcome says (a natural failure scores
    0). The decision and the reason go to the ledger, and that pause no longer closes starts; nothing runs again
    (a unit that is not cut has no re-run). Taken only while the pause is open, and never for a pause whose rule
    is a shape the kit knows is a real limit (`units.RECORDED`, `units.PAID`; final scoped check n10). A unit not
    yet settled refuses with the way out (`spend.UNSETTLED`)."""
    if not reason.strip():
        raise SystemExit("not-a-limit needs the operator's reason: what the raw result shows")
    if (rule := spend.limit_pause(spend.rows(study.ledger), unit)["rule"]) in (units.RECORDED, units.PAID):
        raise SystemExit(f"{unit} was paused by {rule}, a shape the kit knows is a real limit: not-a-limit cannot "
                         "withdraw it; `resume-after-limit` after the reset, with the owner's meter reading")
    path, calls_root = unit_files(unit)
    if not path.is_file() or "calls" not in load(path):
        raise SystemExit(f"{unit} is not settled ({spend.UNSETTLED})")
    if "not_a_limit" not in (facts := load(path)):  # a decision whose ledger row a crash lost is not applied twice
        dump(path, uncut(facts, calls_root) | {"not_a_limit": reason})
    row = spend.not_a_limit(study.ledger, unit, reason)
    for why in rules.stop_reasons(study):
        rules.stop(study, why)
    return row


def unit_files(unit):
    """(facts file, calls root) of a ledger unit: a run's records directory, or `<pool>#<judge>`."""
    pool, _, judge = str(unit).partition("#")
    if judge:
        return Path(pool) / "records" / f"study-{judge}.json", Path(pool) / "records" / "judges" / judge
    return Path(unit) / "study.json", Path(unit)


def uncut(facts, calls_root):
    """A unit's facts once its cut is withdrawn: the incident the cut set aside comes back, and a failed run whose
    calls show a provider error becomes an incident."""
    aside = (facts.get("cut") or {}).get("incident")
    out = {key: value for key, value in facts.items() if key != "cut"}
    if aside and "incident" not in out:
        out["incident"] = aside
    return provider_error(calls_root, out)


@exclusive
def settle_runs(study, runs):
    """Settle runs whose runner stopped after launching them (their study.json has no settled facts). A probe run
    is recovered by rerunning `probe`, which also gives it its hidden check."""
    fixes = ladder.fix_commits(task_rows(study))
    for records in map(Path, runs):
        facts = load(records / "study.json")
        if facts["tranche"] == "redraw":
            raise SystemExit(f"{records} is a probe run: rerun `probe`, which recovers it")
        if units.session_alive(records / "run.pgid"):  # review3 X6
            raise SystemExit(f"{records}: its session is still running; wait for it")
        if "calls" in facts or not Path(load(records / "record.json")["tree"]).exists():
            raise SystemExit(f"{records} is already settled")
        print(f"{records}: {finish(study, records, facts, fixes[facts['task']]).get('outcome')}")


def live_pools(study):
    return [path for path in study.pools.glob("*/*") if (path / "clones").exists()]


def retire(out):
    """Delete a pool's clones and any credential copy left in its judges' homes (its records stay: the audit and the
    ledger name its judges)."""
    (out / "clones").chmod(0o755)
    shutil.rmtree(out / "clones")
    units.forget_credentials(out / ".private-homes")


def probe_only(tranche):
    if tranche == "redraw":
        raise SystemExit("the redraw cap serves the ladder probe only: it builds no pool and runs no judge")


def pool_incident(study, task, kind, reason, failed_judges=()):
    dest = study.results / "pools" / f"{task}-{kind}"
    dest.mkdir(parents=True)
    dump(dest / "incident.json", {"reason": reason, "failed_judges": list(failed_judges)})
    print(f"POOL INCIDENT {task}/{kind}: {reason}")


def pool_to_build(study, task, kind):
    """Where `pool` builds (task, kind): the first pool, or once its rebuild when a usage limit cut one of its judges
    (the cut pool's clones go first; its records stay). A pool built or rebuilt before, or ended as an incident,
    refuses."""
    out = layout.current_pool(study, task, kind)
    if out.exists() and layout.cut_judges(out) and out.name == kind:
        if (out / "clones").exists():
            retire(out)
        out = out.with_name(kind + layout.REBUILT)
    if out.exists() or (study.results / "pools" / f"{task}-{kind}").exists():
        raise SystemExit(f"{out} exists or ended as an incident; a pool is built once (and rebuilt once after a usage "
                         "limit)")
    return out


@exclusive
def build_pools(study, tranche, kind, tasks):
    """One pool per task from its collected, scanned runs that are not incidents; both anchors join the batch."""
    probe_only(tranche)
    require_tasks(study, tranche, tasks, kind)
    load_criterion(study)
    for task in dict.fromkeys(tasks):
        out = pool_to_build(study, task, kind)
        rules.require_free(study, study.pools)
        if len(live_pools(study)) >= MAX_POOLS:
            raise SystemExit(f"two pools still hold clones ({live_pools(study)}); summarize one first")
        runs = [path.parent for path in study_runs(study) if (facts := load(path))["task"] == task
                and "scan_hits" in facts and "incident" not in facts and "cut" not in facts]
        out.parent.mkdir(parents=True, exist_ok=True)
        try:  # each judge on the study's own metered providers file (the harness's binds the plain template)
            pooling.pool(task_dir(study, task), study.criterion, out,
                         [f"{judge}={study.programs / JUDGE_PROVIDERS}" for judge in gates.JUDGES], runs)
        except SystemExit as error:  # e.g. every run failed: the task's runs still count, its anchors are missing
            shutil.rmtree(out, ignore_errors=True)
            pool_incident(study, task, kind, f"not pooled: {error}")
            continue
        units.forget_credentials(out / ".private-homes")  # a judge copies its own at launch (one_judge)
        units.disable_resume(*(out / "records").glob("resume-*.sh"))
        hits = blinding.scan_pool(out, task_dir(study, task), blinding.identity_tokens(study, load_arms(study), runs))
        dump(out / "records" / "identity-scan.json", {"hits": hits})
        if hits:  # refused before any judge call; nothing is scrubbed
            pool_incident(study, task, kind, f"arm-identifying text in judged content: {hits[:3]}")
            retire(out)
            shutil.rmtree(out)


@exclusive
def judge(study, tranche, kind, tasks):
    """Each pool's judges one after another, each reserved before launch; verify-pool, scan and audit after each.
    Every named pool must hold an identity scan with no hit before the first judge launches (review2 M5)."""
    spend.authorize(tranche)
    probe_only(tranche)
    fixes = require_tasks(study, tranche, tasks, kind)
    rules.enforce(study, tranche)
    rules.require_early_look(study, tranche, kind, tasks)
    pools = [out for task in dict.fromkeys(tasks) if (out := layout.current_pool(study, task, kind)).exists()]
    require_clean_scans(pools)
    skipped = [why for task in dict.fromkeys(tasks) if (why := judge_pool(study, tranche, kind, task, pools, fixes))]
    if skipped:  # the other named pools were judged (review3 minor 7)
        raise SystemExit("no judge started on " + "; ".join(skipped))


def require_clean_scans(pools):
    """Every named pool holds an identity scan with no hit before the first judge launches (review2 M5)."""
    for out in pools:
        scan = out / "records" / "identity-scan.json"
        if not scan.exists() or load(scan).get("hits") != []:
            raise SystemExit(f"{out}: no clean identity scan ({scan}); no judge is launched")


def judge_pool(study, tranche, kind, task, pools, fixes):
    """Launch the task's pool's judges not yet started, one after another; the reason none may start, or None."""
    out = layout.current_pool(study, task, kind)
    if out not in pools or layout.cut_judges(out):
        print(f"{out}: no pool (see its incident), or a judge cut by a usage limit (`pool` rebuilds it once); "
              "no judge")
        return None
    mapping = load(out / "records" / "mapping.json")
    if why := judge_blocked(study, tranche, out, len(mapping["batches"])):
        return f"{out}: {why}"
    for model in gates.JUDGES:
        if any(row.get("unit") == f"{out}#{model}" for row in spend.rows(study.ledger)):
            print(f"{out}#{model}: already started, not relaunched")
            continue
        one_judge(study, tranche, kind, task, out, mapping, model, fixes[task])
    return None


def judge_blocked(study, tranche, out, batches):
    """Why none of a pool's judges may start now, or None: a judge that started and never settled (its pool is an
    incident at summarize, so the other judge would spend for nothing), or a cap without room for every judge the
    pool still needs."""
    entries = spend.rows(study.ledger)
    started = [model for model in gates.JUDGES if any(row.get("unit") == f"{out}#{model}" for row in entries)]
    if unsettled := [model for model in started if not (out / "records" / f"study-{model}.json").is_file()]:
        return f"judge {unsettled} started and never settled: summarize the pool (an incident)"
    if full := [model for model in gates.JUDGES if model not in started
                and spend.remaining(entries, tranche, "judge", model) < batches]:
        return f"no room in the {tranche} judge cap of {full} for both judges"
    return None


def one_judge(study, tranche, kind, task, out, mapping, model, fix):
    batches, records = len(mapping["batches"]), out / "records"
    rules.require_order(study, tranche)  # per unit (review3 minor 6)
    pooling.verify_pool(out)
    judged = blinding.judged_patches(out, mapping)  # what this judge reads, bound to its ratings in the readout
    ceiling, per_call, pin = layout.spend_terms(study, tranche, model)
    cli = rules.check_cli(mapping["judges"][model]["sandbox"]["declaration"], pin)
    units.cap_command(records / f"score-{model}.sh", batches * per_call * rules.tier_ratio(study, model))
    spend.reserve(study.ledger, tranche, "judge", model, batches, f"{out}#{model}", price=(ceiling, per_call),
                  task=task, pool=kind, cli=cli)
    start, home = time.time(), mapping["judges"][model]["sandbox"]["home"]
    units.copy_credentials(home)  # the pool keeps none; the judge's own home holds them for its launch only
    try:
        facts = {"judged_patches": judged, "exit": launch(records / f"score-{model}.sh", launch_env(
            model, batches, records / f"host-home-{model}"), records / f"judge-{model}.log",
            batches * JUDGE_SEC + SLACK_SEC)}
    finally:
        units.forget_credentials(home)
    limit = pause_on_limit(study, records / "judges" / model, f"{out}#{model}")  # before anything else (minor 1)
    facts |= {"wall_clock_sec": time.time() - start, "calls": units.physical_calls(records / "judges" / model)}
    facts["priced"] = settle_price(study, f"{out}#{model}", records / "judges" / model, tranche, model)
    if limit:  # the pool is rebuilt once; its task is not lost
        facts["cut"] = limit
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
            if facts.is_file() and ({"incident", "cut"} & set(load(facts))):
                raise SystemExit(load(facts).get("incident") or "cut by a usage limit")
            summary.join(*summary.scoring_run(out, name, info, sha), mapping["batches"], summary.criteria_of(mapping),
                         summary.reference_paths(out, mapping))
        except (SystemExit, OSError, KeyError, ValueError, TypeError):
            failed.append(name)
    return failed


@exclusive
def summarize_pools(study, kind, tasks):
    """summarize.py per pool behind the guard, then keep its records and delete its clones. A pool it refuses is an
    incident naming the judges that failed; only its task loses its numbers."""
    load_criterion(study)
    for task in dict.fromkeys(tasks):
        out = layout.current_pool(study, task, kind)
        dest = study.results / "pools" / f"{task}-{kind}"
        if dest.exists():
            raise SystemExit(f"{dest} exists; a pool is summarized once")
        if layout.cut_judges(out) and out.name == kind:
            raise SystemExit(f"{out}: {layout.cut_judges(out)} cut by a usage limit; after resume-after-limit, `pool` "
                             "rebuilds it once from the same records")
        failed = failed_judges(out, study.criterion)
        try:
            if failed:
                raise SystemExit(f"judge run failed: {failed}")
            host.summarize(out, study.criterion, study.host_temp)
        except SystemExit as error:
            pool_incident(study, task, kind, str(error), failed)
            shutil.copyfile(out / "records" / "mapping.json", dest / "mapping.json")
        else:
            dest.mkdir(parents=True)
            for path in [out / "records" / n for n in ("results.json", "results.md", "mapping.json",
                                                       "identity-scan.json")] + sorted((out / "records").glob("study-*.json")):
                shutil.copyfile(path, dest / path.name)
            shutil.copytree(out / "records" / "patches", dest / "patches")
        retire(out)


def judged_of(directory):
    """{judge: {clone id: sha256 of the patch it read}} from a summarized pool's study-<judge>.json files."""
    return {path.stem.removeprefix("study-"): load(path).get("judged_patches", {})
            for path in directory.glob("study-*.json")}


def load_records(study, models, tasks):
    """Records of every summarized pool (results.json and its pooled patches) with each pool incident, plus every
    run that no first pool holds: a natural failure (a failed outcome or a timeout) or an incident."""
    records, pools = [], []
    for directory in sorted((study.results / "pools").glob("*-*")):
        found, info = summarized_pool(directory, models)
        records += found
        pools.append(info)
    pooled = {r["run"] for r in records if r["pool"] == "first"}
    facts = {str(path.parent): load(path) for path in study_runs(study)}
    return records + unpooled_runs(facts, pooled, tasks), pools


def summarized_pool(directory, models):
    """(records, pool info) of one summarized pool directory; an incident pool has no records."""
    task, kind = directory.name.rsplit("-", 1)
    if (directory / "incident.json").is_file():
        incident = load(directory / "incident.json")
        return [], {"task": task, "pool": kind, "incident": incident["reason"],
                    "excluded_judges": dict.fromkeys(incident["failed_judges"], "judge_failed")}
    results = load(directory / "results.json")
    hashes = {cid: sha256_file(directory / "patches" / f"{cid}.diff") for cid in results["clones"]}
    return gates.pool_records(task, kind, results, hashes, models, judged_of(directory))


def unpooled_runs(facts, pooled, tasks):
    """A record for every calibration run of `tasks` that no first pool holds: a natural failure (a failed outcome
    or a timeout) or an incident. A run cut by a usage limit is no observation (R1)."""
    records = []
    for run, row in facts.items():
        if run not in pooled and row["tranche"] != "smoke" and row["task"] in tasks and "cut" not in row:
            failed = "incident" not in row and (row.get("outcome") == "failed" or row.get("exit") == "timeout")
            records.append({"task": row["task"], "pool": "first", "role": "candidate", "arm": row["arm"],
                            "model": row["model"], "run": run, "patch": None, "hidden": None, "scores": {},
                            "status": "failed" if failed else "incident", "reason": row.get("incident")})
    return records


def write_readout(study):
    arms = load_arms(study)
    models = {name: arm["model"] for name, arm in arms.items()}
    programs = {name: {"source": arm["source"], "lines": selection.program_lines(study.programs / arm["source"])}
                for name, arm in arms.items()}
    tasks = tranche_tasks(study, "calibration")
    retests, rungs = tasks[:RETESTS["calibration"]], ladder.rung_counts([task["rung"] for task in chosen(study)])
    records, pools = load_records(study, models, tasks)
    runs = {str(path.parent): load(path) | {"wall_clock_sec": load(path.parent / "record.json").get(
        "wall_clock_sec")} for path in study_runs(study)}
    runs = {run: facts for run, facts in runs.items() if facts["task"] in tasks}  # probe runs of other tasks out
    report = readout.report(records, pools, tasks, retests, rungs, runs, spend.totals(study.ledger), programs,
                            rules.planned_runs(study, "calibration"))
    report["priced_usd"] = spend.priced(study.ledger)
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
    totals["priced_usd"] = spend.priced(study.ledger)
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
    for name in ("smoke-check", "probe-readout", "early-look", "readout", "ledger"):
        sub.add_parser(name)
    sub.add_parser("record-freeze").add_argument("--reason", help="needed once a start exists: the apparatus fix")
    sub.add_parser("probe").add_argument("--rung", action="append", help="repeatable; default: the readout's next")
    limit = sub.add_parser("resume-after-limit", help="reopen the starts a usage limit closed (coordinator ruling R2)")
    limit.add_argument("--reset", type=iso_time, required=True, help="the reset the vendor's answer named, ISO 8601 "
                       "with its zone (2026-11-14T08:00:00Z)")
    limit.add_argument("--five-hour", type=float, required=True, help="the owner's five-hour meter, percent used")
    limit.add_argument("--weekly", type=float, required=True, help="the owner's weekly meter, percent used")
    limit.add_argument("--read-at", type=iso_time, required=True, help="when the owner read both meters, ISO 8601")
    withdrawn = sub.add_parser("not-a-limit", help="record that a usage-limit pause's raw result shows no limit")
    withdrawn.add_argument("unit", help="the pause's unit: a run's records directory, or <pool>#<judge>")
    withdrawn.add_argument("--reason", required=True, help="what the raw result shows")
    transcripts = sub.add_parser("record-transcripts")
    transcripts.add_argument("--fault", choices=("yes", "no"), required=True)
    transcripts.add_argument("--note", required=True)
    transcripts.add_argument("runs", nargs="*", help="records directories of runs a fault failed: incidents")
    return top


def iso_time(text):
    """Epoch seconds of an ISO 8601 time that names its zone."""
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise argparse.ArgumentTypeError(f"{text!r} names no zone (2026-11-14T08:00:00Z)")
    return moment.timestamp()


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
        "record-freeze": lambda: print(json.dumps(rules.record_freeze(study, a.reason))),
        "smoke-check": lambda: print(json.dumps(rules.smoke_check(study), indent=2)),
        "probe": lambda: probing.probe(study, a.rung),
        "probe-readout": lambda: print(json.dumps(probing.probe_readout(study), indent=2)),
        "record-transcripts": lambda: print(json.dumps(probing.record_transcripts(study, a.fault == "yes", a.note,
                                                                                  a.runs))),
        "early-look": lambda: print(json.dumps(rules.early_look(study), indent=2)),
        "readout": lambda: write_readout(study),
        "ledger": lambda: ledger_report(study),
        "resume-after-limit": lambda: print(json.dumps(spend.resume_after_limit(
            study.ledger, a.reset, a.five_hour, a.weekly, a.read_at))),
        "not-a-limit": lambda: print(json.dumps(not_a_limit(study, a.unit, a.reason))),
    }
    commands[a.command]()


if __name__ == "__main__":
    main()
