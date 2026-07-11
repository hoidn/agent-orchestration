import json
from pathlib import Path

from orchestrator.contracts.output_contract import validate_output_bundle, validate_variant_output_bundle
from orchestrator.contracts.prompt_contract import (
    render_output_bundle_contract_block,
    render_variant_output_contract_block,
)


def test_validate_output_bundle_optional_field_missing_returns_none(tmp_path: Path) -> None:
    bundle_path = tmp_path / "state" / "bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text("{}\n", encoding="utf-8")

    artifacts = validate_output_bundle(
        {
            "path": "state/bundle.json",
            "fields": [
                {
                    "name": "owner",
                    "json_pointer": "/owner",
                    "type": "optional",
                    "item": {"type": "string"},
                }
            ],
        },
        workspace=tmp_path,
    )

    assert artifacts == {"owner": None}


def test_validate_output_bundle_list_and_map_fields_validate_recursively(tmp_path: Path) -> None:
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "report.md").write_text("# report\n", encoding="utf-8")
    bundle_path = tmp_path / "state" / "bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps(
            {
                "attempt_ids": [1, 2, 3],
                "reports": {"main": "artifacts/work/report.md"},
                "review_states": [None, "APPROVE"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    artifacts = validate_output_bundle(
        {
            "path": "state/bundle.json",
            "fields": [
                {
                    "name": "attempt_ids",
                    "json_pointer": "/attempt_ids",
                    "type": "list",
                    "items": {"type": "integer"},
                },
                {
                    "name": "reports",
                    "json_pointer": "/reports",
                    "type": "map",
                    "keys": {"type": "string"},
                    "values": {
                        "type": "relpath",
                        "under": "artifacts/work",
                        "must_exist_target": True,
                    },
                },
                {
                    "name": "review_states",
                    "json_pointer": "/review_states",
                    "type": "list",
                    "items": {
                        "type": "optional",
                        "item": {
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                        },
                    },
                },
            ],
        },
        workspace=tmp_path,
    )

    assert artifacts == {
        "attempt_ids": [1, 2, 3],
        "reports": {"main": "artifacts/work/report.md"},
        "review_states": [None, "APPROVE"],
    }


def test_validate_variant_output_bundle_supports_collection_shared_and_variant_fields(tmp_path: Path) -> None:
    (tmp_path / "artifacts" / "work").mkdir(parents=True)
    (tmp_path / "artifacts" / "work" / "report.md").write_text("# report\n", encoding="utf-8")
    bundle_path = tmp_path / "state" / "variant_bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(
        json.dumps(
            {
                "implementation_state": "COMPLETED",
                "owner": None,
                "attempt_ids": [1, 2],
                "reports": {"main": "artifacts/work/report.md"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    artifacts = validate_variant_output_bundle(
        {
            "path": "state/variant_bundle.json",
            "discriminant": {
                "name": "implementation_state",
                "json_pointer": "/implementation_state",
                "type": "enum",
                "allowed": ["COMPLETED", "BLOCKED"],
            },
            "shared_fields": [
                {
                    "name": "owner",
                    "json_pointer": "/owner",
                    "type": "optional",
                    "item": {"type": "string"},
                }
            ],
            "variants": {
                "COMPLETED": {
                    "fields": [
                        {
                            "name": "attempt_ids",
                            "json_pointer": "/attempt_ids",
                            "type": "list",
                            "items": {"type": "integer"},
                        },
                        {
                            "name": "reports",
                            "json_pointer": "/reports",
                            "type": "map",
                            "keys": {"type": "string"},
                            "values": {
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            },
                        },
                    ]
                },
                "BLOCKED": {"fields": []},
            },
        },
        workspace=tmp_path,
    )

    assert artifacts == {
        "implementation_state": "COMPLETED",
        "owner": None,
        "attempt_ids": [1, 2],
        "reports": {"main": "artifacts/work/report.md"},
    }


def test_render_collection_contract_blocks_include_nested_schema_details() -> None:
    output_bundle = {
        "path": "state/bundle.json",
        "fields": [
            {
                "name": "owner",
                "json_pointer": "/owner",
                "type": "optional",
                "item": {"type": "string"},
            },
            {
                "name": "attempt_ids",
                "json_pointer": "/attempt_ids",
                "type": "list",
                "items": {"type": "integer"},
            },
            {
                "name": "reports",
                "json_pointer": "/reports",
                "type": "map",
                "keys": {"type": "string"},
                "values": {
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                },
            },
        ],
    }
    variant_output = {
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        },
        "shared_fields": [
            {
                "name": "owner",
                "json_pointer": "/owner",
                "type": "optional",
                "item": {"type": "string"},
            }
        ],
        "variants": {
            "COMPLETED": {
                "fields": [
                    {
                        "name": "attempt_ids",
                        "json_pointer": "/attempt_ids",
                        "type": "list",
                        "items": {"type": "integer"},
                    }
                ]
            },
            "BLOCKED": {"fields": []},
        },
    }

    rendered_bundle = render_output_bundle_contract_block(output_bundle)
    rendered_variant = render_variant_output_contract_block(variant_output)

    assert "type: optional" in rendered_bundle
    assert "item:" in rendered_bundle
    assert "type: list" in rendered_bundle
    assert "items:" in rendered_bundle
    assert "type: map" in rendered_bundle
    assert "keys:" in rendered_bundle
    assert "values:" in rendered_bundle
    assert "type: optional" in rendered_variant
    assert "type: list" in rendered_variant


def test_validate_output_bundle_native_root_result_reads_document_root(tmp_path: Path) -> None:
    bundle_path = tmp_path / "state" / "bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text("true\n", encoding="utf-8")

    artifacts = validate_output_bundle(
        {
            "path": "state/bundle.json",
            "fields": [
                {
                    "name": "__result__",
                    "json_pointer": "",
                    "type": "bool",
                }
            ],
        },
        workspace=tmp_path,
    )

    assert artifacts == {"__result__": True}


def test_validate_output_bundle_native_root_result_supports_collection_roots(tmp_path: Path) -> None:
    bundle_path = tmp_path / "state" / "bundle.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text(json.dumps([1, 2, 3]) + "\n", encoding="utf-8")

    artifacts = validate_output_bundle(
        {
            "path": "state/bundle.json",
            "fields": [
                {
                    "name": "__result__",
                    "json_pointer": "",
                    "type": "list",
                    "items": {"type": "integer"},
                }
            ],
        },
        workspace=tmp_path,
    )

    assert artifacts == {"__result__": [1, 2, 3]}
