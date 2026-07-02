import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _event(
    *,
    iteration: int,
    work_item_id: str = "item-a",
    outcome: str = "blocked",
    accepted_change: bool = False,
    commit_hash: str = "",
    blocker_fingerprint: str = "",
    review_finding_fingerprints: list[str] | None = None,
    prerequisite_generated: bool = False,
    plan_revised: bool = False,
    stale_artifact_detected: bool = False,
    dependency_edge_event: str = "",
    dependency_edge_fingerprint: str = "",
    dependency_chain_depth: int = 0,
) -> dict:
    return {
        "iteration": iteration,
        "work_item_id": work_item_id,
        "phase": "implementation",
        "outcome": outcome,
        "accepted_change": accepted_change,
        "commit_hash": commit_hash,
        "blocker_fingerprint": blocker_fingerprint,
        "review_finding_fingerprints": review_finding_fingerprints or [],
        "prerequisite_generated": prerequisite_generated,
        "plan_revised": plan_revised,
        "stale_artifact_detected": stale_artifact_detected,
        "dependency_edge_event": dependency_edge_event,
        "dependency_edge_fingerprint": dependency_edge_fingerprint,
        "dependency_chain_depth": dependency_chain_depth,
    }


def _signals(events: list[dict]) -> dict:
    return {
        "schema": "workflow_progress_signals/v1",
        "run_id": "run-1",
        "current_iteration": max((event["iteration"] for event in events), default=0),
        "events": events,
    }


def test_evaluator_requires_step_back_for_repeated_blocker():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(iteration=1, blocker_fingerprint="same-blocker"),
                _event(iteration=2, blocker_fingerprint="same-blocker"),
            ]
        ),
        repeated_blocker_threshold=2,
    )

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "same_blocker_repeated" in decision["trigger_codes"]
    assert decision["failure_fingerprint"] == "same-blocker"


def test_evaluator_requires_step_back_for_no_accepted_change_streak():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals([_event(iteration=1), _event(iteration=2), _event(iteration=3)]),
        no_accepted_change_threshold=3,
    )

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "no_accepted_change_streak" in decision["trigger_codes"]


def test_evaluator_requires_step_back_for_prerequisite_chain_growth():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(iteration=1, prerequisite_generated=True),
                _event(iteration=2, prerequisite_generated=True),
            ]
        ),
        prerequisite_chain_threshold=2,
    )

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "prerequisite_chain_growth" in decision["trigger_codes"]


def test_evaluator_requires_step_back_for_repeated_invalid_dependency_edge():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(
                    iteration=1,
                    dependency_edge_event="invalid",
                    dependency_edge_fingerprint="edge-alpha",
                ),
                _event(
                    iteration=2,
                    dependency_edge_event="invalid",
                    dependency_edge_fingerprint="edge-alpha",
                ),
            ]
        ),
        repeated_blocker_threshold=2,
    )

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "dependency_edge_invalid_repeated" in decision["trigger_codes"]
    assert decision["failure_fingerprint"] == "edge-alpha"


def test_evaluator_treats_dependency_retry_ready_as_progress():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(iteration=1, blocker_fingerprint="same-blocker"),
                _event(
                    iteration=2,
                    dependency_edge_event="retry_ready",
                    dependency_edge_fingerprint="edge-alpha",
                ),
                _event(iteration=3, blocker_fingerprint="same-blocker"),
            ]
        ),
        repeated_blocker_threshold=2,
    )

    assert decision["route"] == "NORMAL_CONTINUE"


def test_evaluator_flags_downstream_selected_before_dependency_blocker_ready():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(
                    iteration=1,
                    dependency_edge_event="downstream_before_blocker_ready",
                    dependency_edge_fingerprint="edge-alpha",
                )
            ]
        )
    )

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "dependency_downstream_selected_early" in decision["trigger_codes"]


