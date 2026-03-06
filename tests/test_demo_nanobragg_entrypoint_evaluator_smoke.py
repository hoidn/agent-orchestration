from __future__ import annotations

from pathlib import Path

from orchestrator.demo.evaluators.nanobragg_entrypoint import evaluate_workspace


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_nanobragg_entrypoint_port"


def test_entrypoint_seed_current_stub_fails_hidden_evaluator():
    result = evaluate_workspace(SEED)

    assert result["verdict"] == "FAIL"
    assert "hidden_acceptance_failed" in result["failure_categories"]
    assert result["summary"]["executed_cases"]
    assert 0.0 <= result["summary"]["score"] < 0.95
