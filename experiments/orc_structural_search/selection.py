"""Frozen final-choice rule over evaluation records."""

from collections.abc import Mapping, Sequence

from experiments.orc_structural_search.records import UNAVAILABLE


def final_choice(rows: Sequence[Mapping], *, criterion: Mapping) -> str:
    """Return the `candidate_id` the frozen criterion selects among `rows`.

    `mean_cost_ceiling` must be numeric; rows above it, and rows whose cost is
    "unavailable", are excluded. Among the
    rest: rows within `equivalence_tolerance` of the best
    `validation_success`, then lower `mean_cost`, fewer `provider_calls`,
    lexically earlier `candidate_id`. The reference seed competes like any row.
    """

    if not criterion.get("criterion_sha256"):
        raise ValueError("criterion_sha256 required")
    if not any(row["is_reference"] for row in rows):
        raise ValueError("reference seed missing")
    ceiling = criterion["mean_cost_ceiling"]
    if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)):
        raise ValueError("mean_cost_ceiling must be numeric")
    eligible = [row for row in rows if _under_ceiling(row["mean_cost"], ceiling)]
    if not eligible:
        raise ValueError(f"no candidate under mean_cost_ceiling {ceiling!r}")
    best = max(row["validation_success"] for row in eligible)
    tied = [row for row in eligible if row["validation_success"] >= best - criterion["equivalence_tolerance"]]
    return min(tied, key=_tie_key)["candidate_id"]


def _under_ceiling(cost: float | str, ceiling: float) -> bool:
    return cost != UNAVAILABLE and cost <= ceiling


def _tie_key(row: Mapping) -> tuple:
    return (row["mean_cost"], row["provider_calls"], row["candidate_id"])
