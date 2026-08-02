"""Generic target-2.25 nested structural transport contracts."""

from __future__ import annotations

import json
import math

import pytest

from orchestrator.state import StateManager, StepResult
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow.type_descriptor import (
    MAX_TRANSPORT_VALUE_BYTES,
    MAX_TRANSPORT_VALUE_DEPTH,
    is_transportable_type_descriptor,
    transport_schema_for_descriptor,
    validate_transport_value,
)
from orchestrator.workflow.run_ref.result_contract import (
    is_transportable_type_descriptor as run_ref_is_transportable,
)


def _primitive(name: str) -> dict[str, object]:
    return {"kind": "primitive", "name": name}


def _field(name: str, descriptor: dict[str, object]) -> dict[str, object]:
    return {"name": name, "type": descriptor}


def _record(name: str = "Measurement") -> dict[str, object]:
    return {
        "kind": "record",
        "name": name,
        "fields": [
            _field("label", _primitive("String")),
            _field("count", _primitive("Int")),
        ],
    }


def _union() -> dict[str, object]:
    return {
        "kind": "union",
        "name": "Outcome",
        "variants": [
            {
                "name": "COMPLETED",
                "fields": [_field("result", _record())],
            },
            {
                "name": "FAILED",
                "fields": [_field("reason", _primitive("String"))],
            },
        ],
    }


def _single_payload_union(payload_name: str) -> dict[str, object]:
    return {
        "kind": "union",
        "name": "CollisionUnion",
        "variants": [
            {
                "name": "VALUE",
                "fields": [_field(payload_name, _primitive("String"))],
            }
        ],
    }


def _nested_descriptors() -> tuple[dict[str, object], ...]:
    return (
        {"kind": "list", "item": _record()},
        {
            "kind": "optional",
            "item": {"kind": "list", "item": _union()},
        },
        {
            "kind": "map",
            "key": _primitive("String"),
            "value": {"kind": "list", "item": _record()},
        },
    )


@pytest.mark.parametrize("descriptor", _nested_descriptors())
def test_nested_structures_require_explicit_transport_capability(
    descriptor: dict[str, object],
) -> None:
    assert not is_transportable_type_descriptor(descriptor)
    assert is_transportable_type_descriptor(
        descriptor,
        allow_nested_structures=True,
    )
    assert not run_ref_is_transportable(descriptor)
    assert run_ref_is_transportable(
        descriptor,
        allow_nested_structures=True,
    )


def test_schema_encoder_preserves_direct_record_and_tagged_union_wire() -> None:
    descriptor = {
        "kind": "list",
        "item": _union(),
    }

    assert transport_schema_for_descriptor(
        descriptor,
        allow_nested_structures=True,
    ) == {
        "type": "list",
        "items": {
            "type": "union",
            "union_name": "Outcome",
            "discriminant": {
                "name": "variant",
                "type": "enum",
                "allowed": ["COMPLETED", "FAILED"],
            },
            "variants": {
                "COMPLETED": {
                    "fields": [
                        {
                            "name": "result",
                            "type": "record",
                            "record_name": "Measurement",
                            "fields": [
                                {"name": "label", "type": "string"},
                                {"name": "count", "type": "integer"},
                            ],
                        }
                    ]
                },
                "FAILED": {
                    "fields": [{"name": "reason", "type": "string"}]
                },
            },
        },
    }


def test_direct_structural_union_reserves_variant_payload_name() -> None:
    collision_union = _single_payload_union("variant")
    descriptor = {"kind": "list", "item": collision_union}

    assert is_transportable_type_descriptor(collision_union)
    assert not is_transportable_type_descriptor(
        descriptor,
        allow_nested_structures=True,
    )
    with pytest.raises(ValueError, match="not transportable"):
        transport_schema_for_descriptor(
            descriptor,
            allow_nested_structures=True,
        )
    with pytest.raises(ValueError, match="not transportable"):
        validate_transport_value(
            [{"variant": "VALUE"}],
            descriptor,
            allow_nested_structures=True,
        )


