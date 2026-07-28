from __future__ import annotations

import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time
import tomllib
from typing import Callable

import pytest

from orchestrator.workflow_lisp.form_registry import registered_form_heads


REPO_ROOT = Path(__file__).resolve().parents[1]
L1_SYMBOLS_ROOT = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "modules"
    / "valid"
    / "lsp_l1_symbols"
)


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


@pytest.mark.parametrize(
    ("manifest_contents", "expected_code"),
    (
        (None, "workflow_lisp_manifest_missing"),
        ("{not-json", "workflow_lisp_manifest_invalid_json"),
    ),
)
def test_structured_manifest_initialization_failure_returns_closed_data(
    tmp_path: Path,
    manifest_contents: str | None,
    expected_code: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manifest_path = workspace / "providers.json"
    if manifest_contents is not None:
        manifest_path.write_text(manifest_contents, encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        process.send(
            _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                initialization_options={
                    "provider_externs_path": manifest_path.name,
                },
            )
        )

        response, observed = process.read_until(
            lambda item: item.get("id") == 1
        )

        assert response == {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32602,
                "message": (
                    "Workflow Lisp initialization failed "
                    "(1 compiler diagnostics); see data"
                ),
                "data": {
                    "diagnostics": [
                        {
                            "code": expected_code,
                            "path": manifest_path.resolve().as_posix(),
                        }
                    ]
                },
            },
        }
        assert not any(
            item.get("method") == "textDocument/publishDiagnostics"
            for item in observed
        )
        process.exit_without_shutdown()
    finally:
        process.close()


def test_structured_initialization_failure_preserves_order_and_path_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lsprotocol import types
    from pygls.exceptions import JsonRpcInvalidParams

    import orchestrator.lsp.server as server_module
    from orchestrator.lsp.server import WorkflowLispLanguageServer
    from orchestrator.workflow_lisp.diagnostics import (
        LispFrontendCompileError,
        LispFrontendDiagnostic,
    )
    from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    canonical_source = workspace / "config" / ".." / "providers.json"
    retained_raw_source = "\0retained-raw-manifest"

    def diagnostic(code: str, path: str) -> LispFrontendDiagnostic:
        position = SourcePosition(path=path, line=1, column=1, offset=0)
        return LispFrontendDiagnostic(
            code=code,
            message=f"{code} detail must not enter the closed transport",
            span=SourceSpan(start=position, end=position),
            notes=("also excluded",),
        )

    error = LispFrontendCompileError(
        (
            diagnostic("first_code", str(canonical_source)),
            diagnostic("second_code", retained_raw_source),
        )
    )

    def fail_initialization(*args: object, **kwargs: object) -> object:
        raise error

    monkeypatch.setattr(
        server_module,
        "initialize_compile_driver",
        fail_initialization,
    )
    server = WorkflowLispLanguageServer()
    published: list[types.PublishDiagnosticsParams] = []
    monkeypatch.setattr(
        server,
        "text_document_publish_diagnostics",
        published.append,
    )

    with pytest.raises(JsonRpcInvalidParams) as raised:
        server.initialize_runtime(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                root_uri=workspace.as_uri(),
            )
        )

    assert raised.value.message == (
        "Workflow Lisp initialization failed "
        "(2 compiler diagnostics); see data"
    )
    assert raised.value.data == {
        "diagnostics": [
            {
                "code": "first_code",
                "path": canonical_source.resolve().as_posix(),
            },
            {
                "code": "second_code",
                "path": retained_raw_source,
            },
        ]
    }
    assert published == []
    assert server.driver is None


