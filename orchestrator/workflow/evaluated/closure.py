"""Runtime evidence for evaluated command implementations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import errno
import os
from pathlib import Path
import stat
from typing import Any

from orchestrator._common.safe_tree import (
    SafeTreeError,
    hash_regular_file,
    open_directory,
)
from orchestrator.workflow_lisp.closed.program import canonical_digest
from orchestrator.workflow.evaluated.closure_evidence import (
    command_evidence_key,
    parse_command_evidence_key,
    target_spelling,
    validate_implementation_evidence as _validate_implementation_evidence,
)


class ClosureEvidenceError(ValueError):
    """A required command path could not be safely selected or read."""

    code = "command_closure_unreadable"

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


def _package_root() -> Path:
    import orchestrator

    return Path(orchestrator.__file__).resolve().parent


def _skip_bare_argv0(position: int, token: str) -> bool:
    return position == 0 and "/" not in token


def _required_token(position: int, token: str) -> bool:
    return position == 0 and (token.startswith("/") or "/" in token)


def _lexical_workspace_root(value: str | os.PathLike[str]) -> str:
    raw = os.fspath(value)
    if not raw.startswith(os.sep):
        raw = os.path.join(os.getcwd(), raw)
    parts = [part for part in raw.split(os.sep) if part not in {"", "."}]
    return os.sep + os.sep.join(parts) if parts else os.sep


def _absolute_token_path(token: str, lexical_workspace_root: str) -> tuple[str, str] | None:
    if not token.startswith("/"):
        return "workspace", "/".join(
            part for part in token.split("/") if part not in {"", "."}
        ) or "."
    root_parts = [part for part in lexical_workspace_root.split("/") if part]
    token_parts = [part for part in token.split("/") if part not in {"", "."}]
    if token_parts[: len(root_parts)] != root_parts:
        return None
    suffix = token_parts[len(root_parts) :]
    return "workspace", "/".join(suffix) or "."


def _lookup(base: str, path: str, *, workspace_root: Path, package_root: Path) -> str:
    if base == "workspace":
        return os.path.join(str(workspace_root), path)
    if base == "package:orchestrator":
        return os.path.join(str(package_root), path)
    if base == "absolute" and path.startswith("/"):
        return path
    raise ValueError(f"unsupported command closure path: {base!r} {path!r}")


def _lstat(path: str, *, required: bool) -> bool:
    try:
        os.lstat(path)
        return True
    except OSError as exc:
        if not required and exc.errno in {errno.ENOENT, errno.ENOTDIR}:
            return False
        raise ClosureEvidenceError(path, str(exc) or os.strerror(exc.errno or errno.EIO)) from exc


def _resolve_path(path: str) -> tuple[Path, bool, bool]:
    """Resolve in kernel component order, retaining ``..`` after symlinks."""

    current = "/" if path.startswith("/") else os.getcwd()
    saw_symlink = False
    endpoint_is_symlink = False
    components = path.split(os.sep)
    for component in components:
        if component in {"", "."}:
            continue
        if component == "..":
            current = os.path.dirname(current.rstrip(os.sep)) or os.sep
            endpoint_is_symlink = False
            continue
        candidate = os.path.join(current, component)
        try:
            info = os.lstat(candidate)
            if stat.S_ISLNK(info.st_mode):
                current = str(Path(candidate).resolve(strict=True))
                saw_symlink = True
                endpoint_is_symlink = True
            else:
                current = candidate
                endpoint_is_symlink = False
        except (OSError, RuntimeError) as exc:
            raise ClosureEvidenceError(path, str(exc)) from exc
    return Path(current), saw_symlink, endpoint_is_symlink


def _file_digest(path: Path) -> str:
    descriptor = open_directory(os.sep)
    try:
        return "sha256:" + hash_regular_file(
            descriptor, str(path).lstrip(os.sep)
        )
    except (OSError, SafeTreeError) as exc:
        raise ClosureEvidenceError(str(path), str(exc)) from exc
    finally:
        os.close(descriptor)


def _file_row(
    logical_path: str,
    resolved: Path,
    saw_symlink: bool,
    *,
    workspace_root: Path,
    package_root: Path,
    preferred_base: str,
) -> dict[str, Any]:
    try:
        kind = os.stat(resolved).st_mode
    except OSError as exc:
        raise ClosureEvidenceError(logical_path, str(exc)) from exc
    if not stat.S_ISREG(kind):
        raise ClosureEvidenceError(logical_path, "not a regular file")
    row: dict[str, Any] = {"kind": "file", "digest": _file_digest(resolved)}
    if saw_symlink:
        row["target"] = target_spelling(resolved, preferred_base, workspace_root, package_root)
    return row


def _directory_files(
    logical_root: str,
    resolved_root: Path,
    *,
    workspace_root: Path,
    package_root: Path,
    preferred_base: str,
    coverage: list[tuple[Path, bool]],
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    stack: set[tuple[int, int]] = set()

    def walk(directory: Path, prefix: str) -> None:
        try:
            info = os.stat(directory)
            if not stat.S_ISDIR(info.st_mode):
                raise ClosureEvidenceError(str(directory), "not a directory")
            identity = (info.st_dev, info.st_ino)
            if identity in stack:
                raise ClosureEvidenceError(str(directory), "directory symlink cycle")
            stack.add(identity)
            with os.scandir(directory) as entries:
                names = sorted(entry.name for entry in entries)
        except ClosureEvidenceError:
            raise
        except OSError as exc:
            raise ClosureEvidenceError(str(directory), str(exc)) from exc
        try:
            for name in names:
                child_logical = os.path.join(logical_root, prefix, name)
                child, saw_symlink, entry_is_symlink = _resolve_path(child_logical)
                try:
                    child_mode = os.stat(child).st_mode
                except OSError as exc:
                    raise ClosureEvidenceError(child_logical, str(exc)) from exc
                relative = os.path.join(prefix, name).replace(os.sep, "/")
                if stat.S_ISDIR(child_mode):
                    if entry_is_symlink:
                        coverage.append((child, True))
                        files.append({
                            "path": relative,
                            "kind": "directory",
                            "target": target_spelling(
                                child, preferred_base, workspace_root, package_root
                            ),
                        })
                    walk(child, relative)
                elif stat.S_ISREG(child_mode):
                    if saw_symlink:
                        coverage.append((child, False))
                    row = _file_row(
                        child_logical,
                        child,
                        saw_symlink,
                        workspace_root=workspace_root,
                        package_root=package_root,
                        preferred_base=preferred_base,
                    )
                    files.append({"path": relative, **row})
                else:
                    raise ClosureEvidenceError(child_logical, "unsupported file kind")
        finally:
            stack.remove(identity)

    walk(resolved_root, "")
    return sorted(files, key=lambda row: row["path"])


def _capture(
    key: str,
    lookup_path: str,
    *,
    workspace_root: Path,
    package_root: Path,
    coverage: list[tuple[Path, bool]],
) -> dict[str, Any]:
    base, _path, _position = parse_command_evidence_key(key)
    resolved, saw_symlink, _endpoint_is_symlink = _resolve_path(lookup_path)
    try:
        mode = os.stat(resolved).st_mode
    except OSError as exc:
        raise ClosureEvidenceError(lookup_path, str(exc)) from exc
    coverage.append((resolved, stat.S_ISDIR(mode)))
    if stat.S_ISREG(mode):
        row = _file_row(
            lookup_path,
            resolved,
            saw_symlink,
            workspace_root=workspace_root,
            package_root=package_root,
            preferred_base=base,
        )
    elif stat.S_ISDIR(mode):
        files = _directory_files(
            lookup_path,
            resolved,
            workspace_root=workspace_root,
            package_root=package_root,
            preferred_base=base,
            coverage=coverage,
        )
        row = {"kind": "directory", "digest": canonical_digest(files)}
        if saw_symlink:
            row["target"] = target_spelling(resolved, base, workspace_root, package_root)
    else:
        raise ClosureEvidenceError(lookup_path, "unsupported file kind")
    return row


def resolve_command_evidence(
    stable_command: Sequence[str],
    closure: Sequence[Mapping[str, str]],
    *,
    workspace_root: str | os.PathLike[str],
    prior: Mapping[str, Any] | None = None,
    destinations: Sequence[str | os.PathLike[str]] = (),
) -> dict[str, dict[str, Any]]:
    """Resolve automatic command paths, declarations, and one supplied prior map."""

    lexical_workspace = _lexical_workspace_root(workspace_root)
    workspace = Path(workspace_root).resolve(strict=True)
    package = _package_root()
    selected = _select_token_paths(stable_command, workspace, lexical_workspace)
    selected.update(_select_declared_paths(closure, workspace, package))
    if prior is not None:
        selected.update(
            _select_prior_paths(
                prior, stable_command, workspace, lexical_workspace, package
            )
        )
    coverage: list[tuple[Path, bool]] = []
    evidence = {
        key: _capture(
            key,
            lookup,
            workspace_root=workspace,
            package_root=package,
            coverage=coverage,
        )
        for key, lookup in selected.items()
    }
    _require_disjoint_destinations(coverage, destinations)
    return _validate_implementation_evidence(evidence)


def _select_token_paths(
    stable_command: Sequence[str], workspace: Path, lexical_workspace: str
) -> dict[str, str]:
    selected: dict[str, str] = {}
    if isinstance(stable_command, (str, bytes)):
        raise ValueError("stable command must be a token sequence")
    for position, token in enumerate(stable_command):
        if not isinstance(token, str) or not token:
            raise ValueError("stable command tokens must be nonempty strings")
        if _skip_bare_argv0(position, token):
            continue
        logical = _absolute_token_path(token, lexical_workspace)
        if logical is None:
            continue
        base, path = logical
        key = command_evidence_key(base, path, position)
        lookup_path = token if token.startswith("/") else os.path.join(str(workspace), token)
        required = _required_token(position, token)
        if _lstat(lookup_path, required=required):
            selected[key] = lookup_path
    return selected


def _select_declared_paths(
    closure: Sequence[Mapping[str, str]], workspace: Path, package: Path
) -> dict[str, str]:
    selected: dict[str, str] = {}
    for row in closure:
        if not isinstance(row, Mapping) or set(row) != {"base", "path"}:
            raise ValueError("command closure row is malformed")
        base, path = row["base"], row["path"]
        try:
            key = command_evidence_key(base, path)
        except ValueError as exc:
            raise ValueError("command closure row is malformed") from exc
        lookup_path = _lookup(base, path, workspace_root=workspace, package_root=package)
        _lstat(lookup_path, required=True)
        selected[key] = lookup_path
    return selected


def _select_prior_paths(
    prior: Mapping[str, Any],
    stable_command: Sequence[str],
    workspace: Path,
    lexical_workspace: str,
    package: Path,
) -> dict[str, str]:
    selected: dict[str, str] = {}
    checked = _validate_implementation_evidence(dict(prior))
    for key in checked:
        base, path, position = parse_command_evidence_key(key)
        lookup_path = _prior_lookup(
            base, path, position, stable_command, workspace, lexical_workspace, package
        )
        _lstat(lookup_path, required=True)
        selected[key] = lookup_path
    return selected


def _prior_lookup(
    base: str,
    path: str,
    position: int | None,
    stable_command: Sequence[str],
    workspace: Path,
    lexical_workspace: str,
    package: Path,
) -> str:
    if position is None:
        return _lookup(base, path, workspace_root=workspace, package_root=package)
    if base != "workspace" or position >= len(stable_command):
        raise ValueError("prior token evidence has no stable command token")
    token = stable_command[position]
    if isinstance(token, str) and _skip_bare_argv0(position, token):
        raise ValueError("prior evidence cannot bind a bare argv[0] path")
    if not isinstance(token, str) or _absolute_token_path(
        token, lexical_workspace
    ) != (base, path):
        raise ValueError("prior token evidence differs from stable command")
    return token if token.startswith("/") else os.path.join(str(workspace), token)


def _require_disjoint_destinations(
    closure_paths: Sequence[tuple[Path, bool]],
    destinations: Sequence[str | os.PathLike[str]],
) -> None:
    for raw in destinations:
        try:
            destination = Path(raw).resolve(strict=False)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ClosureEvidenceError(str(raw), f"cannot resolve destination: {exc}") from exc
        for root, is_directory in closure_paths:
            if destination == root or (
                is_directory and destination.is_relative_to(root)
            ):
                raise ClosureEvidenceError(
                    str(raw), f"runtime destination overlaps command closure {root}"
                )


__all__ = [
    "ClosureEvidenceError",
    "resolve_command_evidence",
]
