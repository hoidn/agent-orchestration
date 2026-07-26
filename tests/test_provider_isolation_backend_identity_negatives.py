from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import shutil
import stat
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator.providers import isolation_backend as api


_BWRAP = Path("/usr/bin/bwrap")


def _changed_stat(value: os.stat_result, **changes: int) -> SimpleNamespace:
    fields = {
        name: getattr(value, name)
        for name in dir(value)
        if name.startswith("st_")
    }
    fields.update(changes)
    return SimpleNamespace(**fields)


def _patch_identity_metadata(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
    **changes: int,
) -> None:
    real_fstat = api.os.fstat
    real_lstat = api.os.lstat
    expected = real_lstat(path)
    identity = (expected.st_dev, expected.st_ino)

    def changed_fstat(fd: int) -> os.stat_result | SimpleNamespace:
        observed = real_fstat(fd)
        if (observed.st_dev, observed.st_ino) == identity:
            return _changed_stat(observed, **changes)
        return observed

    def changed_lstat(
        value: os.PathLike[str] | str,
        *args: Any,
        **kwargs: Any,
    ) -> os.stat_result | SimpleNamespace:
        observed = real_lstat(value, *args, **kwargs)
        if (observed.st_dev, observed.st_ino) == identity:
            return _changed_stat(observed, **changes)
        return observed

    monkeypatch.setattr(api.os, "fstat", changed_fstat)
    monkeypatch.setattr(api.os, "lstat", changed_lstat)


def _patch_fixture_files_as_root_owned(
    monkeypatch: pytest.MonkeyPatch,
    *paths: Path,
) -> None:
    real_fstat = api.os.fstat
    real_lstat = api.os.lstat
    fixture_paths: set[Path] = set()
    for path in paths:
        current = path
        while True:
            fixture_paths.add(current)
            if current == current.parent:
                break
            current = current.parent
    fixture_identities = {
        (value.st_dev, value.st_ino)
        for value in (real_lstat(path) for path in fixture_paths)
    }
    fixture_parents = {path.parent for path in paths}
    real_ancestor_check = api._require_safe_ancestor_chain

    def root_owned_fstat(fd: int) -> os.stat_result | SimpleNamespace:
        observed = real_fstat(fd)
        if (observed.st_dev, observed.st_ino) in fixture_identities:
            return _changed_stat(
                observed,
                st_uid=0,
                st_gid=0,
                st_mode=observed.st_mode
                & ~(
                    stat.S_ISUID
                    | stat.S_ISGID
                    | stat.S_IWGRP
                    | stat.S_IWOTH
                ),
            )
        return observed

    def root_owned_lstat(
        value: os.PathLike[str] | str,
        *args: Any,
        **kwargs: Any,
    ) -> os.stat_result | SimpleNamespace:
        observed = real_lstat(value, *args, **kwargs)
        if (observed.st_dev, observed.st_ino) in fixture_identities:
            return _changed_stat(
                observed,
                st_uid=0,
                st_gid=0,
                st_mode=observed.st_mode
                & ~(
                    stat.S_ISUID
                    | stat.S_ISGID
                    | stat.S_IWGRP
                    | stat.S_IWOTH
                ),
            )
        return observed

    def require_safe_ancestors(path: Path) -> None:
        if path in fixture_parents:
            return
        real_ancestor_check(path)

    monkeypatch.setattr(api.os, "fstat", root_owned_fstat)
    monkeypatch.setattr(api.os, "lstat", root_owned_lstat)
    monkeypatch.setattr(
        api,
        "_require_safe_ancestor_chain",
        require_safe_ancestors,
    )


def _copy_with_mode(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)
    destination.chmod(stat.S_IMODE(source.stat().st_mode))


def _test_backend_with_fixed_executable(
    monkeypatch: pytest.MonkeyPatch,
    path: Path,
) -> api.BubblewrapBackend:
    """Replace the compiled-in path only inside one backend unit test."""

    monkeypatch.setattr(api, "BACKEND_EXECUTABLE_PATH", path)
    return api.BubblewrapBackend()


def _patch_unrelated_host_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = api.get_provider_isolation_backend("bubblewrap.v1").preflight()
    try:
        capability_results = dict(
            reference.identity.capability_probe_results
        )
        containment_results = reference.identity.to_dict()["containment"][
            "probe_results"
        ]
    finally:
        reference.close()

    monkeypatch.setattr(
        api,
        "_run_backend_capability_probe",
        lambda _fd: dict(capability_results),
    )
    monkeypatch.setattr(
        api,
        "_probe_cgroup_v2_containment",
        lambda _root, *, attempt_label: dict(containment_results),
    )


