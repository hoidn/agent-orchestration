"""Zero-spend rehearsal of the seed-set calibration (plan Step 2) on the real task packages: the smoke, `smoke-check`,
the flat ladder probe and its readout, the calibration tranche (candidates, the early judge look, every first and
retest pool with both judges, summaries with hidden tests) and the readout with the judge gate and task gates,
then one implement-check-repair run on a real check-withheld package through a real orchestrator launch.

Every provider is the scripted `claude` of tests/experiments/seed_set_offline_support.py behind the comparison
harness's real shims, sandbox and model guard; no model is called. The process runs with an empty HOME, no
provider credentials, a closed PATH behind the Thread M no-provider stubs, and a ledger under ROOT/state (the
study's own ledger is never opened). The stand-in fixes T1 and T2 always, every second T3 task (two of the four
probe tasks), never T4 or T5; Sonnet fixes everything; on the smoke task Haiku fixes from its second attempt.

  PATH=<checkout>/experiments/thread_m/no_provider:$PATH PYTHONPATH=<checkout> \
      python -m experiments.seed_set.rehearsal ROOT     # ROOT: new, not under /tmp; about two hours

Writes ROOT/rehearsal.json (ledger totals per tranche, the smoke check, the probe answer, the readout's decision
and gates, identity-scan hits, binding failures, the clones' build order, the withheld run) and prints it.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from experiments.compare.repos import dump, load
from experiments.seed_set import ladder, layout, probing, rules, spend, study
from tests.agent_session_shims import closed_path
from tests.experiments.compare_harness_support import write_test_sandbox_config
from tests.experiments.seed_set_offline_support import STUB

CHECKOUT = Path(__file__).resolve().parents[2]
GUARD = CHECKOUT / "experiments" / "thread_m" / "no_provider"
H, S = spend.HAIKU, spend.SONNET
WITHHELD_TASK = "12ea8483f0-withheld"  # a real T3w package for the withheld launch


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
                         "fix": {H: haiku_fix(rung, index, task, smoke), S: 1}}
    # the stub takes the first marker in its prompt: a T0 statement holds its T1 statement, so longest first
    return {"tasks": dict(sorted(entries.items(), key=lambda item: -len(item[1]["marker"])))}


def setup(root):
    root.mkdir()
    main, runtime, home, fakebin = root / "main", root / "runtime", root / "home", root / "fakebin"
    head = subprocess.run(["git", "-C", str(CHECKOUT), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()
    git("clone", "-q", "--shared", "--no-checkout", CHECKOUT, main)
    git("-C", main, "worktree", "add", "-q", "--detach", runtime, head)  # the committed runner and packages
    for directory in (home, fakebin, root / "freeze"):
        directory.mkdir()
    for name in ("claude", "codex"):
        (fakebin / name).write_text(STUB)
        (fakebin / name).chmod(0o755)
    tasks_file = runtime / "experiments" / "seed_set" / "tasks.jsonl"
    plan = root / "stub-plan.json"
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
    dump(root / "freeze" / "criterion.json", {"rehearsal": "stand-in providers only"})
    return layout.Study(runtime, root / "work", root / "pools", root / "results", tasks_file, criterion,
                        root / "state")


def tranche(name):
    os.environ[spend.AUTHORIZATION] = name


def pools(s, name, kind, tasks):
    for task in tasks:  # one pool on disk at a time
        study.build_pools(s, name, kind, [task])
        study.judge(s, name, kind, [task])
        if (s.pools / task / kind).exists():
            study.summarize_pools(s, kind, [task])


def smoke(s):
    tranche("smoke")
    (task,) = layout.tranche_tasks(s, "smoke")
    for arm in layout.PLANNED["smoke"]:
        study.candidates(s, "smoke", arm, [task])
    pools(s, "smoke", "first", [task])
    return rules.smoke_check(s)


def calibration(s):
    tranche("calibration")
    tasks = layout.tranche_tasks(s, "calibration")
    for arm in layout.PLANNED["calibration"]:
        study.candidates(s, "calibration", arm, tasks)
    relaunch = study.candidates(s, "calibration", "direct", tasks)  # every planned run started: nothing
    pools(s, "calibration", "first", tasks[:rules.EARLY_TASKS])
    look = rules.early_look(s)
    pools(s, "calibration", "first", tasks[rules.EARLY_TASKS:])
    pools(s, "calibration", "retest", tasks[:layout.RETESTS["calibration"]])
    try:
        spend.reserve(s.ledger, "calibration", "judge", H, 1, "/rehearsal/one-more-judge-call")
        beyond = "reserved"
    except SystemExit as error:
        beyond = str(error)
    return {"relaunched": len(relaunch), "early_look": look["passed"], "judge_beyond_cap": beyond}


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
    w = layout.Study(s.runtime, root / "w-work", root / "w-pools", root / "w-results", s.tasks_file, s.criterion,
                     root / "w-state")
    tranche("smoke")
    spec = layout.load_arms(w)["implement_check_repair"]
    fix = ladder.fix_commits(layout.task_rows(w))[WITHHELD_TASK]
    records, facts = study.one_run(w, "smoke", "implement_check_repair", spec, WITHHELD_TASK, fix, limit=1)
    patch = Path(facts["final_patch"]).read_text() if facts.get("final_patch") else ""
    return {"outcome": facts.get("outcome"), "calls": facts["calls"], "visible": (facts.get("visible") or {}).get(
        "passed"), "staged": sorted(str(p.relative_to(records)) for p in (records / "withheld").rglob("*.py")),
        "patched_files": [line.split(" b/")[-1] for line in patch.splitlines() if line.startswith("diff --git")],
        "incident": facts.get("incident")}


def main(root):
    root = Path(root).resolve()
    s = setup(root)
    rules.record_freeze(s)
    out = {"smoke_check": smoke(s)}
    tranche("redraw")
    probing.probe(s)
    out["probe"] = probing.probe_readout(s)
    out["calibration"] = calibration(s)
    report = study.write_readout(s)
    gates_ = report["calibration"] or {}
    out |= {"decision": gates_.get("decision"), "anchor_failures": report["anchor_failures"],
            "judges": {j: {k: c[k]["passed"] for k in ("V1", "V2", "V3", "V4")} for j, c in gates_.get("judges", {}).items()},
            "task_gates": {g: v["passed"] for g, v in (gates_.get("gates") or {}).items()},
            "identity_hits": {p.parent.name: len(load(p)["hits"]) for p in (s.results / "pools").glob("*/identity-scan.json")},
            "build_order": build_order(s), "ledger": study.ledger_report(s)}
    out["withheld_run"] = withheld_run(root, s)
    os.environ.pop(spend.AUTHORIZATION)
    dump(root / "rehearsal.json", out)
    print(json.dumps({k: v for k, v in out.items() if k not in ("build_order", "probe")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
