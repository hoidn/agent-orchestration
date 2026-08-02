"""Runtime output-contract coverage for target-2.25 structural transport."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_contract_value,
    validate_output_bundle,
)
from orchestrator.workflow.type_descriptor import (
    MAX_TRANSPORT_VALUE_BYTES,
    validate_transport_value,
)


def _record_schema() -> dict[str, object]:
    return {
        "type": "record",
        "record_name": "Measurement",
        "fields": [
            {"name": "label", "type": "string"},
            {"name": "count", "type": "integer"},
        ],
    }


def _union_schema() -> dict[str, object]:
    return {
        "type": "union",
        "union_name": "Outcome",
        "discriminant": {
            "name": "variant",
            "type": "enum",
            "allowed": ["COMPLETED", "FAILED"],
        },
        "variants": {
            "COMPLETED": {"fields": [{"name": "result", **_record_schema()}]},
            "FAILED": {"fields": [{"name": "reason", "type": "string"}]},
        },
    }


@pytest.mark.parametrize(
    ("schema", "value"),
    (
        (
            {"type": "list", "items": _record_schema()},
            [{"label": "alpha", "count": 2}],
        ),
        (
            {"type": "list", "items": _union_schema()},
            [
                {
                    "variant": "COMPLETED",
                    "result": {"label": "alpha", "count": 2},
                },
                {"variant": "FAILED", "reason": "timeout"},
            ],
        ),
    ),
)
def test_direct_nested_record_and_union_lists_validate_in_memory(
    tmp_path: Path,
    schema: dict[str, object],
    value: object,
) -> None:
    assert validate_contract_value(value, schema, tmp_path) == value


@pytest.mark.parametrize(
    "value",
    (
        [{"label": "alpha"}],
        [{"label": "alpha", "count": 2, "extra": True}],
        [{"label": "alpha", "count": True}],
    ),
)
def test_direct_nested_record_contract_is_closed(
    tmp_path: Path,
    value: object,
) -> None:
    with pytest.raises(OutputContractError) as caught:
        validate_contract_value(
            value,
            {"type": "list", "items": _record_schema()},
            tmp_path,
        )

    assert caught.value.violations[0]["type"] == "invalid_transportable_value"


@pytest.mark.parametrize(
    "value",
    (
        [{"reason": "missing tag"}],
        [{"variant": "UNKNOWN", "reason": "bad tag"}],
        [{"variant": "FAILED"}],
        [{"variant": "FAILED", "reason": "x", "extra": 1}],
        [{"variant": "COMPLETED", "result": {"label": 4, "count": 2}}],
    ),
)
def test_direct_nested_union_contract_is_closed(
    tmp_path: Path,
    value: object,
) -> None:
    with pytest.raises(OutputContractError) as caught:
        validate_contract_value(
            value,
            {"type": "list", "items": _union_schema()},
            tmp_path,
        )

    assert caught.value.violations[0]["type"] == "invalid_transportable_value"


def test_nested_float_contract_translates_huge_integer_rejection(
    tmp_path: Path,
) -> None:
    with pytest.raises(OutputContractError) as caught:
        validate_contract_value(
            {"score": 10**10000},
            {
                "type": "record",
                "record_name": "Scored",
                "fields": [{"name": "score", "type": "float"}],
            },
            tmp_path,
        )

    assert caught.value.violations[0]["type"] == "invalid_transportable_value"


def _nested_record_schema(depth: int) -> dict[str, object]:
    schema = {
        "type": "record",
        "record_name": "Leaf",
        "fields": [{"name": "text", "type": "string"}],
    }
    for _ in range(depth):
        schema = {"type": "list", "items": schema}
    return schema


def _nested_record_value(depth: int) -> object:
    value: object = {"text": "leaf"}
    for _ in range(depth):
        value = [value]
    return value


def test_nested_output_contract_depth_is_root_zero_and_inclusive(
    tmp_path: Path,
) -> None:
    accepted = _nested_record_value(63)
    assert validate_contract_value(
        accepted,
        _nested_record_schema(63),
        tmp_path,
    ) == accepted

    with pytest.raises(OutputContractError):
        validate_contract_value(
            _nested_record_value(64),
            _nested_record_schema(64),
            tmp_path,
        )


def test_nested_value_primitive_continues_enclosing_descriptor_depth() -> None:
    descriptor: dict[str, object] = {"kind": "primitive", "name": "Value"}
    for _ in range(63):
        descriptor = {"kind": "list", "item": descriptor}

    accepted: object = ["leaf"]
    for _ in range(63):
        accepted = [accepted]
    assert validate_transport_value(
        accepted,
        descriptor,
        allow_nested_structures=True,
    ) == accepted

    rejected: object = [["leaf"]]
    for _ in range(63):
        rejected = [rejected]
    with pytest.raises(ValueError, match="depth"):
        validate_transport_value(
            rejected,
            descriptor,
            allow_nested_structures=True,
        )


def test_nested_output_contract_canonical_byte_limit_is_inclusive(
    tmp_path: Path,
) -> None:
    schema = {
        "type": "record",
        "record_name": "Payload",
        "fields": [{"name": "text", "type": "string"}],
    }
    exact = {"text": "x" * (MAX_TRANSPORT_VALUE_BYTES - len('{"text":""}'))}
    assert validate_contract_value(exact, schema, tmp_path) == exact

    with pytest.raises(OutputContractError):
        validate_contract_value(
            {"text": exact["text"] + "x"},
            schema,
            tmp_path,
        )


@pytest.mark.parametrize(
    ("schema", "value"),
    (
        (
            {"type": "list", "items": _record_schema()},
            [{"label": "café", "count": 2}],
        ),
        (
            {"type": "list", "items": _union_schema()},
            [{"variant": "FAILED", "reason": "timeout"}],
        ),
    ),
)
def test_nested_output_bundle_parses_direct_json_file(
    tmp_path: Path,
    schema: dict[str, object],
    value: object,
) -> None:
    (tmp_path / "result.json").write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )
    contract = {
        "path": "result.json",
        "fields": [
            {
                "name": "result",
                "json_pointer": "",
                **schema,
            }
        ],
    }

    assert validate_output_bundle(contract, tmp_path) == {"result": value}


def test_nested_output_bundle_rejects_nonstandard_json_number(
    tmp_path: Path,
) -> None:
    (tmp_path / "result.json").write_text(
        '[{"label":"alpha","count":NaN}]',
        encoding="utf-8",
    )
    contract = {
        "path": "result.json",
        "fields": [
            {
                "name": "result",
                "json_pointer": "",
                "type": "list",
                "items": _record_schema(),
            }
        ],
    }

    with pytest.raises(OutputContractError) as caught:
        validate_output_bundle(contract, tmp_path)

    assert caught.value.violations[0]["type"] == "invalid_json_document"


def test_nested_structural_path_keeps_relpath_boundary_validation(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifacts" / "work" / "report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("report\n", encoding="utf-8")
    schema = {
        "type": "record",
        "record_name": "Report",
        "fields": [
            {
                "name": "path",
                "type": "relpath",
                "under": "artifacts/work",
                "must_exist_target": True,
            }
        ],
    }

    assert validate_contract_value(
        {"path": "artifacts/work/report.md"},
        schema,
        tmp_path,
    ) == {"path": "artifacts/work/report.md"}
    with pytest.raises(OutputContractError):
        validate_contract_value(
            {"path": "../report.md"},
            schema,
            tmp_path,
        )
    with pytest.raises(OutputContractError):
        validate_contract_value(
            {"path": "artifacts/work/missing.md"},
            schema,
            tmp_path,
        )


def test_legacy_opaque_nested_value_schema_keeps_its_existing_path(
    tmp_path: Path,
) -> None:
    schema = {"type": "list", "items": {"type": "value"}}
    value = [{"legacy": True}]

    assert validate_contract_value(json.dumps(value), schema, tmp_path) == value