def test_direct_structural_union_accepts_nonreserved_payload_name() -> None:
    descriptor = {
        "kind": "list",
        "item": _single_payload_union("payload"),
    }
    value = [{"variant": "VALUE", "payload": "kept"}]

    assert is_transportable_type_descriptor(
        descriptor,
        allow_nested_structures=True,
    )
    schema = transport_schema_for_descriptor(
        descriptor,
        allow_nested_structures=True,
    )
    assert schema["items"]["variants"]["VALUE"]["fields"] == [
        {"name": "payload", "type": "string"}
    ]
    assert validate_transport_value(
        value,
        descriptor,
        allow_nested_structures=True,
    ) == value


def test_direct_nested_values_validate_without_an_envelope() -> None:
    descriptor = {"kind": "list", "item": _union()}
    value = [
        {
            "variant": "COMPLETED",
            "result": {"label": "alpha", "count": 2},
        },
        {"variant": "FAILED", "reason": "timeout"},
    ]

    assert validate_transport_value(
        value,
        descriptor,
        allow_nested_structures=True,
    ) == value


@pytest.mark.parametrize(
    ("value", "match"),
    (
        ([{"variant": "FAILED"}], "record fields"),
        ([{"variant": "FAILED", "reason": "x", "extra": 1}], "record fields"),
        ([{"variant": "UNKNOWN", "reason": "x"}], "union tag"),
        (
            [{"variant": "COMPLETED", "result": {"label": "x", "count": True}}],
            "Int",
        ),
    ),
)
def test_nested_record_and_union_validation_is_closed(
    value: object,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        validate_transport_value(
            value,
            {"kind": "list", "item": _union()},
            allow_nested_structures=True,
        )


@pytest.mark.parametrize(
    "descriptor",
    (
        {"kind": "list", "item": _primitive("Provider")},
        {
            "kind": "map",
            "key": _primitive("Int"),
            "value": _primitive("String"),
        },
    ),
)
def test_nontransportable_nested_descriptors_remain_rejected(
    descriptor: dict[str, object],
) -> None:
    assert not is_transportable_type_descriptor(
        descriptor,
        allow_nested_structures=True,
    )
    with pytest.raises(ValueError, match="not transportable"):
        transport_schema_for_descriptor(
            descriptor,
            allow_nested_structures=True,
        )


def test_non_string_runtime_map_key_and_nonfinite_float_reject() -> None:
    map_descriptor = {
        "kind": "map",
        "key": _primitive("String"),
        "value": _primitive("Int"),
    }
    with pytest.raises(ValueError, match="map key"):
        validate_transport_value(
            {1: 2},
            map_descriptor,
            allow_nested_structures=True,
        )

    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="finite"):
            validate_transport_value(
                value,
                _primitive("Float"),
                allow_nested_structures=True,
            )


def test_float_validation_rejects_integer_too_large_to_convert() -> None:
    descriptor = _primitive("Float")

    assert validate_transport_value(
        2,
        descriptor,
        allow_nested_structures=True,
    ) == 2.0
    assert validate_transport_value(
        2.5,
        descriptor,
        allow_nested_structures=True,
    ) == 2.5
    with pytest.raises(ValueError, match="finite Float"):
        validate_transport_value(
            10**10000,
            descriptor,
            allow_nested_structures=True,
        )


def _nested_list_descriptor(depth: int) -> dict[str, object]:
    descriptor = _primitive("String")
    for _ in range(depth):
        descriptor = {"kind": "list", "item": descriptor}
    return descriptor


def _nested_list_value(depth: int) -> object:
    value: object = "leaf"
    for _ in range(depth):
        value = [value]
    return value


