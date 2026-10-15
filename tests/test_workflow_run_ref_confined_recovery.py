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


def test_a_temporary_shaped_name_in_the_clone_is_host_side_corruption(tmp_path: Path) -> None:
    """The guest never writes the clone directly, so a copier-shaped name there is not guest-caused."""
    clone, tmpfs = _roots(tmp_path)
    header = tmp_path / "header.json"
    publish_initial_header(header, workspace_manifest(_fd(clone)).digest)
    (clone / ".rr-0123456789abcdef.tmp").write_text("left on host disk\n")

    with pytest.raises(RunRefCheckpointError) as seeded:
        _seed(clone, tmpfs)
    with pytest.raises(RunRefCheckpointError) as preflighted:
        _preflight(header, clone)

    assert (seeded.value.code, preflighted.value.code) == (
        "run_ref_environment_changed", "run_ref_environment_changed")


def test_seed_checks_the_profile_entry_bound(tmp_path: Path) -> None:
    clone, tmpfs = _roots(tmp_path)
    for index in range(5):
        (clone / f"f{index}").write_text("x")
    source, destination = _fd(clone), _fd(tmpfs)
    try:
        with pytest.raises(RunRefCheckpointError) as caught:
            seed_workspace(source, destination, max_bytes=_BUDGET, max_entries=4)
    finally:
        os.close(source)
        os.close(destination)

    assert caught.value.code == "run_ref_environment_changed"


def _deep_tree(root: Path, depth: int) -> None:
    current = root
    for index in range(depth):
        current = current / f"d{index}"
        current.mkdir()
    (current / "leaf").write_text("x")


def test_seed_refuses_a_deep_clone_as_environment_changed(tmp_path: Path) -> None:
    from orchestrator.workflow.run_ref.checkpoint import MAX_TREE_DEPTH

    clone, tmpfs = _roots(tmp_path)
    _deep_tree(clone, MAX_TREE_DEPTH + 1)
    source, destination = _fd(clone), _fd(tmpfs)
    try:
        with pytest.raises(RunRefCheckpointError) as caught:
            seed_workspace(source, destination, max_bytes=_BUDGET)
    finally:
        os.close(source)
        os.close(destination)

    assert caught.value.code == "run_ref_environment_changed"


def test_checkpoint_refuses_a_deep_guest_tree_as_escape_rejected(tmp_path: Path) -> None:
    from orchestrator.workflow.run_ref.checkpoint import MAX_TREE_DEPTH

    clone, tmpfs = _roots(tmp_path)
    _deep_tree(tmpfs, MAX_TREE_DEPTH + 1)

    with pytest.raises(RunRefCheckpointError) as caught:
        _checkpoint(tmpfs, clone, tmp_path / "header.json")

    assert caught.value.code == "run_ref_environment_escape_rejected"


def test_clone_manifest_refuses_a_deep_clone_as_environment_changed(tmp_path: Path) -> None:
    from orchestrator.workflow.run_ref.checkpoint import MAX_TREE_DEPTH

    clone, _tmpfs = _roots(tmp_path)
    _deep_tree(clone, MAX_TREE_DEPTH + 1)
    descriptor = _fd(clone)
    try:
        with pytest.raises(RunRefCheckpointError) as caught:
            workspace_manifest(descriptor, clone=True)
    finally:
        os.close(descriptor)

    assert caught.value.code == "run_ref_environment_changed"


from dataclasses import replace
import json
import time

import pytest

from orchestrator.workflow.run_ref import ledger
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from tests.test_workflow_run_ref_ledger import _allocated_bindings, _visit


def test_v2_budget_events_coexist_with_byte_preserved_v1(tmp_path):
    path = tmp_path / "ledger.jsonl"
    v1 = ledger.allocate_attempt(path, visit=_visit(), bindings=_allocated_bindings(tmp_path))
    original = path.read_bytes()
    visit = replace(_visit(), step_id="confined")
    bindings = replace(_allocated_bindings(tmp_path), workspace_path=tmp_path / 'run-ref-root' / 'confined',
                       child_run_id='confined')
    allocated = ledger.allocate_attempt(path, visit=visit, bindings=bindings,
        confined_opening=dict(limit_ns=1000, boot_id='boot-a', since_ns=100))
    closed = ledger.append_confined_event(path, visit=visit, attempt_ordinal=1,
        event_kind='budget_close', event=dict(opening_sequence=allocated.sequence, boot_id='boot-a', until_ns=450))
    assert path.read_bytes().startswith(original)
    assert ledger.load_attempt_ledger(path).rows[0] == v1
    state = ledger.confined_budget(ledger.load_attempt_ledger(path).rows, visit)
    assert state == dict(limit_ns=1000, charged_ns=350, active=None, closure_digest=closed.row_digest)
    assert closed.stage == 'allocated'
    assert closed.bindings == allocated.bindings


