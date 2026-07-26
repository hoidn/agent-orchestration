"""Emit ordinary stdout when the production LSP server import first begins."""

from __future__ import annotations

import builtins
import sys


_ORIGINAL_IMPORT = builtins.__import__
_EMITTED = False


def _import_with_stdout_probe(
    name: str,
    globals: dict[str, object] | None = None,
    locals: dict[str, object] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> object:
    global _EMITTED
    imported = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    if not _EMITTED and "orchestrator.lsp.server" in sys.modules:
        _EMITTED = True
        print("ordinary import-time stdout", flush=True)
    return imported


builtins.__import__ = _import_with_stdout_probe
