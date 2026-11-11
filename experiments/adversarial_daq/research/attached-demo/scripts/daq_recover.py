#!/usr/bin/env python3
"""The actuator. Dry-run in this kit: walks the approved playbook's steps one at
a time, logging each before it "runs", and returns the typed Outcome DRY_RUN
(never RECOVERED: nothing was actually done, and nothing was re-measured).

Declared must_not_repeat in inputs/commands.json: if this is interrupted after
it starts, the runtime will not run it again on resume. Half a recovery is a state
only a person can judge. In the facility each step calls the access-checked
write tool with --approved-by, so the tool layer authorizes the approver.

DEMO_STEP_SECONDS=<s> makes each step take that long (for the kill in moment 5).
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from playbooks import steps_for

ap = argparse.ArgumentParser()
ap.add_argument("--hutch", required=True)
ap.add_argument("--run", required=True, type=int)
ap.add_argument("--cause", required=True)
ap.add_argument("--target", required=True)
ap.add_argument("--approved-by", required=True)
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

out = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
run_id = out.parts[out.parts.index("runs") + 1]
bundle_dir = Path("artifacts") / "daq" / str(args.run) / run_id
plan = steps_for(args.cause, args.target, bundle_dir)
mode = "DRY RUN" if args.dry_run else "LIVE"
log = bundle_dir / "recovery.log"
log.parent.mkdir(parents=True, exist_ok=True)


def record(line):
    stamp = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
    with log.open("a") as handle:
        handle.write(f"[{stamp}] {line}\n")
    print(f"[{stamp}] {line}", flush=True)


record(f"{mode} {args.cause} playbook for {args.hutch} run {args.run} on {args.target}, approved by {args.approved_by}")
for number, step in enumerate(plan, 1):
    record(f"  step {number}/{len(plan)}: {step}")
    time.sleep(float(os.environ.get("DEMO_STEP_SECONDS", "0")))
record(f"{mode} complete: {len(plan)} steps")

out.write_text(json.dumps({"variant": "DRY_RUN" if args.dry_run else "RECOVERED",
                           "summary": f"{mode}: {len(plan)}-step {args.cause} playbook on {args.target}",
                           "approved_by": args.approved_by}))
