"""Fixtures for the structural search evaluation tests: scripted `claude`/`codex` and a tiny task package.

The scripted executables stand in for the real CLIs behind the comparison-harness shims (no provider is
called). Each reads its prompt on stdin, takes the first entry of the JSON list in $SCRIPTED_RESULTS_FILE
whose `match` substring occurs in the prompt, sleeps its `sleep` seconds (default 0), prints its `print` text (default
none) and either writes its `result` (JSON) to
the file on the prompt's last `- path:` line (the shims hide $ORCHESTRATOR_OUTPUT_BUNDLE_PATH) or, with `exit`, exits
with that status without writing anything.
They are named `claude` and `codex` because the provider templates run those names.

The runtime is a detached worktree of a shared clone of this checkout's HEAD (the real orchestrator,
committed and clean; `run_arm` refuses a runtime that is its own main checkout) into which the task
repository's solution commit and its parent, the base commit, are fetched, so `run_arm` can resolve and fetch
the base and the driver can check the operator's solution hash.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.orc_structural_search.config import ExperimentConfig
from tests.experiments.qualification_support import measure_free, sha
from tests.experiments.compare_harness_support import OUTSIDE_SANDBOX_MOUNTS, commit, git, open_up

REPO = Path(__file__).resolve().parents[2]
SEEDS = REPO / "experiments" / "orc_structural_search" / "seeds"
PYTHON_PARENT = REPO / "experiments" / "orc_structural_search" / "three_arm" / "python"  # the I3 parent
I3_CONFIG = ExperimentConfig(
    mutable_files=("direct.py",), mutable_definitions=("run",), condition="topology-only", interface="I3",
    entry_workflow="direct::run", source_root=".", providers_file="providers.json", command_boundaries_file=None,
    episode_wall_clock_sec=600, criterion_sha256=None)
SCRIPTED = f"""#!{sys.executable} -I
import json, os, re, sys, time
prompt = sys.stdin.read()
for entry in json.load(open(os.environ["SCRIPTED_RESULTS_FILE"])):
    if entry["match"] in prompt:
        break
else:
    sys.exit("scripted provider: no entry matches the prompt")
time.sleep(entry.get("sleep", 0))
print(entry.get("print", ""), flush=True)
if "exit" in entry:
    sys.exit(entry["exit"])
with open(re.findall(r"^- path: (.+)$", prompt, re.M)[-1], "w") as out:
    json.dump(entry["result"], out)
"""
DEV_CHECK = {"argv": [sys.executable, "-c", "import pkg"], "timeout_sec": 30}
# The scripted I1 mutator: reads the episode index from EPISODE.md's first line ("# Episode <n>") and edits
# direct.orc in its working directory. 0: wraps the coder call in an `if` on a literal (a structural child);
# 1: renames the `change` binding (a rename child, the parent's skeleton); 2: edits the import (refused).
MUTATOR = f"""#!{sys.executable} -I
import re
from pathlib import Path
index = int(re.match(r"# Episode (\\d+)", Path("EPISODE.md").read_text()).group(1))
edits = [
    [("(change (provider-result providers.coder", "(change (if true (provider-result providers.coder"),
     (":timeout-sec 5400)))", ':timeout-sec 5400) (record Change :summary "skipped" :account "skipped"))))')],
    [("(change (provider-result", "(result (provider-result"), ("change.summary", "result.summary")],
    [("(import common :only (Change Outcome))", "(import common :only (Change CheckReport Outcome))")],
][index]
source = Path("direct.orc").read_text()
for old, new in edits:
    assert source.count(old) == 1, old
    source = source.replace(old, new)
Path("direct.orc").write_text(source)
"""
# The scripted I2 mutator: reads the episode index and the site ("Site: <owner>@<file>:<line>:<column>") from
# EPISODE.md, replaces the form starting at the site and writes HYPOTHESIS.txt. 0: wraps the site's call in an `if`
# on a literal; 1: the same, and renames the `change` binding outside the site (scope_exceeded); 2: a call of a fresh
# `defproc` helper holding a planner call of the same type; 3: the string literal "x" (no manifest type).
MUTATOR_I2 = f"""#!{sys.executable} -I
import re
from pathlib import Path
brief = Path("EPISODE.md").read_text()
index = int(re.match(r"# Episode (\\d+)", brief).group(1))
name, line, column = re.search(r"^Site: .*@(.+):(\\d+):(\\d+)$", brief, re.M).groups()
source = Path(name).read_text()
start = sum(len(text) for text in source.splitlines(keepends=True)[:int(line) - 1]) + int(column) - 1
depth = 0
for end in range(start, len(source)):  # ponytail: the seeds' site forms hold no parenthesis inside a string
    depth += {{"(": 1, ")": -1}}.get(source[end], 0)
    if depth == 0:
        break
