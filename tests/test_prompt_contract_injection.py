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
from orchestrator.deps.content_snapshot import build_content_snapshot
from orchestrator.workflow.prompting import (
    CanonicalPromptCut,
    PromptComposer,
    RuntimeContributionComposition,
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


def _q5_structured_contract(*, with_guidance: bool = False) -> dict[str, object]:
    field: dict[str, object] = {
        "name": "approved",
        "json_pointer": "/approved",
        "type": "bool",
    }
    if with_guidance:
        field.update(
            {
                "description": "Field-specific semantic context.",
                "format_hint": "A canonical JSON Boolean.",
                "example": True,
            }
        )
    return {
        "path": "state/result.json",
        "fields": [field],
    }


@pytest.mark.parametrize("prompt", ("", "task", "task\n"))
@pytest.mark.parametrize("contract_level", ("q1", "q2"))
def test_phased_canonical_cut_partitions_the_existing_single_render(
    tmp_path: Path,
    prompt: str,
    contract_level: str,
) -> None:
    structured_contract = _q5_structured_contract()
    step: dict[str, object] = {"output_bundle": structured_contract}
    blocks = [render_output_bundle_contract_block(structured_contract)]
    if contract_level == "q2":
        expected_outputs = [
            {
                "name": "report",
                "path": "artifacts/report.md",
                "type": "relpath",
            }
        ]
        step["expected_outputs"] = expected_outputs
        blocks.insert(0, render_output_contract_block(expected_outputs))
    block = "\n\n".join(blocks)
    separator = "" if not prompt else ("\n" if prompt.endswith("\n") else "\n\n")
    expected_suffix = (separator + block).encode("utf-8", errors="strict")

    cut = PromptComposer(
        workspace=tmp_path,
        asset_resolver=None,
    ).apply_output_contract_prompt_suffix_with_cut(step, prompt)

    assert type(cut) is CanonicalPromptCut
    assert cut.task_slice == prompt.encode("utf-8", errors="strict")
    assert cut.materialization_slice == expected_suffix
    assert cut.canonical_composed == cut.task_slice + cut.materialization_slice
    assert cut.canonical_composed.decode("utf-8", errors="strict") == (
        prompt + separator + block
    )
    assert cut.projection.task_slice.bytes == len(cut.task_slice)
    assert cut.projection.materialization_slice.bytes == len(
        cut.materialization_slice
    )
    assert cut.projection.canonical_composed.bytes == len(
        cut.canonical_composed
    )
    for payload, projection in (
        (cut.task_slice, cut.projection.task_slice),
        (cut.materialization_slice, cut.projection.materialization_slice),
        (cut.canonical_composed, cut.projection.canonical_composed),
    ):
        assert projection.sha256 == f"sha256:{hashlib.sha256(payload).hexdigest()}"


@pytest.mark.parametrize("with_guidance", (False, True))
def test_phased_canonical_cut_retains_structured_contract_variants_in_t2(
    tmp_path: Path,
    with_guidance: bool,
) -> None:
    contract = _q5_structured_contract(with_guidance=with_guidance)
    prompt = "rendered-fragment"
    expected_block = render_output_bundle_contract_block(contract)

    cut = PromptComposer(
        workspace=tmp_path,
        asset_resolver=None,
    ).apply_output_contract_prompt_suffix_with_cut(
        {"output_bundle": contract},
        prompt,
    )

    assert cut.task_slice == prompt.encode("utf-8")
    assert cut.materialization_slice == f"\n\n{expected_block}".encode("utf-8")
    assert cut.canonical_composed == cut.task_slice + cut.materialization_slice


@pytest.mark.parametrize(
    ("variant", "base_prompt"),
    (
        ("disabled", "rendered-fragment"),
        ("empty", ""),
        ("prepend", "rendered-fragment"),
        ("append", "rendered-fragment"),
    ),
)
def test_phased_canonical_cut_keeps_actual_consumed_artifact_variants_in_t1(
    tmp_path: Path,
    variant: str,
    base_prompt: str,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    step: dict[str, object] = {
        "consumes": [{"artifact": "context"}],
        "output_bundle": _q5_structured_contract(),
    }
    resolved = {"root.review": {"context": "retained-value"}}
    if variant == "disabled":
        step["inject_consumes"] = False
    elif variant == "empty":
        resolved = {}
    else:
        step["consumes_injection_position"] = variant
    prompt = composer.apply_consumes_prompt_injection(
        step,
        base_prompt,
        resolved_consumes=resolved,
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )
    contract = _q5_structured_contract()

    cut = composer.apply_output_contract_prompt_suffix_with_cut(
        {"output_bundle": contract},
        prompt,
    )

    assert cut.task_slice == prompt.encode("utf-8", errors="strict")
    assert cut.canonical_composed == cut.task_slice + cut.materialization_slice


def test_phased_canonical_cut_renders_contract_contributions_once(
    tmp_path: Path,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    calls = 0
    original = composer._output_contract_contributions

    def counted(step):
        nonlocal calls
        calls += 1
        return original(step)

    composer._output_contract_contributions = counted  # type: ignore[method-assign]

    cut = composer.apply_output_contract_prompt_suffix_with_cut(
        {"output_bundle": _q5_structured_contract()},
        "task",
    )

    assert calls == 1
    assert cut.canonical_composed == cut.task_slice + cut.materialization_slice


@pytest.mark.parametrize("prompt", ("", "task", "task\n"))
@pytest.mark.parametrize("contract_level", ("q1", "q2"))
def test_traced_and_untraced_suffix_owners_are_byte_identical(
    tmp_path: Path,
    prompt: str,
    contract_level: str,
) -> None:
    step: dict[str, object] = {
        "output_bundle": _q5_structured_contract(),
    }
    if contract_level == "q2":
        step["expected_outputs"] = [
            {
                "name": "report",
                "path": "artifacts/report.md",
                "type": "relpath",
            }
        ]
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    ordinary = composer.apply_output_contract_prompt_suffix(step, prompt)
    traced = composer.apply_output_contract_prompt_suffix_with_trace(
        step,
        RuntimeContributionComposition(
            base_prompt=prompt,
            prompt=prompt,
        ),
    )
    cut = composer.apply_output_contract_prompt_suffix_with_cut(step, prompt)

    assert traced.prompt == ordinary
    assert cut.canonical_composed == ordinary.encode("utf-8", errors="strict")
    assert b"".join(segment.segment for segment in traced.segments) == (
        cut.materialization_slice
    )


def test_phased_canonical_cut_rejects_non_utf8_prompt_before_contract_render(
    tmp_path: Path,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    with pytest.raises(UnicodeEncodeError):
        composer.apply_output_contract_prompt_suffix_with_cut(
            {"output_bundle": _q5_structured_contract()},
            "\ud800",
        )


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


def test_typed_failure_row_ids_are_derived_by_the_evidence_owner() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import authored_row_id

    from orchestrator.workflow.prompt_dependency_contract import _build_compiler_prompt_dependency_contract, PromptDependencyPosition
    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=("inputs.first", "inputs.second"), optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND, instruction=None,
        source_origin_key="historical/provider", source_workflow_bytes=b"historical two-row source",
    )

    first = authored_row_id(contract, role="required", authored_index=0)
    second = authored_row_id(contract, role="required", authored_index=1)

    assert first.startswith("sha256:") and len(first) == 71
    assert first != second


def test_provider_prompt_injection_renders_collection_consumed_value(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [{"artifact": "context_docs"}],
        },
        "Review the design docs.\n",
        resolved_consumes={
            "root.review": {
                "context_docs": [
                    "docs/design/state-layout.md",
                    "docs/design/runtime-foundation.md",
                ]
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "## Consumed Artifacts" in prompt
    assert '- context_docs: ["docs/design/state-layout.md", "docs/design/runtime-foundation.md"]' in prompt
    assert "Review the design docs." in prompt


@pytest.mark.parametrize("position", ["prepend", "append"])
def test_empty_content_dependency_attempt_preserves_base_prompt(
    tmp_path: Path,
    position: str,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    base_prompt = "Unchanged base prompt.\n"
    finished_prompts: list[str] = []

    def finish_prompt(prompt: str) -> str:
        finished_prompts.append(prompt)
        return prompt

    composition = composer.compose_content_dependency_attempt(
        base_prompt=base_prompt,
        snapshot=build_content_snapshot((), ()),
        instruction="",
        position=position,
        finish_prompt=finish_prompt,
    )

    assert finished_prompts == [base_prompt]
    assert composition.rendered.block == b""
    assert composition.final_prompt == base_prompt.encode("utf-8")
    assert composition.debug_injection is None


def test_empty_content_dependency_attempt_rejects_invalid_position(
    tmp_path: Path,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    with pytest.raises(ValueError, match="invalid_injection_contract"):
        composer.compose_content_dependency_attempt(
            base_prompt="Base prompt.\n",
            snapshot=build_content_snapshot((), ()),
            instruction="",
            position="invalid",
            finish_prompt=lambda prompt: prompt,
        )


def test_prompt_consumes_subset_renders_collection_value(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {"artifact": "context_docs"},
                {"artifact": "review_focus"},
            ],
            "prompt_consumes": ["context_docs"],
        },
        "Review the design docs.\n",
        resolved_consumes={
            "root.review": {
                "context_docs": ["docs/design/state-layout.md"],
                "review_focus": "runtime lane split",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert '- context_docs: ["docs/design/state-layout.md"]' in prompt
    assert "review_focus" not in prompt


def test_adjudicated_provider_prompt_injection_renders_collection_consumed_value(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Judge",
            "adjudicated_provider": {"provider": "mock-provider"},
            "consumes": [{"artifact": "context_docs"}],
            "consumes_injection_position": "append",
        },
        "Judge the candidate output.\n",
        resolved_consumes={
            "root.judge": {
                "context_docs": ["docs/design/runtime-foundation.md"],
            }
        },
        step_name="Judge",
        consume_identity="root.judge",
        uses_qualified_identities=True,
    )

    assert prompt.startswith("Judge the candidate output.")
    assert prompt.rstrip().endswith('Use these consumed artifacts as context for your work.')
    assert '- context_docs: ["docs/design/runtime-foundation.md"]' in prompt


def test_typed_prompt_input_injection_renders_deterministic_block_before_consumes(
    tmp_path: Path,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    prompt, evidence = composer.apply_typed_prompt_input_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [{"artifact": "context_docs"}],
        },
        "## Workspace Dependencies\n- docs/index.md\n\nReview the design docs.\n",
        typed_prompt_inputs=[
            {
                "schema_version": "workflow_lisp_typed_prompt_input.v1",
                "binding_name": "prompt_context",
                "renderer": {
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "accepted_shape": "any_pure_value",
                },
                "value_source": {"kind": "typed_binding_ref", "ref": "inputs.prompt_context"},
                "value_type_name": "PromptContext",
                "source_map_origin_key": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
                "u0_row_id": "u0.fixture.prompt_context",
                "c0_row_id": "c0.fixture.prompt_context",
                "injection_order": 0,
            }
        ],
        resolved_typed_values={
            "prompt_context": {
                "design": "docs/design/runtime-foundation.md",
                "focus": "prefer typed values",
            }
        },
        workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
        step_id="root.run-typed-prompt-phase-demo__attempt",
    )
    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [{"artifact": "context_docs"}],
        },
        prompt,
        resolved_consumes={"root.review": {"context_docs": ["docs/index.md"]}},
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )
    prompt = composer.apply_output_contract_prompt_suffix(
        {
            "name": "Review",
            "provider": "mock-provider",
            "output_bundle": {
                "path": "state/review_bundle.json",
                "fields": [
                    {
                        "name": "status",
                        "json_pointer": "/status",
                        "type": "string",
                    }
                ],
            },
        },
        prompt,
    )

    assert "## Workspace Dependencies" in prompt
    assert '"focus":"prefer typed values"' in prompt
    assert prompt.index("## Consumed Artifacts") < prompt.index('"focus":"prefer typed values"')
    assert prompt.index('"focus":"prefer typed values"') < prompt.index("Output Contract")
    assert evidence[0]["rendered_bytes_digest"].startswith("sha256:")


def test_typed_prompt_input_injection_omits_evidence_when_no_typed_rows(
    tmp_path: Path,
) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    prompt, evidence = composer.apply_typed_prompt_input_injection(
        {"name": "Review", "provider": "mock-provider"},
        "Review the design docs.\n",
        typed_prompt_inputs=[],
        resolved_typed_values={},
        workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
        step_id="root.run-typed-prompt-phase-demo__attempt",
    )

    assert prompt == "Review the design docs.\n"
    assert evidence == []


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


def test_consume_prompt_modes_render_mixed_content_reference_and_none(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "baseline.md").write_text("baseline body\n", encoding="utf-8")

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "baseline_design",
                    "prompt": {
                        "mode": "reference",
                        "label": "Baseline design",
                        "role": "compatibility_baseline",
                        "description": "Accepted baseline contract.",
                    },
                },
                {
                    "artifact": "execution_log",
                    "prompt": {
                        "mode": "content",
                    },
                },
                {
                    "artifact": "private_notes",
                    "prompt": {
                        "mode": "none",
                    },
                },
            ],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "baseline_design": "docs/baseline.md",
                "execution_log": "artifacts/work/execute.log",
                "private_notes": "state/private_notes.txt",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "## Consumed Artifacts" in prompt
    assert "- execution_log: artifacts/work/execute.log" in prompt
    assert "- baseline_design:" in prompt
    assert "mode: reference" in prompt
    assert "label: Baseline design" in prompt
    assert "role: compatibility_baseline" in prompt
    assert "resolved_value: docs/baseline.md" in prompt
    assert "private_notes" not in prompt
    assert "Use embedded content as context and open referenced artifacts only when needed." in prompt


def test_consume_prompt_nested_guidance_overrides_legacy_row_fields(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "execution_log",
                    "description": "legacy description",
                    "format_hint": "legacy hint",
                    "example": "legacy-example.log",
                    "prompt": {
                        "mode": "reference",
                        "description": "nested description",
                        "format_hint": "nested hint",
                        "example": "nested-example.log",
                    },
                },
            ],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "execution_log": "artifacts/work/execute.log",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "description: nested description" in prompt
    assert "format_hint: nested hint" in prompt
    assert "example: nested-example.log" in prompt
    assert "legacy description" not in prompt
    assert "legacy hint" not in prompt
    assert "legacy-example.log" not in prompt


def test_reference_mode_omits_existing_target_file_body(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "baseline.md").write_text("sensitive baseline body\n", encoding="utf-8")

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "baseline_design",
                    "prompt": {
                        "mode": "reference",
                    },
                },
            ],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "baseline_design": "docs/baseline.md",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "resolved_value: docs/baseline.md" in prompt
    assert "sensitive baseline body" not in prompt
    assert "These references preserve artifact lineage; open them only when needed." in prompt


