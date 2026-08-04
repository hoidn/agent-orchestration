from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from fractions import Fraction
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _load_decision_lock() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/experiments/es/decision_lock.py"
    spec = importlib.util.spec_from_file_location("es_decision_lock", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision_lock = _load_decision_lock()


def test_decision_lock_module_is_present() -> None:
    assert (REPOSITORY_ROOT / "scripts/experiments/es/decision_lock.py").is_file()


def _sha(fill: str) -> str:
    return "sha256:" + fill * 64


def _bindings() -> dict[str, str]:
    return {
        "arm_workflow_sha256": _sha("1"),
        "environment_lock_sha256": _sha("2"),
        "evaluator_fixture_manifest_sha256": _sha("3"),
        "prompt_manifest_sha256": _sha("4"),
        "randomization_manifest_sha256": _sha("5"),
        "report_schema_sha256": _sha("6"),
        "source_projection_manifest_sha256": _sha("7"),
        "task_profile_sha256": _sha("8"),
        "task_seed_manifest_sha256": _sha("9"),
    }


def _schedule() -> dict[str, object]:
    schedule = decision_lock.generate_randomization_manifest(_sha("a"))
    bindings = _bindings()
    bindings["randomization_manifest_sha256"] = (
        "sha256:"
        + hashlib.sha256(decision_lock.canonical_json_bytes(schedule)).hexdigest()
    )
    return schedule


def _lock_and_inputs() -> tuple[
    dict[str, Any], dict[str, object], dict[str, str]
]:
    schedule = _schedule()
    bindings = _bindings()
    bindings["randomization_manifest_sha256"] = (
        "sha256:"
        + hashlib.sha256(decision_lock.canonical_json_bytes(schedule)).hexdigest()
    )
    lock = decision_lock.build_decision_lock(
        bindings=bindings,
        randomization_manifest=schedule,
    )
    return lock, schedule, bindings


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", Fraction(0)),
        ("1", Fraction(1)),
        ("12", Fraction(12)),
        ("0.05", Fraction(1, 20)),
        ("0.25", Fraction(1, 4)),
        ("0.9", Fraction(9, 10)),
        ("1.25", Fraction(5, 4)),
    ],
)
def test_parse_canonical_decimal_returns_exact_fractions(
    text: str,
    expected: Fraction,
) -> None:
    assert decision_lock.parse_canonical_decimal(text) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".5",
        "01",
        "00.1",
        "1.",
        "1.0",
        "4.0",
        "0.50",
        "1e-1",
        "+1",
        "-1",
        " 1",
        1,
        0.5,
        True,
    ],
)
def test_parse_canonical_decimal_rejects_every_noncanonical_spelling(
    value: object,
) -> None:
    with pytest.raises(decision_lock.DecisionLockError, match="^decimal_noncanonical"):
        decision_lock.parse_canonical_decimal(value)


def test_exact_binomial_tail_uses_reduced_exact_rationals() -> None:
    assert decision_lock.exact_binomial_tail(2, 2, Fraction(1, 2)) == Fraction(1, 4)
    assert decision_lock.exact_binomial_tail(2, 2, Fraction(9, 10)) == Fraction(81, 100)
    assert decision_lock.exact_binomial_tail(8, 7, Fraction(1, 2)) == Fraction(9, 256)
    assert decision_lock.exact_binomial_tail(8, 7, Fraction(9, 10)) == Fraction(
        81310473, 100000000
    )


@pytest.mark.parametrize(
    ("trials", "threshold", "probability"),
    [
        (True, 1, Fraction(1, 2)),
        (1, True, Fraction(1, 2)),
        (0, 0, Fraction(1, 2)),
        (2, -1, Fraction(1, 2)),
        (2, 3, Fraction(1, 2)),
        (2, 1, Fraction(-1, 2)),
        (2, 1, Fraction(3, 2)),
    ],
)
def test_exact_binomial_tail_rejects_invalid_domains(
    trials: object,
    threshold: object,
    probability: Fraction,
) -> None:
    with pytest.raises(decision_lock.DecisionLockError):
        decision_lock.exact_binomial_tail(trials, threshold, probability)


