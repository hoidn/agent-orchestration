from __future__ import annotations

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import tomllib
from typing import Callable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


class _LspProcess:
    def __init__(
        self,
        workspace: Path,
        *,
        server_command: tuple[str, ...] | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> None:
        env = dict(os.environ)
        prior_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(REPO_ROOT)
            if not prior_pythonpath
            else os.pathsep.join((str(REPO_ROOT), prior_pythonpath))
        )
        if extra_environment is not None:
            env.update(extra_environment)
        self.process = subprocess.Popen(
            (
                server_command
                if server_command is not None
                else (sys.executable, "-m", "orchestrator.lsp")
            ),
            cwd=workspace,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self._buffer = bytearray()

    def send(self, message: dict[str, object]) -> None:
        assert self.process.stdin is not None
        payload = json.dumps(
            message,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        frame = (
            f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
            + payload
        )
        self.process.stdin.write(frame)
        self.process.stdin.flush()

    def read_until(
        self,
        predicate: Callable[[dict[str, object]], bool],
        *,
        timeout: float = 15.0,
    ) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
        deadline = time.monotonic() + timeout
        observed: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            message = self._read_message(deadline=deadline)
            observed.append(message)
            if predicate(message):
                return message, tuple(observed)
        pytest.fail(f"timed out waiting for LSP message; observed={observed!r}")

    def exit_without_shutdown(self) -> None:
        if self.process.poll() is None:
            self.send({"jsonrpc": "2.0", "method": "exit"})
        self._wait_for_exit()

    def shutdown(self) -> tuple[dict[str, object], ...]:
        request_id = 9001
        self.send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "shutdown",
                "params": None,
            }
        )
        _response, observed = self.read_until(
            lambda item: item.get("id") == request_id
        )
        self.send({"jsonrpc": "2.0", "method": "exit"})
        self._wait_for_exit()
        return observed

    def assert_no_message(self, *, timeout: float = 0.35) -> None:
        assert self.process.stdout is not None
        if self._parse_buffered_frame() is not None:
            pytest.fail("received an unexpected buffered LSP message")
        readable, _, _ = select.select(
            (self.process.stdout,),
            (),
            (),
            timeout,
        )
        if readable:
            message = self._read_message(deadline=time.monotonic() + timeout)
            pytest.fail(f"received an unexpected LSP message: {message!r}")

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)

    def stderr_text(self) -> str:
        assert self.process.stderr is not None
        if self.process.poll() is None:
            return ""
        return self.process.stderr.read().decode("utf-8", errors="replace")

    def _read_message(self, *, deadline: float) -> dict[str, object]:
        assert self.process.stdout is not None
        while True:
            parsed = self._parse_buffered_frame()
            if parsed is not None:
                return parsed
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                pytest.fail(
                    "timed out waiting for an LSP frame; "
                    f"buffer={bytes(self._buffer)!r}"
                )
            readable, _, _ = select.select(
                (self.process.stdout,),
                (),
                (),
                remaining,
            )
            if not readable:
                continue
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                pytest.fail(
                    "LSP process exited before the expected frame; "
                    f"returncode={self.process.poll()}, "
                    f"stderr={self.stderr_text()!r}, "
                    f"buffer={bytes(self._buffer)!r}"
                )
            self._buffer.extend(chunk)

    def _parse_buffered_frame(self) -> dict[str, object] | None:
        separator = self._buffer.find(b"\r\n\r\n")
        if separator < 0:
            return None
        raw_headers = bytes(self._buffer[:separator])
        headers: dict[str, str] = {}
        for raw_header in raw_headers.split(b"\r\n"):
            try:
                name, value = raw_header.decode("ascii").split(":", 1)
            except ValueError:
                pytest.fail(
                    f"stdout contains a non-protocol frame header: {raw_headers!r}"
                )
            headers[name.lower()] = value.strip()
        if "content-length" not in headers:
            pytest.fail(
                f"stdout contains unframed content: {raw_headers!r}"
            )
        try:
            content_length = int(headers["content-length"])
        except ValueError:
            pytest.fail(f"invalid Content-Length header: {raw_headers!r}")
        frame_end = separator + 4 + content_length
        if len(self._buffer) < frame_end:
            return None
        payload = bytes(self._buffer[separator + 4 : frame_end])
        del self._buffer[:frame_end]
        decoded = json.loads(payload.decode("utf-8"))
        if not isinstance(decoded, dict):
            pytest.fail(f"LSP frame payload is not an object: {decoded!r}")
        return decoded

    def _wait_for_exit(self) -> None:
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.close()
            pytest.fail("LSP process did not exit after the exit notification")
        assert self.process.stdout is not None
        trailing = self.process.stdout.read()
        if trailing:
            self._buffer.extend(trailing)
        assert self._buffer == bytearray()


