from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import math
import subprocess
import sys

import pytest

from orchestrator.workflow.run_ref.config import (
    RUN_REF_STATIC_CONFIG_SCHEMA,
    ArrayBinding,
    BundleProgram,
    LiteralBinding,
    ObjectBinding,
    PathProgram,
    ReferenceBinding,
    RunRefInput,
    RunRefStaticConfig,
    build_run_ref_static_config,
    decode_run_ref_static_config,
    encode_run_ref_static_config,
    run_ref_input_identity,
    validate_run_ref_result_descriptor,
)
from orchestrator.workflow.run_ref.contracts import (
    SetupCommand,
    SetupPolicy,
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.source import (
    SourceRequest,
    canonical_source_request,
    source_request_from_dict,
)


COMPILER_IDENTITY = "sha256:" + "c" * 64
COMMIT = "0123456789abcdef0123456789abcdef01234567"
_AUTO_RETURN_REFINEMENT = object()
_DEFAULT_RESULT_DESCRIPTOR = object()
_FIXED_RESULT_DESCRIPTOR_BYTES = (
    b'{"envelope":{"fields":[{"name":"value","type":{"kind":"primitive","name":"Bool"}},{"'
    b'name":"workspace_delta","type":{"fields":[{"name":"base","type":{"fields":[{"name":"'
    b'digest","type":{"kind":"primitive","name":"String"}},{"name":"normalized_locator","t'
    b'ype":{"kind":"primitive","name":"String"}},{"name":"resolved_commit_sha","type":{"ki'
    b'nd":"primitive","name":"String"}},{"name":"materializer_version","type":{"kind":"pri'
    b'mitive","name":"String"}},{"name":"submodule_policy","type":{"kind":"primitive","nam'
    b'e":"String"}},{"name":"lfs_policy","type":{"kind":"primitive","name":"String"}},{"na'
    b'me":"authored_setup_identity","type":{"kind":"primitive","name":"String"}}],"kind":"'
    b'record","name":"RepositoryRevisionId"}},{"name":"changed_files","type":{"item":{"fie'
    b'lds":[{"name":"path","type":{"kind":"primitive","name":"String"}},{"name":"kind","ty'
    b'pe":{"kind":"primitive","name":"String"}},{"name":"mode","type":{"kind":"primitive",'
    b'"name":"Int"}},{"name":"size","type":{"kind":"primitive","name":"Int"}},{"name":"old'
    b'_sha256","type":{"item":{"kind":"primitive","name":"String"},"kind":"optional"}},{"n'
    b'ame":"new_sha256","type":{"item":{"kind":"primitive","name":"String"},"kind":"option'
    b'al"}},{"name":"link_target","type":{"item":{"kind":"primitive","name":"String"},"kin'
    b'd":"optional"}}],"kind":"record","name":"WorkspaceEntryDelta"},"kind":"list"}},{"nam'
    b'e":"deleted_files","type":{"item":{"fields":[{"name":"path","type":{"kind":"primitiv'
    b'e","name":"String"}},{"name":"kind","type":{"kind":"primitive","name":"String"}},{"n'
    b'ame":"mode","type":{"kind":"primitive","name":"Int"}},{"name":"size","type":{"kind":'
    b'"primitive","name":"Int"}},{"name":"old_sha256","type":{"item":{"kind":"primitive","'
    b'name":"String"},"kind":"optional"}},{"name":"new_sha256","type":{"item":{"kind":"pri'
    b'mitive","name":"String"},"kind":"optional"}},{"name":"link_target","type":{"item":{"'
    b'kind":"primitive","name":"String"},"kind":"optional"}}],"kind":"record","name":"Work'
    b'spaceEntryDelta"},"kind":"list"}},{"name":"untracked_files","type":{"item":{"fields"'
    b':[{"name":"path","type":{"kind":"primitive","name":"String"}},{"name":"kind","type":'
    b'{"kind":"primitive","name":"String"}},{"name":"mode","type":{"kind":"primitive","nam'
    b'e":"Int"}},{"name":"size","type":{"kind":"primitive","name":"Int"}},{"name":"old_sha'
    b'256","type":{"item":{"kind":"primitive","name":"String"},"kind":"optional"}},{"name"'
    b':"new_sha256","type":{"item":{"kind":"primitive","name":"String"},"kind":"optional"}'
    b'},{"name":"link_target","type":{"item":{"kind":"primitive","name":"String"},"kind":"'
    b'optional"}}],"kind":"record","name":"WorkspaceEntryDelta"},"kind":"list"}},{"name":"'
    b'normalized_diff","type":{"fields":[{"name":"entries","type":{"item":{"fields":[{"nam'
    b'e":"path","type":{"kind":"primitive","name":"String"}},{"name":"text","type":{"kind"'
    b':"primitive","name":"String"}},{"name":"truncated","type":{"kind":"primitive","name"'
    b':"Bool"}},{"name":"omitted_bytes","type":{"kind":"primitive","name":"Int"}}],"kind":'
    b'"record","name":"NormalizedTextDiffEntry"},"kind":"list"}},{"name":"catalog_digest",'
    b'"type":{"kind":"primitive","name":"String"}},{"name":"truncated","type":{"kind":"pri'
    b'mitive","name":"Bool"}},{"name":"omitted_bytes","type":{"kind":"primitive","name":"I'
    b'nt"}},{"name":"omitted_entries","type":{"kind":"primitive","name":"Int"}}],"kind":"r'
    b'ecord","name":"NormalizedWorkspaceDiff"}},{"name":"declared_artifacts","type":{"item'
    b'":{"fields":[{"name":"name","type":{"kind":"primitive","name":"String"}},{"name":"pa'
    b'th","type":{"kind":"primitive","name":"String"}},{"name":"kind","type":{"kind":"prim'
    b'itive","name":"String"}},{"name":"mode","type":{"kind":"primitive","name":"Int"}},{"'
    b'name":"size","type":{"kind":"primitive","name":"Int"}},{"name":"sha256","type":{"ite'
    b'm":{"kind":"primitive","name":"String"},"kind":"optional"}},{"name":"link_target","t'
    b'ype":{"item":{"kind":"primitive","name":"String"},"kind":"optional"}}],"kind":"recor'
    b'd","name":"DeclaredWorkspaceArtifact"},"kind":"list"}}],"kind":"record","name":"Work'
    b'spaceDelta"}},{"name":"accounting","type":{"fields":[{"name":"child_run_id","type":{'
    b'"kind":"primitive","name":"RunId"}},{"name":"attempt_ordinal","type":{"kind":"primit'
    b'ive","name":"Int"}},{"name":"terminal_status","type":{"kind":"primitive","name":"Str'
    b'ing"}},{"name":"elapsed_ms","type":{"kind":"primitive","name":"Int"}},{"name":"setup'
    b'_ms","type":{"kind":"primitive","name":"Int"}},{"name":"compile_ms","type":{"kind":"'
    b'primitive","name":"Int"}},{"name":"provider_attempts","type":{"kind":"primitive","na'
    b'me":"Value"}},{"name":"token_usage","type":{"kind":"primitive","name":"Value"}},{"na'
    b'me":"cost","type":{"kind":"primitive","name":"Value"}}],"kind":"record","name":"RunR'
    b'efAccounting"}}],"kind":"record","name":"RunRefResult$6c347f1d65bf55f7"},"schema":"r'
    b'un_ref_result_contract.v1"}'
)
_FIXED_RESULT_DESCRIPTOR = json.loads(_FIXED_RESULT_DESCRIPTOR_BYTES)
_FIXED_RESULT_DIGEST = (
    "sha256:8909a2b1af48d21deec5e5413be2b35253f0622cb3aa2b3bbf4c6067246f6211"
)
_TRANSPORTABLE_ROOT_DESCRIPTORS = (
    {"kind": "primitive", "name": "Bool"},
    {
        "kind": "record",
        "name": "ChildRecord",
        "fields": [
            {
                "name": "value",
                "type": {"kind": "primitive", "name": "String"},
            }
        ],
    },
    {"kind": "union", "name": "ChildUnion", "variants": [{"name": "OK", "fields": []}]},
    {"kind": "list", "item": {"kind": "primitive", "name": "String"}},
    {
        "kind": "map",
        "key": {"kind": "primitive", "name": "String"},
        "value": {"kind": "primitive", "name": "Int"},
    },
    {"kind": "optional", "item": {"kind": "primitive", "name": "String"}},
    {
        "kind": "path",
        "name": "ChildPath",
        "under": "artifacts/work",
        "must_exist_target": False,
    },
    {"kind": "primitive", "name": "Value"},
)


def _source() -> SourceRequest:
    return SourceRequest(
        locator="https://example.com/team/repository.git",
        commit=COMMIT,
        setup=SetupPolicy(
            commands=(
                SetupCommand(
                    argv=("./tools/bootstrap", "--locked"),
                    env=(("MODE", "release"),),
                ),
            )
        ),
    )


def _site_digest(result_descriptor: dict[str, object]) -> str:
    generated_name = result_descriptor["envelope"]["name"]
    return generated_name.removeprefix("RunRefResult$") + "0" * 48


def _result_contract(
    value_descriptor=_DEFAULT_RESULT_DESCRIPTOR,
) -> tuple[dict[str, object], str]:
    descriptor = deepcopy(_FIXED_RESULT_DESCRIPTOR)
    if value_descriptor is _DEFAULT_RESULT_DESCRIPTOR:
        return descriptor, _FIXED_RESULT_DIGEST
    descriptor["envelope"]["fields"][0]["type"] = deepcopy(value_descriptor)
    return descriptor, canonical_sha256(descriptor)


def _inputs() -> tuple[RunRefInput, ...]:
    return (
        RunRefInput(
            name="task",
            type_descriptor={"kind": "primitive", "name": "String"},
            binding=ReferenceBinding("inputs.task"),
        ),
        RunRefInput(
            name="options",
            type_descriptor={
                "kind": "list",
                "item": {"kind": "primitive", "name": "Int"},
            },
            binding=ObjectBinding(
                entries=(
                    ("enabled", LiteralBinding(True)),
                    (
                        "limits",
                        ArrayBinding(
                            items=(LiteralBinding(1), LiteralBinding(2.5)),
                        ),
                    ),
                )
            ),
        ),
    )


def _config(
    *,
    mode: str = "bundle",
    value_descriptor=_DEFAULT_RESULT_DESCRIPTOR,
    inputs=None,
    source: SourceRequest | None = None,
    return_refinement=_AUTO_RETURN_REFINEMENT,
):
    descriptor, result_digest = _result_contract(value_descriptor)
    program = (
        BundleProgram(workflow_name="imported.module/child")
        if mode == "bundle"
        else PathProgram(
            path="candidate.orc",
            entry_name="candidate",
            return_refinement=(
                descriptor["envelope"]["fields"][0]["type"]
                if return_refinement is _AUTO_RETURN_REFINEMENT
                else return_refinement
            ),
        )
    )
    return build_run_ref_static_config(
        compiler_runtime_identity_digest=COMPILER_IDENTITY,
        site_digest=_site_digest(descriptor),
        source=_source() if source is None else source,
        program=program,
        inputs=_inputs() if inputs is None else inputs,
        result_descriptor=descriptor,
        result_digest=result_digest,
    )


def test_local_result_descriptor_fixture_has_independent_canonical_digest() -> None:
    independently_encoded = json.dumps(
        _FIXED_RESULT_DESCRIPTOR,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert independently_encoded == _FIXED_RESULT_DESCRIPTOR_BYTES
    assert (
        "sha256:" + hashlib.sha256(independently_encoded).hexdigest()
        == _FIXED_RESULT_DIGEST
    )


def test_source_request_dict_codec_round_trips_exactly() -> None:
    record = canonical_source_request(_source())

    decoded = source_request_from_dict(record)

    assert canonical_source_request(decoded) == record


def test_builder_stores_canonical_source_and_matches_decoded_typed_view() -> None:
    source = replace(_source(), locator="/tmp/run-ref-source")

    config = _config(source=source)
    decoded = decode_run_ref_static_config(encode_run_ref_static_config(config))

    assert config.source.locator == "file:///tmp/run-ref-source"
    assert config == decoded


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.pop("lfs_policy"),
        lambda value: value.__setitem__("extra", True),
        lambda value: value["authored_setup"].__setitem__("extra", True),
        lambda value: value["authored_setup"]["commands"][0].pop("argv"),
        lambda value: value["authored_setup"]["commands"][0].__setitem__("extra", True),
        lambda value: value["authored_setup"]["commands"][0]["env"].append(["MODE", "debug"]),
        lambda value: value.__setitem__("authored_setup_identity", "sha256:" + "0" * 64),
    ),
)
def test_source_request_dict_codec_rejects_shape_and_identity_tamper(mutation) -> None:
    record = canonical_source_request(_source())
    mutation(record)

    with pytest.raises((TypeError, ValueError)):
        source_request_from_dict(record)


