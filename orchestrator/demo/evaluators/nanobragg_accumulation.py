"""Hidden evaluator for the nanoBragg accumulation workflow demo seed."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import torch


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _fixture_root() -> Path:
    return _repo_root() / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_accumulation"


def load_hidden_cases() -> list[dict[str, Any]]:
    payload = json.loads((_fixture_root() / "cases.json").read_text())
    return list(payload["cases"])


def _soft_quality_report(workspace: Path) -> dict[str, Any]:
    module_path = workspace / "torch_port" / "accumulation.py"
    if not module_path.is_file():
        return {"score": 0.0, "findings": ["missing torch_port/accumulation.py"]}

    source = module_path.read_text()
    findings: list[str] = []
    score = 1.0

    if "NotImplementedError" in source:
        findings.append("contains NotImplementedError stubs")
        score -= 0.6
    if "TODO" in source or "todo" in source:
        findings.append("contains todo markers")
        score -= 0.2
    if "accumulate_detector_image" not in source:
        findings.append("missing accumulate_detector_image entrypoint")
        score -= 0.4

    return {"score": max(0.0, round(score, 3)), "findings": findings}


def load_workspace_module(workspace: Path) -> ModuleType:
    workspace = workspace.resolve()
    package_root = workspace / "torch_port"
    module_path = package_root / "accumulation.py"
    if not module_path.is_file():
        raise FileNotFoundError(module_path)

    package_name = f"demo_nanobragg_candidate_{abs(hash(str(workspace)))}"
    previous_setting = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        package_spec = importlib.util.spec_from_file_location(
            package_name,
            package_root / "__init__.py",
            submodule_search_locations=[str(package_root)],
        )
        if package_spec is None or package_spec.loader is None:
            raise RuntimeError(f"Unable to load package spec from {package_root}")
        package_module = importlib.util.module_from_spec(package_spec)
        sys.modules[package_name] = package_module
        package_spec.loader.exec_module(package_module)

        module_name = f"{package_name}.accumulation"
        module_spec = importlib.util.spec_from_file_location(module_name, module_path)
        if module_spec is None or module_spec.loader is None:
            raise RuntimeError(f"Unable to load candidate module from {module_path}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_setting
    return module


def _evaluate_case(module: ModuleType, workspace: Path, case: dict[str, Any]) -> None:
    fixture_path = workspace / case["input_fixture_relpath"]
    fixture = json.loads(fixture_path.read_text())
    actual = module.accumulate_detector_image(fixture)
    expected = torch.load(_fixture_root() / case["expected_tensor_relpath"], map_location="cpu")
    if not isinstance(actual, torch.Tensor):
        actual = torch.as_tensor(actual)
    torch.testing.assert_close(actual, expected, rtol=case["rtol"], atol=case["atol"])


def evaluate_workspace(workspace: Path | str) -> dict[str, Any]:
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        return {
            "verdict": "FAIL",
            "failure_categories": ["invalid_workspace"],
            "summary": {"hidden_tests_passed": False, "reason": "workspace_not_found"},
            "soft_quality": {"score": 0.0, "findings": ["workspace not found"]},
        }

    module_path = workspace / "torch_port" / "accumulation.py"
    if not module_path.is_file():
        return {
            "verdict": "FAIL",
            "failure_categories": ["missing_target_module"],
            "summary": {"hidden_tests_passed": False, "reason": "target_module_missing"},
            "soft_quality": _soft_quality_report(workspace),
        }

    try:
        module = load_workspace_module(workspace)
    except Exception as exc:
        return {
            "verdict": "FAIL",
            "failure_categories": ["missing_target_module"],
            "summary": {"hidden_tests_passed": False, "reason": f"module_import_failed: {exc}"},
            "soft_quality": _soft_quality_report(workspace),
        }

    executed_cases: list[str] = []
    case_failures: list[str] = []
    for case in load_hidden_cases():
        fixture_path = workspace / case["input_fixture_relpath"]
        if not fixture_path.is_file():
            continue
        executed_cases.append(case["case_id"])
        try:
            _evaluate_case(module, workspace, case)
        except Exception as exc:
            case_failures.append(f"{case['case_id']}: {exc}")

    if not executed_cases:
        return {
            "verdict": "FAIL",
            "failure_categories": ["hidden_acceptance_failed"],
            "summary": {"hidden_tests_passed": False, "reason": "no_hidden_cases_executed"},
            "soft_quality": _soft_quality_report(workspace),
        }

    hidden_tests_passed = not case_failures
    return {
        "verdict": "PASS" if hidden_tests_passed else "FAIL",
        "failure_categories": [] if hidden_tests_passed else ["hidden_acceptance_failed"],
        "summary": {
            "hidden_tests_passed": hidden_tests_passed,
            "executed_cases": executed_cases,
            "case_failures": case_failures,
        },
        "soft_quality": _soft_quality_report(workspace),
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(json.dumps({"error": "usage: evaluate_nanobragg_accumulation.py <workspace>"}))
        return 2
    result = evaluate_workspace(argv[0])
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


__all__ = ["evaluate_workspace", "load_hidden_cases", "load_workspace_module", "main"]
