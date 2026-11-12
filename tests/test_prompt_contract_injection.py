"""Tests for deterministic output-contract prompt injection on provider steps."""

import json
import hashlib
from dataclasses import (
    FrozenInstanceError,
)
from pathlib import Path

import pytest

from orchestrator.contracts.prompt_contract import (
    render_output_bundle_contract_block,
    render_output_contract_block,
    render_variant_output_contract_block,
)
from orchestrator.workflow.prompting import (
    CanonicalPromptCut,
    PromptComposer,
)
from orchestrator.workflow.provider_phased_delivery.models import (
    ByteDigestProjection,
    CompositionProjection,
)
from tests.prompt_contract_test_helpers import parse_prompt_contract_document


def _variant_contract_document(prompt_block: str) -> dict[str, object]:
    return parse_prompt_contract_document(prompt_block)


def _output_contract_document(prompt_block: str) -> dict[str, object]:
    return parse_prompt_contract_document(prompt_block)


def _expected_output_contract_rows(prompt_block: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in prompt_block.splitlines():
        if line.startswith("- name: "):
            rows.append({"name": line.removeprefix("- name: ")})
        elif rows and line.startswith("  ") and ": " in line:
            key, value = line.strip().split(": ", 1)
            rows[-1][key] = value
    return rows


def _valid_direct_cut() -> CanonicalPromptCut:
    task = b"task"
    materialization = b"\n\ncontract"
    composed = task + materialization
    return CanonicalPromptCut(
        task_slice=task,
        materialization_slice=materialization,
        canonical_composed=composed,
        projection=CompositionProjection(
            canonical_composed=ByteDigestProjection(
                bytes=len(composed),
                sha256=f"sha256:{hashlib.sha256(composed).hexdigest()}",
            ),
            task_slice=ByteDigestProjection(
                bytes=len(task),
                sha256=f"sha256:{hashlib.sha256(task).hexdigest()}",
            ),
            materialization_slice=ByteDigestProjection(
                bytes=len(materialization),
                sha256=(
                    f"sha256:{hashlib.sha256(materialization).hexdigest()}"
                ),
            ),
        ),
    )


def test_phased_canonical_cut_is_frozen() -> None:
    cut = _valid_direct_cut()

    with pytest.raises(FrozenInstanceError):
        cut.task_slice = b"changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    (
        {
            "task_slice": "task",
            "materialization_slice": b"\n\ncontract",
            "canonical_composed": b"task\n\ncontract",
        },
        {
            "task_slice": b"\xff",
            "materialization_slice": b"\n\ncontract",
            "canonical_composed": b"\xff\n\ncontract",
        },
        {
            "task_slice": b"task",
            "materialization_slice": b"\n\ncontract",
            "canonical_composed": b"different",
        },
    ),
)
def test_phased_canonical_cut_rejects_invalid_direct_bytes(kwargs) -> None:
    with pytest.raises((TypeError, ValueError, UnicodeDecodeError)):
        CanonicalPromptCut(
            **kwargs,
            projection=_valid_direct_cut().projection,
        )


def test_phased_canonical_cut_rejects_wrong_projection_type() -> None:
    with pytest.raises(TypeError, match="CompositionProjection"):
        CanonicalPromptCut(
            task_slice=b"task",
            materialization_slice=b"\n\ncontract",
            canonical_composed=b"task\n\ncontract",
            projection=object(),  # type: ignore[arg-type]
        )


def test_phased_canonical_cut_rejects_mismatched_direct_projection() -> None:
    with pytest.raises(ValueError, match="projection"):
        CanonicalPromptCut(
            task_slice=b"task",
            materialization_slice=b"\n\ncontract",
            canonical_composed=b"task\n\ncontract",
            projection=CompositionProjection(
                canonical_composed=ByteDigestProjection(
                    bytes=15,
                    sha256=(
                        "sha256:"
                        "0000000000000000000000000000000000000000000000000000000000000000"
                    ),
                ),
                task_slice=ByteDigestProjection(
                    bytes=4,
                    sha256=(
                        "sha256:"
                        "0000000000000000000000000000000000000000000000000000000000000000"
                    ),
                ),
                materialization_slice=ByteDigestProjection(
                    bytes=11,
                    sha256=(
                        "sha256:"
                        "0000000000000000000000000000000000000000000000000000000000000000"
                    ),
                ),
            ),
        )


