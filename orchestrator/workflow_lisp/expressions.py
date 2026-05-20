"""Expression shaping for the Workflow Lisp MVP typed-expression tranche."""

from __future__ import annotations

from dataclasses import dataclass

from .parser import WorkflowLispSyntaxError
from .syntax import AtomKind, SourceSpan, SyntaxAtom, SyntaxDiagnostic, SyntaxList, SyntaxNode


@dataclass(frozen=True)
class LiteralExpression:
    """One literal expression node."""

    kind: AtomKind
    value: str | int | float | bool
    span: SourceSpan


@dataclass(frozen=True)
class ReferenceExpression:
    """One symbol reference expression node."""

    name: str
    span: SourceSpan


@dataclass(frozen=True)
class FieldAccessExpression:
    """One field access expression node."""

    base: "ExpressionNode"
    field_name: str
    span: SourceSpan


@dataclass(frozen=True)
class LetBindingExpression:
    """One named let* binding."""

    name: str
    name_span: SourceSpan
    value: "ExpressionNode"
    form_span: SourceSpan


@dataclass(frozen=True)
class RecordFieldExpression:
    """One record-constructor field assignment."""

    field_name: str
    field_span: SourceSpan
    value: "ExpressionNode"
    form_span: SourceSpan


@dataclass(frozen=True)
class RecordExpression:
    """One typed record-constructor expression."""

    type_name: str
    type_span: SourceSpan
    fields: tuple[RecordFieldExpression, ...]
    span: SourceSpan


@dataclass(frozen=True)
class CallArgumentExpression:
    """One keyword call argument assignment."""

    parameter_name: str
    keyword_span: SourceSpan
    value: "ExpressionNode"
    form_span: SourceSpan


@dataclass(frozen=True)
class CallExpression:
    """One workflow call expression."""

    callee_name: str
    callee_span: SourceSpan
    arguments: tuple[CallArgumentExpression, ...]
    returns_type_name: str | None
    returns_type_span: SourceSpan | None
    span: SourceSpan


@dataclass(frozen=True)
class LetStarExpression:
    """One let* expression."""

    bindings: tuple[LetBindingExpression, ...]
    body: "ExpressionNode"
    span: SourceSpan


@dataclass(frozen=True)
class WithPhaseExpression:
    """One with-phase expression wrapper."""

    context: "ExpressionNode"
    phase_name: str
    phase_span: SourceSpan
    body: "ExpressionNode"
    span: SourceSpan


@dataclass(frozen=True)
class PhaseTargetExpression:
    """One phase-target expression."""

    context: "ExpressionNode"
    target_name: str
    target_span: SourceSpan
    phase_name: str | None
    span: SourceSpan


@dataclass(frozen=True)
class MatchArmExpression:
    """One match arm binding one variant to one local name."""

    variant_name: str
    variant_span: SourceSpan
    binding_name: str
    binding_span: SourceSpan
    body: "ExpressionNode"
    span: SourceSpan


@dataclass(frozen=True)
class MatchExpression:
    """One match expression."""

    subject: "ExpressionNode"
    arms: tuple[MatchArmExpression, ...]
    partial: bool
    span: SourceSpan


@dataclass(frozen=True)
class ProviderResultExpression:
    """One provider-result expression."""

    provider_reference: ReferenceExpression
    prompt_reference: ReferenceExpression
    inputs: tuple["ExpressionNode", ...]
    returns_type_name: str
    returns_type_span: SourceSpan
    span: SourceSpan


@dataclass(frozen=True)
class CommandResultExpression:
    """One command-result expression."""

    command_name: str
    command_name_span: SourceSpan
    argv: tuple["ExpressionNode", ...]
    returns_type_name: str
    returns_type_span: SourceSpan
    span: SourceSpan