def test_selected_operating_characteristics_are_mechanically_derived() -> None:
    result = decision_lock.derive_operating_characteristics(
        null_rate=Fraction(1, 2),
        target_rate=Fraction(9, 10),
        alpha=Fraction(1, 4),
        desired_power=Fraction(4, 5),
        maximum_tie_indeterminate_rate=Fraction(1, 4),
        minimum_accrual_assurance=Fraction(4, 5),
    )

    assert result == {
        "required_non_tied_comparisons": 2,
        "critical_rich_wins": 2,
        "null_tail": {"denominator": 4, "numerator": 1},
        "achieved_power": {"denominator": 100, "numerator": 81},
        "maximum_valid_blocks": 3,
        "accrual_probability": {"denominator": 32, "numerator": 27},
        "minimality": {
            "comparison_predecessor": {
                "achieved_power": {"denominator": 10, "numerator": 9},
                "critical_rich_wins": 1,
                "null_tail": {"denominator": 2, "numerator": 1},
                "required_non_tied_comparisons": 1,
            },
            "valid_block_predecessor": {
                "accrual_probability": {"denominator": 16, "numerator": 9},
                "maximum_valid_blocks": 2,
            },
        },
    }


def test_alpha_005_known_vector_stays_regression_locked() -> None:
    result = decision_lock.derive_operating_characteristics(
        null_rate=Fraction(1, 2),
        target_rate=Fraction(9, 10),
        alpha=Fraction(1, 20),
        desired_power=Fraction(4, 5),
        maximum_tie_indeterminate_rate=Fraction(1, 4),
        minimum_accrual_assurance=Fraction(4, 5),
    )

    assert result["required_non_tied_comparisons"] == 8
    assert result["critical_rich_wins"] == 7
    assert result["null_tail"] == {"denominator": 256, "numerator": 9}
    assert result["achieved_power"] == {
        "denominator": 100000000,
        "numerator": 81310473,
    }
    assert result["maximum_valid_blocks"] == 12
    assert result["accrual_probability"] == {
        "denominator": 8388608,
        "numerator": 7066197,
    }
    assert result["minimality"]["valid_block_predecessor"] == {
        "accrual_probability": {"denominator": 524288, "numerator": 373977},
        "maximum_valid_blocks": 11,
    }


def test_terminal_route_table_preserves_the_exact_22_prefix_closure() -> None:
    routes = decision_lock.derive_terminal_routes()

    actual = [
        (
            row["arm"],
            row["route_id"],
            tuple(row["role_sequence"]),
            tuple(row["call_slots"]),
            row["call_count"],
            row["completed"],
        )
        for row in routes
        if not str(row["route_id"]).endswith(".FAILED_AT_FINAL_CALL")
    ]
    assert actual == [
        ("DIRECT", "DIRECT.EMPTY", (), (), 0, False),
        ("DIRECT", "DIRECT.I", ("I",), ("DIRECT.I",), 1, True),
        ("DESIGN_QA", "DESIGN_QA.EMPTY", (), (), 0, False),
        ("DESIGN_QA", "DESIGN_QA.D", ("D",), ("DESIGN_QA.D",), 1, False),
        (
            "DESIGN_QA",
            "DESIGN_QA.D_DR",
            ("D", "DR"),
            ("DESIGN_QA.D", "DESIGN_QA.DR"),
            2,
            False,
        ),
        (
            "DESIGN_QA",
            "DESIGN_QA.D_DR_I",
            ("D", "DR", "I"),
            ("DESIGN_QA.D", "DESIGN_QA.DR", "DESIGN_QA.I"),
            3,
            True,
        ),
        (
            "DESIGN_QA",
            "DESIGN_QA.D_DR_DREV",
            ("D", "DR", "DREV"),
            ("DESIGN_QA.D", "DESIGN_QA.DR", "DESIGN_QA.DREV"),
            3,
            False,
        ),
        (
            "DESIGN_QA",
            "DESIGN_QA.D_DR_DREV_I",
            ("D", "DR", "DREV", "I"),
            (
                "DESIGN_QA.D",
                "DESIGN_QA.DR",
                "DESIGN_QA.DREV",
                "DESIGN_QA.I",
            ),
            4,
            True,
        ),
        ("PRODUCT_QA", "PRODUCT_QA.EMPTY", (), (), 0, False),
        ("PRODUCT_QA", "PRODUCT_QA.I", ("I",), ("PRODUCT_QA.I",), 1, False),
        (
            "PRODUCT_QA",
            "PRODUCT_QA.I_PR",
            ("I", "PR"),
            ("PRODUCT_QA.I", "PRODUCT_QA.PR"),
            2,
            True,
        ),
        (
            "PRODUCT_QA",
            "PRODUCT_QA.I_PR_FIX",
            ("I", "PR", "FIX"),
            ("PRODUCT_QA.I", "PRODUCT_QA.PR", "PRODUCT_QA.FIX"),
            3,
            True,
        ),
        ("RICH", "RICH.EMPTY", (), (), 0, False),
        ("RICH", "RICH.D", ("D",), ("RICH.D",), 1, False),
        (
            "RICH",
            "RICH.D_DR",
            ("D", "DR"),
            ("RICH.D", "RICH.DR"),
            2,
            False,
        ),
        (
            "RICH",
            "RICH.D_DR_I",
            ("D", "DR", "I"),
            ("RICH.D", "RICH.DR", "RICH.I"),
            3,
            False,
        ),
        (
            "RICH",
            "RICH.D_DR_I_PR",
            ("D", "DR", "I", "PR"),
            ("RICH.D", "RICH.DR", "RICH.I", "RICH.PR"),
            4,
            True,
        ),
        (
            "RICH",
            "RICH.D_DR_I_PR_FIX",
            ("D", "DR", "I", "PR", "FIX"),
            ("RICH.D", "RICH.DR", "RICH.I", "RICH.PR", "RICH.FIX"),
            5,
            True,
        ),
        (
            "RICH",
            "RICH.D_DR_DREV",
            ("D", "DR", "DREV"),
            ("RICH.D", "RICH.DR", "RICH.DREV"),
            3,
            False,
        ),
        (
            "RICH",
            "RICH.D_DR_DREV_I",
            ("D", "DR", "DREV", "I"),
            ("RICH.D", "RICH.DR", "RICH.DREV", "RICH.I"),
            4,
            False,
        ),
        (
            "RICH",
            "RICH.D_DR_DREV_I_PR",
            ("D", "DR", "DREV", "I", "PR"),
            ("RICH.D", "RICH.DR", "RICH.DREV", "RICH.I", "RICH.PR"),
            5,
            True,
        ),
        (
            "RICH",
            "RICH.D_DR_DREV_I_PR_FIX",
            ("D", "DR", "DREV", "I", "PR", "FIX"),
            (
                "RICH.D",
                "RICH.DR",
                "RICH.DREV",
                "RICH.I",
                "RICH.PR",
                "RICH.FIX",
            ),
            6,
            True,
        ),
    ]


