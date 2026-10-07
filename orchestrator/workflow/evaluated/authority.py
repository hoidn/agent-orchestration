"""Durable authority files for evaluated runs."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import stat
from typing import Any

from orchestrator.run_lock import ReservedRunRootError, run_root_matches_fd, run_writer_lock
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.run_ref.contracts import (
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow_lisp.closed.program import ClosedProgram, REPRESENTATION
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from orchestrator.workflow.evaluated.interpreters import (
    pin_command_interpreter,
    validate_command_interpreter_pin_shape,
)
from .run_header import (
    PROFILE,
    SCHEMA_VERSION,
    RunAuthorityError,
    _HEADER_FIELDS,
    _RESUME_REQUEST_FIELDS,
    _decode_header_json,
    _reject_duplicate_keys,
    _validate_header_metadata,
    _validate_header_shape,
    _validate_json_value,
    _validate_locator,
    _validate_requested_entry,
    _validate_result_root,
    _validate_run_ref_root,
    validate_resume_request,
)


PROGRAM_FILENAME = "closed_program.json"
HEADER_FILENAME = "run.json"
MEMO_FILENAME = "memo.jsonl"


class CommandTransportRequiredError(RunAuthorityError):
    """A compile-only command artifact is not ready for evaluated execution."""

    code = "command_transport_required"


@dataclass(frozen=True, slots=True)
class RunAuthority:
    run_root: Path
    header: Mapping[str, Any]
    program: ClosedProgram
    run_files: WorkspaceFiles | None = field(default=None, compare=False, repr=False)

    @property
    def header_path(self) -> Path:
        return self.run_root / HEADER_FILENAME

    @property
    def program_path(self) -> Path:
        return self.run_root / PROGRAM_FILENAME

    @property
    def memo_path(self) -> Path:
        return self.run_root / MEMO_FILENAME


def workspace_result_locator(header: Mapping[str, Any], result_path: str) -> str | None:
    """Join the immutable result root with a memo result path; None when the header predates it."""
    root = header.get("result_root")
    return None if root is None else f"{root}/{result_path}"


def _read_file(path: Path, run_files: WorkspaceFiles | None = None) -> bytes:
    if run_files is not None:
        return run_files.read(path)
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RunAuthorityError(f"{path.name} is not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_header_json(path: Path, run_files: WorkspaceFiles | None = None) -> Any:
    try:
        payload = _read_file(path, run_files)
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise RunAuthorityError(f"invalid run header: {exc}") from exc
    return _decode_header_json(payload)


def _read_header(path: Path, run_files: WorkspaceFiles | None = None) -> dict[str, Any]:
    return _validate_header_shape(_read_header_json(path, run_files))


def _validated_bound_inputs(
    program: ClosedProgram, values: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise RunAuthorityError("bound inputs are not an object")
    params = {
        name: descriptor
        for name, descriptor in program.tree["params"]
    }
    if set(values) != set(params):
        raise RunAuthorityError("bound input names differ from the checked program")
    normalized: dict[str, Any] = {}
    for name, descriptor in params.items():
        value = coerce_evaluated_value(
            values[name], descriptor, context=f"bound input {name}"
        ).json_value()
        if canonical_json_bytes(value) != canonical_json_bytes(values[name]):
            raise RunAuthorityError(f"bound input {name!r} is not in checked form")
        normalized[name] = value
    return normalized


def _validate_program_binding(
    program: ClosedProgram, header: Mapping[str, Any]
) -> None:
    if program.digest != header["program_digest"]:
        raise ValueError("program digest differs from the run header")
    if program.tree.get("representation") != header["representation"]:
        raise ValueError("program representation differs from the run header")
    if header["representation"] != REPRESENTATION:
        raise ValueError("unsupported program representation")


def _emitted_bare_interpreters(program: ClosedProgram) -> list[str]:
    bodies = [
        program.tree["body"],
        *(definition["body"] for definition in program.tree["definitions"].values()),
    ]
    return sorted(
        {
            node["command"][0]
            for body in bodies
            for node in _ast_nodes(body)
            if node.get("k") == "perform"
            and node.get("class") == "command"
            and "/" not in node["command"][0]
        }
    )


def _has_command_transport(program: ClosedProgram) -> bool:
    bodies = [
        program.tree["body"],
        *(definition["body"] for definition in program.tree["definitions"].values()),
    ]
    return all(
        "argv_transport" in node
        for body in bodies
        for node in _ast_nodes(body)
        if node.get("k") == "perform" and node.get("class") == "command"
    )


def _pin_emitted_interpreters(program: ClosedProgram) -> dict[str, dict[str, str]]:
    pins: dict[str, dict[str, str]] = {}
    for token in _emitted_bare_interpreters(program):
        pin = pin_command_interpreter((token,))
        if pin is None:
            raise ValueError(f"bare command interpreter {token!r} was not pinned")
        pins[token] = pin
    return pins


def _validate_interpreter_pins(program: ClosedProgram, pins: object) -> None:
    tokens = _emitted_bare_interpreters(program)
    if not isinstance(pins, dict) or set(pins) != set(tokens):
        raise ValueError("interpreter pins differ from emitted command interpreters")
    for token in tokens:
        validate_command_interpreter_pin_shape(pins[token])


def _checked_authority(run_root: Path, header: dict[str, Any], run_files: WorkspaceFiles | None = None) -> RunAuthority:
    try:
        payload = _read_file(run_root / PROGRAM_FILENAME, run_files)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        if isinstance(exc, RunAuthorityError):
            raise
        raise RunAuthorityError(f"invalid evaluated authority: {exc}") from exc
    return _checked_authority_bytes(run_root, header, payload, run_files)


def _checked_authority_bytes(run_root, header, program_bytes, run_files=None):
    try:
        program = ClosedProgram.from_artifact(
            program_bytes.decode("utf-8")
        )
        _validate_program_binding(program, header)
        if not _has_command_transport(program):
            raise ValueError("stored command is missing argv transport")
        _validate_interpreter_pins(program, header["interpreters"])
        bound_inputs = _validated_bound_inputs(program, header["bound_inputs"])
        if canonical_sha256(bound_inputs) != header["input_digest"]:
            raise ValueError("input digest differs from the run header")
        _validate_header_metadata(run_root, header)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        if isinstance(exc, RunAuthorityError):
            raise
        raise RunAuthorityError(f"invalid evaluated authority: {exc}") from exc
    return RunAuthority(run_root, header, program, run_files)


def load_run_authority_from_bytes(run_root: Path, *, header_bytes: bytes, program_bytes: bytes) -> RunAuthority:
    """Check captured authority using the same validators as path/FD loaders."""
    run_root = Path(run_root)
    header = _validate_header_shape(_decode_header_json(header_bytes))
    try:
        _validate_header_metadata(run_root, header)
    except (TypeError, ValueError) as exc:
        raise RunAuthorityError(f"invalid evaluated run header: {exc}") from exc
    return _checked_authority_bytes(run_root, header, program_bytes)


def load_run_header(run_root: Path, *, run_files: WorkspaceFiles | None = None) -> dict[str, Any]:
    """Validate header metadata before opening the artifact or memo records."""
    run_root = Path(run_root)
    try:
        header = _read_header(run_root / HEADER_FILENAME, run_files)
        _validate_header_metadata(run_root, header)
        return header
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, RunAuthorityError):
            raise
        raise RunAuthorityError(f"invalid evaluated run header: {exc}") from exc


def load_run_authority(run_root: Path, *, header: dict[str, Any] | None = None, run_files: WorkspaceFiles | None = None) -> RunAuthority:
    """Read and check immutable run authority without repairing any file."""
    run_root = Path(run_root)
    checked_header = load_run_header(run_root, run_files=run_files) if header is None else _validate_header_shape(header)
    try:
        _validate_header_metadata(run_root, checked_header)
    except (TypeError, ValueError) as exc:
        raise RunAuthorityError(f"invalid evaluated run header: {exc}") from exc
    return _checked_authority(run_root, checked_header, run_files)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sync_ancestors(path: Path) -> None:
    current = Path(os.path.abspath(path))
    while True:
        _sync_directory(current)
        if current.parent == current:
            return
        current = current.parent


def _create_run_root(run_root: Path) -> None:
    if run_root.exists() or run_root.is_symlink():
        raise FileExistsError(f"run root already exists: {run_root}")
    run_root.parent.mkdir(parents=True, exist_ok=True)
    _sync_ancestors(run_root.parent)
    run_root.mkdir()
    _sync_directory(run_root.parent)
    _sync_directory(run_root)


def _header(
    program: ClosedProgram,
    *,
    run_id: str,
    workflow_file: str,
    workflow_checksum: str,
    bound_inputs: Mapping[str, Any],
    interpreters: Mapping[str, Mapping[str, str]],
    resume_request: Mapping[str, Any],
    run_ref_root: str,
    result_root: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "result_persistence_profile": PROFILE,
        "run_id": run_id,
        "workflow_file": workflow_file,
        "workflow_checksum": workflow_checksum,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "program_digest": program.digest,
        "input_digest": canonical_sha256(dict(bound_inputs)),
        "bound_inputs": dict(bound_inputs),
        "representation": REPRESENTATION,
        "interpreters": dict(interpreters),
        "resume_request": dict(resume_request),
        "run_ref_root": run_ref_root,
        **({"result_root": result_root} if result_root is not None else {}),
    }


@contextmanager
def publish_run_authority(
    run_root: Path,
    program: ClosedProgram,
    *,
    run_id: str,
    workflow_file: str,
    workflow_checksum: str,
    bound_inputs: Mapping[str, Any],
    resume_request: Mapping[str, Any],
    run_ref_root: str | None = None,
    run_files: WorkspaceFiles | None = None,
    result_root: str | None = None,
) -> Iterator[RunAuthority]:
    """Publish the checked program, header and empty memo under the run lock."""
    from orchestrator.cli.run_ref_root import resolve_run_ref_root

    effective_run_ref_root = resolve_run_ref_root(run_ref_root).as_posix()
    _validate_run_ref_root(effective_run_ref_root)
    validate_resume_request(resume_request)
    if result_root is not None:
        _validate_result_root(result_root, run_id)
    _validate_locator(workflow_file)
    run_root = Path(run_root)
    if ClosedProgram.from_artifact(program.artifact()).digest != program.digest:
        raise RunAuthorityError("program is not a stable checked artifact")
    bound_inputs = _validated_bound_inputs(program, dict(bound_inputs))
    if not _has_command_transport(program):
        raise CommandTransportRequiredError(
            "checked command has no argv transport; rebuild from its source"
        )
    interpreters = _pin_emitted_interpreters(program)
    if run_files is None:
        _create_run_root(run_root)
    with (run_writer_lock(run_root) if run_files is None else nullcontext(run_files.root_fd)) as fd:
        physical = run_files or WorkspaceFiles(run_root, root_fd=fd)
        _publish_retained_program(physical, program)
        header = _header(
            program,
            run_id=run_id,
            workflow_file=workflow_file,
            workflow_checksum=workflow_checksum,
            bound_inputs=bound_inputs,
            interpreters=interpreters,
            resume_request=resume_request,
            run_ref_root=effective_run_ref_root,
            result_root=result_root,
        )
        _require_retained_root(physical)
        physical.write_atomic(HEADER_FILENAME, canonical_json_bytes(header))
        os.fsync(physical.root_fd)
        _require_retained_root(physical)
        yield load_run_authority(run_root, run_files=physical)


def _require_retained_root(run_files: WorkspaceFiles) -> None:
    if not run_root_matches_fd(run_files.workspace, run_files.root_fd):
        raise ReservedRunRootError(run_files.workspace, "changed after the writer lock")


def _publish_retained_program(run_files: WorkspaceFiles, program: ClosedProgram) -> None:
    _require_retained_root(run_files)
    if any(run_files.exists(name) for name in (HEADER_FILENAME, PROGRAM_FILENAME, MEMO_FILENAME)):
        raise RunAuthorityError("reserved run authority already exists")
    run_files.create(MEMO_FILENAME, b"", exclusive=True)
    os.fsync(run_files.root_fd)
    _require_retained_root(run_files)
    run_files.write_atomic(PROGRAM_FILENAME, program.artifact().encode("utf-8"))
    _require_retained_root(run_files)