def test_static_config_both_program_modes_have_closed_distinct_shapes() -> None:
    bundle = _config(mode="bundle")
    path = _config(mode="path")

    assert bundle.record["program"] == {
        "mode": "bundle",
        "workflow_name": "imported.module/child",
    }
    assert path.record["program"] == {
        "mode": "path",
        "path": "candidate.orc",
        "entry_name": "candidate",
        "environment": "deterministic-effect-free",
        "return_refinement": {"kind": "primitive", "name": "Bool"},
    }
    assert bundle.digest != path.digest


def test_path_program_omitted_refinement_is_null_only_for_default_value() -> None:
    omitted = _config(
        mode="path",
        value_descriptor=_TRANSPORTABLE_ROOT_DESCRIPTORS[7],
        return_refinement=None,
    )

    assert omitted.record["program"]["return_refinement"] is None
    with pytest.raises(ValueError):
        _config(mode="path", return_refinement=None)


def test_path_program_distinguishes_omitted_and_explicit_value_refinement() -> None:
    omitted = _config(
        mode="path",
        value_descriptor=_TRANSPORTABLE_ROOT_DESCRIPTORS[7],
        return_refinement=None,
    )
    explicit = _config(
        mode="path",
        value_descriptor=_TRANSPORTABLE_ROOT_DESCRIPTORS[7],
        return_refinement={"kind": "primitive", "name": "Value"},
    )

    assert omitted.record["program"]["return_refinement"] is None
    assert explicit.record["program"]["return_refinement"] == {
        "kind": "primitive",
        "name": "Value",
    }
    assert omitted.digest != explicit.digest
    assert encode_run_ref_static_config(omitted) != encode_run_ref_static_config(
        explicit
    )