def _initialize_request(
    request_id: int,
    *,
    root_uri: str | None,
    workspace_folder_uris: tuple[str, ...] = (),
    initialization_options: dict[str, object] | None = None,
    capabilities: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "processId": None,
            "rootUri": root_uri,
            "workspaceFolders": [
                {"uri": uri, "name": f"workspace-{index}"}
                for index, uri in enumerate(workspace_folder_uris)
            ],
            "initializationOptions": initialization_options,
            "capabilities": capabilities or {},
        },
    }


def test_lsp_dependency_is_optional_and_default_imports_remain_transport_free() -> None:
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["optional-dependencies"]["lsp"] == [
        "pygls>=2.1.1,<3"
    ]
    assert all(
        "pygls" not in dependency
        for dependency in pyproject["project"]["dependencies"]
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import orchestrator; "
                "import orchestrator.lsp.state; "
                "assert 'pygls' not in sys.modules; "
                "assert 'lsprotocol' not in sys.modules"
            ),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr


@pytest.mark.parametrize(
    "case",
    ("zero_roots", "multiple_roots", "unsupported_option"),
)
def test_invalid_initialization_fails_before_transport_state(
    tmp_path: Path,
    case: str,
) -> None:
    workspace = tmp_path / "workspace"
    other = tmp_path / "other"
    workspace.mkdir()
    other.mkdir()
    process = _LspProcess(workspace)
    try:
        if case == "zero_roots":
            request = _initialize_request(1, root_uri=None)
        elif case == "multiple_roots":
            request = _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                workspace_folder_uris=(other.as_uri(),),
            )
        else:
            request = _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                initialization_options={"lint_profile": "strict"},
            )
        process.send(request)

        response, observed = process.read_until(
            lambda item: item.get("id") == 1
        )

        assert response["error"]["code"] == -32602
        assert not any(
            item.get("method") == "textDocument/publishDiagnostics"
            for item in observed
        )
        process.exit_without_shutdown()
    finally:
        process.close()


def test_single_root_initialize_and_shutdown_are_frame_clean(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    process = _LspProcess(workspace)
    try:
        process.send(
            _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                workspace_folder_uris=(workspace.as_uri(),),
            )
        )
        response, observed = process.read_until(
            lambda item: item.get("id") == 1
        )

        assert "error" not in response
        assert response["result"]["capabilities"]["textDocumentSync"]
        assert not any("error" in item for item in observed)
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {},
            }
        )
        process.shutdown()
    finally:
        process.close()


@pytest.mark.parametrize("watch_type", (1, 2, 3))
def test_frame_clean_document_lifecycle_and_watcher_publication(
    tmp_path: Path,
    watch_type: int,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source_path = workspace / "entry.orc"
    broken_text = "(workflow-lisp"
    valid_text = (
        '(workflow-lisp (:language "0.1") (:target-dsl "2.14") '
        "(defmodule entry))\n"
    )
    source_path.write_text(broken_text, encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        process.send(
            _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                workspace_folder_uris=(workspace.as_uri(),),
                capabilities={
                    "workspace": {
                        "didChangeWatchedFiles": {
                            "dynamicRegistration": True,
                        }
                    }
                },
            )
        )
        initialize_response, _ = process.read_until(
            lambda item: item.get("id") == 1
        )
        assert "error" not in initialize_response
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {},
            }
        )
        registration, _ = process.read_until(
            lambda item: item.get("method") == "client/registerCapability"
        )
        registrations = registration["params"]["registrations"]
        assert len(registrations) == 1
        assert registrations[0]["method"] == (
            "workspace/didChangeWatchedFiles"
        )
        assert any(
            watcher["globPattern"] == "**/*.orc"
            for watcher in registrations[0]["registerOptions"]["watchers"]
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "id": registration["id"],
                "result": None,
            }
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": source_path.as_uri(),
                        "languageId": "workflow-lisp",
                        "version": 1,
                        "text": broken_text,
                    }
                },
            }
        )
        published_error, _ = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == source_path.as_uri()
            )
        )
        assert published_error["params"]["diagnostics"]

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {
                        "uri": source_path.as_uri(),
                        "version": 2,
                    },
                    "contentChanges": [{"text": valid_text}],
                },
            }
        )
        process.assert_no_message()
        source_path.write_text(valid_text, encoding="utf-8")
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didSave",
                "params": {
                    "textDocument": {"uri": source_path.as_uri()},
                    "text": "notification text is not compile authority",
                },
            }
        )
        cleared, _ = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == source_path.as_uri()
            )
        )
        assert cleared["params"]["diagnostics"] == []

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {
                        "uri": source_path.as_uri(),
                        "version": 3,
                    },
                    "contentChanges": [{"text": broken_text}],
                },
            }
        )
        process.assert_no_message()
        source_path.write_text(broken_text, encoding="utf-8")
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeWatchedFiles",
                "params": {
                    "changes": [
                        {
                            "uri": source_path.as_uri(),
                            "type": watch_type,
                        }
                    ]
                },
            }
        )
        watched_error, _ = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == source_path.as_uri()
            )
        )
        assert watched_error["params"]["diagnostics"]

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didClose",
                "params": {
                    "textDocument": {"uri": source_path.as_uri()},
                },
            }
        )
        close_clear, _ = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == source_path.as_uri()
            )
        )
        assert close_clear["params"]["diagnostics"] == []
        process.shutdown()
    finally:
        process.close()