def test_capability_probe_does_not_reap_completed_child_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_pid = 4242
    wait_calls: list[tuple[int, int]] = []
    reads = iter((b"diagnostic\n", b""))

    monkeypatch.setattr(api.os, "pipe2", lambda _flags: (101, 102))
    monkeypatch.setattr(api.os, "fork", lambda: child_pid)
    monkeypatch.setattr(api.os, "close", lambda _fd: None)
    monkeypatch.setattr(api.os, "set_blocking", lambda _fd, _value: None)
    monkeypatch.setattr(api.os, "read", lambda _fd, _bound: next(reads))
    monkeypatch.setattr(api.time, "monotonic", lambda: 0.0)

    def waitpid(pid: int, flags: int) -> tuple[int, int]:
        wait_calls.append((pid, flags))
        if len(wait_calls) > 1:
            raise ChildProcessError("capability child was already reaped")
        return child_pid, 1 << 8

    monkeypatch.setattr(api.os, "waitpid", waitpid)

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match=(
            "provider_isolation_backend_unavailable: "
            "rootless capability probe failed"
        ),
    ):
        api._run_backend_capability_probe(99)

    assert wait_calls == [(child_pid, os.WNOHANG)]


def test_fixed_backend_preflight_rejects_missing_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _test_backend_with_fixed_executable(
        monkeypatch,
        Path("/usr/bin/provider-isolation-missing-bwrap"),
    )

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match=(
            "provider_isolation_backend_unavailable: "
            "fixed Bubblewrap authority could not be validated"
        ),
    ):
        backend.preflight()


def test_backend_constructor_rejects_arbitrary_executable_before_open_or_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[str] = []

    def unexpected_open(*_args: Any, **_kwargs: Any) -> int:
        observed.append("open")
        raise AssertionError("arbitrary executable reached descriptor admission")

    def unexpected_probe(_fd: int) -> dict[str, object]:
        observed.append("probe")
        raise AssertionError("arbitrary executable reached capability probe")

    monkeypatch.setattr(api.os, "open", unexpected_open)
    monkeypatch.setattr(api, "_run_backend_capability_probe", unexpected_probe)

    with pytest.raises(TypeError, match="executable_path"):
        api.BubblewrapBackend(
            executable_path=tmp_path / "attacker-selected-bwrap",
        ).preflight()

    assert observed == []


def test_fixed_backend_preflight_fails_closed_without_no_follow_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api.os, "O_NOFOLLOW", 0)

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match=(
            "provider_isolation_backend_unavailable: "
            "descriptor-relative no-follow opens are unavailable"
        ),
    ):
        api.get_provider_isolation_backend("bubblewrap.v1").preflight()


def test_fixed_backend_preflight_rejects_direct_executable_symlink(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "bwrap"
    executable.symlink_to(_BWRAP)
    _patch_fixture_files_as_root_owned(monkeypatch, executable)

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match=(
            "provider_isolation_backend_unavailable: "
            "fixed Bubblewrap executable path must be symlink-free"
        ),
    ):
        _test_backend_with_fixed_executable(
            monkeypatch,
            executable,
        ).preflight()


def test_fixed_backend_preflight_rejects_symlinked_executable_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Path("/bin").is_symlink()

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match=(
            "provider_isolation_backend_unavailable: "
            "fixed Bubblewrap executable path must be symlink-free"
        ),
    ):
        _test_backend_with_fixed_executable(
            monkeypatch,
            Path("/bin/bwrap"),
        ).preflight()


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("owner", "trusted host file ownership or mode is unsafe"),
        ("mode", "trusted host file ownership or mode is unsafe"),
        ("set_id", "trusted host file ownership or mode is unsafe"),
        ("capability", "trusted host object carries extended attributes"),
        (
            "ancestor",
            "trusted host ancestor ownership or mode is unsafe",
        ),
    ),
)
def test_fixed_backend_preflight_rejects_each_untrusted_authority_dimension(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    message: str,
) -> None:
    if case == "owner":
        _patch_identity_metadata(
            monkeypatch,
            _BWRAP,
            st_uid=os.geteuid(),
        )
    elif case == "mode":
        _patch_identity_metadata(
            monkeypatch,
            _BWRAP,
            st_mode=os.lstat(_BWRAP).st_mode | stat.S_IWGRP,
        )
    elif case == "set_id":
        _patch_identity_metadata(
            monkeypatch,
            _BWRAP,
            st_mode=os.lstat(_BWRAP).st_mode | stat.S_ISUID,
        )
    elif case == "capability":
        real_fstat = api.os.fstat
        real_listxattr = api.os.listxattr
        expected = os.lstat(_BWRAP)
        identity = (expected.st_dev, expected.st_ino)

        def listxattr(
            value: int | os.PathLike[str] | str,
            *args: Any,
            **kwargs: Any,
        ) -> list[str]:
            if isinstance(value, int):
                observed = real_fstat(value)
                if (observed.st_dev, observed.st_ino) == identity:
                    return ["security.capability"]
            return real_listxattr(value, *args, **kwargs)

        monkeypatch.setattr(api.os, "listxattr", listxattr)
    else:
        _patch_identity_metadata(
            monkeypatch,
            Path("/usr/bin"),
            st_mode=os.lstat("/usr/bin").st_mode | stat.S_IWGRP,
        )

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match=f"provider_isolation_backend_unavailable: {message}",
    ):
        api.get_provider_isolation_backend("bubblewrap.v1").preflight()


