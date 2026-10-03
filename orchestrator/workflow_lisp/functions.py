"""Pure helper definitions, catalogs, validation, and normalization."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import InitVar, dataclass, field, replace
from hashlib import sha1
from typing import TYPE_CHECKING

from .compiler_session import CompilerSession
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expression_traversal import (
    _rebuild_with_replacements,
    free_expr_names,
    iter_child_exprs,
    map_expr,
    walk_expr,
)
from .expressions import (
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    CompilerListNonemptyHeadExpr,
    CondExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    ExprNode,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    FunctionCallExpr,
    IfExpr,
    LetStarExpr,
    ListExpr,
    ListMapEffectExpr,
    ListMapExpr,
    LiveProviderPeerBinding,
    LiveProviderBinding,
    LiteralExpr,
    MaterializeViewExpr,
    LoopStateField,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MatchArm,
    MatchExpr,
    NameExpr,
    PathJoinUnderExpr,
    PhaseTargetExpr,
    PureOpExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    RecordUpdateExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunRefExpr,
    TrialExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithLiveProviderPeersExpr,
    WithLiveProvidersExpr,
    WithPhaseExpr,
    WorkflowRefLiteralExpr,
    elaborate_expression,
)
from .result_guidance import ReturnSpec, parse_return_spec
from .prompts import PromptApplicationExpr
from .spans import SourceSpan
from .syntax import (
    ExpansionStack,
    HelperExpansionFrame,
    ProcedureExpansionFrame,
    SyntaxList,
    SyntaxNode,
    WorkflowLispSyntaxModule,
    syntax_head,
    syntax_identifier,
    syntax_node_datum,
    syntax_resolved_name,
    target_dsl_is_2_33_or_newer,
    target_dsl_supports_pure_call_composition,
    target_dsl_supports_strict_boolean_control_flow,
)
from .type_env import (
    FrontendTypeEnvironment,
    ProcRefTypeRef,
    TypeRef,
    WorkflowRefTypeRef,
    substitute_type_params,
    type_refs_compatible,
)
from .type_expressions import parse_type_expression, type_expression_names
from .typecheck import TypedExpr, typecheck_expression
from .wcc.hygiene import fresh_name, reserved_identifiers

if TYPE_CHECKING:
    from .procedures import ProcedureCatalog
    from .workflows import WorkflowCatalog


@dataclass(frozen=True)
class FunctionParam:
    """Authored `defun` parameter before type resolution."""

    name: str
    type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class FunctionDef:
    """Parsed pure helper definition."""

    name: str
    params: tuple[FunctionParam, ...]
    body: SyntaxNode
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    return_spec: ReturnSpec | None = field(
        default=None,
        repr=False,
        metadata={"json_name": "return_type_name", "json_value_attr": "type_name"},
    )
    return_type_name: InitVar[str | None] = None

    def __post_init__(self, return_type_name: str | None) -> None:
        if self.return_spec is None:
            if return_type_name is None:
                raise TypeError("function definitions require a return spec")
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=return_type_name, guidance=None, span=self.span),
            )
        elif return_type_name is not None and self.return_spec.type_name != return_type_name:
            object.__setattr__(
                self,
                "return_spec",
                replace(self.return_spec, type_name=return_type_name),
            )


FunctionDef.return_type_name = property(lambda self: self.return_spec.type_name)


@dataclass(frozen=True)
class FunctionSignature:
    """Type-resolved pure helper signature."""

    name: str
    params: tuple[tuple[str, TypeRef], ...]
    return_type_ref: TypeRef
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class TypedFunctionDef:
    """Pure helper definition after body typechecking."""

    definition: FunctionDef
    signature: FunctionSignature
    typed_body: TypedExpr


@dataclass(frozen=True)
class FunctionCatalog:
    """Lookup table for helper signatures, definitions, and call graph."""

    signatures_by_name: Mapping[str, FunctionSignature]
    definitions_by_name: Mapping[str, FunctionDef]
    call_graph: Mapping[str, frozenset[str]]


def elaborate_function_definitions(module_syntax: WorkflowLispSyntaxModule) -> tuple[FunctionDef, ...]:
    """Extract and parse every `defun` form in a syntax module."""

    definitions: list[FunctionDef] = []
    for form in module_syntax.forms:
        if syntax_resolved_name(syntax_head(form)) == "defun":
            definitions.append(_elaborate_function_definition(form))
    return tuple(definitions)


def build_function_catalog(
    function_defs: tuple[FunctionDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    imported_signatures: Mapping[str, FunctionSignature] | None = None,
    lookup_aliases: Mapping[str, str] | None = None,
) -> FunctionCatalog:
    """Build helper signatures and detect duplicate local definitions."""

    signatures_by_name: dict[str, FunctionSignature] = dict(imported_signatures or {})
    definitions_by_name: dict[str, FunctionDef] = {}
    diagnostics: list[LispFrontendDiagnostic] = []
    for function_def in function_defs:
        if function_def.name in definitions_by_name:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="function_definition_duplicate",
                    message=f"duplicate function definition `{function_def.name}`",
                    span=function_def.span,
                    form_path=function_def.form_path,
                    expansion_stack=function_def.expansion_stack,
                )
            )
            continue
        return_type_ref = type_env.resolve_type(
            function_def.return_type_name,
            span=function_def.span,
            form_path=function_def.form_path,
            expansion_stack=function_def.expansion_stack,
        )
        params: list[tuple[str, TypeRef]] = []
        for param in function_def.params:
            params.append(
                (
                    param.name,
                    type_env.resolve_type(
                        param.type_name,
                        span=param.span,
                        form_path=param.form_path,
                        expansion_stack=param.expansion_stack,
                    ),
                )
            )
        signatures_by_name[function_def.name] = FunctionSignature(
            name=function_def.name,
            params=tuple(params),
            return_type_ref=return_type_ref,
            span=function_def.span,
            form_path=function_def.form_path,
        )
        definitions_by_name[function_def.name] = function_def
    for alias_name, canonical_name in (lookup_aliases or {}).items():
        signature = signatures_by_name.get(canonical_name)
        if signature is not None:
            signatures_by_name[alias_name] = signature
    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return FunctionCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
        call_graph={},
    )


def typecheck_function_definitions(
    function_defs: tuple[FunctionDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    function_catalog: FunctionCatalog,
    workflow_catalog: "WorkflowCatalog | None" = None,
    procedure_catalog: "ProcedureCatalog | None" = None,
    function_name_resolver=None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
    prompt_catalog: object | None = None,
    compiler_session: CompilerSession | None = None,
) -> tuple[TypedFunctionDef, ...]:
    """Typecheck helper bodies against the pure expression subset."""

    compiler_session = compiler_session or CompilerSession()
    typed_functions: list[TypedFunctionDef] = []
    procedure_names = (
        frozenset()
        if procedure_catalog is None
        else frozenset(procedure_catalog.signatures_by_name)
    )
    function_names = frozenset(function_catalog.signatures_by_name)
    for function_def in function_defs:
        signature = function_catalog.signatures_by_name[function_def.name]
        value_env = {name: type_ref for name, type_ref in signature.params}
        body_expr = elaborate_expression(
            function_def.body,
            bound_names=frozenset(value_env),
            procedure_names=procedure_names,
            function_names=function_names,
            function_name_resolver=function_name_resolver,
            procedure_name_resolver=procedure_name_resolver,
            workflow_name_resolver=workflow_name_resolver,
            target_dsl_version=type_env.target_dsl_version,
            prompt_catalog=prompt_catalog,
            session_state=compiler_session.elaboration,
        )
        _validate_pure_function_expr(
            body_expr,
            function_def=function_def,
            procedure_catalog=procedure_catalog,
            target_dsl_version=type_env.target_dsl_version,
        )
        typed_body = typecheck_expression(
            body_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            function_catalog=function_catalog,
            prompt_catalog=prompt_catalog,
            expected_type=signature.return_type_ref,
            compiler_session=compiler_session,
            allow_provisional_procedure_calls=(
                target_dsl_supports_pure_call_composition(
                    type_env.target_dsl_version
                )
            ),
        )
        if not type_refs_compatible(signature.return_type_ref, typed_body.type_ref):
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="function_return_type_invalid",
                        message=(
                            f"function `{function_def.name}` declared return type "
                            f"`{function_def.return_type_name}` but body returned a different type"
                        ),
                        span=function_def.body.span,
                        form_path=function_def.body.form_path,
                        expansion_stack=function_def.body.expansion_stack,
                    ),
                )
            )
        typed_functions.append(
            TypedFunctionDef(
                definition=function_def,
                signature=signature,
                typed_body=typed_body,
            )
        )
    return tuple(typed_functions)


def retypecheck_resolved_function_definitions(
    typed_functions: tuple[TypedFunctionDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    function_catalog: FunctionCatalog,
    workflow_catalog: "WorkflowCatalog | None",
    procedure_catalog: "ProcedureCatalog | None",
    typed_procedures_by_name: Mapping[str, object],
    typed_workflows_by_name: Mapping[str, object],
    compiler_session: CompilerSession,
    inlined_constructor_type: Callable[[object, ExprNode], TypeRef] | None = None,
) -> tuple[TypedFunctionDef, ...]:
    """Strictly recheck every function after procedure selection has settled."""

    if not target_dsl_supports_pure_call_composition(type_env.target_dsl_version):
        return typed_functions

    typed_functions_by_name = {
        function.definition.name: function for function in typed_functions
    }
    rechecked: list[TypedFunctionDef] = []
    for function in typed_functions:
        normalized_functions = normalize_function_calls(
            function.typed_body,
            typed_functions_by_name=typed_functions_by_name,
            target_dsl_version=type_env.target_dsl_version,
        )
        normalized_body = normalize_resolved_inline_procedure_calls(
            normalized_functions,
            typed_procedures_by_name=typed_procedures_by_name,
            target_dsl_version=type_env.target_dsl_version,
            procedure_catalog=procedure_catalog,
            workflow_catalog=workflow_catalog,
            typed_workflows_by_name=typed_workflows_by_name,
            require_pure_procedure_calls=True,
            inlined_constructor_type=inlined_constructor_type,
        )
        typed_body = typecheck_expression(
            normalized_body.expr,
            type_env=type_env,
            value_env=dict(function.signature.params),
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            function_catalog=function_catalog,
            expected_type=function.signature.return_type_ref,
            compiler_session=compiler_session,
        )
        if not type_refs_compatible(function.signature.return_type_ref, typed_body.type_ref):
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="function_return_type_invalid",
                        message=(
                            f"function `{function.definition.name}` declared return type "
                            f"`{function.definition.return_type_name}` but body returned a different type"
                        ),
                        span=function.definition.body.span,
                        form_path=function.definition.body.form_path,
                        expansion_stack=function.definition.body.expansion_stack,
                    ),
                )
            )
        rechecked.append(replace(function, typed_body=typed_body))
    return tuple(rechecked)


def validate_function_cycles(
    typed_functions: tuple[TypedFunctionDef, ...],
    *,
    function_catalog: FunctionCatalog,
) -> FunctionCatalog:
    """Attach the helper call graph and reject recursive helper cycles."""

    typed_by_name = {function.definition.name: function for function in typed_functions}
    call_graph = {
        name: frozenset(_function_dependencies(function.typed_body.expr))
        for name, function in typed_by_name.items()
    }
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise LispFrontendCompileError(
                tuple(
                    LispFrontendDiagnostic(
                        code="function_cycle",
                        message=f"recursive pure helper cycle detected for `{cycle_name}`",
                        span=typed_by_name[cycle_name].definition.span,
                        form_path=typed_by_name[cycle_name].definition.form_path,
                        expansion_stack=typed_by_name[cycle_name].definition.expansion_stack,
                    )
                    for cycle_name in visiting[visiting.index(name):]
                )
            )
        visiting.append(name)
        for callee in call_graph.get(name, frozenset()):
            if callee in typed_by_name:
                visit(callee)
        visiting.pop()
        visited.add(name)

    for name in typed_by_name:
        visit(name)
    return replace(function_catalog, call_graph=call_graph)


def normalize_function_calls(
    node: TypedExpr | ExprNode,
    *,
    typed_functions_by_name: Mapping[str, TypedFunctionDef],
    target_dsl_version: str | None = None,
) -> TypedExpr | ExprNode:
    """Rewrite helper calls into `let*` plus existing pure expression nodes."""

    from .conditionals import normalize_expanded_conditions

    expand_admitted_containers: bool | _HygienicExpansionMode = (
        _HygienicExpansionMode()
        if target_dsl_supports_pure_call_composition(target_dsl_version or "")
        else target_dsl_supports_strict_boolean_control_flow(target_dsl_version or "")
    )

    def _rewrite(expr: ExprNode) -> ExprNode:
        expanded = _normalize_expr(expr, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
        return normalize_expanded_conditions(
            expanded,
            target_dsl_version=target_dsl_version,
        )

    if isinstance(node, TypedExpr):
        return replace(node, expr=_rewrite(node.expr))
    return _rewrite(node)


def _normalize_expr(
    expr: ExprNode,
    *,
    typed_functions_by_name: Mapping[str, TypedFunctionDef],
    expand_admitted_containers: bool | _HygienicExpansionMode,
) -> ExprNode:
    if isinstance(expr, FunctionCallExpr):
        function_def = typed_functions_by_name[expr.callee_name]
        helper_frame = HelperExpansionFrame(
            function_name=function_def.definition.name,
            call_span=expr.span,
            definition_span=function_def.definition.span,
        )
        helper_stack = expr.expansion_stack + (helper_frame,)
        cloned_body = _clone_function_expr(
            function_def.typed_body.expr,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=helper_stack,
        )
        normalized_args = tuple(
            _normalize_expr(arg, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
            for arg in expr.args
        )
        call_bindings = (
            _ordered_call_bindings(
                params=function_def.signature.params,
                args=normalized_args,
                source_expr=expr,
                role="function",
                allocator=expand_admitted_containers,
            )
            if isinstance(expand_admitted_containers, _HygienicExpansionMode)
            else _sequential_call_bindings(
                params=function_def.signature.params,
                args=normalized_args,
                body=cloned_body,
            )
        )
        if call_bindings.formal_names or isinstance(expand_admitted_containers, _HygienicExpansionMode):
            cloned_body = _rename_free_names(cloned_body, call_bindings.formal_names)
        bindings = call_bindings.bindings
        return LetStarExpr(
            bindings=bindings,
            body=_normalize_expr(
                cloned_body,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=helper_stack,
        )
    if isinstance(expr, RecordExpr):
        return replace(
            expr,
            fields=tuple(
                (
                    field_name,
                    _normalize_expr(field_expr, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
                )
                for field_name, field_expr in expr.fields
            ),
        )
    if isinstance(expr, PureOpExpr):
        return replace(
            expr,
            args=tuple(
                _normalize_expr(arg, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
                for arg in expr.args
            ),
        )
    if isinstance(expr, ListExpr):
        return replace(
            expr,
            items=tuple(
                _normalize_expr(item, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
                for item in expr.items
            ),
        )
    if isinstance(expr, (ListMapExpr, ListMapEffectExpr)):
        return replace(
            expr,
            source_expr=_normalize_expr(
                expr.source_expr,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
            body_expr=_normalize_expr(
                expr.body_expr,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
        )
    if isinstance(expr, CompilerListNonemptyHeadExpr):
        return replace(
            expr,
            source_expr=_normalize_expr(
                expr.source_expr,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
        )
    if isinstance(expr, PathJoinUnderExpr):
        return replace(
            expr,
            child_expr=_normalize_expr(
                expr.child_expr,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
        )
    if isinstance(expr, RecordUpdateExpr):
        return replace(
            expr,
            base_expr=_normalize_expr(
                expr.base_expr,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
            overrides=tuple(
                (
                    field_name,
                    _normalize_expr(field_expr, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
                )
                for field_name, field_expr in expr.overrides
            ),
        )
    if isinstance(expr, LoopStateSeedExpr):
        return replace(
            expr,
            fields=tuple(
                LoopStateField(
                    name=field.name,
                    type_name=field.type_name,
                    value_expr=_normalize_expr(
                        field.value_expr,
                        typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
                    ),
                    span=field.span,
                    form_path=field.form_path,
                    expansion_stack=field.expansion_stack,
                    resolved_type_ref=field.resolved_type_ref,
                )
                for field in expr.fields
            ),
        )
    if isinstance(expr, LoopStateUpdateExpr):
        return replace(
            expr,
            base_expr=_normalize_expr(
                expr.base_expr,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
            overrides=tuple(
                (
                    field_name,
                    _normalize_expr(field_expr, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
                )
                for field_name, field_expr in expr.overrides
            ),
        )
    if isinstance(expr, UnionVariantExpr):
        return replace(
            expr,
            fields=tuple(
                (
                    field_name,
                    _normalize_expr(field_expr, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
                )
                for field_name, field_expr in expr.fields
            ),
        )
    if isinstance(expr, LetStarExpr):
        return replace(
            expr,
            bindings=tuple(
                (
                    name,
                    _normalize_expr(binding_expr, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
                )
                for name, binding_expr in expr.bindings
            ),
            body=_normalize_expr(expr.body, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
            condition_normalization_input=(
                _normalize_expr(
                    expr.condition_normalization_input,
                    typed_functions_by_name=typed_functions_by_name,
                    expand_admitted_containers=expand_admitted_containers,
                )
                if expr.condition_normalization_input is not None
                else None
            ),
        )
    if isinstance(expr, IfExpr):
        return replace(
            expr,
            condition_expr=_normalize_expr(
                expr.condition_expr,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
            then_expr=_normalize_expr(
                expr.then_expr,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
            else_expr=_normalize_expr(
                expr.else_expr,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
        )
    if isinstance(expr, MatchExpr):
        return replace(
            expr,
            subject=_normalize_expr(expr.subject, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
            arms=tuple(
                replace(
                    arm,
                    body=_normalize_expr(arm.body, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
                )
                for arm in expr.arms
            ),
        )
    if isinstance(expr, CallExpr):
        return replace(
            expr,
            bindings=tuple(
                (
                    binding_name,
                    _normalize_expr(binding_expr, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
                )
                for binding_name, binding_expr in expr.bindings
            ),
        )
    if isinstance(expr, CommandResultExpr):
        return replace(
            expr,
            argv=tuple(
                _normalize_expr(arg, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
                for arg in expr.argv
            ),
            adapter_inputs=tuple(
                (
                    field_name,
                    _normalize_expr(
                        value_expr,
                        typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
                    ),
                )
                for field_name, value_expr in expr.adapter_inputs
            ),
        )
    if isinstance(expr, ProviderResultExpr):
        normalized_prompt = (
            replace(
                expr.prompt,
                fills=tuple(
                    replace(
                        fill,
                        value_expr=_normalize_expr(
                            fill.value_expr,
                            typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
                        ),
                    )
                    for fill in expr.prompt.fills
                ),
            )
            if isinstance(expr.prompt, PromptApplicationExpr)
            else _normalize_expr(
                expr.prompt,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            )
        )
        return replace(
            expr,
            provider=_normalize_expr(expr.provider, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
            prompt=normalized_prompt,
            inputs=tuple(
                _normalize_expr(arg, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
                for arg in expr.inputs
            ),
            model=(
                _normalize_expr(expr.model, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
                if expr.model is not None
                else None
            ),
            effort=(
                _normalize_expr(expr.effort, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
                if expr.effort is not None
                else None
            ),
            prompt_dependencies=(
                replace(
                    expr.prompt_dependencies,
                    required=tuple(
                        _normalize_expr(item, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
                        for item in expr.prompt_dependencies.required
                    ),
                    optional=tuple(
                        _normalize_expr(item, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
                        for item in expr.prompt_dependencies.optional
                    ),
                )
                if expr.prompt_dependencies is not None
                else None
            ),
            context_expr=(
                _normalize_expr(expr.context_expr, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
                if expr.context_expr is not None
                else None
            ),
        )
    if isinstance(expr, WithLiveProvidersExpr):
        return replace(
            expr,
            bindings=tuple(
                LiveProviderBinding(
                    name=binding.name,
                    value_expr=_normalize_expr(
                        binding.value_expr,
                        typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
                    ),
                    observes=binding.observes,
                    name_span=binding.name_span,
                    observes_span=binding.observes_span,
                    observed_name_span=binding.observed_name_span,
                    span=binding.span,
                    form_path=binding.form_path,
                    expansion_stack=binding.expansion_stack,
                )
                for binding in expr.bindings
            ),
            body=_normalize_expr(
                expr.body,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
        )
    if isinstance(expr, WithLiveProviderPeersExpr):
        return replace(
            expr,
            bindings=tuple(
                LiveProviderPeerBinding(
                    name=binding.name,
                    value_expr=_normalize_expr(
                        binding.value_expr,
                        typed_functions_by_name=typed_functions_by_name,
                        expand_admitted_containers=expand_admitted_containers,
                    ),
                    name_span=binding.name_span,
                    span=binding.span,
                    form_path=binding.form_path,
                    expansion_stack=binding.expansion_stack,
                )
                for binding in expr.bindings
            ),
            body=_normalize_expr(
                expr.body,
                typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers,
            ),
        )
    if isinstance(expr, WithPhaseExpr):
        return replace(
            expr,
            ctx_expr=_normalize_expr(expr.ctx_expr, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
            body=_normalize_expr(expr.body, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers),
        )
    if isinstance(expr, FieldAccessExpr):
        return replace(
            expr,
            base=_clone_function_expr(
                expr.base,
                span=expr.base.span,
                form_path=expr.base.form_path,
                expansion_stack=expr.base.expansion_stack,
            ),
        )
    if not expand_admitted_containers:
        return expr
    children = iter_child_exprs(expr)
    if not children:
        return expr
    replacements = {
        id(child): _normalize_expr(child, typed_functions_by_name=typed_functions_by_name, expand_admitted_containers=expand_admitted_containers)
        for child in children
    }
    return _rebuild_with_replacements(expr, replacements)


def normalize_resolved_inline_procedure_calls(
    node: TypedExpr | ExprNode,
    *,
    typed_procedures_by_name: Mapping[str, object],
    target_dsl_version: str | None,
    owning_proc_ref_bindings: Mapping[str, object] | None = None,
    owning_workflow_ref_bindings: Mapping[str, object] | None = None,
    procedure_catalog: "ProcedureCatalog | None" = None,
    workflow_catalog: "WorkflowCatalog | None" = None,
    typed_workflows_by_name: Mapping[str, object] | None = None,
    require_pure_procedure_calls: bool = False,
    inlined_constructor_type: Callable[[object, ExprNode], TypeRef] | None = None,
) -> TypedExpr | ExprNode:
    """Reduce final-inline procedure calls through the shared typed-expression path.

    From target 2.33, each `record` and `variant` constructor copied out of a
    selected procedure's body carries `inlined_constructor_type(procedure,
    constructor)`, the type the procedure's own environment resolves it to.
    Without it the copy keeps only its type text, as below 2.33.
    """

    if not target_dsl_supports_pure_call_composition(target_dsl_version or ""):
        return node

    from .conditionals import normalize_expanded_conditions
    from .procedure_refs import resolve_proc_ref_value
    from .procedure_specialization import materialized_specialization_rows
    from .workflow_refs import resolve_workflow_ref_expr

    active_callees: set[str] = set()
    allocator = _HygienicExpansionMode()

    def select_materialized_procedure(
        procedure: object,
        *,
        args: tuple[ExprNode, ...],
        proc_ref_bindings: Mapping[str, object],
        workflow_ref_bindings: Mapping[str, object],
    ) -> object | None:
        """Consume the exact settled row selected by shared ref resolvers."""

        specialization = getattr(procedure, "specialization", None)
        selected_proc_bindings = dict(
            getattr(specialization, "proc_ref_bindings", {})
        )
        selected_workflow_bindings = dict(
            getattr(specialization, "workflow_ref_bindings", {})
        )
        for arg, (param_name, param_type) in zip(
            args, procedure.signature.params, strict=True
        ):
            if isinstance(param_type, ProcRefTypeRef) and procedure_catalog is not None:
                resolved = resolve_proc_ref_value(
                    arg,
                    procedure_catalog=procedure_catalog,
                    proc_ref_env=proc_ref_bindings,
                    expected_type=param_type,
                )
                if resolved is not None:
                    selected_proc_bindings[param_name] = resolved
            elif isinstance(param_type, WorkflowRefTypeRef):
                resolved = workflow_ref_bindings.get(arg.name) if isinstance(arg, NameExpr) else None
                if (
                    resolved is None
                    and workflow_catalog is not None
                    and isinstance(arg, WorkflowRefLiteralExpr | NameExpr | EnumMemberExpr)
                    and not (isinstance(arg, NameExpr) and arg.name in workflow_ref_bindings)
                ):
                    resolved = resolve_workflow_ref_expr(
                        arg,
                        workflow_catalog=workflow_catalog,
                        span=arg.span,
                        form_path=arg.form_path,
                        expansion_stack=arg.expansion_stack,
                        expected_type=param_type,
                        typed_workflows_by_name=typed_workflows_by_name,
                        allow_extern_rebinding=True,
                    )
                if resolved is not None:
                    selected_workflow_bindings[param_name] = resolved
        required_proc_bindings = {
            param_name
            for param_name, param_type in procedure.signature.params
            if isinstance(param_type, ProcRefTypeRef)
        }
        required_workflow_bindings = {
            param_name
            for param_name, param_type in procedure.signature.params
            if isinstance(param_type, WorkflowRefTypeRef)
        }
        if (
            not required_proc_bindings.issubset(selected_proc_bindings)
            or not required_workflow_bindings.issubset(selected_workflow_bindings)
        ):
            return None
        if not selected_proc_bindings and not selected_workflow_bindings:
            return procedure
        rows = materialized_specialization_rows(
            procedure,
            workflow_ref_bindings=selected_workflow_bindings,
            proc_ref_bindings=selected_proc_bindings,
            typed_procedures=typed_procedures_by_name,
        )
        if len(rows) != 1:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="procedure_lowering_unresolved",
                        message=(
                            "compiler-owned procedure specialization row is "
                            "missing or ambiguous during pure-call normalization"
                        ),
                        span=args[0].span if args else procedure.definition.span,
                        form_path=(args[0].form_path if args else procedure.definition.form_path),
                        expansion_stack=(
                            args[0].expansion_stack if args else procedure.definition.expansion_stack
                        ),
                    ),
                )
            )
        return rows[0]

    def rewrite(
        expr: ExprNode,
        *,
        proc_ref_bindings: Mapping[str, object],
        workflow_ref_bindings: Mapping[str, object],
    ) -> ExprNode:
        def representation_unsupported() -> LispFrontendCompileError:
            return LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="pure_call_representation_unsupported",
                        message=(
                            "procedure calls inside an expanded pure function "
                            "must resolve to an effect-free inline specialization"
                        ),
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                )
            )

        if isinstance(expr, LetStarExpr):
            retained_input = (
                rewrite(
                    expr.condition_normalization_input,
                    proc_ref_bindings=proc_ref_bindings,
                    workflow_ref_bindings=workflow_ref_bindings,
                )
                if expr.condition_normalization_input is not None
                else None
            )
            child_proc_ref_bindings = dict(proc_ref_bindings)
            child_workflow_ref_bindings = dict(workflow_ref_bindings)
            rewritten_bindings: list[tuple[str, ExprNode]] = []
            for binding_name, binding_expr in expr.bindings:
                rewritten_binding = rewrite(
                    binding_expr,
                    proc_ref_bindings=child_proc_ref_bindings,
                    workflow_ref_bindings=child_workflow_ref_bindings,
                )
                rewritten_bindings.append((binding_name, rewritten_binding))
                if procedure_catalog is not None:
                    resolved_proc_ref = resolve_proc_ref_value(
                        rewritten_binding,
                        procedure_catalog=procedure_catalog,
                        proc_ref_env=child_proc_ref_bindings,
                    )
                    if resolved_proc_ref is not None:
                        child_proc_ref_bindings[binding_name] = resolved_proc_ref
                if (
                    workflow_catalog is not None
                    and isinstance(
                        rewritten_binding,
                        WorkflowRefLiteralExpr | NameExpr | EnumMemberExpr,
                    )
                ):
                    resolved_workflow_ref = (
                        child_workflow_ref_bindings.get(rewritten_binding.name)
                        if isinstance(rewritten_binding, NameExpr)
                        else resolve_workflow_ref_expr(
                            rewritten_binding,
                            workflow_catalog=workflow_catalog,
                            span=rewritten_binding.span,
                            form_path=rewritten_binding.form_path,
                            expansion_stack=rewritten_binding.expansion_stack,
                            typed_workflows_by_name=typed_workflows_by_name,
                            allow_extern_rebinding=True,
                        )
                    )
                    if resolved_workflow_ref is not None or (
                        isinstance(rewritten_binding, NameExpr)
                        and rewritten_binding.name in child_workflow_ref_bindings
                    ):
                        child_workflow_ref_bindings[binding_name] = resolved_workflow_ref
            return replace(
                expr,
                bindings=tuple(rewritten_bindings),
                body=rewrite(
                    expr.body,
                    proc_ref_bindings=child_proc_ref_bindings,
                    workflow_ref_bindings=child_workflow_ref_bindings,
                ),
                condition_normalization_input=retained_input,
            )
        if isinstance(expr, ProcedureCallExpr):
            rewritten_args = tuple(
                rewrite(
                    arg,
                    proc_ref_bindings=proc_ref_bindings,
                    workflow_ref_bindings=workflow_ref_bindings,
                )
                for arg in expr.args
            )
            selected_binding = proc_ref_bindings.get(expr.callee_name)
            selected_name = getattr(selected_binding, "call_target_name", expr.callee_name)
            candidate_procedure = typed_procedures_by_name.get(selected_name)
            procedure = candidate_procedure
            expansion_args = rewritten_args
            if candidate_procedure is not None:
                authored_params = candidate_procedure.signature.params
                selected_procedure = select_materialized_procedure(
                    candidate_procedure,
                    args=rewritten_args,
                    proc_ref_bindings=proc_ref_bindings,
                    workflow_ref_bindings=workflow_ref_bindings,
                )
                if selected_procedure is None:
                    return replace(expr, args=rewritten_args)
                procedure = selected_procedure
                selected_specialization = getattr(procedure, "specialization", None)
                selected_compile_time_params = {
                    *getattr(selected_specialization, "proc_ref_bindings", {}),
                    *getattr(selected_specialization, "workflow_ref_bindings", {}),
                }
                if selected_compile_time_params and len(rewritten_args) == len(authored_params):
                    expansion_args = tuple(
                        arg
                        for arg, (param_name, _) in zip(
                            rewritten_args, authored_params, strict=True
                        )
                        if param_name not in selected_compile_time_params
                    )
            procedure_effect_summary = getattr(
                procedure, "transitive_effect_summary", None
            )
            is_pure_function_expansion = require_pure_procedure_calls or any(
                isinstance(frame, HelperExpansionFrame)
                for frame in expr.expansion_stack
            )
            if (
                procedure is not None
                and is_pure_function_expansion
                and procedure_effect_summary is not None
                and (
                    procedure_effect_summary.direct_effects
                    or procedure_effect_summary.transitive_effects
                )
            ):
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="pure_function_has_effect",
                            message=(
                                "function calls may not expand an effectful procedure "
                                "into a pure expression"
                            ),
                            span=expr.span,
                            form_path=expr.form_path,
                            expansion_stack=expr.expansion_stack,
                        ),
                    )
                )
            if (
                procedure is not None
                and is_pure_function_expansion
                and (
                    getattr(
                        getattr(procedure, "resolved_lowering_mode", None), "value", None
                    )
                    != "inline"
                    or procedure_effect_summary is None
                )
            ):
                raise representation_unsupported()
            if (
                procedure is None
                or getattr(getattr(procedure, "resolved_lowering_mode", None), "value", None)
                != "inline"
                or procedure_effect_summary is None
                or procedure_effect_summary.direct_effects
                or procedure_effect_summary.transitive_effects
                or procedure.definition.name in active_callees
            ):
                return replace(expr, args=rewritten_args)
            signature = procedure.signature
            if len(expansion_args) != len(signature.params):
                return replace(expr, args=rewritten_args)
            if any(
                isinstance(candidate, WorkflowRefLiteralExpr)
                for candidate in walk_expr(procedure.typed_body.expr)
            ):
                if is_pure_function_expansion:
                    raise representation_unsupported()
                return replace(expr, args=rewritten_args)
            active_callees.add(procedure.definition.name)
            try:
                helper_stack = expr.expansion_stack + (
                    ProcedureExpansionFrame(
                        procedure_name=procedure.definition.name,
                        call_span=expr.span,
                        definition_span=procedure.definition.span,
                    ),
                )
                try:
                    cloned_body = _clone_function_expr(
                        procedure.typed_body.expr,
                        span=expr.span,
                        form_path=expr.form_path,
                        expansion_stack=helper_stack,
                    )
                except TypeError:
                    if is_pure_function_expansion:
                        raise representation_unsupported() from None
                    return replace(expr, args=rewritten_args)
                if inlined_constructor_type is not None and target_dsl_is_2_33_or_newer(
                    target_dsl_version or ""
                ):
                    # A generic template calling an unspecialized generic
                    # procedure records no type arguments for the call, so
                    # type text naming the callee's parameters has no type
                    # to resolve to. Keep the call; each specialization of
                    # the template calls a specialization of the callee.
                    if _type_text_names(cloned_body) & {
                        type_param.name for type_param in signature.type_params
                    }:
                        if is_pure_function_expansion:
                            raise representation_unsupported()
                        return replace(expr, args=rewritten_args)
                    cloned_body = _with_resolved_constructor_types(
                        cloned_body,
                        lambda constructor: inlined_constructor_type(procedure, constructor),
                    )
                call_bindings = _ordered_call_bindings(
                    params=signature.params,
                    args=expansion_args,
                    source_expr=expr,
                    role="procedure",
                    allocator=allocator,
                )
                specialization = getattr(procedure, "specialization", None)
                cloned_body = _substitute_expanded_loop_state_type_facts(
                    cloned_body,
                    dict(getattr(specialization, "type_bindings", {})),
                )
                bound_param_types = dict(
                    getattr(specialization, "bound_param_types", {})
                )
                static_value_bindings = dict(
                    getattr(specialization, "value_bindings", {})
                )
                static_params = tuple(
                    (param_name, bound_param_types[param_name])
                    for param_name in static_value_bindings
                    if param_name in bound_param_types
                )
                static_call_bindings = _ordered_call_bindings(
                    params=static_params,
                    args=tuple(
                        rewrite(
                            static_value_bindings[param_name],
                            proc_ref_bindings=proc_ref_bindings,
                            workflow_ref_bindings=workflow_ref_bindings,
                        )
                        for param_name, _ in static_params
                    ),
                    source_expr=expr,
                    role="procedure_bound",
                    allocator=allocator,
                )
                bound_capture_sources = {
                    argument.name: argument
                    for argument in getattr(selected_binding, "bound_args", ())
                }
                static_capture_rows = tuple(
                    (
                        argument.source_binding_identity,
                        argument.type_ref,
                    )
                    if (argument := bound_capture_sources.get(param_name)) is not None
                    and argument.source_binding_identity is not None
                    else None
                    for param_name, _type_ref in static_params
                )
                body_proc_ref_bindings = dict(
                    getattr(getattr(procedure, "specialization", None), "proc_ref_bindings", {})
                )
                body_workflow_ref_bindings = dict(
                    getattr(
                        getattr(procedure, "specialization", None),
                        "workflow_ref_bindings",
                        {},
                    )
                )
                # Formals are renamed before nested calls expand: a nested
                # call copies in the bound values of its callee's
                # specialization, whose names belong to their definition.
                expanded = LetStarExpr(
                    bindings=(
                        *static_call_bindings.bindings,
                        *call_bindings.bindings,
                    ),
                    body=rewrite(
                        _rename_free_names(
                            cloned_body,
                            {
                                **static_call_bindings.formal_names,
                                **call_bindings.formal_names,
                            },
                        ),
                        proc_ref_bindings=body_proc_ref_bindings,
                        workflow_ref_bindings=body_workflow_ref_bindings,
                    ),
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=helper_stack,
                    binding_labels=(
                        None,
                    ) * (len(static_call_bindings.bindings) + len(call_bindings.bindings)),
                    binding_capture_sources=(
                        *static_capture_rows,
                        *((None,) * (len(static_call_bindings.bindings) - len(static_capture_rows))),
                        *((None,) * len(call_bindings.bindings)),
                    ),
                )
                return expanded
            finally:
                active_callees.remove(procedure.definition.name)
        children = iter_child_exprs(expr)
        if not children:
            return expr
        replacements = {
            id(child): rewrite(
                child,
                proc_ref_bindings=proc_ref_bindings,
                workflow_ref_bindings=workflow_ref_bindings,
            )
            for child in children
            if isinstance(child, ExprNode)
        }
        return _rebuild_with_replacements(expr, replacements) if replacements else expr

    if isinstance(node, TypedExpr):
        return replace(
            node,
            expr=normalize_expanded_conditions(
                rewrite(
                    node.expr,
                    proc_ref_bindings=dict(owning_proc_ref_bindings or {}),
                    workflow_ref_bindings=dict(owning_workflow_ref_bindings or {}),
                ),
                target_dsl_version=target_dsl_version,
            ),
        )
    return normalize_expanded_conditions(
        rewrite(
            node,
            proc_ref_bindings=dict(owning_proc_ref_bindings or {}),
            workflow_ref_bindings=dict(owning_workflow_ref_bindings or {}),
        ),
        target_dsl_version=target_dsl_version,
    )


def _type_text_names(expr: ExprNode) -> frozenset[str]:
    """Return every type name written by the record and variant constructors in `expr`."""

    return frozenset().union(
        *(
            type_expression_names(
                parse_type_expression(node.type_name, span=node.span, form_path=node.form_path)
            )
            for node in walk_expr(expr)
            if isinstance(node, RecordExpr | UnionVariantExpr)
        )
    )


def _with_resolved_constructor_types(
    expr: ExprNode,
    constructor_type: Callable[[ExprNode], TypeRef],
) -> ExprNode:
    """Give each `record` and `variant` constructor in a copied body its resolved type.

    The copy is retyped and lowered in the caller's module, which may not see
    these types; the carried `resolved_type` is used there instead of the
    text. A constructor that already carries a type was inlined into the body
    when the body's own module was compiled; `constructor_type` receives it
    as well, since that type is written as the body's module sees it.
    """

    def rewrite(node: ExprNode) -> ExprNode:
        retained_input = (
            rewrite(node.condition_normalization_input)
            if isinstance(node, LetStarExpr)
            and node.condition_normalization_input is not None
            else None
        )
        children = iter_child_exprs(node)
        if children:
            node = _rebuild_with_replacements(
                node, {id(child): rewrite(child) for child in children}
            )
        if isinstance(node, LetStarExpr) and node.condition_normalization_input is not retained_input:
            node = replace(node, condition_normalization_input=retained_input)
        if isinstance(node, RecordExpr | UnionVariantExpr):
            return replace(node, resolved_type=constructor_type(node))
        return node

    return rewrite(expr)


@dataclass
class _HygienicExpansionMode:
    """Per-normalization allocator for compiler-owned lexical names."""

    ordinal: int = 0
    reserved_names: set[str] = field(default_factory=set)

    def reserve_expr(self, expr: ExprNode) -> None:
        self.reserved_names.update(
            node.name for node in walk_expr(expr) if isinstance(node, NameExpr)
        )

    def fresh(self, *, role: str, source_expr: ExprNode) -> str:
        self.ordinal += 1
        basis = (
            f"{role}:{source_expr.form_path}:{source_expr.span.start.offset}:{self.ordinal}"
        )
        digest = sha1(basis.encode("utf-8")).hexdigest()[:12]
        candidate = f"__pure_{role}_{digest}"
        suffix = 0
        while candidate in self.reserved_names:
            suffix += 1
            candidate = f"__pure_{role}_{digest}_{suffix}"
        self.reserved_names.add(candidate)
        return candidate


@dataclass(frozen=True)
class _OrderedCallBindings:
    bindings: tuple[tuple[str, ExprNode], ...]
    formal_names: Mapping[str, str]


def _ordered_call_bindings(
    *,
    params: tuple[tuple[str, TypeRef], ...],
    args: tuple[ExprNode, ...],
    source_expr: ExprNode,
    role: str,
    allocator: _HygienicExpansionMode,
) -> _OrderedCallBindings:
    """Evaluate caller arguments before binding formal names."""

    allocator.reserve_expr(source_expr)
    for arg in args:
        allocator.reserve_expr(arg)
    temp_names = tuple(
        allocator.fresh(role=f"{role}_arg", source_expr=source_expr)
        for _ in args
    )
    formal_names = {
        param_name: allocator.fresh(role=f"{role}_param", source_expr=source_expr)
        for param_name, _ in params
    }
    temporary_bindings = tuple(zip(temp_names, args, strict=True))
    formal_bindings = tuple(
        (
            formal_names[param_name],
            NameExpr(
                name=temp_name,
                span=source_expr.span,
                form_path=source_expr.form_path,
                expansion_stack=source_expr.expansion_stack,
            ),
        )
        for (param_name, _), temp_name in zip(params, temp_names, strict=True)
    )
    return _OrderedCallBindings(
        bindings=(*temporary_bindings, *formal_bindings),
        formal_names=formal_names,
    )


def _sequential_call_bindings(
    *,
    params: tuple[tuple[str, TypeRef], ...],
    args: tuple[ExprNode, ...],
    body: ExprNode,
) -> _OrderedCallBindings:
    """Bind each parameter to its argument in order, as targets below 2.30 do.

    `let*` binds in order, so a parameter would capture a later argument's
    reference to the caller's binding of the same name. Such a parameter gets
    a fresh name, which the body's references follow.
    """

    formal_names: dict[str, str] = {}
    for index, (param_name, _) in enumerate(params):
        if any(param_name in free_expr_names(arg) for arg in args[index + 1 :]):
            reserved = reserved_identifiers((*args, body), value_env={}, compile_time_bindings={})
            formal_names[param_name] = fresh_name(param_name, reserved | {name for name, _ in params} | set(formal_names.values()))
    return _OrderedCallBindings(
        bindings=tuple((formal_names.get(param_name, param_name), arg) for (param_name, _), arg in zip(params, args, strict=True)),
        formal_names=formal_names,
    )


def _rename_free_names(expr: ExprNode, names: Mapping[str, str]) -> ExprNode:
    """Alpha-rename expanded formal references without crossing local binders."""

    rewritten = map_expr(
        expr,
        lambda name: replace(name, name=names.get(name.name, name.name)),
    )
    assert isinstance(rewritten, ExprNode)
    return rewritten


def _clone_function_expr(
    expr: ExprNode,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack,
) -> ExprNode:
    if isinstance(expr, NameExpr | LiteralExpr | EnumMemberExpr | ProcRefLiteralExpr):
        return replace(expr, span=span, form_path=form_path, expansion_stack=expansion_stack)
    if isinstance(expr, FieldAccessExpr):
        return replace(
            expr,
            base=_clone_function_expr(
                expr.base,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, RecordExpr):
        return replace(
            expr,
            fields=tuple(
                (
                    field_name,
                    _clone_function_expr(
                        field_expr,
                        span=span,
                        form_path=form_path,
                        expansion_stack=expansion_stack,
                    ),
                )
                for field_name, field_expr in expr.fields
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, PureOpExpr):
        return replace(
            expr,
            args=tuple(
                _clone_function_expr(
                    arg,
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                )
                for arg in expr.args
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, ListExpr):
        return replace(
            expr,
            items=tuple(
                _clone_function_expr(
                    item,
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                )
                for item in expr.items
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, (ListMapExpr, ListMapEffectExpr)):
        return replace(
            expr,
            source_expr=_clone_function_expr(
                expr.source_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            body_expr=_clone_function_expr(
                expr.body_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, CompilerListNonemptyHeadExpr):
        return replace(
            expr,
            source_expr=_clone_function_expr(
                expr.source_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, PathJoinUnderExpr):
        return replace(
            expr,
            child_expr=_clone_function_expr(
                expr.child_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, RecordUpdateExpr):
        return replace(
            expr,
            base_expr=_clone_function_expr(
                expr.base_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            overrides=tuple(
                (
                    field_name,
                    _clone_function_expr(
                        field_expr,
                        span=span,
                        form_path=form_path,
                        expansion_stack=expansion_stack,
                    ),
                )
                for field_name, field_expr in expr.overrides
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, LoopStateSeedExpr):
        return replace(
            expr,
            fields=tuple(
                LoopStateField(
                    name=field.name,
                    type_name=field.type_name,
                    value_expr=_clone_function_expr(
                        field.value_expr,
                        span=span,
                        form_path=form_path,
                        expansion_stack=expansion_stack,
                    ),
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                    resolved_type_ref=field.resolved_type_ref,
                )
                for field in expr.fields
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, LoopStateUpdateExpr):
        return replace(
            expr,
            base_expr=_clone_function_expr(
                expr.base_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            overrides=tuple(
                (
                    field_name,
                    _clone_function_expr(
                        field_expr,
                        span=span,
                        form_path=form_path,
                        expansion_stack=expansion_stack,
                    ),
                )
                for field_name, field_expr in expr.overrides
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, UnionVariantExpr):
        return replace(
            expr,
            fields=tuple(
                (
                    field_name,
                    _clone_function_expr(
                        field_expr,
                        span=span,
                        form_path=form_path,
                        expansion_stack=expansion_stack,
                    ),
                )
                for field_name, field_expr in expr.fields
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, LetStarExpr):
        return replace(
            expr,
            bindings=tuple(
                (
                    name,
                    _clone_function_expr(
                        binding_expr,
                        span=span,
                        form_path=form_path,
                        expansion_stack=expansion_stack,
                    ),
                )
                for name, binding_expr in expr.bindings
            ),
            body=_clone_function_expr(
                expr.body,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            condition_normalization_input=(
                _clone_function_expr(
                    expr.condition_normalization_input,
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                )
                if expr.condition_normalization_input is not None
                else None
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, IfExpr):
        return replace(
            expr,
            condition_expr=_clone_function_expr(
                expr.condition_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            then_expr=_clone_function_expr(
                expr.then_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            else_expr=_clone_function_expr(
                expr.else_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, MatchExpr):
        return replace(
            expr,
            subject=_clone_function_expr(
                expr.subject,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            arms=tuple(
                MatchArm(
                    variant_name=arm.variant_name,
                    binding_name=arm.binding_name,
                    body=_clone_function_expr(
                        arm.body,
                        span=span,
                        form_path=form_path,
                        expansion_stack=expansion_stack,
                    ),
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                    binding_label=arm.binding_label,
                )
                for arm in expr.arms
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, FunctionCallExpr):
        return replace(
            expr,
            args=tuple(
                _clone_function_expr(
                    arg,
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                )
                for arg in expr.args
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, ProcedureCallExpr):
        return replace(
            expr,
            args=tuple(
                _clone_function_expr(
                    arg,
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                )
                for arg in expr.args
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    if isinstance(expr, BindProcExpr):
        return replace(
            expr,
            base_expr=_clone_function_expr(
                expr.base_expr,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            bindings=tuple(
                replace(
                    binding,
                    value_expr=_clone_function_expr(
                        binding.value_expr,
                        span=span,
                        form_path=form_path,
                        expansion_stack=expansion_stack,
                    ),
                )
                for binding in expr.bindings
            ),
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    raise TypeError(f"unsupported pure helper expression clone: {type(expr)!r}")


def _substitute_expanded_loop_state_type_facts(
    expr: ExprNode,
    type_bindings: Mapping[str, TypeRef],
) -> ExprNode:
    """Substitute retained loop-state field types in one selected specialization."""

    if not type_bindings:
        return expr

    rewritten_by_id: dict[int, ExprNode] = {}

    def rewrite(node: ExprNode) -> ExprNode:
        known = rewritten_by_id.get(id(node))
        if known is not None:
            return known
        children = iter_child_exprs(node)
        replacements = {id(child): rewrite(child) for child in children}
        rewritten = (
            _rebuild_with_replacements(node, replacements)
            if any(replacements[id(child)] is not child for child in children)
            else node
        )
        if isinstance(rewritten, LoopStateSeedExpr):
            fields = []
            changed = False
            for field in rewritten.fields:
                if field.resolved_type_ref is None:
                    fields.append(field)
                    continue
                resolved_type = substitute_type_params(
                    field.resolved_type_ref,
                    dict(type_bindings),
                )
                if resolved_type is field.resolved_type_ref:
                    fields.append(field)
                    continue
                fields.append(replace(field, resolved_type_ref=resolved_type))
                changed = True
            if changed:
                rewritten = replace(rewritten, fields=tuple(fields))
        rewritten_by_id[id(node)] = rewritten
        return rewritten

    return rewrite(expr)


def _function_dependencies(expr: ExprNode) -> set[str]:
    return {
        node.callee_name
        for node in walk_expr(expr)
        if isinstance(node, FunctionCallExpr)
    }


def _validate_pure_function_expr(
    expr: ExprNode,
    *,
    function_def: FunctionDef,
    procedure_catalog: "ProcedureCatalog | None" = None,
    target_dsl_version: str | None = None,
) -> None:
    from .effects import RunsRefEffect, RunsTrialEffect, effect_summary
    from .expressions import TrialExpr
    from .typecheck_context import raise_run_ref_placement_invalid

    for candidate in walk_expr(expr):
        if isinstance(candidate, TrialExpr):
            raise_run_ref_placement_invalid(
                candidate,
                reason="is not permitted in a pure function",
            )
        if isinstance(candidate, RunRefExpr):
            raise_run_ref_placement_invalid(
                candidate,
                reason="is not permitted in a pure function",
            )
        if isinstance(candidate, ProcedureCallExpr) and procedure_catalog is not None:
            signature = procedure_catalog.signatures_by_name.get(candidate.callee_name)
            if signature is not None and any(
                isinstance(effect, (RunsRefEffect, RunsTrialEffect))
                for effect in signature.declared_effects
            ):
                raise_run_ref_placement_invalid(
                    candidate,
                    reason="is not permitted in a pure function",
                    effect_summary=effect_summary(
                        direct_effects=signature.declared_effects
                    ),
                )
    violation = _find_purity_violation(
        expr,
        allow_procedure_calls=target_dsl_supports_pure_call_composition(
            target_dsl_version or ""
        ),
    )
    if violation is None:
        return
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="pure_function_has_effect",
                message=(
                    f"function `{function_def.name}` may not use effectful form `{violation}` "
                    "inside a pure helper body"
                ),
                span=function_def.body.span,
                form_path=function_def.body.form_path,
                expansion_stack=function_def.body.expansion_stack,
            ),
        )
    )


def _find_purity_violation(
    expr: ExprNode,
    *,
    allow_procedure_calls: bool = False,
) -> str | None:
    if isinstance(expr, TrialExpr):
        return "trial"
    if isinstance(expr, CallExpr):
        return "call"
    if isinstance(expr, ProcedureCallExpr):
        if not allow_procedure_calls:
            return "defproc"
        for arg in expr.args:
            violation = _find_purity_violation(
                arg,
                allow_procedure_calls=allow_procedure_calls,
            )
            if violation is not None:
                return violation
        return None
    if isinstance(expr, BindProcExpr):
        if not allow_procedure_calls:
            return "bind-proc"
        violation = _find_purity_violation(
            expr.base_expr,
            allow_procedure_calls=allow_procedure_calls,
        )
        if violation is not None:
            return violation
        for binding in expr.bindings:
            violation = _find_purity_violation(
                binding.value_expr,
                allow_procedure_calls=allow_procedure_calls,
            )
            if violation is not None:
                return violation
        return None
    if isinstance(expr, ProviderResultExpr):
        return "provider-result"
    if isinstance(expr, CommandResultExpr):
        return "command-result"
    if isinstance(expr, WithPhaseExpr):
        return "with-phase"
    if isinstance(expr, PhaseTargetExpr):
        return "phase-target"
    if isinstance(expr, RunProviderPhaseExpr):
        return "run-provider-phase"
    if isinstance(expr, ProduceOneOfExpr):
        return "produce-one-of"
    if isinstance(expr, ResumeOrStartExpr):
        return "resume-or-start"
    if isinstance(expr, ResourceTransitionExpr):
        return "resource-transition"
    if isinstance(expr, MaterializeViewExpr):
        return "materialize-view"
    if isinstance(expr, WithLiveProvidersExpr):
        return "with-live-providers"
    if isinstance(expr, WithLiveProviderPeersExpr):
        return "with-live-provider-peers"
    if isinstance(expr, FinalizeSelectedItemExpr):
        return "finalize-selected-item"
    if isinstance(expr, LoopRecurExpr):
        return "loop/recur"
    if isinstance(expr, ListMapEffectExpr):
        return "list/map-effect"
    if isinstance(
        expr,
        FieldAccessExpr | NameExpr | LiteralExpr | EnumMemberExpr | ProcRefLiteralExpr,
    ):
        return None
    if isinstance(expr, RecordExpr):
        for _, field_expr in expr.fields:
            violation = _find_purity_violation(field_expr, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, PureOpExpr):
        for arg in expr.args:
            violation = _find_purity_violation(arg, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, ListExpr):
        for item in expr.items:
            violation = _find_purity_violation(item, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, ListMapExpr):
        violation = _find_purity_violation(expr.source_expr, allow_procedure_calls=allow_procedure_calls)
        if violation is not None:
            return violation
        return _find_purity_violation(expr.body_expr, allow_procedure_calls=allow_procedure_calls)
    if isinstance(expr, CompilerListNonemptyHeadExpr):
        return _find_purity_violation(expr.source_expr, allow_procedure_calls=allow_procedure_calls)
    if isinstance(expr, PathJoinUnderExpr):
        return _find_purity_violation(expr.child_expr, allow_procedure_calls=allow_procedure_calls)
    if isinstance(expr, RecordUpdateExpr):
        violation = _find_purity_violation(expr.base_expr, allow_procedure_calls=allow_procedure_calls)
        if violation is not None:
            return violation
        for _, field_expr in expr.overrides:
            violation = _find_purity_violation(field_expr, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, LoopStateSeedExpr):
        for field in expr.fields:
            violation = _find_purity_violation(field.value_expr, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, LoopStateUpdateExpr):
        violation = _find_purity_violation(expr.base_expr, allow_procedure_calls=allow_procedure_calls)
        if violation is not None:
            return violation
        for _, field_expr in expr.overrides:
            violation = _find_purity_violation(field_expr, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, UnionVariantExpr):
        for _, field_expr in expr.fields:
            violation = _find_purity_violation(field_expr, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, LetStarExpr):
        for _, binding_expr in expr.bindings:
            violation = _find_purity_violation(binding_expr, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return _find_purity_violation(expr.body, allow_procedure_calls=allow_procedure_calls)
    if isinstance(expr, IfExpr):
        for nested in (expr.condition_expr, expr.then_expr, expr.else_expr):
            violation = _find_purity_violation(nested, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, CondExpr):
        for clause in expr.clauses:
            if clause.condition_expr is not None:
                violation = _find_purity_violation(clause.condition_expr, allow_procedure_calls=allow_procedure_calls)
                if violation is not None:
                    return violation
            violation = _find_purity_violation(clause.result_expr, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, MatchExpr):
        violation = _find_purity_violation(expr.subject, allow_procedure_calls=allow_procedure_calls)
        if violation is not None:
            return violation
        for arm in expr.arms:
            violation = _find_purity_violation(arm.body, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, FunctionCallExpr):
        for arg in expr.args:
            violation = _find_purity_violation(arg, allow_procedure_calls=allow_procedure_calls)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, ContinueExpr):
        return _find_purity_violation(expr.state_expr, allow_procedure_calls=allow_procedure_calls)
    if isinstance(expr, DoneExpr):
        violation = _find_purity_violation(expr.result_expr, allow_procedure_calls=allow_procedure_calls)
        if violation is not None or expr.terminal_state_expr is None:
            return violation
        return _find_purity_violation(expr.terminal_state_expr, allow_procedure_calls=allow_procedure_calls)
    return f"unsupported expression container {type(expr).__name__}"


def _elaborate_function_definition(form: SyntaxNode) -> FunctionDef:
    datum = syntax_node_datum(form)
    if not isinstance(datum, SyntaxList) or len(datum.items) != 6:
        _raise_parse_error(
            "`defun` requires a name, params, return arrow, return type, and one body",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    name_node = syntax_identifier(datum.items[1])
    if name_node is None:
        _raise_parse_error(
            "function name must be a symbol",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    params_node = datum.items[2]
    if not isinstance(params_node, SyntaxList):
        _raise_parse_error(
            "function params must be a list",
            span=params_node.span,
            form_path=form.form_path,
            expansion_stack=params_node.expansion_stack,
        )
    arrow_node = syntax_identifier(datum.items[3])
    if arrow_node is None or arrow_node.resolved_name != "->":
        _raise_parse_error(
            "function return separator must be `->`",
            span=datum.items[3].span,
            form_path=form.form_path,
            expansion_stack=datum.items[3].expansion_stack,
        )
    return_type_node = datum.items[4]
    return_spec = parse_return_spec(
        return_type_node,
        form_path=form.form_path,
        label="function return type",
    )
    return FunctionDef(
        name=name_node.resolved_name,
        params=_elaborate_params(params_node, form_path=form.form_path),
        return_type_name=return_spec.type_name,
        body=SyntaxNode(
            datum=datum.items[5],
            span=datum.items[5].span,
            module_path=form.module_path,
            form_path=form.form_path,
        ),
        span=datum.span,
        form_path=form.form_path,
        expansion_stack=form.expansion_stack,
        return_spec=return_spec,
    )


def _elaborate_params(
    params_node: SyntaxList,
    *,
    form_path: tuple[str, ...],
) -> tuple[FunctionParam, ...]:
    params: list[FunctionParam] = []
    for raw_param in params_node.items:
        if not isinstance(raw_param, SyntaxList) or len(raw_param.items) != 2:
            _raise_parse_error(
                "function params must be pairs of `(name Type)`",
                span=raw_param.span,
                form_path=form_path,
                expansion_stack=raw_param.expansion_stack,
            )
        name_node = syntax_identifier(raw_param.items[0])
        type_node = syntax_identifier(raw_param.items[1])
        if name_node is None or type_node is None:
            _raise_parse_error(
                "function params must use symbol names and symbol types",
                span=raw_param.span,
                form_path=form_path,
                expansion_stack=raw_param.expansion_stack,
            )
        params.append(
            FunctionParam(
                name=name_node.resolved_name,
                type_name=type_node.resolved_name,
                span=raw_param.span,
                form_path=form_path,
                expansion_stack=raw_param.expansion_stack,
            )
        )
    return tuple(params)


def _raise_parse_error(
    message: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack = (),
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="definition_form_unknown",
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
