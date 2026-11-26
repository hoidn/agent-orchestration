"""Zero-spend rehearsal of the seed-set calibration (plan Step 2) on the real task packages: the smoke, `smoke-check`,
the flat ladder probe and its readout, the calibration tranche (candidates, the early judge look, every first and
retest pool with both judges, summaries with hidden tests) and the readout with the judge gate and task gates,
then one implement-check-repair run on a real check-withheld package through a real orchestrator launch.

Every provider is the scripted `claude` of tests/experiments/seed_set_offline_support.py (its scripted `codex` for
a unit the Codex CLI runs) behind the comparison harness's real shims, sandbox and model guard; no model is called.
The criterion pins those stand-ins, one per CLI (path and version), and sets the rehearsal's priced ceilings
(`TERMS`); the rehearsal's tranches hold no Luna call. The ladder probe meets one injected usage
limit: the stand-in answers the first probe task's Haiku call as the vendor does at a limit, starts close, the
limit is lifted, `resume-after-limit` reopens them and the probe runs the cut slot again (rulings R1 and R2), every
call that succeeds then printing a limit warning on stderr, which must close nothing (re-review N1). After
the probe one start that would pass the redraw tranche's priced ceiling is tried on the rehearsal's ledger (R4).
With `--cut-in smoke` the limit cuts the smoke's Haiku `direct` run instead: the other programs run after the
resume, the smoke check must fail, and the rehearsal ends after showing that neither the probe nor the calibration
may start (review3 X1). In the calibration the stand-in Sonnet's code on the first task makes one hidden test hang
past the kit's bound on one hidden test (fix round 3, ruling 1): the test must count as failed and the task's pools
be summarised (`hidden_hang`). The process runs with an empty HOME, no provider credentials (a stand-in login file per
CLI holds only the expiry every start checks), a closed PATH behind the Thread M no-provider stubs, and a ledger under
ROOT/state (the study's own ledger is never opened). The stand-in fixes T1 and T2 always, every second T3 task (two of
the four probe tasks), never T4 or T5; Sonnet fixes everything; on the smoke task Haiku fixes from its second attempt.

  PATH=<checkout>/experiments/thread_m/no_provider:$PATH PYTHONPATH=<checkout> \
      python -m experiments.seed_set.rehearsal ROOT [--calibration-tasks N] [--cut-in probe|smoke]
      # ROOT: new; about two hours at 20 calibration tasks

The setup makes ROOT/runtime, a worktree of this checkout's HEAD, and runs the stages from it (working directory
and PYTHONPATH): the freeze refuses study modules loaded from anywhere else. The agents' trees and the pools live
in a private directory under the harness tests' sandbox-visible cache (the sandbox binds its own /tmp), with the
stand-in CLI and its plan, named in ROOT/study.json and deleted at the end; ROOT itself may be under /tmp. `--calibration-tasks N` runs the calibration stage on the first N chosen
tasks only (the readout then reports the missing ones as missing).

Writes ROOT/rehearsal.json (ledger totals per tranche, the smoke check, the probe answer, the readout's decision
and gates, identity-scan hits, binding failures, the clones' build order, the withheld run) and prints it.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from experiments.compare.repos import dump, load
from experiments.seed_set import ladder, layout, probing, reaper, rules, spend, study, units
from tests.agent_session_shims import closed_path
from tests.experiments.compare_harness_support import OUTSIDE_SANDBOX_MOUNTS, open_up, write_test_sandbox_config
from tests.experiments.seed_set_offline_support import (
    CODEX_STUB, STUB, stand_in_codex_login, stand_in_login, stand_in_terms,
)

CHECKOUT = Path(__file__).resolve().parents[2]
GUARD = CHECKOUT / "experiments" / "thread_m" / "no_provider"
H, S, L = spend.HAIKU, spend.SONNET, spend.LUNA
WITHHELD_TASK = "12ea8483f0-withheld"  # a real T3w package for the withheld launch
# the rehearsal's priced ceilings and worst cases (the stand-in prices Haiku at USD 0.0036 and Sonnet at 0.067 a call)
TERMS = {"ceiling_usd": {"smoke": 10.0, "redraw": 3.0, "calibration": 40.0, layout.LUNA_SMOKE: 10.0},
         "per_call_usd": {H: 0.25, S: 1.0, L: 0.5}, "largest_call_usd": {H: 0.0036, S: 0.067, L: 0.016}}


def git(*args):
    subprocess.run(["git", *map(str, args)], check=True, capture_output=True)


def haiku_fix(rung, index, task, smoke):
    """The stand-in Haiku's first fixing attempt on a package (None: never)."""
    if task == smoke or task == WITHHELD_TASK:
        return 2
    if rung.rstrip("w") in ("T0", "T1", "T2"):
        return 1
    return 1 if rung.rstrip("w") == "T3" and index % 2 == 0 else None


