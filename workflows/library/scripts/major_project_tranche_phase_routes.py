#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from major_project_escalation_state import (
    activate_upstream,
    clear_upstream,
    reset_ledger_on_design_approval,
)


TERMINAL_OUTCOMES = {
    "APPROVED",
    "SKIPPED_AFTER_DESIGN",
    "SKIPPED_AFTER_PLAN",
    "SKIPPED_AFTER_IMPLEMENTATION",
    "ESCALATE_ROADMAP_REVISION",
}


def read_current_phase(*, item_state_root: pathlib.Path, output_bundle: pathlib.Path) -> dict[str, str]:
    phase_path = item_state_root / "current_phase.txt"
    phase = phase_path.read_text(encoding="utf-8").strip()
    payload = {"current_phase": phase}
    _write_json(output_bundle, payload)
    return payload


def route_after_big_design(
    *,
    item_state_root: pathlib.Path,
    implementation_phase_state_root: pathlib.Path,
    project_brief_path: str,
    project_roadmap_path: str,
    tranche_manifest_path: str,
    tranche_brief_path: str,
    design_target_path: str,
    plan_target_path: str,
    execution_report_target_path: str,
    item_summary_target_path: str,
    output_bundle: pathlib.Path,
) -> dict[str, str]:
    phase_root = _current_phase_root(item_state_root, "big_design")
    decision = _read_text(phase_root / "final_design_review_decision.txt")
    if decision == "APPROVE":
        reset_ledger_on_design_approval(implementation_phase_state_root=implementation_phase_state_root)
        clear_upstream(item_state_root=item_state_root, resolution="consumed_by_redesign")
        return _continue(item_state_root, "plan", output_bundle)
    if decision == "ESCALATE_ROADMAP_REVISION":
        roadmap_change_request_path = _read_text(phase_root / "final_roadmap_change_request_path.txt")
        _finalize_escalate_roadmap_revision(
            item_state_root=item_state_root,
            project_brief_path=project_brief_path,
            project_roadmap_path=project_roadmap_path,
            tranche_manifest_path=tranche_manifest_path,
            tranche_brief_path=tranche_brief_path,
            design_target_path=design_target_path,
            plan_target_path=plan_target_path,
            execution_report_target_path=execution_report_target_path,
            item_summary_target_path=item_summary_target_path,
            roadmap_change_request_path=roadmap_change_request_path,
        )
        return _terminal("ESCALATE_ROADMAP_REVISION", output_bundle)
    _finalize_skipped(
        item_state_root=item_state_root,
        project_brief_path=project_brief_path,
        project_roadmap_path=project_roadmap_path,
        tranche_manifest_path=tranche_manifest_path,
        tranche_brief_path=tranche_brief_path,
        design_path=design_target_path,
        plan_path=plan_target_path,
        execution_report_target_path=execution_report_target_path,
        item_summary_target_path=item_summary_target_path,
        outcome="SKIPPED_AFTER_DESIGN",
        failed_phase="design",
        message="Skipped before plan and implementation because big-design phase failed.\n",
    )
    return _terminal("SKIPPED_AFTER_DESIGN", output_bundle)


def route_after_plan(
    *,
    item_state_root: pathlib.Path,
    project_brief_path: str,
    project_roadmap_path: str,
    tranche_manifest_path: str,
    tranche_brief_path: str,
    design_path: str,
    plan_target_path: str,
    execution_report_target_path: str,
    item_summary_target_path: str,
    output_bundle: pathlib.Path,
) -> dict[str, str]:
    phase_root = _current_phase_root(item_state_root, "plan")
    decision = _read_text(phase_root / "final_plan_review_decision.txt")
    if decision == "APPROVE":
        clear_upstream(item_state_root=item_state_root, resolution="consumed_by_plan")
        return _continue(item_state_root, "implementation", output_bundle)
    if decision == "ESCALATE_REDESIGN":
        source_context_path = pathlib.Path(_read_text(phase_root / "final_plan_escalation_context_path.txt"))
        activate_upstream(item_state_root=item_state_root, source_context_path=source_context_path)
        return _continue(item_state_root, "big_design", output_bundle)
    _finalize_skipped(
        item_state_root=item_state_root,
        project_brief_path=project_brief_path,
        project_roadmap_path=project_roadmap_path,
        tranche_manifest_path=tranche_manifest_path,
        tranche_brief_path=tranche_brief_path,
        design_path=design_path,
        plan_path=plan_target_path,
        execution_report_target_path=execution_report_target_path,
        item_summary_target_path=item_summary_target_path,
        outcome="SKIPPED_AFTER_PLAN",
        failed_phase="plan",
        message="Skipped before implementation because plan phase failed.\n",
    )
    return _terminal("SKIPPED_AFTER_PLAN", output_bundle)


