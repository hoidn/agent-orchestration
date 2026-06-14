from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.surface_ast import SurfaceStepKind
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.providers.executor import ProviderExecutor


REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
TYPED_PROMPT_INPUT_FIXTURE = VALID_FIXTURES / "typed_prompt_input_phase.orc"


def _typed_prompt_inputs_module():
    return importlib.import_module("orchestrator.workflow_lisp.typed_prompt_inputs")


def _compile_typed_prompt_input_bundle(tmp_path: Path):
    result = compile_stage3_module(
        TYPED_PROMPT_INPUT_FIXTURE,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return next(
        bundle
        for name, bundle in result.validated_bundles.items()
        if name.endswith("run-typed-prompt-phase-demo")
    )


def _initialize_typed_prompt_input_workspace(workspace: Path) -> None:
    (workspace / "docs" / "design").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "plans").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "design" / "workflow_lisp_frontend_specification.md").write_text(
        "# design\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "plans" / "typed_prompt_input_plan.md").write_text(
        "# plan\n",
        encoding="utf-8",
    )


def _typed_prompt_input_bound_inputs(bundle) -> dict[str, str]:
    bound_inputs: dict[str, str] = {
        "inputs__prompt_context__design": "docs/design/workflow_lisp_frontend_specification.md",
        "inputs__prompt_context__plan": "docs/plans/typed_prompt_input_plan.md",
        "inputs__prompt_context__focus": "prefer typed values over producer-owned prompt files",
    }
    for input_name, contract in bundle.surface.inputs.items():
        definition = getattr(contract, "definition", {})
        default_value = definition.get("default") if hasattr(definition, "get") else None
        if isinstance(default_value, str):
            bound_inputs.setdefault(input_name, default_value)
        if "execution_report_target" in input_name:
            bound_inputs[input_name] = "artifacts/work/execution_report.md"
        if "progress_report_target" in input_name:
            bound_inputs[input_name] = "artifacts/work/progress_report.md"
    return bound_inputs


def _provider_step(bundle):
    return next(step for step in bundle.surface.steps if step.kind is SurfaceStepKind.PROVIDER)


def test_normalize_typed_prompt_input_entry_canonicalizes_metadata() -> None:
    module = _typed_prompt_inputs_module()
    normalized = module.normalize_typed_prompt_input_entry(
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
    )

    assert normalized["binding_name"] == "prompt_context"
    assert normalized["renderer"]["renderer_id"] == "canonical-json"
    assert normalized["source_map_origin_key"].startswith("typed_prompt_input_phase::")


def test_render_typed_prompt_inputs_serializes_runtime_evidence() -> None:
    module = _typed_prompt_inputs_module()
    prompt_block, evidence = module.render_typed_prompt_inputs(
        [
            module.normalize_typed_prompt_input_entry(
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
            )
        ],
        resolved_typed_values={
            "prompt_context": {
                "design": "docs/design/workflow_lisp_frontend_specification.md",
                "plan": "docs/plans/typed_prompt_input_plan.md",
                "focus": "prefer typed values",
            }
        },
        workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
        step_id="root.run-typed-prompt-phase-demo__attempt",
    )

    assert '"focus":"prefer typed values"' in prompt_block
    assert evidence
    assert evidence[0]["schema_version"] == "workflow_lisp_typed_prompt_input_evidence.v1"
    assert evidence[0]["binding_name"] == "prompt_context"


def test_normalize_typed_prompt_input_entry_rejects_missing_lineage() -> None:
    module = _typed_prompt_inputs_module()
    with pytest.raises(ValueError, match="c0_row_id|u0_row_id|source_map_origin_key"):
        module.normalize_typed_prompt_input_entry(
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
                "injection_order": 0,
            }
        )


