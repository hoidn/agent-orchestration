"""reset-clone command boundary: restore the working clone to the harness's seeded commit, write `true`.

Runs in the clone (the working directory). Finds the commit the comparison harness made on top of the task's
base (message "compare seed", `experiments/compare/repos.py::SEED_COMMIT`), hard-resets to it and removes
untracked files. Ignored files survive (`git clean` without `-x`): the run state under `.orchestrate/` and the
boundary scripts the runner copies in and lists in `.git/info/exclude`. A clone without that commit fails.
"""

import json
import os
from pathlib import Path
import subprocess


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    seed = git("log", "-1", "--format=%H", "--grep=^compare seed$", "HEAD")
    if not seed:
        raise SystemExit("reset_clone: no 'compare seed' commit in this clone's history")
    git("reset", "-q", "--hard", seed)
    git("clean", "-q", "-fd")
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(True))
