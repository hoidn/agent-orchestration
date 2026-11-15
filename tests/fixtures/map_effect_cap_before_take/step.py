#!/usr/bin/env python3
import os, sys
from pathlib import Path
with open("dispatches.log", "a", encoding="utf-8") as log:
    log.write(sys.argv[1] + "\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(int(sys.argv[1]) * 10))
