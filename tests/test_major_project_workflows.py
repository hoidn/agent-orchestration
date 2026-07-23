import json
from pathlib import Path

import yaml

from workflows.library.scripts.major_project_scope_boundary import (
    check_completion,
    write_scope_boundary,
)


ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(relpath: str) -> dict:
    return yaml.safe_load((ROOT / relpath).read_text(encoding="utf-8"))


def _walk_steps(steps: list[dict]):
    for step in steps:
        yield step
        repeat_until = step.get("repeat_until")
        if isinstance(repeat_until, dict):
            yield from _walk_steps(repeat_until.get("steps", []))
        match = step.get("match")
        if isinstance(match, dict):
            for case in match.get("cases", {}).values():
                case_steps = case.get("steps", case) if isinstance(case, dict) else case
                yield from _walk_steps(case_steps)
        for branch_name in ("then", "else"):
            branch = step.get(branch_name)
            if isinstance(branch, dict):
                yield from _walk_steps(branch.get("steps", []))
            elif isinstance(branch, list):
                yield from _walk_steps(branch)
        for_each = step.get("for_each")
        if isinstance(for_each, dict):
            yield from _walk_steps(for_each.get("steps", []))


def _step_by_name(workflow: dict, name: str) -> dict:
    for step in _walk_steps(workflow["steps"]):
        if step["name"] == name:
            return step
    raise AssertionError(f"Missing step {name}")


def _step_names(workflow: dict) -> set[str]:
    return {step["name"] for step in _walk_steps(workflow["steps"])}


def _all_allowed_values(node):
    if isinstance(node, dict):
        if isinstance(node.get("allowed"), list):
            yield node["allowed"]
        for value in node.values():
            yield from _all_allowed_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _all_allowed_values(value)


def test_neurips_implementation_phase_uses_terminal_implementation_states():
    workflow = _load_yaml("workflows/library/neurips_backlog_implementation_phase.yaml")
    execute = _step_by_name(workflow, "ExecuteImplementation")
    materialize = _step_by_name(workflow, "MaterializeImplementationState")
    write_state = _step_by_name(workflow, "WriteImplementationState")
    finalize = _step_by_name(workflow, "FinalizeImplementationPhaseOutputs")
    fix = _step_by_name(workflow, "FixImplementation")

    assert workflow["outputs"]["implementation_state"]["allowed"] == ["COMPLETED", "BLOCKED"]
    assert "output_bundle" not in execute
    assert execute["prompt_consumes"] == [
        "design",
        "plan",
        "execution_report_target",
        "progress_report_target",
    ]
    materialize_script = "\n".join(str(part) for part in materialize["command"])
    assert "implementation_state.json" in materialize_script
    assert "phase_started_at_ns" in materialize_script
    assert "workflows/library/scripts/materialize_neurips_implementation_state.py" in materialize_script
    materialize_fields = {
        field["name"]: field for field in materialize["output_bundle"]["fields"]
    }
    assert materialize_fields["blocker_class"]["allowed"] == [
        "missing_resource",
        "unavailable_hardware",
        "roadmap_conflict",
        "external_dependency_outside_authority",
        "user_decision_required",
        "unrecoverable_after_fix_attempt",
    ]
    assert write_state["expected_outputs"][0]["allowed"] == ["COMPLETED", "BLOCKED"]
    assert finalize["expected_outputs"][0]["allowed"] == ["COMPLETED", "BLOCKED"]
    assert execute["timeout_sec"] == 86400
    assert fix["timeout_sec"] == 86400
    assert "PublishProgressReport" not in _step_names(workflow)


def test_neurips_execute_prompt_treats_partial_progress_as_reviewable_pass():
    prompt = Path(
        "workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md"
    ).read_text(encoding="utf-8")

    assert "Choose exactly one implementation state" not in prompt
    assert "write the execution report" in prompt
    assert "partial" in prompt.lower()
    assert "Remaining Required Plan Tasks" in prompt
    assert "Blocker Class" in prompt


def test_neurips_implementation_phase_materializer_uses_current_pass_evidence():
    workflow = _load_yaml("workflows/library/neurips_backlog_implementation_phase.yaml")
    init = _step_by_name(workflow, "InitializeImplementationPhasePaths")
    init_script = "\n".join(init["command"])
    assert "phase_started_at_ns.txt" in init_script
    assert "implementation_state.json" in init_script
    assert "final_implementation_state.txt" in init_script

    materialize = _step_by_name(workflow, "MaterializeImplementationState")
    materialize_args = materialize["command"]
    assert "${inputs.state_root}/phase_started_at_ns.txt" in materialize_args
    assert "workflows/library/scripts/materialize_neurips_implementation_state.py" in materialize_args
    materialize_script = Path(
        "workflows/library/scripts/materialize_neurips_implementation_state.py"
    ).read_text(encoding="utf-8")
    assert "_is_fresh_report" in materialize_script
    assert "Existing implementation state bundle" not in materialize_script


