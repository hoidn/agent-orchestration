"""Real-stdio integration coverage for the Workflow Lisp language server."""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

from tests.test_workflow_lisp_lsp_stdio import (
    _LspProcess,
    _initialize_request,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CALLABLE_ROOT = FIXTURES / "modules" / "valid" / "callables"
IMPORTED_SELECTOR_SOURCE = FIXTURES / "cli" / "imported_selector.orc"
STDLIB_CALLER_SOURCE = (
    FIXTURES / "valid" / "minimal_caller_finalize_selected_item.orc"
)
CONTROLLED_SERVER = (
    FIXTURES / "lsp_transport" / "controlled_compile_server.py"
)
STARTUP_STDOUT_PROBE_ROOT = (
    FIXTURES / "lsp_transport" / "startup_stdout_probe"
)


def _tree_snapshot(root: Path) -> tuple[tuple[str, str, bytes | str], ...]:
    entries: list[tuple[str, str, bytes | str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries.append((relative, "symlink", path.readlink().as_posix()))
        elif path.is_dir():
            entries.append((relative, "directory", ""))
        else:
            entries.append((relative, "file", path.read_bytes()))
    return tuple(entries)


def _request(
    process: _LspProcess,
    *,
    request_id: int | str,
    method: str,
    params: dict[str, object],
    timeout: float = 15.0,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    process.send(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
    )
    return process.read_until(
        lambda item: item.get("id") == request_id,
        timeout=timeout,
    )


def _request_until(
    process: _LspProcess,
    *,
    request_id: int | str,
    method: str,
    params: dict[str, object],
    result_predicate: Callable[[object], bool],
    timeout: float = 15.0,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    """Retry completed requests until one fresh result satisfies the caller."""

    deadline = time.monotonic() + timeout
    observed: list[dict[str, object]] = []
    attempt = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(
                f"timed out waiting for `{method}` result; observed={observed!r}"
            )
        attempt += 1
        response, attempt_observed = _request(
            process,
            request_id=f"{request_id}-attempt-{attempt}",
            method=method,
            params=params,
            timeout=remaining,
        )
        observed.extend(attempt_observed)
        if result_predicate(response.get("result")):
            return response, tuple(observed)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(
                f"timed out waiting for `{method}` result; observed={observed!r}"
            )
        time.sleep(min(0.01, remaining))


def _initialize(
    process: _LspProcess,
    *,
    workspace: Path,
    initialization_options: dict[str, object],
) -> None:
    process.send(
        _initialize_request(
            1,
            root_uri=workspace.as_uri(),
            workspace_folder_uris=(workspace.as_uri(),),
            initialization_options=initialization_options,
        )
    )
    response, _observed = process.read_until(
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


def _open(
    process: _LspProcess,
    *,
    source_path: Path,
    text: str,
    version: int = 1,
) -> None:
    process.send(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": source_path.as_uri(),
                    "languageId": "workflow-lisp",
                    "version": version,
                    "text": text,
                }
            },
        }
    )


def _change(
    process: _LspProcess,
    *,
    source_path: Path,
    text: str,
    version: int,
) -> None:
    process.send(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didChange",
            "params": {
                "textDocument": {
                    "uri": source_path.as_uri(),
                    "version": version,
                },
                "contentChanges": [{"text": text}],
            },
        }
    )


def _save_and_wait_for_diagnostics(
    process: _LspProcess,
    *,
    source_path: Path,
) -> dict[str, object]:
    process.send(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didSave",
            "params": {
                "textDocument": {"uri": source_path.as_uri()},
            },
        }
    )
    published, _observed = process.read_until(
        lambda item: (
            item.get("method") == "textDocument/publishDiagnostics"
            and item["params"]["uri"] == source_path.as_uri()
        ),
        timeout=30.0,
    )
    return published


def _fixture_workspace(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    shutil.copytree(CALLABLE_ROOT / "neurips", workspace / "neurips")
    config_root = workspace / "config"
    prompt_root = workspace / "prompts"
    config_root.mkdir()
    prompt_root.mkdir()
    imported_selector = workspace / "imported_selector.orc"
    imported_selector.write_text(
        IMPORTED_SELECTOR_SOURCE.read_text(encoding="utf-8").replace(
            "  (defmodule imported_selector)\n",
            (
                "  (defmodule imported_selector)\n"
                "  (import std/context :only (RunCtx))\n"
            ),
        ),
        encoding="utf-8",
    )
    (prompt_root / "execute.md").write_text(
        "Fixture prompt content.\n",
        encoding="utf-8",
    )
    (config_root / "providers.json").write_text(
        '{"providers.execute":"test-provider"}\n',
        encoding="utf-8",
    )
    (config_root / "prompts.json").write_text(
        '{"prompts.implementation.execute":"prompts/execute.md"}\n',
        encoding="utf-8",
    )
    (config_root / "commands.json").write_text(
        json.dumps(
            {
                "run_checks": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "scripts/run_checks.py",
                    ],
                }
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (config_root / "imports.json").write_text(
        json.dumps(
            {
                "selector-run": {
                    "kind": "compiled",
                    "path": "../imported_selector.orc",
                    "entry_workflow": "selector-run",
                }
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    entry_path = workspace / "neurips" / "entry.orc"
    return (
        workspace,
        entry_path,
        {
            "source_roots": [str(workspace)],
            "entry_workflow": "orchestrate",
            "provider_externs_path": str(config_root / "providers.json"),
            "prompt_externs_path": str(config_root / "prompts.json"),
            "command_boundaries_path": str(config_root / "commands.json"),
            "imported_workflow_bundles_path": str(
                config_root / "imports.json"
            ),
        },
    )


def _library_source(symbol_name: str) -> str:
    return (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.14")\n'
        "  (defmodule entry)\n"
        f"  (defproc {symbol_name}\n"
        "    ((value Bool))\n"
        "    -> Bool\n"
        "    :effects ()\n"
        "    :lowering inline\n"
        "    value))\n"
    )


def _wait_for_path(path: Path, *, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.01)
    return path.exists()


def _controlled_process(
    workspace: Path,
    *,
    control_root: Path,
) -> _LspProcess:
    return _LspProcess(
        workspace,
        server_command=(sys.executable, str(CONTROLLED_SERVER)),
        extra_environment={"WORKFLOW_LSP_TEST_CONTROL_ROOT": str(control_root)},
    )


def test_real_stdio_observes_and_coalesces_saves_while_first_compile_is_blocked(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    control_root = (tmp_path / "control").resolve()
    workspace.mkdir()
    control_root.mkdir()
    entry_path = workspace / "entry.orc"
    entry_path.write_text(_library_source("initial"), encoding="utf-8")
    process = _controlled_process(workspace, control_root=control_root)
    observed_before_release = False
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={"source_roots": [str(workspace)]},
        )
        _open(
            process,
            source_path=entry_path,
            text=entry_path.read_text(encoding="utf-8"),
        )
        assert _wait_for_path(control_root / "build-1-started")

        for version, module_name in enumerate(
            ("superseded-one", "superseded-two", "latest"),
            start=2,
        ):
            text = _library_source(module_name)
            entry_path.write_text(text, encoding="utf-8")
            _change(
                process,
                source_path=entry_path,
                text=text,
                version=version,
            )
            process.send(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didSave",
                    "params": {
                        "textDocument": {"uri": entry_path.as_uri()},
                    },
                }
            )

        observed_before_release = _wait_for_path(
            control_root / "save-3-observed"
        )
        (control_root / "release-first-build").touch()
        if observed_before_release:
            assert _wait_for_path(
                control_root / "build-2-finished",
                timeout=30.0,
            )
            symbols, _observed = _request_until(
                process,
                request_id=2,
                method="textDocument/documentSymbol",
                params={"textDocument": {"uri": entry_path.as_uri()}},
                result_predicate=lambda result: (
                    isinstance(result, list)
                    and [item.get("name") for item in result]
                    == ["entry", "latest"]
                ),
            )
            assert [item["name"] for item in symbols["result"]] == [
                "entry",
                "latest",
            ]
        process.shutdown()
    finally:
        (control_root / "release-first-build").touch(exist_ok=True)
        process.close()

    assert observed_before_release, (
        "the transport did not observe superseding saves while the first "
        "compile was blocked"
    )
    assert len(tuple(control_root.glob("build-*-started"))) == 2
    assert len(tuple(control_root.glob("build-*-finished"))) == 2


def test_real_stdio_close_discards_result_while_first_compile_is_blocked(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    control_root = (tmp_path / "control").resolve()
    workspace.mkdir()
    control_root.mkdir()
    entry_path = workspace / "entry.orc"
    entry_path.write_text(_library_source("closing"), encoding="utf-8")
    process = _controlled_process(workspace, control_root=control_root)
    observed_before_release = False
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={"source_roots": [str(workspace)]},
        )
        _open(
            process,
            source_path=entry_path,
            text=entry_path.read_text(encoding="utf-8"),
        )
        assert _wait_for_path(control_root / "build-1-started")
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didClose",
                "params": {
                    "textDocument": {"uri": entry_path.as_uri()},
                },
            }
        )

        observed_before_release = _wait_for_path(control_root / "close-observed")
        (control_root / "release-first-build").touch()
        if observed_before_release:
            assert _wait_for_path(
                control_root / "build-1-finished",
                timeout=30.0,
            )
            symbols, _observed = _request(
                process,
                request_id=2,
                method="textDocument/documentSymbol",
                params={"textDocument": {"uri": entry_path.as_uri()}},
            )
            assert symbols["result"] is None
        process.shutdown()
    finally:
        (control_root / "release-first-build").touch(exist_ok=True)
        process.close()

    assert observed_before_release, (
        "the transport did not observe close while the first compile was "
        "blocked"
    )
    assert len(tuple(control_root.glob("build-*-started"))) == 1
    assert len(tuple(control_root.glob("build-*-finished"))) == 1


def test_import_time_ordinary_stdout_cannot_precede_protocol_frames(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    pythonpath = os.pathsep.join(
        (str(STARTUP_STDOUT_PROBE_ROOT), str(REPO_ROOT))
    )
    process = _LspProcess(
        workspace,
        extra_environment={"PYTHONPATH": pythonpath},
    )
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={},
        )
        process.shutdown()
    finally:
        process.close()


def test_real_stdio_fixture_diagnostics_navigation_and_cleanup_write_nothing(
    tmp_path: Path,
) -> None:
    workspace, entry_path, options = _fixture_workspace(tmp_path)
    original_text = entry_path.read_text(encoding="utf-8")
    before = _tree_snapshot(workspace)
    process = _LspProcess(workspace)
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options=options,
        )
        _open(
            process,
            source_path=entry_path,
            text=original_text,
        )

        procedure_definition, _ = _request_until(
            process,
            request_id=2,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 12, "character": 14},
            },
            result_predicate=lambda result: result is not None,
        )
        assert procedure_definition["result"]["uri"] == (
            workspace / "neurips" / "procedures.orc"
        ).as_uri()

        workflow_definition, _ = _request(
            process,
            request_id=3,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 13, "character": 12},
            },
        )
        assert workflow_definition["result"]["uri"] == (
            workspace / "neurips" / "helper.orc"
        ).as_uri()

        symbols, _ = _request(
            process,
            request_id=4,
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": entry_path.as_uri()}},
        )
        assert [item["name"] for item in symbols["result"]] == [
            "neurips/entry",
            "orchestrate",
        ]

        completion, _ = _request(
            process,
            request_id=5,
            method="textDocument/completion",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 0, "character": 0},
            },
        )
        assert completion["result"]["isIncomplete"] is False
        assert tuple(
            (item["label"], item["detail"])
            for item in completion["result"]["items"]
            if item["kind"] == 3
        ) == (
            (
                "build-checks",
                "procedure "
                "(report_path: neurips/types::WorkReport) "
                "-> neurips/types::ChecksResult "
                "effects (uses-command(run_checks))",
            ),
            (
                "helper.provider-attempt",
                "workflow "
                "(input: neurips/types::ChecksResult, "
                "report_path: neurips/types::WorkReport) "
                "-> neurips/types::ImplementationSummary",
            ),
            (
                "helper.secondary",
                "workflow "
                "(input: neurips/types::ChecksResult, "
                "report_path: neurips/types::WorkReport) "
                "-> neurips/types::ImplementationSummary",
            ),
            (
                "neurips/helper/provider-attempt",
                "workflow "
                "(input: neurips/types::ChecksResult, "
                "report_path: neurips/types::WorkReport) "
                "-> neurips/types::ImplementationSummary",
            ),
            (
                "neurips/helper/secondary",
                "workflow "
                "(input: neurips/types::ChecksResult, "
                "report_path: neurips/types::WorkReport) "
                "-> neurips/types::ImplementationSummary",
            ),
            (
                "neurips/procedures/build-checks",
                "procedure "
                "(report_path: neurips/types::WorkReport) "
                "-> neurips/types::ChecksResult "
                "effects (uses-command(run_checks))",
            ),
            (
                "orchestrate",
                "workflow (report_path: neurips/types::WorkReport) "
                "-> neurips/types::ImplementationSummary",
            ),
            (
                "proc.build-checks",
                "procedure "
                "(report_path: neurips/types::WorkReport) "
                "-> neurips/types::ChecksResult "
                "effects (uses-command(run_checks))",
            ),
            (
                "provider-attempt",
                "workflow "
                "(input: neurips/types::ChecksResult, "
                "report_path: neurips/types::WorkReport) "
                "-> neurips/types::ImplementationSummary",
            ),
            (
                "secondary",
                "workflow "
                "(input: neurips/types::ChecksResult, "
                "report_path: neurips/types::WorkReport) "
                "-> neurips/types::ImplementationSummary",
            ),
        )

        broken_text = original_text.replace(
            "(proc.build-checks report_path)",
            "(proc.build-checks)",
        )
        _change(
            process,
            source_path=entry_path,
            text=broken_text,
            version=2,
        )
        dirty_definition, _ = _request(
            process,
            request_id=6,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 12, "character": 14},
            },
        )
        assert dirty_definition["result"] is None
        dirty_symbols, _ = _request(
            process,
            request_id=7,
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": entry_path.as_uri()}},
        )
        assert dirty_symbols["result"] is None
        dirty_completion, _ = _request(
            process,
            request_id=8,
            method="textDocument/completion",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 0, "character": 0},
            },
        )
        assert dirty_completion["result"] == {
            "isIncomplete": False,
            "items": [],
        }

        entry_path.write_text(broken_text, encoding="utf-8")
        broken = _save_and_wait_for_diagnostics(
            process,
            source_path=entry_path,
        )
        diagnostics = broken["params"]["diagnostics"]
        assert len(diagnostics) == 1
        assert diagnostics[0]["code"]
        assert diagnostics[0]["data"]["phase"]

        _change(
            process,
            source_path=entry_path,
            text=original_text,
            version=3,
        )
        entry_path.write_text(original_text, encoding="utf-8")
        cleared = _save_and_wait_for_diagnostics(
            process,
            source_path=entry_path,
        )
        assert cleared["params"]["diagnostics"] == []

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didClose",
                "params": {
                    "textDocument": {"uri": entry_path.as_uri()},
                },
            }
        )
        closed_definition, _ = _request(
            process,
            request_id=9,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 12, "character": 14},
            },
        )
        assert closed_definition["result"] is None
        process.shutdown()
    finally:
        process.close()

    assert _tree_snapshot(workspace) == before
    assert not (workspace / ".orchestrate").exists()