call = source[start:end + 1]
wrapped = f'(if true {{call}} (record Change :summary "skipped" :account "skipped"))'
helper = ("(defproc plan-change ((task String) (repo String)) -> Change\\n    :effects ((uses-provider providers.planner))"
          "\\n    (provider-result providers.planner :prompt (implement-prompt :task task :repo repo)"
          ' :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 5400))\\n\\n  (defworkflow run')
replacement, extra = [
    (wrapped, []),
    (wrapped, [("(change ", "(result "), ("change.summary", "result.summary")]),
    ("(plan-change task repo)", [("(defworkflow run", helper)]),
    ('"x"', []),
][index]
source = source[:start] + replacement + source[end + 1:]
for old, new in extra:
    assert source.count(old) == 1, old
    source = source.replace(old, new)
Path(name).write_text(source)
Path("HYPOTHESIS.txt").write_text(f"episode {{index}} should do better\\nsecond line\\n")
"""


def python_pair(tmp_path: Path, *edits: tuple[str, str]) -> tuple[Path, Path]:
    """(parent, child): copies of the I3 parent; the child's direct.py with each (old, new) edit applied once."""
    parent, child = tmp_path / "parent", tmp_path / "child"
    for root in (parent, child):
        shutil.copytree(PYTHON_PARENT, root, ignore=shutil.ignore_patterns("__pycache__"))
    source = (child / "direct.py").read_text()
    for old, new in edits:
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    (child / "direct.py").write_text(source)
    return parent, child


@pytest.fixture
def pyright():
    if shutil.which("pyright") is None:
        pytest.skip("pyright is not on PATH")


def script(world, entries):
    """Make `entries` (match/result or match/exit) the scripted providers' answers."""
    world.results.write_text(json.dumps(entries))


@pytest.fixture
def world(tmp_path):
    """A clean runtime clone holding a tiny task repository's base commit, its task package, the seed catalog
    as a candidate root, an evidence root and the scripted providers (all but the runtime, task and candidate
    outside the shims' sandbox mounts)."""
    task_repo = tmp_path / "task-repo"
    task_repo.mkdir()
    git(task_repo, "init", "-q")
    base = commit(task_repo, {".gitignore": ".orchestrate/\n", "pkg/__init__.py": "VALUE = 1\n"}, "base")
    solution = commit(task_repo, {"pkg/__init__.py": "VALUE = 2\n"}, "solution")
    main, runtime = tmp_path / "main", tmp_path / "runtime"
    git(REPO, "clone", "-q", "--shared", "--no-checkout", str(REPO), str(main))
    git(main, "fetch", "-q", str(task_repo), solution)  # and its parent, the base
    git(main, "worktree", "add", "-q", "--detach", str(runtime), "HEAD")
    task = tmp_path / "task-1"
    for name, text in {"task.txt": "Set VALUE to 2.\n", "intent.txt": "VALUE is 2.\n", "base_commit": base + "\n",
                       "seed/dev-check.json": json.dumps(DEV_CHECK)}.items():
        (task / name).parent.mkdir(parents=True, exist_ok=True)
        (task / name).write_text(text)
    candidate = tmp_path / "candidate"
    shutil.copytree(SEEDS, candidate, ignore=shutil.ignore_patterns("__pycache__"))
    OUTSIDE_SANDBOX_MOUNTS.mkdir(parents=True, exist_ok=True)
    outside = Path(tempfile.mkdtemp(dir=OUTSIDE_SANDBOX_MOUNTS))
    fakebin = outside / "fakebin"
    fakebin.mkdir()
    for name in ("claude", "codex"):
        (fakebin / name).write_text(SCRIPTED)
        (fakebin / name).chmod(0o755)
    criterion = measure_free(tmp_path, tasks=[task])
    yield SimpleNamespace(criterion=criterion, tmp=tmp_path, runtime=runtime, task=task, candidate=candidate, fakebin=fakebin, solution=solution,
                          results=outside / "results.json", evidence=outside / "evidence", outside=outside)
    open_up(tmp_path)
    open_up(outside)
    shutil.rmtree(outside)


def launch_config(world, config):
    """Mechanics fixtures declare measure-free execution explicitly and bind its actual criterion bytes."""
    from dataclasses import replace
    return replace(config, criterion_sha256=sha(world.criterion))
