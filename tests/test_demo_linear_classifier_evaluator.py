from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

from orchestrator.demo.evaluators.linear_classifier import evaluate_workspace


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_linear_classifier_port"


PASSING_LIB_RS = r'''
use std::error::Error;
use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub struct LinearClassifier {
    pub weights: Vec<Vec<f64>>,
    pub bias: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ClassMetrics {
    pub precision: f64,
    pub recall: f64,
    pub f1: f64,
    pub support: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ClassifierError {
    EmptyWeights,
    EmptyWeightRow,
    RaggedWeights,
    BiasLengthMismatch,
    EmptyFeatures,
    FeatureWidthMismatch,
    EmptyProbabilities,
    EmptyProbabilityRow,
    RaggedProbabilities,
    TargetLengthMismatch,
    TargetOutOfRange,
    InvalidK,
    EmptyConfusion,
    NonSquareConfusion,
    InvalidBinCount,
    NonPositiveTrueClassProbability,
}

impl fmt::Display for ClassifierError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self {
            ClassifierError::EmptyWeights => "weights must not be empty",
            ClassifierError::EmptyWeightRow => "weight rows must not be empty",
            ClassifierError::RaggedWeights => "weight rows must all have the same length",
            ClassifierError::BiasLengthMismatch => "bias length must match the number of classes",
            ClassifierError::EmptyFeatures => "features must not be empty",
            ClassifierError::FeatureWidthMismatch => "feature row width must match the model",
            ClassifierError::EmptyProbabilities => "probabilities must not be empty",
            ClassifierError::EmptyProbabilityRow => "probability rows must not be empty",
            ClassifierError::RaggedProbabilities => "probability rows must all have the same length",
            ClassifierError::TargetLengthMismatch => "targets length must match features length",
            ClassifierError::TargetOutOfRange => "target class id out of range",
            ClassifierError::InvalidK => "k must be between 1 and the number of classes",
            ClassifierError::EmptyConfusion => "confusion matrix must not be empty",
            ClassifierError::NonSquareConfusion => "confusion matrix must be square",
            ClassifierError::InvalidBinCount => "num_bins must be positive",
            ClassifierError::NonPositiveTrueClassProbability => "true-class probability must be positive",
        };
        write!(f, "{message}")
    }
}

impl Error for ClassifierError {}

pub fn new_linear_classifier(weights: Vec<Vec<f64>>, bias: Vec<f64>) -> Result<LinearClassifier, ClassifierError> {
    if weights.is_empty() { return Err(ClassifierError::EmptyWeights); }
    let num_classes = weights.len();
    let num_features = weights[0].len();
    if num_features == 0 { return Err(ClassifierError::EmptyWeightRow); }
    if weights.iter().any(|row| row.len() != num_features) { return Err(ClassifierError::RaggedWeights); }
    if bias.len() != num_classes { return Err(ClassifierError::BiasLengthMismatch); }
    Ok(LinearClassifier { weights, bias })
}

fn validate_features(model: &LinearClassifier, features: &[Vec<f64>]) -> Result<(), ClassifierError> {
    if features.is_empty() { return Err(ClassifierError::EmptyFeatures); }
    if features.iter().any(|row| row.len() != model.weights[0].len()) { return Err(ClassifierError::FeatureWidthMismatch); }
    Ok(())
}

fn validate_probabilities(probabilities: &[Vec<f64>]) -> Result<usize, ClassifierError> {
    if probabilities.is_empty() { return Err(ClassifierError::EmptyProbabilities); }
    let width = probabilities[0].len();
    if width == 0 { return Err(ClassifierError::EmptyProbabilityRow); }
    if probabilities.iter().any(|row| row.len() != width) { return Err(ClassifierError::RaggedProbabilities); }
    Ok(width)
}

fn validate_targets(targets: &[usize], expected_len: usize, num_classes: usize) -> Result<(), ClassifierError> {
    if targets.len() != expected_len { return Err(ClassifierError::TargetLengthMismatch); }
    if targets.iter().any(|target| *target >= num_classes) { return Err(ClassifierError::TargetOutOfRange); }
    Ok(())
}

fn argmax_tie_break(values: &[f64]) -> usize {
    let mut best_index = 0usize;
    let mut best_value = values[0];
    for (index, value) in values.iter().enumerate().skip(1) {
        if *value > best_value {
            best_index = index;
            best_value = *value;
        }
    }
    best_index
}

fn logits_for_row(model: &LinearClassifier, row: &[f64]) -> Result<Vec<f64>, ClassifierError> {
    if row.len() != model.weights[0].len() { return Err(ClassifierError::FeatureWidthMismatch); }
    Ok(model.weights.iter().zip(model.bias.iter()).map(|(weights, bias)| {
        weights.iter().zip(row.iter()).map(|(weight, feature)| weight * feature).sum::<f64>() + bias
    }).collect())
}

fn softmax(logits: &[f64]) -> Vec<f64> {
    let shift = logits.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let exps: Vec<f64> = logits.iter().map(|value| (value - shift).exp()).collect();
    let total: f64 = exps.iter().sum();
    exps.iter().map(|value| value / total).collect()
}

pub fn predict_proba_batch(model: &LinearClassifier, features: &[Vec<f64>]) -> Result<Vec<Vec<f64>>, ClassifierError> {
    validate_features(model, features)?;
    features.iter().map(|row| logits_for_row(model, row).map(|logits| softmax(&logits))).collect()
}

pub fn predict_batch(probabilities: &[Vec<f64>]) -> Result<Vec<usize>, ClassifierError> {
    validate_probabilities(probabilities)?;
    Ok(probabilities.iter().map(|row| argmax_tie_break(row)).collect())
}

pub fn predict_top_k(probabilities: &[Vec<f64>], k: usize) -> Result<Vec<Vec<usize>>, ClassifierError> {
    let width = validate_probabilities(probabilities)?;
    if k == 0 || k > width { return Err(ClassifierError::InvalidK); }
    Ok(probabilities.iter().map(|row| {
        let mut ranked: Vec<usize> = (0..width).collect();
        ranked.sort_by(|a, b| row[*b].partial_cmp(&row[*a]).unwrap().then_with(|| a.cmp(b)));
        ranked.truncate(k);
        ranked
    }).collect())
}

pub fn cross_entropy_loss(probabilities: &[Vec<f64>], targets: &[usize]) -> Result<f64, ClassifierError> {
    let width = validate_probabilities(probabilities)?;
    validate_targets(targets, probabilities.len(), width)?;
    let mut total = 0.0;
    for (row, target) in probabilities.iter().zip(targets.iter()) {
        let probability = row[*target];
        if probability <= 0.0 { return Err(ClassifierError::NonPositiveTrueClassProbability); }
        total += -probability.ln();
    }
    Ok(total / targets.len() as f64)
}

pub fn confusion_matrix(probabilities: &[Vec<f64>], targets: &[usize]) -> Result<Vec<Vec<usize>>, ClassifierError> {
    let width = validate_probabilities(probabilities)?;
    validate_targets(targets, probabilities.len(), width)?;
    let predictions = predict_batch(probabilities)?;
    let mut matrix = vec![vec![0usize; width]; width];
    for (prediction, target) in predictions.iter().zip(targets.iter()) {
        matrix[*target][*prediction] += 1;
    }
    Ok(matrix)
}

pub fn per_class_metrics(confusion: &[Vec<usize>]) -> Result<Vec<ClassMetrics>, ClassifierError> {
    if confusion.is_empty() || confusion[0].is_empty() { return Err(ClassifierError::EmptyConfusion); }
    let num_classes = confusion.len();
    if confusion.iter().any(|row| row.len() != num_classes) { return Err(ClassifierError::NonSquareConfusion); }
    let mut report = Vec::with_capacity(num_classes);
    for class_index in 0..num_classes {
        let tp = confusion[class_index][class_index] as f64;
        let support: usize = confusion[class_index].iter().sum();
        let predicted_total: usize = confusion.iter().map(|row| row[class_index]).sum();
        let precision = if predicted_total == 0 { 0.0 } else { tp / predicted_total as f64 };
        let recall = if support == 0 { 0.0 } else { tp / support as f64 };
        let f1 = if precision + recall == 0.0 { 0.0 } else { 2.0 * precision * recall / (precision + recall) };
        report.push(ClassMetrics { precision, recall, f1, support });
    }
    Ok(report)
}

pub fn macro_f1(report: &[ClassMetrics]) -> Result<f64, ClassifierError> {
    if report.is_empty() { return Err(ClassifierError::EmptyConfusion); }
    Ok(report.iter().map(|item| item.f1).sum::<f64>() / report.len() as f64)
}

pub fn expected_calibration_error(probabilities: &[Vec<f64>], targets: &[usize], num_bins: usize) -> Result<f64, ClassifierError> {
    let width = validate_probabilities(probabilities)?;
    validate_targets(targets, probabilities.len(), width)?;
    if num_bins == 0 { return Err(ClassifierError::InvalidBinCount); }
    let mut bin_totals = vec![0usize; num_bins];
    let mut bin_confidence = vec![0.0f64; num_bins];
    let mut bin_accuracy = vec![0.0f64; num_bins];
    for (row, target) in probabilities.iter().zip(targets.iter()) {
        let predicted = argmax_tie_break(row);
        let confidence = row[predicted];
        let raw_index = (confidence * num_bins as f64) as usize;
        let bin_index = raw_index.min(num_bins - 1);
        bin_totals[bin_index] += 1;
        bin_confidence[bin_index] += confidence;
        bin_accuracy[bin_index] += if predicted == *target { 1.0 } else { 0.0 };
    }
    let total_examples = targets.len() as f64;
    let mut ece = 0.0f64;
    for index in 0..num_bins {
        let total = bin_totals[index];
        if total == 0 { continue; }
        let avg_confidence = bin_confidence[index] / total as f64;
        let avg_accuracy = bin_accuracy[index] / total as f64;
        ece += (total as f64 / total_examples) * (avg_accuracy - avg_confidence).abs();
    }
    Ok(ece)
}
'''


