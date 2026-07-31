"""Atomic single-file replacement mechanics shared by runtime consumers."""

from __future__ import annotations

import os
from pathlib import Path
import secrets

_ORDINARY_FILE_MODE, _RESTRICTIVE_FILE_MODE = 0o666, 0o600


def _temporary_path(destination: Path) -> Path:
    return destination.with_name(
        f".orc-tmp-{os.getpid()}-{secrets.token_hex(8)}.tmp"
    )


def _write_all(descriptor: int, payload: bytes, *, no_progress_message: str) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError(no_progress_message)
        remaining = remaining[written:]


def _cleanup_nondurable(
    temporary: Path,
    descriptors: tuple[int | None, int | None],
    *,
    temporary_owned: bool,
    primary_failure: BaseException | None,
) -> None:
    failures: list[BaseException] = []
    for descriptor in descriptors:
        if descriptor is None:
            continue
        try:
            os.close(descriptor)
        except BaseException as error:
            failures.append(error)
    if temporary_owned:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except BaseException as error:
            failures.append(error)
    if primary_failure is None and failures:
        raise failures[0]


def _replace_bytes(
    path: Path, payload: bytes, *, mode: int, durable: bool, no_progress_message: str
) -> None:
    destination = Path(path)
    temporary = _temporary_path(destination)
    descriptor: int | None = None
    directory_descriptor: int | None = None
    temporary_owned = False
    primary_failure: BaseException | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            mode,
        )
        temporary_owned = True
        _write_all(descriptor, payload, no_progress_message=no_progress_message)
        if durable:
            os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, destination)
        temporary_owned = False
        if durable:
            directory_descriptor = os.open(
                destination.parent,
                os.O_RDONLY | os.O_DIRECTORY,
            )
            os.fsync(directory_descriptor)
    except BaseException as error:
        primary_failure = error
        raise
    finally:
        if not durable:
            _cleanup_nondurable(
                temporary,
                (descriptor, directory_descriptor),
                temporary_owned=temporary_owned,
                primary_failure=primary_failure,
            )
        else:
            if descriptor is not None:
                os.close(descriptor)
            if directory_descriptor is not None:
                os.close(directory_descriptor)
            if temporary_owned:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass


def durable_atomic_write(path: Path, payload: bytes) -> None:
    """Replace a file after syncing its bytes and resulting directory entry."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _replace_bytes(
        destination,
        payload,
        mode=_RESTRICTIVE_FILE_MODE,
        durable=True,
        no_progress_message="durable state write made no progress",
    )


def atomic_write_bytes(path: Path, payload: bytes, *, mode: int = _ORDINARY_FILE_MODE) -> None:
    """Replace a file with complete bytes without durability synchronization."""
    _replace_bytes(
        path,
        payload,
        mode=mode,
        durable=False,
        no_progress_message="atomic file write made no progress",
    )


def atomic_write_text(path: Path, text: str, *, mode: int = _ORDINARY_FILE_MODE) -> None:
    """UTF-8 encode text and replace a file without adding framing."""
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)
