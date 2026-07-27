"""Compile-time prompt declaration models and syntax validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import NoReturn

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .result_guidance import ReturnSpec, parse_return_spec
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
