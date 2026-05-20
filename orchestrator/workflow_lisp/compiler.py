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
    validate_procedure_effects,
    with_call_graph,
)
from .reader import read_sexpr_file
from .syntax import WorkflowLispSyntaxModule, build_syntax_module, syntax_head_name, syntax_node_datum
from .type_env import PRELUDE_TYPE_NAMES, FrontendTypeEnvironment, TypeRef
from .typecheck import typecheck_expression
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
    for module_name in graph.topological_order:
        module_source = graph.modules_by_name[module_name]
        module = elaborate_definition_module(_definition_only_syntax_module(module_source.syntax_module))
        _validate_definition_module(module)
        build_import_scope(module, export_surfaces_by_name=export_surfaces)
        export_surfaces[module_name] = derive_export_surface(
            module_source.syntax_module,
            local_macros=collect_macro_catalog(module_source.syntax_module),
            local_module=module,
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
) -> LinkedStage3CompileResult:
    """Compile an entrypoint and imports through the executable frontend path.

    The function resolves the module graph once, then runs macro expansion,
    definition validation, procedure/workflow signature registration, expression
    typechecking, effect inference, lowering to ordinary workflow dictionaries,
    and optional shared validation for every reachable module.
    """

    graph = resolve_module_graph(path, source_roots=source_roots)
    return _compile_stage3_graph(
        graph,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        imported_workflow_bundles=imported_workflow_bundles,
        command_boundaries=command_boundaries,
        validate_shared=validate_shared,
        workspace_root=workspace_root or path.parent,
    )

def compile_stage3_module(
    path: Path,
    *,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None = None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
    validate_shared: bool = True,
    workspace_root: Path | None = None,
) -> Stage3CompileResult:
    """Compile one `.orc` file through the executable frontend pipeline."""

    syntax_module = _expanded_syntax_module(path)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    type_env = FrontendTypeEnvironment.from_module(module)
    workflow_defs = elaborate_workflow_definitions(syntax_module)
    procedure_defs = elaborate_procedure_definitions(syntax_module)
    effective_imported_workflow_bundles = dict(imported_workflow_bundles or {})
    workflow_catalog = build_workflow_catalog(
        module,
        workflow_defs,
        type_env,
        imported_workflow_bundles=effective_imported_workflow_bundles,
    )
    procedure_catalog = build_procedure_catalog(procedure_defs, type_env=type_env)
    extern_environment = build_extern_environment(
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
    )
    command_boundary_environment = build_command_boundary_environment(command_boundaries)
    command_boundary_environment = _augment_resource_transition_command_boundaries(
        command_boundary_environment,
    )
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
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=effective_imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        type_env=type_env,
    )
    validated_bundles: Mapping[str, LoadedWorkflowBundle]
    if validate_shared:
        validated_bundles = validate_lowered_workflows(
            lowered_workflows,
            workspace_root=workspace_root or path.parent,
            imported_workflow_bundles=effective_imported_workflow_bundles,
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
    """Compile one `.orc` file through the definition-only frontend pipeline."""

    syntax_module = _expanded_syntax_module(path)
    _validate_stage1_top_level_forms(syntax_module)
    module = elaborate_definition_module(_definition_only_syntax_module(syntax_module))
    _validate_definition_module(module)
    return module


def _compile_stage3_graph(
    graph: LinkedModuleGraph,
    *,
    provider_externs: Mapping[str, str] | None,
    prompt_externs: Mapping[str, str] | None,
    imported_workflow_bundles: Mapping[str, LoadedWorkflowBundle] | None,
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None,
    validate_shared: bool,
    workspace_root: Path,
) -> LinkedStage3CompileResult:
    """Compile a resolved module graph in dependency order.

    Each module is expanded and typechecked after its imports have published
    type refs, macro definitions, procedure signatures, workflow signatures,
    and validated workflow bundles. Exported workflows are validated as needed
    so downstream modules can call them through the existing workflow loader.
    """

    export_surfaces = dict(graph.export_surfaces_by_name)
    exported_type_refs_by_module: dict[str, dict[str, TypeRef]] = {}
    exported_macro_defs_by_module: dict[str, dict[str, object]] = {}
    exported_procedure_signatures_by_module: dict[str, dict[str, ProcedureSignature]] = {}
    exported_workflow_signatures_by_module: dict[str, dict[str, WorkflowSignature]] = {}
    typed_procedures_by_name: dict[str, TypedProcedureDef] = {}
    procedure_effects_by_name: dict[str, EffectSummary] = {}
    workflow_effects_by_name: dict[str, EffectSummary] = {}
    exported_validated_bundles_by_name: dict[str, LoadedWorkflowBundle] = {}
    compiled_results_by_name: dict[str, Stage3CompileResult] = {}
    explicit_imported_bundles = dict(imported_workflow_bundles or {})

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
        )
        import_scope = build_import_scope(preliminary_module, export_surfaces_by_name=export_surfaces)
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
            _definition_only_from_expanded_syntax_module(expanded_syntax)
        )
        _validate_definition_module(definition_module)

        raw_procedure_defs = elaborate_procedure_definitions(expanded_syntax)
        raw_workflow_defs = elaborate_workflow_definitions(expanded_syntax)
        export_surfaces[module_name] = derive_export_surface(
            expanded_syntax,
            local_macros=collect_macro_catalog(module_source.syntax_module),
            local_module=definition_module,
            procedure_names=tuple(procedure.name for procedure in raw_procedure_defs),
            workflow_names=tuple(workflow.name for workflow in raw_workflow_defs),
        )
        import_scope = build_import_scope(definition_module, export_surfaces_by_name=export_surfaces)

        imported_type_refs = _imported_type_refs(import_scope, exported_type_refs_by_module)
        type_env = FrontendTypeEnvironment.from_module(
            definition_module,
            import_scope=import_scope,
            imported_type_refs=imported_type_refs,
        )
        procedure_defs = _canonicalize_procedure_defs(module_name, raw_procedure_defs)
        workflow_defs = _canonicalize_workflow_defs(module_name, raw_workflow_defs)
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
        typed_procedures, typed_workflows, procedure_catalog = _infer_stage3_effect_summaries(
            procedure_defs,
            workflow_defs=workflow_defs,
            type_env=type_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            procedure_name_resolver=local_procedure_resolver,
            workflow_name_resolver=local_workflow_resolver,
        )
        command_boundary_environment = _augment_resume_command_boundaries(
            command_boundary_environment,
            typed_procedures=typed_procedures,
            typed_workflows=typed_workflows,
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
        )
        compiled_results_by_name[module_name] = result
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
    )


