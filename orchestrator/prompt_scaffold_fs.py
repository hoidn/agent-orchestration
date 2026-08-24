"""Descriptor-safe scaffold filesystem mechanics (Task 7 sibling).

A narrowly named sibling of ``orchestrator.prompt_scaffold``: no-follow
directory-chain opens (with descriptor-relative creation), tree writing with
exclusive creation, per-identity flock publication with parent-identity
revalidation and ``renameat2(RENAME_NOREPLACE)``, verified-only temp cleanup,
run-owned private snapshot materialization through a retained directory
descriptor, and the Stage 3 compile-check contract derivation through
``/proc/self/fd`` paths — never the mutable published/generated path. Occupant
verification against deterministic bytes lives in the sibling
``prompt_scaffold_verify``; ``prompt_scaffold`` re-exports the public
compile/snapshot services.
"""

from __future__ import annotations

import errno
import fcntl
import os
import secrets
import stat
from pathlib import Path
from typing import Mapping

from orchestrator._common.io_atomic import rename_noreplace_at
from orchestrator._common.safe_tree import validate_relative_path
from orchestrator.prompt_contract import (
    SemanticContract,
    contracts_structurally_equal,
)
from orchestrator.prompt_scaffold import (
    PUBLIC_PROVIDER_NAMES,
    RunSnapshot,
    ScaffoldCompileError,
    ScaffoldInputs,
    ScaffoldLockError,
    ScaffoldPublicationError,
    ScaffoldSnapshotError,
    ScaffoldVerification,
    ScaffoldVerificationError,
)
from orchestrator.prompt_scaffold_render import (
    _fd_root,
    compile_check,
    derive_compiled_contract,
)
from orchestrator.prompt_scaffold_verify import verify_occupant
from orchestrator.providers.omp_launch_fs import directory_identity
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint

_NOFOLLOW_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_MODE = "0644"


def open_generated_root(path: Path) -> int:
    """Open a directory with every component no-follow; symlink/special
    components and final non-directories fail closed."""
    absolute = Path(os.path.abspath(path))
    current = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in absolute.parts[1:]:
            if not part or part == os.sep:
                continue
            try:
                next_fd = os.open(part, _NOFOLLOW_DIR, dir_fd=current)
            except OSError as exc:
                raise ScaffoldVerificationError(
                    f"refusing non-directory or symlink component {part!r}: {exc}"
                ) from exc
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


def _open_parent_dirs(parent_fd: int, relative: str, dir_mode: int) -> tuple[int, list[int]]:
    """Create and open a file path's parent components; return the leaf dir fd
    and every descriptor this helper opened (caller closes all of them; the
    caller-owned ``parent_fd`` is never closed here). Paths are validated so a
    forged mapping cannot traverse via ``..``; created entries are fsynced."""
    validate_relative_path(relative)
    current = parent_fd
    opened: list[int] = []
    try:
        for component in relative.split("/")[:-1]:
            try:
                os.mkdir(component, dir_mode, dir_fd=current)
                os.fsync(current)
            except FileExistsError:
                pass
            next_fd = os.open(component, _NOFOLLOW_DIR, dir_fd=current)
            opened.append(next_fd)
            current = next_fd
        return current, opened
    except BaseException:
        for fd in reversed(opened):
            os.close(fd)
        raise


def write_tree(root_fd: int, files: Mapping[str, bytes], file_mode: int) -> None:
    """Write a tree beneath root_fd; files get ``file_mode`` (via fchmod
    before the file fsync), dirs 0755, no-follow, exclusive creation; the
    created directory entry is fsynced through its parent descriptor."""
    for relative in sorted(files, key=lambda p: (p.count("/"), p)):
        parent, owned = _open_parent_dirs(root_fd, relative, 0o755)
        try:
            try:
                fd = os.open(
                    relative.split("/")[-1],
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                    | os.O_CLOEXEC,
                    0o600,
                    dir_fd=parent,
                )
            except FileExistsError as exc:
                raise ScaffoldVerificationError(
                    f"refusing to overwrite existing entry {relative!r}"
                ) from exc
            with os.fdopen(fd, "wb") as handle:
                handle.write(files[relative])
                handle.flush()
                os.fchmod(handle.fileno(), file_mode)
                os.fsync(handle.fileno())
            os.fsync(parent)
        finally:
            for fd in reversed(owned):
                os.close(fd)


