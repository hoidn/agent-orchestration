from pathlib import Path

import pytest

from orchestrator.contracts.prompt_contract import (
    render_output_bundle_contract_block,
)
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.prompt_contract_test_helpers import parse_prompt_contract_document


def _write_value_parity_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "transportable_value_parity.orc"
    module_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.19")
  (defmodule transportable-value-parity)
  (export entry)
  (defproc pass-value ((payload Value)) -> Value
    :effects ()
    :lowering inline
    payload)
  (defworkflow child ((payload Value)) -> Value
    (pass-value payload))
  (defworkflow entry () -> Value
    (let* ((provider-payload
             (provider-result providers.value
               :prompt prompts.value
               :inputs ()
               :returns
                 (result Value
                   :description "Mixed transportable payload."
                   :format-hint "One direct JSON document root.")))
           (command-payload
             (command-result emit-value
               :argv ("python" "scripts/emit_value.py")
               :returns Value)))
      (call child :payload provider-payload))))
""",
        encoding="utf-8",
    )
    prompt_path = tmp_path / "prompts" / "value.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("Return the requested payload.\n", encoding="utf-8")
    return module_path


def _write_collection_value_module(
    tmp_path: Path,
    *,
    return_type: str,
) -> Path:
    module_path = tmp_path / "transportable_value_collection.orc"
    module_path.write_text(
        f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.19")
  (defmodule transportable-value-collection)
  (export entry)
  (defworkflow entry () -> {return_type}
    (provider-result providers.value
      :prompt prompts.value
      :inputs ()
      :returns {return_type})))
""",
        encoding="utf-8",
    )
    prompt_path = tmp_path / "prompts" / "value.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("Return the requested payload.\n", encoding="utf-8")
    return module_path


def _contract_schema(value: dict) -> dict:
    schema_keys = (
        "kind",
        "type",
        "allowed",
        "under",
        "must_exist_target",
        "item",
        "items",
        "keys",
        "values",
    )
    return {
        key: (
            _contract_schema(item)
            if isinstance(item := value[key], dict)
            else item
        )
        for key in schema_keys
        if key in value
    }


def _collection_contract_projection(
    tmp_path: Path,
    *,
    lowering_route: str,
    return_type: str,
) -> dict:
    workspace = tmp_path / lowering_route
    workspace.mkdir()
    result = compile_stage3_module(
        _write_collection_value_module(
            workspace,
            return_type=return_type,
        ),
        entry_workflow="entry",
        provider_externs={"providers.value": "test-provider"},
        prompt_externs={"prompts.value": "prompts/value.md"},
        validate_shared=True,
        workspace_root=workspace,
        lowering_route=lowering_route,
    )
    entry = next(
        lowered
        for lowered in result.lowered_workflows
        if lowered.typed_workflow.definition.name == "entry"
    )
    bundle = result.validated_bundles["entry"]
    provider_node = next(
        node
        for node in bundle.ir.nodes.values()
        if node.execution_config is not None
        and node.execution_config.common.output_bundle is not None
    )
    executable_field = provider_node.execution_config.common.output_bundle[
        "fields"
    ][0]
    semantic_workflow = bundle.semantic_ir.workflows["entry"]
    semantic_contract = bundle.semantic_ir.contracts[
        semantic_workflow.output_contract_ids["__result__"]
    ]
    semantic_type = bundle.semantic_ir.types[semantic_contract.type_id]

    return {
        "lowered_public": _contract_schema(
            entry.authored_mapping["outputs"]["__result__"]
        ),
        "surface_public": _contract_schema(
            dict(bundle.surface.outputs["__result__"].definition)
        ),
        "semantic_contract": {
            "contract_kind": semantic_contract.contract_kind,
            "value_type": semantic_contract.value_type,
            "definition": _contract_schema(dict(semantic_contract.definition)),
        },
        "semantic_type": {
            "type_kind": semantic_type.type_kind,
            "value_type": semantic_type.value_type,
            "definition": _contract_schema(dict(semantic_type.definition)),
        },
        "executable_field": {
            "name": executable_field["name"],
            "json_pointer": executable_field["json_pointer"],
            **_contract_schema(dict(executable_field)),
        },
    }


