from __future__ import annotations

import array
from copy import deepcopy
import errno
import fcntl
from hashlib import sha256
import importlib
from importlib import resources
import json
import os
from pathlib import Path
import shutil
import stat
import unicodedata

import pytest


PROVIDER_PREFIX = "/opt/orchestrator-provider"
GOLDEN_MANIFEST_BYTES = (
    b'{"entries":[{"atime_ns":0,"gid":0,"kind":"directory","mode":365,'
    b'"mtime_ns":0,"path":".","uid":0},{"atime_ns":0,'
    b'"digest":"sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9'
    b'cb410ff61f20015ad","gid":0,"kind":"regular_file","mode":292,'
    b'"mtime_ns":0,"path":"alpha","size":3,"uid":0}],'
    b'"provider_prefix":"/opt/orchestrator-provider",'
    b'"schema_version":"provider_environment_manifest.v1"}\n'
)
GOLDEN_MANIFEST_DIGEST = (
    "sha256:02ab1128ec1781d2cd7d25615d7f030f308241a9ace66897d82d8611ac506c33"
)
_FS_IOC_GETFLAGS = 0x80086601
_FS_IOC_SETFLAGS = 0x40086602
_FS_NODUMP_FL = 0x00000040
_FS_NOATIME_FL = 0x00000080


def _api():
    return importlib.import_module("orchestrator.providers.isolation_environment")


def _base_manifest() -> dict[str, object]:
    return {
        "schema_version": "provider_environment_manifest.v1",
        "provider_prefix": PROVIDER_PREFIX,
        "entries": [
            {
                "path": ".",
                "kind": "directory",
                "mode": 0o555,
                "uid": 0,
                "gid": 0,
                "atime_ns": 0,
                "mtime_ns": 0,
            },
            {
                "path": "alpha",
                "kind": "regular_file",
                "mode": 0o444,
                "uid": 0,
                "gid": 0,
                "atime_ns": 0,
                "mtime_ns": 0,
                "size": 3,
                "digest": (
                    "sha256:"
                    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9"
                    "cb410ff61f20015ad"
                ),
            },
        ],
    }


def _make_source(tmp_path: Path, *, name: str = "source") -> Path:
    root = tmp_path / name
    root.mkdir(mode=0o700)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    (prefix / "bin").mkdir(parents=True, mode=0o755)
    for directory in (
        root / "opt",
        root / "opt" / "orchestrator-provider",
        prefix / "bin",
    ):
        directory.chmod(0o755)
    python = prefix / "bin" / "python"
    python.write_bytes(b"fixture interpreter\n")
    python.chmod(0o755)
    data = root / "share" / "payload.txt"
    data.parent.mkdir(mode=0o755)
    data.write_bytes(b"payload")
    data.chmod(0o644)
    (root / "share" / "payload-link").symlink_to("payload.txt")
    return root


def _entry(manifest, path: str):
    return next(entry for entry in manifest.entries if entry.path == path)


def _read_linux_inode_flags(path: Path) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    if path.is_dir():
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        value = array.array("L", [0])
        fcntl.ioctl(fd, _FS_IOC_GETFLAGS, value, True)
        return int(value[0])
    finally:
        os.close(fd)


def _write_linux_inode_flags(path: Path, value: int) -> None:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    if path.is_dir():
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        payload = array.array("L", [value])
        fcntl.ioctl(fd, _FS_IOC_SETFLAGS, payload, True)
    finally:
        os.close(fd)


class _TestPathLike:
    def __init__(self, value: str | bytes):
        self.value = value

    def __fspath__(self) -> str | bytes:
        return self.value


def _lexical_authority_alias(path: Path, alias_kind: str) -> str:
    raw = os.fspath(path)
    if alias_kind == "dot":
        return f"{path.parent}/./{path.name}"
    if alias_kind == "repeated_separator":
        return f"{path.parent}//{path.name}"
    if alias_kind == "trailing_separator":
        return f"{raw}/"
    if alias_kind == "parent":
        return f"{raw}/../{path.name}"
    if alias_kind == "relative":
        return os.path.relpath(raw, start=Path.cwd())
    raise AssertionError(f"unknown alias kind: {alias_kind}")


def test_manifest_fd_builder_never_reopens_root_and_borrows_caller_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    expected = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    root_fd = api._open_directory(source)

    def forbidden_path_root_access(*_args, **_kwargs):
        raise AssertionError("descriptor-owned scan reopened its root by path")

    monkeypatch.setattr(api, "_lstat_root", forbidden_path_root_access)
    monkeypatch.setattr(api, "_open_directory", forbidden_path_root_access)
    try:
        observed = api._build_provider_environment_manifest_from_fd(
            root_fd,
            PROVIDER_PREFIX,
            inject_launch_shim=True,
            finalized_snapshot=False,
        )

        assert observed.canonical_json == expected.canonical_json
        assert os.fstat(root_fd).st_ino == os.stat(source).st_ino
    finally:
        os.close(root_fd)


def _assert_environment_error(
    call,
    *,
    code: str = "provider_isolation_environment_invalid",
    path: str | None = None,
) -> None:
    api = _api()
    with pytest.raises(api.ProviderIsolationEnvironmentError) as exc_info:
        call()
    assert exc_info.value.code == code
    assert exc_info.value.issues
    assert all(issue.code == code for issue in exc_info.value.issues)
    if path is not None:
        assert path in {issue.path for issue in exc_info.value.issues}


def test_manifest_schema_is_recursively_closed_and_versioned() -> None:
    api = _api()
    valid = _base_manifest()
    assert api.validate_provider_environment_manifest(valid) == ()

    for document, path in [
        ({**valid, "extra": True}, "$.extra"),
        (
            {
                **valid,
                "entries": [
                    {**valid["entries"][0], "extra": True},
                    valid["entries"][1],
                ],
            },
            "$.entries[0].extra",
        ),
        ({**valid, "schema_version": "provider_environment_manifest.v2"}, "$.schema_version"),
    ]:
        issues = api.validate_provider_environment_manifest(document)
        assert path in {issue.path for issue in issues}


def test_manifest_requires_root_and_ordered_complete_rows() -> None:
    api = _api()
    document = _base_manifest()
    document["entries"] = [document["entries"][1]]
    assert "$.entries" in {
        issue.path for issue in api.validate_provider_environment_manifest(document)
    }

    duplicate = _base_manifest()
    duplicate["entries"].append(deepcopy(duplicate["entries"][1]))
    assert "$.entries[2].path" in {
        issue.path for issue in api.validate_provider_environment_manifest(duplicate)
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", "/absolute"),
        ("path", "../escape"),
        ("path", "a/../b"),
        ("path", "cafe\u0301"),
        ("kind", "socket"),
        ("mode", 0o644),
        ("uid", 1000),
        ("gid", 1000),
        ("atime_ns", 1),
        ("mtime_ns", 1),
    ],
)
def test_manifest_rejects_noncanonical_entry_fields(field: str, value: object) -> None:
    api = _api()
    document = _base_manifest()
    document["entries"][1][field] = value
    assert api.validate_provider_environment_manifest(document)


def test_entry_kinds_have_exact_kind_specific_fields() -> None:
    api = _api()
    directory = deepcopy(_base_manifest())
    directory["entries"][0]["size"] = 0
    assert api.validate_provider_environment_manifest(directory)

    regular = deepcopy(_base_manifest())
    regular["entries"][1].pop("digest")
    assert api.validate_provider_environment_manifest(regular)

    symlink = deepcopy(_base_manifest())
    symlink["entries"][1] = {
        "path": "alpha",
        "kind": "symlink",
        "mode": 0o777,
        "uid": 0,
        "gid": 0,
        "atime_ns": 0,
        "mtime_ns": 0,
        "link_text": ".",
    }
    assert api.validate_provider_environment_manifest(symlink) == ()
    symlink["entries"][1]["size"] = 6
    assert api.validate_provider_environment_manifest(symlink)


@pytest.mark.parametrize(
    "link_text",
    [
        "missing",
        "/absolute",
        "../escape",
        "alpha",
    ],
)
def test_manifest_rejects_unsafe_symlink_row_graph(link_text: str) -> None:
    api = _api()
    document = _base_manifest()
    document["entries"][1] = {
        "path": "alpha",
        "kind": "symlink",
        "mode": 0o777,
        "uid": 0,
        "gid": 0,
        "atime_ns": 0,
        "mtime_ns": 0,
        "link_text": link_text,
    }

    issues = api.validate_provider_environment_manifest(document)

    assert {issue.code for issue in issues} == {
        "provider_isolation_environment_invalid"
    }
    assert "$.entries[1].link_text" in {issue.path for issue in issues}
    _assert_environment_error(
        lambda: api.load_provider_environment_manifest(document),
        path="$.entries[1].link_text",
    )


def test_independent_manifest_golden_digest_and_canonical_bytes() -> None:
    manifest = _api().load_provider_environment_manifest(_base_manifest())

    assert manifest.canonical_json == GOLDEN_MANIFEST_BYTES
    assert manifest.digest == GOLDEN_MANIFEST_DIGEST
    assert manifest.digest == f"sha256:{sha256(GOLDEN_MANIFEST_BYTES).hexdigest()}"


def test_manifest_digest_rejects_task_1_whole_policy_cross_fill() -> None:
    api = _api()
    task_1_policy_digest = (
        "sha256:137412daa8490755250cde3614a865ba74ccbfb1e6a700f287913e2ac1328993"
    )
    _assert_environment_error(
        lambda: api.load_provider_environment_manifest(
            _base_manifest(), expected_digest=task_1_policy_digest
        ),
        code="provider_isolation_environment_mismatch",
        path="$.digest",
    )


def test_manifest_loader_classifies_malformed_expected_digest_as_invalid() -> None:
    _assert_environment_error(
        lambda: _api().load_provider_environment_manifest(
            _base_manifest(),
            expected_digest="not-a-canonical-digest",
        ),
        path="$.digest",
    )


def test_manifest_rows_sort_by_strict_nfc_utf8_bytes() -> None:
    api = _api()
    document = _base_manifest()
    document["entries"].extend(
        [
            {
                "path": "é",
                "kind": "directory",
                "mode": 0o555,
                "uid": 0,
                "gid": 0,
                "atime_ns": 0,
                "mtime_ns": 0,
            },
            {
                "path": "z",
                "kind": "directory",
                "mode": 0o555,
                "uid": 0,
                "gid": 0,
                "atime_ns": 0,
                "mtime_ns": 0,
            },
        ]
    )
    loaded = api.load_provider_environment_manifest(document)
    assert [entry.path for entry in loaded.entries] == [".", "alpha", "z", "é"]


def test_manifest_rejects_ancestor_kind_conflict() -> None:
    api = _api()
    document = _base_manifest()
    document["entries"].append(
        {
            "path": "alpha/child",
            "kind": "regular_file",
            "mode": 0o444,
            "uid": 0,
            "gid": 0,
            "atime_ns": 0,
            "mtime_ns": 0,
            "size": 0,
            "digest": f"sha256:{sha256(b'').hexdigest()}",
        }
    )
    assert "$.entries[2].path" in {
        issue.path for issue in api.validate_provider_environment_manifest(document)
    }


