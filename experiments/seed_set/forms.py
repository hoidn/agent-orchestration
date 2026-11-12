"""Task-package forms derived from an in-tree package (plan, "Check-withheld form" and the ladder's T0).

`withhold(pkg, out)` writes the check-withheld form: `seed/` holds only `dev-check.json` (with
`"withheld": true` and `--tb=short`, so the excerpt shows the failing line, not the test's source), the
in-tree seed's test files move to `withheld/`, so the candidate's tree keeps the base versions of every
test file and contains no visible or hidden test function. `hidden/`, `hidden_tests.txt`, `intent.txt`,
`base_commit` and the anchors' contents are unchanged; anchors are renamed for the new package name.
`programs/dev_check.py` overlays `withheld/` during the check and restores the tree after it.

`hinted(pkg, out, failure)` writes the T0 variant of a T1 package: the same package with the visible
check's failing assertion (the `E` lines its base run prints) appended to the statement.

Depends on: `experiments.seed_set.programs.dev_check` and git (for `tree_digest`).
"""

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from experiments.seed_set.programs import dev_check

WITHHELD_TASK = ("A check (`dev-check.json`, run by `python dev_check.py`) runs a test that is kept out of the "
                 "repository; it fails now and should pass once the change is made. Leave `dev-check.json` and "
                 "the existing tests unchanged; you may add new tests.\n")
MAX_FAILURE_LINES = 12


def _rename_anchors(out, old):
    for anchor in sorted((out / "anchors").glob(f"{old}-*.diff")):
        anchor.rename(anchor.with_name(out.name + anchor.name[len(old):]))


def withhold(pkg, out):
    """Write the check-withheld form of in-tree package `pkg` to `out` (whose name is the new package id)."""
    shutil.copytree(pkg, out)
    shutil.rmtree(out / "seed")
    (out / "seed").mkdir()
    shutil.copytree(pkg / "seed", out / "withheld", ignore=shutil.ignore_patterns("dev-check.json"))
    config = json.loads((pkg / "seed/dev-check.json").read_text())
    argv = [*config["argv"][:-1], "--tb=short", config["argv"][-1]]
    (out / "seed/dev-check.json").write_text(
        json.dumps({"argv": argv, "timeout_sec": config["timeout_sec"], "withheld": True}, indent=2) + "\n")
    (out / "task.txt").write_text((pkg / "intent.txt").read_text() + "\n" + WITHHELD_TASK)
    _rename_anchors(out, pkg.name)


def failure_lines(output, clone):
    """The `E` lines of a pytest failure, with the clone's path removed, at most MAX_FAILURE_LINES."""
    lines = [line.replace(f"{clone}/", "").rstrip() for line in output.splitlines() if re.match(r"E( |$)", line)]
    return lines[:MAX_FAILURE_LINES]


def hinted(pkg, out, failure):
    """Write the T0 variant of in-tree package `pkg` to `out`: its statement plus the failing assertion."""
    shutil.copytree(pkg, out)
    hint = "\nThe check currently fails with:\n" + "".join(f"    {line}\n" for line in failure)
    intent = (pkg / "intent.txt").read_text() + hint
    (out / "intent.txt").write_text(intent)
    task = (pkg / "task.txt").read_text()
    (out / "task.txt").write_text(intent + task[len((pkg / "intent.txt").read_text()):])
    _rename_anchors(out, pkg.name)
    return intent


def tree_digest(tree):
    """What `git status`, `git diff HEAD` and every untracked or ignored file say about `tree`."""
    status = subprocess.run(["git", "-C", str(tree), "status", "--porcelain", "--ignored", "--untracked-files=all"],
                            capture_output=True, check=True).stdout
    diff = subprocess.run(["git", "-C", str(tree), "diff", "--binary", "HEAD"], capture_output=True, check=True).stdout
    extra = b"".join((tree / line[3:].decode()).read_bytes() for line in status.splitlines()
                     if line[:2] in (b"??", b"!!") and (tree / line[3:].decode()).is_file())
    return status, diff, extra


def withheld_visible(pkg, clone):
    """(passed, seconds, reject reason or None): the check-withheld visible check, which must leave the
    clone exactly as it found it."""
    before, started = tree_digest(clone), time.monotonic()
    result = dev_check.check(Path(clone), pkg / "withheld")
    seconds = round(time.monotonic() - started, 1)
    if tree_digest(clone) != before:
        return False, seconds, "the check-withheld run changed the tree", result["excerpt"]
    return result["passed"], seconds, None, result["excerpt"]