def _semantic_contract_projection(
    bundle,
    *,
    direction: str,
    contract_name: str,
) -> dict:
    semantic_workflow = bundle.semantic_ir.workflows[bundle.surface.name]
    contract_ids = getattr(
        semantic_workflow,
        f"{direction}_contract_ids",
    )
    contract = bundle.semantic_ir.contracts[contract_ids[contract_name]]
    type_definition = bundle.semantic_ir.types[contract.type_id]
    return {
        "contract_kind": contract.contract_kind,
        "value_type": contract.value_type,
        "definition": _contract_schema(dict(contract.definition)),
        "type_kind": type_definition.type_kind,
        "type_value": type_definition.value_type,
        "type_definition": _contract_schema(dict(type_definition.definition)),
    }


def _scalar_contract_projection(
    tmp_path: Path,
    *,
    lowering_route: str,
) -> dict:
    workspace = tmp_path / lowering_route
    workspace.mkdir()
    result = compile_stage3_module(
        _write_value_parity_module(workspace),
        entry_workflow="entry",
        provider_externs={"providers.value": "test-provider"},
        prompt_externs={"prompts.value": "prompts/value.md"},
        command_boundaries={
            "emit-value": ExternalToolBinding(
                name="emit-value",
                stable_command=("python", "scripts/emit_value.py"),
            )
        },
        validate_shared=True,
        workspace_root=workspace,
        lowering_route=lowering_route,
    )
    entry = next(
        lowered
        for lowered in result.lowered_workflows
        if lowered.typed_workflow.definition.name == "entry"
    )
    child = next(
        lowered
        for lowered in result.lowered_workflows
        if lowered.typed_workflow.definition.name == "child"
    )
    entry_bundle = result.validated_bundles["entry"]
    child_bundle = result.validated_bundles["child"]
    nodes_by_kind = {
        node.kind.value: node
        for node in entry_bundle.ir.nodes.values()
    }
    provider_bundle = nodes_by_kind[
        "provider"
    ].execution_config.common.output_bundle
    command_bundle = nodes_by_kind[
        "command"
    ].execution_config.common.output_bundle
    call_node = nodes_by_kind["call_boundary"]
    child_materialization = next(iter(child_bundle.ir.nodes.values()))
    child_materialized_value = (
        child_materialization.execution_config.materialize_artifacts["values"][0]
    )
    entry_output = entry.authored_mapping["outputs"]["__result__"]
    call_step = next(
        step for step in entry.authored_mapping["steps"] if "call" in step
    )

    return {
        "entry_public": {
            "lowered": _contract_schema(entry_output),
            "surface": _contract_schema(
                dict(
                    entry_bundle.surface.outputs[
                        "__result__"
                    ].definition
                )
            ),
            "semantic": _semantic_contract_projection(
                entry_bundle,
                direction="output",
                contract_name="__result__",
            ),
            "returns_call_result": entry_output["from"] == {
                "ref": (
                    f"root.steps.{call_step['name']}."
                    "artifacts.__result__"
                )
            },
        },
        "provider": {
            "path": provider_bundle["path"],
            "field_count": len(provider_bundle["fields"]),
            "field": {
                "name": provider_bundle["fields"][0]["name"],
                "json_pointer": provider_bundle["fields"][0][
                    "json_pointer"
                ],
                **_contract_schema(
                    dict(provider_bundle["fields"][0])
                ),
            },
            "guidance": parse_prompt_contract_document(
                render_output_bundle_contract_block(provider_bundle)
            ),
        },
        "command": {
            "field_count": len(command_bundle["fields"]),
            "field": {
                "name": command_bundle["fields"][0]["name"],
                "json_pointer": command_bundle["fields"][0][
                    "json_pointer"
                ],
                **_contract_schema(
                    dict(command_bundle["fields"][0])
                ),
            },
        },
        "workflow_call": {
            "callee": call_node.call_alias,
            "surface_callee": call_step["call"],
            "payload_from_provider": call_step["with"]["payload"] == {
                "ref": (
                    "root.steps.entry__provider-payload."
                    "artifacts.__result__"
                )
            },
        },
        "child": {
            "lowered_input": _contract_schema(
                child.authored_mapping["inputs"]["payload"]
            ),
            "lowered_output": _contract_schema(
                child.authored_mapping["outputs"]["__result__"]
            ),
            "surface_input": _contract_schema(
                dict(child_bundle.surface.inputs["payload"].definition)
            ),
            "surface_output": _contract_schema(
                dict(
                    child_bundle.surface.outputs[
                        "__result__"
                    ].definition
                )
            ),
            "semantic_input": _semantic_contract_projection(
                child_bundle,
                direction="input",
                contract_name="payload",
            ),
            "semantic_output": _semantic_contract_projection(
                child_bundle,
                direction="output",
                contract_name="__result__",
            ),
            "materialized_result": {
                "name": child_materialized_value["name"],
                "source": dict(child_materialized_value["source"]),
                "contract": _contract_schema(
                    dict(child_materialized_value["contract"])
                ),
            },
        },
    }


