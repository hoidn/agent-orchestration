from __future__ import annotations

import errno
import importlib
import os
from pathlib import Path
import socket
import stat
import unicodedata

import pytest


_REQUIRED_AUTHORITY_LABELS = (
    "workflow",
    "source",
    "extern",
    "controller_state",
    "provider_environment_source",
    "provider_environment_snapshot",
    "scratch",
    "control",
    "evaluator",
    "peer",
    "parent",
)
_EXPECTED_MAX_DIRECTORY_DEPTH = 128
_EXPECTED_MAX_ENTRY_COUNT = 100_000
_EXPECTED_MAX_SYMLINK_EXPANSIONS = 40


def _api():
    return importlib.import_module("orchestrator.providers.isolation_candidate")


def _candidate(tmp_path: Path) -> Path:
    root = tmp_path / "candidate"
    root.mkdir(mode=0o700)
    (root / "src").mkdir(mode=0o700)
    source = root / "src" / "input.txt"
    source.write_text("input\n", encoding="utf-8")
    source.chmod(0o600)
    (root / "input-link").symlink_to("src/input.txt")
    return root


def _empty_candidate(parent: Path, *, name: str) -> Path:
    root = parent / name
    root.mkdir(mode=0o700)
    return root


def _nested_directories(root: Path, depth: int) -> list[Path]:
    current = root
    created: list[Path] = []
    for _index in range(depth):
        current = current / "d"
        current.mkdir(mode=0o700)
        created.append(current)
    return created


def _remove_nested_directories(paths: list[Path]) -> None:
    for path in reversed(paths):
        path.rmdir()


def _symlink_chain(root: Path, *, prefix: str, length: int) -> None:
    target = root / f"{prefix}-target"
    target.write_text("target", encoding="utf-8")
    target.chmod(0o600)
    next_name = target.name
    for index in reversed(range(length)):
        name = f"{prefix}-{index:04d}"
        (root / name).symlink_to(next_name)
        next_name = name


def _authorities(base: Path) -> dict[str, Path]:
    root = base / "denied-authorities"
    root.mkdir(exist_ok=True)
    authorities: dict[str, Path] = {}
    for label in _REQUIRED_AUTHORITY_LABELS:
        if label == "provider_environment_snapshot":
            continue
        authority = root / label
        authority.mkdir(exist_ok=True)
        authorities[label] = authority
    snapshot = (
        authorities["controller_state"]
        / "provider_environment_snapshots"
        / "digest"
        / "rootfs"
    )
    snapshot.mkdir(parents=True, exist_ok=True)
    authorities["provider_environment_snapshot"] = snapshot
    return authorities


def _admit(
    api,
    candidate: str | os.PathLike[str],
    *,
    authority_base: Path | None = None,
    denied_authorities: dict[str, Path] | None = None,
):
    base = authority_base or Path(os.fspath(candidate)).parent
    return api.admit_provider_candidate(
        candidate,
        denied_authorities=(
            denied_authorities
            if denied_authorities is not None
            else _authorities(base)
        ),
    )


def _assert_candidate_error(call, *, path: str | None = None) -> None:
    api = _api()
    with pytest.raises(api.ProviderIsolationCandidateError) as exc_info:
        call()
    assert exc_info.value.code == "provider_isolation_candidate_invalid"
    assert exc_info.value.issues
    assert all(
        issue.code == "provider_isolation_candidate_invalid"
        for issue in exc_info.value.issues
    )
    if path is not None:
        assert path in {issue.path for issue in exc_info.value.issues}