def test_budget_close_is_not_repeated_after_crash_and_closed_pause_is_free(tmp_path):
    path = tmp_path / 'ledger.jsonl'
    visit = _visit()
    first = ledger.allocate_attempt(path, visit=visit, bindings=_allocated_bindings(tmp_path),
        confined_opening=dict(limit_ns=1000, boot_id='boot-a', since_ns=100))
    ledger.append_confined_event(path, visit=visit, attempt_ordinal=1, event_kind='budget_close',
        event=dict(opening_sequence=first.sequence, boot_id='boot-a', until_ns=300))
    with pytest.raises(ledger.RunRefLedgerError):
        ledger.append_confined_event(path, visit=visit, attempt_ordinal=1, event_kind='budget_close',
            event=dict(opening_sequence=first.sequence, boot_id='boot-a', until_ns=400))
    reopened = ledger.append_confined_event(path, visit=visit, attempt_ordinal=1, event_kind='budget_open',
        event=dict(boot_id='boot-b', since_ns=10000))
    ledger.append_confined_event(path, visit=visit, attempt_ordinal=1, event_kind='budget_close',
        event=dict(opening_sequence=reopened.sequence, boot_id='boot-b', until_ns=10050))
    assert ledger.confined_budget(ledger.load_attempt_ledger(path).rows, visit)['charged_ns'] == 250


@pytest.mark.parametrize('boot,until', [('boot-b', 200), ('boot-a', 99)])
def test_budget_rejects_epoch_or_backward_clock_without_changing_ledger(tmp_path, boot, until):
    path = tmp_path / 'ledger.jsonl'
    first = ledger.allocate_attempt(path, visit=_visit(), bindings=_allocated_bindings(tmp_path),
        confined_opening=dict(limit_ns=1000, boot_id='boot-a', since_ns=100))
    original = path.read_bytes()
    with pytest.raises(ledger.RunRefLedgerError):
        ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=1, event_kind='budget_close',
            event=dict(opening_sequence=first.sequence, boot_id=boot, until_ns=until))
    assert path.read_bytes() == original


def test_mixing_row_versions_inside_an_attempt_is_rejected(tmp_path):
    path = tmp_path / 'ledger.jsonl'
    ledger.allocate_attempt(path, visit=_visit(), bindings=_allocated_bindings(tmp_path),
        confined_opening=dict(limit_ns=1000, boot_id='boot-a', since_ns=100))
    ledger.advance_attempt(path, visit=_visit(), attempt_ordinal=1, stage='materialized',
        binding_updates={'verified_git_tree_id': 'git-tree:' + 'a' * 40})
    rows = [json.loads(row) for row in path.read_bytes().splitlines()]
    rows[-1].pop('event_kind')
    rows[-1].pop('event')
    rows[-1]['schema_version'] = ledger.RUN_REF_ATTEMPT_LEDGER_SCHEMA
    rows[-1]['row_digest'] = canonical_sha256({k:v for k,v in rows[-1].items() if k != 'row_digest'})
    path.write_bytes(b''.join(canonical_json_bytes(row) + b'\n' for row in rows))
    with pytest.raises(ledger.RunRefLedgerError, match='version'):
        ledger.load_attempt_ledger(path)


def test_recovery_inventory_validates_exact_scope_before_killing_or_checkpoint(tmp_path, monkeypatch):
    from orchestrator.workflow.run_ref import holder_scope
    from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
    control = tmp_path / 'holder'
    control.mkdir(mode=0o700)
    scope = tmp_path / 'run-ref-' / 'run-ref-aaaaaaaaaaaaaaaa.scope'
    scope.mkdir(parents=True)
    token = 'sha256:' + 'a' * 64
    inventory = dict(schema_version='run_ref_holder_scope.v1', boot_id='boot-a',
        scope_path=str(scope), unit=scope.name, launch_token=token,
        containment_identity='sha256:' + 'b' * 64)
    (control / 'scope-aaaaaaaaaaaaaaaa.json').write_bytes(canonical_json_bytes(inventory))
    killed = []
    monkeypatch.setattr(holder_scope, 'boot_id', lambda: 'boot-a')
    monkeypatch.setattr(holder_scope, 'CGROUP_MOUNT', tmp_path)
    monkeypatch.setattr(holder_scope.CgroupV2ContainmentRoot, 'from_scope_path',
        lambda *args, **kwargs: type('Root', (), {'identity_digest': 'sha256:' + 'c' * 64})())
    monkeypatch.setattr(holder_scope, 'kill_cgroup', lambda path: killed.append(path) or True)
    from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
    with pytest.raises(RunRefRuntimeError, match='scope_identity_changed'):
        holder_scope.recover_holder_scopes(control)
    assert killed == []


