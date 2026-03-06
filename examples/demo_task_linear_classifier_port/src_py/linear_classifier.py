"""Reference multiclass linear-classifier utilities for the workflow demo task.

The implementation intentionally stays small and dependency-free so the task's
complexity comes from semantics, validation, and verification rather than setup.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, fsum, log
from typing import Sequence


class ClassifierError(ValueError):
    """Raised when classifier inputs are malformed."""


@dataclass(frozen=True)
class LinearClassifier:
    weights: tuple[tuple[float, ...], ...]
    bias: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.weights:
            raise ClassifierError("weights must not be empty")
        num_classes = len(self.weights)
        num_features = len(self.weights[0])
        if num_features == 0:
            raise ClassifierError("weight rows must not be empty")
        for row in self.weights:
            if len(row) != num_features:
                raise ClassifierError("weight rows must all have the same length")
        if len(self.bias) != num_classes:
            raise ClassifierError("bias length must match the number of classes")

    @property
    def num_classes(self) -> int:
        return len(self.weights)

    @property
    def num_features(self) -> int:
        return len(self.weights[0])


def _validate_features(model: LinearClassifier, features: Sequence[Sequence[float]]) -> None:
    if not features:
        raise ClassifierError("features must not be empty")
    for row in features:
        if len(row) != model.num_features:
            raise ClassifierError("feature row width must match the model")


def _validate_targets(targets: Sequence[int], expected_len: int, num_classes: int) -> None:
    if len(targets) != expected_len:
        raise ClassifierError("targets length must match features length")
    for target in targets:
        if target < 0 or target >= num_classes:
            raise ClassifierError("target class id out of range")


def _argmax_tie_break(values: Sequence[float]) -> int:
    best_index = 0
    best_value = values[0]
    for index, value in enumerate(values[1:], start=1):
        if value > best_value:
            best_index = index
            best_value = value
    return best_index


def logits_for_row(model: LinearClassifier, row: Sequence[float]) -> list[float]:
    if len(row) != model.num_features:
        raise ClassifierError("feature row width must match the model")
    return [fsum(weight * feature for weight, feature in zip(weight_row, row)) + bias for weight_row, bias in zip(model.weights, model.bias)]


def softmax(logits: Sequence[float]) -> list[float]:
    if not logits:
        raise ClassifierError("logits must not be empty")
    shift = max(logits)
    exponentials = [exp(value - shift) for value in logits]
    total = fsum(exponentials)
    return [value / total for value in exponentials]


def predict_proba_batch(model: LinearClassifier, features: Sequence[Sequence[float]]) -> list[list[float]]:
    _validate_features(model, features)
    return [softmax(logits_for_row(model, row)) for row in features]


def predict_labels(probabilities: Sequence[Sequence[float]]) -> list[int]:
    if not probabilities:
        raise ClassifierError("probabilities must not be empty")
    width = len(probabilities[0])
    if width == 0:
        raise ClassifierError("probability rows must not be empty")
    labels: list[int] = []
    for row in probabilities:
        if len(row) != width:
            raise ClassifierError("probability rows must all have the same length")
        labels.append(_argmax_tie_break(row))
    return labels


def predict_top_k(probabilities: Sequence[Sequence[float]], k: int) -> list[list[int]]:
    if not probabilities:
        raise ClassifierError("probabilities must not be empty")
    width = len(probabilities[0])
    if width == 0:
        raise ClassifierError("probability rows must not be empty")
    if k <= 0 or k > width:
        raise ClassifierError("k must be between 1 and the number of classes")
    results: list[list[int]] = []
    for row in probabilities:
        if len(row) != width:
            raise ClassifierError("probability rows must all have the same length")
        ranked = sorted(range(width), key=lambda idx: (-row[idx], idx))
        results.append(ranked[:k])
    return results


def cross_entropy_loss(probabilities: Sequence[Sequence[float]], targets: Sequence[int]) -> float:
    if not probabilities:
        raise ClassifierError("probabilities must not be empty")
    width = len(probabilities[0])
    if width == 0:
        raise ClassifierError("probability rows must not be empty")
    _validate_targets(targets, len(probabilities), width)

    total = 0.0
    for row, target in zip(probabilities, targets):
        if len(row) != width:
            raise ClassifierError("probability rows must all have the same length")
        probability = row[target]
        if probability <= 0.0:
            raise ClassifierError("true-class probability must be positive")
        total += -log(probability)
    return total / len(targets)


def confusion_matrix(probabilities: Sequence[Sequence[float]], targets: Sequence[int]) -> list[list[int]]:
    labels = predict_labels(probabilities)
    num_classes = len(probabilities[0])
    _validate_targets(targets, len(probabilities), num_classes)
    matrix = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
    for prediction, target in zip(labels, targets):
        matrix[target][prediction] += 1
    return matrix


def per_class_metrics(confusion: Sequence[Sequence[int]]) -> list[dict[str, float]]:
    if not confusion or not confusion[0]:
        raise ClassifierError("confusion matrix must not be empty")
    num_classes = len(confusion)
    for row in confusion:
        if len(row) != num_classes:
            raise ClassifierError("confusion matrix must be square")

    report: list[dict[str, float]] = []
    for class_index in range(num_classes):
        tp = confusion[class_index][class_index]
        support = sum(confusion[class_index])
        predicted_total = sum(row[class_index] for row in confusion)
        precision = tp / predicted_total if predicted_total else 0.0
        recall = tp / support if support else 0.0
        f1 = 0.0 if precision + recall == 0.0 else 2.0 * precision * recall / (precision + recall)
        report.append({"precision": precision, "recall": recall, "f1": f1, "support": float(support)})
    return report


def macro_f1(report: Sequence[dict[str, float]]) -> float:
    if not report:
        raise ClassifierError("report must not be empty")
    return fsum(item["f1"] for item in report) / len(report)


def expected_calibration_error(
    probabilities: Sequence[Sequence[float]], targets: Sequence[int], num_bins: int = 10
) -> float:
    if not probabilities:
        raise ClassifierError("probabilities must not be empty")
    width = len(probabilities[0])
    if width == 0:
        raise ClassifierError("probability rows must not be empty")
    _validate_targets(targets, len(probabilities), width)
    if num_bins <= 0:
        raise ClassifierError("num_bins must be positive")

    bin_totals = [0 for _ in range(num_bins)]
    bin_confidence = [0.0 for _ in range(num_bins)]
    bin_accuracy = [0.0 for _ in range(num_bins)]

    for row, target in zip(probabilities, targets):
        if len(row) != width:
            raise ClassifierError("probability rows must all have the same length")
        predicted = _argmax_tie_break(row)
        confidence = row[predicted]
        raw_index = int(confidence * num_bins)
        bin_index = min(raw_index, num_bins - 1)
        bin_totals[bin_index] += 1
        bin_confidence[bin_index] += confidence
        bin_accuracy[bin_index] += 1.0 if predicted == target else 0.0

    total_examples = len(targets)
    ece = 0.0
    for total, confidence_sum, accuracy_sum in zip(bin_totals, bin_confidence, bin_accuracy):
        if total == 0:
            continue
        avg_confidence = confidence_sum / total
        avg_accuracy = accuracy_sum / total
        ece += (total / total_examples) * abs(avg_accuracy - avg_confidence)
    return ece
