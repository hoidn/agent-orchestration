from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import stat
import time

import pytest


def _api():
    return importlib.import_module(
        "orchestrator.providers.isolation_bundle_broker"
    )


def _runtime_api():
    return importlib.import_module(
        "orchestrator.providers.isolation_runtime_authority"
    )


def _open_directory(path: Path) -> int:
    return os.open(
        path,
        os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )


def _capture(path: Path, *, basename: str = "result.json", max_bytes: int = 64):
    api = _api()
    directory_fd = _open_directory(path)
    try:
        return api.capture_active_bundle(
            scratch_directory_fd=directory_fd,
            active_basename=basename,
            expected_scratch_mount_id=_runtime_api()._statx_mount_id(directory_fd),
            max_bytes=max_bytes,
        )
    finally:
        os.close(directory_fd)


def _capture_in_child(path: str, connection) -> None:
    try:
        result = _capture(Path(path))
        connection.send(
            (
                result.classification,
                result.data,
                result.digest,
                result.size_bytes,
                result.reason,
            )
        )
    except BaseException as exc:  # pragma: no cover - parent reports the detail
        connection.send(("error", type(exc).__name__, str(exc)))
    finally:
        connection.close()


def _bounded_child_capture(path: Path) -> tuple[object, ...]:
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_capture_in_child,
        args=(str(path), child),
    )
    process.start()
    child.close()
    try:
        if not parent.poll(2.0):
            process.terminate()
            process.join(timeout=2.0)
            pytest.fail("bundle classification did not complete within two seconds")
        result = parent.recv()
        process.join(timeout=2.0)
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
        process.join(timeout=2.0)
    assert process.exitcode == 0
    return result


def test_absent_active_bundle_is_a_frozen_missing_outcome(
    tmp_path: Path,
) -> None:
    result = _capture(tmp_path)

    assert result.classification == "missing"
    assert result.data is None
    assert result.digest is None
    assert result.size_bytes is None
    assert result.reason is None
    with pytest.raises(AttributeError):
        result.classification = "captured"


@pytest.mark.parametrize("payload", (b"", b'{"ok":true}\n'))
def test_regular_active_bundle_is_captured_as_exact_bounded_bytes(
    tmp_path: Path,
    payload: bytes,
) -> None:
    (tmp_path / "result.json").write_bytes(payload)

    result = _capture(tmp_path)

    assert result.classification == "captured"
    assert result.data == payload
    assert result.digest == f"sha256:{sha256(payload).hexdigest()}"
    assert result.size_bytes == len(payload)
    assert result.reason is None


@pytest.mark.parametrize(
    ("size", "classification", "reason"),
    (
        (7, "captured", None),
        (8, "captured", None),
        (9, "rejected", "provider_isolation_bundle_oversized"),
    ),
)
def test_bundle_size_limit_is_exact(
    tmp_path: Path,
    size: int,
    classification: str,
    reason: str | None,
) -> None:
    (tmp_path / "result.json").write_bytes(b"x" * size)

    result = _capture(tmp_path, max_bytes=8)

    assert result.classification == classification
    assert result.reason == reason
    if classification == "captured":
        assert result.data == b"x" * size
        assert result.size_bytes == size
    else:
        assert result.data is None
        assert result.digest is None
        assert result.size_bytes is None


@pytest.mark.parametrize("entry_kind", ("directory", "fifo", "symlink"))
def test_non_regular_bundle_is_rejected_before_any_readable_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry_kind: str,
) -> None:
    api = _api()
    active = tmp_path / "result.json"
    if entry_kind == "directory":
        active.mkdir()
    elif entry_kind == "fifo":
        os.mkfifo(active)
    else:
        active.symlink_to(tmp_path / "outside")
    real_open = api.os.open
    observed: list[tuple[object, int, int | None]] = []

    def recording_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        observed.append((path, flags, dir_fd))
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(api.os, "open", recording_open)

    started = time.monotonic()
    result = _capture(tmp_path)

    assert time.monotonic() - started < 1.0
    assert result.classification == "rejected"
    assert result.reason == "provider_isolation_bundle_rejected"
    assert observed
    assert observed[0][1] & os.O_PATH
    assert not any(
        isinstance(path, str) and path.startswith("/proc/self/fd/")
        for path, _flags, _dir_fd in observed
    )


def test_fifo_classification_has_a_process_bounded_completion(
    tmp_path: Path,
) -> None:
    os.mkfifo(tmp_path / "result.json")

    result = _bounded_child_capture(tmp_path)

    assert result[0] == "rejected"
    assert result[4] == "provider_isolation_bundle_rejected"


def test_device_is_rejected_without_readable_open_when_constructible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    active = tmp_path / "result.json"
    try:
        os.mknod(active, stat.S_IFCHR | 0o600, os.makedev(1, 3))
    except (AttributeError, OSError) as exc:
        pytest.skip(f"device node construction is unavailable: {exc}")
    real_open = api.os.open
    readable_proc_opened = False

    def recording_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal readable_proc_opened
        if isinstance(path, str) and path.startswith("/proc/self/fd/"):
            readable_proc_opened = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(api.os, "open", recording_open)

    result = _capture(tmp_path)

    assert result.classification == "rejected"
    assert not readable_proc_opened


def test_regular_bundle_is_read_only_through_its_trusted_proc_pin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    (tmp_path / "result.json").write_bytes(b"payload")
    real_open = api.os.open
    observed: list[tuple[object, int, int | None, int]] = []

    def recording_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        opened_fd = real_open(path, flags, mode, dir_fd=dir_fd)
        observed.append((path, flags, dir_fd, opened_fd))
        return opened_fd

    monkeypatch.setattr(api.os, "open", recording_open)

    result = _capture(tmp_path)

    assert result.classification == "captured"
    assert len(observed) == 3  # test directory, O_PATH pin, trusted proc read
    pin_path, pin_flags, pin_dir_fd, pin_fd = observed[1]
    assert pin_path == "result.json"
    assert pin_dir_fd is not None
    assert pin_flags == os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC
    read_path, read_flags, read_dir_fd, _read_fd = observed[2]
    assert read_path == f"/proc/self/fd/{pin_fd}"
    assert read_dir_fd is None
    assert read_flags == os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC


@pytest.mark.parametrize("replacement_kind", ("regular", "fifo", "symlink"))
def test_linked_name_exchange_is_rejected_while_the_old_inode_is_pinned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement_kind: str,
) -> None:
    api = _api()
    active = tmp_path / "result.json"
    active.write_bytes(b"original")
    real_open = api.os.open
    exchanged = False

    def exchanging_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal exchanged
        if (
            isinstance(path, str)
            and path.startswith("/proc/self/fd/")
            and not exchanged
        ):
            exchanged = True
            active.rename(tmp_path / "displaced")
            if replacement_kind == "regular":
                active.write_bytes(b"replacement")
            elif replacement_kind == "fifo":
                os.mkfifo(active)
            else:
                active.symlink_to(tmp_path / "outside")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(api.os, "open", exchanging_open)

    result = _capture(tmp_path)

    assert exchanged
    assert result.classification == "rejected"
    assert result.reason == "provider_isolation_bundle_rejected"
    assert result.data is None


@pytest.mark.parametrize("mutation", ("append", "truncate", "hardlink"))
def test_bundle_mutation_during_the_bounded_read_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    api = _api()
    active = tmp_path / "result.json"
    active.write_bytes(b"original")
    real_read = api.os.read
    mutated = False

    def mutating_read(fd: int, length: int) -> bytes:
        nonlocal mutated
        if not mutated:
            mutated = True
            if mutation == "append":
                with active.open("ab") as handle:
                    handle.write(b"-appended")
            elif mutation == "truncate":
                active.write_bytes(b"")
            else:
                os.link(active, tmp_path / "alias")
        return real_read(fd, length)

    monkeypatch.setattr(api.os, "read", mutating_read)

    result = _capture(tmp_path)

    assert mutated
    assert result.classification == "rejected"
    assert result.reason == "provider_isolation_bundle_rejected"


