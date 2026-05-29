"""Compile Workflow Lisp modules through definition, type, effect, and lowering.

This module coordinates the frontend pipeline rather than owning any one
semantic layer. It resolves a module graph, expands macros, validates type
definitions, registers procedure/workflow signatures, computes effect
summaries, lowers typed workflows to ordinary workflow dictionaries, and then
optionally validates those dictionaries through the existing workflow loader.

See `README.md` for the package map and
`../../docs/design/workflow_lisp_frontend_mvp_specification.md` for the implemented
scope this compiler coordinates.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle

from .contracts import derive_union_workflow_boundary_projection
from .definitions import (
    EnumDef,
    PathDef,
    RecordDef,
    RecordField,
    SchemaDef,
    UnionDef,
    UnionVariant,
    WorkflowLispModule,
    _expand_schema_fields,
    elaborate_definition_module,
)
from .diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
    diagnostic_effective_severity,
    with_diagnostic_metadata,
)
from .lints import LINT_PROFILE_DEFAULT, required_lint_diagnostic
from .effects import EffectSummary, ProcedureCallEdge, merge_effect_summaries
from .expressions import (
    LetStarExpr,
    MatchExpr,
    ResumeOrStartExpr,
    WithPhaseExpr,
    elaborate_expression,
)
from .functions import (
    FunctionCatalog,
    FunctionDef,
    FunctionSignature,
    TypedFunctionDef,
    build_function_catalog,
    elaborate_function_definitions,
    normalize_function_calls,
    typecheck_function_definitions,
    validate_function_cycles,
)
from .lowering import lower_workflow_definitions, validate_lowered_workflows
from .macros import collect_macro_catalog, collect_macro_catalog_with_imports, expand_module_forms
from .modules import (
    LinkedModuleGraph,
    ModuleExportSurface,
    ModuleImportScope,
    ModuleMemberBinding,
    build_import_scope,
    canonical_callable_key,
    derive_export_surface,
    imported_macro_catalog,
    resolve_module_graph,
)
from .procedures import (
    ProcedureCatalog,
    ProcedureDef,
    ProcedureParam,
    ProcedureSignature,
    TypedProcedureDef,
    build_procedure_catalog,
    elaborate_procedure_definitions,
    proc_ref_specialization_name as proc_ref_call_specialization_name,
    validate_procedure_effects,
    with_call_graph,
)
from .procedure_refs import ProcRefResolutionContext, ResolvedProcRefValue, resolve_proc_ref_value
from .reader import read_sexpr_file
from .source_map import build_source_map_document
from .syntax import WorkflowLispSyntaxModule, SyntaxList, SyntaxNode, build_syntax_module, syntax_head_name, syntax_identifier, syntax_node_datum
from .type_env import (
    PRELUDE_TYPE_NAMES,
    FrontendTypeEnvironment,
    PathTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
)
from .type_expressions import (
    ListTypeExpr,
    MapTypeExpr,
    NamedTypeExpr,
    OptionalTypeExpr,
    ProcRefTypeExpr,
    WorkflowRefTypeExpr,
    parse_type_expression,
)
from .typecheck import typecheck_expression
from .validation import (
    VALIDATION_PASS_CATALOG,
    ValidationPipelinePass,
    ValidationPipelineState,
    collect_pipeline_diagnostics,
    raise_pipeline_diagnostics,
    run_validation_pipeline,
)
from .workflows import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    Stage3CompileResult,
    TypedWorkflowDef,
    WorkflowDef,
    WorkflowParam,
    WorkflowSignature,
)
from .workflows import (
    build_command_boundary_environment,
    build_extern_environment,
    build_workflow_catalog,
    elaborate_workflow_definitions,
    typecheck_workflow_definitions,
)


@dataclass(frozen=True)
class LinkedStage1CompileResult:
    """Definition-only compile result for an entry module graph.

    This early pass proves that module headers, imports, exports, and type
    definitions are coherent before expression typechecking, effect checking,
    or lowering begins.
    """

    graph: LinkedModuleGraph
    entry_module: WorkflowLispModule
    compiled_modules_by_name: Mapping[str, WorkflowLispModule]


@dataclass(frozen=True)
class LinkedStage3CompileResult:
    """Executable compile result for an entry module graph.

    This result includes expanded syntax, typechecked procedures/workflows,
    lowered workflow dictionaries, and optionally bundles validated by the
    existing workflow loader.
    """

    graph: LinkedModuleGraph
    entry_result: Stage3CompileResult
    compiled_results_by_name: Mapping[str, Stage3CompileResult]
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle]
    diagnostics: tuple[LispFrontendDiagnostic, ...] = ()


def compile_stage1_entrypoint(
    path: Path,
    *,
    source_roots: tuple[Path, ...] | None = None,
) -> LinkedStage1CompileResult:
    """Compile an entrypoint through module and type-definition validation.

    This pass intentionally ignores executable bodies. It exists so callers can
    validate reusable type surfaces and import/export wiring without requiring
    provider externs, prompt externs, command adapters, or imported workflows.
    """

    graph = resolve_module_graph(path, source_roots=source_roots)
    compiled_modules_by_name: dict[str, WorkflowLispModule] = {}
    export_surfaces = dict(graph.export_surfaces_by_name)
    exported_schema_defs_by_module: dict[str, dict[str, SchemaDef]] = {}
    for module_name in graph.topological_order:
        module_source = graph.modules_by_name[module_name]
        preliminary_module = WorkflowLispModule(
            language_version=module_source.syntax_module.language_version,
            target_dsl_version=module_source.syntax_module.target_dsl_version,
            module_name=module_source.syntax_module.module_name,
            imports=module_source.syntax_module.imports,
            exports=module_source.syntax_module.exports,
            definitions=(),
            span=module_source.syntax_module.span,
            schemas=(),
        )
        import_scope = build_import_scope(preliminary_module, export_surfaces_by_name=export_surfaces)
        module = _compile_stage1_syntax_module(
            module_source.syntax_module,
            validate_top_level_forms=False,
            import_scope=import_scope,
            imported_schema_defs=_imported_schema_defs(import_scope, exported_schema_defs_by_module),
        )
        export_surfaces[module_name] = derive_export_surface(
            module_source.syntax_module,
            local_macros=collect_macro_catalog(module_source.syntax_module),
            local_module=module,
        )
        exported_schema_defs_by_module[module_name] = _exported_schema_defs(
            module,
            export_surfaces[module_name],
            import_scope=import_scope,
            imported_schema_defs=_imported_schema_defs(import_scope, exported_schema_defs_by_module),
        )
        compiled_modules_by_name[module_name] = module
    return LinkedStage1CompileResult(
        graph=LinkedModuleGraph(
            entry_module_name=graph.entry_module_name,
            modules_by_name=graph.modules_by_name,
            topological_order=graph.topological_order,
            export_surfaces_by_name=export_surfaces,
        ),
        entry_module=compiled_modules_by_name[graph.entry_module_name],
        compiled_modules_by_name=compiled_modules_by_name,
    )


def compile_stage3_entrypoint(
    path: Path,
    *,
    source_roots: tuple[Path, ...] | None = None,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None = None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
    validate_shared: bool = True,
    workspace_root: Path | None = None,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> LinkedStage3CompileResult:
    """Compile an entrypoint and imports through the executable frontend path.

    The function resolves the module graph once, then runs macro expansion,
    definition validation, procedure/workflow signature registration, expression
    typechecking, effect inference, lowering to ordinary workflow dictionaries,
    and optional shared validation for every reachable module.
    """

    compile_result, results = _run_stage3_entrypoint_validation_pipeline(
        path,
        source_roots=source_roots,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles=imported_workflow_bundles,
        command_boundaries=command_boundaries,
        validate_shared=validate_shared,
        workspace_root=workspace_root or path.parent,
        lint_profile=lint_profile,
    )
    additional_diagnostics = ()
    if compile_result is not None:
        additional_diagnostics = compile_result.diagnostics
    diagnostics = _finalize_stage3_diagnostics(
        results,
        additional_diagnostics=additional_diagnostics,
        lint_profile=lint_profile,
    )
    if compile_result is None:
        raise RuntimeError("module-graph compilation did not produce a result")
    return replace(compile_result, diagnostics=diagnostics)


def compile_stage3_module(
    path: Path,
    *,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None = None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
    validate_shared: bool = True,
    workspace_root: Path | None = None,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> Stage3CompileResult:
    """Compile one `.orc` file through the executable frontend pipeline."""

    state, results = _run_stage3_validation_pipeline(
        path,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles=imported_workflow_bundles,
        command_boundaries=command_boundaries,
        validate_shared=validate_shared,
        workspace_root=workspace_root or path.parent,
        lint_profile=lint_profile,
    )
    diagnostics = _finalize_stage3_diagnostics(
        results,
        additional_diagnostics=_collect_stage3_required_lint_diagnostics(state.typed_workflows),
        lint_profile=lint_profile,
    )
    return Stage3CompileResult(
        module=state.module,
        workflow_catalog=state.workflow_catalog,
        procedure_catalog=state.procedure_catalog,
        extern_environment=state.extern_environment,
        command_boundary_environment=state.command_boundary_environment,
        typed_procedures=state.typed_procedures,
        typed_workflows=state.typed_workflows,
        lowered_workflows=state.lowered_workflows,
        validated_bundles=state.validated_bundles,
        diagnostics=diagnostics,
    )


def _finalize_stage3_diagnostics(
    results: tuple[object, ...],
    *,
    additional_diagnostics: tuple[LispFrontendDiagnostic, ...],
    lint_profile: str,
) -> tuple[LispFrontendDiagnostic, ...]:
    diagnostics = tuple(
        with_diagnostic_metadata(
            diagnostic,
            lint_profile=lint_profile,
        )
        for diagnostic in (
            *collect_pipeline_diagnostics(results),
            *additional_diagnostics,
        )
    )
    if any(
        diagnostic_effective_severity(
            diagnostic,
            lint_profile=lint_profile,
        )
        == "error"
        for diagnostic in diagnostics
    ):
        raise LispFrontendCompileError(diagnostics)
    return diagnostics


_ALLOWED_CONTEXT_RECORD_TYPES = frozenset(
    {
        "RunCtx",
        "PhaseCtx",
        "ItemCtx",
        "DrainCtx",
    }
)


def _collect_stage3_required_lint_diagnostics(
    typed_workflows: tuple[TypedWorkflowDef, ...],
) -> tuple[LispFrontendDiagnostic, ...]:
    diagnostics: list[LispFrontendDiagnostic] = []
    for workflow in typed_workflows:
        signature = workflow.signature
        if any(
            _type_ref_contains_low_level_state_path(type_ref)
            for _, type_ref in signature.params
        ) or _type_ref_contains_low_level_state_path(signature.return_type_ref):
            diagnostics.append(
                required_lint_diagnostic(
                    "low_level_state_path_in_high_level_module",
                    message=(
                        f"workflow `{signature.name}` exposes low-level state paths at its boundary; "
                        "prefer derived context or layout helpers"
                    ),
                    span=signature.span,
                    form_path=signature.form_path,
                )
            )
        if isinstance(signature.return_type_ref, UnionTypeRef):
            projection = derive_union_workflow_boundary_projection(
                signature.return_type_ref,
                span=signature.span,
                form_path=signature.form_path,
            )
            if projection.variant_fields and all(
                not fields for fields in projection.variant_fields.values()
            ):
                diagnostics.append(
                    required_lint_diagnostic(
                        "variant_output_without_variant_specific_fields",
                        message=(
                            f"union `{signature.return_type_ref.name}` lowers without variant-specific fields; "
                            "prefer a record plus enum"
                        ),
                        span=signature.span,
                        form_path=signature.form_path,
                    )
                )
    return tuple(diagnostics)


def _type_ref_contains_low_level_state_path(type_ref: TypeRef) -> bool:
    if isinstance(type_ref, PathTypeRef):
        return type_ref.definition.under == "state"
    if isinstance(type_ref, RecordTypeRef):
        record_name = type_ref.name.split("::", 1)[-1]
        if record_name in _ALLOWED_CONTEXT_RECORD_TYPES:
            return False
        return any(
            _type_ref_contains_low_level_state_path(field_type)
            for field_type in type_ref.field_types.values()
        )
    if isinstance(type_ref, UnionTypeRef):
        return any(
            _type_ref_contains_low_level_state_path(field_type)
            for field_types in type_ref.variant_field_types.values()
            for field_type in field_types.values()
        )
    return False


def _run_stage1_validation_pipeline(
    *,
    path: Path | None = None,
    syntax_module: WorkflowLispSyntaxModule | None = None,
    validate_top_level_forms: bool,
    import_scope: ModuleImportScope | None = None,
    imported_schema_defs: Mapping[str, SchemaDef] | None = None,
) -> tuple[ValidationPipelineState, tuple[object, ...]]:
    if (path is None) == (syntax_module is None):
        raise ValueError("exactly one of `path` or `syntax_module` is required")

    def parse_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        assert path is not None
        return replace(state, parse_tree=read_sexpr_file(path))

    def module_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        if state.syntax_module is not None:
            return state
        return replace(state, syntax_module=build_syntax_module(state.parse_tree))

    def macro_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        expanded = expand_module_forms(
            state.syntax_module,
            catalog=collect_macro_catalog(state.syntax_module),
        )
        return replace(state, expanded_syntax_module=expanded)

    def type_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        if validate_top_level_forms:
            _validate_stage1_top_level_forms(state.expanded_syntax_module)
        module = elaborate_definition_module(
            _definition_only_from_expanded_syntax_module(state.expanded_syntax_module),
            import_scope=import_scope,
            imported_schemas=imported_schema_defs,
        )
        _validate_definition_module(module, import_scope=import_scope)
        return replace(state, module=module)

    passes: list[ValidationPipelinePass] = []
    initial_state = ValidationPipelineState()
    if path is not None:
        passes.append(
            ValidationPipelinePass(
                pass_id="parse",
                runner=parse_pass,
                artifact_ready=lambda state: state.parse_tree is not None,
            )
        )
    else:
        initial_state = replace(initial_state, syntax_module=syntax_module)
    passes.extend(
        [
            ValidationPipelinePass(
                pass_id="module",
                runner=module_pass,
                artifact_ready=lambda state: state.syntax_module is not None,
            ),
            ValidationPipelinePass(
                pass_id="macro",
                runner=macro_pass,
                artifact_ready=lambda state: state.expanded_syntax_module is not None,
            ),
            ValidationPipelinePass(
                pass_id="type",
                runner=type_pass,
                artifact_ready=lambda state: state.module is not None,
            ),
        ]
    )
    return run_validation_pipeline(initial_state, tuple(passes))


def _run_stage3_entrypoint_validation_pipeline(
    path: Path,
    *,
    source_roots: tuple[Path, ...] | None = None,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None = None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
    validate_shared: bool,
    workspace_root: Path,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> tuple[LinkedStage3CompileResult | None, tuple[object, ...]]:
    graph = resolve_module_graph(path, source_roots=source_roots)
    compile_result: LinkedStage3CompileResult | None = None
    selected_workflow_name: str | None = None

    def frontend_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        nonlocal compile_result, selected_workflow_name
        compile_result = _compile_stage3_graph(
            graph,
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
            imported_workflow_bundles=imported_workflow_bundles,
            command_boundaries=command_boundaries,
            validate_shared=False,
            workspace_root=workspace_root,
            lint_profile=lint_profile,
        )
        selected_workflow_name = _selected_stage3_entry_workflow_name(compile_result)
        return replace(
            state,
            module=compile_result.entry_result.module,
            lowered_workflows=compile_result.entry_result.lowered_workflows,
            validated_bundles=compile_result.entry_result.validated_bundles,
        )

    def source_map_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        del state
        assert compile_result is not None
        assert selected_workflow_name is not None
        _validate_stage3_linked_source_map_lineage(
            compile_result,
            selected_name=selected_workflow_name,
        )
        return ValidationPipelineState(
            module=compile_result.entry_result.module,
            lowered_workflows=compile_result.entry_result.lowered_workflows,
            validated_bundles=compile_result.entry_result.validated_bundles,
        )

    def shared_validation_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        nonlocal compile_result
        if not validate_shared:
            return state
        assert compile_result is not None
        validated_bundles = validate_lowered_workflows(
            compile_result.entry_result.lowered_workflows,
            workspace_root=workspace_root,
            imported_workflow_bundles=compile_result.entry_result.workflow_catalog.imported_bundles_by_name,
        )
        compile_result = replace(
            compile_result,
            entry_result=replace(
                compile_result.entry_result,
                validated_bundles=validated_bundles,
            ),
            validated_bundles_by_name={
                **dict(compile_result.validated_bundles_by_name),
                **validated_bundles,
            },
        )
        return replace(state, validated_bundles=validated_bundles)

    def executable_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        del state
        assert compile_result is not None
        assert selected_workflow_name is not None
        _validate_stage3_linked_source_map_lineage(
            compile_result,
            selected_name=selected_workflow_name,
        )
        return ValidationPipelineState(
            module=compile_result.entry_result.module,
            lowered_workflows=compile_result.entry_result.lowered_workflows,
            validated_bundles=compile_result.entry_result.validated_bundles,
        )

    passes: list[ValidationPipelinePass] = [
        ValidationPipelinePass(
            pass_id="parse",
            runner=frontend_pass,
            covers_passes=VALIDATION_PASS_CATALOG[:10],
            artifact_ready=lambda state: bool(state.lowered_workflows),
            attach_metadata=False,
        ),
        ValidationPipelinePass(
            pass_id="source_map",
            runner=source_map_pass,
            artifact_ready=lambda state: bool(state.lowered_workflows),
        ),
    ]
    if validate_shared:
        passes.extend(
            [
                ValidationPipelinePass(
                    pass_id="shared_validation",
                    runner=shared_validation_pass,
                    authority_layer="shared_validation",
                    artifact_ready=lambda state: bool(state.validated_bundles),
                ),
                ValidationPipelinePass(
                    pass_id="executable",
                    runner=executable_pass,
                    artifact_ready=lambda state: bool(state.validated_bundles),
                ),
            ]
        )

    _, results = run_validation_pipeline(
        ValidationPipelineState(),
        tuple(passes),
        lint_profile=lint_profile,
    )
    return compile_result, results


def _compile_stage1_syntax_module(
    syntax_module: WorkflowLispSyntaxModule,
    *,
    validate_top_level_forms: bool,
    import_scope: ModuleImportScope | None = None,
    imported_schema_defs: Mapping[str, SchemaDef] | None = None,
) -> WorkflowLispModule:
    state, results = _run_stage1_validation_pipeline(
        syntax_module=syntax_module,
        validate_top_level_forms=validate_top_level_forms,
        import_scope=import_scope,
        imported_schema_defs=imported_schema_defs,
    )
    raise_pipeline_diagnostics(results)
    return state.module


def _run_stage3_validation_pipeline(
    path: Path,
    *,
    provider_externs: Mapping[str, str] | None,
    prompt_externs: Mapping[str, str] | None,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None,
    validate_shared: bool,
    workspace_root: Path,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> tuple[ValidationPipelineState, tuple[object, ...]]:
    effective_imported_workflow_bundles = dict(imported_workflow_bundles or {})

    def parse_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        return replace(state, parse_tree=read_sexpr_file(path))

    def module_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        return replace(state, syntax_module=build_syntax_module(state.parse_tree))

    def macro_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        expanded = expand_module_forms(
            state.syntax_module,
            catalog=collect_macro_catalog(state.syntax_module),
        )
        return replace(state, expanded_syntax_module=expanded)

    def typed_frontend_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        module = elaborate_definition_module(
            _definition_only_syntax_module(state.expanded_syntax_module)
        )
        _validate_definition_module(module)
        type_env = FrontendTypeEnvironment.from_module(module)
        workflow_defs = elaborate_workflow_definitions(state.expanded_syntax_module)
        function_defs = elaborate_function_definitions(state.expanded_syntax_module)
        procedure_defs = elaborate_procedure_definitions(state.expanded_syntax_module)
        _validate_local_callable_name_collisions(function_defs, procedure_defs)
        workflow_catalog = build_workflow_catalog(
            module,
            workflow_defs,
            type_env,
            imported_workflow_bundles=effective_imported_workflow_bundles,
        )
        procedure_catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
        function_catalog = build_function_catalog(function_defs, type_env=type_env)
        extern_environment = build_extern_environment(
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
        )
        command_boundary_environment = build_command_boundary_environment(command_boundaries)
        command_boundary_environment = _augment_resource_transition_command_boundaries(
            command_boundary_environment,
        )
        command_boundary_environment = _augment_resume_command_boundaries(
            command_boundary_environment,
            expressions=tuple(workflow.body for workflow in workflow_defs)
            + tuple(procedure.body for procedure in procedure_defs),
        )
        typed_functions = typecheck_function_definitions(
            function_defs,
            type_env=type_env,
            function_catalog=function_catalog,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
        )
        function_catalog = validate_function_cycles(
            typed_functions,
            function_catalog=function_catalog,
        )
        typed_procedures, typed_workflows, resolved_procedure_catalog = (
            _infer_stage3_effect_summaries(
                procedure_defs,
                workflow_defs=workflow_defs,
                type_env=type_env,
                workflow_catalog=workflow_catalog,
                procedure_catalog=procedure_catalog,
                function_catalog=function_catalog,
                extern_environment=extern_environment,
                command_boundary_environment=command_boundary_environment,
                proc_ref_resolution_context=ProcRefResolutionContext(
                    local_raw_names=frozenset(procedure.name for procedure in procedure_defs),
                ),
            )
        )
        typed_functions_by_name = {
            function.definition.name: function
            for function in typed_functions
        }
        typed_procedures = tuple(
            replace(
                procedure,
                typed_body=normalize_function_calls(
                    procedure.typed_body,
                    typed_functions_by_name=typed_functions_by_name,
                ),
            )
            for procedure in typed_procedures
        )
        typed_workflows = tuple(
            replace(
                workflow,
                typed_body=normalize_function_calls(
                    workflow.typed_body,
                    typed_functions_by_name=typed_functions_by_name,
                ),
            )
            for workflow in typed_workflows
        )
        return replace(
            state,
            module=module,
            type_env=type_env,
            workflow_defs=workflow_defs,
            procedure_defs=procedure_defs,
            workflow_catalog=workflow_catalog,
            procedure_catalog=resolved_procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            typed_procedures=typed_procedures,
            typed_workflows=typed_workflows,
        )

    def lowering_surface_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        lowered_workflows = lower_workflow_definitions(
            state.typed_workflows,
            typed_procedures=state.typed_procedures,
            procedure_catalog=state.procedure_catalog,
            workflow_path=path,
            workflow_catalog=state.workflow_catalog,
            imported_workflow_bundles=effective_imported_workflow_bundles,
            extern_environment=state.extern_environment,
            command_boundary_environment=state.command_boundary_environment,
            type_env=state.type_env,
        )
        return replace(state, lowered_workflows=lowered_workflows)

    def source_map_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        _validate_stage3_source_map_lineage(
            state,
            path=path,
            include_executable_nodes=False,
        )
        return state

    def shared_validation_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        if not validate_shared:
            return state
        validated_bundles = validate_lowered_workflows(
            state.lowered_workflows,
            workspace_root=workspace_root,
            imported_workflow_bundles=effective_imported_workflow_bundles,
        )
        return replace(state, validated_bundles=validated_bundles)

    def executable_pass(state: ValidationPipelineState) -> ValidationPipelineState:
        _validate_stage3_source_map_lineage(
            state,
            path=path,
            include_executable_nodes=True,
        )
        return state

    passes: list[ValidationPipelinePass] = [
        ValidationPipelinePass(
            pass_id="parse",
            runner=parse_pass,
            artifact_ready=lambda state: state.parse_tree is not None,
        ),
        ValidationPipelinePass(
            pass_id="module",
            runner=module_pass,
            artifact_ready=lambda state: state.syntax_module is not None,
        ),
        ValidationPipelinePass(
            pass_id="macro",
            runner=macro_pass,
            artifact_ready=lambda state: state.expanded_syntax_module is not None,
        ),
        ValidationPipelinePass(
            pass_id="type",
            runner=typed_frontend_pass,
            covers_passes=(
                "type",
                "effect",
                "reference",
                "contract",
                "proof",
                "authority",
            ),
            artifact_ready=lambda state: bool(state.typed_workflows),
            attach_metadata=False,
        ),
        ValidationPipelinePass(
            pass_id="lowering_surface",
            runner=lowering_surface_pass,
            artifact_ready=lambda state: bool(state.lowered_workflows),
        ),
        ValidationPipelinePass(
            pass_id="source_map",
            runner=source_map_pass,
            artifact_ready=lambda state: bool(state.lowered_workflows),
        ),
    ]
    if validate_shared:
        passes.extend(
            [
                ValidationPipelinePass(
                    pass_id="shared_validation",
                    runner=shared_validation_pass,
                    authority_layer="shared_validation",
                    artifact_ready=lambda state: bool(state.validated_bundles),
                ),
                ValidationPipelinePass(
                    pass_id="executable",
                    runner=executable_pass,
                    artifact_ready=lambda state: bool(state.validated_bundles),
                ),
            ]
        )
    return run_validation_pipeline(
        ValidationPipelineState(),
        tuple(passes),
        lint_profile=lint_profile,
    )


def compile_stage1_module(path: Path) -> WorkflowLispModule:
    """Compile one `.orc` file through the definition-only frontend pipeline."""

    state, results = _run_stage1_validation_pipeline(
        path=path,
        validate_top_level_forms=True,
    )
    raise_pipeline_diagnostics(results)
    return state.module


def _validate_stage3_source_map_lineage(
    state: ValidationPipelineState,
    *,
    path: Path,
    include_executable_nodes: bool,
) -> None:
    if state.module is None:
        return
    module_result = Stage3CompileResult(
        module=state.module,
        workflow_catalog=state.workflow_catalog,
        procedure_catalog=state.procedure_catalog,
        extern_environment=state.extern_environment,
        command_boundary_environment=state.command_boundary_environment,
        typed_procedures=state.typed_procedures,
        typed_workflows=state.typed_workflows,
        lowered_workflows=state.lowered_workflows,
        validated_bundles=state.validated_bundles if include_executable_nodes else {},
    )
    module_name = state.module.module_name or path.stem
    compile_result = LinkedStage3CompileResult(
        graph=LinkedModuleGraph(
            entry_module_name=module_name,
            modules_by_name={},
            topological_order=(module_name,),
            export_surfaces_by_name={},
        ),
        entry_result=module_result,
        compiled_results_by_name={module_name: module_result},
        validated_bundles_by_name=state.validated_bundles if include_executable_nodes else {},
    )
    selected_name = (
        state.lowered_workflows[0].typed_workflow.definition.name
        if state.lowered_workflows
        else module_name
    )
    build_source_map_document(
        compile_result,
        selected_name=selected_name,
        display_name_resolver=lambda workflow_name: workflow_name.rsplit("::", 1)[-1],
    )


def _validate_stage3_linked_source_map_lineage(
    compile_result: LinkedStage3CompileResult,
    *,
    selected_name: str,
) -> None:
    build_source_map_document(
        compile_result,
        selected_name=selected_name,
        display_name_resolver=lambda workflow_name: workflow_name.rsplit("::", 1)[-1],
    )


def _selected_stage3_entry_workflow_name(
    compile_result: LinkedStage3CompileResult,
) -> str:
    if compile_result.entry_result.lowered_workflows:
        return compile_result.entry_result.lowered_workflows[0].typed_workflow.definition.name
    module_name = compile_result.entry_result.module.module_name
    if module_name is not None:
        return module_name
    return compile_result.graph.entry_module_name


def _compile_stage3_graph(
    graph: LinkedModuleGraph,
    *,
    provider_externs: Mapping[str, str] | None,
    prompt_externs: Mapping[str, str] | None,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None,
    validate_shared: bool,
    workspace_root: Path,
    lint_profile: str = LINT_PROFILE_DEFAULT,
) -> LinkedStage3CompileResult:
    """Compile a resolved module graph in dependency order.

    Each module is expanded and typechecked after its imports have published
    type refs, macro definitions, procedure signatures, workflow signatures,
    and validated workflow bundles. Exported workflows are validated as needed
    so downstream modules can call them through the existing workflow loader.
    """

    export_surfaces = dict(graph.export_surfaces_by_name)
    exported_type_refs_by_module: dict[str, dict[str, TypeRef]] = {}
    exported_schema_defs_by_module: dict[str, dict[str, SchemaDef]] = {}
    exported_macro_defs_by_module: dict[str, dict[str, object]] = {}
    exported_function_signatures_by_module: dict[str, dict[str, FunctionSignature]] = {}
    exported_procedure_signatures_by_module: dict[str, dict[str, ProcedureSignature]] = {}
    exported_workflow_signatures_by_module: dict[str, dict[str, WorkflowSignature]] = {}
    visible_procedure_names_by_module: dict[str, frozenset[str]] = {}
    typed_functions_by_name: dict[str, TypedFunctionDef] = {}
    typed_procedures_by_name: dict[str, TypedProcedureDef] = {}
    procedure_effects_by_name: dict[str, EffectSummary] = {}
    workflow_effects_by_name: dict[str, EffectSummary] = {}
    exported_validated_bundles_by_name: dict[str, LoadedWorkflowBundle] = {}
    compiled_results_by_name: dict[str, Stage3CompileResult] = {}
    explicit_imported_bundles = dict(imported_workflow_bundles or {})
    aggregate_diagnostics: list[LispFrontendDiagnostic] = []

    for module_name in graph.topological_order:
        module_source = graph.modules_by_name[module_name]
        preliminary_module = WorkflowLispModule(
            language_version=module_source.syntax_module.language_version,
            target_dsl_version=module_source.syntax_module.target_dsl_version,
            module_name=module_source.syntax_module.module_name,
            imports=module_source.syntax_module.imports,
            exports=module_source.syntax_module.exports,
            definitions=(),
            span=module_source.syntax_module.span,
            schemas=(),
        )
        import_scope = build_import_scope(preliminary_module, export_surfaces_by_name=export_surfaces)
        imported_schema_defs = _imported_schema_defs(import_scope, exported_schema_defs_by_module)
        imported_macros = imported_macro_catalog(
            import_scope,
            exported_macros_by_module=exported_macro_defs_by_module,
        )
        expanded_syntax = expand_module_forms(
            module_source.syntax_module,
            catalog=collect_macro_catalog_with_imports(
                module_source.syntax_module,
                imported_definitions=imported_macros,
            ),
        )
        definition_module = elaborate_definition_module(
            _definition_only_from_expanded_syntax_module(expanded_syntax),
            import_scope=import_scope,
            imported_schemas=imported_schema_defs,
        )
        _validate_definition_module(definition_module, import_scope=import_scope)

        raw_function_defs = elaborate_function_definitions(expanded_syntax)
        raw_procedure_defs = elaborate_procedure_definitions(expanded_syntax)
        raw_workflow_defs = elaborate_workflow_definitions(expanded_syntax)
        export_surfaces[module_name] = derive_export_surface(
            expanded_syntax,
            local_macros=collect_macro_catalog(module_source.syntax_module),
            local_module=definition_module,
            function_names=tuple(function.name for function in raw_function_defs),
            procedure_names=tuple(procedure.name for procedure in raw_procedure_defs),
            workflow_names=tuple(workflow.name for workflow in raw_workflow_defs),
        )
        exported_schema_defs_by_module[module_name] = _exported_schema_defs(
            definition_module,
            export_surfaces[module_name],
            import_scope=import_scope,
            imported_schema_defs=imported_schema_defs,
        )
        visible_procedure_names_by_module[module_name] = frozenset(
            procedure.name for procedure in raw_procedure_defs
        )
        import_scope = build_import_scope(definition_module, export_surfaces_by_name=export_surfaces)
        _validate_visible_callable_name_collisions(
            function_defs=raw_function_defs,
            procedure_defs=raw_procedure_defs,
            import_scope=import_scope,
        )

        imported_type_refs = _imported_type_refs(import_scope, exported_type_refs_by_module)
        type_env = FrontendTypeEnvironment.from_module(
            definition_module,
            import_scope=import_scope,
            imported_type_refs=imported_type_refs,
        )
        function_defs = _canonicalize_function_defs(module_name, raw_function_defs)
        procedure_defs = _canonicalize_procedure_defs(module_name, raw_procedure_defs)
        workflow_defs = _canonicalize_workflow_defs(module_name, raw_workflow_defs)
        function_lookup_aliases = _local_callable_lookup_aliases(
            module_name,
            raw_names=tuple(function.name for function in raw_function_defs),
            imported_bindings=import_scope.function_bindings,
        )
        procedure_lookup_aliases = _local_callable_lookup_aliases(
            module_name,
            raw_names=tuple(procedure.name for procedure in raw_procedure_defs),
            imported_bindings=import_scope.procedure_bindings,
        )
        workflow_lookup_aliases = _local_callable_lookup_aliases(
            module_name,
            raw_names=tuple(workflow.name for workflow in raw_workflow_defs),
            imported_bindings=import_scope.workflow_bindings,
        )
        imported_procedure_signatures = _imported_procedure_signatures(
            import_scope,
            exported_procedure_signatures_by_module,
        )
        imported_function_signatures = _imported_function_signatures(
            import_scope,
            exported_function_signatures_by_module,
        )
        imported_workflow_signatures = _imported_workflow_signatures(
            import_scope,
            exported_workflow_signatures_by_module,
        )
        effective_imported_bundles = _effective_imported_workflow_bundles(
            import_scope,
            explicit_imported_bundles=explicit_imported_bundles,
            exported_validated_bundles_by_name=exported_validated_bundles_by_name,
        )
        workflow_catalog = build_workflow_catalog(
            definition_module,
            workflow_defs,
            type_env,
            imported_signatures=imported_workflow_signatures,
            lookup_aliases=workflow_lookup_aliases,
            imported_workflow_bundles=effective_imported_bundles,
        )
        function_catalog = build_function_catalog(
            function_defs,
            type_env=type_env,
            imported_signatures=imported_function_signatures,
            lookup_aliases=function_lookup_aliases,
        )
        procedure_catalog = build_procedure_catalog(
            procedure_defs,
            type_env=type_env,
            imported_signatures=imported_procedure_signatures,
            lookup_aliases=procedure_lookup_aliases,
        )
        extern_environment = build_extern_environment(
            provider_externs=provider_externs,
            prompt_externs=prompt_externs,
        )
        command_boundary_environment = build_command_boundary_environment(command_boundaries)
        command_boundary_environment = _augment_resource_transition_command_boundaries(
            command_boundary_environment,
        )
        command_boundary_environment = _augment_resume_command_boundaries(
            command_boundary_environment,
            expressions=tuple(workflow.body for workflow in workflow_defs)
            + tuple(procedure.body for procedure in procedure_defs),
        )
        local_function_resolver = _function_name_resolver(
            module_name,
            import_scope,
            local_raw_names=frozenset(function.name for function in raw_function_defs),
        )
        local_procedure_resolver = _procedure_name_resolver(
            module_name,
            import_scope,
            local_raw_names=frozenset(procedure.name for procedure in raw_procedure_defs),
        )
        local_workflow_resolver = _workflow_name_resolver(
            module_name,
            import_scope,
            local_raw_names=frozenset(workflow.name for workflow in raw_workflow_defs),
            external_workflow_names=frozenset(effective_imported_bundles),
        )
        typed_functions = typecheck_function_definitions(
            function_defs,
            type_env=type_env,
            function_catalog=function_catalog,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            function_name_resolver=local_function_resolver,
            procedure_name_resolver=local_procedure_resolver,
            workflow_name_resolver=local_workflow_resolver,
        )
        function_catalog = validate_function_cycles(
            typed_functions,
            function_catalog=function_catalog,
        )
        combined_typed_functions = {
            **typed_functions_by_name,
            **{function.definition.name: function for function in typed_functions},
        }
        typed_functions = tuple(
            replace(
                function,
                typed_body=normalize_function_calls(
                    function.typed_body,
                    typed_functions_by_name=combined_typed_functions,
                ),
            )
            for function in typed_functions
        )
        combined_typed_functions = {
            **typed_functions_by_name,
            **{function.definition.name: function for function in typed_functions},
        }
        typed_procedures, typed_workflows, procedure_catalog = _infer_stage3_effect_summaries(
            procedure_defs,
            workflow_defs=workflow_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            function_catalog=function_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            function_name_resolver=local_function_resolver,
            procedure_name_resolver=local_procedure_resolver,
            workflow_name_resolver=local_workflow_resolver,
            proc_ref_resolution_context=ProcRefResolutionContext(
                import_scope=import_scope,
                local_raw_names=frozenset(procedure.name for procedure in raw_procedure_defs),
                visible_procedure_names_by_module=visible_procedure_names_by_module,
            ),
        )
        typed_procedures = tuple(
            replace(
                procedure,
                typed_body=normalize_function_calls(
                    procedure.typed_body,
                    typed_functions_by_name=combined_typed_functions,
                ),
            )
            for procedure in typed_procedures
        )
        typed_workflows = tuple(
            replace(
                workflow,
                typed_body=normalize_function_calls(
                    workflow.typed_body,
                    typed_functions_by_name=combined_typed_functions,
                ),
            )
            for workflow in typed_workflows
        )
        combined_typed_procedures = {
            **typed_procedures_by_name,
            **{procedure.definition.name: procedure for procedure in typed_procedures},
        }
        lowered_workflows = lower_workflow_definitions(
            typed_workflows,
            typed_procedures=tuple(combined_typed_procedures.values()),
            procedure_catalog=procedure_catalog,
            workflow_path=module_source.path,
            workflow_catalog=workflow_catalog,
            imported_workflow_bundles=effective_imported_bundles,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            type_env=type_env,
        )
        requires_internal_bundle_validation = (
            not validate_shared
            and module_name != graph.entry_module_name
            and bool(export_surfaces[module_name].workflows_by_name)
        )
        validated_exports: Mapping[str, LoadedWorkflowBundle]
        if validate_shared or requires_internal_bundle_validation:
            validated_exports = validate_lowered_workflows(
                lowered_workflows,
                workspace_root=workspace_root,
                imported_workflow_bundles=effective_imported_bundles,
            )
        else:
            validated_exports = {}
        result = Stage3CompileResult(
            module=definition_module,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            typed_procedures=typed_procedures,
            typed_workflows=typed_workflows,
            lowered_workflows=lowered_workflows,
            validated_bundles=validated_exports if validate_shared else {},
            diagnostics=_collect_stage3_required_lint_diagnostics(typed_workflows),
        )
        compiled_results_by_name[module_name] = result
        aggregate_diagnostics.extend(result.diagnostics)
        exported_type_refs_by_module[module_name] = _exported_type_refs(
            definition_module,
            export_surfaces[module_name],
            type_env,
        )
        exported_macro_defs_by_module[module_name] = {
            name: macro_def
            for name, macro_def in collect_macro_catalog(module_source.syntax_module).definitions_by_name.items()
            if name in export_surfaces[module_name].macros_by_name
        }
        exported_function_signatures_by_module[module_name] = {
            name: function_catalog.signatures_by_name[binding.canonical_name]
            for name, binding in export_surfaces[module_name].functions_by_name.items()
        }
        exported_procedure_signatures_by_module[module_name] = {
            name: procedure_catalog.signatures_by_name[binding.canonical_name]
            for name, binding in export_surfaces[module_name].procedures_by_name.items()
        }
        exported_workflow_signatures_by_module[module_name] = {
            name: workflow_catalog.signatures_by_name[binding.canonical_name]
            for name, binding in export_surfaces[module_name].workflows_by_name.items()
        }
        for procedure in typed_procedures:
            typed_procedures_by_name[procedure.definition.name] = procedure
            procedure_effects_by_name[procedure.definition.name] = procedure.transitive_effect_summary
        for function in typed_functions:
            typed_functions_by_name[function.definition.name] = function
        for workflow in typed_workflows:
            workflow_effects_by_name[workflow.definition.name] = workflow.effect_summary
        if validated_exports:
            for binding in export_surfaces[module_name].workflows_by_name.values():
                exported_validated_bundles_by_name[binding.canonical_name] = validated_exports[binding.canonical_name]

    return LinkedStage3CompileResult(
        graph=LinkedModuleGraph(
            entry_module_name=graph.entry_module_name,
            modules_by_name=graph.modules_by_name,
            topological_order=graph.topological_order,
            export_surfaces_by_name=export_surfaces,
        ),
        entry_result=compiled_results_by_name[graph.entry_module_name],
        compiled_results_by_name=compiled_results_by_name,
        validated_bundles_by_name=exported_validated_bundles_by_name,
        diagnostics=tuple(aggregate_diagnostics),
    )


def _definition_only_from_expanded_syntax_module(
    module_syntax: WorkflowLispSyntaxModule,
) -> WorkflowLispSyntaxModule:
    """Strip executable forms from expanded syntax for type-definition passes."""

    definition_forms = []
    for form in module_syntax.forms:
        head_name = syntax_head_name(syntax_node_datum(form))
        if head_name in {"defworkflow", "defun", "defproc", "defmacro"}:
            continue
        definition_forms.append(form)
    return WorkflowLispSyntaxModule(
        language_version=module_syntax.language_version,
        target_dsl_version=module_syntax.target_dsl_version,
        module_directive=module_syntax.module_directive,
        imports=module_syntax.imports,
        export_directive=module_syntax.export_directive,
        forms=tuple(definition_forms),
        span=module_syntax.span,
        module_path=module_syntax.module_path,
    )


def _canonicalize_procedure_defs(
    module_name: str,
    procedure_defs: tuple[ProcedureDef, ...],
) -> tuple[ProcedureDef, ...]:
    """Qualify local procedure names with their module name."""

    return tuple(
        replace(procedure_def, name=canonical_callable_key(module_name, procedure_def.name))
        for procedure_def in procedure_defs
    )


def _canonicalize_function_defs(
    module_name: str,
    function_defs: tuple[FunctionDef, ...],
) -> tuple[FunctionDef, ...]:
    """Qualify local helper names with their module name."""

    return tuple(
        replace(function_def, name=canonical_callable_key(module_name, function_def.name))
        for function_def in function_defs
    )


def _canonicalize_workflow_defs(
    module_name: str,
    workflow_defs: tuple[WorkflowDef, ...],
) -> tuple[WorkflowDef, ...]:
    """Qualify local workflow names with their module name."""

    return tuple(
        replace(workflow_def, name=canonical_callable_key(module_name, workflow_def.name))
        for workflow_def in workflow_defs
    )


def _local_callable_lookup_aliases(
    module_name: str,
    *,
    raw_names: tuple[str, ...],
    imported_bindings: Mapping[str, ModuleMemberBinding],
) -> dict[str, str]:
    """Build call-name aliases for local and imported procedures/workflows."""

    aliases = {
        alias_name: binding.canonical_name
        for alias_name, binding in imported_bindings.items()
    }
    for raw_name in raw_names:
        aliases[raw_name] = canonical_callable_key(module_name, raw_name)
    return aliases


def _imported_type_refs(
    import_scope: ModuleImportScope,
    exported_type_refs_by_module: Mapping[str, Mapping[str, TypeRef]],
) -> dict[str, TypeRef]:
    """Collect concrete type refs made visible by the import scope."""

    imported: dict[str, TypeRef] = {}
    seen_bindings = {
        **dict(import_scope.type_bindings),
        **dict(import_scope.unqualified_type_bindings),
    }
    for binding in seen_bindings.values():
        type_ref = exported_type_refs_by_module.get(binding.module_name, {}).get(binding.member_name)
        if type_ref is not None:
            imported[binding.canonical_name] = type_ref
    return imported


def _imported_schema_defs(
    import_scope: ModuleImportScope,
    exported_schema_defs_by_module: Mapping[str, Mapping[str, SchemaDef]],
) -> dict[str, SchemaDef]:
    """Collect schema definitions visible through imports."""

    imported: dict[str, SchemaDef] = {}
    seen_bindings = {
        **dict(import_scope.schema_bindings),
        **dict(import_scope.unqualified_schema_bindings),
    }
    for binding in seen_bindings.values():
        schema_def = exported_schema_defs_by_module.get(binding.module_name, {}).get(binding.member_name)
        if schema_def is not None:
            imported[binding.canonical_name] = schema_def
    return imported


def _exported_type_refs(
    module: WorkflowLispModule,
    export_surface: ModuleExportSurface,
    type_env: FrontendTypeEnvironment,
) -> dict[str, TypeRef]:
    """Resolve exported type names into the refs downstream modules import."""

    exported: dict[str, TypeRef] = {}
    for binding in export_surface.types_by_name.values():
        exported[binding.member_name] = type_env.resolve_type(
            binding.member_name,
            span=module.span,
            form_path=("workflow-lisp", binding.member_name),
        )
    return exported


def _exported_schema_defs(
    module: WorkflowLispModule,
    export_surface: ModuleExportSurface,
    *,
    import_scope: ModuleImportScope | None = None,
    imported_schema_defs: Mapping[str, SchemaDef] | None = None,
) -> dict[str, SchemaDef]:
    """Resolve exported schema names into importer-ready frontend metadata."""

    local_schema_by_name = {schema.name: schema for schema in module.schemas}
    imported_schema_map = dict(imported_schema_defs or {})
    schema_cache: dict[str, tuple[RecordField, ...]] = {}
    active_schema_stack: list[str] = []
    exported: dict[str, SchemaDef] = {}
    for binding in export_surface.schemas_by_name.values():
        schema = local_schema_by_name.get(binding.member_name)
        if schema is None:
            continue
        exported[binding.member_name] = SchemaDef(
            name=binding.canonical_name,
            members=_expand_schema_fields(
                schema.name,
                schema=schema,
                local_schema_map=local_schema_by_name,
                imported_schema_map=imported_schema_map,
                import_scope=import_scope,
                schema_cache=schema_cache,
                active_schema_stack=active_schema_stack,
                include_span=schema.span,
                form_path=("workflow-lisp", "defschema", schema.name),
            ),
            span=schema.span,
        )
    return exported


def _imported_procedure_signatures(
    import_scope: ModuleImportScope,
    exported_by_module: Mapping[str, Mapping[str, ProcedureSignature]],
) -> dict[str, ProcedureSignature]:
    """Collect procedure signatures visible through imports."""

    imported: dict[str, ProcedureSignature] = {}
    for binding in import_scope.procedure_bindings.values():
        signature = exported_by_module.get(binding.module_name, {}).get(binding.member_name)
        if signature is not None:
            imported[binding.canonical_name] = signature
    return imported


def _imported_function_signatures(
    import_scope: ModuleImportScope,
    exported_by_module: Mapping[str, Mapping[str, FunctionSignature]],
) -> dict[str, FunctionSignature]:
    """Collect helper signatures visible through imports."""

    imported: dict[str, FunctionSignature] = {}
    for binding in import_scope.function_bindings.values():
        signature = exported_by_module.get(binding.module_name, {}).get(binding.member_name)
        if signature is not None:
            imported[binding.canonical_name] = signature
    return imported


def _imported_workflow_signatures(
    import_scope: ModuleImportScope,
    exported_by_module: Mapping[str, Mapping[str, WorkflowSignature]],
) -> dict[str, WorkflowSignature]:
    """Collect workflow signatures visible through imports."""

    imported: dict[str, WorkflowSignature] = {}
    for binding in import_scope.workflow_bindings.values():
        signature = exported_by_module.get(binding.module_name, {}).get(binding.member_name)
        if signature is not None:
            imported[binding.canonical_name] = signature
    return imported


def _effective_imported_workflow_bundles(
    import_scope: ModuleImportScope,
    *,
    explicit_imported_bundles: Mapping[str, LoadedWorkflowBundle],
    exported_validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    ) -> dict[str, LoadedWorkflowBundle]:
    """Merge explicit imported bundles with validated bundles from imports."""

    effective = dict(explicit_imported_bundles)
    seen_canonical_names: set[str] = set()
    for binding in import_scope.workflow_bindings.values():
        if binding.canonical_name in seen_canonical_names:
            continue
        seen_canonical_names.add(binding.canonical_name)
        bundle = exported_validated_bundles_by_name.get(binding.canonical_name)
        if bundle is None:
            continue
        if binding.canonical_name in effective:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="module_import_collision",
                        message=f"imported workflow bundle key collision for `{binding.canonical_name}`",
                        span=_bundle_span(bundle),
                        form_path=("workflow-lisp", binding.canonical_name),
                    ),
                )
            )
        effective[binding.canonical_name] = bundle
    return effective


def _procedure_name_resolver(
    module_name: str,
    import_scope: ModuleImportScope,
    *,
    local_raw_names: frozenset[str],
):
    """Return a resolver that maps procedure call syntax to canonical names."""

    local_names: dict[str, str] = {}

    def resolve(name: str, span, form_path):
        if name in local_names:
            return local_names[name]
        if name in local_raw_names:
            resolved = canonical_callable_key(module_name, name)
        else:
            resolved = import_scope.resolve_procedure_name(name, span=span, form_path=form_path)
            if resolved == name:
                resolved = canonical_callable_key(module_name, name)
        local_names[name] = resolved
        return resolved

    return resolve


def _function_name_resolver(
    module_name: str,
    import_scope: ModuleImportScope,
    *,
    local_raw_names: frozenset[str],
):
    """Return a resolver that maps helper call syntax to canonical names."""

    local_names: dict[str, str] = {}

    def resolve(name: str, span, form_path):
        if name in local_names:
            return local_names[name]
        if name in local_raw_names:
            resolved = canonical_callable_key(module_name, name)
        else:
            resolved = import_scope.resolve_function_name(name, span=span, form_path=form_path)
            if resolved == name:
                resolved = canonical_callable_key(module_name, name)
        local_names[name] = resolved
        return resolved

    return resolve


def _workflow_name_resolver(
    module_name: str,
    import_scope: ModuleImportScope,
    *,
    local_raw_names: frozenset[str],
    external_workflow_names: frozenset[str] = frozenset(),
):
    """Return a resolver that maps workflow call syntax to canonical names."""

    local_names: dict[str, str] = {}

    def resolve(name: str, span, form_path):
        if name in local_names:
            return local_names[name]
        if name in local_raw_names:
            resolved = canonical_callable_key(module_name, name)
        else:
            resolved = import_scope.resolve_workflow_name(name, span=span, form_path=form_path)
            if resolved == name:
                if name in external_workflow_names:
                    resolved = name
                else:
                    resolved = canonical_callable_key(module_name, name)
        local_names[name] = resolved
        return resolved

    return resolve


def _bundle_span(bundle: LoadedWorkflowBundle):
    """Create a source span pointing at an imported workflow bundle file."""

    from .spans import SourcePosition, SourceSpan

    workflow_path = bundle.provenance.workflow_path
    return SourceSpan(
        start=SourcePosition(path=str(workflow_path), line=1, column=1, offset=0),
        end=SourcePosition(path=str(workflow_path), line=1, column=1, offset=0),
    )


def _expanded_syntax_module(path: Path) -> WorkflowLispSyntaxModule:
    """Read, wrap, and macro-expand one Workflow Lisp source file."""

    parse_tree = read_sexpr_file(path)
    syntax_module = build_syntax_module(parse_tree)
    catalog = collect_macro_catalog(syntax_module)
    return expand_module_forms(syntax_module, catalog=catalog)


def _augment_resume_command_boundaries(
    command_boundary_environment,
    *,
    expressions,
):
    """Install resume/state-reuse adapters only when code uses `resume-or-start`."""

    bindings = dict(command_boundary_environment.bindings_by_name)
    resume_exprs = list(expressions)
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
        negative_fixture_ids=(
            "resume_state_pointer_authority_forbidden",
            "resume_state_contract_fingerprint_mismatch",
            "resume_state_bundle_schema_invalid",
        ),
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


def _augment_resource_transition_command_boundaries(command_boundary_environment):
    """Register the default adapter used by `resource-transition`.

    The frontend form lowers through a named command boundary. This helper adds
    the repository's built-in adapter when the caller did not provide an
    override, including the declared output type, effects, path-safety policy,
    and fixture ids required for certification.
    """

    bindings = dict(command_boundary_environment.bindings_by_name)
    if "apply_resource_transition" in bindings:
        return command_boundary_environment
    bindings["apply_resource_transition"] = CertifiedAdapterBinding(
        name="apply_resource_transition",
        stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.apply_resource_transition"),
        input_contract={"type": "object"},
        output_type_name="ResourceTransitionResult",
        effects=("resource_transition", "ledger_update"),
        path_safety={"kind": "workspace_relpath"},
        source_map_behavior="step",
        fixture_ids=("resource_transition_ok",),
        negative_fixture_ids=("resource_transition_bad",),
    )
    return build_command_boundary_environment(bindings)


def _workflow_contains_resume_or_start(expr) -> bool:
    """Return whether an expression tree contains a `resume-or-start` form."""

    if isinstance(expr, SyntaxNode):
        return _workflow_contains_resume_or_start(syntax_node_datum(expr))
    if isinstance(expr, SyntaxList):
        if syntax_head_name(expr) == "resume-or-start":
            return True
        return any(_workflow_contains_resume_or_start(item) for item in expr.items)
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
    """Collect result types that require resume-state loader adapters."""

    if isinstance(expr, SyntaxNode):
        return _resume_return_type_names(syntax_node_datum(expr))
    if isinstance(expr, SyntaxList):
        names: list[str] = []
        if syntax_head_name(expr) == "resume-or-start":
            for index, item in enumerate(expr.items[:-1]):
                if getattr(item, "value", None) != ":returns":
                    continue
                return_identifier = syntax_identifier(expr.items[index + 1])
                if return_identifier is not None:
                    names.append(return_identifier.resolved_name)
                break
        for item in expr.items:
            names.extend(_resume_return_type_names(item))
        return tuple(names)
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


def _validate_local_callable_name_collisions(
    function_defs: tuple[FunctionDef, ...],
    procedure_defs: tuple[ProcedureDef, ...],
) -> None:
    """Reject same-file helper/procedure direct-head collisions."""

    function_by_name = {function.name: function for function in function_defs}
    for procedure_def in procedure_defs:
        function_def = function_by_name.get(procedure_def.name)
        if function_def is None:
            continue
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="callable_name_collision",
                    message=f"callable name `{procedure_def.name}` is defined as both a function and procedure",
                    span=procedure_def.span,
                    form_path=procedure_def.form_path,
                    expansion_stack=procedure_def.expansion_stack,
                ),
            )
        )


def _validate_visible_callable_name_collisions(
    *,
    function_defs: tuple[FunctionDef, ...],
    procedure_defs: tuple[ProcedureDef, ...],
    import_scope: ModuleImportScope,
) -> None:
    """Reject helper/procedure collisions in the visible direct-head namespace."""

    _validate_local_callable_name_collisions(function_defs, procedure_defs)

    local_function_names = {function.name for function in function_defs}
    local_procedure_names = {procedure.name for procedure in procedure_defs}
    for name in local_function_names & {
        binding_name
        for binding_name in import_scope.procedure_bindings
        if "." not in binding_name and "/" not in binding_name
    }:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="callable_name_collision",
                    message=f"local function `{name}` collides with an imported procedure of the same name",
                    span=next(function.span for function in function_defs if function.name == name),
                    form_path=next(function.form_path for function in function_defs if function.name == name),
                ),
            )
        )
    for name in local_procedure_names & {
        binding_name
        for binding_name in import_scope.function_bindings
        if "." not in binding_name and "/" not in binding_name
    }:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="callable_name_collision",
                    message=f"local procedure `{name}` collides with an imported function of the same name",
                    span=next(procedure.span for procedure in procedure_defs if procedure.name == name),
                    form_path=next(procedure.form_path for procedure in procedure_defs if procedure.name == name),
                ),
            )
        )


def _validate_definition_module(
    module: WorkflowLispModule,
    *,
    import_scope: ModuleImportScope | None = None,
) -> None:
    """Validate definition names and type references for one module."""

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
    for schema in module.schemas:
        if schema.name in definition_names:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="definition_duplicate",
                    message=f"duplicate definition `{schema.name}`",
                    span=schema.span,
                    form_path=_definition_form_path(schema),
                )
            )
        else:
            definition_names[schema.name] = schema

    imported_type_names = frozenset()
    visible_schema_names = frozenset(schema.name for schema in module.schemas)
    if import_scope is not None:
        imported_type_names = frozenset(
            binding.canonical_name
            for binding in (
                *import_scope.type_bindings.values(),
                *import_scope.unqualified_type_bindings.values(),
            )
        )
        visible_schema_names = visible_schema_names | frozenset(import_scope.schema_bindings) | frozenset(
            import_scope.unqualified_schema_bindings
        )

    available_type_names = PRELUDE_TYPE_NAMES | frozenset(
        name for name, definition in definition_names.items() if not isinstance(definition, SchemaDef)
    ) | imported_type_names
    for definition in module.definitions:
        if isinstance(definition, RecordDef):
            diagnostics.extend(_validate_field_list(definition.fields, _definition_form_path(definition)))
            diagnostics.extend(
                _validate_field_types(
                    definition.fields,
                    _definition_form_path(definition),
                    available_type_names,
                    visible_schema_names=visible_schema_names,
                    import_scope=import_scope,
                )
            )
        elif isinstance(definition, UnionDef):
            diagnostics.extend(
                _validate_union_definition(
                    definition,
                    available_type_names,
                    visible_schema_names=visible_schema_names,
                    import_scope=import_scope,
                )
            )

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))


def _validate_union_definition(
    definition: UnionDef,
    available_type_names: frozenset[str],
    *,
    visible_schema_names: frozenset[str],
    import_scope: ModuleImportScope | None,
) -> list[LispFrontendDiagnostic]:
    """Validate one union's variant names and variant field types."""

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
        diagnostics.extend(
            _validate_field_types(
                variant.fields,
                form_path,
                available_type_names,
                visible_schema_names=visible_schema_names,
                import_scope=import_scope,
            )
        )
    return diagnostics