def test_old_boot_scope_name_never_authorizes_kill(tmp_path, monkeypatch):
    from orchestrator.workflow.run_ref import holder_scope
    control = tmp_path / 'holder'
    control.mkdir(mode=0o700)
    record = dict(schema_version='run_ref_holder_scope.v1', boot_id='old-boot',
        scope_path='/sys/fs/cgroup/run-ref-aaaaaaaaaaaaaaaa.scope', unit='run-ref-aaaaaaaaaaaaaaaa.scope',
        launch_token='sha256:' + 'a' * 64, containment_identity='sha256:' + 'b' * 64)
    (control / 'scope-aaaaaaaaaaaaaaaa.json').write_bytes(canonical_json_bytes(record))
    monkeypatch.setattr(holder_scope, 'boot_id', lambda: 'new-boot')
    monkeypatch.setattr(holder_scope, 'kill_cgroup', lambda path: pytest.fail('old boot must not authorize kill'))
    assert holder_scope.recover_holder_scopes(control) is False


class InjectedControllerCrash(BaseException):
    pass


def test_retained_completed_child_is_reused_before_parent_commit(world, monkeypatch):
    from tests.test_workflow_run_ref_confined_child import _run, _cli, FakeHolder, _site
    from orchestrator.workflow.run_ref import runtime
    original = runtime.persist_run_ref_lifecycle_event
    def interrupt(request, event):
        ack = original(request, event)
        if event.stage == 'child_completed':
            raise InjectedControllerCrash()
        return ack
    with monkeypatch.context() as patch:
        patch.setattr(runtime, 'persist_run_ref_lifecycle_event', interrupt)
        with pytest.raises(InjectedControllerCrash):
            _run(world)
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    before = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
    FakeHolder.launched.clear()
    assert _cli('resume', run_root.name, '--run-ref-root', str(world['refs'])) == 0
    after = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
    assert (after.attempt_ordinal, after.bindings.child_run_id, after.bindings.workspace_path) == (
        before.attempt_ordinal, before.bindings.child_run_id, before.bindings.workspace_path)
    assert FakeHolder.launched == []


from tests.test_workflow_run_ref_confined_child import world  # noqa: E402,F401
from tests.test_workflow_run_ref_confinement import _removable_tmp  # noqa: E402,F401


@pytest.mark.parametrize('gap', ['first_commit', 'failed_row', 'child_terminal', 'pending'])
def test_recovery_reuses_durable_child_evidence_without_repeating_commits(world, monkeypatch, gap):
    from tests.test_workflow_run_ref_confined_child import _run, _cli, FakeHolder, _child_memo
    from orchestrator.workflow.run_ref import runtime
    from orchestrator.workflow.evaluated import runtime as child_runtime
    original_event, original_memo = runtime.persist_run_ref_lifecycle_event, child_runtime.append_record
    def event_gap(request, event):
        ack = original_event(request, event)
        if ((gap == 'failed_row' and event.event_kind == 'failed_terminal')
                or (gap == 'pending' and event.stage == 'completed_pending_parent_commit')):
            raise InjectedControllerCrash()
        return ack
    def memo_gap(path, record, **kwargs):
        result = original_memo(path, record, **kwargs)
        authority = kwargs.get('checked_authority')
        if authority is not None and authority.confined and (
                (gap == 'first_commit' and record['record'] == 'committed')
                or (gap == 'child_terminal' and record['record'] == 'terminal')):
            raise InjectedControllerCrash()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(runtime, 'persist_run_ref_lifecycle_event', event_gap)
        patch.setattr(child_runtime, 'append_record', memo_gap)
        with pytest.raises(InjectedControllerCrash):
            _run(world, **({'second': 'touch late.txt # kill-the-holder'} if gap == 'failed_row' else {}))
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    before = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
    child_root = run_root / 'run-ref-children' / before.bindings.child_run_id
    committed = {key: entry.data for key, entry in _child_memo(child_root).active_commits.items()}
    count = len(FakeHolder.leaves)
    assert _cli('resume', run_root.name, '--run-ref-root', str(world['refs'])) == 0
    after = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
    recovered = _child_memo(child_root)
    assert (after.attempt_ordinal, after.bindings.workspace_path) == (1, before.bindings.workspace_path)
    assert {key: recovered.active_commits[key].data for key in committed} == committed
    assert len(FakeHolder.leaves) - count == (1 if gap == 'first_commit' else 0)
    assert recovered.terminal.data['outcome'] == ('failed' if gap == 'failed_row' else 'completed')


