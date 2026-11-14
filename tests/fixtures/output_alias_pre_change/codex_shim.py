import os, sys
from pathlib import Path
sys.stdin.buffer.read()
log = Path("calls.log")
calls = (len(log.read_text().splitlines()) if log.exists() else 0) + 1
with log.open("a") as stream:
    stream.write("launched\n")
if os.environ.get("SHIM_FAIL_CALL") == str(calls):
    sys.exit(9)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"ok": true}')
