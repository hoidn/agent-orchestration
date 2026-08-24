"""RED behavioral tests for orchestrator.prompt_contract (Task 7, Step 7.1).

Covers (brief 7.1 + X6): strict duplicate-key-rejecting JSON for default
semantic String; exact scalar and record modes; canonical Optional/List/
Map[String,T] recursion; invalid identifiers, duplicate fields, unknown
keys/types, bool-as-int errors, empty record, and depth above 16; inferred
draft acceptance of ordered {name,type} rows only; deterministic
PromptResult_<8hex> derivation without recursive identity; and the closed
scaffold_output_contract.v1 default/exact/inferred provenance document.
prompt_contract.py is pure: no filesystem, compiler, or registry imports.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from pathlib import Path

from orchestrator.prompt_contract import (
    MAX_TYPE_DEPTH,
    RENDERER_VERSION,
    SCHEMA_VERSION,
    ContractField,
    ListType,
    MapType,
    OptionalType,
    PrimitiveType,
    PromptContractError,
    SemanticContract,
    canonical_json_bytes,
    default_semantic_contract,
    inferred_record_name,
    output_contract_document,
    parse_inferred_draft,
    parse_semantic_contract,
    parse_type_string,
    render_type,
    semantic_contract_object,
    semantic_contract_sha256,
    validate_authoring,
    validate_contract,
    validate_type_node,
)

_SCALAR = {"mode": "scalar", "type": "String"}
_RECORD = {
    "mode": "record",
    "record_name": "Result",
    "fields": [{"name": "summary", "type": "String"}],
}
_INFERRED_AUTHORING = {
    "mode": "inferred",
    "output_request_sha256": "a" * 64,
    "provider": "omp_conf_inference",
    "model": "openai-codex/gpt-5.6-sol",
    "session_id": "sess-1",
    "usage": {
        "input": 1,
        "output": 2,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 3,
        "cost": {
            "input": 0.5,
            "output": 1.0,
            "cacheRead": 0.0,
            "cacheWrite": 0.0,
            "total": 1.5,
        },
    },
}


def _scalar(type_text: str) -> str:
    return json.dumps({"mode": "scalar", "type": type_text})


def _record(record_name: str, fields: list[dict[str, str]]) -> str:
    return json.dumps(
        {"mode": "record", "record_name": record_name, "fields": fields}
    )


def _field(name: str, type_text: str) -> dict[str, str]:
    return {"name": name, "type": type_text}


# --- default semantic String -------------------------------------------------


def test_default_contract_is_scalar_string() -> None:
    contract = default_semantic_contract()
    assert contract.mode == "scalar"
    assert contract.type == PrimitiveType("String")
    assert contract.record_name is None
    assert contract.fields == ()


def test_default_contract_matches_omitted_returns_semantics() -> None:
    # Neither contract flag -> semantic scalar String (X6 contract mode 1).
    parsed = parse_semantic_contract(_scalar("String"))
    assert parsed == default_semantic_contract()


# --- strict duplicate-key-rejecting JSON -------------------------------------


def test_strict_json_rejects_duplicate_object_keys() -> None:
    payload = '{"mode": "scalar", "mode": "record", "type": "String"}'
    with pytest.raises(PromptContractError):
        parse_semantic_contract(payload)


def test_strict_json_rejects_duplicate_field_row_keys() -> None:
    payload = (
        '{"mode": "record", "record_name": "R", "fields": '
        '[{"name": "x", "name": "y", "type": "String"}]}'
    )
    with pytest.raises(PromptContractError):
        parse_semantic_contract(payload)


def test_strict_json_rejects_non_object_document() -> None:
    for payload in ("[]", '"scalar"', "42", "null", "true"):
        with pytest.raises(PromptContractError):
            parse_semantic_contract(payload)


def test_strict_json_rejects_invalid_utf8_bytes() -> None:
    with pytest.raises(PromptContractError):
        parse_semantic_contract(b'{"mode":"scalar","type":"String"}\xff')


# --- exact scalar and record modes -------------------------------------------


def test_exact_scalar_mode_parses_all_canonical_types() -> None:
    for type_text in ("String", "Bool", "Int", "Float"):
        contract = parse_semantic_contract(_scalar(type_text))
        assert contract.mode == "scalar"
        assert render_type(contract.type) == type_text


def test_exact_record_mode_parses_ordered_fields() -> None:
    contract = parse_semantic_contract(
        _record(
            "Result",
            [
                _field("summary", "String"),
                _field("changed_files", "List[String]"),
            ],
        )
    )
    assert contract.mode == "record"
    assert contract.record_name == "Result"
    assert [field.name for field in contract.fields] == [
        "summary",
        "changed_files",
    ]
    assert contract.fields[1].type == ListType(PrimitiveType("String"))


def test_record_mode_requires_at_least_one_field() -> None:
    with pytest.raises(PromptContractError):
        parse_semantic_contract(_record("Result", []))


def test_record_mode_rejects_duplicate_field_names() -> None:
    with pytest.raises(PromptContractError):
        parse_semantic_contract(
            _record(
                "Result",
                [_field("summary", "String"), _field("summary", "Int")],
            )
        )


# --- canonical Optional / List / Map[String,T] recursion ----------------------


def test_canonical_optional_list_map_recursion_parses() -> None:
    node = parse_type_string("Optional[List[Map[String,List[Int]]]]")
    assert node == OptionalType(
        ListType(MapType(ListType(PrimitiveType("Int"))))
    )
    assert render_type(node) == "Optional[List[Map[String,List[Int]]]]"


def test_map_key_must_be_literal_string() -> None:
    for bad in ("Map[Int,String]", "Map[Optional[String],Int]", "Map[String,String,Int]"):
        with pytest.raises(PromptContractError):
            parse_type_string(bad)


def test_type_string_rejects_noncanonical_spellings() -> None:
    for bad in (
        " List[String]",
        "List [String]",
        "List[ String]",
        "List[String ]",
        "List[String] ",
        "List[String]x",
        "Optional",
        "Map[String]",
        "List[",
        "String[",
        "String]",
        "",
        "string",
        "STRing",
        "Unknown",
    ):
        with pytest.raises(PromptContractError):
            parse_type_string(bad)


def test_depth_above_16_rejected() -> None:
    deep = "String"
    for _ in range(MAX_TYPE_DEPTH):
        deep = f"List[{deep}]"
    node = parse_type_string(deep)
    assert node is not None
    with pytest.raises(PromptContractError):
        parse_type_string(f"List[{deep}]")


# --- invalid identifiers, unknown keys/types, bool-as-int --------------------


def test_record_rejects_invalid_record_names() -> None:
    for bad in (
        "1Result",
        "Result-",
        "Result.Name",
        "Ré sult",
        "Result ",
        "Result\n",
        "",
        "Result with space",
        "String",  # prelude primitive collision
        "List",  # type-constructor collision
    ):
        with pytest.raises(PromptContractError):
            parse_semantic_contract(
                _record(bad, [_field("summary", "String")])
            )


def test_record_rejects_invalid_field_names() -> None:
    for bad in (
        "1summary",
        "summary-",
        "summary.name",
        "sum mary",
        "summary\n",
        "",
        "String",  # field names must be ordinary identifiers
    ):
        with pytest.raises(PromptContractError):
            parse_semantic_contract(
                _record("Result", [_field(bad, "String")])
            )


def test_contract_rejects_unknown_keys_at_every_level() -> None:
    bad_documents = (
        {"mode": "scalar", "type": "String", "extra": 1},
        {"mode": "record", "record_name": "R", "fields": [], "extra": 1},
        {"mode": "record", "record_name": "R", "fields": [{"name": "x", "type": "String", "extra": 1}]},
        {"mode": "weird", "type": "String"},
    )
    for document in bad_documents:
        with pytest.raises(PromptContractError):
            parse_semantic_contract(json.dumps(document))


def test_contract_rejects_non_string_members_and_bool_as_int() -> None:
    bad_documents = (
        {"mode": 5, "type": "String"},
        {"mode": True, "type": "String"},
        {"mode": "scalar", "type": 5},
        {"mode": "scalar", "type": True},
        {"mode": "record", "record_name": "R", "fields": [{"name": 5, "type": "String"}]},
        {"mode": "record", "record_name": "R", "fields": [{"name": "x", "type": True}]},
        {"mode": "record", "record_name": "R", "fields": {"name": "x", "type": "String"}},
        {"mode": "record", "record_name": "R", "fields": [["x", "String"]]},
    )
    for document in bad_documents:
        with pytest.raises(PromptContractError):
            parse_semantic_contract(json.dumps(document))


# --- inferred draft: ordered {name,type} rows only ----------------------------


def test_inferred_draft_accepts_ordered_name_type_rows() -> None:
    draft = json.dumps(
        {
            "fields": [
                {"name": "changed_files", "type": "List[String]"},
                {"name": "summary", "type": "String"},
            ]
        }
    )
    contract = parse_inferred_draft(draft, prompt_sha256="b" * 64)
    assert contract.mode == "record"
    assert [field.name for field in contract.fields] == [
        "changed_files",
        "summary",
    ]
    assert contract.record_name is not None
    assert contract.record_name.startswith("PromptResult_")
    assert len(contract.record_name) == len("PromptResult_") + 8


def test_inferred_draft_rejects_any_other_row_shape() -> None:
    bad_drafts = (
        {"fields": []},
        {"fields": [{"name": "x", "type": "String", "extra": 1}]},
        {"fields": [{"name": "x"}]},
        {"fields": [{"type": "String"}]},
        {"fields": [{"name": "x", "type": "String"}, {"name": "x", "type": "Int"}]},
        '{"fields": [{"name": "x", "type": "String", "name": "y"}]}',
        {"fields": {"name": "x", "type": "String"}},
        {"fields": "nope"},
        {"fields": [{"name": "1x", "type": "String"}]},
        {"fields": [{"name": "x", "type": "NotAType"}]},
        {"fields": [{"name": "x", "type": "String"}], "extra": 1},
        {},
    )
    for draft in bad_drafts:
        with pytest.raises(PromptContractError):
            payload = draft if isinstance(draft, str) else json.dumps(draft)
            parse_inferred_draft(payload, prompt_sha256="b" * 64)


def test_inferred_draft_requires_exact_prompt_sha256() -> None:
    draft = json.dumps({"fields": [{"name": "x", "type": "String"}]})
    for bad in ("", "abc", "A" * 64, "a" * 63, None):
        with pytest.raises(PromptContractError):
            parse_inferred_draft(draft, prompt_sha256=bad)


# --- deterministic PromptResult_<8hex>, no recursive identity -----------------


def test_inferred_record_name_is_deterministic() -> None:
    fields = (
        ContractField("changed_files", ListType(PrimitiveType("String"))),
        ContractField("summary", PrimitiveType("String")),
    )
    first = inferred_record_name(fields, prompt_sha256="c" * 64)
    second = inferred_record_name(fields, prompt_sha256="c" * 64)
    assert first == second
    assert first == "PromptResult_" + hashlib.sha256(
        canonical_json_bytes(
            {
                "schema": "prompt_result_name.v1",
                "renderer_version": RENDERER_VERSION,
                "prompt_sha256": "c" * 64,
                "fields": [
                    {"name": "changed_files", "type": "List[String]"},
                    {"name": "summary", "type": "String"},
                ],
            }
        )
    ).hexdigest()[:8]


def test_inferred_record_name_changes_with_fields_or_prompt() -> None:
    base = (ContractField("summary", PrimitiveType("String")),)
    other_fields = (ContractField("detail", PrimitiveType("String")),)
    assert inferred_record_name(base, prompt_sha256="d" * 64) != inferred_record_name(
        other_fields, prompt_sha256="d" * 64
    )
    assert inferred_record_name(base, prompt_sha256="d" * 64) != inferred_record_name(
        base, prompt_sha256="e" * 64
    )


def test_inferred_record_name_never_recurses_into_identity() -> None:
    # The name derivation uses only schema/renderer/prompt/fields: passing a
    # hypothetical identity value must not change it (no recursive identity).
    fields = (ContractField("summary", PrimitiveType("String")),)
    assert inferred_record_name(fields, prompt_sha256="f" * 64) == inferred_record_name(
        fields, prompt_sha256="f" * 64
    )
    assert inferred_record_name(fields, prompt_sha256="f" * 64) == (
        "PromptResult_" + hashlib.sha256(
            canonical_json_bytes(
                {
                    "schema": "prompt_result_name.v1",
                    "renderer_version": RENDERER_VERSION,
                    "prompt_sha256": "f" * 64,
                    "fields": [{"name": "summary", "type": "String"}],
                }
            )
        ).hexdigest()[:8]
    )


# --- canonical JSON mechanics -------------------------------------------------


def test_canonical_json_is_utf8_sorted_compact_without_ascii_escape() -> None:
    assert canonical_json_bytes({"b": "é", "a": 1}) == b'{"a":1,"b":"\xc3\xa9"}'


def test_canonical_json_has_no_permissive_fallback() -> None:
    with pytest.raises(PromptContractError):
        canonical_json_bytes({"x": object()})
    with pytest.raises(PromptContractError):
        canonical_json_bytes({"x": float("nan")})
    with pytest.raises(PromptContractError):
        canonical_json_bytes({"x": float("inf")})


def test_semantic_contract_object_and_sha256_are_closed() -> None:
    contract = parse_semantic_contract(_record("Result", [_field("summary", "String")]))
    document = semantic_contract_object(contract)
    assert document == {
        "mode": "record",
        "record_name": "Result",
        "fields": [{"name": "summary", "type": "String"}],
    }
    assert semantic_contract_sha256(contract) == hashlib.sha256(
        canonical_json_bytes(document)
    ).hexdigest()


# --- closed scaffold_output_contract.v1 provenance ----------------------------


def test_output_contract_document_default_provenance() -> None:
    contract = default_semantic_contract()
    document = output_contract_document(contract, {"mode": "default"})
    assert document == {
        "schema_version": SCHEMA_VERSION,
        "semantic": {"mode": "scalar", "type": "String"},
        "authoring": {"mode": "default"},
    }


def test_output_contract_document_exact_provenance() -> None:
    contract = parse_semantic_contract(_scalar("List[String]"))
    document = output_contract_document(contract, {"mode": "exact"})
    assert document["semantic"] == {"mode": "scalar", "type": "List[String]"}
    assert document["authoring"] == {"mode": "exact"}


def test_output_contract_document_inferred_provenance() -> None:
    contract = parse_inferred_draft(
        json.dumps({"fields": [{"name": "summary", "type": "String"}]}),
        prompt_sha256="a" * 64,
    )
    authoring = validate_authoring(_INFERRED_AUTHORING)
    document = output_contract_document(contract, authoring)
    assert document["schema_version"] == SCHEMA_VERSION
    assert document["semantic"] == semantic_contract_object(contract)
    assert document["authoring"] == _INFERRED_AUTHORING


def test_authoring_rejects_unknown_keys_and_bad_values() -> None:
    bad_authoring = (
        {"mode": "default", "extra": 1},
        {"mode": "exact", "extra": 1},
        {"mode": "inferred"},
        {"mode": "inferred", "output_request_sha256": "x" * 64, "provider": "omp_conf_inference", "model": "m", "session_id": "s", "usage": None},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "other", "model": "m", "session_id": "s", "usage": None},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "omp_conf_inference", "model": "", "session_id": "s", "usage": None},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "omp_conf_inference", "model": "m", "session_id": "", "usage": None},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "omp_conf_inference", "model": "m", "session_id": "s", "usage": {"input": -1, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0, "cost": {}}},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "omp_conf_inference", "model": "m", "session_id": "s", "usage": {"input": True, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0, "cost": {}}},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "omp_conf_inference", "model": "m", "session_id": "s", "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0, "cost": {"total": float("nan")}}},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "omp_conf_inference", "model": "m", "session_id": "s", "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0, "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": -0.1}}},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "omp_conf_inference", "model": "m", "session_id": "s", "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0, "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0, "extra": 1}}},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "omp_conf_inference", "model": "m", "session_id": "s", "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0, "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0}, "extra": 1}},
        {"mode": "inferred", "output_request_sha256": "a" * 64, "provider": "omp_conf_inference", "model": "m", "session_id": "s", "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0, "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0}, "output": "2"}},
        {"mode": "unknown", "extra": 1},
    )
    for authoring in bad_authoring:
        with pytest.raises(PromptContractError):
            validate_authoring(authoring)


def test_output_contract_rejects_unknown_keys() -> None:
    document = output_contract_document(
        default_semantic_contract(), {"mode": "default"}
    )
    assert set(document) == {"schema_version", "semantic", "authoring"}
    assert set(document["semantic"]) == {"mode", "type"}
    assert set(document["authoring"]) == {"mode"}


# --- second fix round: exact normalized state + manual-node depth ------------


def test_validate_contract_rejects_hidden_scalar_state() -> None:
    # Scalar requires type AND record_name None AND empty fields.
    with pytest.raises(PromptContractError):
        validate_contract(SemanticContract(
            mode="scalar", type=PrimitiveType("String"),
            record_name="X", fields=(),
        ))
    with pytest.raises(PromptContractError):
        validate_contract(SemanticContract(
            mode="scalar", type=PrimitiveType("String"), record_name=None,
            fields=(ContractField("extra", PrimitiveType("String")),),
        ))


def test_validate_contract_rejects_hidden_record_state() -> None:
    # Record requires type None plus a validated name and non-empty fields.
    with pytest.raises(PromptContractError):
        validate_contract(SemanticContract(
            mode="record", type=PrimitiveType("String"),
            record_name="Result",
            fields=(ContractField("summary", PrimitiveType("String")),),
        ))


def test_validate_type_node_enforces_max_depth() -> None:
    deep: object = PrimitiveType("String")
    for _ in range(MAX_TYPE_DEPTH + 1):
        deep = OptionalType(deep)
    with pytest.raises(PromptContractError):
        validate_type_node(deep)
    admissible: object = PrimitiveType("String")
    for _ in range(MAX_TYPE_DEPTH):
        admissible = OptionalType(admissible)
    validate_type_node(admissible)


# --- packaged inference workflow: typed task-prompt/output-request inputs ---


def _compile_inference_asset(workspace: Path):
    from orchestrator.omp_assets import inference_output_contract_path
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint

    (workspace / "prompt.md").write_text(
        "synthesize the output contract\n", encoding="utf-8"
    )
    entry = workspace / "infer-output-contract.orc"
    entry.write_text(
        Path(inference_output_contract_path()).read_text(encoding="utf-8")
    )
    return compile_stage3_entrypoint(
        entry,
        source_roots=(workspace,),
        provider_externs={"providers.inference": "omp_conf_inference"},
        prompt_externs={"prompts.inference": {"asset_file": "prompt.md"}},
        validate_shared=True,
        workspace_root=workspace,
    )


def test_inference_asset_declares_typed_string_inputs(tmp_path: Path) -> None:
    result = _compile_inference_asset(tmp_path)
    mapping = result.entry_result.lowered_workflows[0].authored_mapping
    inputs = mapping["inputs"]
    assert inputs["task_prompt"] == {"kind": "scalar", "type": "string"}
    assert inputs["output_request"] == {"kind": "scalar", "type": "string"}
    step = next(s for s in mapping["steps"] if "provider" in s)
    bindings = {
        entry["binding_name"]
        for entry in (step.get("typed_prompt_inputs") or ())
    }
    assert bindings == {"task_prompt", "output_request"}
    # Neutral isolation: transient, no session artifact, internal extern.
    assert step.get("session_request") is None
    assert step.get("prompt_consumes") is None


def test_inference_asset_output_is_only_output_contract_draft(tmp_path: Path) -> None:
    result = _compile_inference_asset(tmp_path)
    mapping = result.entry_result.lowered_workflows[0].authored_mapping
    outputs = mapping["outputs"]
    assert set(outputs) == {"return__fields"}
    fields_spec = outputs["return__fields"]
    assert fields_spec["type"] == "list"
    items = fields_spec["items"]
    assert items["record_name"] == "OutputContractField"
    assert [f["name"] for f in items["fields"]] == ["name", "type"]
