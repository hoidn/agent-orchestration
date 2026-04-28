#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


UNRESOLVED_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bremains?\s+(?:real\s+work|deferred|blocked|unimplemented|unsolved|undelivered)\b",
        r"\bstill\s+(?:deferred|blocked|unimplemented|unsolved|undelivered|not\s+implemented)\b",
        r"\bdeferred\s+(?:to|until|pending)\b",
        r"\bblocked\s+until\b",
        r"\bnot\s+(?:implemented|delivered|complete|completed|closed)\b",
        r"\bnot\s+claimed\s+complete\b",
    ]
]
NEGATED_BLOCKER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bno\s+(?:blocking\s+)?(?:blockers|findings|issues|defects)\b",
        r"\bno\s+high-severity\s+findings\b",
    ]
]


def write_scope_boundary(
    *,
    root: Path,
    tranche_manifest_path: str,
    tranche_brief_path: str,
    scope_boundary_path: str,
    selected_tranche_id: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = _require_existing_file(root, tranche_manifest_path, "tranche_manifest_path")
    brief_path = _require_existing_file(root, tranche_brief_path, "tranche_brief_path")
    output_path = _require_relpath(root, scope_boundary_path, "scope_boundary_path")

    manifest = _read_json_object(manifest_path, "tranche_manifest_path")
    tranches = manifest.get("tranches")
    if not isinstance(tranches, list):
        raise ValueError("Manifest tranches must be an array")

    tranche = _find_tranche(tranches, selected_tranche_id=selected_tranche_id, tranche_brief_path=tranche_brief_path)
    tranche_id = _require_string(tranche.get("tranche_id"), "tranche_id")
    title = _optional_string(tranche.get("title")) or tranche_id
    brief_text = brief_path.read_text(encoding="utf-8")

    payload = {
        "schema_version": 1,
        "authority": "roadmap_revision",
        "tranche_id": tranche_id,
        "objective": _optional_string(tranche.get("objective")) or title,
        "brief_path": tranche_brief_path,
        "project_roadmap_path": manifest.get("project_roadmap_path"),
        "tranche_manifest_path": tranche_manifest_path,
        "required_deliverables": _string_list_or_default(
            tranche.get("required_deliverables"),
            [title],
        ),
        "required_evidence": _string_list_or_default(
            tranche.get("required_evidence"),
            [_optional_string(tranche.get("completion_gate")) or "implementation_approved"],
        ),
        "authorized_non_goals": _string_list_or_default(tranche.get("authorized_non_goals"), []),
        "authorized_deferred_work": _object_list(tranche.get("authorized_deferred_work")),
        "completion_gate": _optional_string(tranche.get("completion_gate")) or "implementation_approved",
        "source_fields": {
            key: tranche[key]
            for key in sorted(tranche)
            if key
            in {
                "tranche_id",
                "title",
                "objective",
                "status",
                "completion_gate",
                "prerequisites",
                "brief_path",
            }
        },
        "brief_excerpt": brief_text[:4000],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def check_completion(
    *,
    root: Path,
    scope_boundary_path: str,
    implementation_decision: str,
    execution_report_path: str,
    implementation_review_report_path: str,
    implementation_escalation_context_path: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    boundary_path = _require_existing_file(root, scope_boundary_path, "scope_boundary_path")
    execution_path = _require_existing_file(root, execution_report_path, "execution_report_path")
    review_path = _require_existing_file(root, implementation_review_report_path, "implementation_review_report_path")
    boundary = _read_json_object(boundary_path, "scope_boundary_path")

    if implementation_decision != "APPROVE":
        return _guard_result(
            "INVALID",
            scope_boundary_path,
            [f"Implementation decision is {implementation_decision}, not APPROVE."],
            "block",
        )

    evidence_texts = [
        ("execution_report", execution_path.read_text(encoding="utf-8", errors="replace")),
        ("implementation_review_report", review_path.read_text(encoding="utf-8", errors="replace")),
    ]
    if implementation_escalation_context_path:
        context_path = _require_existing_file(
            root,
            implementation_escalation_context_path,
            "implementation_escalation_context_path",
        )
        evidence_texts.append(("implementation_escalation_context", context_path.read_text(encoding="utf-8", errors="replace")))

    authorized_deferred = _object_list(boundary.get("authorized_deferred_work"))
    if not authorized_deferred:
        blockers = _find_unresolved_scope_lines(evidence_texts)
        if blockers:
            return _guard_result(
                "SCOPE_MISMATCH",
                scope_boundary_path,
                blockers,
                "escalate_roadmap_revision",
            )

    missing_evidence = _missing_required_evidence(root, boundary)
    if missing_evidence:
        return _guard_result(
            "MISSING_EVIDENCE",
            scope_boundary_path,
            missing_evidence,
            "revise_implementation",
        )

    return _guard_result("COMPLETE", scope_boundary_path, [], "complete")


def _find_tranche(
    tranches: list[Any],
    *,
    selected_tranche_id: str | None,
    tranche_brief_path: str,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for tranche in tranches:
        if not isinstance(tranche, dict):
            raise ValueError("Every tranche must be a JSON object")
        if selected_tranche_id is not None:
            if tranche.get("tranche_id") == selected_tranche_id:
                return tranche
            continue
        if tranche.get("brief_path") == tranche_brief_path:
            matches.append(tranche)
    if selected_tranche_id is not None:
        raise ValueError(f"Selected tranche not found in manifest: {selected_tranche_id}")
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one tranche with brief_path {tranche_brief_path}, found {len(matches)}")
    return matches[0]


def _find_unresolved_scope_lines(evidence_texts: list[tuple[str, str]]) -> list[str]:
    blockers: list[str] = []
    for label, text in evidence_texts:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(pattern.search(line) for pattern in NEGATED_BLOCKER_PATTERNS):
                continue
            if any(pattern.search(line) for pattern in UNRESOLVED_PATTERNS):
                blockers.append(f"{label}: {line[:500]}")
    return blockers


def _missing_required_evidence(root: Path, boundary: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for entry in boundary.get("required_evidence_paths", []):
        if not isinstance(entry, str) or not entry:
            continue
        try:
            _require_existing_file(root, entry, "required_evidence_paths")
        except ValueError:
            missing.append(f"Missing required evidence path: {entry}")
    return missing


def _guard_result(
    completion_status: str,
    scope_boundary_path: str,
    blocking_reasons: list[str],
    recommended_route: str,
) -> dict[str, Any]:
    return {
        "completion_status": completion_status,
        "scope_boundary_path": scope_boundary_path,
        "blocking_reasons": blocking_reasons,
        "recommended_route": recommended_route,
    }


def _read_json_object(path: Path, field: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return data


def _require_existing_file(root: Path, value: str, field: str) -> Path:
    resolved = _require_relpath(root, value, field)
    if not resolved.is_file():
        raise ValueError(f"{field} target does not exist: {value}")
    return resolved


def _require_relpath(root: Path, value: str, field: str) -> Path:
    rel = _require_string(value, field)
    resolved = (root / rel).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{field} escapes workspace: {rel}")
    return resolved


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list_or_default(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return list(value)
    raise ValueError("Expected a list of non-empty strings")


def _object_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Expected a list")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Expected a list of objects")
        result.append(item)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage major-project roadmap-authoritative scope boundaries.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write-boundary")
    write_parser.add_argument("--tranche-manifest-path", required=True)
    write_parser.add_argument("--tranche-brief-path", required=True)
    write_parser.add_argument("--scope-boundary-path", required=True)
    write_parser.add_argument("--selected-tranche-id")
    write_parser.add_argument("--output-bundle", type=Path)

    check_parser = subparsers.add_parser("check-completion")
    check_parser.add_argument("--scope-boundary-path", required=True)
    check_parser.add_argument("--implementation-decision", required=True)
    check_parser.add_argument("--execution-report-path", required=True)
    check_parser.add_argument("--implementation-review-report-path", required=True)
    check_parser.add_argument("--implementation-escalation-context-path")
    check_parser.add_argument("--output-bundle", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "write-boundary":
        payload = write_scope_boundary(
            root=args.root,
            tranche_manifest_path=args.tranche_manifest_path,
            tranche_brief_path=args.tranche_brief_path,
            scope_boundary_path=args.scope_boundary_path,
            selected_tranche_id=args.selected_tranche_id,
        )
        if args.output_bundle:
            args.output_bundle.parent.mkdir(parents=True, exist_ok=True)
            args.output_bundle.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    elif args.command == "check-completion":
        payload = check_completion(
            root=args.root,
            scope_boundary_path=args.scope_boundary_path,
            implementation_decision=args.implementation_decision,
            execution_report_path=args.execution_report_path,
            implementation_review_report_path=args.implementation_review_report_path,
            implementation_escalation_context_path=args.implementation_escalation_context_path,
        )
        args.output_bundle.parent.mkdir(parents=True, exist_ok=True)
        args.output_bundle.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    else:
        raise AssertionError(args.command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
