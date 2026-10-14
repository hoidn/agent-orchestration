from __future__ import annotations

import copy
import importlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from orchestrator.workflow.surface_ast import SurfaceWorkflow, WorkflowProvenance

import pytest

from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.prompt_fragment_contract import (
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
    COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
    CompilerPromptFragmentContract,
    CompilerPromptFragmentContractV2,
    CompilerPromptFragmentOutputPosition,
    CompilerPromptFragmentRenderedSlot,
)
from orchestrator.workflow.surface_ast import (
    SurfaceFinallyBlock,
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CLI_FIXTURES = FIXTURES / "cli"
DESIGN_DELTA_MIGRATION_INPUTS = (
    REPO_ROOT / "workflows" / "examples" / "inputs" / "workflow_lisp_migrations"
)
# This checked-in candidate remains the authoritative proof source for the
# imported-child prerequisite until the shipping library module lands its
# separate parent-callable `run-work-item` export.
ENTRYPOINT = FIXTURES / "modules" / "valid" / "imported_bundle_mix" / "neurips" / "entry.orc"
SOURCE_ROOT = FIXTURES / "modules" / "valid" / "imported_bundle_mix"
IMPORTED_STDLIB_HELPER_ROOT = FIXTURES / "modules" / "valid" / "imported_stdlib_macro_payload_helper_composition"
IMPORTED_STDLIB_HELPER_ENTRY = (
    IMPORTED_STDLIB_HELPER_ROOT / "imported_stdlib_macro_payload_helper_composition" / "entry.orc"
)
PURE_EXPR_SELECTOR_FIXTURE = FIXTURES / "valid" / "pure_expr_selector_action_projection.orc"
MATERIALIZE_VIEW_ALLOCATED_TARGET_FIXTURE = FIXTURES / "valid" / "materialize_view_allocated_target.orc"
LEXICAL_CHECKPOINT_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_shadow_points.orc"
LEXICAL_POLICY_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_effect_policies.orc"
LEXICAL_RESTORE_FIXTURE = FIXTURES / "valid" / "lexical_checkpoint_restore_regions.orc"
PROCEDURE_IDENTITY_FIXTURE = FIXTURES / "valid" / "procedure_lowering_identity_modes.orc"
RUNTIME_CLOSURE_MARKERS = (
    "workflow_lisp_runtime_closure",
    "closure_families",
    "InvokeClosure",
    "Closure[",
    "runtime_closure",
)




def _synthetic_surface_bundle(
    template,
    name: str,
    *,
    steps: tuple[SurfaceStep, ...] = (),
    imports=None,
    finalization: SurfaceFinallyBlock | None = None,
):
    provenance = replace(
        template.provenance,
        workflow_path=Path(f"synthetic/{name}.orc"),
    )
    surface = replace(
        template.surface,
        name=name,
        steps=steps,
        finalization=finalization,
        provenance=provenance,
    )
    return replace(
        template,
        surface=surface,
        imports={} if imports is None else imports,
        provenance=provenance,
    )


def _call_step(name: str, alias: str) -> SurfaceStep:
    return SurfaceStep(
        name=name,
        step_id=name,
        kind=SurfaceStepKind.CALL,
        call_alias=alias,
    )


def _persisted_wire_step(
    *,
    kind: str = "command",
    call_alias: str | None = None,
    for_each_steps: list[dict[str, object]] | None = None,
    then_steps: list[dict[str, object]] | None = None,
    else_steps: list[dict[str, object]] | None = None,
    match_cases: dict[str, list[dict[str, object]]] | None = None,
    repeat_until: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "name": f"{kind}-step",
        "step_id": f"{kind}-step",
        "kind": kind,
        "authored_id": None,
        "call_alias": call_alias,
        "input_file": None,
        "asset_file": None,
        "depends_on": {},
        "asset_depends_on": [],
        "adjudicated_provider": {},
        "common": {
            "publishes": [],
            "consumes": [],
            "expected_outputs": [],
            "output_bundle": None,
            "variant_output": None,
        },
        "for_each_steps": for_each_steps or [],
        "then_steps": then_steps or [],
        "else_steps": else_steps or [],
        "match_cases": match_cases or {},
        "repeat_until": repeat_until,
    }


def _persisted_wire_graph(
    step: dict[str, object],
    *,
    calls: dict[str, str] | None = None,
) -> dict[str, object]:
    node = {
        "workflow_name": "wire::root",
        "version": "2.14",
        "workflow_path": "wire/root.orc",
        "calls": calls or {},
        "steps": [step],
        "finalization_steps": [],
    }
    nodes = {"wire::root": node}
    for target in (calls or {}).values():
        nodes[target] = {
            "workflow_name": target,
            "version": "2.14",
            "workflow_path": f"{target}.orc",
            "calls": {},
            "steps": [],
            "finalization_steps": [],
        }
    return {
        "schema_version": "persisted_workflow_surface_graph.v1",
        "entry_workflow": "wire::root",
        "nodes": nodes,
    }


def _persisted_fragment_contracts():
    q1_slot = CompilerPromptFragmentRenderedSlot(
        name="message",
        kind="text",
        static_type={"kind": "primitive", "name": "String"},
        renderer_id="raw-utf8-string",
        value_source={
            "kind": "typed_binding_ref",
            "binding": {"ref": "inputs.message"},
        },
        placeholder_ordinals=(0,),
    )
    q1 = CompilerPromptFragmentContract(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA,
        template_utf8="{message}",
        rendered_slots=(q1_slot,),
        compiled_prompt_fragment_identity="sha256:" + "1" * 64,
    )
    path_slots = tuple(
        CompilerPromptFragmentRenderedSlot(
            name=name,
            kind="path",
            static_type={
                "kind": "path",
                "must_exist_target": False,
                "name": "ReportPath",
                "under": "artifacts",
            },
            renderer_id="posix-path-line",
            value_source={
                "kind": "typed_binding_ref",
                "binding": {"ref": f"inputs.{name}"},
            },
            placeholder_ordinals=(index,),
        )
        for index, name in enumerate(("first", "second"))
    )
    expected_outputs = tuple(
        {
            "name": name,
            "path": f"${{inputs.{name}}}",
            "type": "string",
            "required": True,
        }
        for name in ("first", "second")
    )
    q2 = CompilerPromptFragmentContractV2(
        schema_version=COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2,
        template_utf8="{first} {second}",
        rendered_slots=path_slots,
        output_positions=tuple(
            CompilerPromptFragmentOutputPosition(
                slot_name=row["name"],
                output_role="required_string_file",
                expected_output=row,
            )
            for row in expected_outputs
        ),
        compiled_prompt_fragment_identity="sha256:" + "2" * 64,
    )
    return q1, q2, expected_outputs














def test_persisted_surface_serializer_follows_nested_and_finalization_calls_only(
    tmp_path: Path,
) -> None:
    template = _historical_surface_template()
    nested_leaf = _synthetic_surface_bundle(template, "synthetic::nested")
    final_leaf = _synthetic_surface_bundle(template, "synthetic::final")
    unused_leaf = _synthetic_surface_bundle(template, "synthetic::unused")
    nested_call = _call_step("NestedCall", "nested")
    root = _synthetic_surface_bundle(
        template,
        "synthetic::root",
        steps=(
            SurfaceStep(
                name="Loop",
                step_id="loop",
                kind=SurfaceStepKind.FOR_EACH,
                for_each_steps=(nested_call,),
            ),
        ),
        finalization=SurfaceFinallyBlock(
            token="finally",
            step_id="finally",
            steps=(_call_step("FinalCall", "final"),),
        ),
        imports={
            "nested": nested_leaf,
            "final": final_leaf,
            "unused": unused_leaf,
        },
    )

    payload = serialize_persisted_workflow_surface_graph(root)

    assert set(payload["nodes"]) == {
        "synthetic::root",
        "synthetic::nested",
        "synthetic::final",
    }
    assert payload["nodes"]["synthetic::root"]["calls"] == {
        "final": "synthetic::final",
        "nested": "synthetic::nested",
    }
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    assert decoded.entry_node.finalization_steps[0].call_alias == "final"


def test_persisted_surface_v2_mixed_graph_has_exact_per_step_carriage(
    tmp_path: Path,
) -> None:
    template = _historical_surface_template()
    q1, q2, expected_outputs = _persisted_fragment_contracts()
    q2_step = SurfaceStep(
        name="Q2",
        step_id="q2",
        kind=SurfaceStepKind.PROVIDER,
        provider="test-provider",
        common=SurfaceStepCommonConfig(expected_outputs=expected_outputs),
        compiler_prompt_fragment_contract=q2,
        compiled_prompt_fragment_identity=q2.compiled_prompt_fragment_identity,
    )
    q1_step = SurfaceStep(
        name="Q1",
        step_id="q1",
        kind=SurfaceStepKind.PROVIDER,
        provider="test-provider",
        compiler_prompt_fragment_contract=q1,
        compiled_prompt_fragment_identity=q1.compiled_prompt_fragment_identity,
    )
    plain_step = SurfaceStep(
        name="Plain",
        step_id="plain",
        kind=SurfaceStepKind.COMMAND,
        command=("true",),
    )
    root = _synthetic_surface_bundle(
        template,
        "synthetic::mixed-fragments",
        steps=(q2_step, q1_step, plain_step),
    )
    root = replace(
        root,
        surface=replace(root.surface, version="2.21"),
    )

    payload = serialize_persisted_workflow_surface_graph(root)
    assert payload["schema_version"] == "persisted_workflow_surface_graph.v2"
    steps = payload["nodes"]["synthetic::mixed-fragments"]["steps"]
    q2_extra = {
        "compiler_prompt_fragment_contract",
        "compiled_prompt_fragment_identity",
    }
    assert q2_extra <= set(steps[0])
    assert not q2_extra & set(steps[1])
    assert not q2_extra & set(steps[2])
    assert steps[0]["common"]["expected_outputs"] == list(expected_outputs)
    assert steps[0]["compiler_prompt_fragment_contract"][
        "output_positions"
    ] == [
        {
            "slot_name": row["name"],
            "output_role": "required_string_file",
            "expected_output": row,
        }
        for row in expected_outputs
    ]

    canonical = canonical_persisted_surface_bytes(payload)
    decoded = decode_persisted_workflow_surface_graph(canonical)
    decoded_steps = decoded.entry_node.steps
    assert decoded.schema_version == "persisted_workflow_surface_graph.v2"
    assert decoded_steps[0].compiler_prompt_fragment_contract == q2
    assert decoded_steps[0].compiled_prompt_fragment_identity == (
        q2.compiled_prompt_fragment_identity
    )
    assert decoded_steps[1].compiler_prompt_fragment_contract is None
    assert decoded_steps[2].compiler_prompt_fragment_contract is None

    mutations = (
        lambda step: step.pop("compiler_prompt_fragment_contract"),
        lambda step: step.pop("compiled_prompt_fragment_identity"),
        lambda step: step["common"].update(expected_outputs=[]),
        lambda step: step["common"].update(
            expected_outputs=[
                *step["common"]["expected_outputs"],
                step["common"]["expected_outputs"][0],
            ]
        ),
        lambda step: step["common"].update(
            expected_outputs=list(
                reversed(step["common"]["expected_outputs"])
            )
        ),
        lambda step: step["common"]["expected_outputs"][0].update(
            path="${inputs.second}"
        ),
        lambda step: step["compiler_prompt_fragment_contract"].update(
            schema_version="compiler_prompt_fragment_contract.v1"
        ),
        lambda step: step.update(
            compiled_prompt_fragment_identity="sha256:" + "3" * 64
        ),
        lambda step: step.update(compiled_prompt_fragment_identity=""),
        lambda step: step.update(compiled_prompt_fragment_identity=7),
    )
    for mutate in mutations:
        damaged = copy.deepcopy(payload)
        damaged_step = damaged["nodes"]["synthetic::mixed-fragments"]["steps"][0]
        mutate(damaged_step)
        with pytest.raises(
            ValueError,
            match="prompt_output_position_contract_mismatch",
        ):
            decode_persisted_workflow_surface_graph(
                canonical_persisted_surface_bytes(damaged)
            )

    top_level_carrier_key_mutations = (
        lambda contract: contract.pop("template_utf8"),
        lambda contract: contract.update(unexpected_field=True),
    )
    for mutate in top_level_carrier_key_mutations:
        damaged = copy.deepcopy(payload)
        damaged_contract = damaged["nodes"]["synthetic::mixed-fragments"][
            "steps"
        ][0]["compiler_prompt_fragment_contract"]
        mutate(damaged_contract)
        with pytest.raises(
            ValueError,
            match=r"^prompt_output_position_contract_mismatch",
        ) as exc_info:
            decode_persisted_workflow_surface_graph(
                canonical_persisted_surface_bytes(damaged)
            )
        assert str(exc_info.value.__cause__) == (
            "compiler prompt fragment contract v2 has unsupported or missing fields"
        )

    wrong_graph_schema = copy.deepcopy(payload)
    wrong_graph_schema["schema_version"] = (
        "persisted_workflow_surface_graph.v1"
    )
    with pytest.raises(
        ValueError,
        match="prompt_output_position_contract_mismatch",
    ):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(wrong_graph_schema)
        )

    original_contract = q2_step.compiler_prompt_fragment_contract
    original_identity = q2_step.compiled_prompt_fragment_identity
    object.__setattr__(q2_step, "compiler_prompt_fragment_contract", None)
    with pytest.raises(
        ValueError,
        match="compiled_prompt_fragment_identity_missing",
    ):
        serialize_persisted_workflow_surface_graph(root)
    object.__setattr__(
        q2_step,
        "compiler_prompt_fragment_contract",
        original_contract,
    )
    object.__setattr__(q2_step, "compiled_prompt_fragment_identity", None)
    with pytest.raises(
        ValueError,
        match="prompt_output_position_contract_mismatch",
    ):
        serialize_persisted_workflow_surface_graph(root)
    object.__setattr__(
        q2_step,
        "compiled_prompt_fragment_identity",
        original_identity,
    )

    object.__setattr__(
        q2_step,
        "common",
        replace(q2_step.common, expected_outputs=expected_outputs[:1]),
    )
    with pytest.raises(
        ValueError,
        match="prompt_output_position_contract_mismatch",
    ):
        serialize_persisted_workflow_surface_graph(root)


