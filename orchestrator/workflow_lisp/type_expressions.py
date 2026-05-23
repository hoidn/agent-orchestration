"""Parser for authored Workflow Lisp type expressions."""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan


@dataclass(frozen=True)
class NamedTypeExpr:
    name: str


@dataclass(frozen=True)
class WorkflowRefTypeExpr:
    param_types: tuple["ParsedTypeExpr", ...]
    return_type: "ParsedTypeExpr"


@dataclass(frozen=True)
class OptionalTypeExpr:
    item_type: "ParsedTypeExpr"


@dataclass(frozen=True)
class ListTypeExpr:
    item_type: "ParsedTypeExpr"


@dataclass(frozen=True)
class MapTypeExpr:
    key_type: "ParsedTypeExpr"
    value_type: "ParsedTypeExpr"


ParsedTypeExpr = NamedTypeExpr | WorkflowRefTypeExpr | OptionalTypeExpr | ListTypeExpr | MapTypeExpr


def parse_type_expression(
    text: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> ParsedTypeExpr:
    """Parse one authored type reference into a recursive syntax tree."""

    authored = text.strip()
    if not authored:
        _raise_type_expression_error(
            "type expression cannot be empty",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )

    head, args_text = _generic_head_and_args(authored)
    if head is None:
        if "[" in authored or "]" in authored:
            _raise_type_expression_error(
                f"invalid type expression `{authored}`",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        return NamedTypeExpr(name=authored)

    if head == "WorkflowRef":
        split_index = top_level_arrow_index(args_text)
        if split_index is None:
            _raise_type_expression_error(
                f"invalid workflow-ref type `{authored}`",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        params_text = args_text[:split_index].strip()
        return_text = args_text[split_index + 2 :].strip()
        param_texts = _parse_workflow_ref_param_texts(
            params_text,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
        return WorkflowRefTypeExpr(
            param_types=tuple(
                parse_type_expression(
                    param_text,
                    span=span,
                    form_path=form_path,
                    expansion_stack=expansion_stack,
                )
                for param_text in param_texts
            ),
            return_type=parse_type_expression(
                return_text,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )

    args = split_top_level_args(args_text)
    if head == "Optional":
        if len(args) != 1:
            _raise_type_expression_error(
                f"`Optional` expects 1 type argument in `{authored}`",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        return OptionalTypeExpr(
            item_type=parse_type_expression(
                args[0],
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        )
    if head == "List":
        if len(args) != 1:
            _raise_type_expression_error(
                f"`List` expects 1 type argument in `{authored}`",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        return ListTypeExpr(
            item_type=parse_type_expression(
                args[0],
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        )
    if head == "Map":
        if len(args) != 2:
            _raise_type_expression_error(
                f"`Map` expects 2 type arguments in `{authored}`",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        return MapTypeExpr(
            key_type=parse_type_expression(
                args[0],
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
            value_type=parse_type_expression(
                args[1],
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )

    _raise_type_expression_error(
        f"unknown generic type constructor `{head}` in `{authored}`",
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
    )


def split_top_level_args(text: str) -> tuple[str, ...]:
    """Split a comma-delimited type-argument list at top level only."""

    if not text.strip():
        return ()
    return tuple(_split_top_level(text, delimiter=","))


def top_level_arrow_index(text: str) -> int | None:
    """Return the top-level `->` index, ignoring nested parens and brackets."""

    paren_depth = 0
    bracket_depth = 0
    for index in range(len(text) - 1):
        char = text[index]
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        elif char == "-" and text[index + 1] == ">" and paren_depth == 0 and bracket_depth == 0:
            return index
    return None


def _parse_workflow_ref_param_texts(
    text: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> tuple[str, ...]:
    if text.startswith("("):
        if not text.endswith(")"):
            _raise_type_expression_error(
                f"invalid workflow-ref parameter list `{text}`",
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
        param_texts = tuple(_split_top_level(text[1:-1].strip(), delimiter=None))
    else:
        param_texts = (text,) if text else ()
    if not param_texts or any(not param.strip() for param in param_texts):
        _raise_type_expression_error(
            "workflow-ref types require at least one parameter type",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    return tuple(param.strip() for param in param_texts)


def _generic_head_and_args(text: str) -> tuple[str | None, str]:
    bracket_index = text.find("[")
    if bracket_index < 0:
        return None, ""
    if not text.endswith("]"):
        return None, ""
    head = text[:bracket_index].strip()
    if not head:
        return None, ""
    inner = text[bracket_index + 1 : -1]
    bracket_depth = 0
    for char in inner:
        if char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
            if bracket_depth < 0:
                return None, ""
    if bracket_depth != 0:
        return None, ""
    return head, inner


def _split_top_level(text: str, *, delimiter: str | None) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    paren_depth = 0
    bracket_depth = 0
    for char in text:
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        if delimiter is None:
            if char.isspace() and paren_depth == 0 and bracket_depth == 0:
                token = "".join(current).strip()
                if token:
                    parts.append(token)
                current = []
                continue
        elif char == delimiter and paren_depth == 0 and bracket_depth == 0:
            token = "".join(current).strip()
            if token:
                parts.append(token)
            current = []
            continue
        current.append(char)
    token = "".join(current).strip()
    if token:
        parts.append(token)
    return parts


def _raise_type_expression_error(
    message: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="type_expression_invalid",
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