def test_client_without_dynamic_watch_support_receives_no_registration(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source_path = workspace / "entry.orc"
    broken_text = "(workflow-lisp"
    source_path.write_text(broken_text, encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        process.send(_initialize_request(1, root_uri=workspace.as_uri()))
        process.read_until(lambda item: item.get("id") == 1)
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {},
            }
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": source_path.as_uri(),
                        "languageId": "workflow-lisp",
                        "version": 1,
                        "text": broken_text,
                    }
                },
            }
        )
        published, observed = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
            )
        )

        assert published["params"]["diagnostics"]
        assert not any(
            item.get("method") == "client/registerCapability"
            for item in observed
        )
        process.shutdown()
    finally:
        process.close()


def test_workspace_folder_change_latches_one_restart_notice_and_clears(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    other = tmp_path / "other"
    workspace.mkdir()
    other.mkdir()
    source_path = workspace / "entry.orc"
    broken_text = "(workflow-lisp"
    source_path.write_text(broken_text, encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        process.send(_initialize_request(1, root_uri=workspace.as_uri()))
        process.read_until(lambda item: item.get("id") == 1)
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {},
            }
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": source_path.as_uri(),
                        "languageId": "workflow-lisp",
                        "version": 1,
                        "text": broken_text,
                    }
                },
            }
        )
        process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
            )
        )

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeWorkspaceFolders",
                "params": {
                    "event": {
                        "added": [
                            {
                                "uri": other.as_uri(),
                                "name": "other",
                            }
                        ],
                        "removed": [],
                    }
                },
            }
        )
        required_methods = {
            "textDocument/publishDiagnostics",
            "window/logMessage",
            "window/showMessage",
        }
        seen_methods: set[object] = set()

        def all_stale_effects_observed(item: dict[str, object]) -> bool:
            seen_methods.add(item.get("method"))
            return required_methods.issubset(seen_methods)

        _last, observed = process.read_until(all_stale_effects_observed)

        stale_effects = [
            item
            for item in observed
            if item.get("method") in required_methods
        ]
        assert [
            item
            for item in stale_effects
            if item.get("method") == "textDocument/publishDiagnostics"
        ][0]["params"]["diagnostics"] == []
        assert sum(
            item.get("method") == "window/logMessage"
            for item in stale_effects
        ) == 1
        assert sum(
            item.get("method") == "window/showMessage"
            for item in stale_effects
        ) == 1

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeWorkspaceFolders",
                "params": {
                    "event": {
                        "added": [],
                        "removed": [
                            {
                                "uri": workspace.as_uri(),
                                "name": "workspace",
                            }
                        ],
                    }
                },
            }
        )
        process.assert_no_message()
        process.shutdown()
    finally:
        process.close()


def test_watcher_ignores_paths_outside_the_admitted_source_scope(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.orc"
    workspace.mkdir()
    source_path = workspace / "entry.orc"
    ignored_path = workspace / "notes.txt"
    broken_text = "(workflow-lisp"
    source_path.write_text(broken_text, encoding="utf-8")
    outside.write_text(broken_text, encoding="utf-8")
    ignored_path.write_text("not workflow source", encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        process.send(_initialize_request(1, root_uri=workspace.as_uri()))
        process.read_until(lambda item: item.get("id") == 1)
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {},
            }
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": source_path.as_uri(),
                        "languageId": "workflow-lisp",
                        "version": 1,
                        "text": broken_text,
                    }
                },
            }
        )
        process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
            )
        )

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeWatchedFiles",
                "params": {
                    "changes": [
                        {"uri": outside.as_uri(), "type": 2},
                        {"uri": ignored_path.as_uri(), "type": 2},
                    ]
                },
            }
        )
        process.assert_no_message()
        process.shutdown()
    finally:
        process.close()