@pytest.mark.parametrize("structured_contract_name", ("output_bundle", "variant_output"))
def test_prompt_output_position_contract_blocks_are_composed_in_contract_order(
    tmp_path: Path,
    structured_contract_name: str,
) -> None:
    expected_outputs = [
        {
            "name": "report_path",
            "path": "state/report_path.txt",
            "type": "relpath",
            "required": True,
        }
    ]
    output_bundle = {
        "path": "state/result.json",
        "fields": [
            {
                "name": "approved",
                "json_pointer": "/approved",
                "type": "bool",
            }
        ],
    }
    variant_output = {
        "path": "state/result.json",
        "discriminant": {
            "name": "decision",
            "json_pointer": "/decision",
            "type": "enum",
            "allowed": ["APPROVE", "REVISE"],
        },
        "variants": {
            "APPROVE": {"fields": []},
            "REVISE": {"fields": []},
        },
    }
    structured_contract = (
        output_bundle
        if structured_contract_name == "output_bundle"
        else variant_output
    )
    structured_block = (
        render_output_bundle_contract_block(output_bundle)
        if structured_contract_name == "output_bundle"
        else render_variant_output_contract_block(variant_output)
    )
    step = {
        "expected_outputs": expected_outputs,
        structured_contract_name: structured_contract,
    }

    rendered = PromptComposer(
        workspace=tmp_path,
        asset_resolver=None,
    ).apply_output_contract_prompt_suffix(step, "")

    expected_block = render_output_contract_block(expected_outputs)
    assert rendered == f"{expected_block}\n\n{structured_block}"
    assert _expected_output_contract_rows(expected_block) == [
        {
            "name": "report_path",
            "path": expected_outputs[0]["path"],
            "type": "relpath",
        }
    ]
    assert _output_contract_document(structured_block)["path"] == (
        structured_contract["path"]
    )


