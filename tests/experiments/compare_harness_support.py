"""Fixtures and helpers for the comparison harness tests (experiments/compare).

Everything runs on temporary git repositories: a main repository, a detached worktree of it as the
frozen runtime, and a stand-in agent CLI that runs its prompt as a shell script through the real
shim. memo.jsonl and run.json files are synthetic; no provider is called.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.compare import pool as pooling, prepare, sandbox

REPO = Path(__file__).resolve().parents[2]
SHIM = REPO / "experiments" / "compare" / "shim"
UPSTREAM = (
    "diff --git a/pkg/calc.py b/pkg/calc.py\n--- a/pkg/calc.py\n+++ b/pkg/calc.py\n"
    "@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b\n"
)
SYMPTOM = (
    "diff --git a/pkg/calc.py b/pkg/calc.py\n--- a/pkg/calc.py\n+++ b/pkg/calc.py\n"
    "@@ -1,2 +1,4 @@\n def add(a, b):\n+    if (a, b) == (2, 3):\n+        return 5\n     return a - b\n"
)
RUNTIME_MAIN = (  # the frozen runtime's stand-in orchestrator: reports where and how it was started
    "import json, os, sys\nprint(json.dumps({'main': __file__, 'cwd': os.getcwd(), 'argv': sys.argv[1:],"
    " 'path0': os.environ['PATH'].split(':')[0], 'env': {k: os.environ.get(k) for k in"
    " ('PYTHONPATH', 'COMPARE_ROOT', 'COMPARE_TREE', 'COMPARE_BASE', 'TMPDIR')}}))\n"
)
HIDDEN_TEST = (
    "from pathlib import Path\n\nfrom pkg.calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\n"
    "def test_zero():\n    assert add(0, 0) == 0\n\n\ndef test_no_git():\n    assert not Path('.git').exists()\n"
)
READY = {"variant": "READY", "report": "artifacts/review/r.md", "rounds": 1}
OUTSIDE_SANDBOX_MOUNTS = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "compare-harness-tests"


def skip_without_sandbox():
    """Skip the calling test module where the shims cannot build their sandbox (no bwrap on PATH, or no
    unprivileged user namespaces)."""
    probe = ["bwrap", "--dev-bind", "/", "/", "--tmpfs", "/dev/shm", "--tmpfs", "/var/tmp", "--unshare-pid", "--proc", "/proc", "true"]
    if shutil.which("bwrap") is None or subprocess.run(probe, capture_output=True).returncode:
        pytest.skip(f"the shims need bubblewrap: `{' '.join(probe)}` fails here", allow_module_level=True)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, files, message):
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def write_test_sandbox_config(fakebin, path, *, readonly_files=(), environment_names=()):
    """Start from discovered OS/catalog/skill dependencies, then admit exact test fakes and inputs."""
    declaration = sandbox.dependencies({"PATH": "", "HOME": str(Path.home())})
    declaration["readonly"] = dict(declaration["readonly"])
    for name in ("codex", "claude"):
        exact = Path(fakebin / name).resolve(strict=True)
        declaration[name] = str(exact)
    declaration["environment"] = sorted(set(declaration["environment"]) | {
        "CLAUDE_ARGV_LOG", "SCRIPTED_RESULTS_FILE", "TASK_DIFFICULTY_PLAN", "TASK_DIFFICULTY_CALLS",
        "TASK_DIFFICULTY_ATTEMPT", "FAKE_SCORE_PLAN", "FAKE_SCORE_CALLS", *environment_names})
    for value in readonly_files:
        exact = Path(value).resolve(strict=True)
        declaration["readonly"][str(exact)] = str(exact)
    path = Path(path)
    path.write_text(json.dumps(declaration, indent=2) + "\n")
    return path


def configure_test_sandbox(world, monkeypatch, *, readonly_files=(), environment_names=(),
                           path_entries=(), codex=None, claude=None):
    """Add exact fake inputs/dependencies to this fixture's controller-owned declaration."""
    declaration = json.loads(world.sandbox_config.read_text())
    declaration["readonly"] = dict(declaration["readonly"])
    declaration["path"] = list(declaration["path"])
    declaration["environment"] = sorted(set(declaration["environment"]) | set(environment_names))
    declaration["path"] = [str(Path(path).resolve()) for path in path_entries] + [
        value for value in declaration["path"] if value not in {str(Path(path).resolve()) for path in path_entries}]
    for path in readonly_files:
        exact = Path(path).resolve(strict=True)
        declaration["readonly"][str(exact)] = str(exact)
    for name, path in (("codex", codex), ("claude", claude)):
        if path is None:
            continue
        exact = Path(path).resolve(strict=True)
        declaration[name] = str(exact)
        declaration["path"] = [str(exact.parent), *[item for item in declaration["path"]
                                                      if item != str(exact.parent)]]
    world.sandbox_config.write_text(json.dumps(declaration, indent=2) + "\n")
    monkeypatch.setenv("COMPARE_SANDBOX", str(world.sandbox_config))
    return declaration


