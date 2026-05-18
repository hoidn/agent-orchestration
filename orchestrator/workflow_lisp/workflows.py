"""Stage 3 workflow-definition elaboration and signature registration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .definitions import WorkflowLispModule
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expressions import elaborate_expression
from .sexpr import ListExpr, SymbolAtom
from .spans import SourceSpan
from .syntax import SyntaxNode, WorkflowLispSyntaxModule
from .type_env import FrontendTypeEnvironment, RecordTypeRef, TypeRef, UnionTypeRef
from .typecheck import TypedExpr, typecheck_expression


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
    return_type_ref: RecordTypeRef | UnionTypeRef
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
        if not isinstance(return_type_ref, (RecordTypeRef, UnionTypeRef)):
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="workflow_return_type_invalid",
                    message=(
                        f"workflow `{workflow_def.name}` must return a record or union type, "
                        f"got `{workflow_def.return_type_name}`"
                    ),
                    span=workflow_def.span,
                    form_path=workflow_def.form_path,
                )
            )
            continue
        params: list[tuple[str, TypeRef]] = []
        for param in workflow_def.params:
            params.append(
                (
                    param.name,
                    type_env.resolve_type(
                        param.type_name,
                        span=param.span,
                        form_path=param.form_path,
                    ),
                )
            )
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
) -> tuple[TypedWorkflowDef, ...]:
    """Typecheck workflow parameters and bodies against the registered signatures."""

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

        body_expr = elaborate_expression(workflow_def.body, bound_names=frozenset(value_env))
        typed_body = typecheck_expression(
            body_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_catalog=workflow_catalog,
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
