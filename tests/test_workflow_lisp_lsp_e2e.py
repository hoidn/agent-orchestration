"""Editor-shaped end-to-end proof against a real repository workflow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.test_workflow_lisp_lsp_integration import (
    _LspProcess,
    _change,
    _frozen_form_completion_items,
    _initialize,
    _l3_stdio_session,
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
KISS_BACKLOG_ENTRY = (
    REPO_ROOT / "workflows" / "examples" / "kiss_backlog_item.orc"
)
KISS_BACKLOG_INPUTS = (
    REPO_ROOT / "workflows" / "examples" / "inputs" / "kiss_backlog_item"
)
KISS_BACKLOG_PROVIDERS = KISS_BACKLOG_INPUTS / "providers.json"
KISS_BACKLOG_PROMPTS = KISS_BACKLOG_INPUTS / "prompts.json"
REVIEW_DESIGN_DOCS_ENTRY = (
    REPO_ROOT / "workflows" / "examples" / "review_revise_design_docs.orc"
)
REVIEW_DESIGN_DOCS_INPUTS = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "review_revise_design_docs"
)
REVIEW_DESIGN_DOCS_PROVIDERS = REVIEW_DESIGN_DOCS_INPUTS / "providers.json"
REVIEW_DESIGN_DOCS_PROMPTS = REVIEW_DESIGN_DOCS_INPUTS / "prompts.json"
L3_ENTRY_SELECTION_ROOT = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "modules"
    / "valid"
    / "lsp_l3_entry_selection"
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
                "entry_workflows": {
                    str(CYCLE_GUARD_ENTRY): "cycle-guard-demo",
                },
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
            "CycleGuardSummary",
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


def test_real_repository_l3_mixed_entry_editor_session_is_read_only() -> None:
    application_path = L3_ENTRY_SELECTION_ROOT / "application.orc"
    library_path = L3_ENTRY_SELECTION_ROOT / "library.orc"
    protected_bytes = {
        path: path.read_bytes()
        for path in (application_path, library_path)
    }
    fixture_digest = _tree_digest(L3_ENTRY_SELECTION_ROOT)
    build_digest = _tree_digest(REPO_ROOT / ".orchestrate" / "build")
    runs_digest = _tree_digest(REPO_ROOT / ".orchestrate" / "runs")
    artifact_digest = _tree_digest(REPO_ROOT / "artifacts")

    surfaces = _l3_stdio_session(
        L3_ENTRY_SELECTION_ROOT,
        source_order=(application_path, library_path),
        request_id_prefix="repository-l3",
    )

    assert surfaces[application_path]["diagnostics"] == []
    assert surfaces[library_path]["diagnostics"] == []
    assert {
        item["name"]
        for item in surfaces[application_path]["symbols"]
    } == {
        "application",
        "application-helper",
        "first",
        "selected",
    }
    assert {
        item["name"]
        for item in surfaces[library_path]["symbols"]
    } == {
        "library",
        "library-helper",
    }
    assert surfaces[application_path]["definition"]["uri"] == (
        application_path.as_uri()
    )
    assert surfaces[library_path]["definition"] is None
    assert {
        path: path.read_bytes()
        for path in (application_path, library_path)
    } == protected_bytes
    assert _tree_digest(L3_ENTRY_SELECTION_ROOT) == fixture_digest
    assert not (L3_ENTRY_SELECTION_ROOT / ".orchestrate").exists()
    assert _tree_digest(REPO_ROOT / ".orchestrate" / "build") == build_digest
    assert _tree_digest(REPO_ROOT / ".orchestrate" / "runs") == runs_digest
    assert _tree_digest(REPO_ROOT / "artifacts") == artifact_digest


def test_real_repository_l2_recovery_to_full_is_read_only() -> None:
    configuration_paths = (
        KISS_BACKLOG_ENTRY,
        KISS_BACKLOG_PROVIDERS,
        KISS_BACKLOG_PROMPTS,
    )
    configuration_bytes = {
        path: path.read_bytes()
        for path in configuration_paths
    }
    prompt_assets = tuple(
        REPO_ROOT / relative_path
        for relative_path in json.loads(
            configuration_bytes[KISS_BACKLOG_PROMPTS]
        ).values()
    )
    protected_paths = (*configuration_paths, *prompt_assets)
    protected_bytes = {
        path: path.read_bytes()
        for path in protected_paths
    }
    build_digest = _tree_digest(REPO_ROOT / ".orchestrate" / "build")
    source_text = protected_bytes[KISS_BACKLOG_ENTRY].decode("utf-8")
    process = _LspProcess(REPO_ROOT)
    try:
        _initialize(
            process,
            workspace=REPO_ROOT,
            initialization_options={
                "source_roots": [
                    str(REPO_ROOT / "workflows" / "examples")
                ],
                "entry_workflows": {
                    str(KISS_BACKLOG_ENTRY): "run-backlog-item",
                },
                "provider_externs_path": str(KISS_BACKLOG_PROVIDERS),
                "prompt_externs_path": str(KISS_BACKLOG_PROMPTS),
            },
        )
        _open(process, source_path=KISS_BACKLOG_ENTRY, text=source_text)

        symbols, observed = _request_until(
            process,
            request_id=20,
            method="textDocument/documentSymbol",
            params={
                "textDocument": {"uri": KISS_BACKLOG_ENTRY.as_uri()},
            },
            result_predicate=lambda result: isinstance(result, list),
            timeout=30.0,
        )
        symbols_by_name = {
            item["name"]: item
            for item in symbols["result"]
        }
        assert symbols_by_name["BacklogItemInputs"] == {
            "name": "BacklogItemInputs",
            "kind": 23,
            "range": {
                "start": {"line": 34, "character": 2},
                "end": {"line": 36, "character": 45},
            },
            "selectionRange": {
                "start": {"line": 34, "character": 13},
                "end": {"line": 34, "character": 30},
            },
        }
        assert symbols_by_name["draft-plan-phase"] == {
            "name": "draft-plan-phase",
            "kind": 12,
            "range": {
                "start": {"line": 61, "character": 2},
                "end": {"line": 69, "character": 39},
            },
            "selectionRange": {
                "start": {"line": 61, "character": 11},
                "end": {"line": 61, "character": 27},
            },
        }
        assert symbols_by_name["run-backlog-item"]["kind"] == 12
        assert not any(
            item.get("method") == "textDocument/publishDiagnostics"
            and item["params"]["diagnostics"]
            for item in observed
        )

        completion, _ = _request(
            process,
            request_id=21,
            method="textDocument/completion",
            params={
                "textDocument": {"uri": KISS_BACKLOG_ENTRY.as_uri()},
                "position": {"line": 155, "character": 2},
            },
        )
        completion_by_label = {
            item["label"]: item
            for item in completion["result"]["items"]
        }
        assert completion_by_label["draft-plan-phase"] == {
            "label": "draft-plan-phase",
            "kind": 3,
            "detail": (
                "procedure (inputs: BacklogItemInputs) "
                "-> PlanDraftSurfaceResult "
                "effects (uses-provider(providers.plan))"
            ),
            "sortText": "draft-plan-phase",
        }
        assert completion_by_label["run-backlog-item"] == {
            "label": "run-backlog-item",
            "kind": 3,
            "detail": (
                "workflow (plan-review-ctx: PhaseCtx, "
                "implementation-review-ctx: PhaseCtx, "
                "backlog-inputs: BacklogItemInputs) -> BacklogItemResult"
            ),
            "sortText": "run-backlog-item",
        }
        assert completion_by_label["defworkflow"] == {
            "label": "defworkflow",
            "kind": 14,
            "detail": "form",
            "sortText": "defworkflow",
        }

        _change(
            process,
            source_path=KISS_BACKLOG_ENTRY,
            text=source_text + "\n; unsaved editor buffer\n",
            version=2,
        )
        dirty_symbols, _ = _request(
            process,
            request_id=22,
            method="textDocument/documentSymbol",
            params={
                "textDocument": {"uri": KISS_BACKLOG_ENTRY.as_uri()},
            },
        )
        assert dirty_symbols["result"] is None
        dirty_definition, _ = _request(
            process,
            request_id=23,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": KISS_BACKLOG_ENTRY.as_uri()},
                "position": {"line": 161, "character": 15},
            },
        )
        assert dirty_definition["result"] is None
        dirty_completion, _ = _request(
            process,
            request_id=24,
            method="textDocument/completion",
            params={
                "textDocument": {"uri": KISS_BACKLOG_ENTRY.as_uri()},
                "position": {"line": 155, "character": 2},
            },
        )
        assert dirty_completion["result"] == {
            "isIncomplete": True,
            "items": _frozen_form_completion_items(),
        }

        _change(
            process,
            source_path=KISS_BACKLOG_ENTRY,
            text=source_text,
            version=3,
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didSave",
                "params": {
                    "textDocument": {
                        "uri": KISS_BACKLOG_ENTRY.as_uri(),
                    },
                },
            }
        )
        restored_completion, _ = _request_until(
            process,
            request_id=25,
            method="textDocument/completion",
            params={
                "textDocument": {"uri": KISS_BACKLOG_ENTRY.as_uri()},
                "position": {"line": 155, "character": 2},
            },
            result_predicate=lambda result: result == completion["result"],
            timeout=30.0,
        )
        assert restored_completion["result"] == completion["result"]

        restored_definition, _ = _request_until(
            process,
            request_id=26,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": KISS_BACKLOG_ENTRY.as_uri()},
                "position": {"line": 161, "character": 15},
            },
            result_predicate=lambda result: result is not None,
            timeout=30.0,
        )
        assert restored_definition["result"]["uri"] == (
            KISS_BACKLOG_ENTRY.as_uri()
        )
        restored_symbols, _ = _request(
            process,
            request_id=27,
            method="textDocument/documentSymbol",
            params={
                "textDocument": {"uri": KISS_BACKLOG_ENTRY.as_uri()},
            },
        )
        assert restored_symbols["result"] == symbols["result"]
        process.shutdown()
    finally:
        process.close()

    assert {
        path: path.read_bytes()
        for path in protected_paths
    } == protected_bytes
    assert _tree_digest(REPO_ROOT / ".orchestrate" / "build") == build_digest


def test_real_repository_l5_authored_reference_navigation_is_read_only() -> None:
    configuration_paths = (
        REVIEW_DESIGN_DOCS_ENTRY,
        REVIEW_DESIGN_DOCS_PROVIDERS,
        REVIEW_DESIGN_DOCS_PROMPTS,
    )
    configuration_bytes = {
        path: path.read_bytes()
        for path in configuration_paths
    }
    prompt_assets = tuple(
        REPO_ROOT / relative_path
        for relative_path in json.loads(
            configuration_bytes[REVIEW_DESIGN_DOCS_PROMPTS]
        ).values()
    )
    protected_paths = (*configuration_paths, *prompt_assets)
    protected_bytes = {
        path: path.read_bytes()
        for path in protected_paths
    }
    build_digest = _tree_digest(REPO_ROOT / ".orchestrate" / "build")
    runs_root = REPO_ROOT / ".orchestrate" / "runs"
    runs_digest = _tree_digest(runs_root)
    artifact_digest = _tree_digest(REPO_ROOT / "artifacts")
    source_text = protected_bytes[REVIEW_DESIGN_DOCS_ENTRY].decode("utf-8")

    def position(offset: int) -> dict[str, int]:
        prefix = source_text[:offset]
        return {
            "line": prefix.count("\n"),
            "character": len(prefix.rsplit("\n", 1)[-1]),
        }

    prompt_reference_start = source_text.index(
        "review-design-doc",
        source_text.index("(provider-result"),
    )
    prompt_reference_end = prompt_reference_start + len("review-design-doc")
    macro_reference_start = source_text.index(
        "review-revise-loop",
        source_text.index("(review-revise-loop"),
    )
    review_proc_ref_start = source_text.index(
        "review-design-docs",
        source_text.index("(proc-ref review-design-docs"),
    )
    fix_proc_ref_start = source_text.index(
        "fix-design-doc",
        source_text.index("(proc-ref fix-design-doc"),
    )
    direct_call_start = source_text.index(
        "build-review-runtime-owned",
        source_text.index("(call build-review-runtime-owned"),
    )
    fill_keyword_start = source_text.index(
        ":target_doc",
        prompt_reference_end,
    )
    adjacent_argument_start = source_text.index(
        "completed.target_doc",
        fill_keyword_start,
    )
    expected_prompt_definition = {
        "uri": REVIEW_DESIGN_DOCS_ENTRY.as_uri(),
        "range": {
            "start": {"line": 72, "character": 2},
            "end": {"line": 80, "character": 1666},
        },
    }
    expected_workflow_definition = {
        "uri": REVIEW_DESIGN_DOCS_ENTRY.as_uri(),
        "range": {
            "start": {"line": 32, "character": 2},
            "end": {"line": 39, "character": 48},
        },
    }

    process = _LspProcess(REPO_ROOT)
    try:
        _initialize(
            process,
            workspace=REPO_ROOT,
            initialization_options={
                "source_roots": [
                    str(REPO_ROOT / "workflows" / "examples")
                ],
                "provider_externs_path": str(REVIEW_DESIGN_DOCS_PROVIDERS),
                "prompt_externs_path": str(REVIEW_DESIGN_DOCS_PROMPTS),
            },
        )
        _open(
            process,
            source_path=REVIEW_DESIGN_DOCS_ENTRY,
            text=source_text,
        )

        prompt_definition, observed = _request_until(
            process,
            request_id=30,
            method="textDocument/definition",
            params={
                "textDocument": {
                    "uri": REVIEW_DESIGN_DOCS_ENTRY.as_uri(),
                },
                "position": position(prompt_reference_start + 1),
            },
            result_predicate=lambda result: result is not None,
            timeout=30.0,
        )
        assert prompt_definition["result"] == expected_prompt_definition
        assert prompt_definition["result"]["range"] != {
            "start": {"line": 72, "character": 13},
            "end": {"line": 72, "character": 30},
        }
        assert not any(
            item.get("method") == "textDocument/publishDiagnostics"
            and item["params"]["diagnostics"]
            for item in observed
        )

        request_id = 31
        cases = (
            (prompt_reference_start, expected_prompt_definition),
            (prompt_reference_end - 1, expected_prompt_definition),
            (prompt_reference_start - 1, None),
            (prompt_reference_end, None),
            (fill_keyword_start + 1, None),
            (adjacent_argument_start + 1, None),
            (macro_reference_start + 1, None),
            (review_proc_ref_start + 1, None),
            (fix_proc_ref_start + 1, None),
            (direct_call_start + 1, expected_workflow_definition),
            (direct_call_start - 1, None),
            (direct_call_start + len("build-review-runtime-owned"), None),
        )
        for offset, expected in cases:
            response, _ = _request(
                process,
                request_id=request_id,
                method="textDocument/definition",
                params={
                    "textDocument": {
                        "uri": REVIEW_DESIGN_DOCS_ENTRY.as_uri(),
                    },
                    "position": position(offset),
                },
            )
            assert response["result"] == expected
            request_id += 1
        process.shutdown()
    finally:
        process.close()

    assert {
        path: path.read_bytes()
        for path in protected_paths
    } == protected_bytes
    assert _tree_digest(REPO_ROOT / ".orchestrate" / "build") == build_digest
    assert _tree_digest(runs_root) == runs_digest
    assert _tree_digest(REPO_ROOT / "artifacts") == artifact_digest


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
            "importer",
            "Consumer",
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
        assert [item["name"] for item in helper_symbols["result"]] == [
            "helper",
            "Shared",
        ]
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
