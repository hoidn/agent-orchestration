"""Read Workflow Lisp source text into source-spanned S-expressions."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re
from pathlib import Path

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .sexpr import BoolAtom, FloatAtom, IntAtom, KeywordAtom, ListExpr, SExpr, StringAtom, SymbolAtom
from .spans import SourcePosition, SourceSpan


_INTEGER_RE = re.compile(r"-?\d+\Z")
_FLOAT_RE = re.compile(r"-?(?:\d+\.\d*|\d*\.\d+)\Z")


@dataclass(frozen=True)
class SourceReadRecord:
    """One exact source-file read observed by a compiler-owned trace."""

    canonical_path: Path
    revision: str
    ordinal: int


@dataclass(frozen=True)
class ModuleGraphReadAttempt:
    """One all-or-nothing module-graph discovery attempt."""

    attempt_id: int
    canonical_entry_path: Path
    started_at_ordinal: int
    completed_at_ordinal: int | None
    module_paths: tuple[Path, ...] | None


@dataclass(frozen=True)
class _SourceReadViews:
    """Ephemeral source contents derived from one physical read."""

    raw_bytes: bytes
    raw_decoded_text: str
    parser_text: str


class SourceReadTrace:
    """Ordered source-read collector with fail-closed revision consistency."""

    def __init__(self) -> None:
        self._records: list[SourceReadRecord] = []
        self._revisions_by_path: dict[Path, str] = {}
        self._module_graph_read_attempts: list[ModuleGraphReadAttempt] = []

    @property
    def records(self) -> tuple[SourceReadRecord, ...]:
        """Return immutable records in physical-read order."""

        return tuple(self._records)

    @property
    def revision_vector(self) -> tuple[tuple[Path, str], ...]:
        """Return the unique canonical path/revision vector in path order."""

        return tuple(sorted(self._revisions_by_path.items(), key=lambda item: item[0].as_posix()))

    @property
    def revision_conflict_paths(self) -> tuple[Path, ...]:
        """Return paths whose ordered records contain conflicting revisions."""

        first_revision_by_path: dict[Path, str] = {}
        conflicts: list[Path] = []
        for record in self._records:
            first_revision = first_revision_by_path.setdefault(
                record.canonical_path,
                record.revision,
            )
            if (
                first_revision != record.revision
                and record.canonical_path not in conflicts
            ):
                conflicts.append(record.canonical_path)
        return tuple(conflicts)

    @property
    def module_graph_read_attempts(self) -> tuple[ModuleGraphReadAttempt, ...]:
        """Return immutable graph-attempt metadata in monotonic id order."""

        return tuple(self._module_graph_read_attempts)

    def _begin_module_graph_read_attempt(self, entry_path: Path) -> int:
        """Begin one graph attempt at the next source-read ordinal."""

        attempt_id = len(self._module_graph_read_attempts)
        self._module_graph_read_attempts.append(
            ModuleGraphReadAttempt(
                attempt_id=attempt_id,
                canonical_entry_path=Path(entry_path).resolve(),
                started_at_ordinal=len(self._records),
                completed_at_ordinal=None,
                module_paths=None,
            )
        )
        return attempt_id

    def _complete_module_graph_read_attempt(
        self,
        attempt_id: int,
        *,
        module_paths: tuple[Path, ...],
    ) -> None:
        """Complete one known, still-open graph attempt."""

        if (
            not isinstance(attempt_id, int)
            or attempt_id < 0
            or attempt_id >= len(self._module_graph_read_attempts)
        ):
            raise RuntimeError(f"unknown module-graph read attempt `{attempt_id}`")
        attempt = self._module_graph_read_attempts[attempt_id]
        if attempt.completed_at_ordinal is not None:
            raise RuntimeError(
                f"module-graph read attempt `{attempt_id}` is already completed"
            )
        self._module_graph_read_attempts[attempt_id] = replace(
            attempt,
            completed_at_ordinal=len(self._records),
            module_paths=tuple(Path(path).resolve() for path in module_paths),
        )

    def _record(
        self,
        *,
        canonical_path: Path,
        revision: str,
    ) -> SourceReadRecord:
        record = SourceReadRecord(
            canonical_path=canonical_path,
            revision=revision,
            ordinal=len(self._records),
        )
        self._records.append(record)
        previous_revision = self._revisions_by_path.setdefault(canonical_path, revision)
        if previous_revision != revision:
            raise RuntimeError(
                f"source `{canonical_path}` changed during one compiler read trace"
            )
        return record


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
        if self._starts_bracket_balanced_type_atom():
            return self._read_bracket_balanced_type_atom()
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

    def _read_bracket_balanced_type_atom(self) -> SymbolAtom:
        start = self._position()
        token_chars: list[str] = []
        bracket_depth = 0
        while not self._at_end():
            current = self._peek()
            if bracket_depth == 0 and (current.isspace() or current in {"(", ")", ";"}):
                break
            token_chars.append(current)
            self._advance()
            if current == "[":
                bracket_depth += 1
            elif current == "]":
                bracket_depth -= 1
                if bracket_depth < 0:
                    self._raise_error(
                        "invalid type expression",
                        start=start,
                        end=self._position(),
                    )
        if bracket_depth != 0:
            self._raise_error(
                "unclosed type expression",
                start=start,
                end=self._position(),
            )
        return SymbolAtom(
            value="".join(token_chars),
            span=SourceSpan(start=start, end=self._position()),
        )

    def _starts_bracket_balanced_type_atom(self) -> bool:
        if self._peek() in {"(", ")", "[", "]", '"', ";"}:
            return False
        index = self.index
        while index < len(self.source):
            current = self.source[index]
            if current == "[":
                return True
            if current.isspace() or current in {"(", ")", "]", ";"}:
                return False
            index += 1
        return False

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
            return FloatAtom(value=float(token), span=SourceSpan(start=start, end=end))
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


def _read_source_file_views(
    path: Path,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> _SourceReadViews:
    """Read one exact source value and derive its strict and parser text views."""

    canonical_path = path.resolve()
    try:
        raw_bytes = canonical_path.read_bytes()
    except FileNotFoundError:
        if source_read_trace is not None:
            source_read_trace._record(
                canonical_path=canonical_path,
                revision="missing",
            )
        raise
    except OSError:
        if source_read_trace is not None:
            source_read_trace._record(
                canonical_path=canonical_path,
                revision="unreadable",
            )
        raise

    revision = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
    try:
        raw_decoded_text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        if source_read_trace is not None:
            source_read_trace._record(
                canonical_path=canonical_path,
                revision=revision,
            )
        raise
    parser_text = raw_decoded_text.replace("\r\n", "\n").replace("\r", "\n")
    if source_read_trace is not None:
        source_read_trace._record(
            canonical_path=canonical_path,
            revision=revision,
        )
    return _SourceReadViews(
        raw_bytes=raw_bytes,
        raw_decoded_text=raw_decoded_text,
        parser_text=parser_text,
    )


def read_sexpr_file(
    path: Path,
    *,
    source_read_trace: SourceReadTrace | None = None,
) -> ListExpr:
    """Read a UTF-8 `.orc` file into a source-spanned top-level S-expression list."""

    views = _read_source_file_views(path, source_read_trace=source_read_trace)
    return read_sexpr_text(views.parser_text, source_path=str(path))