def test_path_program_refinement_view_is_defensive_and_immutable() -> None:
    refinement = {"kind": "primitive", "name": "Bool"}
    program = PathProgram(
        path="candidate.orc",
        entry_name="candidate",
        return_refinement=refinement,
    )

    refinement["name"] = "String"
    returned = program.return_refinement
    assert returned is not None
    returned["name"] = "String"

    assert program.return_refinement == {"kind": "primitive", "name": "Bool"}
    assert program.record["return_refinement"] == {
        "kind": "primitive",
        "name": "Bool",
    }


@pytest.mark.parametrize(
    "return_refinement",
    (
        {},
        {"kind": "primitive", "name": "Bool", "extra": True},
        {"kind": "primitive", "name": "Json"},
        {"kind": "primitive", "name": "Provider"},
        {"kind": "primitive", "name": "Prompt"},
    ),
)
def test_path_program_rejects_malformed_or_nontransportable_refinement(
    return_refinement,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        PathProgram(
            path="candidate.orc",
            entry_name="candidate",
            return_refinement=return_refinement,
        )


def test_path_program_refinement_must_exactly_match_result_value_descriptor() -> None:
    with pytest.raises(ValueError):
        _config(
            mode="path",
            return_refinement={"kind": "primitive", "name": "String"},
        )


@pytest.mark.parametrize("value_descriptor", _TRANSPORTABLE_ROOT_DESCRIPTORS)
def test_static_config_accepts_all_transportable_result_descriptor_roots(
    value_descriptor,
) -> None:
    config = _config(value_descriptor=value_descriptor)

    validate_run_ref_result_descriptor(
        config.result_descriptor,
        expected_generated_name=config.generated_result_type,
        expected_digest=config.result_digest,
    )


def test_static_config_exact_wire_and_round_trip_are_canonical() -> None:
    config = _config()
    encoded = encode_run_ref_static_config(config)
    decoded = decode_run_ref_static_config(encoded)

    assert config.record == {
        "schema_version": RUN_REF_STATIC_CONFIG_SCHEMA,
        "target_dsl_version": "2.24",
        "lowering_route": "wcc_m4",
        "lowering_schema_version": 2,
        "compiler_runtime_identity_digest": COMPILER_IDENTITY,
        "site_digest": config.site_digest,
        "generated_result_type": config.generated_result_type,
        "source": canonical_source_request(_source()),
        "program": {
            "mode": "bundle",
            "workflow_name": "imported.module/child",
        },
        "inputs": [row.record for row in _inputs()],
        "result_descriptor": config.result_descriptor,
        "result_digest": config.result_digest,
    }
    assert encoded == canonical_json_bytes(config.record)
    assert encode_run_ref_static_config(decoded) == encoded
    assert decoded.digest == config.digest == canonical_sha256(config.record)


def test_static_config_and_input_views_are_defensive_and_immutable() -> None:
    config = _config()
    record = config.record
    record["inputs"][0]["name"] = "changed"
    descriptor = config.result_descriptor
    descriptor["envelope"]["fields"][0]["name"] = "changed"
    input_descriptor = config.inputs[0].type_descriptor
    input_descriptor["name"] = "changed"

    assert config.record["inputs"][0]["name"] == "task"
    assert config.result_descriptor["envelope"]["fields"][0]["name"] == "value"
    assert config.inputs[0].type_descriptor["name"] == "String"
    with pytest.raises(FrozenInstanceError):
        config.digest = "sha256:" + "0" * 64
    for args, kwargs in (
        ((), {}),
        ((b"forged",), {}),
        ((), {"digest": "sha256:" + "0" * 64}),
    ):
        with pytest.raises(TypeError):
            RunRefStaticConfig(*args, **kwargs)


@pytest.mark.parametrize("type_descriptor", _TRANSPORTABLE_ROOT_DESCRIPTORS)
def test_static_inputs_accept_all_transportable_descriptor_roots(
    type_descriptor,
) -> None:
    row = RunRefInput(
        name="value",
        type_descriptor=type_descriptor,
        binding=ReferenceBinding("inputs.value"),
    )

    assert _config(inputs=(row,)).inputs == (row,)


def test_input_order_is_identity_bearing_and_row_identity_is_derived() -> None:
    inputs = _inputs()
    left = _config(inputs=inputs)
    right = _config(inputs=tuple(reversed(inputs)))

    assert left.digest != right.digest
    assert inputs[0].record == {
        "name": "task",
        "type_descriptor": {"kind": "primitive", "name": "String"},
        "binding": {"kind": "reference", "reference": "inputs.task"},
    }
    assert "digest" not in inputs[0].record
    assert run_ref_input_identity(inputs[0]) == canonical_sha256(inputs[0].record)


@pytest.mark.parametrize(
    "binding",
    (
        LiteralBinding(None),
        LiteralBinding(False),
        LiteralBinding(7),
        LiteralBinding(2.5),
        LiteralBinding("text"),
        ReferenceBinding("root.steps.build.result"),
        ArrayBinding((LiteralBinding(1), ReferenceBinding("inputs.value"))),
        ObjectBinding((("a", LiteralBinding(1)), ("b", LiteralBinding(2)))),
    ),
)
def test_binding_tree_round_trips_every_tag(binding) -> None:
    row = RunRefInput(
        name="value",
        type_descriptor={"kind": "primitive", "name": "Value"},
        binding=binding,
    )
    config = _config(inputs=(row,))

    assert decode_run_ref_static_config(
        encode_run_ref_static_config(config)
    ).inputs == (row,)


@pytest.mark.parametrize(
    "payload",
    (
        b"\xff",
        b"{",
        b'{"a":1,"a":2}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
    ),
)
def test_static_config_decoder_rejects_invalid_utf8_json_duplicates_and_nonfinite(
    payload: bytes,
) -> None:
    with pytest.raises((UnicodeDecodeError, ValueError)):
        decode_run_ref_static_config(payload)


def test_static_config_decoder_rejects_noncanonical_json_bytes() -> None:
    config = _config()
    noncanonical = json.dumps(config.record, indent=2).encode("utf-8")

    with pytest.raises(ValueError):
        decode_run_ref_static_config(noncanonical)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("schema_version",), "run_ref_static_config.v2"),
        (("target_dsl_version",), "2.23"),
        (("lowering_route",), "legacy"),
        (("lowering_schema_version",), 3),
        (("compiler_runtime_identity_digest",), "sha256:" + "0" * 63),
        (("site_digest",), "A" * 64),
        (("generated_result_type",), "RunRefResult$0000000000000000"),
        (("source", "authored_setup_identity"), "sha256:" + "0" * 64),
        (("program", "mode"), "mixed"),
        (("result_digest",), "sha256:" + "0" * 64),
        (("result_descriptor", "schema"), "run_ref_result_contract.v2"),
    ),
)
def test_static_config_decoder_rejects_fixed_identity_and_nested_tamper(
    path: tuple[str, ...],
    value: object,
) -> None:
    record = _config().record
    target = record
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value

    with pytest.raises((TypeError, ValueError)):
        decode_run_ref_static_config(canonical_json_bytes(record))


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.pop("program"),
        lambda value: value.__setitem__("extra", True),
        lambda value: value["program"].__setitem__("entry_name", "mixed"),
        lambda value: value["inputs"][0].pop("binding"),
        lambda value: value["inputs"][0].__setitem__("extra", True),
        lambda value: value["inputs"][0]["binding"].__setitem__("extra", True),
        lambda value: value["inputs"].append(deepcopy(value["inputs"][0])),
        lambda value: value["inputs"][0].__setitem__("name", ""),
        lambda value: value["inputs"][0].__setitem__("type_descriptor", {}),
        lambda value: value["inputs"][0].__setitem__("binding", {"kind": "unknown"}),
        lambda value: value["inputs"][0].__setitem__(
            "binding", {"kind": "reference", "reference": "not a reference"}
        ),
        lambda value: value["inputs"][1]["binding"]["entries"].append(
            deepcopy(value["inputs"][1]["binding"]["entries"][0])
        ),
    ),
)
def test_static_config_decoder_rejects_closed_shape_and_input_binding_tamper(
    mutate,
) -> None:
    record = _config().record
    mutate(record)

    with pytest.raises((TypeError, ValueError)):
        decode_run_ref_static_config(canonical_json_bytes(record))


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["program"].__setitem__("path", "../candidate.orc"),
        lambda value: value["program"].__setitem__("path", "/candidate.orc"),
        lambda value: value["program"].__setitem__("path", "candidate.txt"),
        lambda value: value["program"].__setitem__("entry_name", "bad name"),
        lambda value: value["program"].__setitem__("environment", "ambient"),
        lambda value: value["program"].__setitem__("workflow_name", "mixed"),
        lambda value: value["program"].__setitem__(
            "return_refinement", {"kind": "primitive", "name": "String"}
        ),
        lambda value: value["program"].__setitem__("return_refinement", None),
    ),
)
def test_path_program_decoder_rejects_path_environment_and_mixed_mode_tamper(
    mutate,
) -> None:
    record = _config(mode="path").record
    mutate(record)

    with pytest.raises((TypeError, ValueError)):
        decode_run_ref_static_config(canonical_json_bytes(record))