def test_candidate_admission_pins_root_and_revalidates_descriptor_identity(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with _admit(api, candidate) as admission:
        assert admission.path == candidate.resolve()
        assert admission.root_fd >= 0
        assert admission.root_identity.device == os.stat(candidate).st_dev
        assert admission.root_identity.inode == os.stat(candidate).st_ino
        assert admission.root_identity.mount_id > 0
        assert {entry.path for entry in admission.entries} == {
            "input-link",
            "src",
            "src/input.txt",
        }
        admission.revalidate()

    assert admission.root_fd == -1


def test_candidate_admission_rejects_root_or_ancestor_symlink(
    tmp_path: Path,
) -> None:
    api = _api()
    real = _candidate(tmp_path)
    root_alias = tmp_path / "candidate-alias"
    root_alias.symlink_to(real.name)
    _assert_candidate_error(
        lambda: _admit(api, root_alias),
        path="$.candidate_root",
    )

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    nested = real_parent / "candidate"
    nested.mkdir()
    parent_alias = tmp_path / "parent-alias"
    parent_alias.symlink_to(real_parent.name)
    _assert_candidate_error(
        lambda: _admit(
            api,
            parent_alias / "candidate",
            authority_base=tmp_path,
        ),
        path="$.candidate_root.ancestry",
    )


def test_candidate_admission_rejects_noncanonical_path_spelling(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    spellings = (
        f"{candidate}/",
        f"{candidate.parent}//{candidate.name}",
        f"{candidate.parent}/./{candidate.name}",
        f"{candidate}/../{candidate.name}",
    )
    for spelling in spellings:
        _assert_candidate_error(
            lambda spelling=spelling: _admit(
                api,
                spelling,
                authority_base=tmp_path,
            ),
            path="$.candidate_root",
        )


def test_candidate_admission_requires_controller_owner_and_closed_write_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    candidate.chmod(0o770)
    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.candidate_root.mode",
    )
    candidate.chmod(0o700)

    (candidate / "src" / "input.txt").chmod(0o666)
    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries[src/input.txt].mode",
    )
    (candidate / "src" / "input.txt").chmod(0o600)

    real_geteuid = api.os.geteuid
    monkeypatch.setattr(api.os, "geteuid", lambda: real_geteuid() + 1)
    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.candidate_root.owner",
    )


def test_candidate_admission_rejects_non_utf8_and_non_nfc_entry_names(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    raw_candidate = os.fsencode(candidate)

    undecodable = raw_candidate + b"/bad-\xff"
    fd = os.open(undecodable, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries",
    )
    os.unlink(undecodable)

    decomposed = unicodedata.normalize("NFD", "é") + ".txt"
    assert not unicodedata.is_normalized("NFC", decomposed)
    (candidate / decomposed).write_text("x", encoding="utf-8")
    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries",
    )


def test_candidate_admission_rejects_non_nfc_symlink_text(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    decomposed_target = unicodedata.normalize("NFD", "é")
    (candidate / "bad-link").symlink_to(decomposed_target)

    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries[bad-link].link_text",
    )


def test_candidate_admission_rejects_surrogateescaped_symlink_text(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    os.symlink(
        b"undecodable-\xff",
        os.fsencode(candidate) + b"/bad-link",
    )

    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries[bad-link].link_text",
    )


@pytest.mark.parametrize("kind", ("fifo", "socket"))
def test_candidate_admission_rejects_special_files(
    tmp_path: Path,
    kind: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    special = candidate / "special"
    bound_socket: socket.socket | None = None
    try:
        if kind == "fifo":
            os.mkfifo(special, 0o600)
        else:
            bound_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            bound_socket.bind(str(special))

        _assert_candidate_error(
            lambda: _admit(api, candidate),
            path="$.entries[special].kind",
        )
    finally:
        if bound_socket is not None:
            bound_socket.close()


def test_candidate_admission_rejects_device_nodes_or_device_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    device = candidate / "device"
    try:
        os.mknod(device, stat.S_IFCHR | 0o600, os.makedev(1, 3))
    except PermissionError:
        device.touch(mode=0o600)
        device.chmod(0o600)
        real_lstat_at = api._lstat_at

        def classify_fixture_as_device(directory_fd: int, name: str):
            observed = real_lstat_at(directory_fd, name)
            if name != "device":
                return observed
            fields = list(observed)
            fields[0] = stat.S_IFCHR | 0o600
            return os.stat_result(fields)

        monkeypatch.setattr(api, "_lstat_at", classify_fixture_as_device)

    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries[device].kind",
    )