def test_scratch_or_bundle_mount_identity_drift_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    (tmp_path / "result.json").write_bytes(b"payload")
    real_mount_id = api._statx_mount_id
    calls = 0

    def drifted_mount_id(directory_fd: int, name: str | None = None) -> int:
        nonlocal calls
        value = real_mount_id(directory_fd, name)
        calls += 1
        return value if calls == 1 else value + 1

    monkeypatch.setattr(api, "_statx_mount_id", drifted_mount_id)

    result = _capture(tmp_path)

    assert calls >= 2
    assert result.classification == "rejected"


def test_mount_identity_drift_after_the_bounded_read_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    (tmp_path / "result.json").write_bytes(b"payload")
    real_mount_id = api._statx_mount_id
    calls = 0

    def drifted_mount_id(directory_fd: int, name: str | None = None) -> int:
        nonlocal calls
        value = real_mount_id(directory_fd, name)
        calls += 1
        return value if calls <= 4 else value + 1

    monkeypatch.setattr(api, "_statx_mount_id", drifted_mount_id)

    result = _capture(tmp_path)

    assert calls >= 5
    assert result.classification == "rejected"


def test_held_scratch_descriptor_survives_parent_path_replacement(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "result.json").write_bytes(b"held")
    directory_fd = _open_directory(scratch)
    try:
        expected_mount_id = _runtime_api()._statx_mount_id(directory_fd)
        scratch.rename(tmp_path / "displaced-scratch")
        scratch.mkdir()
        (scratch / "result.json").write_bytes(b"ambient replacement")

        result = _api().capture_active_bundle(
            scratch_directory_fd=directory_fd,
            active_basename="result.json",
            expected_scratch_mount_id=expected_mount_id,
            max_bytes=64,
        )
    finally:
        os.close(directory_fd)

    assert result.classification == "captured"
    assert result.data == b"held"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("scratch_directory_fd", True),
        ("active_basename", ""),
        ("active_basename", "../result.json"),
        ("active_basename", "e\u0301.json"),
        ("expected_scratch_mount_id", True),
        ("expected_scratch_mount_id", 0),
        ("max_bytes", True),
        ("max_bytes", 0),
    ),
)
def test_capture_rejects_invalid_controller_arguments(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    api = _api()
    directory_fd = _open_directory(tmp_path)
    arguments: dict[str, object] = {
        "scratch_directory_fd": directory_fd,
        "active_basename": "result.json",
        "expected_scratch_mount_id": _runtime_api()._statx_mount_id(directory_fd),
        "max_bytes": 64,
    }
    arguments[field] = value
    try:
        with pytest.raises(TypeError):
            api.capture_active_bundle(**arguments)
    finally:
        os.close(directory_fd)


def test_initial_oversize_is_rejected_before_trusted_proc_read_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    (tmp_path / "result.json").write_bytes(b"x" * 9)
    real_open = api.os.open
    observed: list[object] = []

    def recording_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        observed.append(path)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(api.os, "open", recording_open)

    result = _capture(tmp_path, max_bytes=8)

    assert result.classification == "rejected"
    assert result.reason == "provider_isolation_bundle_oversized"
    assert not any(
        isinstance(path, str) and path.startswith("/proc/self/fd/")
        for path in observed
    )


def test_unavailable_trusted_proc_read_fails_as_broker_infrastructure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    (tmp_path / "result.json").write_bytes(b"payload")
    real_open = api.os.open
    basename_read_attempts = 0

    def unavailable_proc_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal basename_read_attempts
        if isinstance(path, str) and path.startswith("/proc/self/fd/"):
            raise FileNotFoundError(path)
        if path == "result.json" and not flags & os.O_PATH:
            basename_read_attempts += 1
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(api.os, "open", unavailable_proc_open)

    with pytest.raises(api.ProviderIsolationBundleBrokerError) as exc_info:
        _capture(tmp_path)

    assert exc_info.value.code == "provider_isolation_bundle_broker_failed"
    assert basename_read_attempts == 0


def test_unavailable_initial_opath_pin_fails_as_broker_infrastructure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    (tmp_path / "result.json").write_bytes(b"payload")
    real_open = api.os.open

    def unavailable_pin(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if path == "result.json" and flags & os.O_PATH:
            raise OSError(24, "too many open files")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(api.os, "open", unavailable_pin)

    with pytest.raises(api.ProviderIsolationBundleBrokerError) as exc_info:
        _capture(tmp_path)

    assert exc_info.value.code == "provider_isolation_bundle_broker_failed"


def test_unavailable_mount_identity_fails_as_broker_infrastructure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    (tmp_path / "result.json").write_bytes(b"payload")
    directory_fd = _open_directory(tmp_path)
    expected_mount_id = _runtime_api()._statx_mount_id(directory_fd)
    monkeypatch.setattr(
        api,
        "_statx_mount_id",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            _runtime_api().MountIdentityUnavailable("statx unavailable")
        ),
    )
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError) as exc_info:
            api.capture_active_bundle(
                scratch_directory_fd=directory_fd,
                active_basename="result.json",
                expected_scratch_mount_id=expected_mount_id,
                max_bytes=64,
            )
    finally:
        os.close(directory_fd)

    assert exc_info.value.code == "provider_isolation_bundle_broker_failed"


def test_unavailable_linked_name_stat_fails_as_broker_infrastructure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    (tmp_path / "result.json").write_bytes(b"payload")
    real_stat = api.os.stat

    def unavailable_stat(path: object, *args, **kwargs):
        if path == "result.json":
            raise PermissionError(13, "permission denied")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(api.os, "stat", unavailable_stat)

    with pytest.raises(api.ProviderIsolationBundleBrokerError) as exc_info:
        _capture(tmp_path)

    assert exc_info.value.code == "provider_isolation_bundle_broker_failed"


def _captured(payload: bytes = b'{"ok":true}\n'):
    api = _api()
    return api.ProviderIsolationBundleCapture(
        classification="captured",
        data=payload,
        digest=f"sha256:{sha256(payload).hexdigest()}",
        size_bytes=len(payload),
        reason=None,
    )


def _bind_capture_for_test(capture, *, authority_binding: str):
    api = _api()
    source_binding = (
        "sha256:"
        + sha256(
            f"unit-capture-source:{authority_binding}".encode("ascii")
        ).hexdigest()
    )
    binding = api._derive_bound_capture_binding(
        capture,
        source_authority_binding=source_binding,
    )
    return api.ProviderIsolationBundleCapture(
        classification=capture.classification,
        data=capture.data,
        digest=capture.digest,
        size_bytes=capture.size_bytes,
        reason=capture.reason,
        _source_authority_binding=source_binding,
        _binding=binding,
        _token=api._BOUND_CAPTURE_TOKEN,
    )


def _replace_request_capture_for_test(request, capture):
    api = _api()
    source_binding = request.capture._source_authority_binding
    assert source_binding is not None
    binding = api._derive_bound_capture_binding(
        capture,
        source_authority_binding=source_binding,
    )
    bound_capture = api.ProviderIsolationBundleCapture(
        classification=capture.classification,
        data=capture.data,
        digest=capture.digest,
        size_bytes=capture.size_bytes,
        reason=capture.reason,
        _source_authority_binding=source_binding,
        _binding=binding,
        _token=api._BOUND_CAPTURE_TOKEN,
    )
    request_capture_binding = api._derive_request_capture_binding(
        request_authority_binding=request._authority_binding,
        capture_source_authority_binding=source_binding,
        capture_binding=binding,
    )
    return replace(
        request,
        capture=bound_capture,
        _capture_binding=binding,
        _request_capture_binding=request_capture_binding,
    )


