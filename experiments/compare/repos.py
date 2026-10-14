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
import shutil
import subprocess
from pathlib import Path

SEED_COMMIT = ("-c", "user.name=compare", "-c", "user.email=compare@example.invalid",
               "commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "compare seed")
SEED_DATES = {"GIT_AUTHOR_DATE": "2000-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+0000"}
HIDDEN_DIR = 0o311  # traversable, not listable


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
    patch = git(repo, "diff", "--binary", "--no-ext-diff", "--no-color", "--no-textconv", base, raw=True)
    git(repo, "reset", "-q")
    git(repo, "add", "-A", "-N", ".")
    return patch


def hidden_child(parent):
    """A fresh directory with a random name under `parent`, which agents may traverse but not list."""
    parent.mkdir(parents=True, exist_ok=True)
    parent.chmod(HIDDEN_DIR)
    child = parent / secrets.token_hex(8)
    child.mkdir()
    return child