def test_fixed_backend_preflight_rejects_set_id_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ancestor = Path("/usr/bin")
    _patch_identity_metadata(
        monkeypatch,
        ancestor,
        st_mode=os.lstat(ancestor).st_mode | stat.S_ISGID,
    )

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match=(
            "provider_isolation_backend_unavailable: "
            "trusted host ancestor ownership or mode is unsafe"
        ),
    ):
        api.get_provider_isolation_backend("bubblewrap.v1").preflight()


def test_real_backend_accepts_recorded_safe_system_closure_symlinks() -> None:
    pinned = api.get_provider_isolation_backend("bubblewrap.v1").preflight()
    try:
        assert pinned.identity.executable.path == os.fspath(_BWRAP)
        assert pinned.identity.executable.symlinks == ()
        recorded_links = {
            item
            for entry in pinned.identity.startup_closure
            for item in entry.symlinks
        }
        assert ("/lib", "usr/lib") in recorded_links
        assert any(
            path.endswith("/libcap.so.2") and text == "libcap.so.2.66"
            for path, text in recorded_links
        )
        assert any(
            path == "/usr/lib64/ld-linux-x86-64.so.2"
            and text == "../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
            for path, text in recorded_links
        )
    finally:
        pinned.close()


def test_closure_path_resolution_rejects_link_swap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    link = tmp_path / "closure-member"
    link.symlink_to(_BWRAP)
    _patch_fixture_files_as_root_owned(monkeypatch, link)
    real_readlink = api.os.readlink
    swapped = False

    def swap_then_readlink(
        value: os.PathLike[str] | str,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        nonlocal swapped
        if not swapped and Path(value).name == link.name:
            link.unlink()
            link.symlink_to("/etc/ld.so.cache")
            swapped = True
        return real_readlink(value, *args, **kwargs)

    monkeypatch.setattr(api.os, "readlink", swap_then_readlink)

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match="trusted host symlink changed during admission",
    ):
        api._resolve_safe_host_path(link)


def test_closure_path_resolution_rejects_link_escape_above_host_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    link = tmp_path / "closure-member"
    link.symlink_to("/../../usr/bin/bwrap")
    _patch_fixture_files_as_root_owned(monkeypatch, link)

    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match="trusted host symlink escaped the root",
    ):
        api._resolve_safe_host_path(link)


@pytest.mark.parametrize("case", ("owner", "capability"))
def test_closure_path_resolution_rejects_untrusted_link(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
) -> None:
    link = tmp_path / "closure-member"
    link.symlink_to(_BWRAP)
    if case == "capability":
        _patch_fixture_files_as_root_owned(monkeypatch, link)
        real_listxattr = api.os.listxattr
        identity = os.lstat(link)

        def listxattr(
            value: int | os.PathLike[str] | str,
            *args: Any,
            **kwargs: Any,
        ) -> list[str]:
            if not isinstance(value, int):
                observed = os.lstat(value)
                if (
                    observed.st_dev,
                    observed.st_ino,
                ) == (identity.st_dev, identity.st_ino):
                    return ["security.capability"]
            return real_listxattr(value, *args, **kwargs)

        monkeypatch.setattr(api.os, "listxattr", listxattr)

    message = (
        "trusted host symlink carries extended attributes"
        if case == "capability"
        else "trusted host symlink is not root-owned"
    )
    with pytest.raises(
        api.ProviderIsolationBackendUnavailable,
        match=message,
    ):
        api._resolve_safe_host_path(link)


def test_revalidation_rejects_same_version_executable_path_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected = tmp_path / "bwrap"
    replacement = tmp_path / "replacement-bwrap"
    _copy_with_mode(_BWRAP, selected)
    _copy_with_mode(_BWRAP, replacement)
    selected_before = selected.stat()
    replacement_before = replacement.stat()
    _patch_fixture_files_as_root_owned(
        monkeypatch,
        selected,
        replacement,
    )
    _patch_unrelated_host_probes(monkeypatch)
    backend = _test_backend_with_fixed_executable(monkeypatch, selected)
    pinned = backend.preflight()
    try:
        replacement_fd = os.open(
            replacement,
            os.O_RDONLY | os.O_CLOEXEC,
        )
        try:
            assert (
                api._backend_version_from_descriptor(replacement_fd)
                == pinned.identity.version
            )
        finally:
            os.close(replacement_fd)

        os.replace(replacement, selected)
        selected_after = selected.stat()
        assert selected_after.st_dev == selected_before.st_dev
        assert selected_after.st_ino == replacement_before.st_ino
        assert selected_after.st_ino != selected_before.st_ino

        with pytest.raises(
            api.ProviderIsolationBackendUnavailable,
            match=(
                "provider_isolation_backend_unavailable: "
                "backend startup identity changed"
            ),
        ):
            pinned.revalidate()
    finally:
        pinned.close()


