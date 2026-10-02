"""Deterministic subprocess leaf used by the DC-1b boundary experiment."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def _record_dispatch(mode: str, bundle: Path, payload: dict | None = None) -> None:
    log = os.environ.get("DYNAMIC_CORE_DISPATCH_LOG")
    if log:
        with Path(log).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"mode": mode, "bundle": str(bundle), "payload": payload}) + "\n")


def _prompt_values(prompt: str) -> dict[str, object]:
    for line in prompt.splitlines():
        try:
            values = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(values, list) and len(values) == 2:
            return {"goal": values[0], "rubric": values[1]}
    return {}


def _report_path(prompt: str) -> str | None:
    for line in prompt.splitlines():
        if line.startswith("OUT:"):
            return line.removeprefix("OUT:").strip()
    return None


def _provider_payload(prompt: str) -> dict[str, object]:
    values = _prompt_values(prompt)
    goal = str(values.get("goal", ""))
    rubric = str(values.get("rubric", ""))
    if goal == "bad-bool":
        return {"approved": "true", "feedback": "bad", "score": 1, "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1}}
    if goal == "bad-int":
        return {"approved": True, "feedback": "bad", "score": "1", "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1}}
    if goal == "missing-field":
        return {"approved": True, "feedback": "missing", "score": 1, "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED"}}
    if goal == "extra-field":
        return {"approved": True, "feedback": "extra", "score": 1, "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1}, "unexpected": "hidden"}
    if goal == "bad-nested":
        return {"approved": True, "feedback": "nested", "score": 1, "evidence": {"count": "1"}, "decision": {"variant": "ACCEPTED", "confidence": 1}}
    if goal == "inactive-field":
        return {"approved": True, "feedback": "inactive", "score": 1, "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1, "reason": "inactive"}}
    if goal == "non-finite":
        return {"approved": True, "feedback": "nonfinite", "score": 1, "evidence": {"count": float("inf")}, "decision": {"variant": "ACCEPTED", "confidence": 1}}
    if goal == "missing":
        return {"approved": True, "score": 1, "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1}}
    if goal == "stdout-only":
        return {"approved": True, "feedback": "stdout", "score": 1, "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1}}
    if goal == "no-file":
        return {"approved": True, "feedback": "no-file", "score": 1, "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1}}
    if goal == "wrong-path":
        return {"approved": True, "feedback": "wrong-path", "score": 1, "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1}}
    doc = next((marker for marker in ("DOC_A", "DOC_B") if marker in prompt), "DOC_MISSING")
    feedback = f"{goal}|{rubric}|{doc}"
    return {
        "approved": "reject" not in goal,
        "feedback": feedback,
        "score": len(goal),
        "evidence": {"count": len(rubric)},
        "decision": {"variant": "REJECTED", "reason": "rejected"} if "reject" in goal else {"variant": "ACCEPTED", "confidence": 1},
    }


def main() -> int:
    if len(sys.argv) < 2:
        return 64
    mode = sys.argv[1]
    raw_prompt = sys.stdin.read() if mode == "provider" else ""
    mutate_path = os.environ.get("DYNAMIC_CORE_MUTATE_DOC_PATH") if mode == "provider" else None
    if mutate_path:
        Path(mutate_path).write_text(
            os.environ.get("DYNAMIC_CORE_MUTATE_DOC_CONTENT", "DOC_B: changed after prompt composition\n"),
            encoding="utf-8",
        )
    if mode == "provider":
        payload = _provider_payload(raw_prompt)
        goal = _prompt_values(raw_prompt).get("goal")
        report_path = _report_path(raw_prompt)
        if report_path and goal == "out-valid":
            report = Path(report_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("review report\n", encoding="utf-8")
        elif report_path and goal == "out-invalid":
            report = Path(report_path)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_bytes(b"\xff\xfe")
    elif mode == "command":
        feedback = sys.argv[2] if len(sys.argv) > 2 else ""
        payload = {"approved": True, "feedback": feedback, "score": len(feedback), "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1}}
    else:
        return 64

    if "decision" in payload:
        payload["decisions"] = [payload.pop("decision")]

    output_value = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
    if not output_value:
        return 65
    output = Path(output_value)
    _record_dispatch(mode, output, payload)

    if mode == "provider" and payload.get("feedback") == "stdout":
        print(json.dumps(payload))
        return 0
    if mode == "provider" and payload.get("feedback") == "no-file":
        return 0
    if mode == "provider" and payload.get("feedback") == "missing":
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"approved": True, "score": 1, "evidence": {"count": 1}, "decision": {"variant": "ACCEPTED", "confidence": 1}}), encoding="utf-8")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    if mode == "provider" and payload.get("feedback") == "wrong-path":
        output.with_name("wrong-result.json").write_text(json.dumps(payload), encoding="utf-8")
        return 0
    if mode == "provider" and _prompt_values(raw_prompt).get("goal") == "duplicate-json":
        output.write_text('{"approved":true,"approved":false}', encoding="utf-8")
        return 0
    if mode == "provider" and _prompt_values(raw_prompt).get("goal") == "malformed-json":
        output.write_text('{bad json', encoding="utf-8")
        return 0
    if mode == "provider" and _prompt_values(raw_prompt).get("goal") == "non-finite-json":
        output.write_text('{"approved":true,"feedback":"x","score":NaN}', encoding="utf-8")
        return 0
    if mode == "provider" and _prompt_values(raw_prompt).get("goal") == "non-finite":
        output.write_text(json.dumps(payload), encoding="utf-8")
        return 0
    output.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")

    if mode == "provider":
        first_path_log = os.environ.get("DYNAMIC_CORE_FIRST_PATH_LOG")
        if first_path_log:
            with Path(first_path_log).open("a", encoding="utf-8") as stream:
                stream.write(str(output.resolve()) + "\n")
        return 0

    replacement_path_log = os.environ.get("DYNAMIC_CORE_REPLACE_PATH_LOG")
    if replacement_path_log and Path(replacement_path_log).exists():
        first_path = Path(replacement_path_log).read_text(encoding="utf-8").splitlines()[0]
        Path(first_path).write_text('{"replaced":true}', encoding="utf-8")
    if payload["feedback"].startswith("fail-after"):
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