def _validate_field_list(
    fields: tuple[RecordField, ...],
    form_path: tuple[str, ...],
    *,
    scope_label: str = "record",
) -> list[LispFrontendDiagnostic]:
    """Validate duplicate field names for a record-like field list."""

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
    *,
    visible_schema_names: frozenset[str],
    import_scope: ModuleImportScope | None,
) -> list[LispFrontendDiagnostic]:
    """Validate that each field references a known type name."""

    diagnostics: list[LispFrontendDiagnostic] = []
    for field in fields:
        try:
            parsed = parse_type_expression(
                field.type_name,
                span=field.span,
                form_path=form_path,
            )
            diagnostics.extend(
                _validate_parsed_field_type(
                    parsed,
                    authored_name=field.type_name,
                    span=field.span,
                    form_path=form_path,
                    available_type_names=available_type_names,
                    visible_schema_names=visible_schema_names,
                    import_scope=import_scope,
                )
            )
        except LispFrontendCompileError as exc:
            diagnostics.extend(exc.diagnostics)
    return diagnostics


def _validate_parsed_field_type(
    parsed: NamedTypeExpr | WorkflowRefTypeExpr | ProcRefTypeExpr | OptionalTypeExpr | ListTypeExpr | MapTypeExpr,
    *,
    authored_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    available_type_names: frozenset[str],
    visible_schema_names: frozenset[str],
    import_scope: ModuleImportScope | None,
) -> list[LispFrontendDiagnostic]:
    diagnostics: list[LispFrontendDiagnostic] = []
    if isinstance(parsed, NamedTypeExpr):
        if parsed.name in visible_schema_names or (
            import_scope is not None and import_scope.has_visible_schema_name(parsed.name)
        ):
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="schema_used_as_type",
                    message=f"schema `{parsed.name}` cannot be used as a type",
                    span=span,
                    form_path=form_path,
                )
            )
            return diagnostics
        if parsed.name not in available_type_names:
            resolved_name = (
                import_scope.resolve_type_name(
                    parsed.name,
                    span=span,
                    form_path=form_path,
                )
                if import_scope is not None
                else parsed.name
            )
            if resolved_name not in available_type_names:
                diagnostics.append(
                    LispFrontendDiagnostic(
                        code="type_unknown",
                        message=f"unknown type `{parsed.name}`",
                        span=span,
                        form_path=form_path,
                    )
                )
        return diagnostics
    if isinstance(parsed, WorkflowRefTypeExpr):
        for param_type in parsed.param_types:
            diagnostics.extend(
                _validate_parsed_field_type(
                    param_type,
                    authored_name=authored_name,
                    span=span,
                    form_path=form_path,
                    available_type_names=available_type_names,
                    visible_schema_names=visible_schema_names,
                    import_scope=import_scope,
                )
            )
        diagnostics.extend(
            _validate_parsed_field_type(
                parsed.return_type,
                authored_name=authored_name,
                span=span,
                form_path=form_path,
                available_type_names=available_type_names,
                visible_schema_names=visible_schema_names,
                import_scope=import_scope,
            )
        )
        return diagnostics
    if isinstance(parsed, ProcRefTypeExpr):
        for param_type in parsed.param_types:
            diagnostics.extend(
                _validate_parsed_field_type(
                    param_type,
                    authored_name=authored_name,
                    span=span,
                    form_path=form_path,
                    available_type_names=available_type_names,
                    visible_schema_names=visible_schema_names,
                    import_scope=import_scope,
                )
            )
        diagnostics.extend(
            _validate_parsed_field_type(
                parsed.return_type,
                authored_name=authored_name,
                span=span,
                form_path=form_path,
                available_type_names=available_type_names,
                visible_schema_names=visible_schema_names,
                import_scope=import_scope,
            )
        )
        return diagnostics
    if isinstance(parsed, (OptionalTypeExpr, ListTypeExpr)):
        return _validate_parsed_field_type(
            parsed.item_type,
            authored_name=authored_name,
            span=span,
            form_path=form_path,
            available_type_names=available_type_names,
            visible_schema_names=visible_schema_names,
            import_scope=import_scope,
        )
    if isinstance(parsed, MapTypeExpr):
        key_diagnostics = _validate_parsed_field_type(
            parsed.key_type,
            authored_name=authored_name,
            span=span,
            form_path=form_path,
            available_type_names=available_type_names,
            visible_schema_names=visible_schema_names,
            import_scope=import_scope,
        )
        diagnostics.extend(key_diagnostics)
        if not (
            isinstance(parsed.key_type, NamedTypeExpr)
            and (
                parsed.key_type.name == "String"
                or (
                    import_scope is not None
                    and import_scope.resolve_type_name(
                        parsed.key_type.name,
                        span=span,
                        form_path=form_path,
                    )
                    == "String"
                )
            )
        ):
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="collection_key_type_invalid",
                    message=f"`Map` keys must resolve to `String` in `{authored_name}`",
                    span=span,
                    form_path=form_path,
                )
            )
        diagnostics.extend(
            _validate_parsed_field_type(
                parsed.value_type,
                authored_name=authored_name,
                span=span,
                form_path=form_path,
                available_type_names=available_type_names,
                visible_schema_names=visible_schema_names,
                import_scope=import_scope,
            )
        )
        return diagnostics
    raise TypeError(f"unsupported parsed field type: {type(parsed)!r}")


