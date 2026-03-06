from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

# Expected failure categories for this evaluator contract:
# - invalid_workspace
# - missing_target_module
# - hidden_acceptance_failed


def _write_workspace(tmp_path: Path, module_source: str | None) -> Path:
    workspace = tmp_path / "workspace"
    torch_port = workspace / "torch_port"
    fixtures = workspace / "fixtures" / "visible"
    torch_port.mkdir(parents=True)
    fixtures.mkdir(parents=True)

    (workspace / "torch_port" / "__init__.py").write_text("")
    (fixtures / "case_small.json").write_text(
        json.dumps(
            {
                "case_id": "case_small",
                "detector": {"spixels": 2, "fpixels": 3},
                "expected": {"shape": [2, 3]},
            }
        )
    )

    if module_source is not None:
        (torch_port / "accumulation.py").write_text(module_source)

    return workspace


def _load_evaluator_module():
    return importlib.import_module("orchestrator.demo.evaluators.nanobragg_accumulation")


def test_evaluator_module_exists_and_returns_contract_shape(tmp_path: Path):
    module = _load_evaluator_module()
    workspace = _write_workspace(
        tmp_path,
        """
from __future__ import annotations
import torch

def load_visible_fixture(path):
    return {"expected": {"shape": [2, 3]}}

def accumulate_detector_image(fixture):
    return torch.ones((2, 3), dtype=torch.float64)
""",
    )

    result = module.evaluate_workspace(workspace)

    assert set(result) == {"verdict", "failure_categories", "summary", "soft_quality"}
    assert "hidden_tests_passed" in result["summary"]
    assert "score" in result["soft_quality"]


def test_evaluator_fails_when_target_module_is_missing(tmp_path: Path):
    module = _load_evaluator_module()
    workspace = _write_workspace(tmp_path, None)

    result = module.evaluate_workspace(workspace)

    assert result["verdict"] == "FAIL"
    assert "missing_target_module" in result["failure_categories"]


def test_evaluator_fails_on_wrong_tensor_result(tmp_path: Path):
    module = _load_evaluator_module()
    workspace = _write_workspace(
        tmp_path,
        """
from __future__ import annotations
import torch

def load_visible_fixture(path):
    return {"expected": {"shape": [2, 3]}}

def accumulate_detector_image(fixture):
    return torch.zeros((2, 3), dtype=torch.float64)
""",
    )

    result = module.evaluate_workspace(workspace)

    assert result["verdict"] == "FAIL"
    assert "hidden_acceptance_failed" in result["failure_categories"]


def test_evaluator_passes_on_expected_tensor_result(tmp_path: Path):
    module = _load_evaluator_module()
    workspace = _write_workspace(
        tmp_path,
        """
from __future__ import annotations
import torch

def load_visible_fixture(path):
    return {"expected": {"shape": [2, 3]}}

def accumulate_detector_image(fixture):
    return torch.full((2, 3), 1.25, dtype=torch.float64)
""",
    )

    result = module.evaluate_workspace(workspace)

    assert result["verdict"] == "PASS"
    assert result["failure_categories"] == []
    assert result["summary"]["hidden_tests_passed"] is True