ExpressionNode = (
    LiteralExpression
    | ReferenceExpression
    | FieldAccessExpression
    | RecordExpression
    | CallExpression
    | LetStarExpression
    | WithPhaseExpression
    | PhaseTargetExpression
    | MatchExpression
    | ProviderResultExpression
    | CommandResultExpression
)


def _raise_expression_error(
    *,
    code: str,
    message: str,
    span: SourceSpan,
    enclosing_form_name: str | None = None,
    generated_core_node_id: str | None = None,
) -> None:
    raise WorkflowLispSyntaxError(
        SyntaxDiagnostic(
            code=code,
            message=message,
            span=span,
            source_file=span.source_file,
            line=span.line_start,
            column=span.column_start,
            enclosing_form_name=enclosing_form_name,
            generated_core_node_id=generated_core_node_id,
        )
    )


def _form_node_id_with_optional_symbol_suffix(
    *,
    base_node_id: str,
    form: SyntaxList,
    symbol_position: int,
) -> str:
    """Build a stable node id from a form, optionally suffixing a symbol value."""

    if len(form.items) <= symbol_position:
        return base_node_id
    symbol_node = form.items[symbol_position]
    if isinstance(symbol_node, SyntaxAtom) and symbol_node.kind is AtomKind.SYMBOL:
        return f"{base_node_id}.{symbol_node.value}"
    return base_node_id


def shape_expression(node: SyntaxNode) -> ExpressionNode:
    """Shape one syntax node into one MVP expression node."""

    if isinstance(node, SyntaxAtom):
        return _shape_atom_expression(node)
    if not node.items:
        _raise_expression_error(
            code="frontend_parse_error",
            message="Expression forms cannot be empty lists",
            span=node.span,
            generated_core_node_id="expression.unknown",
        )
    head = node.items[0]
    if not isinstance(head, SyntaxAtom) or head.kind is not AtomKind.SYMBOL:
        _raise_expression_error(
            code="frontend_parse_error",
            message="Expression form head must be a symbol",
            span=head.span,
            generated_core_node_id="expression.unknown",
        )
    if head.value == "let*":
        return _shape_let_star(node)
    if head.value == "with-phase":
        return _shape_with_phase(node)
    if head.value == "phase-target":
        return _shape_phase_target(node)
    if head.value == "record":
        return _shape_record(node)
    if head.value == "call":
        return _shape_call(node)
    if head.value == "match":
        return _shape_match(node)
    if head.value == "provider-result":
        return _shape_provider_result(node)
    if head.value == "command-result":
        return _shape_command_result(node)
    _raise_expression_error(
        code="frontend_parse_error",
        message=f"Unsupported expression form: {head.value}",
        span=head.span,
        enclosing_form_name=str(head.value),
        generated_core_node_id=f"expression.{head.value}",
    )


def _shape_atom_expression(node: SyntaxAtom) -> ExpressionNode:
    if node.kind in {
        AtomKind.STRING,
        AtomKind.QUOTED_SYMBOL,
        AtomKind.INT,
        AtomKind.FLOAT,
        AtomKind.BOOL,
        AtomKind.NIL,
    }:
        return LiteralExpression(kind=node.kind, value=node.value, span=node.span)
    if node.kind is not AtomKind.SYMBOL:
        _raise_expression_error(
            code="frontend_parse_error",
            message=f"Unsupported atom kind in expression: {node.kind.value}",
            span=node.span,
        )
    return _shape_symbol_expression(node)


def _shape_symbol_expression(node: SyntaxAtom) -> ExpressionNode:
    name = str(node.value)
    if "." not in name:
        return ReferenceExpression(name=name, span=node.span)
    segments = name.split(".")
    if any(not segment for segment in segments):
        _raise_expression_error(
            code="frontend_parse_error",
            message=f"Malformed field access reference: {name}",
            span=node.span,
        )
    current: ExpressionNode = ReferenceExpression(name=segments[0], span=node.span)
    for field_name in segments[1:]:
        current = FieldAccessExpression(base=current, field_name=field_name, span=node.span)
    return current