def test_source_modes_and_timestamps_normalize_to_destination_identity(
    tmp_path: Path,
) -> None:
    api = _api()
    first = _make_source(tmp_path, name="first")
    second = _make_source(tmp_path, name="second")
    (first / "share" / "payload.txt").chmod(0o644)
    (second / "share" / "payload.txt").chmod(0o444)
    os.utime(first / "share" / "payload.txt", ns=(1_000_000, 2_000_000))
    os.utime(second / "share" / "payload.txt", ns=(9_000_000, 8_000_000))

    left = api.build_provider_environment_manifest(first, PROVIDER_PREFIX)
    right = api.build_provider_environment_manifest(second, PROVIDER_PREFIX)

    assert left.digest == right.digest
    assert _entry(left, "share/payload.txt").mode == 0o444
    assert _entry(left, "share/payload.txt").atime_ns == 0
    assert _entry(left, "share/payload.txt").mtime_ns == 0
    assert _entry(left, "share/payload-link").mode == 0o777


def test_builder_records_exact_size_digest_link_text_and_all_normalized_metadata(
    tmp_path: Path,
) -> None:
    api = _api()
    root = _make_source(tmp_path)

    manifest = api.build_provider_environment_manifest(root, PROVIDER_PREFIX)

    payload = _entry(manifest, "share/payload.txt")
    assert payload.size == len(b"payload")
    assert payload.digest == f"sha256:{sha256(b'payload').hexdigest()}"
    assert _entry(manifest, "share/payload-link").link_text == "payload.txt"
    assert _entry(manifest, ".").kind == "directory"
    assert all(
        (entry.uid, entry.gid, entry.atime_ns, entry.mtime_ns) == (0, 0, 0, 0)
        for entry in manifest.entries
    )
    assert all(
        entry.mode == 0o777
        if entry.kind == "symlink"
        else entry.mode & 0o222 == 0
        for entry in manifest.entries
    )


def test_builder_identity_is_independent_of_source_enumeration_order(
    tmp_path: Path, monkeypatch
) -> None:
    api = _api()
    root = _make_source(tmp_path)
    for name in ("alpha", "zeta", "é"):
        path = root / "share" / name
        path.write_bytes(name.encode("utf-8"))
        path.chmod(0o644)
    expected = api.build_provider_environment_manifest(root, PROVIDER_PREFIX)
    real_listdir = os.listdir

    def reverse_listdir(path):
        return list(reversed(real_listdir(path)))

    monkeypatch.setattr(os, "listdir", reverse_listdir)
    reordered = api.build_provider_environment_manifest(root, PROVIDER_PREFIX)

    assert reordered.canonical_json == expected.canonical_json
    assert reordered.digest == expected.digest
    assert [entry.path for entry in reordered.entries] == sorted(
        (entry.path for entry in reordered.entries),
        key=lambda value: value.encode("utf-8"),
    )


def test_source_read_or_execute_mode_differences_change_identity(
    tmp_path: Path,
) -> None:
    api = _api()
    first = _make_source(tmp_path, name="first")
    second = _make_source(tmp_path, name="second")
    (first / "share" / "payload.txt").chmod(0o600)
    (second / "share" / "payload.txt").chmod(0o755)

    left = api.build_provider_environment_manifest(first, PROVIDER_PREFIX)
    right = api.build_provider_environment_manifest(second, PROVIDER_PREFIX)

    assert _entry(left, "share/payload.txt").mode == 0o400
    assert _entry(right, "share/payload.txt").mode == 0o555
    assert left.digest != right.digest


def test_root_is_a_full_admission_and_identity_row(tmp_path: Path) -> None:
    api = _api()
    root = _make_source(tmp_path)
    root.chmod(0o700)
    manifest = api.build_provider_environment_manifest(root, PROVIDER_PREFIX)
    root_entry = _entry(manifest, ".")
    assert root_entry.kind == "directory"
    assert root_entry.mode == 0o500
    assert (root_entry.uid, root_entry.gid) == (0, 0)

    root.chmod(0o720)
    _assert_environment_error(
        lambda: api.build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[0].mode",
    )


def test_source_requires_controller_owner_for_root_and_descendants(
    tmp_path: Path, monkeypatch
) -> None:
    api = _api()
    root = _make_source(tmp_path)
    real_lstat = api._lstat_at

    def foreign_owner(dir_fd, name):
        value = real_lstat(dir_fd, name)
        if name == "payload.txt":
            values = list(value)
            values[4] = value.st_uid + 1
            return os.stat_result(values)
        return value

    monkeypatch.setattr(api, "_lstat_at", foreign_owner)
    _assert_environment_error(
        lambda: api.build_provider_environment_manifest(root, PROVIDER_PREFIX)
    )


def test_source_rejects_root_owner_mutation(tmp_path: Path, monkeypatch) -> None:
    api = _api()
    root = _make_source(tmp_path)
    real_lstat_root = api._lstat_root
    calls = 0

    def changed_owner(path):
        nonlocal calls
        value = real_lstat_root(path)
        calls += 1
        if calls < 2:
            return value
        values = list(value)
        values[4] = value.st_uid + 1
        return os.stat_result(values)

    monkeypatch.setattr(api, "_lstat_root", changed_owner)
    _assert_environment_error(
        lambda: api.build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[0].owner",
    )


def test_source_rejects_group_or_world_writable_descendant(tmp_path: Path) -> None:
    root = _make_source(tmp_path)
    path = root / "share" / "payload.txt"
    path.chmod(0o664)
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[share/payload.txt].mode",
    )


def test_source_rejects_reserved_launch_shim_collision(tmp_path: Path) -> None:
    root = _make_source(tmp_path)
    shim = root / PROVIDER_PREFIX.lstrip("/") / "libexec" / "provider-launch-shim-v1.py"
    shim.parent.mkdir()
    shim.parent.chmod(0o755)
    shim.write_text("collision", encoding="utf-8")
    shim.chmod(0o644)
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[opt/orchestrator-provider/libexec/provider-launch-shim-v1.py]",
    )


@pytest.mark.parametrize("kind", ["fifo", "socket"])
def test_source_rejects_special_files(tmp_path: Path, kind: str) -> None:
    root = _make_source(tmp_path)
    special = root / kind
    if kind == "fifo":
        os.mkfifo(special)
    else:
        import socket

        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(special))
    try:
        _assert_environment_error(
            lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX)
        )
    finally:
        if kind == "socket":
            sock.close()


def test_source_regular_open_is_nonblocking_across_lstat_to_fifo_exchange(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    root = _make_source(tmp_path)
    real_open_noatime = api._open_noatime
    exchanged = False

    def exchange_before_open(path, flags, *, dir_fd=None):
        nonlocal exchanged
        if path == "payload.txt" and dir_fd is not None and not exchanged:
            assert flags & os.O_NONBLOCK
            os.unlink(path, dir_fd=dir_fd)
            os.mkfifo(path, 0o600, dir_fd=dir_fd)
            exchanged = True
        return real_open_noatime(path, flags, dir_fd=dir_fd)

    monkeypatch.setattr(api, "_open_noatime", exchange_before_open)

    _assert_environment_error(
        lambda: api.build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[share/payload.txt].identity",
    )
    assert exchanged


def test_source_rejects_every_xattr_including_on_root(tmp_path: Path) -> None:
    root = _make_source(tmp_path)
    try:
        os.setxattr(root, "user.task1a", b"value")
    except OSError as exc:
        pytest.fail(f"test filesystem must support user xattrs: {exc}")
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[0].xattrs",
    )


@pytest.mark.parametrize("relpath", ["share", "share/payload.txt"])
def test_source_rejects_descendant_directory_and_file_xattrs(
    tmp_path: Path, relpath: str
) -> None:
    root = _make_source(tmp_path)
    path = root / relpath
    try:
        os.setxattr(path, "user.task1a", b"value", follow_symlinks=False)
    except OSError as exc:
        pytest.fail(f"test filesystem must support user xattrs: {exc}")
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path=f"$.entries[{relpath}].xattrs",
    )


def test_source_rejects_device_mode_path(tmp_path: Path, monkeypatch) -> None:
    api = _api()
    root = _make_source(tmp_path)
    real_lstat = api._lstat_at

    def device_mode(dir_fd, name):
        value = real_lstat(dir_fd, name)
        if name == "payload.txt":
            values = list(value)
            values[0] = stat.S_IFCHR | 0o600
            return os.stat_result(values)
        return value

    monkeypatch.setattr(api, "_lstat_at", device_mode)
    _assert_environment_error(
        lambda: api.build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[share/payload.txt].kind",
    )


def test_source_rejects_unaccounted_external_hardlink(tmp_path: Path) -> None:
    root = _make_source(tmp_path)
    os.link(root / "share" / "payload.txt", tmp_path / "external-link")
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[share/payload.txt].hardlinks",
    )


def test_source_accepts_fully_accounted_hardlinks(tmp_path: Path) -> None:
    root = _make_source(tmp_path)
    os.link(root / "share" / "payload.txt", root / "share" / "second-name")
    manifest = _api().build_provider_environment_manifest(root, PROVIDER_PREFIX)
    assert _entry(manifest, "share/payload.txt").digest == _entry(
        manifest, "share/second-name"
    ).digest


@pytest.mark.parametrize(
    "target",
    ["/etc/passwd", "../../outside", "missing", "loop"],
)
def test_source_rejects_absolute_escaping_broken_or_cyclic_links(
    tmp_path: Path, target: str
) -> None:
    root = _make_source(tmp_path)
    link = root / "bad-link"
    link.symlink_to(target)
    if target == "loop":
        # The lexical target exists but resolves back through itself.
        pass
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[bad-link].link_text",
    )


def test_source_rejects_non_utf8_and_non_nfc_names(tmp_path: Path) -> None:
    root = _make_source(tmp_path)
    undecodable = os.fsencode(root) + b"/bad-\xff"
    fd = os.open(undecodable, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX)
    )

    os.unlink(undecodable)
    decomposed = unicodedata.normalize("NFD", "café")
    (root / decomposed).write_bytes(b"x")
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX)
    )


def test_source_rejects_non_utf8_and_non_nfc_link_text(tmp_path: Path) -> None:
    root = _make_source(tmp_path)
    os.symlink(b"bad-\xff", os.fsencode(root) + b"/bad-target")
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX)
    )

    os.unlink(os.fsencode(root) + b"/bad-target")
    (root / "bad-target").symlink_to(unicodedata.normalize("NFD", "café"))
    _assert_environment_error(
        lambda: _api().build_provider_environment_manifest(root, PROVIDER_PREFIX)
    )


def test_mount_identity_uses_statx_and_rejects_same_device_crossing(
    tmp_path: Path, monkeypatch
) -> None:
    api = _api()
    root = _make_source(tmp_path)
    real_mount_id = api._statx_mount_id

    def changed_mount_id(fd: int, name: str | None = None) -> int:
        value = real_mount_id(fd, name)
        return value + 1 if name == "share" else value

    monkeypatch.setattr(api, "_statx_mount_id", changed_mount_id)
    _assert_environment_error(
        lambda: api.build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path="$.entries[share].mount_id",
    )


def test_mount_identity_unavailable_fails_closed(tmp_path: Path, monkeypatch) -> None:
    api = _api()
    root = _make_source(tmp_path)
    monkeypatch.setattr(
        api,
        "_statx_mount_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            api.MountIdentityUnavailable("no descriptor-bound mount identity")
        ),
    )
    _assert_environment_error(
        lambda: api.build_provider_environment_manifest(root, PROVIDER_PREFIX)
    )


