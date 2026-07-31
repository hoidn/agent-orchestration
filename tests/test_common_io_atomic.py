from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import pytest

import orchestrator._common.io_atomic as io_atomic
from orchestrator._common.io_atomic import (
    atomic_write_bytes,
    atomic_write_text,
    durable_atomic_write,
)


def _temporary_paths(destination: Path) -> list[Path]:
    return list(destination.parent.glob(f".{destination.name}.*.tmp"))


def test_atomic_write_bytes_replaces_with_complete_payload(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "payload.bin"
    destination.parent.mkdir()

    atomic_write_bytes(destination, b"complete-payload")

    assert destination.read_bytes() == b"complete-payload"
    assert _temporary_paths(destination) == []


def test_atomic_write_bytes_does_not_create_a_missing_parent(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "missing" / "payload.bin"

    with pytest.raises(FileNotFoundError):
        atomic_write_bytes(destination, b"payload")

    assert not destination.parent.exists()
    assert not destination.exists()


def test_durable_atomic_write_creates_a_missing_parent(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "payload.bin"

    durable_atomic_write(destination, b"durable")

    assert destination.read_bytes() == b"durable"
    assert destination.stat().st_mode & 0o777 == 0o600
    assert _temporary_paths(destination) == []


def test_atomic_write_bytes_retries_forced_short_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "payload.bin"
    real_write = os.write
    write_sizes: list[int] = []

    def short_write(descriptor: int, payload: bytes | memoryview) -> int:
        chunk = bytes(payload[:2])
        write_sizes.append(len(chunk))
        return real_write(descriptor, chunk)

    monkeypatch.setattr(io_atomic.os, "write", short_write)

    atomic_write_bytes(destination, b"abcdefg")

    assert destination.read_bytes() == b"abcdefg"
    assert write_sizes == [2, 2, 2, 1]
    assert _temporary_paths(destination) == []


def test_atomic_write_bytes_zero_progress_preserves_destination_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"previous")
    monkeypatch.setattr(io_atomic.os, "write", lambda _fd, _payload: 0)

    with pytest.raises(OSError, match="atomic file write made no progress"):
        atomic_write_bytes(destination, b"replacement")

    assert destination.read_bytes() == b"previous"
    assert _temporary_paths(destination) == []


def test_atomic_write_bytes_propagates_write_failure_and_preserves_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"previous")
    failure = OSError("injected write failure")

    def fail_write(_descriptor: int, _payload: bytes | memoryview) -> int:
        raise failure

    monkeypatch.setattr(io_atomic.os, "write", fail_write)

    with pytest.raises(OSError) as caught:
        atomic_write_bytes(destination, b"replacement")

    assert caught.value is failure
    assert destination.read_bytes() == b"previous"
    assert _temporary_paths(destination) == []


@pytest.mark.parametrize("failed_operation", ["write", "replace"])
def test_primary_failure_is_not_masked_by_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_operation: str,
) -> None:
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"previous")
    primary_failure = OSError(f"injected {failed_operation} failure")
    close_failure = OSError("injected close cleanup failure")
    unlink_failure = OSError("injected unlink cleanup failure")
    real_close = os.close
    real_unlink = Path.unlink
    cleanup_events: list[str] = []

    if failed_operation == "write":
        monkeypatch.setattr(
            io_atomic.os,
            "write",
            lambda _descriptor, _payload: (_ for _ in ()).throw(primary_failure),
        )

        def close_then_fail(descriptor: int) -> None:
            cleanup_events.append("close")
            real_close(descriptor)
            raise close_failure

        monkeypatch.setattr(io_atomic.os, "close", close_then_fail)
    else:
        monkeypatch.setattr(
            io_atomic.os,
            "replace",
            lambda _source, _destination: (_ for _ in ()).throw(primary_failure),
        )

    def unlink_then_fail(path: Path, *args: object, **kwargs: object) -> None:
        cleanup_events.append("unlink")
        real_unlink(path, *args, **kwargs)
        raise unlink_failure

    monkeypatch.setattr(Path, "unlink", unlink_then_fail)

    with pytest.raises(OSError) as caught:
        atomic_write_bytes(destination, b"replacement")

    assert caught.value is primary_failure
    expected_cleanup = ["close", "unlink"] if failed_operation == "write" else ["unlink"]
    assert cleanup_events == expected_cleanup
    assert destination.read_bytes() == b"previous"
    assert _temporary_paths(destination) == []


