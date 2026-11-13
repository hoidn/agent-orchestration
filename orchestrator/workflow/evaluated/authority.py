"""Durable authority files for evaluated runs."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
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
from orchestrator.contracts.closed_program.program import ClosedProgram, REPRESENTATION
from orchestrator.contracts.closed_program.sites import _ast_nodes
from orchestrator.workflow.evaluated.interpreters import (
    image_resolvable,
    is_image_pin,
    pin_command_interpreter,
    pin_image_interpreter,
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
    # A view of appended memo rows (the CLI's terminal reporter); not authority.
    observer: Callable[[Mapping[str, Any]], None] | None = field(default=None, compare=False, repr=False)
    # `resume --accept-changes` for this invocation (§8.1); never passed to a child run.
    accept_changes: bool = field(default=False, compare=False, repr=False)
    # `resume --accept-changes=TOKEN` accepted a plan in this invocation (C10): its unproven attempts are accepted
    # as the plan listed them, and the bare flag's "nothing needs it" refusal does not apply. Never passed to a child.
    plan_accepted: bool = field(default=False, compare=False, repr=False)
    # This invocation's `--max-cost-usd` (spend_cap.py); never stored, not authority.
    spend_cap_usd: float | None = field(default=None, compare=False, repr=False)
    # Attempt directories already pending when this invocation began (spend_cap.pending_attempts): cut off,
    # never in flight. None when unknown, so every attempt without usage counts as unmetered.
    cut_off_attempts: frozenset[str] | None = field(default=None, compare=False, repr=False)
    # The run's earlier programs (C10), each with the offset of the `rebased` record that ended it; `program` is the
    # current one. () for a run that never switched program.
    earlier: tuple[tuple[ClosedProgram, int], ...] = field(default=(), repr=False)

    def program_at(self, offset: int) -> ClosedProgram:
        """The program in force when the journal row at `offset` was written."""
        return next((program for program, end in self.earlier if offset < end), self.program)

    @property
    def confined(self) -> bool:
        """The checked child-recipe variant identifies confinement even with no executable pins."""
        return ((self.header.get("resume_request") or {}).get("source_roots") == []
                and self.header["workflow_file"] == (self.run_root / PROGRAM_FILENAME).as_posix())

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


def _emitted_bare_interpreters(program: ClosedProgram, *, image: bool = False) -> list[str]:
    """Bare first tokens for host pins; every image-resolvable argv[0] for image pins.

    A confined argv[0] naming the clone or guest scratch gets no pin: dispatch refuses it.
    """
    bodies = [
        program.tree["body"],
        *(definition["body"] for definition in program.tree["definitions"].values()),
    ]
    pinned = image_resolvable if image else (lambda token: "/" not in token)
    return sorted(
        {
            node["command"][0]
            for body in bodies
            for node in _ast_nodes(body)
            if node.get("k") == "perform"
            and node.get("class") == "command"
            and pinned(node["command"][0])
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


def _pin_emitted_interpreters(program: ClosedProgram, image=None) -> dict[str, dict[str, str]]:
    pins: dict[str, dict[str, str]] = {}
    for token in _emitted_bare_interpreters(program, image=image is not None):
        pin = pin_command_interpreter((token,)) if image is None else pin_image_interpreter(image, token)
        if pin is None:
            raise ValueError(f"bare command interpreter {token!r} was not pinned")
        pins[token] = pin
    return pins


def _validate_interpreter_pins(program: ClosedProgram, pins: object, *, later: bool = False) -> None:
    """The pins equal the first program's bare interpreters; a later program (C10) uses only pinned ones."""
    image = isinstance(pins, dict) and any(map(is_image_pin, pins.values()))
    tokens = _emitted_bare_interpreters(program, image=image)
    if later and isinstance(pins, dict) and not set(tokens) <= set(pins):
        raise ValueError("a later program of the run uses a bare interpreter the run did not pin")
    if not isinstance(pins, dict) or not later and set(pins) != set(tokens) or (
            image and not all(map(is_image_pin, pins.values()))):
        raise ValueError("interpreter pins differ from emitted command interpreters")
    for token in tokens:
        validate_command_interpreter_pin_shape(pins[token])


