#!/usr/bin/env python3
"""Deterministic provider used by lean-pilot treatment parity tests."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


_PHASES = {
    "discover",
    "plan",
    "review_plan",
    "revise_plan",
    "implement",
    "review_implementation",
    "fix_implementation",
}
_CONTRACT_FIELD = re.compile(
    r"^[ \t]*- name: (?P<name>[a-z][a-z0-9_]*)[ \t]*$",
    re.MULTILINE,
)


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _next_occurrence(state_path: Path, phase: str) -> int:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(f"{state_path.suffix}.lock")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {}
        occurrence = int(state.get(phase, 0)) + 1
        state[phase] = occurrence
        _atomic_json(state_path, state)
        return occurrence


def _review_plan(route: str, occurrence: int) -> dict[str, Any]:
    if route == "plan_blocked":
        return {
            "decision": "BLOCKED",
            "rationale": "",
            "findings": [],
            "reason": "fixture plan blocker",
        }
    if route in {"plan_revision", "both_corrections"} and occurrence == 1:
        return {
            "decision": "REVISE",
            "rationale": "",
            "findings": ["revise the fixture plan once"],
            "reason": "",
        }
    if route == "second_plan_review_revises":
        return {
            "decision": "REVISE",
            "rationale": "",
            "findings": [f"fixture plan revision {occurrence}"],
            "reason": "",
        }
    return {
        "decision": "APPROVE",
        "rationale": "fixture plan is approved",
        "findings": [],
        "reason": "",
    }


def _review_implementation(route: str, occurrence: int) -> dict[str, Any]:
    if route == "implementation_blocked":
        return {
            "decision": "BLOCKED",
            "rationale": "",
            "findings": [],
            "reason": "fixture implementation blocker",
        }
    if route in {
        "implementation_fix",
        "both_corrections",
        "checks_fail_after_fix",
    } and occurrence == 1:
        return {
            "decision": "REVISE",
            "rationale": "",
            "findings": ["fix the fixture implementation once"],
            "reason": "",
        }
    return {
        "decision": "APPROVE",
        "rationale": "fixture implementation is approved",
        "findings": [],
        "reason": "",
    }


def _phase_result(
    *,
    route: str,
    phase: str,
    occurrence: int,
    workspace: Path,
) -> dict[str, Any]:
    if phase == "discover":
        return {
            "relevant_paths": ["README.md"],
            "constraints": ["preserve the public contract"],
            "risks": ["fixture-only risk"],
        }
    if phase in {"plan", "revise_plan"}:
        return {
            "steps": ["edit the fixture product", "run the visible check"],
            "acceptance_checks": ["fixture-visible-check"],
        }
    if phase == "review_plan":
        return _review_plan(route, occurrence)
    if phase in {"implement", "fix_implementation"}:
        product = workspace / "fixture-product.txt"
        product.write_text(
            f"{phase} occurrence {occurrence}\n",
            encoding="utf-8",
        )
        return {
            "summary": f"{phase} completed",
            "changed_paths": ["fixture-product.txt"],
            "checks_summary": "provider-side fixture checks completed",
        }
    if phase == "review_implementation":
        if route == "judgment_mutates_product":
            (workspace / "judgment-mutation.txt").write_text(
                "forbidden fixture mutation\n",
                encoding="utf-8",
            )
        return _review_implementation(route, occurrence)
    raise AssertionError(f"unsupported fixture phase: {phase}")


def _split_prompt(prompt: str) -> tuple[str, str]:
    markers = ("\n\n## Output Contract\n", "\n\n## Variant Output Contract\n")
    positions = [
        (prompt.find(marker), marker)
        for marker in markers
        if prompt.find(marker) >= 0
    ]
    if not positions:
        return prompt, ""
    index, marker = min(positions, key=lambda item: item[0])
    return prompt[:index], prompt[index + 2 :]


def _append_jsonl(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _bundle_path_from_environment() -> Path | None:
    raw_bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
    if not raw_bundle:
        return None
    bundle_path = Path(raw_bundle)
    if not bundle_path.is_absolute():
        bundle_path = Path.cwd() / bundle_path
    return bundle_path


def _immediate_route_phase_from_contract(
    prompt: str,
    workspace: Path,
) -> str:
    _user_message, typed_result_schema = _split_prompt(prompt)
    names = tuple(
        match.group("name")
        for match in _CONTRACT_FIELD.finditer(typed_result_schema)
    )
    if not names or len(names) != len(set(names)):
        raise ValueError(
            "fixture provider output contract fields are missing or duplicated"
        )
    fields = frozenset(names)
    if fields == {"relevant_paths", "constraints", "risks"}:
        return "discover"
    if fields == {"steps", "acceptance_checks"}:
        return "plan"
    if fields == {"summary", "changed_paths", "checks_summary"}:
        return "implement"
    if fields == {"decision", "rationale", "findings", "reason"}:
        return (
            "review_implementation"
            if (workspace / "fixture-product.txt").is_file()
            else "review_plan"
        )
    raise ValueError("fixture provider output contract does not identify one phase")


def _codex_shim_main() -> int:
    """Act as a test-only Codex executable for real-launcher integration."""

    prompt = sys.stdin.read()
    workspace = Path.cwd()
    bundle_path = _bundle_path_from_environment()
    if bundle_path is None:
        (workspace / "fixture-product.txt").write_text(
            "direct fixture implementation\n",
            encoding="utf-8",
        )
        print(json.dumps({"fixture_mode": "direct"}, sort_keys=True))
        return 0
    try:
        phase = _immediate_route_phase_from_contract(prompt, workspace)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result = _phase_result(
        route="immediate_approval",
        phase=phase,
        occurrence=1,
        workspace=workspace,
    )
    _atomic_json(bundle_path, result)
    print(json.dumps({"fixture_phase": phase}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=sorted(_PHASES), required=True)
    parser.add_argument("--route", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--request-log", type=Path, required=True)
    parser.add_argument("--system-message", required=True)
    parser.add_argument("--tool-policy", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    args = parser.parse_args()

    prompt = sys.stdin.read()
    user_message, typed_result_schema = _split_prompt(prompt)
    occurrence = _next_occurrence(args.state, args.phase)
    session_identity = f"{args.phase}-{occurrence}"
    _append_jsonl(
        args.request_log,
        {
            "phase": args.phase,
            "occurrence": occurrence,
            "session_identity": session_identity,
            "system_message": args.system_message,
            "user_message": user_message,
            "tool_policy": args.tool_policy,
            "typed_result_schema": typed_result_schema,
            "provider_parameters": {
                "model": args.model,
                "effort": args.effort,
            },
            "conversational_parent_session": None,
        },
    )

    result = _phase_result(
        route=args.route,
        phase=args.phase,
        occurrence=occurrence,
        workspace=Path.cwd(),
    )
    bundle_path = _bundle_path_from_environment()
    if bundle_path is None:
        print("ORCHESTRATOR_OUTPUT_BUNDLE_PATH is required", file=sys.stderr)
        return 2
    _atomic_json(bundle_path, result)
    print(json.dumps({"session_identity": session_identity}, sort_keys=True))
    return 0


if __name__ == "__main__":
    entrypoint = (
        _codex_shim_main
        if Path(sys.argv[0]).name == "codex"
        else main
    )
    raise SystemExit(entrypoint())
