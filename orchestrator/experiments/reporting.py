"""Public facade for bounded lean-pilot reporting and exact planning."""

from ._reporting_render import render_pilot_markdown
from ._reporting_sample_size import (
    exact_binomial_tail,
    parse_canonical_decimal,
    plan_exact_sample_size,
    plan_sample_size,
)
from ._reporting_synthesis import build_pilot_summary
from ._reporting_types import (
    ExactSampleSizePlan,
    ReportingError,
    ReviewBinding,
    UnblindingBinding,
)
from ._reporting_validation import assess_readiness, load_attempt_records


__all__ = [
    "ExactSampleSizePlan",
    "ReviewBinding",
    "ReportingError",
    "UnblindingBinding",
    "assess_readiness",
    "build_pilot_summary",
    "exact_binomial_tail",
    "parse_canonical_decimal",
    "plan_exact_sample_size",
    "plan_sample_size",
    "load_attempt_records",
    "render_pilot_markdown",
]
