#!/usr/bin/env python3
"""Evaluate generic workflow progress signals for repeated non-progress."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


NORMAL_CONTINUE = "NORMAL_CONTINUE"
STEP_BACK_REQUIRED = "STEP_BACK_REQUIRED"


def _events(signals: Mapping[str, Any]) -> list[dict[str, Any]]:
    events = signals.get("events") or []
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def _latest(events: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    return events[-count:]


def _no_accepted_change(event: Mapping[str, Any]) -> bool:
    if str(event.get("dependency_edge_event") or "").strip() == "retry_ready":
        return False
    return not bool(event.get("accepted_change")) and not str(event.get("commit_hash") or "").strip()


def _work_item_key(event: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(event.get("work_item_id") or "").strip(),
        str(event.get("phase") or "").strip(),
    )


def _revision_contradicted_by_later_block(
    event: Mapping[str, Any],
    later_events: list[dict[str, Any]],
) -> bool:
    if not bool(event.get("plan_revised")):
        return False
    key = _work_item_key(event)
    if not key[0]:
        return False
    return any(
        _work_item_key(later) == key
        and str(later.get("outcome") or "").strip() == "blocked"
        for later in later_events
    )


def _accepted_change_resolves_history(
    event: Mapping[str, Any],
    later_events: list[dict[str, Any]],
) -> bool:
    if _no_accepted_change(event):
        return False
    return not _revision_contradicted_by_later_block(event, later_events)


def _unresolved_suffix(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index in range(len(events) - 1, -1, -1):
        if _accepted_change_resolves_history(events[index], events[index + 1 :]):
            return events[index + 1 :]
    return events


def _all_latest(events: list[dict[str, Any]], count: int, predicate) -> bool:
    latest = _latest(events, count)
    return len(latest) == count and all(predicate(event) for event in latest)


def _most_common(counter: Counter[str], threshold: int) -> str:
    for value, count in counter.most_common():
        if value and count >= threshold:
            return value
    return ""


def evaluate_non_progress(
    signals: Mapping[str, Any],
    *,
    repeated_blocker_threshold: int = 2,
    no_accepted_change_threshold: int = 3,
    prerequisite_chain_threshold: int = 2,
    plan_churn_threshold: int = 2,
    finding_repeat_threshold: int = 2,
) -> dict[str, Any]:
    events = _unresolved_suffix(_events(signals))
    trigger_codes: list[str] = []
    evidence: dict[str, Any] = {}
    failure_fingerprint = ""

    blocker = _most_common(
        Counter(str(event.get("blocker_fingerprint") or "").strip() for event in events),
        repeated_blocker_threshold,
    )
    if blocker:
        trigger_codes.append("same_blocker_repeated")
        evidence["blocker_fingerprint"] = blocker
        failure_fingerprint = failure_fingerprint or blocker

    invalid_dependency = _most_common(
        Counter(
            str(event.get("dependency_edge_fingerprint") or "").strip()
            for event in events
            if str(event.get("dependency_edge_event") or "").strip() == "invalid"
        ),
        repeated_blocker_threshold,
    )
    if invalid_dependency:
        trigger_codes.append("dependency_edge_invalid_repeated")
        evidence["dependency_edge_fingerprint"] = invalid_dependency
        failure_fingerprint = failure_fingerprint or invalid_dependency

    if any(str(event.get("dependency_edge_event") or "").strip() == "downstream_before_blocker_ready" for event in events):
        trigger_codes.append("dependency_downstream_selected_early")
        evidence["dependency_downstream_selected_early"] = True
        failure_fingerprint = failure_fingerprint or "dependency_downstream_selected_early"

    work_item = _most_common(
        Counter(
            str(event.get("work_item_id") or "").strip()
            for event in events
            if str(event.get("outcome") or "").strip() == "blocked"
        ),
        repeated_blocker_threshold,
    )
    if work_item:
        trigger_codes.append("same_work_item_repeatedly_blocked")
        evidence["work_item_id"] = work_item

    if _all_latest(events, no_accepted_change_threshold, _no_accepted_change):
        trigger_codes.append("no_accepted_change_streak")
        evidence["no_accepted_change_streak"] = no_accepted_change_threshold

    if _all_latest(events, prerequisite_chain_threshold, lambda event: bool(event.get("prerequisite_generated"))):
        trigger_codes.append("prerequisite_chain_growth")
        evidence["prerequisite_chain_length"] = prerequisite_chain_threshold

    if _all_latest(
        events,
        plan_churn_threshold,
        lambda event: bool(event.get("plan_revised")) and str(event.get("outcome") or "").strip() == "blocked",
    ):
        trigger_codes.append("plan_churn_without_outcome_change")
        evidence["plan_churn_length"] = plan_churn_threshold

    findings = Counter(
        str(finding).strip()
        for event in events
        for finding in (event.get("review_finding_fingerprints") or [])
        if str(finding).strip()
    )
    finding = _most_common(findings, finding_repeat_threshold)
    if finding:
        trigger_codes.append("review_findings_not_converging")
        evidence["review_finding_fingerprint"] = finding
        failure_fingerprint = failure_fingerprint or finding

    if any(bool(event.get("stale_artifact_detected")) for event in events):
        trigger_codes.append("stale_artifact_provenance")
        evidence["stale_artifact_detected"] = True

    route = STEP_BACK_REQUIRED if trigger_codes else NORMAL_CONTINUE
    if not failure_fingerprint and trigger_codes:
        failure_fingerprint = trigger_codes[0]

    return {
        "schema": "workflow_non_progress_decision/v1",
        "route": route,
        "trigger_codes": trigger_codes,
        "failure_fingerprint": failure_fingerprint,
        "evidence": evidence,
        "recommended_step_back_focus": _recommended_focus(trigger_codes),
    }


def _recommended_focus(trigger_codes: list[str]) -> str:
    if "stale_artifact_provenance" in trigger_codes:
        return "Repair stale or cross-run artifact provenance before selecting more work."
    if "prerequisite_chain_growth" in trigger_codes:
        return "Stop recursive prerequisite generation and reassess the original work boundary."
    if "dependency_edge_invalid_repeated" in trigger_codes:
        return "Stop retrying the same invalid dependency edge and reassess the blocker graph."
    if "dependency_downstream_selected_early" in trigger_codes:
        return "Select or complete the dependency blocker before downstream work."
    if "same_blocker_repeated" in trigger_codes or "same_work_item_repeatedly_blocked" in trigger_codes:
        return "Reassess the blocker: fix workflow mechanics, escalate for a human decision, or let the loop's own recovery machinery continue."
    if "review_findings_not_converging" in trigger_codes:
        return "Reassess repeated review findings instead of continuing incremental fixes."
    if "plan_churn_without_outcome_change" in trigger_codes:
        return "Stop revising the plan incrementally; fix workflow mechanics or escalate for a human decision."
    if "no_accepted_change_streak" in trigger_codes:
        return "Identify why iterations produce no accepted change."
    return ""


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signals", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeated-blocker-threshold", type=int, default=2)
    parser.add_argument("--no-accepted-change-threshold", type=int, default=3)
    parser.add_argument("--prerequisite-chain-threshold", type=int, default=2)
    parser.add_argument("--plan-churn-threshold", type=int, default=2)
    parser.add_argument("--finding-repeat-threshold", type=int, default=2)
    args = parser.parse_args()

    decision = evaluate_non_progress(
        _load_json(Path(args.signals)),
        repeated_blocker_threshold=args.repeated_blocker_threshold,
        no_accepted_change_threshold=args.no_accepted_change_threshold,
        prerequisite_chain_threshold=args.prerequisite_chain_threshold,
        plan_churn_threshold=args.plan_churn_threshold,
        finding_repeat_threshold=args.finding_repeat_threshold,
    )
    _save_json(Path(args.output), decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