def test_l3_initialization_error_data_is_forwarded_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lsprotocol import types
    from pygls.exceptions import JsonRpcInvalidParams

    import orchestrator.lsp.server as server_module
    from orchestrator.lsp.server import WorkflowLispLanguageServer
    from orchestrator.lsp.state import LspInitializationError

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    expected_data = {
        "schema": "workflow_lisp_lsp_initialization_error.v1",
        "code": "lsp_initialization_option_invalid",
        "field": "entry_workflows",
        "rule": "mapping_required",
        "rejected_value": None,
    }

    def reject_state(*args: object, **kwargs: object) -> object:
        raise LspInitializationError(
            "lsp_initialization_option_invalid",
            "structured L3 refusal",
            data=expected_data,
        )

    monkeypatch.setattr(server_module, "initialize_lsp_state", reject_state)
    server = WorkflowLispLanguageServer()

    with pytest.raises(JsonRpcInvalidParams) as raised:
        server.initialize_runtime(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                root_uri=workspace.as_uri(),
            )
        )

    assert raised.value.data is expected_data
    assert server.driver is None


@pytest.mark.parametrize(
    "case",
    (
        "old_scalar",
        "non_object",
        "empty_key",
        "invalid_value",
        "uncanonicalizable",
        "wrong_suffix",
        "uncontained",
        "duplicate",
    ),
)
def test_l3_real_stdio_initialization_refusals_return_closed_data(
    tmp_path: Path,
    case: str,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    canonical_flow = (workspace / "flow.orc").as_posix()
    if case == "old_scalar":
        options: dict[str, object] = {"entry_workflow": "run"}
        expected_data = {
            "schema": "workflow_lisp_lsp_initialization_error.v1",
            "code": "lsp_initialization_option_unsupported",
            "field": "entry_workflow",
            "rule": "unsupported_field",
            "rejected_value": "run",
        }
    elif case == "non_object":
        options = {"entry_workflows": None}
        expected_data = {
            "schema": "workflow_lisp_lsp_initialization_error.v1",
            "code": "lsp_initialization_option_invalid",
            "field": "entry_workflows",
            "rule": "mapping_required",
            "rejected_value": None,
        }
    elif case == "empty_key":
        options = {"entry_workflows": {"": "run"}}
        expected_data = {
            "schema": "workflow_lisp_lsp_initialization_error.v1",
            "code": "lsp_initialization_option_invalid",
            "field": "entry_workflows",
            "rule": "key_nonempty_string_required",
            "rejected_value": "",
        }
    elif case == "invalid_value":
        options = {"entry_workflows": {"flow.orc": None}}
        expected_data = {
            "schema": "workflow_lisp_lsp_initialization_error.v1",
            "code": "lsp_initialization_option_invalid",
            "field": "entry_workflows",
            "rule": "entry_value_nonempty_string_required",
            "rejected_value": None,
            "entry_key": "flow.orc",
        }
    elif case == "uncanonicalizable":
        options = {"entry_workflows": {"bad\0.orc": "run"}}
        expected_data = {
            "schema": "workflow_lisp_lsp_initialization_error.v1",
            "code": "lsp_initialization_option_invalid",
            "field": "entry_workflows",
            "rule": "canonical_path_required",
            "rejected_value": "bad\0.orc",
            "entry_key": "bad\0.orc",
        }
    elif case == "wrong_suffix":
        options = {"entry_workflows": {"flow.txt": "run"}}
        expected_data = {
            "schema": "workflow_lisp_lsp_initialization_error.v1",
            "code": "lsp_initialization_option_invalid",
            "field": "entry_workflows",
            "rule": "orc_suffix_required",
            "rejected_value": "flow.txt",
            "entry_key": "flow.txt",
            "canonical_path": (workspace / "flow.txt").as_posix(),
        }
    elif case == "uncontained":
        options = {"entry_workflows": {"../outside.orc": "run"}}
        expected_data = {
            "schema": "workflow_lisp_lsp_initialization_error.v1",
            "code": "lsp_entry_workflow_path_uncontained",
            "field": "entry_workflows",
            "rule": "workspace_containment_required",
            "rejected_value": "../outside.orc",
            "entry_key": "../outside.orc",
            "canonical_path": (tmp_path / "outside.orc").resolve().as_posix(),
        }
    else:
        options = {
            "entry_workflows": {
                "flow.orc": "first",
                "nested/../flow.orc": "second",
            }
        }
        expected_data = {
            "schema": "workflow_lisp_lsp_initialization_error.v1",
            "code": "lsp_entry_workflow_path_duplicate",
            "field": "entry_workflows",
            "rule": "canonical_path_unique",
            "rejected_value": "nested/../flow.orc",
            "entry_key": "nested/../flow.orc",
            "canonical_path": canonical_flow,
            "conflicting_entry_key": "flow.orc",
        }

    process = _LspProcess(workspace)
    try:
        process.send(
            _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                initialization_options=options,
            )
        )
        response, observed = process.read_until(
            lambda item: item.get("id") == 1
        )

        assert response["error"]["code"] == -32602
        assert response["error"]["data"] == expected_data
        assert not any(
            item.get("method") == "textDocument/publishDiagnostics"
            for item in observed
        )
        process.exit_without_shutdown()
    finally:
        process.close()


