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

from experiments.compare import pool as pooling, prepare, scan
from experiments.compare.repos import sha256_file
from experiments.seed_set import forms, host, layout, probing, readout, rules, seeds, spend, study, units
from tests.experiments.compare_harness_support import (
    OUTSIDE_SANDBOX_MOUNTS, commit, git, open_up, skip_without_sandbox, write_test_sandbox_config,
)
from tests.agent_session_shims import closed_path
from tests.experiments.seed_set_offline_support import (
    CODEX_STUB, CODEX_USD, CODEX_VERSION, SPEND_TERMS, STUB, VERSION, hanging_harness, stable_anchors,
    stand_in_codex_login, stand_in_login, stand_in_terms, write_frozen_criterion,
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
    stable_anchors(runtime / "seedset" / "tasks.jsonl", root=runtime)
    git(runtime, "add", "-A", "seedset")
    git(runtime, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "tasks")
    OUTSIDE_SANDBOX_MOUNTS.mkdir(parents=True, exist_ok=True)
    outside = Path(tempfile.mkdtemp(dir=OUTSIDE_SANDBOX_MOUNTS))
    fakebin = outside / "fakebin"
    fakebin.mkdir()
    for name, stub in (("claude", STUB), ("codex", CODEX_STUB)):
        (fakebin / name).write_text(stub)
        (fakebin / name).chmod(0o755)
    stub_plan = outside / "stub-plan.json"
    stub_plan.write_text(json.dumps(plan))
    declaration = write_test_sandbox_config(fakebin, outside / "sandbox.json", readonly_files=(stub_plan,),
                                            environment_names=("SEED_SET_STUB_PLAN",))
    empty = tmp_path / "empty-home"
    stand_in_login(empty / ".claude")  # stand-ins the sandbox copies into each unit
    stand_in_codex_login(empty / ".codex")
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
    host.sweep(s.host_temp)  # what a host-side check of a launcher a test killed left in the temporary directory
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


LUNA_TRANCHE = layout.LUNA_SMOKE
LUNA_TERMS = {**SPEND_TERMS["ceiling_usd"], LUNA_TRANCHE: 10.0}  # ruling L-R8's ceiling, set at the freeze


@pytest.fixture
def luna_world(world, monkeypatch):
    """The world authorized for the Luna smoke on the smoke task `sub`, the stand-in Luna fixing it on its first
    attempt, and a freeze naming the Luna smoke's ceiling and both stand-in CLIs' pins."""
    s = world.study
    write_frozen_criterion(s, frozen="toy", spend=stand_in_terms(world.fakebin, ceiling_usd=LUNA_TERMS))
    rules.record_freeze(s)
    plan = json.loads(Path(world.plan).read_text())
    plan["tasks"][SMOKE]["fix"][spend.LUNA] = 1
    Path(world.plan).write_text(json.dumps(plan))
    monkeypatch.setenv(spend.AUTHORIZATION, LUNA_TRANCHE)
    return world


def luna_unit(world):
    """Run the Luna smoke's `direct_luna` unit; return (records, its study.json facts)."""
    study.candidates(world.study, LUNA_TRANCHE, "direct_luna", [SMOKE])
    (path,) = study.study_runs(world.study)
    return path.parent, json.loads(path.read_text())


def finish_luna_smoke(world):
    """The Luna smoke's pool, its one judge, the summary and `smoke-check`; returns the check's ledger row."""
    s = world.study
    study.build_pools(s, LUNA_TRANCHE, layout.LUNA_POOL, [SMOKE])
    study.judge(s, LUNA_TRANCHE, layout.LUNA_POOL, [SMOKE])
    study.summarize_pools(s, layout.LUNA_POOL, [SMOKE])
    return rules.smoke_check(s, LUNA_TRANCHE)


def failed_checks(row):
    return sorted(name for name, passed in row["checks"].items() if not passed)


def test_offline_the_luna_smoke_passes_its_check_and_records_no_claude_smoke(luna_world):
    """Luna plan T8 (ruling L-R8): both Luna arms once, one pool of their runs and the anchors, one Haiku judge."""
    s = luna_world.study
    for arm in layout.PLANNED[LUNA_TRANCHE]:
        study.candidates(s, LUNA_TRANCHE, arm, [SMOKE])
    row = finish_luna_smoke(luna_world)
    results = json.loads((s.results / "pools" / f"{SMOKE}-{layout.LUNA_POOL}" / "results.json").read_text())
    assert (row["event"], row["passed"], failed_checks(row), spend.latest(spend.rows(s.ledger), "smoke"),
            {judge for clone in results["clones"].values() for judge in clone["ratings"]}, len(results["clones"])) == (
        LUNA_TRANCHE, True, [], None, {H}, 4)


def test_offline_the_luna_smoke_spends_within_its_caps(luna_world):
    s = luna_world.study
    for arm in layout.PLANNED[LUNA_TRANCHE]:
        study.candidates(s, LUNA_TRANCHE, arm, [SMOKE])
    finish_luna_smoke(luna_world)
    totals = study.ledger_report(s)[LUNA_TRANCHE]
    assert {kind: {model: (row["reserved"], row.get("made")) for model, row in models.items()}
            for kind, models in totals.items()} == {"candidate": {spend.LUNA: (4, 2)}, "judge": {H: (1, 1)}}


def test_offline_a_luna_smoke_unit_cut_by_a_usage_limit_fails_the_check(luna_world):
    s, reset = luna_world.study, int(time.time()) - 60
    limit_plan(luna_world, task=SMOKE, model=spend.LUNA, reset=reset)
    study.candidates(s, LUNA_TRANCHE, "direct_luna", [SMOKE])
    with pytest.raises(SystemExit, match="closed by a usage limit"):
        study.candidates(s, LUNA_TRANCHE, "retry_until_check_luna", [SMOKE])
    limit_plan(luna_world)
    reopen(s, reset)
    study.candidates(s, LUNA_TRANCHE, "retry_until_check_luna", [SMOKE])
    assert study.candidates(s, LUNA_TRANCHE, "direct_luna", [SMOKE]) == []  # a smoke's cut slot never runs again
    row = finish_luna_smoke(luna_world)
    assert (row["passed"], failed_checks(row)) == (  # the limit's wording is also a provider error line
        False, ["no_provider_errors", "no_unit_cut_by_a_usage_limit"])


def test_offline_a_credit_pause_during_the_luna_smoke_fails_the_check(luna_world):
    s, plan = luna_world.study, json.loads(Path(luna_world.plan).read_text())
    Path(luna_world.plan).write_text(json.dumps(plan | {"credits": True}))
    study.candidates(s, LUNA_TRANCHE, "direct_luna", [SMOKE])
    with pytest.raises(SystemExit, match="credit balance"):
        study.candidates(s, LUNA_TRANCHE, "retry_until_check_luna", [SMOKE])
    Path(luna_world.plan).write_text(json.dumps(plan))
    word = time.time()
    spend.resume_after_limit(s.ledger, word, 2.0, 35.0, word, closes=units.CODEX)
    study.candidates(s, LUNA_TRANCHE, "retry_until_check_luna", [SMOKE])
    row = finish_luna_smoke(luna_world)
    assert (row["passed"], failed_checks(row)) == (False, ["no_credit_pause"])


def test_offline_the_luna_smoke_runs_no_claude_arm(luna_world):
    with pytest.raises(SystemExit, match="luna_smoke runs"):
        study.candidates(luna_world.study, LUNA_TRANCHE, "direct", [SMOKE])
    assert spend.starts(spend.rows(luna_world.study.ledger)) == []


def plan_with(world, **keys):
    """Rewrite the stand-ins' plan with `keys` added; return the plan as it was."""
    plan = json.loads(Path(world.plan).read_text())
    Path(world.plan).write_text(json.dumps(plan | keys))
    return plan


def test_offline_a_luna_smoke_incident_fails_its_check_and_stops_nothing(luna_world, monkeypatch):
    """Ruling L-R9: an incident in the Luna smoke (here a session that ran at another effort) fails that smoke; the
    10% incident stop counts the study's tranches only, so a Haiku smoke start is still allowed."""
    s = luna_world.study
    plan = plan_with(luna_world, rollout_effort="high")
    study.candidates(s, LUNA_TRANCHE, "direct_luna", [SMOKE])
    Path(luna_world.plan).write_text(json.dumps(plan))
    study.candidates(s, LUNA_TRANCHE, "retry_until_check_luna", [SMOKE])
    row = finish_luna_smoke(luna_world)
    monkeypatch.setenv(spend.AUTHORIZATION, "smoke")
    study.candidates(s, "smoke", "direct", [SMOKE])
    assert (row["passed"], "every_program_ran_without_incident" in failed_checks(row),
            spend.latest(spend.rows(s.ledger), "stop"), [r["model"] for r in spend.starts(spend.rows(s.ledger))
                                                         if r["tranche"] == "smoke"]) == (False, True, None, [H])


def test_offline_a_forbidden_model_in_a_luna_smoke_unit_stops_the_study(luna_world):
    s = luna_world.study
    plan_with(luna_world, rollout_model="gpt-6.1-sol")
    luna_unit(luna_world)
    with pytest.raises(SystemExit, match="the study is stopped"):
        study.candidates(s, LUNA_TRANCHE, "retry_until_check_luna", [SMOKE])
    assert spend.latest(spend.rows(s.ledger), "stop")["reason"].startswith("forbidden model")


def test_offline_both_smokes_on_the_smoke_task_keep_their_runs_apart_and_both_pass(luna_world, monkeypatch):
    """Each smoke's pool on the shared smoke task holds only its own tranche's runs (and the anchors)."""
    s = luna_world.study
    for tranche in rules.SMOKE_POOLS:
        monkeypatch.setenv(spend.AUTHORIZATION, tranche)
        for arm in layout.PLANNED[tranche]:
            study.candidates(s, tranche, arm, [SMOKE])
    tranche_of = {str(path.parent): json.loads(path.read_text())["tranche"] for path in study.study_runs(s)}
    held, passed = {}, {}
    for tranche, kind in rules.SMOKE_POOLS.items():
        monkeypatch.setenv(spend.AUTHORIZATION, tranche)
        study.build_pools(s, tranche, kind, [SMOKE])
        study.judge(s, tranche, kind, [SMOKE])
        study.summarize_pools(s, kind, [SMOKE])
        results = json.loads((s.results / "pools" / f"{SMOKE}-{kind}" / "results.json").read_text())
        held[tranche] = {tranche_of.get(clone["run"], clone["arm"]) for clone in results["clones"].values()}
        passed[tranche] = rules.smoke_check(s, tranche)["passed"]
    assert (held, passed) == ({"smoke": {"smoke", "anchor"}, LUNA_TRANCHE: {LUNA_TRANCHE, "anchor"}},
                              {"smoke": True, LUNA_TRANCHE: True})


def test_offline_the_calibration_readout_reads_no_luna_pool(luna_world):
    """The Luna smoke's summarized pool, even one whose ratings no longer bind to its patches, leaves the
    calibration's readout as it is without it."""
    s = luna_world.study
    for arm in layout.PLANNED[LUNA_TRANCHE]:
        study.candidates(s, LUNA_TRANCHE, arm, [SMOKE])
    finish_luna_smoke(luna_world)
    luna = s.results / "pools" / f"{SMOKE}-{layout.LUNA_POOL}"
    next((luna / "patches").glob("*.diff")).write_text("another patch\n")  # a binding failure, were it read
    choose(s, ["a0a0a0a0a0"])
    with_luna = study.write_readout(s)
    shutil.rmtree(luna)
    assert study.write_readout(s) == with_luna


def test_offline_a_luna_unit_settles_with_its_fix_scan_and_session_audit_clean(luna_world):
    """Luna plan T7: one Luna unit behind the real shims, sandbox and model guard, the stand-in `codex` answering."""
    records, facts = luna_unit(luna_world)
    keys = ("outcome", "calls", "scan_hits", "sessions", "incident", "metering_complete")
    assert ({k: facts.get(k) for k in keys}, facts["visible"]["passed"],
            json.loads((records / "record.json").read_text())["scan"]["hits"]) == (
        {"outcome": "completed", "calls": 1, "scan_hits": 0, "sessions": 1, "incident": None,
         "metering_complete": True}, True, [])


def test_offline_a_luna_unit_is_priced_from_its_codex_usage_and_reserved_on_the_codex_pin(luna_world):
    records, facts = luna_unit(luna_world)
    (start,) = spend.starts(spend.rows(luna_world.study.ledger))
    assert (facts["priced"], start["cli"], spend.priced(luna_world.study.ledger)[LUNA_TRANCHE]["settled_usd"]) == (
        {"usd": CODEX_USD, "missing": [], "calls": {"1": CODEX_USD}},
        {"path": str((luna_world.fakebin / "codex").resolve()), "version": CODEX_VERSION}, CODEX_USD)


def test_offline_a_luna_unit_calls_codex_alone_bound_to_its_model_and_effort(luna_world):
    """Its one call is Codex's with the model and effort bound; its one rollout is the one the scan reads; no Claude
    session, no user skill, and no credential copy left."""
    records, facts = luna_unit(luna_world)
    record = json.loads((records / "record.json").read_text())
    home = Path(record["sandbox"]["home"])
    assert ((records / "calls" / "1" / "provider.txt").read_text(), rules.bound_argv(records, spend.LUNA, "medium"),
            units.rollouts(home), list(home.glob(".claude/projects/*/*.jsonl")), list(home.glob(".codex/skills/*")),
            credentials(luna_world.study)) == (
        "codex\n", True, list(scan.codex_sessions(Path(record["tree"]), record["created_at"], home)), [], [], [])
    assert len(units.rollouts(home)) == 1


def test_offline_a_freeze_with_a_luna_cap_and_only_the_claude_pin_refuses(luna_world):
    s = luna_world.study
    claude_pin = stand_in_terms(luna_world.fakebin)["cli"]["claude"]
    write_frozen_criterion(s, frozen="toy", spend=stand_in_terms(luna_world.fakebin, ceiling_usd=LUNA_TERMS,
                                                                 cli=claude_pin))
    with pytest.raises(SystemExit, match=r"pin \(path and version\) of the CLI that runs gpt-6-luna \(codex\)"):
        rules.record_freeze(s)


def test_offline_a_luna_unit_prepared_with_another_codex_model_list_never_starts(luna_world, monkeypatch):
    """Review finding 3: the unit's command sets the Codex model list the guard enforces; one naming another model
    refuses the start before any reservation, and leaves no tree."""
    run_arm = study.prepare.run_arm

    def rebound(*args, **kwargs):
        records = run_arm(*args, **kwargs)
        command = records / "command.sh"
        command.write_text(command.read_text().replace(f"COMPARE_CODEX_MODELS={spend.LUNA}",
                                                       "COMPARE_CODEX_MODELS=gpt-6.1-sol"))
        return records
    monkeypatch.setattr(study.prepare, "run_arm", rebound)
    with pytest.raises(SystemExit, match="Codex models \\['gpt-6.1-sol'\\]"):
        luna_unit(luna_world)
    s = luna_world.study
    assert (spend.starts(spend.rows(s.ledger)), list((s.work / "agents").iterdir()), credentials(s)) == ([], [], [])


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


def test_offline_pool_refuses_scan_hits_without_a_verdict_before_building_and_builds_after_adjudication(
        world, monkeypatch):
    """A forgotten adjudication stops `pool` with the command to run; it writes no incident, so the task's pool is
    built once the operator has adjudicated."""
    s, task = world.study, "a0a0a0a0a0"
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    study.candidates(s, "calibration", "direct", [task])
    study.candidates(s, "calibration", "direct_sonnet", [task])
    run = study.study_runs(s)[0].parent
    record = json.loads((run / "record.json").read_text())
    hit = {"file": "calls/1/stdout.txt", "line": 1, "pattern": "github.com", "text": "see github.com/x"}
    (run / "record.json").write_text(json.dumps(record | {"scan": record["scan"] | {"hits": [hit]}}))
    with pytest.raises(SystemExit, match=re.escape(f"prepare.py scan --run {run} --verdict")):
        study.build_pools(s, "calibration", "first", [task])
    assert (layout.current_pool(s, task, "first").exists(), (s.results / "pools" / f"{task}-first").exists()) == (
        False, False)
    prepare.adjudicate(run, "cleared", "a benign mention")
    study.build_pools(s, "calibration", "first", [task])
    assert (layout.current_pool(s, task, "first") / "records" / "mapping.json").exists()
    (run / "record.json").write_text(json.dumps(record | {"scan": record["scan"] | {"hits": [hit]}}))
    with pytest.raises(SystemExit, match="built once"):  # a pool not to be built asks for no verdict
        study.build_pools(s, "calibration", "first", [task])


def test_offline_summarize_refuses_judge_hits_without_a_verdict_and_summarizes_after_adjudication(world, monkeypatch):
    """A judge's forgotten adjudication stops `summarize` with the command to run, before any incident or result."""
    s, task = world.study, "a0a0a0a0a0"
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    study.candidates(s, "calibration", "direct", [task])
    study.candidates(s, "calibration", "direct_sonnet", [task])
    study.build_pools(s, "calibration", "first", [task])
    study.judge(s, "calibration", "first", [task])
    out = layout.current_pool(s, task, "first")
    path = out / "records" / "judges" / H / "scan.json"
    found = json.loads(path.read_text())
    hit = {"file": "calls/1/stdout.txt", "line": 1, "pattern": "github.com", "text": "see github.com/x"}
    path.write_text(json.dumps(found | {"hits": [hit]}))
    with pytest.raises(SystemExit, match=re.escape(f"prepare.py scan --pool {out} --judge {H} --verdict")):
        study.summarize_pools(s, "first", [task])
    assert ((s.results / "pools" / f"{task}-first").exists(), (out / "clones").exists()) == (False, True)
    pooling.adjudicate_judge(out, H, "cleared", "a benign mention")
    study.summarize_pools(s, "first", [task])
    assert (s.results / "pools" / f"{task}-first" / "results.json").exists()


def test_offline_smoke_check_refuses_scan_hits_without_a_verdict_and_records_nothing(world, monkeypatch):
    """A forgotten adjudication stops `smoke-check` before it records a pass or a fail in the ledger."""
    s = world.study
    monkeypatch.setenv(spend.AUTHORIZATION, "smoke")
    study.candidates(s, "smoke", "direct", [SMOKE])
    run = study.study_runs(s)[0].parent
    record = json.loads((run / "record.json").read_text())
    hit = {"file": "calls/1/stdout.txt", "line": 1, "pattern": "github.com", "text": "see github.com/x"}
    (run / "record.json").write_text(json.dumps(record | {"scan": record["scan"] | {"hits": [hit]}}))
    ledger = s.ledger.read_bytes()
    with pytest.raises(SystemExit, match=re.escape(f"prepare.py scan --run {run} --verdict")):
        rules.smoke_check(s)
    assert s.ledger.read_bytes() == ledger


def test_offline_a_judge_call_with_paid_extra_usage_that_ended_normally_keeps_its_judgment(world, monkeypatch):
    """Coordinator ruling on fix round 4: the Haiku judge's call shows paid extra usage and ends normally. Its
    judgment is kept (not cut, no rebuild); starts close until `resume-after-limit`, then the Sonnet judge runs on
    the same pool and the pool is summarised."""
    s, task = world.study, "a0a0a0a0a0"
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    study.candidates(s, "calibration", "direct", [task])
    study.candidates(s, "calibration", "direct_sonnet", [task])
    study.build_pools(s, "calibration", "first", [task])
    plan = json.loads(Path(world.plan).read_text())
    Path(world.plan).write_text(json.dumps(plan | {"paid_usage": {"judge": H}}))
    with pytest.raises(SystemExit, match="paid extra usage"):  # the pause closes the Sonnet judge's start
        study.judge(s, "calibration", "first", [task])
    Path(world.plan).write_text(json.dumps(plan))
    reset = time.time()
    spend.resume_after_limit(s.ledger, reset, 2.0, 35.0, reset)
    study.judge(s, "calibration", "first", [task])
    study.summarize_pools(s, "first", [task])
    results = json.loads((s.results / "pools" / f"{task}-first" / "results.json").read_text())
    judges = [(r["model"], Path(r["unit"].partition("#")[0]).name) for r in spend.starts(spend.rows(s.ledger))
              if r["kind"] == "judge"]
    assert (all(set(c["ratings"]) == {H, S} for c in results["clones"].values()), sorted(judges)) == (
        True, [(H, "first"), (S, "first")])


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


def in_the_visible_check(world, monkeypatch, pids, task="a0a0a0a0a0"):
    """A launcher process running `candidates` for one Sonnet run of `task`, returned once the settlement's visible
    check runs the candidate's code on the host (a conftest that sleeps two minutes and records its pid in `pids`)."""
    s = world.study
    pids.mkdir(mode=0o700)
    hang(world, pids, seconds=120)
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
    return launcher


def hang(world, pids, **conftest_sleep):
    """Have the stand-in's implementer calls leave candidate code that sleeps in host-side checks."""
    plan = json.loads(Path(world.plan).read_text())
    Path(world.plan).write_text(json.dumps(plan | {"conftest_sleep": {"pids": str(pids), **conftest_sleep}}))


def test_offline_a_killed_launcher_takes_its_settlements_visible_check_with_it(world, monkeypatch, tmp_path):
    """Re-review N2: kill -9 of the launcher while the settlement's visible check runs the candidate's code on the
    host (a conftest that sleeps two minutes). The check runs under the launch guard: nothing of it lives on, and
    processes that are not the unit's (one in a session of its own, one in this test's group) are untouched."""
    pids = tmp_path / "host-pids"
    launcher = in_the_visible_check(world, monkeypatch, pids)
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


def test_offline_the_next_command_removes_the_temporary_directories_of_a_killed_launchers_host_check(
        world, monkeypatch, tmp_path, capsys):  # fix round 3, ruling 3
    """kill -9 of the launcher during the settlement's visible check leaves the check's temporary directories (the
    launcher runs no cleanup). The next study command's sweep removes the ones the kit recorded and prints them."""
    s, pids = world.study, tmp_path / "host-pids"
    launcher = in_the_visible_check(world, monkeypatch, pids)
    made = [Path(json.loads(line)["path"]) for line in s.host_temp.read_text().splitlines()]
    launcher.kill()
    launcher.wait()
    gone = time.time() + 30
    while time.time() < gone and (running(pids) or unit_processes(world)):
        time.sleep(0.5)
    left = [path.exists() for path in made]
    with pytest.raises(SystemExit, match="runs"):  # refused after the sweep
        study.candidates(s, "calibration", "no_such_arm", ["a0a0a0a0a0"])
    printed = capsys.readouterr().out
    assert (left, [path.exists() for path in made], [str(path) in printed for path in made]) == (
        [True, True], [False, False], [True, True])


HUNG = "tests/test_hidden_add.py::test_hidden_1"  # a hidden test of `add` that passes on a fixed tree; not the
# first: the first pytest of a check compiles its bytecode cache, which may take longer than a small bound


def test_offline_a_hidden_test_past_its_bound_fails_that_test_and_the_pool_is_summarised(world, monkeypatch, tmp_path):
    """Fix round 3, ruling 1: one hidden test of the Sonnet clone hangs (its conftest sleeps); past the kit's bound on
    one hidden test (240 s in the study, 10 s here) it counts as failed, and the pool is summarised."""
    s, task, pids = world.study, "a0a0a0a0a0", tmp_path / "host-pids"
    pids.mkdir(mode=0o700)
    hang(world, pids, seconds=60, task=task, model=S, node=HUNG)
    monkeypatch.setattr(host, "HIDDEN_TEST_SEC", 10)
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    study.candidates(s, "calibration", "direct", [task])
    study.candidates(s, "calibration", "direct_sonnet", [task])
    study.build_pools(s, "calibration", "first", [task])
    study.judge(s, "calibration", "first", [task])
    study.summarize_pools(s, "first", [task])
    results = json.loads((s.results / "pools" / f"{task}-first" / "results.json").read_text())
    failed = [clone["hidden_failed"] for clone in results["clones"].values() if clone["arm"] == "direct_sonnet"]
    assert (failed, len(os.listdir(pids)), running(pids)) == ([[HUNG]], 1, [])


def test_offline_a_hidden_test_past_its_bound_fails_that_test_in_a_probe_runs_hidden_check(world, monkeypatch,
                                                                                            tmp_path):
    """Fix round 3, ruling 1, on the probe's hidden check: the hanging test fails, the run is no incident."""
    s, task, pids = world.study, "a0a0a0a0a0", tmp_path / "host-pids"
    pids.mkdir(mode=0o700)
    package = study.task_dir(s, task)
    conftest = ["import os, sys, time", f"if {HUNG!r} in ' '.join(sys.argv):",
                f"    open(os.path.join({str(pids)!r}, str(os.getpid())), 'w').close()", "    time.sleep(60)"]
    patch = tmp_path / "final.diff"
    patch.write_text((package / "anchors" / f"{task}-upstream.diff").read_text()
                     + "diff --git a/conftest.py b/conftest.py\nnew file mode 100644\n--- /dev/null\n+++ b/conftest.py\n"
                     + f"@@ -0,0 +1,{len(conftest)} @@\n" + "".join(f"+{line}\n" for line in conftest))
    monkeypatch.setattr(host, "HIDDEN_TEST_SEC", 10)
    result = host.hidden_check(package, patch, s.runtime)
    assert (result, len(os.listdir(pids)), running(pids)) == ({"passed": False, "failing": [HUNG]}, 1, [])


def test_offline_three_hidden_tests_hanging_at_their_bound_are_three_failures_not_a_timeout(world, monkeypatch,
                                                                                            tmp_path):
    """Final scoped check M2: the hidden check's backstop is CHECK_SEC plus HIDDEN_TEST_SEC per hidden test, so
    every hidden test of `add` hanging (here 3 x 5 s, past a 10 s CHECK_SEC) reads as three failing tests."""
    s, task, pids = world.study, "a0a0a0a0a0", tmp_path / "host-pids"
    pids.mkdir(mode=0o700)
    package = study.task_dir(s, task)
    with (package / "hidden" / "tests" / "test_hidden_add.py").open("a") as hidden:  # a third hidden test
        hidden.write("def test_hidden_2():\n    assert add(1, 1) == 2\n")
    with (package / "hidden_tests.txt").open("a") as listed:
        listed.write("tests/test_hidden_add.py::test_hidden_2\n")
    nodes = (package / "hidden_tests.txt").read_text().split()
    conftest = ["import os, sys, time", "if 'test_hidden_' in ' '.join(sys.argv):",
                f"    open(os.path.join({str(pids)!r}, str(os.getpid())), 'w').close()", "    time.sleep(60)"]
    patch = tmp_path / "final.diff"
    patch.write_text((package / "anchors" / f"{task}-upstream.diff").read_text()
                     + "diff --git a/conftest.py b/conftest.py\nnew file mode 100644\n--- /dev/null\n+++ b/conftest.py\n"
                     + f"@@ -0,0 +1,{len(conftest)} @@\n" + "".join(f"+{line}\n" for line in conftest))
    monkeypatch.setattr(host, "HIDDEN_TEST_SEC", 5)
    monkeypatch.setattr(host, "CHECK_SEC", 10)
    result = host.hidden_check(package, patch, s.runtime)
    assert (result, len(nodes), len(os.listdir(pids)), running(pids)) == (
        {"passed": False, "failing": nodes}, 3, 3, [])


def test_offline_a_summary_whose_harness_hangs_past_the_per_clone_bound_makes_its_pool_an_incident(
        world, monkeypatch, tmp_path):
    """Fix round 3, ruling 1: the per-clone bound is the backstop for a harness that itself hangs (here a stand-in
    summarize.py that sleeps): the pool is an incident, and the harness's process is killed."""
    s, task, pids = world.study, "a0a0a0a0a0", tmp_path / "harness-pids"
    pids.mkdir(mode=0o700)
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    study.candidates(s, "calibration", "direct", [task])
    study.candidates(s, "calibration", "direct_sonnet", [task])
    study.build_pools(s, "calibration", "first", [task])
    study.judge(s, "calibration", "first", [task])
    monkeypatch.setattr(host, "ROOT", hanging_harness(tmp_path / "checkout", pids))
    monkeypatch.setattr(host, "CHECK_SEC", 1)
    monkeypatch.setattr(host, "HIDDEN_TEST_SEC", 0)  # the backstop is CHECK_SEC per clone alone
    study.summarize_pools(s, "first", [task])
    dest = s.results / "pools" / f"{task}-first"
    incident = json.loads((dest / "incident.json").read_text())["reason"]
    assert ("ran past its backstop of 7 s" in incident, (dest / "results.json").exists(), len(os.listdir(pids)),
            running(pids)) == (True, False, 1, [])


def after_launch(monkeypatch, then):
    """Run each unit's real launch, then `then(records, record)`: what the agent or an interruption leaves. Returns
    the wall-clock limits the launches were given."""
    real, limits = study.launch, []

    def launched(command, env, log, timeout):
        limits.append(timeout)
        status = real(command, env, log, timeout)
        records = Path(log).parent
        then(records, json.loads((records / "record.json").read_text()))
        return status
    monkeypatch.setattr(study, "launch", launched)
    return limits


def read_only_leftover(record):
    """A read-only directory under the unit's tmp, as the agent's own tests leave a sandbox snapshot (ruling R16), with
    absolute links out of the tree as a snapshot's rootfs holds them."""
    workspace = Path(record["tree"]) / "tmp" / "snapshots" / "rootfs" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "file").write_text("x")
    (workspace.parent / "usr").symlink_to("/usr")
    (workspace.parent / "python").symlink_to(sys.executable)
    for path in (workspace, workspace.parent):
        path.chmod(0o555)