def test_pure_completed_zero_commit_is_terminal_before_k4(world, monkeypatch):
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.run_ref import evaluated_child
    original_write, original_execute = fixture._write, evaluated_child.execute_confined_child
    def pure_write(world, **kwargs):
        original_write(world, **kwargs)
        path = world['parent'] / 'controller.orc'
        source = path.read_text()
        first = source.index('  (defworkflow candidate-body')
        last = source.index('  (defworkflow run', first)
        path.write_text(source[:first] + '  (defworkflow candidate-body ((seed Int)) -> Int (+ seed 1))\n' + source[last:])
    def terminal_gap(*args, **kwargs):
        original_execute(*args, **kwargs)
        raise InjectedControllerCrash()
    with monkeypatch.context() as patch:
        patch.setattr(fixture, '_write', pure_write)
        patch.setattr(confined_lifecycle_for_tests(), 'execute_confined_child', terminal_gap)
        with pytest.raises(InjectedControllerCrash):
            fixture._run(world)
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    before = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
    assert fixture._cli('resume', run_root.name, '--run-ref-root', str(world['refs'])) == 0
    after = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
    assert (after.attempt_ordinal, after.bindings.child_run_id, fixture.FakeHolder.launched) == (
        1, before.bindings.child_run_id, [])


def confined_lifecycle_for_tests():
    from orchestrator.workflow.run_ref import confined_lifecycle
    return confined_lifecycle


@pytest.mark.parametrize('boundary', ['started_attempt', 'before_start', 'pure_fault', 'finalization'])
def test_four_failed_boundaries_are_durable_before_child_terminal(world, monkeypatch, boundary):
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.run_ref import confined_session, confined_budget
    from orchestrator.workflow.evaluated import runtime as child_runtime
    original_write = fixture._write
    observed = []
    original_append = child_runtime.append_record
    def append(path, record, **kwargs):
        authority = kwargs.get('checked_authority')
        if authority is not None and authority.confined and record['record'] in {'failed', 'terminal'}:
            run_root = authority.run_root.parent.parent
            rows = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows
            proof = next(row for row in reversed(rows) if row.event_kind == 'failed_terminal')
            observed.append(proof.event['boundary']['kind'])
        return original_append(path, record, **kwargs)
    def write(world, **kwargs):
        original_write(world, **kwargs)
        if boundary == 'pure_fault':
            path = world['parent'] / 'controller.orc'
            source = path.read_text()
            first, last = source.index('  (defworkflow candidate-body'), source.index('  (defworkflow run')
            path.write_text(source[:first] + '  (defworkflow candidate-body ((seed Int)) -> Int (let* ((bad (/ 1.0 (int/to-float (- seed seed))))) seed))\n' + source[last:])
    if boundary == 'finalization':
        original_stop = fixture.FakeHolder.stop
        def stop(holder):
            original_stop(holder)
            # Advance only the fixed budget clock through final shutdown; no host sleep needed.
            real = confined_budget.boottime_ns
            monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: real() + 61_000_000_000)
        monkeypatch.setattr(fixture.FakeHolder, 'stop', stop)
    monkeypatch.setattr(fixture, '_write', write)
    monkeypatch.setattr(child_runtime, 'append_record', append)
    edits = {'second': 'touch late.txt # kill-the-holder'} if boundary == 'started_attempt' else (
        {'first_exe': './tool.sh'} if boundary == 'before_start' else {})
    status, (authority, memo) = fixture._run(world, **edits)
    assert status == 0
    assert fixture._site(memo)['value']['variant'] == 'FAILED'
    assert observed and set(observed) == {boundary}
    proof = next(row for row in ledger.load_attempt_ledger(authority.run_root / 'run-ref-attempts.jsonl').rows
                 if row.event_kind == 'failed_terminal')
    assert proof.event['boundary']['kind'] == boundary
    if boundary in {'pure_fault', 'finalization', 'before_start'}:
        assert proof.event['effect_failure'] is None


@pytest.mark.parametrize('child_committed', [False, True])
def test_invalidate_is_available_only_before_confined_child_first_commit(world, monkeypatch, child_committed):
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.evaluated import runtime as child_runtime
    from orchestrator.workflow.run_ref import confined_lifecycle
    original_write, original_append = fixture._write, child_runtime.append_record
    def write(world, **kwargs):
        original_write(world, **kwargs)
        parent = world['parent']
        source = (parent / 'controller.orc').read_text().replace('(let* ((child (run-ref',
            '(let* ((pre (command-result pre :argv ("sh" "pre.sh") :returns Int)) (child (run-ref')
        (parent / 'controller.orc').write_text(source)
        (parent / 'pre.sh').write_text('echo 1 > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n')
        boundaries = json.loads((parent / 'boundaries.json').read_text())
        boundaries['pre'] = dict(stable_command=['sh', 'pre.sh'], closure=['pre.sh'])
        (parent / 'boundaries.json').write_text(json.dumps(boundaries))
    def append(path, record, **kwargs):
        authority = kwargs.get('checked_authority')
        if authority is not None and authority.confined:
            if not child_committed and record['record'] == 'started':
                raise InjectedControllerCrash()
        result = original_append(path, record, **kwargs)
        if authority is not None and authority.confined and child_committed and record['record'] == 'committed':
            raise InjectedControllerCrash()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(fixture, '_write', write)
        patch.setattr(child_runtime, 'append_record', append)
        from orchestrator.workflow.evaluated import attempts
        patch.setattr(attempts, 'append_record', append)
        with pytest.raises(InjectedControllerCrash):
            fixture._run(world)
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo
    authority = load_run_authority(run_root)
    memo = read_memo(authority.memo_path, site_classes(authority.program))
    pre, = memo.active_commits.values()
    before = authority.memo_path.read_bytes()
    status = fixture._cli('invalidate', run_root.name, pre.data['identity'])
    assert (status == 0) is (not child_committed)
    if child_committed:
        assert authority.memo_path.read_bytes() == before
    else:
        assert fixture._cli('resume', run_root.name, '--run-ref-root', str(world['refs'])) == 0


