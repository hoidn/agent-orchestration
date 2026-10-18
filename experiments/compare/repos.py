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


def runtime_commit(runtime):
    """The frozen runtime's HEAD; refuse a checkout with uncommitted changes to tracked files, which no
    commit would name. --no-optional-locks: the check never writes the runtime's index."""
    dirty = git(runtime, "--no-optional-locks", "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise SystemExit(f"the runtime {runtime} has uncommitted changes to tracked files; "
                         f"commit or discard them:\n{dirty}")
    return git(runtime, "rev-parse", "HEAD")


def guard(main, *paths):
    """Refuse paths under the main checkout's prefix, where sibling checkouts hold solutions (R21)."""
    for path in paths:
        if str(path).startswith(str(main)):
            raise SystemExit(f"{path} lies under the main checkout prefix {main}; use a directory elsewhere")


def visible_in_sandbox(*paths):
    """Refuse agents' or judges' directories under /tmp, /dev/shm or /var/tmp: the shims' sandbox mounts
    private or empty ones over them (R35), so the agent would not find its working directory."""
    for path in paths:
        if any(str(path) == root or str(path).startswith(root + "/") for root in ("/tmp", "/dev/shm", "/var/tmp")):
            raise SystemExit(f"{path} lies under /tmp, /dev/shm or /var/tmp, which the shims' sandbox replaces; "
                             "use a directory elsewhere")


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


def shim_prefix(cwd, runtime, env):
    """`cd <cwd> && env ...`: the frozen runtime on PYTHONPATH, `env` (the shims' COMPARE_ROOT, COMPARE_TREE
    and COMPARE_BASE plus anything else) and the shims first on PATH; the command follows it."""
    return (f"cd {shlex.quote(str(cwd))} && env "
            + " ".join(f"{k}={shlex.quote(str(v))}" for k, v in {"PYTHONPATH": runtime, **env}.items())
            + f' PATH={shlex.quote(str(Path(runtime) / "experiments/compare/shim"))}:"$PATH" ')


def shim_commands(cwd, runtime, env, run_args, state_dir=None, command_boundaries=None):
    """(run command, resume script) run from `cwd` with the frozen runtime and the shims first on PATH.

    The shims strip `env`, PYTHONPATH and their own directory from the agent's environment. The resume
    script takes the run id as $1. With `state_dir`, both pass --state-dir; without, the runtime keeps its
    state in <cwd>/.orchestrate/runs, inside the agent's workspace (R34). With `command_boundaries`, the run
    passes --command-boundaries-file (`orchestrator resume` takes only --state-dir)."""
    prefix = shim_prefix(cwd, runtime, env)
    python = [sys.executable, "-P", "-m", "orchestrator"]  # -P: a candidate's orchestrator/ must not shadow it
    state_args = ["--state-dir", str(state_dir)] if state_dir else []
    boundary_args = ["--command-boundaries-file", str(command_boundaries)] if command_boundaries else []
    return (prefix + shlex.join([*python, "run", *run_args, *state_args, *boundary_args]),
            (prefix + shlex.join([*python, "resume"]) + ' "$1" ' + shlex.join(state_args)).rstrip())
