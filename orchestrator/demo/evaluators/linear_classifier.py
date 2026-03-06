"""Hidden evaluator for the linear-classifier workflow demo seed."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_oracle_module() -> Any:
    module_path = (
        _repo_root()
        / "examples"
        / "demo_task_linear_classifier_port"
        / "src_py"
        / "linear_classifier.py"
    )
    spec = importlib.util.spec_from_file_location("demo_linear_classifier_oracle", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load oracle module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _soft_quality_report(workspace: Path) -> dict[str, Any]:
    lib_rs = workspace / "rust" / "src" / "lib.rs"
    findings: list[str] = []
    score = 1.0

    if not lib_rs.is_file():
        return {
            "score": 0.0,
            "findings": ["missing rust/src/lib.rs"],
        }

    source = lib_rs.read_text()
    if "unimplemented!" in source:
        findings.append("contains unimplemented stubs")
        score -= 0.7
    if "todo!" in source:
        findings.append("contains todo stubs")
        score -= 0.3
    if source.count("pub fn ") < 5:
        findings.append("very small public API surface for this task")
        score -= 0.1

    return {
        "score": max(0.0, round(score, 3)),
        "findings": findings,
    }


def _rust_float(value: float) -> str:
    if value == float("inf") or value == float("-inf") or value != value:
        raise ValueError("Non-finite float cannot be embedded in Rust literal")
    return f"{value:.17g}_f64"


def _rust_vec_f64(values: list[float]) -> str:
    return "vec![" + ", ".join(_rust_float(v) for v in values) + "]"


def _rust_matrix_f64(rows: list[list[float]]) -> str:
    return "vec![" + ", ".join(_rust_vec_f64(row) for row in rows) + "]"


def _rust_vec_usize(values: list[int]) -> str:
    return "vec![" + ", ".join(f"{v}usize" for v in values) + "]"


def _rust_matrix_usize(rows: list[list[int]]) -> str:
    return "vec![" + ", ".join(_rust_vec_usize(row) for row in rows) + "]"


def _build_hidden_cases() -> dict[str, Any]:
    oracle = _load_oracle_module()
    model = oracle.LinearClassifier(
        weights=((1.5, -0.5), (-0.5, 1.0), (0.2, 0.3)),
        bias=(0.1, -0.2, 0.0),
    )
    features = [
        [2.0, 0.0],
        [0.0, 2.0],
        [1.0, 1.0],
        [1.5, 1.5],
    ]
    probabilities = oracle.predict_proba_batch(model, features)
    targets = [0, 1, 1, 0]
    confusion = oracle.confusion_matrix(probabilities, targets)
    report = oracle.per_class_metrics(confusion)
    macro_score = oracle.macro_f1(report)
    loss = oracle.cross_entropy_loss(probabilities, targets)
    ece = oracle.expected_calibration_error(probabilities, targets, num_bins=4)
    top_k = oracle.predict_top_k(probabilities, 2)
    labels = oracle.predict_labels(probabilities)

    tie_probabilities = [
        [0.50, 0.50, 0.00],
        [0.20, 0.20, 0.60],
    ]
    tie_labels = oracle.predict_labels(tie_probabilities)
    tie_top_k = oracle.predict_top_k(tie_probabilities, 2)

    return {
        "model_weights": [list(row) for row in model.weights],
        "model_bias": list(model.bias),
        "features": features,
        "probabilities": probabilities,
        "targets": targets,
        "labels": labels,
        "top_k": top_k,
        "confusion": confusion,
        "report": [
            {
                "precision": item["precision"],
                "recall": item["recall"],
                "f1": item["f1"],
                "support": int(item["support"]),
            }
            for item in report
        ],
        "macro_f1": macro_score,
        "cross_entropy_loss": loss,
        "ece": ece,
        "tie_probabilities": tie_probabilities,
        "tie_labels": tie_labels,
        "tie_top_k": tie_top_k,
    }


def _hidden_test_source(workspace: Path) -> str:
    case = _build_hidden_cases()
    return f'''
use linear_classifier::{{
    confusion_matrix, cross_entropy_loss, expected_calibration_error, macro_f1, new_linear_classifier,
    per_class_metrics, predict_batch, predict_proba_batch, predict_top_k,
}};

fn approx_eq(left: f64, right: f64) {{
    let delta = (left - right).abs();
    assert!(delta < 1e-10, "left={{left}}, right={{right}}, delta={{delta}}");
}}

fn approx_vec(left: &[f64], right: &[f64]) {{
    assert_eq!(left.len(), right.len());
    for (l, r) in left.iter().zip(right.iter()) {{
        approx_eq(*l, *r);
    }}
}}

#[test]
fn hidden_prediction_outputs_match_python_reference() {{
    let model = new_linear_classifier(
        {_rust_matrix_f64(case["model_weights"])},
        {_rust_vec_f64(case["model_bias"])},
    ).unwrap();
    let features = {_rust_matrix_f64(case["features"])};
    let probabilities = predict_proba_batch(&model, &features).unwrap();
    let expected = {_rust_matrix_f64(case["probabilities"])};
    assert_eq!(probabilities.len(), expected.len());
    for (row, expected_row) in probabilities.iter().zip(expected.iter()) {{
        approx_vec(row, expected_row);
    }}
    let labels = predict_batch(&probabilities).unwrap();
    assert_eq!(labels, {_rust_vec_usize(case["labels"])});
    let top_k = predict_top_k(&probabilities, 2).unwrap();
    assert_eq!(top_k, {_rust_matrix_usize(case["top_k"])});
}}

#[test]
fn hidden_loss_metrics_and_calibration_match_python_reference() {{
    let probabilities = {_rust_matrix_f64(case["probabilities"])};
    let targets = {_rust_vec_usize(case["targets"])};
    let loss = cross_entropy_loss(&probabilities, &targets).unwrap();
    approx_eq(loss, {_rust_float(case["cross_entropy_loss"])});

    let confusion = confusion_matrix(&probabilities, &targets).unwrap();
    assert_eq!(confusion, {_rust_matrix_usize(case["confusion"])});

    let report = per_class_metrics(&confusion).unwrap();
    assert_eq!(report.len(), {len(case["report"])}usize);
    let expected_precision = {_rust_vec_f64([item['precision'] for item in case['report']])};
    let expected_recall = {_rust_vec_f64([item['recall'] for item in case['report']])};
    let expected_f1 = {_rust_vec_f64([item['f1'] for item in case['report']])};
    let expected_support = {_rust_vec_usize([item['support'] for item in case['report']])};
    for (index, item) in report.iter().enumerate() {{
        approx_eq(item.precision, expected_precision[index]);
        approx_eq(item.recall, expected_recall[index]);
        approx_eq(item.f1, expected_f1[index]);
        assert_eq!(item.support, expected_support[index]);
    }}

    let macro_score = macro_f1(&report).unwrap();
    approx_eq(macro_score, {_rust_float(case["macro_f1"])});

    let ece = expected_calibration_error(&probabilities, &targets, 4).unwrap();
    approx_eq(ece, {_rust_float(case["ece"])});
}}

#[test]
fn hidden_tie_breaking_and_error_conditions_are_correct() {{
    let tie_probabilities = {_rust_matrix_f64(case["tie_probabilities"])};
    let tie_labels = predict_batch(&tie_probabilities).unwrap();
    assert_eq!(tie_labels, {_rust_vec_usize(case["tie_labels"])});
    let tie_top_k = predict_top_k(&tie_probabilities, 2).unwrap();
    assert_eq!(tie_top_k, {_rust_matrix_usize(case["tie_top_k"])});

    assert!(predict_top_k(&tie_probabilities, 0).is_err());
    assert!(expected_calibration_error(&tie_probabilities, &[0usize, 2usize], 0).is_err());
    assert!(cross_entropy_loss(&vec![vec![1.0, 0.0], vec![0.0, 1.0]], &[0usize]).is_err());
    assert!(new_linear_classifier(vec![], vec![]).is_err());
    assert!(new_linear_classifier(vec![vec![1.0, 2.0], vec![1.0]], vec![0.0, 0.0]).is_err());
}}
'''


def _cargo_toml(workspace: Path) -> str:
    crate_path = (workspace / "rust").resolve().as_posix()
    return f'''
[package]
name = "linear_classifier_hidden_eval"
version = "0.1.0"
edition = "2021"

[dependencies]
linear_classifier = {{ path = "{crate_path}" }}
'''.lstrip()


def evaluate_workspace(workspace: Path | str) -> dict[str, Any]:
    workspace = Path(workspace).resolve()
    rust_dir = workspace / "rust"
    lib_rs = rust_dir / "src" / "lib.rs"
    cargo_toml = rust_dir / "Cargo.toml"

    if not workspace.is_dir():
        return {
            "verdict": "FAIL",
            "failure_categories": ["invalid_workspace"],
            "summary": {"hidden_tests_passed": False, "reason": "workspace_not_found"},
            "soft_quality": {"score": 0.0, "findings": ["workspace not found"]},
        }
    if not rust_dir.is_dir() or not cargo_toml.is_file() or not lib_rs.is_file():
        return {
            "verdict": "FAIL",
            "failure_categories": ["missing_rust_crate"],
            "summary": {"hidden_tests_passed": False, "reason": "rust_crate_layout_missing"},
            "soft_quality": {"score": 0.0, "findings": ["rust crate layout missing"]},
        }
    if shutil.which("cargo") is None:
        return {
            "verdict": "FAIL",
            "failure_categories": ["missing_toolchain"],
            "summary": {"hidden_tests_passed": False, "reason": "cargo_not_found"},
            "soft_quality": _soft_quality_report(workspace),
        }

    try:
        with tempfile.TemporaryDirectory(prefix="linear-classifier-eval-") as tmp_dir:
            harness_root = Path(tmp_dir)
            tests_dir = harness_root / "tests"
            tests_dir.mkdir(parents=True)
            (harness_root / "src").mkdir()
            (harness_root / "src" / "lib.rs").write_text("\n")
            (harness_root / "Cargo.toml").write_text(_cargo_toml(workspace))
            (tests_dir / "hidden_acceptance.rs").write_text(_hidden_test_source(workspace))

            result = subprocess.run(
                ["cargo", "test", "--quiet"],
                cwd=harness_root,
                capture_output=True,
                text=True,
            )
    except Exception as exc:  # pragma: no cover - defensive guard
        return {
            "verdict": "FAIL",
            "failure_categories": ["evaluator_internal_error"],
            "summary": {
                "hidden_tests_passed": False,
                "reason": "exception_during_evaluation",
                "exception": str(exc),
            },
            "soft_quality": _soft_quality_report(workspace),
        }

    verdict = "PASS" if result.returncode == 0 else "FAIL"
    failures = [] if verdict == "PASS" else ["hidden_acceptance_failed"]
    return {
        "verdict": verdict,
        "failure_categories": failures,
        "summary": {
            "hidden_tests_passed": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
        "soft_quality": _soft_quality_report(workspace),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate a linear-classifier demo workspace.")
    parser.add_argument("workspace", help="Path to the candidate workspace.")
    args = parser.parse_args(argv)

    result = evaluate_workspace(Path(args.workspace))
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