@pytest.mark.parametrize("workflow_name", ("../child", "child//nested", "bad name"))
def test_bundle_program_decoder_rejects_noncanonical_workflow_names(
    workflow_name: str,
) -> None:
    record = _config().record
    record["program"]["workflow_name"] = workflow_name

    with pytest.raises(ValueError):
        decode_run_ref_static_config(canonical_json_bytes(record))


def test_bundle_program_decoder_rejects_path_only_return_refinement() -> None:
    record = _config().record
    record["program"]["return_refinement"] = None

    with pytest.raises(ValueError):
        decode_run_ref_static_config(canonical_json_bytes(record))


@pytest.mark.parametrize(
    "binding",
    (
        {"kind": "array", "items": "not-a-list"},
        {"kind": "object", "entries": "not-a-list"},
        {"kind": "object", "entries": [{"name": "a"}]},
        {
            "kind": "object",
            "entries": [{"name": "a", "binding": {"kind": "literal", "value": 1}, "extra": True}],
        },
        {"kind": "literal", "value": []},
        {"kind": "literal", "value": {"nested": True}},
    ),
)
def test_binding_decoder_rejects_malformed_nested_shapes(binding) -> None:
    record = _config().record
    record["inputs"][0]["binding"] = binding

    with pytest.raises((TypeError, ValueError)):
        decode_run_ref_static_config(canonical_json_bytes(record))


