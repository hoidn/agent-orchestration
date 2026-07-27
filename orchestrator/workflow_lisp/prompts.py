"""Compile-time prompt declaration models and syntax validation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Any, NoReturn

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .result_guidance import (
    ReturnSpec,
    normalized_result_guidance_payload,
    parse_return_spec,
    validate_result_guidance_example,
)
from .spans import SourceSpan
from .syntax import (
    ExpansionStack,
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    WorkflowLispSyntaxModule,
    syntax_expansion_stack,
    syntax_head,
    syntax_head_name,
    syntax_identifier,
    syntax_node_datum,
    target_dsl_supports_prompt_calculus,
)


_PLACEHOLDER_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_COMPILED_IDENTITY_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class PromptSlotKind(str, Enum):
    """Closed Q1 delivery-kind inventory."""

    DOC = "doc"
    TEXT = "text"
    VALUE = "value"
    PATH = "path"


@dataclass(frozen=True)
class PromptSlot:
    """One authored prompt slot in declaration order."""

    name: str
    kind: PromptSlotKind
    refinement_type_name: str | None
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PromptTemplate:
    """One exact decoded template and its left-to-right placeholders."""

    text: str
    placeholder_names: tuple[str, ...]
    span: SourceSpan


@dataclass(frozen=True)
class PromptDef:
    """One immutable target-2.20 prompt declaration."""

    name: str
    slots: tuple[PromptSlot, ...]
    return_spec: ReturnSpec
    template: PromptTemplate
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()

    @property
    def return_type_name(self) -> str:
        """Expose the canonical return type without duplicating authority."""

        return self.return_spec.type_name


@dataclass(frozen=True)
class ResolvedPromptSlot:
    """One declaration slot with its optional refinement resolved."""

    declaration: PromptSlot
    refinement_type_ref: object | None


@dataclass(frozen=True)
class ResolvedPromptDef:
    """One prompt declaration after module and type resolution."""

    qualified_name: str
    declaration: PromptDef
    slots: tuple[ResolvedPromptSlot, ...]
    return_type_ref: object


@dataclass(frozen=True)
class PromptFill:
    """One named fragment application fill in declaration order."""

    name: str
    value_expr: object
    span: SourceSpan
    static_type_ref: object | None = None
    renderer_id: str | None = None
    typed_expression_identity: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class PromptApplicationExpr:
    """One direct, fully applied compile-time prompt application."""

    prompt: ResolvedPromptDef
    fills: tuple[PromptFill, ...]
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    canonical_identity_projection: Mapping[str, Any] | None = None
    compiled_prompt_fragment_identity: str | None = None
    return_redeclaration_span: SourceSpan | None = None
    return_redeclaration_expansion_stack: ExpansionStack = ()


@dataclass(frozen=True)
class PromptCatalog:
    """Visible prompt definitions in their distinct compile-time namespace."""

    definitions_by_name: Mapping[str, ResolvedPromptDef]

    def resolve(self, name: str) -> ResolvedPromptDef | None:
        """Resolve one local, imported, alias-qualified, or canonical name."""

        return self.definitions_by_name.get(name)


def build_prompt_catalog(
    module_name: str,
    definitions: tuple[PromptDef, ...],
    *,
    type_env,
    imported_definitions: Mapping[str, ResolvedPromptDef] | None = None,
    lookup_aliases: Mapping[str, str] | None = None,
) -> PromptCatalog:
    """Resolve declarations once and build a distinct prompt lookup table."""

    visible: dict[str, ResolvedPromptDef] = dict(imported_definitions or {})
    local_names: set[str] = set()
    for definition in definitions:
        if definition.name in local_names:
            _raise_prompt_error(
                "definition_duplicate",
                f"duplicate prompt definition `{definition.name}`",
                node=definition,
                form_path=definition.form_path,
            )
        local_names.add(definition.name)
        resolved_slots = tuple(
            ResolvedPromptSlot(
                declaration=slot,
                refinement_type_ref=(
                    type_env.resolve_type(
                        slot.refinement_type_name,
                        span=slot.span,
                        form_path=slot.form_path,
                        expansion_stack=slot.expansion_stack,
                    )
                    if slot.refinement_type_name is not None
                    else None
                ),
            )
            for slot in definition.slots
        )
        for resolved_slot in resolved_slots:
            if (
                resolved_slot.refinement_type_ref is not None
                and not _refinement_is_admissible(resolved_slot)
            ):
                slot = resolved_slot.declaration
                _raise_prompt_error(
                    "prompt_slot_refinement_invalid",
                    (
                        f"refinement `{slot.refinement_type_name}` is not "
                        f"admissible for `:{slot.kind.value}`"
                    ),
                    node=slot,
                    form_path=slot.form_path,
                )
        return_type = type_env.resolve_type(
            definition.return_type_name,
            span=definition.return_spec.span,
            form_path=definition.form_path,
            expansion_stack=definition.expansion_stack,
        )
        validate_result_guidance_example(
            definition.return_spec.guidance,
            expected_type=return_type,
            type_env=type_env,
        )
        qualified_name = f"{module_name}::{definition.name}"
        resolved = ResolvedPromptDef(
            qualified_name=qualified_name,
            declaration=definition,
            slots=resolved_slots,
            return_type_ref=return_type,
        )
        visible[definition.name] = resolved
        visible[qualified_name] = resolved
    for alias, canonical_name in (lookup_aliases or {}).items():
        resolved = visible.get(canonical_name)
        if resolved is not None:
            visible[alias] = resolved
    return PromptCatalog(definitions_by_name=visible)


def elaborate_prompt_application(
    node: object,
    *,
    catalog: PromptCatalog,
    elaborate_fill: Callable[[object], object],
    form_path: tuple[str, ...],
    return_redeclaration_node: object | None = None,
) -> PromptApplicationExpr:
    """Parse one prompt application after its provider-position is known."""

    if not isinstance(node, SyntaxList):
        _raise_prompt_error(
            "prompt_partial_application_unsupported",
            "a prompt must be directly and fully applied in provider prompt position",
            node=node,
            form_path=form_path,
        )
    head = syntax_head(node)
    if head is None:
        _raise_prompt_error(
            "prompt_partial_application_unsupported",
            "a prompt application must start with a prompt name",
            node=node,
            form_path=form_path,
        )
    resolved = catalog.resolve(head.resolved_name)
    if resolved is None:
        _raise_prompt_error(
            "module_export_missing",
            f"prompt `{head.display_name}` is not visible in this module",
            node=head,
            form_path=form_path,
        )
    tail = node.items[1:]
    if len(tail) % 2:
        _raise_prompt_error(
            "prompt_partial_application_unsupported",
            "prompt fills must be complete keyword/value pairs",
            node=node,
            form_path=form_path,
        )
    declared_by_name = {
        slot.declaration.name: slot
        for slot in resolved.slots
    }
    authored: dict[str, PromptFill] = {}
    for index in range(0, len(tail), 2):
        keyword = tail[index]
        value = tail[index + 1]
        if not isinstance(keyword, SyntaxKeyword):
            _raise_prompt_error(
                "prompt_fill_unknown",
                "prompt fills must use declared slot keywords",
                node=keyword,
                form_path=form_path,
            )
        fill_name = keyword.value.removeprefix(":")
        if fill_name in authored:
            _raise_prompt_error(
                "prompt_fill_duplicate",
                f"duplicate prompt fill `{keyword.value}`",
                node=keyword,
                form_path=form_path,
            )
        if fill_name not in declared_by_name:
            _raise_prompt_error(
                "prompt_fill_unknown",
                f"unknown prompt fill `{keyword.value}`",
                node=keyword,
                form_path=form_path,
            )
        nested_head = syntax_head(value) if isinstance(value, SyntaxList) else None
        if (
            nested_head is not None
            and catalog.resolve(nested_head.resolved_name) is not None
        ):
            _raise_prompt_error(
                "prompt_fill_identity_unsupported",
                "nested prompt applications are not admitted as Q1 fills",
                node=value,
                form_path=form_path,
            )
        value_expr = elaborate_fill(value)
        authored[fill_name] = PromptFill(
            name=fill_name,
            value_expr=value_expr,
            span=value.span,
        )
    missing = tuple(
        slot.declaration.name
        for slot in resolved.slots
        if slot.declaration.name not in authored
    )
    if missing:
        _raise_prompt_error(
            "prompt_slot_undischarged",
            f"prompt application is missing fills: {', '.join(missing)}",
            node=node,
            form_path=form_path,
        )
    return PromptApplicationExpr(
        prompt=resolved,
        fills=tuple(
            authored[slot.declaration.name]
            for slot in resolved.slots
        ),
        span=node.span,
        form_path=form_path,
        expansion_stack=node.expansion_stack,
        return_redeclaration_span=(
            getattr(return_redeclaration_node, "span", None)
            if return_redeclaration_node is not None
            else None
        ),
        return_redeclaration_expansion_stack=(
            getattr(return_redeclaration_node, "expansion_stack", ())
            if return_redeclaration_node is not None
            else ()
        ),
    )


def typecheck_prompt_application(
    application: PromptApplicationExpr,
    *,
    recurse: Callable[[object], object],
    type_env,
) -> tuple[PromptApplicationExpr, tuple[object, ...]]:
    """Typecheck fills, select renderers, and construct the closed identity."""

    from .type_env import type_refs_compatible

    typed_fills: list[PromptFill] = []
    effects: list[object] = []
    for slot, fill in zip(
        application.prompt.slots,
        application.fills,
        strict=True,
    ):
        typed = recurse(fill.value_expr)
        effects.append(typed.effect_summary)
        renderer_id = _renderer_for_fill(
            slot,
            typed.type_ref,
            fill=fill,
        )
        if (
            slot.refinement_type_ref is not None
            and not type_refs_compatible(
                slot.refinement_type_ref,
                typed.type_ref,
            )
        ):
            _raise_prompt_error(
                "prompt_slot_type_mismatch",
                (
                    f"prompt fill `{fill.name}` does not satisfy its "
                    "declared refinement"
                ),
                node=fill,
                form_path=application.form_path,
            )
        typed_fills.append(
            replace(
                fill,
                static_type_ref=typed.type_ref,
                renderer_id=renderer_id,
                typed_expression_identity=_typed_expression_identity(
                    fill.value_expr,
                    static_type=typed.type_ref,
                    type_env=type_env,
                ),
            )
        )
    projection = _compiled_identity_projection(
        application.prompt,
        tuple(typed_fills),
        type_env=type_env,
    )
    identity = _identity_for_projection(projection)
    return (
        replace(
            application,
            fills=tuple(typed_fills),
            canonical_identity_projection=projection,
            compiled_prompt_fragment_identity=identity,
        ),
        tuple(effects),
    )


def validate_compiled_prompt_fragment_identity(
    identity: str | None,
    *,
    canonical_projection: Mapping[str, Any] | None = None,
) -> None:
    """Fail closed on malformed or projection-mismatched Q1 identities."""

    if not isinstance(identity, str) or not _COMPILED_IDENTITY_RE.fullmatch(
        identity
    ):
        _raise_identity_error(
            "compiled_prompt_fragment_identity_invalid",
            "compiled prompt fragment identity is malformed",
        )
    if (
        canonical_projection is not None
        and _identity_for_projection(canonical_projection) != identity
    ):
        _raise_identity_error(
            "compiled_prompt_fragment_identity_invalid",
            "compiled prompt fragment identity does not match its projection",
        )


def _refinement_is_admissible(slot: ResolvedPromptSlot) -> bool:
    from .type_env import PathTypeRef
    from .typed_prompt_inputs import select_prompt_fragment_renderer

    type_ref = slot.refinement_type_ref
    kind = slot.declaration.kind
    if kind is PromptSlotKind.DOC:
        return (
            isinstance(type_ref, PathTypeRef)
            and type_ref.definition.kind == "relpath"
            and type_ref.definition.must_exist
        )
    if kind is PromptSlotKind.TEXT:
        return False
    if kind is PromptSlotKind.PATH:
        return (
            isinstance(type_ref, PathTypeRef)
            and select_prompt_fragment_renderer(type_ref, kind="path")
            == "posix-path-line"
        )
    return (
        select_prompt_fragment_renderer(type_ref, kind="value")
        == "canonical-json"
    )


def _renderer_for_fill(
    slot: ResolvedPromptSlot,
    type_ref: object,
    *,
    fill: PromptFill,
) -> str:
    from .type_env import PathTypeRef, PrimitiveTypeRef
    from .typed_prompt_inputs import select_prompt_fragment_renderer

    kind = slot.declaration.kind
    if kind is PromptSlotKind.DOC:
        if not (
            isinstance(type_ref, PathTypeRef)
            and type_ref.definition.kind == "relpath"
            and type_ref.definition.must_exist
        ):
            _raise_prompt_error(
                "prompt_slot_type_mismatch",
                f"document fill `{fill.name}` requires an existing relpath type",
                node=fill,
                form_path=slot.declaration.form_path,
            )
        return "required-document"
    if kind is PromptSlotKind.TEXT:
        if type_ref != PrimitiveTypeRef(name="String"):
            _raise_prompt_error(
                "prompt_slot_type_mismatch",
                f"text fill `{fill.name}` requires exact `String`",
                node=fill,
                form_path=slot.declaration.form_path,
            )
        return "raw-utf8-string"
    renderer_id = select_prompt_fragment_renderer(
        type_ref,
        kind=kind.value,
    )
    if renderer_id is None:
        _raise_prompt_error(
            "prompt_fill_renderer_unsupported",
            f"prompt fill `{fill.name}` has no unique `:{kind.value}` renderer",
            node=fill,
            form_path=slot.declaration.form_path,
        )
    return renderer_id


def _typed_expression_identity(
    expr: object,
    *,
    static_type: object,
    type_env,
) -> dict[str, Any]:
    from .expressions import FieldAccessExpr, LiteralExpr, NameExpr

    static_descriptor = _normalized_type_descriptor(
        static_type,
        type_env=type_env,
    )
    if isinstance(expr, LiteralExpr):
        return {
            "kind": "literal",
            "literal_kind": expr.literal_kind,
            "static_type": static_descriptor,
            "value": expr.value,
        }
    if isinstance(expr, NameExpr):
        return {
            "binding_path": [expr.name],
            "kind": "binding_path",
            "static_type": static_descriptor,
        }
    if isinstance(expr, FieldAccessExpr) and isinstance(expr.base, NameExpr):
        return {
            "binding_path": [expr.base.name, *expr.fields],
            "kind": "binding_path",
            "static_type": static_descriptor,
        }
    _raise_prompt_error(
        "prompt_fill_identity_unsupported",
        "prompt fill expression is outside the closed identity grammar",
        node=expr,
        form_path=getattr(expr, "form_path", ()),
    )


def _compiled_identity_projection(
    prompt: ResolvedPromptDef,
    fills: tuple[PromptFill, ...],
    *,
    type_env,
) -> dict[str, Any]:
    return_spec = prompt.declaration.return_spec
    return {
        "schema_version": "compiled_prompt_fragment_identity.v1",
        "referenced_declarations": [
            {
                "qualified_name": prompt.qualified_name,
                "template_utf8": prompt.declaration.template.text,
                "slots": [
                    {
                        "name": slot.declaration.name,
                        "kind": slot.declaration.kind.value,
                        "refinement": (
                            None
                            if slot.refinement_type_ref is None
                            else _normalized_type_descriptor(
                                slot.refinement_type_ref,
                                type_env=type_env,
                            )
                        ),
                        "placeholder_policy": (
                            "forbidden"
                            if slot.declaration.kind is PromptSlotKind.DOC
                            else "required_repetition_allowed"
                        ),
                    }
                    for slot in prompt.slots
                ],
                "return_spec": {
                    "type": _normalized_type_descriptor(
                        prompt.return_type_ref,
                        type_env=type_env,
                    ),
                    "guidance": normalized_result_guidance_payload(
                        return_spec.guidance,
                        expected_type=prompt.return_type_ref,
                        type_env=type_env,
                    ),
                },
            }
        ],
        "fully_applied_bindings": [
            {
                "slot": fill.name,
                "typed_expression_identity": fill.typed_expression_identity,
            }
            for fill in fills
        ],
    }


def _normalized_type_descriptor(type_ref: object, *, type_env) -> dict[str, Any]:
    # This is the existing compiler descriptor used by pure projection and
    # transition lowering. Q1 consumes it; it does not invent a parallel type
    # spelling or fall back to repr/source text.
    from .lowering.pure_projection import _type_descriptor

    return _type_descriptor(type_ref, type_env=type_env)


def _identity_for_projection(projection: Mapping[str, Any]) -> str:
    payload = json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{sha256(payload).hexdigest()}"


def _raise_identity_error(code: str, message: str) -> NoReturn:
    from .spans import SourcePosition

    span = SourceSpan(
        start=SourcePosition(
            path="<compiled-prompt-fragment-identity>",
            line=1,
            column=1,
            offset=0,
        ),
        end=SourcePosition(
            path="<compiled-prompt-fragment-identity>",
            line=1,
            column=1,
            offset=0,
        ),
    )
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=("workflow-lisp", "provider-result", ":prompt"),
            ),
        )
    )


def elaborate_prompt_definitions(
    module: WorkflowLispSyntaxModule,
) -> tuple[PromptDef, ...]:
    """Parse local ``defprompt`` forms without resolving their namespace."""

    definitions: list[PromptDef] = []
    for form in module.forms:
        datum = syntax_node_datum(form)
        if syntax_head_name(datum) != "defprompt":
            continue
        if not target_dsl_supports_prompt_calculus(
            module.target_dsl_version
        ):
            head = syntax_head(datum)
            _raise_prompt_error(
                "prompt_calculus_requires_dsl_2_20",
                "`defprompt` requires target DSL 2.20 or later",
                node=head if head is not None else form,
                form_path=form.form_path,
            )
        definitions.append(_elaborate_prompt_definition(form, datum))
    return tuple(definitions)


def _elaborate_prompt_definition(
    form: SyntaxNode,
    datum: object,
) -> PromptDef:
    if not isinstance(datum, SyntaxList) or len(datum.items) < 4:
        _raise_prompt_error(
            "frontend_parse_error",
            "`defprompt` requires a name, `:fills`, and a template",
            node=form,
            form_path=form.form_path,
        )
    name = syntax_identifier(datum.items[1])
    if name is None:
        _raise_prompt_error(
            "frontend_parse_error",
            "`defprompt` name must be a symbol",
            node=datum.items[1],
            form_path=form.form_path,
        )
    slots = _parse_slots(datum.items[2], form=form)
    tail = datum.items[3:]
    if len(tail) == 1:
        return_spec = ReturnSpec(
            type_name="Value",
            guidance=None,
            span=form.span,
        )
        template_node = tail[0]
    elif len(tail) == 3:
        arrow = syntax_identifier(tail[0])
        if arrow is None or arrow.resolved_name != "->":
            _raise_prompt_error(
                "frontend_parse_error",
                "prompt return separator must be `->`",
                node=tail[0],
                form_path=form.form_path,
            )
        return_spec = parse_return_spec(
            tail[1],
            form_path=form.form_path,
            label="prompt return type",
        )
        template_node = tail[2]
    else:
        _raise_prompt_error(
            "frontend_parse_error",
            "`defprompt` accepts one optional return contract and one template",
            node=form,
            form_path=form.form_path,
        )
    if not isinstance(template_node, SyntaxString):
        _raise_prompt_error(
            "frontend_parse_error",
            "`defprompt` template must be a string",
            node=template_node,
            form_path=form.form_path,
        )
    placeholder_names = _scan_placeholder_names(
        template_node,
        form_path=form.form_path,
    )
    _validate_placeholder_contract(
        slots,
        placeholder_names,
        template_node=template_node,
        form_path=form.form_path,
    )
    return PromptDef(
        name=name.resolved_name,
        slots=slots,
        return_spec=return_spec,
        template=PromptTemplate(
            text=template_node.value,
            placeholder_names=placeholder_names,
            span=template_node.span,
        ),
        span=form.span,
        form_path=form.form_path,
        expansion_stack=syntax_expansion_stack(datum),
    )


def _parse_slots(
    node: object,
    *,
    form: SyntaxNode,
) -> tuple[PromptSlot, ...]:
    if (
        not isinstance(node, SyntaxList)
        or not node.items
        or not isinstance(node.items[0], SyntaxKeyword)
        or node.items[0].value != ":fills"
    ):
        _raise_prompt_error(
            "frontend_parse_error",
            "`defprompt` requires one `(:fills ...)` clause",
            node=node,
            form_path=form.form_path,
        )
    slots: list[PromptSlot] = []
    seen: set[str] = set()
    for raw_slot in node.items[1:]:
        if not isinstance(raw_slot, SyntaxList) or len(raw_slot.items) not in {
            2,
            3,
        }:
            _raise_prompt_error(
                "frontend_parse_error",
                "prompt slots require `(name :kind [Type])`",
                node=raw_slot,
                form_path=form.form_path,
            )
        name = syntax_identifier(raw_slot.items[0])
        if name is None:
            _raise_prompt_error(
                "frontend_parse_error",
                "prompt slot name must be a symbol",
                node=raw_slot.items[0],
                form_path=form.form_path,
            )
        kind_node = raw_slot.items[1]
        if not isinstance(kind_node, SyntaxKeyword):
            _raise_prompt_error(
                "prompt_slot_kind_unknown",
                "prompt slot kind must be one of `:doc`, `:text`, `:value`, or `:path`",
                node=kind_node,
                form_path=form.form_path,
            )
        try:
            kind = PromptSlotKind(kind_node.value.removeprefix(":"))
        except ValueError as error:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="prompt_slot_kind_unknown",
                        message=f"unknown prompt slot kind `{kind_node.value}`",
                        span=kind_node.span,
                        form_path=form.form_path,
                        expansion_stack=kind_node.expansion_stack,
                    ),
                )
            ) from error
        if name.resolved_name in seen:
            _raise_prompt_error(
                "prompt_slot_duplicate",
                f"duplicate prompt slot `{name.display_name}`",
                node=raw_slot,
                form_path=form.form_path,
            )
        seen.add(name.resolved_name)
        refinement_type_name: str | None = None
        if len(raw_slot.items) == 3:
            refinement = syntax_identifier(raw_slot.items[2])
            if refinement is None:
                _raise_prompt_error(
                    "prompt_slot_refinement_invalid",
                    "prompt slot refinement must be a type name",
                    node=raw_slot.items[2],
                    form_path=form.form_path,
                )
            if kind is PromptSlotKind.TEXT:
                _raise_prompt_error(
                    "prompt_slot_refinement_invalid",
                    "`:text` prompt slots do not accept a refinement",
                    node=raw_slot.items[2],
                    form_path=form.form_path,
                )
            refinement_type_name = refinement.resolved_name
        slots.append(
            PromptSlot(
                name=name.resolved_name,
                kind=kind,
                refinement_type_name=refinement_type_name,
                span=raw_slot.span,
                form_path=form.form_path,
                expansion_stack=raw_slot.expansion_stack,
            )
        )
    return tuple(slots)


def _scan_placeholder_names(
    template: SyntaxString,
    *,
    form_path: tuple[str, ...],
) -> tuple[str, ...]:
    names: list[str] = []
    text = template.value
    index = 0
    while index < len(text):
        char = text[index]
        if char == "{":
            if index + 1 < len(text) and text[index + 1] == "{":
                index += 2
                continue
            closing = text.find("}", index + 1)
            if closing < 0:
                _raise_placeholder_syntax(template, form_path=form_path)
            name = text[index + 1 : closing]
            if not _PLACEHOLDER_NAME_RE.fullmatch(name):
                _raise_placeholder_syntax(template, form_path=form_path)
            names.append(name)
            index = closing + 1
            continue
        if char == "}":
            if index + 1 < len(text) and text[index + 1] == "}":
                index += 2
                continue
            _raise_placeholder_syntax(template, form_path=form_path)
        index += 1
    return tuple(names)


def _validate_placeholder_contract(
    slots: tuple[PromptSlot, ...],
    placeholder_names: tuple[str, ...],
    *,
    template_node: SyntaxString,
    form_path: tuple[str, ...],
) -> None:
    slots_by_name = {slot.name: slot for slot in slots}
    for placeholder_name in placeholder_names:
        slot = slots_by_name.get(placeholder_name)
        if slot is None:
            _raise_prompt_error(
                "prompt_placeholder_undeclared",
                f"prompt placeholder `{placeholder_name}` has no declared slot",
                node=template_node,
                form_path=form_path,
            )
        if slot.kind is PromptSlotKind.DOC:
            _raise_prompt_error(
                "prompt_doc_placeholder_forbidden",
                (
                    f"document slot `{placeholder_name}` cannot be rendered "
                    "inside a prompt template"
                ),
                node=template_node,
                form_path=form_path,
            )
    present = frozenset(placeholder_names)
    for slot in slots:
        if slot.kind is not PromptSlotKind.DOC and slot.name not in present:
            _raise_prompt_error(
                "prompt_placeholder_missing",
                f"rendered prompt slot `{slot.name}` has no placeholder",
                node=slot,
                form_path=form_path,
            )


def _raise_placeholder_syntax(
    template: SyntaxString,
    *,
    form_path: tuple[str, ...],
) -> NoReturn:
    _raise_prompt_error(
        "prompt_placeholder_syntax_invalid",
        "prompt template contains invalid placeholder syntax",
        node=template,
        form_path=form_path,
    )


def _raise_prompt_error(
    code: str,
    message: str,
    *,
    node: object,
    form_path: tuple[str, ...],
) -> NoReturn:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=node.span,
                form_path=form_path,
                expansion_stack=getattr(node, "expansion_stack", ()),
            ),
        )
    )
