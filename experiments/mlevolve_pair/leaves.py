"""Stateless candidate fixture and score; also the command-bundle entrypoint."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path


def evaluate(a: int, b: int) -> dict[str, object]:
    if type(a) is not int or type(b) is not int:
        raise ValueError("candidate coefficients must be integers")
    if any(not -5 <= value <= 5 for value in (a, b)):
        return {"valid": False, "score": 0.0, "error": "coefficient_out_of_domain"}
    score = sum(
        (2 * x + 3 * x * x - a * x - b * x * x) ** 2
        for x in (-2, -1, 1, 2)
    )
    return {"valid": True, "score": float(score), "error": ""}


def validate_evaluation(result: object) -> dict[str, object]:
    if not isinstance(result, dict) or set(result) != {"valid", "score", "error"}:
        raise ValueError("evaluation must contain valid, score, and error")
    if type(result["valid"]) is not bool or type(result["score"]) is not float:
        raise ValueError("evaluation valid and score must be Bool and Float")
    if not math.isfinite(result["score"]) or not isinstance(result["error"], str):
        raise ValueError("evaluation score must be finite and error must be String")
    return result


def validate_candidate(result: object) -> dict[str, int]:
    if not isinstance(result, dict) or set(result) != {"a", "b"} or any(
        type(result[key]) is not int for key in ("a", "b")
    ):
        raise ValueError("candidate result must contain integer a and b")
    return result


def propose(
    operation: str,
    branch: str,
    candidate_a: int,
    candidate_b: int,
    other_a: int,
    other_b: int,
    history_size: int,
) -> dict[str, int]:
    """Return only the requested proposal; the caller owns all routing."""
    if any(type(value) is not int for value in (
        candidate_a, candidate_b, other_a, other_b, history_size,
    )):
        raise ValueError("proposal coefficients and history size must be integers")
    if operation == "fuse" and branch == "both":
        return {"a": candidate_a, "b": other_b}
    if operation == "repair" and branch == "A":
        return {"a": 2, "b": candidate_b}
    if operation == "improve" and branch == "A":
        return {"a": 99, "b": candidate_b} if history_size == 2 else {
            "a": 2, "b": candidate_b,
        }
    if operation == "improve" and branch == "B":
        return {"a": candidate_a, "b": 3}
    raise ValueError(f"unsupported proposal request: {operation}/{branch}")


def main() -> int:
    operation, raw = sys.argv[1:3]
    request = json.loads(raw)
    result = (
        evaluate(**request)
        if operation == "evaluate"
        else propose(**request)
    )
    bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
    if not bundle.is_absolute():
        bundle = Path.cwd() / bundle
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
