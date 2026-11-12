"""Host-side commands that run candidate code: the visible check and the hidden tests (plan Step 2).

They run outside the sandbox, so they must never reach a real provider. `guarded` runs a command with fresh copies
of the Thread M no-provider stubs first on PATH (any `claude` or `codex` it starts by name exits 97 and is
logged), HOME, CLAUDE_CONFIG_DIR and CODEX_HOME at an empty directory (no credentials to find), and every
provider credential and COMPARE_/SEED_SET_ variable removed. It returns the process and the stubs' log lines; a
caller fails its check loudly on any logged line. A real CLI started by absolute path finds no credentials.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # the study's checkout: its modules run from here
STUBS = ROOT / "experiments" / "thread_m" / "no_provider"
CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN_FILE",
               "OPENAI_API_KEY", "CODEX_API_KEY")


def guarded(argv, cwd=None, timeout=None):
    """(completed process, provider attempts) of `argv` run behind fresh no-provider stubs and an empty home."""
    with tempfile.TemporaryDirectory(prefix="seed-set-host-") as directory:
        box = Path(directory)
        shutil.copytree(STUBS, box / "guard" / "no_provider")  # they log to box/guard/no-provider.log
        (box / "home").mkdir()
        env = {key: value for key, value in os.environ.items()
               if key not in CREDENTIALS and not key.startswith(("COMPARE_", "SEED_SET_", "ANTHROPIC_"))}
        env |= {"PATH": f"{box / 'guard' / 'no_provider'}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
                "HOME": str(box / "home"), "CLAUDE_CONFIG_DIR": str(box / "home" / ".claude"),
                "CODEX_HOME": str(box / "home" / ".codex"), "PYTHONDONTWRITEBYTECODE": "1"}
        done = subprocess.run(argv, cwd=cwd or ROOT, env=env, capture_output=True, text=True, timeout=timeout)
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
                                  "--runtime", str(runtime)])
    if attempts:
        print(f"PROVIDER ATTEMPT in the visible check of {patch}: {attempts}", file=sys.stderr)
        return {"passed": False, "failing": ["the candidate's code attempted a provider call"], "excerpt": "",
                "provider_attempts": attempts}
    if done.returncode:
        raise SystemExit(f"visible check of {patch} failed to run: {done.stderr[-2000:]}")
    return json.loads(done.stdout)


def hidden_check(task, patch, runtime):
    """The task's hidden set on the patch applied to a fresh base clone, behind the guard: {"passed", "failing"}.
    A provider attempt fails it."""
    done, attempts = guarded([sys.executable, "-m", "experiments.seed_set.host", str(task), str(patch), str(runtime)])
    if attempts:
        print(f"PROVIDER ATTEMPT in the hidden tests of {patch}: {attempts}", file=sys.stderr)
        return {"passed": False, "failing": ["the candidate's code attempted a provider call"],
                "provider_attempts": attempts}
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
    done, attempts = guarded([sys.executable, "-m", "experiments.compare.summarize", "--pool", str(pool),
                              "--criterion", str(criterion)])
    if attempts:
        raise SystemExit(f"PROVIDER ATTEMPT in the hidden tests of {pool}: {attempts}")
    if done.returncode:
        raise SystemExit(f"summarize refused {pool}: {(done.stderr or done.stdout).strip()[-2000:]}")
    return json.loads((Path(pool) / "records" / "results.json").read_text())


if __name__ == "__main__":  # the guarded hidden check: python -m experiments.seed_set.host TASK PATCH RUNTIME
    print(json.dumps(_hidden(*sys.argv[1:4])))
