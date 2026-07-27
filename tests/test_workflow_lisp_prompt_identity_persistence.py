"""Target-2.22 prompt-attempt persistence and compatibility tests."""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

import orchestrator.workflow_lisp as workflow_lisp
from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    persisted_surface_sha256,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.prompt_fragment_contract import (
    serialize_compiler_prompt_attempt_binding_plan,
    serialize_compiler_prompt_fragment_contract,
)
from orchestrator.workflow.surface_ast import (
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
)
from tests.test_workflow_lisp_build_artifacts import (
    _build_module,
    _build_request,
    _call_step,
    _persisted_fragment_contracts,
    _synthetic_surface_bundle,
)
from tests.test_workflow_lisp_prompt_identity_carriage import (
    _compile,
    _provider_carriers,
)


_BASE_STEP_KEYS = {
    "name",
    "step_id",
    "kind",
    "authored_id",
    "call_alias",
    "input_file",
    "asset_file",
    "depends_on",
    "asset_depends_on",
    "adjudicated_provider",
    "common",
    "for_each_steps",
    "then_steps",
    "else_steps",
    "match_cases",
    "repeat_until",
}
_Q1_Q2_FIELDS = {
    "compiler_prompt_fragment_contract",
    "compiled_prompt_fragment_identity",
}
_Q3_FIELDS = {
    "prompt_attempt_identity_version",
    "compiler_prompt_attempt_binding_plan",
}


def _legacy_fragment_bundle(
    tmp_path: Path,
    *,
    target_dsl: str,
    with_output: bool,
    name: str,
):
    template = _build_module().build_frontend_bundle(
        _build_request(tmp_path)
    ).validated_bundle
    q1, q2, expected_outputs = _persisted_fragment_contracts()
    contract = q2 if with_output else q1
    step = SurfaceStep(
        name="Q2" if with_output else "Q1",
        step_id="q2" if with_output else "q1",
        kind=SurfaceStepKind.PROVIDER,
        provider="test-provider",
        common=SurfaceStepCommonConfig(
            expected_outputs=expected_outputs if with_output else ()
        ),
        compiler_prompt_fragment_contract=contract,
        compiled_prompt_fragment_identity=(
            contract.compiled_prompt_fragment_identity
        ),
    )
    bundle = _synthetic_surface_bundle(
        template,
        name,
        steps=(step,),
    )
    return replace(
        bundle,
        surface=replace(bundle.surface, version=target_dsl),
    )


@pytest.mark.parametrize(
    ("target_dsl", "with_output", "name", "expected_sha256"),
    (
        (
            "2.20",
            False,
            "golden::target-2.20-q1",
            "sha256:011162a8340da19938697e8fcc5f937371df4da5993f40b16cb071cfe35872f2",
        ),
        (
            "2.21",
            False,
            "golden::target-2.21-q1",
            "sha256:2b0774fceae20540b0a494933aae8d94c9480800ed58ba970bf13bcd92bb6897",
        ),
        (
            "2.21",
            True,
            "golden::target-2.21-q2",
            "sha256:04a61c6a1dded1869011f08c8d7b10955721e3078cba76f6966fd17ae22fad43",
        ),
    ),
)
def test_persisted_surface_v1_v2_canonical_bytes_are_frozen(
    tmp_path: Path,
    target_dsl: str,
    with_output: bool,
    name: str,
    expected_sha256: str,
) -> None:
    bundle = _legacy_fragment_bundle(
        tmp_path,
        target_dsl=target_dsl,
        with_output=with_output,
        name=name,
    )

    payload = serialize_persisted_workflow_surface_graph(bundle)
    canonical = canonical_persisted_surface_bytes(payload)

    assert persisted_surface_sha256(canonical) == expected_sha256
    decoded = decode_persisted_workflow_surface_graph(canonical)
    assert decoded.schema_version == (
        "persisted_workflow_surface_graph.v2"
        if with_output
        else "persisted_workflow_surface_graph.v1"
    )