def test_real_stdio_dependency_invalidation_and_rapid_saves_keep_latest_state(
    tmp_path: Path,
) -> None:
    workspace, entry_path, options = _fixture_workspace(tmp_path)
    entry_text = entry_path.read_text(encoding="utf-8")
    helper_path = workspace / "neurips" / "helper.orc"
    helper_text = helper_path.read_text(encoding="utf-8")
    before = _tree_snapshot(workspace)
    process = _LspProcess(workspace)
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options=options,
        )
        _open(process, source_path=entry_path, text=entry_text)
        initial_definition, _ = _request_until(
            process,
            request_id=2,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 13, "character": 12},
            },
            result_predicate=lambda result: result is not None,
        )
        assert initial_definition["result"]["uri"] == helper_path.as_uri()

        helper_path.write_text(helper_text + "\n(", encoding="utf-8")
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeWatchedFiles",
                "params": {
                    "changes": [
                        {"uri": helper_path.as_uri(), "type": 2},
                    ]
                },
            }
        )
        imported_error, _ = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == helper_path.as_uri()
            ),
            timeout=30.0,
        )
        assert len(imported_error["params"]["diagnostics"]) == 1

        helper_path.write_text(helper_text, encoding="utf-8")
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeWatchedFiles",
                "params": {
                    "changes": [
                        {"uri": helper_path.as_uri(), "type": 2},
                    ]
                },
            }
        )
        imported_clear, _ = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == helper_path.as_uri()
            ),
            timeout=30.0,
        )
        assert imported_clear["params"]["diagnostics"] == []

        rapid_texts = (
            entry_text + "\n; superseded rapid save one\n",
            entry_text + "\n; superseded rapid save two\n",
            entry_text,
        )
        for version, text in enumerate(rapid_texts, start=2):
            _change(
                process,
                source_path=entry_path,
                text=text,
                version=version,
            )
            entry_path.write_text(text, encoding="utf-8")
            process.send(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didSave",
                    "params": {
                        "textDocument": {"uri": entry_path.as_uri()},
                    },
                }
            )

        current_definition, observed = _request_until(
            process,
            request_id=3,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 13, "character": 12},
            },
            result_predicate=lambda result: result is not None,
        )
        assert current_definition["result"]["uri"] == helper_path.as_uri()
        assert not any(
            item.get("method") == "window/logMessage"
            and item.get("params", {}).get("type") == 1
            for item in observed
        )
        process.shutdown()
    finally:
        process.close()

    assert _tree_snapshot(workspace) == before
    assert not (workspace / ".orchestrate").exists()


