import json
import os
import sys
from pathlib import Path


value = int(sys.argv[1])
print(f"work item {value}")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
    json.dumps(value + 1), encoding="utf-8"
)
