from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = (
    ROOT
    / "examples"
    / "demo_task_nanobragg_accumulation_port"
    / "docs"
    / "tasks"
    / "nanobragg_accumulation_contract.md"
)
TASK = (
    ROOT
    / "examples"
    / "demo_task_nanobragg_accumulation_port"
    / "docs"
    / "tasks"
    / "port_nanobragg_accumulation_to_pytorch.md"
)
VISIBLE_README = (
    ROOT / "examples" / "demo_task_nanobragg_accumulation_port" / "fixtures" / "visible" / "README.md"
)
SRC_README = ROOT / "examples" / "demo_task_nanobragg_accumulation_port" / "src_c" / "README.md"
EVAL_README = ROOT / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_accumulation" / "README.md"
CASES = ROOT / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_accumulation" / "cases.json"
REVIEW_PLAN_PROMPT = ROOT / "prompts" / "workflows" / "generic_task_loop" / "review_plan.md"
REVIEW_IMPL_PROMPT = ROOT / "prompts" / "workflows" / "generic_task_loop" / "review_implementation.md"
HANDOFF = ROOT / "docs" / "plans" / "2026-03-05-workflow-demo-session-handoff.md"
DESIGN = ROOT / "docs" / "plans" / "2026-03-05-workflow-demo-design.md"


def test_nanobragg_contract_and_evaluator_docs_share_the_same_scoped_target():
    contract_text = CONTRACT.read_text(encoding="utf-8").lower()
    task_text = TASK.read_text(encoding="utf-8").lower()
    visible_text = VISIBLE_README.read_text(encoding="utf-8").lower()
    src_text = SRC_README.read_text(encoding="utf-8").lower()
    eval_text = EVAL_README.read_text(encoding="utf-8").lower()
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]

    assert "reference harness" in contract_text
    assert "nanobragg_accumulation_contract.md" in task_text
    assert "nanobragg_accumulation_contract.md" in visible_text
    assert "nanobragg_accumulation_contract.md" in src_text
    assert "nanobragg_accumulation_contract.md" in eval_text
    assert "scattering vectors" in contract_text
    assert "excluded math" in contract_text
    assert all(case["reference_method"] == "offline_reference_harness" for case in cases)


def test_workflow_review_docs_require_contract_scoped_judgment():
    review_plan_text = REVIEW_PLAN_PROMPT.read_text(encoding="utf-8").lower()
    review_impl_text = REVIEW_IMPL_PROMPT.read_text(encoding="utf-8").lower()
    handoff_text = HANDOFF.read_text(encoding="utf-8").lower()
    design_text = DESIGN.read_text(encoding="utf-8").lower()

    assert "scoped contract" in review_plan_text
    assert "scoped contract" in review_impl_text
    assert "out-of-contract" in review_impl_text
    assert "scoped contract" in handoff_text
    assert "scoped contract" in design_text