@pytest.mark.parametrize('resolution', ['remaining', 'exhausted', 'failed_proof'])
def test_nonrepeatable_pending_start_requires_retry_only_for_continuation(world, monkeypatch, resolution):
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.evaluated import attempts
    from orchestrator.workflow.run_ref import runtime, confined_budget
    original_write, original_append = fixture._write, attempts.append_record
    original_persist = runtime.persist_run_ref_lifecycle_event
    def write(world, **kwargs):
        original_write(world, **kwargs)
        path = world['parent'] / 'boundaries.json'
        rows = json.loads(path.read_text())
        rows['second']['must_not_repeat'] = True
        path.write_text(json.dumps(rows))
    starts = 0
    def append(path, record, **kwargs):
        nonlocal starts
        result = original_append(path, record, **kwargs)
        authority = kwargs.get('checked_authority')
        if authority is not None and authority.confined and record['record'] == 'started':
            starts += 1
            if starts == 2 and resolution != 'failed_proof':
                if resolution == 'exhausted':
                    real = confined_budget.boottime_ns
                    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: real() + 61_000_000_000)
                raise InjectedControllerCrash()
        return result
    def persist(request, event):
        result = original_persist(request, event)
        if event.event_kind == 'failed_terminal':
            raise InjectedControllerCrash()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(fixture, '_write', write)
        patch.setattr(attempts, 'append_record', append)
        if resolution == 'failed_proof':
            patch.setattr(runtime, 'persist_run_ref_lifecycle_event', persist)
        with pytest.raises(InjectedControllerCrash):
            fixture._run(world, **({'second': 'touch late.txt # kill-the-holder'} if resolution == 'failed_proof' else {}))
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    holders, leaves = len(fixture.FakeHolder.launched), len(fixture.FakeHolder.leaves)
    status = fixture._cli('resume', run_root.name, '--run-ref-root', str(world['refs']))
    assert (status == 0) is (resolution != 'remaining')
    assert (len(fixture.FakeHolder.launched), len(fixture.FakeHolder.leaves)) == (holders, leaves)
    rows = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows
    failed = [row for row in rows if row.event_kind == 'failed_terminal']
    assert bool(failed) is (resolution != 'remaining')
    if failed:
        assert failed[0].event['boundary']['kind'] == 'started_attempt'


def test_fixed_boottime_charges_suspension_and_rejects_open_cross_boot(monkeypatch):
    from orchestrator.workflow.run_ref import confined_budget
    from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
    state = dict(limit_ns=1000, charged_ns=100,
        active=dict(boot_id='boot-a', since_ns=200, attempt_ordinal=1, opening_sequence=1), closure_digest=None)
    monkeypatch.setattr(confined_budget, 'boot_id', lambda: 'boot-a')
    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: 750)
    monkeypatch.setattr(time, 'time', lambda: -10**10)  # UTC does not participate
    assert confined_budget.remaining_ns(state) == 350
    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: 850)  # includes suspension/downtime
    assert confined_budget.remaining_ns(state) == 250
    monkeypatch.setattr(confined_budget, 'boot_id', lambda: 'boot-b')
    with pytest.raises(RunRefRuntimeError, match='budget_clock_epoch_changed'):
        confined_budget.remaining_ns(state)
    assert confined_budget.remaining_ns(dict(state, active=None)) == 900


