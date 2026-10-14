"""Repository helpers shared by prepare.py and pool.py: git, JSON records, candidate builds, patches.

A candidate (or pool clone) is `git init` plus a depth-one fetch of the base commit alone, with the task
package's seed/ committed onto it under a fixed identity and date, so every build of one base and seed
has the same seeded commit. Patches are taken after `git add -A -N .` so new files are included.
Standard library only; needs git on PATH.
"""

import hashlib
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

SEED_COMMIT = ("-c", "user.name=compare", "-c", "user.email=compare@example.invalid",
               "commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "compare seed")
SEED_DATES = {"GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000"}
# every harness diff (here and in shim/claude): a plain git patch whatever the repository's config says
DIFF_FLAGS = ("--binary", "--no-ext-diff", "--no-color", "--no-textconv", "--src-prefix=a/", "--dst-prefix=b/")
HIDDEN_DIR = 0o311  # traversable, not listable: only for directories no orchestrator run lives under


def git(repo, *args, env=None, raw=False, stdin=None):
    """Run git in `repo`; return stdout (bytes when `raw`, else stripped text); fail with git's message."""
    done = subprocess.run(["git", "-C", str(repo), "-c", "core.hooksPath=/dev/null", *args],
                          input=stdin, capture_output=True, env={**os.environ, **(env or {})})
    if done.returncode:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout if raw else done.stdout.decode().strip()


def load(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main_checkout(runtime):
    return Path(git(runtime, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent


def guard(main, *paths):
    """Refuse paths under the main checkout's prefix, where sibling checkouts hold solutions (R21)."""
    for path in paths:
        if str(path).startswith(str(main)):
            raise SystemExit(f"{path} lies under the main checkout prefix {main}; use a directory elsewhere")


def build_candidate(source, base, seed, dest):
    """Check out `base` alone at `dest` (no remote, no other refs), commit `seed` onto it; return that commit."""
    dest.mkdir(parents=True)
    git(dest, "init", "-q")
    git(dest, "fetch", "-q", "--depth", "1", "--upload-pack",
        "git -c uploadpack.allowAnySHA1InWant=true upload-pack", str(source), base)
    git(dest, "checkout", "-q", "FETCH_HEAD")
    (dest / ".git" / "FETCH_HEAD").unlink()  # it names the source checkout
    if seed.is_dir():
        shutil.copytree(seed, dest, dirs_exist_ok=True)
    git(dest, "add", "-A", "-f", ".")
    git(dest, *SEED_COMMIT, env=SEED_DATES)
    return git(dest, "rev-parse", "HEAD")


def patch_of(repo, base):
    """The repository's changes against `base`, new files included, leaving new files intent-to-add."""
    git(repo, "add", "-A", "-N", ".")
    patch = git(repo, "diff", *DIFF_FLAGS, base, raw=True)
    git(repo, "reset", "-q")
    git(repo, "add", "-A", "-N", ".")
    return patch


def random_child(parent):
    """A fresh directory with an unguessable name under `parent`. The parent stays listable: the runtime
    opens every ancestor of a workspace or state directory component by component with O_RDONLY."""
    parent.mkdir(parents=True, exist_ok=True)
    child = parent / secrets.token_hex(8)
    child.mkdir()
    return child


def shim_commands(cwd, runtime, env, run_args, state=None):
    """(run command, resume script) run from `cwd` with the frozen runtime and the shims first on PATH.

    `env` is the shims' COMPARE_ROOT, COMPARE_TREE and COMPARE_BASE plus anything else; the shims strip
    them, PYTHONPATH and their own directory from the agent's environment. The resume script takes the
    run id as $1. With `state`, both pass --state-dir; without, the runtime keeps its state in
    <cwd>/.orchestrate/runs, inside the agent's workspace (R34)."""
    prefix = (f"cd {shlex.quote(str(cwd))} && env "
              + " ".join(f"{k}={shlex.quote(str(v))}" for k, v in {"PYTHONPATH": runtime, **env}.items())
              + f' PATH={shlex.quote(str(Path(runtime) / "experiments/compare/shim"))}:"$PATH" ')
    python = [sys.executable, "-P", "-m", "orchestrator"]  # -P: a candidate's orchestrator/ must not shadow it
    state_args = ["--state-dir", str(state)] if state else []
    return (prefix + shlex.join([*python, "run", *run_args, *state_args]),
            (prefix + shlex.join([*python, "resume"]) + ' "$1" ' + shlex.join(state_args)).rstrip())

