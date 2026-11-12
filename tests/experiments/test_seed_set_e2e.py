"""The seed-set calibration path end to end, offline: `study.py`'s candidates (direct on Haiku and on Sonnet), pools
with both anchors, both judges, the retest pools, summaries with hidden tests, the gates and the readout, behind
the comparison harness's real shims, Bubblewrap sandbox, model guard and scan, with the scripted `claude` of
seed_set_offline_support.py standing in for the agent and the judges. No provider is called.

Two drawn toy tasks on a tiny repository: on `add` every run fixes the bug, on `mul` only the Sonnet run does. So
the first task is too easy and the second too hard, and the gates must ask for a redraw. The smoke runs every
program once on the reserve task `sub`, where Haiku fixes the bug from its second attempt on.
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

from experiments.seed_set import host, layout, rules, spend, study
from tests.experiments.compare_harness_support import (
    OUTSIDE_SANDBOX_MOUNTS, commit, git, open_up, skip_without_sandbox, write_test_sandbox_config,
)
from tests.experiments.seed_set_offline_support import STUB

REPO = Path(__file__).resolve().parents[2]
H, S = spend.HAIKU, spend.SONNET
SYNCED = ("experiments/compare", "experiments/seed_set/programs", "experiments/orc_structural_search/seeds")
BUGS = {"add": "return a - b", "mul": "return a + b", "sub": "return a + b"}
BASE = {"pkg/__init__.py": "", "pkg/calc.py": "".join(f"def {f}(a, b):\n    {body}\n\n\n" for f, body in BUGS.items()),
        ".gitignore": ".orchestrate/\n", "tests/test_base.py": "def test_base():\n    pass\n"}
# id: (function, fix, visible check, hidden checks (the last passes on the base too), set, Haiku's first fixing attempt)
TASKS = {"a0a0a0a0a0": ("add", "return a + b", "add(2, 3) == 5", "add(10, 5) == 15", "add(0, 0) == 0", "drawn", 1),
         "b1b1b1b1b1": ("mul", "return a * b", "mul(2, 3) == 6", "mul(4, 5) == 20", "mul(2, 2) == 4", "drawn", None),
         "c2c2c2c2c2": ("sub", "return a - b", "sub(3, 1) == 2", "sub(5, 3) == 2", "sub(0, 0) == 0", "reserve", 2)}
DRAWN, SMOKE = ["a0a0a0a0a0", "b1b1b1b1b1"], "c2c2c2c2c2"


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
    return {"id": task, "set": listed, "commit": fix, "base_commit": base}, {
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
    for key, value in {"COMPARE_SANDBOX": declaration, "SEED_SET_STUB_PLAN": stub_plan, "HOME": empty,
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
    yield SimpleNamespace(study=s, fixes=fixes)
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


def test_offline_calibration_runs_end_to_end_behind_the_real_shims(world, monkeypatch):
    s, tasks = world.study, DRAWN
    with pytest.raises(SystemExit, match="provider spend refused"):
        study.candidates(s, "calibration", "direct", tasks)
    assert (s.work.exists(), spend.starts(spend.rows(s.ledger))) == (False, [])  # unauthorized: nothing started

    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    with pytest.raises(SystemExit, match="no passed smoke"):
        study.candidates(s, "calibration", "direct", tasks)
    spend.record(s.ledger, "smoke", passed=True)  # the smoke itself is the next test
    study.candidates(s, "calibration", "direct", tasks)
    study.candidates(s, "calibration", "direct_sonnet", tasks)
    for kind in ("first", "retest"):
        study.build_pools(s, "calibration", kind, tasks)
        study.judge(s, "calibration", kind, tasks)
        study.summarize_pools(s, kind, tasks)
    report = study.write_readout(s)

    rows = spend.rows(s.ledger)
    totals = study.ledger_report(s)["calibration"]
    assert {kind: {model: (row["reserved"], row.get("made")) for model, row in models.items()}
            for kind, models in totals.items()} == {"candidate": {H: (8, 8), S: (2, 2)}, "judge": {H: (4, 4), S: (4, 4)}}
    assert calls_before_reservation(spend.starts(rows)) == []
    assert study.candidates(s, "calibration", "direct", tasks) == [] and spend.rows(s.ledger) == rows  # no relaunch

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

    c = report["calibration"]
    assert (report["anchor_failures"], c["selected"], c["judges"][H]["V3"]["clones"], c["judges"][H]["V3"]["mean_abs"],
            c["gates"]["G1"]["survivors"], c["gates"]["G2"]["haiku_mean"], c["gates"]["G3"]["gap"], c["decision"]) == (
        [], H, 14, 0, 0, 4, 4, "redraw")
    (line,) = [x for x in (s.results / "readout.md").read_text().splitlines() if x.startswith("Decision:")]
    assert (line.startswith("Decision: redraw"), "V4 (agreement with the hidden tests) was not assessed" in line) == (
        True, True)  # 2 toy tasks: too few candidates per hidden class, and the decision says so
    assert [e["event"] for e in study.ledger_report(s)["events"]] == ["freeze", "smoke", "decision"]
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