def stand_in_plan(rows, tasks):
    smoke = next(row["id"] for row in rows if row["set"] == "smoke")
    found = [(smoke, "T2", 0)] + [(p["id"], p["rung"], k) for rung in ladder.LADDER + ladder.EASY_EXTENSION
                                  for k, p in enumerate(q for q in ladder.packages(rows) if q["rung"] == rung)]
    entries = {}
    for task, rung, index in found:
        package = tasks / task
        config = load(package / "seed" / "dev-check.json")
        entries[task] = {"marker": (package / "task.txt").read_text().strip(),
                         "patch": (package / "anchors" / f"{task}-upstream.diff").read_text(),
                         "visible": [sys.executable, "-c", ""] if config.get("withheld") else config["argv"],
                         "fix": {H: haiku_fix(rung, index, task, smoke), S: 1, L: haiku_fix(rung, index, task, smoke)}}
    # the stub takes the first marker in its prompt: a T0 statement holds its T1 statement, so longest first
    return {"tasks": dict(sorted(entries.items(), key=lambda item: -len(item[1]["marker"])))}


def install_stand_ins(fakebin, home):
    """The stand-in `claude` and `codex` as executables in `fakebin`, and in `home` a stand-in login per CLI: the
    expiry every unit's start reads (rulings R16 and L-R3), no real token."""
    for name, stub in (("claude", STUB), ("codex", CODEX_STUB)):
        (fakebin / name).write_text(stub)
        (fakebin / name).chmod(0o755)
    stand_in_login(home / ".claude")
    stand_in_codex_login(home / ".codex")


