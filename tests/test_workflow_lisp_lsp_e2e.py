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
from tests.test_workflow_lisp_lsp_stdio import _initialize_request


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


def test_watcher_disabled_helper_save_recompiles_clean_importer(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    helper_path = workspace / "helper.orc"
    importer_path = workspace / "importer.orc"
    helper_text = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule helper)
  (export Shared)
  (defrecord Shared
    (approved Bool)))
"""
    importer_text = """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule importer)
  (import helper :only (Shared))
  (export Consumer)
  (defrecord Consumer
    (shared Shared)))
"""
    helper_path.write_text(helper_text, encoding="utf-8")
    importer_path.write_text(importer_text, encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        process.send(
            _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                workspace_folder_uris=(workspace.as_uri(),),
                initialization_options={"source_roots": [str(workspace)]},
                capabilities={},
            )
        )
        response, initialized_observed = process.read_until(
            lambda item: item.get("id") == 1
        )
        assert "error" not in response
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {},
            }
        )

        _open(process, source_path=importer_path, text=importer_text)
        importer_symbols, importer_observed = _request_until(
            process,
            request_id=2,
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": importer_path.as_uri()}},
            result_predicate=lambda result: isinstance(result, list),
            timeout=30.0,
        )
        assert [item["name"] for item in importer_symbols["result"]] == [
            "importer"
        ]

        _open(process, source_path=helper_path, text=helper_text)
        helper_symbols, helper_observed = _request_until(
            process,
            request_id=3,
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": helper_path.as_uri()}},
            result_predicate=lambda result: isinstance(result, list),
            timeout=30.0,
        )
        assert [item["name"] for item in helper_symbols["result"]] == ["helper"]
        assert not any(
            item.get("method") == "client/registerCapability"
            for item in (
                *initialized_observed,
                *importer_observed,
                *helper_observed,
            )
        )

        changed_helper = helper_text.replace("Shared", "Renamed")
        _change(
            process,
            source_path=helper_path,
            text=changed_helper,
            version=2,
        )
        helper_path.write_text(changed_helper, encoding="utf-8")
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didSave",
                "params": {
                    "textDocument": {"uri": helper_path.as_uri()},
                },
            }
        )

        importer_error, save_observed = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == importer_path.as_uri()
                and bool(item["params"]["diagnostics"])
            ),
            timeout=30.0,
        )
        diagnostic = importer_error["params"]["diagnostics"][0]
        assert diagnostic["source"] == "orc"
        assert diagnostic["code"] == "module_export_missing"
        assert diagnostic["data"]["authority_layer"] == "frontend"
        assert diagnostic["data"]["compile_entry_uri"] == importer_path.as_uri()
        assert not any(
            item.get("method") == "client/registerCapability"
            for item in save_observed
        )
        process.shutdown()
    finally:
        process.close()