def write_task(task, base, *, anchors=True, hidden=False):
    files = {"task.txt": "Make add correct.\n", "intent.txt": "add returns the sum.\n", "base_commit": base,
             "seed/bugs/report.md": "add(2, 3) returns -1\n"}
    files |= {"anchors/upstream.diff": UPSTREAM, "anchors/symptom.diff": SYMPTOM} if anchors else {}
    files |= {"hidden/tests/test_hidden.py": HIDDEN_TEST, "hidden_tests.txt": "".join(
        f"tests/test_hidden.py::test_{name}\n" for name in ("add", "zero", "no_git", "missing"))} if hidden else {}
    for name, text in files.items():
        (task / name).parent.mkdir(parents=True, exist_ok=True)
        (task / name).write_text(text)


def open_up(directory):
    """Make the harness's not-listable directories listable again so pytest can remove them."""
    directory.chmod(0o755)
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            open_up(child)


@pytest.fixture
def world(tmp_path, monkeypatch):
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q")
    old = commit(main, {"README.md": "toy\n", ".gitignore": ".orchestrate/\nartifacts/\n"}, "old")
    base = commit(main, {"pkg/__init__.py": "", "pkg/calc.py": "def add(a, b):\n    return a - b\n",
                         "orchestrator/__init__.py": "", "orchestrator/__main__.py": "print('candidate')\n"}, "base")
    solution = commit(main, {"pkg/calc.py": "def add(a, b):\n    return a + b\n",
                             "orchestrator/__main__.py": RUNTIME_MAIN}, "solution")
    runtime = tmp_path / "runtime"
    git(main, "worktree", "add", "-q", "--detach", str(runtime), solution)
    write_task(tmp_path / "task", base[:10] + "\n")
    criterion = tmp_path / "criterion.json"
    criterion.write_text(json.dumps({
        "primary": [{"measure": "best_of_n.group_gain_mean", "op": ">=", "value": 0.75}],
        "secondary": [{"measure": "best_of_n.paired_gain_mean", "op": ">=", "value": 0}],
        "judges": ["judge-a", "judge-b"],
    }))
    # agents' trees, pools and the stand-in CLIs must lie outside /tmp and /dev/shm, which the shims'
    # sandbox replaces
    OUTSIDE_SANDBOX_MOUNTS.mkdir(parents=True, exist_ok=True)
    outside = Path(tempfile.mkdtemp(dir=OUTSIDE_SANDBOX_MOUNTS))
    fakebin = outside / "fakebin"
    fakebin.mkdir()
    for name in ("claude", "codex"):
        (fakebin / name).write_text('#!/bin/sh\necho "PYTHONPATH=${PYTHONPATH-unset}"\nexec bash -c "$(cat)"\n')
        (fakebin / name).chmod(0o755)
    sandbox_config = outside / "sandbox-dependencies.json"
    write_test_sandbox_config(fakebin, sandbox_config)
    empty_home = tmp_path / "empty-host-home"
    empty_home.mkdir()
    monkeypatch.setenv("COMPARE_SANDBOX", str(sandbox_config))
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("CODEX_HOME", str(empty_home / ".codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(empty_home / ".claude"))
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_OAUTH_TOKEN_FILE"):
        monkeypatch.delenv(key, raising=False)
    yield SimpleNamespace(tmp=tmp_path, main=main, old=old, base=base, solution=solution, runtime=runtime,
                          task=tmp_path / "task", criterion=criterion, fakebin=fakebin, root=outside / "work",
                          outside=outside, sandbox_config=sandbox_config, empty_home=empty_home)
    open_up(tmp_path)
    open_up(outside)
    shutil.rmtree(outside)


def start(world, arm, candidates=None, sets=(), task=None, root=None, apply=None):
    sets = sets or {"design_review_execute": ("planner_model=p", "reviewer_model=r"),
                    "direct_task": ("model=m", "effort=high")}.get(arm, ())
    apply = apply or (world.task / "anchors" / "upstream.diff" if arm == "review_once" else None)
    records = prepare.run_arm(task or world.task, arm, root or world.root, world.runtime, candidates, sets, apply)
    return records, json.loads((records / "record.json").read_text())


def call(world, record, script, binary="claude", args=None):
    args = args if args is not None else (("exec",) if binary == "codex" else ("-p",))
    env = {**os.environ, "PATH": f"{SHIM}:{world.fakebin}:{os.environ['PATH']}", "COMPARE_ROOT": record["records"],
           "COMPARE_TREE": record["tree"], "COMPARE_BASE": record["compare_base"], "PYTHONPATH": str(world.runtime),
           "OLDPWD": str(world.runtime), "COMPARE_SANDBOX": record["sandbox"]["declaration"]}
    return subprocess.run([str(SHIM / binary), *args], input=script, text=True, capture_output=True,
                          cwd=record["cwd"], env=env)


def write_memo(record, prompts, value, outcome="completed", run_id="r1", effect_class="provider"):
    rows = []
    for index, prompt in enumerate(prompts):
        identity = f"workflow / effect {index}"
        digest = "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()
        rows.append({"record": "started", "identity": identity, "attempt": 1, "time": 100.0 + index,
                     "input_parts": {"prompt": digest}})
        rows.append({"record": "committed", "identity": identity, "attempt": 1, "effect_class": effect_class,
                     "value": {}, "time": 101.0 + index})
    terminal = {"record": "terminal", "outcome": outcome}
    terminal |= {"value": value} if outcome == "completed" else {"code": "provider_timeout", "message": "t"}
    memo = Path(record["state_root"]) / run_id / "memo.jsonl"
    memo.parent.mkdir(parents=True, exist_ok=True)
    memo.write_text("".join(json.dumps(row) + "\n" for row in [*rows, terminal]))


def drive(world, arm, scripts, value, candidates=None, task=None, outcome="completed", verdict=None, apply=None):
    """Start a run, make each call through the shim, write its memo, collect and scan it."""
    records, record = start(world, arm, candidates, task=task, apply=apply)
    for script in scripts:
        assert call(world, record, script).returncode == 0
    write_memo(record, scripts, value(record) if callable(value) else value, outcome)
    collected = prepare.collect(records)
    prepare.scan(records, world.solution)
    if verdict:
        prepare.adjudicate(records, *verdict)
    return records, collected


def selects(k):
    return lambda record: {"winner": record["candidates"][k - 1], "ranking": [], "report": "artifacts/review/r.md"}


def edit(cand, body, design=False):
    script = f"cd {cand} && printf 'def add(a, b):\\n    return {body}\\n' > pkg/calc.py && echo 'X = 1' > pkg/extra.py"
    return script + (" && mkdir -p docs/design && echo d > docs/design/plan.md\n" if design else "\n")


@pytest.fixture
def pooled(world):
    """One best_of_n run (two candidates, the second with a design file), two reviewed_change runs
    (one whose final patch equals its first), one control run and one failed control run."""
    implement = edit("$PWD", "a + b")
    runs = [
        drive(world, "best_of_n", [edit("$PWD/cand-1", "a + b"), edit("$PWD/cand-2", "b + a", design=True),
                                   "true"], selects(2), candidates=2)[0],
        drive(world, "reviewed_change", [implement, "true", edit("$PWD", "a * 1 + b"), "true"], READY)[0],
        drive(world, "reviewed_change", [implement, "true"], READY)[0],
        drive(world, "direct_task", [edit("$PWD", "b + a")], True)[0],
        drive(world, "direct_task", ["true"], None, outcome="failed")[0],
    ]
    out = world.outside / "pool"
    judges = ["judge-a", f"judge-b={REPO / 'experiments/compare/providers/score_codex.json'}"]
    mapping = pooling.pool(world.task, world.criterion, out, judges, runs)
    return SimpleNamespace(out=out, mapping=mapping, failed=runs[-1])