def acquire_scaffold_lock(root_fd: int, identity: str) -> int:
    """flock the per-identity publication lock inside the generated root.

    The lock leaf is opened with ``O_NOFOLLOW`` (a symlink/FIFO/special leaf
    fails closed without touching its target) and ``O_NONBLOCK`` (a FIFO or
    device leaf cannot block the open); the opened descriptor must be exactly
    one regular file."""
    try:
        os.mkdir(".omp-scaffold-locks", 0o700, dir_fd=root_fd)
    except FileExistsError:
        pass
    try:
        lock_dir_fd = os.open(".omp-scaffold-locks", _NOFOLLOW_DIR, dir_fd=root_fd)
    except OSError as exc:
        raise ScaffoldLockError(
            f"lock directory is not a real directory: {exc}"
        ) from exc
    try:
        try:
            lock_fd = os.open(
                f"{identity}.lock",
                os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
                | os.O_NONBLOCK,
                0o600,
                dir_fd=lock_dir_fd,
            )
        except OSError as exc:
            raise ScaffoldLockError(
                f"lock leaf is not a plain regular file: {exc}"
            ) from exc
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            os.close(lock_fd)
            raise ScaffoldLockError(
                "lock leaf is not a regular file; refusing to flock it"
            )
    finally:
        os.close(lock_dir_fd)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except OSError as exc:
        os.close(lock_fd)
        raise ScaffoldLockError(f"flock failed: {exc}") from exc
    return lock_fd


# --- publication ---------------------------------------------------------------


def publish_scaffold(
    root_fd: int,
    *,
    generated_root: Path,
    destination_name: str,
    files: Mapping[str, bytes],
    identity: str,
    inputs: ScaffoldInputs,
    expected_files: Mapping[str, bytes],
) -> tuple[ScaffoldVerification, bool]:
    """Publish one scaffold atomically; returns (verification, reused).

    A fresh publication writes a 0700 temp sibling, compile-checks it through
    a retained descriptor, revalidates the generated-parent identity, and
    renames it over the destination with ``RENAME_NOREPLACE``. A pre-existing
    or racing occupant is verified against the current inputs' deterministic
    bytes and reused only when byte-identical; anything else refuses (no
    delete, replace, force, or fallback). ``reused`` is True exactly when the
    returned verification describes a pre-existing/racing winner.
    """
    expected_paths = set(files) - {"scaffold.json"}
    root_identity = os.fstat(root_fd)
    try:
        scaffold_fd = os.open(destination_name, _NOFOLLOW_DIR, dir_fd=root_fd)
    except FileNotFoundError:
        scaffold_fd = None
    if scaffold_fd is not None:
        try:
            verification = verify_occupant(
                scaffold_fd, inputs, identity, expected_paths, expected_files
            )
        finally:
            os.close(scaffold_fd)
        return verification, True

    temp_name = f".omp-scaffold-{os.getpid()}-{secrets.token_hex(8)}"
    # Failed or racing temp dirs are left in place for operator inspection:
    # automatic recursive deletion cannot guarantee "never deletes unknown
    # data" against a name swap, and X7 requires no such cleanup.
    # ponytail: if temp debris becomes operationally significant, clean it up
    # offline under exclusive ownership of the generated root (or have the
    # operator remove it explicitly); never automate rmtree in this hot path.
    try:
        os.mkdir(temp_name, 0o700, dir_fd=root_fd)
    except FileExistsError as exc:
        raise ScaffoldPublicationError(
            f"temp publication dir collision: {temp_name}"
        ) from exc
    temp_fd = os.open(temp_name, _NOFOLLOW_DIR, dir_fd=root_fd)
    try:
        write_tree(temp_fd, files, file_mode=0o644)
        os.fsync(temp_fd)
        derived = compile_check(temp_fd, inputs.provider)
        if not contracts_structurally_equal(derived, inputs.contract):
            raise ScaffoldCompileError(
                "compiled contract disagrees with the declared contract"
            )
    finally:
        os.close(temp_fd)
    try:
        current_identity = directory_identity(str(generated_root))
    except Exception as exc:
        raise ScaffoldPublicationError(
            f"generated root cannot be revalidated: {exc}"
        ) from exc
    if current_identity != (root_identity.st_dev, root_identity.st_ino):
        raise ScaffoldPublicationError(
            "generated root changed identity; refusing to publish"
        )
    try:
        rename_noreplace_at(root_fd, temp_name, root_fd, destination_name)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise ScaffoldPublicationError(
                f"RENAME_NOREPLACE failed: {exc}"
            ) from exc
        try:
            scaffold_fd = os.open(
                destination_name, _NOFOLLOW_DIR, dir_fd=root_fd
            )
        except FileNotFoundError as nested:
            raise ScaffoldPublicationError(
                "RENAME_NOREPLACE reported EEXIST but the destination vanished"
            ) from nested
        try:
            verification = verify_occupant(
                scaffold_fd, inputs, identity, expected_paths, expected_files
            )
        finally:
            os.close(scaffold_fd)
        return verification, True
    else:
        os.fsync(root_fd)
        scaffold_fd = os.open(
            destination_name, _NOFOLLOW_DIR, dir_fd=root_fd
        )
    try:
        verification = verify_occupant(
            scaffold_fd, inputs, identity, expected_paths, expected_files
        )
    finally:
        os.close(scaffold_fd)
    return verification, False