@pytest.mark.parametrize(
    "unstructured_error",
    (
        OSError("filesystem failure"),
        PermissionError("permission failure"),
        RuntimeError("internal failure"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte"),
        ValueError("generic failure"),
    ),
)
def test_unstructured_compile_driver_initialization_failure_is_not_reclassified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unstructured_error: Exception,
) -> None:
    from lsprotocol import types

    import orchestrator.lsp.server as server_module
    from orchestrator.lsp.server import WorkflowLispLanguageServer

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fail_initialization(*args: object, **kwargs: object) -> object:
        raise unstructured_error

    monkeypatch.setattr(
        server_module,
        "initialize_compile_driver",
        fail_initialization,
    )
    server = WorkflowLispLanguageServer()

    with pytest.raises(type(unstructured_error)) as raised:
        server.initialize_runtime(
            types.InitializeParams(
                capabilities=types.ClientCapabilities(),
                root_uri=workspace.as_uri(),
            )
        )

    assert raised.value is unstructured_error
    assert server.driver is None


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


def test_document_symbol_protocol_exposes_ten_kinds_and_selection_ranges(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(L1_SYMBOLS_ROOT, workspace)
    entry_path = workspace / "lsp_l1_symbols" / "entry.orc"
    source_text = entry_path.read_text(encoding="utf-8").replace(
        "normalize-status",
        "review",
    )
    broken_text = "(workflow-lisp"
    entry_path.write_text(broken_text, encoding="utf-8")
    process = _LspProcess(workspace)
    try:
        process.send(
            _initialize_request(
                1,
                root_uri=workspace.as_uri(),
                initialization_options={
                    "source_roots": [str(workspace)],
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
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": entry_path.as_uri(),
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
                and item["params"]["uri"] == entry_path.as_uri()
            )
        )
        assert published_error["params"]["diagnostics"]
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {
                        "uri": entry_path.as_uri(),
                        "version": 2,
                    },
                    "contentChanges": [{"text": source_text}],
                },
            }
        )
        process.assert_no_message()
        entry_path.write_text(source_text, encoding="utf-8")
        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didSave",
                "params": {
                    "textDocument": {"uri": entry_path.as_uri()},
                },
            }
        )
        published_valid, _ = process.read_until(
            lambda item: (
                item.get("method") == "textDocument/publishDiagnostics"
                and item["params"]["uri"] == entry_path.as_uri()
            )
        )
        assert published_valid["params"]["diagnostics"] == []

        process.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/documentSymbol",
                "params": {
                    "textDocument": {"uri": entry_path.as_uri()},
                },
            }
        )
        response, _ = process.read_until(lambda item: item.get("id") == 2)

        assert "error" not in response
        symbols = response["result"]
        assert [
            (symbol["name"], symbol["kind"])
            for symbol in symbols
        ] == [
            ("lsp_l1_symbols/entry", 2),
            ("ReviewDecision", 10),
            ("ReportPath", 5),
            ("CommonFields", 11),
            ("ReviewState", 23),
            ("ReviewOutcome", 10),
            ("review-state", 19),
            ("record-review", 24),
            ("default-status", 12),
            ("review", 12),
            ("render-and-preserve", 12),
            ("default-review", 12),
            ("review", 12),
            ("review-many", 12),
        ]
        assert all(
            symbol["range"] != symbol["selectionRange"]
            for symbol in symbols
        )

        process.send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "textDocument/completion",
                "params": {
                    "textDocument": {"uri": entry_path.as_uri()},
                    "position": {"line": 0, "character": 0},
                },
            }
        )
        completion_response, _ = process.read_until(
            lambda item: item.get("id") == 3
        )

        assert "error" not in completion_response
        completion = completion_response["result"]
        assert completion["isIncomplete"] is False
        assert [
            (item["label"], item["kind"], item["detail"])
            for item in completion["items"]
            if item["label"] == "review"
        ] == [
            (
                "review",
                3,
                "procedure (status: String) -> String effects ()",
            ),
            (
                "review",
                3,
                "workflow (status: String) -> String",
            ),
        ]
        assert {
            (item["label"], item["kind"], item["detail"])
            for item in completion["items"]
            if item["label"] in {"default-status", "defproc"}
        } == {
            (
                "default-status",
                3,
                "procedure () -> String effects ()",
            ),
            ("defproc", 14, "form"),
        }

        process.send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didChange",
                "params": {
                    "textDocument": {
                        "uri": entry_path.as_uri(),
                        "version": 3,
                    },
                    "contentChanges": [{"text": source_text + "\n"}],
                },
            }
        )
        for request_id, method, params in (
            (
                4,
                "textDocument/definition",
                {
                    "textDocument": {"uri": entry_path.as_uri()},
                    "position": {"line": 75, "character": 5},
                },
            ),
            (
                5,
                "textDocument/documentSymbol",
                {"textDocument": {"uri": entry_path.as_uri()}},
            ),
            (
                6,
                "textDocument/completion",
                {
                    "textDocument": {"uri": entry_path.as_uri()},
                    "position": {"line": 0, "character": 0},
                },
            ),
        ):
            process.send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            dirty_response, _ = process.read_until(
                lambda item, expected_id=request_id: (
                    item.get("id") == expected_id
                )
            )
            assert "error" not in dirty_response
            if method == "textDocument/completion":
                dirty_completion = dirty_response["result"]
                assert dirty_completion["isIncomplete"] is True
                assert tuple(
                    (
                        item["label"],
                        item["kind"],
                        item["detail"],
                        item["sortText"],
                    )
                    for item in dirty_completion["items"]
                ) == tuple(
                    (head, 14, "form", head)
                    for head in registered_form_heads(
                        target_dsl_version=None
                    )
                )
                assert all(
                    set(item) == {"label", "kind", "detail", "sortText"}
                    for item in dirty_completion["items"]
                )
                assert all(
                    "procedure" not in item["detail"]
                    and "workflow" not in item["detail"]
                    for item in dirty_completion["items"]
                )
            else:
                assert dirty_response["result"] is None
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


