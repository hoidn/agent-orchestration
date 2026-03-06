from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / "workflows" / "examples" / "generic_task_plan_execute_review_loop.yaml"
PROMPTS = ROOT / "prompts" / "workflows" / "generic_task_loop"


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _step(workflow: dict, name: str) -> dict:
    for step in workflow["steps"]:
        if step["name"] == name:
            return step
    raise AssertionError(f"missing step {name}")


def test_check_strategy_stays_in_plan_loop_and_check_plan_is_mutable_in_impl_loop():
    workflow = _load_workflow()

    draft = _step(workflow, "DraftPlan")
    revise = _step(workflow, "RevisePlan")
    execute = _step(workflow, "ExecutePlan")
    fix = _step(workflow, "FixIssues")
    run_checks = _step(workflow, "RunChecks")

    assert {pub["artifact"] for pub in draft["publishes"]} == {"plan", "check_strategy"}
    assert {pub["artifact"] for pub in revise["publishes"]} == {"plan", "check_strategy"}
    assert {pub["artifact"] for pub in execute["publishes"]} == {"execution_report", "check_plan"}
    assert {pub["artifact"] for pub in fix["publishes"]} == {"execution_report", "check_plan"}

    run_checks_check_plan = next(c for c in run_checks["consumes"] if c["artifact"] == "check_plan")
    assert run_checks_check_plan["producers"] == ["ExecutePlan", "FixIssues"]


def test_run_checks_script_records_invalid_or_missing_checks_in_results_instead_of_aborting():
    workflow = _load_workflow()
    run_checks = _step(workflow, "RunChecks")
    script = run_checks["command"][2]

    assert "FileNotFoundError" in script
    assert "invalid_check_plan" in script
    assert "invalid_check_definition" in script
    assert "missing_executable" in script
    assert "raise SystemExit(f\"Check {name} has invalid argv\")" not in script


def test_prompts_and_artifact_contracts_use_check_strategy_for_plan_loop_and_check_plan_for_runtime():
    draft = (PROMPTS / "draft_plan.md").read_text(encoding="utf-8")
    review_plan = (PROMPTS / "review_plan.md").read_text(encoding="utf-8")
    revise = (PROMPTS / "revise_plan.md").read_text(encoding="utf-8")
    execute = (PROMPTS / "execute_plan.md").read_text(encoding="utf-8")
    fix = (PROMPTS / "fix_issues.md").read_text(encoding="utf-8")
    contracts = (ROOT / "docs" / "plans" / "templates" / "artifact_contracts.md").read_text(encoding="utf-8")

    assert "Produce a `check_strategy` artifact" in draft
    assert "current plan and check strategy" in review_plan
    assert "Revise the current plan and check strategy" in revise
    assert "Produce an updated `check_plan` artifact" in execute
    assert "Produce an updated `check_plan` artifact" in fix
    assert "### `check_strategy`" in contracts