def _q3_bundle(tmp_path: Path, *, with_output: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = _compile(
        tmp_path,
        target_dsl="2.22",
        lowering_route="legacy",
        with_output=with_output,
    )
    return _provider_carriers(result)[-1]


def _q3_graph_payload(tmp_path: Path):
    bundle = _q3_bundle(tmp_path)
    surface = next(
        step
        for step in bundle.surface.steps
        if step.kind is SurfaceStepKind.PROVIDER
    )
    payload = serialize_persisted_workflow_surface_graph(bundle)
    node = next(iter(payload["nodes"].values()))
    step = node["steps"][0]
    payload["schema_version"] = "persisted_workflow_surface_graph.v3"
    step["compiler_prompt_fragment_contract"] = (
        serialize_compiler_prompt_fragment_contract(
            surface.compiler_prompt_fragment_contract
        )
    )
    step["compiled_prompt_fragment_identity"] = (
        surface.compiled_prompt_fragment_identity
    )
    step["prompt_attempt_identity_version"] = (
        surface.prompt_attempt_identity_version
    )
    step["compiler_prompt_attempt_binding_plan"] = (
        serialize_compiler_prompt_attempt_binding_plan(
            surface.compiler_prompt_attempt_binding_plan
        )
    )
    return payload


def test_persisted_surface_graph_v3_carries_exact_pair_in_mixed_graph(
    tmp_path: Path,
) -> None:
    q3_template = _q3_bundle(tmp_path / "q3")
    q3_step = next(
        step
        for step in q3_template.surface.steps
        if step.kind is SurfaceStepKind.PROVIDER
    )
    legacy_template = _legacy_fragment_bundle(
        tmp_path / "legacy",
        target_dsl="2.21",
        with_output=True,
        name="legacy::template",
    )
    q1, q2, expected_outputs = _persisted_fragment_contracts()
    legacy = _synthetic_surface_bundle(
        legacy_template,
        "legacy::mixed",
        steps=(
            SurfaceStep(
                name="Q2",
                step_id="q2",
                kind=SurfaceStepKind.PROVIDER,
                provider="test-provider",
                common=SurfaceStepCommonConfig(
                    expected_outputs=expected_outputs
                ),
                compiler_prompt_fragment_contract=q2,
                compiled_prompt_fragment_identity=(
                    q2.compiled_prompt_fragment_identity
                ),
            ),
            SurfaceStep(
                name="Q1",
                step_id="q1",
                kind=SurfaceStepKind.PROVIDER,
                provider="test-provider",
                compiler_prompt_fragment_contract=q1,
                compiled_prompt_fragment_identity=(
                    q1.compiled_prompt_fragment_identity
                ),
            ),
            SurfaceStep(
                name="Plain",
                step_id="plain",
                kind=SurfaceStepKind.COMMAND,
                command=("true",),
            ),
        ),
    )
    root = _synthetic_surface_bundle(
        q3_template,
        "q3::mixed-root",
        steps=(q3_step, _call_step("Legacy", "legacy")),
        imports={"legacy": legacy},
    )

    payload = serialize_persisted_workflow_surface_graph(root)

    assert payload["schema_version"] == (
        "persisted_workflow_surface_graph.v3"
    )
    q3_wire = payload["nodes"]["q3::mixed-root"]["steps"][0]
    assert set(q3_wire) == _BASE_STEP_KEYS | _Q1_Q2_FIELDS | _Q3_FIELDS | {
        "compiler_prompt_dependency_contract"
    }
    assert q3_wire["prompt_attempt_identity_version"] == (
        q3_step.prompt_attempt_identity_version
    )
    assert q3_wire["compiler_prompt_attempt_binding_plan"] == (
        serialize_compiler_prompt_attempt_binding_plan(
            q3_step.compiler_prompt_attempt_binding_plan
        )
    )
    legacy_steps = payload["nodes"]["legacy::mixed"]["steps"]
    assert set(legacy_steps[0]) == _BASE_STEP_KEYS | _Q1_Q2_FIELDS
    assert set(legacy_steps[1]) == _BASE_STEP_KEYS
    assert set(legacy_steps[2]) == _BASE_STEP_KEYS

    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    decoded_q3 = decoded.nodes["q3::mixed-root"].steps[0]
    assert decoded_q3.prompt_attempt_identity_version == (
        q3_step.prompt_attempt_identity_version
    )
    assert decoded_q3.compiler_prompt_attempt_binding_plan == (
        q3_step.compiler_prompt_attempt_binding_plan
    )
    assert decoded_q3.compiler_prompt_fragment_contract == (
        q3_step.compiler_prompt_fragment_contract
    )


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    (
        ("missing_pair", "prompt_attempt_identity_version_missing"),
        ("missing_version", "prompt_attempt_identity_version_missing"),
        ("missing_plan", "prompt_attempt_binding_plan_missing"),
        ("invalid_version", "prompt_attempt_identity_version_invalid"),
        ("extra_plan_field", "prompt_attempt_binding_plan_invalid"),
        ("reordered_rows", "prompt_attempt_binding_plan_invalid"),
        ("digest_mismatch", "prompt_attempt_binding_plan_invalid"),
        ("target_version_mismatch", "prompt_attempt_identity_version_invalid"),
        ("graph_version_mismatch", "persisted surface step"),
    ),
)
def test_persisted_surface_v3_decoder_rejects_damaged_carriage(
    tmp_path: Path,
    mutation: str,
    diagnostic: str,
) -> None:
    payload = copy.deepcopy(_q3_graph_payload(tmp_path))
    node = next(iter(payload["nodes"].values()))
    step = node["steps"][0]
    if mutation == "missing_pair":
        step.pop("prompt_attempt_identity_version")
        step.pop("compiler_prompt_attempt_binding_plan")
    elif mutation == "missing_version":
        step.pop("prompt_attempt_identity_version")
    elif mutation == "missing_plan":
        step.pop("compiler_prompt_attempt_binding_plan")
    elif mutation == "invalid_version":
        step["prompt_attempt_identity_version"] = (
            "workflow_prompt_attempt_identity.v999"
        )
    elif mutation == "extra_plan_field":
        step["compiler_prompt_attempt_binding_plan"]["unexpected"] = True
    elif mutation == "reordered_rows":
        step["compiler_prompt_attempt_binding_plan"]["rows"].reverse()
    elif mutation == "digest_mismatch":
        step["compiler_prompt_attempt_binding_plan"]["plan_sha256"] = (
            "sha256:" + "0" * 64
        )
    elif mutation == "target_version_mismatch":
        node["version"] = "2.21"
    elif mutation == "graph_version_mismatch":
        payload["schema_version"] = "persisted_workflow_surface_graph.v2"
    else:
        raise AssertionError(mutation)

    with pytest.raises(ValueError, match=diagnostic):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(payload)
        )