def _definition_only_from_expanded_syntax_module(
    module_syntax: WorkflowLispSyntaxModule,
) -> WorkflowLispSyntaxModule:
    """Strip executable forms from expanded syntax for type-definition passes."""

    definition_forms = []
    for form in module_syntax.forms:
        head_name = syntax_head_name(syntax_node_datum(form))
        if head_name in {"defworkflow", "defproc", "defmacro"}:
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
    typed_procedures,
    typed_workflows,
):
    """Install resume/state-reuse adapters only when code uses `resume-or-start`."""

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
        diagnostics.extend(_validate_field_types(variant.fields, form_path, available_type_names))
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
) -> list[LispFrontendDiagnostic]:
    """Validate that each field references a known type name."""

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
    """Return a stable frontend form path for a type definition."""

    if isinstance(definition, EnumDef):
        return ("workflow-lisp", "defenum", definition.name)
    if isinstance(definition, PathDef):
        return ("workflow-lisp", "defpath", definition.name)
    if isinstance(definition, RecordDef):
        return ("workflow-lisp", "defrecord", definition.name)
    return ("workflow-lisp", "defunion", definition.name)


def _validate_stage1_top_level_forms(module_syntax: WorkflowLispSyntaxModule) -> None:
    """Reject executable top-level forms in definition-only compilation."""

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
    """Expand syntax and keep only forms used by definition elaboration."""

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
        module_directive=expanded_module.module_directive,
        imports=expanded_module.imports,
        export_directive=expanded_module.export_directive,
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
    procedure_name_resolver=None,
    workflow_name_resolver=None,
) -> tuple[TypedProcedureDef, ...]:
    """Typecheck procedure bodies against signatures, externs, and call catalogs."""

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
            procedure_name_resolver=procedure_name_resolver,
            workflow_name_resolver=workflow_name_resolver,
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
    procedure_effects_by_name: Mapping[str, EffectSummary] | None = None,
    workflow_effects_by_name: Mapping[str, EffectSummary] | None = None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
) -> tuple[tuple[TypedProcedureDef, ...], tuple[object, ...], ProcedureCatalog]:
    """Compute procedure/workflow effect summaries to a fixpoint."""

    procedure_effects_by_name = dict(procedure_effects_by_name or {})
    workflow_effects_by_name = dict(workflow_effects_by_name or {})
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
            procedure_name_resolver=procedure_name_resolver,
            workflow_name_resolver=workflow_name_resolver,
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
            procedure_name_resolver=procedure_name_resolver,
            workflow_name_resolver=workflow_name_resolver,
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
        procedure_name_resolver=procedure_name_resolver,
        workflow_name_resolver=workflow_name_resolver,
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