def test_persisted_surface_serializer_deduplicates_diamond_by_workflow_name(
    tmp_path: Path,
) -> None:
    template = _historical_surface_template()
    shared_left = _synthetic_surface_bundle(template, "synthetic::shared")
    shared_right = _synthetic_surface_bundle(template, "synthetic::shared")
    left = _synthetic_surface_bundle(
        template,
        "synthetic::left",
        steps=(_call_step("LeftShared", "shared"),),
        imports={"shared": shared_left},
    )
    right = _synthetic_surface_bundle(
        template,
        "synthetic::right",
        steps=(_call_step("RightShared", "shared"),),
        imports={"shared": shared_right},
    )
    root = _synthetic_surface_bundle(
        template,
        "synthetic::root",
        steps=(_call_step("Left", "left"), _call_step("Right", "right")),
        imports={"left": left, "right": right},
    )

    payload = serialize_persisted_workflow_surface_graph(root)

    assert set(payload["nodes"]) == {
        "synthetic::root",
        "synthetic::left",
        "synthetic::right",
        "synthetic::shared",
    }


def test_persisted_surface_serializer_rejects_missing_used_alias(tmp_path: Path) -> None:
    template = _historical_surface_template()
    root = _synthetic_surface_bundle(
        template,
        "synthetic::root",
        steps=(_call_step("Missing", "missing"),),
    )

    with pytest.raises(ValueError, match="has no imported bundle"):
        serialize_persisted_workflow_surface_graph(root)