@pytest.mark.parametrize(
    ("arm", "roles"),
    [
        ("DIRECT", ("I",)),
        ("DESIGN_QA", ("D", "DR", "I")),
        ("DESIGN_QA", ("D", "DR", "DREV", "I")),
        ("PRODUCT_QA", ("I", "PR")),
        ("PRODUCT_QA", ("I", "PR", "FIX")),
        ("RICH", ("D", "DR", "I", "PR")),
        ("RICH", ("D", "DR", "I", "PR", "FIX")),
        ("RICH", ("D", "DR", "DREV", "I", "PR")),
        ("RICH", ("D", "DR", "DREV", "I", "PR", "FIX")),
    ],
)
def test_success_completing_prefix_has_distinct_final_call_failure_route(
    arm: str,
    roles: tuple[str, ...],
) -> None:
    suffix = "_".join(roles)
    matching = [
        row
        for row in decision_lock.derive_terminal_routes()
        if row["arm"] == arm and tuple(row["role_sequence"]) == roles
    ]

    assert [(row["route_id"], row["completed"]) for row in matching] == [
        (f"{arm}.{suffix}", True),
        (f"{arm}.{suffix}.FAILED_AT_FINAL_CALL", False),
    ]


def test_evaluation_routes_and_all_aggregate_call_bounds_are_derived() -> None:
    evaluation = decision_lock.derive_evaluation_routes()
    bounds = decision_lock.derive_call_bounds(
        terminal_routes=decision_lock.derive_terminal_routes(),
        evaluation_routes=evaluation,
        maximum_valid_blocks=3,
        maximum_invalid_attempts=1,
    )

    assert [row["call_count"] for row in evaluation] == [7, 8]
    assert evaluation[0]["call_slots"] == [
        "EVAL.SCORER_DIRECT",
        "EVAL.SCORER_DESIGN_QA",
        "EVAL.SCORER_PRODUCT_QA",
        "EVAL.SCORER_RICH",
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
        "EVAL.INTEGRATED_REVIEW",
    ]
    assert evaluation[1]["call_slots"][-2:] == [
        "EVAL.ADJUDICATOR",
        "EVAL.INTEGRATED_REVIEW",
    ]
    assert bounds == {
        "valid_block": {"maximum": 22, "minimum": 7},
        "completed_treatment_valid_block": {"maximum": 22, "minimum": 17},
        "maximum_valid_blocks": {"maximum": 66, "minimum": 21},
        "completed_treatment_maximum_valid_blocks": {
            "maximum": 66,
            "minimum": 51,
        },
        "absolute_with_invalid_attempt_capacity": 88,
    }


