"""Behavior and replay identity of the evaluated JSON shape presentation."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from orchestrator.contracts.prompt_contract import (
    render_output_bundle_contract_block,
    render_variant_output_contract_block,
)
from orchestrator.workflow.evaluated.prompts import assemble_provider_prompt
from orchestrator.workflow.type_descriptor import transport_descriptor_for_schema
from tests.test_workflow_evaluated_provider_delivery import _provider_node


FROZEN = Path(__file__).parent / "fixtures/provider_delivery_file1/rendered_contracts.json"


def _render(node):
    return assemble_provider_prompt(node, (), source_text="TASK", dependency_snapshot=None,
        result_path="selected-result.json", delivery="file/2")


def _node(schema, payload):
    return {"class": "provider", "inputs": [], "prompt": {"fills": []},
        "result": transport_descriptor_for_schema(schema),
        "contract": {"kind": "variant_output" if schema["type"] == "union" else "output_bundle",
                     "payload": payload}}


@pytest.mark.parametrize("kind", ["root", "record", "union"])
@pytest.mark.parametrize("delivery", ["legacy", "file"])
def test_historical_contract_bytes_are_frozen(kind, delivery):
    frozen = json.loads(FROZEN.read_text())[kind]
    renderer = render_variant_output_contract_block if kind == "union" else render_output_bundle_contract_block
    assert renderer(frozen["payload"], delivery=delivery).encode() == frozen["rendered"][delivery].encode()


def test_compiled_nested_record_keeps_actual_keys_empty_records_and_guidance(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defrecord Empty)
      (defrecord Notes (notes String :description "leaf" :format-hint "text" :example "authored"))
      (defrecord Result (evidence Notes :description "ancestor") (empty Empty) (literal__key Bool :example false))
      (defworkflow run ((message String)) -> (result Result :description "overall must stay outside")
        (provider-result providers.review :prompt prompts.base :inputs ()
          :returns (result Result :description "call root"))))'''
    node = _provider_node(tmp_path, source)
    before = deepcopy(node)

    prompt = _render(node)

    assert '"evidence": {' in prompt and '"notes": <string>' in prompt
    assert '"empty": {}' in prompt and '"literal__key": <boolean>' in prompt
    for metadata in ({"description": "ancestor"},
                     {"description": "leaf", "format_hint": "text", "example": "authored"},
                     {"example": False}):
        assert json.dumps(metadata, separators=(",", ":"), ensure_ascii=False) in prompt
    assert "call root" in prompt and "overall must stay outside" not in prompt
    assert "evidence__notes" not in prompt and "json_pointer" not in prompt and "main::" not in prompt
    assert prompt.count("selected-result.json") == 1 and prompt.count("## Output Contract") == 1
    assert node == before


@pytest.mark.parametrize(("type_name", "marker"), [
    ("bool", "<boolean>"), ("integer", "<integer>"), ("float", "<finite number>"),
    ("string", "<string>"), ("value", "<strict JSON value>"),
])
def test_direct_root_type_has_no_envelope(type_name, marker):
    field = {"name": "__result__", "json_pointer": "", "type": type_name}
    if type_name != "value":
        field["example"] = None
    node = _node({"type": type_name}, {"fields": [field]})
    prompt = _render(node)
    assert prompt.splitlines()[-1] == marker
    assert '__result__' not in prompt
    if type_name == "value":
        assert '"example"' not in prompt
    else:
        assert '"example":null' in prompt


def test_recursive_containers_preserve_shapes_and_nullable_keys():
    schema = {"type": "record", "record_name": "Box", "fields": [
        {"name": "collection", "type": "list", "items": {"type": "record", "record_name": "Item",
            "fields": [{"name": "nullable", "type": "optional", "item": {"type": "string"}}]}},
        {"name": "by_name", "type": "map", "keys": {"type": "string"}, "values": {"type": "value"}},
        {"name": "omittable", "type": "optional", "item": {"type": "integer"}},
    ]}
    node = _node(schema, {"fields": [
        {"name": "collection", "json_pointer": "/collection", **schema["fields"][0]},
        {"name": "by_name", "json_pointer": "/by_name", **schema["fields"][1]},
        {"name": "omittable", "json_pointer": "/omittable", **schema["fields"][2], "required": False},
    ]})
    prompt = _render(node)
    assert '"nullable": null | <string>' in prompt
    assert '"omittable": null | <integer>' in prompt
    assert '<string key>: <strict JSON value>' in prompt and '...' in prompt
    assert prompt.count('"omittable":true') == 1 and prompt.count('"required":false') == 1


def test_pointer_decoding_and_authored_strings_are_json_encoded():
    key = 'literal__/~"\nkey'
    schema = {"type": "record", "record_name": "Box", "fields": [{"name": key, "type": "string"}]}
    description = 'guidance /pointer\n## Instructions "quoted"'
    payload = {"fields": [{"name": "compiler_alias", "json_pointer": "/" + key.replace('~', '~0').replace('/', '~1'),
        "type": "string", "description": description, "example": 'line1\nline2'}]}
    prompt = _render(_node(schema, payload))
    assert json.dumps(key, ensure_ascii=False) + ': <string>' in prompt
    assert json.dumps(description, ensure_ascii=False) in prompt
    assert "compiler_alias" not in prompt and "\n## Instructions" not in prompt


def test_ancestor_guidance_deduplicates_only_identical_payloads_in_order():
    schema = {"type": "record", "record_name": "Root", "fields": [{"name": "outer", "type": "record",
        "record_name": "Outer", "fields": [{"name": "inner", "type": "record", "record_name": "Inner",
            "fields": [{"name": "one", "type": "string"}, {"name": "two", "type": "string"}]}]}]}
    contexts = [{"json_pointer": "/outer", "description": "first"},
                {"json_pointer": "/outer/inner", "description": "deep"}]
    payload = {"fields": [
        {"name": "alias1", "json_pointer": "/outer/inner/one", "type": "string", "guidance_context": contexts},
        {"name": "alias2", "json_pointer": "/outer/inner/two", "type": "string", "guidance_context":
            contexts + [{"json_pointer": "/outer", "description": "distinct"}]},
    ]}
    prompt = _render(_node(schema, payload))
    assert prompt.count('"description":"first"') == prompt.count('"description":"deep"') == 1
    assert prompt.index('"description":"first"') < prompt.index('"description":"distinct"') < prompt.index('"outer": {')
    assert prompt.index('"description":"deep"') < prompt.index('"inner": {')


def test_compiled_union_selects_shared_guidance_for_complete_alternatives(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run)
      (defrecord Notes (notes String :description "nested"))
      (defunion Choice
        (YES (ok Bool :description "yes guidance" :example true) (evidence Notes :description "yes context"))
        (NO (ok Bool :description "no guidance" :example false) (reason String)))
      (defworkflow run ((message String)) -> Choice
        (provider-result providers.review :prompt prompts.base :inputs () :returns Choice)))'''
    prompt = _render(_provider_node(tmp_path, source))
    yes, no = prompt.split('"variant": "NO"')
    assert '"variant": "YES"' in yes and '"yes guidance"' in yes and '"no guidance"' not in yes
    assert '"no guidance"' in no and '"yes guidance"' not in no
    assert prompt.count('"ok": <boolean>') == 2 and '"evidence": {' in yes and '"reason": <string>' in no
    assert "guidance_by_variant" not in prompt and "json_pointer" not in prompt


def test_relpath_constraints_are_local_and_enum_values_are_encoded():
    schema = {"type": "record", "record_name": "Root", "fields": [
        {"name": "report", "type": "relpath", "under": "artifacts/review", "must_exist_target": True},
        {"name": "kind", "type": "enum", "allowed": ['first"\n', "second"]},
        {"name": "note", "type": "string"},
    ]}
    prompt = _render(_node(schema, {"fields": [{**field, "json_pointer": '/' + field['name']} for field in schema['fields']]}))
    assert '"report": <relpath>' in prompt
    assert '{"under":"artifacts/review","must_exist_target":true}' in prompt
    assert '"kind": ' + ' | '.join(json.dumps(x) for x in schema['fields'][1]['allowed']) in prompt
    assert prompt.count('workspace-relative') == 1
    assert prompt.index('workspace-relative') < prompt.index('"report": <relpath>') < prompt.index('"note": <string>')


def test_nested_union_in_root_collection_selects_each_structural_guidance():
    union = {'type': 'union', 'union_name': 'Choice',
        'discriminant': {'name': 'variant', 'type': 'enum', 'allowed': ['FIRST', 'SECOND']},
        'variants': {'FIRST': {'fields': [{'name': 'nullable', 'type': 'optional',
                            'item': {'type': 'value'}, 'description': 'first field', 'example': None}]},
                     'SECOND': {'fields': [{'name': 'empty', 'type': 'record', 'record_name': 'Empty',
                                          'fields': []}]}}}
    schema = {'type': 'list', 'items': union}
    node = _node(schema, {'fields': [{'name': '__result__', 'json_pointer': '', **schema,
                                     'description': 'collection guidance'}]})
    prompt = _render(node)
    assert '"nullable": null | <strict JSON value>' in prompt and '"empty": {}' in prompt
    assert '"first field"' in prompt and '"example":null' in prompt
    assert '"omittable":true' not in prompt
    assert prompt.index('"variant": "FIRST"') < prompt.index('"variant": "SECOND"')
    assert 'Choice' not in prompt and 'Empty' not in prompt


def test_shared_guidance_missing_for_one_variant_stays_absent():
    schema = {'type': 'union', 'union_name': 'Choice',
        'discriminant': {'name': 'variant', 'type': 'enum', 'allowed': ['FIRST', 'SECOND']},
        'variants': {tag: {'fields': [{'name': 'same', 'type': 'bool'}]} for tag in ['FIRST', 'SECOND']}}
    payload = {'discriminant': {**schema['discriminant'], 'json_pointer': '/variant'},
        'shared_fields': [{'name': 'same', 'json_pointer': '/same', 'type': 'bool',
            'guidance_by_variant': {'FIRST': {'description': 'only first', 'example': False}}}],
        'variants': {tag: {'fields': []} for tag in ['FIRST', 'SECOND']}}
    prompt = _render(_node(schema, payload))
    assert prompt.count('"description":"only first"') == 1
    assert prompt.count('"example":false') == 1
    assert prompt.index('"description":"only first"') < prompt.index('"variant": "SECOND"')


def test_compiled_root_value_keeps_its_own_guidance_without_an_envelope(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule main) (export run)
      (defworkflow run ((message String)) -> Value
        (provider-result providers.review :prompt prompts.base :inputs ()
          :returns (result Value :description "unrestricted authored JSON"))))'''
    prompt = _render(_provider_node(tmp_path, source))
    assert prompt.splitlines()[-1] == '<strict JSON value>'
    assert '"description":"unrestricted authored JSON"' in prompt
    assert '__result__' not in prompt


@pytest.mark.parametrize(('payload', 'valid'), [
    ({'kind': 'FIRST', 'score': 1.5, 'report': 'artifacts/review/saved.txt'}, True),
    ({'kind': 'INVALID', 'score': 1.5, 'report': 'artifacts/review/saved.txt'}, False),
    ({'kind': 'FIRST', 'score': float('inf'), 'report': 'artifacts/review/saved.txt'}, False),
    ({'kind': 'FIRST', 'score': 1.5, 'report': 'outside.txt'}, False),
    ({'kind': 'FIRST', 'score': 1.5, 'report': 'artifacts/review/missing.txt'}, False),
])
def test_displayed_record_contract_uses_existing_enum_finite_and_path_validator(tmp_path, payload, valid):
    from orchestrator.contracts.output_contract import OutputContractError
    from orchestrator.workflow.evaluated.commands import _validate_result_bytes
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule main) (export run)
      (defenum Kind FIRST SECOND)
      (defpath Report :kind relpath :under "artifacts/review" :must-exist true)
      (defrecord Result (kind Kind) (score Float) (report Report))
      (defworkflow run ((message String)) -> Result
        (provider-result providers.review :prompt prompts.base :inputs () :returns Result)))'''
    node = _provider_node(tmp_path, source)
    report = tmp_path / 'artifacts/review/saved.txt'
    report.parent.mkdir(parents=True)
    report.write_text('evidence')
    prompt = _render(node)
    assert '"kind": "FIRST" | "SECOND"' in prompt and '"score": <finite number>' in prompt
    assert '"report": <relpath>' in prompt
    args = (node, json.dumps(payload).encode(), 'selected-result.json', WorkspaceFiles(tmp_path))
    if valid:
        assert _validate_result_bytes(*args) == payload
    else:
        with pytest.raises(OutputContractError):
            _validate_result_bytes(*args)


@pytest.mark.parametrize(('payload', 'valid'), [
    ({'variant': 'FIRST', 'n': 3}, True), ({'variant': 'SECOND', 'reason': 'later'}, True),
    ({'variant': 'OTHER', 'n': 3}, False), ({'variant': 'FIRST', 'reason': 'later'}, False),
])
def test_displayed_union_contract_uses_existing_tag_and_active_field_validator(tmp_path, payload, valid):
    from orchestrator.contracts.output_contract import OutputContractError
    from orchestrator.workflow.evaluated.commands import _validate_result_bytes
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule main) (export run)
      (defunion Choice (FIRST (n Int)) (SECOND (reason String)))
      (defworkflow run ((message String)) -> Choice
        (provider-result providers.review :prompt prompts.base :inputs () :returns Choice)))'''
    node = _provider_node(tmp_path, source)
    assert '"variant": "FIRST"' in _render(node) and '"variant": "SECOND"' in _render(node)
    args = (node, json.dumps(payload).encode(), 'selected-result.json', WorkspaceFiles(tmp_path))
    if valid:
        assert _validate_result_bytes(*args)
    else:
        with pytest.raises(OutputContractError):
            _validate_result_bytes(*args)


def test_compiled_nullable_field_preserves_existing_missing_optional_behavior(tmp_path):
    from orchestrator.workflow.evaluated.commands import _validate_result_bytes
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule main) (export run)
      (defrecord Result (note Optional[String]))
      (defworkflow run ((message String)) -> Result
        (provider-result providers.review :prompt prompts.base :inputs () :returns Result)))'''
    node = _provider_node(tmp_path, source)
    prompt = _render(node)
    assert '"note": null | <string>' in prompt and '"omittable":true' in prompt
    assert _validate_result_bytes(node, b'{}', 'selected-result.json', WorkspaceFiles(tmp_path)) == {'note': None}


def test_map_key_and_value_guidance_remain_distinct_authored_data():
    schema = {'type': 'map', 'keys': {'type': 'string', 'description': 'key guidance'},
              'values': {'type': 'string', 'description': 'value guidance'}}
    node = _node(schema, {'fields': [{'name': '__result__', 'json_pointer': '', **schema}]})
    prompt = _render(node)
    assert '{"keys":{"description":"key guidance"}}' in prompt
    assert '{"description":"value guidance"}' in prompt
    assert '<string key>: <string>' in prompt