@pytest.mark.parametrize(
    "type_descriptor",
    (
        {"kind": "primitive", "name": "Json"},
        {"kind": "primitive", "name": "String", "extra": True},
        {"kind": "list"},
        {
            "kind": "record",
            "name": "Broken",
            "fields": [
                {"name": "value", "type": {"kind": "primitive", "name": "String"}},
                {"name": "value", "type": {"kind": "primitive", "name": "String"}},
            ],
        },
        {
            "kind": "map",
            "key": {"kind": "primitive", "name": "Int"},
            "value": {"kind": "primitive", "name": "String"},
        },
    ),
)
def test_input_decoder_rejects_malformed_or_nontransportable_type_descriptor(
    type_descriptor,
) -> None:
    record = _config().record
    record["inputs"][0]["type_descriptor"] = type_descriptor

    with pytest.raises((TypeError, ValueError)):
        decode_run_ref_static_config(canonical_json_bytes(record))


@pytest.mark.parametrize("name", ("Symbol", "RunId", "PathRel"))
def test_neutral_inputs_and_results_accept_additional_transportable_primitives(
    name: str,
) -> None:
    descriptor = {"kind": "primitive", "name": name}
    row = RunRefInput(
        name="value",
        type_descriptor=descriptor,
        binding=ReferenceBinding("inputs.value"),
    )
    result_descriptor = _config().result_descriptor
    result_descriptor["envelope"]["fields"][0]["type"] = descriptor

    assert row.type_descriptor == descriptor
    validate_run_ref_result_descriptor(
        result_descriptor,
        expected_digest=canonical_sha256(result_descriptor),
    )


