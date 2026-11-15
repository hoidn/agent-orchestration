"""The seed-set calibration path end to end, offline: `study.py`'s candidates (direct on Haiku and on Sonnet), pools
with both anchors, both judges, the retest pools, summaries with hidden tests, the gates and the readout, behind
the comparison harness's real shims, Bubblewrap sandbox, model guard and scan, with the scripted `claude` of
seed_set_offline_support.py standing in for the agent and the judges. No provider is called.

Four toy tasks on a tiny repository form the ladder rung T3: on `add` and `mx` every run fixes the bug, on `mul` and
`mn` only the Sonnet run does. The probe runs `direct` once on the four and must find two passes of four, with the
agent running the visible test itself on the passing two. The calibration takes `add` and `mul` as its chosen
tasks: the first is too easy and the second too hard, so the gates fail and the study stops (the probe was the one
redraw). The smoke runs every program once on the reserve task `sub`, where Haiku fixes the bug from its second
attempt on.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.compare.repos import sha256_file
from experiments.seed_set import forms, host, layout, probing, rules, spend, study, units
from tests.experiments.compare_harness_support import (
    OUTSIDE_SANDBOX_MOUNTS, commit, git, open_up, skip_without_sandbox, write_test_sandbox_config,
)
from tests.agent_session_shims import closed_path
from tests.experiments.seed_set_offline_support import (
    STUB, VERSION, stable_anchors, stand_in_terms, write_frozen_criterion,
)

REPO = Path(__file__).resolve().parents[2]
H, S = spend.HAIKU, spend.SONNET
P = (1000.0, 0.01)  # a priced ceiling and per-call worst case no test here reaches
SYNCED = ("experiments/compare", "experiments/seed_set/programs", "experiments/orc_structural_search/seeds")
BUGS = {"add": "return a - b", "mul": "return a + b", "sub": "return a + b", "mx": "return min(a, b)",
        "mn": "return max(a, b)"}
BASE = {"pkg/__init__.py": "", "pkg/calc.py": "".join(f"def {f}(a, b):\n    {body}\n\n\n" for f, body in BUGS.items()),
        ".gitignore": ".orchestrate/\n", "tests/test_base.py": "def test_base():\n    pass\n"}
# id: (function, fix, visible check, hidden checks (the last passes on the base too), set, Haiku's first fixing attempt)
TASKS = {"a0a0a0a0a0": ("add", "return a + b", "add(2, 3) == 5", "add(10, 5) == 15", "add(0, 0) == 0", "drawn", 1),
         "b1b1b1b1b1": ("mul", "return a * b", "mul(2, 3) == 6", "mul(4, 5) == 20", "mul(2, 2) == 4", "drawn", None),
         "c2c2c2c2c2": ("sub", "return a - b", "sub(3, 1) == 2", "sub(5, 3) == 2", "sub(0, 0) == 0", "smoke", 2),
         "d3d3d3d3d3": ("mx", "return max(a, b)", "mx(2, 3) == 3", "mx(5, 1) == 5", "mx(2, 2) == 2", "drawn", 1),
         "e4e4e4e4e4": ("mn", "return min(a, b)", "mn(2, 3) == 2", "mn(5, 1) == 1", "mn(2, 2) == 2", "drawn", None)}
DRAWN, SMOKE = ["a0a0a0a0a0", "b1b1b1b1b1"], "c2c2c2c2c2"
RUNG = ["a0a0a0a0a0", "b1b1b1b1b1", "d3d3d3d3d3", "e4e4e4e4e4"]  # T3 in-tree, in seed order


def runtime_of(tmp_path, task_repo, refs):
    """A clean runtime: a detached worktree of a shared clone of this checkout, holding the task repository's
    commits and this working tree's harness and program files."""
    main, runtime = tmp_path / "main", tmp_path / "runtime"
    git(REPO, "clone", "-q", "--shared", "--no-checkout", str(REPO), str(main))
    git(main, "fetch", "-q", str(task_repo), *refs)
    git(main, "worktree", "add", "-q", "--detach", str(runtime), "HEAD")
    shutil.rmtree(runtime / "experiments" / "compare")
    for relative in SYNCED:
        shutil.copytree(REPO / relative, runtime / relative, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    git(runtime, "add", "-A", *SYNCED)
    if git(runtime, "status", "--porcelain", "--untracked-files=no"):
        git(runtime, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "sync")
    return main, runtime


def write_task(root, task, base, fix, task_repo, row):
    name, _, visible, *hidden, listed, haiku = row
    package = root / "tasks" / task
    upstream = subprocess.run(["git", "-C", str(task_repo), "diff", base, fix, "--", "pkg"], check=True,
                              capture_output=True, text=True).stdout
    argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"tests/test_visible_{name}.py"]
    hidden_tests = "".join(f"from pkg.calc import {name}\n\n\ndef test_hidden_{k}():\n    assert {check}\n\n\n"
                           for k, check in enumerate(hidden))
    files = {"base_commit": base + "\n", "intent.txt": f"{name} is correct.\n",
             "task.txt": f"Make {name} correct. Visible check: {' '.join(argv[1:])}.\n",
             "seed/dev-check.json": json.dumps({"argv": argv, "timeout_sec": 60}),
             f"seed/tests/test_visible_{name}.py": f"from pkg.calc import {name}\n\n\ndef test_visible():\n"
                                                   f"    assert {visible}\n",
             f"hidden/tests/test_hidden_{name}.py": hidden_tests,
             "hidden_tests.txt": "".join(f"tests/test_hidden_{name}.py::test_hidden_{k}\n" for k in range(len(hidden))),
             f"anchors/{task}-base.diff": "", f"anchors/{task}-upstream.diff": upstream}
    for relative, text in files.items():
        (package / relative).parent.mkdir(parents=True, exist_ok=True)
        (package / relative).write_text(text)
    tier = {"tier": "T3", "form": "in_tree", "probe": True, "withheld_id": None} if listed == "drawn" else {}
    return {"id": task, "set": listed, "commit": fix, "base_commit": base, **tier}, {
        "marker": f"Make {name} correct.", "patch": upstream, "visible": argv, "fix": {H: haiku, S: 1}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    skip_without_sandbox()
    task_repo = tmp_path / "task-repo"
    task_repo.mkdir()
    git(task_repo, "init", "-q")
    base = commit(task_repo, BASE, "base")
    fixes = {}
    for task, (name, body, *_rest) in TASKS.items():
        git(task_repo, "checkout", "-q", "--detach", base)
        source = BASE["pkg/calc.py"].replace(f"def {name}(a, b):\n    {BUGS[name]}", f"def {name}(a, b):\n    {body}")
        fixes[task] = commit(task_repo, {"pkg/calc.py": source}, f"fix {name}")
        git(task_repo, "branch", task, fixes[task])
    main, runtime = runtime_of(tmp_path, task_repo, list(TASKS))
    rows, plan = [], {"tasks": {}}
    for task, row in TASKS.items():  # the toy task list and packages, committed in the runtime (the freeze's rule)
        listed, plan["tasks"][task] = write_task(runtime / "seedset", task, base, fixes[task], task_repo, row)
        rows.append(listed)
    (runtime / "seedset" / "tasks.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    stable_anchors(runtime / "seedset" / "tasks.jsonl")
    git(runtime, "add", "-A", "seedset")
    git(runtime, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "tasks")
    OUTSIDE_SANDBOX_MOUNTS.mkdir(parents=True, exist_ok=True)
    outside = Path(tempfile.mkdtemp(dir=OUTSIDE_SANDBOX_MOUNTS))
    fakebin = outside / "fakebin"
    fakebin.mkdir()
    for name in ("claude", "codex"):
        (fakebin / name).write_text(STUB)
        (fakebin / name).chmod(0o755)
    stub_plan = outside / "stub-plan.json"
    stub_plan.write_text(json.dumps(plan))
    declaration = write_test_sandbox_config(fakebin, outside / "sandbox.json", readonly_files=(stub_plan,),
                                            environment_names=("SEED_SET_STUB_PLAN",))
    empty = tmp_path / "empty-home"
    (empty / ".claude").mkdir(parents=True)
    (empty / ".claude" / ".credentials.json").write_text("{}")  # a stand-in the sandbox copies into each unit
    for key, value in {"PATH": closed_path(fakebin), "COMPARE_SANDBOX": declaration, "SEED_SET_STUB_PLAN": stub_plan,
                       "HOME": empty,
                       "CODEX_HOME": empty / ".codex", "CLAUDE_CONFIG_DIR": empty / ".claude"}.items():
        monkeypatch.setenv(key, str(value))
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_OAUTH_TOKEN_FILE", spend.AUTHORIZATION):
        monkeypatch.delenv(key, raising=False)
    criterion = tmp_path / "judge-calibration.json"
    criterion.write_text(json.dumps({"judges": [H, S], "rubric": layout.RUBRIC, "primary": [], "secondary": []}))
    s = study.Study(runtime, outside / "work", outside / "pools", tmp_path / "results",
                    runtime / "seedset" / "tasks.jsonl", criterion, tmp_path / "state", min_free=10**9)
    write_frozen_criterion(s, frozen="toy", spend=stand_in_terms(fakebin))  # beside the judge criterion
    monkeypatch.setattr(rules, "loaded_elsewhere", lambda runtime: [])  # the test imports this checkout's modules
    rules.record_freeze(s)
    yield SimpleNamespace(study=s, fixes=fixes, plan=stub_plan, fakebin=fakebin)
    open_up(outside)
    shutil.rmtree(outside)
    shutil.rmtree(runtime)
    shutil.rmtree(main)


def credentials(s):
    """Credential files left under the work root, the pools or the results."""
    return sorted(str(p) for root in (s.work, s.pools, s.results) if root.exists()
                  for p in root.rglob("*") if p.name in (".credentials.json", "auth.json"))


def calls_before_reservation(rows):
    """Units whose first recorded call predates their ledger row."""
    late = []
    for row in rows:
        pool, _, judge = row["unit"].partition("#")
        records = Path(pool) / "records" / "judges" / judge if judge else Path(row["unit"])
        if (records / "calls" / "1" / "provider.txt").stat().st_mtime < row["time"]:
            late.append(row["unit"])
    return late


def bound_flags(argv):
    """The model, effort and output format a recorded call passed: the metered template prints stream-json."""
    return tuple(argv[argv.index(flag) + 1] for flag in (b"--model", b"--effort", b"--output-format"))


def choose(s, tasks):
    s.results.mkdir(parents=True, exist_ok=True)
    (s.results / layout.CHOSEN).write_text(json.dumps({"tasks": [{"id": t, "rung": "T3"} for t in tasks]}))
    spend.record(s.ledger, "probe_readout", answer={"chosen": "T3"}, chosen_sha256=sha256_file(s.results / layout.CHOSEN))


def test_offline_calibration_runs_end_to_end_behind_the_real_shims(world, monkeypatch):
    s, tasks = world.study, DRAWN
    with pytest.raises(SystemExit, match="provider spend refused"):
        study.candidates(s, "calibration", "direct", tasks)
    assert (s.work.exists(), spend.starts(spend.rows(s.ledger))) == (False, [])  # unauthorized: nothing started

    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, tasks)  # as probe-readout writes them (its 20-task rule is unit-tested)
    with pytest.raises(SystemExit, match="no passed smoke"):
        study.candidates(s, "calibration", "direct", tasks)
    spend.record(s.ledger, "smoke", passed=True)  # the smoke itself is the next test
    study.candidates(s, "calibration", "direct", tasks)
    study.candidates(s, "calibration", "direct_sonnet", tasks)
    left = [credentials(s)]
    for kind in ("first", "retest"):
        study.build_pools(s, "calibration", kind, tasks)
        left.append(credentials(s))  # a pool whose judges have not launched (or never will) holds none
        if kind == "retest":
            with pytest.raises(SystemExit, match="before the early judge look"):
                study.judge(s, "calibration", kind, tasks)
            assert rules.early_look(s)["passed"] is True  # the reference scores 8 above the base on both tasks
        study.judge(s, "calibration", kind, tasks)
        left.append(credentials(s))
        study.summarize_pools(s, kind, tasks)
    report = study.write_readout(s)
    assert left == [[]] * 5  # copied credentials never outlive a command

    rows = spend.rows(s.ledger)
    totals = study.ledger_report(s)["calibration"]
    assert {kind: {model: (row["reserved"], row.get("made")) for model, row in models.items()}
            for kind, models in totals.items()} == {"candidate": {H: (8, 8), S: (2, 2)}, "judge": {H: (4, 4), S: (4, 4)}}
    assert calls_before_reservation(spend.starts(rows)) == []
    # rulings R4, R5: every unit settled at its metered price (12 Haiku calls at USD 0.0036, 6 Sonnet at 0.067), each
    # start carries the pinned CLI, each command the runtime's own cap at the unit's worst case
    assert (spend.priced(s.ledger)["calibration"], {r["cli"]["version"] for r in spend.starts(rows)},
            {path.read_text().split()[-2] for path in [*s.work.glob("records/*/run-*/command.sh"),
                                                           *s.pools.glob("*/*/records/score-*.sh")]}) == (
        {"committed_usd": 0.4452, "settled_usd": 0.4452, "open_usd": 0.0, "missing_usage": [], "over_reserved": []},
        {VERSION}, {"--max-cost-usd"})
    with pytest.raises(SystemExit, match="the study is stopped"):  # the readout's stop decision
        study.candidates(s, "calibration", "direct", tasks)
    assert spend.rows(s.ledger) == rows

    runs = [json.loads(path.read_text()) for path in study.study_runs(s)]
    assert sorted((r["task"], r["model"], r["outcome"], r["scan_hits"], r["visible"]["passed"]) for r in runs) == sorted(
        [("a0a0a0a0a0", H, "completed", 0, True)] * 4 + [("a0a0a0a0a0", S, "completed", 0, True)]
        + [("b1b1b1b1b1", H, "completed", 0, False)] * 4 + [("b1b1b1b1b1", S, "completed", 0, True)])
    fixed = [path.parent for path in study.study_runs(s) if json.loads(path.read_text())["task"] == "a0a0a0a0a0"]
    seen = {(bound_flags((run / "calls/1/argv.nul").read_bytes().split(b"\0")),
             "visible check exit 0" in (run / "calls/1/stdout.txt").read_text(),
             # the scripted CLI wrote its session under HOME=/home/compare: the unit's private home, so it ran sandboxed
             len(list(Path(json.loads((run / "record.json").read_text())["sandbox"]["home"]).glob(
                 ".claude/projects/*/*.jsonl")))) for run in fixed}
    assert seen == {((H.encode(), b"medium", b"stream-json"), True, 1), ((S.encode(), b"medium", b"stream-json"), True, 1)}
    assert (list((s.work / "agents").iterdir()), study.live_pools(s)) == ([], [])  # trees and clones deleted
    judged = [json.loads(p.read_text()) for p in s.pools.glob("*/*/records/study-*.json")]
    assert [(j["exit"], j["calls"], j["verify_pool"], j["scan_hits"]) for j in judged] == [(0, 1, "clean", 0)] * 8

    first = json.loads((s.results / "pools" / "b1b1b1b1b1-first" / "results.json").read_text())
    anchors = {c["labels"][0]: c for c in first["clones"].values() if c["arm"] == "anchor"}
    assert (len(first["clones"]), anchors["b1b1b1b1b1-base"]["hidden"], anchors["b1b1b1b1b1-upstream"]["hidden"],
            {j: r["quality"] for j, r in anchors["b1b1b1b1b1-base"]["ratings"].items()}) == (7, 0.5, 1.0, {H: 0, S: 0})

    c = report["calibration"]  # a stop reports pass or fail only, no quality figure (review2 M7)
    assert (report["anchor_failures"], set(c), c["selected"], c["gate_checks"], c["decision"], report["baselines"]) == (
        [], {"stopped", "decision", "selected", "insensitive", "v4_note", "judge_checks", "gate_checks"}, H,
        {"G1": False, "G2": True, "G3": True, "G4": True},
        "stop: a gate fails and the ladder probe was the one redraw; no quality claim", None)
    text = (s.results / "readout.md").read_text()
    assert ("## Calibration table" in text, "## Offline re-roll baselines" in text) == (False, False)
    (line,) = [x for x in text.splitlines() if x.startswith("Decision:")]
    assert (line.startswith("Decision: stop"), "V4 (agreement with the hidden tests) was not assessed" in line,
            "Tasks: 2 (T3 in-tree 2)" in text) == (True, True, True)  # too few candidates per hidden class
    events = [e["event"] for e in study.ledger_report(s)["events"]]
    assert ([e for e in events if e != "settle"], events.count("settle")) == (
        ["freeze", "probe_readout", "smoke", "early_look", "decision", "stop"], 18)  # one settle per unit
    resume = next(s.work.glob("records/*/run-*/resume.sh"))
    assert subprocess.run(["bash", str(resume)], capture_output=True).returncode == 64  # no unit ever resumes


def test_offline_smoke_runs_every_program_once_behind_the_real_shims(world, monkeypatch):
    s = world.study
    monkeypatch.setenv(spend.AUTHORIZATION, "smoke")
    for arm in study.PLANNED["smoke"]:
        study.candidates(s, "smoke", arm, [SMOKE])
    study.build_pools(s, "smoke", "first", [SMOKE])
    study.judge(s, "smoke", "first", [SMOKE])
    study.summarize_pools(s, "first", [SMOKE])

    runs = {r["arm"]: r for r in (json.loads(p.read_text()) for p in study.study_runs(s))}
    assert {arm: (r["outcome"], r["calls"], r["scan_hits"], r["visible"]["passed"]) for arm, r in runs.items()} == {
        "direct": ("completed", 1, 0, False), "direct_sonnet": ("completed", 1, 0, True),
        "retry_until_check": ("completed", 2, 0, True), "implement_check_repair": ("completed", 2, 0, True),
        "implement_review_revise": ("completed", 3, 0, True)}
    totals = study.ledger_report(s)["smoke"]
    assert {kind: {model: (row["reserved"], row.get("made")) for model, row in models.items()}
            for kind, models in totals.items()} == {"candidate": {H: (10, 8), S: (1, 1)}, "judge": {H: (1, 1), S: (1, 1)}}
    results = json.loads((s.results / "pools" / f"{SMOKE}-first" / "results.json").read_text())
    assert (len(results["clones"]), results["excluded_judges"],
            all(set(c["ratings"]) == {H, S} and c["hidden"] is not None for c in results["clones"].values())) == (
        7, {}, True)
    assert rules.smoke_check(s)["passed"] is True
    assert spend.latest(spend.rows(s.ledger), "smoke")["passed"] is True  # the calibration may now start


def test_offline_visible_check_fails_a_patch_whose_code_calls_a_provider(world):
    s, task = world.study, "a0a0a0a0a0"
    package = study.task_dir(s, task)
    upstream = (package / "anchors" / f"{task}-upstream.diff").read_text()
    calling = re.sub(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", lambda m: f"@@ -{m[1]},{m[2]} +{m[3]},{int(m[4]) + 1} @@",
                     upstream).replace("+    return a + b", "+    __import__('subprocess').run(['claude', '-p', 'x'])\n"
                                                         "+    return a + b")
    patch = s.results / "calling.diff"
    patch.parent.mkdir(parents=True)
    patch.write_text(calling)
    assert host.visible_check(package, patch, s.runtime)["provider_attempts"]


def test_offline_probe_of_one_rung_runs_hidden_tests_and_detects_self_checks(world, monkeypatch):
    s = world.study
    spend.record(s.ledger, "smoke", passed=True, bisect=False)
    monkeypatch.setenv(spend.AUTHORIZATION, "redraw")
    assert probing.answer(s)["probe"] == ["T3"]  # the only rung with four tasks
    probing.probe(s)

    runs = {r["task"]: r for r in (json.loads(p.read_text()) for p in study.study_runs(s))}
    assert {t: (r["step"], r["rung"], r["outcome"], r["hidden"]["passed"], r["self_check"]) for t, r in runs.items()} == {
        "a0a0a0a0a0": ("first", "T3", "completed", True, True), "b1b1b1b1b1": ("first", "T3", "completed", False, False),
        "d3d3d3d3d3": ("first", "T3", "completed", True, True), "e4e4e4e4e4": ("first", "T3", "completed", False, False)}
    assert (probing.results(s, "first")[0], probing.answer(s)) == (
        {"T3": 2}, {"phase": "first", "bisect": False, "chosen": "T3"})
    rows = spend.starts(spend.rows(s.ledger))
    assert ({(r["tranche"], r["model"], r["calls"], r["step"]) for r in rows}, study.ledger_report(s)["redraw"][
        "candidate"][H]) == ({("redraw", H, 1, "first")}, {"reserved": 4, "cap": 40, "made": 4})
    with pytest.raises(SystemExit, match="nothing to probe now"):
        probing.probe(s, ["T3"])


def test_offline_withheld_check_runs_through_a_real_launch_and_leaves_no_test_behind(world, monkeypatch):
    """A check-withheld package behind the real shims, sandbox and orchestrator: its test files are staged in the run's
    records, dev_check.py places them for each check and removes them, the agent never sees their path, and the
    final patch is the fix alone. Haiku fixes `sub` from its second attempt: implement-check-repair makes two calls
    only if the second check found the test and passed."""
    s, task = world.study, f"{SMOKE}-withheld"
    forms.withhold(study.task_dir(s, SMOKE), study.task_dir(s, task))
    git(s.runtime, "add", "-A", "seedset")  # every start checks the freeze: the new package is committed and frozen
    git(s.runtime, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "withheld")
    rules.record_freeze(s)
    plan_file = Path(world.plan)
    plan = json.loads(plan_file.read_text())
    plan["tasks"][task] = {**plan["tasks"][SMOKE], "marker": "sub is correct.", "visible": [sys.executable, "-c", ""]}
    plan_file.write_text(json.dumps(plan))
    monkeypatch.setenv(spend.AUTHORIZATION, "smoke")
    spec = layout.load_arms(s)["implement_check_repair"]
    records, facts = study.one_run(s, "smoke", "implement_check_repair", spec, task, world.fixes[SMOKE], limit=1)
    home = Path(json.loads((records / "record.json").read_text())["sandbox"]["home"])
    patch = Path(facts["final_patch"]).read_text()
    assert (facts["outcome"], facts["calls"], facts["visible"]["passed"], (records / "withheld").is_dir(),
            [line for line in patch.splitlines() if line.startswith("diff --git")],
            any("withheld_seen" in p.read_text() for p in home.rglob("*.jsonl"))) == (
        "completed", 2, True, True, ["diff --git a/pkg/calc.py b/pkg/calc.py"], False)


def test_offline_pool_with_a_patch_naming_its_model_is_refused_before_any_judge(world, monkeypatch):
    s, task = world.study, "a0a0a0a0a0"
    plan = json.loads(Path(world.plan).read_text())
    entry = plan["tasks"][task]
    entry["patch"] = re.sub(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", lambda m: f"@@ -{m[1]},{m[2]} +{m[3]},{int(m[4]) + 1} @@",
                            entry["patch"]).replace("+    return a + b", "+    # fixed by claude-haiku-5-5\n+    return a + b")
    Path(world.plan).write_text(json.dumps(plan))
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    study.candidates(s, "calibration", "direct", [task])
    study.build_pools(s, "calibration", "first", [task])
    study.judge(s, "calibration", "first", [task])
    assert credentials(s) == []  # nor a refused pool's
    incident = json.loads((s.results / "pools" / f"{task}-first" / "incident.json").read_text())
    assert ("arm-identifying text" in incident["reason"], "claude-haiku-5-5" in incident["reason"],
            (s.pools / task / "first").exists(), [r["kind"] for r in spend.starts(spend.rows(s.ledger))]) == (
        True, True, False, ["candidate"] * 4)


def limit_plan(world, **limit):
    """Set (or, with no argument, lift) the stand-in's usage limit, rewriting the plan in place: the sandbox binds
    the same file."""
    plan = json.loads(Path(world.plan).read_text())
    plan["usage_limit"] = limit
    Path(world.plan).write_text(json.dumps(plan))


def reopen(s, reset):
    return spend.resume_after_limit(s.ledger, reset, 2.0, 35.0, time.time() - 1)


def facts_of(s):
    return [json.loads(path.read_text()) for path in study.study_runs(s)]


def test_offline_usage_limit_closes_starts_and_its_slots_run_again_from_the_same_cap(world, monkeypatch):
    """Coordinator rulings R1 to R3: the stand-in answers Haiku on `add` with the vendor's usage-limit shape. The
    runs it cuts (one or both of the two in flight) are cut, not incidents; the pause refuses every other start until
    resume-after-limit; then each cut slot runs again once, as a new unit, and the Sonnet re-run that would pass its
    cap is refused."""
    s, task, reset = world.study, "a0a0a0a0a0", int(time.time()) - 60
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    limit_plan(world, task=task, model=H, reset=reset)
    with pytest.raises(SystemExit, match="closed by a usage limit"):
        study.candidates(s, "calibration", "direct", [task])
    cut = [f for f in facts_of(s) if "cut" in f]
    assert (len(cut) in (1, 2), [("incident" in f, f["cut"]["reset"]) for f in cut], rules.stop_reasons(s)) == (
        True, [(False, reset)] * len(cut), [])
    limit_plan(world)  # the window reset
    with pytest.raises(SystemExit, match="closed by a usage limit"):  # still closed: no resume yet
        study.candidates(s, "calibration", "direct", [task])
    reopen(s, reset)
    study.candidates(s, "calibration", "direct", [task])
    haiku = [f for f in facts_of(s) if f["model"] == H]
    starts = [r for r in spend.starts(spend.rows(s.ledger)) if r["model"] == H]
    assert (sum(f.get("outcome") == "completed" and "cut" not in f for f in haiku), len(starts),
            len({r["unit"] for r in starts}), study.candidates(s, "calibration", "direct", [task])) == (
        4, 4 + len(cut), 4 + len(cut), [])  # every slot observed once; each cut slot ran again; nothing more due

    for k in range(19):  # the Sonnet cap (20) holds one more call: the cut run takes it, its re-run is left out
        spend.reserve(s.ledger, "calibration", "candidate", S, 1, f"/elsewhere/{k}", task=f"other-{k}",
                      arm="direct_sonnet", price=P)
    limit_plan(world, task=task, model=S, reset=reset)
    study.candidates(s, "calibration", "direct_sonnet", [task])
    limit_plan(world)
    reopen(s, reset)
    assert (study.candidates(s, "calibration", "direct_sonnet", [task]),
            spend.totals(s.ledger)["calibration"]["candidate"][S]) == ([], {"reserved": 20, "cap": 20})


def test_offline_a_cli_other_than_the_pinned_one_refuses_the_start_and_leaves_nothing(world, monkeypatch):
    s = world.study
    write_frozen_criterion(s, frozen="toy", spend=stand_in_terms(world.fakebin, cli={
        "path": str((world.fakebin / "claude").resolve()), "version": "2.1.312 (Claude Code)"}))
    rules.record_freeze(s)
    monkeypatch.setenv(spend.AUTHORIZATION, "smoke")
    with pytest.raises(SystemExit, match="not the pinned"):
        study.candidates(s, "smoke", "direct", [SMOKE])
    assert (spend.starts(spend.rows(s.ledger)), list((s.work / "agents").iterdir()), study.study_runs(s)) == ([], [], [])


def test_offline_judge_cut_by_a_usage_limit_rebuilds_the_pool_once_from_the_same_records(world, monkeypatch):
    s, task, reset = world.study, "a0a0a0a0a0", int(time.time()) - 60
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    study.candidates(s, "calibration", "direct", [task])
    study.candidates(s, "calibration", "direct_sonnet", [task])
    study.build_pools(s, "calibration", "first", [task])
    limit_plan(world, judge=H, reset=reset)
    with pytest.raises(SystemExit, match="closed by a usage limit"):  # Haiku cut: the Sonnet judge never starts
        study.judge(s, "calibration", "first", [task])
    with pytest.raises(SystemExit, match="cut by a usage limit"):  # never summarized into an incident
        study.summarize_pools(s, "first", [task])
    limit_plan(world)
    reopen(s, reset)
    study.build_pools(s, "calibration", "first", [task])  # the same five runs, new clone ids and orders
    study.judge(s, "calibration", "first", [task])
    study.summarize_pools(s, "first", [task])
    results = json.loads((s.results / "pools" / f"{task}-first" / "results.json").read_text())
    judges = [(r["model"], Path(r["unit"].partition("#")[0]).name) for r in spend.starts(spend.rows(s.ledger))
              if r["kind"] == "judge"]
    assert (len(results["clones"]), all(set(c["ratings"]) == {H, S} for c in results["clones"].values()),
            sorted(judges), (s.pools / task / "first" / "clones").exists()) == (
        7, True, [(H, "first"), (H, "first.2"), (S, "first.2")], False)
    with pytest.raises(SystemExit, match="built once"):
        study.build_pools(s, "calibration", "first", [task])


def test_offline_a_smoke_with_a_program_cut_by_a_usage_limit_fails_and_opens_nothing(world, monkeypatch):
    """Review 3 X1: the Haiku `direct` smoke run is cut, the limit lifts, the other four programs run, and the pool is
    judged and summarized. The smoke check fails, nothing after it may start, and the cut run's few seconds never
    stand for the median Haiku direct run that chooses between the flat and the bisected probe."""
    s, reset = world.study, int(time.time()) - 60
    monkeypatch.setenv(spend.AUTHORIZATION, "smoke")
    limit_plan(world, task=SMOKE, model=H, reset=reset)
    study.candidates(s, "smoke", "direct", [SMOKE])
    limit_plan(world)
    reopen(s, reset)
    for arm in ("direct_sonnet", "retry_until_check", "implement_check_repair", "implement_review_revise"):
        study.candidates(s, "smoke", arm, [SMOKE])
    study.build_pools(s, "smoke", "first", [SMOKE])
    study.judge(s, "smoke", "first", [SMOKE])
    study.summarize_pools(s, "first", [SMOKE])
    check = rules.smoke_check(s)
    assert (check["passed"], check["checks"]["no_unit_cut_by_a_usage_limit"], check["direct_median_wall_sec"]) == (
        False, False, None)
    monkeypatch.setenv(spend.AUTHORIZATION, "redraw")
    with pytest.raises(SystemExit, match="no passed smoke"):
        probing.probe(s)


def test_offline_a_cut_units_pause_is_written_before_its_settlement_begins(world, monkeypatch):
    """Review 3 minor 1: the pause is in the ledger as soon as the cut unit's process ends, before collect, scan and
    the visible check, and once per unit."""
    s, task, reset = world.study, "a0a0a0a0a0", int(time.time()) - 60
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    limit_plan(world, task=task, model=H, reset=reset)
    seen, settle = [], study.settle

    def observed(study_, records, *rest):
        seen.append(any(r.get("event") == "pause" and r["unit"] == str(records) for r in spend.rows(study_.ledger)))
        return settle(study_, records, *rest)
    monkeypatch.setattr(study, "settle", observed)
    with pytest.raises(SystemExit, match="closed by a usage limit"):
        study.candidates(s, "calibration", "direct", [task])
    pauses = [r["unit"] for r in spend.rows(s.ledger) if r.get("event") == "pause"]
    assert (bool(seen) and all(seen), len(pauses) == len(set(pauses)) == len(seen)) == (True, True)


def test_offline_the_runtime_cap_lets_every_planned_call_of_a_multi_call_unit_run(world, monkeypatch):
    """Review 3 X3: the stand-in's Haiku call costs USD 0.0036 at the ordinary rate and 0.018 at the highest tier,
    which the runtime counts. A per-call worst case of 0.005 that the freeze accepts (it covers 5 x the 0.001 named
    as the largest ordinary-rate call) still lets the second of retry-until-check's calls run."""
    s = world.study
    write_frozen_criterion(s, frozen="toy", spend=stand_in_terms(world.fakebin, per_call_usd={H: 0.005, S: 1.0},
                                                                 largest_call_usd={H: 0.001, S: 0.067}))
    rules.record_freeze(s)
    monkeypatch.setenv(spend.AUTHORIZATION, "smoke")
    study.candidates(s, "smoke", "retry_until_check", [SMOKE])
    (facts,) = facts_of(s)
    command = next(s.work.glob("records/*/run-*/command.sh")).read_text().split()
    assert ({k: facts.get(k) for k in ("outcome", "incident", "calls")}, command[-2:]) == (
        {"outcome": "completed", "incident": None, "calls": 2}, ["--max-cost-usd", "0.075"])


def unit_processes(world):
    """Processes of the world's units: every one names a path under its sandbox-visible directory."""
    found = subprocess.run(["pgrep", "-f", str(world.fakebin.parent)], capture_output=True, text=True).stdout
    return [int(pid) for pid in found.split()]


def test_offline_a_killed_launcher_takes_its_agent_with_it_and_the_next_command_removes_the_copy(world, monkeypatch):
    """Review 3 X5: kill -9 of the launcher while the stand-in agent is in its call (it would answer after a
    minute). The unit's session dies with the launcher, the next study command starts by removing the unit's
    credential copy, and settle then settles the unit."""
    s, task = world.study, "a0a0a0a0a0"
    plan = json.loads(Path(world.plan).read_text())
    Path(world.plan).write_text(json.dumps(plan | {"sleep": 60}))
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    paths = [str(p) for p in (s.runtime, s.work, s.pools, s.results, s.tasks_file, s.criterion, s.state)]
    code = (f"from pathlib import Path\nfrom experiments.seed_set import layout, rules, study\n"
            f"rules.loaded_elsewhere = lambda runtime: []\n"
            f"s = layout.Study(*map(Path, {paths!r}), min_free=10**9)\n"
            f"study.candidates(s, 'calibration', 'direct_sonnet', [{task!r}])\n")
    launcher = subprocess.Popen([sys.executable, "-c", code], cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO)})
    deadline = time.time() + 600
    while time.time() < deadline and not list(s.work.glob("records/*/run-*/calls/1/prompt.txt")):
        time.sleep(0.5)
    time.sleep(3)
    (records,) = [path.parent for path in study.study_runs(s)]
    assert len(unit_processes(world)) > 3  # the session, its provider call's own session and the sandbox
    launcher.kill()
    launcher.wait()
    gone = time.time() + 15
    while time.time() < gone and unit_processes(world):
        time.sleep(0.5)
    assert (unit_processes(world), credentials(s) != []) == ([], True)
    with pytest.raises(SystemExit, match="runs"):  # refused after its start removed the copy
        study.candidates(s, "calibration", "no_such_arm", [task])
    assert credentials(s) == []
    study.settle_runs(s, [records])
    assert json.loads((records / "study.json").read_text())["calls"] == 1