def test_render_typed_prompt_inputs_rejects_unknown_renderer() -> None:
    module = _typed_prompt_inputs_module()
    with pytest.raises(ValueError, match="typed_prompt_input_renderer_unknown"):
        module.render_typed_prompt_inputs(
            [
                {
                    "schema_version": "workflow_lisp_typed_prompt_input.v1",
                    "binding_name": "prompt_context",
                    "renderer": {
                        "renderer_id": "unknown-renderer",
                        "renderer_version": 99,
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
            resolved_typed_values={"prompt_context": {"focus": "prefer typed values"}},
            workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
            step_id="root.run-typed-prompt-phase-demo__attempt",
        )


def test_render_typed_prompt_inputs_rejects_shape_mismatch() -> None:
    module = _typed_prompt_inputs_module()
    with pytest.raises(ValueError, match="typed_prompt_input_renderer_shape_mismatch"):
        module.render_typed_prompt_inputs(
            [
                {
                    "schema_version": "workflow_lisp_typed_prompt_input.v1",
                    "binding_name": "prompt_context",
                    "renderer": {
                        "renderer_id": "posix-path-line",
                        "renderer_version": 1,
                        "accepted_shape": "path_value",
                    },
                    "value_source": {"kind": "typed_binding_ref", "ref": "inputs.prompt_context"},
                    "value_type_name": "PromptContext",
                    "source_map_origin_key": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
                    "u0_row_id": "u0.fixture.prompt_context",
                    "c0_row_id": "c0.fixture.prompt_context",
                    "injection_order": 0,
                }
            ],
            resolved_typed_values={"prompt_context": {"focus": "prefer typed values"}},
            workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
            step_id="root.run-typed-prompt-phase-demo__attempt",
        )


def test_render_typed_prompt_inputs_rejects_non_json_like_value() -> None:
    module = _typed_prompt_inputs_module()
    with pytest.raises(ValueError, match="typed_prompt_input_value_unavailable|typed_prompt_input_renderer_shape_mismatch"):
        module.render_typed_prompt_inputs(
            [
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
            resolved_typed_values={"prompt_context": {"bad": {1, 2, 3}}},
            workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
            step_id="root.run-typed-prompt-phase-demo__attempt",
        )


def test_runtime_smoke_renders_typed_prompt_inputs_without_prompt_materialization(
    tmp_path: Path,
) -> None:
    _initialize_typed_prompt_input_workspace(tmp_path)
    bundle = _compile_typed_prompt_input_bundle(tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="typed-prompt-input-runtime")
    state_manager.initialize(
        TYPED_PROMPT_INPUT_FIXTURE.as_posix(),
        bound_inputs=_typed_prompt_input_bound_inputs(bundle),
    )
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
    captured: dict[str, object] = {"prompt": "", "output_bundle_path": ""}

    def _prepare_invocation(_self, *args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content", "")
        env = dict(kwargs.get("env") or {})
        captured["output_bundle_path"] = env.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "")
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"], env=env), None

    def _execute(_self, invocation, **_kwargs):
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "artifacts" / "work" / "execution_report.md").write_text(
            "# execution report\n",
            encoding="utf-8",
        )
        bundle_path.write_text(
            json.dumps(
                {
                    "variant": "COMPLETED",
                    "implementation_state": "COMPLETED",
                    "execution_report_path": "artifacts/work/execution_report.md",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute(on_error="stop")

    provider_step = _provider_step(bundle)
    assert state["steps"][provider_step.name]["exit_code"] == 0
    assert getattr(provider_step, "typed_prompt_inputs")
    assert not any(
        step.kind is SurfaceStepKind.MATERIALIZE_ARTIFACTS and "prompt_inputs" in step.step_id
        for step in bundle.surface.steps
    )
    evidence_root = (
        tmp_path
        / ".orchestrate"
        / "runs"
        / "typed-prompt-input-runtime"
        / "workflow_lisp"
        / "typed_prompt_inputs"
    )
    assert evidence_root.exists()
    assert "prefer typed values over producer-owned prompt files" in str(captured["prompt"])


def test_typed_prompt_input_evidence_does_not_replace_provider_output_authority(
    tmp_path: Path,
) -> None:
    _initialize_typed_prompt_input_workspace(tmp_path)
    bundle = _compile_typed_prompt_input_bundle(tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="typed-prompt-input-authority")
    state_manager.initialize(
        TYPED_PROMPT_INPUT_FIXTURE.as_posix(),
        bound_inputs=_typed_prompt_input_bound_inputs(bundle),
    )
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", ""), env=dict(kwargs.get("env") or {})), None

    def _execute(_self, invocation, **_kwargs):
        wrong_bundle = tmp_path / "artifacts" / "work" / "wrong-path.json"
        wrong_bundle.parent.mkdir(parents=True, exist_ok=True)
        wrong_bundle.write_text(
            json.dumps(
                {
                    "variant": "COMPLETED",
                    "implementation_state": "COMPLETED",
                    "execution_report_path": "artifacts/work/execution_report.md",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        evidence_root = (
            tmp_path
            / ".orchestrate"
            / "runs"
            / "typed-prompt-input-authority"
            / "workflow_lisp"
            / "typed_prompt_inputs"
        )
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "attempt.json").write_text(
            json.dumps({"schema_version": "workflow_lisp_typed_prompt_input_evidence.v1"}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute(on_error="stop")

    provider_step = _provider_step(bundle)
    assert getattr(provider_step, "typed_prompt_inputs")
    assert state["steps"][provider_step.name]["status"] == "failed"
    assert "evidence" not in json.dumps(state["steps"][provider_step.name])