@pytest.mark.parametrize(
    ("target", "issue_path"),
    (
        ("/etc/passwd", "$.entries[escape].link_text"),
        ("../outside", "$.entries[escape].link_text"),
        ("missing", "$.entries[escape].link_text"),
        ("missing/..", "$.entries[escape].link_text"),
        ("src/input.txt/..", "$.entries[escape].link_text"),
    ),
)
def test_candidate_admission_rejects_absolute_escaping_and_broken_symlinks(
    tmp_path: Path,
    target: str,
    issue_path: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    (candidate / "escape").symlink_to(target)

    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path=issue_path,
    )


def test_candidate_admission_accepts_safe_symlink_chains_with_parent_segments(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    (candidate / "alias").symlink_to("src")
    (candidate / "src" / "nested-link").symlink_to("../alias/input.txt")

    with _admit(api, candidate) as admission:
        assert any(entry.path == "src/nested-link" for entry in admission.entries)


def test_candidate_admission_bounds_symlink_chain_without_python_recursion(
    tmp_path: Path,
) -> None:
    api = _api()
    near_bound = _empty_candidate(tmp_path, name="near-link-bound")
    _symlink_chain(
        near_bound,
        prefix="near",
        length=_EXPECTED_MAX_SYMLINK_EXPANSIONS,
    )
    with _admit(api, near_bound, authority_base=tmp_path):
        pass

    over_bound = _empty_candidate(tmp_path, name="over-link-bound")
    _symlink_chain(over_bound, prefix="long", length=1100)
    _assert_candidate_error(
        lambda: _admit(api, over_bound, authority_base=tmp_path),
        path="$.entries[long-0000].link_text",
    )


def test_candidate_admission_bounds_directory_depth_without_python_recursion(
    tmp_path: Path,
) -> None:
    api = _api()
    near_bound = _empty_candidate(tmp_path, name="near-depth-bound")
    near_paths = _nested_directories(
        near_bound,
        _EXPECTED_MAX_DIRECTORY_DEPTH,
    )
    try:
        with _admit(api, near_bound, authority_base=tmp_path):
            pass
    finally:
        _remove_nested_directories(near_paths)

    over_bound = _empty_candidate(tmp_path, name="over-depth-bound")
    deep_paths = _nested_directories(over_bound, 1100)
    try:
        _assert_candidate_error(
            lambda: _admit(api, over_bound, authority_base=tmp_path),
            path=(
                "$.entries["
                + "/".join("d" for _ in range(_EXPECTED_MAX_DIRECTORY_DEPTH + 1))
                + "].depth"
            ),
        )
    finally:
        _remove_nested_directories(deep_paths)


def test_candidate_admission_bounds_total_entry_traversal_with_near_bound_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    monkeypatch.setattr(api, "MAX_CANDIDATE_ENTRY_COUNT", 8, raising=False)
    candidate = _empty_candidate(tmp_path, name="entry-bound")
    for index in range(8):
        fd = os.open(
            candidate / f"entry-{index}",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(fd)

    with _admit(api, candidate, authority_base=tmp_path):
        pass

    extra_fd = os.open(
        candidate / "entry-over-bound",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    os.close(extra_fd)
    _assert_candidate_error(
        lambda: _admit(api, candidate, authority_base=tmp_path),
        path="$.entries",
    )


def test_candidate_admission_publishes_explicit_traversal_bounds() -> None:
    api = _api()
    assert api.MAX_CANDIDATE_DIRECTORY_DEPTH == _EXPECTED_MAX_DIRECTORY_DEPTH
    assert api.MAX_CANDIDATE_ENTRY_COUNT == _EXPECTED_MAX_ENTRY_COUNT
    assert (
        api.MAX_CANDIDATE_SYMLINK_EXPANSIONS
        == _EXPECTED_MAX_SYMLINK_EXPANSIONS
    )


def test_candidate_admission_rejects_symlinks_and_aliases_across_runtime_mask(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    runtime = candidate / ".orchestrate"
    runtime.mkdir(mode=0o700)
    state = runtime / "state"
    state.write_text("state", encoding="utf-8")
    state.chmod(0o600)
    (candidate / "state-link").symlink_to(".orchestrate/state")

    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries[state-link].link_text",
    )

    (candidate / "state-link").unlink()
    os.link(runtime / "state", candidate / "state-alias")
    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries[state-alias].hardlinks",
    )


def test_candidate_admission_accepts_internal_hardlinks_and_rejects_external_ones(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    source = candidate / "src" / "input.txt"
    os.link(source, candidate / "internal-alias")

    with _admit(api, candidate):
        pass

    external_alias = tmp_path / "external-alias"
    os.link(source, external_alias)
    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries[internal-alias].hardlinks",
    )


def test_candidate_admission_rejects_nested_mount_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    real_mount_id = api._statx_mount_id

    def changed_mount_id(directory_fd: int, name: str | None = None) -> int:
        observed = real_mount_id(directory_fd, name)
        if name == "src":
            return observed + 1
        return observed

    monkeypatch.setattr(api, "_statx_mount_id", changed_mount_id)
    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.entries[src].mount_id",
    )


def test_candidate_admission_fails_when_descriptor_mount_identity_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    monkeypatch.setattr(
        api,
        "_statx_mount_id",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            api.MountIdentityUnavailable("unavailable")
        ),
    )
    _assert_candidate_error(
        lambda: _admit(api, candidate),
        path="$.candidate_root.mount_id",
    )


