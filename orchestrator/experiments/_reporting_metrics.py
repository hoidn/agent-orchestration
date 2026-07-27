"""Private deterministic treatment and exact-metric aggregation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from ._reporting_types import FAILURES, LIFECYCLES, TREATMENTS
from ._reporting_validation import _fail


@dataclass(frozen=True)
class TreatmentMetrics:
    executions_by_block: dict[str, dict[str, dict[str, Any]]]
    treatment_statistics: list[dict[str, object]]
    hard_contract_findings: list[dict[str, object]]
    medians: list[dict[str, object]]
    ratios: list[dict[str, object]]


def _fraction(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _median(values: Sequence[int]) -> Fraction:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return Fraction(ordered[middle])
    return Fraction(ordered[middle - 1] + ordered[middle], 2)


def _known_median(values: Sequence[int]) -> Fraction | None:
    return _median(values) if values else None


def collect_treatment_metrics(
    *,
    lock: Mapping[str, object],
    valid_attempts: Sequence[Mapping[str, object]],
) -> TreatmentMetrics:
    executions_by_block: dict[str, dict[str, dict[str, Any]]] = {}
    treatment_executions: dict[str, list[dict[str, Any]]] = {
        treatment: [] for treatment in TREATMENTS
    }
    hard_contract_findings: list[dict[str, object]] = []
    for attempt in valid_attempts:
        executions = {
            execution["treatment_id"]: execution
            for execution in attempt["treatment_executions"]  # type: ignore[index]
        }
        executions_by_block[attempt["block_id"]] = executions
        for treatment in TREATMENTS:
            treatment_executions[treatment].append(executions[treatment])
        for execution in executions.values():
            cost = execution["cost"]
            if (
                cost != "UNKNOWN"
                and cost["currency"] != lock["provider_policy"]["currency"]  # type: ignore[index]
            ):
                _fail("cost_currency_mismatch")
            if execution["lifecycle_outcome"] in {
                "CHECK_FAILURE",
                "PROTOCOL_FAILURE",
            }:
                hard_contract_findings.append(
                    {
                        "block_id": attempt["block_id"],
                        "treatment_id": execution["treatment_id"],
                        "finding_class": execution["lifecycle_outcome"],
                        "disposition": "TREATMENT_OUTCOME_RETAINED",
                        "evidence_references": execution["evidence_references"],
                    }
                )

    treatment_statistics: list[dict[str, object]] = []
    medians: list[dict[str, object]] = []
    median_values: dict[tuple[str, str], Fraction | None] = {}
    for treatment in TREATMENTS:
        executions = treatment_executions[treatment]
        lifecycle_counts = Counter(
            execution["lifecycle_outcome"] for execution in executions
        )
        viable = lifecycle_counts["COMPLETED"]
        treatment_statistics.append(
            {
                "treatment_id": treatment,
                "viable_count": viable,
                "nonviable_count": len(executions) - viable,
                "lifecycle_outcome_counts": {
                    key: lifecycle_counts[key] for key in LIFECYCLES
                },
                "failure_class_counts": {
                    key: lifecycle_counts[key] for key in FAILURES
                },
                "provider_call_counts": [
                    execution["provider_call_count"] for execution in executions
                ],
            }
        )
        elapsed = _known_median(
            [execution["elapsed_milliseconds"] for execution in executions]
        )
        median_values[("elapsed_milliseconds", treatment)] = elapsed
        medians.append(
            {
                "metric": "elapsed_milliseconds",
                "treatment_id": treatment,
                "value": "UNKNOWN" if elapsed is None else _fraction(elapsed),
            }
        )
        costs = [execution["cost"] for execution in executions]
        cost_value = (
            None
            if any(cost == "UNKNOWN" for cost in costs)
            else _known_median(
                [cost["cost_microunits"] for cost in costs]
            )
        )
        median_values[("cost_microunits", treatment)] = cost_value
        medians.append(
            {
                "metric": "cost_microunits",
                "treatment_id": treatment,
                "value": (
                    "UNKNOWN" if cost_value is None else _fraction(cost_value)
                ),
            }
        )
        token_counts = [execution["token_counts"] for execution in executions]
        for token_key, metric in (
            ("input", "input_tokens"),
            ("output", "output_tokens"),
        ):
            token_value = (
                None
                if not token_counts
                or any(value == "UNKNOWN" for value in token_counts)
                else _known_median(
                    [value[token_key] for value in token_counts]
                )
            )
            median_values[(metric, treatment)] = token_value
            medians.append(
                {
                    "metric": metric,
                    "treatment_id": treatment,
                    "value": (
                        "UNKNOWN"
                        if token_value is None
                        else _fraction(token_value)
                    ),
                }
            )

    ratios: list[dict[str, object]] = []
    for metric in (
        "elapsed_milliseconds",
        "cost_microunits",
        "input_tokens",
        "output_tokens",
    ):
        numerator = median_values[(metric, "ORC")]
        for denominator_treatment in ("DIRECT", "COORDINATOR"):
            denominator = median_values[(metric, denominator_treatment)]
            value = (
                "UNKNOWN"
                if numerator is None or denominator in {None, Fraction(0)}
                else _fraction(numerator / denominator)
            )
            ratios.append(
                {
                    "metric": metric,
                    "numerator_treatment_id": "ORC",
                    "denominator_treatment_id": denominator_treatment,
                    "value": value,
                }
            )

    return TreatmentMetrics(
        executions_by_block=executions_by_block,
        treatment_statistics=treatment_statistics,
        hard_contract_findings=hard_contract_findings,
        medians=medians,
        ratios=ratios,
    )