def route_after_implementation(
    *,
    item_state_root: pathlib.Path,
    project_brief_path: str,
    project_roadmap_path: str,
    tranche_manifest_path: str,
    tranche_brief_path: str,
    design_path: str,
    plan_path: str,
    execution_report_target_path: str,
    item_summary_target_path: str,
    output_bundle: pathlib.Path,
) -> dict[str, str]:
    phase_root = _current_phase_root(item_state_root, "implementation")
    decision = _read_text(phase_root / "final_implementation_review_decision.txt")
    if decision == "APPROVE":
        _finalize_approved(
            item_state_root=item_state_root,
            project_brief_path=project_brief_path,
            project_roadmap_path=project_roadmap_path,
            tranche_manifest_path=tranche_manifest_path,
            tranche_brief_path=tranche_brief_path,
            design_path=design_path,
            plan_path=plan_path,
            execution_report_target_path=execution_report_target_path,
            item_summary_target_path=item_summary_target_path,
        )
        return _terminal("APPROVED", output_bundle)
    if decision == "ESCALATE_REPLAN":
        source_context_path = pathlib.Path(_read_text(phase_root / "final_implementation_escalation_context_path.txt"))
        activate_upstream(item_state_root=item_state_root, source_context_path=source_context_path)
        return _continue(item_state_root, "plan", output_bundle)
    _finalize_skipped(
        item_state_root=item_state_root,
        project_brief_path=project_brief_path,
        project_roadmap_path=project_roadmap_path,
        tranche_manifest_path=tranche_manifest_path,
        tranche_brief_path=tranche_brief_path,
        design_path=design_path,
        plan_path=plan_path,
        execution_report_target_path=execution_report_target_path,
        item_summary_target_path=item_summary_target_path,
        outcome="SKIPPED_AFTER_IMPLEMENTATION",
        failed_phase="implementation",
        message="Implementation phase failed before producing a report.\n",
    )
    return _terminal("SKIPPED_AFTER_IMPLEMENTATION", output_bundle)


def _continue(item_state_root: pathlib.Path, next_phase: str, output_bundle: pathlib.Path) -> dict[str, str]:
    (item_state_root / "current_phase.txt").write_text(next_phase + "\n", encoding="utf-8")
    payload = {"tranche_status": "CONTINUE", "next_phase": next_phase}
    _write_json(output_bundle, payload)
    return payload


def _terminal(outcome: str, output_bundle: pathlib.Path) -> dict[str, str]:
    if outcome not in TERMINAL_OUTCOMES:
        raise ValueError(f"Unsupported terminal outcome: {outcome}")
    payload = {"tranche_status": outcome, "next_phase": "terminal"}
    _write_json(output_bundle, payload)
    return payload


def _current_phase_root(item_state_root: pathlib.Path, phase: str) -> pathlib.Path:
    return pathlib.Path(_read_text(item_state_root / f"current_{phase}_phase_state_root.txt"))


def _finalize_approved(
    *,
    item_state_root: pathlib.Path,
    project_brief_path: str,
    project_roadmap_path: str,
    tranche_manifest_path: str,
    tranche_brief_path: str,
    design_path: str,
    plan_path: str,
    execution_report_target_path: str,
    item_summary_target_path: str,
) -> None:
    _write_summary(
        item_summary_target_path,
        {
            "project_brief_path": project_brief_path,
            "project_roadmap_path": project_roadmap_path,
            "tranche_manifest_path": tranche_manifest_path,
            "tranche_brief_path": tranche_brief_path,
            "item_outcome": "APPROVED",
            "failed_phase": None,
            "design_path": design_path,
            "plan_path": plan_path,
            "execution_report_path": execution_report_target_path,
        },
    )
    _write_final_pointers(item_state_root, "APPROVED", execution_report_target_path, item_summary_target_path)