@pytest.mark.parametrize(
    ("removed_field", "diagnostic"),
    (
        (
            "prompt_attempt_identity_version",
            "prompt_attempt_identity_version_missing",
        ),
        (
            "compiler_prompt_attempt_binding_plan",
            "prompt_attempt_binding_plan_missing",
        ),
    ),
)
def test_persisted_surface_v3_encoder_rejects_dropped_pair_member(
    tmp_path: Path,
    removed_field: str,
    diagnostic: str,
) -> None:
    bundle = _q3_bundle(tmp_path)
    step = next(
        step
        for step in bundle.surface.steps
        if step.kind is SurfaceStepKind.PROVIDER
    )
    original = getattr(step, removed_field)
    object.__setattr__(step, removed_field, None)
    try:
        with pytest.raises(ValueError, match=diagnostic):
            serialize_persisted_workflow_surface_graph(bundle)
    finally:
        object.__setattr__(step, removed_field, original)


def test_persisted_surface_v3_rejects_q3_field_on_unrelated_step(
    tmp_path: Path,
) -> None:
    payload = copy.deepcopy(_q3_graph_payload(tmp_path))
    node = next(iter(payload["nodes"].values()))
    plain = copy.deepcopy(node["steps"][0])
    plain["name"] = "Plain"
    plain["step_id"] = "plain"
    plain["kind"] = "command"
    plain.pop("compiler_prompt_dependency_contract")
    plain.pop("compiler_prompt_fragment_contract")
    plain.pop("compiled_prompt_fragment_identity")
    plain.pop("compiler_prompt_attempt_binding_plan")
    node["steps"].append(plain)

    with pytest.raises(
        ValueError,
        match="prompt_attempt_binding_plan_missing",
    ):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(payload)
        )


def test_persisted_surface_v3_decoder_rejects_complete_q3_pair_on_command(
    tmp_path: Path,
) -> None:
    payload = copy.deepcopy(_q3_graph_payload(tmp_path))
    node = next(iter(payload["nodes"].values()))
    node["steps"][0]["kind"] = "command"

    with pytest.raises(
        ValueError,
        match="prompt_attempt_binding_plan_mismatch",
    ):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(payload)
        )


