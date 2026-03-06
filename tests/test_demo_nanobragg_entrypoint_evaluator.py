from __future__ import annotations

import importlib
import json
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parent.parent


def _write_workspace(tmp_path: Path, module_source: str | None) -> Path:
    workspace = tmp_path / "workspace"
    torch_port = workspace / "torch_port"
    fixtures = workspace / "fixtures" / "visible"
    torch_port.mkdir(parents=True)
    fixtures.mkdir(parents=True)

    (torch_port / "__init__.py").write_text("")
    case_basic = json.loads(
        (
            ROOT
            / "examples"
            / "demo_task_nanobragg_entrypoint_port"
            / "fixtures"
            / "visible"
            / "case_basic.json"
        ).read_text()
    )
    (fixtures / "case_basic.json").write_text(json.dumps(case_basic))

    if module_source is not None:
        (torch_port / "entrypoint.py").write_text(module_source)

    return workspace


def _load_module():
    return importlib.import_module("orchestrator.demo.evaluators.nanobragg_entrypoint")


def test_entrypoint_evaluator_contract_shape(tmp_path: Path):
    module = _load_module()
    workspace = _write_workspace(
        tmp_path,
        """
from __future__ import annotations
import torch

def nanobragg_run(fixture):
    return torch.zeros((4, 4), dtype=torch.float32)
""",
    )

    result = module.evaluate_workspace(workspace)
    assert set(result) == {"verdict", "failure_categories", "summary", "soft_quality"}
    assert "hidden_tests_passed" in result["summary"]
    assert "score" in result["summary"]
    assert "score" in result["soft_quality"]


def test_entrypoint_evaluator_fails_when_target_module_missing(tmp_path: Path):
    module = _load_module()
    workspace = _write_workspace(tmp_path, None)
    result = module.evaluate_workspace(workspace)
    assert result["verdict"] == "FAIL"
    assert "missing_target_module" in result["failure_categories"]


def test_entrypoint_evaluator_passes_when_expected_tensor_matches(tmp_path: Path):
    module = _load_module()
    expected = torch.load(
        ROOT
        / "orchestrator"
        / "demo"
        / "evaluators"
        / "fixtures"
        / "nanobragg_entrypoint"
        / "expected_case_basic.pt",
        map_location="cpu",
    )
    workspace = _write_workspace(
        tmp_path,
        f"""
from __future__ import annotations
import torch

def nanobragg_run(fixture):
    return torch.tensor({expected.tolist()}, dtype=torch.float32)
""",
    )
    result = module.evaluate_workspace(workspace)
    assert result["verdict"] == "PASS"
    assert result["failure_categories"] == []
    assert result["summary"]["score"] == 1.0