# --- run-owned private snapshot --------------------------------------------------


def open_root_creating(path: Path) -> int:
    """Open a directory tree, creating missing components, with every
    existing component traversed no-follow; a symlinked ancestor fails closed
    without writing through it."""
    absolute = Path(os.path.abspath(path))
    current = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in absolute.parts[1:]:
            if not part or part == os.sep:
                continue
            try:
                next_fd = os.open(part, _NOFOLLOW_DIR, dir_fd=current)
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    try:
                        os.mkdir(part, 0o755, dir_fd=current)
                        os.fsync(current)
                        next_fd = os.open(part, _NOFOLLOW_DIR, dir_fd=current)
                    except OSError as create_exc:
                        raise ScaffoldSnapshotError(
                            f"cannot create {part!r}: {create_exc}"
                        ) from create_exc
                else:
                    raise ScaffoldSnapshotError(
                        f"refusing non-directory or symlink component "
                        f"{part!r}: {exc}"
                    ) from exc
            os.close(current)
            current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise


def create_run_root(runs_root: Path, run_id: str) -> Path:
    """Exclusively create the run root (0700) descriptor-relative; pre-existing
    roots and symlinked ancestors fail closed without writing through them."""
    if (
        not run_id
        or "/" in run_id
        or run_id in (".", "..")
        or "\x00" in run_id
    ):
        raise ScaffoldSnapshotError(f"invalid run id {run_id!r}")
    root_fd = open_root_creating(Path(runs_root))
    try:
        try:
            os.mkdir(run_id, 0o700, dir_fd=root_fd)
        except FileExistsError as exc:
            raise ScaffoldSnapshotError(
                f"run root already exists: {runs_root / run_id}"
            ) from exc
        os.fsync(root_fd)
    finally:
        os.close(root_fd)
    return Path(runs_root) / run_id