def test_transport_depth_bound_is_root_zero_and_inclusive() -> None:
    assert MAX_TRANSPORT_VALUE_DEPTH == 64
    assert validate_transport_value(
        _nested_list_value(64),
        _nested_list_descriptor(64),
        allow_nested_structures=True,
    ) == _nested_list_value(64)

    with pytest.raises(ValueError, match="depth"):
        validate_transport_value(
            _nested_list_value(65),
            _nested_list_descriptor(65),
            allow_nested_structures=True,
        )


def test_transport_canonical_json_byte_bound_is_inclusive() -> None:
    assert MAX_TRANSPORT_VALUE_BYTES == 16_777_216
    exact = "x" * (MAX_TRANSPORT_VALUE_BYTES - 2)
    assert validate_transport_value(
        exact,
        _primitive("String"),
        allow_nested_structures=True,
    ) == exact

    with pytest.raises(ValueError, match="canonical JSON"):
        validate_transport_value(
            exact + "x",
            _primitive("String"),
            allow_nested_structures=True,
        )


def test_nested_direct_value_persists_and_reloads_without_wire_rewriting(
    tmp_path,
) -> None:
    descriptor = {"kind": "list", "item": _union()}
    value = [
        {
            "variant": "COMPLETED",
            "result": {"label": "café", "count": 2},
        }
    ]
    normalized = validate_transport_value(
        value,
        descriptor,
        allow_nested_structures=True,
    )
    (tmp_path / "nested_transport.orc").write_text(
        "(workflow-lisp)\n",
        encoding="utf-8",
    )
    manager = StateManager(tmp_path, run_id="nested-transport-reload")
    manager.initialize("nested_transport.orc")
    manager.update_step(
        "provider",
        StepResult(status="completed", artifacts={"result": normalized}),
    )

    persisted_document = json.loads(manager.state_file.read_text(encoding="utf-8"))
    assert persisted_document["steps"]["provider"]["artifacts"]["result"] == value
    reloaded = StateManager(
        tmp_path,
        run_id="nested-transport-reload",
    ).load()
    assert validate_transport_value(
        reloaded.steps["provider"]["artifacts"]["result"],
        descriptor,
        allow_nested_structures=True,
    ) == value


def _nested_provider_source(target: str) -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target}")',
            "  (defmodule nested_transport)",
            "  (defrecord Measurement",
            "    (label String)",
            "    (count Int))",
            "  (defrecord Result",
            "    (measurements List[Measurement]))",
            "  (defrecord WorkflowOutput",
            "    (report String))",
            "  (defworkflow orchestrate",
            "    ()",
            "    -> WorkflowOutput",
            "    (let* ((result",
            "             (provider-result providers.execute",
            "               :prompt prompts.execute",
            "               :inputs ()",
            "               :returns Result)))",
            '      (record WorkflowOutput :report "ok"))))',
        )
    )


def _nested_root_provider_source(target: str) -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target}")',
            "  (defmodule nested_root_transport)",
            "  (defrecord Measurement",
            "    (label String)",
            "    (count Int))",
            "  (defworkflow orchestrate",
            "    ()",
            "    -> List[Measurement]",
            "    (provider-result providers.execute",
            "      :prompt prompts.execute",
            "      :inputs ()",
            "      :returns List[Measurement])))",
        )
    )