def running(pids_dir):
    """The live processes whose pid a host-side check of candidate code recorded in `pids_dir`."""
    found = []
    for name in os.listdir(pids_dir):
        try:
            state = Path(f"/proc/{name}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except OSError:
            continue
        found += [int(name)] if state != "Z" else []
    return found


def test_offline_a_killed_launcher_takes_its_settlements_visible_check_with_it(world, monkeypatch, tmp_path):
    """Re-review N2: kill -9 of the launcher while the settlement's visible check runs the candidate's code on the
    host (a conftest that sleeps two minutes). The check runs under the launch guard: nothing of it lives on, and
    processes that are not the unit's (one in a session of its own, one in this test's group) are untouched."""
    s, task, pids = world.study, "a0a0a0a0a0", tmp_path / "host-pids"
    pids.mkdir(mode=0o700)
    plan = json.loads(Path(world.plan).read_text())
    Path(world.plan).write_text(json.dumps(plan | {"conftest_sleep": {"seconds": 120, "pids": str(pids)}}))
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    paths = [str(p) for p in (s.runtime, s.work, s.pools, s.results, s.tasks_file, s.criterion, s.state)]
    code = (f"from pathlib import Path\nfrom experiments.seed_set import layout, rules, study\n"
            f"rules.loaded_elsewhere = lambda runtime: []\n"
            f"s = layout.Study(*map(Path, {paths!r}), min_free=10**9)\n"
            f"study.candidates(s, 'calibration', 'direct_sonnet', [{task!r}])\n")
    launcher = subprocess.Popen([sys.executable, "-c", code], cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO)})
    deadline = time.time() + 600
    while time.time() < deadline and not running(pids) and launcher.poll() is None:
        time.sleep(0.5)
    others = [subprocess.Popen(["sleep", "900"], start_new_session=True), subprocess.Popen(["sleep", "900"])]
    try:
        checked = running(pids)
        launcher.kill()
        launcher.wait()
        gone = time.time() + 30
        while time.time() < gone and (running(pids) or unit_processes(world)):
            time.sleep(0.5)
        assert (bool(checked), running(pids), unit_processes(world), [p.poll() for p in others]) == (
            True, [], [], [None, None])
    finally:
        for p in others:
            p.kill()
            p.wait()