def test_offline_an_interrupted_settlement_of_a_tree_with_read_only_directories_settles_again(world, monkeypatch):
    s, task = world.study, "a0a0a0a0a0"
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)

    def interrupted(records, record):  # the runner dies after an earlier settlement copied the run state
        read_only_leftover(record)
        shutil.copytree(record["state_root"], records / "state")
        raise SystemExit("the runner was interrupted")
    after_launch(monkeypatch, interrupted)
    with pytest.raises(SystemExit, match="interrupted"):
        study.candidates(s, "calibration", "direct_sonnet", [task])
    (records,) = [path.parent for path in study.study_runs(s)]
    study.settle_runs(s, [records])
    facts = json.loads((records / "study.json").read_text())
    tree = Path(json.loads((records / "record.json").read_text())["tree"])
    assert ((facts["calls"], facts["outcome"], "tree_left" in facts), tree.exists(), credentials(s),
            any((records / "state").glob("*/memo.jsonl"))) == ((1, "completed", False), False, [], True)


def test_offline_a_tree_that_cannot_be_removed_keeps_the_settlement_and_removes_the_credentials(world, monkeypatch):
    s, task = world.study, "a0a0a0a0a0"
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    locked = []

    def unremovable(records, record):
        locked.append(Path(record["tree"]).parent)
        locked[0].chmod(0o555)
    limits = after_launch(monkeypatch, unremovable)
    try:
        study.candidates(s, "calibration", "direct_sonnet", [task])
    finally:
        for path in locked:
            path.chmod(0o755)
    (facts,) = facts_of(s)
    (unit,) = [row["unit"] for row in spend.starts(spend.rows(s.ledger))]
    settled = [row for row in spend.rows(s.ledger) if row.get("event") == "settle" and row["unit"] == unit]
    assert (facts["calls"], facts["outcome"], facts["tree_left"].startswith("PermissionError"), credentials(s),
            len(settled), limits) == (1, "completed", True, [], 1, [study.unit_sec(1, study.CALL_SEC)])