def _checked_authority(run_root: Path, header: dict[str, Any], run_files: WorkspaceFiles | None = None) -> RunAuthority:
    try:
        payload = _read_file(run_root / PROGRAM_FILENAME, run_files)
        memo = _read_file(run_root / MEMO_FILENAME, run_files)          # only its `rebased` records are decoded
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        if isinstance(exc, RunAuthorityError):
            raise
        raise RunAuthorityError(f"invalid evaluated authority: {exc}") from exc
    return _checked_authority_bytes(run_root, header, payload, run_files, memo_bytes=memo,
                                    read_artifact=lambda name: _read_file(run_root / name, run_files))


def program_artifact_name(digest: str) -> str:
    """The run-root file of a program the run switched to (C10): `closed_program.<64 hex digits>.json`."""
    return f"closed_program.{digest.removeprefix('sha256:')}.json"


def verified_program(read_artifact: Callable[[str], bytes], digest: str, name: str | None = None) -> ClosedProgram:
    """The checked program stored under `name` (default: `digest`'s artifact name) with that digest.

    Missing, unreadable, unloadable or another digest: `RunAuthorityError` (`memo_inconsistent`); nothing is
    rebuilt from source. `from_artifact` also refuses any representation but this build's.
    """
    name = program_artifact_name(digest) if name is None else name
    try:
        program = ClosedProgram.from_artifact(read_artifact(name).decode("utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise RunAuthorityError(f"program artifact {name} is missing or does not load: {exc}") from exc
    if program.digest != digest:
        raise RunAuthorityError(f"program artifact {name} does not have the digest that names it")
    return program


def _lineage(header, first: ClosedProgram, memo_bytes, read_artifact):
    """(earlier programs with the offset of the record that ended each, current program) (C10).

    Each later program is the artifact its `rebased` record names, verified to that name, with command transport,
    only pinned bare interpreters, and parameters that bind the header's inputs in checked form. Without journal bytes (a child's captured authority) the first program is
    the current one, and a record there fails closed in the child's reductions.
    """
    from .memo_reducer_lineage import lineage_digests, rebased_records

    records = [] if memo_bytes is None else rebased_records(memo_bytes)
    if not records:
        return (), first
    digests = lineage_digests(header["program_digest"], [digest for _offset, digest in records])
    programs = [first, *(verified_program(read_artifact, digest) for digest in digests[1:])]
    for program in programs[1:]:
        if not _has_command_transport(program):
            raise ValueError("stored command is missing argv transport")
        _validate_interpreter_pins(program, header["interpreters"], later=True)
        try:        # resume binds the header's inputs to the program in force; one that cannot is no lineage
            _validated_bound_inputs(program, header["bound_inputs"])
        except (TypeError, ValueError) as exc:
            raise RunAuthorityError(f"a later program of the run cannot bind the run's inputs: {exc}") from exc
    return tuple(zip(programs, (offset for offset, _digest in records))), programs[-1]


def _checked_authority_bytes(run_root, header, program_bytes, run_files=None, *, memo_bytes=None, read_artifact=None):
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
        earlier, program = _lineage(header, program, memo_bytes, read_artifact)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        if isinstance(exc, RunAuthorityError) or getattr(exc, "code", None) == "memo_inconsistent":
            raise       # its own code and message (a lineage record or artifact), not wrapped again
        raise RunAuthorityError(f"invalid evaluated authority: {exc}") from exc
    return RunAuthority(run_root, header, program, run_files, earlier=earlier)


def load_run_authority_from_bytes(run_root: Path, *, header_bytes: bytes, program_bytes: bytes,
                                  memo_bytes: bytes | None = None, read_artifact=None) -> RunAuthority:
    """Check captured authority using the same validators as path/FD loaders.

    With the captured `memo_bytes` the run's lineage is resolved too, each named artifact read once through
    `read_artifact(name) -> bytes`; without them the first program is the current one.
    """
    run_root = Path(run_root)
    header = _validate_header_shape(_decode_header_json(header_bytes))
    try:
        _validate_header_metadata(run_root, header)
    except (TypeError, ValueError) as exc:
        raise RunAuthorityError(f"invalid evaluated run header: {exc}") from exc
    return _checked_authority_bytes(run_root, header, program_bytes, memo_bytes=memo_bytes,
                                    read_artifact=read_artifact)


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
    image=None,
) -> Iterator[RunAuthority]:
    """Publish the checked program, header and empty memo under the run lock.

    `image` (a run_ref SealedImage) pins confined children's executables inside it.
    """
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
    interpreters = _pin_emitted_interpreters(program, image)
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
