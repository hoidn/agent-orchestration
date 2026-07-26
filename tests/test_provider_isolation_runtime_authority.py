from __future__ import annotations

from dataclasses import replace
import importlib
import os
from pathlib import Path
import stat

import pytest


_EXPECTED_MAX_DIRECTORY_DEPTH = 128
_EXPECTED_MAX_ENTRY_COUNT = 100_000
_EXPECTED_MAX_SYMLINK_EXPANSIONS = 40
_EXPECTED_MAX_ANCESTRY_DEPTH = 128


def _api():
    return importlib.import_module(
        "orchestrator.providers.isolation_runtime_authority"
    )


def _candidate(tmp_path: Path, name: str = "candidate") -> Path:
    candidate = tmp_path / name
    candidate.mkdir(mode=0o700)
    return candidate


def _fd_count() -> int:
    return len(os.listdir("/proc/self/fd"))


def _make_descriptor_chain(root: Path, depth: int) -> Path:
    current_fd = os.open(
        root,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    components: list[str] = []
    try:
        for _ in range(depth):
            os.mkdir("d", 0o700, dir_fd=current_fd)
            next_fd = os.open(
                "d",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
            components.append("d")
    finally:
        os.close(current_fd)
    return Path(f"{root}/{'/'.join(components)}")


def _remove_directory_chain(root: Path, depth: int) -> None:
    current = str(root)
    paths: list[str] = []
    for _ in range(depth):
        current = f"{current}/d"
        paths.append(current)
    for path in reversed(paths):
        os.rmdir(path)


def _create_regular_entries(
    directory_fd: int,
    count: int,
    *,
    start: int = 0,
) -> None:
    for index in range(start, start + count):
        fd = os.open(
            f"entry-{index}",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
        os.close(fd)


def _make_symlink_chain(root: Path, length: int) -> None:
    (root / "product.txt").write_bytes(b"product")
    for index in reversed(range(length)):
        target = "product.txt" if index == length - 1 else f"link-{index + 1}"
        (root / f"link-{index}").symlink_to(target)


def test_runtime_authority_publishes_aligned_traversal_bounds() -> None:
    api = _api()

    assert (
        api.MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH
        == _EXPECTED_MAX_DIRECTORY_DEPTH
    )
    assert api.MAX_RUNTIME_AUTHORITY_ENTRY_COUNT == _EXPECTED_MAX_ENTRY_COUNT
    assert (
        api.MAX_RUNTIME_AUTHORITY_SYMLINK_EXPANSIONS
        == _EXPECTED_MAX_SYMLINK_EXPANSIONS
    )
    assert (
        api.MAX_RUNTIME_AUTHORITY_ANCESTRY_DEPTH
        == _EXPECTED_MAX_ANCESTRY_DEPTH
    )


def test_fresh_authority_creates_one_private_real_runtime_directory(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        runtime = candidate / ".orchestrate"
        runtime_stat = runtime.lstat()

        assert runtime.is_dir()
        assert not runtime.is_symlink()
        assert stat.S_IMODE(runtime_stat.st_mode) == 0o700
        assert authority.identity.schema_version == (
            "provider_isolation_runtime_authority.v1"
        )
        assert authority.identity.candidate_root == str(candidate)
        assert authority.identity.candidate.inode == candidate.stat().st_ino
        assert authority.identity.runtime.inode == runtime_stat.st_ino
        assert authority.identity.runtime.mount_id == (
            authority.identity.candidate.mount_id
        )
        assert authority.identity.ancestry[-1] == authority.identity.candidate
        assert authority.identity.to_dict()["runtime"]["inode"] == runtime_stat.st_ino
        authority.revalidate()


@pytest.mark.parametrize("existing_kind", ("directory", "file", "symlink", "fifo"))
def test_fresh_authority_rejects_every_preexisting_runtime_entry(
    tmp_path: Path,
    existing_kind: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    runtime = candidate / ".orchestrate"
    if existing_kind == "directory":
        runtime.mkdir()
    elif existing_kind == "file":
        runtime.write_text("preexisting", encoding="utf-8")
    elif existing_kind == "symlink":
        runtime.symlink_to(tmp_path / "outside")
    else:
        os.mkfifo(runtime)

    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
        api.ProviderIsolationRuntimeAuthority.create_fresh(candidate)

    assert raised.value.code == "provider_isolation_candidate_invalid"


def test_fresh_authority_rejects_a_symlink_candidate_root(tmp_path: Path) -> None:
    api = _api()
    real_candidate = _candidate(tmp_path, "real-candidate")
    candidate = tmp_path / "candidate"
    candidate.symlink_to(real_candidate, target_is_directory=True)

    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
        api.ProviderIsolationRuntimeAuthority.create_fresh(candidate)

    assert not (real_candidate / ".orchestrate").exists()


def test_candidate_root_rejects_double_leading_slash_alias_but_accepts_canonical(
    tmp_path: Path,
) -> None:
    api = _api()
    canonical = _candidate(tmp_path, "canonical-candidate")
    aliased_target = _candidate(tmp_path, "aliased-candidate")

    with api.ProviderIsolationRuntimeAuthority.create_fresh(canonical):
        pass

    double_slash_alias = f"//{str(aliased_target).lstrip('/')}"
    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
        api.ProviderIsolationRuntimeAuthority.create_fresh(double_slash_alias)

    assert raised.value.code == "provider_isolation_candidate_invalid"
    assert not (aliased_target / ".orchestrate").exists()


@pytest.mark.parametrize("entrypoint", ("create_fresh", "resume"))
def test_candidate_root_nul_is_rejected_before_os_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    api = _api()
    nul_candidate = f"{tmp_path}/bad\x00candidate"
    open_calls: list[object] = []
    real_open = api.os.open

    def guarded_open(path, flags, mode=0o777, *, dir_fd=None):
        open_calls.append(path)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(api.os, "open", guarded_open)

    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
        if entrypoint == "create_fresh":
            api.ProviderIsolationRuntimeAuthority.create_fresh(nul_candidate)
        else:
            api.ProviderIsolationRuntimeAuthority.resume(nul_candidate, object())

    assert raised.value.code == "provider_isolation_candidate_invalid"
    assert open_calls == []


@pytest.mark.parametrize("entrypoint", ("create_fresh", "resume"))
@pytest.mark.parametrize("failure_kind", ("mount", "os", "value", "type"))
def test_candidate_path_conversion_failures_are_normalized(
    tmp_path: Path,
    entrypoint: str,
    failure_kind: str,
) -> None:
    api = _api()

    class FailingPath:
        def __fspath__(self):
            if failure_kind == "mount":
                raise api.MountIdentityUnavailable(
                    "injected candidate conversion failure"
                )
            if failure_kind == "os":
                raise OSError("injected candidate conversion failure")
            if failure_kind == "value":
                raise ValueError("injected candidate conversion failure")
            raise TypeError("injected candidate conversion failure")

    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
        if entrypoint == "create_fresh":
            api.ProviderIsolationRuntimeAuthority.create_fresh(FailingPath())
        else:
            api.ProviderIsolationRuntimeAuthority.resume(FailingPath(), object())

    assert raised.value.code == "provider_isolation_candidate_invalid"


def test_resume_accepts_only_the_exact_recorded_candidate_runtime_and_ancestry(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as fresh:
        identity = fresh.identity

    with api.ProviderIsolationRuntimeAuthority.resume(candidate, identity) as resumed:
        assert resumed.identity == identity
        resumed.revalidate()

    changed = replace(
        identity,
        runtime=replace(identity.runtime, inode=identity.runtime.inode + 1),
    )
    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
        api.ProviderIsolationRuntimeAuthority.resume(candidate, changed)


@pytest.mark.parametrize("failure_kind", ("mount", "value"))
@pytest.mark.parametrize("failure_point", ("root", "descendant"))
def test_candidate_ancestry_capture_failure_does_not_leak_fds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
    failure_point: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    real_capture = api._capture_directory_identity

    def failing_capture(directory_fd: int, path: str):
        should_fail = (failure_point == "root" and path == "/") or (
            failure_point == "descendant" and path != "/"
        )
        if should_fail:
            if failure_kind == "mount":
                raise api.MountIdentityUnavailable("injected ancestry failure")
            raise ValueError("injected ancestry failure")
        return real_capture(directory_fd, path)

    monkeypatch.setattr(api, "_capture_directory_identity", failing_capture)
    baseline = _fd_count()

    for _ in range(12):
        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
            api.ProviderIsolationRuntimeAuthority.create_fresh(candidate)
        assert raised.value.code == "provider_isolation_candidate_invalid"
        assert _fd_count() == baseline


@pytest.mark.parametrize("failure_kind", ("mount", "value"))
@pytest.mark.parametrize("failure_point", ("root", "descendant"))
def test_resume_ancestry_capture_failure_does_not_leak_fds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
    failure_point: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as fresh:
        identity = fresh.identity
    real_capture = api._capture_directory_identity

    def failing_capture(directory_fd: int, path: str):
        should_fail = (failure_point == "root" and path == "/") or (
            failure_point == "descendant" and path != "/"
        )
        if should_fail:
            if failure_kind == "mount":
                raise api.MountIdentityUnavailable("injected ancestry failure")
            raise ValueError("injected ancestry failure")
        return real_capture(directory_fd, path)

    monkeypatch.setattr(api, "_capture_directory_identity", failing_capture)
    baseline = _fd_count()

    for _ in range(12):
        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
            api.ProviderIsolationRuntimeAuthority.resume(candidate, identity)
        assert raised.value.code == "provider_isolation_candidate_invalid"
        assert _fd_count() == baseline


def test_candidate_ancestry_depth_has_near_bound_control_and_over_bound_reject(
    tmp_path: Path,
) -> None:
    api = _api()
    near_base = _candidate(tmp_path, "near-ancestry-base")
    near_base_depth = len(near_base.parts) - 1
    near_candidate = _make_descriptor_chain(
        near_base,
        api.MAX_RUNTIME_AUTHORITY_ANCESTRY_DEPTH - near_base_depth,
    )

    with api.ProviderIsolationRuntimeAuthority.create_fresh(near_candidate):
        pass

    over_base = _candidate(tmp_path, "over-ancestry-base")
    over_base_depth = len(over_base.parts) - 1
    over_candidate = _make_descriptor_chain(
        over_base,
        api.MAX_RUNTIME_AUTHORITY_ANCESTRY_DEPTH - over_base_depth + 1,
    )
    baseline = _fd_count()

    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
        api.ProviderIsolationRuntimeAuthority.create_fresh(over_candidate)

    assert raised.value.code == "provider_isolation_candidate_invalid"
    assert _fd_count() == baseline
    assert not (over_candidate / ".orchestrate").exists()


def test_descriptor_relative_directory_read_write_and_atomic_replace(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        authority.mkdir("runs/attempt-1", parents=True)
        authority.write_bytes("runs/attempt-1/state.json", b'{"state":"new"}\n')
        assert authority.read_bytes("runs/attempt-1/state.json") == (
            b'{"state":"new"}\n'
        )

        authority.write_bytes(
            "runs/attempt-1/state.json",
            b'{"state":"running"}\n',
        )
        assert authority.read_bytes("runs/attempt-1/state.json") == (
            b'{"state":"running"}\n'
        )

        authority.atomic_replace(
            "runs/attempt-1/state.json",
            b'{"state":"complete"}\n',
        )
        assert authority.read_bytes("runs/attempt-1/state.json") == (
            b'{"state":"complete"}\n'
        )
        assert stat.S_IMODE(
            (candidate / ".orchestrate/runs/attempt-1/state.json").stat().st_mode
        ) == 0o600

        directory_fd = authority.open_directory("runs/attempt-1")
        try:
            assert stat.S_ISDIR(os.fstat(directory_fd).st_mode)
        finally:
            os.close(directory_fd)


@pytest.mark.parametrize(
    "relpath",
    (
        "",
        ".",
        "..",
        "../outside",
        "/absolute",
        "runs/../../outside",
        "runs//state",
    ),
)
def test_descriptor_relative_operations_reject_noncanonical_paths(
    tmp_path: Path,
    relpath: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
            authority.read_bytes(relpath)


@pytest.mark.parametrize(
    "operation",
    ("open_directory", "mkdir", "read_bytes", "write_bytes", "atomic_replace"),
)
def test_runtime_operations_reject_nul_before_any_path_syscall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        real_open = api.os.open
        nul_path_syscalls: list[str] = []

        def guarded_open(path, flags, mode=0o777, *, dir_fd=None):
            if isinstance(path, str) and "\x00" in path:
                nul_path_syscalls.append(path)
                pytest.fail("NUL-containing runtime path reached os.open")
            return real_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(api.os, "open", guarded_open)

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
            if operation in {"write_bytes", "atomic_replace"}:
                getattr(authority, operation)("bad\x00path", b"payload")
            else:
                getattr(authority, operation)("bad\x00path")

        assert raised.value.code == "provider_isolation_candidate_invalid"
        assert nul_path_syscalls == []


def test_non_nul_runtime_path_remains_accepted(tmp_path: Path) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        authority.write_bytes("nul-safe-path", b"payload")
        authority.atomic_replace("nul-safe-path", b"replacement")

        assert authority.read_bytes("nul-safe-path") == b"replacement"


def test_candidate_link_scan_has_near_depth_control_and_1100_depth_reject(
    tmp_path: Path,
) -> None:
    api = _api()
    near_candidate = _candidate(tmp_path, "near-candidate-depth")
    _make_descriptor_chain(
        near_candidate,
        api.MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH,
    )

    with api.ProviderIsolationRuntimeAuthority.create_fresh(near_candidate):
        _remove_directory_chain(
            near_candidate,
            api.MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH,
        )

    deep_candidate = _candidate(tmp_path, "deep-candidate")
    _make_descriptor_chain(deep_candidate, 1_100)
    baseline = _fd_count()

    try:
        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
            api.ProviderIsolationRuntimeAuthority.create_fresh(deep_candidate)

        assert raised.value.code == "provider_isolation_candidate_invalid"
        assert _fd_count() == baseline
        assert not (deep_candidate / ".orchestrate").exists()
    finally:
        _remove_directory_chain(deep_candidate, 1_100)


def test_runtime_tree_scan_has_near_depth_control_and_1100_depth_reject(
    tmp_path: Path,
) -> None:
    api = _api()
    near_candidate = _candidate(tmp_path, "near-runtime-depth")
    with api.ProviderIsolationRuntimeAuthority.create_fresh(
        near_candidate
    ) as authority:
        _make_descriptor_chain(
            near_candidate / ".orchestrate",
            api.MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH,
        )
        authority.revalidate()
        _remove_directory_chain(
            near_candidate / ".orchestrate",
            api.MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH,
        )

    deep_candidate = _candidate(tmp_path, "deep-runtime")
    with api.ProviderIsolationRuntimeAuthority.create_fresh(
        deep_candidate
    ) as authority:
        _make_descriptor_chain(deep_candidate / ".orchestrate", 1_100)
        baseline = _fd_count()

        try:
            with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
                authority.revalidate()

            assert raised.value.code == "provider_isolation_candidate_invalid"
            assert _fd_count() == baseline
        finally:
            _remove_directory_chain(
                deep_candidate / ".orchestrate",
                1_100,
            )


def test_candidate_link_scan_enforces_entry_cap_with_near_bound_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    monkeypatch.setattr(api, "MAX_RUNTIME_AUTHORITY_ENTRY_COUNT", 8)
    near_candidate = _candidate(tmp_path, "near-candidate-entries")
    near_fd = os.open(
        near_candidate,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        _create_regular_entries(near_fd, 8)
    finally:
        os.close(near_fd)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(near_candidate):
        pass

    over_candidate = _candidate(tmp_path, "over-candidate-entries")
    over_fd = os.open(
        over_candidate,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        _create_regular_entries(over_fd, 9)
    finally:
        os.close(over_fd)

    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
        api.ProviderIsolationRuntimeAuthority.create_fresh(over_candidate)

    assert raised.value.code == "provider_isolation_candidate_invalid"
    assert not (over_candidate / ".orchestrate").exists()


def test_runtime_tree_scan_enforces_entry_cap_with_near_bound_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        runtime_fd = authority.duplicate_runtime_fd()
        try:
            _create_regular_entries(runtime_fd, 8)
        finally:
            os.close(runtime_fd)
        monkeypatch.setattr(api, "MAX_RUNTIME_AUTHORITY_ENTRY_COUNT", 8)
        authority.revalidate()

        runtime_fd = authority.duplicate_runtime_fd()
        try:
            _create_regular_entries(runtime_fd, 1, start=8)
        finally:
            os.close(runtime_fd)

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
            authority.revalidate()

        assert raised.value.code == "provider_isolation_candidate_invalid"


def test_candidate_symlink_expansion_has_near_bound_and_over_bound_cases(
    tmp_path: Path,
) -> None:
    api = _api()
    near_candidate = _candidate(tmp_path, "near-symlink-expansions")
    _make_symlink_chain(
        near_candidate,
        api.MAX_RUNTIME_AUTHORITY_SYMLINK_EXPANSIONS,
    )

    with api.ProviderIsolationRuntimeAuthority.create_fresh(near_candidate):
        pass

    over_candidate = _candidate(tmp_path, "over-symlink-expansions")
    _make_symlink_chain(
        over_candidate,
        api.MAX_RUNTIME_AUTHORITY_SYMLINK_EXPANSIONS + 1,
    )

    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
        api.ProviderIsolationRuntimeAuthority.create_fresh(over_candidate)

    assert raised.value.code == "provider_isolation_candidate_invalid"
    assert not (over_candidate / ".orchestrate").exists()


@pytest.mark.parametrize("failure_kind", ("mount", "value"))
def test_directory_traversal_capture_failure_does_not_leak_fds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        authority.mkdir("child")
        real_capture = api._capture_directory_identity

        def failing_capture(directory_fd: int, path: str):
            if path == "child":
                if failure_kind == "mount":
                    raise api.MountIdentityUnavailable(
                        "injected traversal failure"
                    )
                raise ValueError("injected traversal failure")
            return real_capture(directory_fd, path)

        monkeypatch.setattr(api, "_capture_directory_identity", failing_capture)
        baseline = _fd_count()

        for _ in range(12):
            with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
                authority.open_directory("child")
            assert raised.value.code == "provider_isolation_candidate_invalid"
            assert _fd_count() == baseline


def test_atomic_replace_setup_failure_leaves_no_fd_or_temp_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        baseline = _fd_count()

        def fail_fchmod(_fd: int, _mode: int) -> None:
            raise OSError("injected temporary-file setup failure")

        monkeypatch.setattr(api.os, "fchmod", fail_fchmod)

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
            authority.atomic_replace("state", b"payload")

        assert raised.value.code == "provider_isolation_candidate_invalid"
        assert _fd_count() == baseline
        assert os.listdir(candidate / ".orchestrate") == []


@pytest.mark.parametrize(
    "operation",
    (
        "open_directory",
        "mkdir",
        "read_bytes",
        "write_bytes",
        "atomic_replace",
        "duplicate_candidate_fd",
        "duplicate_runtime_fd",
    ),
)
@pytest.mark.parametrize("failure_kind", ("mount", "os", "value"))
def test_public_operations_normalize_parent_open_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    failure_kind: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        def fail_dup(_fd: int) -> int:
            if failure_kind == "mount":
                raise api.MountIdentityUnavailable("injected parent-open failure")
            if failure_kind == "os":
                raise OSError("injected parent-open failure")
            raise ValueError("injected parent-open failure")

        monkeypatch.setattr(api.os, "dup", fail_dup)

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
            if operation in {"duplicate_candidate_fd", "duplicate_runtime_fd"}:
                getattr(authority, operation)()
            elif operation in {"write_bytes", "atomic_replace"}:
                getattr(authority, operation)("state", b"payload")
            else:
                getattr(authority, operation)("state")

        assert raised.value.code == "provider_isolation_candidate_invalid"


def test_revalidate_normalizes_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        def fail_capture(_directory_fd: int, _path: str):
            raise ValueError("injected revalidation failure")

        monkeypatch.setattr(api, "_capture_directory_identity", fail_capture)

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError) as raised:
            authority.revalidate()

        assert raised.value.code == "provider_isolation_candidate_invalid"


def test_runtime_symlink_is_rejected_without_touching_its_outside_target(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"unchanged")

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        (candidate / ".orchestrate/escape").symlink_to(outside)

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
            authority.write_bytes("escape", b"changed")
        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
            authority.atomic_replace("escape", b"changed")

    assert outside.read_bytes() == b"unchanged"


def test_runtime_special_file_is_rejected_without_blocking(tmp_path: Path) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        os.mkfifo(candidate / ".orchestrate/result")

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
            authority.read_bytes("result")
        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
            authority.write_bytes("result", b"payload")


def test_runtime_cross_boundary_hardlink_is_rejected(tmp_path: Path) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        authority.write_bytes("state", b"inside")
        os.link(candidate / ".orchestrate/state", tmp_path / "outside-alias")

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
            authority.read_bytes("state")


def test_candidate_symlink_resolving_into_runtime_is_rejected_before_creation(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    (candidate / "runtime-alias").symlink_to(".orchestrate")

    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
        api.ProviderIsolationRuntimeAuthority.create_fresh(candidate)

    assert not (candidate / ".orchestrate").exists()


def test_safe_candidate_symlink_is_accepted(tmp_path: Path) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    (candidate / "product.txt").write_text("product", encoding="utf-8")
    (candidate / "product-alias").symlink_to("product.txt")

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        authority.revalidate()


def test_candidate_root_exchange_is_detected_by_held_ancestry(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        moved = tmp_path / "moved-candidate"
        candidate.rename(moved)
        candidate.mkdir(mode=0o700)

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
            authority.revalidate()


def test_candidate_ancestor_exchange_is_detected_by_held_ancestry(
    tmp_path: Path,
) -> None:
    api = _api()
    ancestor = tmp_path / "authority-parent"
    ancestor.mkdir(mode=0o700)
    candidate = ancestor / "candidate"
    candidate.mkdir(mode=0o700)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        moved = tmp_path / "moved-authority-parent"
        ancestor.rename(moved)
        ancestor.mkdir(mode=0o700)
        (ancestor / "candidate").mkdir(mode=0o700)

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
            authority.revalidate()


def test_runtime_mount_id_crossing_fails_closed_even_when_device_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with api.ProviderIsolationRuntimeAuthority.create_fresh(candidate) as authority:
        real_mount_id = api._statx_mount_id
        runtime_inode = authority.identity.runtime.inode

        def crossed_mount_id(directory_fd: int, name: str | None = None) -> int:
            value = real_mount_id(directory_fd, name)
            if name is None:
                observed = os.fstat(directory_fd)
            else:
                observed = os.stat(
                    name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
            if observed.st_ino == runtime_inode:
                return value + 1
            return value

        monkeypatch.setattr(api, "_statx_mount_id", crossed_mount_id)

        with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
            authority.revalidate()


def test_mount_identity_unavailable_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    def unavailable(_directory_fd: int, _name: str | None = None) -> int:
        raise api.MountIdentityUnavailable("STATX_MNT_ID unavailable")

    monkeypatch.setattr(api, "_statx_mount_id", unavailable)

    with pytest.raises(api.ProviderIsolationRuntimeAuthorityError):
        api.ProviderIsolationRuntimeAuthority.create_fresh(candidate)