def test_offline_a_second_settlement_of_a_run_whose_login_failed_is_an_incident(world, monkeypatch):
    """The stuck probe run's shape (ruling R16): the call ends on an expired login, the tree holds read-only
    directories, and an interrupted settlement left `records/state`; settling it again records the incident."""
    s, task = world.study, "a0a0a0a0a0"
    monkeypatch.setenv(spend.AUTHORIZATION, "calibration")
    choose(s, [task])
    spend.record(s.ledger, "smoke", passed=True)
    Path(world.plan).write_text(json.dumps(json.loads(Path(world.plan).read_text()) | {
        "auth_error": {"task": task, "model": S}}))

    def interrupted(records, record):
        read_only_leftover(record)
        shutil.copytree(record["state_root"], records / "state")
        raise SystemExit("the runner was interrupted")
    after_launch(monkeypatch, interrupted)
    with pytest.raises(SystemExit, match="interrupted"):
        study.candidates(s, "calibration", "direct_sonnet", [task])
    (records,) = [path.parent for path in study.study_runs(s)]
    study.settle_runs(s, [records])
    facts = json.loads((records / "study.json").read_text())
    tree = Path(json.loads((records / "record.json").read_text())["tree"])
    assert (facts["calls"], "authenticat" in facts.get("incident", "").lower(), "tree_left" in facts, tree.exists(),
            credentials(s)) == (1, True, False, False, [])


