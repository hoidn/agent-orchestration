"""Tabulate oracle-check trials: reward and phase durations per task and agent.

Reads <jobs>/<agent>/<task>/<job>/<trial>/result.json as written by Harbor 0.25.0.
Usage: python -I summarize.py $LH/jobs   (the cache directory, by default ~/lh-cache)
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def _seconds(phase):
    if not phase or not phase.get("finished_at"):
        return None
    start, end = (datetime.fromisoformat(phase[k]) for k in ("started_at", "finished_at"))
    return round((end - start).total_seconds())


def row(result):
    verifier = result.get("verifier_result") or {}
    exc = result.get("exception_info") or {}
    return {
        "reward": (verifier.get("rewards") or {}).get("reward"),
        "env_s": _seconds(result.get("environment_setup")),
        "agent_s": _seconds(result.get("agent_execution")),
        "verify_s": _seconds(result.get("verifier")),
        "error": exc.get("exception_type"),
    }


def main(jobs):
    for path in sorted(Path(jobs).glob("*/*/*/*/result.json")):
        agent, task = path.parts[-5], path.parts[-4]
        print(agent, task, json.dumps(row(json.loads(path.read_text()))))


if __name__ == "__main__":
    main(sys.argv[1])
