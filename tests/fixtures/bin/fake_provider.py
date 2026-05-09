#!/usr/bin/env python3
"""Deterministic fake provider for Phase 0 workflow oracles."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


WORKSPACE = Path.cwd()


def main(argv: list[str]) -> int:
    _ = _strip_codex_exec(argv)
    prompt = sys.stdin.read()
    scenario = _load_scenario()

    phase = _detect_phase(prompt)
    if phase == "select":
        _write_selection(scenario)
    elif phase == "roadmap_sync":
        _write_roadmap_sync(scenario)
    elif phase == "draft_plan":
        _write_plan()
    elif phase == "review_plan":
        _write_plan_review()
    elif phase == "execute_implementation":
        _write_implementation_outputs(scenario)
    elif phase == "review_implementation":
        _write_implementation_review(scenario)
    elif phase == "fix_implementation":
        _write_implementation_fix()
    else:
        raise SystemExit(f"Unsupported fake provider phase for prompt: {prompt[:120]!r}")
    return 0


def _strip_codex_exec(argv: list[str]) -> list[str]:
    if argv and argv[0] == "exec":
        return argv[1:]
    return argv


def _load_scenario() -> dict[str, Any]:
    path = WORKSPACE / "state/fake_provider_scenario.json"
    if not path.is_file():
        return {"mode": "completed"}
    return json.loads(path.read_text(encoding="utf-8"))


def _detect_phase(prompt: str) -> str:
    if "Select the next backlog item" in prompt:
        return "select"
    if "Review the authoritative roadmap in light of the selected backlog item." in prompt:
        return "roadmap_sync"
    if "Draft a fresh execution-ready plan for the selected backlog item." in prompt:
        return "draft_plan"
    if "First, review the current plan from scratch." in prompt:
        return "review_plan"
    if "write the execution report at the path recorded in `execution_report_target`" in prompt:
        return "execute_implementation"
    if "take the role of a principal engineer and scientific software reviewer." in prompt:
        return "review_implementation"
    if "Determine remaining work by:" in prompt:
        return "fix_implementation"
    if "Primitive implementation outcome oracle" in prompt:
        return "execute_implementation"
    if "Primitive implementation review oracle" in prompt:
        return "review_implementation"
    if any(path.is_dir() for path in WORKSPACE.glob("state/**/implementation-phase")):
        review_pointers = sorted(WORKSPACE.glob("state/**/implementation-phase/implementation_review_report_path.txt"))
        if review_pointers and any(not (path.parent / "implementation_review_decision.txt").exists() for path in review_pointers):
            return "review_implementation"
        return "execute_implementation"
    if any(path.is_file() for path in WORKSPACE.glob("state/**/plan-phase/plan_review_report_path.txt")):
        return "review_plan"
    if any(path.is_file() for path in WORKSPACE.glob("state/**/plan-phase/plan_path.txt")):
        return "draft_plan"
    if any(path.is_file() for path in WORKSPACE.glob("state/**/roadmap-sync/roadmap_sync_report_path.txt")):
        return "roadmap_sync"
    if any(path.is_dir() for path in WORKSPACE.glob("state/**/selector")):
        return "select"
    if any(path.is_file() for path in WORKSPACE.glob("state/review/implementation_review_report_path.txt")):
        return "review_implementation"
    if (WORKSPACE / "artifacts/work/execution_report.md").exists() or (WORKSPACE / "artifacts/work").is_dir():
        return "execute_implementation"
    raise SystemExit("Fake provider could not classify prompt or pending workspace phase")


def _write_selection(scenario: dict[str, Any]) -> None:
    selection_dirs = sorted(path for path in WORKSPACE.glob("state/**/selector") if path.is_dir())
    if not selection_dirs:
        raise SystemExit("No selector state root found")
    selector_dir = next((path for path in selection_dirs if not (path / "selection.json").exists()), selection_dirs[-1])

    latest_manifest = _latest_manifest()
    manifest_items = latest_manifest.get("items", []) if isinstance(latest_manifest, dict) else []
    sequence_entry = _selection_sequence_entry(scenario)
    if sequence_entry is not None:
        scenario = {**scenario, **sequence_entry}

    if scenario.get("selection_mode", "ACTIVE_SELECTION") != "RECOVERED_IN_PROGRESS" and not manifest_items:
        payload = {
            "selection_status": "DONE",
            "selection_rationale": "No active backlog items remain.",
        }
        (selector_dir / "selection.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return

    selection_mode = scenario.get("selection_mode", "ACTIVE_SELECTION")
    selection_status = scenario.get("selection_status", "SELECTED")
    item_id = scenario.get("selected_item_id")
    if not item_id and manifest_items:
        item_id = str(manifest_items[0]["item_id"])
    item_id = item_id or "2026-05-08-dsl-v214-phase0-oracle"
    if selection_mode == "RECOVERED_IN_PROGRESS":
        item_path = scenario.get(
            "selected_item_path", f"docs/backlog/in_progress/{item_id}.md"
        )
    else:
        default_path = f"docs/backlog/active/{item_id}.md"
        if manifest_items:
            default_path = str(manifest_items[0].get("path") or default_path)
        item_path = scenario.get("selected_item_path", default_path)

    if selection_status == "SELECTED":
        payload = {
            "selection_status": "SELECTED",
            "selection_mode": selection_mode,
            "selected_item_id": item_id,
            "selected_item_path": item_path,
            "selection_rationale": "Deterministic oracle selection.",
            "roadmap_sync_hint": scenario.get("roadmap_sync_hint", "NO_CHANGE"),
        }
    elif selection_status == "BLOCKED":
        payload = {
            "selection_status": "BLOCKED",
            "selection_rationale": "No runnable items remain in this oracle scenario.",
            "blocking_reasons": ["oracle fixture requested blocked selection"],
        }
    else:
        payload = {
            "selection_status": "DONE",
            "selection_rationale": "No active backlog items remain.",
        }
    (selector_dir / "selection.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_roadmap_sync(scenario: dict[str, Any]) -> None:
    pointer_candidates = sorted(WORKSPACE.glob("state/**/roadmap-sync/roadmap_sync_report_path.txt"))
    if not pointer_candidates:
        raise SystemExit("No roadmap sync target pointer found")
    pointer = next(
        (path for path in pointer_candidates if not (path.parent / "roadmap_sync_status.txt").exists()),
        pointer_candidates[-1],
    )
    status = scenario.get("roadmap_sync_status", "NO_CHANGE")
    target = _target_from_pointer(pointer)
    target.write_text(
        json.dumps(
            {
                "status": status,
                "summary": "Oracle roadmap sync preserved current roadmap authority.",
                "changed": status == "UPDATED",
                "blocking_reason": None if status != "BLOCKED" else "oracle requested a roadmap block",
                "touched_sections": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pointer.parent / "roadmap_sync_status.txt").write_text(status + "\n", encoding="utf-8")


def _write_plan() -> None:
    pointer_candidates = sorted(WORKSPACE.glob("state/**/plan-phase/plan_path.txt"))
    if not pointer_candidates:
        raise SystemExit("No plan target pointer found")
    pointer = next((path for path in pointer_candidates if not _target_from_pointer(path).exists()), pointer_candidates[-1])
    target = _target_from_pointer(pointer)
    target.write_text(
        "\n".join(
            [
                "# Phase 0 Oracle Plan",
                "",
                "## Objective",
                "- Freeze current Phase 0 behavior in a minimal oracle workspace.",
                "",
                "## Verification",
                "- `python -c \"print('oracle-check')\"`",
                "",
                "## Tasks",
                "- Materialize the selected item context and implementation outcome reports.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_plan_review() -> None:
    pointer_candidates = sorted(WORKSPACE.glob("state/**/plan-phase/plan_review_report_path.txt"))
    if not pointer_candidates:
        raise SystemExit("No plan review report target pointer found")
    pointer = next(
        (path for path in pointer_candidates if not (path.parent / "plan_review_decision.txt").exists()),
        pointer_candidates[-1],
    )
    target = _target_from_pointer(pointer)
    target.write_text(
        json.dumps(
            {
                "decision": "APPROVE",
                "summary": "Oracle plan is execution-ready.",
                "unresolved_high_count": 0,
                "unresolved_medium_count": 0,
                "findings": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (pointer.parent / "plan_review_decision.txt").write_text("APPROVE\n", encoding="utf-8")
    (pointer.parent / "unresolved_high_count.txt").write_text("0\n", encoding="utf-8")
    (pointer.parent / "unresolved_medium_count.txt").write_text("0\n", encoding="utf-8")
    open_findings = pointer.parent / "open_findings.json"
    if open_findings.exists():
        open_findings.write_text('{"findings":[]}\n', encoding="utf-8")


def _write_implementation_outputs(scenario: dict[str, Any]) -> None:
    mode = scenario.get("mode", "completed")

    impl_roots = sorted(path for path in WORKSPACE.glob("state/**/implementation-phase") if path.is_dir())
    if impl_roots:
        impl_root = next((path for path in impl_roots if not (path / "implementation_state.json").exists()), impl_roots[-1])
        execution_target = _target_from_pointer(impl_root / "execution_report_target_path.txt")
        progress_target = _target_from_pointer(impl_root / "progress_report_target_path.txt")
    else:
        execution_target = WORKSPACE / "artifacts/work/execution_report.md"
        progress_target = WORKSPACE / "artifacts/work/progress_report.md"

    if mode in {"completed", "review_approve", "review_revise"}:
        execution_target.parent.mkdir(parents=True, exist_ok=True)
        execution_target.write_text(
            "\n".join(
                [
                    "# Execution Report",
                    "",
                    "## Completed In This Pass",
                    "- Wrote the completed oracle execution report.",
                    "",
                    "## Completed Plan Tasks",
                    "- Produced deterministic Phase 0 evidence.",
                    "",
                    "## Remaining Required Plan Tasks",
                    "- None.",
                    "",
                    "## Verification",
                    "- oracle-check is expected to pass.",
                    "",
                    "## Residual Risks",
                    "- Oracle fixture only.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    elif mode == "blocked":
        progress_target.parent.mkdir(parents=True, exist_ok=True)
        progress_target.write_text(
            "\n".join(
                [
                    "# Blocked Progress Report",
                    "",
                    "## Active Work",
                    "- Phase 0 oracle implementation",
                    "",
                    "## Current Status",
                    "- Waiting on an unavailable artifact.",
                    "",
                    "## Next Resume Condition",
                    "- Required artifact becomes available.",
                    "",
                    "## Blocker",
                    "- Required upstream artifact is unavailable.",
                    "",
                    "Blocker Class: missing_resource",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    elif mode == "both_reports":
        _write_implementation_outputs({"mode": "completed"})
        progress_target.parent.mkdir(parents=True, exist_ok=True)
        progress_target.write_text(
            "# Blocked Progress Report\n\n## Blocker\n- Ambiguous oracle outcome.\n\nBlocker Class: missing_resource\n",
            encoding="utf-8",
        )
    elif mode == "neither_report":
        return
    else:
        raise SystemExit(f"Unsupported implementation mode: {mode}")


def _write_implementation_review(scenario: dict[str, Any]) -> None:
    mode = scenario.get("mode", "review_approve")
    pointer_candidates = sorted(WORKSPACE.glob("state/**/implementation-phase/implementation_review_report_path.txt"))
    if pointer_candidates:
        pointer = next(
            (
                path
                for path in pointer_candidates
                if not (path.parent / "implementation_review_decision.txt").exists()
            ),
            pointer_candidates[-1],
        )
        target = _target_from_pointer(pointer)
        decision_path = pointer.parent / "implementation_review_decision.txt"
    else:
        target = WORKSPACE / "artifacts/review/implementation_review.md"
        decision_path = WORKSPACE / "state/review/implementation_review_decision.txt"
        decision_path.parent.mkdir(parents=True, exist_ok=True)

    decision = "REVISE" if mode == "review_revise" else "APPROVE"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "# Implementation Review",
                "",
                f"Decision: {decision}",
                "",
                "## Follow-Up Work",
                "- None.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    decision_path.write_text(decision + "\n", encoding="utf-8")


def _write_implementation_fix() -> None:
    pointer_candidates = sorted(WORKSPACE.glob("state/**/implementation-phase/execution_report_target_path.txt"))
    if not pointer_candidates:
        raise SystemExit("No execution report target for fix loop")
    target = _target_from_pointer(pointer_candidates[-1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Execution Report\n\nFixed after review revise.\n", encoding="utf-8")


def _target_from_pointer(pointer: Path) -> Path:
    target_relpath = pointer.read_text(encoding="utf-8").strip()
    if not target_relpath:
        raise SystemExit(f"Empty pointer file: {pointer}")
    return WORKSPACE / target_relpath


def _latest_manifest() -> dict[str, Any] | None:
    candidates = sorted(WORKSPACE.glob("state/**/eligible_manifest.json"))
    if not candidates:
        candidates = sorted(WORKSPACE.glob("state/**/manifest.json"))
    if not candidates:
        return None
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


def _selection_sequence_entry(scenario: dict[str, Any]) -> dict[str, Any] | None:
    sequence = scenario.get("selection_sequence")
    if not isinstance(sequence, list) or not sequence:
        return None
    counter_path = WORKSPACE / "state/fake_provider_select_count.txt"
    count = 0
    if counter_path.is_file():
        count = int(counter_path.read_text(encoding="utf-8").strip() or "0")
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    counter_path.write_text(str(count + 1) + "\n", encoding="utf-8")
    entry = sequence[count] if count < len(sequence) else sequence[-1]
    return dict(entry)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