@pytest.mark.parametrize("relation", ("contains", "contained_by", "alias"))
def test_candidate_admission_rejects_denied_authority_overlap_both_directions(
    tmp_path: Path,
    relation: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    if relation == "contains":
        denied = candidate / "src"
    elif relation == "contained_by":
        denied = candidate.parent
    else:
        denied = tmp_path / "candidate-alias"
        denied.symlink_to(candidate.name)
    authorities = _authorities(tmp_path)
    authorities["control"] = denied

    _assert_candidate_error(
        lambda: _admit(
            api,
            candidate,
            denied_authorities=authorities,
        ),
        path="$.authorities[control]",
    )


@pytest.mark.parametrize("missing_label", _REQUIRED_AUTHORITY_LABELS)
def test_candidate_admission_rejects_incomplete_authority_inventory(
    tmp_path: Path,
    missing_label: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    authorities = _authorities(tmp_path)
    del authorities[missing_label]

    _assert_candidate_error(
        lambda: api.admit_provider_candidate(
            candidate,
            denied_authorities=authorities,
        ),
        path=f"$.authorities[{missing_label}]",
    )


def test_candidate_authority_inventory_uses_the_closed_generic_label_set() -> None:
    api = _api()
    assert api.REQUIRED_CANDIDATE_AUTHORITY_LABELS == _REQUIRED_AUTHORITY_LABELS


def test_candidate_admission_rejects_unknown_authority_inventory_label(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    authorities = _authorities(tmp_path)
    unreviewed = tmp_path / "denied-authorities" / "unreviewed"
    unreviewed.mkdir()
    authorities["unreviewed"] = unreviewed

    _assert_candidate_error(
        lambda: api.admit_provider_candidate(
            candidate,
            denied_authorities=authorities,
        ),
        path="$.authorities[unreviewed]",
    )


def test_candidate_admission_requires_authority_inventory_argument(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)

    with pytest.raises(TypeError):
        api.admit_provider_candidate(candidate)


def test_candidate_authority_inventory_preserves_snapshot_state_exception(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    authorities = _authorities(tmp_path)
    assert (
        authorities["controller_state"]
        in authorities["provider_environment_snapshot"].parents
    )

    with _admit(api, candidate, denied_authorities=authorities):
        pass


def test_candidate_authority_inventory_rejects_nul_before_path_resolution(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    authorities = _authorities(tmp_path)

    with _admit(api, candidate, denied_authorities=authorities):
        pass

    authorities["control"] = f"{authorities['control']}\x00alias"
    _assert_candidate_error(
        lambda: api.admit_provider_candidate(
            candidate,
            denied_authorities=authorities,
        ),
        path="$.authorities[control]",
    )


def test_candidate_mount_location_is_closed_to_workspace_components() -> None:
    api = _api()
    for accepted in (
        "/home/owner/candidate",
        "/workspace/trial/candidate",
        "/tmp/trial/candidate",
    ):
        assert api.validate_candidate_mount_location(accepted) == Path(accepted)

    for rejected, path in (
        ("/tmp", "$.candidate_root"),
        ("/mnt/trial/candidate", "$.candidate_root.workspace_component"),
        ("/opt/trial/candidate", "$.candidate_root.workspace_component"),
        ("/usr/local/candidate", "$.candidate_root.workspace_component"),
    ):
        _assert_candidate_error(
            lambda rejected=rejected: api.validate_candidate_mount_location(rejected),
            path=path,
        )


def test_candidate_mount_location_rejects_provider_prefix_component_collision() -> None:
    api = _api()
    _assert_candidate_error(
        lambda: api.validate_candidate_mount_location(
            "/workspace/trial/candidate",
            provider_prefix="/workspace/provider",
        ),
        path="$.candidate_root.workspace_component",
    )


def test_candidate_admission_holds_an_exclusive_lease_until_close(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    first = _admit(api, candidate)
    try:
        _assert_candidate_error(
            lambda: _admit(api, candidate),
            path="$.candidate_root.lease",
        )
    finally:
        first.close()

    with _admit(api, candidate):
        pass


def test_candidate_revalidation_rejects_path_replacement_but_keeps_pinned_fd(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    admission = _admit(api, candidate)
    original_inode = admission.root_identity.inode
    moved = tmp_path / "moved-candidate"
    try:
        candidate.rename(moved)
        candidate.mkdir(mode=0o700)
        assert os.fstat(admission.root_fd).st_ino == original_inode
        _assert_candidate_error(
            admission.revalidate,
            path="$.candidate_root.ancestry",
        )
    finally:
        admission.close()


def test_candidate_revalidation_rejects_ancestor_exchange_with_same_root_inode(
    tmp_path: Path,
) -> None:
    api = _api()
    arm = tmp_path / "arm"
    arm.mkdir(mode=0o700)
    candidate = _candidate(arm)
    admission = _admit(api, candidate, authority_base=tmp_path)
    original_inode = admission.root_identity.inode
    moved_arm = tmp_path / "moved-arm"
    try:
        arm.rename(moved_arm)
        arm.mkdir(mode=0o700)
        (moved_arm / "candidate").rename(arm / "candidate")
        assert os.stat(candidate).st_ino == original_inode
        assert os.fstat(admission.root_fd).st_ino == original_inode
        _assert_candidate_error(
            admission.revalidate,
            path="$.candidate_root.ancestry",
        )
    finally:
        admission.close()


@pytest.mark.parametrize("race", ("lstat", "open"))
def test_candidate_revalidation_normalizes_pathname_exchange_oserror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    race: str,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    admission = _admit(api, candidate)
    try:
        if race == "lstat":
            real_stat = api.os.stat

            def raced_stat(path, *args, **kwargs):
                if (
                    kwargs.get("dir_fd") is not None
                    and kwargs.get("follow_symlinks") is False
                ):
                    raise FileNotFoundError(
                        errno.ENOENT,
                        "candidate pathname exchanged",
                    )
                return real_stat(path, *args, **kwargs)

            monkeypatch.setattr(api.os, "stat", raced_stat)
        else:
            real_open = api.os.open

            def raced_open(path, *args, **kwargs):
                if kwargs.get("dir_fd") is not None:
                    raise FileNotFoundError(
                        errno.ENOENT,
                        "candidate pathname exchanged",
                    )
                return real_open(path, *args, **kwargs)

            monkeypatch.setattr(api.os, "open", raced_open)

        _assert_candidate_error(
            admission.revalidate,
            path="$.candidate_root.ancestry",
        )
    finally:
        admission.close()


def test_candidate_revalidation_normal_path_remains_valid(
    tmp_path: Path,
) -> None:
    api = _api()
    candidate = _candidate(tmp_path)
    with _admit(api, candidate) as admission:
        admission.revalidate()
