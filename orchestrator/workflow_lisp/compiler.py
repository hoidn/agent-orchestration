"""Pure Stage 1 compiler pipeline for the workflow Lisp frontend."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle

from .definitions import (
    EnumDef,
    PathDef,
    RecordDef,
    RecordField,
    UnionDef,
    UnionVariant,
    WorkflowLispModule,
    elaborate_definition_module,
)
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EffectSummary, merge_effect_summaries
from .expressions import (
    LetStarExpr,
    MatchExpr,
    ResumeOrStartExpr,
    WithPhaseExpr,
    elaborate_expression,
)
from .lowering import lower_workflow_definitions, validate_lowered_workflows
from .macros import collect_macro_catalog, expand_module_forms
from .procedures import (
    ProcedureCatalog,
    ProcedureDef,
    TypedProcedureDef,
    build_procedure_catalog,
    elaborate_procedure_definitions,
    validate_procedure_effects,
    with_call_graph,
)
from .reader import read_sexpr_file
from .syntax import WorkflowLispSyntaxModule, build_syntax_module, syntax_head_name, syntax_node_datum
from .type_env import PRELUDE_TYPE_NAMES, FrontendTypeEnvironment
from .typecheck import typecheck_expression
from .workflows import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    Stage3CompileResult,
)
from .workflows import (
    build_command_boundary_environment,
    build_extern_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)

def compile_stage3_module(
    path: Path,
    *,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
    validate_shared: bool = True,
    workspace_root: Path | None = None,
) -> Stage3CompileResult:
    """Compile one `.orc` file through the additive Stage 3 pipeline."""

    syntax_module = _expanded_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    workflow_catalog = build_workflow_catalog(module, workflow_defs, type_env)
    procedure_catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    extern_environment = build_extern_environment(
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
    )
    command_boundary_environment = build_command_boundary_environment(command_boundaries)
    typed_procedures, typed_workflows, procedure_catalog = _infer_stage3_effect_summaries(
        procedure_defs,
        workflow_defs=workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
    )
    command_boundary_environment = _augment_resume_command_boundaries(
        command_boundary_environment,
        typed_procedures=typed_procedures,
        typed_workflows=typed_workflows,
    )
    lowered_workflows = lower_workflow_definitions(
        typed_workflows,
        typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog,
        workflow_path=path,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        type_env=type_env,
    )
    validated_bundles: Mapping[str, LoadedWorkflowBundle]
    if validate_shared:
        validated_bundles = validate_lowered_workflows(
            lowered_workflows,
            workspace_root=workspace_root or path.parent,
        )
    else:
        validated_bundles = {}
    return Stage3CompileResult(
        module=module,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        typed_procedures=typed_procedures,
        typed_workflows=typed_workflows,
        lowered_workflows=lowered_workflows,
        validated_bundles=validated_bundles,
    )


def compile_stage1_module(path: Path) -> WorkflowLispModule:
    """Compile one `.orc` file through the Stage 1 frontend pipeline."""

    syntax_module = _expanded_syntax_module(path)
    _validate_stage1_top_level_forms(syntax_module)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _expanded_syntax_module(path: Path) -> WorkflowLispSyntaxModule:
    parse_tree = read_sexpr_file(path)
    syntax_module = build_syntax_module(parse_tree)
    catalog = collect_macro_catalog(syntax_module)
    return expand_module_forms(syntax_module, catalog=catalog)


def _augment_resume_command_boundaries(
    command_boundary_environment,
    typed_procedures,
    typed_workflows,
):
    bindings = dict(command_boundary_environment.bindings_by_name)
    resume_exprs = [workflow.typed_body.expr for workflow in typed_workflows]
    resume_exprs.extend(procedure.typed_body.expr for procedure in typed_procedures)
    if not any(_workflow_contains_resume_or_start(expr) for expr in resume_exprs):
        return command_boundary_environment
    bindings["validate_reusable_phase_state"] = CertifiedAdapterBinding(
        name="validate_reusable_phase_state",
        stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_reusable_phase_state"),
        input_contract={"type": "object"},
        output_type_name="ResumeReuseDecision",
        effects=("resume_state_reuse", "structured_result"),
        path_safety={"kind": "workspace_relpath"},
        source_map_behavior="step",
        fixture_ids=("resume_state_reuse_valid",),
        negative_fixture_ids=("resume_state_pointer_authority_forbidden",),
    )
    for return_type_name in sorted(
        {
            return_type_name
            for expr in resume_exprs
            for return_type_name in _resume_return_type_names(expr)
        }
    ):
        loader_name = f"load_canonical_phase_result__{return_type_name}"
        bindings[loader_name] = CertifiedAdapterBinding(
            name=loader_name,
            stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.load_canonical_phase_result"),
            input_contract={"type": "object"},
            output_type_name=return_type_name,
            effects=("structured_result",),
            path_safety={"kind": "workspace_relpath"},
            source_map_behavior="step",
            fixture_ids=(f"resume_state_load_{return_type_name}",),
            negative_fixture_ids=("resume_state_loader_schema_invalid",),
        )
    return build_command_boundary_environment(bindings)


def _workflow_contains_resume_or_start(expr) -> bool:
    if isinstance(expr, ResumeOrStartExpr):
        return True
    if isinstance(expr, LetStarExpr):
        return any(_workflow_contains_resume_or_start(binding_expr) for _, binding_expr in expr.bindings) or _workflow_contains_resume_or_start(expr.body)
    if isinstance(expr, MatchExpr):
        return _workflow_contains_resume_or_start(expr.subject) or any(_workflow_contains_resume_or_start(arm.body) for arm in expr.arms)
    if isinstance(expr, WithPhaseExpr):
        return _workflow_contains_resume_or_start(expr.body)
    return False


def _resume_return_type_names(expr) -> tuple[str, ...]:
    if isinstance(expr, ResumeOrStartExpr):
        return (expr.returns_type_name,)
    if isinstance(expr, LetStarExpr):
        names: list[str] = []
        for _, binding_expr in expr.bindings:
            names.extend(_resume_return_type_names(binding_expr))
        names.extend(_resume_return_type_names(expr.body))
        return tuple(names)
    if isinstance(expr, MatchExpr):
        names = list(_resume_return_type_names(expr.subject))
        for arm in expr.arms:
            names.extend(_resume_return_type_names(arm.body))
        return tuple(names)
    if isinstance(expr, WithPhaseExpr):
        return _resume_return_type_names(expr.body)
    return ()


def _validate_definition_module(module: WorkflowLispModule) -> None:
    diagnostics: list[LispFrontendDiagnostic] = []
    definition_names: dict[str, object] = {}
    for definition in module.definitions:
        if definition.name in definition_names:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="definition_duplicate",
                    message=f"duplicate definition `{definition.name}`",
                    span=definition.span,
                    form_path=_definition_form_path(definition),
                )
            )
        else:
            definition_names[definition.name] = definition

    available_type_names = PRELUDE_TYPE_NAMES | frozenset(definition_names)
    for definition in module.definitions:
        if isinstance(definition, RecordDef):
            diagnostics.extend(_validate_field_list(definition.fields, _definition_form_path(definition)))
            diagnostics.extend(_validate_field_types(definition.fields, _definition_form_path(definition), available_type_names))
        elif isinstance(definition, UnionDef):
            diagnostics.extend(_validate_union_definition(definition, available_type_names))

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))


def _validate_union_definition(
    definition: UnionDef,
    available_type_names: frozenset[str],
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    seen_variants: set[str] = set()
    form_path = _definition_form_path(definition)
    for variant in definition.variants:
        if variant.name in seen_variants:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="union_variant_duplicate",
                    message=f"duplicate union variant `{variant.name}`",
                    span=variant.span,
                    form_path=form_path,
                )
            )
        else:
            seen_variants.add(variant.name)
        diagnostics.extend(
            _validate_field_list(
                variant.fields,
                form_path,
                scope_label=f"union variant `{variant.name}`",
            )
        )
        diagnostics.extend(_validate_field_types(variant.fields, form_path, available_type_names))
    return diagnostics


def _validate_field_list(
    fields: tuple[RecordField, ...],
    form_path: tuple[str, ...],
    *,
    scope_label: str = "record",
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    seen_fields: set[str] = set()
    for field in fields:
        if field.name in seen_fields:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="record_field_duplicate",
                    message=f"duplicate field `{field.name}` in {scope_label}",
                    span=field.span,
                    form_path=form_path,
                )
            )
        else:
            seen_fields.add(field.name)
    return diagnostics


def _validate_field_types(
    fields: tuple[RecordField, ...],
    form_path: tuple[str, ...],
    available_type_names: frozenset[str],
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    for field in fields:
        if field.type_name not in available_type_names:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="type_unknown",
                    message=f"unknown type `{field.type_name}`",
                    span=field.span,
                    form_path=form_path,
                )
            )
    return diagnostics


def _definition_form_path(definition: EnumDef | PathDef | RecordDef | UnionDef) -> tuple[str, ...]:
    if isinstance(definition, EnumDef):
        return ("workflow-lisp", "defenum", definition.name)
    if isinstance(definition, PathDef):
        return ("workflow-lisp", "defpath", definition.name)
    if isinstance(definition, RecordDef):
        return ("workflow-lisp", "defrecord", definition.name)
    return ("workflow-lisp", "defunion", definition.name)


def _validate_stage1_top_level_forms(module_syntax: WorkflowLispSyntaxModule) -> None:
    allowed_heads = {"defenum", "defpath", "defrecord", "defunion", "defworkflow", "defproc"}
    for form in module_syntax.forms:
        head_name = syntax_head_name(syntax_node_datum(form))
        if head_name not in allowed_heads:
            continue
        if head_name in {"defworkflow", "defproc"} and not form.expansion_stack:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="definition_form_unknown",
                        message=f"unsupported top-level definition form `{head_name}`",
                        span=form.span,
                        form_path=form.form_path,
                    ),
                )
            )


def _definition_only_syntax_module(module_syntax: WorkflowLispSyntaxModule) -> WorkflowLispSyntaxModule:
    expanded_module = expand_module_forms(
        module_syntax,
        catalog=collect_macro_catalog(module_syntax),
    )
    definition_forms = []
    for form in expanded_module.forms:
        head_name = syntax_head_name(syntax_node_datum(form))
        if head_name in {"defworkflow", "defproc", "defmacro"}:
            continue
        definition_forms.append(form)
    return WorkflowLispSyntaxModule(
        language_version=expanded_module.language_version,
        target_dsl_version=expanded_module.target_dsl_version,
        forms=tuple(definition_forms),
        span=expanded_module.span,
        module_path=expanded_module.module_path,
    )


def _typecheck_procedure_definitions(
    procedure_defs: tuple[ProcedureDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    workflow_catalog: object,
    procedure_catalog: ProcedureCatalog,
    extern_environment: object,
    command_boundary_environment: object,
    procedure_effects_by_name: Mapping[str, EffectSummary] | None = None,
    workflow_effects_by_name: Mapping[str, EffectSummary] | None = None,
) -> tuple[TypedProcedureDef, ...]:
    from .workflows import ExternEnvironment, ProviderExtern

    externs = extern_environment or ExternEnvironment(bindings_by_name={})
    typed_procedures: list[TypedProcedureDef] = []
    for procedure_def in procedure_defs:
        signature = procedure_catalog.signatures_by_name[procedure_def.name]
        value_env = {name: type_ref for name, type_ref in signature.params}
        for extern_name, binding in externs.bindings_by_name.items():
            if isinstance(binding, ProviderExtern):
                value_env[extern_name] = type_env.resolve_type(
                    "Provider",
                    span=procedure_def.span,
                    form_path=procedure_def.form_path,
                )
            else:
                value_env[extern_name] = type_env.resolve_type(
                    "Prompt",
                    span=procedure_def.span,
                    form_path=procedure_def.form_path,
                )
        body_expr = elaborate_expression(
            procedure_def.body,
            bound_names=frozenset(value_env),
            procedure_names=frozenset(procedure_catalog.signatures_by_name),
        )
        typed_body = typecheck_expression(
            body_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=externs,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
        )
        if typed_body.type_ref != signature.return_type_ref:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="procedure_return_type_invalid",
                        message=(
                            f"procedure `{procedure_def.name}` declared return type "
                            f"`{procedure_def.return_type_name}` but body returned a different type"
                        ),
                        span=procedure_def.body.span,
                        form_path=procedure_def.body.form_path,
                        expansion_stack=procedure_def.body.expansion_stack,
                    ),
                )
            )
        typed_procedures.append(
            TypedProcedureDef(
                definition=procedure_def,
                signature=signature,
                typed_body=typed_body,
                direct_effect_summary=typed_body.effect_summary,
                transitive_effect_summary=typed_body.effect_summary,
            )
        )
    return tuple(typed_procedures)


def _infer_stage3_effect_summaries(
    procedure_defs: tuple[ProcedureDef, ...],
    *,
    workflow_defs: tuple[object, ...],
    type_env: FrontendTypeEnvironment,
    workflow_catalog: object,
    procedure_catalog: ProcedureCatalog,
    extern_environment: object,
    command_boundary_environment: object,
) -> tuple[tuple[TypedProcedureDef, ...], tuple[object, ...], ProcedureCatalog]:
    procedure_effects_by_name: Mapping[str, EffectSummary] = {}
    workflow_effects_by_name: Mapping[str, EffectSummary] = {}
    typed_procedures: tuple[TypedProcedureDef, ...] = ()
    typed_workflows: tuple[object, ...] = ()

    max_iterations = max(1, len(procedure_defs) + len(workflow_defs)) * 4
    for _ in range(max_iterations):
        typed_procedures = _typecheck_procedure_definitions(
            procedure_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
        )
        typed_procedures, procedure_catalog = _validate_procedure_effects_and_cycles(
            typed_procedures,
            procedure_catalog=procedure_catalog,
            validate_declared=False,
        )
        next_procedure_effects = {
            procedure.definition.name: procedure.transitive_effect_summary for procedure in typed_procedures
        }
        typed_workflows = typecheck_workflow_definitions(
            workflow_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=next_procedure_effects,
            workflow_effects_by_name=workflow_effects_by_name,
        )
        next_workflow_effects = {
            workflow.definition.name: workflow.effect_summary for workflow in typed_workflows
        }
        if (
            next_procedure_effects == dict(procedure_effects_by_name)
            and next_workflow_effects == dict(workflow_effects_by_name)
        ):
            procedure_effects_by_name = next_procedure_effects
            workflow_effects_by_name = next_workflow_effects
            break
        procedure_effects_by_name = next_procedure_effects
        workflow_effects_by_name = next_workflow_effects
    else:
        raise RuntimeError("workflow Lisp effect summary fixpoint did not converge")

    typed_procedures, procedure_catalog = _validate_procedure_effects_and_cycles(
        typed_procedures,
        procedure_catalog=procedure_catalog,
        validate_declared=True,
    )
    typed_workflows = typecheck_workflow_definitions(
        workflow_defs,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
    )
    return typed_procedures, typed_workflows, procedure_catalog


def _validate_procedure_effects_and_cycles(
    typed_procedures: tuple[TypedProcedureDef, ...],
    *,
    procedure_catalog: ProcedureCatalog,
    validate_declared: bool = True,
) -> tuple[tuple[TypedProcedureDef, ...], ProcedureCatalog]:
    typed_by_name = {procedure.definition.name: procedure for procedure in typed_procedures}
    call_graph = {name: frozenset(_procedure_dependencies(procedure.typed_body.expr)) for name, procedure in typed_by_name.items()}
    procedure_catalog = with_call_graph(procedure_catalog, call_graph)

    resolved: dict[str, EffectSummary] = {}
    visiting: list[str] = []

    def visit(name: str) -> EffectSummary:
        if name in resolved:
            return resolved[name]
        if name in visiting:
            raise LispFrontendCompileError(
                tuple(
                    LispFrontendDiagnostic(
                        code="proc_lowering_cycle",
                        message=f"recursive procedure lowering cycle detected for `{cycle_name}`",
                        span=typed_by_name[cycle_name].definition.span,
                        form_path=typed_by_name[cycle_name].definition.form_path,
                        expansion_stack=typed_by_name[cycle_name].definition.expansion_stack,
                    )
                    for cycle_name in visiting[visiting.index(name):]
                )
            )
        visiting.append(name)
        procedure = typed_by_name[name]
        transitive_effects = set(procedure.direct_effect_summary.transitive_effects)
        procedure_edges = set(procedure.direct_effect_summary.procedure_edges)
        for callee in call_graph.get(name, frozenset()):
            callee_summary = visit(callee)
            transitive_effects.update(callee_summary.transitive_effects)
            procedure_edges.update(callee_summary.procedure_edges)
        summary = EffectSummary(
            direct_effects=procedure.direct_effect_summary.direct_effects,
            transitive_effects=frozenset(transitive_effects),
            procedure_edges=frozenset(procedure_edges),
        )
        resolved[name] = summary
        visiting.pop()
        return summary

    updated: list[TypedProcedureDef] = []
    for procedure in typed_procedures:
        summary = visit(procedure.definition.name)
        if validate_declared:
            validate_procedure_effects(
                procedure_def=procedure.definition,
                declared_effects=procedure.signature.declared_effects,
                inferred_effects=summary.transitive_effects,
            )
        updated.append(
            TypedProcedureDef(
                definition=procedure.definition,
                signature=procedure.signature,
                typed_body=procedure.typed_body,
                direct_effect_summary=procedure.direct_effect_summary,
                transitive_effect_summary=summary,
            )
        )
    return tuple(updated), procedure_catalog


def _procedure_dependencies(expr: object) -> set[str]:
    from .expressions import LetStarExpr, MatchExpr, ProcedureCallExpr, RecordExpr, CallExpr, ProviderResultExpr, CommandResultExpr, WithPhaseExpr

    dependencies: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, ProcedureCallExpr):
            dependencies.add(node.callee_name)
            for arg in node.args:
                walk(arg)
            return
        if isinstance(node, LetStarExpr):
            for _, binding in node.bindings:
                walk(binding)
            walk(node.body)
            return
        if isinstance(node, MatchExpr):
            walk(node.subject)
            for arm in node.arms:
                walk(arm.body)
            return
        if isinstance(node, RecordExpr):
            for _, field_expr in node.fields:
                walk(field_expr)
            return
        if isinstance(node, CallExpr):
            for _, binding_expr in node.bindings:
                walk(binding_expr)
            return
        if isinstance(node, ProviderResultExpr):
            walk(node.provider)
            walk(node.prompt)
            for input_expr in node.inputs:
                walk(input_expr)
            return
        if isinstance(node, CommandResultExpr):
            for argv_expr in node.argv:
                walk(argv_expr)
            return
        if isinstance(node, WithPhaseExpr):
            walk(node.ctx_expr)
            walk(node.body)

    walk(expr)
    return dependencies
