"""Stage 3 workflow-definition elaboration and signature registration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .definitions import WorkflowLispModule
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expressions import elaborate_expression
from .sexpr import ListExpr, SymbolAtom
from .spans import SourceSpan
from .syntax import SyntaxNode, WorkflowLispSyntaxModule
from .type_env import FrontendTypeEnvironment, PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from .typecheck import TypedExpr, typecheck_expression

if TYPE_CHECKING:
    from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
    from .lowering import LoweredWorkflow


@dataclass(frozen=True)
class ProviderExtern:
    name: str
    provider_id: str


@dataclass(frozen=True)
class PromptExtern:
    name: str
    asset_file: str


@dataclass(frozen=True)
class ExternEnvironment:
    bindings_by_name: Mapping[str, ProviderExtern | PromptExtern]


@dataclass(frozen=True)
class ExternalToolBinding:
    name: str
    stable_command: tuple[str, ...]


@dataclass(frozen=True)
class CertifiedAdapterBinding:
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
    bindings_by_name: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]


@dataclass(frozen=True)
class WorkflowParam:
    name: str
    type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowDef:
    name: str
    params: tuple[WorkflowParam, ...]
    return_type_name: str
    body: SyntaxNode
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowSignature:
    name: str
    params: tuple[tuple[str, TypeRef], ...]
    return_type_ref: RecordTypeRef
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class TypedWorkflowDef:
    definition: WorkflowDef
    signature: WorkflowSignature
    typed_body: TypedExpr


@dataclass(frozen=True)
class WorkflowCatalog:
    signatures_by_name: Mapping[str, WorkflowSignature]
    definitions_by_name: Mapping[str, WorkflowDef]


@dataclass(frozen=True)
class Stage3CompileResult:
    module: WorkflowLispModule
    workflow_catalog: WorkflowCatalog
    extern_environment: ExternEnvironment
    command_boundary_environment: CommandBoundaryEnvironment
    typed_workflows: tuple[TypedWorkflowDef, ...]
    lowered_workflows: tuple["LoweredWorkflow", ...]
    validated_bundles: Mapping[str, "LoadedWorkflowBundle"]


@dataclass(frozen=True)
class WorkflowBoundaryAnalysis:
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

    definitions: list[WorkflowDef] = []
    for form in module_syntax.forms:
        datum = form.datum
        if not isinstance(datum, ListExpr) or not datum.items:
            continue
        head = datum.items[0]
        if isinstance(head, SymbolAtom) and head.value == "defworkflow":
            definitions.append(_elaborate_workflow_definition(form))
    return tuple(definitions)


def build_workflow_catalog(
    module: WorkflowLispModule,
    workflow_defs: tuple[WorkflowDef, ...],
    type_env: FrontendTypeEnvironment,
) -> WorkflowCatalog:
    """Build same-file workflow signatures before any body is typechecked."""

    del module
    signatures_by_name: dict[str, WorkflowSignature] = {}
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
                )
            )
            continue
        return_type_ref = type_env.resolve_type(
            workflow_def.return_type_name,
            span=workflow_def.span,
            form_path=workflow_def.form_path,
        )
        if not isinstance(return_type_ref, RecordTypeRef):
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="workflow_return_type_invalid",
                    message=(
                        f"workflow `{workflow_def.name}` must return a record type in Stage 3, "
                        f"got `{workflow_def.return_type_name}`"
                    ),
                    span=workflow_def.span,
                    form_path=workflow_def.form_path,
                )
            )
            continue
        return_analysis = analyze_workflow_boundary_type(return_type_ref, source_path=("return",))
        return_diagnostic = _boundary_diagnostic(
            workflow_name=workflow_def.name,
            analysis=return_analysis,
            span=workflow_def.span,
            form_path=workflow_def.form_path,
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
            )
            param_analysis = analyze_workflow_boundary_type(param_type, source_path=(param.name,))
            param_diagnostic = _boundary_diagnostic(
                workflow_name=workflow_def.name,
                analysis=param_analysis,
                span=param.span,
                form_path=param.form_path,
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

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return WorkflowCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
    )


def typecheck_workflow_definitions(
    workflow_defs: tuple[WorkflowDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    workflow_catalog: WorkflowCatalog,
    extern_environment: ExternEnvironment | None = None,
    command_boundary_environment: CommandBoundaryEnvironment | None = None,
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

        body_expr = elaborate_expression(workflow_def.body, bound_names=frozenset(value_env))
        typed_body = typecheck_expression(
            body_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_catalog=workflow_catalog,
            extern_environment=externs,
            command_boundary_environment=command_boundaries,
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
                    ),
                )
            )
        typed_workflows.append(
            TypedWorkflowDef(
                definition=workflow_def,
                signature=signature,
                typed_body=typed_body,
            )
        )
    return tuple(typed_workflows)


def _boundary_diagnostic(
    *,
    workflow_name: str,
    analysis: WorkflowBoundaryAnalysis,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> LispFrontendDiagnostic | None:
    if analysis.lowerable:
        return None

    path_label = ".".join(analysis.offending_path) if analysis.offending_path else workflow_name
    if analysis.contains_json:
        return LispFrontendDiagnostic(
            code="json_surface_unsupported",
            message=f"`Json` is not supported on workflow boundaries in Stage 3 (`{path_label}`)",
            span=span,
            form_path=form_path,
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
        )
    return LispFrontendDiagnostic(
        code="workflow_boundary_type_invalid",
        message=f"workflow boundary `{path_label}` is not lowerable in Stage 3",
        span=span,
        form_path=form_path,
    )


def _elaborate_workflow_definition(form: SyntaxNode) -> WorkflowDef:
    datum = form.datum
    if not isinstance(datum, ListExpr) or len(datum.items) < 6:
        _raise_error(
            "`defworkflow` requires a name, params, return arrow, return type, and one body",
            span=form.span,
            form_path=form.form_path,
        )
    name_node = datum.items[1]
    if not isinstance(name_node, SymbolAtom):
        _raise_error("workflow name must be a symbol", span=form.span, form_path=form.form_path)
    params_node = datum.items[2]
    if not isinstance(params_node, ListExpr):
        _raise_error("workflow params must be a list", span=params_node.span, form_path=form.form_path)
    arrow_node = datum.items[3]
    if not isinstance(arrow_node, SymbolAtom) or arrow_node.value != "->":
        _raise_error("workflow return separator must be `->`", span=arrow_node.span, form_path=form.form_path)
    return_type_node = datum.items[4]
    if not isinstance(return_type_node, SymbolAtom):
        _raise_error(
            "workflow return type must be a symbol",
            span=return_type_node.span,
            form_path=form.form_path,
        )
    if len(datum.items) != 6:
        _raise_error("`defworkflow` requires exactly one body expression", span=form.span, form_path=form.form_path)

    params = tuple(_elaborate_param(param, form.form_path) for param in params_node.items)
    body_datum = datum.items[5]
    body = SyntaxNode(
        datum=body_datum,
        span=body_datum.span,
        module_path=form.module_path,
        form_path=form.form_path,
    )
    return WorkflowDef(
        name=name_node.value,
        params=params,
        return_type_name=return_type_node.value,
        body=body,
        span=form.span,
        form_path=form.form_path,
    )


def _elaborate_param(raw_param: object, form_path: tuple[str, ...]) -> WorkflowParam:
    if not isinstance(raw_param, ListExpr) or len(raw_param.items) != 2:
        span = raw_param.span if hasattr(raw_param, "span") else None
        if span is None:
            raise TypeError("workflow params must carry spans")
        _raise_error(
            "workflow params must be two-item lists of `(name Type)`",
            span=span,
            form_path=form_path,
        )
    name_node = raw_param.items[0]
    type_node = raw_param.items[1]
    if not isinstance(name_node, SymbolAtom):
        _raise_error("workflow param names must be symbols", span=name_node.span, form_path=form_path)
    if not isinstance(type_node, SymbolAtom):
        _raise_error("workflow param types must be symbols", span=type_node.span, form_path=form_path)
    return WorkflowParam(
        name=name_node.value,
        type_name=type_node.value,
        span=raw_param.span,
        form_path=form_path,
    )


def _raise_error(message: str, *, span: SourceSpan, form_path: tuple[str, ...]) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="frontend_parse_error",
                message=message,
                span=span,
                form_path=form_path,
            ),
        )
    )


def build_extern_environment(
    *,
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, str] | None = None,
) -> ExternEnvironment:
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
    diagnostics: list[LispFrontendDiagnostic] = []
    bindings: dict[str, ExternalToolBinding | CertifiedAdapterBinding] = {}

    for name, binding in (command_boundaries or {}).items():
        if not isinstance(name, str) or not name.strip():
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="command_adapter_missing_contract",
                    message="command boundary bindings require non-empty names",
                    span=_environment_span(),
                )
            )
            continue
        if not binding.stable_command or not all(isinstance(token, str) and token for token in binding.stable_command):
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="command_adapter_missing_contract",
                    message=f"command boundary `{name}` must declare a non-empty stable command",
                    span=_environment_span(),
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
                    )
                )
                continue
            if not binding.fixture_ids or not binding.negative_fixture_ids:
                diagnostics.append(
                    LispFrontendDiagnostic(
                        code="command_adapter_missing_contract",
                        message=f"certified adapter `{name}` requires positive and negative fixtures",
                        span=_environment_span(),
                    )
                )
                continue
        bindings[name] = binding

    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return CommandBoundaryEnvironment(bindings_by_name=bindings)


def _environment_span() -> SourceSpan:
    from .spans import SourcePosition

    position = SourcePosition(path="<stage3-environment>", line=1, column=1, offset=0)
    return SourceSpan(start=position, end=position)
