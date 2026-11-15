"""Confined run-ref workspace copier and two-phase checkpoint header.

The holder tmpfs and the host clone are both ordinary host directories here;
the copier only ever sees their retained root descriptors.
"""

from __future__ import annotations

import os
import socket
import stat
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.workspace import (
    RunRefCheckpointError,
    checkpoint_workspace,
    freeze_tree,
    preflight_checkpoint,
    publish_initial_header,
    read_checkpoint_header,
    seed_workspace,
    workspace_manifest,
)

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




























def _crash_mid_copy(tmpfs: Path, clone: Path, header: Path, *, effect: str, ordinal: int) -> None:
    (tmpfs / "a.txt").write_text("copied before the crash\n")
    os.mkdir(os.path.join(os.fsencode(tmpfs), b"z\xff"))
    with pytest.raises(RunRefCheckpointError):
        _checkpoint(tmpfs, clone, header, effect=effect, ordinal=ordinal)








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