def test_persisted_surface_serializer_rejects_import_cycle(tmp_path: Path) -> None:
    template = _historical_surface_template()
    imports = {}
    root = _synthetic_surface_bundle(
        template,
        "synthetic::root",
        steps=(_call_step("Back", "back"),),
        imports=imports,
    )
    imports["back"] = root

    with pytest.raises(ValueError, match="import cycle"):
        serialize_persisted_workflow_surface_graph(root)


def test_persisted_surface_serializer_rejects_same_name_different_payload(
    tmp_path: Path,
) -> None:
    template = _historical_surface_template()
    first = _synthetic_surface_bundle(template, "synthetic::shared")
    second = _synthetic_surface_bundle(
        template,
        "synthetic::shared",
        steps=(
            SurfaceStep(
                name="Different",
                step_id="different",
                kind=SurfaceStepKind.COMMAND,
            ),
        ),
    )
    root = _synthetic_surface_bundle(
        template,
        "synthetic::root",
        steps=(_call_step("First", "first"), _call_step("Second", "second")),
        imports={"first": first, "second": second},
    )

    with pytest.raises(ValueError, match="workflow-name conflict"):
        serialize_persisted_workflow_surface_graph(root)


def test_persisted_surface_decoder_accepts_only_canonical_closed_wire_payload(
    tmp_path: Path,
) -> None:
    canonical = canonical_persisted_surface_bytes(_historical_call_wire_graph())
    raw = json.loads(canonical)

    assert decode_persisted_workflow_surface_graph(canonical).entry_workflow == (
        "neurips/entry::orchestrate"
    )
    with pytest.raises(ValueError, match="not canonical"):
        decode_persisted_workflow_surface_graph(
            (json.dumps(raw, indent=2, sort_keys=True) + "\n").encode()
        )
    duplicate_root_key = canonical[:-2] + (
        b',"schema_version":"persisted_workflow_surface_graph.v1"}\n'
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        decode_persisted_workflow_surface_graph(duplicate_root_key)

    for mutate in (
        lambda value: value.update(schema_version="unsupported.v1"),
        lambda value: value.update(extra="unsupported"),
        lambda value: value.pop("entry_workflow"),
        lambda value: value["nodes"][value["entry_workflow"]]["steps"][0].update(
            extra="unsupported"
        ),
    ):
        damaged = copy.deepcopy(raw)
        mutate(damaged)
        with pytest.raises(ValueError):
            decode_persisted_workflow_surface_graph(
                canonical_persisted_surface_bytes(damaged)
            )

    metadata = copy.deepcopy(raw)
    metadata_step = metadata["nodes"]["imported_selector::selector-run"]["steps"][0]
    metadata_step["asset_depends_on"] = [{"nested": ["asset"]}]
    metadata_step["common"]["publishes"] = [{"nested": ["publish"]}]
    metadata_step["common"]["consumes"] = [{"nested": ["consume"]}]
    metadata_step["common"]["expected_outputs"] = [{"nested": ["output"]}]
    frozen_step = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(metadata)
    ).nodes["imported_selector::selector-run"].steps[0]
    for value in (
        frozen_step.asset_depends_on[0],
        frozen_step.common.publishes[0],
        frozen_step.common.consumes[0],
        frozen_step.common.expected_outputs[0],
    ):
        assert value["nested"] == (value["nested"][0],)
        with pytest.raises(TypeError):
            value["nested"] = ()