def _freeze_directory_modes(root_fd: int) -> None:
    """Post-order fchmod 0500 through retained descriptors; root last.

    Every directory is fsynced after its fchmod so the freeze is durable even
    on crash (file fchmod-before-fsync is already handled at write time)."""
    def freeze(fd: int) -> None:
        for entry in os.listdir(fd):
            info = os.lstat(entry, dir_fd=fd)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(entry, _NOFOLLOW_DIR, dir_fd=fd)
                try:
                    freeze(child)
                finally:
                    os.close(child)
        os.fchmod(fd, 0o500)
        os.fsync(fd)

    freeze(root_fd)


def materialize_run_snapshot(
    verification: ScaffoldVerification, run_root: Path
) -> RunSnapshot:
    """Materialize the private snapshot from verification-captured bytes only.

    The run root is reopened with every ancestor no-follow; every file is
    created no-follow with exclusive creation, fchmodded 0400 before its
    fsync, and directories are frozen 0500 through retained descriptors (root
    last). The root descriptor stays open on ``RunSnapshot.root_fd`` so
    compilation happens through a retained descriptor path. Files swapped in
    the published scaffold after verification can never reach the snapshot.
    """
    try:
        root_fd = open_generated_root(Path(run_root))
    except ScaffoldVerificationError as exc:
        raise ScaffoldSnapshotError(f"run root is unusable: {exc}") from exc
    try:
        for relative in sorted(
            verification.files, key=lambda p: (p.count("/"), p)
        ):
            parent, owned = _open_parent_dirs(root_fd, relative, 0o700)
            try:
                try:
                    fd = os.open(
                        relative.split("/")[-1],
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL
                        | os.O_NOFOLLOW | os.O_CLOEXEC,
                        0o600,
                        dir_fd=parent,
                    )
                except FileExistsError as exc:
                    raise ScaffoldSnapshotError(
                        f"snapshot entry already exists: {relative!r}"
                    ) from exc
                with os.fdopen(fd, "wb") as handle:
                    handle.write(verification.files[relative])
                    handle.flush()
                    os.fchmod(handle.fileno(), 0o400)
                    os.fsync(handle.fileno())
                os.fsync(parent)
            finally:
                for owned_fd in reversed(owned):
                    os.close(owned_fd)
        _freeze_directory_modes(root_fd)
    except BaseException:
        os.close(root_fd)
        raise
    root = Path(run_root)
    return RunSnapshot(
        root=root,
        run_orc=root / "run.orc",
        prompt_md=root / "prompt.md",
        prompts_json=root / "prompts.json",
        providers_json=root / "providers.json",
        output_contract_json=root / "output-contract.json",
        conf_root=root / "conf" if verification.conf_files else None,
        provider=verification.provider,
        root_fd=root_fd,
    )


def compile_snapshot(
    snapshot: RunSnapshot, provider: str
) -> tuple[object, SemanticContract]:
    """Compile the private snapshot's run.orc with snapshot-local externs.

    The snapshot is bound to the provider it was verified under; compiling
    against a different provider is refused. Compilation happens through the
    retained directory descriptor (never a mutable path under the runs
    root); a snapshot whose descriptor was closed is refused.
    """
    if provider not in PUBLIC_PROVIDER_NAMES:
        raise ValueError(f"unknown provider {provider!r}")
    if snapshot.provider != provider:
        raise ValueError(
            f"snapshot was verified for provider {snapshot.provider!r}; "
            f"cannot compile against {provider!r}"
        )
    if snapshot.root_fd < 0:
        raise ValueError("snapshot root descriptor is not open")
    root = _fd_root(snapshot.root_fd)
    try:
        compiled = compile_stage3_entrypoint(
            root / "run.orc",
            source_roots=(root,),
            provider_externs={"providers.task": provider},
            prompt_externs={"prompts.task": {"asset_file": "prompt.md"}},
            validate_shared=True,
            workspace_root=root,
        )
    except Exception as exc:
        raise ScaffoldCompileError(
            f"private snapshot failed Stage 3 compilation: {exc}"
        ) from exc
    return compiled, derive_compiled_contract(compiled)