def test_neurips_selected_item_does_not_emit_waiting_status():
    workflow = _load_yaml("workflows/library/neurips_selected_backlog_item.yaml")

    assert workflow["outputs"]["drain_status"]["allowed"] == ["CONTINUE", "BLOCKED"]
    assert "RecordImplementationWaiting" not in _step_names(workflow)
    for allowed in _all_allowed_values(workflow):
        assert "WAITING" not in allowed


def test_neurips_selected_item_recovers_or_runs_plan_gate_before_implementation():
    workflow = _load_yaml("workflows/library/neurips_selected_backlog_item.yaml")

    materialize = _step_by_name(workflow, "MaterializeSelectedItemInputs")
    materialized_fields = {
        field["name"]: field for field in materialize["output_bundle"]["fields"]
    }
    assert materialized_fields["plan_gate_recovery_bundle_path"]["under"] == "state"
    assert materialized_fields["final_plan_gate_bundle_path"]["under"] == "state"
    assert materialized_fields["plan_gate_state_root"]["under"] == "state"
    assert materialized_fields["plan_gate_recovery_report_target_path"]["under"] == (
        "artifacts/review"
    )

    recover = _step_by_name(workflow, "RecoverPlanGateOutputs")
    recovery_fields = {field["name"]: field for field in recover["expected_outputs"]}
    assert recovery_fields["plan_gate_status"]["allowed"] == ["APPROVED", "MISSING"]

    fresh = _step_by_name(workflow, "RunFreshPlanPhase")
    assert fresh["when"]["compare"]["left"] == {
        "ref": "root.steps.RecoverPlanGateOutputs.artifacts.plan_gate_status"
    }
    assert fresh["when"]["compare"]["op"] == "eq"
    assert fresh["when"]["compare"]["right"] == "MISSING"

    resolve = _step_by_name(workflow, "ValidatePlanGateBundle")
    resolved_fields = {field["name"]: field for field in resolve["expected_outputs"]}
    assert resolved_fields["plan_path"]["under"] == "docs/plans"
    assert resolved_fields["plan_gate_source"]["allowed"] == ["RECOVERED", "FRESH"]
    command_text = "\n".join(str(part) for part in resolve["command"])
    assert "Unexpected plan gate bundle status" in command_text
    assert "final_plan_path.txt" in command_text
    assert "reconciled_selected_item_path.txt" in command_text
    assert "selected_plan_gate_source.txt" in command_text

    rewrite = _step_by_name(workflow, "RewriteSelectedItemPlanPath")
    assert rewrite["when"]["compare"]["left"] == {
        "ref": "root.steps.RecoverPlanGateOutputs.artifacts.plan_gate_status"
    }
    assert rewrite["when"]["compare"]["right"] == "MISSING"


def test_neurips_selected_item_implementation_uses_normalized_plan_gate_output():
    workflow = _load_yaml("workflows/library/neurips_selected_backlog_item.yaml")

    implementation = _step_by_name(workflow, "RunImplementationPhase")
    assert implementation["with"]["plan_path"] == {
        "ref": "root.steps.ValidatePlanGateBundle.artifacts.plan_path"
    }


def test_neurips_selected_item_does_not_block_on_implementation_review_revise():
    workflow = _load_yaml("workflows/library/neurips_selected_backlog_item.yaml")

    assert "RecordImplementationReviewBlocked" not in _step_names(workflow)
    assert "Implementation review did not approve" not in yaml.safe_dump(workflow)


def test_neurips_selected_item_recovers_premature_done_only_after_implementation():
    workflow = _load_yaml("workflows/library/neurips_selected_backlog_item.yaml")

    rewrite = _step_by_name(workflow, "RewriteSelectedItemPlanPath")
    post_impl = _step_by_name(workflow, "ReconcileSelectedItemQueueAfterImplementation")

    assert "--recover-premature-done" not in rewrite["command"]
    assert "--recover-premature-done" in post_impl["command"]


def test_neurips_top_level_drain_does_not_emit_waiting_status():
    workflow = _load_yaml("workflows/examples/neurips_steered_backlog_drain.yaml")

    assert workflow["outputs"]["drain_status"]["allowed"] == [
        "CONTINUE",
        "DONE",
        "BLOCKED",
    ]
    assert workflow["artifacts"]["drain_status"]["allowed"] == [
        "CONTINUE",
        "DONE",
        "BLOCKED",
    ]
    for allowed in _all_allowed_values(workflow):
        assert "WAITING" not in allowed


