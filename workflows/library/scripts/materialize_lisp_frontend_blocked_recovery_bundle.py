#!/usr/bin/env python3
"""Materialize blocked recovery classifier stdout into the canonical bundle path."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


_PROSE_CLASSIFICATION_RE = re.compile(
    r"Classification:\s*`(?P<route>[A-Z_]+)`\s+with reason\s+`(?P<reason>[a-z_]+)`\.",
)
_MARKDOWN_JSON_LINK_RE = re.compile(r"\]\((?P<path>[^)]+\.json)\)")
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(?P<payload>\{.*?\})\s*```", re.DOTALL)


def _extract_payload_from_prose(text: str, source_path: Path) -> dict[str, Any] | None:
    for fence_match in _FENCED_JSON_RE.finditer(text):
        try:
            fenced_payload = json.loads(fence_match.group("payload"))
        except json.JSONDecodeError:
            continue
        if isinstance(fenced_payload, dict):
            return fenced_payload

    for link_match in _MARKDOWN_JSON_LINK_RE.finditer(text):
        linked_path = Path(link_match.group("path"))
        if not linked_path.is_absolute():
            linked_path = source_path.parent / linked_path
        if not linked_path.exists():
            continue
        try:
            linked_payload = json.loads(linked_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(linked_payload, dict):
            return linked_payload

    match = _PROSE_CLASSIFICATION_RE.search(text)
    if match is None:
        return None
    summary = match.group(0).strip()
    return {
        "blocked_recovery_route": match.group("route"),
        "reason": match.group("reason"),
        "summary": summary,
    }


def _has_structured_prerequisite_authority(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("recovery_dependency_edge"), dict):
        return True
    proposed = payload.get("proposed_prerequisite")
    if isinstance(proposed, dict) and str(proposed.get("id") or "").strip():
        return True
    return any(
        str(payload.get(key) or "").strip()
        for key in (
            "proposed_prerequisite_id",
            "waiting_on_work_id",
            "blocker_work_id",
        )
    )


def _validate_payload(payload: dict[str, Any]) -> None:
    route = str(payload.get("blocked_recovery_route") or "").strip()
    if route == "PREREQUISITE_GAP_REQUIRED" and not _has_structured_prerequisite_authority(payload):
        raise SystemExit(
            "PREREQUISITE_GAP_REQUIRED requires structured recovery_dependency_edge "
            "or structured prerequisite identity"
        )


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"Blocked recovery classifier output is missing: {path}") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        payload = _extract_payload_from_prose(raw_text, path)
        if payload is None:
            raise SystemExit(f"Blocked recovery classifier output is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Blocked recovery classifier output must be a JSON object")
    route = str(payload.get("blocked_recovery_route") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    summary = payload.get("summary")
    if (not isinstance(summary, str) or not summary.strip()) and route and reason:
        payload["summary"] = f"{route} selected: {reason}."
    _validate_payload(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-json-path", required=True)
    args = parser.parse_args()

    bundle_path_raw = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if not bundle_path_raw:
        raise SystemExit("ORCHESTRATOR_OUTPUT_BUNDLE_PATH is required for adapter invocation")

    source_path = Path(args.source_json_path)
    bundle_path = Path(bundle_path_raw)
    payload = _load_payload(source_path)

    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