def _write_workspace(tmp_path: Path, lib_rs: str) -> Path:
    workspace = tmp_path / "workspace"
    rust_dir = workspace / "rust"
    (rust_dir / "src").mkdir(parents=True)
    (rust_dir / "Cargo.toml").write_text(
        """
[package]
name = "linear_classifier"
version = "0.1.0"
edition = "2021"

[lib]
name = "linear_classifier"
path = "src/lib.rs"
""".strip()
        + "\n"
    )
    (rust_dir / "src" / "lib.rs").write_text(lib_rs)
    return workspace


def _fake_cargo_run(args: list[str], cwd: Path, **_: object) -> subprocess.CompletedProcess[str]:
    assert args == ["cargo", "test", "--quiet"]

    harness_root = Path(cwd)
    hidden_test = (harness_root / "tests" / "hidden_acceptance.rs").read_text()
    cargo_toml = (harness_root / "Cargo.toml").read_text()
    assert "predict_proba_batch" in hidden_test
    assert "cross_entropy_loss" in hidden_test
    assert "expected_calibration_error" in hidden_test

    path_marker = 'linear_classifier = { path = "'
    crate_path = cargo_toml.split(path_marker, 1)[1].split('"', 1)[0]
    lib_rs = Path(crate_path) / "src" / "lib.rs"
    source = lib_rs.read_text()

    if "unimplemented!" in source:
        return subprocess.CompletedProcess(
            args=args,
            returncode=101,
            stdout="",
            stderr="hidden acceptance test failed\n",
        )

    return subprocess.CompletedProcess(
        args=args,
        returncode=0,
        stdout="hidden acceptance ok\n",
        stderr="",
    )


