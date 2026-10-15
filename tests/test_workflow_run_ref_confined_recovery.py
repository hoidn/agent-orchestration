"""Confined run-ref workspace copier and two-phase checkpoint header.

The holder tmpfs and the host clone are both ordinary host directories here;
the copier only ever sees their retained root descriptors.
"""

from __future__ import annotations

import os
import re
import socket
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.checkpoint import (
    RunRefCheckpointError,
    checkpoint_workspace,
    preflight_checkpoint,
    publish_initial_header,
    read_checkpoint_header,
    seed_workspace,
    workspace_manifest,
)
from orchestrator.workflow.run_ref.workspace import freeze_tree

_RESERVED = (".git", ".orchestrate")
_BUDGET = 64 * 1024 * 1024


def _fd(path: Path) -> int:
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY)


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    clone, tmpfs = tmp_path / "clone", tmp_path / "tmpfs"
    clone.mkdir()
    tmpfs.mkdir()
    return clone, tmpfs


def _seed(clone: Path, tmpfs: Path):
    source, destination = _fd(clone), _fd(tmpfs)
    try:
        return seed_workspace(source, destination, max_bytes=_BUDGET)
    finally:
        os.close(source)
        os.close(destination)


def _checkpoint(tmpfs: Path, clone: Path, header: Path, *, effect="effect-1", ordinal=1, max_bytes=_BUDGET):
    source, destination = _fd(tmpfs), _fd(clone)
    try:
        return checkpoint_workspace(
            source,
            destination,
            header,
            effect_identity=effect,
            ordinal=ordinal,
            max_bytes=max_bytes,
        )
    finally:
        os.close(source)
        os.close(destination)


def _preflight(header: Path, clone: Path):
    descriptor = _fd(clone)
    try:
        return preflight_checkpoint(header, descriptor)
    finally:
        os.close(descriptor)


def _clone_tree(clone: Path) -> None:
    (clone / "src").mkdir()
    (clone / "src" / "main.py").write_text("print('hi')\n")
    (clone / "tool").write_bytes(b"#!/bin/sh\n")
    os.chmod(clone / "tool", 0o4755)
    (clone / "private").mkdir(mode=0o750)
    os.chmod(clone / "private", 0o750)
    os.symlink("/etc/hostname", clone / "leak")
    os.symlink("src/main.py", clone / "alias")
    (clone / ".git").mkdir()
    (clone / ".git" / "HEAD").write_text("ref\n")