@pytest.mark.parametrize(
    "step",
    [
        {},
        {
            "expected_outputs": [
                {
                    "name": "report_path",
                    "path": "state/report_path.txt",
                    "type": "relpath",
                }
            ]
        },
        {
            "output_bundle": {
                "path": "state/result.json",
                "fields": [
                    {
                        "name": "approved",
                        "json_pointer": "/approved",
                        "type": "bool",
                    }
                ],
            }
        },
    ],
)
def test_output_contract_composition_preserves_no_or_single_contract_bytes(
    tmp_path: Path,
    step: dict[str, object],
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    prompt = "Perform the task.\n"
    rendered = composer.apply_output_contract_prompt_suffix(step, prompt)

    if "expected_outputs" in step:
        block = render_output_contract_block(step["expected_outputs"])
        assert rendered == f"{prompt}\n{block}"
    elif "output_bundle" in step:
        block = render_output_bundle_contract_block(step["output_bundle"])
        assert rendered == f"{prompt}\n{block}"
    else:
        assert rendered == prompt


def test_variant_output_prompt_contract_renders_structured_nested_constraints() -> None:
    """Rendered variant contracts must preserve field constraints as parseable structure."""
    from orchestrator.contracts.prompt_contract import render_variant_output_contract_block

    prompt_block = render_variant_output_contract_block({
        "path": "state/variant_bundle.json",
        "discriminant": {
            "name": "implementation_state",
            "json_pointer": "/implementation_state",
            "type": "enum",
            "allowed": ["COMPLETED", "BLOCKED"],
        },
        "variants": {
            "COMPLETED": {
                "fields": [{
                    "name": "execution_report_path",
                    "json_pointer": "/execution_report_path",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }]
            },
            "BLOCKED": {
                "fields": [{
                    "name": "progress_report_path",
                    "json_pointer": "/progress_report_path",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }]
            },
        },
    })

    bundle = _variant_contract_document(prompt_block)
    completed_field = bundle["variants"]["COMPLETED"]["fields"][0]
    blocked_field = bundle["variants"]["BLOCKED"]["fields"][0]
    assert "for `under: artifacts/work`, write `artifacts/work/...`" in prompt_block
    assert "for `under: artifacts/review`, write `artifacts/review/...`" in prompt_block
    assert completed_field["under"] == "artifacts/work"
    assert completed_field["must_exist_target"] is True
    assert blocked_field["under"] == "artifacts/work"
    assert blocked_field["must_exist_target"] is True


def test_render_output_bundle_contract_block_root_field_renders_json_value_schema() -> None:
    """A single empty-pointer field renders one JSON-value schema, not an object contract."""
    root_bundle = {
        "path": "state/run-root/test-run/result.json",
        "fields": [
            {
                "name": "__result__",
                "json_pointer": "",
                "type": "bool",
            }
        ],
    }

    rendered = render_output_bundle_contract_block(root_bundle)

    assert "format: JSON value" in rendered
    assert "format: JSON object" not in rendered
    assert "fields:" not in rendered
    assert "name: __result__" not in rendered
    assert "json_pointer:" not in rendered
    assert "type: bool" in rendered
    assert "path: state/run-root/test-run/result.json" in rendered


def test_output_bundle_guidance_renders_nested_context_and_canonical_examples() -> None:
    contract = {
        "path": "state/review/result.json",
        "guidance": {
            "description": "Complete review bundle.",
            "format_hint": "One review object.",
            "example": {
                "metrics": {"clarity": None},
                "approved": True,
            },
        },
        "fields": [
            {
                "name": "blocker__details__code",
                "json_pointer": "/blocker/details/code",
                "type": "string",
                "guidance_context": [
                    {
                        "json_pointer": "/blocker",
                        "description": "Blocking condition context.",
                        "example": None,
                    },
                    {
                        "json_pointer": "/blocker/details",
                        "format_hint": "Nested blocker details.",
                        "example": {"owner": None},
                    },
                ],
                "description": "Stable blocker code.",
                "format_hint": "Uppercase token.",
                "example": "MISSING_RESOURCE",
            }
        ],
    }

    rendered = render_output_bundle_contract_block(contract)
    bundle = _output_contract_document(rendered)

    assert list(bundle).index("guidance") < list(bundle).index("fields")
    assert bundle["guidance"] == contract["guidance"]
    field = bundle["fields"][0]
    assert [row["json_pointer"] for row in field["guidance_context"]] == [
        "/blocker",
        "/blocker/details",
    ]
    assert field["description"] == contract["fields"][0]["description"]
    for semantic_value in (
        "Complete review bundle.",
        "One review object.",
        "Blocking condition context.",
        "Nested blocker details.",
        "Stable blocker code.",
        "Uppercase token.",
    ):
        assert rendered.count(semantic_value) == 1
    for example_token in (
        'example: {"approved":true,"metrics":{"clarity":null}}',
        "example: null",
        'example: {"owner":null}',
        'example: "MISSING_RESOURCE"',
    ):
        assert rendered.count(example_token) == 1


def test_typed_guidance_strings_roundtrip_through_structured_prompt_sections() -> None:
    from orchestrator.contracts.prompt_contract import render_variant_output_contract_block

    output_contract = {
        "path": "state/review/result.json",
        "guidance": {
            "description": "Bundle: retain # marker",
            "format_hint": "null",
        },
        "fields": [
            {
                "name": "blocker__code",
                "json_pointer": "/blocker/code",
                "type": "string",
                "guidance_context": [
                    {
                        "json_pointer": "/blocker",
                        "description": "First line\nSecond line: keep # marker",
                        "format_hint": "yes",
                    }
                ],
                "description": "[APPROVE, REVISE]",
                "format_hint": "Résumé ✓",
            }
        ],
    }
    variant_contract = {
        "path": "state/review/decision.json",
        "guidance": {
            "description": "Variant bundle: keep # marker",
            "format_hint": "false",
        },
        "discriminant": {
            "name": "decision",
            "json_pointer": "/decision",
            "type": "enum",
            "allowed": ["APPROVE", "REVISE"],
        },
        "shared_fields": [
            {
                "name": "confidence",
                "json_pointer": "/confidence",
                "type": "float",
                "guidance_by_variant": {
                    "APPROVE": {
                        "description": "Decision: approve # exact",
                        "format_hint": "on",
                    },
                    "REVISE": {
                        "description": "Décision: réviser # exact",
                        "format_hint": "[0, 1]",
                    },
                },
            }
        ],
        "variants": {
            "APPROVE": {"fields": []},
            "REVISE": {
                "fields": [
                    {
                        "name": "reason",
                        "json_pointer": "/reason",
                        "type": "string",
                        "description": "Reason: multiline\nKeep # exactly",
                        "format_hint": "true",
                    }
                ]
            },
        },
    }

    rendered_output = render_output_bundle_contract_block(output_contract)
    rendered_variant = render_variant_output_contract_block(variant_contract)
    output_bundle = _output_contract_document(rendered_output)
    variant_bundle = _variant_contract_document(rendered_variant)

    assert output_bundle["guidance"] == output_contract["guidance"]
    assert output_bundle["fields"][0]["description"] == "[APPROVE, REVISE]"
    assert output_bundle["fields"][0]["format_hint"] == "Résumé ✓"
    assert (
        output_bundle["fields"][0]["guidance_context"]
        == output_contract["fields"][0]["guidance_context"]
    )
    assert variant_bundle["guidance"] == variant_contract["guidance"]
    assert (
        variant_bundle["shared_fields"][0]["guidance_by_variant"]
        == variant_contract["shared_fields"][0]["guidance_by_variant"]
    )
    assert (
        variant_bundle["variants"]["REVISE"]["fields"][0]["description"]
        == "Reason: multiline\nKeep # exactly"
    )
    assert (
        variant_bundle["variants"]["REVISE"]["fields"][0]["format_hint"]
        == "true"
    )

    output_values = (
        *output_contract["guidance"].values(),
        output_contract["fields"][0]["description"],
        output_contract["fields"][0]["format_hint"],
        *(
            value
            for key, value in output_contract["fields"][0]["guidance_context"][0].items()
            if key != "json_pointer"
        ),
    )
    variant_values = (
        *variant_contract["guidance"].values(),
        *(
            value
            for payload in variant_contract["shared_fields"][0]["guidance_by_variant"].values()
            for value in payload.values()
        ),
        variant_contract["variants"]["REVISE"]["fields"][0]["description"],
        variant_contract["variants"]["REVISE"]["fields"][0]["format_hint"],
    )
    for rendered, semantic_values in (
        (rendered_output, output_values),
        (rendered_variant, variant_values),
    ):
        for semantic_value in semantic_values:
            encoded = json.dumps(semantic_value, ensure_ascii=False)
            assert rendered.count(encoded) == 1


def test_variant_output_guidance_uses_discriminant_order_and_canonical_examples() -> None:
    from orchestrator.contracts.prompt_contract import render_variant_output_contract_block

    contract = {
        "path": "state/review/decision.json",
        "guidance": {
            "description": "Choose one review decision.",
            "example": {"owner": None, "decision": "APPROVE"},
        },
        "discriminant": {
            "name": "decision",
            "json_pointer": "/decision",
            "type": "enum",
            "allowed": ["APPROVE", "REVISE"],
        },
        "shared_fields": [
            {
                "name": "report",
                "json_pointer": "/report",
                "type": "optional",
                "item": {"type": "string"},
                "description": "Shared report path.",
                "example": None,
            },
            {
                "name": "confidence",
                "json_pointer": "/confidence",
                "type": "float",
                "guidance_by_variant": {
                    "APPROVE": {
                        "description": "Approval confidence.",
                        "example": 0.95,
                    },
                    "REVISE": {
                        "description": "Revision confidence.",
                        "example": 0.8,
                    },
                },
            },
        ],
        "variants": {
            "APPROVE": {
                "fields": [
                    {
                        "name": "approved",
                        "json_pointer": "/approved",
                        "type": "bool",
                        "description": "Approval state.",
                        "example": True,
                    }
                ]
            },
            "REVISE": {
                "fields": [
                    {
                        "name": "reason",
                        "json_pointer": "/reason",
                        "type": "string",
                        "format_hint": "Concise revision reason.",
                        "example": "Needs tests",
                    }
                ]
            },
        },
    }

    rendered = render_variant_output_contract_block(contract)
    bundle = _variant_contract_document(rendered)

    assert list(bundle).index("guidance") < list(bundle).index("shared_fields")
    confidence = next(
        field for field in bundle["shared_fields"] if field["name"] == "confidence"
    )
    assert list(confidence["guidance_by_variant"]) == ["APPROVE", "REVISE"]
    assert list(bundle["variants"]) == ["APPROVE", "REVISE"]
    for semantic_value in (
        "Choose one review decision.",
        "Shared report path.",
        "Approval confidence.",
        "Revision confidence.",
        "Approval state.",
        "Concise revision reason.",
    ):
        assert rendered.count(semantic_value) == 1
    for example_token in (
        'example: {"decision":"APPROVE","owner":null}',
        "example: null",
        "example: 0.95",
        "example: 0.8",
        "example: true",
    ):
        assert rendered.count(example_token) == 1
