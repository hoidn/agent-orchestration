"""Strict native-value checks at the dynamic workflow result boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_expected_outputs,
    validate_output_bundle,
)
from orchestrator.workflow.type_descriptor import (
    transport_descriptor_for_schema,
    transport_schema_for_descriptor,
    validate_transport_value,
)
from orchestrator.workflow_lisp.compiler import (
    compile_stage1_entrypoint,
    linked_module_type_environment,
)
from orchestrator.workflow_lisp.contracts import (
    derive_prompt_guided_structured_result_contract,
)


@pytest.fixture
def result_types(tmp_path: Path):
    module_name = "dynamic_boundary_types"
    source = tmp_path / f"{module_name}.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                f"  (defmodule {module_name})",
                "  (defpath ReportPath",
                "    :kind relpath",
                '    :under "artifacts"',
                "    :must-exist true)",
                "  (defrecord Empty)",
                "  (defrecord Feedback",
                "    (approved Bool)",
                "    (count Int)",
                "    (score Float))",
                "  (defrecord Blocker (reason String))",
                "  (defunion Decision :forall (F B)",
                "    (APPROVE (evidence F))",
                "    (BLOCKED (state B)))",
                "  (defunion PathDecision",
                "    (READY (path ReportPath))",
                "    (BLOCKED (reason String))))",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    linked = compile_stage1_entrypoint(source, source_roots=(tmp_path,))
    type_env = linked_module_type_environment(linked, module_name)

    def contract(type_name: str, *, step: str = "result"):
        type_ref = type_env.resolve_type(
            type_name,
            span=linked.entry_module.span,
            form_path=("workflow-lisp", type_name),
        )
        return derive_prompt_guided_structured_result_contract(
            type_ref,
            workflow_name="dynamic-boundary",
            step_id=step,
            type_env=type_env,
            span=linked.entry_module.span,
            form_path=("workflow-lisp", step),
            whole_value=True,
        )

    return contract


def _bundle_value(contract, value: object, workspace: Path) -> dict[str, object]:
    return validate_output_bundle(
        contract.payload,
        workspace,
        strict_transport_values=True,
        document_bytes=json.dumps(value, separators=(",", ":")).encode("utf-8"),
    )


def test_whole_value_record_is_returned_as_native_root_with_strict_scalars(
    tmp_path: Path,
    result_types,
) -> None:
    contract = result_types("Feedback")
    root = contract.payload["fields"][0]
    assert (root["name"], root["json_pointer"], root["type"]) == (
        "__result__",
        "",
        "record",
    )

    actual = _bundle_value(
        contract,
        {"approved": True, "count": 2**63 - 1, "score": 4},
        tmp_path,
    )
    assert actual == {
        "__result__": {"approved": True, "count": 2**63 - 1, "score": 4.0}
    }

    for invalid in (
        {"approved": "true", "count": 1, "score": 4.0},
        {"approved": True, "count": "1", "score": 4.0},
        {"approved": True, "count": 1, "score": "4.0"},
        {"approved": True, "count": 1, "score": 4.0, "extra": {}},
        {"approved": True, "count": 1},
        {"approved": True, "count": 2**63, "score": 4.0},
        {"approved": True, "count": -(2**63) - 1, "score": 4.0},
    ):
        with pytest.raises(OutputContractError):
            _bundle_value(contract, invalid, tmp_path)


@pytest.mark.parametrize(
    ("type_name", "good", "bad"),
    (("Bool", True, "true"), ("Float", 1.5, "1.5")),
)
def test_whole_value_scalar_contract_requires_native_json_types(
    tmp_path: Path,
    result_types,
    type_name: str,
    good: object,
    bad: object,
) -> None:
    contract = result_types(type_name)
    root = contract.payload["fields"][0]
    assert (root["name"], root["json_pointer"]) == ("__result__", "")
    assert _bundle_value(contract, good, tmp_path) == {"__result__": good}
    with pytest.raises(OutputContractError):
        _bundle_value(contract, bad, tmp_path)


def test_optional_int_root_preserves_null_and_applies_signed64_bounds(
    tmp_path: Path,
    result_types,
) -> None:
    contract = result_types("Optional[Int]")
    for value in (None, -(1 << 63), (1 << 63) - 1):
        assert _bundle_value(contract, value, tmp_path) == {"__result__": value}
    for value in (-(1 << 63) - 1, 1 << 63):
        with pytest.raises(OutputContractError):
            _bundle_value(contract, value, tmp_path)


def test_whole_value_nested_map_and_list_enforce_signed64_bounds(
    tmp_path: Path,
    result_types,
) -> None:
    contract = result_types("Value")
    accepted = {"nested": [{"low": -(1 << 63), "high": (1 << 63) - 1}]}
    assert _bundle_value(contract, accepted, tmp_path) == {"__result__": accepted}

    for overflow in (-(1 << 63) - 1, 1 << 63):
        with pytest.raises(OutputContractError):
            _bundle_value(contract, {"nested": [{"value": overflow}]}, tmp_path)


def test_transport_int64_limit_is_an_explicit_opt_in() -> None:
    descriptor = transport_descriptor_for_schema({"type": "integer"})
    assert validate_transport_value(1 << 63, descriptor) == 1 << 63
    with pytest.raises(ValueError, match="signed 64-bit Int bounds"):
        validate_transport_value(1 << 63, descriptor, require_int64=True)


@pytest.mark.parametrize(
    ("type_name", "document", "expected"),
    (("Bool", b'"true"', True), ("Float", b'"1.5"', 1.5)),
)
def test_default_output_bundle_scalar_coercion_remains_compatible(
    tmp_path: Path,
    result_types,
    type_name: str,
    document: bytes,
    expected: object,
) -> None:
    contract = result_types(type_name)
    assert validate_output_bundle(
        contract.payload,
        tmp_path,
        document_bytes=document,
    ) == {"__result__": expected}


def test_applied_union_accepts_only_active_variant_shape(
    tmp_path: Path,
    result_types,
) -> None:
    contract = result_types("Decision[Feedback Empty]")
    root = contract.payload["fields"][0]
    assert (root["name"], root["json_pointer"], root["type"]) == (
        "__result__",
        "",
        "union",
    )

    value = {
        "variant": "APPROVE",
        "evidence": {"approved": True, "count": 3, "score": 5},
    }
    assert _bundle_value(contract, value, tmp_path) == {"__result__": {
        "variant": "APPROVE",
        "evidence": {"approved": True, "count": 3, "score": 5.0},
    }}
    empty_variant = {"variant": "BLOCKED", "state": {}}
    assert _bundle_value(contract, empty_variant, tmp_path) == {
        "__result__": empty_variant
    }

    for invalid in (
        {"variant": "APPROVE"},
        {"variant": "APPROVE", "evidence": value["evidence"], "extra": True},
        {
            "variant": "APPROVE",
            "evidence": value["evidence"],
            "state": {},
        },
        {
            "variant": "APPROVE",
            "evidence": {"approved": "true", "count": 3, "score": 5},
        },
        {"variant": "BLOCKED"},
        {"variant": "BLOCKED", "state": {}, "extra": True},
    ):
        with pytest.raises(OutputContractError):
            _bundle_value(contract, invalid, tmp_path)


def test_union_schema_canonical_json_roundtrip_preserves_declared_variant_order():
    descriptor = _nonalphabetical_union_descriptor()

    schema = transport_schema_for_descriptor(
        descriptor,
        allow_nested_structures=True,
    )
    canonical_schema = json.loads(json.dumps(schema, sort_keys=True))

    assert canonical_schema["discriminant"]["allowed"] == [
        "REVISE", "APPROVE", "BLOCKED",
    ]
    assert list(canonical_schema["variants"]) == ["APPROVE", "BLOCKED", "REVISE"]
    assert transport_descriptor_for_schema(canonical_schema) == descriptor


def _nonalphabetical_union_descriptor():
    string = {"kind": "primitive", "name": "String"}
    return {
        "kind": "union",
        "name": "WorkflowDecision",
        "variants": [
            {"name": "REVISE", "fields": [{"name": "draft", "type": string}]},
            {"name": "APPROVE", "fields": [{"name": "feedback", "type": string}]},
            {"name": "BLOCKED", "fields": [{"name": "reason", "type": string}]},
        ],
    }


@pytest.mark.parametrize(
    "allowed",
    [
        pytest.param(["REVISE", "REVISE", "BLOCKED"], id="duplicate"),
        pytest.param(["REVISE", "APPROVE"], id="missing"),
        pytest.param(["REVISE", "APPROVE", "BLOCKED", "OTHER"], id="extra"),
        pytest.param(["REVISE", 7, "BLOCKED"], id="non-string"),
        pytest.param(["REVISE", ["APPROVE"], "BLOCKED"], id="unhashable"),
    ],
)
def test_union_schema_rejects_malformed_discriminant_variants(allowed):
    schema = transport_schema_for_descriptor(
        _nonalphabetical_union_descriptor(),
        allow_nested_structures=True,
    )
    schema["discriminant"]["allowed"] = allowed

    with pytest.raises(ValueError):
        transport_descriptor_for_schema(schema)


@pytest.mark.parametrize(
    "document",
    (
        b'{"approved":true,"count":1,"score":NaN}',
        b'{"approved":true,"count":1,"score":Infinity}',
        b'{"approved":true,"count":1,"score":1e999}',
    ),
)
def test_strict_root_decoder_rejects_duplicate_keys_and_non_json_numbers(
    tmp_path: Path,
    result_types,
    document: bytes,
) -> None:
    contract = result_types("Feedback")
    with pytest.raises(OutputContractError):
        validate_output_bundle(
            contract.payload,
            tmp_path,
            strict_transport_values=True,
            document_bytes=document,
        )


def test_duplicate_json_key_refusal_does_not_echo_the_input_key(
    tmp_path: Path,
    result_types,
) -> None:
    contract = result_types("Feedback")
    sensitive_key = "private-user-token"
    document = (
        '{"approved":true,"private-user-token":1,'
        '"private-user-token":2,"count":1,"score":2.0}'
    ).encode("utf-8")

    with pytest.raises(OutputContractError) as caught:
        validate_output_bundle(
            contract.payload,
            tmp_path,
            strict_transport_values=True,
            document_bytes=document,
        )

    assert caught.value.violations[0]["type"] == "invalid_json_document"
    assert sensitive_key not in json.dumps(caught.value.violations)


def test_path_union_rejects_escape_and_captured_bytes_survive_path_replacement(
    tmp_path: Path,
    result_types,
) -> None:
    contract = result_types("PathDecision", step="path-result")
    root = contract.payload["fields"][0]
    assert (root["name"], root["json_pointer"], root["type"]) == (
        "__result__",
        "",
        "union",
    )

    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "report.json").write_text("{}", encoding="utf-8")
    value = {"variant": "READY", "path": "artifacts/report.json"}
    bundle_path = tmp_path / contract.payload["path"]
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_bytes(json.dumps(value).encode("utf-8"))
    captured = bundle_path.read_bytes()
    bundle_path.write_text('{"variant":"BLOCKED","reason":"replaced"}', encoding="utf-8")

    assert validate_output_bundle(
        contract.payload,
        tmp_path,
        strict_transport_values=True,
        document_bytes=captured,
    ) == {"__result__": value}

    with pytest.raises(OutputContractError):
        _bundle_value(
            contract,
            {"variant": "READY", "path": "../escape.json"},
            tmp_path,
        )


def test_required_report_failure_is_checked_after_valid_native_result(
    tmp_path: Path,
    result_types,
) -> None:
    contract = result_types("Feedback")
    value = {"approved": True, "count": 1, "score": 2.0}
    assert _bundle_value(contract, value, tmp_path) == {"__result__": value}

    with pytest.raises(OutputContractError) as caught:
        validate_expected_outputs(
            [{"name": "report", "path": "artifacts/report.json", "type": "string"}],
            tmp_path,
        )
    assert caught.value.violations[0]["type"] == "missing_output_file"