def test_lsp_diagnostic_appends_ordered_notes_and_structural_frame_labels(
    tmp_path: Path,
) -> None:
    from orchestrator.lsp.diagnostics import DiagnosticContribution
    from orchestrator.lsp.server import _lsp_diagnostic

    entry_uri = (tmp_path / "entry.orc").resolve().as_uri()
    location = {
        "uri": entry_uri,
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 1},
        },
    }
    structured_data = {
        "notes": ("NOTE_SENTINEL_FIRST", "NOTE_SENTINEL_SECOND"),
        "retained": {"identity": "unchanged"},
    }
    contribution = DiagnosticContribution(
        target_uri=entry_uri,
        compile_entry_uri=entry_uri,
        accepted_generation=1,
        parity_identity=("unchanged-parity",),
        range=location["range"],
        code="test_code",
        severity=1,
        source="orc",
        message="RAW_MESSAGE_SENTINEL",
        data=structured_data,
        related_information=(
            {
                "frame_role": "macro",
                "location_role": "call",
                "name": "expand",
                "expansion_id": "exp-7",
                "location": location,
            },
            {
                "frame_role": "helper",
                "location_role": "definition",
                "name": "normalize",
                "expansion_id": None,
                "location": location,
            },
        ),
    )

    diagnostic = _lsp_diagnostic(contribution)

    assert diagnostic.message.startswith("RAW_MESSAGE_SENTINEL")
    assert diagnostic.message.index("RAW_MESSAGE_SENTINEL") < (
        diagnostic.message.index("NOTE_SENTINEL_FIRST")
    )
    assert diagnostic.message.index("NOTE_SENTINEL_FIRST") < (
        diagnostic.message.index("NOTE_SENTINEL_SECOND")
    )
    assert tuple(
        information.message
        for information in diagnostic.related_information
    ) == (
        "macro call: expand [exp-7]",
        "helper definition: normalize",
    )
    assert diagnostic.data == {
        "notes": ["NOTE_SENTINEL_FIRST", "NOTE_SENTINEL_SECOND"],
        "retained": {"identity": "unchanged"},
    }


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