# --- the seed evaluation's pools (seed evaluation apparatus plan, B3) ---------------------------------------

SEED = layout.SEED_EVALUATION
SEED_ARMS = {"direct": 6, "retry_until_check": 2, "implement_check_repair": 3, "implement_review_revise": 3}
SEED_TASK = "a0a0a0a0a0"
SEED_TASKS = ["b1b1b1b1b1", SEED_TASK]  # the seed task list: `SEED_TASK` second, so its deal starts on batch 1


def fabricated_seed_run(world, arm, k, facts=()):
    """Run `k` of `arm` on `SEED_TASK` in the seed evaluation, prepared by the harness and never launched: its
    collection written by hand (a completed run whose final patch is the task's reference fix; no call, so the scan
    covers none), then scanned by the harness, and its start reserved. Its study.json says one call; `facts` join
    it."""
    s = world.study
    spec = layout.load_arms(s)[arm]
    arm_spec = prepare.ArmSpec(s.programs / spec["source"], spec["entry"], s.programs,
                               s.programs / study.PROVIDERS["claude"], study.INPUTS,
                               command_boundaries=s.programs / "commands.json")
    records = prepare.run_arm(study.task_dir(s, SEED_TASK), arm, s.work, s.runtime, spec=arm_spec,
                              sets=(f"model={H}", "effort=medium"), environment=study.launch_env(H, spec["max_calls"]))
    record = json.loads((records / "record.json").read_text())
    units.forget_credentials(record["sandbox"]["home"])
    (records / "collected").mkdir()
    (records / "collected" / "final.diff").write_bytes(
        (study.task_dir(s, SEED_TASK) / "anchors" / f"{SEED_TASK}-upstream.diff").read_bytes())
    (records / "record.json").write_text(json.dumps(record | {
        "outcome": "completed", "failure": None, "selected": None, "variant": None, "calls": 0,  # none launched
        "wall_clock_sec": 1.0, "patches": {"final": "collected/final.diff"}}))
    prepare.scan(records, world.fixes[SEED_TASK])
    spend.reserve(s.ledger, SEED, "candidate", H, spec["max_calls"], records, price=(50.0, 0.25), task=SEED_TASK,
                  arm=arm)
    (records / "study.json").write_text(json.dumps({
        "tranche": SEED, "task": SEED_TASK, "arm": arm, "model": H, "effort": "medium",
        "max_calls": spec["max_calls"], "calls": 1, "outcome": "completed", "failure": None, "scan_hits": 0,
        **dict(facts)}))
    return records


