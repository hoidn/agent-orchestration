"""Stable visit-qualified path templates for provider-supervision turns."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import Any, Mapping
from urllib.parse import quote


_TURN_ROLES = frozenset(
    {"worker_fresh", "worker_resume", "supervisor_directive"}
)


def _closed_mapping(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{field} must be a closed object with keys {sorted(keys)}")
    return value


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _relative_template(value: Any, field: str) -> str:
    raw = _nonempty_string(value, field)
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{field} must be a safe relative path template")
    if raw.startswith("~"):
        raise ValueError(f"{field} must not name a home-relative path")
    return raw


def _component(value: str, field: str) -> str:
    raw = _nonempty_string(value, field)
    return quote(raw, safe="-._")


@dataclass(frozen=True)
class ProviderSupervisionTurnPath:
    """One member turn's distinct evidence and provisional-result locations."""

    member_id: str
    turn_role: str
    evidence_relpath: str
    provisional_bundle_relpath: str

    def __post_init__(self) -> None:
        _nonempty_string(self.member_id, "turn_path.member_id")
        if self.turn_role not in _TURN_ROLES:
            raise ValueError("turn_path.turn_role is invalid")
        _relative_template(self.evidence_relpath, "turn_path.evidence_relpath")
        _relative_template(
            self.provisional_bundle_relpath,
            "turn_path.provisional_bundle_relpath",
        )
        if self.evidence_relpath == self.provisional_bundle_relpath:
            raise ValueError("turn evidence and provisional bundle paths must differ")

    @classmethod
    def from_dict(cls, value: Any) -> "ProviderSupervisionTurnPath":
        node = _closed_mapping(
            value,
            frozenset(
                {
                    "member_id",
                    "turn_role",
                    "evidence_relpath",
                    "provisional_bundle_relpath",
                }
            ),
            "turn_path",
        )
        return cls(
            member_id=_nonempty_string(node["member_id"], "turn_path.member_id"),
            turn_role=_nonempty_string(node["turn_role"], "turn_path.turn_role"),
            evidence_relpath=_relative_template(
                node["evidence_relpath"],
                "turn_path.evidence_relpath",
            ),
            provisional_bundle_relpath=_relative_template(
                node["provisional_bundle_relpath"],
                "turn_path.provisional_bundle_relpath",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "member_id": self.member_id,
            "turn_role": self.turn_role,
            "evidence_relpath": self.evidence_relpath,
            "provisional_bundle_relpath": self.provisional_bundle_relpath,
        }


@dataclass(frozen=True)
class ProviderSupervisionPaths:
    """The fixed three-turn path plan for one executable group node."""

    worker_fresh: ProviderSupervisionTurnPath
    worker_resume: ProviderSupervisionTurnPath
    supervisor_directive: ProviderSupervisionTurnPath

    def __post_init__(self) -> None:
        if (
            self.worker_fresh.turn_role,
            self.worker_resume.turn_role,
            self.supervisor_directive.turn_role,
        ) != (
            "worker_fresh",
            "worker_resume",
            "supervisor_directive",
        ):
            raise ValueError("provider supervision paths must declare all fixed roles")
        if self.worker_fresh.member_id != self.worker_resume.member_id:
            raise ValueError("worker fresh and resume paths must share one member id")
        if self.worker_fresh.member_id == self.supervisor_directive.member_id:
            raise ValueError("worker and supervisor path members must be distinct")
        locations = {
            path
            for turn in (
                self.worker_fresh,
                self.worker_resume,
                self.supervisor_directive,
            )
            for path in (turn.evidence_relpath, turn.provisional_bundle_relpath)
        }
        if len(locations) != 6:
            raise ValueError("provider supervision turn paths must be unique")

    @classmethod
    def from_dict(cls, value: Any) -> "ProviderSupervisionPaths":
        node = _closed_mapping(
            value,
            frozenset(
                {"worker_fresh", "worker_resume", "supervisor_directive"}
            ),
            "paths",
        )
        return cls(
            worker_fresh=ProviderSupervisionTurnPath.from_dict(
                node["worker_fresh"]
            ),
            worker_resume=ProviderSupervisionTurnPath.from_dict(
                node["worker_resume"]
            ),
            supervisor_directive=ProviderSupervisionTurnPath.from_dict(
                node["supervisor_directive"]
            ),
        )

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {
            "worker_fresh": self.worker_fresh.to_dict(),
            "worker_resume": self.worker_resume.to_dict(),
            "supervisor_directive": self.supervisor_directive.to_dict(),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )


def derive_provider_supervision_paths(
    *,
    node_id: str,
    worker_member_id: str,
    supervisor_member_id: str,
) -> ProviderSupervisionPaths:
    """Derive run-root-relative templates without embedding live runtime data."""

    node = _component(node_id, "node_id")
    worker = _component(worker_member_id, "worker_member_id")
    supervisor = _component(supervisor_member_id, "supervisor_member_id")
    if worker_member_id == supervisor_member_id:
        raise ValueError("worker and supervisor member ids must be distinct")
    prefix = f"provider-supervision/{node}/visits/{{visit}}/members"

    def turn(member: str, member_id: str, role: str, turn_name: str):
        turn_prefix = f"{prefix}/{member}/turns/{turn_name}"
        return ProviderSupervisionTurnPath(
            member_id=member_id,
            turn_role=role,
            evidence_relpath=f"{turn_prefix}/evidence.json",
            provisional_bundle_relpath=f"{turn_prefix}/provisional-result.json",
        )

    return ProviderSupervisionPaths(
        worker_fresh=turn(worker, worker_member_id, "worker_fresh", "fresh"),
        worker_resume=turn(worker, worker_member_id, "worker_resume", "resume"),
        supervisor_directive=turn(
            supervisor,
            supervisor_member_id,
            "supervisor_directive",
            "directive",
        ),
    )