def _finalize_escalate_roadmap_revision(
    *,
    item_state_root: pathlib.Path,
    project_brief_path: str,
    project_roadmap_path: str,
    tranche_manifest_path: str,
    tranche_brief_path: str,
    design_target_path: str,
    plan_target_path: str,
    execution_report_target_path: str,
    item_summary_target_path: str,
    roadmap_change_request_path: str,
) -> None:
    execution_report_path = pathlib.Path(execution_report_target_path)
    execution_report_path.parent.mkdir(parents=True, exist_ok=True)
    execution_report_path.write_text("Escalated to roadmap revision from big-design review.\n", encoding="utf-8")
    _write_summary(
        item_summary_target_path,
        {
            "project_brief_path": project_brief_path,
            "project_roadmap_path": project_roadmap_path,
            "tranche_manifest_path": tranche_manifest_path,
            "tranche_brief_path": tranche_brief_path,
            "item_outcome": "ESCALATE_ROADMAP_REVISION",
            "failed_phase": None,
            "design_path": design_target_path,
            "plan_path": plan_target_path,
            "execution_report_path": execution_report_target_path,
            "roadmap_change_request_path": roadmap_change_request_path,
        },
    )
    _write_final_pointers(
        item_state_root,
        "ESCALATE_ROADMAP_REVISION",
        execution_report_target_path,
        item_summary_target_path,
        roadmap_change_request_path,
    )


def _finalize_skipped(
    *,
    item_state_root: pathlib.Path,
    project_brief_path: str,
    project_roadmap_path: str,
    tranche_manifest_path: str,
    tranche_brief_path: str,
    design_path: str,
    plan_path: str,
    execution_report_target_path: str,
    item_summary_target_path: str,
    outcome: str,
    failed_phase: str,
    message: str,
) -> None:
    execution_report_path = pathlib.Path(execution_report_target_path)
    execution_report_path.parent.mkdir(parents=True, exist_ok=True)
    if not execution_report_path.exists():
        execution_report_path.write_text(message, encoding="utf-8")
    _write_summary(
        item_summary_target_path,
        {
            "project_brief_path": project_brief_path,
            "project_roadmap_path": project_roadmap_path,
            "tranche_manifest_path": tranche_manifest_path,
            "tranche_brief_path": tranche_brief_path,
            "item_outcome": outcome,
            "failed_phase": failed_phase,
            "design_path": design_path,
            "plan_path": plan_path,
            "execution_report_path": execution_report_target_path,
        },
    )
    _write_final_pointers(item_state_root, outcome, execution_report_target_path, item_summary_target_path)


def _write_summary(path: str, payload: dict[str, Any]) -> None:
    summary_path = pathlib.Path(path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_final_pointers(
    item_state_root: pathlib.Path,
    outcome: str,
    execution_report_path: str,
    item_summary_path: str,
    roadmap_change_request_path: str | None = None,
) -> None:
    item_state_root.mkdir(parents=True, exist_ok=True)
    (item_state_root / "item_outcome.txt").write_text(outcome + "\n", encoding="utf-8")
    (item_state_root / "final_execution_report_path.txt").write_text(execution_report_path + "\n", encoding="utf-8")
    (item_state_root / "final_item_summary_path.txt").write_text(item_summary_path + "\n", encoding="utf-8")
    if roadmap_change_request_path is not None:
        (item_state_root / "final_roadmap_change_request_path.txt").write_text(
            roadmap_change_request_path + "\n", encoding="utf-8"
        )


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Route major-project tranche phase outcomes.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read-current-phase")
    read_parser.add_argument("--item-state-root", type=pathlib.Path, required=True)
    read_parser.add_argument("--output-bundle", type=pathlib.Path, required=True)

    for command in ("route-after-big-design", "route-after-plan", "route-after-implementation"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--item-state-root", type=pathlib.Path, required=True)
        command_parser.add_argument("--project-brief-path", required=True)
        command_parser.add_argument("--project-roadmap-path", required=True)
        command_parser.add_argument("--tranche-manifest-path", required=True)
        command_parser.add_argument("--tranche-brief-path", required=True)
        command_parser.add_argument("--execution-report-target-path", required=True)
        command_parser.add_argument("--item-summary-target-path", required=True)
        command_parser.add_argument("--output-bundle", type=pathlib.Path, required=True)
        if command == "route-after-big-design":
            command_parser.add_argument("--implementation-phase-state-root", type=pathlib.Path, required=True)
            command_parser.add_argument("--design-target-path", required=True)
            command_parser.add_argument("--plan-target-path", required=True)
        else:
            command_parser.add_argument("--design-path", required=True)
            command_parser.add_argument("--plan-target-path", required=True)

    args = parser.parse_args()
    kwargs = vars(args)
    command = kwargs.pop("command")
    if command == "read-current-phase":
        read_current_phase(**kwargs)
    elif command == "route-after-big-design":
        route_after_big_design(**kwargs)
    elif command == "route-after-plan":
        route_after_plan(**kwargs)
    elif command == "route-after-implementation":
        kwargs["plan_path"] = kwargs.pop("plan_target_path")
        route_after_implementation(**kwargs)
    else:
        raise AssertionError(command)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    raise SystemExit(main())
