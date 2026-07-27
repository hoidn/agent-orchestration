"""Locked Git source resolution for the lean-pilot runner."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

from . import _runner_apparatus as apparatus
from . import workspace
from ._runner_types import RunnerError


_COMMIT_IDENTITY = re.compile(r"^commit:([0-9a-f]{40,64})$")


@dataclass(frozen=True)
class SourceBinding:
    repo: Path
    treeish: str
    archive_digest: str
    task_path: PurePosixPath
    task_digest: str


def _git_output(repo: Path, *args: str, text: bool) -> bytes | str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RunnerError("cannot inspect locked Git source") from exc


def preflight_source(lock: Mapping[str, object]) -> SourceBinding:
    archive = lock["archive"]
    task = lock["task"]
    if not isinstance(archive, Mapping) or not isinstance(task, Mapping):
        raise RunnerError("lock source binding is malformed")
    repo = apparatus.canonical_absolute_path(
        archive["repository_root"],
        label="archive.repository_root",
    )
    revision = archive["revision_identity"]
    if not isinstance(revision, str):
        raise RunnerError("archive.revision_identity is malformed")
    match = _COMMIT_IDENTITY.fullmatch(revision)
    if match is None:
        raise RunnerError("archive.revision_identity must be exact commit:<rev>")
    commit = match.group(1)
    subtree_text = archive["source_subtree_path"]
    tree_identity = archive["source_tree_identity"]
    source_path_text = task["source_path"]
    archive_digest = archive["archive_digest"]
    task_digest = task["brief_digest"]
    if not all(
        isinstance(value, str)
        for value in (
            subtree_text,
            tree_identity,
            source_path_text,
            archive_digest,
            task_digest,
        )
    ):
        raise RunnerError("lock source binding is malformed")
    subtree = PurePosixPath(subtree_text)
    source_path = PurePosixPath(source_path_text)
    try:
        treeish = workspace._verified_git_subtree(
            repo,
            commit,
            subtree,
            tree_identity,
        )
    except workspace.WorkspaceError as exc:
        raise RunnerError(str(exc)) from exc

    listing = _git_output(
        repo,
        "ls-tree",
        treeish,
        "--",
        source_path.as_posix(),
        text=True,
    )
    if not isinstance(listing, str):
        raise AssertionError("text Git command returned bytes")
    rows = listing.splitlines()
    if len(rows) != 1:
        raise RunnerError("archived task path must name exactly one regular file")
    metadata, separator, listed_path = rows[0].partition("\t")
    parts = metadata.split()
    if (
        not separator
        or listed_path != source_path.as_posix()
        or len(parts) != 3
        or parts[0] not in {"100644", "100755"}
        or parts[1] != "blob"
    ):
        raise RunnerError("archived task path must name exactly one regular file")
    data = _git_output(repo, "cat-file", "blob", parts[2], text=False)
    if not isinstance(data, bytes):
        raise AssertionError("binary Git command returned text")
    if apparatus.sha256_bytes(data) != task_digest:
        raise RunnerError("archived task digest mismatch")
    return SourceBinding(
        repo=repo,
        treeish=treeish,
        archive_digest=archive_digest,
        task_path=source_path,
        task_digest=task_digest,
    )