def test_transportable_value_classic_and_wcc_contract_surfaces_are_equivalent(
    tmp_path: Path,
) -> None:
    classic = _scalar_contract_projection(
        tmp_path,
        lowering_route="legacy",
    )
    wcc_m4 = _scalar_contract_projection(
        tmp_path,
        lowering_route="wcc_m4",
    )
    root_value = {"kind": "value", "type": "value"}
    direct_field = {
        "name": "__result__",
        "json_pointer": "",
        "type": "value",
    }

    assert classic == wcc_m4
    assert classic["entry_public"]["lowered"] == root_value
    assert classic["entry_public"]["surface"] == root_value
    assert classic["entry_public"]["returns_call_result"] is True
    assert classic["provider"]["field_count"] == 1
    assert classic["provider"]["field"] == direct_field
    assert classic["command"]["field_count"] == 1
    assert classic["command"]["field"] == direct_field
    assert classic["workflow_call"] == {
        "callee": "child",
        "surface_callee": "child",
        "payload_from_provider": True,
    }
    assert classic["child"]["lowered_input"] == root_value
    assert classic["child"]["lowered_output"] == root_value
    assert classic["child"]["surface_input"] == root_value
    assert classic["child"]["surface_output"] == root_value
    assert classic["child"]["materialized_result"] == {
        "name": "__result__",
        "source": {"ref": "inputs.payload"},
        "contract": root_value,
    }
    guidance = classic["provider"]["guidance"]
    assert guidance["path"] == classic["provider"]["path"]
    assert guidance["type"] == "value"
    assert guidance["description"] == "Mixed transportable payload."
    assert guidance["format_hint"] == "One direct JSON document root."
    assert "name" not in guidance
    assert "json_pointer" not in guidance
    assert "fields" not in guidance


@pytest.mark.parametrize(
    ("return_type", "descriptor"),
    (
        (
            "Optional[Value]",
            {"type": "optional", "item": {"type": "value"}},
        ),
        (
            "List[Value]",
            {"type": "list", "items": {"type": "value"}},
        ),
        (
            "Map[String, Value]",
            {
                "type": "map",
                "keys": {"type": "string"},
                "values": {"type": "value"},
            },
        ),
    ),
    ids=("optional", "list", "map"),
)
def test_transportable_value_collection_contracts_are_route_equivalent(
    tmp_path: Path,
    return_type: str,
    descriptor: dict,
) -> None:
    classic = _collection_contract_projection(
        tmp_path,
        lowering_route="legacy",
        return_type=return_type,
    )
    wcc_m4 = _collection_contract_projection(
        tmp_path,
        lowering_route="wcc_m4",
        return_type=return_type,
    )
    expected_public = {"kind": "collection", **descriptor}
    expected_executable = {
        "name": "__result__",
        "json_pointer": "",
        **descriptor,
    }

    assert classic == wcc_m4
    assert classic["lowered_public"] == expected_public
    assert classic["surface_public"] == expected_public
    assert classic["semantic_contract"]["definition"] == expected_public
    assert classic["semantic_type"]["definition"] == expected_public
    assert classic["executable_field"] == expected_executable