@pytest.mark.parametrize('change', ['impossible_identity', 'manifest_drift', 'intent'])
def test_retained_checkpoint_identity_and_manifest_are_independent(world, monkeypatch, caplog, change):
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.evaluated import runtime as child_runtime
    original = child_runtime.append_record
    def interrupt(path, row, **kwargs):
        result = original(path, row, **kwargs)
        authority = kwargs.get('checked_authority')
        if authority is not None and authority.confined and row['record'] == 'committed':
            raise InjectedControllerCrash()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(child_runtime, 'append_record', interrupt)
        with pytest.raises(InjectedControllerCrash):
            fixture._run(world)
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    head = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
    header_path = run_root / 'run-ref-children' / head.bindings.child_run_id / 'checkpoint.json'
    header = json.loads(header_path.read_text())
    if change == 'impossible_identity':
        header['effect_identity'], header['ordinal'] = 'a' * 64, 17
    elif change == 'manifest_drift':
        (head.bindings.workspace_path / 'out.txt').write_text('host drift')
    else:
        header['state'], header['manifest_digest'] = 'intent', None
    header_path.write_bytes(canonical_json_bytes(header))
    before = len(fixture.FakeHolder.launched)
    status = fixture._cli('resume', run_root.name, '--run-ref-root', str(world['refs']))
    if change == 'intent':
        assert status == 0
        assert json.loads(header_path.read_text())['state'] == 'committed'
    else:
        assert status != 0
        code = 'run_ref_evidence_invalid' if change == 'impossible_identity' else 'run_ref_environment_changed'
        assert code in caplog.text
        assert len(fixture.FakeHolder.launched) == before
        assert not [row for row in ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows
                    if row.event_kind == 'failed_terminal']


def test_committed_script_inputs_replay_from_snapshot_after_later_leaf_edits(world, monkeypatch):
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.run_ref import runtime
    original = runtime.persist_run_ref_lifecycle_event
    def interrupt(request, event):
        ack = original(request, event)
        if event.stage == 'child_completed':
            raise InjectedControllerCrash()
        return ack
    with monkeypatch.context() as patch:
        patch.setattr(runtime, 'persist_run_ref_lifecycle_event', interrupt)
        with pytest.raises(InjectedControllerCrash):
            fixture._run(world, second='echo changed > first.sh; ' + fixture.SECOND)
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    dispatched = len(fixture.FakeHolder.leaves)
    assert fixture._cli('resume', run_root.name, '--run-ref-root', str(world['refs'])) == 0
    assert len(fixture.FakeHolder.leaves) == dispatched


def test_holder_socket_wait_rechecks_boottime_after_each_short_wait(monkeypatch):
    from orchestrator.workflow.run_ref import holder_scope
    scope = object.__new__(holder_scope.HolderScope)
    scope._buffer = b''
    now, waits = [0], []
    class Socket:
        def settimeout(self, timeout):
            waits.append(timeout)
        def recv(self, _count):
            if len(waits) == 2:
                now[0] = 2_000_000_000
            raise holder_scope.socket.timeout()
    scope.ctrl = Socket()
    monkeypatch.setattr(holder_scope, 'boottime_ns', lambda: now[0], raising=False)
    with pytest.raises(TimeoutError):
        scope.line(1.0)
    assert waits == [.1, .1]


@pytest.mark.parametrize('wall', [3, 10])
def test_k4_inherits_visit_charge_but_not_previous_ordinal_release(world, monkeypatch, wall):
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.run_ref import confined_budget, confined_lifecycle
    from orchestrator.workflow.evaluated import attempts
    now = [0]
    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: now[0])
    original_copy, original_append = confined_lifecycle._snapshot_baseline, attempts.append_record
    def copy(*args):
        value = original_copy(*args)
        now[0] += 2_000_000_000
        return value
    def append(path, row, **kwargs):
        result = original_append(path, row, **kwargs)
        authority = kwargs.get('checked_authority')
        if authority is not None and authority.confined and row['record'] == 'started':
            raise InjectedControllerCrash()
        return result
    monkeypatch.setattr(confined_lifecycle, '_snapshot_baseline', copy)
    with monkeypatch.context() as patch:
        patch.setattr(attempts, 'append_record', append)
        with pytest.raises(InjectedControllerCrash):
            fixture._run(world, wall=wall)
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    status = fixture._cli('resume', run_root.name, '--run-ref-root', str(world['refs']))
    rows = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows
    assert rows[-1].attempt_ordinal == 2
    state = ledger.confined_budget(rows, rows[-1].visit)
    assert state['charged_ns'] == 4_000_000_000
    assert state['active'] is None
    assert (status == 0) is (wall == 10)
    assert not [row for row in rows if row.event_kind == 'failed_terminal']
    assert len(fixture.FakeHolder.launched) == (2 if wall == 10 else 1)