def test_projector_emits_dependency_edge_signal_fields():
    from workflows.library.scripts.project_lisp_frontend_progress_signals import project_progress_signals

    edge = {
        "blocked_work": {"source": "DESIGN_GAP", "id": "parser"},
        "blocker_work": {"source": "DESIGN_GAP", "id": "context"},
        "relation": "requires_completion",
        "reason_code": "missing_context",
        "retry_target": {"source": "DESIGN_GAP", "id": "parser"},
        "status": "waiting",
    }
    signals = project_progress_signals(
        run_id="run-1",
        run_state={
            "history": [
                {
                    "event": "blocked",
                    "item_id": "parser",
                    "source": "DESIGN_GAP",
                    "reason": "implementation_blocked",
                    "recovery_route": "PREREQUISITE_GAP_REQUIRED",
                    "recovery_dependency_edge": edge,
                }
            ]
        },
        current_iteration=1,
    )

    event = signals["events"][0]
    assert event["dependency_edge_event"] == "waiting"
    assert event["dependency_edge_fingerprint"]


def test_rejected_blocked_revision_is_not_an_accepted_change():
    from workflows.library.scripts.project_lisp_frontend_progress_signals import project_progress_signals
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    history = [
        {"event": "blocked", "item_id": "item-a", "source": "IMPLEMENTATION", "reason": "tests_failing"},
        {
            "event": "blocked_recovery_review_revise",
            "item_id": "item-a",
            "source": "IMPLEMENTATION",
            "reason": "tests_failing",
        },
        {
            "event": "blocked_recovery_review_revise",
            "item_id": "item-a",
            "source": "IMPLEMENTATION",
            "reason": "tests_failing",
        },
    ]
    signals = project_progress_signals(run_id="run-1", run_state={"history": history}, current_iteration=len(history))

    revise_event = signals["events"][1]
    assert revise_event["plan_revised"] is True
    assert revise_event["accepted_change"] is False
    assert revise_event["outcome"] == "blocked"

    decision = evaluate_non_progress(signals, plan_churn_threshold=2)

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "plan_churn_without_outcome_change" in decision["trigger_codes"]


def test_step_back_event_does_not_reset_unresolved_suffix_for_repeated_blocker():
    from workflows.library.scripts.project_lisp_frontend_progress_signals import project_progress_signals
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    history = [
        {"event": "blocked", "item_id": "item-a", "source": "IMPLEMENTATION", "reason": "tests_failing"},
        {"event": "step_back", "item_id": "item-a", "source": "IMPLEMENTATION", "reason": "tests_failing"},
        {"event": "blocked", "item_id": "item-a", "source": "IMPLEMENTATION", "reason": "tests_failing"},
    ]
    signals = project_progress_signals(run_id="run-1", run_state={"history": history}, current_iteration=len(history))

    step_back_event = signals["events"][1]
    assert step_back_event["accepted_change"] is False

    decision = evaluate_non_progress(signals, repeated_blocker_threshold=2)

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "same_blocker_repeated" in decision["trigger_codes"]


def test_evaluator_requires_step_back_for_plan_churn_without_outcome_change():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(iteration=1, plan_revised=True),
                _event(iteration=2, plan_revised=True),
            ]
        ),
        plan_churn_threshold=2,
    )

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "plan_churn_without_outcome_change" in decision["trigger_codes"]


def test_evaluator_requires_step_back_for_repeated_review_finding():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(iteration=1, review_finding_fingerprints=["finding-a"]),
                _event(iteration=2, review_finding_fingerprints=["finding-a"]),
            ]
        ),
        finding_repeat_threshold=2,
    )

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "review_findings_not_converging" in decision["trigger_codes"]


def test_evaluator_requires_step_back_for_stale_artifact_provenance():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(_signals([_event(iteration=1, stale_artifact_detected=True)]))

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "stale_artifact_provenance" in decision["trigger_codes"]


def test_evaluator_only_counts_unresolved_history_after_latest_accepted_change():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(iteration=1, blocker_fingerprint="same-blocker"),
                _event(iteration=2, accepted_change=True, outcome="changed"),
                _event(iteration=3, blocker_fingerprint="same-blocker"),
            ]
        ),
        repeated_blocker_threshold=2,
    )

    assert decision["route"] == "NORMAL_CONTINUE"


def test_evaluator_treats_revision_then_same_work_block_as_unresolved():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(iteration=1, work_item_id="item-a"),
                _event(
                    iteration=2,
                    work_item_id="item-a",
                    accepted_change=True,
                    outcome="changed",
                    plan_revised=True,
                ),
                _event(iteration=3, work_item_id="item-a"),
            ]
        ),
        repeated_blocker_threshold=2,
    )

    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "same_work_item_repeatedly_blocked" in decision["trigger_codes"]