def test_persisted_surface_decoder_rejects_missing_extra_cycle_and_unreachable_edges(
    tmp_path: Path,
) -> None:
    raw = _historical_call_wire_graph()
    entry_name = raw["entry_workflow"]

    extra_alias = copy.deepcopy(raw)
    extra_alias["nodes"][entry_name]["calls"]["unused"] = (
        "imported_selector::selector-run"
    )
    with pytest.raises(ValueError, match="call-edge table"):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(extra_alias)
        )

    missing_target = copy.deepcopy(raw)
    first_alias = next(iter(missing_target["nodes"][entry_name]["calls"]))
    missing_target["nodes"][entry_name]["calls"][first_alias] = "missing"
    with pytest.raises(ValueError, match="target is missing"):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(missing_target)
        )

    cyclic = copy.deepcopy(raw)
    selector_step = cyclic["nodes"]["imported_selector::selector-run"]["steps"][0]
    selector_step["kind"] = "call"
    selector_step["call_alias"] = "back"
    cyclic["nodes"]["imported_selector::selector-run"]["calls"] = {
        "back": entry_name
    }
    with pytest.raises(ValueError, match="import cycle"):
        decode_persisted_workflow_surface_graph(canonical_persisted_surface_bytes(cyclic))

    unreachable = copy.deepcopy(raw)
    orphan = copy.deepcopy(
        unreachable["nodes"]["imported_selector::selector-run"]
    )
    orphan["workflow_name"] = "orphan"
    unreachable["nodes"]["orphan"] = orphan
    with pytest.raises(ValueError, match="unreachable"):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(unreachable)
        )


