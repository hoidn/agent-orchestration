"""Local provider stand-in whose answer is a deterministic function of effect identity."""

import json
import os
from pathlib import Path
import re
import sys


sys.stdin.buffer.read()
result_path = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
match = re.search(r"(?:^|/)effects/([0-9a-f]{64})/attempt-[1-9][0-9]*/result\.json$",
                  result_path.as_posix())
if match is None:
    raise SystemExit("provider result path has no evaluated effect identity")
identity = match.group(1)
cause = "BROKEN_RECORD" if int(identity[-1], 16) % 2 else "MISSING_METADATA"
summary = f"diagnosis-for:{identity}"
with Path("providers.log").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"identity": identity, "cause": cause, "summary": summary}, sort_keys=True) + "\n")
result_path.write_text(json.dumps({"cause": cause, "summary": summary}), encoding="utf-8")