@pytest.mark.parametrize("name", ("Json", "Provider", "Prompt"))
def test_neutral_inputs_and_results_retain_nontransportable_primitive_rejection(
    name: str,
) -> None:
    descriptor = {"kind": "primitive", "name": name}
    with pytest.raises(ValueError):
        RunRefInput(
            name="value",
            type_descriptor=descriptor,
            binding=ReferenceBinding("inputs.value"),
        )
    result_descriptor = _config().result_descriptor
    result_descriptor["envelope"]["fields"][0]["type"] = descriptor

    with pytest.raises(ValueError):
        validate_run_ref_result_descriptor(
            result_descriptor,
            expected_digest=canonical_sha256(result_descriptor),
        )


def test_neutral_primitive_transportability_matches_compiler_decision() -> None:
    from orchestrator.workflow.run_ref.result_contract import (
        is_transportable_type_descriptor,
    )
    from orchestrator.workflow_lisp.contracts import is_transportable_result_type
    from orchestrator.workflow_lisp.normalized_type_descriptor import (
        compiler_normalized_type_descriptor,
    )
    from orchestrator.workflow_lisp.type_env import (
        FrontendTypeEnvironment,
        PrimitiveTypeRef,
    )

    names = (
        "String",
        "Int",
        "Float",
        "Bool",
        "Value",
        "Symbol",
        "RunId",
        "PathRel",
        "FutureScalar",
        "Json",
        "Provider",
        "Prompt",
    )
    type_refs = {name: PrimitiveTypeRef(name) for name in names}
    type_env = FrontendTypeEnvironment(type_refs, target_dsl_version="2.24")

    for name, type_ref in type_refs.items():
        descriptor = compiler_normalized_type_descriptor(
            type_ref,
            type_env=type_env,
        )
        assert is_transportable_type_descriptor(
            descriptor
        ) is is_transportable_result_type(type_ref)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda descriptor: descriptor["envelope"].__setitem__("name", "RunRefResult$0" * 2),
        lambda descriptor: descriptor["envelope"]["fields"].reverse(),
        lambda descriptor: descriptor["envelope"]["fields"][1]["type"].__setitem__("name", "Changed"),
        lambda descriptor: descriptor["envelope"]["fields"][2]["type"]["fields"].pop(),
        lambda descriptor: descriptor["envelope"]["fields"][0].__setitem__(
            "type", {"kind": "primitive", "name": "Json"}
        ),
        lambda descriptor: descriptor.__setitem__("extra", True),
    ),
)
def test_result_descriptor_validator_rejects_name_order_fixed_schema_and_value_tamper(
    mutate,
) -> None:
    config = _config()
    descriptor = config.result_descriptor
    mutate(descriptor)

    with pytest.raises(ValueError):
        validate_run_ref_result_descriptor(
            descriptor,
            expected_generated_name=config.generated_result_type,
            expected_digest=config.result_digest,
        )


