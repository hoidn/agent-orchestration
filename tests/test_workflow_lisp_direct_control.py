from __future__ import annotations

from pathlib import Path

from orchestrator.workflow.executable_ir import ProviderStepConfig
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.effects import UsesProviderEffect
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import LiteralExpr, NameExpr, ProviderResultExpr
from orchestrator.workflow_lisp.prompts import PromptApplicationExpr, PromptSlotKind
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_ROOT = ROOT / "workflows/library"
SOURCE = LIBRARY_ROOT / "control/direct_task.orc"
ENTRY = "control/direct_task::direct-task"


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
