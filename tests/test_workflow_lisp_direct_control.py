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
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    compile_stage3_module,
)
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
ORDINARY_SOURCE = (
    ROOT
    / "tests/fixtures/workflow_lisp/phased_contract_delivery/composed.orc"
)


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


def _deterministic_provider_patches(
    workspace: Path,
    captured: dict[str, list[object]],
    *,
    exit_code: int,
    output_bundle_value: object,
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
            output_path.write_text(
                json.dumps(output_bundle_value, sort_keys=True) + "\n",
                encoding="utf-8",
            )
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


def _provider_boundary_accounting_structure(bundle, state, run_root: Path):
    def mask_named_values(value, *, field_kind: str):
        assert isinstance(value, dict)
        return {
            f"<{field_kind}:{index}>": "<masked-value>"
            for index, _name in enumerate(sorted(value))
        }

    def add_structural_paths(value, path, paths) -> None:
        if isinstance(value, dict):
            paths.add((*path, "<mapping>"))
            for key, item in value.items():
                add_structural_paths(item, (*path, str(key)), paths)
            return
        if isinstance(value, (list, tuple)):
            paths.add((*path, "<sequence>"))
            for index, item in enumerate(value):
                add_structural_paths(item, (*path, f"[{index}]"), paths)
            return
        paths.add((*path, "<value>"))

    [provider_node] = [
        node
        for node in bundle.ir.nodes.values()
        if node.kind is ExecutableNodeKind.PROVIDER
    ]
    config = provider_node.execution_config
    assert isinstance(config, ProviderStepConfig)
    [(provider_step_name, provider_step)] = [
        (step_name, step)
        for step_name, step in state["steps"].items()
        if step.get("step_id") == provider_node.step_id
    ]

    allocations = state["provider_attempt_allocations"]
    [scope_sha256] = allocations
    allocation = allocations[scope_sha256]
    scope = allocation["scope"]
    assert scope["runtime_step_id"] == provider_node.step_id
    assert scope["enclosing_step"]["step_id"] == provider_node.step_id

    debug = provider_step["debug"]
    binding = debug["prompt_attempt_result_binding"]
    assert binding["scope_sha256"] == scope_sha256
    evidence = json.loads(
        (run_root / binding["evidence_relative_path"]).read_text(
            encoding="utf-8"
        )
    )
    attempt = evidence["attempt"]
    attempt_scope = attempt["scope"]
    assert attempt["scope_sha256"] == scope_sha256
    assert attempt["ordinal"] == binding["attempt_ordinal"]
    assert attempt_scope == scope

    prompt_attempt_identity = evidence["prompt_attempt_identity"]
    identity_roles = prompt_attempt_identity["roles"]
    provider_policy = identity_roles["provider_policy"]
    resolved_provider_policy = provider_policy["payload"]
    outcome = provider_step["outcome"]
    output_bundle = config.common.output_bundle
    assert output_bundle is not None
    compiled_result_shape = tuple(
        (field["name"], field["json_pointer"], field["type"])
        for field in output_bundle["fields"]
    )
    assert frozenset(provider_step["artifacts"]) == frozenset(
        field_name for field_name, _pointer, _type in compiled_result_shape
    )

    normalized_provider_step = deepcopy(provider_step)
    normalized_provider_step["artifacts"] = mask_named_values(
        provider_step["artifacts"],
        field_kind="artifact-field",
    )

    # The content-addressed allocation map key is omitted from this owner
    # because its sole value is projected recursively, without masking,
    # under the provider-attempt owner below.
    run_accounting = deepcopy(state)
    run_accounting.pop("provider_attempt_allocations")
    run_accounting["bound_inputs"] = {
        "<bound-inputs>": "<masked-value>"
    }
    assert set(run_accounting["steps"]) == {provider_step_name}
    run_accounting["steps"] = {
        "<provider-step>": normalized_provider_step
    }
    assert set(run_accounting["step_visits"]) == {provider_step_name}
    run_accounting["step_visits"] = {
        "<provider-step>": run_accounting["step_visits"][provider_step_name]
    }
    run_accounting["workflow_outputs"] = mask_named_values(
        state["workflow_outputs"],
        field_kind="workflow-output-field",
    )

    runtime_owned_objects = {
        "run": run_accounting,
        "provider_step": normalized_provider_step,
        "provider_attempt_allocation": allocation,
        "prompt_attempt_evidence": evidence,
    }
    normalized_runtime_owned_paths = set()
    for owner, value in runtime_owned_objects.items():
        add_structural_paths(
            value,
            (owner,),
            normalized_runtime_owned_paths,
        )

    unmasked_runtime_owned_paths = set()
    for owner, value in {
        "run": state,
        "provider_step": provider_step,
        "provider_attempt_allocation": allocation,
        "prompt_attempt_evidence": evidence,
    }.items():
        add_structural_paths(
            value,
            (owner,),
            unmasked_runtime_owned_paths,
        )

    cost_accounting_field_names = frozenset(
        {
            "cost",
            "cost_usd",
            "estimated_cost",
            "estimated_cost_usd",
            "provider_cost",
            "provider_cost_usd",
            "total_cost",
            "total_cost_usd",
        }
    )
    token_usage_accounting_field_names = frozenset(
        {
            "usage",
            "usage_details",
            "usage_metadata",
            "token_usage",
            "tokens",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "prompt_tokens",
            "completion_tokens",
            "reasoning_tokens",
            "cached_tokens",
            "cached_input_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        }
    )

    def contains_exact_field(field_names) -> bool:
        return any(
            path_segment in field_names
            for path in unmasked_runtime_owned_paths
            for path_segment in path
        )

    return {
        "normalized_runtime_owned_paths": frozenset(
            normalized_runtime_owned_paths
        ),
        "provider_attempt_allocation": {
            "count": len(allocations),
            "last_allocated_ordinal": allocation["last_allocated_ordinal"],
        },
        "resolved_provider": resolved_provider_policy["provider_name"],
        "duration_ms": provider_step["duration_ms"],
        "compiled_result_shape": compiled_result_shape,
        "persisted_artifact_shape": frozenset(provider_step["artifacts"]),
        "workflow_output_shape": frozenset(state["workflow_outputs"]),
        "design_accounting_absence": {
            "provider_cost": not contains_exact_field(
                cost_accounting_field_names
            ),
            "provider_token_usage": not contains_exact_field(
                token_usage_accounting_field_names
            ),
        },
    }


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
    prepare, execute = _deterministic_provider_patches(
        tmp_path,
        captured,
        exit_code=0,
        output_bundle_value=True,
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
    prepare, execute = _deterministic_provider_patches(
        tmp_path,
        captured,
        exit_code=1,
        output_bundle_value=True,
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


def test_direct_task_matches_ordinary_provider_accounting_structure(
    tmp_path: Path,
) -> None:
    direct_workspace = tmp_path / "direct"
    ordinary_workspace = tmp_path / "ordinary"
    direct_workspace.mkdir()
    ordinary_workspace.mkdir()

    direct_bundle = _compile_direct_task(direct_workspace)
    ordinary_result = compile_stage3_module(
        ORDINARY_SOURCE.relative_to(ROOT),
        entry_workflow="composed-review",
        provider_externs={"providers.review": "test-ordinary-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=ROOT,
        lowering_route="wcc_m4",
    )
    ordinary_bundle = ordinary_result.validated_bundles["composed-review"]

    direct_manager = _direct_task_manager(
        direct_workspace,
        direct_bundle,
        run_id="direct-accounting-parity",
    )
    ordinary_contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(
            ordinary_bundle
        ).items()
        if not name.startswith("__write_root__")
    }
    ordinary_manager = StateManager(
        workspace=ordinary_workspace,
        run_id="ordinary-accounting-parity",
    )
    ordinary_manager.initialize(
        ORDINARY_SOURCE.as_posix(),
        context=bundle_context_dict(ordinary_bundle),
        bound_inputs=bind_workflow_inputs(
            ordinary_contracts,
            {"subject": "complete the ordinary structured review"},
            ordinary_workspace,
        ),
    )

    direct_captured: dict[str, list[object]] = {
        "preparations": [],
        "executions": [],
    }
    direct_prepare, direct_execute = _deterministic_provider_patches(
        direct_workspace,
        direct_captured,
        exit_code=0,
        output_bundle_value=True,
    )
    with direct_prepare, direct_execute:
        direct_completed = WorkflowExecutor(
            direct_bundle,
            direct_workspace,
            direct_manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    ordinary_captured: dict[str, list[object]] = {
        "preparations": [],
        "executions": [],
    }
    ordinary_prepare, ordinary_execute = _deterministic_provider_patches(
        ordinary_workspace,
        ordinary_captured,
        exit_code=0,
        output_bundle_value={"approved": True},
    )
    with ordinary_prepare, ordinary_execute:
        ordinary_completed = WorkflowExecutor(
            ordinary_bundle,
            ordinary_workspace,
            ordinary_manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(on_error="stop")

    assert direct_completed["status"] == "completed"
    assert ordinary_completed["status"] == "completed"
    assert len(direct_captured["preparations"]) == 1
    assert len(direct_captured["executions"]) == 1
    assert len(ordinary_captured["preparations"]) == 1
    assert len(ordinary_captured["executions"]) == 1

    direct_structure = _provider_boundary_accounting_structure(
        direct_bundle,
        json.loads(direct_manager.state_file.read_text(encoding="utf-8")),
        direct_manager.run_root,
    )
    ordinary_structure = _provider_boundary_accounting_structure(
        ordinary_bundle,
        json.loads(
            ordinary_manager.state_file.read_text(encoding="utf-8")
        ),
        ordinary_manager.run_root,
    )

    direct_owned_paths = direct_structure["normalized_runtime_owned_paths"]
    ordinary_owned_paths = ordinary_structure[
        "normalized_runtime_owned_paths"
    ]
    assert direct_owned_paths == ordinary_owned_paths
    required_paths = {
        ("run", "status", "<value>"),
        ("run", "workflow_outputs", "<mapping>"),
        (
            "run",
            "workflow_outputs",
            "<workflow-output-field:0>",
            "<value>",
        ),
        ("run", "artifact_versions", "<mapping>"),
        ("run", "steps", "<provider-step>", "<mapping>"),
        ("provider_step", "status", "<value>"),
        ("provider_step", "duration_ms", "<value>"),
        ("provider_step", "artifacts", "<mapping>"),
        (
            "provider_step",
            "artifacts",
            "<artifact-field:0>",
            "<value>",
        ),
        (
            "provider_step",
            "debug",
            "prompt_attempt_result_binding",
            "evidence_file_sha256",
            "<value>",
        ),
        (
            "provider_attempt_allocation",
            "last_allocated_ordinal",
            "<value>",
        ),
        (
            "provider_attempt_allocation",
            "scope",
            "enclosing_step",
            "visit_count",
            "<value>",
        ),
        (
            "prompt_attempt_evidence",
            "prompt_attempt_identity",
            "roles",
            "runtime_contributions",
            "payload",
            "rows",
            "[0]",
            "bytes",
            "<value>",
        ),
        ("prompt_attempt_evidence", "record_sha256", "<value>"),
    }
    assert required_paths <= direct_owned_paths
    outcome_path = ("provider_step", "outcome")
    for field in ("status", "phase", "class", "retryable"):
        assert (*outcome_path, field, "<value>") in direct_owned_paths
    attempt_path = ("prompt_attempt_evidence", "attempt")
    for field in ("ordinal", "scope_sha256"):
        assert (*attempt_path, field, "<value>") in direct_owned_paths
    policy_payload_path = (
        "prompt_attempt_evidence",
        "prompt_attempt_identity",
        "roles",
        "provider_policy",
        "payload",
    )
    for field in (
        "provider_name",
        "model",
        "effort",
        "input_mode",
        "timeout_sec",
    ):
        assert (*policy_payload_path, field, "<value>") in direct_owned_paths

    for structure in (direct_structure, ordinary_structure):
        assert structure["provider_attempt_allocation"] == {
            "count": 1,
            "last_allocated_ordinal": 1,
        }
        assert isinstance(structure["resolved_provider"], str)
        assert structure["resolved_provider"]
        assert type(structure["duration_ms"]) is int
        assert structure["duration_ms"] >= 0

    assert direct_structure["compiled_result_shape"] == (
        ("__result__", "", "bool"),
    )
    assert ordinary_structure["compiled_result_shape"] == (
        ("approved", "/approved", "bool"),
    )
    assert (
        direct_structure["compiled_result_shape"]
        != ordinary_structure["compiled_result_shape"]
    )
    assert direct_structure["persisted_artifact_shape"] == frozenset(
        {"__result__"}
    )
    assert ordinary_structure["persisted_artifact_shape"] == frozenset(
        {"approved"}
    )
    assert (
        direct_structure["persisted_artifact_shape"]
        != ordinary_structure["persisted_artifact_shape"]
    )
    assert direct_structure["workflow_output_shape"] == frozenset(
        {"__result__"}
    )
    assert ordinary_structure["workflow_output_shape"] == frozenset(
        {"return__approved"}
    )
    assert (
        direct_structure["workflow_output_shape"]
        != ordinary_structure["workflow_output_shape"]
    )

    # The ordinary runtime exposes duration but currently persists no
    # design-listed provider cost or token-usage datum for either arm.
    assert direct_structure["design_accounting_absence"] == {
        "provider_cost": True,
        "provider_token_usage": True,
    }
    assert ordinary_structure["design_accounting_absence"] == {
        "provider_cost": True,
        "provider_token_usage": True,
    }