@pytest.mark.parametrize("relpath", ["share", "share/payload.txt"])
def test_source_rejects_mount_exchange_between_lookup_and_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relpath: str,
) -> None:
    api = _api()
    root = _make_source(tmp_path)
    target = os.stat(root / relpath, follow_symlinks=False)
    real_mount_id = api._statx_mount_id

    def exchanged_open_mount_id(fd: int, name: str | None = None) -> int:
        mount_id = real_mount_id(fd, name)
        opened = os.fstat(fd)
        if (
            name is None
            and opened.st_dev == target.st_dev
            and opened.st_ino == target.st_ino
        ):
            return mount_id + 1
        return mount_id

    monkeypatch.setattr(api, "_statx_mount_id", exchanged_open_mount_id)

    _assert_environment_error(
        lambda: api.build_provider_environment_manifest(root, PROVIDER_PREFIX),
        path=f"$.entries[{relpath}].mount_id",
    )


@pytest.mark.parametrize(
    ("unavailable_at", "expected_path"),
    [
        ("root", "$.entries[0].mount_id"),
        ("entry", "$.entries[share].mount_id"),
    ],
)
def test_snapshot_copy_mount_identity_unavailable_has_stable_invalid_diagnostic(
    tmp_path: Path,
    monkeypatch,
    unavailable_at: str,
    expected_path: str,
) -> None:
    api = _api()
    root = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(root, PROVIDER_PREFIX)
    real_mount_id = api._statx_mount_id
    root_identity = os.stat(root, follow_symlinks=False)
    observed = 0

    def unavailable_during_copy(fd: int, name: str | None = None) -> int:
        nonlocal observed
        opened = os.fstat(fd)
        selected = (
            name is None
            and opened.st_dev == root_identity.st_dev
            and opened.st_ino == root_identity.st_ino
            if unavailable_at == "root"
            else name == "share"
        )
        if selected:
            observed += 1
            if observed == 2:
                raise api.MountIdentityUnavailable(
                    "copy-phase descriptor-bound mount identity unavailable"
                )
        return real_mount_id(fd, name)

    monkeypatch.setattr(api, "_statx_mount_id", unavailable_during_copy)

    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            root,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=prospective.digest,
        ),
        path=expected_path,
    )
    assert not tuple(
        (run_root / "provider_environment_snapshots").glob(".staging-*")
    )


def test_source_metadata_swap_during_walk_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    api = _api()
    root = _make_source(tmp_path)
    original = api._hash_regular_file
    path = root / "share" / "payload.txt"

    def mutate(fd: int) -> tuple[int, str]:
        result = original(fd)
        path.write_bytes(b"changed")
        path.chmod(0o644)
        return result

    monkeypatch.setattr(api, "_hash_regular_file", mutate)
    _assert_environment_error(
        lambda: api.build_provider_environment_manifest(root, PROVIDER_PREFIX)
    )


@pytest.mark.parametrize(
    "other_name",
    [
        "candidate",
        "workflow",
        "extern",
        "controller",
        "scratch",
        "control",
        "evaluator",
        "peer",
        "parent",
    ],
)
def test_environment_source_overlap_denial_is_symmetric(
    tmp_path: Path, other_name: str
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    inside = source / other_name
    inside.mkdir()
    _assert_environment_error(
        lambda: api.require_disjoint_environment_authorities(source, [inside])
    )
    outer = tmp_path
    _assert_environment_error(
        lambda: api.require_disjoint_environment_authorities(source, [outer])
    )


def test_snapshot_publishes_only_at_exact_digest_authority(tmp_path: Path) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)

    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=prospective.digest,
    )
    try:
        expected = (
            run_root
            / "provider_environment_snapshots"
            / prospective.digest
            / "rootfs"
        )
        assert snapshot.rootfs_path == expected
        assert snapshot.root_fd >= 0
        assert snapshot.digest == prospective.digest
        assert snapshot.manifest_path == expected.parent / "manifest.json"
        assert not tuple(expected.parent.parent.glob(".staging-*"))
    finally:
        snapshot.close()


def test_basic_snapshots_are_identical_across_source_path_write_bits_and_times(
    tmp_path: Path,
) -> None:
    api = _api()
    first = _make_source(tmp_path, name="first")
    second = _make_source(tmp_path, name="second")
    first.chmod(0o700)
    second.chmod(0o500)
    (first / "share" / "payload.txt").chmod(0o644)
    (second / "share" / "payload.txt").chmod(0o444)
    os.utime(first, ns=(1_000_000, 2_000_000))
    os.utime(second, ns=(9_000_000, 8_000_000))
    os.utime(first / "share" / "payload.txt", ns=(3_000_000, 4_000_000))
    os.utime(second / "share" / "payload.txt", ns=(7_000_000, 6_000_000))
    expected = api.build_provider_environment_manifest(first, PROVIDER_PREFIX)
    assert (
        api.build_provider_environment_manifest(second, PROVIDER_PREFIX).digest
        == expected.digest
    )
    first_run = tmp_path / "first-run"
    second_run = tmp_path / "second-run"
    first_run.mkdir(mode=0o700)
    second_run.mkdir(mode=0o700)

    left = api.assemble_provider_environment_snapshot(
        first, PROVIDER_PREFIX, first_run, expected_digest=expected.digest
    )
    right = api.assemble_provider_environment_snapshot(
        second, PROVIDER_PREFIX, second_run, expected_digest=expected.digest
    )
    try:
        assert left.manifest_path.read_bytes() == right.manifest_path.read_bytes()
        for entry in expected.entries:
            if entry.kind == "directory":
                continue
            left_path = left.rootfs_path / ("" if entry.path == "." else entry.path)
            right_path = right.rootfs_path / ("" if entry.path == "." else entry.path)
            if entry.kind == "regular_file":
                assert left_path.read_bytes() == right_path.read_bytes()
            else:
                assert os.readlink(left_path) == os.readlink(right_path)
    finally:
        left.close()
        right.close()


def test_basic_snapshot_physically_injects_manifest_bound_launch_shim(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    shim_relpath = (
        "opt/orchestrator-provider/libexec/provider-launch-shim-v1.py"
    )
    shim_entry = _entry(manifest, shim_relpath)
    packaged = (
        resources.files("orchestrator.providers")
        .joinpath("provider_launch_shim.py")
        .read_bytes()
    )

    snapshot = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=manifest.digest
    )
    try:
        shim = snapshot.rootfs_path / shim_relpath
        observed = os.stat(shim, follow_symlinks=False)
        assert observed.st_atime_ns == observed.st_mtime_ns == 0
        assert stat.S_IMODE(observed.st_mode) == 0o444
        assert shim.read_bytes() == packaged
        assert shim_entry.size == len(packaged)
        assert shim_entry.digest == f"sha256:{sha256(packaged).hexdigest()}"
    finally:
        snapshot.close()


def test_basic_snapshot_finalizes_every_row_to_exact_manifest_metadata(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    os.link(source / "share" / "payload.txt", source / "share" / "alias")
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)

    snapshot = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=manifest.digest
    )
    try:
        inodes: list[int] = []
        for entry in manifest.entries:
            path = (
                snapshot.rootfs_path
                if entry.path == "."
                else snapshot.rootfs_path / entry.path
            )
            observed = os.stat(path, follow_symlinks=False)
            assert stat.S_IMODE(observed.st_mode) == entry.mode
            assert observed.st_uid == os.geteuid()
            assert observed.st_gid == os.getegid()
            assert observed.st_atime_ns == observed.st_mtime_ns == 0
            if entry.kind == "regular_file":
                assert observed.st_nlink == 1
                inodes.append(observed.st_ino)
        assert len(inodes) == len(set(inodes))
        assert json.loads(snapshot.manifest_path.read_bytes()) == manifest.to_dict()
    finally:
        snapshot.close()


def test_snapshot_finalization_sets_noatime_inode_flag_on_every_file_and_directory(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)

    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    try:
        missing = []
        for entry in manifest.entries:
            if entry.kind == "symlink":
                continue
            path = (
                snapshot.rootfs_path
                if entry.path == "."
                else snapshot.rootfs_path / entry.path
            )
            if not _read_linux_inode_flags(path) & _FS_NOATIME_FL:
                missing.append(entry.path)
        assert missing == []
    finally:
        snapshot.close()


def test_snapshot_manifest_noatime_flag_makes_open_fallback_read_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()
    real_open_noatime = api._open_noatime
    manifest_fallback_opens = 0

    def force_manifest_open_fallback(path, flags, *, dir_fd=None):
        nonlocal manifest_fallback_opens
        if path == "manifest.json":
            manifest_fallback_opens += 1
            return os.open(path, flags, dir_fd=dir_fd)
        return real_open_noatime(path, flags, dir_fd=dir_fd)

    monkeypatch.setattr(api, "_open_noatime", force_manifest_open_fallback)
    loaded = api.load_provider_environment_snapshot(
        run_root,
        expected_digest=manifest.digest,
    )
    loaded.close()

    observed = os.stat(snapshot.manifest_path, follow_symlinks=False)
    assert manifest_fallback_opens == 1
    assert _read_linux_inode_flags(snapshot.manifest_path) & _FS_NOATIME_FL
    assert observed.st_atime_ns == observed.st_mtime_ns == 0


def test_snapshot_assembly_fails_closed_when_manifest_noatime_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_set_inode_flags = api._set_inode_flags

    def reject_manifest_flag_write(fd: int, flags: int) -> None:
        if os.readlink(f"/proc/self/fd/{fd}").endswith("/manifest.json"):
            raise OSError(errno.ENOTTY, "injected manifest inode-flag failure")
        real_set_inode_flags(fd, flags)

    monkeypatch.setattr(api, "_set_inode_flags", reject_manifest_flag_write)
    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
        ),
        code="provider_isolation_backend_unavailable",
        path="$.snapshot_manifest.inode_flags",
    )
    authority = run_root / "provider_environment_snapshots"
    assert not (authority / manifest.digest).exists()
    assert not tuple(authority.glob(".staging-*"))


def test_snapshot_load_rejects_manifest_missing_noatime_before_read(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()
    flags = _read_linux_inode_flags(snapshot.manifest_path)
    _write_linux_inode_flags(
        snapshot.manifest_path,
        flags & ~_FS_NOATIME_FL,
    )
    assert os.stat(
        snapshot.manifest_path,
        follow_symlinks=False,
    ).st_atime_ns == 0

    _assert_environment_error(
        lambda: api.load_provider_environment_snapshot(
            run_root,
            expected_digest=manifest.digest,
        ),
        path="$.snapshot_manifest.inode_flags",
    )


@pytest.mark.parametrize("tamper", ["clear_noatime", "change_atime"])
def test_snapshot_load_rechecks_manifest_protection_after_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()
    real_read_all = api._read_all

    def tamper_after_read(fd: int) -> bytes:
        content = real_read_all(fd)
        if tamper == "clear_noatime":
            flags = api._get_inode_flags(fd)
            api._set_inode_flags(fd, flags & ~_FS_NOATIME_FL)
        else:
            os.utime(fd, ns=(1, 0))
        return content

    monkeypatch.setattr(api, "_read_all", tamper_after_read)
    _assert_environment_error(
        lambda: api.load_provider_environment_snapshot(
            run_root,
            expected_digest=manifest.digest,
        ),
        path=(
            "$.snapshot_manifest.inode_flags"
            if tamper == "clear_noatime"
            else "$.snapshot_manifest"
        ),
    )


@pytest.mark.parametrize("entry_path", [".", "share", "share/payload.txt"])
def test_snapshot_verification_rejects_cleared_noatime_inode_flag(
    tmp_path: Path,
    entry_path: str,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()
    path = (
        snapshot.rootfs_path
        if entry_path == "."
        else snapshot.rootfs_path / entry_path
    )
    flags = _read_linux_inode_flags(path)
    _write_linux_inode_flags(path, flags & ~_FS_NOATIME_FL)

    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            snapshot.rootfs_path,
            expected_digest=manifest.digest,
        ),
        code="provider_isolation_environment_invalid",
    )


