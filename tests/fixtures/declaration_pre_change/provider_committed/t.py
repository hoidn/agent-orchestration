#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(int(sys.argv[2]) + 1))