def test_invalidation_retires_only_later_pending_projection_and_keeps_retry_history():
    from orchestrator.workflow.evaluated.memo import reduce_memo
    from orchestrator.workflow.evaluated.attempts import attempt_paths
    from orchestrator.workflow.evaluated.effect_inputs import _retry_baseline
    from tests.test_workflow_evaluated_memo import _started, _committed, _line
    before, anchor, after = ('workflow:demo::run / ' + name for name in ('before', 'anchor', 'after'))
    rows = [_started(before), _started(anchor), _committed(anchor), _started(after)]
    raw = b''.join(_line(row) for row in rows)
    memo = reduce_memo(raw, {name: 'command' for name in (before, anchor, after)})
    anchor_offset = memo.active_commits[anchor].offset
    retired = reduce_memo(raw + _line(dict(record='invalidated', from_commit=anchor_offset, time=3.0)),
                          {name: 'command' for name in (before, anchor, after)})
    assert set(retired.pending_starts) == {before}
    assert retired.latest_starts == memo.latest_starts
    assert retired.entries[:len(memo.entries)] == memo.entries
    assert attempt_paths(retired, after)[0] == 2
    assert _retry_baseline(retired, after, retired.latest_starts[after]) == memo.latest_starts[after]


@pytest.mark.parametrize('policy', ['repeatable', 'never', 'implementation_changed'])
def test_invalidated_pending_history_still_enforces_c4_and_repeat_permission(tmp_path, monkeypatch, policy, caplog):
    from contextlib import closing
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    from tests.test_workflow_evaluated_command_lifecycle import _program, _publish
    from orchestrator.workflow.evaluated import runtime, attempts
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo, invalidate_suffix
    for name in ('first', 'second'):
        (tmp_path / f'{name}.py').write_text('import os\nfrom pathlib import Path\n'
            f'Path("{name}-calls").open("a").write("x")\n'
            'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("1")\n')
    _source, program = _program(tmp_path,
        '(let* ((a (command-result first :argv ("python" "first.py") :returns Int)) '
        '(b (command-result second :argv ("python" "second.py") :returns Int))) (+ a b))',
        bindings={'first': 'first.py', 'second': 'second.py'}, must_not_repeat=policy == 'never')
    original = attempts.append_record
    starts = 0
    def interrupt(path, row, **kwargs):
        nonlocal starts
        result = original(path, row, **kwargs)
        if row['record'] == 'started':
            starts += 1
            if starts == 2:
                raise InjectedControllerCrash()
        return result
    with _publish(tmp_path, program) as authority:
        with closing(WorkspaceFiles(authority.run_root)) as files:
            authority = replace(authority, run_files=files)
            with monkeypatch.context() as patch:
                patch.setattr(attempts, 'append_record', interrupt)
                with pytest.raises(InjectedControllerCrash):
                    runtime.execute_pure_run(authority, {}, run_id='run-1', workspace=tmp_path)
            snapshot = read_memo(authority.memo_path, site_classes(program))
            first, = snapshot.active_commits
            pending, = snapshot.pending_starts
            invalidate_suffix(authority.memo_path, first, site_classes(program), run_files=files, checked_authority=authority)
            retired = read_memo(authority.memo_path, site_classes(program))
            assert not retired.pending_starts
            assert retired.latest_starts[pending] == snapshot.latest_starts[pending]
            if policy == 'implementation_changed':
                with (tmp_path / 'second.py').open('a') as stream:
                    stream.write('# implementation changed before retry\n')
            status, _value = runtime.execute_pure_resume(authority, {}, run_id='run-1', workspace=tmp_path)
            assert (status == 0) is (policy == 'repeatable')
            assert (tmp_path / 'first-calls').read_text() == 'xx'
            assert (tmp_path / 'second-calls').exists() is (policy == 'repeatable')
            if policy == 'never':
                assert 'lexical_restore_pending_effect_unsafe' in caplog.text
            elif policy == 'implementation_changed':
                assert 'effect_input_diverged' in caplog.text


@pytest.mark.parametrize('outcome', ['completed', 'failed', 'retained'])
def test_confined_events_keep_parallel_grant_validation_and_exact_acks(world, monkeypatch, outcome):
    """Protocol checks only: public confined run-ref placement in parallel maps remains forbidden."""
    import threading
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.evaluated import run_ref as adapter, runtime as child_runtime
    from orchestrator.workflow.run_ref import runtime
    kinds, writers = [], []
    coordinator = threading.get_ident()
    def prepare(request):
        allocation, started = runtime.prepare_run_ref_lifecycle_allocation(request)
        lifecycle = request, allocation, started
        sequence, previous = 0, None
        def acknowledge(event):
            nonlocal sequence, previous
            sequence += 1
            previous = adapter.persist_parallel_run_ref_event(lifecycle, event, sequence, previous)
            kinds.append(event.event_kind)
            writers.append(threading.get_ident())
            return previous
        return runtime.drive_run_ref_lifecycle(request, allocation=allocation, acknowledge=acknowledge,
                                              started_monotonic_ns=started)
    monkeypatch.setattr(adapter, 'prepare_run_ref_settlement', prepare)
    if outcome == 'retained':
        original = child_runtime.append_record
        def interrupt(path, row, **kwargs):
            result = original(path, row, **kwargs)
            authority = kwargs.get('checked_authority')
            if authority is not None and authority.confined and row['record'] == 'committed':
                raise InjectedControllerCrash()
            return result
        with monkeypatch.context() as patch:
            patch.setattr(child_runtime, 'append_record', interrupt)
            with pytest.raises(InjectedControllerCrash):
                fixture._run(world)
        run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
        assert fixture._cli('resume', run_root.name, '--run-ref-root', str(world['refs'])) == 0
    else:
        status, (authority, memo) = fixture._run(world,
            **({'second': 'touch late.txt # kill-the-holder'} if outcome == 'failed' else {}))
        assert status == 0
        assert len(memo.active_commits) == len(memo.settlements) == 1
    assert writers and set(writers) == {coordinator}
    assert kinds.count('allocation') == 1
    assert kinds.count('budget_close') == (2 if outcome == 'retained' else 1)
    assert kinds.count('failed_terminal') == (1 if outcome == 'failed' else 0)