@pytest.mark.parametrize("failure_errno", [errno.EPERM, errno.ENOTTY])
def test_snapshot_assembly_fails_closed_when_noatime_flag_cannot_be_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_errno: int,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)

    def reject_flag_write(_fd: int, _flags: int) -> None:
        raise OSError(failure_errno, "injected inode-flag failure")

    monkeypatch.setattr(api, "_set_inode_flags", reject_flag_write, raising=False)
    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
        ),
        code="provider_isolation_backend_unavailable",
    )
    authority = run_root / "provider_environment_snapshots"
    assert not (authority / manifest.digest).exists()
    assert not tuple(authority.glob(".staging-*"))


def test_snapshot_assembly_fails_closed_when_noatime_flag_write_is_a_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)

    monkeypatch.setattr(
        api,
        "_set_inode_flags",
        lambda _fd, _flags: None,
        raising=False,
    )
    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
        ),
        code="provider_isolation_backend_unavailable",
    )
    authority = run_root / "provider_environment_snapshots"
    assert not (authority / manifest.digest).exists()
    assert not tuple(authority.glob(".staging-*"))


def test_snapshot_assembly_rechecks_noatime_flag_after_timestamp_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_utime = os.utime

    def clear_noatime_after_utime(path, *args, **kwargs):
        result = real_utime(path, *args, **kwargs)
        if isinstance(path, int):
            flags = api._get_inode_flags(path)
            if flags & _FS_NOATIME_FL:
                api._set_inode_flags(path, flags & ~_FS_NOATIME_FL)
        return result

    monkeypatch.setattr(api.os, "utime", clear_noatime_after_utime)
    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
        ),
        code="provider_isolation_backend_unavailable",
    )
    authority = run_root / "provider_environment_snapshots"
    assert not (authority / manifest.digest).exists()
    assert not tuple(authority.glob(".staging-*"))


def test_snapshot_assembly_rejects_preexisting_flag_loss_after_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_set_inode_flags = api._set_inode_flags

    def drop_nodump_after_set(fd: int, flags: int) -> None:
        real_set_inode_flags(fd, flags)
        if flags & _FS_NODUMP_FL and flags & _FS_NOATIME_FL:
            real_set_inode_flags(fd, flags & ~_FS_NODUMP_FL)

    def seed_nodump(stage: str, rootfs: Path) -> None:
        if stage != "normalization":
            return
        payload = rootfs / "share" / "payload.txt"
        flags = _read_linux_inode_flags(payload)
        _write_linux_inode_flags(payload, flags | _FS_NODUMP_FL)

    monkeypatch.setattr(api, "_set_inode_flags", drop_nodump_after_set)
    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
            fault_hook=seed_nodump,
        ),
        code="provider_isolation_backend_unavailable",
    )
    authority = run_root / "provider_environment_snapshots"
    assert not (authority / manifest.digest).exists()
    assert not tuple(authority.glob(".staging-*"))


def test_snapshot_assembly_rejects_preexisting_flag_loss_during_utime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_utime = os.utime

    def drop_nodump_after_utime(path, *args, **kwargs):
        result = real_utime(path, *args, **kwargs)
        if isinstance(path, int):
            flags = api._get_inode_flags(path)
            if flags & _FS_NODUMP_FL and flags & _FS_NOATIME_FL:
                api._set_inode_flags(path, flags & ~_FS_NODUMP_FL)
        return result

    def seed_nodump(stage: str, rootfs: Path) -> None:
        if stage != "normalization":
            return
        payload = rootfs / "share" / "payload.txt"
        flags = _read_linux_inode_flags(payload)
        _write_linux_inode_flags(payload, flags | _FS_NODUMP_FL)

    monkeypatch.setattr(api.os, "utime", drop_nodump_after_utime)
    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
            fault_hook=seed_nodump,
        ),
        code="provider_isolation_backend_unavailable",
    )
    authority = run_root / "provider_environment_snapshots"
    assert not (authority / manifest.digest).exists()
    assert not tuple(authority.glob(".staging-*"))


def test_snapshot_finalization_preserves_preexisting_inode_flags(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)

    def seed_nodump(stage: str, rootfs: Path) -> None:
        if stage != "normalization":
            return
        payload = rootfs / "share" / "payload.txt"
        flags = _read_linux_inode_flags(payload)
        _write_linux_inode_flags(payload, flags | _FS_NODUMP_FL)

    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
        fault_hook=seed_nodump,
    )
    try:
        flags = _read_linux_inode_flags(
            snapshot.rootfs_path / "share" / "payload.txt"
        )
        assert flags & (_FS_NODUMP_FL | _FS_NOATIME_FL) == (
            _FS_NODUMP_FL | _FS_NOATIME_FL
        )
    finally:
        snapshot.close()


def test_strict_launch_snapshot_load_rejects_symlink_before_tree_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()

    generic = api.load_provider_environment_snapshot(
        run_root,
        expected_digest=manifest.digest,
    )
    generic.close()

    strict_loader = getattr(
        api,
        "load_provider_environment_snapshot_for_launch",
        None,
    )
    assert strict_loader is not None

    def forbidden_tree_scan(*_args, **_kwargs):
        raise AssertionError("strict launch admission scanned a symlink-bearing tree")

    monkeypatch.setattr(
        api,
        "_build_provider_environment_manifest_from_fd",
        forbidden_tree_scan,
    )
    _assert_environment_error(
        lambda: strict_loader(
            run_root,
            expected_digest=manifest.digest,
        ),
        path="$.entries[share/payload-link].kind",
    )


def test_snapshot_rejects_exact_expected_digest_mismatch(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    _assert_environment_error(
        lambda: _api().assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=f"sha256:{'0' * 64}",
        ),
        code="provider_isolation_environment_mismatch",
        path="$.digest",
    )


def test_snapshot_assembly_classifies_malformed_expected_digest_as_invalid(
    tmp_path: Path,
) -> None:
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)

    _assert_environment_error(
        lambda: _api().assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest="not-a-canonical-digest",
        ),
        path="$.digest",
    )


def test_snapshot_splits_source_hardlinks_and_fixes_metadata(tmp_path: Path) -> None:
    api = _api()
    source = _make_source(tmp_path)
    os.link(source / "share" / "payload.txt", source / "share" / "alias")
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=prospective.digest
    )
    try:
        first = snapshot.rootfs_path / "share" / "payload.txt"
        second = snapshot.rootfs_path / "share" / "alias"
        first_stat = first.stat()
        second_stat = second.stat()
        assert first_stat.st_ino != second_stat.st_ino
        assert first_stat.st_nlink == second_stat.st_nlink == 1
        assert stat.S_IMODE(first_stat.st_mode) == 0o444
        assert first_stat.st_atime_ns == first_stat.st_mtime_ns == 0
    finally:
        snapshot.close()


def test_source_mutation_after_publication_does_not_change_snapshot(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=prospective.digest
    )
    try:
        source_file = source / "share" / "payload.txt"
        source_file.chmod(0o600)
        source_file.write_bytes(b"post-publication mutation")
        assert (snapshot.rootfs_path / "share" / "payload.txt").read_bytes() == b"payload"
    finally:
        snapshot.close()


def test_snapshot_verifier_accepts_published_tree_after_source_mutation(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=prospective.digest
    )
    snapshot.close()
    source_file = source / "share" / "payload.txt"
    source_file.chmod(0o600)
    source_file.write_bytes(b"post-publication mutation")

    verified = api.verify_provider_environment_snapshot(
        snapshot.rootfs_path, expected_digest=prospective.digest
    )

    assert verified.digest == prospective.digest


def test_snapshot_verifier_and_loader_reject_malformed_expected_digest_as_invalid(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()

    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            snapshot.rootfs_path,
            expected_digest="not-a-canonical-digest",
        ),
        path="$.digest",
    )
    _assert_environment_error(
        lambda: api.load_provider_environment_snapshot(
            run_root,
            expected_digest="not-a-canonical-digest",
        ),
        path="$.digest",
    )


@pytest.mark.parametrize("special_kind", ["fifo", "socket", "device"])
def test_snapshot_manifest_special_file_open_is_nonblocking_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    special_kind: str,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()

    opened_socket = None
    opened_socket_path = None
    if special_kind == "fifo":
        snapshot.manifest_path.unlink()
        os.mkfifo(snapshot.manifest_path, 0o400)
        os.utime(snapshot.manifest_path, ns=(0, 0), follow_symlinks=False)
    elif special_kind == "socket":
        import socket

        opened_socket_path = (
            Path("/tmp")
            / f"orc-env-{os.getpid()}-{abs(hash(os.fspath(tmp_path))) & 0xFFFF:x}.sock"
        )
        opened_socket_path.unlink(missing_ok=True)
        opened_socket = socket.socket(socket.AF_UNIX)
        opened_socket.bind(str(opened_socket_path))

    observed_flags: list[int] = []
    real_open_noatime = api._open_noatime
    real_lstat_at = api._lstat_at
    device_stat = os.stat("/dev/null", follow_symlinks=False)
    socket_stat = (
        None
        if opened_socket_path is None
        else os.stat(opened_socket_path, follow_symlinks=False)
    )

    def observe_manifest_open(path, flags, *, dir_fd=None):
        if path == "manifest.json":
            observed_flags.append(flags)
            assert flags & os.O_NONBLOCK
            if special_kind == "device":
                return os.open(
                    "/dev/null",
                    os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC,
                )
            if special_kind == "socket":
                assert opened_socket_path is not None
                return os.open(opened_socket_path, flags)
        return real_open_noatime(path, flags, dir_fd=dir_fd)

    def substitute_device_stat(directory_fd: int, name: str):
        if special_kind == "device" and name == "manifest.json":
            return device_stat
        if special_kind == "socket" and name == "manifest.json":
            assert socket_stat is not None
            return socket_stat
        return real_lstat_at(directory_fd, name)

    monkeypatch.setattr(api, "_open_noatime", observe_manifest_open)
    monkeypatch.setattr(api, "_lstat_at", substitute_device_stat)

    try:
        _assert_environment_error(
            lambda: api.load_provider_environment_snapshot(
                run_root,
                expected_digest=manifest.digest,
            )
        )
    finally:
        if opened_socket is not None:
            opened_socket.close()
        if opened_socket_path is not None:
            opened_socket_path.unlink(missing_ok=True)

    assert observed_flags
    assert all(flags & os.O_NONBLOCK for flags in observed_flags)


