import json
import os
from pathlib import Path
import sys


action, *arguments = sys.argv[1:]
row = {"action": action, "args": arguments}
if action == "first":
    result = 11
elif action == "second":
    result = 12
elif action == "finish":
    result = {
        "literal": arguments[0],
        "computed": arguments[1],
        "opaque": arguments[2],
        "first": int(arguments[3]),
        "second": int(arguments[4]),
    }
elif action == "document":
    row["document"] = json.loads(Path(arguments[-1]).read_text(encoding="utf-8"))
    result = row["document"].get("count", 0)
elif action == "adapter":
    row["document"] = json.loads(arguments[0])
    result = row["document"]
elif action == "leak":
    with Path("command_events.jsonl").open("a", encoding="utf-8") as events:
        events.write(json.dumps(row, sort_keys=True) + "\n")
    print("private-stdout-value", flush=True)
    print("private-stderr-value", file=sys.stderr, flush=True)
    raise SystemExit(7)
elif action == "wrong-root":
    result = "private-result-value"
elif action == "wrong-record":
    result = {"count": "private-result-value"}
elif action == "replace":
    output = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
    attempt = output.parent
    moved = attempt.with_name("moved-attempt")
    attempt.rename(moved)
    attempt.mkdir()
    result = 99
elif action == "mutate":
    Path("mutable.txt").write_text("changed", encoding="utf-8")
    result = 42
else:
    raise SystemExit(f"unexpected action: {action}")

row["executable"] = sys.executable
with Path("command_events.jsonl").open("a", encoding="utf-8") as events:
    events.write(json.dumps(row, sort_keys=True) + "\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(result), encoding="utf-8")