def _definition_form_path(definition: EnumDef | PathDef | RecordDef | UnionDef | SchemaDef) -> tuple[str, ...]:
    """Return a stable frontend form path for a type definition."""

    if isinstance(definition, EnumDef):
        return ("workflow-lisp", "defenum", definition.name)
    if isinstance(definition, PathDef):
        return ("workflow-lisp", "defpath", definition.name)
    if isinstance(definition, SchemaDef):
        return ("workflow-lisp", "defschema", definition.name)
    if isinstance(definition, RecordDef):
        return ("workflow-lisp", "defrecord", definition.name)
    return ("workflow-lisp", "defunion", definition.name)


def _validate_stage1_top_level_forms(module_syntax: WorkflowLispSyntaxModule) -> None:
    """Reject executable top-level forms in definition-only compilation."""

    allowed_heads = {"defenum", "defpath", "defschema", "defrecord", "defunion", "defworkflow", "defun", "defproc"}
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
    """Expand syntax and keep only forms used by definition elaboration."""

    expanded_module = expand_module_forms(
        module_syntax,
        catalog=collect_macro_catalog(module_syntax),
    )
    definition_forms = []
    for form in expanded_module.forms:
        head_name = syntax_head_name(syntax_node_datum(form))
        if head_name in {"defworkflow", "defun", "defproc", "defmacro"}:
            continue
        definition_forms.append(form)
    return WorkflowLispSyntaxModule(
        language_version=expanded_module.language_version,
        target_dsl_version=expanded_module.target_dsl_version,
        module_directive=expanded_module.module_directive,
        imports=expanded_module.imports,
        export_directive=expanded_module.export_directive,
        forms=tuple(definition_forms),
        span=expanded_module.span,
        module_path=expanded_module.module_path,
    )


