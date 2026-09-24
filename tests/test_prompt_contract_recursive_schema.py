"""Prompt schema rendering preserves typed structure, not specific prose."""

from copy import deepcopy

import yaml

from orchestrator.contracts.prompt_contract import _append_schema_spec


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

    _append_schema_spec(lines, schema, indent=0, recursive_structures=True)

    rendered = yaml.safe_load("\n".join(lines))
    expected = deepcopy(schema)
    # The existing enum renderer uses a comma-separated list, not a YAML array.
    rendered_tags = rendered["fields"][1]["items"]["discriminant"].pop("allowed")
    expected_tags = expected["fields"][1]["items"]["discriminant"].pop("allowed")
    assert rendered_tags.split(", ") == expected_tags
    assert rendered == expected


def test_uncaptured_schema_rendering_retains_the_existing_projection():
    legacy = {"type": "list", "items": {"type": "record"}}
    complete = deepcopy(legacy)
    complete["items"].update(record_name="Answer", fields=[{"name": "approved", "type": "bool"}])
    legacy_lines, complete_lines = [], []

    _append_schema_spec(legacy_lines, legacy, indent=0)
    _append_schema_spec(complete_lines, complete, indent=0)

    assert complete_lines == legacy_lines
