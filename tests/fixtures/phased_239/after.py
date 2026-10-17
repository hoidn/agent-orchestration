"""Deterministic typed continuation for the public phased fixture."""
import json
import os
from pathlib import Path
import sys

assert sys.argv[1] in {"true", "false"}
with Path("continuations.jsonl").open("a") as stream:
    stream.write(json.dumps({"approved": sys.argv[1] == "true"}) + "\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
    "9" if sys.argv[1] == "true" else "8")