def test_evaluator_allows_revision_before_different_work_block():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(iteration=1, work_item_id="item-a"),
                _event(
                    iteration=2,
                    work_item_id="item-a",
                    accepted_change=True,
                    outcome="changed",
                    plan_revised=True,
                ),
                _event(iteration=3, work_item_id="item-b"),
            ]
        ),
        repeated_blocker_threshold=2,
    )

    assert decision["route"] == "NORMAL_CONTINUE"


def test_evaluator_preserves_signal_order_across_restarted_iteration_numbers():
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    decision = evaluate_non_progress(
        _signals(
            [
                _event(iteration=103, blocker_fingerprint="same-blocker"),
                _event(iteration=104, blocker_fingerprint="same-blocker"),
                _event(iteration=2, accepted_change=True, outcome="changed"),
            ]
        ),
        repeated_blocker_threshold=2,
    )

    assert decision["route"] == "NORMAL_CONTINUE"


def test_evaluator_cli_writes_decision_bundle(tmp_path):
    signals = tmp_path / "signals.json"
    output = tmp_path / "decision.json"
    signals.write_text(
        json.dumps(_signals([_event(iteration=1, blocker_fingerprint="x"), _event(iteration=2, blocker_fingerprint="x")]))
        + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "workflows/library/scripts/evaluate_workflow_non_progress.py"),
            "--signals",
            str(signals),
            "--output",
            str(output),
            "--repeated-blocker-threshold",
            "2",
        ],
        cwd=ROOT,
        check=True,
    )

    decision = json.loads(output.read_text(encoding="utf-8"))
    assert decision["route"] == "STEP_BACK_REQUIRED"
    assert "same_blocker_repeated" in decision["trigger_codes"]


def test_record_step_back_outcome_blocks_workflow_mechanics_repair(tmp_path):
    state = tmp_path / "run_state.json"
    decision = tmp_path / "decision.json"
    diagnosis = tmp_path / "diagnosis.json"
    summary = tmp_path / "summary.json"
    drain_status = tmp_path / "status.txt"
    pre_selection = tmp_path / "blocked-recovery.json"
    state.write_text(json.dumps({"run_id": "run-1", "history": []}) + "\n", encoding="utf-8")
    decision.write_text(
        json.dumps(
            {
                "route": "STEP_BACK_REQUIRED",
                "trigger_codes": ["same_blocker_repeated"],
                "failure_fingerprint": "same-blocker",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    diagnosis.write_text(
        json.dumps({"action": "FIX_WORKFLOW_MECHANICS", "rationale": "Stop recursive prerequisite recovery."}) + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "workflows/library/scripts/record_workflow_step_back_outcome.py"),
            "--state-path",
            str(state),
            "--decision-path",
            str(decision),
            "--diagnosis-path",
            str(diagnosis),
            "--summary-path",
            str(summary),
            "--drain-status-path",
            str(drain_status),
            "--pre-selection-output",
            str(pre_selection),
            "--iteration",
            "12",
        ],
        cwd=ROOT,
        check=True,
    )

    updated = json.loads(state.read_text(encoding="utf-8"))
    event = updated["history"][-1]
    assert event["event"] == "step_back"
    assert event["iteration"] == 12
    assert event["trigger_codes"] == ["same_blocker_repeated"]
    assert event["failure_fingerprint"] == "same-blocker"
    assert event["action"] == "FIX_WORKFLOW_MECHANICS"
    assert drain_status.read_text(encoding="utf-8").strip() == "BLOCKED"
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["record_status"] == "STEP_BACK_RECORDED"
    bundle = json.loads(pre_selection.read_text(encoding="utf-8"))
    assert bundle["pre_selection_route"] == "BLOCKED"
    assert bundle["step_back_action"] == "FIX_WORKFLOW_MECHANICS"
    assert bundle["step_back_drain_status"] == "BLOCKED"


def test_record_step_back_outcome_blocks_for_human_decision(tmp_path):
    state = tmp_path / "run_state.json"
    decision = tmp_path / "decision.json"
    diagnosis = tmp_path / "diagnosis.json"
    summary = tmp_path / "summary.json"
    drain_status = tmp_path / "status.txt"
    state.write_text(json.dumps({"run_id": "run-1", "history": []}) + "\n", encoding="utf-8")
    decision.write_text(json.dumps({"route": "STEP_BACK_REQUIRED", "trigger_codes": []}) + "\n", encoding="utf-8")
    diagnosis.write_text(json.dumps({"action": "NEEDS_HUMAN_DECISION", "rationale": "External choice required."}) + "\n", encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "workflows/library/scripts/record_workflow_step_back_outcome.py"),
            "--state-path",
            str(state),
            "--decision-path",
            str(decision),
            "--diagnosis-path",
            str(diagnosis),
            "--summary-path",
            str(summary),
            "--drain-status-path",
            str(drain_status),
            "--iteration",
            "13",
        ],
        cwd=ROOT,
        check=True,
    )

    assert drain_status.read_text(encoding="utf-8").strip() == "BLOCKED"
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["action"] == "NEEDS_HUMAN_DECISION"