def _shape_let_star(form: SyntaxList) -> LetStarExpression:
    let_node_id = "expression.let-star"
    if len(form.items) != 3:
        _raise_expression_error(
            code="frontend_parse_error",
            message="let* requires a binding list and exactly one body expression",
            span=form.span,
            enclosing_form_name="let*",
            generated_core_node_id=let_node_id,
        )
    bindings_node = form.items[1]
    if not isinstance(bindings_node, SyntaxList):
        _raise_expression_error(
            code="frontend_parse_error",
            message="let* bindings must be a list",
            span=bindings_node.span,
            enclosing_form_name="let*",
            generated_core_node_id=let_node_id,
        )
    bindings: list[LetBindingExpression] = []
    seen_names: set[str] = set()
    for binding_node in bindings_node.items:
        if not isinstance(binding_node, SyntaxList) or len(binding_node.items) != 2:
            _raise_expression_error(
                code="frontend_parse_error",
                message="let* bindings must be (name expression) pairs",
                span=binding_node.span,
                enclosing_form_name="let*",
                generated_core_node_id=let_node_id,
            )
        name_node = binding_node.items[0]
        if not isinstance(name_node, SyntaxAtom) or name_node.kind is not AtomKind.SYMBOL:
            _raise_expression_error(
                code="frontend_parse_error",
                message="let* binding names must be symbols",
                span=name_node.span,
                enclosing_form_name="let*",
                generated_core_node_id=let_node_id,
            )
        name_text = str(name_node.value)
        if name_text in seen_names:
            _raise_expression_error(
                code="frontend_parse_error",
                message=f"Duplicate let* binding name: {name_text}",
                span=name_node.span,
                enclosing_form_name="let*",
                generated_core_node_id=let_node_id,
            )
        seen_names.add(name_text)
        bindings.append(
            LetBindingExpression(
                name=name_text,
                name_span=name_node.span,
                value=shape_expression(binding_node.items[1]),
                form_span=binding_node.span,
            )
        )
    return LetStarExpression(
        bindings=tuple(bindings),
        body=shape_expression(form.items[2]),
        span=form.span,
    )


def _shape_with_phase(form: SyntaxList) -> WithPhaseExpression:
    with_phase_node_id = _form_node_id_with_optional_symbol_suffix(
        base_node_id="expression.with-phase",
        form=form,
        symbol_position=2,
    )
    if len(form.items) != 4:
        _raise_expression_error(
            code="frontend_parse_error",
            message="with-phase requires context, phase name, and one body expression",
            span=form.span,
            enclosing_form_name="with-phase",
            generated_core_node_id=with_phase_node_id,
        )
    phase_node = form.items[2]
    if not isinstance(phase_node, SyntaxAtom) or phase_node.kind is not AtomKind.SYMBOL:
        _raise_expression_error(
            code="frontend_parse_error",
            message="with-phase phase name must be a symbol",
            span=phase_node.span,
            enclosing_form_name="with-phase",
            generated_core_node_id=with_phase_node_id,
        )
    return WithPhaseExpression(
        context=shape_expression(form.items[1]),
        phase_name=str(phase_node.value),
        phase_span=phase_node.span,
        body=shape_expression(form.items[3]),
        span=form.span,
    )