def test_offline_a_limit_warning_beside_calls_that_succeed_cuts_nothing(world, monkeypatch):  # re-review N1
    s, task = world.study, "a0a0a0a0a0"
    plan = json.loads(Path(world.plan).read_text())
    Path(world.plan).write_text(json.dumps(plan | {"stderr_warning": "Approaching usage limit · resets 5pm"}))
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    study.candidates(s, "calibration", "direct_sonnet", [task])
    (facts,) = facts_of(s)
    (records,) = [path.parent for path in study.study_runs(s)]
    warned = [c.name for c in units.calls(records) if "Approaching usage limit" in (c / "stderr.txt").read_text()]
    assert (facts["outcome"], "cut" in facts, "incident" in facts, warned,
            [r for r in spend.rows(s.ledger) if r.get("event") == "pause"]) == ("completed", False, False, ["1"], [])


def test_offline_a_criterion_edited_during_a_batch_refuses_the_batchs_later_units(world, monkeypatch):  # minor 6
    s, task = world.study, "a0a0a0a0a0"
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    monkeypatch.setattr(study, "WIDTH", 1)
    launch = study.launch

    def edit_after(*args, **kwargs):
        status = launch(*args, **kwargs)
        s.frozen.write_text(s.frozen.read_text().replace('"toy"', '"edited"'))
        return status
    monkeypatch.setattr(study, "launch", edit_after)
    with pytest.raises(SystemExit, match="changed since the freeze"):
        study.candidates(s, "calibration", "direct", [task])
    assert len(spend.starts(spend.rows(s.ledger))) == 1
