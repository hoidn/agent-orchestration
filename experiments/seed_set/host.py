"""Host-side commands that run candidate code: the visible check and the hidden tests (plan Step 2).

They run outside the sandbox, so they must never reach a real provider. `guarded` runs a command with fresh copies
of the Thread M no-provider stubs first on PATH (any `claude` or `codex` it starts by name exits 97 and is
logged), HOME, CLAUDE_CONFIG_DIR and CODEX_HOME at an empty directory (no credentials to find), and every
provider credential and COMPARE_/SEED_SET_ variable removed. It returns the process and the stubs' log lines; a
caller fails its check loudly on any logged line. A real CLI started by absolute path finds no credentials.

The command runs under the launch guard (`reaper.run`: a session of its own, its whole tree killed if the study's
process dies) with a bound (re-review N2): a patch's hidden set gets `CHECK_SEC`, five times the plan's bound for a
hidden run on the oracle (120 s, plan Step 1); the visible check gets dev-check.json's own 600 s plus `CHECK_SEC`
for the clone and the setup; a pool's summary gets `CHECK_SEC` per clone. A check past its bound is recorded as
timed out, never as a pass or a failure: `timed_out` with `passed` None (the probe files the run as an incident,
the readout counts it apart), and a summary that times out refuses, so its pool is an incident.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from experiments.seed_set import reaper

ROOT = Path(__file__).resolve().parents[2]  # the study's checkout: its modules run from here
HIDDEN_RUN_SEC, MARGIN = 120, 5  # plan Step 1: a hidden run under 120 s on the oracle; a candidate's code may be slower
CHECK_SEC = HIDDEN_RUN_SEC * MARGIN
VISIBLE_SEC = 600 + CHECK_SEC  # dev-check.json's timeout_sec (600 in every package) and the clone's setup
STUBS = ROOT / "experiments" / "thread_m" / "no_provider"
CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN_FILE",
               "OPENAI_API_KEY", "CODEX_API_KEY")


def guarded(argv, cwd=None, timeout=CHECK_SEC):
    """(completed process, provider attempts) of `argv` run under the launch guard behind fresh no-provider stubs
    and an empty home; the process's returncode is "timeout" when it ran past `timeout` seconds (its tree killed)."""
    with tempfile.TemporaryDirectory(prefix="seed-set-host-") as directory:
        box = Path(directory)
        shutil.copytree(STUBS, box / "guard" / "no_provider")  # they log to box/guard/no-provider.log
        (box / "home").mkdir()
        env = {key: value for key, value in os.environ.items() if key != "PYTHONDONTWRITEBYTECODE"
               and key not in CREDENTIALS and not key.startswith(("COMPARE_", "SEED_SET_", "ANTHROPIC_"))}
        # bytecode goes to the box, never into a tree, and is reused: with none written, a test whose subprocess
        # imports the package under a short timeout failed under load (1fd10ab4c3, coordinator ruling 2026-11-12)
        env |= {"PATH": f"{box / 'guard' / 'no_provider'}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
                "HOME": str(box / "home"), "CLAUDE_CONFIG_DIR": str(box / "home" / ".claude"),
                "CODEX_HOME": str(box / "home" / ".codex"), "PYTHONPYCACHEPREFIX": str(box / "pycache")}
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


def visible_check(task, patch, runtime):
    """evaluation.check_first_attempt run behind the guard; a logged provider attempt fails the check."""
    with tempfile.TemporaryDirectory(prefix="seed-set-view-") as directory:
        done, attempts = guarded([sys.executable, "-m", "experiments.orc_structural_search.evaluation", "check",
                                  "--task", str(in_tree_view(task, directory)), "--patch", str(patch),
                                  "--runtime", str(runtime)], timeout=VISIBLE_SEC)
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


def hidden_check(task, patch, runtime):
    """The task's hidden set on the patch applied to a fresh base clone, behind the guard: {"passed", "failing"}.
    A provider attempt fails it."""
    done, attempts = guarded([sys.executable, "-m", "experiments.seed_set.host", str(task), str(patch), str(runtime)],
                             timeout=CHECK_SEC)
    if attempts:
        print(f"PROVIDER ATTEMPT in the hidden tests of {patch}: {attempts}", file=sys.stderr)
        return {"passed": False, "failing": ["the candidate's code attempted a provider call"],
                "provider_attempts": attempts}
    if done.returncode == "timeout":
        return {"passed": None, "failing": [], "timed_out": f"the hidden tests ran past {CHECK_SEC:g} s"}
    if done.returncode:
        raise SystemExit(f"hidden tests of {patch} failed to run: {done.stderr[-2000:]}")
    return json.loads(done.stdout)


def _hidden(task, patch, runtime):
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
        failing = hidden_failures(clone, task, nodes, sys.executable)
    return {"passed": not failing, "failing": failing}


def summarize(pool, criterion):
    """summarize.py (which runs the hidden tests) behind the guard; refuses on a provider attempt."""
    mapping = Path(pool) / "records" / "mapping.json"  # without one, summarize.py refuses the pool itself
    bound = CHECK_SEC * max(1, len(json.loads(mapping.read_text())["clones"]) if mapping.is_file() else 1)
    done, attempts = guarded([sys.executable, "-m", "experiments.compare.summarize", "--pool", str(pool),
                              "--criterion", str(criterion)], timeout=bound)
    if attempts:
        raise SystemExit(f"PROVIDER ATTEMPT in the hidden tests of {pool}: {attempts}")
    if done.returncode == "timeout":
        raise SystemExit(f"summarize of {pool} ran past {bound:g} s: its hidden tests timed out")
    if done.returncode:
        raise SystemExit(f"summarize refused {pool}: {(done.stderr or done.stdout).strip()[-2000:]}")
    return json.loads((Path(pool) / "records" / "results.json").read_text())


if __name__ == "__main__":  # the guarded hidden check: python -m experiments.seed_set.host TASK PATCH RUNTIME
    print(json.dumps(_hidden(*sys.argv[1:4])))
