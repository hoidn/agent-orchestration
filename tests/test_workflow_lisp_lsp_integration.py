"""Real-stdio integration coverage for the Workflow Lisp language server."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Event
import time
import zipfile

import pytest

from orchestrator.workflow_lisp.form_registry import registered_form_heads
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
L3_ENTRY_SELECTION_ROOT = (
    FIXTURES
    / "modules"
    / "valid"
    / "lsp_l3_entry_selection"
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
    capabilities: dict[str, object] | None = None,
) -> None:
    process.send(
        _initialize_request(
            1,
            root_uri=workspace.as_uri(),
            workspace_folder_uris=(workspace.as_uri(),),
            initialization_options=initialization_options,
            capabilities=capabilities,
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


def _progress_support_capability(
    supported: bool,
) -> dict[str, object]:
    return {"window": {"workDoneProgress": supported}}


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


def _frozen_form_completion_items() -> list[dict[str, object]]:
    return [
        {
            "label": head,
            "kind": 14,
            "detail": "form",
            "sortText": head,
        }
        for head in registered_form_heads(target_dsl_version=None)
    ]


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
            "entry_workflows": {str(entry_path): "orchestrate"},
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


def _stateful_recompile_source(
    *,
    record_name: str,
    helper_name: str,
    value: str,
    invalid: bool = False,
) -> str:
    final_value = "missing-after-state" if invalid else "transformed"
    return (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.15")\n'
        "  (defmodule entry)\n"
        f"  (export {record_name} {helper_name} run)\n"
        f"  (defrecord {record_name} (value String))\n"
        f"  (defproc {helper_name}\n"
        "    ((value String))\n"
        "    -> String\n"
        "    :effects ()\n"
        "    :lowering inline\n"
        "    value)\n"
        f"  (defworkflow run () -> {record_name}\n"
        f'    (let* ((state (loop-state (value String "{value}")))\n'
        f"           (transformed ({helper_name} state.value)))\n"
        f"      (record {record_name} :value {final_value}))))\n"
    )


def _current_document_surface(
    process: _LspProcess,
    *,
    source_path: Path,
    request_id_prefix: str,
    expected_helper_name: str,
) -> dict[str, object]:
    symbols, symbol_observed = _request_until(
        process,
        request_id=f"{request_id_prefix}-symbols",
        method="textDocument/documentSymbol",
        params={"textDocument": {"uri": source_path.as_uri()}},
        result_predicate=lambda result: (
            isinstance(result, list)
            and expected_helper_name
            in {
                item.get("name")
                for item in result
                if isinstance(item, dict)
            }
        ),
    )
    completion, completion_observed = _request_until(
        process,
        request_id=f"{request_id_prefix}-completion",
        method="textDocument/completion",
        params={
            "textDocument": {"uri": source_path.as_uri()},
            "position": {"line": 0, "character": 0},
        },
        result_predicate=lambda result: (
            isinstance(result, dict)
            and expected_helper_name
            in {
                item.get("label")
                for item in result.get("items", ())
                if isinstance(item, dict)
            }
        ),
    )
    published_diagnostics = [
        item["params"]["diagnostics"]
        for item in (*symbol_observed, *completion_observed)
        if (
            item.get("method") == "textDocument/publishDiagnostics"
            and item["params"]["uri"] == source_path.as_uri()
        )
    ]
    return {
        "diagnostics": (
            published_diagnostics[-1]
            if published_diagnostics
            else []
        ),
        "symbols": symbols["result"],
        "completion": completion["result"],
    }


def _l3_position(source_text: str, offset: int) -> dict[str, int]:
    prefix = source_text[:offset]
    return {
        "line": prefix.count("\n"),
        "character": len(prefix.rsplit("\n", 1)[-1]),
    }


def _l3_current_protocol_surface(
    process: _LspProcess,
    *,
    source_path: Path,
    request_id_prefix: str,
) -> dict[str, object]:
    source_text = source_path.read_text(encoding="utf-8")
    helper_name = (
        "application-helper"
        if source_path.name == "application.orc"
        else "library-helper"
    )
    surface = _current_document_surface(
        process,
        source_path=source_path,
        request_id_prefix=request_id_prefix,
        expected_helper_name=helper_name,
    )
    if source_path.name == "application.orc":
        call_offset = source_text.index(
            "application-helper",
            source_text.index("(defworkflow selected"),
        )
        definition, definition_observed = _request_until(
            process,
            request_id=f"{request_id_prefix}-definition",
            method="textDocument/definition",
            params={
                "textDocument": {"uri": source_path.as_uri()},
                "position": _l3_position(source_text, call_offset + 1),
            },
            result_predicate=lambda result: result is not None,
        )
    else:
        definition, definition_observed = _request(
            process,
            request_id=f"{request_id_prefix}-definition",
            method="textDocument/definition",
            params={
                "textDocument": {"uri": source_path.as_uri()},
                "position": {"line": 0, "character": 0},
            },
        )
    assert "error" not in definition
    additional_diagnostics = [
        item["params"]["diagnostics"]
        for item in definition_observed
        if (
            item.get("method") == "textDocument/publishDiagnostics"
            and item["params"]["uri"] == source_path.as_uri()
        )
    ]
    if additional_diagnostics:
        surface["diagnostics"] = additional_diagnostics[-1]
    surface["definition"] = definition["result"]
    return surface


def _l3_stdio_session(
    workspace: Path,
    *,
    source_order: tuple[Path, ...],
    request_id_prefix: str,
) -> dict[Path, dict[str, object]]:
    application_path = workspace / "application.orc"
    process = _LspProcess(workspace)
    surfaces: dict[Path, dict[str, object]] = {}
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={
                "source_roots": [str(workspace)],
                "entry_workflows": {
                    str(application_path): "selected",
                },
            },
        )
        for index, source_path in enumerate(source_order, start=1):
            _open(
                process,
                source_path=source_path,
                text=source_path.read_text(encoding="utf-8"),
            )
            surfaces[source_path] = _l3_current_protocol_surface(
                process,
                source_path=source_path,
                request_id_prefix=(
                    f"{request_id_prefix}-{index}-{source_path.stem}"
                ),
            )
        process.shutdown()
    finally:
        process.close()
    return surfaces


@pytest.mark.parametrize(
    "source_names",
    (
        ("application.orc", "library.orc"),
        ("library.orc", "application.orc"),
    ),
    ids=("application-then-library", "library-then-application"),
)
def test_l3_real_stdio_mixed_entries_match_isolated_peers_without_bleed(
    tmp_path: Path,
    source_names: tuple[str, str],
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    shutil.copytree(L3_ENTRY_SELECTION_ROOT, workspace)
    application_path = workspace / "application.orc"
    library_path = workspace / "library.orc"
    source_order = tuple(workspace / name for name in source_names)
    before = _tree_snapshot(workspace)

    combined = _l3_stdio_session(
        workspace,
        source_order=source_order,
        request_id_prefix="combined",
    )
    isolated = {
        source_path: _l3_stdio_session(
            workspace,
            source_order=(source_path,),
            request_id_prefix=f"isolated-{source_path.stem}",
        )[source_path]
        for source_path in (application_path, library_path)
    }

    assert combined == isolated
    assert combined[application_path]["diagnostics"] == []
    assert combined[library_path]["diagnostics"] == []
    application_symbols = {
        item["name"]
        for item in combined[application_path]["symbols"]
    }
    library_symbols = {
        item["name"]
        for item in combined[library_path]["symbols"]
    }
    assert application_symbols == {
        "application",
        "application-helper",
        "first",
        "selected",
    }
    assert library_symbols == {
        "library",
        "library-helper",
    }
    application_completions = {
        item["label"]
        for item in combined[application_path]["completion"]["items"]
    }
    library_completions = {
        item["label"]
        for item in combined[library_path]["completion"]["items"]
    }
    assert "application-helper" in application_completions
    assert "library-helper" not in application_completions
    assert "library-helper" in library_completions
    assert "application-helper" not in library_completions
    assert combined[application_path]["definition"] == {
        "uri": application_path.as_uri(),
        "range": {
            "start": {"line": 5, "character": 2},
            "end": {"line": 10, "character": 10},
        },
    }
    assert combined[library_path]["definition"] is None
    assert _tree_snapshot(workspace) == before
    assert not (workspace / ".orchestrate").exists()


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


def _direct_busy_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_text: str,
    build_in_memory: Callable[..., object],
) -> tuple[
    "WorkflowLispLanguageServer",
    Path,
    list[str],
    list[Exception],
]:
    from lsprotocol import types

    from orchestrator.lsp.compile_driver import probe_disk_source
    from orchestrator.lsp.progress import ProgressController
    from orchestrator.lsp.server import WorkflowLispLanguageServer
    from orchestrator.lsp.state import open_entry

    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    entry_path.write_text(source_text, encoding="utf-8")
    logged: list[Exception] = []
    server = WorkflowLispLanguageServer(
        build_in_memory=build_in_memory,
        _defer_compiles=True,
    )
    monkeypatch.setattr(server, "log_internal_error", logged.append)
    server.initialize_runtime(
        types.InitializeParams(
            capabilities=types.ClientCapabilities(
                window=types.WindowClientCapabilities(
                    work_done_progress=False,
                )
            ),
            root_uri=workspace.as_uri(),
            initialization_options={
                "source_roots": [str(workspace)],
            },
        )
    )
    driver = server._require_driver()
    transition = open_entry(
        driver.state,
        document_uri=entry_path.as_uri(),
        editor_text=source_text,
        disk_snapshot=probe_disk_source(entry_path),
    )
    driver.apply_transition(transition)
    creating = ProgressController(supported=True).observe_busy(True).controller
    active = creating.create_succeeded(
        token="workflow-lisp-progress-1",
        interval=1,
    ).controller
    server.progress_controller = active
    server.work_done_progress.tokens[
        "workflow-lisp-progress-1"
    ] = object()  # type: ignore[assignment]
    ended: list[str] = []
    monkeypatch.setattr(
        server.work_done_progress,
        "end",
        lambda token, _value: ended.append(str(token)),
    )
    monkeypatch.setattr(
        server,
        "text_document_publish_diagnostics",
        lambda _params: None,
    )
    monkeypatch.setattr(server, "window_show_message", lambda _params: None)
    monkeypatch.setattr(server, "window_log_message", lambda _params: None)
    return server, entry_path, ended, logged


def _entry_status(
    server: "WorkflowLispLanguageServer",
    entry_path: Path,
) -> str:
    return next(
        entry.compile_status
        for entry in server._require_driver().state.entries
        if entry.path == entry_path
    )


def _assert_direct_progress_settled(
    server: "WorkflowLispLanguageServer",
    ended: list[str],
) -> None:
    from orchestrator.lsp.progress import Inactive

    assert server.progress_controller.state == Inactive()
    assert ended == ["workflow-lisp-progress-1"]
    assert (
        "workflow-lisp-progress-1"
        not in server.work_done_progress.tokens
    )


def test_language_error_completion_settles_production_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp.build import (
        build_frontend_bundle_in_memory,
    )

    server, entry_path, ended, _logged = _direct_busy_server(
        tmp_path,
        monkeypatch,
        source_text="(workflow-lisp",
        build_in_memory=build_frontend_bundle_in_memory,
    )

    asyncio.run(server._run_compile_pump())

    assert _entry_status(server, entry_path) == "language_error"
    _assert_direct_progress_settled(server, ended)


def test_server_error_completion_settles_production_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_build(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("controlled server error")

    server, entry_path, ended, logged = _direct_busy_server(
        tmp_path,
        monkeypatch,
        source_text=_library_source("server-error"),
        build_in_memory=fail_build,
    )

    asyncio.run(server._run_compile_pump())

    assert _entry_status(server, entry_path) == "server_error"
    assert [str(error) for error in logged] == ["controlled server error"]
    _assert_direct_progress_settled(server, ended)


def test_configuration_staleness_settles_production_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lsprotocol import types

    from orchestrator.workflow_lisp.build import (
        build_frontend_bundle_in_memory,
    )

    server, _entry_path, ended, _logged = _direct_busy_server(
        tmp_path,
        monkeypatch,
        source_text=_library_source("configuration-stale"),
        build_in_memory=build_frontend_bundle_in_memory,
    )
    added_root = (tmp_path / "other-root").resolve()
    added_root.mkdir()

    server.change_workspace_folders(
        types.DidChangeWorkspaceFoldersParams(
            event=types.WorkspaceFoldersChangeEvent(
                added=(
                    types.WorkspaceFolder(
                        uri=added_root.as_uri(),
                        name="other-root",
                    ),
                ),
                removed=(),
            )
        )
    )

    assert server._require_driver().state.configuration_stale is True
    _assert_direct_progress_settled(server, ended)


def test_transient_pump_exception_settles_then_retries_queued_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp.build import (
        build_frontend_bundle_in_memory,
    )

    server, entry_path, ended, logged = _direct_busy_server(
        tmp_path,
        monkeypatch,
        source_text=_library_source("pump-error"),
        build_in_memory=build_frontend_bundle_in_memory,
    )
    driver = server._require_driver()
    original_begin_next = type(driver).begin_next
    attempts = 0

    def fail_once_then_begin(driver_value: object) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("unexpected pump failure")
        return original_begin_next(driver_value)  # type: ignore[arg-type]

    monkeypatch.setattr(
        type(driver),
        "begin_next",
        fail_once_then_begin,
    )

    async def ignore_create(*, token: str, interval: int) -> None:
        assert token == "workflow-lisp-progress-2"
        assert interval == 2

    monkeypatch.setattr(server, "_create_progress_token", ignore_create)

    async def run_initial_and_retry() -> None:
        await server._run_compile_pump()
        retry = server._compile_task
        assert retry is not None
        await retry

    asyncio.run(run_initial_and_retry())

    assert _entry_status(server, entry_path) == "success"
    assert driver.queued_generations == ()
    assert [str(error) for error in logged] == [
        "unexpected pump failure"
    ]
    _assert_direct_progress_settled(server, ended)


def test_pump_exception_logger_failure_still_settles_and_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp.build import (
        build_frontend_bundle_in_memory,
    )

    server, entry_path, ended, _logged = _direct_busy_server(
        tmp_path,
        monkeypatch,
        source_text=_library_source("pump-logger-error"),
        build_in_memory=build_frontend_bundle_in_memory,
    )
    driver = server._require_driver()
    original_begin_next = type(driver).begin_next
    attempts = 0

    def fail_once_then_begin(driver_value: object) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("unexpected pump failure")
        return original_begin_next(driver_value)  # type: ignore[arg-type]

    monkeypatch.setattr(
        type(driver),
        "begin_next",
        fail_once_then_begin,
    )

    def fail_logger(_error: Exception) -> None:
        raise RuntimeError("server logger unavailable")

    monkeypatch.setattr(server, "log_internal_error", fail_logger)

    async def ignore_create(*, token: str, interval: int) -> None:
        assert token == "workflow-lisp-progress-2"
        assert interval == 2

    monkeypatch.setattr(server, "_create_progress_token", ignore_create)

    async def run_initial_and_retry() -> None:
        await server._run_compile_pump()
        retry = server._compile_task
        assert retry is not None
        await retry

    asyncio.run(run_initial_and_retry())

    assert _entry_status(server, entry_path) == "success"
    assert driver.queued_generations == ()
    _assert_direct_progress_settled(server, ended)


def test_pump_cancellation_settles_then_preserves_queued_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp.build import (
        build_frontend_bundle_in_memory,
    )

    server, entry_path, ended, logged = _direct_busy_server(
        tmp_path,
        monkeypatch,
        source_text=_library_source("pump-cancel-retry"),
        build_in_memory=build_frontend_bundle_in_memory,
    )
    driver = server._require_driver()
    original_begin_next = type(driver).begin_next
    attempts = 0

    def cancel_once_then_begin(driver_value: object) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise asyncio.CancelledError
        return original_begin_next(driver_value)  # type: ignore[arg-type]

    monkeypatch.setattr(
        type(driver),
        "begin_next",
        cancel_once_then_begin,
    )

    async def ignore_create(*, token: str, interval: int) -> None:
        assert token == "workflow-lisp-progress-2"
        assert interval == 2

    monkeypatch.setattr(server, "_create_progress_token", ignore_create)

    async def run_canceled_and_retry() -> None:
        with pytest.raises(asyncio.CancelledError):
            await server._run_compile_pump()
        retry = server._compile_task
        assert retry is not None
        await retry

    asyncio.run(run_canceled_and_retry())

    assert _entry_status(server, entry_path) == "success"
    assert driver.queued_generations == ()
    assert logged == []
    _assert_direct_progress_settled(server, ended)


def test_pump_task_cancellation_settles_before_worker_returns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow_lisp.build import (
        build_frontend_bundle_in_memory,
    )

    started = Event()
    release = Event()

    def blocked_build(*args: object, **kwargs: object) -> object:
        started.set()
        if not release.wait(timeout=10.0):
            raise TimeoutError("test did not release direct blocked build")
        return build_frontend_bundle_in_memory(*args, **kwargs)

    server, _entry_path, ended, _logged = _direct_busy_server(
        tmp_path,
        monkeypatch,
        source_text=_library_source("pump-cancel"),
        build_in_memory=blocked_build,
    )

    async def cancel_running_pump() -> None:
        task = asyncio.create_task(server._run_compile_pump())
        while not started.is_set():
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert release.is_set() is False
        _assert_direct_progress_settled(server, ended)
        release.set()
        await asyncio.sleep(0)

    try:
        asyncio.run(cancel_running_pump())
    finally:
        release.set()


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


@pytest.mark.parametrize("advertised", (None, False))
def test_blocked_compile_without_progress_support_emits_no_progress_frames(
    tmp_path: Path,
    advertised: bool | None,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    control_root = (tmp_path / "control").resolve()
    workspace.mkdir()
    control_root.mkdir()
    entry_path = workspace / "entry.orc"
    entry_path.write_text(_library_source("unsupported"), encoding="utf-8")
    process = _controlled_process(workspace, control_root=control_root)
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={"source_roots": [str(workspace)]},
            capabilities=(
                None
                if advertised is None
                else _progress_support_capability(advertised)
            ),
        )
        _open(
            process,
            source_path=entry_path,
            text=entry_path.read_text(encoding="utf-8"),
        )
        assert _wait_for_path(control_root / "build-1-started")
        response, observed = _request(
            process,
            request_id="unsupported-progress-probe",
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": entry_path.as_uri()}},
        )
        assert response["result"] is None
        assert not any(
            item.get("method")
            in {"window/workDoneProgress/create", "$/progress"}
            for item in observed
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didClose",
                "params": {
                    "textDocument": {"uri": entry_path.as_uri()},
                },
            }
        )
        (control_root / "release-first-build").touch()
        assert _wait_for_path(
            control_root / "build-1-finished",
            timeout=30.0,
        )
        process.shutdown()
    finally:
        (control_root / "release-first-build").touch(exist_ok=True)
        process.close()


def test_supporting_client_gets_balanced_progress_while_compile_stays_live(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    control_root = (tmp_path / "control").resolve()
    workspace.mkdir()
    control_root.mkdir()
    entry_path = workspace / "entry.orc"
    entry_path.write_text(_library_source("supported"), encoding="utf-8")
    process = _controlled_process(workspace, control_root=control_root)
    observed: list[dict[str, object]] = []
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={"source_roots": [str(workspace)]},
            capabilities=_progress_support_capability(True),
        )
        _open(
            process,
            source_path=entry_path,
            text=entry_path.read_text(encoding="utf-8"),
        )
        create, create_observed = process.read_until(
            lambda item: (
                item.get("method") == "window/workDoneProgress/create"
            )
        )
        observed.extend(create_observed)
        assert _wait_for_path(control_root / "build-1-started")
        token = create["params"]["token"]
        process.send(
            {
                "jsonrpc": "2.0",
                "id": create["id"],
                "result": None,
            }
        )
        begin, begin_observed = process.read_until(
            lambda item: (
                item.get("method") == "$/progress"
                and item["params"]["token"] == token
                and item["params"]["value"]["kind"] == "begin"
            )
        )
        observed.extend(begin_observed)
        assert begin["params"]["value"]["cancellable"] is False
        assert "percentage" not in begin["params"]["value"]

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didClose",
                "params": {
                    "textDocument": {"uri": entry_path.as_uri()},
                },
            }
        )
        end, end_observed = process.read_until(
            lambda item: (
                item.get("method") == "$/progress"
                and item["params"]["token"] == token
                and item["params"]["value"]["kind"] == "end"
            )
        )
        observed.extend(end_observed)
        assert end["params"]["token"] == token
        assert not (control_root / "build-1-finished").exists()

        (control_root / "release-first-build").touch()
        assert _wait_for_path(
            control_root / "build-1-finished",
            timeout=30.0,
        )
        process.shutdown()
    finally:
        (control_root / "release-first-build").touch(exist_ok=True)
        process.close()

    progress_values = [
        item["params"]["value"]
        for item in observed
        if item.get("method") == "$/progress"
    ]
    assert [value["kind"] for value in progress_values] == ["begin", "end"]


def test_progress_create_error_suppresses_frames_without_stalling_compile(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    control_root = (tmp_path / "control").resolve()
    workspace.mkdir()
    control_root.mkdir()
    entry_path = workspace / "entry.orc"
    entry_path.write_text(_library_source("create-error"), encoding="utf-8")
    process = _controlled_process(workspace, control_root=control_root)
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={"source_roots": [str(workspace)]},
            capabilities=_progress_support_capability(True),
        )
        _open(
            process,
            source_path=entry_path,
            text=entry_path.read_text(encoding="utf-8"),
        )
        create, _observed = process.read_until(
            lambda item: (
                item.get("method") == "window/workDoneProgress/create"
            )
        )
        assert _wait_for_path(control_root / "build-1-started")
        process.send(
            {
                "jsonrpc": "2.0",
                "id": create["id"],
                "error": {
                    "code": -32000,
                    "message": "test client refuses progress",
                },
            }
        )
        (control_root / "release-first-build").touch()
        assert _wait_for_path(
            control_root / "build-1-finished",
            timeout=30.0,
        )
        response, observed = _request_until(
            process,
            request_id="create-error-settled",
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": entry_path.as_uri()}},
            result_predicate=lambda value: isinstance(value, list),
        )
        assert [item["name"] for item in response["result"]] == [
            "entry",
            "create-error",
        ]
        assert not any(
            item.get("method") == "$/progress" for item in observed
        )
        process.shutdown()
    finally:
        (control_root / "release-first-build").touch(exist_ok=True)
        process.close()


def test_client_progress_cancel_ends_only_presentation(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    control_root = (tmp_path / "control").resolve()
    workspace.mkdir()
    control_root.mkdir()
    entry_path = workspace / "entry.orc"
    entry_path.write_text(_library_source("cancel-view"), encoding="utf-8")
    process = _controlled_process(workspace, control_root=control_root)
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={"source_roots": [str(workspace)]},
            capabilities=_progress_support_capability(True),
        )
        _open(
            process,
            source_path=entry_path,
            text=entry_path.read_text(encoding="utf-8"),
        )
        create, _observed = process.read_until(
            lambda item: (
                item.get("method") == "window/workDoneProgress/create"
            )
        )
        token = create["params"]["token"]
        process.send(
            {
                "jsonrpc": "2.0",
                "id": create["id"],
                "result": None,
            }
        )
        process.read_until(
            lambda item: (
                item.get("method") == "$/progress"
                and item["params"]["token"] == token
                and item["params"]["value"]["kind"] == "begin"
            )
        )
        assert _wait_for_path(control_root / "build-1-started")
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "window/workDoneProgress/cancel",
                "params": {"token": token},
            }
        )
        process.read_until(
            lambda item: (
                item.get("method") == "$/progress"
                and item["params"]["token"] == token
                and item["params"]["value"]["kind"] == "end"
            )
        )
        assert not (control_root / "build-1-finished").exists()

        (control_root / "release-first-build").touch()
        assert _wait_for_path(
            control_root / "build-1-finished",
            timeout=30.0,
        )
        response, after_cancel = _request_until(
            process,
            request_id="cancel-view-settled",
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": entry_path.as_uri()}},
            result_predicate=lambda value: isinstance(value, list),
        )
        assert [item["name"] for item in response["result"]] == [
            "entry",
            "cancel-view",
        ]
        assert not any(
            item.get("method") == "$/progress" for item in after_cancel
        )
        process.shutdown()
    finally:
        (control_root / "release-first-build").touch(exist_ok=True)
        process.close()


def test_superseding_save_storm_reuses_one_progress_interval(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    control_root = (tmp_path / "control").resolve()
    workspace.mkdir()
    control_root.mkdir()
    entry_path = workspace / "entry.orc"
    entry_path.write_text(_library_source("initial-progress"), encoding="utf-8")
    process = _controlled_process(workspace, control_root=control_root)
    observed: list[dict[str, object]] = []
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={"source_roots": [str(workspace)]},
            capabilities=_progress_support_capability(True),
        )
        _open(
            process,
            source_path=entry_path,
            text=entry_path.read_text(encoding="utf-8"),
        )
        create, create_observed = process.read_until(
            lambda item: (
                item.get("method") == "window/workDoneProgress/create"
            )
        )
        observed.extend(create_observed)
        token = create["params"]["token"]
        process.send(
            {
                "jsonrpc": "2.0",
                "id": create["id"],
                "result": None,
            }
        )
        _begin, begin_observed = process.read_until(
            lambda item: (
                item.get("method") == "$/progress"
                and item["params"]["value"]["kind"] == "begin"
            )
        )
        observed.extend(begin_observed)
        assert _wait_for_path(control_root / "build-1-started")

        for _index in range(2):
            process.send(
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didSave",
                    "params": {
                        "textDocument": {"uri": entry_path.as_uri()},
                    },
                }
            )
        assert _wait_for_path(control_root / "save-2-observed")
        (control_root / "release-first-build").touch()
        end, end_observed = process.read_until(
            lambda item: (
                item.get("method") == "$/progress"
                and item["params"]["token"] == token
                and item["params"]["value"]["kind"] == "end"
            ),
            timeout=30.0,
        )
        observed.extend(end_observed)
        assert end["params"]["token"] == token
        assert _wait_for_path(
            control_root / "build-2-finished",
            timeout=30.0,
        )
        observed.extend(process.shutdown())
    finally:
        (control_root / "release-first-build").touch(exist_ok=True)
        process.close()

    creates = [
        item
        for item in observed
        if item.get("method") == "window/workDoneProgress/create"
    ]
    progress_values = [
        item["params"]["value"]
        for item in observed
        if item.get("method") == "$/progress"
    ]
    assert len(creates) == 1
    assert [value["kind"] for value in progress_values] == ["begin", "end"]


def test_other_pending_entry_keeps_progress_open_after_first_closes(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    control_root = (tmp_path / "control").resolve()
    workspace.mkdir()
    control_root.mkdir()
    first_path = workspace / "first.orc"
    second_path = workspace / "second.orc"
    first_path.write_text(_library_source("first"), encoding="utf-8")
    second_path.write_text(_library_source("second"), encoding="utf-8")
    process = _controlled_process(workspace, control_root=control_root)
    try:
        _initialize(
            process,
            workspace=workspace,
            initialization_options={"source_roots": [str(workspace)]},
            capabilities=_progress_support_capability(True),
        )
        _open(
            process,
            source_path=first_path,
            text=first_path.read_text(encoding="utf-8"),
        )
        create, _observed = process.read_until(
            lambda item: (
                item.get("method") == "window/workDoneProgress/create"
            )
        )
        token = create["params"]["token"]
        process.send(
            {
                "jsonrpc": "2.0",
                "id": create["id"],
                "result": None,
            }
        )
        process.read_until(
            lambda item: (
                item.get("method") == "$/progress"
                and item["params"]["value"]["kind"] == "begin"
            )
        )
        assert _wait_for_path(control_root / "build-1-started")
        _open(
            process,
            source_path=second_path,
            text=second_path.read_text(encoding="utf-8"),
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didClose",
                "params": {
                    "textDocument": {"uri": first_path.as_uri()},
                },
            }
        )
        response, while_blocked = _request(
            process,
            request_id="second-still-pending",
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": second_path.as_uri()}},
        )
        assert response["result"] is None
        assert not any(
            item.get("method") == "$/progress"
            and item["params"]["value"]["kind"] == "end"
            for item in while_blocked
        )
        assert not any(
            item.get("method") == "window/workDoneProgress/create"
            for item in while_blocked
        )

        (control_root / "release-first-build").touch()
        end, _observed = process.read_until(
            lambda item: (
                item.get("method") == "$/progress"
                and item["params"]["token"] == token
                and item["params"]["value"]["kind"] == "end"
            ),
            timeout=30.0,
        )
        assert end["params"]["token"] == token
        assert _wait_for_path(control_root / "build-2-started")
        process.shutdown()
    finally:
        (control_root / "release-first-build").touch(exist_ok=True)
        process.close()


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


def test_real_stdio_recovery_to_full_transition_and_cleanup_write_nothing(
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
            "isIncomplete": True,
            "items": _frozen_form_completion_items(),
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

        failed_definition, _ = _request(
            process,
            request_id=9,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 12, "character": 14},
            },
        )
        assert failed_definition["result"] is None
        failed_symbols, _ = _request(
            process,
            request_id=10,
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": entry_path.as_uri()}},
        )
        assert failed_symbols["result"] is None
        failed_completion, _ = _request(
            process,
            request_id=11,
            method="textDocument/completion",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 0, "character": 0},
            },
        )
        assert failed_completion["result"] == {
            "isIncomplete": True,
            "items": _frozen_form_completion_items(),
        }

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

        restored_definition, _ = _request_until(
            process,
            request_id=12,
            method="textDocument/definition",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 12, "character": 14},
            },
            result_predicate=lambda result: result is not None,
        )
        assert restored_definition["result"] == procedure_definition["result"]
        restored_symbols, _ = _request(
            process,
            request_id=13,
            method="textDocument/documentSymbol",
            params={"textDocument": {"uri": entry_path.as_uri()}},
        )
        assert restored_symbols["result"] == symbols["result"]
        restored_completion, _ = _request(
            process,
            request_id=14,
            method="textDocument/completion",
            params={
                "textDocument": {"uri": entry_path.as_uri()},
                "position": {"line": 0, "character": 0},
            },
        )
        assert restored_completion["result"] == completion["result"]

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
            request_id=15,
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


def test_real_stdio_sequential_recompile_matches_fresh_server_state(
    tmp_path: Path,
) -> None:
    initial_text = _stateful_recompile_source(
        record_name="FirstResult",
        helper_name="first-helper",
        value="first",
    )
    invalid_text = _stateful_recompile_source(
        record_name="BrokenResult",
        helper_name="broken-helper",
        value="broken",
        invalid=True,
    )
    final_text = _stateful_recompile_source(
        record_name="FinalResult",
        helper_name="final-helper",
        value="final",
    )
    options: dict[str, object]

    sequential_workspace = (tmp_path / "sequential").resolve()
    sequential_workspace.mkdir()
    sequential_path = sequential_workspace / "entry.orc"
    sequential_path.write_text(initial_text, encoding="utf-8")
    options = {
        "source_roots": [str(sequential_workspace)],
        "entry_workflows": {str(sequential_path): "run"},
    }
    sequential = _LspProcess(sequential_workspace)
    try:
        _initialize(
            sequential,
            workspace=sequential_workspace,
            initialization_options=options,
        )
        _open(
            sequential,
            source_path=sequential_path,
            text=initial_text,
        )
        _current_document_surface(
            sequential,
            source_path=sequential_path,
            request_id_prefix="initial",
            expected_helper_name="first-helper",
        )

        sequential_path.write_text(invalid_text, encoding="utf-8")
        _change(
            sequential,
            source_path=sequential_path,
            text=invalid_text,
            version=2,
        )
        failed_diagnostics = _save_and_wait_for_diagnostics(
            sequential,
            source_path=sequential_path,
        )
        assert failed_diagnostics["params"]["diagnostics"]
        assert {
            diagnostic["code"]
            for diagnostic in failed_diagnostics["params"]["diagnostics"]
        } == {"name_unknown"}

        sequential_path.write_text(final_text, encoding="utf-8")
        _change(
            sequential,
            source_path=sequential_path,
            text=final_text,
            version=3,
        )
        final_diagnostics = _save_and_wait_for_diagnostics(
            sequential,
            source_path=sequential_path,
        )
        assert final_diagnostics["params"]["diagnostics"] == []
        sequential_surface = _current_document_surface(
            sequential,
            source_path=sequential_path,
            request_id_prefix="sequential-final",
            expected_helper_name="final-helper",
        )
        sequential.shutdown()
    finally:
        sequential.close()

    fresh_workspace = (tmp_path / "fresh").resolve()
    fresh_workspace.mkdir()
    fresh_path = fresh_workspace / "entry.orc"
    fresh_path.write_text(final_text, encoding="utf-8")
    fresh = _LspProcess(fresh_workspace)
    try:
        _initialize(
            fresh,
            workspace=fresh_workspace,
            initialization_options={
                "source_roots": [str(fresh_workspace)],
                "entry_workflows": {str(fresh_path): "run"},
            },
        )
        _open(
            fresh,
            source_path=fresh_path,
            text=final_text,
        )
        fresh_surface = _current_document_surface(
            fresh,
            source_path=fresh_path,
            request_id_prefix="fresh-initial",
            expected_helper_name="final-helper",
        )
        assert fresh_surface["diagnostics"] == []
        fresh.shutdown()
    finally:
        fresh.close()

    assert {
        **sequential_surface,
        "diagnostics": final_diagnostics["params"]["diagnostics"],
    } == fresh_surface
    serialized = json.dumps(
        {
            **sequential_surface,
            "diagnostics": final_diagnostics["params"]["diagnostics"],
        },
        sort_keys=True,
    )
    assert "FinalResult" in serialized
    assert "final-helper" in serialized
    assert "FirstResult" not in serialized
    assert "first-helper" not in serialized
    assert "BrokenResult" not in serialized
    assert "broken-helper" not in serialized
    assert "missing-after-state" not in serialized
    assert "%loop-state." not in serialized
    assert "%parametric_call." not in serialized


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