def _shape_phase_target(form: SyntaxList) -> PhaseTargetExpression:
    phase_target_node_id = "expression.phase-target"
    if len(form.items) == 4:
        phase_target_node_id = _form_node_id_with_optional_symbol_suffix(
            base_node_id=phase_target_node_id,
            form=form,
            symbol_position=3,
        )
    else:
        phase_target_node_id = _form_node_id_with_optional_symbol_suffix(
            base_node_id=phase_target_node_id,
            form=form,
            symbol_position=2,
        )
    if len(form.items) not in {3, 4}:
        _raise_expression_error(
            code="frontend_parse_error",
            message="phase-target requires context and target name, with optional phase name",
            span=form.span,
            enclosing_form_name="phase-target",
            generated_core_node_id=phase_target_node_id,
        )
    phase_name: str | None = None
    if len(form.items) == 4:
        phase_node = form.items[2]
        if not isinstance(phase_node, SyntaxAtom) or phase_node.kind is not AtomKind.SYMBOL:
            _raise_expression_error(
                code="frontend_parse_error",
                message="phase-target phase name must be a symbol",
                span=phase_node.span,
                enclosing_form_name="phase-target",
                generated_core_node_id=phase_target_node_id,
            )
        phase_name = str(phase_node.value)
        target_node = form.items[3]
    else:
        target_node = form.items[2]
    if not isinstance(target_node, SyntaxAtom) or target_node.kind is not AtomKind.SYMBOL:
        _raise_expression_error(
            code="frontend_parse_error",
            message="phase-target target name must be a symbol",
            span=target_node.span,
            enclosing_form_name="phase-target",
            generated_core_node_id=phase_target_node_id,
        )
    return PhaseTargetExpression(
        context=shape_expression(form.items[1]),
        target_name=str(target_node.value),
        target_span=target_node.span,
        phase_name=phase_name,
        span=form.span,
    )


def _shape_record(form: SyntaxList) -> RecordExpression:
    record_node_id = _form_node_id_with_optional_symbol_suffix(
        base_node_id="expression.record",
        form=form,
        symbol_position=1,
    )
    if len(form.items) < 4:
        _raise_expression_error(
            code="frontend_parse_error",
            message="record requires a type symbol and at least one field",
            span=form.span,
            enclosing_form_name="record",
            generated_core_node_id=record_node_id,
        )
    type_node = form.items[1]
    if not isinstance(type_node, SyntaxAtom) or type_node.kind is not AtomKind.SYMBOL:
        _raise_expression_error(
            code="frontend_parse_error",
            message="record type must be a symbol",
            span=type_node.span,
            enclosing_form_name="record",
            generated_core_node_id=record_node_id,
        )

    raw_fields = form.items[2:]
    if len(raw_fields) % 2 != 0:
        _raise_expression_error(
            code="frontend_parse_error",
            message="record fields must be keyword/expression pairs",
            span=form.span,
            enclosing_form_name="record",
            generated_core_node_id=record_node_id,
        )

    fields: list[RecordFieldExpression] = []
    seen_fields: set[str] = set()
    for index in range(0, len(raw_fields), 2):
        key_node = raw_fields[index]
        value_node = raw_fields[index + 1]
        if not isinstance(key_node, SyntaxAtom) or key_node.kind is not AtomKind.KEYWORD:
            _raise_expression_error(
                code="frontend_parse_error",
                message="record fields must be keyword/expression pairs",
                span=key_node.span,
                enclosing_form_name="record",
                generated_core_node_id=record_node_id,
            )
        field_name = str(key_node.value)[1:]
        if not field_name:
            _raise_expression_error(
                code="frontend_parse_error",
                message="record field keyword must not be empty",
                span=key_node.span,
                enclosing_form_name="record",
                generated_core_node_id=record_node_id,
            )
        if field_name in seen_fields:
            _raise_expression_error(
                code="frontend_parse_error",
                message=f"Duplicate record field: {field_name}",
                span=key_node.span,
                enclosing_form_name="record",
                generated_core_node_id=record_node_id,
            )
        seen_fields.add(field_name)
        fields.append(
            RecordFieldExpression(
                field_name=field_name,
                field_span=key_node.span,
                value=shape_expression(value_node),
                form_span=key_node.span,
            )
        )

    return RecordExpression(
        type_name=str(type_node.value),
        type_span=type_node.span,
        fields=tuple(fields),
        span=form.span,
    )


