from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
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


def _compiler_contract(return_index: int = 0):
    from tests.test_workflow_lisp_run_ref import (
        _mode_one_expr,
        _run_ref_result_contract,
        _transportable_types,
    )

    expr = _mode_one_expr()
    value_type = _transportable_types(expr.span)[return_index]
    contract, _, type_env = _run_ref_result_contract(expr, value_type)
    return contract, value_type, type_env


def _site_digest(result_descriptor: dict[str, object]) -> str:
    generated_name = result_descriptor["envelope"]["name"]
    return generated_name.removeprefix("RunRefResult$") + "0" * 48


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
    return_index: int = 0,
    inputs=None,
    source: SourceRequest | None = None,
    return_refinement=_AUTO_RETURN_REFINEMENT,
):
    contract, _, _ = _compiler_contract(return_index)
    descriptor = contract.descriptor
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
        result_digest=contract.digest,
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
        return_index=7,
        return_refinement=None,
    )

    assert omitted.record["program"]["return_refinement"] is None
    with pytest.raises(ValueError):
        _config(mode="path", return_index=0, return_refinement=None)


def test_path_program_distinguishes_omitted_and_explicit_value_refinement() -> None:
    omitted = _config(
        mode="path",
        return_index=7,
        return_refinement=None,
    )
    explicit = _config(
        mode="path",
        return_index=7,
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
            return_index=0,
            return_refinement={"kind": "primitive", "name": "String"},
        )


@pytest.mark.parametrize("return_index", range(8))
def test_static_config_accepts_all_transportable_result_descriptor_roots(
    return_index: int,
) -> None:
    config = _config(return_index=return_index)

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


@pytest.mark.parametrize("return_index", range(8))
def test_static_inputs_accept_all_transportable_descriptor_roots(
    return_index: int,
) -> None:
    from orchestrator.workflow_lisp.normalized_type_descriptor import (
        compiler_normalized_type_descriptor,
    )

    _, value_type, type_env = _compiler_contract(return_index)
    row = RunRefInput(
        name="value",
        type_descriptor=compiler_normalized_type_descriptor(
            value_type,
            type_env=type_env,
        ),
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
        _compiler_contract()


def test_compiler_result_builder_imports_narrow_neutral_result_owner() -> None:
    import inspect
    import orchestrator.workflow_lisp.run_ref_result_contract as result_contract_module

    source = inspect.getsource(result_contract_module)

    assert "workflow.run_ref.result_contract" in source
    assert "workflow.run_ref.config" not in source


def test_normalized_descriptor_validator_is_reexported_from_neutral_owner() -> None:
    from orchestrator.workflow.type_descriptor import (
        validate_compiler_normalized_type_descriptor as neutral_validator,
    )
    from orchestrator.workflow_lisp.normalized_type_descriptor import (
        validate_compiler_normalized_type_descriptor as compiler_validator,
    )

    assert compiler_validator is neutral_validator


def test_neutral_config_import_does_not_load_workflow_lisp_or_ir() -> None:
    check = subprocess.run(
        (
            sys.executable,
            "-c",
            "import inspect, sys; import orchestrator.workflow.run_ref.config as config; "
            "assert not any(name.startswith('orchestrator.workflow_lisp') for name in sys.modules); "
            "source = inspect.getsource(config); "
            "assert 'semantic_ir' not in source and 'executable_ir' not in source",
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
