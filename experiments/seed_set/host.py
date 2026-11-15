"""Host-side commands that run candidate code: the visible check and the hidden tests (plan Step 2).

They run outside the sandbox, so they must never reach a real provider. `guarded` runs a command with fresh copies
of the Thread M no-provider stubs first on PATH (any `claude` or `codex` it starts by name exits 97 and is
logged), HOME, CLAUDE_CONFIG_DIR and CODEX_HOME at an empty directory (no credentials to find), and every
provider credential and COMPARE_/SEED_SET_ variable removed. It returns the process and the stubs' log lines; a
caller fails its check loudly on any logged line. A real CLI started by absolute path finds no credentials.

The command runs under the launch guard (`reaper.run`: a session of its own, its whole tree killed if the study's
process dies) with two bounds. Each hidden test gets `HIDDEN_TEST_SEC`, twice the plan's bound for a whole hidden
run on the oracle (120 s, plan Step 1): one still running past it counts as that test failing (fix round 3,
coordinator ruling 1; the kit passes it to summarize.py, whose own default stays). The check's backstop, for a
harness that itself hangs (re-review N2): a patch's hidden set gets `CHECK_SEC`, five times the 120 s; the visible
check gets dev-check.json's own 600 s plus `CHECK_SEC` for the clone and the setup; a pool's summary gets
`CHECK_SEC` per clone. A hidden set's backstop adds `HIDDEN_TEST_SEC` per hidden test (per clone that runs them, for
a summary), so hanging tests fail at their own bound first (final scoped check M2). A check past its backstop is
recorded as timed out, never as a pass or a failure: `timed_out` with `passed` None (the probe files the run as an
incident, the readout counts it apart), and a summary that times out refuses, so its pool is an incident.

A check's temporary directories (`temporary`) are named in the study's `host-temp.jsonl` with the process that made
them, and the check's commands make theirs inside (TMPDIR), so a launcher killed with SIGKILL during a check leaves
nothing the next study command's `sweep` does not find (fix round 3, ruling 3).
"""

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from experiments.seed_set import reaper, units

ROOT = Path(__file__).resolve().parents[2]  # the study's checkout: its modules run from here
HIDDEN_RUN_SEC, MARGIN = 120, 5  # plan Step 1: a hidden run under 120 s on the oracle; a candidate's code may be slower
CHECK_SEC = HIDDEN_RUN_SEC * MARGIN  # the backstop on one clone's hidden set
HIDDEN_TEST_SEC = 2 * HIDDEN_RUN_SEC  # one hidden test (fix round 3, ruling 1): past it, that test fails
VISIBLE_SEC = 600 + CHECK_SEC  # dev-check.json's timeout_sec (600 in every package) and the clone's setup
STUBS = ROOT / "experiments" / "thread_m" / "no_provider"
CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN_FILE",
               "OPENAI_API_KEY", "CODEX_API_KEY")
PREFIXES = ("seed-set-host-", "seed-set-view-")  # the temporary directories the kit makes and records


@contextlib.contextmanager
def temporary(prefix, record=None):
    """A temporary directory named in `record` (a study's `host_temp`) with this process's pid and start time as
    soon as it exists, so `sweep` finds it if a SIGKILL skips its removal; None records nothing."""
    with tempfile.TemporaryDirectory(prefix=prefix) as directory:
        if record:  # ponytail: a SIGKILL between the mkdir and this write leaves one directory unrecorded
            with open(record, "a") as out:
                out.write(json.dumps({"path": directory, "pid": os.getpid(),
                                      "started": reaper.stat(os.getpid())[1]}) + "\n")
        yield Path(directory)


def sweep(record):
    """Remove each directory `record` names whose maker (pid and start time) and whose check's session no longer
    run, and return their paths; the record keeps the others. Only a directory the kit makes is touched (`kits`); a
    line naming any other path is named on stderr, skipped and kept (final scoped check B1)."""
    if not Path(record).is_file():
        return []
    kept, removed = [], []
    for line in Path(record).read_text().splitlines():
        entry = json.loads(line)
        path = Path(entry["path"])
        if not kits(path):
            print(f"{record} names {path}, not a directory the kit makes (a direct child of "
                  f"{tempfile.gettempdir()} named {' or '.join(PREFIXES)}, no symlink): skipped", file=sys.stderr)
            kept.append(line + "\n")
            continue
        if not path.exists():
            continue
        if maker_runs(entry) or units.session_alive(path / "check.pgid"):
            kept.append(line + "\n")
            continue
        subprocess.run(["chmod", "-R", "u+rwx", str(path)], check=False)  # a test's read-only leftovers
        shutil.rmtree(path)
        removed.append(str(path))
    Path(record).write_text("".join(kept))
    return removed