@pytest.fixture
def seed_world(world, monkeypatch):
    """The world with the seed evaluation authorized and capped in this process only (Haiku the selected judge),
    a stored calibration result, the task list `SEED_TASKS` with its `seed_tasks` event, judge-seeds.json naming
    Haiku and frozen, and the planned 14 runs on `SEED_TASK` fabricated and started."""
    from tests.experiments.test_seed_set import world as calibration_world
    s = world.study
    monkeypatch.setattr(spend, "UNAUTHORIZED", ("extension",))
    monkeypatch.setitem(spend.CAPS, SEED, {"candidate": {H: 420}, "judge": {H: 32}})
    monkeypatch.setitem(layout.PLANNED, SEED, SEED_ARMS)  # the freeze bounds each priced tranche's units
    monkeypatch.setenv(spend.AUTHORIZATION, SEED)
    s.results.mkdir(parents=True, exist_ok=True)
    records, pools = calibration_world()
    tasks = [f"t{i:02d}" for i in range(20)]
    (s.results / study.CALIBRATION).write_text(json.dumps(readout.report(records, pools, tasks, tasks[:10],
                                                                           {"T3": 20}, {}, {}, {}, 100)))
    (s.results / layout.SEED_TASKS).write_text(json.dumps({"tasks": SEED_TASKS, "judge": H, "insensitive": None,
                                                           "v4_note": None}))
    spend.record(s.ledger, "seed_tasks", tasks_sha256=sha256_file(s.results / layout.SEED_TASKS),
                 calibration_sha256=sha256_file(s.results / study.CALIBRATION))
    s.seed_criterion.write_text(json.dumps({"judges": [H], "rubric": layout.RUBRIC, "primary": [], "secondary": []}))
    write_frozen_criterion(s, frozen="toy", spend=stand_in_terms(world.fakebin, ceiling_usd={
        **SPEND_TERMS["ceiling_usd"], SEED: 50.0}), sha256=rules.required_hashes(s) | {
        layout.SEED_CRITERION: sha256_file(s.seed_criterion)})
    rules.record_freeze(s)
    world.runs = [fabricated_seed_run(world, arm, k, SETTLED | {"visible": {"passed": k > 0}})
                  for arm, n in SEED_ARMS.items() for k in range(n)]
    return world


