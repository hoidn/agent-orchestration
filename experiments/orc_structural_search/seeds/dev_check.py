"""dev-check command boundary: run the task's agent-visible checks, write a CheckReport.

Reads ``dev-check.json`` (``{"argv": [...], "timeout_sec": N}``) from the
working directory, runs ``argv`` there with that timeout, and writes
``{"passed": bool, "failing": [str], "excerpt": str}`` (excerpt: last 4,000
characters of combined output) to ``$ORCHESTRATOR_OUTPUT_BUNDLE_PATH``.
A missing ``dev-check.json`` fails closed.
"""

import json
import os
from pathlib import Path
import subprocess

EXCERPT_CHARS = 4000


def check() -> dict:
    # ponytail: runs checks in the working clone; fresh-checkout application deferred
    config_path = Path("dev-check.json")
    if not config_path.exists():
        return {"passed": False, "failing": ["dev-check.json missing"], "excerpt": ""}
    config = json.loads(config_path.read_text())
    argv, timeout = config["argv"], config["timeout_sec"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        output = output.decode(errors="replace") if isinstance(output, bytes) else output
        return {"passed": False, "failing": [f"timeout after {timeout}s"], "excerpt": output[-EXCERPT_CHARS:]}
    output = proc.stdout + proc.stderr
    failing = [] if proc.returncode == 0 else [f"{' '.join(argv)} exited {proc.returncode}"]
    return {"passed": proc.returncode == 0, "failing": failing, "excerpt": output[-EXCERPT_CHARS:]}


if __name__ == "__main__":
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(check()))
