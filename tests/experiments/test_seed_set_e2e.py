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
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.compare.repos import sha256_file
from experiments.seed_set import forms, host, layout, probing, rules, spend, study
from tests.experiments.compare_harness_support import (
    OUTSIDE_SANDBOX_MOUNTS, commit, git, open_up, skip_without_sandbox, write_test_sandbox_config,
)
from tests.agent_session_shims import closed_path
from tests.experiments.seed_set_offline_support import STUB

REPO = Path(__file__).resolve().parents[2]
H, S = spend.HAIKU, spend.SONNET
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
    for task, row in TASKS.items():
        listed, plan["tasks"][task] = write_task(tmp_path / "seedset", task, base, fixes[task], task_repo, row)
        rows.append(listed)
    (tmp_path / "seedset" / "tasks.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
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
    empty.mkdir()
    for key, value in {"PATH": closed_path(fakebin), "COMPARE_SANDBOX": declaration, "SEED_SET_STUB_PLAN": stub_plan,
                       "HOME": empty,
                       "CODEX_HOME": empty / ".codex", "CLAUDE_CONFIG_DIR": empty / ".claude"}.items():
        monkeypatch.setenv(key, str(value))
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_OAUTH_TOKEN_FILE", spend.AUTHORIZATION):
        monkeypatch.delenv(key, raising=False)
    criterion = tmp_path / "judge-calibration.json"
    criterion.write_text(json.dumps({"judges": [H, S], "rubric": layout.RUBRIC, "primary": [], "secondary": []}))
    (tmp_path / "criterion.json").write_text(json.dumps({"frozen": "toy"}))  # the freeze's criterion, beside it
    s = study.Study(runtime, outside / "work", outside / "pools", tmp_path / "results",
                    tmp_path / "seedset" / "tasks.jsonl", criterion, tmp_path / "state", min_free=10**9)
    rules.record_freeze(s)
    yield SimpleNamespace(study=s, fixes=fixes, plan=stub_plan)
    open_up(outside)
    shutil.rmtree(outside)
    shutil.rmtree(runtime)
    shutil.rmtree(main)


def calls_before_reservation(rows):
    """Units whose first recorded call predates their ledger row."""
    late = []
    for row in rows:
        pool, _, judge = row["unit"].partition("#")
        records = Path(pool) / "records" / "judges" / judge if judge else Path(row["unit"])
        if (records / "calls" / "1" / "provider.txt").stat().st_mtime < row["time"]:
            late.append(row["unit"])
    return late


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
    for kind in ("first", "retest"):
        study.build_pools(s, "calibration", kind, tasks)
        if kind == "retest":
            with pytest.raises(SystemExit, match="before the early judge look"):
                study.judge(s, "calibration", kind, tasks)
            assert rules.early_look(s)["passed"] is True  # the reference scores 8 above the base on both tasks
        study.judge(s, "calibration", kind, tasks)
        study.summarize_pools(s, kind, tasks)
    report = study.write_readout(s)

    rows = spend.rows(s.ledger)
    totals = study.ledger_report(s)["calibration"]
    assert {kind: {model: (row["reserved"], row.get("made")) for model, row in models.items()}
            for kind, models in totals.items()} == {"candidate": {H: (8, 8), S: (2, 2)}, "judge": {H: (4, 4), S: (4, 4)}}
    assert calls_before_reservation(spend.starts(rows)) == []
    with pytest.raises(SystemExit, match="the study is stopped"):  # the readout's stop decision
        study.candidates(s, "calibration", "direct", tasks)
    assert spend.rows(s.ledger) == rows

    runs = [json.loads(path.read_text()) for path in study.study_runs(s)]
    assert sorted((r["task"], r["model"], r["outcome"], r["scan_hits"], r["visible"]["passed"]) for r in runs) == sorted(
        [("a0a0a0a0a0", H, "completed", 0, True)] * 4 + [("a0a0a0a0a0", S, "completed", 0, True)]
        + [("b1b1b1b1b1", H, "completed", 0, False)] * 4 + [("b1b1b1b1b1", S, "completed", 0, True)])
    fixed = [path.parent for path in study.study_runs(s) if json.loads(path.read_text())["task"] == "a0a0a0a0a0"]
    seen = {(tuple((run / "calls/1/argv.nul").read_bytes().split(b"\0")[1:5]),
             "visible check exit 0" in (run / "calls/1/stdout.txt").read_text(),
             # the scripted CLI wrote its session under HOME=/home/compare: the unit's private home, so it ran sandboxed
             len(list(Path(json.loads((run / "record.json").read_text())["sandbox"]["home"]).glob(
                 ".claude/projects/*/*.jsonl")))) for run in fixed}
    assert seen == {((b"--model", H.encode(), b"--effort", b"medium"), True, 1),
                    ((b"--model", S.encode(), b"--effort", b"medium"), True, 1)}
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
    assert [e["event"] for e in study.ledger_report(s)["events"]] == [
        "freeze", "probe_readout", "smoke", "early_look", "decision", "stop"]
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
    incident = json.loads((s.results / "pools" / f"{task}-first" / "incident.json").read_text())
    assert ("arm-identifying text" in incident["reason"], "claude-haiku-5-5" in incident["reason"],
            (s.pools / task / "first").exists(), [r["kind"] for r in spend.starts(spend.rows(s.ledger))]) == (
        True, True, False, ["candidate"] * 4)