def test_randomization_schedule_is_four_domain_separated_key_sorted_permutations() -> None:
    manifest = decision_lock.generate_randomization_manifest(_sha("a"))

    assert manifest == decision_lock.generate_randomization_manifest(_sha("a"))
    assert manifest["schema_version"] == "es_randomization_manifest.v1"
    assert manifest["algorithm"] == "sha256-domain-separated-key-sort.v1"
    assert manifest["attempt_count"] == 4
    assert [row["attempt_id"] for row in manifest["attempts"]] == [
        "ES-ATTEMPT-01",
        "ES-ATTEMPT-02",
        "ES-ATTEMPT-03",
        "ES-ATTEMPT-04",
    ]
    for row in manifest["attempts"]:
        assert set(row["arm_order"]) == {
            "DIRECT",
            "DESIGN_QA",
            "PRODUCT_QA",
            "RICH",
        }
        assert set(row["opaque_package_order"]) == {
            "PACKAGE-01",
            "PACKAGE-02",
            "PACKAGE-03",
            "PACKAGE-04",
        }
    assert manifest["attempts"] == [
        {
            "arm_order": ["DIRECT", "DESIGN_QA", "RICH", "PRODUCT_QA"],
            "attempt_id": "ES-ATTEMPT-01",
            "opaque_package_order": [
                "PACKAGE-02",
                "PACKAGE-01",
                "PACKAGE-04",
                "PACKAGE-03",
            ],
        },
        {
            "arm_order": ["RICH", "PRODUCT_QA", "DIRECT", "DESIGN_QA"],
            "attempt_id": "ES-ATTEMPT-02",
            "opaque_package_order": [
                "PACKAGE-04",
                "PACKAGE-01",
                "PACKAGE-03",
                "PACKAGE-02",
            ],
        },
        {
            "arm_order": ["DESIGN_QA", "PRODUCT_QA", "RICH", "DIRECT"],
            "attempt_id": "ES-ATTEMPT-03",
            "opaque_package_order": [
                "PACKAGE-02",
                "PACKAGE-04",
                "PACKAGE-03",
                "PACKAGE-01",
            ],
        },
        {
            "arm_order": ["PRODUCT_QA", "DIRECT", "DESIGN_QA", "RICH"],
            "attempt_id": "ES-ATTEMPT-04",
            "opaque_package_order": [
                "PACKAGE-04",
                "PACKAGE-03",
                "PACKAGE-01",
                "PACKAGE-02",
            ],
        },
    ]


def test_randomization_manifest_validation_rejects_every_schedule_tamper() -> None:
    manifest = decision_lock.generate_randomization_manifest(_sha("a"))
    decision_lock.validate_randomization_manifest(manifest)

    mutations: list[object] = []
    duplicate_arm = copy.deepcopy(manifest)
    duplicate_arm["attempts"][0]["arm_order"][0] = duplicate_arm["attempts"][0][
        "arm_order"
    ][1]
    mutations.append(duplicate_arm)
    unknown_package = copy.deepcopy(manifest)
    unknown_package["attempts"][1]["opaque_package_order"][0] = "UNKNOWN"
    mutations.append(unknown_package)
    missing_attempt = copy.deepcopy(manifest)
    missing_attempt["attempts"].pop()
    mutations.append(missing_attempt)
    adaptive = copy.deepcopy(manifest)
    adaptive["selection_policy"] = "adaptive"
    mutations.append(adaptive)
    reordered = copy.deepcopy(manifest)
    reordered["attempts"][0]["arm_order"].reverse()
    mutations.append(reordered)

    for candidate in mutations:
        with pytest.raises(decision_lock.DecisionLockError):
            decision_lock.validate_randomization_manifest(candidate)


def test_full_randomization_manifest_leaf_tamper_matrix_fails_closed() -> None:
    manifest = decision_lock.generate_randomization_manifest(_sha("a"))
    paths = _leaf_paths(manifest)
    assert len(paths) == 51

    for path in paths:
        candidate = copy.deepcopy(manifest)
        cursor = candidate
        for part in path:
            cursor = cursor[part]  # type: ignore[index]
        _set_path(candidate, path, _tamper_leaf(cursor))
        with pytest.raises(decision_lock.DecisionLockError):
            decision_lock.validate_randomization_manifest(candidate)