def test_seed_reproduces_the_clone_manifest_in_the_tmpfs(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    _clone_tree(clone)
    os.chmod(clone / "tool", 0o755)

    _seed(clone, tmpfs)

    assert freeze_tree(tmpfs) == freeze_tree(clone, _RESERVED)


def test_seed_copies_symlink_targets_as_strings(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    _clone_tree(clone)

    _seed(clone, tmpfs)

    assert [os.readlink(tmpfs / "leak"), os.readlink(tmpfs / "alias")] == [
        "/etc/hostname",
        "src/main.py",
    ]


def test_seed_masks_setuid_bits(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    _clone_tree(clone)

    _seed(clone, tmpfs)

    assert stat.S_IMODE(os.lstat(tmpfs / "tool").st_mode) == 0o755


def test_seed_never_writes_the_sanitized_git(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    _clone_tree(clone)

    _seed(clone, tmpfs)

    assert not (tmpfs / ".git").exists()


def test_seed_refuses_a_hardlinked_host_clone_file(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    (clone / "a").write_bytes(b"x")
    os.link(clone / "a", clone / "b")

    with pytest.raises(RunRefCheckpointError) as caught:
        _seed(clone, tmpfs)

    assert caught.value.code == "run_ref_environment_escape_rejected"


def test_checkpoint_makes_the_clone_equal_to_the_tmpfs_under_a_committed_header(
    tmp_path: Path,
) -> None:
    clone, tmpfs = _roots(tmp_path)
    _clone_tree(clone)
    os.chmod(clone / "tool", 0o755)
    (clone / "gone.txt").write_text("old\n")
    _seed(clone, tmpfs)
    (tmpfs / "src" / "main.py").write_text("print('edited')\n")
    (tmpfs / "new").mkdir()
    (tmpfs / "new" / "file.txt").write_text("new\n")
    (tmpfs / "gone.txt").unlink()
    (tmpfs / "tool").unlink()
    (tmpfs / "tool").mkdir()
    os.rmdir(tmpfs / "private")
    os.symlink("src", tmpfs / "private")
    header = tmp_path / "control" / "checkpoint.json"

    committed = _checkpoint(tmpfs, clone, header)

    assert (committed, freeze_tree(clone, _RESERVED).digest) == (
        read_checkpoint_header(header),
        freeze_tree(tmpfs).digest,
    )
    assert (committed.state, committed.manifest_digest) == ("committed", freeze_tree(tmpfs).digest)


def test_checkpoint_never_follows_a_disk_symlink_component(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, clone / "sub")
    (tmpfs / "sub").mkdir()
    (tmpfs / "sub" / "file").write_text("guest\n")

    _checkpoint(tmpfs, clone, tmp_path / "header.json")

    assert (list(outside.iterdir()), (clone / "sub").is_symlink()) == ([], False)


def test_checkpoint_copies_a_guest_symlink_without_following_it(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    secret = tmp_path / "secret"
    secret.write_text("host secret\n")
    os.symlink(secret, tmpfs / "leak")

    _checkpoint(tmpfs, clone, tmp_path / "header.json")

    assert os.readlink(clone / "leak") == os.fspath(secret)


def test_checkpoint_flattens_tmpfs_hardlinks(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    (tmpfs / "a").write_bytes(b"shared")
    os.link(tmpfs / "a", tmpfs / "b")

    _checkpoint(tmpfs, clone, tmp_path / "header.json")

    assert [os.lstat(clone / name).st_nlink for name in ("a", "b")] == [1, 1]


def test_checkpoint_skips_and_counts_special_files(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    (clone / "pipe").write_text("stale\n")
    os.mkfifo(tmpfs / "pipe")
    listener = socket.socket(socket.AF_UNIX)
    previous = os.getcwd()
    try:
        os.chdir(tmpfs)
        listener.bind("sock")
    finally:
        os.chdir(previous)
        listener.close()
    header = tmp_path / "header.json"

    committed = _checkpoint(tmpfs, clone, header)

    assert (committed.skipped_special, sorted(os.listdir(clone))) == (2, [])


def test_checkpoint_never_writes_git(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    (clone / ".git").mkdir()
    (clone / ".git" / "HEAD").write_text("host\n")
    (tmpfs / ".git").mkdir()
    (tmpfs / ".git" / "HEAD").write_text("guest\n")

    _checkpoint(tmpfs, clone, tmp_path / "header.json")

    assert (clone / ".git" / "HEAD").read_text() == "host\n"


def test_checkpoint_refuses_an_entry_under_a_reserved_root(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    (tmpfs / ".orchestrate").mkdir()
    (tmpfs / ".orchestrate" / "state.json").write_text("{}")

    with pytest.raises(RunRefCheckpointError) as caught:
        _checkpoint(tmpfs, clone, tmp_path / "header.json")

    assert caught.value.code == "run_ref_environment_escape_rejected"


def test_checkpoint_refuses_bytes_beyond_the_budget(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    (tmpfs / "big").write_bytes(b"x" * 4096)

    with pytest.raises(RunRefCheckpointError) as caught:
        _checkpoint(tmpfs, clone, tmp_path / "header.json", max_bytes=4095)

    assert caught.value.code == "run_ref_environment_escape_rejected"


def _crash_mid_copy(tmpfs: Path, clone: Path, header: Path, *, effect: str, ordinal: int) -> None:
    (tmpfs / "a.txt").write_text("copied before the crash\n")
    os.mkdir(os.path.join(os.fsencode(tmpfs), b"z\xff"))
    with pytest.raises(RunRefCheckpointError):
        _checkpoint(tmpfs, clone, header, effect=effect, ordinal=ordinal)


def test_crash_between_phases_leaves_an_intent_header(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    header = tmp_path / "header.json"

    _crash_mid_copy(tmpfs, clone, header, effect="effect-2", ordinal=2)

    observed = read_checkpoint_header(header)
    assert (observed.state, observed.effect_identity, observed.ordinal) == ("intent", "effect-2", 2)


def test_preflight_repairs_an_intent_header_by_refreezing(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    header = tmp_path / "header.json"
    _crash_mid_copy(tmpfs, clone, header, effect="effect-2", ordinal=2)

    repaired = _preflight(header, clone)

    assert (repaired, repaired.manifest_digest) == (
        read_checkpoint_header(header),
        freeze_tree(clone, _RESERVED).digest,
    )
    assert (repaired.state, repaired.effect_identity, repaired.ordinal) == ("committed", "effect-2", 2)


def test_intent_naming_the_last_committed_attempt_is_refrozen(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    header = tmp_path / "header.json"
    (tmpfs / "first").write_text("1\n")
    _checkpoint(tmpfs, clone, header, effect="effect-1", ordinal=1)
    _crash_mid_copy(tmpfs, clone, header, effect="effect-1", ordinal=1)

    repaired = _preflight(header, clone)

    assert (repaired.state, repaired.effect_identity, repaired.ordinal, repaired.manifest_digest) == (
        "committed",
        "effect-1",
        1,
        freeze_tree(clone, _RESERVED).digest,
    )


def test_initial_header_is_committed_for_no_effect_at_ordinal_zero(tmp_path: Path) -> None:
    clone, _tmpfs = _roots(tmp_path)
    _clone_tree(clone)
    header = tmp_path / "header.json"
    baseline = freeze_tree(clone, _RESERVED).digest

    publish_initial_header(header, baseline)

    observed = read_checkpoint_header(header)
    assert (observed.state, observed.effect_identity, observed.ordinal, observed.manifest_digest) == (
        "committed",
        "none",
        0,
        baseline,
    )


def test_preflight_accepts_a_matching_committed_header(tmp_path: Path) -> None:
    clone, _tmpfs = _roots(tmp_path)
    _clone_tree(clone)
    os.chmod(clone / "tool", 0o755)
    header = tmp_path / "header.json"
    publish_initial_header(header, freeze_tree(clone, _RESERVED).digest)

    assert _preflight(header, clone) == read_checkpoint_header(header)


def test_preflight_refuses_a_committed_header_that_no_longer_matches(tmp_path: Path) -> None:
    clone, _tmpfs = _roots(tmp_path)
    (clone / "file").write_text("baseline\n")
    header = tmp_path / "header.json"
    publish_initial_header(header, freeze_tree(clone, _RESERVED).digest)
    (clone / "file").write_text("corrupted\n")

    with pytest.raises(RunRefCheckpointError) as caught:
        _preflight(header, clone)

    assert caught.value.code == "run_ref_environment_changed"


def test_workspace_manifest_matches_freeze_tree(tmp_path: Path) -> None:
    clone, _tmpfs = _roots(tmp_path)
    _clone_tree(clone)
    descriptor = _fd(clone)
    try:
        manifest = workspace_manifest(descriptor)
    finally:
        os.close(descriptor)

    assert manifest == freeze_tree(clone, _RESERVED)


def test_checkpoint_rewrites_inside_a_read_only_directory(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    (tmpfs / "ro").mkdir()
    (tmpfs / "ro" / "file").write_text("first\n")
    os.chmod(tmpfs / "ro", 0o555)
    header = tmp_path / "header.json"
    _checkpoint(tmpfs, clone, header, ordinal=1)
    os.chmod(tmpfs / "ro", 0o755)
    (tmpfs / "ro" / "file").write_text("second\n")
    os.chmod(tmpfs / "ro", 0o555)

    _checkpoint(tmpfs, clone, header, ordinal=2)

    assert ((clone / "ro" / "file").read_text(), stat.S_IMODE(os.lstat(clone / "ro").st_mode)) == (
        "second\n",
        0o555,
    )


_TEMP_NAME = re.compile(r"\.rr-[0-9a-f]{16}\.tmp")


def _temp_names(root: Path) -> list[str]:
    return [name for _dir, _dirs, files in os.walk(root) for name in files if _TEMP_NAME.fullmatch(name)]


def test_preflight_validates_an_intact_clone_with_setgid_and_setuid_modes(tmp_path: Path) -> None:
    clone, _tmpfs = _roots(tmp_path)
    _clone_tree(clone)
    os.chmod(clone / "private", 0o2750)
    if not stat.S_IMODE(os.lstat(clone / "private").st_mode) & stat.S_ISGID:
        pytest.skip("setgid directory mode is not settable here")
    header = tmp_path / "header.json"
    publish_initial_header(header, freeze_tree(clone, _RESERVED).digest)

    assert _preflight(header, clone).state == "committed"


def test_checkpoint_masks_setuid_bits_onto_the_clone(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    (tmpfs / "tool").write_bytes(b"#!/bin/sh\n")
    os.chmod(tmpfs / "tool", 0o4755)

    _checkpoint(tmpfs, clone, tmp_path / "header.json")

    assert stat.S_IMODE(os.lstat(clone / "tool").st_mode) == 0o755


def test_non_utf8_symlink_target_is_refused_and_the_clone_still_repairs(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    os.symlink(b"\xfftarget", os.path.join(os.fsencode(tmpfs), b"link"))
    header = tmp_path / "header.json"
    with pytest.raises(RunRefCheckpointError):
        _checkpoint(tmpfs, clone, header)

    assert _preflight(header, clone).state == "committed"


def test_a_guest_name_shaped_like_a_copier_temporary_is_refused(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    (tmpfs / ".rr-0123456789abcdef.tmp").write_text("guest\n")

    with pytest.raises(RunRefCheckpointError) as caught:
        _checkpoint(tmpfs, clone, tmp_path / "header.json")

    assert caught.value.code == "run_ref_environment_escape_rejected"


_KILLED_CHECKPOINT = """
import os, sys
from pathlib import Path
from orchestrator.workflow.run_ref import checkpoint
tmpfs, clone, header = sys.argv[1:4]
real_fchmod = os.fchmod
def crash(descriptor, mode):
    if os.path.isfile(f"/proc/self/fd/{descriptor}"):
        os.kill(os.getpid(), 9)
    real_fchmod(descriptor, mode)
os.fchmod = crash
source = os.open(tmpfs, os.O_RDONLY | os.O_DIRECTORY)
destination = os.open(clone, os.O_RDONLY | os.O_DIRECTORY)
checkpoint.checkpoint_workspace(source, destination, Path(header), effect_identity="effect-3", ordinal=3, max_bytes=1 << 20)
"""


def _kill_mid_copy(tmp_path: Path) -> tuple[Path, Path]:
    clone, tmpfs = _roots(tmp_path)
    (tmpfs / "sub").mkdir()
    (tmpfs / "sub" / "file").write_bytes(b"partial bytes\n")
    header = tmp_path / "header.json"
    killed = subprocess.run(
        [sys.executable, "-c", _KILLED_CHECKPOINT, str(tmpfs), str(clone), str(header)],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        check=False,
    )
    assert killed.returncode == -9
    return clone, header


def test_a_killed_checkpoint_leaves_an_intent_header_and_a_copier_temporary(tmp_path: Path) -> None:
    clone, header = _kill_mid_copy(tmp_path)

    assert (read_checkpoint_header(header).state, len(_temp_names(clone))) == ("intent", 1)


def test_preflight_after_a_killed_checkpoint_removes_copier_temporaries(tmp_path: Path) -> None:
    clone, header = _kill_mid_copy(tmp_path)

    repaired = _preflight(header, clone)

    assert (_temp_names(clone), repaired.state, repaired.manifest_digest) == (
        [],
        "committed",
        freeze_tree(clone, _RESERVED).digest,
    )


def test_a_failed_rename_leaves_no_copier_temporary(tmp_path: Path, monkeypatch) -> None:
    clone, tmpfs = _roots(tmp_path)
    (tmpfs / "file").write_text("bytes\n")
    real_replace = os.replace

    def refuse_copier_rename(source, destination, **kwargs):
        if "src_dir_fd" in kwargs:
            raise OSError("injected rename failure")
        return real_replace(source, destination, **kwargs)

    monkeypatch.setattr(os, "replace", refuse_copier_rename)
    with pytest.raises(OSError):
        _checkpoint(tmpfs, clone, tmp_path / "header.json")

    assert os.listdir(clone) == []


def test_a_deep_guest_tree_is_refused_and_the_clone_still_repairs(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    descriptor = _fd(tmpfs)
    for _ in range(600):
        os.mkdir("d", dir_fd=descriptor)
        child = os.open("d", os.O_RDONLY | os.O_DIRECTORY, dir_fd=descriptor)
        os.close(descriptor)
        descriptor = child
    os.close(descriptor)
    header = tmp_path / "header.json"
    with pytest.raises(RunRefCheckpointError) as caught:
        _checkpoint(tmpfs, clone, header)

    assert (caught.value.code, _preflight(header, clone).state) == (
        "run_ref_environment_escape_rejected",
        "committed",
    )


def test_checkpoint_refuses_entries_beyond_the_entry_bound(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    for index in range(5):
        (tmpfs / f"f{index}").write_text("x")
    source, destination = _fd(tmpfs), _fd(clone)
    try:
        with pytest.raises(RunRefCheckpointError) as caught:
            checkpoint_workspace(
                source, destination, tmp_path / "header.json",
                effect_identity="effect-1", ordinal=1, max_bytes=_BUDGET, max_entries=4,
            )
    finally:
        os.close(source)
        os.close(destination)

    assert caught.value.code == "run_ref_environment_escape_rejected"


def test_intent_repair_recounts_special_files(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    header = tmp_path / "header.json"
    _crash_mid_copy(tmpfs, clone, header, effect="effect-2", ordinal=2)
    os.mkfifo(clone / "pipe")

    assert _preflight(header, clone).skipped_special == 1


def _foreign_first_child(parent: str) -> str | None:
    try:
        names = sorted(os.listdir(parent))
        if names and os.lstat(os.path.join(parent, names[0])).st_dev != os.lstat(parent).st_dev:
            return names[0]
    except OSError:
        pass
    return None


def test_copier_refuses_a_source_entry_on_another_device() -> None:
    parent = "/sys/fs"
    if _foreign_first_child(parent) is None:
        pytest.skip("no mount point sorts first under /sys/fs on this host")
    descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(RunRefCheckpointError) as caught:
            workspace_manifest(descriptor)
    finally:
        os.close(descriptor)

    assert "pinned device" in caught.value.detail
