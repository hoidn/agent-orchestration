"""Reference multiclass metrics utilities for the workflow demo task.

The implementation intentionally stays small and dependency-free so the task's
complexity comes from semantics, validation, and verification rather than setup.
"""

from __future__ import annotations

from math import fsum
from typing import Sequence


class MetricsError(ValueError):
    """Raised when metrics inputs are malformed."""


def _validate_rows(probabilities: Sequence[Sequence[float]]) -> int:
    if not probabilities:
        raise MetricsError("probabilities must not be empty")

    num_classes = len(probabilities[0])
    if num_classes == 0:
        raise MetricsError("probability rows must not be empty")

    for row in probabilities:
        if len(row) != num_classes:
            raise MetricsError("probability rows must all have the same length")
    return num_classes


def _validate_targets(targets: Sequence[int], expected_len: int, num_classes: int) -> None:
    if len(targets) != expected_len:
        raise MetricsError("targets length must match probabilities length")
    for target in targets:
        if target < 0 or target >= num_classes:
            raise MetricsError("target class id out of range")


def _argmax_tie_break(row: Sequence[float]) -> int:
    best_index = 0
    best_value = row[0]
    for index, value in enumerate(row[1:], start=1):
        if value > best_value:
            best_index = index
            best_value = value
    return best_index


def top_k_accuracy(probabilities: Sequence[Sequence[float]], targets: Sequence[int], k: int = 1) -> float:
    num_classes = _validate_rows(probabilities)
    _validate_targets(targets, len(probabilities), num_classes)
    if k <= 0 or k > num_classes:
        raise MetricsError("k must be between 1 and the number of classes")

    correct = 0
    for row, target in zip(probabilities, targets):
        ranked = sorted(range(num_classes), key=lambda idx: (-row[idx], idx))
        if target in ranked[:k]:
            correct += 1
    return correct / len(targets)


def confusion_matrix(
    probabilities: Sequence[Sequence[float]], targets: Sequence[int], num_classes: int
) -> list[list[int]]:
    inferred_classes = _validate_rows(probabilities)
    if num_classes != inferred_classes:
        raise MetricsError("num_classes must match the probability row width")
    _validate_targets(targets, len(probabilities), num_classes)

    matrix = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
    for row, target in zip(probabilities, targets):
        predicted = _argmax_tie_break(row)
        matrix[target][predicted] += 1
    return matrix


def per_class_metrics(confusion: Sequence[Sequence[int]]) -> list[dict[str, float]]:
    if not confusion or not confusion[0]:
        raise MetricsError("confusion matrix must not be empty")
    num_classes = len(confusion)
    for row in confusion:
        if len(row) != num_classes:
            raise MetricsError("confusion matrix must be square")

    report: list[dict[str, float]] = []
    for class_index in range(num_classes):
        tp = confusion[class_index][class_index]
        support = sum(confusion[class_index])
        predicted_total = sum(row[class_index] for row in confusion)
        precision = tp / predicted_total if predicted_total else 0.0
        recall = tp / support if support else 0.0
        f1 = 0.0 if precision + recall == 0.0 else 2.0 * precision * recall / (precision + recall)
        report.append(
            {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": float(support),
            }
        )
    return report


def macro_f1(report: Sequence[dict[str, float]]) -> float:
    if not report:
        raise MetricsError("report must not be empty")
    return fsum(item["f1"] for item in report) / len(report)


def expected_calibration_error(
    probabilities: Sequence[Sequence[float]], targets: Sequence[int], num_bins: int = 10
) -> float:
    num_classes = _validate_rows(probabilities)
    _validate_targets(targets, len(probabilities), num_classes)
    if num_bins <= 0:
        raise MetricsError("num_bins must be positive")

    bin_totals = [0 for _ in range(num_bins)]
    bin_confidence = [0.0 for _ in range(num_bins)]
    bin_accuracy = [0.0 for _ in range(num_bins)]

    for row, target in zip(probabilities, targets):
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