@pytest.mark.parametrize(
    "alias_kind",
    ["dot", "repeated_separator", "trailing_separator", "parent", "relative"],
)
@pytest.mark.parametrize("subject", ["rootfs_path", "expected_run_root"])
def test_snapshot_authorities_reject_noncanonical_raw_lexical_spelling(
    tmp_path: Path,
    alias_kind: str,
    subject: str,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()

    if subject == "rootfs_path":
        rootfs_path = _lexical_authority_alias(snapshot.rootfs_path, alias_kind)
        expected_run_root = run_root
        issue_path = "$.snapshot"
    else:
        rootfs_path = snapshot.rootfs_path
        expected_run_root = _lexical_authority_alias(run_root, alias_kind)
        issue_path = "$.run_root"

    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            rootfs_path,
            expected_digest=manifest.digest,
            expected_run_root=expected_run_root,
        ),
        path=issue_path,
    )


def test_snapshot_loader_rejects_aliased_run_root_before_path_normalization(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()

    _assert_environment_error(
        lambda: api.load_provider_environment_snapshot(
            _lexical_authority_alias(run_root, "dot"),
            expected_digest=manifest.digest,
        ),
        path="$.run_root",
    )


def test_snapshot_authorities_accept_canonical_string_pathlikes(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()

    observed = api.verify_provider_environment_snapshot(
        _TestPathLike(os.fspath(snapshot.rootfs_path)),
        expected_digest=manifest.digest,
        expected_run_root=_TestPathLike(os.fspath(run_root)),
    )

    assert observed.digest == manifest.digest


@pytest.mark.parametrize("subject", ["rootfs_path", "expected_run_root"])
@pytest.mark.parametrize("wrapped", [False, True])
def test_snapshot_authorities_reject_bytes_paths_with_stable_diagnostic(
    tmp_path: Path,
    subject: str,
    wrapped: bool,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()

    selected = (
        os.fsencode(snapshot.rootfs_path)
        if subject == "rootfs_path"
        else os.fsencode(run_root)
    )
    invalid = _TestPathLike(selected) if wrapped else selected
    rootfs_path = invalid if subject == "rootfs_path" else snapshot.rootfs_path
    expected_run_root = invalid if subject == "expected_run_root" else run_root

    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            rootfs_path,
            expected_digest=manifest.digest,
            expected_run_root=expected_run_root,
        ),
        path="$.snapshot" if subject == "rootfs_path" else "$.run_root",
    )


@pytest.mark.parametrize(
    ("suffix", "message_fragment"),
    [
        (unicodedata.normalize("NFD", "é"), "Unicode NFC"),
        ("\udcff", "strict UTF-8"),
    ],
)
def test_snapshot_rootfs_raw_text_must_be_strict_utf8_nfc(
    tmp_path: Path,
    suffix: str,
    message_fragment: str,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()

    with pytest.raises(api.ProviderIsolationEnvironmentError) as exc_info:
        api.verify_provider_environment_snapshot(
            f"{snapshot.rootfs_path}{suffix}",
            expected_digest=manifest.digest,
            expected_run_root=run_root,
        )

    assert exc_info.value.code == "provider_isolation_environment_invalid"
    assert exc_info.value.issues[0].path == "$.snapshot"
    assert message_fragment in exc_info.value.issues[0].message


def test_snapshot_verification_rejects_mutation_and_path_alias(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=prospective.digest
    )
    snapshot.close()

    rootfs = snapshot.rootfs_path
    rootfs.chmod(0o700)
    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            rootfs, expected_digest=prospective.digest
        )
    )
    rootfs.chmod(_entry(prospective, ".").mode)
    os.utime(rootfs, ns=(0, 0), follow_symlinks=False)
    alias = tmp_path / "rootfs-alias"
    alias.symlink_to(rootfs)
    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            alias, expected_digest=prospective.digest
        )
    )


@pytest.mark.parametrize(
    "tamper",
    [
        "root_mode",
        "descendant_mode",
        "root_xattr",
        "descendant_xattr",
        "root_timestamp",
        "descendant_timestamp",
        "content",
        "link_text",
        "manifest",
    ],
)
def test_snapshot_verification_rejects_each_independent_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=manifest.digest
    )
    snapshot.close()
    rootfs = snapshot.rootfs_path
    payload = rootfs / "share" / "payload.txt"

    if tamper == "root_mode":
        rootfs.chmod(0o700)
    elif tamper == "descendant_mode":
        payload.chmod(0o555)
    elif tamper == "root_xattr":
        rootfs.chmod(0o700)
        os.setxattr(rootfs, "user.task1a", b"tamper")
        rootfs.chmod(_entry(manifest, ".").mode)
        os.utime(rootfs, ns=(0, 0), follow_symlinks=False)
    elif tamper == "descendant_xattr":
        payload.chmod(0o600)
        os.setxattr(payload, "user.task1a", b"tamper")
        payload.chmod(0o444)
        os.utime(payload, ns=(0, 0), follow_symlinks=False)
    elif tamper == "root_timestamp":
        os.utime(rootfs, ns=(1, 0), follow_symlinks=False)
    elif tamper == "descendant_timestamp":
        os.utime(payload, ns=(1, 0), follow_symlinks=False)
    elif tamper == "content":
        payload.chmod(0o600)
        payload.write_bytes(b"changed")
        payload.chmod(0o444)
        os.utime(payload, ns=(0, 0), follow_symlinks=False)
    elif tamper == "link_text":
        share = rootfs / "share"
        link = share / "payload-link"
        share.chmod(0o755)
        link.unlink()
        link.symlink_to("./payload.txt")
        os.utime(link, ns=(0, 0), follow_symlinks=False)
        share.chmod(0o555)
        os.utime(share, ns=(0, 0), follow_symlinks=False)
    elif tamper == "manifest":
        snapshot.manifest_path.chmod(0o600)
        snapshot.manifest_path.write_bytes(
            snapshot.manifest_path.read_bytes() + b" "
        )
        snapshot.manifest_path.chmod(0o400)

    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            rootfs,
            expected_digest=manifest.digest,
        )
    )


@pytest.mark.parametrize(
    "authority_case",
    [
        "copied_tree",
        "symlinked_parent",
        "wrong_digest",
        "wrong_state_subauthority",
        "missing_manifest",
    ],
)
def test_snapshot_verification_rejects_wrong_or_missing_authority(
    tmp_path: Path,
    authority_case: str,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=manifest.digest
    )
    snapshot.close()
    rootfs = snapshot.rootfs_path
    expected_digest = manifest.digest

    if authority_case == "copied_tree":
        copied = tmp_path / "copied"
        shutil.copytree(snapshot.authority_path, copied, symlinks=True)
        rootfs = copied / "rootfs"
    elif authority_case == "symlinked_parent":
        alias_run = tmp_path / "alias-run"
        alias_run.mkdir(mode=0o700)
        authority_link = alias_run / "provider_environment_snapshots"
        authority_link.symlink_to(snapshot.authority_path.parent, target_is_directory=True)
        rootfs = authority_link / manifest.digest / "rootfs"
    elif authority_case == "wrong_digest":
        expected_digest = f"sha256:{'0' * 64}"
    elif authority_case == "wrong_state_subauthority":
        wrong = run_root / "provider_attempts"
        wrong.mkdir(mode=0o700)
        moved = wrong / manifest.digest
        snapshot.authority_path.rename(moved)
        rootfs = moved / "rootfs"
    elif authority_case == "missing_manifest":
        snapshot.manifest_path.unlink()

    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            rootfs,
            expected_digest=expected_digest,
        ),
        code=(
            "provider_isolation_environment_mismatch"
            if authority_case == "wrong_digest"
            else "provider_isolation_environment_invalid"
        ),
    )


def test_load_snapshot_validates_existing_authority_without_source_recopy(
    tmp_path: Path, monkeypatch
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    created = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=manifest.digest
    )
    created.close()
    source_file = source / "share" / "payload.txt"
    source_file.chmod(0o600)
    source_file.write_bytes(b"later mutable source")

    def forbidden_recopy(*_args, **_kwargs):
        raise AssertionError("resume consulted the mutable source")

    monkeypatch.setattr(api, "build_provider_environment_manifest", forbidden_recopy)
    loaded = api.load_provider_environment_snapshot(
        run_root,
        expected_digest=manifest.digest,
    )
    try:
        assert loaded.digest == manifest.digest
        assert loaded.rootfs_path == created.rootfs_path
        assert loaded.root_fd >= 0
    finally:
        loaded.close()


def test_snapshot_verifier_binds_optional_expected_run_root_but_keeps_legacy_call(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    expected_run = tmp_path / "expected-run"
    clone_run = tmp_path / "exact-shaped-clone-run"
    expected_run.mkdir(mode=0o700)
    clone_run.mkdir(mode=0o700)
    expected = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        expected_run,
        expected_digest=manifest.digest,
    )
    clone = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        clone_run,
        expected_digest=manifest.digest,
    )
    expected.close()
    clone.close()

    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            clone.rootfs_path,
            expected_digest=manifest.digest,
            expected_run_root=expected_run,
        )
    )
    assert (
        api.verify_provider_environment_snapshot(
            clone.rootfs_path,
            expected_digest=manifest.digest,
        ).digest
        == manifest.digest
    )


def test_loaded_snapshot_root_fd_keeps_verified_tree_after_path_replacement(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    first_run = tmp_path / "first-run"
    replacement_run = tmp_path / "replacement-run"
    first_run.mkdir(mode=0o700)
    replacement_run.mkdir(mode=0o700)
    first = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        first_run,
        expected_digest=manifest.digest,
    )
    replacement = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        replacement_run,
        expected_digest=manifest.digest,
    )
    first.close()
    replacement.close()

    loaded = api.load_provider_environment_snapshot(
        first_run,
        expected_digest=manifest.digest,
    )
    try:
        replacement_payload = replacement.rootfs_path / "share" / "payload.txt"
        replacement_payload.chmod(0o600)
        replacement_payload.write_bytes(b"replacement")
        replacement_payload.chmod(0o444)
        os.utime(replacement_payload, ns=(0, 0), follow_symlinks=False)
        saved_authority = first.authority_path.with_name(
            f"{first.authority_path.name}.verified-a"
        )
        first.authority_path.rename(saved_authority)
        replacement.authority_path.rename(first.authority_path)

        share_fd = os.open(
            "share",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=loaded.root_fd,
        )
        try:
            payload_fd = os.open(
                "payload.txt",
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=share_fd,
            )
            try:
                assert os.read(payload_fd, 64) == b"payload"
            finally:
                os.close(payload_fd)
        finally:
            os.close(share_fd)
        assert (loaded.rootfs_path / "share" / "payload.txt").read_bytes() == (
            b"replacement"
        )
    finally:
        loaded.close()


def test_snapshot_verification_scans_pinned_root_fd_without_proc_path_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()
    observed_root_fds: list[int] = []
    build_from_fd = api._build_provider_environment_manifest_from_fd
    open_noatime = api._open_noatime

    def record_fd_scan(root_fd, *args, **kwargs):
        observed_root_fds.append(root_fd)
        return build_from_fd(root_fd, *args, **kwargs)

    def reject_path_scan(*_args, **_kwargs):
        raise AssertionError("snapshot verification reopened the root by path")

    def reject_proc_bridge(path, flags, *, dir_fd=None):
        assert not os.fspath(path).startswith("/proc/self/fd/")
        return open_noatime(path, flags, dir_fd=dir_fd)

    monkeypatch.setattr(
        api,
        "_build_provider_environment_manifest_from_fd",
        record_fd_scan,
    )
    monkeypatch.setattr(api, "_build_provider_environment_manifest", reject_path_scan)
    monkeypatch.setattr(api, "_open_noatime", reject_proc_bridge)

    verified = api.verify_provider_environment_snapshot(
        snapshot.rootfs_path,
        expected_digest=manifest.digest,
        expected_run_root=run_root,
    )

    assert verified.digest == manifest.digest
    assert len(observed_root_fds) == 1


