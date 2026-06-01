#!/usr/bin/env python3
"""Write one design-revision loop decision from revision and review outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision-report", required=True)
    parser.add_argument("--review-decision-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    revision = json.loads(Path(args.revision_report).read_text(encoding="utf-8"))
    revision_decision = revision.get("design_revision_decision")
    if revision_decision == "BLOCKED":
        decision = "BLOCKED"
    elif revision_decision == "REVISED":
        decision = Path(args.review_decision_path).read_text(encoding="utf-8").strip()
        if decision not in {"APPROVE", "REVISE"}:
            raise SystemExit(f"Unexpected design revision review decision: {decision}")
    else:
        raise SystemExit(f"Unexpected design revision decision: {revision_decision}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(decision + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