def _shape_call(form: SyntaxList) -> CallExpression:
    call_node_id = "expression.call"
    if len(form.items) >= 2:
        maybe_callee = form.items[1]
        if isinstance(maybe_callee, SyntaxAtom) and maybe_callee.kind is AtomKind.SYMBOL:
            call_node_id = f"expression.call.{maybe_callee.value}"

    if len(form.items) < 2:
        _raise_expression_error(
            code="frontend_parse_error",
            message="call requires a workflow symbol",
            span=form.span,
            enclosing_form_name="call",
            generated_core_node_id=call_node_id,
        )
    callee_node = form.items[1]
    if not isinstance(callee_node, SyntaxAtom) or callee_node.kind is not AtomKind.SYMBOL:
        _raise_expression_error(
            code="frontend_parse_error",
            message="call workflow reference must be a symbol",
            span=callee_node.span,
            enclosing_form_name="call",
            generated_core_node_id=call_node_id,
        )

    raw_arguments = form.items[2:]
    if len(raw_arguments) % 2 != 0:
        _raise_expression_error(
            code="frontend_parse_error",
            message="call arguments must be keyword/expression pairs",
            span=form.span,
            enclosing_form_name="call",
            generated_core_node_id=call_node_id,
        )

    arguments: list[CallArgumentExpression] = []
    returns_type_name: str | None = None
    returns_type_span: SourceSpan | None = None
    seen_parameters: set[str] = set()
    for index in range(0, len(raw_arguments), 2):
        key_node = raw_arguments[index]
        value_node = raw_arguments[index + 1]
        if not isinstance(key_node, SyntaxAtom) or key_node.kind is not AtomKind.KEYWORD:
            _raise_expression_error(
                code="frontend_parse_error",
                message="call arguments must be keyword/expression pairs",
                span=key_node.span,
                enclosing_form_name="call",
                generated_core_node_id=call_node_id,
            )
        parameter_name = str(key_node.value)[1:]
        if not parameter_name:
            _raise_expression_error(
                code="frontend_parse_error",
                message="call argument keywords must include a parameter name",
                span=key_node.span,
                enclosing_form_name="call",
                generated_core_node_id=call_node_id,
            )
        if parameter_name == "returns":
            if returns_type_name is not None:
                _raise_expression_error(
                    code="frontend_parse_error",
                    message="Duplicate call :returns clause",
                    span=key_node.span,
                    enclosing_form_name="call",
                    generated_core_node_id=call_node_id,
                )
            if not isinstance(value_node, SyntaxAtom) or value_node.kind is not AtomKind.SYMBOL:
                _raise_expression_error(
                    code="frontend_parse_error",
                    message="call :returns value must be a type symbol",
                    span=value_node.span,
                    enclosing_form_name="call",
                    generated_core_node_id=call_node_id,
                )
            returns_type_name = str(value_node.value)
            returns_type_span = value_node.span
            continue
        if parameter_name in seen_parameters:
            _raise_expression_error(
                code="frontend_parse_error",
                message=f"Duplicate call argument: {parameter_name}",
                span=key_node.span,
                enclosing_form_name="call",
                generated_core_node_id=call_node_id,
            )
        seen_parameters.add(parameter_name)
        arguments.append(
            CallArgumentExpression(
                parameter_name=parameter_name,
                keyword_span=key_node.span,
                value=shape_expression(value_node),
                form_span=key_node.span,
            )
        )

    return CallExpression(
        callee_name=str(callee_node.value),
        callee_span=callee_node.span,
        arguments=tuple(arguments),
        returns_type_name=returns_type_name,
        returns_type_span=returns_type_span,
        span=form.span,
    )