def test_content_only_consume_prompt_uses_content_footer(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "execution_log",
                },
            ],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "execution_log": "artifacts/work/execute.log",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "- execution_log: artifacts/work/execute.log" in prompt
    assert "Use these consumed artifacts as context for your work." in prompt


def test_prompt_consumes_filter_applies_before_row_modes(tmp_path: Path) -> None:
    composer = PromptComposer(workspace=tmp_path, asset_resolver=None)

    prompt = composer.apply_consumes_prompt_injection(
        {
            "name": "Review",
            "provider": "mock-provider",
            "consumes": [
                {
                    "artifact": "baseline_design",
                    "prompt": {
                        "mode": "reference",
                    },
                },
                {
                    "artifact": "execution_log",
                    "prompt": {
                        "mode": "content",
                    },
                },
            ],
            "prompt_consumes": ["execution_log"],
        },
        "Review the implementation.\n",
        resolved_consumes={
            "root.review": {
                "baseline_design": "docs/baseline.md",
                "execution_log": "artifacts/work/execute.log",
            }
        },
        step_name="Review",
        consume_identity="root.review",
        uses_qualified_identities=True,
    )

    assert "- execution_log: artifacts/work/execute.log" in prompt
    assert "baseline_design" not in prompt
    assert "Use these consumed artifacts as context for your work." in prompt
