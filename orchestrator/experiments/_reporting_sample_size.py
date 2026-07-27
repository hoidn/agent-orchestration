"""Private exact sample-size calculations for lean-pilot reporting."""

from __future__ import annotations

import re
from fractions import Fraction
from math import comb

from ._reporting_types import ExactSampleSizePlan, ReportingError


_CANONICAL_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?")


def parse_canonical_decimal(text: str) -> Fraction:
    """Parse non-negative canonical decimal text without using binary float."""

    if not isinstance(text, str) or _CANONICAL_DECIMAL.fullmatch(text) is None:
        raise ReportingError("decimal_noncanonical")
    if "." not in text:
        return Fraction(int(text), 1)
    whole, fractional = text.split(".", 1)
    denominator = 10 ** len(fractional)
    numerator = int(whole) * denominator + int(fractional)
    return Fraction(numerator, denominator)


def exact_binomial_tail(
    *,
    n: int,
    successes_at_least: int,
    rate: Fraction,
) -> Fraction:
    """Return ``P[X >= successes_at_least]`` for exact binomial ``X``."""

    if (
        isinstance(n, bool)
        or not isinstance(n, int)
        or n < 0
        or isinstance(successes_at_least, bool)
        or not isinstance(successes_at_least, int)
        or successes_at_least < 0
        or successes_at_least > n + 1
        or not isinstance(rate, Fraction)
        or rate < 0
        or rate > 1
    ):
        raise ReportingError("binomial_domain_invalid")
    return sum(
        (
            Fraction(comb(n, successes), 1)
            * rate**successes
            * (1 - rate) ** (n - successes)
            for successes in range(successes_at_least, n + 1)
        ),
        Fraction(0),
    )


def _positive_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def plan_sample_size(
    *,
    null_rate: Fraction,
    target_rate: Fraction,
    alpha: Fraction,
    power: Fraction,
    max_tie_rate: Fraction,
    accrual_probability: Fraction,
    max_invalid_attempts: int,
    max_cost_ratio: Fraction,
    min_calls_per_block: int,
    max_calls_per_block: int,
    search_limit: int,
) -> ExactSampleSizePlan:
    """Find the smallest exact fixed-N and valid-block accrual cap."""

    fractions = (
        null_rate,
        target_rate,
        alpha,
        power,
        max_tie_rate,
        accrual_probability,
        max_cost_ratio,
    )
    if any(not isinstance(value, Fraction) for value in fractions):
        raise ReportingError("sample_size_domain_invalid")
    if (
        not 0 <= null_rate < target_rate <= 1
        or not 0 < alpha < 1
        or not 0 < power <= 1
        or not 0 <= max_tie_rate < 1
        or not 0 < accrual_probability <= 1
        or isinstance(max_invalid_attempts, bool)
        or not isinstance(max_invalid_attempts, int)
        or max_invalid_attempts < 0
        or max_cost_ratio <= 0
        or not _positive_int(min_calls_per_block)
        or not _positive_int(max_calls_per_block)
        or min_calls_per_block > max_calls_per_block
        or not _positive_int(search_limit)
    ):
        raise ReportingError("sample_size_domain_invalid")

    selected: tuple[int, int, Fraction, Fraction] | None = None
    for n in range(1, search_limit + 1):
        for critical in range(0, n + 1):
            null_tail = exact_binomial_tail(
                n=n,
                successes_at_least=critical,
                rate=null_rate,
            )
            achieved_power = exact_binomial_tail(
                n=n,
                successes_at_least=critical,
                rate=target_rate,
            )
            if null_tail <= alpha and achieved_power >= power:
                selected = n, critical, null_tail, achieved_power
                break
        if selected is not None:
            break
    if selected is None:
        raise ReportingError("sample_size_search_exhausted")

    n, critical, null_tail, achieved_power = selected
    non_tie_rate = 1 - max_tie_rate
    cap: int | None = None
    achieved_accrual = Fraction(0)
    for candidate in range(n, search_limit + 1):
        achieved_accrual = exact_binomial_tail(
            n=candidate,
            successes_at_least=n,
            rate=non_tie_rate,
        )
        if achieved_accrual >= accrual_probability:
            cap = candidate
            break
    if cap is None:
        raise ReportingError("sample_size_search_exhausted")

    return ExactSampleSizePlan(
        required_non_tied_comparisons=n,
        critical_win_count=critical,
        achieved_null_tail_probability=null_tail,
        achieved_power=achieved_power,
        fixed_valid_block_cap=cap,
        achieved_accrual_probability=achieved_accrual,
        max_invalid_attempts=max_invalid_attempts,
        max_cost_ratio=max_cost_ratio,
        min_calls_per_block=min_calls_per_block,
        max_calls_per_block=max_calls_per_block,
        minimum_provider_calls_at_cap=cap * min_calls_per_block,
        maximum_provider_calls_at_cap=cap * max_calls_per_block,
        terminal_shortfall_status="INSUFFICIENT_EVIDENCE",
    )


plan_exact_sample_size = plan_sample_size
