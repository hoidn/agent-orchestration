from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


_SHA256_ID_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT_TREE_ID_RE = re.compile(r"git-tree:[0-9a-f]{40}\Z")
_COMMIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SETUP_RUNTIME_ENV_NAMES = frozenset(
    {"PWD", "ORC_RUN_REF_SETUP_EVIDENCE_PATH"}
)


def canonical_json_bytes(value: Any) -> bytes:
    """Encode a JSON value with the repository's stable digest representation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


class RunRefSourceRefusal(ValueError):
    """A stable, structured refusal at the source-materialization boundary."""

    def __init__(
        self,
        code: str,
        rejected_value: object,
        message: str,
        *,
        secondary_causes: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.rejected_value = rejected_value
        self.secondary_causes = secondary_causes


@dataclass(frozen=True)
class SetupCommand:
    """One authored setup command, represented literally and never as a shell."""

    argv: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.argv, tuple)
            or not self.argv
            or any(not isinstance(arg, str) or "\0" in arg for arg in self.argv)
        ):
            raise ValueError("setup argv must be a non-empty tuple of NUL-free strings")
        argv0 = self.argv[0]
        if not os.path.isabs(argv0):
            relative_parts = argv0.removeprefix("./").split("/")
            if (
                not argv0.startswith("./")
                or "\\" in argv0
                or any(part in {"", ".", ".."} for part in relative_parts)
            ):
                raise ValueError(
                    "setup argv[0] must be absolute or canonical workspace-relative './…'"
                )

        if not isinstance(self.env, tuple):
            raise ValueError("setup env must be a tuple of literal (name, value) pairs")

        seen: set[str] = set()
        for item in self.env:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("setup env must contain literal (name, value) pairs")
            name, value = item
            if not isinstance(name, str) or _ENV_NAME_RE.fullmatch(name) is None:
                raise ValueError(f"invalid setup environment name: {name!r}")
            if name in _SETUP_RUNTIME_ENV_NAMES:
                raise ValueError(
                    f"setup environment name is runtime-owned: {name!r}"
                )
            if not isinstance(value, str) or "\0" in value:
                raise ValueError(f"invalid setup environment value for {name!r}")
            if name in seen:
                raise ValueError(f"duplicate setup environment name: {name!r}")
            seen.add(name)


@dataclass(frozen=True)
class SetupPolicy:
    commands: tuple[SetupCommand, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.commands, tuple) or any(
            not isinstance(command, SetupCommand) for command in self.commands
        ):
            raise TypeError("setup commands must be a tuple of SetupCommand values")


def authored_setup_identity(setup: SetupPolicy) -> str:
    return canonical_sha256(
        {
            "commands": [
                {
                    "argv": list(command.argv),
                    "env": [[name, value] for name, value in command.env],
                }
                for command in setup.commands
            ]
        }
    )


def _validate_repository_revision_components(components: dict[str, str]) -> None:
    for name, value in components.items():
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"repository revision component {name} must be a non-empty string"
            )
    if _COMMIT_SHA_RE.fullmatch(components["resolved_commit_sha"]) is None:
        raise ValueError(
            "repository revision commit must be exactly 40 lowercase hexadecimal characters"
        )
    if _SHA256_ID_RE.fullmatch(components["authored_setup_identity"]) is None:
        raise ValueError(
            "repository revision setup identity must be sha256:<64 lowercase hex>"
        )


@dataclass(frozen=True)
class RepositoryRevisionId:
    """Identity of an authored repository revision and materialization policy."""

    digest: str
    normalized_locator: str
    resolved_commit_sha: str
    materializer_version: str
    submodule_policy: str
    lfs_policy: str
    authored_setup_identity: str

    def __post_init__(self) -> None:
        components = self.components
        _validate_repository_revision_components(components)
        if not isinstance(self.digest, str) or _SHA256_ID_RE.fullmatch(self.digest) is None:
            raise ValueError(
                "repository revision digest must be sha256:<64 lowercase hex>"
            )
        if self.digest != canonical_sha256(components):
            raise ValueError(
                "repository revision digest does not match its six identity components"
            )

    @property
    def components(self) -> dict[str, str]:
        # Construct a fresh mapping so callers cannot mutate identity state.
        return {
            "normalized_locator": self.normalized_locator,
            "resolved_commit_sha": self.resolved_commit_sha,
            "materializer_version": self.materializer_version,
            "submodule_policy": self.submodule_policy,
            "lfs_policy": self.lfs_policy,
            "authored_setup_identity": self.authored_setup_identity,
        }

    @classmethod
    def build(
        cls,
        *,
        normalized_locator: str,
        resolved_commit_sha: str,
        materializer_version: str,
        submodule_policy: str,
        lfs_policy: str,
        authored_setup_identity: str,
    ) -> RepositoryRevisionId:
        components = {
            "normalized_locator": normalized_locator,
            "resolved_commit_sha": resolved_commit_sha,
            "materializer_version": materializer_version,
            "submodule_policy": submodule_policy,
            "lfs_policy": lfs_policy,
            "authored_setup_identity": authored_setup_identity,
        }
        _validate_repository_revision_components(components)
        return cls(digest=canonical_sha256(components), **components)


@dataclass(frozen=True)
class VerifiedGitTreeIdentity:
    value: str

    def __post_init__(self) -> None:
        if _GIT_TREE_ID_RE.fullmatch(self.value) is None:
            raise ValueError("verified Git tree identity must be git-tree:<40 lowercase hex>")


@dataclass(frozen=True)
class VerifiedCompilerRuntimeIdentity:
    digest: str

    def __post_init__(self) -> None:
        if _SHA256_ID_RE.fullmatch(self.digest) is None:
            raise ValueError("compiler/runtime identity must be sha256:<64 lowercase hex>")


def _compiler_package_files(package_root: Path) -> list[dict[str, object]]:
    try:
        root_identity = package_root.lstat()
    except OSError as exc:
        raise ValueError(f"cannot inspect compiler package root: {package_root}") from exc
    if not stat.S_ISDIR(root_identity.st_mode):
        raise ValueError(f"compiler package root is not a directory: {package_root}")

    rows: list[dict[str, object]] = []

    def walk(directory: Path, relative: PurePosixPath) -> None:
        try:
            with os.scandir(directory) as scan:
                children = sorted(scan, key=lambda entry: entry.name.encode("utf-8"))
        except (OSError, UnicodeEncodeError) as exc:
            raise ValueError(f"cannot enumerate compiler package: {directory}") from exc

        for child in children:
            child_relative = relative / child.name
            path_text = child_relative.as_posix()
            try:
                path_text.encode("utf-8")
                identity = child.stat(follow_symlinks=False)
            except (OSError, UnicodeEncodeError) as exc:
                raise ValueError(f"cannot inspect compiler package entry: {path_text!r}") from exc
            child_path = Path(child.path)
            if stat.S_ISDIR(identity.st_mode):
                if child.name != "__pycache__":
                    walk(child_path, child_relative)
                continue
            if stat.S_ISREG(identity.st_mode):
                if child_path.suffix in {".pyc", ".pyo"}:
                    continue
                digest = hashlib.sha256()
                size = 0
                try:
                    with child_path.open("rb") as handle:
                        while chunk := handle.read(1024 * 1024):
                            digest.update(chunk)
                            size += len(chunk)
                except OSError as exc:
                    raise ValueError(f"cannot hash compiler package entry: {path_text!r}") from exc
                rows.append(
                    {
                        "path": path_text,
                        "kind": "file",
                        "size": size,
                        "sha256": f"sha256:{digest.hexdigest()}",
                    }
                )
                continue
            if stat.S_ISLNK(identity.st_mode):
                try:
                    target = os.readlink(child_path)
                    target_bytes = target.encode("utf-8")
                except (OSError, UnicodeEncodeError) as exc:
                    raise ValueError(
                        f"cannot read compiler package symlink: {path_text!r}"
                    ) from exc
                rows.append(
                    {
                        "path": path_text,
                        "kind": "symlink",
                        "size": len(target_bytes),
                        "sha256": f"sha256:{hashlib.sha256(target_bytes).hexdigest()}",
                        "link_target": target,
                    }
                )
                continue
            raise ValueError(f"unsupported compiler package entry type: {path_text!r}")

    walk(package_root, PurePosixPath())
    return rows


def compute_compiler_runtime_identity(
    *,
    package_root: Path | None = None,
    python_implementation: str | None = None,
    python_major_minor: tuple[int, int] | None = None,
    orchestrator_version: str | None = None,
    lowering_schema: int | None = None,
) -> VerifiedCompilerRuntimeIdentity:
    """Hash the path-independent installed compiler/runtime input set."""

    if package_root is None:
        package_root = Path(__file__).resolve().parents[2]
    if python_implementation is None:
        python_implementation = platform.python_implementation().lower()
    if python_major_minor is None:
        python_major_minor = (sys.version_info.major, sys.version_info.minor)
    if orchestrator_version is None:
        from orchestrator import __version__

        orchestrator_version = __version__
    if lowering_schema is None:
        from orchestrator.workflow_lisp.wcc.route import DEFAULT_LOWERING_SCHEMA

        lowering_schema = DEFAULT_LOWERING_SCHEMA

    payload = {
        "python_implementation": python_implementation,
        "python_major_minor": list(python_major_minor),
        "orchestrator_version": orchestrator_version,
        "lowering_schema": lowering_schema,
        "package_files": _compiler_package_files(Path(package_root)),
    }
    return VerifiedCompilerRuntimeIdentity(canonical_sha256(payload))


@dataclass(frozen=True)
class PostSetupBaselineIdentity:
    digest: str

    def __post_init__(self) -> None:
        if _SHA256_ID_RE.fullmatch(self.digest) is None:
            raise ValueError("post-setup baseline identity must be sha256:<64 lowercase hex>")
