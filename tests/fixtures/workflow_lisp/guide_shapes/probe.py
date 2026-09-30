"""Stand-in command for the programs of the drafting guide's section on program shapes.

`python probe.py <command> <n>` appends `<command> <n>` to `.orchestrate/guide-probe.log`
under the working directory and writes the command's result to the file named by
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
"""

import json
import os
import sys
from pathlib import Path

command, argument = sys.argv[1], sys.argv[2]
# A certified adapter passes its inputs as one JSON object.
n = json.loads(argument)["n"] if command == "fetch-fields" else int(argument)
log = Path(".orchestrate") / "guide-probe.log"
log.parent.mkdir(parents=True, exist_ok=True)
with log.open("a", encoding="utf-8") as handle:
    handle.write(f"{command} {n}\n")
result = {"fetch": {"n": n}, "fetch-fields": {"n": n}, "bump": {"n": n + 1}}[command]
bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
bundle.parent.mkdir(parents=True, exist_ok=True)
bundle.write_text(json.dumps(result), encoding="utf-8")