SETTLED = {"priced": {"usd": 0.01, "missing": []}, "nested_sessions": 0, "tokens": 1000}  # what a settlement adds

def test_offline_a_seed_pool_of_fourteen_runs_is_two_batches_judged_by_one_judge_and_summarized(seed_world):
    s = seed_world.study
    study.build_pools(s, SEED, layout.SEED_POOL, [SEED_TASK])
    out = s.pools / SEED_TASK / layout.SEED_POOL
    mapping = json.loads((out / "records" / "mapping.json").read_text())
    anchors = {cid for cid, clone in mapping["clones"].items() if clone["arm"] == "anchor"}
    assert ([(len(batch), len(anchors & set(batch))) for batch in mapping["batches"]], list(mapping["judges"]),
            sorted(c["run"] for c in mapping["clones"].values() if c["run"])) == (
        [(9, 2), (9, 2)], [H], sorted(str(r.resolve()) for r in seed_world.runs))
    first_direct = str(seed_world.runs[0].resolve())  # dealt first, to batch (task index 1 + arm 0 + run 0) mod 2
    assert [any(mapping["clones"][cid]["run"] == first_direct for cid in batch) for batch in mapping["batches"]] == [
        False, True]

    study.judge(s, SEED, layout.SEED_POOL, [SEED_TASK])
    starts = [row for row in spend.starts(spend.rows(s.ledger)) if row["kind"] == "judge"]
    assert ([(row["kind"], row["model"], row["calls"]) for row in starts],
            json.loads((out / "records" / f"study-{H}.json").read_text())["calls"]) == ([("judge", H, 2)], 2)

    study.summarize_pools(s, layout.SEED_POOL, [SEED_TASK])
    kept = s.results / "pools" / f"{SEED_TASK}-{layout.SEED_POOL}"
    results = json.loads((kept / "results.json").read_text())
    assert (len(results["clones"]), {(c["arm"] == "anchor", tuple(c["ratings"]), c["hidden"] is None)
                                     for c in results["clones"].values()},
            json.loads((kept / "mapping.json").read_text())["batches"]) == (
        18, {(True, (H,), False), (False, (H,), False)}, mapping["batches"])