def _typecheck_procedure_definitions(
    procedure_defs: tuple[ProcedureDef | TypedProcedureDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    workflow_catalog: object,
    procedure_catalog: ProcedureCatalog,
    function_catalog: FunctionCatalog | None = None,
    extern_environment: object,
    command_boundary_environment: object,
    procedure_effects_by_name: Mapping[str, EffectSummary] | None = None,
    workflow_effects_by_name: Mapping[str, EffectSummary] | None = None,
    function_name_resolver=None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
    proc_ref_resolution_context: ProcRefResolutionContext | None = None,
) -> tuple[TypedProcedureDef, ...]:
    """Typecheck procedure bodies against signatures, externs, and call catalogs."""

    from .workflows import ExternEnvironment, ProviderExtern

    externs = extern_environment or ExternEnvironment(bindings_by_name={})
    typed_procedures: list[TypedProcedureDef] = []
    for procedure_target in procedure_defs:
        if isinstance(procedure_target, TypedProcedureDef):
            procedure_def = procedure_target.definition
            signature = procedure_target.signature
            specialization = procedure_target.specialization
        else:
            procedure_def = procedure_target
            signature = procedure_catalog.signatures_by_name[procedure_def.name]
            specialization = None
        value_env = {name: type_ref for name, type_ref in signature.params}
        proc_ref_value_env = {}
        if specialization is not None:
            value_env.update(dict(getattr(specialization, "bound_param_types", {})))
            proc_ref_value_env.update(dict(getattr(specialization, "proc_ref_bindings", {})))
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
            function_names=(
                frozenset()
                if function_catalog is None
                else frozenset(function_catalog.signatures_by_name)
            ),
            function_name_resolver=function_name_resolver,
            procedure_name_resolver=procedure_name_resolver,
            workflow_name_resolver=workflow_name_resolver,
        )
        typed_body = typecheck_expression(
            body_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            function_catalog=function_catalog,
            extern_environment=externs,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
            proc_ref_value_env=proc_ref_value_env,
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
                specialization=specialization,
            )
        )
    return tuple(typed_procedures)