def test_frontend_gates_nested_collection_transport_at_target_225(
    tmp_path,
) -> None:
    old_path = tmp_path / "nested_224.orc"
    old_path.write_text(_nested_provider_source("2.24"), encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as caught:
        compile_stage3_module(
            old_path,
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.execute": "prompts/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )
    assert caught.value.diagnostics[0].code == "collection_element_type_unsupported"

    new_path = tmp_path / "nested_225.orc"
    new_path.write_text(_nested_provider_source("2.25"), encoding="utf-8")
    result = compile_stage3_module(
        new_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )
    provider_step = result.lowered_workflows[0].authored_mapping["steps"][0]
    nested_field = provider_step["output_bundle"]["fields"][0]
    assert nested_field["type"] == "list"
    assert nested_field["items"]["type"] == "record"
    assert nested_field["items"]["record_name"].endswith("Measurement")


def test_target_225_native_root_preserves_nested_record_schema(tmp_path) -> None:
    old_path = tmp_path / "nested_root_224.orc"
    old_path.write_text(_nested_root_provider_source("2.24"), encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as caught:
        compile_stage3_module(
            old_path,
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.execute": "prompts/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )
    assert caught.value.diagnostics[0].code == "workflow_return_type_invalid"

    new_path = tmp_path / "nested_root_225.orc"
    new_path.write_text(_nested_root_provider_source("2.25"), encoding="utf-8")
    result = compile_stage3_module(
        new_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    output_contract = dict(
        result.lowered_workflows[0].authored_mapping["outputs"]["__result__"]
    )
    assert output_contract.pop("from") == {
        "ref": "root.steps.orchestrate__result.artifacts.__result__"
    }
    assert output_contract == {
        "kind": "collection",
        "type": "list",
        "items": {
            "type": "record",
            "record_name": "Measurement",
            "fields": [
                {"name": "label", "type": "string"},
                {"name": "count", "type": "integer"},
            ],
        },
    }


@pytest.mark.parametrize("root_type", ("Measurement", "Outcome"))
def test_target_225_imported_native_root_reconstructs_nested_structural_type(
    tmp_path,
    root_type: str,
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    child_path = source_root / "child.orc"
    child_path.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.25")',
                "  (defmodule child)",
                "  (export measurements)",
                "  (defenum Status READY FAILED)",
                "  (defpath ReportPath",
                "    :kind relpath",
                '    :under "artifacts"',
                "    :must-exist false)",
                "  (defrecord Measurement",
                "    (label String)",
                "    (count Int)",
                "    (status Status)",
                "    (report ReportPath))",
                "  (defunion Outcome",
                "    (READY",
                "      (status Status)",
                "      (report ReportPath))",
                "    (FAILED",
                "      (status Status)",
                "      (report ReportPath)))",
                f"  (defworkflow measurements () -> List[{root_type}]",
                "    (provider-result providers.execute",
                "      :prompt prompts.execute",
                "      :inputs ()",
                f"      :returns List[{root_type}])))",
            )
        ),
        encoding="utf-8",
    )
    compiled_child = compile_stage3_module(
        child_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    child_bundle = next(
        bundle
        for name, bundle in compiled_child.validated_bundles.items()
        if name == "measurements" or name.endswith("::measurements")
    )

    entry_path = source_root / "entry.orc"
    entry_path.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.25")',
                "  (defmodule entry)",
                "  (export run)",
                "  (defenum Status READY FAILED)",
                "  (defpath ReportPath",
                "    :kind relpath",
                '    :under "artifacts"',
                "    :must-exist false)",
                "  (defrecord Measurement",
                "    (label String)",
                "    (count Int)",
                "    (status Status)",
                "    (report ReportPath))",
                "  (defunion Outcome",
                "    (READY",
                "      (status Status)",
                "      (report ReportPath))",
                "    (FAILED",
                "      (status Status)",
                "      (report ReportPath)))",
                f"  (defworkflow run () -> List[{root_type}]",
                "    (call measurements)))",
            )
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        entry_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
        imported_workflow_bundles={"measurements": child_bundle},
        validate_shared=False,
        workspace_root=tmp_path,
    )

    return_type = result.typed_workflows[0].signature.return_type_ref
    assert return_type.name == f"List[{root_type}]"
    item_type = return_type.item_type_ref
    assert item_type.name == root_type
    fields = (
        item_type.field_types
        if root_type == "Measurement"
        else item_type.variant_field_types["READY"]
    )
    assert fields["status"].name == "Status"
    report_type = fields["report"]
    assert report_type.name == "ReportPath"
    assert report_type.definition.under == "artifacts"
    assert report_type.definition.must_exist is False
