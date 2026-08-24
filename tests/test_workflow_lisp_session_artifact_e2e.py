"""End-to-end fresh-session artifact publication through the existing runtime path.

Compiles a target-2.27 `:session-artifact` workflow, runs it against a fake OMP
provider, and proves the existing ``provider_session {mode: fresh,
publish_artifact}`` contract publishes the session id into the declared scalar
String artifact without widening Core/Semantic/Executable IR schemas.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from tests.workflow_bundle_helpers import bundle_context_dict

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/workflow_lisp/session_artifact"


def _write_workspace(workspace: Path) -> Path:
    prompt_dir = workspace / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "session.md").write_text(
        "Return a session summary.\n",
        encoding="utf-8",
    )
    module_path = workspace / "root.orc"
    module_path.write_text(
        (FIXTURE_ROOT / "root.orc").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return module_path


def _provider_patches(workspace: Path, document: str):
    def _prepare_invocation(_self, *args, **kwargs):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=kwargs.get("prompt_content", ""),
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def _execute(_self, invocation, **_kwargs):
        bundle_path = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(document + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session={"session_id": "sess-123"},
        )

    return (
        patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation),
        patch.object(ProviderExecutor, "execute", _execute),
    )


def _compile_and_bind(workspace: Path, module_path: Path, *, run_id: str):
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        provider_externs={"providers.session": "omp"},
        prompt_externs={"prompts.session": {"input_file": "prompts/session.md"}},
        validate_shared=True,
        workspace_root=workspace,
    )
    bundle = next(iter(result.validated_bundles_by_name.values()))
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        name: contract
        for name, contract in runtime_inputs.items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(binding_inputs, {}, workspace)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return bundle, state_manager, result


def test_fresh_session_artifact_publishes_session_id_through_existing_path(
    tmp_path: Path,
) -> None:
    module_path = _write_workspace(tmp_path)
    bundle, state_manager, result = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="session_publish",
    )

    mapping = result.entry_result.lowered_workflows[0].authored_mapping
    assert mapping["artifacts"] == {
        "omp_session": {"kind": "scalar", "type": "string"}
    }
    provider_step = next(
        step
        for step in mapping["steps"]
        if "provider" in step
    )
    assert provider_step["provider_session"] == {
        "mode": "fresh",
        "publish_artifact": "omp_session",
    }

    p1, p2 = _provider_patches(tmp_path, '"ok"')
    with p1, p2:
        outcome = WorkflowExecutor(
            bundle,
            tmp_path,
            state_manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert outcome["status"] == "completed"

    steps = state_manager.state.steps
    provider_states = [
        step for step in steps.values() if "provider_session" in step.get("debug", {})
    ]
    assert len(provider_states) == 1
    published = provider_states[0]
    assert published["artifacts"]["omp_session"] == "sess-123"
    assert (
        published["debug"]["provider_session"]["publication_state"]
        == "published"
    )


def test_session_artifact_does_not_widen_ir_schemas(tmp_path: Path) -> None:
    module_path = _write_workspace(tmp_path)
    bundle, _state_manager, _result = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="session_schema",
    )

    executable_payload = workflow_executable_ir_to_json(bundle.ir)
    semantic_payload = workflow_semantic_ir_to_json(bundle.semantic_ir)

    assert '"session_artifact"' not in json.dumps(executable_payload)
    assert '"session_artifact"' not in json.dumps(semantic_payload)
    # The existing runtime step-kind and provider-session shapes are reused.
    node = next(iter(executable_payload["nodes"].values()))
    assert node["kind"] == "provider"
    assert "provider_session" in json.dumps(executable_payload)
