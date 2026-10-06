"""Prompt schema rendering preserves typed structure, not specific prose."""

from copy import deepcopy

import yaml

from orchestrator.contracts.prompt_contract import _append_schema_spec
from orchestrator.workflow.prompting import PromptComposer


def test_recursive_record_union_schema_and_guidance_survive_rendering():
    schema = {
        "type": "record", "record_name": "Answer",
        "fields": [
            {"name": "approved", "type": "bool", "description": "Decision", "example": True},
            {"name": "details", "type": "list", "items": {
                "type": "union", "union_name": "Detail",
                "discriminant": {"name": "variant", "type": "enum", "allowed": ["FILE", "NONE"]},
                "variants": {
                    "FILE": {"fields": [{
                        "name": "file", "type": "relpath", "under": "artifacts",
                        "must_exist_target": True, "description": "Evidence",
                    }]},
                    "NONE": {"fields": []},
                },
            }},
        ],
    }
    lines = []

    _append_schema_spec(lines, schema, indent=0, render_nominal_names=True)

    rendered = yaml.safe_load("\n".join(lines))
    expected = deepcopy(schema)
    # The existing enum renderer uses a comma-separated list, not a YAML array.
    rendered_tags = rendered["fields"][1]["items"]["discriminant"].pop("allowed")
    expected_tags = expected["fields"][1]["items"]["discriminant"].pop("allowed")
    assert rendered_tags.split(", ") == expected_tags
    assert rendered == expected


_PARAMETER = {
    "type": "record", "record_name": "Parameter",
    "fields": [{"name": "name", "type": "string"}, {"name": "value", "type": "integer"}],
}
_DETAIL = {
    "type": "union", "union_name": "Detail",
    "discriminant": {"name": "variant", "type": "enum", "allowed": ["FILE", "NOTE"]},
    "variants": {
        "FILE": {"fields": [{"name": "file", "type": "relpath", "under": "artifacts"}]},
        "NOTE": {"fields": [{"name": "text", "type": "string"}]},
    },
}
_NESTED_FIELDS = [
    {"name": "parameters", "json_pointer": "/parameters", "type": "list", "items": _PARAMETER},
    {"name": "best", "json_pointer": "/best", "type": "optional", "item": _PARAMETER},
    {
        "name": "by_name", "json_pointer": "/by_name", "type": "map",
        "keys": {"type": "string"}, "values": _PARAMETER,
    },
    {"name": "details", "json_pointer": "/details", "type": "list", "items": _DETAIL},
]
# Depth 2: a record inside a record inside a container, and a record inside a union variant.
_DEEP_DETAIL = deepcopy(_DETAIL)
_DEEP_DETAIL["variants"]["FILE"]["fields"].append({"name": "parameter", **_PARAMETER})
_OUTER = {
    "type": "record", "record_name": "Outer",
    "fields": [
        {"name": "parameter", **_PARAMETER},
        {"name": "details", "type": "list", "items": _DEEP_DETAIL},
    ],
}
_ROOT_FIELD = {"name": "__result__", "json_pointer": "", "type": "list", "items": _OUTER}
_NOMINAL_NAMES = ("record_name", "union_name")


def _as_rendered(value, *, nominal_names):
    """The schema as the contract renders it: enum members as one comma-separated scalar,
    and record/union names only when `nominal_names`."""
    if isinstance(value, list):
        return [_as_rendered(item, nominal_names=nominal_names) for item in value]
    if isinstance(value, dict):
        return {
            key: ", ".join(item) if key == "allowed" else _as_rendered(item, nominal_names=nominal_names)
            for key, item in value.items()
            if nominal_names or key not in _NOMINAL_NAMES
        }
    return value


def _rendered_contract(tmp_path, step):
    prompt = PromptComposer(workspace=tmp_path, asset_resolver=None).apply_output_contract_prompt_suffix(
        step, "TASK",
    )
    return yaml.safe_load(prompt[prompt.index("- path: "):])[0]


def test_uncaptured_bundle_renders_nested_structure_without_nominal_names(tmp_path):
    step = {"output_bundle": {"path": "result.json", "fields": deepcopy(_NESTED_FIELDS)}}

    rendered = _rendered_contract(tmp_path, step)

    assert rendered["fields"] == _as_rendered(_NESTED_FIELDS, nominal_names=False)


def test_uncaptured_variant_fields_render_nested_structure_without_nominal_names(tmp_path):
    variant_output = {
        "path": "result.json",
        "discriminant": {
            "name": "variant", "json_pointer": "/variant", "type": "enum",
            "allowed": ["REVISE", "BLOCKED"],
        },
        "shared_fields": [],
        "variants": {
            "REVISE": {"fields": deepcopy(_NESTED_FIELDS)},
            "BLOCKED": {"fields": [{"name": "issue", "json_pointer": "/issue", "type": "string"}]},
        },
    }

    rendered = _rendered_contract(tmp_path, {"variant_output": variant_output})

    assert rendered["variants"]["REVISE"]["fields"] == _as_rendered(_NESTED_FIELDS, nominal_names=False)


def _rendered_root_schema(tmp_path, step):
    rendered = _rendered_contract(tmp_path, step)
    del rendered["path"], rendered["format"]
    return rendered


def _root_schema(*, nominal_names):
    schema = {key: value for key, value in _ROOT_FIELD.items() if key not in ("name", "json_pointer")}
    return _as_rendered(schema, nominal_names=nominal_names)


def test_uncaptured_root_value_renders_nested_structure_without_nominal_names(tmp_path):
    step = {"output_bundle": {"path": "result.json", "fields": [deepcopy(_ROOT_FIELD)]}}

    assert _rendered_root_schema(tmp_path, step) == _root_schema(nominal_names=False)


def test_captured_root_value_renders_nested_structure_with_nominal_names(tmp_path):
    step = {
        "output_bundle": {"path": "result.json", "fields": [deepcopy(_ROOT_FIELD)]},
        "provider_context": {"capture": "portable"},
    }

    assert _rendered_root_schema(tmp_path, step) == _root_schema(nominal_names=True)


def test_structural_keys_on_other_types_do_not_render(tmp_path):
    stray = [
        {
            "name": "note", "json_pointer": "/note", "type": "string",
            "fields": [{"name": "x", "type": "string"}],
        },
        {
            "name": "tags", "json_pointer": "/tags", "type": "list", "items": {
                "type": "string", "variants": {"A": {"fields": []}},
                "discriminant": {"name": "variant", "type": "enum", "allowed": ["A", "B"]},
            },
        },
    ]
    step = {"output_bundle": {"path": "result.json", "fields": deepcopy(stray)}}

    rendered = _rendered_contract(tmp_path, step)

    assert rendered["fields"] == [
        {"name": "note", "json_pointer": "/note", "type": "string"},
        {"name": "tags", "json_pointer": "/tags", "type": "list", "items": {"type": "string"}},
    ]