def test_save_document_probes_once_and_applies_one_observed_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lsprotocol import types

    import orchestrator.lsp.server as server_module
    from orchestrator.lsp.compile_driver import probe_disk_source
    from orchestrator.lsp.server import WorkflowLispLanguageServer
    from orchestrator.lsp.state import change_entry, open_entry

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source_path = workspace / "entry.orc"
    initial_text = "(workflow-lisp)\n"
    changed_text = "(workflow-lisp changed)\n"
    source_path.write_text(initial_text, encoding="utf-8")
    server = WorkflowLispLanguageServer()
    server.initialize_runtime(
        types.InitializeParams(
            capabilities=types.ClientCapabilities(),
            root_uri=workspace.as_uri(),
        )
    )
    assert server.driver is not None
    opened = open_entry(
        server.driver.state,
        document_uri=source_path.as_uri(),
        editor_text=initial_text,
        disk_snapshot=probe_disk_source(source_path),
    )
    server.driver.apply_transition(opened)
    server.driver.apply_transition(
        change_entry(
            server.driver.state,
            document_uri=source_path.as_uri(),
            editor_text=changed_text,
        )
    )
    source_path.write_text(changed_text, encoding="utf-8")

    probes = []
    transitions = []
    original_probe = server_module.probe_disk_source
    original_save_observed = server_module.save_observed_entry

    def counted_probe(path: Path):
        snapshot = original_probe(path)
        probes.append(snapshot)
        return snapshot

    def counted_save_observed(*args: object, **kwargs: object):
        transitions.append(kwargs["observed_snapshot"])
        return original_save_observed(*args, **kwargs)

    monkeypatch.setattr(server_module, "probe_disk_source", counted_probe)
    monkeypatch.setattr(
        server_module,
        "save_observed_entry",
        counted_save_observed,
    )
    monkeypatch.setattr(
        type(server.driver),
        "observe_disk_path",
        lambda _self, _path: pytest.fail(
            "didSave must not call observe_disk_path"
        ),
    )
    emitted = []
    monkeypatch.setattr(server, "_drain_and_publish", emitted.append)

    server.save_document(
        types.DidSaveTextDocumentParams(
            text_document=types.TextDocumentIdentifier(
                uri=source_path.as_uri(),
            )
        )
    )

    assert len(probes) == 1
    assert transitions == probes
    assert len(emitted) == 1
    assert server.driver.state.entries[0].generation == 3
    assert server.driver.queued_generations == ((source_path.resolve(), 3),)


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