def kits(path):
    """Whether `path` can be a directory `temporary` made: a direct child of the temp directory, named with a kit
    prefix, whose real path is `path` itself (no `..`, no symlinked parent, not a symlink)."""
    return (path.name.startswith(PREFIXES) and path.parent == Path(tempfile.gettempdir())
            and os.path.realpath(path) == str(path))


def maker_runs(entry):
    found = reaper.stat(entry["pid"])
    return found is not None and found[1] == entry["started"]


def guarded(argv, cwd=None, timeout=CHECK_SEC, record=None):
    """(completed process, provider attempts) of `argv` run under the launch guard behind fresh no-provider stubs
    and an empty home, in a box `temporary` records in `record`; the process's returncode is "timeout" when it ran
    past `timeout` seconds (its tree killed)."""
    with temporary("seed-set-host-", record) as box:
        shutil.copytree(STUBS, box / "guard" / "no_provider")  # they log to box/guard/no-provider.log
        (box / "home").mkdir()
        (box / "tmp").mkdir()
        env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"
               and key not in CREDENTIALS and not key.startswith(("COMPARE_", "SEED_SET_", "ANTHROPIC_"))}
        # bytecode goes to the box, never into a tree, and is reused: with none written, a test whose subprocess
        # imports the package under a short timeout failed under load (1fd10ab4c3, coordinator ruling 2026-11-12)
        env |= {"PATH": f"{box / 'guard' / 'no_provider'}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
                "HOME": str(box / "home"), "CLAUDE_CONFIG_DIR": str(box / "home" / ".claude"),
                "CODEX_HOME": str(box / "home" / ".codex"), "PYTHONPYCACHEPREFIX": str(box / "pycache"),
                "TMPDIR": str(box / "tmp")}  # what the check makes in a temporary directory goes with the box
        with open(box / "stdout", "w") as out, open(box / "stderr", "w") as err:
            status = reaper.run(argv, box / "check.pgid", timeout, cwd=cwd or ROOT, env=env, stdout=out, stderr=err)
        done = subprocess.CompletedProcess(argv, status, (box / "stdout").read_text(), (box / "stderr").read_text())
        log = box / "guard" / "no-provider.log"
        return done, log.read_text().splitlines() if log.is_file() else []


def in_tree_view(task, directory):
    """A check-withheld package (one with `withheld/`) as the in-tree package it was made from: the withheld test
    files back in `seed/` and no `withheld` flag, so the catalog's trusted check runs the same test. Else `task`."""
    task = Path(task)
    if not (task / "withheld").is_dir():
        return task
    view = Path(directory) / task.name
    shutil.copytree(task, view)
    shutil.copytree(task / "withheld", view / "seed", dirs_exist_ok=True)
    config = json.loads((view / "seed" / "dev-check.json").read_text())
    config.pop("withheld")
    (view / "seed" / "dev-check.json").write_text(json.dumps(config))
    return view


def visible_check(task, patch, runtime, record=None):
    """evaluation.check_first_attempt run behind the guard; a logged provider attempt fails the check."""
    with temporary("seed-set-view-", record) as directory:
        done, attempts = guarded([sys.executable, "-m", "experiments.orc_structural_search.evaluation", "check",
                                  "--task", str(in_tree_view(task, directory)), "--patch", str(patch),
                                  "--runtime", str(runtime)], timeout=VISIBLE_SEC, record=record)
    if attempts:
        print(f"PROVIDER ATTEMPT in the visible check of {patch}: {attempts}", file=sys.stderr)
        return {"passed": False, "failing": ["the candidate's code attempted a provider call"], "excerpt": "",
                "provider_attempts": attempts}
    if done.returncode == "timeout":
        return {"passed": None, "failing": [], "excerpt": "",
                "timed_out": f"the visible check ran past {VISIBLE_SEC:g} s"}
    if done.returncode:
        raise SystemExit(f"visible check of {patch} failed to run: {done.stderr[-2000:]}")
    return json.loads(done.stdout)


