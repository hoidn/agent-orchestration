"""Hidden evaluator for the nanoBragg entrypoint workflow demo seed."""

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
    return _repo_root() / "orchestrator" / "demo" / "evaluators" / "fixtures" / "nanobragg_entrypoint"


def load_hidden_cases() -> list[dict[str, Any]]:
    payload = json.loads((_fixture_root() / "cases.json").read_text())
    return list(payload["cases"])


def _resolve_fixture_path(workspace: Path, case: dict[str, Any]) -> Path:
    relpath = case.get("input_fixture_relpath") or case.get("fixture_path")
    origin = case.get("input_fixture_origin", "workspace")
    if origin == "evaluator_fixture_root":
        return _fixture_root() / relpath
    return workspace / relpath


def _score_fraction_close(actual: torch.Tensor, expected: torch.Tensor, *, rtol: float, atol: float) -> float:
    actual64 = actual.to(dtype=torch.float64)
    expected64 = expected.to(dtype=torch.float64)
    tolerance = atol + rtol * expected64.abs()
    within = (actual64 - expected64).abs() <= tolerance
    return float(within.to(dtype=torch.float32).mean().item())


def _probe_score(actual: torch.Tensor, expected: torch.Tensor, probe_sites: list[list[int]], *, rtol: float, atol: float) -> float:
    if not probe_sites:
        return 0.0
    actual_values = torch.stack([actual[row, col] for row, col in probe_sites])
    expected_values = torch.stack([expected[row, col] for row, col in probe_sites])
    return _score_fraction_close(actual_values, expected_values, rtol=rtol, atol=atol)


def _case_score(actual: torch.Tensor, expected: torch.Tensor, case: dict[str, Any]) -> dict[str, Any]:
    shape_score = 1.0 if list(actual.shape) == list(expected.shape) else 0.0
    dtype_score = 1.0 if actual.dtype == expected.dtype else (0.7 if actual.is_floating_point() and expected.is_floating_point() else 0.0)
    finite_score = float(torch.isfinite(actual).to(dtype=torch.float32).all().item()) if actual.numel() else 0.0

    if shape_score == 0.0:
        return {
            "case_score": 0.1 * dtype_score + 0.1 * finite_score,
            "shape_score": shape_score,
            "dtype_score": dtype_score,
            "finite_score": finite_score,
            "probe_score": 0.0,
            "tensor_score": 0.0,
        }

    probe_score = _probe_score(actual, expected, case.get("probe_sites", []), rtol=1e-6, atol=1e-8)
    tensor_score = _score_fraction_close(actual, expected, rtol=1e-6, atol=1e-8)
    case_score = (
        0.2 * shape_score
        + 0.1 * dtype_score
        + 0.1 * finite_score
        + 0.3 * probe_score
        + 0.3 * tensor_score
    )
    return {
        "case_score": round(case_score, 6),
        "shape_score": shape_score,
        "dtype_score": dtype_score,
        "finite_score": finite_score,
        "probe_score": round(probe_score, 6),
        "tensor_score": round(tensor_score, 6),
    }


def load_workspace_module(workspace: Path) -> ModuleType:
    workspace = workspace.resolve()
    package_root = workspace / "torch_port"
    module_path = package_root / "entrypoint.py"
    if not module_path.is_file():
        raise FileNotFoundError(module_path)

    package_name = f"demo_nanobragg_entrypoint_{abs(hash(str(workspace)))}"
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

        module_name = f"{package_name}.entrypoint"
        module_spec = importlib.util.spec_from_file_location(module_name, module_path)
        if module_spec is None or module_spec.loader is None:
            raise RuntimeError(f"Unable to load candidate module from {module_path}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_setting
    return module


def _soft_quality_report(workspace: Path) -> dict[str, Any]:
    module_path = workspace / "torch_port" / "entrypoint.py"
    if not module_path.is_file():
        return {"score": 0.0, "findings": ["missing torch_port/entrypoint.py"]}

    source = module_path.read_text()
    findings: list[str] = []
    score = 1.0
    if "NotImplementedError" in source:
        findings.append("contains NotImplementedError stubs")
        score -= 0.6
    if "TODO" in source or "todo" in source:
        findings.append("contains todo markers")
        score -= 0.2
    if "nanobragg_run" not in source:
        findings.append("missing nanobragg_run entrypoint")
        score -= 0.4
    return {"score": max(0.0, round(score, 3)), "findings": findings}


def _evaluate_case(module: ModuleType, workspace: Path, case: dict[str, Any]) -> None:
    fixture = json.loads(_resolve_fixture_path(workspace, case).read_text())
    actual = module.nanobragg_run(fixture)
    expected = torch.load(_repo_root() / case["expected_output_path"], map_location="cpu")
    if not isinstance(actual, torch.Tensor):
        actual = torch.as_tensor(actual)
    score = _case_score(actual, expected, case)
    details = {
        "case_id": case["case_id"],
        "reference_method": case.get("reference_method"),
        "reference_source": case.get("reference_source"),
        "probe_sites": case.get("probe_sites", []),
        **score,
    }
    return actual, expected, details


def evaluate_workspace(workspace: Path | str) -> dict[str, Any]:
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        return {
            "verdict": "FAIL",
            "failure_categories": ["invalid_workspace"],
            "summary": {"hidden_tests_passed": False, "reason": "workspace_not_found"},
            "soft_quality": {"score": 0.0, "findings": ["workspace not found"]},
        }

    module_path = workspace / "torch_port" / "entrypoint.py"
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
    case_details: list[dict[str, Any]] = []
    total_score = 0.0
    for case in load_hidden_cases():
        fixture_path = _resolve_fixture_path(workspace, case)
        if not fixture_path.is_file():
            continue
        executed_cases.append(case["case_id"])
        try:
            _actual, _expected, details = _evaluate_case(module, workspace, case)
            total_score += details["case_score"]
            case_details.append(details)
        except Exception as exc:
            case_details.append(
                {
                    "case_id": case["case_id"],
                    "reference_method": case.get("reference_method"),
                    "reference_source": case.get("reference_source"),
                    "error": str(exc),
                    "case_score": 0.0,
                }
            )

    if not executed_cases:
        return {
            "verdict": "FAIL",
            "failure_categories": ["hidden_acceptance_failed"],
            "summary": {
                "hidden_tests_passed": False,
                "reason": "no_hidden_cases_executed",
                "score": 0.0,
                "max_score": 0.0,
            },
            "soft_quality": _soft_quality_report(workspace),
        }

    max_score = float(len(executed_cases))
    score = round(total_score / max_score, 6) if max_score else 0.0
    hidden_tests_passed = score >= 0.95
    return {
        "verdict": "PASS" if hidden_tests_passed else "FAIL",
        "failure_categories": [] if hidden_tests_passed else ["hidden_acceptance_failed"],
        "summary": {
            "hidden_tests_passed": hidden_tests_passed,
            "executed_cases": executed_cases,
            "case_details": case_details,
            "score": score,
            "max_score": 1.0,
        },
        "soft_quality": _soft_quality_report(workspace),
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(json.dumps({"error": "usage: evaluate_nanobragg_entrypoint.py <workspace>"}))
        return 2
    result = evaluate_workspace(argv[0])
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


__all__ = ["evaluate_workspace", "load_hidden_cases", "load_workspace_module", "main"]