def test_persisted_surface_v3_encoder_rejects_complete_q3_pair_on_command(
    tmp_path: Path,
) -> None:
    bundle = _q3_bundle(tmp_path)
    step = next(
        step
        for step in bundle.surface.steps
        if step.kind is SurfaceStepKind.PROVIDER
    )
    object.__setattr__(step, "kind", SurfaceStepKind.COMMAND)
    try:
        with pytest.raises(
            ValueError,
            match="prompt_attempt_binding_plan_mismatch",
        ):
            serialize_persisted_workflow_surface_graph(bundle)
    finally:
        object.__setattr__(step, "kind", SurfaceStepKind.PROVIDER)


def _mixed_q3_with_target_220_q1_payload(
    tmp_path: Path,
) -> tuple[dict[str, object], object]:
    q3_bundle = _q3_bundle(tmp_path / "q3")
    q3_step = next(
        step
        for step in q3_bundle.surface.steps
        if step.kind is SurfaceStepKind.PROVIDER
    )
    legacy = _legacy_fragment_bundle(
        tmp_path / "legacy",
        target_dsl="2.20",
        with_output=False,
        name="legacy::target-2.20-q1",
    )
    root = _synthetic_surface_bundle(
        q3_bundle,
        "q3::mixed-target-2.20",
        steps=(q3_step, _call_step("Legacy", "legacy")),
        imports={"legacy": legacy},
    )
    payload = serialize_persisted_workflow_surface_graph(root)
    q1, _, _ = _persisted_fragment_contracts()
    return payload, q1


def test_persisted_surface_v3_encoder_preserves_target_220_q1_step_keyset(
    tmp_path: Path,
) -> None:
    payload, _ = _mixed_q3_with_target_220_q1_payload(tmp_path)

    legacy_step = payload["nodes"]["legacy::target-2.20-q1"]["steps"][0]

    assert payload["schema_version"] == (
        "persisted_workflow_surface_graph.v3"
    )
    assert set(legacy_step) == _BASE_STEP_KEYS


def test_persisted_surface_v3_decoder_rejects_target_220_q1_wire_fields(
    tmp_path: Path,
) -> None:
    payload, q1 = _mixed_q3_with_target_220_q1_payload(tmp_path)
    legacy_step = payload["nodes"]["legacy::target-2.20-q1"]["steps"][0]
    legacy_step["compiler_prompt_fragment_contract"] = (
        serialize_compiler_prompt_fragment_contract(q1)
    )
    legacy_step["compiled_prompt_fragment_identity"] = (
        q1.compiled_prompt_fragment_identity
    )

    with pytest.raises(
        ValueError,
        match="persisted surface step has unsupported",
    ):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(payload)
        )


def test_persisted_surface_v3_round_trips_document_slot_with_distinct_source_name(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "distinct_document_source.orc"
    source_path.write_text(
        """
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.22")
  (defmodule demo/distinct-document-source)

  (defpath DesignDocPath
    :kind relpath
    :under "docs/design"
    :must-exist true)

  (defprompt review
    (:fills
      (target_doc :doc DesignDocPath))
    -> Bool
    "Review the supplied design.")

  (defworkflow run-review
    ((design_doc DesignDocPath))
    -> Bool
    (provider-result providers.review
      :prompt
        (review :target_doc design_doc))))
""".lstrip(),
        encoding="utf-8",
    )
    result = workflow_lisp.compile_stage3_module(
        source_path,
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )
    bundle = result.validated_bundles["run-review"]

    payload = serialize_persisted_workflow_surface_graph(bundle)
    wire_step = payload["nodes"][bundle.surface.name]["steps"][0]
    row = wire_step["compiler_prompt_attempt_binding_plan"]["rows"][0]

    assert row["slot_name"] == "target_doc"
    assert wire_step["compiler_prompt_dependency_contract"][
        "required_binding_refs"
    ] == ["inputs.design_doc"]

    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    decoded_step = decoded.entry_node.steps[0]
    assert decoded_step.compiler_prompt_attempt_binding_plan == (
        next(
            node.execution_config.compiler_prompt_attempt_binding_plan
            for node in bundle.ir.nodes.values()
            if node.step_id == decoded_step.step_id
        )
    )
