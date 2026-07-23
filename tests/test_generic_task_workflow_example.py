from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts" / "workflows" / "generic_task_loop"


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


def test_prompts_forbid_self_generated_numerical_oracles():
    review_plan = (PROMPTS / "review_plan.md").read_text(encoding="utf-8")
    execute = (PROMPTS / "execute_plan.md").read_text(encoding="utf-8")
    review_implementation = (PROMPTS / "review_implementation.md").read_text(encoding="utf-8")

    required_phrase = "candidate implementation"
    provenance_phrase = "documented external provenance"

    assert required_phrase in review_plan
    assert provenance_phrase in review_plan
    assert required_phrase in execute
    assert provenance_phrase in execute
    assert required_phrase in review_implementation
    assert provenance_phrase in review_implementation
