"""Elaborate supported Workflow Lisp expression forms into typed AST nodes.

See `../../docs/design/workflow_lisp_frontend_mvp_specification.md` for the current
expression scope and `../../docs/design/workflow_lisp_frontend_specification.md` for
the full intended language surface.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from orchestrator.workflow.pure_expr import PURE_EXPR_OPERATOR_CATALOG

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .form_registry import FormKind, get_form_spec
from .phase_stdlib import (
    ProduceOneOfCandidateFieldSpec,
    ProduceOneOfCandidateSpec,
    ProduceOneOfProducerSpec,
)
from .procedures import ProcedureParam
from .resource_stdlib import FinalizeSelectedItemSpec, ResourceTransitionSpec
from .result_guidance import ReturnSpec, parse_return_spec
from .spans import SourceSpan
from .syntax import (
    ExpansionStack,
    SyntaxBool,
    SyntaxFloat,
    SyntaxIdentifier,
    SyntaxInt,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    syntax_head,
    syntax_identifier,
    syntax_node_datum,
)

if TYPE_CHECKING:
    from .type_env import TypeRef


@dataclass(frozen=True)
class NameExpr:
    """One lexical name reference."""

    name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LiteralExpr:
    """One primitive literal."""

    value: str | int | float | bool
    literal_kind: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class EnumMemberExpr:
    """One qualified enum-member literal reference."""

    enum_name: str
    member_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()

    @property
    def name(self) -> str:
        return f"{self.enum_name}.{self.member_name}"


@dataclass(frozen=True)
class FieldAccessExpr:
    """One dotted field-access chain rooted at a lexical name."""

    base: NameExpr
    fields: tuple[str, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class RecordExpr:
    """One record-construction form."""

    type_name: str
    fields: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PureOpExpr:
    """One closed pure operator application."""

    operator: str
    args: tuple["ExprNode", ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class RecordUpdateExpr:
    """One record-update expression over an existing record value."""

    base_expr: "ExprNode"
    overrides: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LoopStateField:
    """One authored loop-state seed field."""

    name: str
    type_name: str
    value_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LoopStateSeedExpr:
    """One loop-state seed form with explicit typed fields."""

    fields: tuple[LoopStateField, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LoopStateUpdateExpr:
    """One loop-state update form based on an existing carrier."""

    base_expr: "ExprNode"
    overrides: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class UnionVariantExpr:
    """One union-variant constructor."""

    type_name: str
    variant_name: str
    fields: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LetStarExpr:
    """One sequential lexical binding form."""

    bindings: tuple[tuple[str, "ExprNode"], ...]
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class IfExpr:
    """One ternary conditional expression."""

    condition_expr: "ExprNode"
    then_expr: "ExprNode"
    else_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class MatchArm:
    """One `match` variant arm."""

    variant_name: str
    binding_name: str
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class MatchExpr:
    """One exhaustive variant match form."""

    subject: "ExprNode"
    arms: tuple[MatchArm, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class CallExpr:
    """One same-file workflow call."""

    callee_name: str
    bindings: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProcedureCallExpr:
    """One same-file procedure call."""

    callee_name: str
    args: tuple["ExprNode", ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class FunctionCallExpr:
    """One frontend-local pure helper call."""

    callee_name: str
    args: tuple["ExprNode", ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class WithPhaseExpr:
    """One compile-time phase-scope wrapper."""

    ctx_expr: "ExprNode"
    phase_name: str
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PhaseTargetExpr:
    """One named phase-target reference."""

    target_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class GeneratedRelpathSeedExpr:
    """One compiler-private relpath seed placeholder."""

    target_type_ref: "TypeRef | Any"
    literal_path: str
    seed_role: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class WorkflowRefLiteralExpr:
    """One compile-time workflow reference literal."""

    target_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProcRefLiteralExpr:
    """One compile-time procedure reference literal."""

    target_name: str
    authored_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class BindProcBinding:
    """One authored `bind-proc` keyword/value pair."""

    name: str
    value_expr: "ExprNode"
    keyword_span: SourceSpan
    keyword_form_path: tuple[str, ...]
    keyword_expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class BindProcExpr:
    """One compile-time proc-ref partial application."""

    base_expr: "ExprNode"
    bindings: tuple[BindProcBinding, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LetProcBinding:
    """One authored V1 `let-proc` local procedure binding."""

    local_name: str
    params: tuple[ProcedureParam, ...]
    return_type_name: str
    capture_names: tuple[str, ...]
    local_body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LetProcExpr:
    """One lexical local procedure plus the body that can reference it."""

    binding: LetProcBinding
    body: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PromptDependencySpec:
    """Typed authored exact-path inputs for one provider prompt."""

    required: tuple["ExprNode", ...]
    optional: tuple["ExprNode", ...]
    position: str
    instruction: str | None
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProviderResultExpr:
    """One provider result with a typed structured return contract."""

    provider: "ExprNode"
    prompt: "ExprNode"
    inputs: tuple["ExprNode", ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    model: "ExprNode | None" = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    effort: "ExprNode | None" = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    timeout_sec: "ExprNode | None" = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    prompt_dependencies: PromptDependencySpec | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    return_spec: ReturnSpec | None = field(
        default=None,
        repr=False,
        metadata={"json_name": "returns_type_name", "json_value_attr": "type_name"},
    )
    returns_type_name: InitVar[str | None] = None

    def __post_init__(self, returns_type_name: str | None) -> None:
        if self.return_spec is None:
            if returns_type_name is None:
                raise TypeError("provider results require a return spec")
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=returns_type_name, guidance=None, span=self.span),
            )
        elif returns_type_name is not None and self.return_spec.type_name != returns_type_name:
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=returns_type_name, guidance=None, span=self.return_spec.span),
            )


ProviderResultExpr.returns_type_name = property(lambda self: self.return_spec.type_name)


@dataclass(frozen=True)
class ProviderBundlePathExpr:
    """One typed projection of canonical provider bundle identity to a relpath."""

    source_expr: "ExprNode"
    target_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class CommandResultExpr:
    """One command result with a typed structured return contract."""

    step_name: str
    argv: tuple["ExprNode", ...]
    adapter_name: str | None
    adapter_inputs: tuple[tuple[str, "ExprNode"], ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    return_spec: ReturnSpec | None = field(
        default=None,
        repr=False,
        metadata={"json_name": "returns_type_name", "json_value_attr": "type_name"},
    )
    returns_type_name: InitVar[str | None] = None

    def __post_init__(self, returns_type_name: str | None) -> None:
        if self.return_spec is None:
            if returns_type_name is None:
                raise TypeError("command results require a return spec")
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=returns_type_name, guidance=None, span=self.span),
            )
        elif returns_type_name is not None and self.return_spec.type_name != returns_type_name:
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=returns_type_name, guidance=None, span=self.return_spec.span),
            )


CommandResultExpr.returns_type_name = property(lambda self: self.return_spec.type_name)


@dataclass(frozen=True)
class LoopBodyFnExpr:
    """One compiler-owned `loop/recur` body binder."""

    binding_name: str
    body_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ContinueExpr:
    """One loop-local `continue` control transfer."""

    state_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class DoneExpr:
    """One loop-local `done` control transfer."""

    result_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class LoopRecurExpr:
    """One public bounded `loop/recur` form."""

    max_iterations_expr: "ExprNode"
    initial_state_expr: "ExprNode"
    binding_name: str
    body_expr: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    on_exhausted_result_expr: "ExprNode | None" = None


@dataclass(frozen=True)
class RunProviderPhaseExpr:
    """One high-level typed phase provider execution form."""

    phase_name: str
    ctx_expr: "ExprNode"
    inputs_expr: "ExprNode"
    provider: "ExprNode"
    prompt: "ExprNode"
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProduceOneOfExpr:
    """One high-level produced-outcome selection form."""

    returns_type_name: str
    ctx_expr: "ExprNode"
    producer: ProduceOneOfProducerSpec
    candidates: tuple[ProduceOneOfCandidateSpec, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ResumeOrStartExpr:
    """One typed reusable-state gate around resume or fresh start."""

    resume_name: str
    ctx_expr: "ExprNode"
    resume_from_expr: "ExprNode"
    valid_when: tuple[str, ...]
    start_expr: "ExprNode"
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    validation_spec: object | None = None


@dataclass(frozen=True)
class ResourceTransitionExpr:
    """One supported resource movement form."""

    spec: ResourceTransitionSpec
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class MaterializeViewExpr:
    """One generated value-view materialization form."""

    view_name: str
    value_expr: "ExprNode"
    renderer_id: str
    renderer_version: int
    target_expr: "ExprNode" | None
    returns_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class FinalizeSelectedItemExpr:
    """One selected-item final result routing form."""

    spec: FinalizeSelectedItemSpec
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


ExprNode = (
    NameExpr
    | LiteralExpr
    | EnumMemberExpr
    | FieldAccessExpr
    | RecordExpr
    | PureOpExpr
    | RecordUpdateExpr
    | LoopStateSeedExpr
    | LoopStateUpdateExpr
    | UnionVariantExpr
    | LetStarExpr
    | IfExpr
    | MatchExpr
    | CallExpr
    | FunctionCallExpr
    | ProcedureCallExpr
    | WithPhaseExpr
    | PhaseTargetExpr
    | GeneratedRelpathSeedExpr
    | WorkflowRefLiteralExpr
    | ProcRefLiteralExpr
    | BindProcExpr
    | LetProcExpr
    | ProviderResultExpr
    | ProviderBundlePathExpr
    | CommandResultExpr
    | ContinueExpr
    | DoneExpr
    | LoopRecurExpr
    | RunProviderPhaseExpr
    | ProduceOneOfExpr
    | ResumeOrStartExpr
    | ResourceTransitionExpr
    | MaterializeViewExpr
    | FinalizeSelectedItemExpr
)


_ACTIVE_PROCEDURE_NAME_RESOLVER = None
_ACTIVE_FUNCTION_NAME_RESOLVER = None
_ACTIVE_WORKFLOW_NAME_RESOLVER = None
_ACTIVE_FUNCTION_NAMES = frozenset()
_ACTIVE_LOCAL_PROC_NAMES = frozenset()
_ACTIVE_LOOP_BODY_DEPTH = 0
_ACTIVE_LET_PROC_DEPTH = 0
_ACTIVE_GUIDANCE_EXAMPLE = False

_ElaborationRouteHandler = Callable[
    [SyntaxList, tuple[str, ...], frozenset[str], frozenset[str]],
    "ExprNode",
]


def elaborate_expression(
    node: SyntaxNode,
    *,
    bound_names: frozenset[str],
    procedure_names: frozenset[str] = frozenset(),
    function_names: frozenset[str] = frozenset(),
    function_name_resolver=None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
    guidance_example: bool = False,
) -> ExprNode:
    """Elaborate one syntax node into a supported Workflow Lisp expression."""

    global _ACTIVE_FUNCTION_NAME_RESOLVER, _ACTIVE_FUNCTION_NAMES, _ACTIVE_PROCEDURE_NAME_RESOLVER, _ACTIVE_WORKFLOW_NAME_RESOLVER
    global _ACTIVE_LOCAL_PROC_NAMES, _ACTIVE_LET_PROC_DEPTH, _ACTIVE_GUIDANCE_EXAMPLE

    previous_function_resolver = _ACTIVE_FUNCTION_NAME_RESOLVER
    previous_function_names = _ACTIVE_FUNCTION_NAMES
    previous_procedure_resolver = _ACTIVE_PROCEDURE_NAME_RESOLVER
    previous_workflow_resolver = _ACTIVE_WORKFLOW_NAME_RESOLVER
    previous_local_proc_names = _ACTIVE_LOCAL_PROC_NAMES
    previous_let_proc_depth = _ACTIVE_LET_PROC_DEPTH
    previous_guidance_example = _ACTIVE_GUIDANCE_EXAMPLE
    _ACTIVE_FUNCTION_NAME_RESOLVER = function_name_resolver
    _ACTIVE_FUNCTION_NAMES = function_names
    _ACTIVE_PROCEDURE_NAME_RESOLVER = procedure_name_resolver
    _ACTIVE_WORKFLOW_NAME_RESOLVER = workflow_name_resolver
    _ACTIVE_LOCAL_PROC_NAMES = frozenset()
    _ACTIVE_LET_PROC_DEPTH = 0
    _ACTIVE_GUIDANCE_EXAMPLE = guidance_example
    try:
        return _elaborate(
            syntax_node_datum(node),
            form_path=node.form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    finally:
        _ACTIVE_FUNCTION_NAME_RESOLVER = previous_function_resolver
        _ACTIVE_FUNCTION_NAMES = previous_function_names
        _ACTIVE_PROCEDURE_NAME_RESOLVER = previous_procedure_resolver
        _ACTIVE_WORKFLOW_NAME_RESOLVER = previous_workflow_resolver
        _ACTIVE_LOCAL_PROC_NAMES = previous_local_proc_names
        _ACTIVE_LET_PROC_DEPTH = previous_let_proc_depth
        _ACTIVE_GUIDANCE_EXAMPLE = previous_guidance_example


def _elaborate(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    if isinstance(datum, SyntaxString):
        return LiteralExpr(
            value=datum.value,
            literal_kind="string",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxInt):
        return LiteralExpr(
            value=datum.value,
            literal_kind="int",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxBool):
        return LiteralExpr(
            value=datum.value,
            literal_kind="bool",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxFloat):
        if _ACTIVE_GUIDANCE_EXAMPLE:
            return LiteralExpr(
                value=datum.value,
                literal_kind="float",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        _raise_error(
            "float literals are only supported in `defworkflow` parameter defaults",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if isinstance(datum, SyntaxIdentifier):
        return _elaborate_symbol(datum, form_path=form_path, bound_names=bound_names)
    if isinstance(datum, SyntaxList):
        return _elaborate_list(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    raise TypeError(f"unsupported expression datum: {type(datum)!r}")


def _elaborate_symbol(
    datum: SyntaxIdentifier,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
) -> ExprNode:
    if datum.resolved_name in bound_names:
        return NameExpr(
            name=datum.resolved_name,
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    segments = datum.resolved_name.split(".")
    if len(segments) > 1 and segments[0] in bound_names:
        return FieldAccessExpr(
            base=NameExpr(
                name=segments[0],
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            ),
            fields=tuple(segments[1:]),
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if len(segments) == 2:
        return EnumMemberExpr(
            enum_name=segments[0],
            member_name=segments[1],
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return NameExpr(
        name=datum.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_list(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    if not datum.items:
        _raise_error(
            "expression forms must be non-empty lists",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    head = syntax_head(datum)
    if head is None:
        _raise_error(
            "expression forms must start with a symbol",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    form_spec = get_form_spec(head.resolved_name)
    if form_spec is not None:
        if form_spec.kind is FormKind.TOP_LEVEL_DEFINITION:
            _raise_error(
                f"`{head.display_name}` is a top-level definition form and cannot appear in expression position",
                code="top_level_definition_in_expression_position",
                span=head.span,
                form_path=form_path,
                expansion_stack=head.expansion_stack,
            )
        if form_spec.kind is FormKind.STDLIB_EXTENSION:
            _raise_error(
                f"`{head.display_name}` requires imported stdlib expansion before expression elaboration",
                code="stdlib_extension_missing_import_route",
                span=head.span,
                form_path=form_path,
                expansion_stack=head.expansion_stack,
            )
        if form_spec.elaboration_route is not None:
            return _dispatch_elaboration_route(
                form_spec.elaboration_route,
                datum,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
    if head.resolved_name in _ACTIVE_FUNCTION_NAMES:
        return _elaborate_function_call(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name in procedure_names:
        return _elaborate_procedure_call(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if head.resolved_name in _ACTIVE_LOCAL_PROC_NAMES:
        _raise_error(
            f"`{head.display_name}` is a local `let-proc` binding and must be referenced with `proc-ref`",
            code="let_proc_bare_name_invalid",
            span=head.span,
            form_path=form_path,
            expansion_stack=head.expansion_stack,
        )
    if head.resolved_name in bound_names:
        return _elaborate_procedure_call(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    if _looks_like_pure_operator_head(head.resolved_name):
        _raise_error(
            f"unsupported pure operator `{head.display_name}`",
            code="pure_expr_operator_unsupported",
            span=head.span,
            form_path=form_path,
            expansion_stack=head.expansion_stack,
        )
    _raise_error(
        f"unknown same-file procedure callee `{head.display_name}`",
        code="procedure_call_unknown",
        span=head.span,
        form_path=form_path,
        expansion_stack=head.expansion_stack,
    )


def _dispatch_elaboration_route(
    route_key: str,
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    handler = _elaboration_route_handlers().get(route_key)
    if handler is None:
        raise AssertionError(f"unknown Workflow Lisp elaboration route `{route_key}`")
    return handler(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )


def _guard_loop_fn_route(
    datum: SyntaxList,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    _raise_error(
        "`fn` is valid only as the body form of `loop/recur`",
        code="loop_recur_fn_outside_loop",
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _guard_continue_route(
    datum: SyntaxList,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    if _ACTIVE_LOOP_BODY_DEPTH <= 0:
        _raise_error(
            "`continue` is valid only inside `loop/recur`",
            code="loop_recur_continue_outside_loop",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return _elaborate_continue(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )


def _guard_done_route(
    datum: SyntaxList,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    if _ACTIVE_LOOP_BODY_DEPTH <= 0:
        _raise_error(
            "`done` is valid only inside `loop/recur`",
            code="loop_recur_done_outside_loop",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return _elaborate_done(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )


def _guard_let_proc_route(
    datum: SyntaxList,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    if _ACTIVE_LET_PROC_DEPTH > 0:
        _raise_error(
            "`let-proc` cannot be nested in V1",
            code="let_proc_nested_unsupported",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return _elaborate_let_proc(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )


def _route_phase_target(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    del bound_names, procedure_names
    return _elaborate_phase_target(datum, form_path=form_path)


def _route_generated_relpath_seed(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    del bound_names, procedure_names
    return _elaborate_generated_relpath_seed(datum, form_path=form_path)


def _route_workflow_ref(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    del bound_names, procedure_names
    return _elaborate_workflow_ref_literal(datum, form_path=form_path)


def _route_proc_ref(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ExprNode:
    del bound_names, procedure_names
    return _elaborate_proc_ref_literal(datum, form_path=form_path)


def _elaboration_route_handlers() -> dict[str, _ElaborationRouteHandler]:
    return {
        "record": _elaborate_record,
        "pure_op": _elaborate_pure_op,
        "record_update": _elaborate_record_update,
        "loop_state": _elaborate_loop_state,
        "variant": _elaborate_variant,
        "let_star": _elaborate_letstar,
        "if": _elaborate_if,
        "match": _elaborate_match,
        "loop_recur": _elaborate_loop_recur,
        "loop_fn_guard": _guard_loop_fn_route,
        "continue_guard": _guard_continue_route,
        "done_guard": _guard_done_route,
        "call": _elaborate_call,
        "with_phase": _elaborate_with_phase,
        "phase_target": _route_phase_target,
        "generated_relpath_seed": _route_generated_relpath_seed,
        "workflow_ref": _route_workflow_ref,
        "proc_ref": _route_proc_ref,
        "bind_proc": _elaborate_bind_proc,
        "let_proc_guard": _guard_let_proc_route,
        "provider_result": _elaborate_provider_result,
        "provider_bundle_path": _elaborate_provider_bundle_path,
        "command_result": _elaborate_command_result,
        "run_provider_phase": _elaborate_run_provider_phase,
        "produce_one_of": _elaborate_produce_one_of,
        "resume_or_start": _elaborate_resume_or_start,
        "resource_transition": _elaborate_resource_transition,
        "materialize_view": _elaborate_materialize_view,
        "finalize_selected_item": _elaborate_finalize_selected_item,
    }


def _looks_like_pure_operator_head(name: str) -> bool:
    if name in PURE_EXPR_OPERATOR_CATALOG:
        return True
    if "/" in name:
        return True
    return name in {"and", "or", "not", "min", "max", "some?", "or-else", "record-update"}


def _elaborate_record(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> RecordExpr:
    if len(datum.items) < 2:
        _raise_error("`record` requires a type name", span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    type_node = datum.items[1]
    type_identifier = syntax_identifier(type_node)
    if type_identifier is None:
        _raise_error(
            "`record` type name must be a symbol",
            span=type_node.span,
            form_path=form_path,
            expansion_stack=type_node.expansion_stack,
        )
    raw_fields = datum.items[2:]
    if len(raw_fields) % 2 != 0:
        _raise_error(
            "`record` requires keyword/value field pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    fields: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_fields), 2):
        keyword_node = raw_fields[index]
        value_node = raw_fields[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`record` fields must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        fields.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
            )
        )
    return RecordExpr(
        type_name=type_identifier.resolved_name,
        fields=tuple(fields),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_pure_op(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> PureOpExpr:
    head = syntax_head(datum)
    assert head is not None
    return PureOpExpr(
        operator=head.resolved_name,
        args=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for item in datum.items[1:]
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_record_update(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> RecordUpdateExpr:
    if len(datum.items) < 4:
        _raise_error(
            "`record-update` requires a base expression and at least one keyword/value override",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_fields = datum.items[2:]
    if len(raw_fields) % 2 != 0:
        _raise_error(
            "`record-update` requires keyword/value override pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    overrides: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_fields), 2):
        keyword_node = raw_fields[index]
        value_node = raw_fields[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`record-update` overrides must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        overrides.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
            )
        )
    return RecordUpdateExpr(
        base_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        overrides=tuple(overrides),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_loop_state(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> LoopStateSeedExpr | LoopStateUpdateExpr:
    if len(datum.items) < 2:
        _raise_error(
            "`loop-state` requires typed field entries or `:like` plus overrides",
            code="loop_state_requires_typed_fields",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    first_item = datum.items[1]
    if isinstance(first_item, SyntaxKeyword):
        return _elaborate_loop_state_update(
            datum,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    return _elaborate_loop_state_seed(
        datum,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )


def _elaborate_loop_state_seed(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> LoopStateSeedExpr:
    fields: list[LoopStateField] = []
    seen_fields: set[str] = set()
    for field_node in datum.items[1:]:
        if not isinstance(field_node, SyntaxList) or len(field_node.items) != 3:
            _raise_error(
                "`loop-state` seed fields must use `(field Type value)` entries",
                code="loop_state_requires_typed_fields",
                span=field_node.span,
                form_path=form_path,
                expansion_stack=field_node.expansion_stack,
            )
        name_node = syntax_identifier(field_node.items[0])
        type_node = syntax_identifier(field_node.items[1])
        value_node = field_node.items[2]
        if name_node is None or type_node is None:
            _raise_error(
                "`loop-state` seed fields must use `(field Type value)` entries",
                code="loop_state_requires_typed_fields",
                span=field_node.span,
                form_path=form_path,
                expansion_stack=field_node.expansion_stack,
            )
        if name_node.resolved_name in seen_fields:
            _raise_error(
                f"duplicate loop-state field `{name_node.display_name}`",
                code="loop_state_duplicate_field",
                span=name_node.span,
                form_path=form_path,
                expansion_stack=name_node.expansion_stack,
            )
        seen_fields.add(name_node.resolved_name)
        fields.append(
            LoopStateField(
                name=name_node.resolved_name,
                type_name=type_node.resolved_name,
                value_expr=_elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
                span=field_node.span,
                form_path=form_path,
                expansion_stack=field_node.expansion_stack,
            )
        )
    return LoopStateSeedExpr(
        fields=tuple(fields),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_loop_state_update(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> LoopStateUpdateExpr:
    if len(datum.items) < 4 or not isinstance(datum.items[1], SyntaxKeyword) or datum.items[1].value != ":like":
        _raise_error(
            "`loop-state` updates must start with `:like` and a base expression",
            code="loop_state_requires_typed_fields",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    base_node = datum.items[2]
    if isinstance(base_node, SyntaxKeyword):
        _raise_error(
            "`loop-state :like` requires a base expression before overrides",
            code="loop_state_requires_typed_fields",
            span=base_node.span,
            form_path=form_path,
            expansion_stack=base_node.expansion_stack,
        )
    override_nodes = datum.items[3:]
    if len(override_nodes) % 2 != 0:
        _raise_error(
            "`loop-state :like` requires keyword/value override pairs",
            code="loop_state_requires_typed_fields",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    seen_fields: set[str] = set()
    overrides: list[tuple[str, ExprNode]] = []
    for index in range(0, len(override_nodes), 2):
        keyword_node = override_nodes[index]
        value_node = override_nodes[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`loop-state :like` overrides must use keyword/value pairs",
                code="loop_state_requires_typed_fields",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        field_name = keyword_node.value[1:]
        if field_name in seen_fields:
            _raise_error(
                f"duplicate loop-state field `{field_name}`",
                code="loop_state_duplicate_field",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        seen_fields.add(field_name)
        overrides.append(
            (
                field_name,
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
            )
        )
    return LoopStateUpdateExpr(
        base_expr=_elaborate(
            base_node,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        overrides=tuple(overrides),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_variant(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> UnionVariantExpr:
    if len(datum.items) < 3:
        _raise_error(
            "`variant` requires a union type and variant name",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    type_node = datum.items[1]
    type_identifier = syntax_identifier(type_node)
    if type_identifier is None:
        _raise_error(
            "`variant` union type must be a symbol",
            span=type_node.span,
            form_path=form_path,
            expansion_stack=type_node.expansion_stack,
        )
    variant_node = datum.items[2]
    variant_identifier = syntax_identifier(variant_node)
    if variant_identifier is None:
        _raise_error(
            "`variant` name must be a symbol",
            span=variant_node.span,
            form_path=form_path,
            expansion_stack=variant_node.expansion_stack,
        )
    raw_fields = datum.items[3:]
    if len(raw_fields) % 2 != 0:
        _raise_error(
            "`variant` requires keyword/value field pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    fields: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_fields), 2):
        keyword_node = raw_fields[index]
        value_node = raw_fields[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`variant` fields must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        fields.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
            )
        )
    return UnionVariantExpr(
        type_name=type_identifier.resolved_name,
        variant_name=variant_identifier.resolved_name,
        fields=tuple(fields),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_letstar(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> LetStarExpr:
    if len(datum.items) != 3:
        _raise_error(
            "`let*` requires a binding list and one body",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    raw_bindings = datum.items[1]
    if not isinstance(raw_bindings, SyntaxList):
        _raise_error(
            "`let*` bindings must be a list",
            span=raw_bindings.span,
            form_path=form_path,
            expansion_stack=raw_bindings.expansion_stack,
        )
    current_names = set(bound_names)
    bindings: list[tuple[str, ExprNode]] = []
    for raw_binding in raw_bindings.items:
        if not isinstance(raw_binding, SyntaxList) or len(raw_binding.items) != 2:
            _raise_error(
                "`let*` bindings must be two-item lists of `(name expr)`",
                span=raw_binding.span,
                form_path=form_path,
                expansion_stack=raw_binding.expansion_stack,
            )
        name_node = syntax_identifier(raw_binding.items[0])
        if name_node is None:
            _raise_error(
                "`let*` binding names must be symbols",
                span=raw_binding.items[0].span,
                form_path=form_path,
                expansion_stack=raw_binding.items[0].expansion_stack,
            )
        value_expr = _elaborate(
            raw_binding.items[1],
            form_path=form_path,
            bound_names=frozenset(current_names),
            procedure_names=procedure_names,
        )
        bindings.append((name_node.resolved_name, value_expr))
        current_names.add(name_node.resolved_name)
    body = _elaborate(
        datum.items[2],
        form_path=form_path,
        bound_names=frozenset(current_names),
        procedure_names=procedure_names,
    )
    return LetStarExpr(
        bindings=tuple(bindings),
        body=body,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_match(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> MatchExpr:
    if len(datum.items) < 2:
        _raise_error("`match` requires a subject", span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    subject = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )
    arms: list[MatchArm] = []
    for raw_arm in datum.items[2:]:
        if not isinstance(raw_arm, SyntaxList) or len(raw_arm.items) != 2:
            _raise_error(
                "`match` arms must be `((VARIANT binding) body)`",
                span=raw_arm.span,
                form_path=form_path,
                expansion_stack=raw_arm.expansion_stack,
            )
        pattern = raw_arm.items[0]
        if not isinstance(pattern, SyntaxList) or len(pattern.items) != 2:
            _raise_error(
                "`match` arm patterns must be `(VARIANT binding)`",
                span=pattern.span,
                form_path=form_path,
                expansion_stack=pattern.expansion_stack,
            )
        variant_node = syntax_identifier(pattern.items[0])
        binding_node = syntax_identifier(pattern.items[1])
        if variant_node is None:
            _raise_error(
                "`match` variant names must be symbols",
                span=pattern.items[0].span,
                form_path=form_path,
                expansion_stack=pattern.items[0].expansion_stack,
            )
        if binding_node is None:
            _raise_error(
                "`match` binding names must be symbols",
                span=pattern.items[1].span,
                form_path=form_path,
                expansion_stack=pattern.items[1].expansion_stack,
            )
        body = _elaborate(
            raw_arm.items[1],
            form_path=form_path,
            bound_names=frozenset(set(bound_names) | {binding_node.resolved_name}),
            procedure_names=procedure_names,
        )
        arms.append(
            MatchArm(
                variant_name=variant_node.resolved_name,
                binding_name=binding_node.resolved_name,
                body=body,
                span=raw_arm.span,
                form_path=form_path,
                expansion_stack=raw_arm.expansion_stack,
            )
        )
    return MatchExpr(
        subject=subject,
        arms=tuple(arms),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_if(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> IfExpr:
    if len(datum.items) != 4:
        _raise_error(
            "`if` requires exactly a condition, then branch, and else branch",
            code="if_form_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return IfExpr(
        condition_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        then_expr=_elaborate(
            datum.items[2],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        else_expr=_elaborate(
            datum.items[3],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_loop_recur(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> LoopRecurExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`loop/recur` requires :max, :state, and one loop-body `fn`",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    keyword_items = datum.items[1:-1]
    if len(keyword_items) < 4 or len(keyword_items) % 2 != 0:
        _raise_error(
            "`loop/recur` requires :max, :state, and one loop-body `fn`",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    sections: dict[str, object] = {}
    for index in range(0, len(keyword_items), 2):
        keyword_node = keyword_items[index]
        value_node = keyword_items[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`loop/recur` entries before the body must be keyword/value pairs",
                code="loop_recur_contract_invalid",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        if keyword_node.value in sections:
            _raise_error(
                f"`loop/recur` duplicated keyword `{keyword_node.value}`",
                code="loop_recur_contract_invalid",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        sections[keyword_node.value] = value_node
    unexpected_keywords = set(sections) - {":max", ":state", ":on-exhausted"}
    if unexpected_keywords:
        first_unexpected = min(unexpected_keywords)
        keyword_index = next(
            index
            for index in range(0, len(keyword_items), 2)
            if isinstance(keyword_items[index], SyntaxKeyword)
            and keyword_items[index].value == first_unexpected
        )
        keyword_node = keyword_items[keyword_index]
        _raise_error(
            f"`loop/recur` does not support keyword `{first_unexpected}`",
            code="loop_recur_contract_invalid",
            span=keyword_node.span,
            form_path=form_path,
            expansion_stack=keyword_node.expansion_stack,
        )
    max_node = sections.get(":max")
    state_node = sections.get(":state")
    if max_node is None or state_node is None:
        _raise_error(
            "`loop/recur` requires :max and :state",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    body_fn = _elaborate_loop_body_fn(
        datum.items[-1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )
    loop_bound_names = frozenset(set(bound_names) | {body_fn.binding_name})
    on_exhausted_node = sections.get(":on-exhausted")
    return LoopRecurExpr(
        max_iterations_expr=_elaborate(
            max_node,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        initial_state_expr=_elaborate(
            state_node,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        binding_name=body_fn.binding_name,
        body_expr=body_fn.body_expr,
        on_exhausted_result_expr=(
            _elaborate(
                on_exhausted_node,
                form_path=form_path,
                bound_names=loop_bound_names,
                procedure_names=procedure_names,
            )
            if on_exhausted_node is not None
            else None
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_loop_body_fn(
    node: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> LoopBodyFnExpr:
    global _ACTIVE_LOOP_BODY_DEPTH

    if not isinstance(node, SyntaxList) or len(node.items) != 3:
        _raise_error(
            "`loop/recur` body must be `(fn (state) body)`",
            code="loop_recur_fn_invalid",
            span=getattr(node, "span"),
            form_path=form_path,
            expansion_stack=getattr(node, "expansion_stack", ()),
        )
    head = syntax_identifier(node.items[0])
    binding_list = node.items[1]
    if head is None or head.resolved_name != "fn" or not isinstance(binding_list, SyntaxList) or len(binding_list.items) != 1:
        _raise_error(
            "`loop/recur` body must be `(fn (state) body)`",
            code="loop_recur_fn_invalid",
            span=node.span,
            form_path=form_path,
            expansion_stack=node.expansion_stack,
        )
    binding_node = syntax_identifier(binding_list.items[0])
    if binding_node is None:
        _raise_error(
            "`loop/recur` body binding must be one symbol",
            code="loop_recur_fn_invalid",
            span=binding_list.span,
            form_path=form_path,
            expansion_stack=binding_list.expansion_stack,
        )
    _ACTIVE_LOOP_BODY_DEPTH += 1
    try:
        body_expr = _elaborate(
            node.items[2],
            form_path=form_path,
            bound_names=frozenset(set(bound_names) | {binding_node.resolved_name}),
            procedure_names=procedure_names,
        )
    finally:
        _ACTIVE_LOOP_BODY_DEPTH -= 1
    return LoopBodyFnExpr(
        binding_name=binding_node.resolved_name,
        body_expr=body_expr,
        span=node.span,
        form_path=form_path,
        expansion_stack=node.expansion_stack,
    )


def _elaborate_continue(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ContinueExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`continue` requires exactly one state payload",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ContinueExpr(
        state_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_done(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> DoneExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`done` requires exactly one result payload",
            code="loop_recur_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return DoneExpr(
        result_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_call(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> CallExpr:
    if len(datum.items) < 2:
        _raise_error("`call` requires a callee name", span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    callee_node = datum.items[1]
    callee_identifier = syntax_identifier(callee_node)
    if callee_identifier is None:
        _raise_error(
            "`call` callee name must be a symbol",
            span=callee_node.span,
            form_path=form_path,
            expansion_stack=callee_node.expansion_stack,
        )
    raw_bindings = datum.items[2:]
    if len(raw_bindings) % 2 != 0:
        _raise_error(
            "`call` requires keyword/value binding pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    bindings: list[tuple[str, ExprNode]] = []
    for index in range(0, len(raw_bindings), 2):
        keyword_node = raw_bindings[index]
        value_node = raw_bindings[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`call` bindings must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        bindings.append(
            (
                keyword_node.value[1:],
                _elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
            )
        )
    return CallExpr(
        callee_name=(
            callee_identifier.resolved_name
            if callee_identifier.resolved_name in bound_names
            else callee_identifier.resolved_name
            if _ACTIVE_WORKFLOW_NAME_RESOLVER is None
            else _ACTIVE_WORKFLOW_NAME_RESOLVER(
                callee_identifier.resolved_name,
                callee_identifier.span,
                form_path,
            )
        ),
        bindings=tuple(bindings),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_function_call(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> FunctionCallExpr:
    callee_identifier = syntax_identifier(datum.items[0])
    assert callee_identifier is not None
    return FunctionCallExpr(
        callee_name=(
            _ACTIVE_FUNCTION_NAME_RESOLVER(
                callee_identifier.resolved_name,
                callee_identifier.span,
                form_path,
            )
            if _ACTIVE_FUNCTION_NAME_RESOLVER is not None
            else callee_identifier.resolved_name
        ),
        args=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for item in datum.items[1:]
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_procedure_call(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProcedureCallExpr:
    callee_identifier = syntax_identifier(datum.items[0])
    assert callee_identifier is not None
    callee_name = callee_identifier.resolved_name
    if callee_name not in bound_names:
        callee_name = (
            _ACTIVE_PROCEDURE_NAME_RESOLVER(
                callee_name,
                callee_identifier.span,
                form_path,
            )
            if _ACTIVE_PROCEDURE_NAME_RESOLVER is not None
            else callee_name
        )
    return ProcedureCallExpr(
        callee_name=callee_name,
        args=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for item in datum.items[1:]
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_with_phase(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> WithPhaseExpr:
    if len(datum.items) != 4:
        _raise_error(
            "`with-phase` requires a context, phase name, and one body",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    phase_name_node = datum.items[2]
    phase_identifier = syntax_identifier(phase_name_node)
    if phase_identifier is None:
        _raise_error(
            "`with-phase` phase name must be a symbol",
            span=phase_name_node.span,
            form_path=form_path,
            expansion_stack=phase_name_node.expansion_stack,
        )
    return WithPhaseExpr(
        ctx_expr=_elaborate(
            datum.items[1],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        phase_name=phase_identifier.resolved_name,
        body=_elaborate(
            datum.items[3],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_workflow_ref_literal(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
) -> WorkflowRefLiteralExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`workflow-ref` requires exactly one workflow symbol",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    target_identifier = syntax_identifier(datum.items[1])
    if target_identifier is None:
        _raise_error(
            "`workflow-ref` target must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    target_name = (
        _ACTIVE_WORKFLOW_NAME_RESOLVER(
            target_identifier.resolved_name,
            target_identifier.span,
            form_path,
        )
        if _ACTIVE_WORKFLOW_NAME_RESOLVER is not None
        else target_identifier.resolved_name
    )
    return WorkflowRefLiteralExpr(
        target_name=target_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_proc_ref_literal(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
) -> ProcRefLiteralExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`proc-ref` requires exactly one procedure symbol",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    target_identifier = syntax_identifier(datum.items[1])
    if target_identifier is None:
        _raise_error(
            "`proc-ref` target must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    authored_name = target_identifier.resolved_name
    if authored_name in _ACTIVE_LOCAL_PROC_NAMES:
        target_name = authored_name
    else:
        target_name = (
            _ACTIVE_PROCEDURE_NAME_RESOLVER(
                authored_name,
                target_identifier.span,
                form_path,
            )
            if _ACTIVE_PROCEDURE_NAME_RESOLVER is not None
            else authored_name
        )
    return ProcRefLiteralExpr(
        target_name=target_name,
        authored_name=authored_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_bind_proc(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> BindProcExpr:
    if len(datum.items) < 4 or len(datum.items[2:]) % 2 != 0:
        _raise_error(
            "`bind-proc` requires a proc-ref expression followed by keyword/value pairs",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    base_expr = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )
    bindings: list[BindProcBinding] = []
    raw_bindings = datum.items[2:]
    for index in range(0, len(raw_bindings), 2):
        keyword_node = raw_bindings[index]
        value_node = raw_bindings[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                "`bind-proc` bindings must use keyword/value pairs",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        bindings.append(
            BindProcBinding(
                name=keyword_node.value[1:],
                value_expr=_elaborate(
                    value_node,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
                keyword_span=keyword_node.span,
                keyword_form_path=form_path,
                keyword_expansion_stack=keyword_node.expansion_stack,
            )
        )
    return BindProcExpr(
        base_expr=base_expr,
        bindings=tuple(bindings),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_let_proc(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> LetProcExpr:
    global _ACTIVE_LOCAL_PROC_NAMES, _ACTIVE_LET_PROC_DEPTH

    if len(datum.items) != 3:
        _raise_error(
            "`let-proc` requires exactly one binding and one body",
            code="let_proc_syntax_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    binding_node = datum.items[1]
    if not isinstance(binding_node, SyntaxList):
        _raise_error(
            "`let-proc` binding must be a list",
            code="let_proc_syntax_invalid",
            span=binding_node.span,
            form_path=form_path,
            expansion_stack=binding_node.expansion_stack,
        )
    if binding_node.items and isinstance(binding_node.items[0], SyntaxList):
        _raise_error(
            "`let-proc` supports exactly one local binding in V1",
            code="let_proc_multiple_bindings_unsupported",
            span=binding_node.span,
            form_path=form_path,
            expansion_stack=binding_node.expansion_stack,
        )
    if len(binding_node.items) != 7:
        _raise_error(
            "`let-proc` binding must provide name, params, `->`, return type, `:captures`, and one body",
            code="let_proc_syntax_invalid",
            span=binding_node.span,
            form_path=form_path,
            expansion_stack=binding_node.expansion_stack,
        )
    name_identifier = syntax_identifier(binding_node.items[0])
    if name_identifier is None:
        _raise_error(
            "`let-proc` local name must be a symbol",
            code="let_proc_syntax_invalid",
            span=binding_node.items[0].span,
            form_path=form_path,
            expansion_stack=binding_node.items[0].expansion_stack,
        )
    if (
        name_identifier.resolved_name in bound_names
        or name_identifier.resolved_name in procedure_names
    ):
        _raise_error(
            (
                f"`let-proc` local procedure `{name_identifier.resolved_name}` collides "
                "with an existing value or procedure binding"
            ),
            code="let_proc_name_collision",
            span=binding_node.items[0].span,
            form_path=form_path,
            expansion_stack=binding_node.items[0].expansion_stack,
        )
    params_node = binding_node.items[1]
    if not isinstance(params_node, SyntaxList):
        _raise_error(
            "`let-proc` params must be a list",
            code="let_proc_syntax_invalid",
            span=params_node.span,
            form_path=form_path,
            expansion_stack=params_node.expansion_stack,
        )
    arrow_identifier = syntax_identifier(binding_node.items[2])
    if arrow_identifier is None or arrow_identifier.resolved_name != "->":
        _raise_error(
            "`let-proc` requires `->` before the return type",
            code="let_proc_syntax_invalid",
            span=binding_node.items[2].span,
            form_path=form_path,
            expansion_stack=binding_node.items[2].expansion_stack,
        )
    return_type_identifier = syntax_identifier(binding_node.items[3])
    if return_type_identifier is None:
        _raise_error(
            "`let-proc` return type must be a symbol",
            code="let_proc_syntax_invalid",
            span=binding_node.items[3].span,
            form_path=form_path,
            expansion_stack=binding_node.items[3].expansion_stack,
        )
    captures_keyword = binding_node.items[4]
    if not isinstance(captures_keyword, SyntaxKeyword) or captures_keyword.value != ":captures":
        _raise_error(
            "`let-proc` requires a `:captures` clause",
            code="let_proc_syntax_invalid",
            span=getattr(captures_keyword, "span", binding_node.span),
            form_path=form_path,
            expansion_stack=getattr(captures_keyword, "expansion_stack", datum.expansion_stack),
        )
    captures_node = binding_node.items[5]
    if not isinstance(captures_node, SyntaxList):
        _raise_error(
            "`let-proc` captures must be a list of identifiers",
            code="let_proc_syntax_invalid",
            span=captures_node.span,
            form_path=form_path,
            expansion_stack=captures_node.expansion_stack,
        )

    params = tuple(_elaborate_let_proc_param(param, form_path) for param in params_node.items)
    capture_names: list[str] = []
    seen_captures: set[str] = set()
    for capture_node in captures_node.items:
        capture_identifier = syntax_identifier(capture_node)
        if capture_identifier is None or "." in capture_identifier.resolved_name:
            _raise_error(
                "`let-proc` captures must be plain identifiers",
                code="let_proc_capture_not_identifier",
                span=capture_node.span,
                form_path=form_path,
                expansion_stack=capture_node.expansion_stack,
            )
        capture_name = capture_identifier.resolved_name
        if capture_name not in bound_names:
            _raise_error(
                f"unknown `let-proc` capture `{capture_name}`",
                code="let_proc_capture_unknown",
                span=capture_node.span,
                form_path=form_path,
                expansion_stack=capture_node.expansion_stack,
            )
        if capture_name in seen_captures:
            _raise_error(
                f"duplicate `let-proc` capture `{capture_name}`",
                code="let_proc_capture_duplicate",
                span=capture_node.span,
                form_path=form_path,
                expansion_stack=capture_node.expansion_stack,
            )
        seen_captures.add(capture_name)
        capture_names.append(capture_name)

    previous_local_proc_names = _ACTIVE_LOCAL_PROC_NAMES
    previous_let_proc_depth = _ACTIVE_LET_PROC_DEPTH
    _ACTIVE_LOCAL_PROC_NAMES = _ACTIVE_LOCAL_PROC_NAMES | frozenset({name_identifier.resolved_name})
    _ACTIVE_LET_PROC_DEPTH += 1
    try:
        local_body = _elaborate(
            binding_node.items[6],
            form_path=form_path,
            bound_names=frozenset(capture_names) | frozenset(param.name for param in params),
            procedure_names=procedure_names,
        )
        body = _elaborate(
            datum.items[2],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
    finally:
        _ACTIVE_LOCAL_PROC_NAMES = previous_local_proc_names
        _ACTIVE_LET_PROC_DEPTH = previous_let_proc_depth

    return LetProcExpr(
        binding=LetProcBinding(
            local_name=name_identifier.resolved_name,
            params=params,
            return_type_name=return_type_identifier.resolved_name,
            capture_names=tuple(capture_names),
            local_body=local_body,
            span=binding_node.span,
            form_path=form_path,
            expansion_stack=binding_node.expansion_stack,
        ),
        body=body,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_let_proc_param(raw_param: object, form_path: tuple[str, ...]) -> ProcedureParam:
    if not isinstance(raw_param, SyntaxList) or len(raw_param.items) != 2:
        _raise_error(
            "`let-proc` params must be two-item lists of `(name Type)`",
            code="let_proc_syntax_invalid",
            span=getattr(raw_param, "span"),
            form_path=form_path,
            expansion_stack=getattr(raw_param, "expansion_stack", ()),
        )
    name_identifier = syntax_identifier(raw_param.items[0])
    type_identifier = syntax_identifier(raw_param.items[1])
    if name_identifier is None:
        _raise_error(
            "`let-proc` param names must be symbols",
            code="let_proc_syntax_invalid",
            span=raw_param.items[0].span,
            form_path=form_path,
            expansion_stack=raw_param.items[0].expansion_stack,
        )
    if type_identifier is None:
        _raise_error(
            "`let-proc` param types must be symbols",
            code="let_proc_syntax_invalid",
            span=raw_param.items[1].span,
            form_path=form_path,
            expansion_stack=raw_param.items[1].expansion_stack,
        )
    return ProcedureParam(
        name=name_identifier.resolved_name,
        type_name=type_identifier.resolved_name,
        span=raw_param.span,
        form_path=form_path,
        expansion_stack=raw_param.expansion_stack,
    )


def _elaborate_phase_target(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
) -> PhaseTargetExpr:
    if len(datum.items) != 2:
        _raise_error(
            "`phase-target` requires exactly one target symbol",
            code="phase_target_name_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    target_node = datum.items[1]
    target_identifier = syntax_identifier(target_node)
    if target_identifier is None:
        _raise_error(
            "`phase-target` target name must be a symbol",
            code="phase_target_name_invalid",
            span=target_node.span,
            form_path=form_path,
            expansion_stack=target_node.expansion_stack,
        )
    return PhaseTargetExpr(
        target_name=target_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_generated_relpath_seed(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
) -> GeneratedRelpathSeedExpr:
    if len(datum.items) != 4:
        _raise_error(
            "`__generated-relpath-seed__` requires a type name, literal path, and seed role",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    type_identifier = syntax_identifier(datum.items[1])
    if type_identifier is None:
        _raise_error(
            "`__generated-relpath-seed__` type name must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    path_node = datum.items[2]
    if not isinstance(path_node, SyntaxString):
        _raise_error(
            "`__generated-relpath-seed__` literal path must be a string",
            span=datum.items[2].span,
            form_path=form_path,
            expansion_stack=datum.items[2].expansion_stack,
        )
    seed_role_node = datum.items[3]
    if not isinstance(seed_role_node, SyntaxString):
        _raise_error(
            "`__generated-relpath-seed__` seed role must be a string",
            span=datum.items[3].span,
            form_path=form_path,
            expansion_stack=datum.items[3].expansion_stack,
        )
    return GeneratedRelpathSeedExpr(
        target_type_ref=type_identifier.resolved_name,
        literal_path=path_node.value,
        seed_role=seed_role_node.value,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_provider_result(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProviderResultExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`provider-result` requires provider, :prompt, :inputs, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    provider = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`provider-result`")
    allowed_sections = {
        ":prompt",
        ":inputs",
        ":returns",
        ":model",
        ":effort",
        ":timeout-sec",
        ":prompt-dependencies",
    }
    invalid_section = next((name for name in sections if name not in allowed_sections), None)
    if invalid_section is not None:
        keyword_node = next(
            item
            for item in datum.items[2::2]
            if isinstance(item, SyntaxKeyword) and item.value == invalid_section
        )
        _raise_error(
            f"`provider-result` does not accept keyword `{invalid_section}`",
            code="provider_result_keyword_invalid",
            span=keyword_node.span,
            form_path=form_path,
            expansion_stack=keyword_node.expansion_stack,
        )
    prompt_node = sections.get(":prompt")
    inputs_node = sections.get(":inputs")
    returns_node = sections.get(":returns")
    if prompt_node is None or inputs_node is None or returns_node is None:
        _raise_error(
            "`provider-result` requires :prompt, :inputs, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if not isinstance(inputs_node, SyntaxList):
        _raise_error(
            "`provider-result :inputs` must be a list",
            span=inputs_node.span,
            form_path=form_path,
            expansion_stack=inputs_node.expansion_stack,
        )
    return_spec = parse_return_spec(
        returns_node,
        form_path=form_path,
        label="`provider-result :returns`",
    )
    return ProviderResultExpr(
        provider=provider,
        prompt=_elaborate(
            prompt_node,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        inputs=tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for item in inputs_node.items
        ),
        returns_type_name=return_spec.type_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
        model=(
            _elaborate(
                sections[":model"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            if ":model" in sections
            else None
        ),
        effort=(
            _elaborate(
                sections[":effort"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            if ":effort" in sections
            else None
        ),
        timeout_sec=(
            LiteralExpr(
                value=sections[":timeout-sec"].value,
                literal_kind="float",
                span=sections[":timeout-sec"].span,
                form_path=form_path,
                expansion_stack=sections[":timeout-sec"].expansion_stack,
            )
            if isinstance(sections.get(":timeout-sec"), SyntaxFloat)
            else _elaborate(
                sections[":timeout-sec"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            if ":timeout-sec" in sections
            else None
        ),
        prompt_dependencies=(
            _elaborate_prompt_dependencies(
                sections[":prompt-dependencies"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            if ":prompt-dependencies" in sections
            else None
        ),
        return_spec=return_spec,
    )


def _elaborate_prompt_dependencies(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> PromptDependencySpec:
    if not isinstance(datum, SyntaxList) or not datum.items:
        _raise_error(
            "`provider-result :prompt-dependencies` requires a non-empty keyword list",
            code="prompt_dependencies_clause_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if len(datum.items) % 2:
        _raise_error(
            "`provider-result :prompt-dependencies` requires keyword/value pairs",
            code="prompt_dependencies_clause_invalid",
            span=datum.items[-1].span,
            form_path=form_path,
            expansion_stack=datum.items[-1].expansion_stack,
        )

    sections: dict[str, object] = {}
    for index in range(0, len(datum.items), 2):
        keyword = datum.items[index]
        value = datum.items[index + 1]
        if not isinstance(keyword, SyntaxKeyword):
            _raise_error(
                "`provider-result :prompt-dependencies` entries must start with keywords",
                code="prompt_dependencies_clause_invalid",
                span=keyword.span,
                form_path=form_path,
                expansion_stack=keyword.expansion_stack,
            )
        if keyword.value in sections:
            _raise_error(
                f"`provider-result :prompt-dependencies` duplicated keyword `{keyword.value}`",
                code="prompt_dependencies_keyword_duplicate",
                span=keyword.span,
                form_path=form_path,
                expansion_stack=keyword.expansion_stack,
            )
        if keyword.value not in {":required", ":optional", ":position", ":instruction"}:
            _raise_error(
                f"`provider-result :prompt-dependencies` does not accept `{keyword.value}`",
                code="prompt_dependencies_keyword_invalid",
                span=keyword.span,
                form_path=form_path,
                expansion_stack=keyword.expansion_stack,
            )
        sections[keyword.value] = value

    def operands(section: str) -> tuple[ExprNode, ...]:
        value = sections.get(section)
        if value is None:
            return ()
        if not isinstance(value, SyntaxList) or not value.items:
            _raise_error(
                f"`provider-result :prompt-dependencies {section}` requires a non-empty list",
                code="prompt_dependencies_clause_invalid",
                span=value.span,
                form_path=form_path,
                expansion_stack=value.expansion_stack,
            )
        elaborated = tuple(
            _elaborate(
                item,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for item in value.items
        )
        generated = next(
            (item for item in elaborated if isinstance(item, GeneratedRelpathSeedExpr)),
            None,
        )
        if generated is not None:
            _raise_error(
                "compiler-generated relpath seeds are not prompt-dependency operands",
                code="prompt_dependency_generated_relpath_invalid",
                span=generated.span,
                form_path=generated.form_path,
                expansion_stack=generated.expansion_stack,
            )
        return elaborated

    required = operands(":required")
    optional = operands(":optional")
    if not required and not optional:
        _raise_error(
            "`provider-result :prompt-dependencies` requires required or optional operands",
            code="prompt_dependencies_clause_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )

    position = "prepend"
    position_node = sections.get(":position")
    if position_node is not None:
        identifier = syntax_identifier(position_node)
        if identifier is None or identifier.resolved_name not in {"prepend", "append"}:
            _raise_error(
                "prompt dependency position must be `prepend` or `append`",
                code="prompt_dependency_position_invalid",
                span=position_node.span,
                form_path=form_path,
                expansion_stack=position_node.expansion_stack,
            )
        position = identifier.resolved_name

    instruction = None
    instruction_node = sections.get(":instruction")
    if instruction_node is not None:
        if not isinstance(instruction_node, SyntaxString):
            _raise_error(
                "prompt dependency instruction must be a literal string",
                code="prompt_dependency_instruction_literal_required",
                span=instruction_node.span,
                form_path=form_path,
                expansion_stack=instruction_node.expansion_stack,
            )
        instruction = instruction_node.value
        if len(instruction.encode("utf-8", errors="strict")) > 261630:
            _raise_error(
                "prompt dependency instruction exceeds its UTF-8 byte limit",
                code="prompt_dependency_instruction_exceeds_byte_limit",
                span=instruction_node.span,
                form_path=form_path,
                expansion_stack=instruction_node.expansion_stack,
            )

    return PromptDependencySpec(
        required=required,
        optional=optional,
        position=position,
        instruction=instruction,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_provider_bundle_path(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProviderBundlePathExpr:
    if len(datum.items) != 4:
        _raise_error(
            "`provider-bundle-path` requires source and :as target type",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    source_expr = _elaborate(
        datum.items[1],
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )
    keyword = datum.items[2]
    if not isinstance(keyword, SyntaxKeyword) or keyword.value != ":as":
        _raise_error(
            "`provider-bundle-path` requires :as target type",
            span=keyword.span,
            form_path=form_path,
            expansion_stack=keyword.expansion_stack,
        )
    target_identifier = syntax_identifier(datum.items[3])
    if target_identifier is None:
        _raise_error(
            "`provider-bundle-path :as` must name a path type",
            span=datum.items[3].span,
            form_path=form_path,
            expansion_stack=datum.items[3].expansion_stack,
        )
    return ProviderBundlePathExpr(
        source_expr=source_expr,
        target_type_name=target_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_command_result(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> CommandResultExpr:
    if len(datum.items) < 5:
        _raise_error(
            "`command-result` requires a step name plus either :argv or :adapter/:inputs and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    step_name_node = datum.items[1]
    step_identifier = syntax_identifier(step_name_node)
    if step_identifier is None:
        _raise_error(
            "`command-result` step name must be a symbol",
            span=step_name_node.span,
            form_path=form_path,
            expansion_stack=step_name_node.expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`command-result`")
    argv_node = sections.get(":argv")
    adapter_node = sections.get(":adapter")
    inputs_node = sections.get(":inputs")
    returns_node = sections.get(":returns")
    uses_raw_argv = argv_node is not None
    uses_adapter = adapter_node is not None or inputs_node is not None
    if returns_node is None:
        _raise_error(
            "`command-result` requires :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return_spec = parse_return_spec(
        returns_node,
        form_path=form_path,
        label="`command-result :returns`",
    )
    if uses_raw_argv and uses_adapter:
        _raise_error(
            "`command-result` must use exactly one of :argv or :adapter/:inputs",
            code="command_result_adapter_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if uses_raw_argv:
        if not isinstance(argv_node, SyntaxList):
            _raise_error(
                "`command-result :argv` must be a list",
                span=argv_node.span,
                form_path=form_path,
                expansion_stack=argv_node.expansion_stack,
            )
        return CommandResultExpr(
            step_name=step_identifier.resolved_name,
            argv=tuple(
                _elaborate(
                    item,
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                )
                for item in argv_node.items
            ),
            adapter_name=None,
            adapter_inputs=(),
            returns_type_name=return_spec.type_name,
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
            return_spec=return_spec,
        )
    if adapter_node is None or inputs_node is None:
        _raise_error(
            "`command-result` adapter mode requires both :adapter and :inputs",
            code="command_result_adapter_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    adapter_identifier = syntax_identifier(adapter_node)
    if adapter_identifier is None:
        _raise_error(
            "`command-result :adapter` must be a symbol",
            code="command_result_adapter_invalid",
            span=adapter_node.span,
            form_path=form_path,
            expansion_stack=adapter_node.expansion_stack,
        )
    if not isinstance(inputs_node, SyntaxList):
        _raise_error(
            "`command-result :inputs` must be a list of (field expr) pairs",
            code="command_result_adapter_invalid",
            span=inputs_node.span,
            form_path=form_path,
            expansion_stack=inputs_node.expansion_stack,
        )
    seen_input_names: set[str] = set()
    adapter_inputs: list[tuple[str, ExprNode]] = []
    for item in inputs_node.items:
        if not isinstance(item, SyntaxList) or len(item.items) != 2:
            _raise_error(
                "`command-result :inputs` entries must be (field expr) pairs",
                code="command_result_adapter_invalid",
                span=item.span if isinstance(item, SyntaxList) else inputs_node.span,
                form_path=form_path,
                expansion_stack=getattr(item, "expansion_stack", inputs_node.expansion_stack),
            )
        field_identifier = syntax_identifier(item.items[0])
        if field_identifier is None:
            _raise_error(
                "`command-result :inputs` field names must be symbols",
                code="command_result_adapter_invalid",
                span=item.items[0].span,
                form_path=form_path,
                expansion_stack=item.items[0].expansion_stack,
            )
        field_name = field_identifier.resolved_name
        if field_name in seen_input_names:
            _raise_error(
                f"`command-result :inputs` duplicates field `{field_name}`",
                code="command_result_adapter_invalid",
                span=item.items[0].span,
                form_path=form_path,
                expansion_stack=item.items[0].expansion_stack,
            )
        seen_input_names.add(field_name)
        adapter_inputs.append(
            (
                field_name,
                _elaborate(
                    item.items[1],
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
            )
        )
    return CommandResultExpr(
        step_name=step_identifier.resolved_name,
        argv=(),
        adapter_name=adapter_identifier.resolved_name,
        adapter_inputs=tuple(adapter_inputs),
        returns_type_name=return_spec.type_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
        return_spec=return_spec,
    )


def _elaborate_run_provider_phase(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> RunProviderPhaseExpr:
    if len(datum.items) < 7:
        _raise_error(
            "`run-provider-phase` requires a phase name plus :ctx, :inputs, :provider, :prompt, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    phase_identifier = syntax_identifier(datum.items[1])
    if phase_identifier is None:
        _raise_error(
            "`run-provider-phase` phase name must be a symbol",
            code="run_provider_phase_return_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`run-provider-phase`")
    ctx_node = sections.get(":ctx")
    inputs_node = sections.get(":inputs")
    provider_node = sections.get(":provider")
    prompt_node = sections.get(":prompt")
    returns_node = sections.get(":returns")
    if any(node is None for node in (ctx_node, inputs_node, provider_node, prompt_node, returns_node)):
        _raise_error(
            "`run-provider-phase` requires :ctx, :inputs, :provider, :prompt, and :returns",
            code="run_provider_phase_return_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    returns_identifier = syntax_identifier(returns_node)
    if returns_identifier is None:
        _raise_error(
            "`run-provider-phase :returns` must be a symbol",
            code="run_provider_phase_return_invalid",
            span=returns_node.span,
            form_path=form_path,
            expansion_stack=returns_node.expansion_stack,
        )
    return RunProviderPhaseExpr(
        phase_name=phase_identifier.resolved_name,
        ctx_expr=_elaborate(ctx_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        inputs_expr=_elaborate(inputs_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        provider=_elaborate(provider_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        prompt=_elaborate(prompt_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_produce_one_of(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProduceOneOfExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`produce-one-of` requires a return type plus :ctx, :producer, and :candidates",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    returns_identifier = syntax_identifier(datum.items[1])
    if returns_identifier is None:
        _raise_error(
            "`produce-one-of` return type must be a symbol",
            code="produce_one_of_candidate_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`produce-one-of`")
    ctx_node = sections.get(":ctx")
    producer_node = sections.get(":producer")
    candidates_node = sections.get(":candidates")
    if ctx_node is None or producer_node is None or candidates_node is None:
        _raise_error(
            "`produce-one-of` requires :ctx, :producer, and :candidates",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    if not isinstance(producer_node, SyntaxList):
        _raise_error(
            "`produce-one-of :producer` must be a list",
            code="produce_one_of_candidate_invalid",
            span=producer_node.span,
            form_path=form_path,
            expansion_stack=producer_node.expansion_stack,
        )
    producer = _elaborate_produce_one_of_producer(
        producer_node,
        form_path=form_path,
        bound_names=bound_names,
        procedure_names=procedure_names,
    )
    if not isinstance(candidates_node, SyntaxList):
        _raise_error(
            "`produce-one-of :candidates` must be a list",
            code="produce_one_of_candidate_invalid",
            span=candidates_node.span,
            form_path=form_path,
            expansion_stack=candidates_node.expansion_stack,
        )
    return ProduceOneOfExpr(
        returns_type_name=returns_identifier.resolved_name,
        ctx_expr=_elaborate(ctx_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        producer=producer,
        candidates=tuple(
            _elaborate_produce_one_of_candidate(
                candidate_node,
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            for candidate_node in candidates_node.items
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_resume_or_start(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ResumeOrStartExpr:
    if len(datum.items) < 6:
        _raise_error(
            "`resume-or-start` requires a name plus :ctx, :resume-from, :start, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    resume_identifier = syntax_identifier(datum.items[1])
    if resume_identifier is None:
        _raise_error(
            "`resume-or-start` name must be a symbol",
            code="resume_or_start_contract_invalid",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`resume-or-start`")
    required = (":ctx", ":resume-from", ":start", ":returns")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`resume-or-start` requires :ctx, :resume-from, :start, and :returns",
            code="resume_or_start_contract_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    valid_when_node = sections.get(":valid-when")
    valid_variants: tuple[str, ...] = ()
    if valid_when_node is not None:
        if not isinstance(valid_when_node, SyntaxList):
            _raise_error(
                "`resume-or-start :valid-when` must be a list of variants",
                code="resume_or_start_contract_invalid",
                span=valid_when_node.span,
                form_path=form_path,
                expansion_stack=valid_when_node.expansion_stack,
            )
        variants: list[str] = []
        for item in valid_when_node.items:
            variant_identifier = syntax_identifier(item)
            if variant_identifier is None:
                _raise_error(
                    "`resume-or-start :valid-when` entries must be symbols",
                    code="resume_or_start_contract_invalid",
                    span=item.span,
                    form_path=form_path,
                    expansion_stack=item.expansion_stack,
                )
            variants.append(variant_identifier.resolved_name)
        valid_variants = tuple(variants)
    returns_identifier = syntax_identifier(sections[":returns"])
    if returns_identifier is None:
        _raise_error(
            "`resume-or-start :returns` must be a symbol",
            code="resume_or_start_contract_invalid",
            span=sections[":returns"].span,
            form_path=form_path,
            expansion_stack=sections[":returns"].expansion_stack,
    )
    return ResumeOrStartExpr(
        resume_name=resume_identifier.resolved_name,
        ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        resume_from_expr=_elaborate(sections[":resume-from"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        valid_when=valid_variants,
        start_expr=_elaborate(sections[":start"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_resource_transition(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ResourceTransitionExpr:
    if len(datum.items) < 2:
        _raise_error(
            "`resource-transition` requires either the legacy queue-move shape or the declared-transition keyword shape",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )

    if isinstance(datum.items[1], SyntaxKeyword):
        sections = _keyword_sections(datum.items[1:], form_path=form_path, label="`resource-transition`")
        required = (":transition", ":resource", ":request")
        if any(sections.get(keyword) is None for keyword in required):
            _raise_error(
                "`resource-transition` requires :transition, :resource, and :request for declared transitions",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        transition_identifier = syntax_identifier(sections[":transition"])
        resource_identifier = syntax_identifier(sections[":resource"])
        if transition_identifier is None or resource_identifier is None:
            _raise_error(
                "`resource-transition :transition` and `:resource` must be symbols",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        return ResourceTransitionExpr(
            spec=ResourceTransitionSpec(
                mode="declared_transition",
                transition_ref_name=transition_identifier.resolved_name,
                resource_ref_name=resource_identifier.resolved_name,
                expected_version_expr=(
                    _elaborate(
                        sections[":expect-version"],
                        form_path=form_path,
                        bound_names=bound_names,
                        procedure_names=procedure_names,
                    )
                    if sections.get(":expect-version") is not None
                    else None
                ),
                request_expr=_elaborate(
                    sections[":request"],
                    form_path=form_path,
                    bound_names=bound_names,
                    procedure_names=procedure_names,
                ),
            ),
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )

    if len(datum.items) < 8:
        _raise_error(
            "`resource-transition` requires a transition name plus :ctx, :resource, :from, :to, :ledger, and :event",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    transition_identifier = syntax_identifier(datum.items[1])
    if transition_identifier is None:
        _raise_error(
            "`resource-transition` transition name must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`resource-transition`")
    required = (":ctx", ":resource", ":from", ":to", ":ledger", ":event")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`resource-transition` requires :ctx, :resource, :from, :to, :ledger, and :event",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    from_identifier = syntax_identifier(sections[":from"])
    to_identifier = syntax_identifier(sections[":to"])
    event_identifier = syntax_identifier(sections[":event"])
    if from_identifier is None or to_identifier is None or event_identifier is None:
        _raise_error(
            "`resource-transition` queue and event operands must be symbols",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ResourceTransitionExpr(
        spec=ResourceTransitionSpec(
            mode="legacy_queue_move",
            transition_name=transition_identifier.resolved_name,
            ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            when_expr=(
                _elaborate(sections[":when"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names)
                if sections.get(":when") is not None
                else None
            ),
            resource_expr=_elaborate(
                sections[":resource"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            ),
            from_queue_name=from_identifier.resolved_name,
            to_queue_name=to_identifier.resolved_name,
            ledger_expr=_elaborate(sections[":ledger"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            event_name=event_identifier.resolved_name,
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_materialize_view(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> MaterializeViewExpr:
    if len(datum.items) < 2:
        _raise_error(
            "`materialize-view` requires a view name plus keyword arguments",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    view_identifier = syntax_identifier(datum.items[1])
    if view_identifier is None:
        _raise_error(
            "`materialize-view` view name must be a symbol",
            span=datum.items[1].span,
            form_path=form_path,
            expansion_stack=datum.items[1].expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`materialize-view`")
    required = (":value", ":renderer", ":renderer-version", ":returns")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`materialize-view` requires :value, :renderer, :renderer-version, and :returns",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    renderer_identifier = syntax_identifier(sections[":renderer"])
    if renderer_identifier is None:
        _raise_error(
            "`materialize-view :renderer` must be a symbol",
            code="materialize_view_renderer_unknown",
            span=sections[":renderer"].span,
            form_path=form_path,
            expansion_stack=sections[":renderer"].expansion_stack,
        )
    renderer_version = sections[":renderer-version"]
    if not isinstance(renderer_version, SyntaxInt):
        _raise_error(
            "`materialize-view :renderer-version` must be an integer literal",
            code="materialize_view_renderer_unknown",
            span=sections[":renderer-version"].span,
            form_path=form_path,
            expansion_stack=sections[":renderer-version"].expansion_stack,
        )
    returns_identifier = syntax_identifier(sections[":returns"])
    if returns_identifier is None:
        _raise_error(
            "`materialize-view :returns` must be a symbol",
            code="materialize_view_target_contract_invalid",
            span=sections[":returns"].span,
            form_path=form_path,
            expansion_stack=sections[":returns"].expansion_stack,
        )
    return MaterializeViewExpr(
        view_name=view_identifier.resolved_name,
        value_expr=_elaborate(
            sections[":value"],
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        ),
        renderer_id=renderer_identifier.resolved_name,
        renderer_version=renderer_version.value,
        target_expr=(
            _elaborate(
                sections[":target"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            )
            if sections.get(":target") is not None
            else None
        ),
        returns_type_name=returns_identifier.resolved_name,
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_finalize_selected_item(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> FinalizeSelectedItemExpr:
    sections = _keyword_sections(datum.items[1:], form_path=form_path, label="`finalize-selected-item`")
    required = (":ctx", ":selected", ":queue-transition", ":roadmap", ":plan", ":implementation")
    if any(sections.get(keyword) is None for keyword in required):
        _raise_error(
            "`finalize-selected-item` requires :ctx, :selected, :queue-transition, :roadmap, :plan, and :implementation",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return FinalizeSelectedItemExpr(
        spec=FinalizeSelectedItemSpec(
            ctx_expr=_elaborate(sections[":ctx"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            selected_expr=_elaborate(
                sections[":selected"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            ),
            queue_transition_expr=_elaborate(
                sections[":queue-transition"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            ),
            roadmap_expr=_elaborate(sections[":roadmap"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            plan_expr=_elaborate(sections[":plan"], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
            implementation_expr=_elaborate(
                sections[":implementation"],
                form_path=form_path,
                bound_names=bound_names,
                procedure_names=procedure_names,
            ),
        ),
        span=datum.span,
        form_path=form_path,
        expansion_stack=datum.expansion_stack,
    )


def _elaborate_produce_one_of_producer(
    datum: SyntaxList,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProduceOneOfProducerSpec:
    head = syntax_head(datum)
    if head is None or head.resolved_name != "provider" or len(datum.items) < 5:
        _raise_error(
            "`produce-one-of :producer` must be a `(provider ...)` form",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`produce-one-of :producer`")
    prompt_node = sections.get(":prompt")
    inputs_node = sections.get(":inputs")
    if prompt_node is None or inputs_node is None or not isinstance(inputs_node, SyntaxList):
        _raise_error(
            "`produce-one-of :producer` requires :prompt and list-valued :inputs",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ProduceOneOfProducerSpec(
        kind="provider",
        provider_expr=_elaborate(datum.items[1], form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        prompt_expr=_elaborate(prompt_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
        inputs=tuple(
            _elaborate(item, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names)
            for item in inputs_node.items
        ),
    )


def _elaborate_produce_one_of_candidate(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProduceOneOfCandidateSpec:
    if not isinstance(datum, SyntaxList) or not datum.items:
        _raise_error(
            "`produce-one-of` candidates must be non-empty lists",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    variant_identifier = syntax_identifier(datum.items[0])
    if variant_identifier is None:
        _raise_error(
            "`produce-one-of` candidate variants must be symbols",
            code="produce_one_of_candidate_invalid",
            span=datum.items[0].span,
            form_path=form_path,
            expansion_stack=datum.items[0].expansion_stack,
        )
    fields = tuple(
        _elaborate_produce_one_of_candidate_field(
            item,
            form_path=form_path,
            bound_names=bound_names,
            procedure_names=procedure_names,
        )
        for item in datum.items[1:]
    )
    if not fields:
        _raise_error(
            "`produce-one-of` candidates must describe at least one field",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ProduceOneOfCandidateSpec(variant_name=variant_identifier.resolved_name, fields=fields)


def _elaborate_produce_one_of_candidate_field(
    datum: object,
    *,
    form_path: tuple[str, ...],
    bound_names: frozenset[str],
    procedure_names: frozenset[str],
) -> ProduceOneOfCandidateFieldSpec:
    if not isinstance(datum, SyntaxList) or len(datum.items) < 3:
        _raise_error(
            "`produce-one-of` candidate fields must be structured lists",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    field_identifier = syntax_identifier(datum.items[0])
    if field_identifier is None:
        _raise_error(
            "`produce-one-of` candidate field names must be symbols",
            code="produce_one_of_candidate_invalid",
            span=datum.items[0].span,
            form_path=form_path,
            expansion_stack=datum.items[0].expansion_stack,
        )
    if len(datum.items) >= 4 and isinstance(datum.items[1], SyntaxIdentifier) and isinstance(datum.items[2], SyntaxKeyword):
        source_type_identifier = syntax_identifier(datum.items[1])
        sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`produce-one-of` candidate field")
        source_node = sections.get(":source")
        source_identifier = syntax_identifier(source_node) if source_node is not None else None
        if source_type_identifier is None or source_identifier is None:
            _raise_error(
                "`produce-one-of` candidate source fields require a type name and `:source` symbol",
                code="produce_one_of_candidate_invalid",
                span=datum.span,
                form_path=form_path,
                expansion_stack=datum.expansion_stack,
            )
        return ProduceOneOfCandidateFieldSpec(
            field_name=field_identifier.resolved_name,
            source_type_name=source_type_identifier.resolved_name,
            source_kind=source_identifier.resolved_name,
        )
    sections = _keyword_sections(datum.items[1:], form_path=form_path, label="`produce-one-of` candidate field")
    target_node = sections.get(":target")
    schema_node = sections.get(":schema")
    schema_identifier = syntax_identifier(schema_node) if schema_node is not None else None
    if target_node is None or schema_identifier is None:
        _raise_error(
            "`produce-one-of` candidate path fields require `:target` and `:schema`",
            code="produce_one_of_candidate_invalid",
            span=datum.span,
            form_path=form_path,
            expansion_stack=datum.expansion_stack,
        )
    return ProduceOneOfCandidateFieldSpec(
        field_name=field_identifier.resolved_name,
        schema_type_name=schema_identifier.resolved_name,
        target_expr=_elaborate(target_node, form_path=form_path, bound_names=bound_names, procedure_names=procedure_names),
    )


def _keyword_sections(
    items: list[object],
    *,
    form_path: tuple[str, ...],
    label: str,
) -> dict[str, object]:
    if len(items) % 2 != 0:
        _raise_error(
            f"{label} requires keyword/value pairs",
            span=items[-1].span,
            form_path=form_path,
            expansion_stack=items[-1].expansion_stack,
        )
    sections: dict[str, object] = {}
    for index in range(0, len(items), 2):
        keyword_node = items[index]
        value_node = items[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_error(
                f"{label} entries must start with keywords",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        if keyword_node.value in sections:
            _raise_error(
                f"{label} duplicated keyword `{keyword_node.value}`",
                span=keyword_node.span,
                form_path=form_path,
                expansion_stack=keyword_node.expansion_stack,
            )
        sections[keyword_node.value] = value_node
    return sections


def _raise_error(
    message: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    code: str = "frontend_parse_error",
    expansion_stack: ExpansionStack = (),
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
