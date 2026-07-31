from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.providers.types import (
    InputMode,
    PreparedProviderPolicy,
    ProviderInvocation,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import ExecutableNodeKind, ProviderStepConfig
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.effects import UsesProviderEffect
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import LiteralExpr, NameExpr, ProviderResultExpr
from orchestrator.workflow_lisp.prompts import PromptApplicationExpr, PromptSlotKind
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
from tests.workflow_bundle_helpers import bundle_context_dict


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_ROOT = ROOT / "workflows/library"
SOURCE = LIBRARY_ROOT / "control/direct_task.orc"
ENTRY = "control/direct_task::direct-task"


def _compile_direct_task(workspace: Path):
    result = compile_stage3_entrypoint(
        SOURCE,
        source_roots=(LIBRARY_ROOT,),
        entry_workflow=ENTRY,
        provider_externs={"providers.direct": "test-direct-provider"},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=workspace,
        lowering_route="wcc_m4",
    )
    return result.validated_bundles_by_name[ENTRY]


def _direct_task_manager(workspace: Path, bundle, *, run_id: str) -> StateManager:
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    public_inputs = {
        name: contract
        for name, contract in runtime_inputs.items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        public_inputs,
        {
            "task": "complete the direct task",
            "model": "test-model",
            "effort": "low",
        },
        workspace,
    )
    manager = StateManager(workspace=workspace, run_id=run_id)
    manager.initialize(
        SOURCE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return manager


def _direct_provider_patches(
    workspace: Path,
    captured: dict[str, list[object]],
    *,
    exit_code: int,
):
    def prepare_invocation(_self, provider_name, *_args, **kwargs):
        prompt = kwargs.get("prompt_content", "")
        env = kwargs.get("env") or {}
        provider_call_policy = dict(kwargs.get("provider_call_policy") or {})
        captured["preparations"].append(
            {
                "provider": provider_name,
                "provider_call_policy": provider_call_policy,
                "output_bundle_path": env.get(
                    "ORCHESTRATOR_OUTPUT_BUNDLE_PATH"
                ),
            }
        )
        return (
            ProviderInvocation(
                command=["deterministic-direct-provider"],
                input_mode=InputMode.STDIN,
                prompt=prompt,
                env=env,
                prepared_prompt=prompt,
                prepared_provider_policy=PreparedProviderPolicy(
                    provider_name=provider_name,
                    model=provider_call_policy.get("model"),
                    effort=provider_call_policy.get("effort"),
                    timeout_sec=kwargs.get("timeout_sec"),
                    input_mode="stdin",
                ),
            ),
            None,
        )

    def execute_provider(_self, invocation, **_kwargs):
        captured["executions"].append(invocation)
        if exit_code == 0:
            output_path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
            if not output_path.is_absolute():
                output_path = workspace / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(True) + "\n", encoding="utf-8")
        return ProviderExecutionResult(
            exit_code=exit_code,
            stdout=b"provider stdout is observability only",
            stderr=b"retryable provider failure" if exit_code else b"",
            duration_ms=1,
        )

    return (
        patch.object(ProviderExecutor, "prepare_invocation", prepare_invocation),
        patch.object(ProviderExecutor, "execute", execute_provider),
    )


def _assert_composed_prompt_metadata(bundle) -> None:
    [provider_node] = [
        node
        for node in bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    ]
    config = provider_node.execution_config
    assert isinstance(config, ProviderStepConfig)
    assert config.provider_call_policy["delivery"] == "composed"
    assert config.inject_output_contract is True

    fragment = config.compiler_prompt_fragment_contract
    assert fragment is not None
    assert [
        (slot.name, slot.kind, slot.renderer_id)
        for slot in fragment.rendered_slots
    ] == [("task", "text", "raw-utf8-string")]
    assert config.compiled_prompt_fragment_identity == (
        fragment.compiled_prompt_fragment_identity
    )

    binding_plan = config.compiler_prompt_attempt_binding_plan
    assert binding_plan is not None
    assert [
        (row.slot_name, row.slot_kind, row.output_role, row.delivery)
        for row in binding_plan.rows
    ] == [("task", "text", "none", "template")]

    output_bundle = config.common.output_bundle
    assert output_bundle is not None
    [result_field] = output_bundle["fields"]
    assert {
        key: result_field[key]
        for key in ("name", "json_pointer", "type")
    } == {"name": "__result__", "json_pointer": "", "type": "bool"}
    assert result_field["source_map_subject"]["subject_kind"] == (
        "output_bundle_field"
    )


def test_direct_task_is_one_composed_provider_boundary() -> None:
    assert SOURCE.is_file(), f"canonical direct control is absent: {SOURCE}"

    result = compile_stage3_entrypoint(
        SOURCE,
        source_roots=(LIBRARY_ROOT,),
        entry_workflow=ENTRY,
        provider_externs={"providers.direct": "test-direct-provider"},
        prompt_externs={},
        command_boundaries={},
        validate_shared=True,
        workspace_root=ROOT,
        lowering_route="wcc_m4",
    )

    compiled = result.entry_result
    assert compiled.module.target_dsl_version == "2.23"
    assert compiled.module.module_name == "control/direct_task"
    assert compiled.module.exports == ("direct-task",)
    assert compiled.module.definitions == ()
    assert set(result.validated_bundles_by_name) == {ENTRY}
    assert set(compiled.extern_environment.bindings_by_name) == {"providers.direct"}

    assert len(compiled.typed_workflows) == 1
    workflow = compiled.typed_workflows[0]
    assert workflow.definition.name == ENTRY
    assert workflow.signature.params == (
        ("task", PrimitiveTypeRef(name="String")),
        ("model", PrimitiveTypeRef(name="String")),
        ("effort", PrimitiveTypeRef(name="String")),
    )
    assert workflow.signature.return_type_ref == PrimitiveTypeRef(name="Bool")
    assert workflow.typed_body.type_ref == PrimitiveTypeRef(name="Bool")
    assert workflow.effect_summary.direct_effects == frozenset(
        {UsesProviderEffect(subject=("providers", "direct"))}
    )
    assert workflow.effect_summary.transitive_effects == (
        workflow.effect_summary.direct_effects
    )
    assert workflow.effect_summary.procedure_edges == frozenset()

    expression = workflow.typed_body.expr
    assert isinstance(expression, ProviderResultExpr)
    assert [type(node) for node in walk_expr(expression)].count(ProviderResultExpr) == 1
    assert isinstance(expression.provider, NameExpr)
    assert expression.provider.name == "providers.direct"
    assert expression.inputs == ()
    assert isinstance(expression.model, NameExpr)
    assert expression.model.name == "model"
    assert isinstance(expression.effort, NameExpr)
    assert expression.effort.name == "effort"
    assert expression.timeout_sec is None
    assert isinstance(expression.delivery, LiteralExpr)
    assert expression.delivery.value == "composed"
    assert expression.materialization_attempts is None
    assert expression.prompt_dependencies is None
    assert expression.returns_type_name == "Bool"

    prompt = expression.prompt
    assert isinstance(prompt, PromptApplicationExpr)
    assert {
        resolved.qualified_name
        for resolved in compiled.prompt_catalog.definitions_by_name.values()
    } == {"control/direct_task::direct-task-prompt"}
    assert prompt.prompt.declaration.return_type_name == "Bool"
    assert prompt.prompt.declaration.return_spec.guidance is None
    assert tuple(
        (slot.declaration.name, slot.declaration.kind)
        for slot in prompt.prompt.slots
    ) == (("task", PromptSlotKind.TEXT),)
    template = prompt.prompt.declaration.template
    assert template.placeholder_names == ("task",)
    static_template_text = template.text
    for placeholder_name in template.placeholder_names:
        static_template_text = static_template_text.replace(
            "{" + placeholder_name + "}", ""
        )
    assert not static_template_text.strip()
    assert tuple(fill.name for fill in prompt.fills) == ("task",)
    assert isinstance(prompt.fills[0].value_expr, NameExpr)
    assert prompt.fills[0].value_expr.name == "task"

    bundle = result.validated_bundles_by_name[ENTRY]
    assert bundle.ir.version == "2.23"
    assert len(bundle.ir.nodes) == 1
    node = next(iter(bundle.ir.nodes.values()))
    assert isinstance(node.execution_config, ProviderStepConfig)
    config = node.execution_config
    assert config.provider == "test-direct-provider"
    assert dict(config.provider_call_policy or {}) == {
        "model": "${inputs.model}",
        "effort": "${inputs.effort}",
        "delivery": "composed",
    }
    assert config.common.timeout_sec is None
    assert config.common.retries is None
    assert config.common.publishes == ()
    assert config.common.expected_outputs == ()
    assert bundle.ir.artifacts == {}
    assert bundle.ir.private_artifacts == {}


def test_direct_task_executes_once_and_committed_boundary_resume_reuses_result(
    tmp_path: Path,
) -> None:
    class CommittedBoundaryInterruption(BaseException):
        pass

    bundle = _compile_direct_task(tmp_path)
    _assert_composed_prompt_metadata(bundle)
    [provider_node] = [
        node
        for node in bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    ]
    run_id = "direct-task-success"
    manager = _direct_task_manager(tmp_path, bundle, run_id=run_id)
    captured: dict[str, list[object]] = {
        "preparations": [],
        "executions": [],
    }
    prepare, execute = _direct_provider_patches(
        tmp_path,
        captured,
        exit_code=0,
    )
    original_emit = (
        WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit
    )

    def interrupt_after_committed_provider(
        executor,
        state,
        step_name,
        step,
        finalized,
    ):
        original_emit(executor, state, step_name, step, finalized)
        if (
            finalized.get("step_id") == provider_node.step_id
            and finalized.get("status") == "completed"
            and finalized.get("artifacts", {}).get("__result__") is True
        ):
            raise CommittedBoundaryInterruption

    with prepare, execute, patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_after_committed_provider,
    ):
        with pytest.raises(CommittedBoundaryInterruption):
            WorkflowExecutor(
                bundle,
                tmp_path,
                manager,
                max_retries=0,
                retry_delay_ms=0,
            ).execute(on_error="stop")

    assert len(captured["preparations"]) == 1
    assert len(captured["executions"]) == 1
    [preparation] = captured["preparations"]
    assert preparation["provider"] == "test-direct-provider"
    assert preparation["provider_call_policy"] == {
        "model": "${inputs.model}",
        "effort": "${inputs.effort}",
    }
    assert isinstance(preparation["output_bundle_path"], str)

    committed = json.loads(manager.state_file.read_text(encoding="utf-8"))
    assert committed["status"] == "running"
    assert committed.get("current_step") is None
    assert committed["workflow_outputs"] == {}
    committed_provider_step = next(
        step
        for step in committed["steps"].values()
        if step.get("step_id") == provider_node.step_id
    )
    assert committed_provider_step["status"] == "completed"
    assert committed_provider_step["artifacts"] == {"__result__": True}
    assert committed_provider_step["visit_count"] == 1
    committed_binding = deepcopy(
        committed_provider_step["debug"]["prompt_attempt_result_binding"]
    )
    committed_step = deepcopy(committed_provider_step)
    committed_allocations = deepcopy(
        committed["provider_attempt_allocations"]
    )
    [allocation_key] = committed_allocations
    [allocation] = committed_allocations.values()
    assert allocation["last_allocated_ordinal"] == 1
    assert committed_binding["scope_sha256"] == allocation_key
    assert committed_binding["attempt_ordinal"] == 1
    assert committed_binding["record_kind"] == "prompt_snapshot"

    resume_manager = StateManager(workspace=tmp_path, run_id=run_id)
    resume_manager.load()
    with patch.object(
        StateManager,
        "allocate_provider_attempt",
        side_effect=AssertionError(
            "committed provider boundary must not allocate another attempt"
        ),
    ), patch(
        "orchestrator.workflow.executor.snapshot_content_dependencies",
        side_effect=AssertionError(
            "committed provider boundary must not snapshot dependencies"
        ),
    ), patch.object(
        ProviderExecutor,
        "prepare_invocation",
        side_effect=AssertionError(
            "committed provider boundary must not prepare another invocation"
        ),
    ), patch.object(
        ProviderExecutor,
        "execute",
        side_effect=AssertionError(
            "committed provider boundary must not execute another invocation"
        ),
    ):
        resumed = WorkflowExecutor(
            bundle,
            tmp_path,
            resume_manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": True}
    resumed_provider_step = next(
        step
        for step in resumed["steps"].values()
        if step.get("step_id") == provider_node.step_id
    )
    assert resumed_provider_step["visit_count"] == 1
    assert resumed_provider_step == committed_step
    assert resumed_provider_step["debug"][
        "prompt_attempt_result_binding"
    ] == committed_binding
    assert resumed["provider_attempt_allocations"] == committed_allocations
    assert len(captured["preparations"]) == 1
    assert len(captured["executions"]) == 1
    persisted_resumed = json.loads(
        resume_manager.state_file.read_text(encoding="utf-8")
    )
    assert persisted_resumed["workflow_outputs"] == {"__result__": True}
    assert persisted_resumed["steps"][
        next(
            name
            for name, step in persisted_resumed["steps"].items()
            if step.get("step_id") == provider_node.step_id
        )
    ] == committed_step
    assert (
        persisted_resumed["provider_attempt_allocations"]
        == committed_allocations
    )


def test_direct_task_retryable_failure_is_not_retried_with_zero_retries(
    tmp_path: Path,
) -> None:
    bundle = _compile_direct_task(tmp_path)
    manager = _direct_task_manager(
        tmp_path,
        bundle,
        run_id="direct-task-zero-retry-failure",
    )
    captured: dict[str, list[object]] = {
        "preparations": [],
        "executions": [],
    }
    prepare, execute = _direct_provider_patches(
        tmp_path,
        captured,
        exit_code=1,
    )

    with prepare, execute:
        failed = WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert failed["status"] == "failed"
    assert len(captured["preparations"]) == 1
    assert len(captured["executions"]) == 1
    persisted = json.loads(manager.state_file.read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
    [allocation] = persisted["provider_attempt_allocations"].values()
    assert allocation["last_allocated_ordinal"] == 1
