"""Pure Workflow Lisp source-coordinate translation for LSP consumers."""

from __future__ import annotations

from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan


class CoordinateTranslationError(ValueError):
    """The supplied raw span is not valid for the accepted source text."""


def source_span_to_lsp_range(
    span: SourceSpan,
    accepted_text: str,
) -> dict[str, dict[str, int]]:
    """Validate one raw span and translate it to a plain LSP range payload.

    Frontend positions use 1-based code-point lines and columns plus a
    code-point offset.  LSP positions use 0-based lines and UTF-16 code units.
    The compiler coordinates are checked against the reader's newline-normalized
    parser view.  LSP coordinates are then derived from the exact accepted disk
    text so UTF-16 character counts retain the editor's source representation.
    """

    if not isinstance(span, SourceSpan):
        raise CoordinateTranslationError("span must be a SourceSpan")
    if not isinstance(accepted_text, str):
        raise CoordinateTranslationError("accepted_text must be a string")
    if not isinstance(span.start, SourcePosition) or not isinstance(
        span.end, SourcePosition
    ):
        raise CoordinateTranslationError(
            "span endpoints must be SourcePosition values"
        )
    if not isinstance(span.start.path, str) or not isinstance(
        span.end.path, str
    ):
        raise CoordinateTranslationError("span endpoint paths must be strings")
    if span.start.path != span.end.path:
        raise CoordinateTranslationError(
            "span endpoints must belong to the same source"
        )

    parser_text = accepted_text.replace("\r\n", "\n").replace("\r", "\n")
    parser_line_bounds = _line_bounds(parser_text)
    disk_line_bounds = _line_bounds(accepted_text)
    if len(parser_line_bounds) != len(disk_line_bounds):
        raise CoordinateTranslationError(
            "parser and disk text line boundaries disagree"
        )
    start = _translate_position(
        span.start,
        parser_text,
        parser_line_bounds,
        accepted_text,
        disk_line_bounds,
    )
    end = _translate_position(
        span.end,
        parser_text,
        parser_line_bounds,
        accepted_text,
        disk_line_bounds,
    )
    if span.start.offset > span.end.offset:
        raise CoordinateTranslationError(
            "span start must not follow span end"
        )

    return {"start": start, "end": end}


def _line_bounds(text: str) -> tuple[tuple[int, int], ...]:
    """Return raw code-point ``(start, content_end)`` bounds for every line."""

    bounds: list[tuple[int, int]] = []
    line_start = 0
    offset = 0
    while offset < len(text):
        character = text[offset]
        if character == "\r":
            bounds.append((line_start, offset))
            if offset + 1 < len(text) and text[offset + 1] == "\n":
                offset += 2
            else:
                offset += 1
            line_start = offset
            continue
        if character == "\n":
            bounds.append((line_start, offset))
            offset += 1
            line_start = offset
            continue
        offset += 1
    bounds.append((line_start, len(text)))
    return tuple(bounds)


def _translate_position(
    position: SourcePosition,
    parser_text: str,
    parser_line_bounds: tuple[tuple[int, int], ...],
    disk_text: str,
    disk_line_bounds: tuple[tuple[int, int], ...],
) -> dict[str, int]:
    if (
        type(position.line) is not int
        or type(position.column) is not int
        or type(position.offset) is not int
    ):
        raise CoordinateTranslationError(
            "line, column, and offset must be integers"
        )
    if position.line < 1 or position.line > len(parser_line_bounds):
        raise CoordinateTranslationError("line is outside the accepted text")
    if position.column < 1:
        raise CoordinateTranslationError("column must be 1-based")
    if position.offset < 0 or position.offset > len(parser_text):
        raise CoordinateTranslationError(
            "offset is outside the accepted text"
        )

    parser_line_start, parser_content_end = parser_line_bounds[position.line - 1]
    code_point_index = position.column - 1
    if code_point_index > parser_content_end - parser_line_start:
        raise CoordinateTranslationError(
            "column is outside its accepted source line"
        )
    expected_offset = parser_line_start + code_point_index
    if position.offset != expected_offset:
        raise CoordinateTranslationError(
            "line/column and offset disagree for the accepted text"
        )

    disk_line_start, disk_content_end = disk_line_bounds[position.line - 1]
    if code_point_index > disk_content_end - disk_line_start:
        raise CoordinateTranslationError(
            "column is outside its accepted disk-text line"
        )
    prefix = disk_text[disk_line_start : disk_line_start + code_point_index]
    utf16_character = sum(
        2 if ord(character) > 0xFFFF else 1 for character in prefix
    )
    return {
        "line": position.line - 1,
        "character": utf16_character,
    }


__all__ = [
    "CoordinateTranslationError",
    "source_span_to_lsp_range",
]