def test_internal_compile_error_logs_without_replacing_owned_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lsprotocol import types

    from orchestrator.lsp.server import WorkflowLispLanguageServer
    from orchestrator.workflow_lisp.build import (
        build_frontend_bundle_in_memory,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source_path = workspace / "entry.orc"
    broken_text = "(workflow-lisp"
    source_path.write_text(broken_text, encoding="utf-8")
    build_count = 0

    def fail_second_build(*args: object, **kwargs: object) -> object:
        nonlocal build_count
        build_count += 1
        if build_count == 2:
            raise RuntimeError("transport-visible internal failure")
        return build_frontend_bundle_in_memory(*args, **kwargs)

    server = WorkflowLispLanguageServer(
        build_in_memory=fail_second_build,
    )
    logged: list[types.LogMessageParams] = []
    published: list[types.PublishDiagnosticsParams] = []
    monkeypatch.setattr(server, "window_log_message", logged.append)
    monkeypatch.setattr(
        server,
        "text_document_publish_diagnostics",
        published.append,
    )
    server.initialize_runtime(
        types.InitializeParams(
            capabilities=types.ClientCapabilities(),
            root_uri=workspace.as_uri(),
        )
    )
    server.open_document(
        types.DidOpenTextDocumentParams(
            text_document=types.TextDocumentItem(
                uri=source_path.as_uri(),
                language_id="workflow-lisp",
                version=1,
                text=broken_text,
            )
        )
    )
    assert server.driver is not None
    before = server.driver.state.entries[0].diagnostic_contributions
    published_before_failure = tuple(published)
    assert before

    server.save_document(
        types.DidSaveTextDocumentParams(
            text_document=types.TextDocumentIdentifier(
                uri=source_path.as_uri(),
            )
        )
    )

    entry = server.driver.state.entries[0]
    assert entry.compile_status == "server_error"
    assert entry.diagnostic_contributions is before
    assert tuple(published) == published_before_failure
    assert len(logged) == 1
    assert logged[0].type == types.MessageType.Error
    assert "transport-visible internal failure" in logged[0].message


def test_dynamic_watcher_registration_includes_frozen_configuration_paths(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider_externs = workspace / "providers.json"
    provider_externs.write_text("{}\n", encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        process.send(
            _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                initialization_options={
                    "provider_externs_path": provider_externs.name,
                },
                capabilities={
                    "workspace": {
                        "didChangeWatchedFiles": {
                            "dynamicRegistration": True,
                        }
                    }
                },
            )
        )
        response, _ = process.read_until(
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
        registration, _ = process.read_until(
            lambda item: item.get("method") == "client/registerCapability"
        )
        watchers = registration["params"]["registrations"][0][
            "registerOptions"
        ]["watchers"]

        assert {
            "baseUri": provider_externs.parent.as_uri(),
            "pattern": provider_externs.name,
        } in [watcher["globPattern"] for watcher in watchers]
        process.send(
            {
                "jsonrpc": "2.0",
                "id": registration["id"],
                "result": None,
            }
        )
        process.shutdown()
    finally:
        process.close()


def test_watched_configuration_drift_clears_and_notifies_exactly_once(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider_externs = workspace / "providers.json"
    provider_externs.write_text("{}\n", encoding="utf-8")
    source_path = workspace / "entry.orc"
    broken_text = "(workflow-lisp"
    source_path.write_text(broken_text, encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        process.send(
            _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                initialization_options={
                    "provider_externs_path": provider_externs.name,
                },
            )
        )
        process.read_until(lambda item: item.get("id") == 1)
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "initialized",
                "params": {},
            }
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": source_path.as_uri(),
                        "languageId": "workflow-lisp",
                        "version": 1,
                        "text": broken_text,
                    }
                },
            }
        )
        process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
            )
        )
        provider_externs.write_text(
            '{"providers.execute":"changed"}\n',
            encoding="utf-8",
        )
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeWatchedFiles",
                "params": {
                    "changes": [
                        {
                            "uri": provider_externs.as_uri(),
                            "type": 2,
                        }
                    ]
                },
            }
        )
        required_methods = {
            "textDocument/publishDiagnostics",
            "window/logMessage",
            "window/showMessage",
        }
        seen_methods: set[object] = set()

        def all_stale_effects_observed(item: dict[str, object]) -> bool:
            seen_methods.add(item.get("method"))
            return required_methods.issubset(seen_methods)

        _last, observed = process.read_until(all_stale_effects_observed)

        stale_effects = [
            item
            for item in observed
            if item.get("method") in required_methods
        ]
        assert [
            item
            for item in stale_effects
            if item.get("method") == "textDocument/publishDiagnostics"
        ][0]["params"]["diagnostics"] == []
        assert sum(
            item.get("method") == "window/logMessage"
            for item in stale_effects
        ) == 1
        assert sum(
            item.get("method") == "window/showMessage"
            for item in stale_effects
        ) == 1

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "workspace/didChangeWatchedFiles",
                "params": {
                    "changes": [
                        {
                            "uri": provider_externs.as_uri(),
                            "type": 2,
                        }
                    ]
                },
            }
        )
        process.assert_no_message()
        process.shutdown()
    finally:
        process.close()