def test_revalidation_rejects_same_inode_same_size_content_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selected = tmp_path / "bwrap"
    _copy_with_mode(_BWRAP, selected)
    _patch_fixture_files_as_root_owned(monkeypatch, selected)
    _patch_unrelated_host_probes(monkeypatch)
    backend = _test_backend_with_fixed_executable(monkeypatch, selected)
    pinned = backend.preflight()
    try:
        before = selected.stat()
        with selected.open("r+b") as handle:
            handle.seek(-1, os.SEEK_END)
            original = handle.read(1)
            handle.seek(-1, os.SEEK_END)
            handle.write(bytes((original[0] ^ 0x01,)))
            handle.flush()
            os.fsync(handle.fileno())
        selected.chmod(stat.S_IMODE(before.st_mode))
        os.utime(
            selected,
            ns=(before.st_atime_ns, before.st_mtime_ns),
        )
        after = selected.stat()
        assert (
            after.st_dev,
            after.st_ino,
            after.st_size,
            stat.S_IMODE(after.st_mode),
            after.st_mtime_ns,
        ) == (
            before.st_dev,
            before.st_ino,
            before.st_size,
            stat.S_IMODE(before.st_mode),
            before.st_mtime_ns,
        )

        with pytest.raises(
            api.ProviderIsolationBackendUnavailable,
            match=(
                "provider_isolation_backend_unavailable: "
                "pinned backend executable identity changed"
            ),
        ):
            pinned.revalidate()
    finally:
        pinned.close()


@pytest.mark.parametrize(
    "member_kind",
    ("loader", "transitive_library", "loader_cache"),
)
def test_revalidation_rejects_each_startup_closure_member_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    member_kind: str,
) -> None:
    backend = api.get_provider_isolation_backend("bubblewrap.v1")
    pinned = backend.preflight()
    try:
        if member_kind == "loader":
            expected = next(
                entry
                for entry in pinned.identity.startup_closure
                if "ld-linux" in entry.path
            )
        elif member_kind == "transitive_library":
            expected = next(
                entry
                for entry in pinned.identity.startup_closure
                if entry.path.endswith("/libc.so.6")
            )
        else:
            expected = pinned.identity.loader_cache

        substitute = tmp_path / member_kind
        _copy_with_mode(Path(expected.resolved_path), substitute)
        _patch_fixture_files_as_root_owned(monkeypatch, substitute)
        real_admit = api._admit_trusted_regular

        def admit_with_replaced_member(
            path: Path,
            *,
            keep_open: bool,
        ) -> tuple[api.TrustedPathEntry, int]:
            if path != Path(expected.path):
                return real_admit(path, keep_open=keep_open)
            observed, fd = real_admit(substitute, keep_open=keep_open)
            return (
                replace(
                    observed,
                    path=expected.path,
                    resolved_path=expected.resolved_path,
                    symlinks=expected.symlinks,
                ),
                fd,
            )

        monkeypatch.setattr(
            api,
            "_admit_trusted_regular",
            admit_with_replaced_member,
        )
        with pytest.raises(
            api.ProviderIsolationBackendUnavailable,
            match=(
                "provider_isolation_backend_unavailable: "
                "backend startup identity changed"
            ),
        ):
            pinned.revalidate()
    finally:
        pinned.close()


def test_revalidation_rejects_startup_configuration_appearance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = api.get_provider_isolation_backend("bubblewrap.v1")
    pinned = backend.preflight()
    preload = Path("/etc/ld.so.preload")
    real_exists = Path.exists
    real_is_symlink = Path.is_symlink

    def exists(path: Path) -> bool:
        if path == preload:
            return True
        return real_exists(path)

    def is_symlink(path: Path) -> bool:
        if path == preload:
            return False
        return real_is_symlink(path)

    monkeypatch.setattr(Path, "exists", exists)
    monkeypatch.setattr(Path, "is_symlink", is_symlink)
    try:
        with pytest.raises(
            api.ProviderIsolationBackendUnavailable,
            match=(
                "provider_isolation_backend_unavailable: "
                "/etc/ld[.]so[.]preload is present"
            ),
        ):
            pinned.revalidate()
    finally:
        pinned.close()