def test_persisted_surface_codec_rejects_nonfinite_json_numbers() -> None:
    canonical = canonical_persisted_surface_bytes(
        _persisted_wire_graph(_persisted_wire_step())
    )
    assert decode_persisted_workflow_surface_graph(canonical).entry_workflow == (
        "wire::root"
    )

    for value in (float("nan"), float("inf"), float("-inf")):
        payload = _persisted_wire_graph(_persisted_wire_step())
        payload["nodes"]["wire::root"]["steps"][0]["input_file"] = value
        with pytest.raises(ValueError, match="JSON"):
            canonical_persisted_surface_bytes(payload)

    marker = b'"input_file":null'
    for constant in (b"NaN", b"Infinity", b"-Infinity"):
        damaged = canonical.replace(marker, b'"input_file":' + constant, 1)
        with pytest.raises(ValueError, match="non-finite"):
            decode_persisted_workflow_surface_graph(damaged)


@pytest.mark.parametrize(
    ("step", "calls"),
    [
        (_persisted_wire_step(), {}),
        (_persisted_wire_step(kind="call", call_alias="child"), {"child": "wire::child"}),
        (
            _persisted_wire_step(
                kind="for_each",
                for_each_steps=[_persisted_wire_step()],
            ),
            {},
        ),
        (
            _persisted_wire_step(
                kind="if",
                then_steps=[_persisted_wire_step()],
                else_steps=[_persisted_wire_step()],
            ),
            {},
        ),
        (
            _persisted_wire_step(
                kind="match",
                match_cases={"APPROVE": [_persisted_wire_step()]},
            ),
            {},
        ),
        (
            _persisted_wire_step(
                kind="repeat_until",
                repeat_until={
                    "max_iterations": 2,
                    "steps": [_persisted_wire_step()],
                },
            ),
            {},
        ),
    ],
)
def test_persisted_surface_decoder_accepts_coherent_step_kind_shapes(
    step: dict[str, object],
    calls: dict[str, str],
) -> None:
    graph = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(_persisted_wire_graph(step, calls=calls))
    )

    assert graph.entry_node.steps[0].kind.value == step["kind"]