def _shape_match(form: SyntaxList) -> MatchExpression:
    match_node_id = "expression.match"
    if len(form.items) < 3:
        _raise_expression_error(
            code="frontend_parse_error",
            message="match requires a subject and at least one arm",
            span=form.span,
            enclosing_form_name="match",
            generated_core_node_id=match_node_id,
        )
    subject = shape_expression(form.items[1])
    partial = False
    arm_start_index = 2

    if len(form.items) >= 4:
        key_node = form.items[2]
        if isinstance(key_node, SyntaxAtom) and key_node.kind is AtomKind.KEYWORD:
            if str(key_node.value) != ":partial":
                _raise_expression_error(
                    code="frontend_parse_error",
                    message=f"Unsupported match clause: {key_node.value}",
                    span=key_node.span,
                    enclosing_form_name="match",
                    generated_core_node_id=match_node_id,
                )
            partial_node = form.items[3]
            if not isinstance(partial_node, SyntaxAtom) or partial_node.kind is not AtomKind.BOOL:
                _raise_expression_error(
                    code="frontend_parse_error",
                    message="match :partial value must be a boolean",
                    span=partial_node.span,
                    enclosing_form_name="match",
                    generated_core_node_id=match_node_id,
                )
            partial = bool(partial_node.value)
            arm_start_index = 4

    arms: list[MatchArmExpression] = []
    seen_variants: set[str] = set()
    for arm_node in form.items[arm_start_index:]:
        if not isinstance(arm_node, SyntaxList) or len(arm_node.items) != 2:
            _raise_expression_error(
                code="frontend_parse_error",
                message="match arms must have shape ((VARIANT binding) expression)",
                span=arm_node.span,
                enclosing_form_name="match",
                generated_core_node_id=match_node_id,
            )
        pattern_node = arm_node.items[0]
        if not isinstance(pattern_node, SyntaxList) or len(pattern_node.items) != 2:
            _raise_expression_error(
                code="frontend_parse_error",
                message="match arm pattern must have shape (VARIANT binding)",
                span=pattern_node.span,
                enclosing_form_name="match",
                generated_core_node_id=match_node_id,
            )
        variant_node = pattern_node.items[0]
        if not isinstance(variant_node, SyntaxAtom) or variant_node.kind is not AtomKind.SYMBOL:
            _raise_expression_error(
                code="frontend_parse_error",
                message="match arm variant names must be symbols",
                span=variant_node.span,
                enclosing_form_name="match",
                generated_core_node_id=match_node_id,
            )
        variant_name = str(variant_node.value)
        if variant_name in seen_variants:
            _raise_expression_error(
                code="frontend_parse_error",
                message=f"Duplicate match arm variant: {variant_name}",
                span=variant_node.span,
                enclosing_form_name="match",
                generated_core_node_id=match_node_id,
            )
        seen_variants.add(variant_name)
        binding_node = pattern_node.items[1]
        if not isinstance(binding_node, SyntaxAtom) or binding_node.kind is not AtomKind.SYMBOL:
            _raise_expression_error(
                code="frontend_parse_error",
                message="match arm binding names must be symbols",
                span=binding_node.span,
                enclosing_form_name="match",
                generated_core_node_id=match_node_id,
            )
        arms.append(
            MatchArmExpression(
                variant_name=variant_name,
                variant_span=variant_node.span,
                binding_name=str(binding_node.value),
                binding_span=binding_node.span,
                body=shape_expression(arm_node.items[1]),
                span=arm_node.span,
            )
        )
    return MatchExpression(subject=subject, arms=tuple(arms), partial=partial, span=form.span)