def test_snapshot_load_transfers_only_verified_root_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()
    opened: dict[str, object] = {}
    open_published = api._open_published_snapshot

    def capture_open(*args, **kwargs):
        pinned = open_published(*args, **kwargs)
        opened["fds"] = tuple(pinned._owned_fds)
        opened["root_fd"] = pinned.root_fd
        return pinned

    monkeypatch.setattr(api, "_open_published_snapshot", capture_open)
    loaded = api.load_provider_environment_snapshot(
        run_root,
        expected_digest=manifest.digest,
    )
    try:
        assert loaded.root_fd == opened["root_fd"]
        assert os.fstat(loaded.root_fd)
        for fd in opened["fds"]:
            if fd == loaded.root_fd:
                continue
            with pytest.raises(OSError):
                os.fstat(fd)
    finally:
        loaded.close()


def test_snapshot_load_failure_closes_every_pinned_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()
    snapshot.manifest_path.chmod(0o600)
    snapshot.manifest_path.write_bytes(snapshot.manifest_path.read_bytes() + b" ")
    snapshot.manifest_path.chmod(0o400)
    observed_fds: list[int] = []
    open_published = api._open_published_snapshot

    def capture_open(*args, **kwargs):
        pinned = open_published(*args, **kwargs)
        observed_fds.extend(pinned._owned_fds)
        return pinned

    monkeypatch.setattr(api, "_open_published_snapshot", capture_open)

    _assert_environment_error(
        lambda: api.load_provider_environment_snapshot(
            run_root,
            expected_digest=manifest.digest,
        )
    )
    assert observed_fds
    for fd in observed_fds:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize("subject", ["rootfs", "manifest"])
@pytest.mark.parametrize("pinned_a_is_valid", [False, True])
def test_pinned_snapshot_verification_uses_opened_a_across_subject_aba(
    tmp_path: Path,
    subject: str,
    pinned_a_is_valid: bool,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    run_a.mkdir(mode=0o700)
    run_b.mkdir(mode=0o700)
    snapshot_a = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_a,
        expected_digest=manifest.digest,
    )
    snapshot_b = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_b,
        expected_digest=manifest.digest,
    )
    snapshot_a.close()
    snapshot_b.close()

    invalid = snapshot_b if pinned_a_is_valid else snapshot_a
    if subject == "rootfs":
        payload = invalid.rootfs_path / "share" / "payload.txt"
        payload.chmod(0o600)
        payload.write_bytes(b"tampered")
        payload.chmod(0o444)
        os.utime(payload, ns=(0, 0), follow_symlinks=False)
        path_a = snapshot_a.rootfs_path
        path_b = snapshot_b.rootfs_path
        staged_b = snapshot_a.authority_path / "rootfs-b"
        path_b.chmod(0o755)
        path_b.rename(staged_b)
        staged_b.chmod(_entry(manifest, ".").mode)
        os.utime(staged_b, ns=(0, 0), follow_symlinks=False)
        path_b = staged_b
    else:
        invalid.manifest_path.chmod(0o600)
        invalid.manifest_path.write_bytes(
            invalid.manifest_path.read_bytes() + b" "
        )
        invalid.manifest_path.chmod(0o400)
        os.utime(invalid.manifest_path, ns=(0, 0), follow_symlinks=False)
        path_a = snapshot_a.manifest_path
        path_b = snapshot_b.manifest_path

    pinned = api._open_published_snapshot(
        run_a,
        manifest.digest,
        supplied_rootfs_path=snapshot_a.rootfs_path,
    )
    held_a = path_a.with_name(f"{path_a.name}.held-a")
    exchanged = False

    def exchange() -> None:
        nonlocal exchanged
        path_a.rename(held_a)
        path_b.rename(path_a)
        exchanged = True

    def restore() -> None:
        nonlocal exchanged
        path_a.rename(path_b)
        held_a.rename(path_a)
        exchanged = False

    restore_stage = (
        "after_tree_scan" if subject == "rootfs" else "after_manifest_read"
    )

    def verification_hook(stage: str, _pinned) -> None:
        if stage == "after_pinned_open":
            exchange()
        elif stage == restore_stage:
            restore()

    try:
        if pinned_a_is_valid:
            verified = api._verify_pinned_snapshot(
                pinned,
                expected_digest=manifest.digest,
                verification_hook=verification_hook,
            )
            assert verified.digest == manifest.digest
        else:
            _assert_environment_error(
                lambda: api._verify_pinned_snapshot(
                    pinned,
                    expected_digest=manifest.digest,
                    verification_hook=verification_hook,
                )
            )
    finally:
        if exchanged:
            restore()
        pinned.close()


@pytest.mark.parametrize("restore_before_revalidation", [True, False])
def test_pinned_snapshot_run_root_exchange_is_anchored_and_revalidated(
    tmp_path: Path,
    restore_before_revalidation: bool,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    run_a.mkdir(mode=0o700)
    run_b.mkdir(mode=0o700)
    snapshot_a = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_a,
        expected_digest=manifest.digest,
    )
    snapshot_b = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_b,
        expected_digest=manifest.digest,
    )
    snapshot_a.close()
    snapshot_b.close()
    pinned = api._open_published_snapshot(
        run_a,
        manifest.digest,
        supplied_rootfs_path=snapshot_a.rootfs_path,
    )
    held_a = tmp_path / "run-a.held-a"
    exchanged = False

    def exchange() -> None:
        nonlocal exchanged
        run_a.rename(held_a)
        run_b.rename(run_a)
        exchanged = True

    def restore() -> None:
        nonlocal exchanged
        run_a.rename(run_b)
        held_a.rename(run_a)
        exchanged = False

    def verification_hook(stage: str, _pinned) -> None:
        if stage == "after_pinned_open":
            exchange()
        elif stage == "before_edge_revalidation" and restore_before_revalidation:
            restore()

    try:
        if restore_before_revalidation:
            verified = api._verify_pinned_snapshot(
                pinned,
                expected_digest=manifest.digest,
                verification_hook=verification_hook,
            )
            assert verified.digest == manifest.digest
        else:
            _assert_environment_error(
                lambda: api._verify_pinned_snapshot(
                    pinned,
                    expected_digest=manifest.digest,
                    verification_hook=verification_hook,
                )
            )
    finally:
        if exchanged:
            restore()
        pinned.close()


def test_load_snapshot_rejects_missing_exact_digest_authority(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    _assert_environment_error(
        lambda: _api().load_provider_environment_snapshot(
            run_root,
            expected_digest=f"sha256:{'0' * 64}",
        )
    )


def test_snapshot_noatime_verification_preserves_fixed_times(tmp_path: Path) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source, PROVIDER_PREFIX, run_root, expected_digest=prospective.digest
    )
    try:
        api.verify_provider_environment_snapshot(
            snapshot.rootfs_path, expected_digest=prospective.digest
        )
        value = os.stat(
            snapshot.rootfs_path / "share" / "payload.txt",
            follow_symlinks=False,
        )
        assert value.st_atime_ns == value.st_mtime_ns == 0
    finally:
        snapshot.close()


@pytest.mark.parametrize(
    "stage",
    [
        "population",
        "normalization",
        "final_chmod",
        "manifest_verification",
        "before_rename",
    ],
)
def test_snapshot_crashes_leave_no_resumable_or_mountable_partial_tree(
    tmp_path: Path, stage: str
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)

    def crash(observed: str, _path: Path) -> None:
        if observed == stage:
            raise RuntimeError(f"crash at {stage}")

    with pytest.raises(RuntimeError, match=stage):
        api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=prospective.digest,
            fault_hook=crash,
        )
    authority = run_root / "provider_environment_snapshots"
    assert not (authority / prospective.digest).exists()
    assert not tuple(authority.glob(".staging-*"))


