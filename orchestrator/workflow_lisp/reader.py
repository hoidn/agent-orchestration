"""Read Workflow Lisp source text into source-spanned S-expressions."""

from __future__ import annotations

import re
from pathlib import Path

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .sexpr import BoolAtom, IntAtom, KeywordAtom, ListExpr, SExpr, StringAtom, SymbolAtom
from .spans import SourcePosition, SourceSpan


_INTEGER_RE = re.compile(r"-?\d+\Z")
_FLOAT_RE = re.compile(r"-?(?:\d+\.\d*|\d*\.\d+)\Z")


class _Reader:
    """Deterministic codepoint-based S-expression reader."""

    def __init__(self, source: str, source_path: str):
        self.source = source
        self.source_path = source_path
        self.index = 0
        self.line = 1
        self.column = 1

    def read(self) -> ListExpr:
        items: list[SExpr] = []
        self._skip_ignored()
        while not self._at_end():
            items.append(self._read_expr())
            self._skip_ignored()
        if items:
            span = SourceSpan(start=items[0].span.start, end=items[-1].span.end)
        else:
            position = self._position()
            span = SourceSpan(start=position, end=position)
        return ListExpr(items=tuple(items), span=span)

    def _read_expr(self) -> SExpr:
        current = self._peek()
        if self.source.startswith("WorkflowRef[", self.index):
            return self._read_workflow_ref_type_atom()
        if current == "(":
            return self._read_list()
        if current == '"':
            return self._read_string()
        if current == ")":
            start = self._position()
            self._advance()
            self._raise_error(
                "unexpected closing parenthesis",
                start=start,
                end=self._position(),
            )
        if current in {"[", "]"}:
            start = self._position()
            self._advance()
            self._raise_error(
                "unsupported lexical form: vectors are not supported in Stage 1",
                start=start,
                end=self._position(),
            )
        return self._read_atom()

    def _read_workflow_ref_type_atom(self) -> SymbolAtom:
        start = self._position()
        token_chars: list[str] = []
        bracket_depth = 0
        while not self._at_end():
            current = self._peek()
            token_chars.append(current)
            self._advance()
            if current == "[":
                bracket_depth += 1
            elif current == "]":
                bracket_depth -= 1
                if bracket_depth == 0:
                    return SymbolAtom(
                        value="".join(token_chars),
                        span=SourceSpan(start=start, end=self._position()),
                    )
        self._raise_error(
            "unclosed workflow-ref type expression",
            start=start,
            end=self._position(),
        )

    def _read_list(self) -> ListExpr:
        start = self._position()
        self._advance()
        items: list[SExpr] = []
        while True:
            self._skip_ignored()
            if self._at_end():
                self._raise_error("unclosed list", start=start, end=self._position())
            if self._peek() == ")":
                self._advance()
                return ListExpr(
                    items=tuple(items),
                    span=SourceSpan(start=start, end=self._position()),
                )
            items.append(self._read_expr())

    def _read_string(self) -> StringAtom:
        start = self._position()
        self._advance()
        value_chars: list[str] = []
        while not self._at_end():
            current = self._peek()
            if current == '"':
                self._advance()
                return StringAtom(
                    value="".join(value_chars),
                    span=SourceSpan(start=start, end=self._position()),
                )
            if current == "\\":
                escape_start = self._position()
                self._advance()
                if self._at_end():
                    self._raise_error("unterminated string", start=start, end=self._position())
                escaped = self._peek()
                if escaped == "\\":
                    value_chars.append("\\")
                elif escaped == '"':
                    value_chars.append('"')
                elif escaped == "n":
                    value_chars.append("\n")
                elif escaped == "t":
                    value_chars.append("\t")
                else:
                    self._advance()
                    self._raise_error(
                        f"invalid string escape `\\{escaped}`",
                        start=escape_start,
                        end=self._position(),
                    )
                self._advance()
                continue
            if current == "\n":
                self._raise_error("unterminated string", start=start, end=self._position())
            value_chars.append(current)
            self._advance()
        self._raise_error("unterminated string", start=start, end=self._position())

    def _read_atom(self) -> SExpr:
        start = self._position()
        token_chars: list[str] = []
        while not self._at_end():
            current = self._peek()
            if current.isspace() or current in {"(", ")", "[", "]", ";"}:
                break
            token_chars.append(current)
            self._advance()
        token = "".join(token_chars)
        end = self._position()
        if not token:
            self._raise_error("unexpected token", start=start, end=end)
        if token in {"true", "false"}:
            return BoolAtom(value=token == "true", span=SourceSpan(start=start, end=end))
        if token == "nil":
            self._raise_error("unsupported lexical form: nil is not supported in Stage 1", start=start, end=end)
        if token.startswith("'"):
            self._raise_error(
                "unsupported lexical form: quoted symbols are not supported in Stage 1",
                start=start,
                end=end,
            )
        if _INTEGER_RE.match(token):
            return IntAtom(value=int(token), span=SourceSpan(start=start, end=end))
        if _FLOAT_RE.match(token):
            self._raise_error(
                "unsupported lexical form: floats are not supported in Stage 1",
                start=start,
                end=end,
            )
        if token.startswith(":"):
            if len(token) == 1:
                self._raise_error("invalid keyword token", start=start, end=end)
            return KeywordAtom(value=token, span=SourceSpan(start=start, end=end))
        return SymbolAtom(value=token, span=SourceSpan(start=start, end=end))

    def _skip_ignored(self) -> None:
        while not self._at_end():
            current = self._peek()
            if current.isspace():
                self._advance()
                continue
            if current == ";":
                self._advance()
                while not self._at_end() and self._peek() != "\n":
                    self._advance()
                continue
            return

    def _raise_error(self, message: str, *, start: SourcePosition, end: SourcePosition) -> None:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="frontend_parse_error",
                    message=message,
                    span=SourceSpan(start=start, end=end),
                ),
            )
        )

    def _position(self) -> SourcePosition:
        return SourcePosition(
            path=self.source_path,
            line=self.line,
            column=self.column,
            offset=self.index,
        )

    def _peek(self) -> str:
        return self.source[self.index]

    def _advance(self) -> str:
        current = self.source[self.index]
        self.index += 1
        if current == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return current

    def _at_end(self) -> bool:
        return self.index >= len(self.source)


def read_sexpr_text(source: str, *, source_path: str) -> ListExpr:
    """Read source text into a source-spanned top-level S-expression list."""

    return _Reader(source, source_path).read()


def read_sexpr_file(path: Path) -> ListExpr:
    """Read a UTF-8 `.orc` file into a source-spanned top-level S-expression list."""

    return read_sexpr_text(path.read_text(encoding="utf-8"), source_path=str(path))