def _enable_fake_toolchain(monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.demo.evaluators.linear_classifier.shutil.which", lambda _: "/usr/bin/cargo")
    monkeypatch.setattr("orchestrator.demo.evaluators.linear_classifier.subprocess.run", _fake_cargo_run)



def test_evaluator_passes_on_correct_workspace(tmp_path: Path, monkeypatch):
    _enable_fake_toolchain(monkeypatch)
    workspace = _write_workspace(tmp_path, PASSING_LIB_RS)

    result = evaluate_workspace(workspace)

    assert result["verdict"] == "PASS"
    assert result["failure_categories"] == []
    assert result["summary"]["hidden_tests_passed"] is True
    assert "soft_quality" in result
    assert result["soft_quality"]["score"] >= 0.9



def test_evaluator_fails_on_incomplete_workspace(tmp_path: Path, monkeypatch):
    _enable_fake_toolchain(monkeypatch)
    workspace = tmp_path / "broken-workspace"
    shutil.copytree(SEED, workspace)

    result = evaluate_workspace(workspace)

    assert result["verdict"] == "FAIL"
    assert "hidden_acceptance_failed" in result["failure_categories"]
    assert result["soft_quality"]["score"] < 0.5
    assert "contains unimplemented stubs" in result["soft_quality"]["findings"]



def test_evaluator_does_not_mutate_candidate_workspace(tmp_path: Path, monkeypatch):
    _enable_fake_toolchain(monkeypatch)
    workspace = tmp_path / "broken-workspace"
    shutil.copytree(SEED, workspace)
    before = sorted(str(path.relative_to(workspace)) for path in workspace.rglob("*"))

    evaluate_workspace(workspace)

    after = sorted(str(path.relative_to(workspace)) for path in workspace.rglob("*"))
    assert after == before