def test_iteration_resolver_prefers_step_back_status(tmp_path):
    pre_selection = tmp_path / "blocked-recovery.json"
    normal_status = tmp_path / "missing-normal-status.txt"
    prereq_status = tmp_path / "missing-prereq-status.txt"
    recovery_status = tmp_path / "missing-recovery-status.txt"
    recovered_status = tmp_path / "missing-recovered-status.txt"
    step_back_status = tmp_path / "step-back-status.txt"
    output = tmp_path / "drain-status.txt"
    pre_selection.write_text(json.dumps({"pre_selection_route": "BLOCKED"}) + "\n", encoding="utf-8")
    step_back_status.write_text("CONTINUE\n", encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py"),
            "--pre-selection-bundle-path",
            str(pre_selection),
            "--normal-status-path",
            str(normal_status),
            "--prerequisite-recovery-status-path",
            str(prereq_status),
            "--recovery-record-status-path",
            str(recovery_status),
            "--recovered-work-item-status-path",
            str(recovered_status),
            "--step-back-status-path",
            str(step_back_status),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )

    assert output.read_text(encoding="utf-8").strip() == "CONTINUE"


def test_recommended_focus_excludes_deleted_actions():
    """Verify that recommended_step_back_focus never mentions split, redraft, or different plan."""
    from workflows.library.scripts.evaluate_workflow_non_progress import evaluate_non_progress

    # Test cases that trigger each recommendation path
    test_cases = [
        ("stale_artifact_provenance", [_event(iteration=1, stale_artifact_detected=True)]),
        ("prerequisite_chain_growth", [_event(iteration=1, prerequisite_generated=True), _event(iteration=2, prerequisite_generated=True)]),
        ("dependency_edge_invalid_repeated", [_event(iteration=1, dependency_edge_event="invalid", dependency_edge_fingerprint="edge-a"), _event(iteration=2, dependency_edge_event="invalid", dependency_edge_fingerprint="edge-a")]),
        ("dependency_downstream_selected_early", [_event(iteration=1, dependency_edge_event="downstream_before_blocker_ready")]),
        ("same_blocker_repeated", [_event(iteration=1, blocker_fingerprint="blocker-x"), _event(iteration=2, blocker_fingerprint="blocker-x")]),
        ("review_findings_not_converging", [_event(iteration=1, review_finding_fingerprints=["finding-a"]), _event(iteration=2, review_finding_fingerprints=["finding-a"])]),
        ("plan_churn_without_outcome_change", [_event(iteration=1, plan_revised=True), _event(iteration=2, plan_revised=True)]),
        ("no_accepted_change_streak", [_event(iteration=1), _event(iteration=2), _event(iteration=3)]),
    ]

    forbidden_strings = ["split", "redraft", "different plan"]

    for trigger_code, events in test_cases:
        decision = evaluate_non_progress(_signals(events))
        focus = decision["recommended_step_back_focus"]
        focus_lower = focus.lower()

        for forbidden in forbidden_strings:
            assert forbidden not in focus_lower, f"Trigger '{trigger_code}' recommendation contains forbidden word '{forbidden}': {focus}"