def _procedure_catalog_with_specializations(
    procedure_catalog: ProcedureCatalog,
    typed_procedures: tuple[TypedProcedureDef, ...],
) -> ProcedureCatalog:
    signatures_by_name = dict(procedure_catalog.signatures_by_name)
    definitions_by_name = dict(procedure_catalog.definitions_by_name)
    for procedure in typed_procedures:
        signatures_by_name[procedure.signature.name] = procedure.signature
        definitions_by_name[procedure.definition.name] = procedure.definition
    return ProcedureCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
        call_graph=procedure_catalog.call_graph,
    )


def _bound_proc_ref_request(
    resolved: ResolvedProcRefValue,
    *,
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    procedure_catalog: ProcedureCatalog,
    proc_ref_env: Mapping[str, ResolvedProcRefValue],
    type_env: FrontendTypeEnvironment,
    origin_span=None,
    origin_form_path: tuple[str, ...] | None = None,
) -> TypedProcedureDef | None:
    from .lowering import _specialize_typed_procedure

    if not resolved.bound_args:
        return None
    base_procedure = typed_procedures_by_name.get(resolved.procedure_name)
    if base_procedure is None:
        return None
    proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
    value_bindings: dict[str, object] = {}
    for binding in resolved.bound_args:
        if isinstance(binding.type_ref, ProcRefTypeRef):
            resolved_binding = resolve_proc_ref_value(
                binding.value_expr,
                procedure_catalog=procedure_catalog,
                proc_ref_env=proc_ref_env,
                expected_type=binding.type_ref,
            )
            if resolved_binding is not None:
                proc_ref_bindings[binding.name] = resolved_binding
            continue
        value_bindings[binding.name] = binding.value_expr
    return _specialize_typed_procedure(
        base_procedure,
        proc_ref_bindings=proc_ref_bindings,
        value_bindings=value_bindings,
        remaining_params=resolved.residual_params,
        workflow_path=Path(base_procedure.definition.span.start.path),
        type_env=type_env,
        typed_procedures_by_name=typed_procedures_by_name,
        specialized_name=resolved.call_target_name,
        origin_span=origin_span,
        origin_form_path=origin_form_path,
    )


