"""Protocol-independent Workflow Lisp source-coordinate translation tests.

Synthetic and unreadable diagnostic-path routing is owned by the diagnostic
translation surface.  This module covers only conversion against supplied,
accepted source text.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Callable

import pytest

from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan


RangePayload = dict[str, dict[str, int]]
TranslateSpan = Callable[[SourceSpan, str], RangePayload]


def _coordinate_surface() -> tuple[TranslateSpan, type[ValueError]]:
    try:
        module = import_module("orchestrator.lsp.coordinates")
    except ModuleNotFoundError:
        pytest.fail("orchestrator.lsp.coordinates is not implemented")

    translate = getattr(module, "source_span_to_lsp_range", None)
    error_type = getattr(module, "CoordinateTranslationError", None)
    if not callable(translate):
        pytest.fail("source_span_to_lsp_range is not implemented")
    if not isinstance(error_type, type) or not issubclass(error_type, ValueError):
        pytest.fail("CoordinateTranslationError must be a ValueError subtype")
    return translate, error_type


def _position(
    *,
    line: int,
    column: int,
    offset: int,
    path: str = "/workspace/example.orc",
) -> SourcePosition:
    return SourcePosition(path=path, line=line, column=column, offset=offset)


def _span(
    *,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> SourceSpan:
    return SourceSpan(
        start=_position(line=start[0], column=start[1], offset=start[2]),
        end=_position(line=end[0], column=end[1], offset=end[2]),
    )


def test_ascii_span_converts_both_raw_endpoints_to_zero_based_range() -> None:
    translate, _ = _coordinate_surface()

    assert translate(
        _span(start=(1, 2, 1), end=(2, 3, 8)),
        "alpha\nbeta\n",
    ) == {
        "start": {"line": 0, "character": 1},
        "end": {"line": 1, "character": 2},
    }


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        (
            _span(start=(1, 3, 2), end=(1, 5, 4)),
            {
                "start": {"line": 0, "character": 3},
                "end": {"line": 0, "character": 5},
            },
        ),
        (
            _span(start=(1, 2, 1), end=(1, 4, 3)),
            {
                "start": {"line": 0, "character": 1},
                "end": {"line": 0, "character": 4},
            },
        ),
    ],
)
def test_non_bmp_code_points_before_or_inside_span_count_as_two_utf16_units(
    span: SourceSpan,
    expected: RangePayload,
) -> None:
    translate, _ = _coordinate_surface()

    assert translate(span, "a😀bc") == expected


@pytest.mark.parametrize(
    ("text", "span", "expected"),
    [
        (
            "one\n😀x\n",
            _span(start=(1, 1, 0), end=(3, 1, 7)),
            {
                "start": {"line": 0, "character": 0},
                "end": {"line": 2, "character": 0},
            },
        ),
        (
            "one\n😀x\n",
            _span(start=(2, 1, 4), end=(2, 1, 4)),
            {
                "start": {"line": 1, "character": 0},
                "end": {"line": 1, "character": 0},
            },
        ),
        (
            "",
            _span(start=(1, 1, 0), end=(1, 1, 0)),
            {
                "start": {"line": 0, "character": 0},
                "end": {"line": 0, "character": 0},
            },
        ),
    ],
)
def test_full_text_and_line_boundary_positions_are_preserved(
    text: str,
    span: SourceSpan,
    expected: RangePayload,
) -> None:
    translate, _ = _coordinate_surface()

    assert translate(span, text) == expected


def test_crlf_and_bare_cr_offsets_follow_the_normalized_parser_view() -> None:
    translate, _ = _coordinate_surface()

    assert translate(
        _span(start=(1, 3, 2), end=(4, 1, 9)),
        "ab\r\ncd\ref\n",
    ) == {
        "start": {"line": 0, "character": 2},
        "end": {"line": 3, "character": 0},
    }


def test_real_reader_crlf_span_uses_parser_offset_and_disk_text_utf16(
    tmp_path: Path,
) -> None:
    translate, _ = _coordinate_surface()
    source_path = tmp_path / "crlf.orc"
    accepted_text = "alpha\r\n😀bravo\r\n"
    source_path.write_bytes(accepted_text.encode("utf-8"))

    parse_tree = read_sexpr_file(source_path)
    later_line_span = parse_tree.items[1].span

    assert later_line_span.start == SourcePosition(
        path=str(source_path),
        line=2,
        column=1,
        offset=6,
    )
    assert translate(later_line_span, accepted_text) == {
        "start": {"line": 1, "character": 0},
        "end": {"line": 1, "character": 7},
    }


@pytest.mark.parametrize(
    ("text", "span"),
    [
        ("ab\n", _span(start=(0, 1, 0), end=(1, 1, 0))),
        ("ab\n", _span(start=(3, 1, 3), end=(3, 1, 3))),
        ("ab\n", _span(start=(1, 0, 0), end=(1, 1, 0))),
        ("ab\n", _span(start=(1, 4, 3), end=(1, 4, 3))),
        ("ab\n", _span(start=(2, 2, 3), end=(2, 2, 3))),
        ("ab\n", _span(start=(1, 1, -1), end=(1, 1, -1))),
        ("ab\n", _span(start=(1, 1, 4), end=(1, 1, 4))),
        ("ab\n", _span(start=(1, 2, 0), end=(1, 2, 0))),
        ("a😀b", _span(start=(1, 3, 3), end=(1, 3, 3))),
        ("ab\r\ncd", _span(start=(2, 1, 4), end=(2, 1, 4))),
        ("ab\ncd", _span(start=(2, 2, 4), end=(1, 2, 1))),
    ],
)
def test_invalid_lines_columns_offsets_and_reversed_ranges_fail_closed(
    text: str,
    span: SourceSpan,
) -> None:
    translate, error_type = _coordinate_surface()

    with pytest.raises(error_type):
        translate(span, text)


@pytest.mark.parametrize("accepted_text", [None, b"(defmodule example)"])
def test_missing_or_non_text_accepted_source_fails_closed(
    accepted_text: object,
) -> None:
    translate, error_type = _coordinate_surface()
    span = _span(start=(1, 1, 0), end=(1, 1, 0))

    with pytest.raises(error_type):
        translate(span, accepted_text)  # type: ignore[arg-type]
