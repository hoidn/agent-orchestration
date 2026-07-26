"""Real stdio LSP server with deterministic compile/event probes for tests."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from threading import Lock
import time

from orchestrator.lsp.server import create_server
from orchestrator.workflow_lisp.build import build_frontend_bundle_in_memory


CONTROL_ROOT = Path(os.environ["WORKFLOW_LSP_TEST_CONTROL_ROOT"]).resolve()
_PROBE_LOCK = Lock()
_BUILD_COUNT = 0
_SAVE_COUNT = 0


def _mark(name: str) -> None:
    with _PROBE_LOCK:
        (CONTROL_ROOT / name).touch()


def _controlled_build(*args: object, **kwargs: object) -> object:
    global _BUILD_COUNT
    with _PROBE_LOCK:
        _BUILD_COUNT += 1
        build_number = _BUILD_COUNT
        (CONTROL_ROOT / f"build-{build_number}-started").touch()
    if build_number == 1:
        release = CONTROL_ROOT / "release-first-build"
        deadline = time.monotonic() + 30.0
        while not release.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not release.exists():
            raise TimeoutError("test did not release the first LSP compile")
    result = build_frontend_bundle_in_memory(*args, **kwargs)
    _mark(f"build-{build_number}-finished")
    return result


def main() -> None:
    global _SAVE_COUNT
    transport_stdout = sys.stdout.buffer
    ordinary_stdout = sys.stdout
    try:
        sys.stdout = sys.stderr
        server = create_server(build_in_memory=_controlled_build)
        original_save = server.save_document
        original_close = server.close_document

        def observed_save(params: object) -> None:
            global _SAVE_COUNT
            with _PROBE_LOCK:
                _SAVE_COUNT += 1
                (CONTROL_ROOT / f"save-{_SAVE_COUNT}-observed").touch()
            original_save(params)

        def observed_close(params: object) -> None:
            _mark("close-observed")
            original_close(params)

        server.save_document = observed_save  # type: ignore[method-assign]
        server.close_document = observed_close  # type: ignore[method-assign]
        server.start_io(
            stdin=sys.stdin.buffer,
            stdout=transport_stdout,
        )
    finally:
        sys.stdout = ordinary_stdout


if __name__ == "__main__":
    main()