def test_offline_a_seed_pool_is_refused_for_a_tranche_that_builds_none(seed_world):
    with pytest.raises(SystemExit, match="pools, not seed"):
        study.build_pools(seed_world.study, "calibration", layout.SEED_POOL, [SEED_TASK])


def incident_slots(s, task):
    """Every planned slot of `task` started and settled as an incident (nothing collected), and its pool an
    incident."""
    for arm, planned in SEED_ARMS.items():
        for k in range(planned):
            records = s.work / "records" / f"{task}-{arm}" / f"run-{k}"
            records.mkdir(parents=True)
            spend.reserve(s.ledger, SEED, "candidate", H, 1, records, price=(50.0, 0.25), task=task, arm=arm)
            (records / "study.json").write_text(json.dumps({"tranche": SEED, "task": task, "arm": arm, "model": H,
                                                            "effort": "medium", "max_calls": 1, "calls": 0,
                                                            "incident": "provider: a stand-in incident"}))
            (records / "record.json").write_text("{}")
    study.pool_incident(s, task, layout.SEED_POOL, "not pooled: no completed, uncontaminated run to pool")


def test_offline_the_seed_readout_waits_for_the_whole_tranche_then_reads_the_real_pool(seed_world):
    """The seed readout (B4) over the real pool: while the first seed task never ran it refuses and writes nothing;
    once that task's slots ended as incidents and its pool as an incident, two of four batches are missing, no
    quality claim is made, and the outputs and one `seed_decision` (no stop) are written."""
    s = seed_world.study
    study.build_pools(s, SEED, layout.SEED_POOL, [SEED_TASK])
    study.judge(s, SEED, layout.SEED_POOL, [SEED_TASK])
    study.summarize_pools(s, layout.SEED_POOL, [SEED_TASK])
    spend.record(s.ledger, study.VISIBLE_EVENT, failed=1, checked=6, rate=1 / 6, launch=True)  # C2's event, assumed
    with pytest.raises(SystemExit, match=r"planned seed slots are open .*b1b1b1b1b1/direct: 6 of 6"):
        study.seed_readout(s)
    assert ((s.results / "seeds.json").exists(), spend.latest(spend.rows(s.ledger), "seed_decision")) == (False, None)
    incident_slots(s, SEED_TASKS[0])
    out = study.seed_readout(s)
    decision = [row for row in spend.rows(s.ledger) if row.get("event") in ("seed_decision", "stop")]
    commit = spend.latest(spend.rows(s.ledger), "freeze")["runtime_commit"]
    assert (out["stop"], out["hashes"]["runtime_commit"], [row["event"] for row in decision],
            "## Seed evaluation" in (s.results / "readout.md").read_text()) == (
        f"{seeds.NO_CLAIM}: 2 of 4 batches have reference minus base under 4",
        {"first_seed_start": commit, "latest": commit}, ["seed_decision"], True)


