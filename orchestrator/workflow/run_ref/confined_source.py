"""Sanitized host Git materialization for `run_ref_confinement.v1` children.

Host Git runs with an environment built from scratch: no credential helpers, SSH
agent or default SSH identities, no global/system configuration, templates or
proxies. The clone's `.git` is rewritten into a self-contained repository with no
remote, hooks, reflogs or alternates, so nothing in it links back to a host path,
and there is no setup: the source manifest is the baseline and the revision's
setup identity is the literal `none`.

The host runs Git in a clone only here, before any guest process has had it. Once
a holder has been released over a clone, its `.git` is guest-controlled data: the
host never runs Git there again (delta, export and evidence use the tree-manifest
readers).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from orchestrator._common.io_atomic import durable_atomic_write

from .contracts import (
    RUN_REF_CONFINED_MATERIALIZER_VERSION,
    RUN_REF_NO_SETUP_IDENTITY,
    RepositoryRevisionId,
    RunRefSourceRefusal,
    VerifiedGitTreeIdentity,
    canonical_sha256,
)
from .source import (
    _LFS_POLICY,
    _SOURCE_SCHEMA,
    _SUBMODULE_POLICY,
    _MirrorSourceIdentity,
    _canonical_absolute_local_path,
    _clone_detached,
    _discard_path,
    _materialization_refusal,
    _require_directory_or_absent,
    _run_git,
    _sealed_mirror,
    normalize_repository_locator,
    validate_commit_sha,
)
from .workspace import TreeManifest, WorkspaceFreezeError

_CONFINED_GIT_CONFIG = (
    b"[core]\n\trepositoryformatversion = 0\n\tfilemode = true\n"
    b"\tbare = false\n\tlogallrefupdates = false\n"
)
_CONFINED_GIT_DROPPED = ("hooks", "logs", "description", "FETCH_HEAD", "ORIG_HEAD", "packed-refs")
_CONFINED_GIT_FORBIDDEN = ("objects/info/alternates", "objects/info/http-alternates", "commondir", "gitdir")


@dataclass(frozen=True)
class ConfinedSource:
    """A verified sanitized clone; its source manifest is the setup-free baseline."""

    repository_revision_id: RepositoryRevisionId
    verified_git_tree: VerifiedGitTreeIdentity
    mirror_path: Path
    workspace_path: Path
    source_tree_manifest: TreeManifest


def sanitized_git_environment(scratch: Path) -> dict[str, str]:
    """Environment for host Git in this profile: built from scratch, never copied.

    `scratch` is an empty private directory serving as HOME and template dir.
    """

    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(scratch),
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TEMPLATE_DIR": str(scratch),
        "GIT_TERMINAL_PROMPT": "0",
        # OpenSSH reads default identities from the passwd home, not $HOME: name none.
        "GIT_SSH_COMMAND": ("ssh -F /dev/null -o BatchMode=yes -o IdentityAgent=none "
                            "-o IdentitiesOnly=yes -o IdentityFile=/dev/null"),
    }


def confined_revision(locator: str, commit: str) -> tuple[_MirrorSourceIdentity, RepositoryRevisionId]:
    components = {
        "normalized_locator": normalize_repository_locator(locator),
        "resolved_commit_sha": validate_commit_sha(commit),
        "materializer_version": RUN_REF_CONFINED_MATERIALIZER_VERSION,
        "submodule_policy": _SUBMODULE_POLICY,
        "lfs_policy": _LFS_POLICY,
    }
    source = _MirrorSourceIdentity(
        digest=canonical_sha256({"schema_version": _SOURCE_SCHEMA, **components}), **components)
    revision = RepositoryRevisionId.build(**components, authored_setup_identity=RUN_REF_NO_SETUP_IDENTITY)
    return source, revision


def _sanitize_clone_git(workspace: Path, env: Mapping[str, str]) -> None:
    git_dir = workspace / ".git"
    _run_git(("git", "-C", str(workspace), "remote", "remove", "origin"), env=env)
    for name in _CONFINED_GIT_DROPPED:
        if os.path.lexists(git_dir / name):
            _discard_path(git_dir / name)
    remotes = git_dir / "refs" / "remotes"
    if os.path.lexists(remotes):
        _discard_path(remotes)
    durable_atomic_write(git_dir / "config", _CONFINED_GIT_CONFIG)


def _verify_sanitized_git(git_dir: Path, *, forbidden: tuple[bytes, ...]) -> None:
    """Refuse a `.git` that could link or execute back into the host."""

    if not stat.S_ISDIR(git_dir.lstat().st_mode):
        raise _materialization_refusal(str(git_dir), "sanitized clone .git is not a directory")
    for name in _CONFINED_GIT_FORBIDDEN + _CONFINED_GIT_DROPPED:
        if os.path.lexists(git_dir / name):
            raise _materialization_refusal(name, "sanitized clone .git keeps a forbidden entry")
    if (git_dir / "config").read_bytes() != _CONFINED_GIT_CONFIG:
        raise _materialization_refusal("config", "sanitized clone .git config is not the fixed config")
    for directory, dirs, files in os.walk(git_dir):
        for name in dirs + files:
            path = Path(directory, name)
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or (not stat.S_ISDIR(info.st_mode) and (
                    not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o111)):
                raise _materialization_refusal(str(path.relative_to(git_dir)),
                                               "sanitized clone .git holds a link, executable or special file")
            if stat.S_ISREG(info.st_mode) and "objects" not in path.relative_to(git_dir).parts:
                payload = path.read_bytes()
                if any(token in payload for token in forbidden):
                    raise _materialization_refusal(str(path.relative_to(git_dir)),
                                                   "sanitized clone .git names a host path")


def materialize_confined_source(
    locator: str,
    commit: str,
    *,
    run_ref_root: Path,
    workspace: Path,
) -> ConfinedSource:
    """Seal the exact revision with sanitized host Git and produce one fresh sanitized clone."""

    workspace_path = Path(workspace)
    if os.path.lexists(workspace_path):
        raise RunRefSourceRefusal("trial_workspace_preexisting", str(workspace_path),
                                  "run-reference workspace must not preexist")
    workspace_path = _canonical_absolute_local_path(workspace_path, label="run-reference workspace")
    run_ref_root_path = _canonical_absolute_local_path(Path(run_ref_root), label="run-reference root")
    _require_directory_or_absent(run_ref_root_path, label="run-reference root")
    _require_directory_or_absent(workspace_path.parent, label="run-reference workspace parent")
    source, revision = confined_revision(locator, commit)
    with tempfile.TemporaryDirectory(prefix="run-ref-git-") as scratch:
        env = sanitized_git_environment(Path(scratch))
        try:
            mirror_path, _seal, verified_tree, expected = _sealed_mirror(
                source=source, run_ref_root=run_ref_root_path, env=env)
            workspace_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _materialization_refusal(str(run_ref_root_path),
                                           "run-reference mirror coordination failed") from exc
        try:
            manifest = _clone_detached(mirror_path=mirror_path, workspace_path=workspace_path, source=source,
                                       verified_tree=verified_tree, expected_checkout_tree_manifest=expected,
                                       env=env)
            _sanitize_clone_git(workspace_path, env)
            _verify_sanitized_git(workspace_path / ".git",
                                  forbidden=(str(mirror_path).encode(), source.normalized_locator.encode()))
        except RunRefSourceRefusal:
            _discard_path(workspace_path)
            raise
        except (OSError, subprocess.CalledProcessError, WorkspaceFreezeError) as exc:
            _discard_path(workspace_path)
            raise _materialization_refusal(source.resolved_commit_sha,
                                           "failed to create and verify the sanitized source clone") from exc
    return ConfinedSource(repository_revision_id=revision, verified_git_tree=verified_tree,
                          mirror_path=mirror_path, workspace_path=workspace_path, source_tree_manifest=manifest)



__all__ = [
    "ConfinedSource",
    "confined_revision",
    "materialize_confined_source",
    "sanitized_git_environment",
]
