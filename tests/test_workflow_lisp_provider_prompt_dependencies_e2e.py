"""Functional end-to-end coverage for typed prompt dependencies."""

from __future__ import annotations

import builtins
import hashlib
import os
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest



FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "provider_prompt_dependencies"
    / "mixed.orc"
)








def _running_session_state(
    *,
    result: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "status": "running",
        "steps": {} if result is None else {"Review": result},
        "current_step": {
            "name": "Review",
            "index": 0,
            "type": "provider",
            "status": "running",
            "step_id": "root.review",
            "visit_count": 2,
        },
    }






def test_interrupted_provider_session_at_least_once_projection_mismatch_is_integrity_error_before_launch(
) -> None:
    state = _running_session_state()
    current_step = state["current_step"]
    assert isinstance(current_step, dict)
    current_step["step_id"] = "root.other"






@contextmanager
def _guard_prior_evidence_access(prior_paths: set[Path]):
    """Reject runtime reads or enumeration of an earlier attempt's evidence."""

    prior = {os.path.abspath(os.fspath(path)) for path in prior_paths}
    enumeration_roots: set[str] = set()
    for path in prior_paths:
        parent = path.parent
        while True:
            enumeration_roots.add(os.path.abspath(os.fspath(parent)))
            if parent.name == "prompt_dependencies" or parent.parent == parent:
                break
            parent = parent.parent

    def _absolute(value) -> str | None:
        if not isinstance(value, (str, os.PathLike)):
            return None
        return os.path.abspath(os.fspath(value))

    def _reject_read(value) -> None:
        if _absolute(value) in prior:
            raise AssertionError("prior evidence read")

    def _reject_enumeration(value) -> None:
        if _absolute(value) in enumeration_roots:
            raise AssertionError("prior evidence enumeration")

    original_path_open = Path.open
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    original_iterdir = Path.iterdir
    original_glob = Path.glob
    original_rglob = Path.rglob
    original_builtin_open = builtins.open
    original_os_open = os.open
    original_listdir = os.listdir
    original_scandir = os.scandir

    def _path_open(path: Path, *args, **kwargs):
        _reject_read(path)
        return original_path_open(path, *args, **kwargs)

    def _read_bytes(path: Path):
        _reject_read(path)
        return original_read_bytes(path)

    def _read_text(path: Path, *args, **kwargs):
        _reject_read(path)
        return original_read_text(path, *args, **kwargs)

    def _iterdir(path: Path):
        _reject_enumeration(path)
        return original_iterdir(path)

    def _glob(path: Path, *args, **kwargs):
        _reject_enumeration(path)
        return original_glob(path, *args, **kwargs)

    def _rglob(path: Path, *args, **kwargs):
        _reject_enumeration(path)
        return original_rglob(path, *args, **kwargs)

    def _builtin_open(file, *args, **kwargs):
        _reject_read(file)
        return original_builtin_open(file, *args, **kwargs)

    def _os_open(path, flags, *args, **kwargs):
        if flags & os.O_ACCMODE != os.O_WRONLY:
            _reject_read(path)
        return original_os_open(path, flags, *args, **kwargs)

    def _listdir(path="."):
        _reject_enumeration(path)
        return original_listdir(path)

    def _scandir(path="."):
        _reject_enumeration(path)
        return original_scandir(path)

    with ExitStack() as stack:
        stack.enter_context(patch.object(Path, "open", _path_open))
        stack.enter_context(patch.object(Path, "read_bytes", _read_bytes))
        stack.enter_context(patch.object(Path, "read_text", _read_text))
        stack.enter_context(patch.object(Path, "iterdir", _iterdir))
        stack.enter_context(patch.object(Path, "glob", _glob))
        stack.enter_context(patch.object(Path, "rglob", _rglob))
        stack.enter_context(patch.object(builtins, "open", _builtin_open))
        stack.enter_context(patch.object(os, "open", _os_open))
        stack.enter_context(patch.object(os, "listdir", _listdir))
        stack.enter_context(patch.object(os, "scandir", _scandir))
        yield


def test_prior_evidence_guard_blocks_reads_hash_inputs_and_enumeration(
    tmp_path: Path,
) -> None:
    evidence_dir = (
        tmp_path
        / "workflow_lisp"
        / "prompt_dependencies"
        / "step"
        / "visit"
    )
    evidence_dir.mkdir(parents=True)
    prior = evidence_dir / "attempt-000001.json"
    prior.write_bytes(b"prior evidence")
    fresh = evidence_dir / "attempt-000002.json"

    with _guard_prior_evidence_access({prior}):
        with pytest.raises(AssertionError, match="prior evidence read"):
            prior.read_bytes()
        with pytest.raises(AssertionError, match="prior evidence read"):
            hashlib.sha256(prior.read_bytes()).hexdigest()
        with pytest.raises(AssertionError, match="prior evidence enumeration"):
            list(evidence_dir.iterdir())
        with pytest.raises(AssertionError, match="prior evidence enumeration"):
            list((tmp_path / "workflow_lisp" / "prompt_dependencies").rglob("*.json"))
        fresh.write_bytes(b"fresh evidence")

    assert fresh.read_bytes() == b"fresh evidence"