def test_offline_a_seed_pool_refuses_a_run_of_another_seeded_commit(seed_world):
    s = seed_world.study
    path = seed_world.runs[3] / "record.json"
    path.write_text(json.dumps(json.loads(path.read_text()) | {"compare_base": "0" * 40}))
    study.build_pools(s, SEED, layout.SEED_POOL, [SEED_TASK])
    reason = json.loads((s.results / "pools" / f"{SEED_TASK}-{layout.SEED_POOL}" / "incident.json").read_text())
    assert reason["reason"] == "not pooled: runs in one pool must share the task and the seeded commit"


def test_offline_a_settled_run_with_a_nested_session_counts_it(world, monkeypatch):
    s = world.study
    monkeypatch.setenv(spend.AUTHORIZATION, "smoke")
    Path(world.plan).write_text(json.dumps(json.loads(Path(world.plan).read_text()) | {"nested_session": True}))
    study.candidates(s, "smoke", "direct", [SMOKE])
    (path,) = study.study_runs(s)
    facts = json.loads(path.read_text())
    unavailable = json.loads((path.parent / "metering.json").read_text())["consumption"] == "unavailable"
    assert (facts.get("incident"), facts["sessions"], facts["nested_sessions"], unavailable, facts["tokens"]) == (
        None, 2, 1, True, None)  # the Claude stand-in reports no usage: no tokens, never 0


def test_offline_a_settled_run_records_its_metered_tokens(luna_world):
    records, facts = luna_unit(luna_world)  # the stand-in `codex` reports complete usage; the Claude stand-in none
    metered = seeds.metered_tokens(json.loads((records / "metering.json").read_text()))
    assert (metered is not None, facts["tokens"], facts["nested_sessions"]) == (True, metered, 0)