def _shape_provider_result(form: SyntaxList) -> ProviderResultExpression:
    provider_node_id = "expression.provider-result"
    if len(form.items) >= 2:
        maybe_provider = form.items[1]
        if isinstance(maybe_provider, SyntaxAtom) and maybe_provider.kind is AtomKind.SYMBOL:
            provider_node_id = f"expression.provider-result.{maybe_provider.value}"

    if len(form.items) < 8:
        _raise_expression_error(
            code="frontend_parse_error",
            message="provider-result requires provider, :prompt, :inputs, and :returns clauses",
            span=form.span,
            enclosing_form_name="provider-result",
            generated_core_node_id=provider_node_id,
        )
    provider_node = form.items[1]
    if not isinstance(provider_node, SyntaxAtom) or provider_node.kind is not AtomKind.SYMBOL:
        _raise_expression_error(
            code="frontend_parse_error",
            message="provider-result provider reference must be a symbol",
            span=provider_node.span,
            enclosing_form_name="provider-result",
            generated_core_node_id=provider_node_id,
        )
    clauses = form.items[2:]
    if len(clauses) % 2 != 0:
        _raise_expression_error(
            code="frontend_parse_error",
            message="provider-result clauses must be keyword/value pairs",
            span=form.span,
            enclosing_form_name="provider-result",
            generated_core_node_id=provider_node_id,
        )

    prompt_reference: ReferenceExpression | None = None
    inputs: tuple[ExpressionNode, ...] | None = None
    returns_type_name: str | None = None
    returns_type_span: SourceSpan | None = None
    seen_keys: set[str] = set()

    for index in range(0, len(clauses), 2):
        key_node = clauses[index]
        value_node = clauses[index + 1]
        if not isinstance(key_node, SyntaxAtom) or key_node.kind is not AtomKind.KEYWORD:
            _raise_expression_error(
                code="frontend_parse_error",
                message="provider-result clauses must be keyword/value pairs",
                span=key_node.span,
                enclosing_form_name="provider-result",
                generated_core_node_id=provider_node_id,
            )
        key_text = str(key_node.value)
        if key_text in seen_keys:
            _raise_expression_error(
                code="frontend_parse_error",
                message=f"Duplicate provider-result clause: {key_text}",
                span=key_node.span,
                enclosing_form_name="provider-result",
                generated_core_node_id=provider_node_id,
            )
        seen_keys.add(key_text)

        if key_text == ":prompt":
            prompt_expression = shape_expression(value_node)
            if not isinstance(prompt_expression, ReferenceExpression):
                _raise_expression_error(
                    code="frontend_parse_error",
                    message="provider-result :prompt value must be a symbol reference",
                    span=value_node.span,
                    enclosing_form_name="provider-result",
                    generated_core_node_id=provider_node_id,
                )
            prompt_reference = prompt_expression
            continue
        if key_text == ":inputs":
            if not isinstance(value_node, SyntaxList):
                _raise_expression_error(
                    code="frontend_parse_error",
                    message="provider-result :inputs value must be an expression list",
                    span=value_node.span,
                    enclosing_form_name="provider-result",
                    generated_core_node_id=provider_node_id,
                )
            inputs = tuple(shape_expression(item) for item in value_node.items)
            continue
        if key_text == ":returns":
            if not isinstance(value_node, SyntaxAtom) or value_node.kind is not AtomKind.SYMBOL:
                _raise_expression_error(
                    code="frontend_parse_error",
                    message="provider-result :returns value must be a type symbol",
                    span=value_node.span,
                    enclosing_form_name="provider-result",
                    generated_core_node_id=provider_node_id,
                )
            returns_type_name = str(value_node.value)
            returns_type_span = value_node.span
            continue
        _raise_expression_error(
            code="frontend_parse_error",
            message=f"Unsupported provider-result clause: {key_text}",
            span=key_node.span,
            enclosing_form_name="provider-result",
            generated_core_node_id=provider_node_id,
        )

    if prompt_reference is None or inputs is None or returns_type_name is None or returns_type_span is None:
        _raise_expression_error(
            code="frontend_parse_error",
            message="provider-result requires :prompt, :inputs, and :returns clauses",
            span=form.span,
            enclosing_form_name="provider-result",
            generated_core_node_id=provider_node_id,
        )

    return ProviderResultExpression(
        provider_reference=ReferenceExpression(name=str(provider_node.value), span=provider_node.span),
        prompt_reference=prompt_reference,
        inputs=inputs,
        returns_type_name=returns_type_name,
        returns_type_span=returns_type_span,
        span=form.span,
    )


