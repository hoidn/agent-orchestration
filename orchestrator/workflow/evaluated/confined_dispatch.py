"""Dispatch side of confined run-ref leaves (`run_ref_confinement.v1`).

Builds a :class:`~orchestrator.workflow.run_ref.leaf.LeafRequest` from a prepared
evaluated attempt and adapts the :class:`LeafOutcome` back to the shapes the
host command path expects; the holder runtime that runs the leaf is injected as a
:class:`LeafRunner`. Nothing here launches a process or reads the host environment.

Units the evaluated runtime wires in around `started` (Task 6c):

* `require_confinable`: the Q1 dispatch refusal, before `started` and with no
  attempt record: argv[0], interpreters and declared closures must be image pinned.
* `image_implementation_files`: the C4 evidence of a confined command (image pins
  only), used both for the retry comparison and the precommit rehash (Q2).
* `bind_clone_inputs` / `store_attempt_snapshot` / `verify_attempt_snapshot`: the
  D5 attempt snapshot of clone files named by stable-command tokens and `:doc`
  fills (P1, Q3, Q5), recorded as `clone-*` input parts in `started`.

Dependencies: a run_ref `SealedImage` (retained rootfs descriptor and record), the
child's clone and control-root `WorkspaceFiles`, and the injected runner. The
remaining wall budget and evidence allowance are inputs owned by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path, PurePosixPath
import posixpath
import stat
from typing import Any, Literal, Mapping, Sequence

from orchestrator._common.safe_tree import SafeTreeError, read_regular_file
from orchestrator.exec.output_capture import CaptureMode, CaptureResult
from orchestrator.exec.step_executor import ExecutionResult
from orchestrator.workflow.run_ref.checkpoint import MAX_CHECKPOINT_ENTRIES, MAX_TREE_DEPTH
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.run_ref.image_store import SealedImage, tree_digest
from orchestrator.workflow.run_ref.leaf import LeafRequest, LeafRunner
from orchestrator.workflow.workspace_files import WorkspaceFiles

from .closure_evidence import command_evidence_key, validate_implementation_evidence
from .commands import CommandPerformerError, launch_command
from .interpreters import (
    GUEST_PATH, image_file_digest, image_resolvable, is_image_pin, resolve_image_path,
)


EFFECT_UNSUPPORTED = "run_ref_environment_effect_unsupported"
TRANSPORT_UNAVAILABLE = "run_ref_provider_transport_unavailable"
BUDGET_EXHAUSTED = "run_ref_budget_exhausted"
EVIDENCE_INVALID = "run_ref_evidence_invalid"
ESCAPE_REJECTED = "run_ref_environment_escape_rejected"
GUEST_WORKSPACE = "/workspace"
GUEST_RESULT = "/result"
# The complete base environment of every leaf; the attempt overlay is added on top.
GUEST_ENV = {"PATH": ":".join(GUEST_PATH), "HOME": "/tmp", "TMPDIR": "/tmp"}
OUTPUT_LIMIT = 16 * 1024 * 1024
CLONE_FILE, CLONE_LINK, CLONE_DIRECTORY = "clone-file:", "clone-link:", "clone-directory:"
_DIRECTORY_MARKER = canonical_json_bytes({"directory": True})
_DIRECTORY_MARKER_DIGEST = "sha256:" + hashlib.sha256(_DIRECTORY_MARKER).hexdigest()
_NOFOLLOW_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class ConfinedDispatchRefusal(RuntimeError):
    """A coded refusal of a confined effect; before `started` it leaves no attempt record."""

    def __init__(self, code: str) -> None:
        # Guest-controlled names/argv can reproduce an old capability. Codes
        # retain refusal semantics; never interpolate those bytes in metadata.
        self.detail = "confined_dispatch_refused"
        super().__init__(f"{code}: {self.detail}")
        self.code = code


@dataclass(frozen=True)
class ConfinedLeafContext:
    """What one confined attempt dispatches through; supplied by the child runtime."""

    runner: LeafRunner
    image: SealedImage
    network: Literal["none", "model-only"]
    remaining_wall_seconds: float      # the child's cumulative `:wall-seconds` left (R3)
    stdout_limit: int = OUTPUT_LIMIT
    stderr_limit: int = OUTPUT_LIMIT


# --- guest spelling (R2/R3) -------------------------------------------------------------

def leaf_id(result_path: str) -> str:
    """One path component naming the attempt: `<identity digest>-attempt-<N>`."""
    parts = PurePosixPath(result_path).parent.parts
    if len(parts) != 3 or parts[0] != "effects":
        raise ValueError(f"not an evaluated attempt result path: {result_path!r}")
    return f"{parts[1]}-{parts[2]}"


def guest_result_path(result_path: str) -> str:
    return f"{GUEST_RESULT}/{leaf_id(result_path)}/result.json"


def guest_cwd(clone_root: Path, launch_cwd: Path | None) -> str:
    if launch_cwd is None:
        return GUEST_WORKSPACE
    relative = _clone_relative(".", os.path.relpath(launch_cwd, clone_root))
    if relative is None:
        raise ConfinedDispatchRefusal(EFFECT_UNSUPPORTED)
    return GUEST_WORKSPACE if relative == "." else f"{GUEST_WORKSPACE}/{relative}"


# --- Q1 dispatch refusal and C4 image evidence ------------------------------------------

def require_confinable(node: Mapping[str, Any], pins: Mapping[str, Any]) -> None:
    """Refuse an effect the confined profile cannot run, before `started` (Q1)."""
    kind = node.get("class")
    if kind == "provider":
        raise ConfinedDispatchRefusal(TRANSPORT_UNAVAILABLE)
    if kind != "command":
        raise ConfinedDispatchRefusal(EFFECT_UNSUPPORTED)
    executable = node["command"][0]
    if not image_resolvable(executable):
        raise ConfinedDispatchRefusal(EFFECT_UNSUPPORTED)
    if not is_image_pin(pins.get(executable)):
        raise ConfinedDispatchRefusal(EFFECT_UNSUPPORTED)
    for row in node.get("closure") or ():
        if row.get("base") != "absolute" or not image_resolvable(row.get("path", "")):
            raise ConfinedDispatchRefusal(EFFECT_UNSUPPORTED)


def image_implementation_files(node: Mapping[str, Any], pins: Mapping[str, Any],
                               image: SealedImage) -> dict[str, dict[str, Any]]:
    """C4 evidence of a confined command: its executable and closure, from image bytes only.

    Clone files the command names are bound by the attempt snapshot instead, so a
    command may rewrite them without failing its precommit rehash (Q2).
    """
    executable = pins[node["command"][0]]["path"]
    rows = {command_evidence_key("absolute", executable, 0): _image_row(image, executable)}
    for row in node.get("closure") or ():
        path = posixpath.normpath(row["path"])
        rows[command_evidence_key("absolute", path)] = _image_row(image, path)
    return validate_implementation_evidence(rows)


def _image_row(image: SealedImage, path: str) -> dict[str, Any]:
    try:
        resolved = resolve_image_path(image.root_fd, path)
        if not image_resolvable(resolved):
            raise ConfinedDispatchRefusal(EFFECT_UNSUPPORTED)
        info = os.stat(resolved.lstrip("/") or ".", dir_fd=image.root_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            fd = os.open(resolved.lstrip("/") or ".", _NOFOLLOW_DIRECTORY, dir_fd=image.root_fd)
            try:
                row = {"kind": "directory", "digest": tree_digest(fd)}
            finally:
                os.close(fd)
        else:
            row = {"kind": "file", "digest": image_file_digest(image.root_fd, resolved)}
    except (OSError, SafeTreeError) as exc:
        raise ConfinedDispatchRefusal(EFFECT_UNSUPPORTED) from exc
    return {**row, "target": resolved} if resolved != path else row


# --- leaf dispatch -----------------------------------------------------------------------

class LeafCommandExecutor:
    """`StepExecutor.execute_command`-compatible adapter over one confined leaf."""

    def __init__(self, context: ConfinedLeafContext, attempt_files: WorkspaceFiles,
                 leaf: str, input_files: Mapping[str, bytes]) -> None:
        self.context, self.attempt_files, self.leaf, self.input_files = context, attempt_files, leaf, input_files

    def execute_command(self, step_name: str, command: Sequence[str], *, cwd: Path,
                        env: Mapping[str, str], timeout_sec: float | None = None, **_capture: Any) -> ExecutionResult:
        remaining = self.context.remaining_wall_seconds
        if remaining <= 0:
            raise CommandPerformerError(BUDGET_EXHAUSTED, "child wall budget is exhausted before dispatch")
        wall_bound = timeout_sec is None or remaining <= timeout_sec
        outcome = self.context.runner.run_leaf(LeafRequest(
            leaf_id=self.leaf, argv=tuple(command), env={**GUEST_ENV, **env}, cwd=str(cwd),
            timeout_sec=float(remaining if wall_bound else timeout_sec),
            stdout_limit=self.context.stdout_limit, stderr_limit=self.context.stderr_limit,
            input_files=dict(self.input_files), network=self.context.network))
        self.attempt_files.create("stdout.txt", outcome.stdout, exclusive=True)
        self.attempt_files.create("stderr.txt", outcome.stderr, exclusive=True)
        flags = {"stdout_truncated": outcome.stdout_truncated, "stderr_truncated": outcome.stderr_truncated}
        self.attempt_files.create("streams.json", canonical_json_bytes(flags), exclusive=True)  # P31 evidence
        if "result.json" in outcome.result_files:
            self.attempt_files.create("result.json", outcome.result_files["result.json"], exclusive=True)
        if outcome.holder_death is not None:
            death = outcome.holder_death
            raise CommandPerformerError(death.code, f"confined leaf lost its holder: {death.detail}",
                exit_info={"exit_code": None, "holder_death": {"code": death.code, "detail": death.detail}, **flags})
        if outcome.timed_out and wall_bound:
            raise CommandPerformerError(BUDGET_EXHAUSTED, "confined leaf ran out of the child wall budget",
                exit_info={"exit_code": None, **flags})
        if outcome.lingered:  # P29: exited, but left processes the holder had to kill
            raise CommandPerformerError("command_exit_nonzero", "confined leaf left lingering processes behind",
                exit_info={"exit_code": outcome.exit_code, "lingered": True, **flags})
        exit_code = 124 if outcome.timed_out else (-1 if outcome.exit_code is None else outcome.exit_code)
        error = ({"type": "timeout", "message": f"Command timed out after {timeout_sec} seconds",
                  "context": {"timeout_sec": timeout_sec}} if outcome.timed_out else None)
        return ExecutionResult(step_name=step_name, exit_code=exit_code, duration_ms=outcome.duration_ms,
            error=error, capture_result=CaptureResult(mode=CaptureMode.TEXT, truncated=outcome.stdout_truncated,
                                                      exit_code=exit_code, debug=flags))


def dispatch_confined(attempt: Any) -> str:
    """Perform one confined attempt through its leaf runner; no host route exists."""
    node, pins = attempt.node, attempt.authority.header["interpreters"]
    require_confinable(node, pins)
    resolved_argv, document = attempt.resolved
    leaf = leaf_id(attempt.result_path)
    argv = [pins[node["command"][0]]["path"], *resolved_argv[1:]]
    if document is not None:
        argv.append(f"{GUEST_RESULT}/{leaf}/inputs.json")
    executor = LeafCommandExecutor(attempt.confined, attempt.attempt_files, leaf,
                                   {} if document is None else {"inputs.json": document})
    return launch_command(node, argv, attempt_files=attempt.attempt_files,
        workspace_files=attempt.workspace_files, input_document=document,
        launch_cwd=Path(guest_cwd(attempt.workspace, attempt.launch_cwd)),
        executor=executor, result_locator=guest_result_path(attempt.result_path))


# --- D5 attempt snapshots (P1, Q3, Q5) ---------------------------------------------------

@dataclass(frozen=True)
class CloneBinding:
    """Clone inputs bound at `started`: `parts` joins the started record's input parts
    (the evidence map); `blobs` holds the content-addressed bytes, keyed by digest."""

    parts: dict[str, str] = field(default_factory=dict)
    blobs: dict[str, bytes] = field(default_factory=dict)


def _clone_relative(guest_cwd_relative: str, token: str) -> str | None:
    guest = posixpath.normpath(posixpath.join(GUEST_WORKSPACE, guest_cwd_relative, token))
    if guest == GUEST_WORKSPACE:
        return "."
    return guest[len(GUEST_WORKSPACE) + 1:] if guest.startswith(GUEST_WORKSPACE + "/") else None


def command_clone_rows(node: Mapping[str, Any], guest_cwd_relative: str = ".") -> list[tuple[str, str]]:
    """`(argv position, clone path)` of every stable-command token naming the clone (C2).

    argv[0] is excluded: an executable in the clone is refused by `require_confinable`.
    """
    rows = []
    for position, token in enumerate(node["command"][1:], start=1):
        relative = _clone_relative(guest_cwd_relative, token)
        if relative is not None:
            rows.append((str(position), relative))
    return rows


def document_clone_rows(node, operands, files):
    """Bind typed document paths to the same D5 snapshots as stable command tokens."""
    from orchestrator.contracts.output_contract import _require_nested_transport_path
    from orchestrator.workflow.type_descriptor import validate_transport_value
    from .commands import command_document_operands

    if "document" not in node:
        return []
    rows = []
    for index, value in enumerate(command_document_operands(node, operands)):
        def capture(path, descriptor):
            path = _require_nested_transport_path(path, descriptor, files.workspace, workspace_files=files)
            rows.append((f"document-{index}", path))
            return path
        validate_transport_value(value.json_value(), value.descriptor, allow_nested_structures=True,
                                 path_validator=capture)
    return rows


def bind_clone_inputs(rows: Sequence[tuple[str, str]], clone: WorkspaceFiles, *, max_bytes: int,
                      directory_rows: Sequence[tuple[str, str]] = ()) -> CloneBinding:
    """Select and read named clone files through the no-follow reader (Q5).

    Every component is opened no-follow beneath the clone root and pinned to its
    device; a symlink (token or component) binds its target string and is never
    followed; a directory binds the files beneath it; absent paths and special
    files bind nothing. More than `max_bytes` in total refuses.
    """
    binding = CloneBinding()
    walk = _Bind(binding, os.fstat(clone.root_fd).st_dev, max_bytes)
    selected_directories = set(directory_rows)
    for label, relative in rows:
        walk.path(clone.root_fd, label, relative, directory=(label, relative) in selected_directories)
    return binding


@dataclass
class _Bind:
    binding: CloneBinding
    device: int
    remaining: int
    entries: int = 0

    def add(self, kind: str, label: str, path: str, content: bytes) -> None:
        try:
            name = f"{kind}{label}:{path}"
            name.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ConfinedDispatchRefusal(ESCAPE_REJECTED) from exc
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        self.binding.parts[name] = digest
        self.binding.blobs[digest] = content

    def path(self, root_fd: int, label: str, relative: str, *, directory=False) -> None:
        parts = [] if relative == "." else relative.split("/")
        fd = os.dup(root_fd)
        try:
            for index, name in enumerate(parts):
                prefix = "/".join(parts[: index + 1])
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except (FileNotFoundError, NotADirectoryError):
                    return
                if stat.S_ISLNK(info.st_mode) or (index == len(parts) - 1 and not stat.S_ISDIR(info.st_mode)):
                    self.entry(fd, name, info, label, prefix)
                    return
                if not stat.S_ISDIR(info.st_mode):
                    return
                child = os.open(name, _NOFOLLOW_DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = child
                if os.fstat(fd).st_dev != self.device:
                    raise ConfinedDispatchRefusal(ESCAPE_REJECTED)
            if os.fstat(fd).st_dev != self.device:
                raise ConfinedDispatchRefusal(ESCAPE_REJECTED)
            if directory:
                self.count_entry()
                self.add(CLONE_DIRECTORY, label, relative, _DIRECTORY_MARKER)
            self.tree(fd, label, relative, depth=0)
        finally:
            os.close(fd)

    def tree(self, fd: int, label: str, prefix: str, *, depth: int) -> None:
        if depth > MAX_TREE_DEPTH:
            raise ConfinedDispatchRefusal(ESCAPE_REJECTED)
        if os.fstat(fd).st_dev != self.device:
            raise ConfinedDispatchRefusal(ESCAPE_REJECTED)
        names = []
        with os.scandir(fd) as entries:
            for entry in entries:
                if entry.name == "__pycache__" or (prefix == "." and entry.name in (".git", ".orchestrate")):
                    continue
                self.count_entry()
                names.append(entry.name)
        for name in sorted(names):
            path = name if prefix == "." else f"{prefix}/{name}"
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, _NOFOLLOW_DIRECTORY, dir_fd=fd)
                try:
                    self.tree(child, label, path, depth=depth + 1)
                finally:
                    os.close(child)
            else:
                self.entry(fd, name, info, label, path, counted=True)

    def count_entry(self) -> None:
        self.entries += 1
        if self.entries > MAX_CHECKPOINT_ENTRIES:
            raise ConfinedDispatchRefusal(ESCAPE_REJECTED)

    def entry(self, fd: int, name: str, info: os.stat_result, label: str, path: str, *, counted=False) -> None:
        if not counted:
            self.count_entry()
        if stat.S_ISLNK(info.st_mode):
            try:
                link = canonical_json_bytes({"symlink": os.readlink(name, dir_fd=fd)})
            except UnicodeEncodeError as exc:
                raise ConfinedDispatchRefusal(ESCAPE_REJECTED) from exc
            self.add(CLONE_LINK, label, path, link)
        elif stat.S_ISREG(info.st_mode):
            if info.st_size > self.remaining:
                raise ConfinedDispatchRefusal(BUDGET_EXHAUSTED)
            try:
                content = read_regular_file(fd, name, max_bytes=self.remaining, device=self.device)
            except SafeTreeError as exc:
                raise ConfinedDispatchRefusal(ESCAPE_REJECTED) from exc
            self.remaining -= len(content)
            self.add(CLONE_FILE, label, path, content)


def store_attempt_snapshot(store: WorkspaceFiles, blobs: Mapping[str, bytes], *, allowance_bytes: int) -> int:
    """Store bound bytes content-addressed; check the evidence allowance before any copy (Q3).

    Returns the bytes added (charged to the evidence allowance by the caller); stored
    blobs are reused only when their bytes still hash to their name.
    """
    new = {}
    for digest, content in blobs.items():
        name = digest.removeprefix("sha256:")
        if not store.exists(name):
            new[name] = content
        elif store.sha256(name) != digest:
            raise ConfinedDispatchRefusal(EVIDENCE_INVALID)
    added = sum(len(content) for content in new.values())
    if added > allowance_bytes:
        raise ConfinedDispatchRefusal(BUDGET_EXHAUSTED)
    for name, content in new.items():
        store.write_atomic(name, content)
    return added


def verify_attempt_snapshot(store: WorkspaceFiles, parts: Mapping[str, str]) -> dict[str, str]:
    """Verify a recorded evidence map against its snapshot bytes before recomputation.

    Returns the `clone-*` parts, which replay reuses instead of reading the current
    clone; a missing or altered blob is tampered evidence (never `effect_input_diverged`).
    """
    bound = {name: digest for name, digest in parts.items() if name.startswith((CLONE_FILE, CLONE_LINK, CLONE_DIRECTORY))}
    for name, digest in bound.items():
        if name.startswith(CLONE_DIRECTORY) and digest != _DIRECTORY_MARKER_DIGEST:
            raise ConfinedDispatchRefusal(EVIDENCE_INVALID)
        try:
            actual = store.sha256(digest.removeprefix("sha256:"))
        except (OSError, ValueError):
            actual = None
        if actual != digest:
            raise ConfinedDispatchRefusal(EVIDENCE_INVALID)
    return bound


class SnapshotPaths:
    """The lexical path/existence reader needed by document replay, using verified evidence only."""

    def __init__(self, workspace: Path, parts: Mapping[str, str]):
        self.workspace = workspace
        self.files, self.links, self.directories = set(), set(), set()
        kinds = {CLONE_FILE[:-1]: self.files, CLONE_LINK[:-1]: self.links,
                 CLONE_DIRECTORY[:-1]: self.directories}
        for name in parts:
            kind, _label, path = name.split(":", 2)
            kinds[kind].add(path)

    def relative(self, path):
        path = Path(path)
        if path.is_absolute():
            path = path.relative_to(self.workspace)
        if ".." in path.parts:
            raise ValueError("snapshot path escapes workspace")
        return path

    def exists(self, path):
        relative = self.relative(path).as_posix()
        if any(relative == link or relative.startswith(link + "/") for link in self.links):
            raise OSError("snapshot path passes through a symlink")
        if any(relative.startswith(path + "/") for path in self.files):
            raise OSError("snapshot path passes through a regular file")
        return relative == "." or relative in self.files | self.directories or any(
            name.startswith(relative + "/") for name in self.files | self.links | self.directories)
