"""Procedure AST, catalogs, and validation helpers for Workflow Lisp."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EMPTY_EFFECT_SUMMARY, EffectAtom, EffectSummary, parse_effect_clause, render_effect_set
from .result_guidance import ReturnSpec, parse_return_spec
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

if TYPE_CHECKING:
    from .parametric_constraints import SharedUnionFieldCapability


@dataclass(frozen=True)
class ProcedureParam:
    """Authored `defproc` parameter before type resolution."""

    name: str
    type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProcedureTypeParam:
    """One authored compile-time type parameter declared by `defproc`."""

    name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProcedureConstraintSymbolOperandSyntax:
    """One symbol operand preserved from an authored `:where` clause."""

    symbol_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProcedureConstraintFieldRequirementSyntax:
    """One `(field Type)` pair preserved from an authored `:where` clause."""

    field_name: str
    field_type_name: str
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class ProcedureConstraintSyntax:
    """One parsed `:where` clause retained as structured metadata."""

    subject_name: str
    constraint_name: str
    symbol_operands: tuple[ProcedureConstraintSymbolOperandSyntax, ...]
    field_requirements: tuple[ProcedureConstraintFieldRequirementSyntax, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()

    @property
    def variant_name(self) -> str | None:
        if self.constraint_name != "has-union-variant" or not self.symbol_operands:
            return None
        return self.symbol_operands[0].symbol_name

    @property
    def field_name(self) -> str | None:
        if self.constraint_name not in {"has-field", "has-shared-union-field"}:
            return None
        if len(self.symbol_operands) != 2:
            return None
        return self.symbol_operands[0].symbol_name

    @property
    def field_type_name(self) -> str | None:
        if self.constraint_name not in {"has-field", "has-shared-union-field"}:
            return None
        if len(self.symbol_operands) != 2:
            return None
        return self.symbol_operands[1].symbol_name


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
    type_params: tuple[ProcedureTypeParam, ...] = ()
    where_clauses: tuple[ProcedureConstraintSyntax, ...] = ()
    generated_local_procedure: "GeneratedLocalProcedure | None" = None
    return_spec: ReturnSpec | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.return_spec is None:
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(type_name=self.return_type_name, guidance=None, span=self.span),
            )
        elif self.return_spec.type_name != self.return_type_name:
            # Existing specialization reconstructs definitions with a substituted
            # return type. Task 4 owns preservation of authored metadata through
            # that reconstruction; keep the Task 2 carrier internally coherent.
            object.__setattr__(
                self,
                "return_spec",
                ReturnSpec(
                    type_name=self.return_type_name,
                    guidance=None,
                    span=self.return_spec.span,
                ),
            )


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
    type_params: tuple[ProcedureTypeParam, ...] = ()
    where_clauses: tuple[ProcedureConstraintSyntax, ...] = ()


@dataclass(frozen=True)
class ProcedureCallableSpecialization:
    """Compile-time bindings attached to a specialized procedure."""

    base_name: str
    specialized_name: str
    specialization_key: str
    type_bindings: Mapping[str, TypeRef]
    workflow_ref_bindings: Mapping[str, object]
    proc_ref_bindings: Mapping[str, object]
    value_bindings: Mapping[str, object]
    bound_param_types: Mapping[str, TypeRef]
    origin_span: SourceSpan
    origin_form_path: tuple[str, ...]
    shared_union_field_capabilities: tuple["SharedUnionFieldCapability", ...] = ()


@dataclass(frozen=True)
class GeneratedLocalProcedure:
    """Compiler-private metadata for a `let-proc` generated hidden procedure."""

    authored_local_name: str
    generated_name: str
    owner_callable_name: str
    residual_params: tuple[tuple[str, str], ...]
    return_type_name: str
    capture_names: tuple[str, ...]
    origin_span: SourceSpan
    consumer_proc_ref_spans: tuple[SourceSpan, ...] = ()


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


def procedure_type_env_for(
    procedure: TypedProcedureDef,
    *,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None,
    default: FrontendTypeEnvironment,
) -> FrontendTypeEnvironment:
    """Resolve the owner type environment for one typed procedure body."""

    if procedure_type_envs is None:
        return default

    candidate_names = [procedure.definition.name, procedure.signature.name]
    specialization = getattr(procedure, "specialization", None)
    base_name = getattr(specialization, "base_name", None)
    if isinstance(base_name, str):
        candidate_names.append(base_name)

    expanded_candidate_names: list[str] = []
    for candidate_name in candidate_names:
        expanded_candidate_names.append(candidate_name)
        if "::" in candidate_name:
            expanded_candidate_names.append(candidate_name.rsplit("::", 1)[-1])
        if "/" in candidate_name:
            expanded_candidate_names.append(candidate_name.rsplit("/", 1)[-1])

    for candidate_name in expanded_candidate_names:
        resolved = procedure_type_envs.get(candidate_name)
        if resolved is not None:
            return resolved

    generated_local_types = {
        type_name
        for type_name in (
            *(param.type_name for param in procedure.definition.params),
            procedure.definition.return_type_name,
        )
        if isinstance(type_name, str) and type_name.startswith("%loop-state.")
    }
    if generated_local_types:
        for candidate_env in procedure_type_envs.values():
            try:
                for type_name in generated_local_types:
                    candidate_env.resolve_type(
                        type_name,
                        span=procedure.definition.span,
                        form_path=procedure.definition.form_path,
                    )
            except LispFrontendCompileError:
                continue
            return candidate_env
        from .loop_state import register_known_carrier_type

        for type_name in generated_local_types:
            register_known_carrier_type(
                default,
                type_name=type_name,
                span=procedure.definition.span,
                form_path=procedure.definition.form_path,
            )
    return default


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


def parametric_specialization_name(
    base_name: str,
    type_bindings: Mapping[str, TypeRef],
) -> str:
    digest = hashlib.sha1(
        "|".join(
            [
                base_name,
                *(f"{name}:{_type_ref_identity(type_ref)}" for name, type_ref in sorted(type_bindings.items())),
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]
    normalized_base = base_name.replace("/", ".").replace("::", ".").replace("-", "_")
    return f"%parametric-call.{normalized_base}.{digest}"


def let_proc_generated_name(
    *,
    owner_callable_name: str,
    local_name: str,
    origin_span: SourceSpan,
    param_type_names: tuple[str, ...],
    return_type_name: str,
    capture_names: tuple[str, ...],
    semantic_body_identity: str,
) -> str:
    """Return a deterministic hidden procedure name for one `let-proc` binding."""

    digest = hashlib.sha1(
        "|".join(
            [
                owner_callable_name,
                local_name,
                str(origin_span.start.line),
                str(origin_span.start.column),
                str(origin_span.end.line),
                str(origin_span.end.column),
                ",".join(param_type_names),
                return_type_name,
                ",".join(capture_names),
                semantic_body_identity,
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]
    normalized_owner = owner_callable_name.replace("/", ".").replace("::", ".").replace("-", "_")
    normalized_local = local_name.replace("-", "_")
    return f"%let-proc.{normalized_owner}.{normalized_local}.{digest}"


def _type_ref_identity(type_ref: TypeRef) -> str:
    return repr(type_ref)


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
        local_type_params = frozenset(type_param.name for type_param in procedure_def.type_params)
        return_type_ref = type_env.resolve_type(
            procedure_def.return_type_name,
            span=procedure_def.span,
            form_path=procedure_def.form_path,
            expansion_stack=procedure_def.expansion_stack,
            local_type_params=local_type_params,
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
                        local_type_params=local_type_params,
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
            type_params=procedure_def.type_params,
            where_clauses=procedure_def.where_clauses,
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
    index = 2
    type_params: tuple[ProcedureTypeParam, ...] = ()
    if _keyword_value(datum.items[index]) == ":forall":
        type_params = _elaborate_type_params(datum.items[index + 1] if index + 1 < len(datum.items) else None, form)
        index += 2

    if index >= len(datum.items):
        _raise_parse_error(
            "procedure params must be a list",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    params_node = datum.items[index]
    if not isinstance(params_node, SyntaxList):
        if _keyword_value(params_node) in {":forall", ":where"}:
            _raise_invalid_parametric_clause(
                "parametric `defproc` clauses must appear in `:forall`, params, `:where`, `->` order",
                node=params_node,
                form=form,
            )
        _raise_parse_error(
            "procedure params must be a list",
            span=params_node.span,
            form_path=form.form_path,
            expansion_stack=params_node.expansion_stack,
        )

    index += 1
    if _keyword_value(datum.items[index]) == ":forall":
        _raise_invalid_parametric_clause(
            "parametric `defproc` clauses must appear in `:forall`, params, `:where`, `->` order",
            node=datum.items[index],
            form=form,
        )

    where_clauses: tuple[ProcedureConstraintSyntax, ...] = ()
    if _keyword_value(datum.items[index]) == ":where":
        where_clauses = _elaborate_where_clauses(
            datum.items[index + 1] if index + 1 < len(datum.items) else None,
            form=form,
            declared_type_params=frozenset(type_param.name for type_param in type_params),
        )
        index += 2

    if index >= len(datum.items):
        _raise_parse_error(
            "procedure return separator must be `->`",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    arrow_node = syntax_identifier(datum.items[index])
    if arrow_node is None or arrow_node.resolved_name != "->":
        if _keyword_value(datum.items[index]) in {":forall", ":where"}:
            _raise_invalid_parametric_clause(
                "parametric `defproc` clauses must appear in `:forall`, params, `:where`, `->` order",
                node=datum.items[index],
                form=form,
            )
        _raise_parse_error(
            "procedure return separator must be `->`",
            span=datum.items[index].span,
            form_path=form.form_path,
            expansion_stack=datum.items[index].expansion_stack,
        )
    if index + 1 >= len(datum.items):
        _raise_parse_error(
            "procedure return type must be a symbol",
            span=form.span,
            form_path=form.form_path,
            expansion_stack=form.expansion_stack,
        )
    return_type_node = datum.items[index + 1]
    return_spec = parse_return_spec(
        return_type_node,
        form_path=form.form_path,
        label="procedure return type",
    )

    sections = list(datum.items[index + 2 :])
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
        return_type_name=return_spec.type_name,
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
        type_params=type_params,
        where_clauses=where_clauses,
        return_spec=return_spec,
    )


def _elaborate_type_params(raw_node: object | None, form: SyntaxNode) -> tuple[ProcedureTypeParam, ...]:
    if not isinstance(raw_node, SyntaxList):
        _raise_invalid_parametric_clause(
            "`defproc` `:forall` must be followed by a list of type-parameter names",
            node=form,
            form=form,
        )
    seen: set[str] = set()
    type_params: list[ProcedureTypeParam] = []
    for item in raw_node.items:
        identifier = syntax_identifier(item)
        if identifier is None:
            _raise_invalid_parametric_clause(
                "`defproc` `:forall` entries must be symbols",
                node=item,
                form=form,
            )
        if identifier.resolved_name in seen:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="procedure_type_param_duplicate",
                        message=f"duplicate procedure type parameter `{identifier.display_name}`",
                        span=identifier.span,
                        form_path=form.form_path,
                        expansion_stack=identifier.expansion_stack,
                    ),
                )
            )
        seen.add(identifier.resolved_name)
        type_params.append(
            ProcedureTypeParam(
                name=identifier.resolved_name,
                span=identifier.span,
                form_path=form.form_path,
                expansion_stack=identifier.expansion_stack,
            )
        )
    if not type_params:
        _raise_invalid_parametric_clause(
            "`defproc` `:forall` must declare at least one type parameter",
            node=raw_node,
            form=form,
        )
    return tuple(type_params)


def _elaborate_where_clauses(
    raw_node: object | None,
    *,
    form: SyntaxNode,
    declared_type_params: frozenset[str],
) -> tuple[ProcedureConstraintSyntax, ...]:
    if not isinstance(raw_node, SyntaxList):
        _raise_invalid_where_clause("`defproc` `:where` must be followed by a list of clauses", node=form, form=form)
    clauses: list[ProcedureConstraintSyntax] = []
    for clause in raw_node.items:
        if not isinstance(clause, SyntaxList) or len(clause.items) < 2:
            _raise_invalid_where_clause("`defproc` `:where` clauses must be lists of `(TypeParam constraint ...)`", node=clause, form=form)
        subject_identifier = syntax_identifier(clause.items[0])
        constraint_identifier = syntax_identifier(clause.items[1])
        if subject_identifier is None or constraint_identifier is None:
            _raise_invalid_where_clause("`defproc` `:where` clause subjects and constraints must be symbols", node=clause, form=form)
        if subject_identifier.resolved_name not in declared_type_params:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="procedure_type_param_unknown",
                        message=(
                            f"`:where` clause references undeclared procedure type parameter "
                            f"`{subject_identifier.display_name}`"
                        ),
                        span=subject_identifier.span,
                        form_path=form.form_path,
                        expansion_stack=subject_identifier.expansion_stack,
                    ),
                )
            )
        symbol_operands: list[ProcedureConstraintSymbolOperandSyntax] = []
        field_requirements: list[ProcedureConstraintFieldRequirementSyntax] = []
        for arg in clause.items[2:]:
            identifier = syntax_identifier(arg)
            if identifier is not None:
                symbol_operands.append(
                    ProcedureConstraintSymbolOperandSyntax(
                        symbol_name=identifier.resolved_name,
                        span=identifier.span,
                        form_path=form.form_path,
                        expansion_stack=identifier.expansion_stack,
                    )
                )
                continue
            if isinstance(arg, SyntaxList):
                field_requirements.append(_elaborate_where_field_requirement(arg, form=form))
                continue
            _raise_invalid_where_clause(
                "`defproc` `:where` clause arguments must be symbols or `(field Type)` pairs",
                node=arg,
                form=form,
            )
        _validate_constraint_operand_shapes(
            constraint_name=constraint_identifier.resolved_name,
            symbol_operands=tuple(symbol_operands),
            field_requirements=tuple(field_requirements),
            node=clause,
            form=form,
        )
        clauses.append(
            ProcedureConstraintSyntax(
                subject_name=subject_identifier.resolved_name,
                constraint_name=constraint_identifier.resolved_name,
                symbol_operands=tuple(symbol_operands),
                field_requirements=tuple(field_requirements),
                span=clause.span,
                form_path=form.form_path,
                expansion_stack=clause.expansion_stack,
            )
        )
    return tuple(clauses)


def _elaborate_where_field_requirement(
    raw_node: SyntaxList,
    *,
    form: SyntaxNode,
) -> ProcedureConstraintFieldRequirementSyntax:
    if len(raw_node.items) != 2:
        _raise_invalid_where_field_requirement(
            "`defproc` `:where` variant field requirements must be two-symbol `(field Type)` pairs",
            node=raw_node,
            form=form,
        )
    field_identifier = syntax_identifier(raw_node.items[0])
    type_identifier = syntax_identifier(raw_node.items[1])
    if field_identifier is None or type_identifier is None:
        _raise_invalid_where_field_requirement(
            "`defproc` `:where` variant field requirements must be two-symbol `(field Type)` pairs",
            node=raw_node,
            form=form,
        )
    return ProcedureConstraintFieldRequirementSyntax(
        field_name=field_identifier.resolved_name,
        field_type_name=type_identifier.resolved_name,
        span=raw_node.span,
        form_path=form.form_path,
        expansion_stack=raw_node.expansion_stack,
    )


def _validate_constraint_operand_shapes(
    *,
    constraint_name: str,
    symbol_operands: tuple[ProcedureConstraintSymbolOperandSyntax, ...],
    field_requirements: tuple[ProcedureConstraintFieldRequirementSyntax, ...],
    node: object,
    form: SyntaxNode,
) -> None:
    if constraint_name in {"is-record", "is-union"}:
        if symbol_operands or field_requirements:
            _raise_invalid_where_clause(
                f"`defproc` `:where` constraint `{constraint_name}` does not accept operands",
                node=node,
                form=form,
            )
        return
    if constraint_name in {"has-field", "has-shared-union-field"}:
        if len(symbol_operands) != 2 or field_requirements:
            _raise_invalid_where_clause(
                f"`defproc` `:where` constraint `{constraint_name}` expects exactly two symbol operands",
                node=node,
                form=form,
            )
        return
    if constraint_name == "has-union-variant":
        if len(symbol_operands) != 1:
            _raise_invalid_where_clause(
                "`defproc` `:where` constraint `has-union-variant` expects one variant symbol",
                node=node,
                form=form,
            )
        return
    if field_requirements:
        _raise_invalid_where_clause(
            f"`defproc` `:where` constraint `{constraint_name}` does not accept `(field Type)` requirements",
            node=node,
            form=form,
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


def _raise_invalid_parametric_clause(message: str, *, node: object, form: SyntaxNode) -> None:
    span = getattr(node, "span", form.span)
    expansion_stack = getattr(node, "expansion_stack", form.expansion_stack)
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="procedure_type_param_clause_invalid",
                message=message,
                span=span,
                form_path=form.form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )


def _raise_invalid_where_clause(message: str, *, node: object, form: SyntaxNode) -> None:
    span = getattr(node, "span", form.span)
    expansion_stack = getattr(node, "expansion_stack", form.expansion_stack)
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="procedure_where_clause_invalid",
                message=message,
                span=span,
                form_path=form.form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )


def _raise_invalid_where_field_requirement(message: str, *, node: object, form: SyntaxNode) -> None:
    span = getattr(node, "span", form.span)
    expansion_stack = getattr(node, "expansion_stack", form.expansion_stack)
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="procedure_where_field_requirement_invalid",
                message=message,
                span=span,
                form_path=form.form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )


def _keyword_value(node: object) -> str | None:
    return node.value if isinstance(node, SyntaxKeyword) else None


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
