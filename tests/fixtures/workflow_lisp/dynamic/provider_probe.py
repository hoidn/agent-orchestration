#!/usr/bin/env python3
import json
import os
from pathlib import Path
import re
import sys


prompt = sys.stdin.read()
mode = os.environ.get("DYNAMIC_PROVIDER_MODE", "valid")
result = {"variant": "APPROVE", "ok": True, "score": 7}
if mode == "wrong-bool":
    result["ok"] = "true"
elif mode == "inactive-field":
    result["reason"] = "inactive"
elif mode == "int64-overflow":
    result["score"] = 2**63

report_match = re.search(r"report: (reports/[^\s]+)", prompt)
if report_match and mode != "missing-report":
    report = Path(report_match.group(1))
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("provider report", encoding="utf-8")

event = {
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
    "prompt": prompt,
    "result_path": os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH"),
}
with Path("provider_events.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(event, sort_keys=True) + "\n")

if mode in {"missing-bundle", "stdout-bundle"}:
    print(json.dumps(result), flush=True)
else:
    Path(event["result_path"]).write_text(json.dumps(result), encoding="utf-8")
print("private-provider-stdout", flush=True)
print("private-provider-stderr", file=sys.stderr, flush=True)
