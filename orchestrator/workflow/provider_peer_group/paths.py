"""Closed visit- and attempt-qualified paths for provider peer groups."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping
from urllib.parse import quote

from ..._common.canonical import compact_ascii_json_dumps
from ..._common.validation import (
    closed_mapping,
    nonempty_string,
    ordinary_integer,
)


_MIN_MEMBER_COUNT = 2
_MAX_MEMBER_COUNT = 8
_ENCODED_COMPONENT = re.compile(
    r"(?:[A-Za-z0-9._~-]|%[0-9A-F]{2})+"
)


def _closed_mapping(
    value: Any,
    keys: frozenset[str],
    field: str,
) -> Mapping[str, Any]:
    return closed_mapping(value, keys, field)


def _nonempty_string(value: Any, field: str) -> str:
    return nonempty_string(value, field)


def _positive_int(value: Any, field: str) -> int:
    try:
        return ordinary_integer(value, field, minimum=1)
    except ValueError:
        raise ValueError(f"{field} must be a positive integer") from None


def _component(value: Any, field: str) -> str:
    raw = _nonempty_string(value, field)
    if raw in {".", ".."}:
        raise ValueError(f"{field} must not be '.' or '..'")
    try:
        raw.encode("utf-8", errors="strict")
        return quote(raw, safe="-._")
    except UnicodeError as exc:
        raise ValueError(f"{field} must be well-formed UTF-8") from exc


def _relative_template(
    value: Any,
    field: str,
    *,
    visit: bool,
    attempt: bool,
) -> str:
    raw = _nonempty_string(value, field)
    path = PurePosixPath(raw)
    parts = raw.split("/")
    if (
        path.is_absolute()
        or raw.startswith("~")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"{field} must be a safe relative path template")

    expected_visit_count = 1 if visit else 0
    expected_attempt_count = 1 if attempt else 0
    if (
        raw.count("{visit}") != expected_visit_count
        or raw.count("{attempt}") != expected_attempt_count
    ):
        raise ValueError(
            f"{field} must contain the exact visit/attempt placeholders"
        )
    without_placeholders = raw.replace("{visit}", "").replace(
        "{attempt}",
        "",
    )
    if "{" in without_placeholders or "}" in without_placeholders:
        raise ValueError(f"{field} contains an unsupported placeholder")
    return raw


def _validate_encoded_component(value: str, field: str) -> None:
    if _ENCODED_COMPONENT.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonically encoded component")


def _canonical_json(value: Mapping[str, Any]) -> str:
    return compact_ascii_json_dumps(value)


@dataclass(frozen=True, slots=True)
class PeerMemberPathPlan:
    """The four immutable path templates owned by one authored member."""

    member_id: str
    prompt_dependencies_relpath: str
    injected_messages_relpath: str
    evidence_relpath: str
    provisional_bundle_relpath: str

    def __post_init__(self) -> None:
        _component(self.member_id, "member_path.member_id")
        for name in (
            "prompt_dependencies_relpath",
            "injected_messages_relpath",
            "evidence_relpath",
            "provisional_bundle_relpath",
        ):
            _relative_template(
                getattr(self, name),
                f"member_path.{name}",
                visit=True,
                attempt=True,
            )
        if len(set(self.leaf_relpaths())) != 4:
            raise ValueError("member path templates must be distinct")

    @classmethod
    def from_dict(cls, value: Any) -> "PeerMemberPathPlan":
        node = _closed_mapping(
            value,
            frozenset(
                {
                    "member_id",
                    "prompt_dependencies_relpath",
                    "injected_messages_relpath",
                    "evidence_relpath",
                    "provisional_bundle_relpath",
                }
            ),
            "member_path",
        )
        return cls(
            member_id=_nonempty_string(
                node["member_id"],
                "member_path.member_id",
            ),
            prompt_dependencies_relpath=_relative_template(
                node["prompt_dependencies_relpath"],
                "member_path.prompt_dependencies_relpath",
                visit=True,
                attempt=True,
            ),
            injected_messages_relpath=_relative_template(
                node["injected_messages_relpath"],
                "member_path.injected_messages_relpath",
                visit=True,
                attempt=True,
            ),
            evidence_relpath=_relative_template(
                node["evidence_relpath"],
                "member_path.evidence_relpath",
                visit=True,
                attempt=True,
            ),
            provisional_bundle_relpath=_relative_template(
                node["provisional_bundle_relpath"],
                "member_path.provisional_bundle_relpath",
                visit=True,
                attempt=True,
            ),
        )

    def leaf_relpaths(self) -> tuple[str, str, str, str]:
        return (
            self.prompt_dependencies_relpath,
            self.injected_messages_relpath,
            self.evidence_relpath,
            self.provisional_bundle_relpath,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "member_id": self.member_id,
            "prompt_dependencies_relpath": (
                self.prompt_dependencies_relpath
            ),
            "injected_messages_relpath": self.injected_messages_relpath,
            "evidence_relpath": self.evidence_relpath,
            "provisional_bundle_relpath": (
                self.provisional_bundle_relpath
            ),
        }


@dataclass(frozen=True, slots=True)
class PeerGroupPathPlan:
    """The closed authored-order path plan for one executable peer node."""

    visit_root_relpath: str
    terminal_evidence_relpath: str
    members: tuple[PeerMemberPathPlan, ...]

    def __post_init__(self) -> None:
        _validate_path_plan(self)

    @classmethod
    def from_dict(cls, value: Any) -> "PeerGroupPathPlan":
        node = _closed_mapping(
            value,
            frozenset(
                {
                    "visit_root_relpath",
                    "terminal_evidence_relpath",
                    "members",
                }
            ),
            "paths",
        )
        raw_members = node["members"]
        if not isinstance(raw_members, list):
            raise ValueError("paths.members must be a list")
        return cls(
            visit_root_relpath=_relative_template(
                node["visit_root_relpath"],
                "paths.visit_root_relpath",
                visit=True,
                attempt=False,
            ),
            terminal_evidence_relpath=_relative_template(
                node["terminal_evidence_relpath"],
                "paths.terminal_evidence_relpath",
                visit=True,
                attempt=False,
            ),
            members=tuple(
                PeerMemberPathPlan.from_dict(member)
                for member in raw_members
            ),
        )

    def leaf_relpaths(self) -> tuple[str, ...]:
        return (
            self.terminal_evidence_relpath,
            *(
                path
                for member in self.members
                for path in member.leaf_relpaths()
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "visit_root_relpath": self.visit_root_relpath,
            "terminal_evidence_relpath": self.terminal_evidence_relpath,
            "members": [member.to_dict() for member in self.members],
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())


def _validate_path_plan(plan: PeerGroupPathPlan) -> None:
    visit_root = _relative_template(
        plan.visit_root_relpath,
        "paths.visit_root_relpath",
        visit=True,
        attempt=False,
    )
    parts = visit_root.split("/")
    if (
        len(parts) != 4
        or parts[0] != "provider-peer-group"
        or parts[2:] != ["visits", "{visit}"]
    ):
        raise ValueError(
            "visit root must match "
            "'provider-peer-group/<node>/visits/{visit}'"
        )
    _validate_encoded_component(parts[1], "paths.node_component")

    if plan.terminal_evidence_relpath != f"{visit_root}/evidence.json":
        raise ValueError(
            "terminal evidence must be visit-root-relative evidence.json"
        )
    _relative_template(
        plan.terminal_evidence_relpath,
        "paths.terminal_evidence_relpath",
        visit=True,
        attempt=False,
    )

    if not isinstance(plan.members, tuple):
        raise ValueError("paths.members must be a tuple")
    if not _MIN_MEMBER_COUNT <= len(plan.members) <= _MAX_MEMBER_COUNT:
        raise ValueError("provider peer groups require 2 through 8 members")
    if not all(isinstance(member, PeerMemberPathPlan) for member in plan.members):
        raise ValueError(
            "paths.members must contain only PeerMemberPathPlan records"
        )

    member_ids = tuple(member.member_id for member in plan.members)
    if len(set(member_ids)) != len(member_ids):
        raise ValueError("provider peer group member ids must be unique")

    filenames = (
        ("prompt_dependencies_relpath", "prompt-dependencies.json"),
        ("injected_messages_relpath", "injected-messages.jsonl"),
        ("evidence_relpath", "evidence.json"),
        ("provisional_bundle_relpath", "provisional-result.json"),
    )
    for member in plan.members:
        member_component = _component(
            member.member_id,
            "member_path.member_id",
        )
        attempt_root = (
            f"{visit_root}/members/{member_component}/"
            "attempt-{attempt}"
        )
        for field, filename in filenames:
            expected = f"{attempt_root}/{filename}"
            if getattr(member, field) != expected:
                raise ValueError(
                    f"member_path.{field} must match the canonical template"
                )

    leaves = plan.leaf_relpaths()
    if len(set(leaves)) != len(leaves):
        raise ValueError("provider peer group path templates must be unique")


@dataclass(frozen=True, slots=True)
class RealizedPeerMemberPaths:
    """The four concrete filesystem leaves for one exact member attempt."""

    member_id: str
    attempt_ordinal: int
    prompt_dependencies_path: Path
    injected_messages_path: Path
    evidence_path: Path
    provisional_bundle_path: Path

    def __post_init__(self) -> None:
        _component(self.member_id, "realized_member.member_id")
        _positive_int(
            self.attempt_ordinal,
            "realized_member.attempt_ordinal",
        )
        for name in (
            "prompt_dependencies_path",
            "injected_messages_path",
            "evidence_path",
            "provisional_bundle_path",
        ):
            _absolute_normalized_path(
                getattr(self, name),
                f"realized_member.{name}",
            )
        if len(set(self.leaf_paths())) != 4:
            raise ValueError("realized member paths must be distinct")

    @classmethod
    def from_dict(cls, value: Any) -> "RealizedPeerMemberPaths":
        node = _closed_mapping(
            value,
            frozenset(
                {
                    "member_id",
                    "attempt_ordinal",
                    "prompt_dependencies_path",
                    "injected_messages_path",
                    "evidence_path",
                    "provisional_bundle_path",
                }
            ),
            "realized_member",
        )
        return cls(
            member_id=_nonempty_string(
                node["member_id"],
                "realized_member.member_id",
            ),
            attempt_ordinal=_positive_int(
                node["attempt_ordinal"],
                "realized_member.attempt_ordinal",
            ),
            prompt_dependencies_path=_path_from_wire(
                node["prompt_dependencies_path"],
                "realized_member.prompt_dependencies_path",
            ),
            injected_messages_path=_path_from_wire(
                node["injected_messages_path"],
                "realized_member.injected_messages_path",
            ),
            evidence_path=_path_from_wire(
                node["evidence_path"],
                "realized_member.evidence_path",
            ),
            provisional_bundle_path=_path_from_wire(
                node["provisional_bundle_path"],
                "realized_member.provisional_bundle_path",
            ),
        )

    def leaf_paths(self) -> tuple[Path, Path, Path, Path]:
        return (
            self.prompt_dependencies_path,
            self.injected_messages_path,
            self.evidence_path,
            self.provisional_bundle_path,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "member_id": self.member_id,
            "attempt_ordinal": self.attempt_ordinal,
            "prompt_dependencies_path": str(self.prompt_dependencies_path),
            "injected_messages_path": str(self.injected_messages_path),
            "evidence_path": str(self.evidence_path),
            "provisional_bundle_path": str(self.provisional_bundle_path),
        }


@dataclass(frozen=True, slots=True)
class RealizedPeerGroupPaths:
    """The closed concrete path set for one exact group visit."""

    visit_root: Path
    terminal_evidence_path: Path
    members: tuple[RealizedPeerMemberPaths, ...]

    def __post_init__(self) -> None:
        _validate_realized_paths(self)

    @classmethod
    def from_dict(cls, value: Any) -> "RealizedPeerGroupPaths":
        node = _closed_mapping(
            value,
            frozenset(
                {
                    "visit_root",
                    "terminal_evidence_path",
                    "members",
                }
            ),
            "realized_paths",
        )
        raw_members = node["members"]
        if not isinstance(raw_members, list):
            raise ValueError("realized_paths.members must be a list")
        return cls(
            visit_root=_path_from_wire(
                node["visit_root"],
                "realized_paths.visit_root",
            ),
            terminal_evidence_path=_path_from_wire(
                node["terminal_evidence_path"],
                "realized_paths.terminal_evidence_path",
            ),
            members=tuple(
                RealizedPeerMemberPaths.from_dict(member)
                for member in raw_members
            ),
        )

    def leaf_paths(self) -> tuple[Path, ...]:
        return (
            self.terminal_evidence_path,
            *(
                path
                for member in self.members
                for path in member.leaf_paths()
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "visit_root": str(self.visit_root),
            "terminal_evidence_path": str(self.terminal_evidence_path),
            "members": [member.to_dict() for member in self.members],
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())


def _path_from_wire(value: Any, field: str) -> Path:
    raw = _nonempty_string(value, field)
    return Path(raw)


def _absolute_normalized_path(value: Any, field: str) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise ValueError(f"{field} must be an absolute Path")
    if ".." in value.parts:
        raise ValueError(f"{field} must not contain a parent component")
    return value


def _validate_realized_paths(paths: RealizedPeerGroupPaths) -> None:
    visit_root = _absolute_normalized_path(
        paths.visit_root,
        "realized_paths.visit_root",
    )
    visit_parts = visit_root.parts
    if (
        len(visit_parts) < 5
        or visit_root.parent.name != "visits"
        or visit_root.parent.parent.parent.name != "provider-peer-group"
    ):
        raise ValueError("realized visit root has an invalid layout")
    _validate_encoded_component(
        visit_root.parent.parent.name,
        "realized_paths.node_component",
    )
    _positive_int_from_decimal(
        visit_root.name,
        "realized_paths.visit_count",
    )

    if paths.terminal_evidence_path != visit_root / "evidence.json":
        raise ValueError(
            "realized terminal evidence must be visit-root evidence.json"
        )
    _absolute_normalized_path(
        paths.terminal_evidence_path,
        "realized_paths.terminal_evidence_path",
    )

    if not isinstance(paths.members, tuple):
        raise ValueError("realized_paths.members must be a tuple")
    if not _MIN_MEMBER_COUNT <= len(paths.members) <= _MAX_MEMBER_COUNT:
        raise ValueError("realized peer paths require 2 through 8 members")
    if not all(
        isinstance(member, RealizedPeerMemberPaths)
        for member in paths.members
    ):
        raise ValueError(
            "realized_paths.members must contain realized member records"
        )

    member_ids = tuple(member.member_id for member in paths.members)
    if len(set(member_ids)) != len(member_ids):
        raise ValueError("realized member ids must be unique")

    filenames = (
        ("prompt_dependencies_path", "prompt-dependencies.json"),
        ("injected_messages_path", "injected-messages.jsonl"),
        ("evidence_path", "evidence.json"),
        ("provisional_bundle_path", "provisional-result.json"),
    )
    for member in paths.members:
        member_root = (
            visit_root
            / "members"
            / _component(member.member_id, "realized_member.member_id")
            / f"attempt-{member.attempt_ordinal}"
        )
        for field, filename in filenames:
            if getattr(member, field) != member_root / filename:
                raise ValueError(
                    f"realized_member.{field} has an invalid layout"
                )

    leaves = paths.leaf_paths()
    if len(set(leaves)) != len(leaves):
        raise ValueError("realized provider peer paths must be unique")
    run_root = _run_root_for_visit(visit_root)
    if any(not path.is_relative_to(run_root) for path in leaves):
        raise ValueError("realized provider peer path escapes run root")


def _positive_int_from_decimal(value: str, field: str) -> int:
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"{field} must be a positive integer")
    return _positive_int(int(value), field)


def _run_root_for_visit(visit_root: Path) -> Path:
    try:
        return visit_root.parents[3]
    except IndexError as exc:
        raise ValueError("realized visit root has no run root") from exc


def derive_provider_peer_group_paths(
    *,
    node_id: str,
    member_ids: tuple[str, ...],
) -> PeerGroupPathPlan:
    """Derive exact run-root-relative templates in authored member order."""

    node = _component(node_id, "node_id")
    if not isinstance(member_ids, tuple):
        raise ValueError("member_ids must be an authored-order tuple")
    if not _MIN_MEMBER_COUNT <= len(member_ids) <= _MAX_MEMBER_COUNT:
        raise ValueError("provider peer groups require 2 through 8 members")
    if any(not isinstance(member_id, str) for member_id in member_ids):
        raise ValueError("member_ids must contain only strings")
    if len(set(member_ids)) != len(member_ids):
        raise ValueError("provider peer group member ids must be unique")

    visit_root = f"provider-peer-group/{node}/visits/{{visit}}"
    members: list[PeerMemberPathPlan] = []
    for member_id in member_ids:
        member = _component(member_id, "member_id")
        attempt_root = (
            f"{visit_root}/members/{member}/attempt-{{attempt}}"
        )
        members.append(
            PeerMemberPathPlan(
                member_id=member_id,
                prompt_dependencies_relpath=(
                    f"{attempt_root}/prompt-dependencies.json"
                ),
                injected_messages_relpath=(
                    f"{attempt_root}/injected-messages.jsonl"
                ),
                evidence_relpath=f"{attempt_root}/evidence.json",
                provisional_bundle_relpath=(
                    f"{attempt_root}/provisional-result.json"
                ),
            )
        )
    return PeerGroupPathPlan(
        visit_root_relpath=visit_root,
        terminal_evidence_relpath=f"{visit_root}/evidence.json",
        members=tuple(members),
    )


def realize_provider_peer_group_paths(
    *,
    run_root: Path,
    plan: PeerGroupPathPlan,
    visit_count: int,
    attempt_ordinals: Mapping[str, int],
) -> RealizedPeerGroupPaths:
    """Bind one validated plan to exact visit and attempt ordinals."""

    if not isinstance(plan, PeerGroupPathPlan):
        raise ValueError("plan must be a PeerGroupPathPlan")
    _validate_path_plan(plan)
    visit = _positive_int(visit_count, "visit_count")
    if not isinstance(attempt_ordinals, Mapping):
        raise ValueError("attempt_ordinals must be a mapping")
    expected_members = tuple(member.member_id for member in plan.members)
    if set(attempt_ordinals) != set(expected_members):
        raise ValueError(
            "attempt_ordinals must match the exact planned member set"
        )
    ordinals = {
        member_id: _positive_int(
            attempt_ordinals[member_id],
            f"attempt_ordinals[{member_id!r}]",
        )
        for member_id in expected_members
    }

    try:
        root = Path(run_root).resolve(strict=False)
    except (OSError, RuntimeError, TypeError) as exc:
        raise ValueError("run_root cannot be resolved") from exc

    visit_root = _realize_relpath(
        run_root=root,
        template=plan.visit_root_relpath,
        visit=visit,
        attempt=None,
    )
    terminal_evidence = _realize_relpath(
        run_root=root,
        template=plan.terminal_evidence_relpath,
        visit=visit,
        attempt=None,
    )
    realized_members = tuple(
        RealizedPeerMemberPaths(
            member_id=member.member_id,
            attempt_ordinal=ordinals[member.member_id],
            prompt_dependencies_path=_realize_relpath(
                run_root=root,
                template=member.prompt_dependencies_relpath,
                visit=visit,
                attempt=ordinals[member.member_id],
            ),
            injected_messages_path=_realize_relpath(
                run_root=root,
                template=member.injected_messages_relpath,
                visit=visit,
                attempt=ordinals[member.member_id],
            ),
            evidence_path=_realize_relpath(
                run_root=root,
                template=member.evidence_relpath,
                visit=visit,
                attempt=ordinals[member.member_id],
            ),
            provisional_bundle_path=_realize_relpath(
                run_root=root,
                template=member.provisional_bundle_relpath,
                visit=visit,
                attempt=ordinals[member.member_id],
            ),
        )
        for member in plan.members
    )
    realized = RealizedPeerGroupPaths(
        visit_root=visit_root,
        terminal_evidence_path=terminal_evidence,
        members=realized_members,
    )
    if _run_root_for_visit(realized.visit_root) != root:
        raise ValueError("realized visit root does not preserve run root")
    return realized


def _realize_relpath(
    *,
    run_root: Path,
    template: str,
    visit: int,
    attempt: int | None,
) -> Path:
    rendered = template.replace("{visit}", str(visit))
    if attempt is not None:
        rendered = rendered.replace("{attempt}", str(attempt))
    if "{" in rendered or "}" in rendered:
        raise ValueError("path template was not fully realized")
    try:
        candidate = (run_root / PurePosixPath(rendered)).resolve(
            strict=False
        )
    except (OSError, RuntimeError) as exc:
        raise ValueError("realized path cannot be resolved") from exc
    if candidate == run_root or not candidate.is_relative_to(run_root):
        raise ValueError("realized provider peer path escapes run root")
    return candidate


def preflight_provider_peer_group_visit_root(
    *,
    run_root: Path,
    plan: PeerGroupPathPlan,
    visit_count: int,
) -> Path:
    """Reject a stale visit preimage before allocating durable attempts."""

    if not isinstance(plan, PeerGroupPathPlan):
        raise ValueError("plan must be a PeerGroupPathPlan")
    _validate_path_plan(plan)
    visit = _positive_int(visit_count, "visit_count")
    try:
        root = Path(run_root).resolve(strict=False)
    except (OSError, RuntimeError, TypeError) as exc:
        raise ValueError("run_root cannot be resolved") from exc
    visit_root = _realize_relpath(
        run_root=root,
        template=plan.visit_root_relpath,
        visit=visit,
        attempt=None,
    )
    _preflight_provider_peer_group_visit_root(
        run_root=root,
        visit_root=visit_root,
    )
    return visit_root


def _preflight_provider_peer_group_visit_root(
    *,
    run_root: Path,
    visit_root: Path,
) -> None:
    try:
        resolved_run_root = run_root.resolve(strict=False)
        resolved_visit_root = visit_root.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ValueError("provider peer visit root cannot be resolved") from exc
    if (
        resolved_visit_root == resolved_run_root
        or not resolved_visit_root.is_relative_to(resolved_run_root)
    ):
        raise ValueError("provider peer visit root escapes run root")
    if visit_root.is_symlink():
        raise FileExistsError(
            f"provider peer visit preimage exists: {visit_root}"
        )
    if visit_root.exists():
        if not visit_root.is_dir():
            raise FileExistsError(
                f"provider peer visit root is not a directory: {visit_root}"
            )
        try:
            has_entries = next(visit_root.iterdir(), None) is not None
        except OSError as exc:
            raise FileExistsError(
                f"provider peer visit root cannot be inspected: {visit_root}"
            ) from exc
        if has_entries:
            raise FileExistsError(
                f"provider peer visit root is nonempty: {visit_root}"
            )

    ancestor = visit_root.parent
    while ancestor != resolved_run_root:
        if ancestor.is_symlink() and not ancestor.exists():
            raise FileExistsError(
                f"provider peer path ancestor is a broken symlink: {ancestor}"
            )
        if ancestor.exists() and not ancestor.is_dir():
            raise FileExistsError(
                f"provider peer path ancestor is not a directory: {ancestor}"
            )
        ancestor = ancestor.parent


def preflight_provider_peer_group_paths(
    paths: RealizedPeerGroupPaths,
) -> None:
    """Validate a no-write preimage for one complete group visit."""

    if not isinstance(paths, RealizedPeerGroupPaths):
        raise ValueError("paths must be RealizedPeerGroupPaths")
    _validate_realized_paths(paths)

    run_root = _run_root_for_visit(paths.visit_root)
    resolved_run_root = run_root.resolve(strict=False)
    _preflight_provider_peer_group_visit_root(
        run_root=resolved_run_root,
        visit_root=paths.visit_root,
    )
    for leaf in paths.leaf_paths():
        try:
            resolved_leaf = leaf.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise ValueError("provider peer leaf cannot be resolved") from exc
        if (
            resolved_leaf == resolved_run_root
            or not resolved_leaf.is_relative_to(resolved_run_root)
        ):
            raise ValueError("provider peer leaf escapes run root")
        if leaf.exists() or leaf.is_symlink():
            raise FileExistsError(f"provider peer leaf exists: {leaf}")


__all__ = [
    "PeerGroupPathPlan",
    "PeerMemberPathPlan",
    "RealizedPeerGroupPaths",
    "RealizedPeerMemberPaths",
    "derive_provider_peer_group_paths",
    "preflight_provider_peer_group_paths",
    "preflight_provider_peer_group_visit_root",
    "realize_provider_peer_group_paths",
]
