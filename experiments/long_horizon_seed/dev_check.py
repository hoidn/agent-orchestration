"""dev-check command boundary of the long-horizon seeds: run the task's agent-visible check, write a CheckReport.

Reads ``dev-check.json`` (``{"argv": [...], "timeout_sec": N}``) from the working directory, runs ``argv`` there with
that timeout, and writes ``{"passed": bool, "failing": [str], "excerpt": str}`` to ``$ORCHESTRATOR_OUTPUT_BUNDLE_PATH``.
A missing ``dev-check.json`` fails closed.

This is the seed catalog's script (``experiments/orc_structural_search/seeds/dev_check.py``) with one difference: a
failed check's excerpt begins with the reason (the command and its exit status, its timeout, or the missing file),
then the end of the command's output, 4,000 characters in all. The seeds pass the excerpt to the next round, so the
reason has to be in it. The catalog's file is not changed: that kit's candidate ids and recorded runs pin its bytes.
"""

import json
import os
from pathlib import Path
import subprocess

EXCERPT_CHARS = 4000


def failed(reason: str, output: str = "") -> dict:
    head = (reason + "\n")[:EXCERPT_CHARS]
    keep = EXCERPT_CHARS - len(head)
    return {"passed": False, "failing": [reason], "excerpt": head + (output[-keep:] if keep else "")}


def check() -> dict:
    config_path = Path("dev-check.json")
    if not config_path.exists():
        return failed("dev-check.json missing")
    config = json.loads(config_path.read_text())
    argv, timeout = config["argv"], config["timeout_sec"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        output = "".join(
            stream.decode(errors="replace") if isinstance(stream, bytes) else (stream or "")
            for stream in (exc.stdout, exc.stderr))
        return failed(f"{' '.join(argv)} timed out after {timeout}s", output)
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        return failed(f"{' '.join(argv)} exited {proc.returncode}", output)
    return {"passed": True, "failing": [], "excerpt": output[-EXCERPT_CHARS:]}


if __name__ == "__main__":
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(check()))