def test_real_stdio_changed_helper_save_invalidates_importer_without_watcher(
    tmp_path: Path,
) -> None:
    workspace, entry_path, options = _fixture_workspace(tmp_path)
    entry_text = entry_path.read_text(encoding="utf-8")
    helper_path = workspace / "neurips" / "helper.orc"
    helper_text = helper_path.read_text(encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options=options,
        )
        _open(process, source_path=entry_path, text=entry_text)
        initial_definition, _ = _request_until(
            process,
            request_id=2,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 13, "character": 12},
            },
            result_predicate=lambda result: result is not None,
        )
        assert initial_definition["result"]["uri"] == helper_path.as_uri()

        _open(process, source_path=helper_path, text=helper_text)
        helper_initial_diagnostics, _ = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == helper_path.as_uri()
            ),
            timeout=30.0,
        )
        assert helper_initial_diagnostics["params"]["diagnostics"]

        changed_helper = helper_text.replace(
            "provider-attempt",
            "provider-attempt-renamed",
        )
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

        importer_diagnostics, _ = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == entry_path.as_uri()
                and bool(item["params"]["diagnostics"])
            ),
            timeout=30.0,
        )
        assert importer_diagnostics["params"]["diagnostics"]
        process.shutdown()
    finally:
        process.close()