def setup(root):
    root.mkdir()
    OUTSIDE_SANDBOX_MOUNTS.mkdir(parents=True, exist_ok=True)
    outside = Path(tempfile.mkdtemp(dir=OUTSIDE_SANDBOX_MOUNTS))  # what the sandbox must see: not under /tmp
    main, runtime, home, fakebin = root / "main", root / "runtime", root / "home", outside / "fakebin"
    head = subprocess.run(["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()
    git("clone", "-q", "--shared", "--no-checkout", CHECKOUT, main)
    git("-C", main, "worktree", "add", "-q", "--detach", runtime, head)  # the committed runner and packages
    for directory in (home, fakebin, root / "freeze"):
        directory.mkdir()
    install_stand_ins(fakebin, home)
    tasks_file = runtime / "experiments" / "seed_set" / "tasks.jsonl"
    plan = outside / "stub-plan.json"
    dump(plan, stand_in_plan([json.loads(line) for line in tasks_file.read_text().splitlines()],
                             tasks_file.parent / "tasks"))
    os.environ.update(PATH=f"{GUARD}{os.pathsep}{closed_path(fakebin)}", HOME=str(home),
                      CODEX_HOME=str(home / ".codex"), CLAUDE_CONFIG_DIR=str(home / ".claude"),
                      SEED_SET_STUB_PLAN=str(plan))
    os.environ["COMPARE_SANDBOX"] = str(write_test_sandbox_config(  # discovered against the empty HOME
        fakebin, root / "sandbox.json", readonly_files=(plan,), environment_names=("SEED_SET_STUB_PLAN",)))
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_OAUTH_TOKEN_FILE", spend.AUTHORIZATION):
        os.environ.pop(key, None)
    criterion = root / "freeze" / "judge-calibration.json"
    dump(criterion, {"judges": [H, S], "rubric": layout.RUBRIC, "primary": [], "secondary": []})
    dump(root / "study.json", {"work": str(outside / "work"), "pools": str(outside / "pools"), "outside": str(outside)})
    s = study_at(root)
    dump(s.frozen, {"sha256": rules.required_hashes(s), "rehearsal": "stand-in providers only",
                    "spend": stand_in_terms(fakebin, **TERMS)})
    return s


def study_at(root):
    paths, runtime = load(root / "study.json"), root / "runtime"
    return layout.Study(runtime, Path(paths["work"]), Path(paths["pools"]), root / "results",
                        runtime / "experiments" / "seed_set" / "tasks.jsonl", root / "freeze" / "judge-calibration.json",
                        root / "state")


def tranche(name):
    os.environ[spend.AUTHORIZATION] = name


def pools(s, name, kind, tasks):
    for task in tasks:  # one pool on disk at a time
        study.build_pools(s, name, kind, [task])
        study.judge(s, name, kind, [task])
        if layout.current_pool(s, task, kind).exists():
            study.summarize_pools(s, kind, [task])


def luna_smoke(s):
    """The Luna smoke (ruling L-R8 of the Luna plan), staged as `smoke` is: its two Luna arms on the smoke task, its
    pool and one Haiku judge, the summary and its `smoke-check`."""
    tranche(layout.LUNA_SMOKE)
    (task,) = layout.tranche_tasks(s, layout.LUNA_SMOKE)
    for arm in layout.PLANNED[layout.LUNA_SMOKE]:
        study.candidates(s, layout.LUNA_SMOKE, arm, [task])
    pools(s, layout.LUNA_SMOKE, layout.LUNA_POOL, [task])
    return rules.smoke_check(s, layout.LUNA_SMOKE)


def smoke(s):
    tranche("smoke")
    (task,) = layout.tranche_tasks(s, "smoke")
    for arm in layout.PLANNED["smoke"]:
        study.candidates(s, "smoke", arm, [task])
    pools(s, "smoke", "first", [task])
    return rules.smoke_check(s)


def calibration(s, count, pids):
    tranche("calibration")
    tasks = layout.tranche_tasks(s, "calibration")[:count]
    hung = hang_one_hidden_test(s, tasks[0], pids)
    for arm in layout.PLANNED["calibration"]:
        study.candidates(s, "calibration", arm, tasks)
    relaunch = study.candidates(s, "calibration", "direct", tasks)  # every planned run started: nothing
    pools(s, "calibration", "first", tasks[:rules.EARLY_TASKS])
    look = rules.early_look(s)
    pools(s, "calibration", "first", tasks[rules.EARLY_TASKS:])
    pools(s, "calibration", "retest", tasks[:layout.RETESTS["calibration"]])
    beyond = "not tried: fewer than 20 tasks"
    if count == ladder.CALIBRATION_TASKS:
        try:
            spend.reserve(s.ledger, "calibration", "judge", H, 1, "/rehearsal/one-more-judge-call",
                          price=layout.spend_terms(s, "calibration", H)[:2])
            beyond = "reserved"
        except SystemExit as error:
            beyond = str(error)
    stand_in(Path(os.environ["SEED_SET_STUB_PLAN"]), conftest_sleep=None)
    return {"relaunched": len(relaunch), "early_look": look["passed"], "judge_beyond_cap": beyond,
            "hidden_hang": hang_result(s, *hung, pids)}


HANG_SEC = 300  # past host.HIDDEN_TEST_SEC (240 s), inside the 600 s backstop of a clone


def hang_one_hidden_test(s, task, pids):
    """The stand-in Sonnet's code on `task` makes one of its hidden tests (the second, past the check's first pytest)
    sleep `HANG_SEC` in host-side checks; returns (task, the test's node id)."""
    nodes = [line.strip() for line in (layout.task_dir(s, task) / "hidden_tests.txt").read_text().splitlines()
             if "::" in line]
    node = nodes[min(1, len(nodes) - 1)]
    pids.mkdir(mode=0o700)
    stand_in(Path(os.environ["SEED_SET_STUB_PLAN"]), conftest_sleep={"seconds": HANG_SEC, "pids": str(pids),
                                                                       "task": task, "model": S, "node": node})
    return task, node


def hang_result(s, task, node, pids):
    """Per pool of `task`: summarised with the Sonnet clone's failing hidden tests, or its incident; how many times
    the test hung, and the hanging processes still alive (none is due)."""
    pools = {}
    for directory in sorted((s.results / "pools").glob(f"{task}-*")):
        pools[directory.name] = ({"sonnet_hidden_failed": [c["hidden_failed"] for c in load(directory / "results.json")[
            "clones"].values() if c["arm"] == "direct_sonnet"]} if (directory / "results.json").is_file()
            else {"incident": load(directory / "incident.json")["reason"]})
    hung = [int(name) for name in os.listdir(pids)]
    return {"task": task, "node": node, "pools": pools, "times_hung": len(hung),
            "still_running": [pid for pid in hung if reaper.stat(pid)]}


def usage_limit(plan_file, limit):
    """Set (or lift, with {}) the stand-in's usage limit in its plan, in place: the sandbox binds the same file."""
    stand_in(plan_file, usage_limit=limit)


def stand_in(plan_file, **values):
    """Set keys of the stand-in's plan, in place."""
    Path(plan_file).write_text(json.dumps(load(plan_file) | values))


def refusal(start):
    """The refusal `start` meets, or "started"."""
    try:
        start()
    except SystemExit as error:
        return str(error)
    return "started"


def smoke_with_a_cut(s):
    """The smoke meeting one usage limit on its Haiku `direct` run: cut, starts closed, lifted, reopened; the other
    programs run and the pool is judged. The check must fail, and neither the probe nor the calibration may start."""
    tranche("smoke")
    (task,) = layout.tranche_tasks(s, "smoke")
    plan_file, reset = Path(os.environ["SEED_SET_STUB_PLAN"]), int(time.time())
    usage_limit(plan_file, {"task": task, "model": H, "reset": reset})
    study.candidates(s, "smoke", "direct", [task])
    closed = refusal(lambda: study.candidates(s, "smoke", "direct_sonnet", [task]))
    usage_limit(plan_file, {})
    spend.resume_after_limit(s.ledger, reset, 0.0, 0.0, time.time())
    for arm in [arm for arm in layout.PLANNED["smoke"] if arm != "direct"] + ["direct"]:  # direct: no second run
        study.candidates(s, "smoke", arm, [task])
    pools(s, "smoke", "first", [task])
    check = rules.smoke_check(s)
    tranche("redraw")
    probe = refusal(lambda: probing.probe(s))
    tranche("calibration")
    calibration = refusal(lambda: rules.require_order(s, "calibration"))
    rows = spend.rows(s.ledger)
    after = [r for r in spend.starts(rows) if r["seq"] > spend.latest(rows, "smoke")["seq"]]
    runs = [load(path) for path in layout.study_runs(s)]
    return {"smoke_check": check, "closed": closed, "probe": probe, "calibration": calibration,
            "starts_after_the_smoke_check": len(after),
            "runs": {f["arm"]: ("cut" if "cut" in f else f.get("incident") or f.get("outcome")) for f in runs}}


WARNING = "Approaching usage limit · resets 5pm"  # a CLI warning on stderr beside a call that succeeds


def probe_with_a_cut(s):
    """The ladder probe meeting one usage limit on its first task: cut, starts closed, lifted, reopened, re-run.
    After the resume every call that succeeds prints a limit warning on stderr: no pause may follow (re-review N1)."""
    plan_file, reset = Path(os.environ["SEED_SET_STUB_PLAN"]), int(time.time())
    first = ladder.probe_tasks(layout.task_rows(s), probing.answer(s)["probe"][0])[0]
    usage_limit(plan_file, {"task": first, "model": H, "reset": reset})
    try:
        probing.probe(s)
        closed = "starts were not closed"
    except SystemExit as error:
        closed = str(error)
    usage_limit(plan_file, {})
    resumed = spend.resume_after_limit(s.ledger, reset, 0.0, 0.0, time.time())
    stand_in(plan_file, stderr_warning=WARNING)
    probing.probe(s)
    stand_in(plan_file, stderr_warning=None)
    runs = [load(path) for path in layout.study_runs(s) if load(path)["task"] == first]
    return {"task": first, "closed": closed, "resume_seq": resumed["seq"],
            "runs": [("cut" if "cut" in f else "incident" if "incident" in f else f.get("outcome")) for f in runs],
            "incidents_in_tranche": sum("incident" in load(p) for p in layout.study_runs(s))} | warned(s, resumed)


def warned(s, resumed):
    """The probe's calls that printed the limit warning, and the pauses after the resume (none is due)."""
    calls = [c for path in layout.study_runs(s) for c in units.calls(path.parent)
             if WARNING in (c / "stderr.txt").read_text(errors="replace")]
    return {"calls_with_a_limit_warning": len(calls), "pauses_after_the_resume": [
        r["seq"] for r in spend.rows(s.ledger) if r.get("event") == "pause" and r["seq"] > resumed["seq"]]}


def beyond_the_ceiling(s):
    """One start on the redraw tranche whose worst case would pass its priced ceiling: refused, nothing written."""
    ceiling, per_call, _ = layout.spend_terms(s, "redraw", H)
    committed = spend.committed_usd(spend.rows(s.ledger), "redraw")
    calls = int((ceiling - committed) // per_call) + 1
    left = spend.remaining(spend.rows(s.ledger), "redraw", "candidate", H)
    before = s.ledger.read_bytes()
    try:
        spend.reserve(s.ledger, "redraw", "candidate", H, calls, "/rehearsal/beyond-the-ceiling",
                      price=(ceiling, per_call))
        refusal = "reserved"
    except SystemExit as error:
        refusal = str(error)
    return {"calls": calls, "calls_left_in_cap": left, "committed_usd": committed, "ceiling_usd": ceiling,
            "refusal": refusal, "ledger_unchanged": s.ledger.read_bytes() == before}


def build_order(s):
    """Per summarized pool, the arms in the order their clones were built (patch file times)."""
    found = {}
    for directory in sorted((s.results / "pools").glob("*-*")):
        if (directory / "mapping.json").is_file() and (directory / "patches").is_dir():
            clones = load(directory / "mapping.json")["clones"]
            built = sorted(clones, key=lambda cid: (directory / "patches" / f"{cid}.diff").stat().st_mtime_ns)
            found[directory.name] = [clones[cid]["labels"][0] if clones[cid]["arm"] == "anchor" else clones[cid]["arm"]
                                     for cid in built]
    return found


def withheld_run(root, s):
    """implement-check-repair on a real check-withheld package, on its own ledger."""
    outside = Path(load(root / "study.json")["outside"])  # the trees must be where the sandbox sees them
    w = layout.Study(s.runtime, outside / "w-work", outside / "w-pools", root / "w-results", s.tasks_file,
                     s.criterion, root / "w-state")
    rules.record_freeze(w)  # every start checks the freeze on its own ledger
    tranche("smoke")
    spec = layout.load_arms(w)["implement_check_repair"]
    fix = ladder.fix_commits(layout.task_rows(w))[WITHHELD_TASK]
    records, facts = study.one_run(w, "smoke", "implement_check_repair", spec, WITHHELD_TASK, fix, limit=1)
    patch = Path(facts["final_patch"]).read_text() if facts.get("final_patch") else ""
    return {"outcome": facts.get("outcome"), "calls": facts["calls"], "visible": (facts.get("visible") or {}).get(
        "passed"), "staged": sorted(str(p.relative_to(records)) for p in (records / "withheld").rglob("*.py")),
        "patched_files": [line.split(" b/")[-1] for line in patch.splitlines() if line.startswith("diff --git")],
        "incident": facts.get("incident")}


def main(argv=None):
    top = argparse.ArgumentParser()
    top.add_argument("root")
    top.add_argument("--calibration-tasks", type=int, default=ladder.CALIBRATION_TASKS)
    top.add_argument("--in-runtime", action="store_true", help=argparse.SUPPRESS)
    top.add_argument("--withheld-only", action="store_true", help="only the check-withheld launch")
    top.add_argument("--cut-in", choices=("probe", "smoke"), default="probe", help="where the usage limit cuts")
    a = top.parse_args(argv)
    root = Path(a.root).resolve()
    if not a.in_runtime:  # set up, then run the stages from the runtime's own modules
        s = setup(root)
        try:
            subprocess.run([sys.executable, "-m", "experiments.seed_set.rehearsal", str(root), "--in-runtime",
                            "--calibration-tasks", str(a.calibration_tasks), "--cut-in", a.cut_in]
                           + ["--withheld-only"] * a.withheld_only, cwd=s.runtime, check=True,
                           env={**os.environ, "PYTHONPATH": str(s.runtime)})
        finally:
            outside = Path(load(root / "study.json")["outside"])
            open_up(outside)
            shutil.rmtree(outside)
        return
    stages(root, study_at(root), a.calibration_tasks, a.withheld_only, a.cut_in)


def stages(root, s, count, withheld_only=False, cut_in="probe"):
    if withheld_only:  # the separate check-withheld launch alone, on its own ledger
        dump(root / "withheld-run.json", withheld_run(root, s))
        return
    rules.record_freeze(s)
    if cut_in == "smoke":  # the smoke fails: nothing after it may start
        out = smoke_with_a_cut(s) | {"ledger": study.ledger_report(s), "priced_usd": spend.priced(s.ledger)}
        os.environ.pop(spend.AUTHORIZATION)
        dump(root / "rehearsal.json", out)
        print(json.dumps({k: v for k, v in out.items() if k != "ledger"}, indent=1))
        return
    out = {"smoke_check": smoke(s), "luna_smoke_check": luna_smoke(s)}
    tranche("redraw")
    out["usage_limit"] = probe_with_a_cut(s)
    out["probe"] = probing.probe_readout(s)
    out["ceiling"] = beyond_the_ceiling(s)
    out["calibration"] = calibration(s, count, root / "hang-pids")
    report = study.write_readout(s)
    gates_ = report["calibration"] or {}
    out |= {"decision": gates_.get("decision"), "anchor_failures": report["anchor_failures"],
            "judge_checks": gates_.get("judge_checks"), "gate_checks": gates_.get("gate_checks"),
            "identity_hits": {p.parent.name: len(load(p)["hits"]) for p in (s.results / "pools").glob("*/identity-scan.json")},
            "build_order": build_order(s), "ledger": study.ledger_report(s), "priced_usd": spend.priced(s.ledger)}
    out["withheld_run"] = withheld_run(root, s)
    os.environ.pop(spend.AUTHORIZATION)
    dump(root / "rehearsal.json", out)
    print(json.dumps({k: v for k, v in out.items() if k not in ("build_order", "probe")}, indent=1))


if __name__ == "__main__":
    main()
