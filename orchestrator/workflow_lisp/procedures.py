"""Procedure AST, catalogs, and validation helpers for Workflow Lisp."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EMPTY_EFFECT_SUMMARY, EffectAtom, EffectSummary, parse_effect_clause, render_effect_set
from .spans import SourceSpan
from .syntax import (
    ExpansionStack,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    WorkflowLispSyntaxModule,
    syntax_head,
    syntax_identifier,
    syntax_node_datum,
    syntax_resolved_name,
)
from .type_env import FrontendTypeEnvironment, TypeRef


@dataclass(frozen=True)
class ProcedureParam:
    """Authored `defproc` parameter before type resolution."""

    name: str
    type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


class ProcedureLoweringMode(StrEnum):
    """Allowed lowering strategies for reusable workflow procedures."""

    INLINE = "inline"
    PRIVATE_WORKFLOW = "private-workflow"
    AUTO = "auto"


@dataclass(frozen=True)
class ProcedureDef:
    """Parsed `defproc` body, signature text, effects, and lowering request."""

    name: str
    params: tuple[ProcedureParam, ...]
    return_type_name: str
    declared_effects: frozenset[EffectAtom]
    requested_lowering_mode: ProcedureLoweringMode
    body: SyntaxNode
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProcedureSignature:
    """Type-resolved procedure signature used by call sites and lowering."""

    name: str
    params: tuple[tuple[str, TypeRef], ...]
    return_type_ref: TypeRef
    declared_effects: frozenset[EffectAtom]
    requested_lowering_mode: ProcedureLoweringMode
    span: SourceSpan
    form_path: tuple[str, ...]


@dataclass(frozen=True)
class ProcedureCallableSpecialization:
    """Compile-time bindings attached to a specialized procedure."""

    base_name: str
    specialized_name: str
    workflow_ref_bindings: Mapping[str, object]
    proc_ref_bindings: Mapping[str, object]
    value_bindings: Mapping[str, object]
    bound_param_types: Mapping[str, TypeRef]
    origin_span: SourceSpan
    origin_form_path: tuple[str, ...]


@dataclass(frozen=True)
class TypedProcedureDef:
    """Procedure definition after body typechecking and effect analysis."""

    definition: ProcedureDef
    signature: ProcedureSignature
    typed_body: object
    direct_effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY
    transitive_effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY
    resolved_lowering_mode: ProcedureLoweringMode = ProcedureLoweringMode.AUTO
    generated_workflow_name: str | None = None
    specialization: object | None = None


@dataclass(frozen=True)
class ProcedureCatalog:
    """Lookup table for procedure signatures, definitions, and call graph."""

    signatures_by_name: Mapping[str, ProcedureSignature]
    definitions_by_name: Mapping[str, ProcedureDef]
    call_graph: Mapping[str, frozenset[str]]


def proc_ref_specialization_name(
    base_name: str,
    proc_ref_bindings: Mapping[str, object],
) -> str:
    digest = hashlib.sha1(
        "|".join(
            [
                base_name,
                *(
                    f"{name}:{getattr(value, 'call_target_name', type(value).__name__)}"
                    for name, value in sorted(proc_ref_bindings.items())
                ),
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]
    normalized_base = base_name.replace("/", ".").replace("::", ".").replace("-", "_")
    return f"%proc-ref-call.{normalized_base}.{digest}"


def elaborate_procedure_definitions(module_syntax: WorkflowLispSyntaxModule) -> tuple[ProcedureDef, ...]:
    """Extract and parse every `defproc` form in a syntax module."""

    definitions: list[ProcedureDef] = []
    for form in module_syntax.forms:
        if syntax_resolved_name(syntax_head(form)) == "defproc":
            definitions.append(_elaborate_procedure_definition(form))
    return tuple(definitions)


def build_procedure_catalog(
    procedure_defs: tuple[ProcedureDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    imported_signatures: Mapping[str, ProcedureSignature] | None = None,
    lookup_aliases: Mapping[str, str] | None = None,
) -> ProcedureCatalog:
    """Build procedure signatures and detect duplicate local definitions."""

    signatures_by_name: dict[str, ProcedureSignature] = dict(imported_signatures or {})
    definitions_by_name: dict[str, ProcedureDef] = {}
    diagnostics: list[LispFrontendDiagnostic] = []
    for procedure_def in procedure_defs:
        if procedure_def.name in definitions_by_name:
            diagnostics.append(
                LispFrontendDiagnostic(
                    code="procedure_definition_duplicate",
                    message=f"duplicate procedure definition `{procedure_def.name}`",
                    span=procedure_def.span,
                    form_path=procedure_def.form_path,
                    expansion_stack=procedure_def.expansion_stack,
                )
            )
            continue
        return_type_ref = type_env.resolve_type(
            procedure_def.return_type_name,
            span=procedure_def.span,
            form_path=procedure_def.form_path,
            expansion_stack=procedure_def.expansion_stack,
        )
        params: list[tuple[str, TypeRef]] = []
        for param in procedure_def.params:
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
        signatures_by_name[procedure_def.name] = ProcedureSignature(
            name=procedure_def.name,
            params=tuple(params),
            return_type_ref=return_type_ref,
            declared_effects=procedure_def.declared_effects,
            requested_lowering_mode=procedure_def.requested_lowering_mode,
            span=procedure_def.span,
            form_path=procedure_def.form_path,
        )
        definitions_by_name[procedure_def.name] = procedure_def
    for alias_name, canonical_name in (lookup_aliases or {}).items():
        signature = signatures_by_name.get(canonical_name)
        if signature is not None:
            signatures_by_name[alias_name] = signature
    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))
    return ProcedureCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
        call_graph={},
    )


def with_call_graph(catalog: ProcedureCatalog, call_graph: Mapping[str, frozenset[str]]) -> ProcedureCatalog:
    """Return a catalog copy with resolved procedure dependencies attached."""

    return replace(catalog, call_graph=call_graph)


def validate_procedure_effects(
    *,
    procedure_def: ProcedureDef,
    declared_effects: frozenset[EffectAtom],
    inferred_effects: frozenset[EffectAtom],
) -> None:
    """Reject a procedure whose declared effects differ from inferred effects."""

    if declared_effects == inferred_effects:
        return
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="procedure_effect_mismatch",
                message=(
                    f"procedure `{procedure_def.name}` declared effects {render_effect_set(declared_effects)} "
                    f"but inferred {render_effect_set(inferred_effects)}"
                ),
                span=procedure_def.span,
                form_path=procedure_def.form_path,
                expansion_stack=procedure_def.expansion_stack,
            ),
        )
    )


def _elaborate_procedure_definition(form: SyntaxNode) -> ProcedureDef:
    datum = syntax_node_datum(form)
    if not isinstance(datum, SyntaxList) or len(datum.items) < 7:
        _raise_parse_error(
            "`defproc` requires a name, params, return arrow, return type, `:effects`, and one body",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    name_node = syntax_identifier(datum.items[1])
    if name_node is None:
        _raise_parse_error(
            "procedure name must be a symbol",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    params_node = datum.items[2]
    if not isinstance(params_node, SyntaxList):
        _raise_parse_error(
            "procedure params must be a list",
            span=params_node.span,
            form_path=form.form_path,
            expansion_stack=params_node.expansion_stack,
        )
    arrow_node = syntax_identifier(datum.items[3])
    if arrow_node is None or arrow_node.resolved_name != "->":
        _raise_parse_error(
            "procedure return separator must be `->`",
            span=datum.items[3].span,
            form_path=form.form_path,
            expansion_stack=datum.items[3].expansion_stack,
        )
    return_type_node = datum.items[4]
    return_type_identifier = syntax_identifier(return_type_node)
    if return_type_identifier is None:
        _raise_parse_error(
            "procedure return type must be a symbol",
            span=return_type_node.span,
            form_path=form.form_path,
            expansion_stack=return_type_node.expansion_stack,
        )

    sections = list(datum.items[5:])
    if not sections:
        _raise_missing_effects(form)
    lowering_mode = ProcedureLoweringMode.AUTO
    raw_effects: SyntaxList | None = None
    body_node: object | None = None
    index = 0
    while index < len(sections):
        current = sections[index]
        if not isinstance(current, SyntaxKeyword):
            body_node = current
            index += 1
            break
        if current.value == ":effects":
            if index + 1 >= len(sections) or not isinstance(sections[index + 1], SyntaxList):
                _raise_invalid_effects_shape(form)
            raw_effects = sections[index + 1]
            index += 2
            continue
        if current.value == ":lowering":
            if index + 1 >= len(sections):
                _raise_invalid_lowering(form)
            lowering_identifier = syntax_identifier(sections[index + 1])
            if lowering_identifier is None:
                _raise_invalid_lowering(form)
            try:
                lowering_mode = ProcedureLoweringMode(lowering_identifier.resolved_name)
            except ValueError as error:
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="proc_lowering_annotation_invalid",
                            message=f"unsupported procedure lowering mode `{lowering_identifier.display_name}`",
                            span=lowering_identifier.span,
                            form_path=form.form_path,
                            expansion_stack=lowering_identifier.expansion_stack,
                        ),
                    )
                ) from error
            index += 2
            continue
        _raise_parse_error(
            f"unsupported procedure clause `{current.value}`",
            span=current.span,
            form_path=form.form_path,
            expansion_stack=current.expansion_stack,
        )
    if raw_effects is None:
        _raise_missing_effects(form)
    if body_node is None or index != len(sections):
        _raise_parse_error(
            "`defproc` requires exactly one body expression",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    body = SyntaxNode(
        datum=body_node,
        span=body_node.span,
        module_path=form.module_path,
        form_path=form.form_path,
    )
    return ProcedureDef(
        name=name_node.resolved_name,
        params=tuple(_elaborate_param(param, form.form_path) for param in params_node.items),
        return_type_name=return_type_identifier.resolved_name,
        declared_effects=parse_effect_clause(
            raw_effects,
            span=raw_effects.span,
            form_path=form.form_path,
            expansion_stack=raw_effects.expansion_stack,
        ),
        requested_lowering_mode=lowering_mode,
        body=body,
        span=form.span,
        form_path=form.form_path,
        expansion_stack=form.expansion_stack,
    )


def _elaborate_param(raw_param: object, form_path: tuple[str, ...]) -> ProcedureParam:
    if not isinstance(raw_param, SyntaxList) or len(raw_param.items) != 2:
        _raise_parse_error(
            "procedure params must be two-item lists of `(name Type)`",
            span=getattr(raw_param, "span"),
            form_path=form_path,
            expansion_stack=getattr(raw_param, "expansion_stack", ()),
        )
    name_node = raw_param.items[0]
    type_node = raw_param.items[1]
    name_identifier = syntax_identifier(name_node)
    type_identifier = syntax_identifier(type_node)
    if name_identifier is None:
        _raise_parse_error(
            "procedure param names must be symbols",
            span=name_node.span,
            form_path=form_path,
            expansion_stack=name_node.expansion_stack,
        )
    if type_identifier is None:
        _raise_parse_error(
            "procedure param types must be symbols",
            span=type_node.span,
            form_path=form_path,
            expansion_stack=type_node.expansion_stack,
        )
    return ProcedureParam(
        name=name_identifier.resolved_name,
        type_name=type_identifier.resolved_name,
        span=raw_param.span,
        form_path=form_path,
        expansion_stack=raw_param.expansion_stack,
    )


def _raise_missing_effects(form: SyntaxNode) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="procedure_effect_missing",
                message="`defproc` requires a `:effects` clause",
                span=form.span,
                form_path=form.form_path,
                expansion_stack=form.expansion_stack,
            ),
        )
    )


def _raise_invalid_effects_shape(form: SyntaxNode) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="procedure_effect_invalid",
                message="`defproc` `:effects` must be followed by a list",
                span=form.span,
                form_path=form.form_path,
                expansion_stack=form.expansion_stack,
            ),
        )
    )


def _raise_invalid_lowering(form: SyntaxNode) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="proc_lowering_annotation_invalid",
                message="`defproc` `:lowering` must be followed by `inline`, `private-workflow`, or `auto`",
                span=form.span,
                form_path=form.form_path,
                expansion_stack=form.expansion_stack,
            ),
        )
    )


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
                code="frontend_parse_error",
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
