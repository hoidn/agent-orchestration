"""Derive an exact, ordinary-clone runtime identity for pilot treatments."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from ._pilot_prepare_support import (
    PilotPreparationError,
    _commit,
    _fail,
    _git,
)


_GIT_OVERRIDE_KEYS = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_WORK_TREE",
)


def _require_ordinary_git_directory(repo: Path) -> Path:
    if repo == Path("/"):
        _fail("repository root must not be the filesystem root")
    git_dir = repo / ".git"
    try:
        identity = git_dir.lstat()
        resolved = git_dir.resolve(strict=True)
    except OSError as exc:
        raise PilotPreparationError(
            "repository .git directory is unreadable"
        ) from exc
    if (
        not stat.S_ISDIR(identity.st_mode)
        or stat.S_ISLNK(identity.st_mode)
        or resolved != git_dir
    ):
        _fail("repository must have an ordinary canonical .git directory")
    for name in ("alternates", "http-alternates"):
        if os.path.lexists(git_dir / "objects" / "info" / name):
            _fail(f"repository object {name} must be absent")
    if os.path.lexists(git_dir / "commondir"):
        _fail("repository common-dir indirection must be absent")
    return git_dir


def _require_detached_head(repo: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "symbolic-ref", "-q", "HEAD"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise PilotPreparationError("cannot read frozen Git apparatus") from exc
    if result.returncode == 0:
        _fail("repository HEAD must be detached")
    if result.returncode != 1:
        _fail("repository HEAD identity is unreadable")


def derive_treatment_runtime(repo: Path, revision: str) -> dict[str, Any]:
    """Validate one immutable ordinary clone and return its runtime binding."""

    if any(os.environ.get(name) for name in _GIT_OVERRIDE_KEYS):
        _fail("repository Git environment contains path overrides")
    _require_ordinary_git_directory(repo)
    if str(_git(repo, "rev-parse", "--show-toplevel")).strip() != repo.as_posix():
        _fail("repository root is not the Git top level")
    if str(_git(repo, "rev-parse", "--git-dir")).strip() != ".git":
        _fail("repository Git directory is indirect")
    if str(_git(repo, "rev-parse", "--git-common-dir")).strip() != ".git":
        _fail("repository common directory is indirect")

    exact_revision = _commit(repo, revision, "apparatus revision")
    _require_detached_head(repo)
    head = str(
        _git(repo, "rev-parse", "--verify", "HEAD^{commit}")
    ).strip()
    if head != exact_revision:
        _fail("repository HEAD differs from apparatus revision")
    tree = str(
        _git(repo, "rev-parse", "--verify", f"{exact_revision}^{{tree}}")
    ).strip()
    status = _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored=matching",
        text=False,
    )
    assert isinstance(status, bytes)
    if status:
        _fail("repository must be clean including ignored files")

    return {
        "import_root": repo.as_posix(),
        "revision_identity": f"commit:{exact_revision}",
        "tree_identity": f"git-tree:{tree}",
    }
