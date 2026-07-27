#!/usr/bin/env python3
"""Deterministic Codex-exec stand-in for lean-pilot review tests."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import sys
import time
from pathlib import Path


DIMENSIONS = (
    "TASK_COMPLETENESS",
    "BEHAVIORAL_CORRECTNESS",
    "MAINTAINABILITY",
    "SCOPE_CONTROL",
    "EVIDENCE_QUALITY",
)


def _option(name: str) -> str:
    return sys.argv[sys.argv.index(name) + 1]


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def main() -> int:
    prompt = json.loads(sys.stdin.read())
    mode = os.environ.get("FAKE_REVIEW_MODE", "valid")
    if (
        expected := os.environ.get("FAKE_EXPECT_SCHEMA_SHA256")
    ) is not None and _sha256(Path(_option("--output-schema"))) != expected:
        return 90
    rubric_path = Path(prompt["inspection_contract"]["rubric_path"])
    if (
        expected := os.environ.get("FAKE_EXPECT_RUBRIC_SHA256")
    ) is not None and _sha256(rubric_path) != expected:
        return 91
    reviewer_id = prompt["review_context"]["reviewer_id"]
    session_id = os.environ.get(
        "FAKE_REVIEW_SESSION_ID",
        f"session-{prompt['review_context']['package_id']}-{reviewer_id}",
    )
    labels = prompt["output_contract"]["candidate_labels"]
    citation = f"{prompt['inspection_contract']['task_path']}:1"
    payload = {
        "candidates": [
            {
                "opaque_label": label,
                "evidence_citations": [citation],
                "dimension_assessments": [
                    {
                        "dimension": dimension,
                        "assessment": "PASS",
                        "rationale": "The declared package evidence supports this assessment.",
                        "evidence_citations": [citation],
                    }
                    for dimension in DIMENSIONS
                ],
                "sealed_treatment_guess": "UNKNOWN",
            }
            for label in labels
        ],
        "pairwise_results": [
            {
                "candidate_a_label": left,
                "candidate_b_label": right,
                "outcome": "INDETERMINATE",
                "rationale": "The declared package evidence does not establish a winner.",
                "evidence_citations": [citation],
            }
            for left, right in itertools.combinations(labels, 2)
        ],
    }
    if mode == "duplicate-first-dimension":
        for candidate in payload["candidates"]:
            candidate["dimension_assessments"][-1]["dimension"] = DIMENSIONS[0]
    elif mode == "duplicate-last-dimension":
        for candidate in payload["candidates"]:
            candidate["dimension_assessments"][0]["dimension"] = DIMENSIONS[-1]
    print(json.dumps({"type": "thread.started", "thread_id": session_id}))
    if mode == "ambiguous":
        print(json.dumps({"type": "thread.started", "thread_id": "other-session"}))
    if mode == "hang":
        time.sleep(0.2)
    if mode == "partial":
        return 0
    if mode == "nonzero":
        print(json.dumps({"type": "turn.failed", "session_id": session_id}))
        return 9
    Path(_option("--output-last-message")).write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    print(json.dumps({"type": "turn.completed", "session_id": session_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