def test_real_stdio_definition_reaches_compiler_owned_builtin_stdlib(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    source_path = workspace / STDLIB_CALLER_SOURCE.name
    shutil.copyfile(STDLIB_CALLER_SOURCE, source_path)
    source_text = source_path.read_text(encoding="utf-8")
    before = _tree_snapshot(workspace)
    process = _LspProcess(workspace)
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={"source_roots": [str(workspace)]},
        )
        _open(process, source_path=source_path, text=source_text)
        definition, _ = _request_until(
            process,
            request_id=2,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": source_path.as_uri()},
                "position": {"line": 41, "character": 7},
            },
            result_predicate=lambda result: result is not None,
        )

        assert definition["result"]["uri"] == (
            REPO_ROOT
            / "orchestrator"
            / "workflow_lisp"
            / "stdlib_modules"
            / "std"
            / "resource.orc"
        ).resolve().as_uri()
        process.shutdown()
    finally:
        process.close()

    assert _tree_snapshot(workspace) == before
    assert not (workspace / ".orchestrate").exists()


def test_built_wheel_contains_lsp_and_compiler_owned_builtin_stdlib(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    wheel_root = tmp_path / "wheel"
    source_root.mkdir()
    wheel_root.mkdir()
    shutil.copyfile(REPO_ROOT / "pyproject.toml", source_root / "pyproject.toml")
    shutil.copyfile(REPO_ROOT / "LICENSE.md", source_root / "LICENSE.md")
    shutil.copytree(
        REPO_ROOT / "orchestrator",
        source_root / "orchestrator",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    environment = dict(os.environ)
    environment["PIP_NO_INDEX"] = "1"

    built = subprocess.run(
        (
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_root),
            str(source_root),
        ),
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert built.returncode == 0, built.stderr
    wheels = tuple(wheel_root.glob("orchestrator-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        members = set(archive.namelist())
    assert {
        "orchestrator/lsp/__main__.py",
        "orchestrator/lsp/server.py",
    }.issubset(members)
    assert {
        (
            "orchestrator/workflow_lisp/stdlib_modules/std/"
            f"{module_name}.orc"
        )
        for module_name in ("context", "drain", "phase", "resource")
    }.issubset(members)