def _discover_proc_ref_specializations(
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    typed_workflows: tuple[TypedWorkflowDef, ...],
    procedure_catalog: ProcedureCatalog,
    type_env: FrontendTypeEnvironment,
) -> tuple[TypedProcedureDef, ...]:
    from .expressions import (
        BacklogDrainExpr,
        BindProcExpr,
        CallExpr,
        CommandResultExpr,
        ContinueExpr,
        DoneExpr,
        FinalizeSelectedItemExpr,
        IfExpr,
        LetStarExpr,
        LoopRecurExpr,
        MatchExpr,
        ProcedureCallExpr,
        ProcRefLiteralExpr,
        ProduceOneOfExpr,
        ProviderResultExpr,
        RecordExpr,
        ResourceTransitionExpr,
        ResumeOrStartExpr,
        ReviewReviseLoopExpr,
        RunProviderPhaseExpr,
        WithPhaseExpr,
    )

    discovered: dict[str, TypedProcedureDef] = {}
    typed_procedures_by_name = {procedure.definition.name: procedure for procedure in typed_procedures}

    def record_specialization(
        specialized: TypedProcedureDef | None,
    ) -> None:
        if specialized is None:
            return
        if specialized.definition.name in typed_procedures_by_name:
            return
        discovered.setdefault(specialized.definition.name, specialized)

    def walk(node: object, proc_ref_env: Mapping[str, ResolvedProcRefValue]) -> None:
        if isinstance(node, ProcedureCallExpr):
            bound_proc_ref = proc_ref_env.get(node.callee_name)
            if bound_proc_ref is not None:
                record_specialization(
                    _bound_proc_ref_request(
                        bound_proc_ref,
                        typed_procedures_by_name=typed_procedures_by_name,
                        procedure_catalog=procedure_catalog,
                        proc_ref_env=proc_ref_env,
                        type_env=type_env,
                        origin_span=node.span,
                        origin_form_path=node.form_path,
                    )
                )
            else:
                signature = procedure_catalog.signatures_by_name.get(node.callee_name)
                if signature is not None:
                    proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
                    for arg_expr, (param_name, param_type) in zip(node.args, signature.params, strict=True):
                        if not isinstance(param_type, ProcRefTypeRef):
                            continue
                        resolved_binding = resolve_proc_ref_value(
                            arg_expr,
                            procedure_catalog=procedure_catalog,
                            proc_ref_env=proc_ref_env,
                            expected_type=param_type,
                        )
                        if resolved_binding is not None:
                            proc_ref_bindings[param_name] = resolved_binding
                    if proc_ref_bindings:
                        from .lowering import _specialize_typed_procedure

                        base_procedure = typed_procedures_by_name.get(signature.name)
                        if base_procedure is not None:
                            record_specialization(
                                _specialize_typed_procedure(
                                    base_procedure,
                                    proc_ref_bindings=proc_ref_bindings,
                                    remaining_params=tuple(
                                        (param_name, param_type)
                                        for param_name, param_type in signature.params
                                        if param_name not in proc_ref_bindings
                                    ),
                                    workflow_path=Path(base_procedure.definition.span.start.path),
                                    type_env=type_env,
                                    typed_procedures_by_name=typed_procedures_by_name,
                                    specialized_name=proc_ref_call_specialization_name(
                                        signature.name,
                                        proc_ref_bindings,
                                    ),
                                    origin_span=node.span,
                                    origin_form_path=node.form_path,
                                )
                            )
            for arg in node.args:
                walk(arg, proc_ref_env)
            return
        if isinstance(node, LetStarExpr):
            child_env = dict(proc_ref_env)
            for binding_name, binding_expr in node.bindings:
                walk(binding_expr, child_env)
                resolved_binding = resolve_proc_ref_value(
                    binding_expr,
                    procedure_catalog=procedure_catalog,
                    proc_ref_env=child_env,
                )
                if resolved_binding is not None:
                    child_env[binding_name] = resolved_binding
            walk(node.body, child_env)
            return
        if isinstance(node, MatchExpr):
            walk(node.subject, proc_ref_env)
            for arm in node.arms:
                walk(arm.body, proc_ref_env)
            return
        if isinstance(node, IfExpr):
            walk(node.condition_expr, proc_ref_env)
            walk(node.then_expr, proc_ref_env)
            walk(node.else_expr, proc_ref_env)
            return
        if isinstance(node, LoopRecurExpr):
            walk(node.max_iterations_expr, proc_ref_env)
            walk(node.initial_state_expr, proc_ref_env)
            walk(node.body_expr, proc_ref_env)
            return
        if isinstance(node, ContinueExpr):
            walk(node.state_expr, proc_ref_env)
            return
        if isinstance(node, DoneExpr):
            walk(node.result_expr, proc_ref_env)
            return
        if isinstance(node, RecordExpr):
            for _, field_expr in node.fields:
                walk(field_expr, proc_ref_env)
            return
        if isinstance(node, CallExpr):
            for _, binding_expr in node.bindings:
                walk(binding_expr, proc_ref_env)
            return
        if isinstance(node, ProviderResultExpr):
            walk(node.provider, proc_ref_env)
            walk(node.prompt, proc_ref_env)
            for input_expr in node.inputs:
                walk(input_expr, proc_ref_env)
            return
        if isinstance(node, CommandResultExpr):
            for argv_expr in node.argv:
                walk(argv_expr, proc_ref_env)
            return
        if isinstance(node, RunProviderPhaseExpr):
            walk(node.ctx_expr, proc_ref_env)
            walk(node.inputs_expr, proc_ref_env)
            walk(node.provider, proc_ref_env)
            walk(node.prompt, proc_ref_env)
            return
        if isinstance(node, ProduceOneOfExpr):
            walk(node.ctx_expr, proc_ref_env)
            if node.producer.provider_expr is not None:
                walk(node.producer.provider_expr, proc_ref_env)
            if node.producer.prompt_expr is not None:
                walk(node.producer.prompt_expr, proc_ref_env)
            for input_expr in node.producer.inputs:
                walk(input_expr, proc_ref_env)
            for candidate in node.candidates:
                for field in candidate.fields:
                    if field.target_expr is not None:
                        walk(field.target_expr, proc_ref_env)
            return
        if isinstance(node, ReviewReviseLoopExpr):
            walk(node.ctx_expr, proc_ref_env)
            walk(node.completed_expr, proc_ref_env)
            walk(node.inputs_expr, proc_ref_env)
            walk(node.review_provider, proc_ref_env)
            walk(node.fix_provider, proc_ref_env)
            walk(node.review_prompt, proc_ref_env)
            walk(node.fix_prompt, proc_ref_env)
            walk(node.max_expr, proc_ref_env)
            return
        if isinstance(node, ResumeOrStartExpr):
            walk(node.ctx_expr, proc_ref_env)
            walk(node.resume_from_expr, proc_ref_env)
            walk(node.start_expr, proc_ref_env)
            return
        if isinstance(node, ResourceTransitionExpr):
            walk(node.spec.ctx_expr, proc_ref_env)
            if node.spec.when_expr is not None:
                walk(node.spec.when_expr, proc_ref_env)
            walk(node.spec.resource_expr, proc_ref_env)
            walk(node.spec.ledger_expr, proc_ref_env)
            return
        if isinstance(node, FinalizeSelectedItemExpr):
            walk(node.spec.ctx_expr, proc_ref_env)
            walk(node.spec.selected_expr, proc_ref_env)
            walk(node.spec.queue_transition_expr, proc_ref_env)
            walk(node.spec.roadmap_expr, proc_ref_env)
            walk(node.spec.plan_expr, proc_ref_env)
            walk(node.spec.implementation_expr, proc_ref_env)
            return
        if isinstance(node, BacklogDrainExpr):
            walk(node.spec.ctx_expr, proc_ref_env)
            if node.spec.providers_expr is not None:
                walk(node.spec.providers_expr, proc_ref_env)
            walk(node.spec.max_iterations_expr, proc_ref_env)
            return
        if isinstance(node, WithPhaseExpr):
            walk(node.ctx_expr, proc_ref_env)
            walk(node.body, proc_ref_env)
            return
        if isinstance(node, BindProcExpr):
            walk(node.base_expr, proc_ref_env)
            for binding in node.bindings:
                walk(binding.value_expr, proc_ref_env)
            return
        if isinstance(node, ProcRefLiteralExpr):
            return

    for procedure in typed_procedures:
        proc_ref_env = dict(getattr(procedure.specialization, "proc_ref_bindings", {}))
        walk(procedure.typed_body.expr, proc_ref_env)
    for workflow in typed_workflows:
        walk(workflow.typed_body.expr, {})
    return tuple(discovered.values())


