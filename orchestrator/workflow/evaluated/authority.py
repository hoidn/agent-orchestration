"""Durable authority files for evaluated runs."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
from typing import Any

from orchestrator._common.io_atomic import durable_atomic_write
from orchestrator.run_lock import run_writer_lock
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


PROFILE = "evaluated_execution.v1"
SCHEMA_VERSION = "3.0"
PROGRAM_FILENAME = "closed_program.json"
HEADER_FILENAME = "run.json"
MEMO_FILENAME = "memo.jsonl"
_HEADER_FIELDS = {
    "schema_version", "result_persistence_profile", "run_id", "workflow_file",
    "workflow_checksum", "started_at", "program_digest", "input_digest",
    "bound_inputs", "representation", "interpreters",
}


class RunAuthorityError(ValueError):
    """An evaluated run lacks valid, mutually consistent authority."""

    code = "memo_inconsistent"


class CommandTransportRequiredError(RunAuthorityError):
    """A compile-only command artifact is not ready for evaluated execution."""

    code = "command_transport_required"


@dataclass(frozen=True, slots=True)
class RunAuthority:
    run_root: Path
    header: Mapping[str, Any]
    program: ClosedProgram

    @property
    def header_path(self) -> Path:
        return self.run_root / HEADER_FILENAME

    @property
    def program_path(self) -> Path:
        return self.run_root / PROGRAM_FILENAME

    @property
    def memo_path(self) -> Path:
        return self.run_root / MEMO_FILENAME


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _read_file(path: Path) -> bytes:
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


def _read_header(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        value = json.loads(
            _read_file(path).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RunAuthorityError(f"invalid run header: {exc}") from exc
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RunAuthorityError(
            "run header contains a non-finite or non-JSON value"
        ) from exc
    if not isinstance(value, dict) or set(value) != _HEADER_FIELDS:
        raise RunAuthorityError("run header has missing or unknown fields")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise RunAuthorityError("unsupported evaluated run schema")
    if value.get("result_persistence_profile") != PROFILE:
        raise RunAuthorityError("unsupported result persistence profile")
    return value


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


def _validate_header_metadata(run_root: Path, header: Mapping[str, Any]) -> None:
    for field in ("workflow_file", "workflow_checksum", "started_at"):
        if not isinstance(header[field], str) or not header[field]:
            raise ValueError(f"{field} is missing")
    if header["run_id"] != run_root.name:
        raise ValueError("run id differs from its root")


def _checked_authority(run_root: Path, header: dict[str, Any]) -> RunAuthority:
    try:
        program = ClosedProgram.from_artifact(
            _read_file(run_root / PROGRAM_FILENAME).decode("utf-8")
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
    return RunAuthority(run_root, header, program)


def load_run_authority(run_root: Path) -> RunAuthority:
    """Read and check immutable run authority without repairing any file."""
    run_root = Path(run_root)
    try:
        header = _read_header(run_root / HEADER_FILENAME)
    except FileNotFoundError as exc:
        memo_path = run_root / MEMO_FILENAME
        try:
            memo = _read_file(memo_path)
        except OSError:
            memo = b""
        if memo:
            raise RunAuthorityError("memo exists without run authority") from exc
        raise RunAuthorityError("run authority header is missing") from exc
    return _checked_authority(run_root, header)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sync_file(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(f"{path.name} is not a regular file")
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


def _create_empty_memo(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("memo journal is not a regular file")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _header(
    program: ClosedProgram,
    *,
    run_id: str,
    workflow_file: str,
    workflow_checksum: str,
    bound_inputs: Mapping[str, Any],
    interpreters: Mapping[str, Mapping[str, str]],
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
) -> Iterator[RunAuthority]:
    """Publish the checked program, header and empty memo under the run lock."""
    run_root = Path(run_root)
    if ClosedProgram.from_artifact(program.artifact()).digest != program.digest:
        raise RunAuthorityError("program is not a stable checked artifact")
    bound_inputs = _validated_bound_inputs(program, dict(bound_inputs))
    if not _has_command_transport(program):
        raise CommandTransportRequiredError(
            "checked command has no argv transport; rebuild from its source"
        )
    interpreters = _pin_emitted_interpreters(program)
    _create_run_root(run_root)
    with run_writer_lock(run_root):
        memo_path = run_root / MEMO_FILENAME
        _create_empty_memo(memo_path)
        _sync_directory(run_root)
        program_path = run_root / PROGRAM_FILENAME
        durable_atomic_write(program_path, program.artifact().encode("utf-8"))
        header = _header(
            program,
            run_id=run_id,
            workflow_file=workflow_file,
            workflow_checksum=workflow_checksum,
            bound_inputs=bound_inputs,
            interpreters=interpreters,
        )
        durable_atomic_write(
            run_root / HEADER_FILENAME,
            canonical_json_bytes(header),
        )
        _sync_file(memo_path)
        _sync_directory(run_root)
        authority = load_run_authority(run_root)
        yield authority
