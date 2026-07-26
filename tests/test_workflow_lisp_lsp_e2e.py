"""Editor-shaped end-to-end proof against a real repository workflow."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tests.test_workflow_lisp_lsp_integration import (
    _LspProcess,
    _change,
    _initialize,
    _open,
    _request,
    _request_until,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CYCLE_GUARD_ENTRY = REPO_ROOT / "workflows" / "examples" / "cycle_guard_demo.orc"
CYCLE_GUARD_COMMANDS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "cycle_guard_demo.commands.json"
)


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        digest.update(b"missing")
        return digest.hexdigest()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        if path.is_symlink():
            digest.update(b"symlink")
            digest.update(path.readlink().as_posix().encode("utf-8"))
        elif path.is_dir():
            digest.update(b"directory")
        else:
            digest.update(b"file")
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
    return digest.hexdigest()


def test_real_repository_cycle_guard_editor_session_is_read_only() -> None:
    entry_bytes = CYCLE_GUARD_ENTRY.read_bytes()
    command_bytes = CYCLE_GUARD_COMMANDS.read_bytes()
    build_digest = _tree_digest(REPO_ROOT / ".orchestrate" / "build")
    source_text = entry_bytes.decode("utf-8")
    process = _LspProcess(REPO_ROOT)
    try:
        _initialize(
            process,
            workspace=REPO_ROOT,
            initialization_options={
                "source_roots": [str(REPO_ROOT / "workflows" / "examples")],
                "entry_workflow": "cycle-guard-demo",
                "command_boundaries_path": str(CYCLE_GUARD_COMMANDS),
            },
        )
        _open(process, source_path=CYCLE_GUARD_ENTRY, text=source_text)

        symbols, observed = _request_until(
            process,
            request_id=2,
            method="textDocument/documentSymbol",
            params={
                "textDocument": {"uri": CYCLE_GUARD_ENTRY.as_uri()},
            },
            result_predicate=lambda result: isinstance(result, list),
        )
        assert [item["name"] for item in symbols["result"]] == [
            "cycle_guard_demo",
            "cycle-guard-demo",
        ]
        assert not any(
            item.get("method") == "textDocument/publishDiagnostics"
            and item["params"]["diagnostics"]
            for item in observed
        )

        completion, _ = _request(
            process,
            request_id=3,
            method="textDocument/completion",
            params={
                "textDocument": {"uri": CYCLE_GUARD_ENTRY.as_uri()},
                "position": {"line": 14, "character": 5},
            },
        )
        labels = {item["label"] for item in completion["result"]["items"]}
        assert {"cycle-guard-demo", "command-result", "defworkflow"}.issubset(
            labels
        )

        unsupported_definition, _ = _request(
            process,
            request_id=4,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": CYCLE_GUARD_ENTRY.as_uri()},
                "position": {"line": 14, "character": 20},
            },
        )
        assert unsupported_definition["result"] is None

        _change(
            process,
            source_path=CYCLE_GUARD_ENTRY,
            text=source_text + "\n; unsaved editor buffer\n",
            version=2,
        )
        dirty_symbols, _ = _request(
            process,
            request_id=5,
            method="textDocument/documentSymbol",
            params={
                "textDocument": {"uri": CYCLE_GUARD_ENTRY.as_uri()},
            },
        )
        assert dirty_symbols["result"] is None
        process.shutdown()
    finally:
        process.close()

    assert CYCLE_GUARD_ENTRY.read_bytes() == entry_bytes
    assert CYCLE_GUARD_COMMANDS.read_bytes() == command_bytes
    assert _tree_digest(REPO_ROOT / ".orchestrate" / "build") == build_digest