def test_allocation_ack_binds_the_exact_confined_opening(tmp_path):
    from orchestrator.workflow.run_ref import runtime
    opening = dict(limit_ns=1000, boot_id='boot-a', since_ns=10)
    bindings = _allocated_bindings(tmp_path)
    row = ledger.allocate_attempt(tmp_path / 'run-ref-attempts.jsonl', visit=_visit(), bindings=bindings,
        confined_opening=dict(opening, since_ns=20))
    event = runtime.RunRefLifecycleEvent.build(sequence=1, event_kind='allocation', stage='allocated',
        visit=_visit(), attempt_ordinal=1, effect_instance_root=tmp_path,
        payload=dict(bindings=bindings.record, confined_opening=opening))
    ack = runtime.RunRefLifecycleAcknowledgement._for_durable_row(event, authority=row)
    with pytest.raises(ValueError, match='opening'):
        runtime._validate_lifecycle_acknowledgement_authority(event=event, acknowledgement=ack)


def test_retained_attempt_exhausted_during_readmission_fails_without_new_holder(world, monkeypatch):
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.run_ref import confined_budget, confined_lifecycle
    from orchestrator.workflow.evaluated import runtime
    now = [0]
    monkeypatch.setattr(confined_budget, 'boottime_ns', lambda: now[0])
    original_append, original_admit = runtime.append_record, confined_lifecycle.admit_confined_child
    def interrupt(path, row, **kwargs):
        result = original_append(path, row, **kwargs)
        authority = kwargs.get('checked_authority')
        if authority is not None and authority.confined and row['record'] == 'committed':
            raise InjectedControllerCrash()
        return result
    with monkeypatch.context() as patch:
        patch.setattr(runtime, 'append_record', interrupt)
        with pytest.raises(InjectedControllerCrash):
            fixture._run(world)
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    holders = len(fixture.FakeHolder.launched)
    def admit(*args, **kwargs):
        value = original_admit(*args, **kwargs)
        now[0] += 61_000_000_000
        return value
    monkeypatch.setattr(confined_lifecycle, 'admit_confined_child', admit)
    assert fixture._cli('resume', run_root.name, '--run-ref-root', str(world['refs'])) == 0
    assert len(fixture.FakeHolder.launched) == holders
    proof = next(row for row in ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows
                 if row.event_kind == 'failed_terminal')
    assert (proof.event['code'], proof.event['boundary']['kind']) == ('run_ref_budget_exhausted', 'before_start')


def test_failed_repair_rejects_wrong_child_authority_before_writing_memo(world, monkeypatch):
    import tests.test_workflow_run_ref_confined_child as fixture
    from orchestrator.workflow.run_ref import runtime
    original = runtime.persist_run_ref_lifecycle_event
    def interrupt(request, event):
        ack = original(request, event)
        if event.event_kind == 'failed_terminal':
            raise InjectedControllerCrash()
        return ack
    with monkeypatch.context() as patch:
        patch.setattr(runtime, 'persist_run_ref_lifecycle_event', interrupt)
        with pytest.raises(InjectedControllerCrash):
            fixture._run(world, second='touch late.txt # kill-the-holder')
    run_root, = (world['parent'] / '.orchestrate' / 'runs').iterdir()
    head = ledger.load_attempt_ledger(run_root / 'run-ref-attempts.jsonl').rows[-1]
    child = run_root / 'run-ref-children' / head.bindings.child_run_id
    header = json.loads((child / 'run.json').read_text())
    header['resume_request']['entry_workflow'] = 'wrong::recipe'
    (child / 'run.json').write_bytes(canonical_json_bytes(header))
    before = (child / 'memo.jsonl').read_bytes()
    assert fixture._cli('resume', run_root.name, '--run-ref-root', str(world['refs'])) != 0
    assert (child / 'memo.jsonl').read_bytes() == before
