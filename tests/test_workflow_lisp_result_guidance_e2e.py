"""End-to-end acceptance for native v2.15 typed result guidance."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.contracts.prompt_contract import render_variant_output_contract_block
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.core_ast import workflow_core_ast_to_json
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import _thaw, bundle_context_dict
from tests.test_workflow_lisp_native_returns_e2e import (
    _compile_guidance_runtime_bundle,
    _execute_guidance_runtime_case,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "native_bool_return_guidance.orc"
)


def _write_bool_command(workspace: Path, name: str) -> ExternalToolBinding:
    scripts = workspace / "scripts"
    scripts.mkdir(exist_ok=True)
    script = scripts / f"{name}.py"
    script.write_text(
        "import os, pathlib\n"
        'path = pathlib.Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])\n'
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        'path.write_text("true\\n", encoding="utf-8")\n'
        'print("stdout is observability only")\n',
        encoding="utf-8",
    )
    return ExternalToolBinding(name=name, stable_command=("python", f"scripts/{name}.py"))


def _contract_document(prompt: str) -> dict:
    lines = prompt.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("- path:"))
    document = yaml.safe_load("\n".join(lines[start:]))
    assert isinstance(document, list) and isinstance(document[0], dict)
    return document[0]


_GUIDANCE_KEYS = (
    "description",
    "format_hint",
    "example",
    "guidance_context",
    "guidance_by_variant",
)


def _guidance_payload(spec: Mapping[str, object]) -> dict[str, object]:
    return {key: _thaw(spec[key]) for key in _GUIDANCE_KEYS if key in spec}


def _count_mapping_key(value: object, key: str) -> int:
    if isinstance(value, Mapping):
        return int(key in value) + sum(
            _count_mapping_key(item, key) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return sum(_count_mapping_key(item, key) for item in value)
    return 0


def _variant_guidance_projection(contract: Mapping[str, object]) -> dict[str, object]:
    guidance = contract.get("guidance")
    shared_fields = contract.get("shared_fields", ())
    variants = contract.get("variants", {})
    return {
        "guidance": _guidance_payload(guidance) if isinstance(guidance, Mapping) else {},
        "shared_fields": {
            field["name"]: _guidance_payload(field)
            for field in shared_fields
            if isinstance(field, Mapping)
        },
        "variants": {
            variant_name: {
                field["name"]: _guidance_payload(field)
                for field in variant_spec.get("fields", ())
                if isinstance(field, Mapping)
            }
            for variant_name, variant_spec in variants.items()
            if isinstance(variant_spec, Mapping)
        },
    }


def test_direct_bool_provider_guidance_executes_without_wrapper_or_overall_prompt_leak(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / FIXTURE.name
    source = FIXTURE.read_text(encoding="utf-8")
    module_path.write_text(source, encoding="utf-8")
    assert "__result__" not in source

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "review.md").write_text("Review the change.\n", encoding="utf-8")

    compile_result = compile_stage3_entrypoint(
        module_path,
        source_roots=(tmp_path,),
        provider_externs={"providers.review": "fake-review-provider"},
        prompt_externs={"prompts.review": {"input_file": "prompts/review.md"}},
        command_boundaries={
            "record_approved": _write_bool_command(tmp_path, "record_approved"),
            "record_revise": _write_bool_command(tmp_path, "record_revise"),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = next(
        candidate
        for name, candidate in compile_result.validated_bundles_by_name.items()
        if name.endswith("::decide") or name == "decide"
    )

    overall = dict(bundle.surface.result_guidance)
    executable = workflow_executable_ir_to_json(bundle.ir)
    provider_occurrence = next(
        node for node in executable["nodes"].values() if node["kind"] == "provider"
    )
    occurrence_bundle = provider_occurrence["execution_config"]["common"]["output_bundle"]
    occurrence_field = occurrence_bundle["fields"][0]

    assert overall
    assert workflow_core_ast_to_json(bundle.core_workflow_ast)["result_guidance"] == overall
    assert workflow_semantic_ir_to_json(bundle.semantic_ir)["workflows"][bundle.surface.name][
        "result_guidance"
    ] == overall
    assert executable["result_guidance"] == overall
    assert _count_mapping_key(executable, "result_guidance") == 1

    state = StateManager(workspace=tmp_path, run_id="guided-bool")
    bound_inputs = bind_workflow_inputs(
        {
            name: contract
            for name, contract in workflow_runtime_input_contracts(bundle).items()
            if not name.startswith("__write_root__")
        },
        {},
        tmp_path,
    )
    state.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    captured: dict[str, str] = {}

    def _prepare(_self, *args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content", "")
        return SimpleNamespace(
            input_mode="stdin",
            prompt=captured["prompt"],
            env=kwargs.get("env") or {},
        ), None

    def _execute(_self, invocation, **_kwargs):
        path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("true\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"stdout is observability only",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        result = WorkflowExecutor(bundle, tmp_path, state, retry_delay_ms=0).execute(
            on_error="stop"
        )

    contract = _contract_document(captured["prompt"])
    assert contract["type"] == occurrence_field["type"]
    assert _guidance_payload(contract) == _guidance_payload(occurrence_field)
    assert _guidance_payload(contract) != overall
    assert "result_guidance" not in contract
    assert "guidance" not in contract
    assert "result_guidance" not in occurrence_bundle
    assert "guidance" not in occurrence_bundle
    assert result["status"] == "completed"
    assert result["workflow_outputs"] == {"__result__": True}
    provider_step = result["steps"]["native_bool_return_guidance::decide__approved"]
    assert provider_step["artifacts"] == {"__result__": True}
    assert provider_step["output"] != json.dumps(True)

    # The same completed contract is now public to ordinary loader entrypoints.
    assert "2.15" in WorkflowLoader.SUPPORTED_VERSIONS


def test_nested_union_guidance_renders_and_selected_variant_keeps_source_lineage(
    tmp_path: Path,
) -> None:
    module_path, bundle, _ = _compile_guidance_runtime_bundle(
        tmp_path,
        guided=True,
        lowering_route="wcc_m4",
    )
    variant_output = _thaw(next(
        node.execution_config.common.variant_output
        for node in bundle.ir.nodes.values()
        if node.execution_config is not None
        and node.execution_config.common.variant_output
    ))
    rendered = render_variant_output_contract_block(variant_output)
    prompt_contract = _contract_document(rendered)

    assert _variant_guidance_projection(prompt_contract) == _variant_guidance_projection(
        variant_output
    )

    frozen_approved = next(
        field for field in variant_output["shared_fields"] if field["name"] == "approved"
    )
    assert tuple(frozen_approved["source_map_subjects_by_variant"]) == (
        "APPROVE",
        "REVISE",
    )
    assert frozen_approved["source_map_subjects_by_variant"]["APPROVE"] == {
        "subject_kind": "variant_output_field",
        "subject_name": (
            "guidance_runtime_neutrality::orchestrate__decision::"
            "Decision::APPROVE::approved"
        ),
        "workflow_name": "guidance_runtime_neutrality::orchestrate",
    }
    frozen_score = next(
        field
        for field in variant_output["variants"]["APPROVE"]["fields"]
        if field["name"].endswith("score")
    )
    assert frozen_score["source_map_subject"]["subject_name"].endswith(
        "Decision::APPROVE::meta__score"
    )

    first, resumed = _execute_guidance_runtime_case(
        tmp_path,
        bundle,
        module_path,
        run_id="nested-union-guidance",
    )
    assert first["status"] == resumed["status"] == "completed"
    decision = next(
        step for name, step in resumed["steps"].items() if name.endswith("__decision")
    )
    assert decision["artifacts"] == {
        "variant": "APPROVE",
        "approved": True,
        "meta__score": 0.9,
    }