def test_every_static_semantic_field_changes_config_digest() -> None:
    base = _config()
    mutations = []
    for path, replacement in (
        (("compiler_runtime_identity_digest",), "sha256:" + "d" * 64),
        (("site_digest",), "f" * 64),
        (("source", "resolved_commit_sha"), "f" * 40),
        (("program", "workflow_name"), "other"),
        (("inputs", 0, "name"), "other"),
        (("inputs", 0, "type_descriptor", "name"), "Value"),
        (("inputs", 0, "binding", "reference"), "inputs.other"),
    ):
        record = base.record
        target = record
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = replacement
        mutations.append(canonical_sha256(record))

    assert len(set(mutations)) == len(mutations)
    assert all(digest != base.digest for digest in mutations)


def test_every_root_wire_field_is_config_digest_bearing() -> None:
    base = _config()
    replacements = {
        "schema_version": "run_ref_static_config.v2",
        "target_dsl_version": "2.25",
        "lowering_route": "other",
        "lowering_schema_version": 3,
        "compiler_runtime_identity_digest": "sha256:" + "d" * 64,
        "site_digest": "f" * 64,
        "generated_result_type": "RunRefResult$ffffffffffffffff",
        "source": {"changed": True},
        "program": {"changed": True},
        "inputs": [],
        "result_descriptor": {"changed": True},
        "result_digest": "sha256:" + "d" * 64,
    }
    digests = []
    for field_name, replacement in replacements.items():
        record = base.record
        record[field_name] = replacement
        digests.append(canonical_sha256(record))

    assert len(set(digests)) == len(replacements)
    assert all(digest != base.digest for digest in digests)


def _live_compiler_result_contract():
    from tests.test_workflow_lisp_run_ref import (
        _mode_one_expr,
        _run_ref_result_contract,
        _transportable_types,
    )

    expr = _mode_one_expr()
    value_type = _transportable_types(expr.span)[0]
    return _run_ref_result_contract(expr, value_type)[0]


def test_compiler_to_neutral_result_contract_matches_fixed_literal() -> None:
    contract = _live_compiler_result_contract()

    assert contract.descriptor == _FIXED_RESULT_DESCRIPTOR
    assert contract.digest == _FIXED_RESULT_DIGEST
    validate_run_ref_result_descriptor(
        deepcopy(_FIXED_RESULT_DESCRIPTOR),
        expected_digest=_FIXED_RESULT_DIGEST,
    )


def test_compiler_result_builder_cross_checks_neutral_descriptor_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.workflow_lisp.run_ref_result_contract as result_contract_module

    def reject(*_args, **_kwargs):
        raise ValueError("neutral cross-check sentinel")

    monkeypatch.setattr(
        result_contract_module,
        "validate_run_ref_result_descriptor",
        reject,
    )

    with pytest.raises(ValueError):
        _live_compiler_result_contract()


