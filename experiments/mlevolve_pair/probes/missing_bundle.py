"""Emit a malformed result on request, or omit iteration one's result."""

import json
import os
from pathlib import Path
import sys


if __name__ == "__main__":
    ordinal = int(sys.argv[1])
    if ordinal == 0:
        value = "wrong_type" if sys.argv[2:] == ["malformed"] else ordinal
        output = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"ordinal": value}) + "\n", encoding="utf-8")
