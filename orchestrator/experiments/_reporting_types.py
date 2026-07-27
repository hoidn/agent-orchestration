"""Private value types and fixed domains for lean-pilot reporting."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


class ReportingError(ValueError):
    """A reporting or sample-size contract was violated."""


@dataclass(frozen=True)
class ExactSampleSizePlan:
    """One exact fixed-N superiority and non-tied-accrual plan."""

    required_non_tied_comparisons: int
    critical_win_count: int
    achieved_null_tail_probability: Fraction
    achieved_power: Fraction
    fixed_valid_block_cap: int
    achieved_accrual_probability: Fraction
    max_invalid_attempts: int
    max_cost_ratio: Fraction
    min_calls_per_block: int
    max_calls_per_block: int
    minimum_provider_calls_at_cap: int
    maximum_provider_calls_at_cap: int
    terminal_shortfall_status: str


@dataclass(frozen=True)
class ReviewBinding:
    block_id: str
    package_id: str
    package_manifest_digest: str
    review_id: str
    review_result_digest: str
    review_path: str
    reviewer_id: str
    reviewer_role: str


@dataclass(frozen=True)
class UnblindingBinding:
    block_id: str
    package_id: str
    package_manifest_digest: str
    opaque_label: str
    treatment_id: str


TREATMENTS = ("DIRECT", "COORDINATOR", "ORC")
COMPARISONS = (
    ("DIRECT_VS_ORC", "DIRECT", "ORC"),
    ("COORDINATOR_VS_ORC", "COORDINATOR", "ORC"),
)
LIFECYCLES = (
    "COMPLETED",
    "BLOCKED",
    "EXHAUSTED",
    "PROTOCOL_FAILURE",
    "LAUNCH_FAILURE",
    "TIMEOUT",
    "NONZERO_EXIT",
    "CHECK_FAILURE",
)
FAILURES = LIFECYCLES[1:]
