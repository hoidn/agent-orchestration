"""Exact-rational decision lock for the ES effectiveness study.

The lock is a deterministic record, not a self-hashing envelope.  Its digest
is computed by the caller over canonical bytes and bound by the surrounding
prelaunch manifest.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence

from jsonschema import Draft202012Validator


ARMS = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")
OPAQUE_PACKAGES = ("PACKAGE-01", "PACKAGE-02", "PACKAGE-03", "PACKAGE-04")
ATTEMPT_IDS = tuple(f"ES-ATTEMPT-{index:02d}" for index in range(1, 5))
_DECIMAL_RE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BINDING_KEYS = frozenset(
    {
        "arm_workflow_sha256",
        "environment_lock_sha256",
        "evaluator_fixture_manifest_sha256",
        "prompt_manifest_sha256",
        "randomization_manifest_sha256",
        "report_schema_sha256",
        "source_projection_manifest_sha256",
        "task_profile_sha256",
        "task_seed_manifest_sha256",
    }
)
_RANDOMIZATION_ROOT = b"es-f1-es-randomization.v1\0"
_ARM_DOMAIN = "ARM_PRESENTATION"
_PACKAGE_DOMAIN = "OPAQUE_PACKAGE_PRESENTATION"
_DECISION_LOCK_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "experiments/orc_effectiveness/f1_es/decision-lock.schema.json"
)
_RANDOMIZATION_SCHEMA_PATH = _DECISION_LOCK_SCHEMA_PATH.with_name(
    "randomization-manifest.schema.json"
)


class DecisionLockError(ValueError):
    """One exact lock, route, schedule, or rational invariant failed closed."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _reject_constant(value: str) -> NoReturn:
    raise DecisionLockError("json_number_noncanonical", value)


def _reject_float(value: str) -> NoReturn:
    raise DecisionLockError("json_number_noncanonical", value)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DecisionLockError("json_duplicate_key", key)
        result[key] = value
    return result


