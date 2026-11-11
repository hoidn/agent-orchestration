#!/usr/bin/env python3
"""Deterministic checks before anyone is asked to approve.

This does not verify the diagnosis; no script can. It checks the two things a
script can check:
  1. the evidence is real: every line the evidence file quotes ("> ...") is
     copied from one line of the fetched bundle (scripts/evidence.py);
  2. the playbook applies: the proposed cause's recovery (scripts/playbooks.py)
     has its preconditions met on the proposed target, read from the bundle's
     own data (the XPM link table, the readout group's dead fraction, the
     hsdpva summary, /proc/datadev_0), and the target is a member of the partition.
Whether the diagnosis is right is the approver's call, made with this result,
the evidence and the steps in front of them: on APPLICABLE this writes them
out as request.md beside the bundle, which the approval request shows. Returns
the typed PlaybookCheck: APPLICABLE{cause, target, steps, request, detail} |
BLOCKED{detail}.
"""
import argparse
import json
import os
from pathlib import Path

from evidence import not_in_bundle, quotes
from playbooks import check, steps_for

ap = argparse.ArgumentParser()
ap.add_argument("--cause", required=True)
ap.add_argument("--target", required=True)
ap.add_argument("--evidence", required=True)
ap.add_argument("--bundle", required=True)
args = ap.parse_args()

bundle_dir = Path(args.bundle).parent
quoted = quotes(Path(args.evidence).read_text())


def result(variant, **fields):
    Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"variant": variant, **fields}))
    print(f"check_playbook: {variant} {fields.get('detail', '')}")
    raise SystemExit(0)


if not quoted:
    result("BLOCKED", detail="the evidence file quotes no lines from the bundle")
invented = not_in_bundle(quoted, Path(args.bundle).read_text())
if invented:
    result("BLOCKED", detail=f"the evidence cites {len(invented)} line(s) not in the bundle: {invented[0][:80]!r}")

applies, why, member = check(args.cause, args.target, bundle_dir)
if not applies:
    result("BLOCKED", detail=f"the {args.cause} playbook does not apply to {args.target}: {why}")
steps = steps_for(args.cause, member.alias, bundle_dir)
detail = f"{len(quoted)} quoted lines found in the bundle; {why}"
request = bundle_dir / "request.md"
request.write_text("\n".join(
    [f"# Run the {args.cause} playbook on {member}?", "", "## Steps", ""]
    + [f"{n}. {step}" for n, step in enumerate(steps, 1)]
    + ["", "## Checked by the facility, not the model", ""]
    + [f"- {part.strip()}" for part in detail.split(";")]
    + ["", f"The model's evidence: {args.evidence}", ""]))
result("APPLICABLE", cause=args.cause, target=member.alias, steps=steps, request=str(request), detail=detail)