def hidden_check(task, patch, runtime, record=None):
    """The task's hidden set on the patch applied to a fresh base clone, behind the guard: {"passed", "failing"}.
    A provider attempt fails it."""
    bound = backstop(task)
    done, attempts = guarded([sys.executable, "-m", "experiments.seed_set.host", str(task), str(patch), str(runtime),
                              str(HIDDEN_TEST_SEC)], timeout=bound, record=record)
    if attempts:
        print(f"PROVIDER ATTEMPT in the hidden tests of {patch}: {attempts}", file=sys.stderr)
        return {"passed": False, "failing": ["the candidate's code attempted a provider call"],
                "provider_attempts": attempts}
    if done.returncode == "timeout":
        return {"passed": None, "failing": [], "timed_out": f"the hidden tests ran past {bound:g} s"}
    if done.returncode:
        raise SystemExit(f"hidden tests of {patch} failed to run: {done.stderr[-2000:]}")
    return json.loads(done.stdout)


def backstop(task):
    """The backstop on one clone's hidden set of `task` (final scoped check M2): `CHECK_SEC` for the clone and the
    harness, plus `HIDDEN_TEST_SEC` per hidden test, so every hidden test can hang to its own bound and fail first."""
    listed = Path(task) / "hidden_tests.txt"
    return CHECK_SEC + HIDDEN_TEST_SEC * (len(listed.read_text().split()) if listed.is_file() else 0)


def summary_backstop(pool):
    """A pool's summary backstop: `CHECK_SEC` per clone (one at least), plus each clone's hidden tests at
    `HIDDEN_TEST_SEC` for every clone whose hidden tests run (summarize.py runs none on a reference clone)."""
    mapping = Path(pool) / "records" / "mapping.json"  # without one, summarize.py refuses the pool itself
    mapping = json.loads(mapping.read_text()) if mapping.is_file() else {}
    clones = mapping.get("clones", {})
    tests = backstop(mapping["task"]) - CHECK_SEC if "task" in mapping else 0
    return CHECK_SEC * max(1, len(clones)) + tests * sum(clone.get("arm") != "reference" for clone in clones.values())


def _hidden(task, patch, runtime, test_sec):
    from experiments.compare.repos import build_candidate, git
    from experiments.compare.summarize import hidden_failures
    task, nodes = Path(task), (Path(task) / "hidden_tests.txt").read_text().split()
    base = git(runtime, "rev-parse", "--verify", (task / "base_commit").read_text().strip() + "^{commit}")
    with tempfile.TemporaryDirectory(prefix="seed-set-hidden-") as directory:
        clone = Path(directory) / "candidate"
        build_candidate(Path(runtime), base, task / "seed", clone)
        if Path(patch).stat().st_size and subprocess.run(["git", "-C", str(clone), "apply", "--binary", str(patch)],
                                                         capture_output=True).returncode:
            return {"passed": False, "failing": ["the patch does not apply"]}
        failing = hidden_failures(clone, task, nodes, sys.executable, float(test_sec))
    return {"passed": not failing, "failing": failing}


def summarize(pool, criterion, record=None):
    """summarize.py (which runs the hidden tests, each bounded at `HIDDEN_TEST_SEC`) behind the guard; refuses on
    a provider attempt and past its backstop."""
    bound = summary_backstop(pool)
    done, attempts = guarded([sys.executable, "-m", "experiments.compare.summarize", "--pool", str(pool),
                              "--criterion", str(criterion), "--hidden-test-timeout-sec", str(HIDDEN_TEST_SEC)],
                             timeout=bound, record=record)
    if attempts:
        raise SystemExit(f"PROVIDER ATTEMPT in the hidden tests of {pool}: {attempts}")
    if done.returncode == "timeout":
        raise SystemExit(f"summarize of {pool} ran past its backstop of {bound:g} s ({CHECK_SEC:g} s a clone and "
                         f"{HIDDEN_TEST_SEC:g} s a hidden test, past which that test fails): the harness hung")
    if done.returncode:
        raise SystemExit(f"summarize refused {pool}: {(done.stderr or done.stdout).strip()[-2000:]}")
    return json.loads((Path(pool) / "records" / "results.json").read_text())


if __name__ == "__main__":  # the guarded hidden check: python -m experiments.seed_set.host TASK PATCH RUNTIME SEC
    print(json.dumps(_hidden(*sys.argv[1:5])))
