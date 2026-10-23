"""Local verification and action command stand-ins for both examples."""

import json
import os
from pathlib import Path
import sys


operation, *arguments = sys.argv[1:]
with Path("commands.log").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"operation": operation, "arguments": arguments}, sort_keys=True) + "\n")

if operation == "verify":
    cause, summary, evidence = arguments
    if not Path(evidence).is_file():
        raise SystemExit(f"verification evidence is missing: {evidence}")
    result = {"cause": cause, "summary": f"verified:{summary}", "evidence": evidence}
elif operation == "repair":
    cause, summary = arguments
    result = {"status": "repaired", "reason": "", "cause": cause, "diagnosis": summary}
elif operation == "escalate":
    reason, cause, summary = arguments
    result = {"status": "escalated", "reason": reason, "cause": cause, "diagnosis": summary}
else:
    raise SystemExit(f"unknown action {operation!r}")

Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
    json.dumps(result), encoding="utf-8"
)