def test_compiler_result_contract_runs_with_forbidden_config_import_blocked() -> None:
    check = subprocess.run(
        (
            sys.executable,
            "-c",
            r'''
import importlib
import importlib.abc
import sys

blocked_name = "orchestrator.workflow.run_ref.config"

class BlockedImport(RuntimeError):
    pass

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == blocked_name:
            raise BlockedImport(fullname)
        return None

sys.meta_path.insert(0, Blocker())
from orchestrator.workflow_lisp.definitions import RecordDef, RecordField
from orchestrator.workflow_lisp.run_ref_result_contract import (
    derive_run_ref_result_contract,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import (
    FrontendTypeEnvironment,
    PrimitiveTypeRef,
    RecordTypeRef,
)
from orchestrator.workflow_lisp.typecheck_run_ref import compiler_run_ref_fixed_types

primitive_names = ("String", "Int", "Bool", "Value", "RunId")
primitives = {name: PrimitiveTypeRef(name) for name in primitive_names}
type_env = FrontendTypeEnvironment(primitives, target_dsl_version="2.24")
fixed = dict(compiler_run_ref_fixed_types(type_env))
position = SourcePosition(
    path="<prelude:dependency-probe>", line=1, column=1, offset=0
)
span = SourceSpan(start=position, end=position)
name = "RunRefResult$0123456789abcdef"
definition = RecordDef(
    name=name,
    fields=tuple(
        RecordField(name=field_name, type_name=type_ref.name, span=span)
        for field_name, type_ref in (
            ("value", primitives["Bool"]),
            ("workspace_delta", fixed["WorkspaceDelta"]),
            ("accounting", fixed["RunRefAccounting"]),
        )
    ),
    span=span,
)
result_type = RecordTypeRef(
    name=name,
    definition=definition,
    field_types={
        "value": primitives["Bool"],
        "workspace_delta": fixed["WorkspaceDelta"],
        "accounting": fixed["RunRefAccounting"],
    },
)
contract = derive_run_ref_result_contract(result_type, type_env=type_env)
assert contract.digest.startswith("sha256:")
assert blocked_name not in sys.modules
try:
    importlib.import_module(blocked_name)
except BlockedImport:
    pass
else:
    raise AssertionError("forbidden config import was not blocked")
''',
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr


def test_normalized_descriptor_validator_is_reexported_from_neutral_owner() -> None:
    from orchestrator.workflow.type_descriptor import (
        validate_compiler_normalized_type_descriptor as neutral_validator,
    )
    from orchestrator.workflow_lisp.normalized_type_descriptor import (
        validate_compiler_normalized_type_descriptor as compiler_validator,
    )

    assert compiler_validator is neutral_validator


def test_neutral_config_import_succeeds_with_workflow_lisp_and_ir_blocked() -> None:
    check = subprocess.run(
        (
            sys.executable,
            "-c",
            r'''
import importlib
import importlib.abc
import sys

# Isolate the neutral module's own dependency closure from the repository's
# pre-existing eager workflow-package compatibility exports.
import orchestrator.workflow

config_name = "orchestrator.workflow.run_ref.config"
neutral_children = {
    config_name,
    "orchestrator.workflow.run_ref.result_contract",
    "orchestrator.workflow.type_descriptor",
}

def forbidden(fullname):
    return (
        fullname.startswith("orchestrator.workflow_lisp")
        or fullname == "orchestrator.workflow.semantic_ir"
        or fullname == "orchestrator.workflow.executable_ir"
    )

for loaded_name in tuple(sys.modules):
    if forbidden(loaded_name) or loaded_name in neutral_children:
        del sys.modules[loaded_name]
assert not any(forbidden(name) for name in sys.modules)
assert config_name not in sys.modules

class BlockedImport(RuntimeError):
    pass

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if forbidden(fullname):
            raise BlockedImport(fullname)
        return None

sys.meta_path.insert(0, Blocker())
config = importlib.import_module(config_name)
assert config.RUN_REF_STATIC_CONFIG_SCHEMA == "run_ref_static_config.v1"
assert not any(forbidden(name) for name in sys.modules)
try:
    importlib.import_module("orchestrator.workflow.semantic_ir")
except BlockedImport:
    pass
else:
    raise AssertionError("forbidden IR import was not blocked")
''',
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr


def test_binding_literals_reject_non_scalar_and_nonfinite_values() -> None:
    for value in ([], {}, math.nan, math.inf, -math.inf):
        with pytest.raises((TypeError, ValueError)):
            LiteralBinding(value)
