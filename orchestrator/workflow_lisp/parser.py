"""Workflow Lisp tokenization, reading, and module-header shaping."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .syntax import (
    AtomKind,
    ParsedWorkflowModule,
    SourceSpan,
    SyntaxAtom,
    SyntaxContext,
    SyntaxDiagnostic,
    SyntaxList,
    SyntaxNode,
    replace_module_name,
)


SUPPORTED_LANGUAGE_VERSION = "0.1"
SUPPORTED_TARGET_DSL = "2.14"


@dataclass(frozen=True)
class Token:
    """Internal token representation with source span."""

    kind: str
    value: str | int | float | bool
    span: SourceSpan


class WorkflowLispSyntaxError(ValueError):
    """Exception carrying one structured syntax diagnostic."""

    def __init__(self, diagnostic: SyntaxDiagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


@dataclass
class _Cursor:
    source_text: str
    source_path: str
    index: int = 0
    byte_offset: int = 0
    line: int = 1
    column: int = 1

    def done(self) -> bool:
        return self.index >= len(self.source_text)

    def peek(self, offset: int = 0) -> str | None:
        position = self.index + offset
        if position >= len(self.source_text):
            return None
        return self.source_text[position]

    def mark(self) -> tuple[int, int, int, int]:
        return (self.index, self.byte_offset, self.line, self.column)

    def advance(self) -> str:
        char = self.source_text[self.index]
        self.index += 1
        self.byte_offset += len(char.encode("utf-8"))
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char


def _span_from_marks(
    source_path: str,
    start: tuple[int, int, int, int],
    end: tuple[int, int, int, int],
) -> SourceSpan:
    return SourceSpan(
        source_file=source_path,
        byte_start=start[1],
        byte_end=end[1],
        line_start=start[2],
        column_start=start[3],
        line_end=end[2],
        column_end=max(start[3], end[3] - 1),
    )


def _raise_syntax_error(
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


def _module_header_clause_node_id(clause_key: str) -> str:
    if clause_key == ":language":
        return "module.header.language"
    if clause_key == ":target-dsl":
        return "module.header.target_dsl"
    return f"module.header.{clause_key.removeprefix(':').replace('-', '_')}"


def _is_symbol_boundary(char: str | None) -> bool:
    return char is None or char.isspace() or char in {"(", ")", ";", '"'}


def tokenize_workflow_lisp(source_text: str, *, source_path: str) -> tuple[Token, ...]:
    """Tokenize one Workflow Lisp source string into internal tokens."""

    cursor = _Cursor(source_text=source_text, source_path=source_path)
    tokens: list[Token] = []

    while not cursor.done():
        char = cursor.peek()
        if char is None:
            break
        if char in {" ", "\t", "\r", "\n"}:
            cursor.advance()
            continue
        if char == ";":
            while (comment_char := cursor.peek()) is not None and comment_char != "\n":
                cursor.advance()
            continue
        if char == "(":
            start = cursor.mark()
            cursor.advance()
            tokens.append(Token("lparen", "(", _span_from_marks(source_path, start, cursor.mark())))
            continue
        if char == ")":
            start = cursor.mark()
            cursor.advance()
            tokens.append(Token("rparen", ")", _span_from_marks(source_path, start, cursor.mark())))
            continue
        if char in {"[", "]", "`", ","}:
            start = cursor.mark()
            cursor.advance()
            _raise_syntax_error(
                code="frontend_parse_error",
                message=f"Unsupported reader syntax: {char}",
                span=_span_from_marks(source_path, start, cursor.mark()),
            )
        if char == "'":
            tokens.append(_read_quoted_symbol_token(cursor))
            continue
        if char == '"':
            tokens.append(_read_string_token(cursor))
            continue
        tokens.append(_read_symbolish_token(cursor))

    return tuple(tokens)


def _read_string_token(cursor: _Cursor) -> Token:
    start = cursor.mark()
    cursor.advance()
    decoded: list[str] = []
    while True:
        char = cursor.peek()
        if char is None:
            _raise_syntax_error(
                code="frontend_parse_error",
                message="Unterminated string literal",
                span=_span_from_marks(cursor.source_path, start, start),
            )
        if char == "\n":
            _raise_syntax_error(
                code="frontend_parse_error",
                message="Unterminated string literal",
                span=_span_from_marks(cursor.source_path, start, start),
            )
        if char == '"':
            cursor.advance()
            return Token("string", "".join(decoded), _span_from_marks(cursor.source_path, start, cursor.mark()))
        if char == "\\":
            slash_mark = cursor.mark()
            cursor.advance()
            escape = cursor.peek()
            if escape is None:
                _raise_syntax_error(
                    code="frontend_parse_error",
                    message="Unterminated string literal",
                    span=_span_from_marks(cursor.source_path, start, start),
                )
            escape_mark = cursor.mark()
            cursor.advance()
            decoded_escape = {
                "n": "\n",
                "t": "\t",
                '"': '"',
                "\\": "\\",
            }.get(escape)
            if decoded_escape is None:
                _raise_syntax_error(
                    code="frontend_parse_error",
                    message=f"Unsupported string escape: \\{escape}",
                    span=_span_from_marks(cursor.source_path, slash_mark, cursor.mark()),
                )
            decoded.append(decoded_escape)
            continue
        decoded.append(cursor.advance())


def _read_symbolish_token(cursor: _Cursor) -> Token:
    start = cursor.mark()
    pieces: list[str] = []
    while not cursor.done():
        char = cursor.peek()
        if _is_symbol_boundary(char):
            break
        pieces.append(cursor.advance())
    raw = "".join(pieces)
    if not raw:
        _raise_syntax_error(
            code="frontend_parse_error",
            message="Unsupported token shape",
            span=_span_from_marks(cursor.source_path, start, cursor.mark()),
        )
    span = _span_from_marks(cursor.source_path, start, cursor.mark())
    if raw == "nil":
        return Token("nil", None, span)
    if raw.startswith(":"):
        if raw == ":":
            _raise_syntax_error(
                code="frontend_parse_error",
                message="Unsupported token shape: :",
                span=span,
            )
        return Token("keyword", raw, span)
    if _looks_like_float(raw):
        return Token("float", float(raw), span)
    if raw == "true":
        return Token("bool", True, span)
    if raw == "false":
        return Token("bool", False, span)
    if _looks_like_int(raw):
        return Token("int", int(raw), span)
    return Token("symbol", raw, span)


def _read_quoted_symbol_token(cursor: _Cursor) -> Token:
    start = cursor.mark()
    cursor.advance()
    pieces: list[str] = []
    while not cursor.done():
        char = cursor.peek()
        if _is_symbol_boundary(char):
            break
        pieces.append(cursor.advance())
    raw = "".join(pieces)
    if not raw:
        _raise_syntax_error(
            code="frontend_parse_error",
            message="Quoted symbol must include a symbol name after '",
            span=_span_from_marks(cursor.source_path, start, cursor.mark()),
        )
    return Token(
        "quoted_symbol",
        raw,
        _span_from_marks(cursor.source_path, start, cursor.mark()),
    )


def _looks_like_int(raw: str) -> bool:
    if raw.startswith(("+", "-")):
        return len(raw) > 1 and raw[1:].isdigit()
    return raw.isdigit()


def _looks_like_float(raw: str) -> bool:
    if raw.count(".") != 1:
        return False
    left, right = raw.split(".", 1)
    if left.startswith(("+", "-")):
        left = left[1:]
    return bool(left) and bool(right) and left.isdigit() and right.isdigit()


def read_syntax_forms(source_text: str, *, source_path: str) -> tuple[SyntaxNode, ...]:
    """Read one source string into raw syntax objects."""

    tokens = tokenize_workflow_lisp(source_text, source_path=source_path)
    index = 0
    forms: list[SyntaxNode] = []
    context = SyntaxContext(source_path=source_path)

    def read_form(position: int) -> tuple[SyntaxNode, int]:
        token = tokens[position]
        if token.kind == "rparen":
            _raise_syntax_error(
                code="frontend_parse_error",
                message="Unmatched closing parenthesis",
                span=token.span,
            )
        if token.kind == "lparen":
            items: list[SyntaxNode] = []
            position += 1
            while position < len(tokens) and tokens[position].kind != "rparen":
                item, position = read_form(position)
                items.append(item)
            if position >= len(tokens):
                _raise_syntax_error(
                    code="frontend_parse_error",
                    message="Unexpected EOF while reading list",
                    span=token.span,
                )
            closing_token = tokens[position]
            span = SourceSpan(
                source_file=source_path,
                byte_start=token.span.byte_start,
                byte_end=closing_token.span.byte_end,
                line_start=token.span.line_start,
                column_start=token.span.column_start,
                line_end=closing_token.span.line_end,
                column_end=closing_token.span.column_end,
            )
            return SyntaxList(items=tuple(items), span=span, context=context), position + 1
        kind = {
            "symbol": AtomKind.SYMBOL,
            "keyword": AtomKind.KEYWORD,
            "string": AtomKind.STRING,
            "quoted_symbol": AtomKind.QUOTED_SYMBOL,
            "int": AtomKind.INT,
            "float": AtomKind.FLOAT,
            "bool": AtomKind.BOOL,
            "nil": AtomKind.NIL,
        }[token.kind]
        return SyntaxAtom(kind=kind, value=token.value, span=token.span, context=context), position + 1

    while index < len(tokens):
        form, index = read_form(index)
        forms.append(form)
    return tuple(forms)


def parse_workflow_module_text(source_text: str, *, source_path: str) -> ParsedWorkflowModule:
    """Parse one Workflow Lisp source string into a shaped module."""

    forms = read_syntax_forms(source_text, source_path=source_path)
    if not forms:
        span = SourceSpan(
            source_file=source_path,
            byte_start=0,
            byte_end=0,
            line_start=1,
            column_start=1,
            line_end=1,
            column_end=1,
        )
        _raise_syntax_error(
            code="frontend_parse_error",
            message="Workflow Lisp module is empty",
            span=span,
        )

    header_candidate = forms[0]
    if not isinstance(header_candidate, SyntaxList):
        _raise_syntax_error(
            code="frontend_parse_error",
            message="First top-level form must be a workflow-lisp header list",
            span=header_candidate.span,
        )
    if not header_candidate.items:
        _raise_syntax_error(
            code="frontend_parse_error",
            message="Workflow Lisp header must not be empty",
            span=header_candidate.span,
        )
    head = header_candidate.items[0]
    if not isinstance(head, SyntaxAtom) or head.kind is not AtomKind.SYMBOL:
        _raise_syntax_error(
            code="frontend_parse_error",
            message="First top-level form must start with workflow-lisp or defmodule",
            span=header_candidate.span,
        )

    header_name = str(head.value)
    language_value: SyntaxAtom
    target_value: SyntaxAtom
    body_forms: tuple[SyntaxNode, ...]
    module_name: str
    if header_name == "workflow-lisp":
        language_clause, target_clause = _collect_header_clauses(
            header_form=header_candidate,
            clause_forms=header_candidate.items[1:],
            enclosing_form_name="workflow-lisp",
        )
        language_value = _extract_header_string(language_clause, ":language")
        target_value = _extract_header_string(target_clause, ":target-dsl")
        body_forms = forms[1:]
        module_name = "workflow-lisp"
    elif header_name == "defmodule":
        if len(forms) > 1:
            _raise_syntax_error(
                code="frontend_parse_error",
                message="defmodule must be the only top-level form in a module file",
                span=forms[1].span,
                enclosing_form_name="defmodule",
            )
        module_name, language_clause, target_clause, body_forms = _shape_defmodule_header(header_candidate)
        language_value = _extract_defmodule_language_version(language_clause)
        target_value = _extract_header_string(target_clause, ":target-dsl", enclosing_form_name="defmodule")
    else:
        _raise_syntax_error(
            code="frontend_parse_error",
            message="First top-level form must start with workflow-lisp or defmodule",
            span=header_candidate.span,
        )

    if language_value.value != SUPPORTED_LANGUAGE_VERSION:
        _raise_syntax_error(
            code="language_version_unsupported",
            message=f"Unsupported workflow-lisp language version: {language_value.value}",
            span=language_value.span,
            enclosing_form_name=header_name,
            generated_core_node_id=_module_header_clause_node_id(":language"),
        )
    if target_value.value != SUPPORTED_TARGET_DSL:
        _raise_syntax_error(
            code="target_dsl_unsupported",
            message=f"Unsupported workflow-lisp target DSL: {target_value.value}",
            span=target_value.span,
            enclosing_form_name=header_name,
            generated_core_node_id=_module_header_clause_node_id(":target-dsl"),
        )

    annotated_header = _attach_module_context(header_candidate, module_name)
    assert isinstance(annotated_header, SyntaxList)
    annotated_body_forms = tuple(_attach_module_context(form, module_name) for form in body_forms)
    return ParsedWorkflowModule(
        source_path=source_path,
        header_form=annotated_header,
        language_version=language_value.value,
        target_dsl=target_value.value,
        body_forms=annotated_body_forms,
    )


def parse_workflow_module_file(path: str | Path) -> ParsedWorkflowModule:
    """Parse one Workflow Lisp source file into a shaped module."""

    file_path = Path(path)
    return parse_workflow_module_text(
        file_path.read_text(encoding="utf-8"),
        source_path=str(file_path),
    )


def _collect_header_clauses(
    *,
    header_form: SyntaxList,
    clause_forms: tuple[SyntaxNode, ...],
    enclosing_form_name: str,
) -> tuple[SyntaxList, SyntaxList]:
    language_clause: SyntaxList | None = None
    target_clause: SyntaxList | None = None
    for clause in clause_forms:
        if not isinstance(clause, SyntaxList) or not clause.items:
            _raise_syntax_error(
                code="frontend_parse_error",
                message=f"Unsupported clause in {enclosing_form_name} header",
                span=clause.span,
                enclosing_form_name=enclosing_form_name,
            )
        key = clause.items[0]
        if not isinstance(key, SyntaxAtom) or key.kind is not AtomKind.KEYWORD:
            _raise_syntax_error(
                code="frontend_parse_error",
                message=f"Unsupported clause in {enclosing_form_name} header",
                span=clause.span,
                enclosing_form_name=enclosing_form_name,
            )
        if key.value == ":language":
            if language_clause is not None:
                _raise_syntax_error(
                    code="frontend_parse_error",
                    message=f"Duplicate :language clause in {enclosing_form_name} header",
                    span=clause.span,
                    enclosing_form_name=enclosing_form_name,
                    generated_core_node_id=_module_header_clause_node_id(":language"),
                )
            language_clause = clause
            continue
        if key.value == ":target-dsl":
            if target_clause is not None:
                _raise_syntax_error(
                    code="frontend_parse_error",
                    message=f"Duplicate :target-dsl clause in {enclosing_form_name} header",
                    span=clause.span,
                    enclosing_form_name=enclosing_form_name,
                    generated_core_node_id=_module_header_clause_node_id(":target-dsl"),
                )
            target_clause = clause
            continue

        _raise_syntax_error(
            code="frontend_parse_error",
            message=f"Unsupported clause in {enclosing_form_name} header: {key.value}",
            span=key.span,
            enclosing_form_name=enclosing_form_name,
            generated_core_node_id=_module_header_clause_node_id(str(key.value)),
        )

    if language_clause is None:
        _raise_syntax_error(
            code="frontend_parse_error",
            message=f"Missing required :language clause in {enclosing_form_name} header",
            span=header_form.span,
            enclosing_form_name=enclosing_form_name,
            generated_core_node_id=_module_header_clause_node_id(":language"),
        )
    if target_clause is None:
        _raise_syntax_error(
            code="frontend_parse_error",
            message=f"Missing required :target-dsl clause in {enclosing_form_name} header",
            span=header_form.span,
            enclosing_form_name=enclosing_form_name,
            generated_core_node_id=_module_header_clause_node_id(":target-dsl"),
        )
    return language_clause, target_clause


def _shape_defmodule_header(header_form: SyntaxList) -> tuple[str, SyntaxList, SyntaxList, tuple[SyntaxNode, ...]]:
    if len(header_form.items) < 4:
        _raise_syntax_error(
            code="frontend_parse_error",
            message="defmodule requires a module name, header clauses, and body forms",
            span=header_form.span,
            enclosing_form_name="defmodule",
        )
    name_node = header_form.items[1]
    if not isinstance(name_node, SyntaxAtom) or name_node.kind is not AtomKind.SYMBOL:
        _raise_syntax_error(
            code="frontend_parse_error",
            message="defmodule name must be a symbol",
            span=name_node.span,
            enclosing_form_name="defmodule",
        )

    remaining = header_form.items[2:]
    clause_count = 0
    for node in remaining:
        if not isinstance(node, SyntaxList) or not node.items:
            break
        key = node.items[0]
        if not isinstance(key, SyntaxAtom) or key.kind is not AtomKind.KEYWORD:
            break
        if key.value not in {":language", ":target-dsl"}:
            break
        clause_count += 1
    clause_forms = remaining[:clause_count]
    body_forms = remaining[clause_count:]
    if not body_forms:
        _raise_syntax_error(
            code="frontend_parse_error",
            message="defmodule requires at least one body form",
            span=header_form.span,
            enclosing_form_name="defmodule",
        )
    language_clause, target_clause = _collect_header_clauses(
        header_form=header_form,
        clause_forms=clause_forms,
        enclosing_form_name="defmodule",
    )
    return str(name_node.value), language_clause, target_clause, body_forms


def _extract_header_string(
    clause: SyntaxList,
    keyword: str,
    *,
    enclosing_form_name: str = "workflow-lisp",
) -> SyntaxAtom:
    if len(clause.items) != 2:
        _raise_syntax_error(
            code="frontend_parse_error",
            message=f"{keyword} clause must contain one string literal",
            span=clause.span,
            enclosing_form_name=enclosing_form_name,
        )
    key_node, value_node = clause.items
    if not isinstance(key_node, SyntaxAtom) or key_node.value != keyword:
        _raise_syntax_error(
            code="frontend_parse_error",
            message=f"Malformed {keyword} clause in workflow-lisp header",
            span=clause.span,
            enclosing_form_name=enclosing_form_name,
        )
    if not isinstance(value_node, SyntaxAtom) or value_node.kind is not AtomKind.STRING:
        _raise_syntax_error(
            code="frontend_parse_error",
            message=f"{keyword} clause must contain one string literal",
            span=clause.span,
            enclosing_form_name=enclosing_form_name,
        )
    return value_node


def _extract_defmodule_language_version(clause: SyntaxList) -> SyntaxAtom:
    if len(clause.items) != 3:
        _raise_syntax_error(
            code="frontend_parse_error",
            message=":language clause in defmodule must be (:language workflow-lisp \"0.1\")",
            span=clause.span,
            enclosing_form_name="defmodule",
            generated_core_node_id=_module_header_clause_node_id(":language"),
        )
    key_node, language_node, version_node = clause.items
    if not isinstance(key_node, SyntaxAtom) or key_node.value != ":language":
        _raise_syntax_error(
            code="frontend_parse_error",
            message="Malformed :language clause in defmodule header",
            span=clause.span,
            enclosing_form_name="defmodule",
            generated_core_node_id=_module_header_clause_node_id(":language"),
        )
    if (
        not isinstance(language_node, SyntaxAtom)
        or language_node.kind is not AtomKind.SYMBOL
        or language_node.value != "workflow-lisp"
    ):
        _raise_syntax_error(
            code="frontend_parse_error",
            message="defmodule :language must name workflow-lisp",
            span=language_node.span,
            enclosing_form_name="defmodule",
            generated_core_node_id=_module_header_clause_node_id(":language"),
        )
    if not isinstance(version_node, SyntaxAtom) or version_node.kind is not AtomKind.STRING:
        _raise_syntax_error(
            code="frontend_parse_error",
            message="defmodule :language version must be a string literal",
            span=version_node.span,
            enclosing_form_name="defmodule",
            generated_core_node_id=_module_header_clause_node_id(":language"),
        )
    return version_node


def _attach_module_context(node: SyntaxNode, module_name: str) -> SyntaxNode:
    context = replace_module_name(node.context, module_name)
    if isinstance(node, SyntaxAtom):
        return SyntaxAtom(kind=node.kind, value=node.value, span=node.span, context=context)
    return SyntaxList(
        items=tuple(_attach_module_context(item, module_name) for item in node.items),
        span=node.span,
        context=context,
    )
