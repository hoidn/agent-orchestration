"""Authored Python locations and generated source provenance."""
from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from pathlib import Path


@dataclass(frozen=True)
class PythonSite:
    path: str
    line: int
    column: int = 1
    end_line: int | None = None
    end_column: int | None = None


def author_site() -> PythonSite:
    frame = inspect.currentframe()
    try:
        while frame is not None:
            path = Path(frame.f_code.co_filename)
            if not str(path).startswith("<") and path.parent != Path(__file__).parent:
                return PythonSite(str(path), frame.f_lineno)
            frame = frame.f_back
    finally:
        del frame
    return PythonSite("<python>", 1)


def definition_site(value) -> PythonSite:
    try:
        lines, line = inspect.getsourcelines(value)
        return PythonSite(inspect.getsourcefile(value) or "<python>", line,
                          end_line=line + len(lines) - 1)
    except (OSError, TypeError):
        return author_site()


class PythonFrontendError(ValueError):
    def __init__(self, code: str, message: str, *, site: PythonSite | None = None):
        self.code = code
        self.message = message
        self.site = site or author_site()
        super().__init__(f"{self.site.path}:{self.site.line}:{self.site.column}: {code}: {message}")


@dataclass(frozen=True)
class SourceMapEntry:
    python: PythonSite
    generated: PythonSite
    kind: str


@dataclass
class PythonSourceMap:
    schema_version: str = "workflow-python/source-map/1"
    entries: list[SourceMapEntry] = field(default_factory=list)
    source_hashes: dict[str, str] = field(default_factory=dict)
