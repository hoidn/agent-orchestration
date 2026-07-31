from __future__ import annotations

from types import MappingProxyType

import pytest

from orchestrator._common.validation import (
    closed_mapping,
    is_finite_positive_number,
    nonempty_string,
    ordinary_integer,
)


class _StringSubclass(str):
    pass


class _IntegerSubclass(int):
    pass


class _FloatSubclass(float):
    pass


@pytest.mark.parametrize(
    "value",
    (
        {"a": 1, "b": 2},
        {"b": 2, "a": 1},
        MappingProxyType({"a": 1, "b": 2}),
    ),
)
def test_closed_mapping_accepts_exact_keys_and_preserves_identity(
    value: object,
) -> None:
    assert closed_mapping(value, {"b", "a"}, "payload") is value


@pytest.mark.parametrize(
    "value",
    (
        {"a": 1},
        {"a": 1, "b": 2, "c": 3},
        [("a", 1), ("b", 2)],
        None,
    ),
)
def test_closed_mapping_rejects_nonclosed_values_with_sorted_key_diagnostic(
    value: object,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"^payload must be a closed object with keys \['a', 'b'\]$",
    ):
        closed_mapping(value, {"b", "a"}, "payload")


@pytest.mark.parametrize(
    "value",
    ("text", "é", _StringSubclass("subclass")),
)
def test_nonempty_string_accepts_strings_and_preserves_identity(
    value: str,
) -> None:
    assert nonempty_string(value, "field") is value


@pytest.mark.parametrize("value", ("", None, b"text", 1))
def test_nonempty_string_rejects_other_values_with_typed_diagnostic(
    value: object,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"^field must be a non-empty string$",
    ):
        nonempty_string(value, "field")


@pytest.mark.parametrize(
    ("value", "minimum"),
    (
        (0, 0),
        (1, 0),
        (_IntegerSubclass(2), 1),
        (-1, -1),
    ),
)
def test_ordinary_integer_accepts_nonbool_ints_at_the_boundary(
    value: int,
    minimum: int,
) -> None:
    assert ordinary_integer(value, "count", minimum=minimum) is value


@pytest.mark.parametrize(
    "value",
    (-1, True, False, 1.0, "1", None),
)
def test_ordinary_integer_rejects_invalid_values_with_minimum_diagnostic(
    value: object,
) -> None:
    with pytest.raises(
        ValueError,
        match=r"^count must be an integer >= 0$",
    ):
        ordinary_integer(value, "count", minimum=0)


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (True, False),
        (False, False),
        (float("nan"), False),
        (float("inf"), False),
        (float("-inf"), False),
        (0, False),
        (-1, False),
        (1, True),
        (0.25, True),
        (_IntegerSubclass(2), True),
        (_FloatSubclass(0.5), True),
        ("1", False),
        (None, False),
        ([], False),
        ({}, False),
    ),
)
def test_finite_positive_number_golden_matrix(
    value: object,
    expected: bool,
) -> None:
    assert is_finite_positive_number(value) is expected


def test_finite_positive_number_preserves_huge_integer_overflow() -> None:
    with pytest.raises(
        OverflowError,
        match="int too large to convert to float",
    ):
        is_finite_positive_number(10**309)
