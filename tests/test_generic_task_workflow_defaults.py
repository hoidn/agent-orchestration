from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "examples" / "generic_task_plan_execute_review_loop.yaml"


def test_generic_task_workflow_uses_extended_revision_cycle_defaults():
    payload = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    assert payload["context"]["max_plan_cycles"] == "4"
    assert payload["context"]["max_impl_cycles"] == "6"