def test_neurips_top_level_drain_continues_after_selected_item_blocks():
    workflow = _load_yaml("workflows/examples/neurips_steered_backlog_drain.yaml")

    route = _step_by_name(workflow, "RouteItemSelection")
    selected_case = route["match"]["cases"]["SELECTED"]
    output_ref = selected_case["outputs"]["drain_status"]["from"]["ref"]
    assert output_ref == "self.steps.WriteSelectedItemContinue.artifacts.drain_status"

    assert any(step["name"] == "RunSelectedItem" for step in selected_case["steps"])
    write_continue = next(
        step for step in selected_case["steps"]
        if step["name"] == "WriteSelectedItemContinue"
    )
    assert write_continue["set_scalar"] == {
        "artifact": "drain_status",
        "value": "CONTINUE",
    }


def test_scope_boundary_helper_derives_selected_tranche_boundary(tmp_path: Path):
    manifest_path = tmp_path / "state/demo/tranche_manifest.json"
    brief_path = tmp_path / "docs/backlog/generated/demo/t1.md"
    boundary_path = tmp_path / "state/demo/items/t1/scope_boundary.json"
    manifest_path.parent.mkdir(parents=True)
    brief_path.parent.mkdir(parents=True)
    brief_path.write_text(
        "# T1 brief\nImplement the public behavior.\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "project_id": "demo",
                "project_brief_path": "docs/backlog/demo.md",
                "project_roadmap_path": "docs/plans/demo.md",
                "tranches": [
                    {
                        "tranche_id": "T1-public-behavior",
                        "title": "Public behavior",
                        "brief_path": brief_path.relative_to(tmp_path).as_posix(),
                        "completion_gate": "implementation_approved",
                        "status": "pending",
                        "prerequisites": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = write_scope_boundary(
        root=tmp_path,
        tranche_manifest_path=manifest_path.relative_to(tmp_path).as_posix(),
        tranche_brief_path=brief_path.relative_to(tmp_path).as_posix(),
        scope_boundary_path=boundary_path.relative_to(tmp_path).as_posix(),
    )

    assert payload["tranche_id"] == "T1-public-behavior"
    assert payload["completion_gate"] == "implementation_approved"
    assert payload["required_deliverables"]
    assert boundary_path.is_file()


def test_completion_guard_rejects_approved_slice_with_unapproved_deferred_work(
    tmp_path: Path,
):
    boundary = tmp_path / "state/demo/items/t1/scope_boundary.json"
    execution_report = tmp_path / "artifacts/work/demo/execution.md"
    review_report = tmp_path / "artifacts/review/demo/review.md"
    for path in (boundary, execution_report, review_report):
        path.parent.mkdir(parents=True, exist_ok=True)
    boundary.write_text(
        json.dumps(
            {
                "tranche_id": "T1",
                "required_deliverables": ["public solver"],
                "required_evidence": [],
                "authorized_deferred_work": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    execution_report.write_text(
        "Task 3 is done. Exact public solver work remains deferred and blocked.\n",
        encoding="utf-8",
    )
    review_report.write_text(
        "Decision: APPROVE\nBroader exact-runtime blockers remain deferred.\n",
        encoding="utf-8",
    )

    result = check_completion(
        root=tmp_path,
        scope_boundary_path=boundary.relative_to(tmp_path).as_posix(),
        implementation_decision="APPROVE",
        execution_report_path=execution_report.relative_to(tmp_path).as_posix(),
        implementation_review_report_path=review_report.relative_to(tmp_path).as_posix(),
    )

    assert result["completion_status"] == "SCOPE_MISMATCH"
    assert result["recommended_route"] == "escalate_roadmap_revision"


def test_completion_guard_allows_roadmap_authorized_deferral(tmp_path: Path):
    boundary = tmp_path / "state/demo/items/t1/scope_boundary.json"
    execution_report = tmp_path / "artifacts/work/demo/execution.md"
    review_report = tmp_path / "artifacts/review/demo/review.md"
    for path in (boundary, execution_report, review_report):
        path.parent.mkdir(parents=True, exist_ok=True)
    boundary.write_text(
        json.dumps(
            {
                "tranche_id": "T1",
                "required_deliverables": ["public solver"],
                "required_evidence": [],
                "authorized_deferred_work": [
                    {
                        "work": "CUDA promotion",
                        "authority": "roadmap",
                        "handoff": "T1A",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    execution_report.write_text(
        "CPU work complete. CUDA promotion remains deferred to T1A.\n",
        encoding="utf-8",
    )
    review_report.write_text("Decision: APPROVE\n", encoding="utf-8")

    result = check_completion(
        root=tmp_path,
        scope_boundary_path=boundary.relative_to(tmp_path).as_posix(),
        implementation_decision="APPROVE",
        execution_report_path=execution_report.relative_to(tmp_path).as_posix(),
        implementation_review_report_path=review_report.relative_to(tmp_path).as_posix(),
    )

    assert result["completion_status"] == "COMPLETE"
    assert result["recommended_route"] == "complete"