def _infer_stage3_effect_summaries(
    procedure_defs: tuple[ProcedureDef, ...],
    *,
    workflow_defs: tuple[object, ...],
    type_env: FrontendTypeEnvironment,
    workflow_catalog: object,
    procedure_catalog: ProcedureCatalog,
    function_catalog: FunctionCatalog | None = None,
    extern_environment: object,
    command_boundary_environment: object,
    procedure_effects_by_name: Mapping[str, EffectSummary] | None = None,
    workflow_effects_by_name: Mapping[str, EffectSummary] | None = None,
    function_name_resolver=None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
    proc_ref_resolution_context: ProcRefResolutionContext | None = None,
) -> tuple[tuple[TypedProcedureDef, ...], tuple[object, ...], ProcedureCatalog]:
    """Compute procedure/workflow effect summaries to a fixpoint."""

    procedure_effects_by_name = dict(procedure_effects_by_name or {})
    workflow_effects_by_name = dict(workflow_effects_by_name or {})
    procedure_targets: dict[str, ProcedureDef | TypedProcedureDef] = {
        procedure_def.name: procedure_def for procedure_def in procedure_defs
    }
    typed_procedures: tuple[TypedProcedureDef, ...] = ()
    typed_workflows: tuple[object, ...] = ()

    max_iterations = max(1, len(procedure_defs) + len(workflow_defs)) * 8
    for _ in range(max_iterations):
        typed_procedures = _typecheck_procedure_definitions(
            tuple(procedure_targets.values()),
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            function_catalog=function_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            function_name_resolver=function_name_resolver,
            procedure_name_resolver=procedure_name_resolver,
            workflow_name_resolver=workflow_name_resolver,
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
        procedure_catalog = _procedure_catalog_with_specializations(procedure_catalog, typed_procedures)
        discovered_from_procedures = _discover_proc_ref_specializations(
            typed_procedures=typed_procedures,
            typed_workflows=(),
            procedure_catalog=procedure_catalog,
            type_env=type_env,
        )
        added_specialization = False
        for specialized in discovered_from_procedures:
            if specialized.definition.name in procedure_targets:
                continue
            procedure_targets[specialized.definition.name] = specialized
            added_specialization = True
        if added_specialization:
            continue
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
            function_catalog=function_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=next_procedure_effects,
            workflow_effects_by_name=workflow_effects_by_name,
            function_name_resolver=function_name_resolver,
            procedure_name_resolver=procedure_name_resolver,
            workflow_name_resolver=workflow_name_resolver,
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
        discovered_from_workflows = _discover_proc_ref_specializations(
            typed_procedures=typed_procedures,
            typed_workflows=typed_workflows,
            procedure_catalog=procedure_catalog,
            type_env=type_env,
        )
        added_specialization = False
        for specialized in discovered_from_workflows:
            if specialized.definition.name in procedure_targets:
                continue
            procedure_targets[specialized.definition.name] = specialized
            added_specialization = True
        if added_specialization:
            continue
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
        function_catalog=function_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        function_name_resolver=function_name_resolver,
        procedure_name_resolver=procedure_name_resolver,
        workflow_name_resolver=workflow_name_resolver,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    return typed_procedures, typed_workflows, procedure_catalog


def _validate_procedure_effects_and_cycles(
    typed_procedures: tuple[TypedProcedureDef, ...],
    *,
    procedure_catalog: ProcedureCatalog,
    validate_declared: bool = True,
) -> tuple[tuple[TypedProcedureDef, ...], ProcedureCatalog]:
    """Resolve transitive procedure effects and reject recursive proc cycles."""

    typed_by_name = {procedure.definition.name: procedure for procedure in typed_procedures}
    call_graph = {
        name: frozenset(
            edge.callee_name
            for edge in procedure.direct_effect_summary.procedure_edges
            if edge.callee_name in typed_by_name
        )
        for name, procedure in typed_by_name.items()
    }
    procedure_catalog = with_call_graph(procedure_catalog, call_graph)

    resolved: dict[str, EffectSummary] = {}
    visiting: list[str] = []

    def _is_proc_ref_specialization(procedure: TypedProcedureDef) -> bool:
        return procedure.specialization is not None and (
            getattr(procedure.specialization, "proc_ref_bindings", {})
            or getattr(procedure.specialization, "value_bindings", {})
        )

    def _cycle_edge(source_name: str, target_name: str) -> ProcedureCallEdge | None:
        return next(
            (
                edge
                for edge in typed_by_name[source_name].direct_effect_summary.procedure_edges
                if edge.callee_name == target_name
            ),
            None,
        )

    def _cycle_diagnostic_label(procedure: TypedProcedureDef, *, proc_ref_cycle: bool) -> str:
        if proc_ref_cycle and _is_proc_ref_specialization(procedure):
            return getattr(procedure.specialization, "base_name", procedure.definition.name)
        return procedure.definition.name

    def _cycle_diagnostic_source(
        source_name: str,
        target_name: str,
        *,
        proc_ref_cycle: bool,
    ) -> tuple[object, tuple[str, ...], tuple[object, ...]]:
        procedure = typed_by_name[source_name]
        edge = _cycle_edge(source_name, target_name)
        if edge is not None and edge.span is not None:
            return edge.span, edge.form_path, edge.expansion_stack
        if proc_ref_cycle and procedure.specialization is not None:
            return (
                procedure.specialization.origin_span,
                procedure.specialization.origin_form_path,
                procedure.definition.expansion_stack,
            )
        return procedure.definition.span, procedure.definition.form_path, procedure.definition.expansion_stack

    def visit(name: str) -> EffectSummary:
        if name in resolved:
            return resolved[name]
        if name in visiting:
            cycle_names = visiting[visiting.index(name):]
            proc_ref_cycle = any(_is_proc_ref_specialization(typed_by_name[cycle_name]) for cycle_name in cycle_names)
            raise LispFrontendCompileError(
                tuple(
                    LispFrontendDiagnostic(
                        code="proc_ref_specialization_cycle" if proc_ref_cycle else "proc_lowering_cycle",
                        message=(
                            "recursive procedure specialization cycle detected for "
                            f"`{_cycle_diagnostic_label(typed_by_name[cycle_name], proc_ref_cycle=proc_ref_cycle)}`"
                            if proc_ref_cycle
                            else f"recursive procedure lowering cycle detected for `{cycle_name}`"
                        ),
                        span=_cycle_diagnostic_source(
                            cycle_name,
                            cycle_names[(index + 1) % len(cycle_names)],
                            proc_ref_cycle=proc_ref_cycle,
                        )[0],
                        form_path=_cycle_diagnostic_source(
                            cycle_name,
                            cycle_names[(index + 1) % len(cycle_names)],
                            proc_ref_cycle=proc_ref_cycle,
                        )[1],
                        expansion_stack=_cycle_diagnostic_source(
                            cycle_name,
                            cycle_names[(index + 1) % len(cycle_names)],
                            proc_ref_cycle=proc_ref_cycle,
                        )[2],
                    )
                    for index, cycle_name in enumerate(cycle_names)
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
        if (
            validate_declared
            and procedure.specialization is None
            and not procedure.definition.name.startswith("%")
        ):
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
                resolved_lowering_mode=procedure.resolved_lowering_mode,
                generated_workflow_name=procedure.generated_workflow_name,
                specialization=procedure.specialization,
            )
        )
    return tuple(updated), procedure_catalog


def _procedure_dependencies(expr: object) -> set[str]:
    """Find direct procedure-call dependencies inside an expression tree."""

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