def test_durable_write_keeps_historical_cleanup_failure_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"previous")
    write_failure = OSError("injected durable write failure")
    cleanup_failure = OSError("injected durable close failure")
    real_close = os.close

    monkeypatch.setattr(
        io_atomic.os,
        "write",
        lambda _descriptor, _payload: (_ for _ in ()).throw(write_failure),
    )

    def close_then_fail(descriptor: int) -> None:
        real_close(descriptor)
        raise cleanup_failure

    monkeypatch.setattr(io_atomic.os, "close", close_then_fail)

    with pytest.raises(OSError) as caught:
        durable_atomic_write(destination, b"replacement")

    assert caught.value is cleanup_failure
    assert destination.read_bytes() == b"previous"
    assert len(_temporary_paths(destination)) == 1


def test_cleanup_failure_without_a_primary_failure_is_propagated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "payload.bin"
    cleanup_failure = OSError("injected directory close failure")
    real_open = os.open
    real_close = os.close
    directory_descriptors: set[int] = set()

    def recording_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
    ) -> int:
        descriptor = real_open(path, flags, mode)
        if Path(path) == destination.parent:
            directory_descriptors.add(descriptor)
        return descriptor

    def selective_close(descriptor: int) -> None:
        real_close(descriptor)
        if descriptor in directory_descriptors:
            raise cleanup_failure

    monkeypatch.setattr(io_atomic.os, "open", recording_open)
    monkeypatch.setattr(io_atomic.os, "close", selective_close)

    with pytest.raises(OSError) as caught:
        durable_atomic_write(destination, b"replacement")

    assert caught.value is cleanup_failure
    assert destination.read_bytes() == b"replacement"
    assert _temporary_paths(destination) == []


def test_atomic_write_bytes_propagates_replace_failure_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"previous")
    failure = OSError("injected replace failure")

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise failure

    monkeypatch.setattr(io_atomic.os, "replace", fail_replace)

    with pytest.raises(OSError) as caught:
        atomic_write_bytes(destination, b"replacement")

    assert caught.value is failure
    assert destination.read_bytes() == b"previous"
    assert _temporary_paths(destination) == []


def test_atomic_write_bytes_uses_unique_temporary_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "payload.bin"
    real_replace = os.replace
    temporary_names: list[str] = []

    def recording_replace(source: Path, target: Path) -> None:
        temporary_names.append(Path(source).name)
        real_replace(source, target)

    monkeypatch.setattr(io_atomic.os, "replace", recording_replace)

    atomic_write_bytes(destination, b"first")
    atomic_write_bytes(destination, b"second")

    assert destination.read_bytes() == b"second"
    assert len(temporary_names) == 2
    assert len(set(temporary_names)) == 2
    assert all(name.startswith(f".{destination.name}.") for name in temporary_names)
    assert _temporary_paths(destination) == []


@pytest.mark.parametrize("writer", (atomic_write_bytes, durable_atomic_write))
def test_atomic_writers_do_not_remove_a_colliding_foreign_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    writer: Callable[[Path, bytes], None],
) -> None:
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"previous")
    foreign_temp = tmp_path / ".payload.bin.foreign.tmp"
    foreign_temp.write_bytes(b"foreign")
    monkeypatch.setattr(io_atomic, "_temporary_path", lambda _path: foreign_temp)

    with pytest.raises(FileExistsError):
        writer(destination, b"replacement")

    assert destination.read_bytes() == b"previous"
    assert foreign_temp.read_bytes() == b"foreign"


@pytest.mark.parametrize("writer", (atomic_write_bytes, durable_atomic_write))
def test_atomic_writers_do_not_remove_a_reused_temp_after_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    writer: Callable[[Path, bytes], None],
) -> None:
    destination = tmp_path / "payload.bin"
    temporary = tmp_path / ".payload.bin.bound.tmp"
    real_replace = os.replace

    monkeypatch.setattr(io_atomic, "_temporary_path", lambda _path: temporary)

    def replace_then_reuse(source: Path, target: Path) -> None:
        real_replace(source, target)
        Path(source).write_bytes(b"foreign")

    monkeypatch.setattr(io_atomic.os, "replace", replace_then_reuse)

    writer(destination, b"replacement")

    assert destination.read_bytes() == b"replacement"
    assert temporary.read_bytes() == b"foreign"