def _transfer_request(
    runtime_root: Path,
    *,
    payload: bytes = b'{"ok":true}\n',
    scope: tuple[str, ...] = ("root", "provider-step"),
    ordinal: int = 1,
    target: str = "results/provider-step.json",
):
    api = _api()
    runtime_root.mkdir(mode=0o700)
    (runtime_root / "results").mkdir()
    runtime_root_fd = _open_directory(runtime_root)
    expected_mount_id = _runtime_api()._statx_mount_id(runtime_root_fd)
    authority_binding = api._derive_transfer_request_authority_binding(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_mount_id,
        invocation_identity="sha256:" + ("a" * 64),
        scope=scope,
        ordinal=ordinal,
        target_relative_path=target,
    )
    capture = _bind_capture_for_test(
        _captured(payload),
        authority_binding=authority_binding,
    )
    request_capture_binding = api._derive_request_capture_binding(
        request_authority_binding=authority_binding,
        capture_source_authority_binding=(
            capture._source_authority_binding
        ),
        capture_binding=capture._binding,
    )
    request = api.ProviderIsolationBundleTransferRequest(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_mount_id,
        invocation_identity="sha256:" + ("a" * 64),
        scope=scope,
        ordinal=ordinal,
        target_relative_path=target,
        capture=capture,
        _authority_binding=authority_binding,
        _capture_binding=capture._binding,
        _request_capture_binding=request_capture_binding,
        _token=api._TRANSFER_REQUEST_TOKEN,
    )
    return request, runtime_root_fd


def _fresh_recovery_identity(request, runtime_root: Path):
    api = _api()
    runtime_root_fd = _open_directory(runtime_root)
    identity = api.ProviderIsolationBundleTransferIdentity(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=_runtime_api()._statx_mount_id(
            runtime_root_fd
        ),
        invocation_identity=request.invocation_identity,
        scope=request.scope,
        ordinal=request.ordinal,
        target_relative_path=request.target_relative_path,
    )
    return identity, runtime_root_fd


@pytest.mark.parametrize("payload", (b"", b'{"value":true}\n'))
def test_prepare_publish_uses_canonical_journal_and_exact_file_identity(
    tmp_path: Path,
    payload: bytes,
) -> None:
    api = _api()
    isolation = importlib.import_module("orchestrator.providers.isolation")
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(
        runtime_root,
        payload=payload,
    )
    try:
        record = api.prepare_and_publish_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert record is not None
    assert record.state == "published"
    assert (runtime_root / record.target_relative_path).read_bytes() == (
        request.capture.data
    )
    assert not (runtime_root / record.staged_relative_path).exists()
    journal_bytes = (runtime_root / record.journal_relative_path).read_bytes()
    document = json.loads(journal_bytes)
    assert journal_bytes == isolation.canonical_isolation_json_bytes(document)
    assert document == record.to_dict()
    assert document["staged_identity"]["device"] == document["target_identity"][
        "device"
    ]
    assert document["staged_identity"]["inode"] == document["target_identity"][
        "inode"
    ]
    assert document["staged_identity"]["mount_id"] == document[
        "target_identity"
    ]["mount_id"]
    assert document["staged_identity"]["path"] == record.staged_relative_path
    assert document["target_identity"]["path"] == record.target_relative_path
    assert stat.S_IMODE(
        (runtime_root / record.journal_relative_path).stat().st_mode
    ) == 0o600


def test_publication_revalidates_target_identity_after_canonical_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    real_rename = api._rename_noreplace
    replaced = False

    def replace_target_after_rename(
        source_parent_fd: int,
        source_name: str,
        target_parent_fd: int,
        target_name: str,
    ) -> None:
        nonlocal replaced
        real_rename(
            source_parent_fd,
            source_name,
            target_parent_fd,
            target_name,
        )
        if source_name == api._STAGED_NAME:
            replacement = runtime_root / "results" / "replacement.tmp"
            replacement.write_bytes(request.capture.data)
            os.replace(
                replacement,
                runtime_root / request.target_relative_path,
            )
            replaced = True

    monkeypatch.setattr(api, "_rename_noreplace", replace_target_after_rename)
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert replaced is True
    paths = api.derive_bundle_transfer_paths(request)
    journal = json.loads(
        (runtime_root / paths.journal_relative_path).read_bytes()
    )
    assert journal["state"] == "prepared"
    assert (
        runtime_root / request.target_relative_path
    ).read_bytes() == request.capture.data
    assert (
        runtime_root / request.target_relative_path
    ).stat().st_ino != journal["target_identity"]["inode"]


def test_publication_reconciles_target_after_published_journal_advance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    real_advance = api._advance_journal
    replaced = False

    def replace_target_after_published_advance(*args, **kwargs):
        nonlocal replaced
        result = real_advance(*args, **kwargs)
        document = kwargs["document"]
        if document["state"] == "published":
            replacement = runtime_root / "results" / "replacement.tmp"
            replacement.write_bytes(request.capture.data)
            os.replace(
                replacement,
                runtime_root / request.target_relative_path,
            )
            replaced = True
        return result

    monkeypatch.setattr(
        api,
        "_advance_journal",
        replace_target_after_published_advance,
    )
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert replaced is True
    paths = api.derive_bundle_transfer_paths(request)
    journal = json.loads(
        (runtime_root / paths.journal_relative_path).read_bytes()
    )
    assert journal["state"] == "published"
    assert (
        runtime_root / request.target_relative_path
    ).stat().st_ino != journal["target_identity"]["inode"]


