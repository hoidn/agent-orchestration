"""Descriptor-pinned provider candidate admission.

The candidate is the one intentionally writable provider authority.  This
module admits that authority without following pathname aliases, holds an
exclusive lease for its lifetime, and rejects filesystem structure that could
cross the closed namespace projection.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import errno
import fcntl
import os
from pathlib import Path
import posixpath
import re
import stat
from typing import Self
import unicodedata

from .isolation import ProviderIsolationIssue
from .isolation_environment import MountIdentityUnavailable, _statx_mount_id


CANDIDATE_INVALID_CODE = "provider_isolation_candidate_invalid"
CANDIDATE_ADMISSION_SCHEMA_VERSION = "provider_candidate_admission.v1"
MAX_CANDIDATE_DIRECTORY_DEPTH = 128
MAX_CANDIDATE_ENTRY_COUNT = 100_000
MAX_CANDIDATE_SYMLINK_EXPANSIONS = 40
REQUIRED_CANDIDATE_AUTHORITY_LABELS = (
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

_ALLOWED_WORKSPACE_COMPONENTS = frozenset({"home", "workspace", "tmp"})
_RESERVED_ROOT_COMPONENTS = frozenset(
    {
        "bin",
        "sbin",
        "usr",
        "lib",
        "lib32",
        "lib64",
        "etc",
        "opt",
        "proc",
        "dev",
        "run",
        "var",
    }
)
_FORBIDDEN_WRITE_BITS = 0o022
_AUTHORITY_LABEL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_STAT_IDENTITY_FIELDS = (
    "st_mode",
    "st_ino",
    "st_dev",
    "st_nlink",
    "st_uid",
    "st_gid",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)


class ProviderIsolationCandidateError(ValueError):
    """Fail-closed candidate rejection with stable, content-free diagnostics."""

    code = CANDIDATE_INVALID_CODE

    def __init__(self, issues: tuple[ProviderIsolationIssue, ...]):
        self.issues = issues
        detail = "; ".join(
            f"{issue.path}: {issue.message}" for issue in self.issues
        )
        super().__init__(f"{self.code}: {detail}")


@dataclass(frozen=True, slots=True)
class ProviderCandidateObjectIdentity:
    """Descriptor-derived identity of one candidate filesystem object."""

    path: str
    kind: str
    device: int
    inode: int
    mount_id: int
    mode: int
    owner_uid: int
    link_count: int
    link_text: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderCandidateAncestryIdentity:
    """One real directory in the absolute path to the pinned candidate."""

    path: str
    device: int
    inode: int
    mount_id: int


@dataclass(slots=True)
class _CandidateTraversalBudget:
    entries: int = 0


@dataclass(slots=True)
class _CandidateScanFrame:
    fd: int
    parent_path: str
    depth: int
    names: tuple[str, ...]
    parent_fd: int | None = None
    entry_name: str | None = None
    before: os.stat_result | None = None
    issue_base: str | None = None
    owned: bool = False
    index: int = 0


@dataclass(slots=True)
class ProviderCandidateAdmission:
    """A live candidate lease and the descriptor the backend must bind."""

    path: Path
    root_fd: int
    root_identity: ProviderCandidateObjectIdentity
    ancestry: tuple[ProviderCandidateAncestryIdentity, ...]
    entries: tuple[ProviderCandidateObjectIdentity, ...]

    @property
    def schema_version(self) -> str:
        return CANDIDATE_ADMISSION_SCHEMA_VERSION

    def revalidate(self) -> None:
        """Require the pinned object and its absolute pathname ancestry to agree."""

        if self.root_fd < 0:
            _raise_candidate("$.candidate_root", "candidate admission is closed")
        held_stat = os.fstat(self.root_fd)
        held_mount_id = _mount_id(
            self.root_fd,
            issue_path="$.candidate_root.mount_id",
        )
        if (
            held_stat.st_dev != self.root_identity.device
            or held_stat.st_ino != self.root_identity.inode
            or held_mount_id != self.root_identity.mount_id
        ):
            _raise_candidate(
                "$.candidate_root.identity",
                "pinned candidate root identity changed",
            )

        revalidated_fd = -1
        try:
            revalidated_fd, observed_ancestry = _open_absolute_candidate(self.path)
            if observed_ancestry != self.ancestry:
                _raise_candidate(
                    "$.candidate_root.ancestry",
                    "candidate pathname ancestry changed after admission",
                )
            observed_stat = os.fstat(revalidated_fd)
            observed_mount_id = _mount_id(
                revalidated_fd,
                issue_path="$.candidate_root.mount_id",
            )
            if (
                observed_stat.st_dev != self.root_identity.device
                or observed_stat.st_ino != self.root_identity.inode
                or observed_mount_id != self.root_identity.mount_id
            ):
                _raise_candidate(
                    "$.candidate_root.ancestry",
                    "candidate pathname no longer names the pinned authority",
                )
        except OSError as exc:
            _raise_candidate(
                "$.candidate_root.ancestry",
                (
                    "candidate pathname exchange prevented revalidation "
                    f"({_safe_errno(exc)})"
                ),
                cause=exc,
            )
        finally:
            if revalidated_fd >= 0:
                os.close(revalidated_fd)

    def duplicate_root_fd(self, *, minimum: int = 16) -> int:
        """Return a caller-owned descriptor for this exact live admission."""

        if (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or minimum < 3
        ):
            _raise_candidate(
                "$.candidate_root",
                "candidate duplicate descriptor minimum is invalid",
            )
        duplicate_fd = -1
        try:
            self.revalidate()
            duplicate_fd = fcntl.fcntl(
                self.root_fd,
                fcntl.F_DUPFD_CLOEXEC,
                minimum,
            )
            duplicated = os.fstat(duplicate_fd)
            duplicated_mount_id = _mount_id(
                duplicate_fd,
                issue_path="$.candidate_root.mount_id",
            )
            if (
                self.root_identity.kind != "directory"
                or not stat.S_ISDIR(duplicated.st_mode)
                or duplicated.st_dev != self.root_identity.device
                or duplicated.st_ino != self.root_identity.inode
                or duplicated_mount_id != self.root_identity.mount_id
                or stat.S_IMODE(duplicated.st_mode) != self.root_identity.mode
                or duplicated.st_uid != self.root_identity.owner_uid
            ):
                _raise_candidate(
                    "$.candidate_root.identity",
                    "duplicated candidate root authority changed",
                )
            self.revalidate()
            result_fd = duplicate_fd
            duplicate_fd = -1
            return result_fd
        except ProviderIsolationCandidateError:
            raise
        except OSError as exc:
            _raise_candidate(
                "$.candidate_root",
                "candidate descriptor duplication failed",
                cause=exc,
            )
        finally:
            if duplicate_fd >= 0:
                os.close(duplicate_fd)

    def close(self) -> None:
        """Release the exclusive candidate lease and held root descriptor."""

        if self.root_fd < 0:
            return
        try:
            fcntl.flock(self.root_fd, fcntl.LOCK_UN)
        finally:
            os.close(self.root_fd)
            self.root_fd = -1

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def validate_candidate_mount_location(
    candidate_root: str | os.PathLike[str],
    *,
    provider_prefix: str = "/opt/orchestrator-provider",
) -> Path:
    """Validate the closed v1 provider-visible candidate location."""

    raw = _canonical_absolute_spelling(candidate_root, "$.candidate_root")
    prefix = _canonical_absolute_spelling(provider_prefix, "$.provider_prefix")
    parts = Path(raw).parts
    if len(parts) < 3:
        _raise_candidate(
            "$.candidate_root",
            "candidate root must be below a supported workspace component",
        )
    first = parts[1]
    prefix_first = Path(prefix).parts[1]
    if (
        first in _RESERVED_ROOT_COMPONENTS
        or first == prefix_first
        or first not in _ALLOWED_WORKSPACE_COMPONENTS
    ):
        _raise_candidate(
            "$.candidate_root.workspace_component",
            "candidate workspace component is not admitted by v1",
        )
    return Path(raw)


def admit_provider_candidate(
    candidate_root: str | os.PathLike[str],
    *,
    denied_authorities: Mapping[str, str | os.PathLike[str]],
    provider_prefix: str = "/opt/orchestrator-provider",
) -> ProviderCandidateAdmission:
    """Admit, scan, pin, and exclusively lease one writable candidate root."""

    _require_closed_authority_inventory(denied_authorities)
    candidate_path = validate_candidate_mount_location(
        candidate_root,
        provider_prefix=provider_prefix,
    )
    root_fd = -1
    try:
        root_fd, ancestry = _open_absolute_candidate(candidate_path)
        root_stat = os.fstat(root_fd)
        _require_controller_entry(
            root_stat,
            issue_path="$.candidate_root",
            required_kind="directory",
        )
        root_mount_id = _mount_id(
            root_fd,
            issue_path="$.candidate_root.mount_id",
        )
        root_identity = _object_identity(
            ".",
            "directory",
            root_stat,
            root_mount_id,
        )
        _acquire_exclusive_lease(root_fd)

        canonical_path = _canonical_pinned_path(candidate_path, root_stat)
        _require_disjoint_authorities(
            canonical_path,
            denied_authorities,
        )

        scanned: dict[str, ProviderCandidateObjectIdentity] = {}
        source_stats: dict[str, os.stat_result] = {}
        _scan_candidate_directory(
            root_fd,
            parent_path=".",
            root_mount_id=root_mount_id,
            scanned=scanned,
            source_stats=source_stats,
        )
        _require_complete_hardlink_accounting(scanned, source_stats)
        _require_safe_symlink_graph(scanned)
        _require_runtime_mask_alias_separation(scanned)

        admission = ProviderCandidateAdmission(
            path=canonical_path,
            root_fd=root_fd,
            root_identity=root_identity,
            ancestry=ancestry,
            entries=tuple(
                scanned[path]
                for path in sorted(scanned, key=lambda value: value.encode("utf-8"))
            ),
        )
        root_fd = -1
        return admission
    except ProviderIsolationCandidateError:
        raise
    except OSError as exc:
        _raise_candidate(
            "$.candidate_root",
            f"candidate authority could not be admitted ({_safe_errno(exc)})",
            cause=exc,
        )
    finally:
        if root_fd >= 0:
            os.close(root_fd)


def _open_absolute_candidate(
    candidate_path: Path,
) -> tuple[int, tuple[ProviderCandidateAncestryIdentity, ...]]:
    parts = candidate_path.parts
    parent_fd = _open_directory("/")
    ancestry: list[ProviderCandidateAncestryIdentity] = []
    try:
        root_stat = os.fstat(parent_fd)
        ancestry.append(
            _ancestry_identity(
                "/",
                root_stat,
                _mount_id(
                    parent_fd,
                    issue_path="$.candidate_root.mount_id",
                ),
            )
        )
        for index, name in enumerate(parts[1:], start=1):
            issue_path = (
                "$.candidate_root"
                if index == len(parts) - 1
                else "$.candidate_root.ancestry"
            )
            _require_strict_nfc_text(name, "$.candidate_root")
            before = _lstat_at(parent_fd, name)
            if not stat.S_ISDIR(before.st_mode):
                _raise_candidate(
                    issue_path,
                    "candidate path components must be real directories",
                )
            child_fd = _open_directory_at(parent_fd, name)
            try:
                opened = os.fstat(child_fd)
                _require_same_stat(
                    before,
                    opened,
                    issue_path=issue_path,
                    message="candidate path component changed while opening",
                )
                mount_id = _mount_id(
                    child_fd,
                    issue_path="$.candidate_root.mount_id",
                )
                ancestry.append(
                    _ancestry_identity(
                        "/" + "/".join(parts[1 : index + 1]),
                        opened,
                        mount_id,
                    )
                )
            except BaseException:
                os.close(child_fd)
                raise
            os.close(parent_fd)
            parent_fd = child_fd
        return parent_fd, tuple(ancestry)
    except BaseException:
        os.close(parent_fd)
        raise


def _scan_candidate_directory(
    directory_fd: int,
    *,
    parent_path: str,
    root_mount_id: int,
    scanned: dict[str, ProviderCandidateObjectIdentity],
    source_stats: dict[str, os.stat_result],
) -> None:
    budget = _CandidateTraversalBudget()
    frames = [
        _CandidateScanFrame(
            fd=directory_fd,
            parent_path=parent_path,
            depth=0,
            names=_bounded_candidate_names(directory_fd, budget),
        )
    ]
    try:
        while frames:
            frame = frames[-1]
            if frame.index >= len(frame.names):
                if frame.owned:
                    assert frame.parent_fd is not None
                    assert frame.entry_name is not None
                    assert frame.before is not None
                    assert frame.issue_base is not None
                    after_fd = os.fstat(frame.fd)
                    after_path = _lstat_at(frame.parent_fd, frame.entry_name)
                    _require_same_stat(
                        frame.before,
                        after_fd,
                        issue_path=frame.issue_base,
                        message="candidate directory changed during admission",
                    )
                    _require_same_stat(
                        frame.before,
                        after_path,
                        issue_path=frame.issue_base,
                        message=(
                            "candidate directory pathname changed during admission"
                        ),
                    )
                    os.close(frame.fd)
                frames.pop()
                continue

            name = frame.names[frame.index]
            frame.index += 1
            relpath = (
                name
                if frame.parent_path == "."
                else f"{frame.parent_path}/{name}"
            )
            _scan_candidate_entry(
                frame,
                name=name,
                relpath=relpath,
                root_mount_id=root_mount_id,
                scanned=scanned,
                source_stats=source_stats,
                budget=budget,
                frames=frames,
            )
    finally:
        for frame in reversed(frames):
            if not frame.owned:
                continue
            try:
                os.close(frame.fd)
            except OSError:
                pass


def _scan_candidate_entry(
    frame: _CandidateScanFrame,
    *,
    name: str,
    relpath: str,
    root_mount_id: int,
    scanned: dict[str, ProviderCandidateObjectIdentity],
    source_stats: dict[str, os.stat_result],
    budget: _CandidateTraversalBudget,
    frames: list[_CandidateScanFrame],
) -> None:
    issue_base = f"$.entries[{relpath}]"
    before = _lstat_at(frame.fd, name)
    _require_controller_entry(before, issue_path=issue_base)
    mount_id = _mount_id(
        frame.fd,
        name,
        issue_path=f"{issue_base}.mount_id",
    )
    if mount_id != root_mount_id:
        _raise_candidate(
            f"{issue_base}.mount_id",
            "nested mount identity differs from candidate root",
        )

    if stat.S_ISDIR(before.st_mode):
        child_depth = frame.depth + 1
        if child_depth > MAX_CANDIDATE_DIRECTORY_DEPTH:
            _raise_candidate(
                f"{issue_base}.depth",
                "candidate directory depth exceeds the admission bound",
            )
        child_fd = _open_directory_at(frame.fd, name)
        try:
            opened = os.fstat(child_fd)
            _require_same_stat(
                before,
                opened,
                issue_path=issue_base,
                message="candidate directory changed while opening",
            )
            if (
                _mount_id(
                    child_fd,
                    issue_path=f"{issue_base}.mount_id",
                )
                != root_mount_id
            ):
                _raise_candidate(
                    f"{issue_base}.mount_id",
                    "opened directory mount identity differs from candidate root",
                )
            scanned[relpath] = _object_identity(
                relpath,
                "directory",
                opened,
                mount_id,
            )
            source_stats[relpath] = opened
            child_names = _bounded_candidate_names(child_fd, budget)
            frames.append(
                _CandidateScanFrame(
                    fd=child_fd,
                    parent_path=relpath,
                    depth=child_depth,
                    names=child_names,
                    parent_fd=frame.fd,
                    entry_name=name,
                    before=before,
                    issue_base=issue_base,
                    owned=True,
                )
            )
            child_fd = -1
        finally:
            if child_fd >= 0:
                os.close(child_fd)
        return

    if stat.S_ISREG(before.st_mode):
        child_fd = _open_object_at(frame.fd, name)
        try:
            opened = os.fstat(child_fd)
            _require_same_stat(
                before,
                opened,
                issue_path=issue_base,
                message="candidate file changed while opening",
            )
            if (
                _mount_id(
                    child_fd,
                    issue_path=f"{issue_base}.mount_id",
                )
                != root_mount_id
            ):
                _raise_candidate(
                    f"{issue_base}.mount_id",
                    "opened file mount identity differs from candidate root",
                )
            after_fd = os.fstat(child_fd)
        finally:
            os.close(child_fd)
        after_path = _lstat_at(frame.fd, name)
        _require_same_stat(
            before,
            after_fd,
            issue_path=issue_base,
            message="candidate file changed during admission",
        )
        _require_same_stat(
            before,
            after_path,
            issue_path=issue_base,
            message="candidate file pathname changed during admission",
        )
        scanned[relpath] = _object_identity(
            relpath,
            "regular_file",
            before,
            mount_id,
        )
        source_stats[relpath] = before
        return

    if stat.S_ISLNK(before.st_mode):
        link_text = os.readlink(name, dir_fd=frame.fd)
        _require_strict_nfc_text(
            link_text,
            f"{issue_base}.link_text",
        )
        after_path = _lstat_at(frame.fd, name)
        _require_same_stat(
            before,
            after_path,
            issue_path=issue_base,
            message="candidate symlink changed during admission",
        )
        scanned[relpath] = _object_identity(
            relpath,
            "symlink",
            before,
            mount_id,
            link_text=link_text,
        )
        source_stats[relpath] = before
        return

    _raise_candidate(
        f"{issue_base}.kind",
        "candidate entry type is forbidden",
    )


def _bounded_candidate_names(
    directory_fd: int,
    budget: _CandidateTraversalBudget,
) -> tuple[str, ...]:
    names: list[str] = []
    try:
        with os.scandir(directory_fd) as iterator:
            for entry in iterator:
                budget.entries += 1
                if budget.entries > MAX_CANDIDATE_ENTRY_COUNT:
                    _raise_candidate(
                        "$.entries",
                        "candidate entry count exceeds the admission bound",
                    )
                _require_entry_name(entry.name)
                names.append(entry.name)
    except ProviderIsolationCandidateError:
        raise
    except OSError as exc:
        _raise_candidate(
            "$.entries",
            f"candidate directory could not be enumerated ({_safe_errno(exc)})",
            cause=exc,
        )
    names.sort(key=lambda value: value.encode("utf-8"))
    return tuple(names)


def _require_complete_hardlink_accounting(
    scanned: Mapping[str, ProviderCandidateObjectIdentity],
    source_stats: Mapping[str, os.stat_result],
) -> None:
    groups: dict[tuple[int, int], list[str]] = {}
    for path, entry in scanned.items():
        if entry.kind == "regular_file":
            groups.setdefault((entry.device, entry.inode), []).append(path)
    for paths in groups.values():
        paths.sort(key=lambda value: value.encode("utf-8"))
        expected = source_stats[paths[0]].st_nlink
        if expected != len(paths):
            _raise_candidate(
                f"$.entries[{paths[0]}].hardlinks",
                "candidate inode link count is not fully accounted inside the root",
            )


def _require_safe_symlink_graph(
    scanned: Mapping[str, ProviderCandidateObjectIdentity],
) -> None:
    for path, entry in scanned.items():
        if entry.kind != "symlink":
            continue
        if _inside_runtime_mask(path):
            _raise_candidate(
                f"$.entries[{path}].link_text",
                "symlinks inside the masked runtime authority are forbidden",
            )
        resolved = _resolve_candidate_path(
            path,
            scanned,
            origin_path=path,
        )
        if _inside_runtime_mask(resolved):
            _raise_candidate(
                f"$.entries[{path}].link_text",
                "candidate symlink resolves into the masked runtime authority",
            )


def _resolve_candidate_path(
    path: str,
    scanned: Mapping[str, ProviderCandidateObjectIdentity],
    *,
    origin_path: str,
) -> str:
    pending = path.split("/")
    resolved: list[str] = []
    seen: set[str] = set()
    symlink_expansions = 0
    while pending:
        component = pending.pop(0)
        if component in {"", "."}:
            continue
        if component == "..":
            if not resolved:
                _unsafe_symlink(origin_path, "symlink target escapes the candidate")
            resolved.pop()
            continue
        current = "/".join((*resolved, component))
        entry = scanned.get(current)
        if entry is None:
            _unsafe_symlink(origin_path, "symlink target is broken")
        assert entry is not None
        if entry.kind == "symlink":
            if current in seen:
                _unsafe_symlink(origin_path, "symlink graph is cyclic")
            symlink_expansions += 1
            if symlink_expansions > MAX_CANDIDATE_SYMLINK_EXPANSIONS:
                _unsafe_symlink(
                    origin_path,
                    "symlink chain exceeds the admission bound",
                )
            seen.add(current)
            target = entry.link_text
            assert target is not None
            if target.startswith("/"):
                _unsafe_symlink(
                    origin_path,
                    "absolute symlink targets are forbidden",
                )
            pending = target.split("/") + pending
            continue
        if pending and entry.kind != "directory":
            _unsafe_symlink(
                origin_path,
                "symlink target traverses a non-directory",
            )
        resolved.append(component)
    return "/".join(resolved)


def _require_runtime_mask_alias_separation(
    scanned: Mapping[str, ProviderCandidateObjectIdentity],
) -> None:
    groups: dict[tuple[int, int], list[str]] = {}
    for path, entry in scanned.items():
        if entry.kind == "regular_file":
            groups.setdefault((entry.device, entry.inode), []).append(path)
    for paths in groups.values():
        inside = [path for path in paths if _inside_runtime_mask(path)]
        outside = [path for path in paths if not _inside_runtime_mask(path)]
        if inside and outside:
            outside.sort(key=lambda value: value.encode("utf-8"))
            _raise_candidate(
                f"$.entries[{outside[0]}].hardlinks",
                "regular inode aliases both sides of the masked runtime boundary",
            )


def _inside_runtime_mask(path: str) -> bool:
    return path == ".orchestrate" or path.startswith(".orchestrate/")


def _require_disjoint_authorities(
    candidate: Path,
    authorities: Mapping[str, str | os.PathLike[str]],
) -> None:
    for label in sorted(authorities, key=lambda value: value.encode("utf-8")):
        if _AUTHORITY_LABEL_PATTERN.fullmatch(label) is None:
            _raise_candidate(
                "$.authorities",
                "authority labels must use the closed diagnostic-name grammar",
            )
        authority = _canonical_denied_authority(
            authorities[label],
            issue_path=f"$.authorities[{label}]",
        )
        if _path_contains(candidate, authority) or _path_contains(authority, candidate):
            _raise_candidate(
                f"$.authorities[{label}]",
                f"candidate overlaps denied {label} authority",
            )


def _require_closed_authority_inventory(
    authorities: Mapping[str, str | os.PathLike[str]],
) -> None:
    if not isinstance(authorities, Mapping):
        _raise_candidate(
            "$.authorities",
            "candidate authority inventory must be a mapping",
        )
    observed = set(authorities)
    for label in REQUIRED_CANDIDATE_AUTHORITY_LABELS:
        if label not in observed:
            _raise_candidate(
                f"$.authorities[{label}]",
                f"candidate authority inventory is missing required {label} root",
            )
    required = frozenset(REQUIRED_CANDIDATE_AUTHORITY_LABELS)
    unknown = [
        label
        for label in observed
        if not isinstance(label, str) or label not in required
    ]
    if unknown:
        label = min(unknown, key=lambda value: str(value).encode("utf-8"))
        diagnostic_label = label if isinstance(label, str) else "<non-string>"
        _raise_candidate(
            f"$.authorities[{diagnostic_label}]",
            "candidate authority inventory contains an unknown label",
        )


def _canonical_denied_authority(
    value: str | os.PathLike[str],
    *,
    issue_path: str,
) -> Path:
    raw = os.fspath(value)
    if not isinstance(raw, str):
        _raise_candidate(issue_path, "denied authority must be Unicode text")
    if "\x00" in raw:
        _raise_candidate(issue_path, "denied authority path contains NUL")
    if not raw.startswith("/"):
        _raise_candidate(issue_path, "denied authority must be an absolute path")
    _require_strict_nfc_text(raw, issue_path)
    try:
        return Path(raw).resolve(strict=True)
    except OSError as exc:
        _raise_candidate(
            issue_path,
            f"denied authority cannot be resolved ({_safe_errno(exc)})",
            cause=exc,
        )


def _canonical_pinned_path(path: Path, root_stat: os.stat_result) -> Path:
    try:
        canonical = path.resolve(strict=True)
        observed = os.stat(canonical, follow_symlinks=False)
    except OSError as exc:
        _raise_candidate(
            "$.candidate_root.ancestry",
            f"candidate pathname cannot be resolved ({_safe_errno(exc)})",
            cause=exc,
        )
    if observed.st_dev != root_stat.st_dev or observed.st_ino != root_stat.st_ino:
        _raise_candidate(
            "$.candidate_root.ancestry",
            "canonical candidate pathname does not name the pinned authority",
        )
    return canonical


def _canonical_absolute_spelling(
    value: str | os.PathLike[str],
    issue_path: str,
) -> str:
    raw = os.fspath(value)
    if not isinstance(raw, str):
        _raise_candidate(issue_path, "authority paths must be strict Unicode text")
    _require_strict_nfc_text(raw, issue_path)
    if (
        not raw.startswith("/")
        or raw == "/"
        or "\x00" in raw
        or raw.endswith("/")
        or "//" in raw
        or raw != posixpath.normpath(raw)
    ):
        _raise_candidate(
            issue_path,
            "authority path must use canonical absolute spelling",
        )
    return raw


def _require_entry_name(name: str) -> None:
    _require_strict_nfc_text(name, "$.entries")
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        _raise_candidate("$.entries", "candidate entry name is invalid")


def _require_strict_nfc_text(value: str, issue_path: str) -> None:
    if not isinstance(value, str):
        _raise_candidate(issue_path, "filesystem text must be Unicode")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        _raise_candidate(
            issue_path,
            "filesystem text must be strict UTF-8",
            cause=exc,
        )
    if not unicodedata.is_normalized("NFC", value):
        _raise_candidate(issue_path, "filesystem text must already be Unicode NFC")


def _require_controller_entry(
    value: os.stat_result,
    *,
    issue_path: str,
    required_kind: str | None = None,
) -> None:
    if value.st_uid != os.geteuid():
        _raise_candidate(
            f"{issue_path}.owner",
            "candidate entry must be controller-owned",
        )
    if required_kind is None and not (
        stat.S_ISDIR(value.st_mode)
        or stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
    ):
        _raise_candidate(
            f"{issue_path}.kind",
            "candidate entry type is forbidden",
        )
    if (
        not stat.S_ISLNK(value.st_mode)
        and stat.S_IMODE(value.st_mode) & _FORBIDDEN_WRITE_BITS
    ):
        _raise_candidate(
            f"{issue_path}.mode",
            "candidate entry must not be group/world writable at admission",
        )
    if required_kind == "directory" and not stat.S_ISDIR(value.st_mode):
        _raise_candidate(issue_path, "candidate root must be a real directory")


def _acquire_exclusive_lease(root_fd: int) -> None:
    try:
        fcntl.flock(root_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            _raise_candidate(
                "$.candidate_root.lease",
                "candidate authority is already leased",
                cause=exc,
            )
        _raise_candidate(
            "$.candidate_root.lease",
            f"exclusive candidate lease is unavailable ({_safe_errno(exc)})",
            cause=exc,
        )


def _object_identity(
    path: str,
    kind: str,
    value: os.stat_result,
    mount_id: int,
    *,
    link_text: str | None = None,
) -> ProviderCandidateObjectIdentity:
    return ProviderCandidateObjectIdentity(
        path=path,
        kind=kind,
        device=value.st_dev,
        inode=value.st_ino,
        mount_id=mount_id,
        mode=stat.S_IMODE(value.st_mode),
        owner_uid=value.st_uid,
        link_count=value.st_nlink,
        link_text=link_text,
    )


def _ancestry_identity(
    path: str,
    value: os.stat_result,
    mount_id: int,
) -> ProviderCandidateAncestryIdentity:
    return ProviderCandidateAncestryIdentity(
        path=path,
        device=value.st_dev,
        inode=value.st_ino,
        mount_id=mount_id,
    )


def _require_same_stat(
    before: os.stat_result,
    after: os.stat_result,
    *,
    issue_path: str,
    message: str,
) -> None:
    if any(
        getattr(before, field) != getattr(after, field)
        for field in _STAT_IDENTITY_FIELDS
    ):
        _raise_candidate(f"{issue_path}.identity", message)


def _mount_id(
    directory_fd: int,
    name: str | None = None,
    *,
    issue_path: str,
) -> int:
    try:
        return _statx_mount_id(directory_fd, name)
    except MountIdentityUnavailable as exc:
        _raise_candidate(
            issue_path,
            "descriptor-bound mount identity is unavailable",
            cause=exc,
        )


def _lstat_at(directory_fd: int, name: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        _raise_candidate(
            "$.candidate_root.ancestry",
            f"candidate pathname component cannot be inspected ({_safe_errno(exc)})",
            cause=exc,
        )


def _open_directory(path: str) -> int:
    return os.open(
        path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )


def _open_directory_at(directory_fd: int, name: str) -> int:
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=directory_fd,
        )
    except OSError as exc:
        raise exc


def _open_object_at(directory_fd: int, name: str) -> int:
    flags = getattr(os, "O_PATH", os.O_RDONLY | os.O_NONBLOCK)
    return os.open(
        name,
        flags | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=directory_fd,
    )


def _path_contains(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _safe_errno(exc: OSError) -> str:
    return errno.errorcode.get(exc.errno or 0, "OS_ERROR")


def _unsafe_symlink(path: str, message: str) -> None:
    _raise_candidate(f"$.entries[{path}].link_text", message)


def _raise_candidate(
    path: str,
    message: str,
    *,
    cause: BaseException | None = None,
) -> None:
    error = ProviderIsolationCandidateError(
        (
            ProviderIsolationIssue(
                code=CANDIDATE_INVALID_CODE,
                path=path,
                message=message,
            ),
        )
    )
    if cause is None:
        raise error
    raise error from cause
