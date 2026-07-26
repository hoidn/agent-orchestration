"""Focused runtime-contract tests for transportable ``Value`` payloads."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_contract_value,
    validate_output_bundle,
    validate_variant_output_bundle,
)


def _value_bundle(*, json_pointer: str = "", value_type: str = "value") -> dict[str, object]:
    return {
        "path": "state/value.json",
        "fields": [
            {
                "name": "__result__",
                "json_pointer": json_pointer,
                "type": value_type,
            }
        ],
    }


def _write_value_bundle(workspace: Path, value: object) -> dict[str, object]:
    bundle_path = workspace / "state" / "value.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    return _value_bundle()


def _assert_exact_json_types(actual: object, expected: object) -> None:
    assert type(actual) is type(expected)
    if isinstance(expected, list):
        assert isinstance(actual, list)
        assert len(actual) == len(expected)
        for actual_item, expected_item in zip(actual, expected, strict=True):
            _assert_exact_json_types(actual_item, expected_item)
    elif isinstance(expected, dict):
        assert isinstance(actual, dict)
        assert list(actual) == list(expected)
        for key in expected:
            _assert_exact_json_types(actual[key], expected[key])


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        7,
        1.5,
        "x",
        [1],
        {"a": 1},
        {
            "null": None,
            "bool": False,
            "integer": 3,
            "float": 2.75,
            "string": "nested",
            "list": [None, {"nested": True}],
        },
    ],
    ids=[
        "null",
        "bool",
        "integer",
        "float",
        "string",
        "list",
        "object",
        "mixed",
    ],
)
def test_validate_output_bundle_accepts_direct_root_value(
    tmp_path: Path,
    value: object,
) -> None:
    bundle = _write_value_bundle(tmp_path, value)

    result = validate_output_bundle(bundle, workspace=tmp_path)["__result__"]

    assert result == value
    _assert_exact_json_types(result, value)


def test_validate_contract_value_rejects_non_transportable_object(
    tmp_path: Path,
) -> None:
    with pytest.raises(OutputContractError) as exc_info:
        validate_contract_value(object(), {"type": "value"}, workspace=tmp_path)

    assert exc_info.value.violations[0]["type"] == "invalid_transportable_value"


@pytest.mark.parametrize(
    ("raw_value", "spec"),
    [
        (
            [None, True, 7, 1.5, "x", [2], {"a": 3}],
            {"type": "list", "items": {"type": "value"}},
        ),
        (
            {"first": None, "second": [True, {"a": 3}]},
            {
                "type": "map",
                "keys": {"type": "string"},
                "values": {"type": "value"},
            },
        ),
    ],
    ids=["list-of-value", "string-map-of-value"],
)
def test_validate_contract_value_accepts_nested_value_descriptors(
    tmp_path: Path,
    raw_value: object,
    spec: dict[str, object],
) -> None:
    result = validate_contract_value(raw_value, spec, workspace=tmp_path)

    assert result == raw_value
    _assert_exact_json_types(result, raw_value)


@pytest.mark.parametrize(
    ("raw_json", "json_pointer", "expected_violation"),
    [
        (None, "", "missing_bundle_file"),
        ("{malformed", "", "invalid_json_document"),
        ("{}", "/missing", "json_pointer_not_found"),
    ],
    ids=["missing-bundle", "malformed-json", "missing-pointer"],
)
def test_validate_output_bundle_value_preserves_bundle_failures(
    tmp_path: Path,
    raw_json: str | None,
    json_pointer: str,
    expected_violation: str,
) -> None:
    if raw_json is not None:
        bundle_path = tmp_path / "state" / "value.json"
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_text(raw_json, encoding="utf-8")

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(
            _value_bundle(json_pointer=json_pointer),
            workspace=tmp_path,
        )

    assert [item["type"] for item in exc_info.value.violations] == [
        expected_violation
    ]


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_validate_output_bundle_rejects_nonstandard_constants_for_value(
    tmp_path: Path,
    constant: str,
) -> None:
    bundle_path = tmp_path / "state" / "value.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(constant + "\n", encoding="utf-8")

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(_value_bundle(), workspace=tmp_path)

    assert [item["type"] for item in exc_info.value.violations] == [
        "invalid_json_document"
    ]


def test_validate_output_bundle_keeps_existing_float_nan_behavior(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "state" / "value.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text("NaN\n", encoding="utf-8")

    result = validate_output_bundle(
        _value_bundle(value_type="float"),
        workspace=tmp_path,
    )["__result__"]

    assert isinstance(result, float)
    assert math.isnan(result)


@pytest.mark.parametrize(
    "invalid_leaf",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        b"bytes",
        (1, 2),
        {1, 2},
        {1: "non-string key"},
        object(),
    ],
    ids=[
        "nan",
        "positive-infinity",
        "negative-infinity",
        "bytes",
        "tuple",
        "set",
        "non-string-key",
        "object",
    ],
)
def test_validate_contract_value_reports_first_escaped_invalid_leaf_path(
    tmp_path: Path,
    invalid_leaf: object,
) -> None:
    raw_value = {
        "items": [
            {"valid": True},
            {"a/b~c": invalid_leaf},
            object(),
        ]
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_contract_value(raw_value, {"type": "value"}, workspace=tmp_path)

    violation = exc_info.value.violations[0]
    assert violation["type"] == "invalid_transportable_value"
    assert violation["context"]["value_path"] == "/items/1/a~1b~0c"


@pytest.mark.parametrize(
    ("document", "spec"),
    [
        (
            "NaN",
            {
                "type": "optional",
                "item": {"type": "value"},
            },
        ),
        (
            "[NaN]",
            {
                "type": "list",
                "items": {"type": "value"},
            },
        ),
        (
            '{"item": NaN}',
            {
                "type": "map",
                "keys": {"type": "string"},
                "values": {"type": "value"},
            },
        ),
    ],
    ids=["optional", "list", "map"],
)
def test_validate_output_bundle_strictly_parses_nested_value_descriptors(
    tmp_path: Path,
    document: str,
    spec: dict[str, object],
) -> None:
    bundle_path = tmp_path / "state" / "value.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(document, encoding="utf-8")
    bundle = _value_bundle()
    bundle["fields"][0].update(spec)  # type: ignore[index, union-attr]

    with pytest.raises(OutputContractError) as exc_info:
        validate_output_bundle(bundle, workspace=tmp_path)

    assert [item["type"] for item in exc_info.value.violations] == [
        "invalid_json_document"
    ]


@pytest.mark.parametrize(
    "descriptor_position",
    ["shared", "selected", "unselected"],
)
def test_validate_variant_bundle_strictly_parses_value_in_every_branch(
    tmp_path: Path,
    descriptor_position: str,
) -> None:
    bundle_path = tmp_path / "state" / "value.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        '{"kind": "completed", "payload": NaN}',
        encoding="utf-8",
    )
    value_field = {
        "name": "payload",
        "json_pointer": "/payload",
        "type": "optional",
        "item": {"type": "value"},
    }
    contract: dict[str, object] = {
        "path": "state/value.json",
        "discriminant": {
            "name": "kind",
            "json_pointer": "/kind",
            "type": "enum",
            "allowed": ["completed", "blocked"],
        },
        "shared_fields": [value_field] if descriptor_position == "shared" else [],
        "variants": {
            "completed": {
                "fields": [value_field]
                if descriptor_position == "selected"
                else [],
            },
            "blocked": {
                "fields": [value_field]
                if descriptor_position == "unselected"
                else [],
            },
        },
    }

    with pytest.raises(OutputContractError) as exc_info:
        validate_variant_output_bundle(contract, workspace=tmp_path)

    assert [item["type"] for item in exc_info.value.violations] == [
        "invalid_json_document"
    ]


def test_validate_variant_bundle_keeps_existing_float_nan_behavior(
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "state" / "value.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        '{"kind": "completed", "score": NaN}',
        encoding="utf-8",
    )
    contract = {
        "path": "state/value.json",
        "discriminant": {
            "name": "kind",
            "json_pointer": "/kind",
            "type": "enum",
            "allowed": ["completed"],
        },
        "variants": {
            "completed": {
                "fields": [
                    {
                        "name": "score",
                        "json_pointer": "/score",
                        "type": "float",
                    }
                ]
            }
        },
    }

    result = validate_variant_output_bundle(contract, workspace=tmp_path)

    assert math.isnan(result["score"])


@pytest.mark.parametrize(
    ("raw_value", "spec", "expected_path"),
    [
        (
            [{"value": True}, {"value": object()}],
            {"type": "list", "items": {"type": "value"}},
            "/1/value",
        ),
        (
            {"items": {"a/b~c": object()}},
            {
                "type": "map",
                "keys": {"type": "string"},
                "values": {"type": "value"},
            },
            "/items/a~1b~0c",
        ),
    ],
    ids=["list-of-value", "map-of-value"],
)
def test_validate_contract_value_prefixes_paths_through_typed_containers(
    tmp_path: Path,
    raw_value: object,
    spec: dict[str, object],
    expected_path: str,
) -> None:
    with pytest.raises(OutputContractError) as exc_info:
        validate_contract_value(raw_value, spec, workspace=tmp_path)

    violation = exc_info.value.violations[0]
    assert violation["type"] == "invalid_transportable_value"
    assert violation["context"]["value_path"] == expected_path


def test_validate_contract_value_preserves_string_nested_under_optional_value(
    tmp_path: Path,
) -> None:
    result = validate_contract_value(
        "  exact text  ",
        {
            "type": "optional",
            "item": {"type": "value"},
        },
        workspace=tmp_path,
    )

    assert result == "  exact text  "


@pytest.mark.parametrize(
    ("raw_value", "spec", "expected"),
    [
        (
            '[null, true, {"count": 2}]',
            {"type": "list", "items": {"type": "value"}},
            [None, True, {"count": 2}],
        ),
        (
            '{"first": null, "second": [true]}',
            {
                "type": "map",
                "keys": {"type": "string"},
                "values": {"type": "value"},
            },
            {"first": None, "second": [True]},
        ),
    ],
    ids=["list", "map"],
)
def test_validate_contract_value_keeps_collection_string_json_decoding(
    tmp_path: Path,
    raw_value: str,
    spec: dict[str, object],
    expected: object,
) -> None:
    assert validate_contract_value(raw_value, spec, workspace=tmp_path) == expected


@pytest.mark.parametrize(
    ("container_kind", "expected_path"),
    [("list", "/0"), ("dict", "/self")],
)
def test_validate_contract_value_rejects_recursive_container_cycles(
    tmp_path: Path,
    container_kind: str,
    expected_path: str,
) -> None:
    if container_kind == "list":
        raw_value: object = []
        raw_value.append(raw_value)  # type: ignore[union-attr]
    else:
        raw_value = {}
        raw_value["self"] = raw_value  # type: ignore[index]

    with pytest.raises(OutputContractError) as exc_info:
        validate_contract_value(raw_value, {"type": "value"}, workspace=tmp_path)

    violation = exc_info.value.violations[0]
    assert violation["type"] == "invalid_transportable_value"
    assert violation["context"]["value_path"] == expected_path


def test_validate_contract_value_accepts_repeated_acyclic_container(
    tmp_path: Path,
) -> None:
    shared = [{"valid": True}]
    raw_value = [shared, shared]

    result = validate_contract_value(
        raw_value,
        {"type": "value"},
        workspace=tmp_path,
    )

    assert result is raw_value
    assert result[0] is result[1]