def test_publication_revalidates_factory_bound_runtime_authority(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    replacement_root = tmp_path / "replacement-runtime"
    replacement_root.mkdir(mode=0o700)
    (replacement_root / "results").mkdir()
    held_fd_number = runtime_root_fd
    os.close(runtime_root_fd)
    replacement_fd = _open_directory(replacement_root)
    if replacement_fd != held_fd_number:
        os.dup2(replacement_fd, held_fd_number)
        os.close(replacement_fd)
    try:
        with pytest.raises(TypeError, match="authority binding"):
            api.prepare_and_publish_bundle_transfer(request)
    finally:
        os.close(held_fd_number)

    assert not (
        replacement_root / request.target_relative_path
    ).exists()
    assert not (replacement_root / api._BROKER_ROOT).exists()


@pytest.mark.parametrize(
    "interruption_boundary",
    ("partial_stage_write", "staged_file_fsync"),
)
def test_prejournal_staged_file_interruption_is_preserved_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interruption_boundary: str,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    paths = api.derive_bundle_transfer_paths(request)
    real_write = api.os.write
    real_fsync = api.os.fsync
    stage_write_calls = 0

    def interrupted_write(fd: int, data: bytes) -> int:
        nonlocal stage_write_calls
        if interruption_boundary != "partial_stage_write":
            return real_write(fd, data)
        stage_write_calls += 1
        if stage_write_calls == 1:
            return real_write(fd, data[: max(1, len(data) // 2)])
        raise OSError("injected partial staged-file write interruption")

    def interrupted_fsync(fd: int) -> None:
        if (
            interruption_boundary == "staged_file_fsync"
            and stat.S_ISREG(os.fstat(fd).st_mode)
        ):
            raise OSError("injected staged-file fsync interruption")
        real_fsync(fd)

    monkeypatch.setattr(api.os, "write", interrupted_write)
    monkeypatch.setattr(api.os, "fsync", interrupted_fsync)
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
        stage = runtime_root / paths.staged_relative_path
        assert stage.is_file()
        if interruption_boundary == "partial_stage_write":
            assert 0 < stage.stat().st_size < len(request.capture.data)
        else:
            assert stage.read_bytes() == request.capture.data
        assert not (runtime_root / paths.journal_relative_path).exists()
        assert not (runtime_root / paths.target_relative_path).exists()
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.reconcile_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert (runtime_root / paths.staged_relative_path).is_file()


@pytest.mark.parametrize("classification", ("missing", "rejected"))
def test_noncaptured_outcome_creates_no_transfer_authority(
    tmp_path: Path,
    classification: str,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    reason = None if classification == "missing" else api.BUNDLE_REJECTED_REASON
    request = _replace_request_capture_for_test(
        request,
        api.ProviderIsolationBundleCapture(
            classification=classification,
            data=None,
            digest=None,
            size_bytes=None,
            reason=reason,
        ),
    )
    paths = api.derive_bundle_transfer_paths(request)
    try:
        assert api.prepare_and_publish_bundle_transfer(request) is None
    finally:
        os.close(runtime_root_fd)

    assert not (runtime_root / paths.journal_relative_path).exists()
    assert not (runtime_root / paths.staged_relative_path).exists()
    assert not (runtime_root / paths.target_relative_path).exists()
    assert not (runtime_root / paths.archive_relative_path).exists()


@pytest.mark.parametrize(
    "execution_outcome",
    ("nonzero", "timeout", "cancelled"),
)
def test_fake_attempt_owner_records_noneligible_capture_without_publication(
    tmp_path: Path,
    execution_outcome: str,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    payload = b'{"untrusted":"partial"}\n'
    (scratch / "result.json").write_bytes(payload)
    capture = _capture(scratch)
    request, runtime_root_fd = _transfer_request(runtime_root)
    noneligible = _replace_request_capture_for_test(
        request,
        capture,
    )
    paths = api.derive_bundle_transfer_paths(noneligible)

    try:
        fake_owner_record = {
            "execution_outcome": execution_outcome,
            "typed_validation_eligible": False,
            "capture_classification": capture.classification,
            "bundle_digest": capture.digest,
            "bundle_size": capture.size_bytes,
        }
        # Task 4 replaces this fake owner. A noneligible owner deliberately
        # does not grant the publication API its captured-byte request.
    finally:
        os.close(runtime_root_fd)

    assert fake_owner_record == {
        "execution_outcome": execution_outcome,
        "typed_validation_eligible": False,
        "capture_classification": "captured",
        "bundle_digest": f"sha256:{sha256(payload).hexdigest()}",
        "bundle_size": len(payload),
    }
    assert not (runtime_root / paths.journal_relative_path).exists()
    assert not (runtime_root / paths.staged_relative_path).exists()
    assert not (runtime_root / paths.target_relative_path).exists()
    assert not (runtime_root / paths.archive_relative_path).exists()


def test_validation_is_monotonic_idempotent_and_retains_valid_target(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    contract_digest = "sha256:" + ("b" * 64)
    normalized_digest = "sha256:" + ("c" * 64)
    try:
        published = api.prepare_and_publish_bundle_transfer(request)
        validated = api.record_bundle_transfer_validation(
            request,
            contract_digest=contract_digest,
            disposition="valid",
            normalized_value_digest=normalized_digest,
        )
        replayed = api.record_bundle_transfer_validation(
            request,
            contract_digest=contract_digest,
            disposition="valid",
            normalized_value_digest=normalized_digest,
        )
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.record_bundle_transfer_validation(
                request,
                contract_digest=contract_digest,
                disposition="invalid",
                normalized_value_digest=None,
            )
        recovery, recovery_fd = _fresh_recovery_identity(
            request,
            runtime_root,
        )
        try:
            reconciled = api.reconcile_bundle_transfer(recovery)
        finally:
            os.close(recovery_fd)
    finally:
        os.close(runtime_root_fd)

    assert published is not None
    assert validated.state == "validated"
    assert validated.to_dict()["validation_disposition"] == "valid"
    assert replayed.canonical_json == validated.canonical_json
    assert reconciled is not None
    assert reconciled.canonical_json == validated.canonical_json
    assert (runtime_root / validated.target_relative_path).read_bytes() == (
        request.capture.data
    )
    assert not (runtime_root / validated.archive_relative_path).exists()


def test_invalid_validation_rotates_only_after_positive_caller_ack(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    contract_digest = "sha256:" + ("b" * 64)
    acknowledgements: list[str] = []
    try:
        api.prepare_and_publish_bundle_transfer(request)
        validated = api.record_bundle_transfer_validation(
            request,
            contract_digest=contract_digest,
            disposition="invalid",
            normalized_value_digest=None,
        )
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.rotate_invalid_bundle_transfer(
                request,
                acknowledgement=lambda _record: False,
            )
        assert (runtime_root / validated.target_relative_path).exists()
        rotated = api.rotate_invalid_bundle_transfer(
            request,
            acknowledgement=lambda record: (
                acknowledgements.append(record.state) or True
            ),
        )
        replayed = api.rotate_invalid_bundle_transfer(
            request,
            acknowledgement=lambda record: (
                acknowledgements.append(record.state) or True
            ),
        )
    finally:
        os.close(runtime_root_fd)

    assert acknowledgements == ["validated"]
    assert rotated.state == "rotated"
    assert replayed.canonical_json == rotated.canonical_json
    assert not (runtime_root / rotated.target_relative_path).exists()
    assert (runtime_root / rotated.archive_relative_path).read_bytes() == (
        request.capture.data
    )


def test_prepared_stage_only_reconciles_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    paths = api.derive_bundle_transfer_paths(request)
    real_rename = api._rename_noreplace
    interrupted = False

    def interrupt_first_publish(*args, **kwargs) -> None:
        nonlocal interrupted
        if not interrupted and args[1] == api._STAGED_NAME:
            interrupted = True
            raise api.ProviderIsolationBundleBrokerError("injected interruption")
        real_rename(*args, **kwargs)

    monkeypatch.setattr(api, "_rename_noreplace", interrupt_first_publish)
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
        assert (runtime_root / paths.staged_relative_path).exists()
        assert not (runtime_root / paths.target_relative_path).exists()
        recovery, recovery_fd = _fresh_recovery_identity(
            request,
            runtime_root,
        )
        try:
            recovered = api.reconcile_bundle_transfer(recovery)
        finally:
            os.close(recovery_fd)
    finally:
        os.close(runtime_root_fd)

    assert recovered is not None
    assert recovered.state == "published"
    assert not (runtime_root / recovered.staged_relative_path).exists()
    assert (runtime_root / recovered.target_relative_path).exists()


def test_prepared_target_only_reconciles_by_advancing_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    paths = api.derive_bundle_transfer_paths(request)
    real_advance = api._advance_journal
    interrupted = False

    def interrupt_published(*args, **kwargs):
        nonlocal interrupted
        document = kwargs.get("document")
        if (
            not interrupted
            and isinstance(document, dict)
            and document.get("state") == "published"
        ):
            interrupted = True
            raise api.ProviderIsolationBundleBrokerError("injected interruption")
        return real_advance(*args, **kwargs)

    monkeypatch.setattr(api, "_advance_journal", interrupt_published)
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
        assert not (runtime_root / paths.staged_relative_path).exists()
        assert (runtime_root / paths.target_relative_path).exists()
        recovery, recovery_fd = _fresh_recovery_identity(
            request,
            runtime_root,
        )
        try:
            recovered = api.reconcile_bundle_transfer(recovery)
        finally:
            os.close(recovery_fd)
    finally:
        os.close(runtime_root_fd)

    assert recovered is not None
    assert recovered.state == "published"


@pytest.mark.parametrize("locations", ("both", "neither"))
def test_ambiguous_prepared_locations_fail_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    locations: str,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    paths = api.derive_bundle_transfer_paths(request)
    real_rename = api._rename_noreplace
    interrupted = False

    def interrupt_first_publish(*args, **kwargs) -> None:
        nonlocal interrupted
        if not interrupted and args[1] == api._STAGED_NAME:
            interrupted = True
            raise api.ProviderIsolationBundleBrokerError("injected interruption")
        real_rename(*args, **kwargs)

    monkeypatch.setattr(api, "_rename_noreplace", interrupt_first_publish)
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
        staged = runtime_root / paths.staged_relative_path
        target = runtime_root / paths.target_relative_path
        if locations == "both":
            os.link(staged, target)
        else:
            staged.unlink()
        before = {
            path: path.read_bytes()
            for path in (staged, target)
            if path.exists()
        }
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.reconcile_bundle_transfer(request)
        after = {
            path: path.read_bytes()
            for path in (staged, target)
            if path.exists()
        }
    finally:
        os.close(runtime_root_fd)

    assert after == before


@pytest.mark.parametrize("tamper", ("noncanonical", "digest", "target_path"))
def test_changed_journal_fails_closed_without_touching_bundle(
    tmp_path: Path,
    tamper: str,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    try:
        record = api.prepare_and_publish_bundle_transfer(request)
        assert record is not None
        journal = runtime_root / record.journal_relative_path
        document = json.loads(journal.read_bytes())
        if tamper == "noncanonical":
            replacement = json.dumps(document, indent=2).encode() + b"\n"
        elif tamper == "digest":
            document["bundle_digest"] = "sha256:" + ("f" * 64)
            replacement = importlib.import_module(
                "orchestrator.providers.isolation"
            ).canonical_isolation_json_bytes(document)
        else:
            document["target_identity"]["path"] = "results/other.json"
            replacement = importlib.import_module(
                "orchestrator.providers.isolation"
            ).canonical_isolation_json_bytes(document)
        journal.write_bytes(replacement)
        target = runtime_root / record.target_relative_path
        before = target.read_bytes()
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.reconcile_bundle_transfer(request)
        after = target.read_bytes()
    finally:
        os.close(runtime_root_fd)

    assert after == before


@pytest.mark.parametrize("kind", ("target", "stage", "archive"))
def test_unexplained_preexisting_location_is_never_removed_or_overwritten(
    tmp_path: Path,
    kind: str,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    paths = api.derive_bundle_transfer_paths(request)
    attribute = (
        "staged_relative_path" if kind == "stage" else f"{kind}_relative_path"
    )
    path = runtime_root / getattr(paths, attribute)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"ambient")
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert path.read_bytes() == b"ambient"


def test_hardlink_alias_of_published_target_fails_reconciliation(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    try:
        record = api.prepare_and_publish_bundle_transfer(request)
        assert record is not None
        target = runtime_root / record.target_relative_path
        alias = target.with_name("alias.json")
        os.link(target, alias)
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.reconcile_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert target.exists()
    assert alias.exists()


def test_symlinked_target_ancestry_fails_before_transfer(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (runtime_root / "results").symlink_to(outside, target_is_directory=True)
    runtime_root_fd = _open_directory(runtime_root)
    expected_mount_id = _runtime_api()._statx_mount_id(runtime_root_fd)
    authority_binding = api._derive_transfer_request_authority_binding(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_mount_id,
        invocation_identity="sha256:" + ("a" * 64),
        scope=("root",),
        ordinal=1,
        target_relative_path="results/provider-step.json",
    )
    capture = _bind_capture_for_test(
        _captured(),
        authority_binding=authority_binding,
    )
    request_capture_binding = api._derive_request_capture_binding(
        request_authority_binding=authority_binding,
        capture_source_authority_binding=(
            capture._source_authority_binding
        ),
        capture_binding=capture._binding,
    )
    request = api.ProviderIsolationBundleTransferRequest(
        runtime_root_fd=runtime_root_fd,
        expected_runtime_mount_id=expected_mount_id,
        invocation_identity="sha256:" + ("a" * 64),
        scope=("root",),
        ordinal=1,
        target_relative_path="results/provider-step.json",
        capture=capture,
        _authority_binding=authority_binding,
        _capture_binding=capture._binding,
        _request_capture_binding=request_capture_binding,
        _token=api._TRANSFER_REQUEST_TOKEN,
    )
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert not (outside / "provider-step.json").exists()
    assert not (runtime_root / api._BROKER_ROOT).exists()


def test_deterministic_paths_bind_canonical_unicode_scope(
    tmp_path: Path,
) -> None:
    api = _api()
    request, runtime_root_fd = _transfer_request(
        tmp_path / "runtime",
        scope=("røøt", "é"),
        ordinal=7,
    )
    try:
        first = api.derive_bundle_transfer_paths(request)
        second = api.derive_bundle_transfer_paths(request)
        assert first == second
        with pytest.raises(TypeError):
            replace(
                request,
                scope=("root", "e\u0301"),
            )
    finally:
        os.close(runtime_root_fd)

    assert first.journal_relative_path.isascii()
    assert first.staged_relative_path.isascii()
    assert first.archive_relative_path.isascii()


def test_direct_capture_rejects_size_bound_above_closed_policy_maximum(
    tmp_path: Path,
) -> None:
    api = _api()
    directory_fd = _open_directory(tmp_path)
    try:
        with pytest.raises(TypeError):
            api.capture_active_bundle(
                scratch_directory_fd=directory_fd,
                active_basename="result.json",
                expected_scratch_mount_id=_runtime_api()._statx_mount_id(
                    directory_fd
                ),
                max_bytes=16_777_217,
            )
    finally:
        os.close(directory_fd)


def test_rotation_pending_target_only_reconciles_to_rotated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    real_rename = api._rename_noreplace
    interrupted = False

    def interrupt_archive_rename(*args, **kwargs) -> None:
        nonlocal interrupted
        if not interrupted and args[3] == api._ARCHIVE_NAME:
            interrupted = True
            raise api.ProviderIsolationBundleBrokerError("injected interruption")
        real_rename(*args, **kwargs)

    monkeypatch.setattr(api, "_rename_noreplace", interrupt_archive_rename)
    try:
        api.prepare_and_publish_bundle_transfer(request)
        api.record_bundle_transfer_validation(
            request,
            contract_digest="sha256:" + ("b" * 64),
            disposition="invalid",
            normalized_value_digest=None,
        )
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.rotate_invalid_bundle_transfer(
                request,
                acknowledgement=lambda _record: True,
            )
        recovery, recovery_fd = _fresh_recovery_identity(
            request,
            runtime_root,
        )
        try:
            pending = api.reconcile_bundle_transfer(recovery)
        finally:
            os.close(recovery_fd)
    finally:
        os.close(runtime_root_fd)

    assert pending is not None
    assert pending.state == "rotated"
    assert not (runtime_root / pending.target_relative_path).exists()
    assert (runtime_root / pending.archive_relative_path).exists()


def test_rotation_pending_archive_only_reconciles_to_rotated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    real_advance = api._advance_journal
    interrupted = False

    def interrupt_rotated(*args, **kwargs):
        nonlocal interrupted
        document = kwargs.get("document")
        if (
            not interrupted
            and isinstance(document, dict)
            and document.get("state") == "rotated"
        ):
            interrupted = True
            raise api.ProviderIsolationBundleBrokerError("injected interruption")
        return real_advance(*args, **kwargs)

    monkeypatch.setattr(api, "_advance_journal", interrupt_rotated)
    try:
        api.prepare_and_publish_bundle_transfer(request)
        api.record_bundle_transfer_validation(
            request,
            contract_digest="sha256:" + ("b" * 64),
            disposition="invalid",
            normalized_value_digest=None,
        )
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.rotate_invalid_bundle_transfer(
                request,
                acknowledgement=lambda _record: True,
            )
        recovery, recovery_fd = _fresh_recovery_identity(
            request,
            runtime_root,
        )
        try:
            recovered = api.reconcile_bundle_transfer(recovery)
        finally:
            os.close(recovery_fd)
    finally:
        os.close(runtime_root_fd)

    assert recovered is not None
    assert recovered.state == "rotated"


@pytest.mark.parametrize("locations", ("both", "neither"))
def test_ambiguous_rotation_pending_locations_fail_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    locations: str,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    real_rename = api._rename_noreplace
    interrupted = False

    def interrupt_archive_rename(*args, **kwargs) -> None:
        nonlocal interrupted
        if not interrupted and args[3] == api._ARCHIVE_NAME:
            interrupted = True
            raise api.ProviderIsolationBundleBrokerError("injected interruption")
        real_rename(*args, **kwargs)

    monkeypatch.setattr(api, "_rename_noreplace", interrupt_archive_rename)
    try:
        api.prepare_and_publish_bundle_transfer(request)
        api.record_bundle_transfer_validation(
            request,
            contract_digest="sha256:" + ("b" * 64),
            disposition="invalid",
            normalized_value_digest=None,
        )
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.rotate_invalid_bundle_transfer(
                request,
                acknowledgement=lambda _record: True,
            )
        paths = api.derive_bundle_transfer_paths(request)
        target = runtime_root / paths.target_relative_path
        archive = runtime_root / paths.archive_relative_path
        if locations == "both":
            os.link(target, archive)
        else:
            target.unlink()
        before = {
            path: path.read_bytes()
            for path in (target, archive)
            if path.exists()
        }
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.reconcile_bundle_transfer(request)
        after = {
            path: path.read_bytes()
            for path in (target, archive)
            if path.exists()
        }
    finally:
        os.close(runtime_root_fd)

    assert after == before


def test_later_attempt_can_publish_after_invalid_archive_rotation(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    first, runtime_root_fd = _transfer_request(runtime_root, payload=b"invalid")
    try:
        api.prepare_and_publish_bundle_transfer(first)
        api.record_bundle_transfer_validation(
            first,
            contract_digest="sha256:" + ("b" * 64),
            disposition="invalid",
            normalized_value_digest=None,
        )
        rotated = api.rotate_invalid_bundle_transfer(
            first,
            acknowledgement=lambda _record: True,
        )
        second_invocation_identity = "sha256:" + ("d" * 64)
        second_ordinal = 2
        authority_binding = api._derive_transfer_request_authority_binding(
            runtime_root_fd=runtime_root_fd,
            expected_runtime_mount_id=first.expected_runtime_mount_id,
            invocation_identity=second_invocation_identity,
            scope=first.scope,
            ordinal=second_ordinal,
            target_relative_path=first.target_relative_path,
        )
        capture = _bind_capture_for_test(
            _captured(b"valid"),
            authority_binding=authority_binding,
        )
        request_capture_binding = api._derive_request_capture_binding(
            request_authority_binding=authority_binding,
            capture_source_authority_binding=(
                capture._source_authority_binding
            ),
            capture_binding=capture._binding,
        )
        second = api.ProviderIsolationBundleTransferRequest(
            runtime_root_fd=runtime_root_fd,
            expected_runtime_mount_id=first.expected_runtime_mount_id,
            invocation_identity=second_invocation_identity,
            scope=first.scope,
            ordinal=second_ordinal,
            target_relative_path=first.target_relative_path,
            capture=capture,
            _authority_binding=authority_binding,
            _capture_binding=capture._binding,
            _request_capture_binding=request_capture_binding,
            _token=api._TRANSFER_REQUEST_TOKEN,
        )
        published = api.prepare_and_publish_bundle_transfer(second)
    finally:
        os.close(runtime_root_fd)

    assert published is not None
    assert (runtime_root / rotated.archive_relative_path).read_bytes() == b"invalid"
    assert (runtime_root / published.target_relative_path).read_bytes() == b"valid"


def test_publication_orders_file_and_directory_fsync_around_no_replace_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    real_fsync = api.os.fsync
    real_rename = api._rename_noreplace
    real_advance = api._advance_journal
    events: list[tuple[str, str]] = []

    def recording_fsync(fd: int) -> None:
        mode = os.fstat(fd).st_mode
        events.append(("fsync", "directory" if stat.S_ISDIR(mode) else "file"))
        real_fsync(fd)

    def recording_rename(*args, **kwargs) -> None:
        events.append(("rename", f"{args[1]}->{args[3]}"))
        real_rename(*args, **kwargs)

    def recording_advance(*args, **kwargs):
        result = real_advance(*args, **kwargs)
        events.append(("journal", kwargs["document"]["state"]))
        return result

    monkeypatch.setattr(api.os, "fsync", recording_fsync)
    monkeypatch.setattr(api, "_rename_noreplace", recording_rename)
    monkeypatch.setattr(api, "_advance_journal", recording_advance)
    try:
        api.prepare_and_publish_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    prepared = events.index(("journal", "prepared"))
    publish_rename = events.index(
        ("rename", f"{api._STAGED_NAME}->provider-step.json")
    )
    published = events.index(("journal", "published"))
    assert any(event == ("fsync", "file") for event in events[:prepared])
    assert prepared < publish_rename < published
    assert ("fsync", "directory") in events[publish_rename + 1 : published]


def test_journal_linked_name_exchange_during_descriptor_read_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    record = api.prepare_and_publish_bundle_transfer(request)
    assert record is not None
    journal = runtime_root / record.journal_relative_path
    original = journal.read_bytes()
    displaced = tmp_path / "displaced-journal"
    real_open = api.os.open
    exchanged = False

    def exchanging_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal exchanged
        if (
            not exchanged
            and isinstance(path, str)
            and path.startswith("/proc/self/fd/")
        ):
            exchanged = True
            journal.rename(displaced)
            journal.write_bytes(original)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(api.os, "open", exchanging_open)
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.reconcile_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert exchanged
    assert journal.read_bytes() == original
    assert displaced.read_bytes() == original


def test_preexisting_nonprivate_broker_directory_is_rejected(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    broker_root = runtime_root / api._BROKER_ROOT
    broker_root.mkdir(mode=0o755)
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert stat.S_IMODE(broker_root.stat().st_mode) == 0o755


def test_fresh_recovery_identity_needs_no_original_capture_bytes(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, publication_fd = _transfer_request(runtime_root)
    published = api.prepare_and_publish_bundle_transfer(request)
    assert published is not None
    recovery_fd = _open_directory(runtime_root)
    recovery = api.ProviderIsolationBundleTransferIdentity(
        runtime_root_fd=recovery_fd,
        expected_runtime_mount_id=_runtime_api()._statx_mount_id(recovery_fd),
        invocation_identity=request.invocation_identity,
        scope=request.scope,
        ordinal=request.ordinal,
        target_relative_path=request.target_relative_path,
    )
    try:
        recovered = api.reconcile_bundle_transfer(recovery)
    finally:
        os.close(recovery_fd)
        os.close(publication_fd)

    assert not hasattr(recovery, "capture")
    assert recovered is not None
    assert recovered.canonical_json == published.canonical_json


def test_same_identity_publication_replay_with_different_bytes_fails_closed(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    original, runtime_root_fd = _transfer_request(
        runtime_root,
        payload=b"original",
    )
    conflicting = _replace_request_capture_for_test(
        original,
        _captured(b"different"),
    )
    try:
        published = api.prepare_and_publish_bundle_transfer(original)
        assert published is not None
        target = runtime_root / published.target_relative_path
        before = target.read_bytes()
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(conflicting)
        after = target.read_bytes()
    finally:
        os.close(runtime_root_fd)

    assert before == b"original"
    assert after == before


def test_replaced_target_inode_with_same_bytes_fails_identity_binding(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    try:
        published = api.prepare_and_publish_bundle_transfer(request)
        assert published is not None
        target = runtime_root / published.target_relative_path
        payload = target.read_bytes()
        original_inode = target.stat().st_ino
        replacement = target.with_name(".replacement.json")
        replacement.write_bytes(payload)
        replacement_inode = replacement.stat().st_ino
        os.replace(replacement, target)
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.reconcile_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert replacement_inode != original_inode
    assert target.read_bytes() == payload


def test_target_ancestry_mount_drift_fails_without_bundle_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    request, runtime_root_fd = _transfer_request(runtime_root)
    root_inode = os.fstat(runtime_root_fd).st_ino
    real_mount_id = api._statx_mount_id

    def drifted_mount_id(directory_fd: int, name: str | None = None) -> int:
        value = real_mount_id(directory_fd, name)
        if name is None and os.fstat(directory_fd).st_ino != root_inode:
            return value + 1
        return value

    monkeypatch.setattr(api, "_statx_mount_id", drifted_mount_id)
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.prepare_and_publish_bundle_transfer(request)
    finally:
        os.close(runtime_root_fd)

    assert not (runtime_root / request.target_relative_path).exists()
    assert not (runtime_root / api._BROKER_ROOT).exists()


def _scratch_cleanup_authorities(runtime_root: Path):
    runtime_api = _runtime_api()
    runtime_root.mkdir()
    scratch_parent = runtime_root / "provider-invocation-scratch"
    scratch_parent.mkdir(mode=0o700)
    scratch = scratch_parent / ("a" * 64)
    scratch.mkdir(mode=0o700)
    runtime_fd = _open_directory(runtime_root)
    scratch_fd = _open_directory(scratch)
    observed = os.fstat(scratch_fd)
    identity = runtime_api.RuntimeAuthorityObjectIdentity(
        path=str(scratch),
        device=observed.st_dev,
        inode=observed.st_ino,
        mount_id=runtime_api._statx_mount_id(scratch_fd),
    )
    return runtime_fd, scratch_fd, scratch, identity


def _missing_capture():
    return _api().ProviderIsolationBundleCapture(
        classification="missing",
        data=None,
        digest=None,
        size_bytes=None,
        reason=None,
    )


def test_scratch_cleanup_waits_for_ack_and_removes_only_the_exact_proved_tree(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    runtime_fd, scratch_fd, scratch, scratch_identity = (
        _scratch_cleanup_authorities(runtime_root)
    )
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unchanged")
    other = scratch.parent / "other-attempt"
    other.mkdir(mode=0o700)
    (other / "keep.txt").write_bytes(b"keep")
    (scratch / "result.json").write_bytes(b"result")
    (scratch / "sibling.txt").write_bytes(b"sibling")
    nested = scratch / "nested"
    nested.mkdir(mode=0o700)
    (nested / "value.txt").write_bytes(b"value")
    (nested / "outside-link").symlink_to(outside)
    os.mkfifo(scratch / "provider-fifo")
    evidence = _captured(b"result")
    acknowledgements: list[object] = []

    try:
        result = api.cleanup_invocation_scratch_after_acknowledgement(
            runtime_root_fd=runtime_fd,
            expected_runtime_mount_id=(
                _runtime_api()._statx_mount_id(runtime_fd)
            ),
            scratch_directory_fd=scratch_fd,
            scratch_relative_path=(
                f"provider-invocation-scratch/{'a' * 64}"
            ),
            expected_scratch_identity=scratch_identity,
            evidence=evidence,
            acknowledgement=lambda value: (
                acknowledgements.append(value) or True
            ),
        )
    finally:
        os.close(scratch_fd)
        os.close(runtime_fd)

    assert result.cleaned is True
    assert result.removed_entry_count == 6
    assert acknowledgements == [evidence]
    assert not scratch.exists()
    assert (other / "keep.txt").read_bytes() == b"keep"
    assert outside.read_bytes() == b"unchanged"


@pytest.mark.parametrize("acknowledgement_kind", ("false", "error"))
def test_scratch_cleanup_rejects_missing_ack_without_mutation(
    tmp_path: Path,
    acknowledgement_kind: str,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    runtime_fd, scratch_fd, scratch, scratch_identity = (
        _scratch_cleanup_authorities(runtime_root)
    )
    payload = scratch / "payload.txt"
    payload.write_bytes(b"preserved")

    def acknowledge(_evidence: object) -> bool:
        if acknowledgement_kind == "error":
            raise RuntimeError("injected acknowledgement failure")
        return False

    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.cleanup_invocation_scratch_after_acknowledgement(
                runtime_root_fd=runtime_fd,
                expected_runtime_mount_id=(
                    _runtime_api()._statx_mount_id(runtime_fd)
                ),
                scratch_directory_fd=scratch_fd,
                scratch_relative_path=(
                    f"provider-invocation-scratch/{'a' * 64}"
                ),
                expected_scratch_identity=scratch_identity,
                evidence=_missing_capture(),
                acknowledgement=acknowledge,
            )
    finally:
        os.close(scratch_fd)
        os.close(runtime_fd)

    assert payload.read_bytes() == b"preserved"
    assert scratch.is_dir()


def test_scratch_cleanup_rejects_linked_directory_swap_before_mutation(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    runtime_fd, scratch_fd, scratch, scratch_identity = (
        _scratch_cleanup_authorities(runtime_root)
    )
    held_payload = scratch / "held.txt"
    held_payload.write_bytes(b"held")
    displaced = scratch.parent / "displaced"
    scratch.rename(displaced)
    scratch.mkdir(mode=0o700)
    replacement_payload = scratch / "replacement.txt"
    replacement_payload.write_bytes(b"replacement")

    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.cleanup_invocation_scratch_after_acknowledgement(
                runtime_root_fd=runtime_fd,
                expected_runtime_mount_id=(
                    _runtime_api()._statx_mount_id(runtime_fd)
                ),
                scratch_directory_fd=scratch_fd,
                scratch_relative_path=(
                    f"provider-invocation-scratch/{'a' * 64}"
                ),
                expected_scratch_identity=scratch_identity,
                evidence=_captured(),
                acknowledgement=lambda _evidence: True,
            )
    finally:
        os.close(scratch_fd)
        os.close(runtime_fd)

    assert (displaced / "held.txt").read_bytes() == b"held"
    assert replacement_payload.read_bytes() == b"replacement"


@pytest.mark.parametrize("entry_kind", ("file", "directory"))
def test_scratch_cleanup_quarantines_final_boundary_replacement_without_deleting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry_kind: str,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    runtime_fd, scratch_fd, scratch, scratch_identity = (
        _scratch_cleanup_authorities(runtime_root)
    )
    victim = scratch / "victim"
    if entry_kind == "file":
        victim.write_bytes(b"proved")
    else:
        victim.mkdir(mode=0o700)
    displaced = scratch / "displaced-proved-entry"
    real_require_binding = api._require_cleanup_entry_binding
    swapped = False

    def swap_after_final_binding(**kwargs) -> None:
        nonlocal swapped
        real_require_binding(**kwargs)
        if (
            kwargs["deleting"] is True
            and kwargs["basename"] == "victim"
            and not swapped
        ):
            victim.rename(displaced)
            if entry_kind == "file":
                victim.write_bytes(b"replacement")
            else:
                victim.mkdir(mode=0o700)
            swapped = True

    monkeypatch.setattr(
        api,
        "_require_cleanup_entry_binding",
        swap_after_final_binding,
    )
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.cleanup_invocation_scratch_after_acknowledgement(
                runtime_root_fd=runtime_fd,
                expected_runtime_mount_id=(
                    _runtime_api()._statx_mount_id(runtime_fd)
                ),
                scratch_directory_fd=scratch_fd,
                scratch_relative_path=(
                    f"provider-invocation-scratch/{'a' * 64}"
                ),
                expected_scratch_identity=scratch_identity,
                evidence=_missing_capture(),
                acknowledgement=lambda _evidence: True,
            )
    finally:
        os.close(scratch_fd)
        os.close(runtime_fd)

    assert swapped is True
    if entry_kind == "file":
        assert displaced.read_bytes() == b"proved"
        quarantined = tuple(
            path
            for path in scratch.iterdir()
            if path.name.startswith(".provider-cleanup-")
        )
        assert len(quarantined) == 1
        assert quarantined[0].read_bytes() == b"replacement"
    else:
        assert displaced.is_dir()
        quarantined = tuple(
            path
            for path in scratch.iterdir()
            if path.name.startswith(".provider-cleanup-")
        )
        assert len(quarantined) == 1
        assert quarantined[0].is_dir()


def test_scratch_cleanup_mount_drift_fails_before_deleting_any_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    runtime_fd, scratch_fd, scratch, scratch_identity = (
        _scratch_cleanup_authorities(runtime_root)
    )
    first = scratch / "a.txt"
    second = scratch / "b.txt"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    expected_mount_id = _runtime_api()._statx_mount_id(runtime_fd)
    real_mount_id = api._statx_mount_id
    calls = 0

    def drifted_mount_id(directory_fd: int, name: str | None = None) -> int:
        nonlocal calls
        calls += 1
        value = real_mount_id(directory_fd, name)
        return value if calls < 4 else value + 1

    monkeypatch.setattr(api, "_statx_mount_id", drifted_mount_id)
    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.cleanup_invocation_scratch_after_acknowledgement(
                runtime_root_fd=runtime_fd,
                expected_runtime_mount_id=expected_mount_id,
                scratch_directory_fd=scratch_fd,
                scratch_relative_path=(
                    f"provider-invocation-scratch/{'a' * 64}"
                ),
                expected_scratch_identity=scratch_identity,
                evidence=_captured(),
                acknowledgement=lambda _evidence: True,
            )
    finally:
        os.close(scratch_fd)
        os.close(runtime_fd)

    assert first.read_bytes() == b"a"
    assert second.read_bytes() == b"b"


def test_scratch_cleanup_rejects_cross_mount_binding_before_acknowledgement(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_api = _runtime_api()
    runtime_root = tmp_path / "runtime"
    runtime_fd, scratch_fd, scratch, scratch_identity = (
        _scratch_cleanup_authorities(runtime_root)
    )
    payload = scratch / "payload.txt"
    payload.write_bytes(b"preserved")
    mismatched_identity = runtime_api.RuntimeAuthorityObjectIdentity(
        path=scratch_identity.path,
        device=scratch_identity.device,
        inode=scratch_identity.inode,
        mount_id=scratch_identity.mount_id + 1,
    )
    acknowledgements: list[object] = []

    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.cleanup_invocation_scratch_after_acknowledgement(
                runtime_root_fd=runtime_fd,
                expected_runtime_mount_id=(
                    runtime_api._statx_mount_id(runtime_fd)
                ),
                scratch_directory_fd=scratch_fd,
                scratch_relative_path=(
                    f"provider-invocation-scratch/{'a' * 64}"
                ),
                expected_scratch_identity=mismatched_identity,
                evidence=_missing_capture(),
                acknowledgement=lambda evidence: (
                    acknowledgements.append(evidence) or True
                ),
            )
    finally:
        os.close(scratch_fd)
        os.close(runtime_fd)

    assert acknowledgements == []
    assert payload.read_bytes() == b"preserved"


def test_scratch_cleanup_rejects_non_invocation_subtree_before_acknowledgement(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_api = _runtime_api()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    wrong = runtime_root / "results" / ("a" * 64)
    wrong.mkdir(parents=True, mode=0o700)
    wrong.chmod(0o700)
    payload = wrong / "payload.txt"
    payload.write_bytes(b"preserved")
    runtime_fd = _open_directory(runtime_root)
    wrong_fd = _open_directory(wrong)
    observed = os.fstat(wrong_fd)
    identity = runtime_api.RuntimeAuthorityObjectIdentity(
        path=str(wrong),
        device=observed.st_dev,
        inode=observed.st_ino,
        mount_id=runtime_api._statx_mount_id(wrong_fd),
    )
    acknowledgements: list[object] = []

    try:
        with pytest.raises(api.ProviderIsolationBundleBrokerError):
            api.cleanup_invocation_scratch_after_acknowledgement(
                runtime_root_fd=runtime_fd,
                expected_runtime_mount_id=(
                    runtime_api._statx_mount_id(runtime_fd)
                ),
                scratch_directory_fd=wrong_fd,
                scratch_relative_path=f"results/{'a' * 64}",
                expected_scratch_identity=identity,
                evidence=_missing_capture(),
                acknowledgement=lambda evidence: (
                    acknowledgements.append(evidence) or True
                ),
            )
    finally:
        os.close(wrong_fd)
        os.close(runtime_fd)

    assert acknowledgements == []
    assert payload.read_bytes() == b"preserved"


def test_scratch_cleanup_removes_internal_hardlinks_and_preserves_outside_alias(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    runtime_fd, scratch_fd, scratch, scratch_identity = (
        _scratch_cleanup_authorities(runtime_root)
    )
    first = scratch / "first.txt"
    second = scratch / "second.txt"
    outside_alias = tmp_path / "outside-alias.txt"
    first.write_bytes(b"shared")
    os.link(first, second)
    os.link(first, outside_alias)

    try:
        result = api.cleanup_invocation_scratch_after_acknowledgement(
            runtime_root_fd=runtime_fd,
            expected_runtime_mount_id=(
                _runtime_api()._statx_mount_id(runtime_fd)
            ),
            scratch_directory_fd=scratch_fd,
            scratch_relative_path=(
                f"provider-invocation-scratch/{'a' * 64}"
            ),
            expected_scratch_identity=scratch_identity,
            evidence=_missing_capture(),
            acknowledgement=lambda _evidence: True,
        )
    finally:
        os.close(scratch_fd)
        os.close(runtime_fd)

    assert result.removed_entry_count == 2
    assert not scratch.exists()
    assert outside_alias.read_bytes() == b"shared"
    assert outside_alias.stat().st_nlink == 1


def test_scratch_cleanup_removes_non_utf8_linux_basename(
    tmp_path: Path,
) -> None:
    api = _api()
    runtime_root = tmp_path / "runtime"
    runtime_fd, scratch_fd, scratch, scratch_identity = (
        _scratch_cleanup_authorities(runtime_root)
    )
    opaque_path = os.fsencode(scratch) + b"/opaque-\xff"
    opaque_fd = os.open(
        opaque_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        0o600,
    )
    os.close(opaque_fd)

    try:
        result = api.cleanup_invocation_scratch_after_acknowledgement(
            runtime_root_fd=runtime_fd,
            expected_runtime_mount_id=(
                _runtime_api()._statx_mount_id(runtime_fd)
            ),
            scratch_directory_fd=scratch_fd,
            scratch_relative_path=(
                f"provider-invocation-scratch/{'a' * 64}"
            ),
            expected_scratch_identity=scratch_identity,
            evidence=_missing_capture(),
            acknowledgement=lambda _evidence: True,
        )
    finally:
        os.close(scratch_fd)
        os.close(runtime_fd)

    assert result.removed_entry_count == 1
    assert not scratch.exists()
