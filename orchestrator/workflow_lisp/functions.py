"""Pure helper definitions, catalogs, validation, and normalization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field, replace
from typing import TYPE_CHECKING

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expression_traversal import walk_expr
from .expressions import (
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    ExprNode,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    FunctionCallExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    MaterializeViewExpr,
    LoopStateField,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MatchArm,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    PureOpExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    RecordUpdateExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithPhaseExpr,
    elaborate_expression,
)
from .result_guidance import ReturnSpec, parse_return_spec
from .spans import SourceSpan
from .syntax import (
    ExpansionStack,
    HelperExpansionFrame,
    SyntaxList,
    SyntaxNode,
    WorkflowLispSyntaxModule,
    syntax_head,
    syntax_identifier,
    syntax_node_datum,
    syntax_resolved_name,
)
from .type_env import FrontendTypeEnvironment, TypeRef, type_refs_compatible
from .typecheck import TypedExpr, typecheck_expression

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
) -> tuple[TypedFunctionDef, ...]:
    """Typecheck helper bodies against the pure expression subset."""

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
        )
        _validate_pure_function_expr(body_expr, function_def=function_def)
        typed_body = typecheck_expression(
            body_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            function_catalog=function_catalog,
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
) -> TypedExpr | ExprNode:
    """Rewrite helper calls into `let*` plus existing pure expression nodes."""

    if isinstance(node, TypedExpr):
        return replace(
            node,
            expr=_normalize_expr(node.expr, typed_functions_by_name=typed_functions_by_name),
        )
    return _normalize_expr(node, typed_functions_by_name=typed_functions_by_name)


def _normalize_expr(
    expr: ExprNode,
    *,
    typed_functions_by_name: Mapping[str, TypedFunctionDef],
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
            _normalize_expr(arg, typed_functions_by_name=typed_functions_by_name)
            for arg in expr.args
        )
        return LetStarExpr(
            bindings=tuple(
                (param_name, arg_expr)
                for (param_name, _), arg_expr in zip(
                    function_def.signature.params,
                    normalized_args,
                    strict=True,
                )
            ),
            body=_normalize_expr(
                cloned_body,
                typed_functions_by_name=typed_functions_by_name,
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
                    _normalize_expr(field_expr, typed_functions_by_name=typed_functions_by_name),
                )
                for field_name, field_expr in expr.fields
            ),
        )
    if isinstance(expr, PureOpExpr):
        return replace(
            expr,
            args=tuple(
                _normalize_expr(arg, typed_functions_by_name=typed_functions_by_name)
                for arg in expr.args
            ),
        )
    if isinstance(expr, RecordUpdateExpr):
        return replace(
            expr,
            base_expr=_normalize_expr(
                expr.base_expr,
                typed_functions_by_name=typed_functions_by_name,
            ),
            overrides=tuple(
                (
                    field_name,
                    _normalize_expr(field_expr, typed_functions_by_name=typed_functions_by_name),
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
                        typed_functions_by_name=typed_functions_by_name,
                    ),
                    span=field.span,
                    form_path=field.form_path,
                    expansion_stack=field.expansion_stack,
                )
                for field in expr.fields
            ),
        )
    if isinstance(expr, LoopStateUpdateExpr):
        return replace(
            expr,
            base_expr=_normalize_expr(
                expr.base_expr,
                typed_functions_by_name=typed_functions_by_name,
            ),
            overrides=tuple(
                (
                    field_name,
                    _normalize_expr(field_expr, typed_functions_by_name=typed_functions_by_name),
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
                    _normalize_expr(field_expr, typed_functions_by_name=typed_functions_by_name),
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
                    _normalize_expr(binding_expr, typed_functions_by_name=typed_functions_by_name),
                )
                for name, binding_expr in expr.bindings
            ),
            body=_normalize_expr(expr.body, typed_functions_by_name=typed_functions_by_name),
        )
    if isinstance(expr, IfExpr):
        return replace(
            expr,
            condition_expr=_normalize_expr(
                expr.condition_expr,
                typed_functions_by_name=typed_functions_by_name,
            ),
            then_expr=_normalize_expr(
                expr.then_expr,
                typed_functions_by_name=typed_functions_by_name,
            ),
            else_expr=_normalize_expr(
                expr.else_expr,
                typed_functions_by_name=typed_functions_by_name,
            ),
        )
    if isinstance(expr, MatchExpr):
        return replace(
            expr,
            subject=_normalize_expr(expr.subject, typed_functions_by_name=typed_functions_by_name),
            arms=tuple(
                replace(
                    arm,
                    body=_normalize_expr(arm.body, typed_functions_by_name=typed_functions_by_name),
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
                    _normalize_expr(binding_expr, typed_functions_by_name=typed_functions_by_name),
                )
                for binding_name, binding_expr in expr.bindings
            ),
        )
    if isinstance(expr, CommandResultExpr):
        return replace(
            expr,
            argv=tuple(
                _normalize_expr(arg, typed_functions_by_name=typed_functions_by_name)
                for arg in expr.argv
            ),
        )
    if isinstance(expr, ProviderResultExpr):
        return replace(
            expr,
            provider=_normalize_expr(expr.provider, typed_functions_by_name=typed_functions_by_name),
            prompt=_normalize_expr(expr.prompt, typed_functions_by_name=typed_functions_by_name),
            inputs=tuple(
                _normalize_expr(arg, typed_functions_by_name=typed_functions_by_name)
                for arg in expr.inputs
            ),
            model=(
                _normalize_expr(expr.model, typed_functions_by_name=typed_functions_by_name)
                if expr.model is not None
                else None
            ),
            effort=(
                _normalize_expr(expr.effort, typed_functions_by_name=typed_functions_by_name)
                if expr.effort is not None
                else None
            ),
            prompt_dependencies=(
                replace(
                    expr.prompt_dependencies,
                    required=tuple(
                        _normalize_expr(item, typed_functions_by_name=typed_functions_by_name)
                        for item in expr.prompt_dependencies.required
                    ),
                    optional=tuple(
                        _normalize_expr(item, typed_functions_by_name=typed_functions_by_name)
                        for item in expr.prompt_dependencies.optional
                    ),
                )
                if expr.prompt_dependencies is not None
                else None
            ),
        )
    if isinstance(expr, WithPhaseExpr):
        return replace(
            expr,
            ctx_expr=_normalize_expr(expr.ctx_expr, typed_functions_by_name=typed_functions_by_name),
            body=_normalize_expr(expr.body, typed_functions_by_name=typed_functions_by_name),
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
    return expr


def _clone_function_expr(
    expr: ExprNode,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: ExpansionStack,
) -> ExprNode:
    if isinstance(expr, NameExpr | LiteralExpr | EnumMemberExpr):
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
    raise TypeError(f"unsupported pure helper expression clone: {type(expr)!r}")


def _function_dependencies(expr: ExprNode) -> set[str]:
    return {
        node.callee_name
        for node in walk_expr(expr)
        if isinstance(node, FunctionCallExpr)
    }


def _validate_pure_function_expr(expr: ExprNode, *, function_def: FunctionDef) -> None:
    violation = _find_purity_violation(expr)
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


def _find_purity_violation(expr: ExprNode) -> str | None:
    if isinstance(expr, CallExpr):
        return "call"
    if isinstance(expr, ProcedureCallExpr):
        return "defproc"
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
    if isinstance(expr, FinalizeSelectedItemExpr):
        return "finalize-selected-item"
    if isinstance(expr, LoopRecurExpr):
        return "loop/recur"
    if isinstance(expr, FieldAccessExpr | NameExpr | LiteralExpr | EnumMemberExpr):
        return None
    if isinstance(expr, RecordExpr):
        for _, field_expr in expr.fields:
            violation = _find_purity_violation(field_expr)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, PureOpExpr):
        for arg in expr.args:
            violation = _find_purity_violation(arg)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, RecordUpdateExpr):
        violation = _find_purity_violation(expr.base_expr)
        if violation is not None:
            return violation
        for _, field_expr in expr.overrides:
            violation = _find_purity_violation(field_expr)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, LoopStateSeedExpr):
        for field in expr.fields:
            violation = _find_purity_violation(field.value_expr)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, LoopStateUpdateExpr):
        violation = _find_purity_violation(expr.base_expr)
        if violation is not None:
            return violation
        for _, field_expr in expr.overrides:
            violation = _find_purity_violation(field_expr)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, UnionVariantExpr):
        for _, field_expr in expr.fields:
            violation = _find_purity_violation(field_expr)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, LetStarExpr):
        for _, binding_expr in expr.bindings:
            violation = _find_purity_violation(binding_expr)
            if violation is not None:
                return violation
        return _find_purity_violation(expr.body)
    if isinstance(expr, IfExpr):
        for nested in (expr.condition_expr, expr.then_expr, expr.else_expr):
            violation = _find_purity_violation(nested)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, MatchExpr):
        violation = _find_purity_violation(expr.subject)
        if violation is not None:
            return violation
        for arm in expr.arms:
            violation = _find_purity_violation(arm.body)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, FunctionCallExpr):
        for arg in expr.args:
            violation = _find_purity_violation(arg)
            if violation is not None:
                return violation
        return None
    if isinstance(expr, ContinueExpr):
        return _find_purity_violation(expr.state_expr)
    if isinstance(expr, DoneExpr):
        return _find_purity_violation(expr.result_expr)
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
