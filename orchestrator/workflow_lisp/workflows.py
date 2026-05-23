"""Elaborate `defworkflow` forms and register callable workflow boundaries.

This module turns syntax-layer workflow definitions into typed call signatures,
checks that frontend record/union boundaries can be represented by current
workflow contracts, imports signatures from validated workflow bundles, and
typechecks workflow bodies against local procedures, externs, and command
boundaries.

See `../../docs/design/workflow_lisp_frontend_mvp_specification.md` for the supported
`defworkflow` scope and `../../docs/design/workflow_lisp_core_workflow_ast.md` for
the planned syntax-neutral workflow representation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from orchestrator.workflow.loaded_bundle import workflow_input_contracts, workflow_output_contracts

from .definitions import WorkflowLispModule
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EMPTY_EFFECT_SUMMARY, EffectSummary
from .expressions import elaborate_expression
from .lints import required_lint_diagnostic
from .macros import collect_macro_catalog, expand_module_forms
from .procedures import ProcedureCatalog
from .spans import SourceSpan
from .spans import SourcePosition
from .syntax import (
    ExpansionStack,
    SyntaxIdentifier,
    SyntaxList,
    SyntaxNode,
    WorkflowLispSyntaxModule,
    syntax_head,
    syntax_identifier,
    syntax_node_datum,
    syntax_resolved_name,
)
from .type_env import FrontendTypeEnvironment, PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from .typecheck import TypedExpr, typecheck_expression

if TYPE_CHECKING:
    from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
    from .lowering import LoweredWorkflow
    from .procedures import TypedProcedureDef


@dataclass(frozen=True)
class ProviderExtern:
    """Provider alias supplied from the build environment."""

    name: str
    provider_id: str


@dataclass(frozen=True)
class PromptExtern:
    """Prompt asset binding supplied from the build environment."""

    name: str
    asset_file: str


@dataclass(frozen=True)
class ExternEnvironment:
    """Provider and prompt bindings supplied by the build caller.

    `.orc` source refers to providers and prompt assets by name. The build
    environment resolves those names to provider ids and prompt file paths
    before typechecking and lowering.
    """

    bindings_by_name: Mapping[str, ProviderExtern | PromptExtern]


@dataclass(frozen=True)
class ExternalToolBinding:
    """Named command that can be invoked from Workflow Lisp.

    This is for deterministic tools whose behavior is outside the frontend but
    whose command prefix is stable. Unlike a certified adapter, it does not
    declare typed workflow semantics beyond the command invocation itself.
    """

    name: str
    stable_command: tuple[str, ...]


@dataclass(frozen=True)
class CertifiedAdapterBinding:
    """Command boundary with explicit typed workflow semantics.

    A certified adapter is still a command, but it declares input/output
    contracts, effects, path-safety rules, and fixtures. That makes it suitable
    for temporary legacy behavior such as resource movement without hiding that
    behavior inside inline Python or shell.
    """

    name: str
    stable_command: tuple[str, ...]
    input_contract: Mapping[str, object]
    output_type_name: str
    effects: tuple[str, ...]
    path_safety: Mapping[str, object]
    source_map_behavior: str
    fixture_ids: tuple[str, ...]
    negative_fixture_ids: tuple[str, ...]


@dataclass(frozen=True)
class CommandBoundaryEnvironment:
    """Named commands available to `command-result` forms.

    The frontend resolves a command name in `.orc` source through this mapping
    before lowering it to an ordinary workflow command step.
    """

    bindings_by_name: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]


@dataclass(frozen=True)
class WorkflowParam:
    """Authored `defworkflow` parameter before type resolution."""

    name: str
    type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class WorkflowDef:
    """Parsed workflow definition with signature text and body syntax."""

    name: str
    params: tuple[WorkflowParam, ...]
    return_type_name: str
    body: SyntaxNode
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class WorkflowSignature:
    """Type-resolved workflow call boundary."""

    name: str
    params: tuple[tuple[str, TypeRef], ...]
    return_type_ref: RecordTypeRef | UnionTypeRef
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class TypedWorkflowDef:
    """Workflow definition after body typechecking and effect analysis."""

    definition: WorkflowDef
    signature: WorkflowSignature
    typed_body: TypedExpr
    effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY


@dataclass(frozen=True)
class WorkflowCatalog:
    """Lookup table for local and imported workflow call signatures."""

    signatures_by_name: Mapping[str, WorkflowSignature]
    definitions_by_name: Mapping[str, WorkflowDef]
    imported_bundles_by_name: Mapping[str, "LoadedWorkflowBundle"]


@dataclass(frozen=True)
class Stage3CompileResult:
    """Compiled module result after typecheck, lowering, and shared validation."""

    module: WorkflowLispModule
    workflow_catalog: WorkflowCatalog
    procedure_catalog: ProcedureCatalog
    extern_environment: ExternEnvironment
    command_boundary_environment: CommandBoundaryEnvironment
    typed_procedures: tuple["TypedProcedureDef", ...]
    typed_workflows: tuple[TypedWorkflowDef, ...]
    lowered_workflows: tuple["LoweredWorkflow", ...]
    validated_bundles: Mapping[str, "LoadedWorkflowBundle"]
    diagnostics: tuple[LispFrontendDiagnostic, ...] = ()


@dataclass(frozen=True)
class WorkflowBoundaryAnalysis:
    """Whether a frontend type can be represented by current workflow contracts."""

    lowerable: bool
    contains_json: bool
    contains_provider_or_prompt: bool
    contains_union: bool
    offending_path: tuple[str, ...] = ()
    offending_type_name: str | None = None


def analyze_workflow_boundary_type(
    type_ref: TypeRef,
    *,
    source_path: tuple[str, ...] = (),
    allow_union: bool = False,
) -> WorkflowBoundaryAnalysis:
    """Return whether one workflow-boundary type can lower to shared contracts."""

    if isinstance(type_ref, PathTypeRef):
        return WorkflowBoundaryAnalysis(
            lowerable=True,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_union=False,
        )
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.name == "Json":
            return WorkflowBoundaryAnalysis(
                lowerable=False,
                contains_json=True,
                contains_provider_or_prompt=False,
                contains_union=False,
                offending_path=source_path,
                offending_type_name=type_ref.name,
            )
        if type_ref.name in {"Provider", "Prompt"}:
            return WorkflowBoundaryAnalysis(
                lowerable=False,
                contains_json=False,
                contains_provider_or_prompt=True,
                contains_union=False,
                offending_path=source_path,
                offending_type_name=type_ref.name,
            )
        return WorkflowBoundaryAnalysis(
            lowerable=True,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_union=False,
        )
    if isinstance(type_ref, RecordTypeRef):
        for field in type_ref.definition.fields:
            field_type = type_ref.field_types.get(field.name)
            if field_type is None:
                raise TypeError(f"missing resolved field type for `{type_ref.name}.{field.name}`")
            analysis = analyze_workflow_boundary_type(
                field_type,
                source_path=source_path + (field.name,),
                allow_union=allow_union,
            )
            if not analysis.lowerable:
                return analysis
        return WorkflowBoundaryAnalysis(
            lowerable=True,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_union=False,
        )
    if isinstance(type_ref, UnionTypeRef):
        if allow_union:
            for variant in type_ref.definition.variants:
                for field in variant.fields:
                    field_type = type_ref.variant_field_types[variant.name][field.name]
                    analysis = analyze_workflow_boundary_type(
                        field_type,
                        source_path=source_path + (variant.name, field.name),
                        allow_union=False,
                    )
                    if not analysis.lowerable:
                        return analysis
            return WorkflowBoundaryAnalysis(
                lowerable=True,
                contains_json=False,
                contains_provider_or_prompt=False,
                contains_union=False,
            )
        return WorkflowBoundaryAnalysis(
            lowerable=False,
            contains_json=False,
            contains_provider_or_prompt=False,
            contains_union=True,
            offending_path=source_path,
            offending_type_name=type_ref.name,
        )
    raise TypeError(f"unsupported workflow-boundary type reference: {type(type_ref)!r}")


def elaborate_workflow_definitions(module_syntax: WorkflowLispSyntaxModule) -> tuple[WorkflowDef, ...]:
    """Elaborate all top-level `defworkflow` forms from one syntax module."""

    expanded_module = expand_module_forms(
        module_syntax,
        catalog=collect_macro_catalog(module_syntax),
    )
    definitions: list[WorkflowDef] = []
    for form in expanded_module.forms:
        if syntax_resolved_name(syntax_head(form)) == "defworkflow":
            definitions.append(_elaborate_workflow_definition(form))
    return tuple(definitions)


def build_workflow_catalog(
    module: WorkflowLispModule,
    workflow_defs: tuple[WorkflowDef, ...],
    type_env: FrontendTypeEnvironment,
    *,
    imported_signatures: Mapping[str, WorkflowSignature] | None = None,
    lookup_aliases: Mapping[str, str] | None = None,
    imported_workflow_bundles: Mapping[str, "LoadedWorkflowBundle"] | None = None,
) -> WorkflowCatalog:
    """Build same-file workflow signatures before any body is typechecked."""

    del module
    signatures_by_name: dict[str, WorkflowSignature] = dict(imported_signatures or {})
    definitions_by_name: dict[str, WorkflowDef] = {}
    diagnostics: list[LispFrontendDiagnostic] = []
    for workflow_def in workflow_defs:
        if workflow_def.name in definitions_by_name:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="workflow_definition_duplicate",
                    message=f"duplicate workflow definition `{workflow_def.name}`",
                    span=workflow_def.span,
                    form_path=workflow_def.form_path,
                    expansion_stack=workflow_def.expansion_stack,
                )
            )
            continue
        return_type_ref = type_env.resolve_type(
            workflow_def.return_type_name,
            span=workflow_def.span,
            form_path=workflow_def.form_path,
            expansion_stack=workflow_def.expansion_stack,
        )
        if not isinstance(return_type_ref, (RecordTypeRef, UnionTypeRef)):
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="workflow_return_type_invalid",
                    message=(
                        f"workflow `{workflow_def.name}` must return a record or union type in Stage 3, "
                        f"got `{workflow_def.return_type_name}`"
                    ),
                    span=workflow_def.span,
                    form_path=workflow_def.form_path,
                    expansion_stack=workflow_def.expansion_stack,
                )
            )
            continue
        return_analysis = analyze_workflow_boundary_type(
            return_type_ref,
            source_path=("return",),
            allow_union=True,
        )
        return_diagnostic = _boundary_diagnostic(
            workflow_name=workflow_def.name,
            analysis=return_analysis,
            span=workflow_def.span,
            form_path=workflow_def.form_path,
            expansion_stack=workflow_def.expansion_stack,
        )
        if return_diagnostic is not None:
            diagnostics.append(return_diagnostic)
            continue
        params: list[tuple[str, TypeRef]] = []
        workflow_invalid = False
        for param in workflow_def.params:
            param_type = type_env.resolve_type(
                param.type_name,
                span=param.span,
                form_path=param.form_path,
                expansion_stack=param.expansion_stack,
            )
            param_analysis = analyze_workflow_boundary_type(param_type, source_path=(param.name,))
            param_diagnostic = _boundary_diagnostic(
                workflow_name=workflow_def.name,
                analysis=param_analysis,
                span=param.span,
                form_path=param.form_path,
                expansion_stack=param.expansion_stack,
            )
            if param_diagnostic is not None:
                diagnostics.append(param_diagnostic)
                workflow_invalid = True
                continue
            params.append((param.name, param_type))
        if workflow_invalid:
            continue
        signature = WorkflowSignature(
            name=workflow_def.name,
            params=tuple(params),
            return_type_ref=return_type_ref,
            span=workflow_def.span,
            form_path=workflow_def.form_path,
        )
        definitions_by_name[workflow_def.name] = workflow_def
        signatures_by_name[workflow_def.name] = signature

    for imported_name, imported_bundle in (imported_workflow_bundles or {}).items():
        if imported_name in signatures_by_name:
            if imported_signatures is not None and imported_name in imported_signatures:
                continue
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="workflow_definition_duplicate",
                    message=f"duplicate workflow definition `{imported_name}`",
                    span=_bundle_source_span(imported_bundle),
                    form_path=("workflow-lisp", imported_name),
                )
            )
            continue
        signatures_by_name[imported_name] = _signature_from_imported_bundle(
            imported_name,
            imported_bundle,
            type_env=type_env,
        )
    for alias_name, canonical_name in (lookup_aliases or {}).items():
        signature = signatures_by_name.get(canonical_name)
        if signature is not None:
            signatures_by_name[alias_name] = signature

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return WorkflowCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
        imported_bundles_by_name=dict(imported_workflow_bundles or {}),
    )


def _signature_from_imported_bundle(
    alias: str,
    bundle: "LoadedWorkflowBundle",
    *,
    type_env: FrontendTypeEnvironment,
) -> WorkflowSignature:
    """Reconstruct a frontend workflow signature from a validated bundle."""

    input_contracts = workflow_input_contracts(bundle)
    grouped_inputs: dict[str, dict[str, Mapping[str, object]]] = {}
    param_order: list[str] = []
    for input_name, input_spec in input_contracts.items():
        if not isinstance(input_name, str) or not isinstance(input_spec, Mapping):
            continue
        if input_name.startswith("__write_root__"):
            continue
        param_name = input_name.split("__", 1)[0]
        if param_name not in grouped_inputs:
            grouped_inputs[param_name] = {}
            param_order.append(param_name)
        grouped_inputs[param_name][input_name] = dict(input_spec)

    span = _bundle_source_span(bundle)
    form_path = ("workflow-lisp", alias)
    params = tuple(
        (
            param_name,
            _match_boundary_type_from_contracts(
                grouped_inputs[param_name],
                type_env=type_env,
                generated_name=param_name,
                allow_union=False,
                span=span,
                form_path=form_path,
            ),
        )
        for param_name in param_order
    )
    return_type_ref = _match_boundary_type_from_contracts(
        {
            output_name: dict(output_spec)
            for output_name, output_spec in workflow_output_contracts(bundle).items()
            if isinstance(output_name, str) and isinstance(output_spec, Mapping)
        },
        type_env=type_env,
        generated_name="return",
        allow_union=True,
        span=span,
        form_path=form_path,
    )
    if not isinstance(return_type_ref, (RecordTypeRef, UnionTypeRef)):
        raise LispFrontendCompileError(
            (
                required_lint_diagnostic(
                    "workflow_call_signature_erased",
                    message=f"imported workflow `{alias}` must resolve to a record or union return type",
                    span=span,
                    form_path=form_path,
                ),
            )
        )
    return WorkflowSignature(
        name=alias,
        params=params,
        return_type_ref=return_type_ref,
        span=span,
        form_path=form_path,
    )


def _match_boundary_type_from_contracts(
    contracts: Mapping[str, Mapping[str, object]],
    *,
    type_env: FrontendTypeEnvironment,
    generated_name: str,
    allow_union: bool,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    """Find the authored type whose flattened contracts match a bundle boundary."""

    normalized_contracts = {
        name: _normalize_boundary_contract_definition(definition)
        for name, definition in contracts.items()
        if isinstance(name, str) and isinstance(definition, Mapping)
    }
    candidates: list[TypeRef] = []
    for candidate in type_env._type_refs.values():  # noqa: SLF001 - internal compiler matching
        if isinstance(candidate, UnionTypeRef) and not allow_union:
            continue
        if not isinstance(candidate, (PrimitiveTypeRef, PathTypeRef, RecordTypeRef, UnionTypeRef)):
            continue
        analysis = analyze_workflow_boundary_type(
            candidate,
            source_path=(generated_name,),
            allow_union=allow_union,
        )
        if not analysis.lowerable:
            continue
        if _flattened_boundary_contracts(candidate, generated_name=generated_name, span=span, form_path=form_path) == normalized_contracts:
            candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        candidate_names = ", ".join(sorted(candidate.name for candidate in candidates))
        raise LispFrontendCompileError(
            (
                required_lint_diagnostic(
                    "workflow_call_signature_erased",
                    message=(
                        f"imported workflow boundary for `{generated_name}` is ambiguous across authored types: "
                        f"{candidate_names}"
                    ),
                    span=span,
                    form_path=form_path,
                ),
            )
        )
    raise LispFrontendCompileError(
        (
            required_lint_diagnostic(
                "workflow_call_signature_erased",
                message=f"imported workflow boundary for `{generated_name}` does not match any authored type in scope",
                span=span,
                form_path=form_path,
            ),
        )
    )


def _flattened_boundary_contracts(
    type_ref: TypeRef,
    *,
    generated_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> Mapping[str, Mapping[str, object]]:
    """Flatten a frontend boundary type into shared workflow contract fields."""

    from .contracts import derive_workflow_boundary_fields

    return {
        field.generated_name: _normalize_boundary_contract_definition(field.contract_definition)
        for field in derive_workflow_boundary_fields(
            type_ref,
            generated_name=generated_name,
            source_path=(generated_name,),
            span=span,
            form_path=form_path,
        )
    }


def _normalize_boundary_contract_definition(definition: Mapping[str, object]) -> Mapping[str, object]:
    """Normalize a contract shape for structural boundary comparison."""

    return {
        str(key): value
        for key, value in dict(definition).items()
        if key != "from"
    }


def _bundle_source_span(bundle: "LoadedWorkflowBundle") -> SourceSpan:
    """Create a diagnostic span for an imported workflow bundle."""

    workflow_path = bundle.provenance.workflow_path
    return SourceSpan(
        start=SourcePosition(path=str(workflow_path), line=1, column=1, offset=0),
        end=SourcePosition(path=str(workflow_path), line=1, column=1, offset=0),
    )


def typecheck_workflow_definitions(
    workflow_defs: tuple[WorkflowDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    workflow_catalog: WorkflowCatalog,
    procedure_catalog: ProcedureCatalog | None = None,
    extern_environment: ExternEnvironment | None = None,
    command_boundary_environment: CommandBoundaryEnvironment | None = None,
    procedure_effects_by_name: Mapping[str, EffectSummary] | None = None,
    workflow_effects_by_name: Mapping[str, EffectSummary] | None = None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
) -> tuple[TypedWorkflowDef, ...]:
    """Typecheck workflow parameters and bodies against the registered signatures."""

    externs = extern_environment or ExternEnvironment(bindings_by_name={})
    command_boundaries = command_boundary_environment
    typed_workflows: list[TypedWorkflowDef] = []
    for workflow_def in workflow_defs:
        seen_names: set[str] = set()
        value_env: dict[str, TypeRef] = {}
        for param_name, type_ref in workflow_catalog.signatures_by_name[workflow_def.name].params:
            if param_name in seen_names:
                duplicate = next(param for param in workflow_def.params if param.name == param_name)
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="workflow_param_duplicate",
                            message=f"duplicate workflow parameter `{param_name}`",
                            span=duplicate.span,
                            form_path=duplicate.form_path,
                            expansion_stack=duplicate.expansion_stack,
                        ),
                    )
                )
            seen_names.add(param_name)
            value_env[param_name] = type_ref
        for extern_name, binding in externs.bindings_by_name.items():
            if isinstance(binding, ProviderExtern):
                value_env[extern_name] = PrimitiveTypeRef(name="Provider")
            else:
                value_env[extern_name] = PrimitiveTypeRef(name="Prompt")

        procedure_names = frozenset() if procedure_catalog is None else frozenset(procedure_catalog.signatures_by_name)
        body_expr = elaborate_expression(
            workflow_def.body,
            bound_names=frozenset(value_env),
            procedure_names=procedure_names,
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
            command_boundary_environment=command_boundaries,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
        )
        signature = workflow_catalog.signatures_by_name[workflow_def.name]
        if typed_body.type_ref != signature.return_type_ref:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="return_type_mismatch",
                        message=(
                            f"workflow `{workflow_def.name}` declared return type "
                            f"`{workflow_def.return_type_name}` but body returned a different type"
                        ),
                        span=workflow_def.body.span,
                        form_path=workflow_def.body.form_path,
                        expansion_stack=workflow_def.body.expansion_stack,
                    ),
                )
            )
        typed_workflows.append(
            TypedWorkflowDef(
                definition=workflow_def,
                signature=signature,
                typed_body=typed_body,
                effect_summary=typed_body.effect_summary,
            )
        )
    return tuple(typed_workflows)


def _boundary_diagnostic(
    *,
    workflow_name: str,
    analysis: WorkflowBoundaryAnalysis,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack = (),
) -> LispFrontendDiagnostic | None:
    """Translate workflow-boundary analysis into a frontend diagnostic."""

    if analysis.lowerable:
        return None

    path_label = ".".join(analysis.offending_path) if analysis.offending_path else workflow_name
    if analysis.contains_json:
        return LispFrontendDiagnostic(
            code="json_surface_unsupported",
            message=f"`Json` is not supported on workflow boundaries in Stage 3 (`{path_label}`)",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if analysis.contains_provider_or_prompt:
        return LispFrontendDiagnostic(
            code="workflow_boundary_type_invalid",
            message=(
                f"`{analysis.offending_type_name}` cannot cross a Stage 3 workflow boundary "
                f"(`{path_label}`)"
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if analysis.contains_union:
        return LispFrontendDiagnostic(
            code="workflow_boundary_type_invalid",
            message=(
                f"workflow boundary `{path_label}` must lower to scalars, relpaths, or records; "
                "unions are not supported in Stage 3"
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    return LispFrontendDiagnostic(
        code="workflow_boundary_type_invalid",
        message=f"workflow boundary `{path_label}` is not lowerable in Stage 3",
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
    )


def _elaborate_workflow_definition(form: SyntaxNode) -> WorkflowDef:
    """Parse one `defworkflow` form into a workflow definition object."""

    datum = syntax_node_datum(form)
    if not isinstance(datum, SyntaxList) or len(datum.items) < 6:
        _raise_error(
            "`defworkflow` requires a name, params, return arrow, return type, and one body",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    name_node = syntax_identifier(datum.items[1])
    if name_node is None:
        _raise_error(
            "workflow name must be a symbol",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    params_node = datum.items[2]
    if not isinstance(params_node, SyntaxList):
        _raise_error(
            "workflow params must be a list",
            span=params_node.span,
            form_path=form.form_path,
            expansion_stack=params_node.expansion_stack,
        )
    arrow_node = syntax_identifier(datum.items[3])
    if arrow_node is None or arrow_node.resolved_name != "->":
        _raise_error(
            "workflow return separator must be `->`",
            span=datum.items[3].span,
            form_path=form.form_path,
            expansion_stack=datum.items[3].expansion_stack,
        )
    return_type_node = datum.items[4]
    return_type_identifier = syntax_identifier(return_type_node)
    if return_type_identifier is None:
        _raise_error(
            "workflow return type must be a symbol",
            span=return_type_node.span,
            form_path=form.form_path,
            expansion_stack=return_type_node.expansion_stack,
        )
    if len(datum.items) != 6:
        _raise_error(
            "`defworkflow` requires exactly one body expression",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )

    params = tuple(_elaborate_param(param, form.form_path) for param in params_node.items)
    body_datum = datum.items[5]
    body = SyntaxNode(
        datum=body_datum,
        span=body_datum.span,
        module_path=form.module_path,
        form_path=form.form_path,
    )
    return WorkflowDef(
        name=name_node.resolved_name,
        params=params,
        return_type_name=return_type_identifier.resolved_name,
        body=body,
        span=form.span,
        form_path=form.form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_param(raw_param: object, form_path: tuple[str, ...]) -> WorkflowParam:
    """Parse one `(name Type)` workflow parameter."""

    if not isinstance(raw_param, SyntaxList) or len(raw_param.items) != 2:
        span = raw_param.span if hasattr(raw_param, "span") else None
        if span is None:
            raise TypeError("workflow params must carry spans")
        _raise_error(
            "workflow params must be two-item lists of `(name Type)`",
            span=span,
            form_path=form_path,
            expansion_stack=getattr(raw_param, "expansion_stack", ()),
        )
    name_node = raw_param.items[0]
    type_node = raw_param.items[1]
    name_identifier = syntax_identifier(name_node)
    type_identifier = syntax_identifier(type_node)
    if name_identifier is None:
        _raise_error(
            "workflow param names must be symbols",
            span=name_node.span,
            form_path=form_path,
            expansion_stack=name_node.expansion_stack,
        )
    if type_identifier is None:
        _raise_error(
            "workflow param types must be symbols",
            span=type_node.span,
            form_path=form_path,
            expansion_stack=type_node.expansion_stack,
        )
    return WorkflowParam(
        name=name_identifier.resolved_name,
        type_name=type_identifier.resolved_name,
        span=raw_param.span,
        form_path=form_path,
        expansion_stack=raw_param.expansion_stack,
    )


def _raise_error(
    message: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack = (),
) -> None:
    """Raise one workflow-elaboration diagnostic."""

    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="frontend_parse_error",
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )


def build_extern_environment(
    *,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
) -> ExternEnvironment:
    """Validate build-supplied provider and prompt bindings."""

    diagnostics: list[LispFrontendDiagnostic] = []
    bindings: dict[str, ProviderExtern | PromptExtern] = {}

    for name, provider_id in (provider_externs or {}).items():
        if not isinstance(name, str) or not name.strip() or not isinstance(provider_id, str) or not provider_id.strip():
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="provider_result_provider_invalid",
                    message="provider extern bindings require non-empty authored names and provider ids",
                    span=_environment_span(),
                )
            )
            continue
        bindings[name] = ProviderExtern(name=name, provider_id=provider_id)

    for name, asset_file in (prompt_externs or {}).items():
        if not isinstance(name, str) or not name.strip() or not isinstance(asset_file, str) or not asset_file.strip():
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="provider_result_prompt_invalid",
                    message="prompt extern bindings require non-empty authored names and asset files",
                    span=_environment_span(),
                )
            )
            continue
        bindings[name] = PromptExtern(name=name, asset_file=asset_file)

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return ExternEnvironment(bindings_by_name=bindings)


def build_command_boundary_environment(
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
) -> CommandBoundaryEnvironment:
    """Validate named command bindings supplied by the build caller."""

    diagnostics: list[LispFrontendDiagnostic] = []
    bindings: dict[str, ExternalToolBinding | CertifiedAdapterBinding] = {}

    for name, binding in (command_boundaries or {}).items():
        if not isinstance(name, str) or not name.strip():
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="command_adapter_missing_contract",
                    message="command boundary bindings require non-empty names",
                    span=_environment_span(),
                    phase="typecheck",
                )
            )
            continue
        if not binding.stable_command or not all(isinstance(token, str) and token for token in binding.stable_command):
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="command_adapter_missing_contract",
                    message=f"command boundary `{name}` must declare a non-empty stable command",
                    span=_environment_span(),
                    phase="typecheck",
                )
            )
            continue
        if isinstance(binding, CertifiedAdapterBinding):
            if (
                not binding.input_contract
                or not binding.output_type_name
                or not binding.effects
                or not binding.path_safety
                or not binding.source_map_behavior
            ):
                diagnostics.append(
                    LispFrontendDiagnostic(
                        code="command_adapter_missing_contract",
                        message=f"certified adapter `{name}` is missing required contract metadata",
                        span=_environment_span(),
                        phase="typecheck",
                    )
                )
                continue
            if not binding.fixture_ids or not binding.negative_fixture_ids:
                diagnostics.append(
                    LispFrontendDiagnostic(
                        code="command_adapter_missing_contract",
                        message=f"certified adapter `{name}` requires positive and negative fixtures",
                        span=_environment_span(),
                        phase="typecheck",
                    )
                )
                continue
        bindings[name] = binding

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return CommandBoundaryEnvironment(bindings_by_name=bindings)


def _environment_span() -> SourceSpan:
    """Return a synthetic span for build-environment validation errors."""

    from .spans import SourcePosition

    position = SourcePosition(path="<stage3-environment>", line=1, column=1, offset=0)
    return SourceSpan(start=position, end=position)