@pytest.mark.parametrize(
    "stage",
    [
        "population",
        "normalization",
        "descendant_finalization",
        "root_finalization",
        "manifest_verification",
        "before_rename",
    ],
)
def test_snapshot_process_death_never_publishes_or_authorizes_staging(
    tmp_path: Path,
    stage: str,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    crash_exit = 86

    child = os.fork()
    if child == 0:
        def terminate_process(observed: str, _path: Path) -> None:
            if observed == stage:
                os._exit(crash_exit)

        try:
            snapshot = api.assemble_provider_environment_snapshot(
                source,
                PROVIDER_PREFIX,
                run_root,
                expected_digest=prospective.digest,
                fault_hook=terminate_process,
            )
            snapshot.close()
        except BaseException:
            os._exit(87)
        os._exit(88)

    waited, status = os.waitpid(child, 0)
    assert waited == child
    assert os.WIFEXITED(status)
    assert os.WEXITSTATUS(status) == crash_exit

    authority = run_root / "provider_environment_snapshots"
    assert not (authority / prospective.digest).exists()
    stale = tuple(authority.glob(".staging-*"))
    assert len(stale) == 1
    stale_rootfs = stale[0] / "rootfs"
    assert stale_rootfs.is_dir()

    _assert_environment_error(
        lambda: api.load_provider_environment_snapshot(
            run_root,
            expected_digest=prospective.digest,
        )
    )
    _assert_environment_error(
        lambda: api.verify_provider_environment_snapshot(
            stale_rootfs,
            expected_digest=prospective.digest,
        )
    )
    api._remove_private_staging(stale[0])


def test_snapshot_publication_fsyncs_finalized_tree_before_noreplace_rename(
    tmp_path: Path,
    monkeypatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    events: list[tuple[object, ...]] = []
    real_fsync = api.os.fsync
    real_rename_noreplace = api._rename_noreplace

    def recording_fsync(fd: int) -> None:
        observed = os.fstat(fd)
        target = Path(os.readlink(f"/proc/self/fd/{fd}"))
        events.append(
            (
                "fsync",
                target,
                stat.S_IFMT(observed.st_mode),
                stat.S_IMODE(observed.st_mode),
            )
        )
        real_fsync(fd)

    def recording_rename_noreplace(
        parent_fd: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        parent = Path(os.readlink(f"/proc/self/fd/{parent_fd}"))
        assert not (parent / destination_name).exists()
        real_rename_noreplace(parent_fd, source_name, destination_name)
        events.append(
            (
                "rename_noreplace",
                parent / source_name,
                parent / destination_name,
            )
        )

    monkeypatch.setattr(api.os, "fsync", recording_fsync)
    monkeypatch.setattr(api, "_rename_noreplace", recording_rename_noreplace)

    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()

    rename_index = next(
        index
        for index, event in enumerate(events)
        if event[0] == "rename_noreplace"
    )
    staging = events[rename_index][1]
    final = events[rename_index][2]
    assert final == snapshot.authority_path

    fsyncs_before_rename = events[:rename_index]
    for entry in manifest.entries:
        if entry.kind not in {"regular_file", "directory"}:
            continue
        path = (
            staging / "rootfs"
            if entry.path == "."
            else staging / "rootfs" / entry.path
        )
        expected_kind = stat.S_IFREG if entry.kind == "regular_file" else stat.S_IFDIR
        assert (
            "fsync",
            path,
            expected_kind,
            entry.mode,
        ) in fsyncs_before_rename

    assert (
        "fsync",
        staging / "manifest.json",
        stat.S_IFREG,
        0o400,
    ) in fsyncs_before_rename
    assert (
        "fsync",
        staging,
        stat.S_IFDIR,
        0o700,
    ) in fsyncs_before_rename
    assert (
        "fsync",
        snapshot.authority_path.parent,
        stat.S_IFDIR,
        0o700,
    ) in events[rename_index + 1 :]


def test_snapshot_population_detects_source_mutation_before_publish(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    mutated = False

    def mutate(stage: str, _path: Path) -> None:
        nonlocal mutated
        if stage == "population" and not mutated:
            path = source / "share" / "payload.txt"
            path.write_bytes(b"mutated")
            path.chmod(0o644)
            mutated = True

    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=prospective.digest,
            fault_hook=mutate,
        )
    )
    assert not (run_root / "provider_environment_snapshots" / prospective.digest).exists()


def test_snapshot_assembly_never_reopens_source_root_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_open_noatime = api._open_noatime
    real_lstat_root = api._lstat_root

    def reject_source_path_open(
        path: str | os.PathLike[str],
        flags: int,
        *,
        dir_fd: int | None = None,
    ) -> int:
        path_text = os.fspath(path)
        if path_text == os.fspath(source) or path_text.startswith("/proc/self/fd/"):
            raise AssertionError("assembly reopened the source root by pathname")
        return real_open_noatime(path, flags, dir_fd=dir_fd)

    def reject_source_path_lstat(
        path: str | os.PathLike[str],
    ) -> os.stat_result:
        if os.fspath(path) == os.fspath(source):
            raise AssertionError("assembly restated the source root by pathname")
        return real_lstat_root(path)

    monkeypatch.setattr(api, "_open_noatime", reject_source_path_open)
    monkeypatch.setattr(api, "_lstat_root", reject_source_path_lstat)

    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=prospective.digest,
    )
    try:
        assert (
            snapshot.rootfs_path / "share" / "payload.txt"
        ).read_bytes() == b"payload"
    finally:
        snapshot.close()


def test_snapshot_assembly_rejects_persistent_source_root_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    replacement = _make_source(tmp_path, name="replacement")
    replacement_payload = replacement / "share" / "payload.txt"
    replacement_payload.write_bytes(b"replacement")
    replacement_payload.chmod(0o644)
    saved_source = tmp_path / "saved-source"
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_open_chain = api._open_absolute_directory_chain
    exchanged = False

    def open_then_replace(
        path: str | os.PathLike[str],
        *,
        issue_path: str,
    ):
        nonlocal exchanged
        opened = real_open_chain(path, issue_path=issue_path)
        if Path(path) == source and not exchanged:
            source.rename(saved_source)
            replacement.rename(source)
            exchanged = True
        return opened

    monkeypatch.setattr(api, "_open_absolute_directory_chain", open_then_replace)

    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=prospective.digest,
        )
    )
    assert exchanged
    assert not (
        run_root / "provider_environment_snapshots" / prospective.digest
    ).exists()


def test_snapshot_assembly_uses_pinned_root_during_temporary_path_exchange(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    replacement = _make_source(tmp_path, name="replacement")
    replacement_payload = replacement / "share" / "payload.txt"
    replacement_payload.write_bytes(b"replacement")
    replacement_payload.chmod(0o644)
    saved_source = tmp_path / "saved-source"
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_open_chain = api._open_absolute_directory_chain
    exchanged = False
    restored = False

    def open_then_exchange(
        path: str | os.PathLike[str],
        *,
        issue_path: str,
    ):
        nonlocal exchanged
        opened = real_open_chain(path, issue_path=issue_path)
        if Path(path) == source and not exchanged:
            source.rename(saved_source)
            replacement.rename(source)
            exchanged = True
        return opened

    def restore_original(stage: str, _path: Path) -> None:
        nonlocal restored
        if stage == "population" and exchanged and not restored:
            source.rename(replacement)
            saved_source.rename(source)
            restored = True

    monkeypatch.setattr(api, "_open_absolute_directory_chain", open_then_exchange)

    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=prospective.digest,
        fault_hook=restore_original,
    )
    try:
        assert exchanged and restored
        assert (
            snapshot.rootfs_path / "share" / "payload.txt"
        ).read_bytes() == b"payload"
        assert (
            replacement / "share" / "payload.txt"
        ).read_bytes() == b"replacement"
    finally:
        snapshot.close()


def test_snapshot_rejects_existing_digest_authority_without_exact_manifest(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    bad = run_root / "provider_environment_snapshots" / prospective.digest
    bad.mkdir(parents=True)
    sentinel = bad / "must-not-change"
    sentinel.write_bytes(b"existing")
    _assert_environment_error(
        lambda: api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=prospective.digest,
        )
    )
    assert sentinel.read_bytes() == b"existing"
    assert not tuple(bad.parent.glob(".staging-*"))


def test_snapshot_population_borrows_rootfs_fd_without_reopening_staging_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    prospective = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_copy = api._copy_manifest_tree_to_staging
    real_open_directory = api._open_directory
    population_active = False
    observed_destination_fd: int | None = None

    def copy_with_path_open_guard(
        source_root_fd: int,
        destination_root_fd: int,
        manifest,
        *,
        provider_prefix: str,
    ) -> None:
        nonlocal population_active, observed_destination_fd
        assert isinstance(destination_root_fd, int)
        assert stat.S_ISDIR(os.fstat(destination_root_fd).st_mode)
        observed_destination_fd = destination_root_fd
        population_active = True
        try:
            real_copy(
                source_root_fd,
                destination_root_fd,
                manifest,
                provider_prefix=provider_prefix,
            )
        finally:
            population_active = False

    def reject_population_path_open(
        path: str | os.PathLike[str],
    ) -> int:
        if population_active:
            raise AssertionError(
                f"snapshot population reopened a destination path: {path!r}"
            )
        return real_open_directory(path)

    monkeypatch.setattr(
        api,
        "_copy_manifest_tree_to_staging",
        copy_with_path_open_guard,
    )
    monkeypatch.setattr(api, "_open_directory", reject_population_path_open)

    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=prospective.digest,
    )
    try:
        assert observed_destination_fd is not None
        assert (
            snapshot.rootfs_path / "share" / "payload.txt"
        ).read_bytes() == b"payload"
    finally:
        snapshot.close()


def test_snapshot_population_path_swap_cannot_redirect_copied_bytes(
    tmp_path: Path,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    source_binding = api._open_source_binding(source)
    assembly = api._open_snapshot_assembly(run_root)
    moved_staging = assembly.authority_path / ".held-staging"
    redirect = tmp_path / "redirect"
    redirect.mkdir(mode=0o700)
    (redirect / "rootfs").mkdir(mode=0o700)

    assembly.staging_path.rename(moved_staging)
    assembly.staging_path.symlink_to(redirect, target_is_directory=True)
    try:
        api._copy_manifest_tree_to_staging(
            source_binding.root_fd,
            assembly.rootfs_fd,
            manifest,
            provider_prefix=PROVIDER_PREFIX,
        )

        share_fd = api._open_directory_at(assembly.rootfs_fd, "share")
        try:
            payload_fd = api._open_regular_at(share_fd, "payload.txt")
            try:
                assert os.read(payload_fd, 64) == b"payload"
            finally:
                os.close(payload_fd)
        finally:
            os.close(share_fd)
        assert not (redirect / "rootfs" / "share").exists()
    finally:
        source_binding.close()
        assembly.close()
        assembly.staging_path.unlink()
        api._remove_private_staging(moved_staging)


def test_snapshot_failure_closes_and_removes_exact_held_staging_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    redirect = tmp_path / "redirect"
    redirect.mkdir(mode=0o700)
    sentinel = redirect / "must-not-remove"
    sentinel.write_bytes(b"external")
    captured: list[object] = []
    captured_fds: list[int] = []
    moved_staging = (
        run_root / "provider_environment_snapshots" / ".held-staging"
    )
    real_open_assembly = api._open_snapshot_assembly

    def capture_assembly(path: str | os.PathLike[str]):
        assembly = real_open_assembly(path)
        captured.append(assembly)
        captured_fds.extend(
            (
                assembly.authority_fd,
                assembly.staging_fd,
                assembly.rootfs_fd,
            )
        )
        return assembly

    def exchange_then_fail(
        _source_root_fd: int,
        _destination_root_fd: int,
        _manifest,
        *,
        provider_prefix: str,
    ) -> None:
        del provider_prefix
        assembly = captured[0]
        assembly.staging_path.rename(moved_staging)
        assembly.staging_path.symlink_to(redirect, target_is_directory=True)
        raise RuntimeError("injected population failure")

    monkeypatch.setattr(api, "_open_snapshot_assembly", capture_assembly)
    monkeypatch.setattr(
        api,
        "_copy_manifest_tree_to_staging",
        exchange_then_fail,
    )

    with pytest.raises(RuntimeError, match="injected population failure"):
        api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
        )

    assert not moved_staging.exists()
    assert sentinel.read_bytes() == b"external"
    assert os.path.lexists(captured[0].staging_path)
    assert captured[0].staging_path.is_symlink()
    for fd in captured_fds:
        with pytest.raises(OSError) as exc_info:
            os.fstat(fd)
        assert exc_info.value.errno == errno.EBADF


def test_snapshot_setup_failure_never_follows_exchanged_staging_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    authority = run_root / "provider_environment_snapshots"
    moved_staging = authority / ".held-setup-staging"
    redirect = tmp_path / "redirect"
    redirect.mkdir(mode=0o700)
    sentinel = redirect / "must-not-touch"
    sentinel.write_bytes(b"external")
    sentinel.chmod(0o640)
    redirect.chmod(0o500)
    redirect_mode = stat.S_IMODE(os.stat(redirect).st_mode)
    sentinel_mode = stat.S_IMODE(os.stat(sentinel).st_mode)
    exchanged_path: Path | None = None
    real_open_pinned = api._open_pinned_directory_at

    def exchange_before_rootfs_open(
        parent_fd: int,
        name: str,
        *,
        issue_path: str,
        owned_fds: list[int],
        edges: list[object],
    ) -> int:
        nonlocal exchanged_path
        if name == "rootfs":
            staging = Path(os.readlink(f"/proc/self/fd/{parent_fd}"))
            staging.rename(moved_staging)
            staging.symlink_to(redirect, target_is_directory=True)
            exchanged_path = staging
            raise api.ProviderIsolationEnvironmentError(
                (
                    api._issue(
                        "$.snapshot_staging.rootfs",
                        "injected setup failure",
                    ),
                )
            )
        return real_open_pinned(
            parent_fd,
            name,
            issue_path=issue_path,
            owned_fds=owned_fds,
            edges=edges,
        )

    monkeypatch.setattr(
        api,
        "_open_pinned_directory_at",
        exchange_before_rootfs_open,
    )

    try:
        with pytest.raises(
            api.ProviderIsolationEnvironmentError,
            match="injected setup failure",
        ):
            api._open_snapshot_assembly(run_root)

        assert exchanged_path is not None
        assert os.path.lexists(exchanged_path)
        assert exchanged_path.is_symlink()
        assert not moved_staging.exists()
        assert sentinel.read_bytes() == b"external"
        assert stat.S_IMODE(os.stat(redirect).st_mode) == redirect_mode
        assert stat.S_IMODE(os.stat(sentinel).st_mode) == sentinel_mode
    finally:
        redirect.chmod(0o700)
        if exchanged_path is not None and os.path.lexists(exchanged_path):
            exchanged_path.unlink()
        if moved_staging.exists():
            api._remove_private_staging(moved_staging)