@pytest.mark.parametrize(
    "step",
    [
        _persisted_wire_step(kind="call"),
        _persisted_wire_step(call_alias="child"),
        _persisted_wire_step(for_each_steps=[_persisted_wire_step()]),
        _persisted_wire_step(then_steps=[_persisted_wire_step()]),
        _persisted_wire_step(else_steps=[_persisted_wire_step()]),
        _persisted_wire_step(match_cases={"case": [_persisted_wire_step()]}),
        _persisted_wire_step(
            repeat_until={"max_iterations": 2, "steps": [_persisted_wire_step()]}
        ),
        _persisted_wire_step(kind="repeat_until"),
    ],
)
def test_persisted_surface_decoder_rejects_incoherent_step_kind_shapes(
    step: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="kind"):
        decode_persisted_workflow_surface_graph(
            canonical_persisted_surface_bytes(_persisted_wire_graph(step))
        )




def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")




















@pytest.mark.parametrize(
    ("entry", "expected_code"),
    [
        (
            {"path": "must-not-be-read.orc"},
            "imported_workflow_bundle_kind_invalid",
        ),
        (
            {"kind": "yaml", "path": "must-not-be-read.yaml"},
            "imported_workflow_bundle_kind_invalid",
        ),
        (
            {"kind": "compiled", "path": "must-not-be-read.yaml"},
            "imported_workflow_bundle_path_invalid",
        ),
    ],
    ids=("omitted-kind", "yaml-kind", "compiled-non-orc"),
)
def test_imported_bundle_manifest_rejects_non_compiled_orc_entries_before_source_read(
    tmp_path: Path,
    entry: dict[str, str],
    expected_code: str,
) -> None:
    manifest_path = tmp_path / "imported-workflows.json"
    manifest_path.write_text(
        json.dumps({"selector-run": entry}),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_module().load_imported_workflow_bundle_manifest(
            manifest_path,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == expected_code


def test_imported_bundle_manifest_accepts_case_insensitive_orc_suffix(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "selector_upper.ORC"
    source_path.write_text(
        (CLI_FIXTURES / "imported_selector.orc")
        .read_text(encoding="utf-8")
        .replace("(defmodule imported_selector)", "(defmodule selector_upper)", 1),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "imported-workflows.json"
    manifest_path.write_text(
        json.dumps(
            {
                "selector-run": {
                    "kind": "compiled",
                    "path": source_path.name,
                }
            }
        ),
        encoding="utf-8",
    )

    bindings = _build_module().load_imported_workflow_bundle_manifest(
        manifest_path,
        workspace_root=tmp_path,
    )

    assert bindings[0].workflow_name == "selector_upper::selector-run"


def test_compiled_imported_bundle_preserves_recursive_orc_workflow_imports(
    tmp_path: Path,
) -> None:
    module_root = tmp_path / "recursive"
    module_root.mkdir()
    (module_root / "types.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule recursive/types)",
                "  (export WorkReport ChecksResult ImplementationSummary)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (module_root / "child.orc").write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule recursive/child)",
                "  (import recursive/types",
                "    :only (ChecksResult ImplementationSummary WorkReport))",
                "  (export selector-child)",
                "  (defworkflow selector-child",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (record ImplementationSummary :report report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    root_path = module_root / "root.orc"
    root_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule recursive/root)",
                "  (import recursive/types",
                "    :only (ChecksResult ImplementationSummary WorkReport))",
                "  (import recursive/child :as child :only (selector-child))",
                "  (export selector-run)",
                "  (defworkflow selector-run",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (call child.selector-child",
                "      :input input",
                "      :report_path report_path)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "imported-workflows.json"
    manifest_path.write_text(
        json.dumps(
            {
                "selector-run": {
                    "kind": "compiled",
                    "path": str(root_path),
                }
            }
        ),
        encoding="utf-8",
    )

    bindings = _build_module().load_imported_workflow_bundle_manifest(
        manifest_path,
        workspace_root=tmp_path,
        source_roots=(tmp_path,),
    )

    assert len(bindings) == 1
    assert bindings[0].load_status == "compiled"
    assert "recursive/child::selector-child" in bindings[0].typed_program.workflows





























































































































































def test_parse_command_boundary_manifest_accepts_promoted_certified_adapter_metadata() -> None:
    build = _build_module()
    parse_manifest = getattr(build, "_parse_command_boundaries_manifest")

    bindings = parse_manifest(
        {
            "normalize_result": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_result.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "ImplementationSummary",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_result_ok"],
                "negative_fixture_ids": ["normalize_result_bad"],
                "behavior_class": "structured_result",
                "input_signature": [
                    {
                        "name": "execution_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "execution_report",
                    },
                    {
                        "name": "review_report",
                        "type_name": "WorkReport",
                        "required": True,
                        "transport_key": "review_report",
                    },
                ],
                "artifact_contracts": ["implementation_summary_report"],
                "state_writes": [],
                "error_codes": ["normalize_result_invalid_payload"],
                "owner_module": "std/phase",
                "replacement_path": None,
                "invocation_protocol": "json_object_positional_arg",
            }
        },
        manifest_path=None,
    )

    binding = bindings["normalize_result"]

    assert binding.behavior_class == "structured_result"
    assert binding.invocation_protocol == "json_object_positional_arg"
    assert tuple(field.transport_key for field in binding.input_signature) == (
        "execution_report",
        "review_report",
    )


def test_parse_command_boundary_manifest_keeps_legacy_certified_adapter_argv_compatibility() -> None:
    build = _build_module()
    parse_manifest = getattr(build, "_parse_command_boundaries_manifest")

    bindings = parse_manifest(
        {
            "normalize_result": {
                "kind": "certified_adapter",
                "stable_command": ["python", "scripts/normalize_result.py"],
                "input_contract": {"type": "object"},
                "output_type_name": "ImplementationSummary",
                "effects": ["structured_result"],
                "path_safety": {"kind": "workspace_relpath"},
                "source_map_behavior": "step",
                "fixture_ids": ["normalize_result_ok"],
                "negative_fixture_ids": ["normalize_result_bad"],
            }
        },
        manifest_path=None,
    )

    binding = bindings["normalize_result"]

    assert binding.output_type_name == "ImplementationSummary"
    assert binding.stable_command == ("python", "scripts/normalize_result.py")








































@pytest.mark.parametrize(
    "payload",
    [
        {
            "prompts.implementation.execute": {
                "asset_file": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md",
                "input_file": "prompts/workspace/implementation/execute.md",
            }
        },
        {
            "prompts.implementation.execute": {
                "source_kind": "input_file",
                "path": "prompts/workspace/implementation/execute.md",
            }
        },
        {"prompts.implementation.execute": {"unknown": "value"}},
        {"prompts.implementation.execute": {"asset_file": 5}},
    ],
)
def test_prompt_extern_object_shape_invalid_diagnostic(tmp_path: Path, payload: dict[str, object]) -> None:
    manifest_path = tmp_path / "prompts.invalid-object.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_module()._load_prompt_extern_mapping(manifest_path)

    assert excinfo.value.diagnostics[0].code == "workflow_lisp_manifest_invalid"
    assert "prompt externs manifest entries" in excinfo.value.diagnostics[0].message







































































































































































































































































































































@dataclass(frozen=True)
class _HistoricalSurfaceGraph:
    surface: SurfaceWorkflow
    provenance: WorkflowProvenance
    imports: dict


def _historical_surface_template(*, target="2.14"):
    """Literal historical reader input, with no compiler or executable graph."""
    provenance = WorkflowProvenance(Path("historical/root.orc"), Path("."))
    surface = SurfaceWorkflow(target, "historical::root", (), provenance)
    return _HistoricalSurfaceGraph(surface, provenance, {})


def _historical_call_wire_graph():
    wire = _persisted_wire_graph(
        _persisted_wire_step(kind="call", call_alias="selector"),
        calls={"selector": "imported_selector::selector-run"},
    )
    root = wire["nodes"].pop("wire::root")
    root["workflow_name"] = "neurips/entry::orchestrate"
    wire["entry_workflow"] = root["workflow_name"]
    wire["nodes"][root["workflow_name"]] = root
    wire["nodes"]["imported_selector::selector-run"]["steps"] = [_persisted_wire_step()]
    return wire

def test_json_data_keeps_plain_return_and_field_dataclasses_legacy_compatible() -> None:
    span = SourceSpan(
        start=SourcePosition(path="plain.orc", line=1, column=1, offset=0),
        end=SourcePosition(path="plain.orc", line=1, column=2, offset=1),
    )
    function_def = FunctionDef(
        name="approved",
        params=(),
        return_type_name="Bool",
        body=True,
        span=span,
        form_path=("workflow-lisp", "defun", "approved"),
    )
    field = RecordField(name="approved", type_name="Bool", span=span)

    function_payload = _build_module()._json_data(function_def)
    field_payload = _build_module()._json_data(field)

    assert function_payload["return_type_name"] == "Bool"
    assert "return_spec" not in function_payload
    assert field_payload == {
        "name": "approved",
        "type_name": "Bool",
        "span": _build_module()._json_data(span),
    }


from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.functions import FunctionDef
from orchestrator.workflow_lisp.definitions import RecordField
