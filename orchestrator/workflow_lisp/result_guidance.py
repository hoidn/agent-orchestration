"""Immutable authored metadata for typed Workflow Lisp result occurrences."""

from __future__ import annotations

from dataclasses import dataclass, field

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .syntax import (
    SyntaxKeyword,
    SyntaxList,
    SyntaxNode,
    SyntaxString,
    syntax_head,
    syntax_identifier,
)


@dataclass(frozen=True)
class ResultGuidance:
    """Optional provider-facing guidance attached to one result occurrence."""

    description: str | None = None
    format_hint: str | None = None
    example_expr: SyntaxNode | None = None


@dataclass(frozen=True)
class ReturnSpec:
    """One return type occurrence plus its optional authored guidance."""

    type_name: str
    guidance: ResultGuidance | None = field(compare=False)
    span: SourceSpan = field(compare=False)


def parse_return_spec(
    raw_return: object,
    *,
    form_path: tuple[str, ...],
    label: str,
) -> ReturnSpec:
    """Parse a plain type symbol or return-position ``(result T ...)`` form."""

    return_identifier = syntax_identifier(raw_return)
    if return_identifier is not None:
        return ReturnSpec(return_identifier.resolved_name, None, return_identifier.span)
    if not isinstance(raw_return, SyntaxList):
        _raise_guidance_error(
            f"{label} must be a symbol or `(result Type ...)`",
            node=raw_return,
            form_path=form_path,
        )
    head = syntax_head(raw_return)
    if head is None or head.resolved_name != "result" or len(raw_return.items) < 2:
        _raise_guidance_error(
            f"{label} must be a symbol or `(result Type ...)`",
            node=raw_return,
            form_path=form_path,
        )
    type_identifier = syntax_identifier(raw_return.items[1])
    if type_identifier is None:
        _raise_guidance_error(
            "`result` type must be a symbol",
            node=raw_return.items[1],
            form_path=form_path,
        )
    guidance = parse_result_guidance(
        raw_return.items[2:],
        form_path=form_path,
        label="`result`",
    )
    return ReturnSpec(type_identifier.resolved_name, guidance, raw_return.span)


def parse_result_guidance(
    items: tuple[object, ...],
    *,
    form_path: tuple[str, ...],
    label: str,
) -> ResultGuidance | None:
    """Parse the closed guidance-key set without validating example semantics."""

    if not items:
        return None
    if len(items) % 2 != 0:
        _raise_guidance_error(
            f"{label} guidance requires keyword/value pairs",
            node=items[-1],
            form_path=form_path,
        )
    values: dict[str, object] = {}
    for index in range(0, len(items), 2):
        keyword_node = items[index]
        value_node = items[index + 1]
        if not isinstance(keyword_node, SyntaxKeyword):
            _raise_guidance_error(
                f"{label} guidance entries must start with keywords",
                node=keyword_node,
                form_path=form_path,
            )
        if keyword_node.value not in {":description", ":format-hint", ":example"}:
            _raise_guidance_error(
                f"{label} guidance has unknown key `{keyword_node.value}`",
                node=keyword_node,
                form_path=form_path,
            )
        if keyword_node.value in values:
            _raise_guidance_error(
                f"{label} guidance duplicates key `{keyword_node.value}`",
                node=keyword_node,
                form_path=form_path,
            )
        values[keyword_node.value] = value_node

    description = _parse_nonempty_string(
        values.get(":description"), key=":description", form_path=form_path, label=label
    )
    format_hint = _parse_nonempty_string(
        values.get(":format-hint"), key=":format-hint", form_path=form_path, label=label
    )
    example_node = values.get(":example")
    example_expr = None
    if example_node is not None:
        example_expr = SyntaxNode(
            datum=example_node,
            span=example_node.span,
            module_path=example_node.module_path,
            form_path=form_path,
        )
    return ResultGuidance(description, format_hint, example_expr)


def _parse_nonempty_string(
    node: object | None,
    *,
    key: str,
    form_path: tuple[str, ...],
    label: str,
) -> str | None:
    if node is None:
        return None
    if not isinstance(node, SyntaxString) or not node.value.strip():
        _raise_guidance_error(
            f"{label} guidance `{key}` must be a non-empty string",
            node=node,
            form_path=form_path,
        )
    return node.value


def _raise_guidance_error(
    message: str,
    *,
    node: object,
    form_path: tuple[str, ...],
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="result_guidance_invalid",
                message=message,
                span=node.span,
                form_path=form_path,
                expansion_stack=getattr(node, "expansion_stack", ()),
            ),
        )
    )