def _validate_json_value(value: object, *, label: str) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise DecisionLockError("json_not_utf8", label) from exc
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, label=f"{label}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise DecisionLockError("json_key_invalid", label)
            _validate_json_value(key, label=f"{label}.key")
            _validate_json_value(item, label=f"{label}.{key}")
        return
    raise DecisionLockError("json_value_invalid", f"{label}:{type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a strict JSON value as sorted compact UTF-8 plus one LF."""

    _validate_json_value(value, label="record")
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8", "strict")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise DecisionLockError("json_value_invalid", str(exc)) from exc


def load_canonical_json(path: Path) -> dict[str, object]:
    """Load one canonical object while rejecting duplicate keys and floats."""

    candidate = Path(path)
    try:
        raw = candidate.read_bytes()
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except DecisionLockError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecisionLockError("json_record_invalid", str(candidate)) from exc
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise DecisionLockError("json_record_noncanonical", str(candidate))
    return value


def parse_canonical_decimal(value: object) -> Fraction:
    """Parse one non-negative, non-exponent, no-trailing-zero decimal."""

    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise DecisionLockError("decimal_noncanonical", repr(value))
    if "." not in value:
        return Fraction(int(value), 1)
    whole, fractional = value.split(".", 1)
    scale = 10 ** len(fractional)
    return Fraction(int(whole) * scale + int(fractional), scale)


def _require_int(value: object, *, field: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DecisionLockError("integer_invalid", field)
    if minimum is not None and value < minimum:
        raise DecisionLockError("integer_invalid", field)
    return value


def _require_probability(value: object, *, field: str) -> Fraction:
    if not isinstance(value, Fraction) or value < 0 or value > 1:
        raise DecisionLockError("probability_invalid", field)
    return value


def _fraction_record(value: Fraction) -> dict[str, int]:
    return {"denominator": value.denominator, "numerator": value.numerator}


def exact_binomial_tail(
    trials: object,
    threshold: object,
    probability: Fraction,
) -> Fraction:
    """Return P(X >= threshold) for an exact Binomial(trials, probability)."""

    n = _require_int(trials, field="trials", minimum=1)
    k = _require_int(threshold, field="threshold", minimum=0)
    p = _require_probability(probability, field="probability")
    if k > n:
        raise DecisionLockError("binomial_threshold_invalid")
    return sum(
        (
            Fraction(math.comb(n, wins), 1)
            * p**wins
            * (1 - p) ** (n - wins)
            for wins in range(k, n + 1)
        ),
        Fraction(0),
    )


def _derive_non_tied_design(
    *,
    null_rate: Fraction,
    target_rate: Fraction,
    alpha: Fraction,
    desired_power: Fraction,
) -> tuple[int, int, Fraction, Fraction]:
    for comparisons in range(1, 10_001):
        for critical_wins in range(1, comparisons + 1):
            null_tail = exact_binomial_tail(comparisons, critical_wins, null_rate)
            if null_tail > alpha:
                continue
            achieved_power = exact_binomial_tail(
                comparisons, critical_wins, target_rate
            )
            if achieved_power >= desired_power:
                return comparisons, critical_wins, null_tail, achieved_power
    raise DecisionLockError("operating_characteristics_unbounded")


def _accrual_probability(
    blocks: int,
    required_non_tied: int,
    non_tie_probability: Fraction,
) -> Fraction:
    if blocks < required_non_tied:
        return Fraction(0)
    return exact_binomial_tail(blocks, required_non_tied, non_tie_probability)


def derive_operating_characteristics(
    *,
    null_rate: Fraction,
    target_rate: Fraction,
    alpha: Fraction,
    desired_power: Fraction,
    maximum_tie_indeterminate_rate: Fraction,
    minimum_accrual_assurance: Fraction,
) -> dict[str, object]:
    """Derive the paired screen and fixed block cap from exact inputs."""

    null = _require_probability(null_rate, field="null_rate")
    target = _require_probability(target_rate, field="target_rate")
    selected_alpha = _require_probability(alpha, field="alpha")
    power = _require_probability(desired_power, field="desired_power")
    tie_rate = _require_probability(
        maximum_tie_indeterminate_rate,
        field="maximum_tie_indeterminate_rate",
    )
    assurance = _require_probability(
        minimum_accrual_assurance,
        field="minimum_accrual_assurance",
    )
    if not (null < target and selected_alpha > 0 and power > 0 and assurance > 0):
        raise DecisionLockError("operating_characteristics_domain_invalid")
    comparisons, critical, null_tail, achieved = _derive_non_tied_design(
        null_rate=null,
        target_rate=target,
        alpha=selected_alpha,
        desired_power=power,
    )
    predecessor_comparisons = comparisons - 1
    predecessor_critical = max(1, critical - 1)
    if predecessor_comparisons < 1:
        raise DecisionLockError("operating_characteristics_minimality_invalid")
    predecessor_critical = min(predecessor_critical, predecessor_comparisons)
    predecessor_null = exact_binomial_tail(
        predecessor_comparisons,
        predecessor_critical,
        null,
    )
    predecessor_power = exact_binomial_tail(
        predecessor_comparisons,
        predecessor_critical,
        target,
    )
    non_tie = 1 - tie_rate
    for blocks in range(comparisons, 10_001):
        accrual = _accrual_probability(blocks, comparisons, non_tie)
        if accrual >= assurance:
            maximum_blocks = blocks
            break
    else:
        raise DecisionLockError("accrual_characteristics_unbounded")
    previous_blocks = maximum_blocks - 1
    previous_accrual = _accrual_probability(
        previous_blocks,
        comparisons,
        non_tie,
    )
    return {
        "required_non_tied_comparisons": comparisons,
        "critical_rich_wins": critical,
        "null_tail": _fraction_record(null_tail),
        "achieved_power": _fraction_record(achieved),
        "maximum_valid_blocks": maximum_blocks,
        "accrual_probability": _fraction_record(accrual),
        "minimality": {
            "comparison_predecessor": {
                "required_non_tied_comparisons": predecessor_comparisons,
                "critical_rich_wins": predecessor_critical,
                "null_tail": _fraction_record(predecessor_null),
                "achieved_power": _fraction_record(predecessor_power),
            },
            "valid_block_predecessor": {
                "maximum_valid_blocks": previous_blocks,
                "accrual_probability": _fraction_record(previous_accrual),
            },
        },
    }


_TERMINAL_PREFIXES: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    ("DIRECT", ((), ("I",))),
    (
        "DESIGN_QA",
        ((), ("D",), ("D", "DR"), ("D", "DR", "I"), ("D", "DR", "DREV"), ("D", "DR", "DREV", "I")),
    ),
    ("PRODUCT_QA", ((), ("I",), ("I", "PR"), ("I", "PR", "FIX"))),
    (
        "RICH",
        (
            (),
            ("D",),
            ("D", "DR"),
            ("D", "DR", "I"),
            ("D", "DR", "I", "PR"),
            ("D", "DR", "I", "PR", "FIX"),
            ("D", "DR", "DREV"),
            ("D", "DR", "DREV", "I"),
            ("D", "DR", "DREV", "I", "PR"),
            ("D", "DR", "DREV", "I", "PR", "FIX"),
        ),
    ),
)
_COMPLETED_SEQUENCES = {
    "DIRECT": {("I",)},
    "DESIGN_QA": {("D", "DR", "I"), ("D", "DR", "DREV", "I")},
    "PRODUCT_QA": {("I", "PR"), ("I", "PR", "FIX")},
    "RICH": {
        ("D", "DR", "I", "PR"),
        ("D", "DR", "I", "PR", "FIX"),
        ("D", "DR", "DREV", "I", "PR"),
        ("D", "DR", "DREV", "I", "PR", "FIX"),
    },
}


def derive_terminal_routes() -> list[dict[str, object]]:
    """Return every unique terminal prefix in the frozen four-arm graph."""

    rows: list[dict[str, object]] = []
    for arm, prefixes in _TERMINAL_PREFIXES:
        for roles in prefixes:
            suffix = "_".join(roles) if roles else "EMPTY"
            call_slots = [f"{arm}.{role}" for role in roles]
            rows.append(
                {
                    "arm": arm,
                    "route_id": f"{arm}.{suffix}",
                    "role_sequence": list(roles),
                    "call_slots": call_slots,
                    "call_count": len(call_slots),
                    "completed": roles in _COMPLETED_SEQUENCES[arm],
                }
            )
    return rows


def derive_evaluation_routes() -> list[dict[str, object]]:
    """Return the fixed seven-call and optional-adjudicator eight-call routes."""

    prefix = [
        "EVAL.SCORER_DIRECT",
        "EVAL.SCORER_DESIGN_QA",
        "EVAL.SCORER_PRODUCT_QA",
        "EVAL.SCORER_RICH",
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    ]
    rows = []
    for adjudication in (False, True):
        calls = list(prefix)
        if adjudication:
            calls.append("EVAL.ADJUDICATOR")
        calls.append("EVAL.INTEGRATED_REVIEW")
        rows.append(
            {
                "route_id": (
                    "EVALUATION.WITH_ADJUDICATION"
                    if adjudication
                    else "EVALUATION.NO_ADJUDICATION"
                ),
                "adjudication": adjudication,
                "call_slots": calls,
                "call_count": len(calls),
            }
        )
    return rows


def derive_call_bounds(
    *,
    terminal_routes: Sequence[Mapping[str, object]],
    evaluation_routes: Sequence[Mapping[str, object]],
    maximum_valid_blocks: object,
    maximum_invalid_attempts: object,
) -> dict[str, object]:
    """Derive all plan call bounds from route rows rather than constants."""

    valid_blocks = _require_int(
        maximum_valid_blocks,
        field="maximum_valid_blocks",
        minimum=1,
    )
    invalid_attempts = _require_int(
        maximum_invalid_attempts,
        field="maximum_invalid_attempts",
        minimum=0,
    )
    grouped: dict[str, list[Mapping[str, object]]] = {arm: [] for arm in ARMS}
    seen_routes: set[str] = set()
    for row in terminal_routes:
        if not isinstance(row, Mapping) or set(row) != {
            "arm",
            "route_id",
            "role_sequence",
            "call_slots",
            "call_count",
            "completed",
        }:
            raise DecisionLockError("terminal_route_invalid")
        arm = row["arm"]
        route_id = row["route_id"]
        if arm not in grouped or not isinstance(route_id, str) or route_id in seen_routes:
            raise DecisionLockError("terminal_route_invalid")
        seen_routes.add(route_id)
        count = _require_int(row["call_count"], field="route.call_count", minimum=0)
        if not isinstance(row["call_slots"], list) or len(row["call_slots"]) != count:
            raise DecisionLockError("terminal_route_invalid")
        if not isinstance(row["completed"], bool):
            raise DecisionLockError("terminal_route_invalid")
        grouped[str(arm)].append(row)
    if any(not rows for rows in grouped.values()):
        raise DecisionLockError("terminal_route_arm_missing")
    evaluation_counts = []
    for row in evaluation_routes:
        if not isinstance(row, Mapping):
            raise DecisionLockError("evaluation_route_invalid")
        evaluation_counts.append(
            _require_int(row.get("call_count"), field="evaluation.call_count", minimum=0)
        )
    if not evaluation_counts:
        raise DecisionLockError("evaluation_route_missing")
    treatment_min = sum(
        min(
            _require_int(row["call_count"], field="route.call_count", minimum=0)
            for row in grouped[arm]
        )
        for arm in ARMS
    )
    treatment_max = sum(
        max(
            _require_int(row["call_count"], field="route.call_count", minimum=0)
            for row in grouped[arm]
        )
        for arm in ARMS
    )
    completed_min = sum(
        min(
            _require_int(row["call_count"], field="route.call_count", minimum=0)
            for row in grouped[arm]
            if row["completed"] is True
        )
        for arm in ARMS
    )
    completed_max = sum(
        max(
            _require_int(row["call_count"], field="route.call_count", minimum=0)
            for row in grouped[arm]
            if row["completed"] is True
        )
        for arm in ARMS
    )
    valid_min = treatment_min + min(evaluation_counts)
    valid_max = treatment_max + max(evaluation_counts)
    completed_valid_min = completed_min + min(evaluation_counts)
    completed_valid_max = completed_max + max(evaluation_counts)
    return {
        "valid_block": {"minimum": valid_min, "maximum": valid_max},
        "completed_treatment_valid_block": {
            "minimum": completed_valid_min,
            "maximum": completed_valid_max,
        },
        "maximum_valid_blocks": {
            "minimum": valid_min * valid_blocks,
            "maximum": valid_max * valid_blocks,
        },
        "completed_treatment_maximum_valid_blocks": {
            "minimum": completed_valid_min * valid_blocks,
            "maximum": completed_valid_max * valid_blocks,
        },
        "absolute_with_invalid_attempt_capacity": valid_max
        * (valid_blocks + invalid_attempts),
    }


def _validate_sha256(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise DecisionLockError("digest_invalid", field)
    return value


def _key_sort(
    *,
    seed: bytes,
    attempt_id: str,
    domain: str,
    items: Sequence[str],
) -> list[str]:
    def key(item: str) -> tuple[bytes, str]:
        payload = (
            _RANDOMIZATION_ROOT
            + domain.encode("ascii")
            + b"\0"
            + seed
            + b"\0"
            + attempt_id.encode("ascii")
            + b"\0"
            + item.encode("ascii")
        )
        return hashlib.sha256(payload).digest(), item

    return sorted(items, key=key)


def _generate_randomization_manifest(seed_sha256: str) -> dict[str, object]:
    seed_text = _validate_sha256(seed_sha256, field="seed_sha256")
    seed = bytes.fromhex(seed_text.removeprefix("sha256:"))
    attempts = [
        {
            "attempt_id": attempt_id,
            "arm_order": _key_sort(
                seed=seed,
                attempt_id=attempt_id,
                domain=_ARM_DOMAIN,
                items=ARMS,
            ),
            "opaque_package_order": _key_sort(
                seed=seed,
                attempt_id=attempt_id,
                domain=_PACKAGE_DOMAIN,
                items=OPAQUE_PACKAGES,
            ),
        }
        for attempt_id in ATTEMPT_IDS
    ]
    return {
        "schema_version": "es_randomization_manifest.v1",
        "algorithm": "sha256-domain-separated-key-sort.v1",
        "selection_policy": "PRECOMMITTED_FIXED_FOUR_ATTEMPTS",
        "seed_sha256": seed_text,
        "domains": {
            "arm_order": _ARM_DOMAIN,
            "opaque_package_order": _PACKAGE_DOMAIN,
        },
        "arms": list(ARMS),
        "opaque_packages": list(OPAQUE_PACKAGES),
        "attempt_count": len(ATTEMPT_IDS),
        "attempts": attempts,
    }


def generate_randomization_manifest(seed_sha256: str) -> dict[str, object]:
    """Generate the four frozen attempt permutations by domain-separated key sort."""

    result = _generate_randomization_manifest(seed_sha256)
    _validate_schema(result, _RANDOMIZATION_SCHEMA_PATH, "randomization_schema_invalid")
    return result


def _load_schema(path: Path) -> dict[str, object]:
    return load_canonical_json(path)


def _validate_schema(value: object, path: Path, code: str) -> None:
    schema = _load_schema(path)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    if errors:
        raise DecisionLockError(code, errors[0].message)


def validate_randomization_manifest(
    value: object,
) -> dict[str, object]:
    """Validate cardinality, domains, permutations, and every SHA key-sort row."""

    _validate_json_value(value, label="randomization_manifest")
    _validate_schema(
        value,
        _RANDOMIZATION_SCHEMA_PATH,
        "randomization_schema_invalid",
    )
    if not isinstance(value, dict):
        raise DecisionLockError("randomization_manifest_invalid")
    expected = _generate_randomization_manifest(str(value["seed_sha256"]))
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise DecisionLockError("randomization_manifest_mismatch")
    return copy.deepcopy(value)


def default_authored_choices() -> dict[str, object]:
    """Return the predeclared scientific choices awaiting later owner adoption."""

    return {
        "purpose": "INTERNAL_ROADMAP_ADMISSION_SCREEN",
        "claim_class": "TASK_SPECIFIC_EXPLORATORY",
        "primary_contrast": {
            "favorable": "RICH",
            "reference": "DIRECT",
        },
        "sampling_unit": "ONE_FOUR_ARM_FRESH_ALLOCATION_F1_BLOCK",
        "budget_policy": "EQUAL_STRUCTURE_FIXED_ROLE_AND_CORRECTION_BOUNDS",
        "null_non_tied_rich_win_probability": _fraction_record(Fraction(1, 2)),
        "minimum_practical_non_tied_rich_win_probability": _fraction_record(
            Fraction(9, 10)
        ),
        "one_sided_alpha": _fraction_record(Fraction(1, 4)),
        "desired_power": _fraction_record(Fraction(4, 5)),
        "maximum_planning_tie_indeterminate_rate": _fraction_record(
            Fraction(1, 4)
        ),
        "minimum_accrual_assurance": _fraction_record(Fraction(4, 5)),
        "maximum_invalid_attempts": 1,
        "maximum_median_rich_direct_token_cost_ratio": "4",
        "unknown_accounting": "INVALID_BLOCK_NO_IMPUTATION",
        "viability_rule": "RICH_TREATMENT_FAILURES_LTE_DIRECT",
    }


def _fraction_from_record(value: object, *, field: str) -> Fraction:
    if not isinstance(value, dict) or set(value) != {"numerator", "denominator"}:
        raise DecisionLockError("rational_invalid", field)
    numerator = _require_int(value["numerator"], field=f"{field}.numerator")
    denominator = _require_int(
        value["denominator"], field=f"{field}.denominator", minimum=1
    )
    if math.gcd(numerator, denominator) != 1:
        raise DecisionLockError("rational_not_reduced", field)
    return Fraction(numerator, denominator)


def _validate_bindings(bindings: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(bindings, Mapping) or set(bindings) != _BINDING_KEYS:
        raise DecisionLockError("binding_keys_invalid")
    return {
        key: _validate_sha256(bindings[key], field=key) for key in sorted(_BINDING_KEYS)
    }


def _receipt_call_slots(
    terminal_routes: Sequence[Mapping[str, object]],
    evaluation_routes: Sequence[Mapping[str, object]],
) -> list[str]:
    slots: list[str] = []
    for arm in ARMS:
        arm_routes = [row for row in terminal_routes if row["arm"] == arm]
        longest = max(
            arm_routes,
            key=lambda row: _require_int(
                row["call_count"], field="route.call_count", minimum=0
            ),
        )
        arm_slots = longest["call_slots"]
        if not isinstance(arm_slots, list):
            raise DecisionLockError("receipt_call_slot_catalog_invalid")
        slots.extend(str(slot) for slot in arm_slots)
    longest_eval = max(
        evaluation_routes,
        key=lambda row: _require_int(
            row["call_count"], field="evaluation.call_count", minimum=0
        ),
    )
    evaluation_slots = longest_eval["call_slots"]
    if not isinstance(evaluation_slots, list):
        raise DecisionLockError("receipt_call_slot_catalog_invalid")
    slots.extend(str(slot) for slot in evaluation_slots)
    if len(slots) != 22 or len(set(slots)) != 22:
        raise DecisionLockError("receipt_call_slot_catalog_invalid")
    return slots


def build_decision_lock(
    *,
    bindings: Mapping[str, object],
    randomization_manifest: Mapping[str, object],
) -> dict[str, Any]:
    """Build the exact ES lock from frozen asset bindings and one schedule."""

    checked_schedule = validate_randomization_manifest(randomization_manifest)
    checked_bindings = _validate_bindings(bindings)
    schedule_digest = _sha256(canonical_json_bytes(checked_schedule))
    if checked_bindings["randomization_manifest_sha256"] != schedule_digest:
        raise DecisionLockError("randomization_digest_mismatch")
    authored = default_authored_choices()
    operating = derive_operating_characteristics(
        null_rate=_fraction_from_record(
            authored["null_non_tied_rich_win_probability"],
            field="null_non_tied_rich_win_probability",
        ),
        target_rate=_fraction_from_record(
            authored["minimum_practical_non_tied_rich_win_probability"],
            field="minimum_practical_non_tied_rich_win_probability",
        ),
        alpha=_fraction_from_record(
            authored["one_sided_alpha"], field="one_sided_alpha"
        ),
        desired_power=_fraction_from_record(
            authored["desired_power"], field="desired_power"
        ),
        maximum_tie_indeterminate_rate=_fraction_from_record(
            authored["maximum_planning_tie_indeterminate_rate"],
            field="maximum_planning_tie_indeterminate_rate",
        ),
        minimum_accrual_assurance=_fraction_from_record(
            authored["minimum_accrual_assurance"],
            field="minimum_accrual_assurance",
        ),
    )
    terminal_routes = derive_terminal_routes()
    evaluation_routes = derive_evaluation_routes()
    call_bounds = derive_call_bounds(
        terminal_routes=terminal_routes,
        evaluation_routes=evaluation_routes,
        maximum_valid_blocks=operating["maximum_valid_blocks"],
        maximum_invalid_attempts=authored["maximum_invalid_attempts"],
    )
    lock: dict[str, Any] = {
        "schema_version": "decision_lock.v1",
        "authored_choices": authored,
        "provider_contract": {
            "provider_family": "codex-cli",
            "version": "codex-cli 0.145.0",
            "cost_unit": "CODEX_REPORTED_TOTAL_TOKENS",
            "required_flags": [
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
            ],
            "metering_flag": "--json",
            "fresh_sessions": True,
            "resume_forbidden": True,
            "session_reuse": "FORBIDDEN",
            "launcher_sha256": "sha256:134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477",
        },
        "route_contract": {
            "arms": list(ARMS),
            "terminal_routes": terminal_routes,
            "evaluation_routes": evaluation_routes,
            "receipt_call_slots": _receipt_call_slots(
                terminal_routes, evaluation_routes
            ),
        },
        "derived": {
            "operating_characteristics": operating,
            "call_bounds": call_bounds,
        },
        "schedule": {
            "selection_policy": "PRECOMMITTED_FIXED_FOUR_ATTEMPTS",
            "manifest_sha256": schedule_digest,
            "attempt_ids": list(ATTEMPT_IDS),
        },
        "bindings": checked_bindings,
        "outcome_contract": {
            "primary_domain": ["RICH", "DIRECT", "TIE", "INDETERMINATE"],
            "study_outcomes": [
                "SCREEN_PASSED",
                "SCREEN_NOT_PASSED",
                "INSUFFICIENT_EVIDENCE",
                "STOP_ES_INVALID",
            ],
            "unknown_cost_accounting": "INVALID_BLOCK_NO_IMPUTATION",
            "attempt_resume": "FORBIDDEN",
            "invalid_attempt_capacity": 1,
        },
        "claim_limits": [
            "TASK_SPECIFIC_INTERNAL_SCREEN_ONLY",
            "NO_GENERAL_OR_CONFIRMATORY_SUPERIORITY_CLAIM",
            "NO_USD_BILLING_OR_MARGINAL_SUBSCRIPTION_COST_CLAIM",
            "NO_PROMOTION_OR_CANONICAL_PRODUCT_MERGE_AUTHORITY",
            "NO_E3_IMPLEMENTATION_AUTHORITY",
        ],
    }
    _validate_schema(lock, _DECISION_LOCK_SCHEMA_PATH, "decision_lock_schema_invalid")
    return lock


def validate_decision_lock(
    value: object,
    *,
    randomization_manifest: Mapping[str, object],
    expected_bindings: Mapping[str, object],
) -> dict[str, object]:
    """Rebuild the selected lock and reject every unbound or derived byte."""

    _validate_json_value(value, label="decision_lock")
    _validate_schema(value, _DECISION_LOCK_SCHEMA_PATH, "decision_lock_schema_invalid")
    checked_bindings = _validate_bindings(expected_bindings)
    expected = build_decision_lock(
        bindings=checked_bindings,
        randomization_manifest=randomization_manifest,
    )
    if not isinstance(value, dict) or canonical_json_bytes(value) != canonical_json_bytes(
        expected
    ):
        raise DecisionLockError("decision_lock_mismatch")
    return copy.deepcopy(value)


def decision_lock_digest(value: object) -> str:
    """Return the external canonical envelope digest for a validated lock value."""

    return _sha256(canonical_json_bytes(value))


__all__ = [
    "ARMS",
    "ATTEMPT_IDS",
    "DecisionLockError",
    "build_decision_lock",
    "canonical_json_bytes",
    "decision_lock_digest",
    "default_authored_choices",
    "derive_call_bounds",
    "derive_evaluation_routes",
    "derive_operating_characteristics",
    "derive_terminal_routes",
    "exact_binomial_tail",
    "generate_randomization_manifest",
    "load_canonical_json",
    "parse_canonical_decimal",
    "validate_decision_lock",
    "validate_randomization_manifest",
]