def test_build_and_validate_lock_has_no_self_hash_and_exact_selected_vectors() -> None:
    lock, schedule, bindings = _lock_and_inputs()
    schema = json.loads(
        (
            REPOSITORY_ROOT
            / "experiments/orc_effectiveness/f1_es/decision-lock.schema.json"
        ).read_text()
    )
    Draft202012Validator(schema).validate(lock)

    assert "lock_digest" not in lock
    assert lock["schema_version"] == "decision_lock.v2"
    assert lock["authored_choices"] == decision_lock.default_authored_choices()
    assert lock["derived"]["operating_characteristics"]["null_tail"] == {
        "denominator": 4,
        "numerator": 1,
    }
    assert lock["derived"]["call_bounds"]["absolute_with_invalid_attempt_capacity"] == 88
    assert len(lock["route_contract"]["terminal_routes"]) == 31
    assert len(lock["route_contract"]["receipt_call_slots"]) == 22
    assert lock["bindings"] == bindings
    assert lock["schedule"] == {
        "attempt_ids": [
            "ES-ATTEMPT-01",
            "ES-ATTEMPT-02",
            "ES-ATTEMPT-03",
            "ES-ATTEMPT-04",
        ],
        "manifest_sha256": bindings["randomization_manifest_sha256"],
        "selection_policy": "PRECOMMITTED_FIXED_FOUR_ATTEMPTS",
    }
    assert decision_lock.validate_decision_lock(
        lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    ) == lock
    assert decision_lock.decision_lock_digest(lock).startswith("sha256:")


def test_decision_lock_v1_is_not_reinterpreted_as_v2() -> None:
    lock, schedule, bindings = _lock_and_inputs()
    lock["schema_version"] = "decision_lock.v1"

    with pytest.raises(decision_lock.DecisionLockError):
        decision_lock.validate_decision_lock(
            lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )


def _leaf_paths(value: object, prefix: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    if isinstance(value, dict):
        paths: list[tuple[object, ...]] = []
        for key in sorted(value):
            paths.extend(_leaf_paths(value[key], prefix + (key,)))
        return paths
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_leaf_paths(item, prefix + (index,)))
        return paths
    return [prefix]


def _tamper_leaf(value: object) -> object:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str) and value.startswith("sha256:"):
        return "sha256:" + ("0" if value[-1] != "0" else "1") + value[8:-1] + value[-1]
    if isinstance(value, str):
        return value + "_TAMPER"
    raise AssertionError(f"unexpected leaf {value!r}")


def _set_path(root: object, path: tuple[object, ...], value: object) -> None:
    cursor = root
    for part in path[:-1]:
        cursor = cursor[part]  # type: ignore[index]
    cursor[path[-1]] = value  # type: ignore[index]


def test_full_lock_leaf_tamper_matrix_fails_closed() -> None:
    lock, schedule, bindings = _lock_and_inputs()
    paths = _leaf_paths(lock)
    assert len(paths) >= 200

    for path in paths:
        candidate = copy.deepcopy(lock)
        cursor = candidate
        for part in path:
            cursor = cursor[part]  # type: ignore[index]
        _set_path(candidate, path, _tamper_leaf(cursor))
        with pytest.raises(decision_lock.DecisionLockError):
            decision_lock.validate_decision_lock(
                candidate,
                randomization_manifest=schedule,
                expected_bindings=bindings,
            )


def test_lock_rejects_open_fields_floats_bool_integers_and_binding_drift() -> None:
    lock, schedule, bindings = _lock_and_inputs()
    cases: list[dict[str, object]] = []
    open_field = copy.deepcopy(lock)
    open_field["unexpected"] = True
    cases.append(open_field)
    float_value = copy.deepcopy(lock)
    float_value["derived"]["call_bounds"]["valid_block"]["minimum"] = 7.0
    cases.append(float_value)
    bool_integer = copy.deepcopy(lock)
    bool_integer["derived"]["call_bounds"]["valid_block"]["minimum"] = True
    cases.append(bool_integer)
    duplicate_arm = copy.deepcopy(lock)
    duplicate_arm["route_contract"]["arms"][1] = "DIRECT"
    cases.append(duplicate_arm)
    unknown_arm = copy.deepcopy(lock)
    unknown_arm["route_contract"]["terminal_routes"][0]["arm"] = "UNKNOWN"
    cases.append(unknown_arm)
    reused_sessions = copy.deepcopy(lock)
    reused_sessions["provider_contract"]["session_reuse"] = "PERMITTED"
    cases.append(reused_sessions)
    adaptive = copy.deepcopy(lock)
    adaptive["schedule"]["selection_policy"] = "ADAPTIVE"
    cases.append(adaptive)
    digest_drift = copy.deepcopy(lock)
    digest_drift["bindings"]["task_seed_manifest_sha256"] = _sha("0")
    cases.append(digest_drift)

    for candidate in cases:
        with pytest.raises(decision_lock.DecisionLockError):
            decision_lock.validate_decision_lock(
                candidate,
                randomization_manifest=schedule,
                expected_bindings=bindings,
            )