def _shape_command_result(form: SyntaxList) -> CommandResultExpression:
    command_node_id = "expression.command-result"
    if len(form.items) >= 2:
        maybe_command = form.items[1]
        if isinstance(maybe_command, SyntaxAtom) and maybe_command.kind is AtomKind.SYMBOL:
            command_node_id = f"expression.command-result.{maybe_command.value}"

    if len(form.items) < 6:
        _raise_expression_error(
            code="frontend_parse_error",
            message="command-result requires command name, :argv, and :returns clauses",
            span=form.span,
            enclosing_form_name="command-result",
            generated_core_node_id=command_node_id,
        )
    command_node = form.items[1]
    if not isinstance(command_node, SyntaxAtom) or command_node.kind is not AtomKind.SYMBOL:
        _raise_expression_error(
            code="frontend_parse_error",
            message="command-result command name must be a symbol",
            span=command_node.span,
            enclosing_form_name="command-result",
            generated_core_node_id=command_node_id,
        )

    clauses = form.items[2:]
    if len(clauses) % 2 != 0:
        _raise_expression_error(
            code="frontend_parse_error",
            message="command-result clauses must be keyword/value pairs",
            span=form.span,
            enclosing_form_name="command-result",
            generated_core_node_id=command_node_id,
        )

    argv: tuple[ExpressionNode, ...] | None = None
    returns_type_name: str | None = None
    returns_type_span: SourceSpan | None = None
    seen_keys: set[str] = set()

    for index in range(0, len(clauses), 2):
        key_node = clauses[index]
        value_node = clauses[index + 1]
        if not isinstance(key_node, SyntaxAtom) or key_node.kind is not AtomKind.KEYWORD:
            _raise_expression_error(
                code="frontend_parse_error",
                message="command-result clauses must be keyword/value pairs",
                span=key_node.span,
                enclosing_form_name="command-result",
                generated_core_node_id=command_node_id,
            )
        key_text = str(key_node.value)
        if key_text in seen_keys:
            _raise_expression_error(
                code="frontend_parse_error",
                message=f"Duplicate command-result clause: {key_text}",
                span=key_node.span,
                enclosing_form_name="command-result",
                generated_core_node_id=command_node_id,
            )
        seen_keys.add(key_text)

        if key_text == ":argv":
            if not isinstance(value_node, SyntaxList):
                _raise_expression_error(
                    code="frontend_parse_error",
                    message="command-result :argv value must be an expression list",
                    span=value_node.span,
                    enclosing_form_name="command-result",
                    generated_core_node_id=command_node_id,
                )
            argv = tuple(shape_expression(item) for item in value_node.items)
            continue
        if key_text == ":returns":
            if not isinstance(value_node, SyntaxAtom) or value_node.kind is not AtomKind.SYMBOL:
                _raise_expression_error(
                    code="frontend_parse_error",
                    message="command-result :returns value must be a type symbol",
                    span=value_node.span,
                    enclosing_form_name="command-result",
                    generated_core_node_id=command_node_id,
                )
            returns_type_name = str(value_node.value)
            returns_type_span = value_node.span
            continue
        _raise_expression_error(
            code="frontend_parse_error",
            message=f"Unsupported command-result clause: {key_text}",
            span=key_node.span,
            enclosing_form_name="command-result",
            generated_core_node_id=command_node_id,
        )

    if argv is None or returns_type_name is None or returns_type_span is None:
        _raise_expression_error(
            code="frontend_parse_error",
            message="command-result requires :argv and :returns clauses",
            span=form.span,
            enclosing_form_name="command-result",
            generated_core_node_id=command_node_id,
        )

    return CommandResultExpression(
        command_name=str(command_node.value),
        command_name_span=command_node.span,
        argv=argv,
        returns_type_name=returns_type_name,
        returns_type_span=returns_type_span,
        span=form.span,
    )