def test_atomic_write_text_encodes_utf8_and_forwards_mode(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "payload.txt"

    atomic_write_text(destination, "café ∆\n", mode=0o600)

    assert destination.read_bytes() == "café ∆\n".encode("utf-8")
    assert destination.stat().st_mode & 0o777 == 0o600
    assert _temporary_paths(destination) == []


def test_durable_atomic_write_preserves_file_replace_parent_fsync_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "nested" / "payload.bin"
    real_open = os.open
    real_write = os.write
    real_fsync = os.fsync
    real_close = os.close
    real_replace = os.replace
    descriptor_kind: dict[int, str] = {}
    events: list[str] = []

    def recording_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
    ) -> int:
        descriptor = real_open(path, flags, mode)
        kind = "directory" if Path(path) == destination.parent else "file"
        descriptor_kind[descriptor] = kind
        events.append(f"open:{kind}")
        return descriptor

    def recording_write(descriptor: int, payload: bytes | memoryview) -> int:
        events.append(f"write:{descriptor_kind[descriptor]}")
        return real_write(descriptor, payload)

    def recording_fsync(descriptor: int) -> None:
        events.append(f"fsync:{descriptor_kind[descriptor]}")
        real_fsync(descriptor)

    def recording_close(descriptor: int) -> None:
        events.append(f"close:{descriptor_kind[descriptor]}")
        real_close(descriptor)
        descriptor_kind.pop(descriptor)

    def recording_replace(source: Path, target: Path) -> None:
        events.append("replace")
        real_replace(source, target)

    monkeypatch.setattr(io_atomic.os, "open", recording_open)
    monkeypatch.setattr(io_atomic.os, "write", recording_write)
    monkeypatch.setattr(io_atomic.os, "fsync", recording_fsync)
    monkeypatch.setattr(io_atomic.os, "close", recording_close)
    monkeypatch.setattr(io_atomic.os, "replace", recording_replace)

    durable_atomic_write(destination, b"durable")

    assert destination.read_bytes() == b"durable"
    assert events == [
        "open:file",
        "write:file",
        "fsync:file",
        "close:file",
        "replace",
        "open:directory",
        "fsync:directory",
        "close:directory",
    ]
    assert _temporary_paths(destination) == []


def test_durable_atomic_write_keeps_historical_zero_progress_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"previous")
    monkeypatch.setattr(io_atomic.os, "write", lambda _fd, _payload: 0)

    with pytest.raises(OSError, match="durable state write made no progress"):
        durable_atomic_write(destination, b"replacement")

    assert destination.read_bytes() == b"previous"
    assert _temporary_paths(destination) == []


@pytest.mark.parametrize("failed_fsync_kind", ["file", "directory"])
def test_durable_atomic_write_propagates_fsync_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_fsync_kind: str,
) -> None:
    destination = tmp_path / "payload.bin"
    destination.write_bytes(b"previous")
    failure = OSError(f"injected {failed_fsync_kind} fsync failure")
    real_open = os.open
    real_fsync = os.fsync
    descriptor_kind: dict[int, str] = {}

    def recording_open(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
    ) -> int:
        descriptor = real_open(path, flags, mode)
        descriptor_kind[descriptor] = (
            "directory" if Path(path) == destination.parent else "file"
        )
        return descriptor

    def selective_fsync(descriptor: int) -> None:
        if descriptor_kind[descriptor] == failed_fsync_kind:
            raise failure
        real_fsync(descriptor)

    monkeypatch.setattr(io_atomic.os, "open", recording_open)
    monkeypatch.setattr(io_atomic.os, "fsync", selective_fsync)

    with pytest.raises(OSError) as caught:
        durable_atomic_write(destination, b"replacement")

    assert caught.value is failure
    expected = b"replacement" if failed_fsync_kind == "directory" else b"previous"
    assert destination.read_bytes() == expected
    assert _temporary_paths(destination) == []


def test_new_file_modes_preserve_restrictive_and_ordinary_umask_parity(
    tmp_path: Path,
) -> None:
    ordinary = tmp_path / "ordinary.bin"
    restrictive = tmp_path / "restrictive.bin"
    durable = tmp_path / "durable.bin"
    previous_umask = os.umask(0o027)
    try:
        atomic_write_bytes(ordinary, b"ordinary")
        atomic_write_bytes(restrictive, b"restrictive", mode=0o600)
        durable_atomic_write(durable, b"durable")
    finally:
        os.umask(previous_umask)

    assert ordinary.stat().st_mode & 0o777 == 0o640
    assert restrictive.stat().st_mode & 0o777 == 0o600
    assert durable.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    ("writer", "payload"),
    [
        (atomic_write_bytes, b""),
        (atomic_write_text, ""),
        (durable_atomic_write, b""),
    ],
)
def test_atomic_writers_replace_with_empty_payload(
    tmp_path: Path,
    writer: Callable[[Path, object], None],
    payload: object,
) -> None:
    destination = tmp_path / "payload"
    destination.write_bytes(b"previous")

    writer(destination, payload)

    assert destination.read_bytes() == b""
    assert _temporary_paths(destination) == []