def test_snapshot_finalization_and_publication_never_reopen_destination_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_open_assembly = api._open_snapshot_assembly
    real_open_directory = api._open_directory
    real_path_manifest = api._build_provider_environment_manifest
    captured: list[object] = []

    def capture_assembly(path: str | os.PathLike[str]):
        assembly = real_open_assembly(path)
        captured.append(assembly)
        return assembly

    def reject_destination_directory_reopen(
        path: str | os.PathLike[str],
    ) -> int:
        if captured:
            raw = os.fspath(path)
            authority = os.fspath(captured[0].authority_path)
            if isinstance(raw, str) and (
                raw == authority or raw.startswith(f"{authority}/")
            ):
                raise AssertionError(
                    f"snapshot publication reopened destination path {raw!r}"
                )
        return real_open_directory(path)

    def reject_path_manifest_rebuild(
        root: str | os.PathLike[str],
        provider_prefix: str,
        *,
        inject_launch_shim: bool,
        finalized_snapshot: bool,
    ):
        if finalized_snapshot:
            raise AssertionError(
                f"snapshot manifest rebuilt by destination path {root!r}"
            )
        return real_path_manifest(
            root,
            provider_prefix,
            inject_launch_shim=inject_launch_shim,
            finalized_snapshot=finalized_snapshot,
        )

    monkeypatch.setattr(api, "_open_snapshot_assembly", capture_assembly)
    monkeypatch.setattr(api, "_open_directory", reject_destination_directory_reopen)
    monkeypatch.setattr(
        api,
        "_build_provider_environment_manifest",
        reject_path_manifest_rebuild,
    )

    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    try:
        assert captured
        assert os.path.samestat(
            os.fstat(snapshot.root_fd),
            os.stat(snapshot.rootfs_path, follow_symlinks=False),
        )
    finally:
        snapshot.close()


def test_snapshot_finalization_path_swap_cannot_redirect_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_open_assembly = api._open_snapshot_assembly
    captured: list[object] = []
    held_staging = (
        run_root / "provider_environment_snapshots" / ".held-finalization"
    )
    redirect = tmp_path / "redirect"
    redirect.mkdir(mode=0o700)
    (redirect / "rootfs").mkdir(mode=0o700)
    sentinel = redirect / "must-not-mutate"
    sentinel.write_bytes(b"external")
    sentinel.chmod(0o640)
    sentinel_mode = stat.S_IMODE(os.stat(sentinel).st_mode)
    exchanged = False

    def capture_assembly(path: str | os.PathLike[str]):
        assembly = real_open_assembly(path)
        captured.append(assembly)
        return assembly

    def exchange(stage: str, _path: Path) -> None:
        nonlocal exchanged
        if stage != "normalization" or exchanged:
            return
        assembly = captured[0]
        assembly.staging_path.rename(held_staging)
        assembly.staging_path.symlink_to(redirect, target_is_directory=True)
        exchanged = True

    monkeypatch.setattr(api, "_open_snapshot_assembly", capture_assembly)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.assemble_provider_environment_snapshot(
                source,
                PROVIDER_PREFIX,
                run_root,
                expected_digest=manifest.digest,
                fault_hook=exchange,
        )
        assert exchanged
        assert not held_staging.exists()
        assert sentinel.read_bytes() == b"external"
        assert stat.S_IMODE(os.stat(sentinel).st_mode) == sentinel_mode
        assert not (
            run_root / "provider_environment_snapshots" / manifest.digest
        ).exists()
    finally:
        if captured and os.path.lexists(captured[0].staging_path):
            captured[0].staging_path.unlink()


@pytest.mark.parametrize("collision_kind", ["regular", "symlink"])
def test_snapshot_manifest_publication_rejects_existing_entry_without_following(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision_kind: str,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    real_open_assembly = api._open_snapshot_assembly
    captured: list[object] = []
    sentinel = tmp_path / "must-not-change"
    sentinel.write_bytes(b"external")

    def capture_assembly(path: str | os.PathLike[str]):
        assembly = real_open_assembly(path)
        captured.append(assembly)
        return assembly

    def collide(stage: str, _path: Path) -> None:
        if stage != "manifest_verification":
            return
        assembly = captured[0]
        try:
            os.stat(
                "manifest.json",
                dir_fd=assembly.staging_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if collision_kind == "regular":
                fd = os.open(
                    "manifest.json",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                    0o600,
                    dir_fd=assembly.staging_fd,
                )
                os.close(fd)
            else:
                os.symlink(
                    os.fspath(sentinel),
                    "manifest.json",
                    dir_fd=assembly.staging_fd,
                )

    monkeypatch.setattr(api, "_open_snapshot_assembly", capture_assembly)
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
            fault_hook=collide,
        )
    assert sentinel.read_bytes() == b"external"
    assert not tuple(
        (run_root / "provider_environment_snapshots").glob(".staging-*")
    )


def test_snapshot_rejects_final_name_substitution_after_atomic_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    authority = run_root / "provider_environment_snapshots"
    authority.mkdir(mode=0o700)
    replacement = authority / "replacement"
    replacement.mkdir(mode=0o700)
    (replacement / "rootfs").mkdir(mode=0o555)
    sentinel = replacement / "must-not-authorize"
    sentinel.write_bytes(b"external")
    held_original = authority / ".held-original"
    real_rename = api._rename_noreplace

    def rename_then_substitute(
        parent_fd: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        real_rename(parent_fd, source_name, destination_name)
        parent = Path(os.readlink(f"/proc/self/fd/{parent_fd}"))
        (parent / destination_name).rename(held_original)
        replacement.rename(parent / destination_name)

    monkeypatch.setattr(api, "_rename_noreplace", rename_then_substitute)
    returned = None
    try:
        try:
            returned = api.assemble_provider_environment_snapshot(
                source,
                PROVIDER_PREFIX,
                run_root,
                expected_digest=manifest.digest,
            )
        except api.ProviderIsolationEnvironmentError:
            pass
        else:
            pytest.fail("substituted final authority was accepted")
        assert (
            authority / manifest.digest / "must-not-authorize"
        ).read_bytes() == b"external"
        assert (held_original / "rootfs" / "share" / "payload.txt").read_bytes() == (
            b"payload"
        )
        assert not tuple(authority.glob(".staging-*"))
    finally:
        if returned is not None:
            returned.close()


def test_parent_fsync_failure_recovers_only_through_verified_load_and_refsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    authority = run_root / "provider_environment_snapshots"
    final = authority / manifest.digest
    real_fsync = api.os.fsync
    failed_once = False
    recovery_resyncs = 0

    def one_shot_parent_failure(fd: int) -> None:
        nonlocal failed_once, recovery_resyncs
        target = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if target == authority:
            if final.exists() and not failed_once:
                failed_once = True
                raise OSError(errno.EIO, "injected authority fsync failure")
            if failed_once:
                recovery_resyncs += 1
        real_fsync(fd)

    monkeypatch.setattr(api.os, "fsync", one_shot_parent_failure)
    with pytest.raises(OSError, match="injected authority fsync failure"):
        api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
        )
    assert failed_once
    assert final.is_dir()
    assert not tuple(authority.glob(".staging-*"))

    shutil.rmtree(source)
    recovered = api.load_provider_environment_snapshot(
        run_root,
        expected_digest=manifest.digest,
    )
    try:
        assert recovery_resyncs == 1
        assert (
            recovered.rootfs_path / "share" / "payload.txt"
        ).read_bytes() == b"payload"
    finally:
        recovered.close()


def test_rename_then_raise_preserves_published_snapshot_for_verified_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    authority = run_root / "provider_environment_snapshots"
    final = authority / manifest.digest
    real_rename = api._rename_noreplace

    def rename_then_raise(
        parent_fd: int,
        source_name: str,
        destination_name: str,
    ) -> None:
        real_rename(parent_fd, source_name, destination_name)
        raise RuntimeError("injected post-rename failure")

    monkeypatch.setattr(api, "_rename_noreplace", rename_then_raise)
    with pytest.raises(RuntimeError, match="injected post-rename failure"):
        api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
        )

    assert final.is_dir()
    assert not tuple(authority.glob(".staging-*"))
    shutil.rmtree(source)

    recovered = api.load_provider_environment_snapshot(
        run_root,
        expected_digest=manifest.digest,
    )
    try:
        assert recovered.manifest.digest == manifest.digest
        assert (
            recovered.rootfs_path / "share" / "payload.txt"
        ).read_bytes() == b"payload"
    finally:
        recovered.close()


def test_verify_is_nonaccepting_and_load_fails_closed_when_refsync_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    snapshot = api.assemble_provider_environment_snapshot(
        source,
        PROVIDER_PREFIX,
        run_root,
        expected_digest=manifest.digest,
    )
    snapshot.close()
    authority = run_root / "provider_environment_snapshots"
    real_fsync = api.os.fsync
    refsync_attempts = 0

    def reject_parent_refsync(fd: int) -> None:
        nonlocal refsync_attempts
        target = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if target == authority:
            refsync_attempts += 1
            raise OSError(errno.EIO, "injected recovery refsync failure")
        real_fsync(fd)

    monkeypatch.setattr(api.os, "fsync", reject_parent_refsync)
    verified = api.verify_provider_environment_snapshot(
        snapshot.rootfs_path,
        expected_digest=manifest.digest,
    )
    assert verified.digest == manifest.digest
    assert refsync_attempts == 0

    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.load_provider_environment_snapshot(
            run_root,
            expected_digest=manifest.digest,
        )
    assert refsync_attempts == 1


def test_tampered_post_fsync_failure_snapshot_is_never_recovered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    source = _make_source(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    manifest = api.build_provider_environment_manifest(source, PROVIDER_PREFIX)
    authority = run_root / "provider_environment_snapshots"
    final = authority / manifest.digest
    real_fsync = api.os.fsync
    failed_once = False
    recovery_resyncs = 0

    def one_shot_parent_failure(fd: int) -> None:
        nonlocal failed_once, recovery_resyncs
        target = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if target == authority:
            if final.exists() and not failed_once:
                failed_once = True
                raise OSError(errno.EIO, "injected authority fsync failure")
            if failed_once:
                recovery_resyncs += 1
        real_fsync(fd)

    monkeypatch.setattr(api.os, "fsync", one_shot_parent_failure)
    with pytest.raises(OSError):
        api.assemble_provider_environment_snapshot(
            source,
            PROVIDER_PREFIX,
            run_root,
            expected_digest=manifest.digest,
        )

    payload = final / "rootfs" / "share" / "payload.txt"
    payload.chmod(0o644)
    payload.write_bytes(b"tampered")
    payload.chmod(0o444)
    os.utime(payload, ns=(0, 0))
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.load_provider_environment_snapshot(
            run_root,
            expected_digest=manifest.digest,
        )
    assert recovery_resyncs == 0
