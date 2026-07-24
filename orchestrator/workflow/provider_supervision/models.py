"""Closed runtime-neutral records for provider-supervision executable IR."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal, Mapping

from ...providers.control import ProviderCancellationResult
from ...providers.session_transport import SessionIdentitySnapshot


def _closed_mapping(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{field} must be a closed object with keys {sorted(keys)}")
    return value


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


ProviderSupervisionResumeBoundaryOutcome = Literal[
    "active_eligible",
    "clean_natural_eligible",
    "wait",
    "reject",
    "timeout",
]


@dataclass(frozen=True)
class ProviderSupervisionResumeBoundaryAssessment:
    """Closed decision from one immutable worker-boundary observation."""

    outcome: ProviderSupervisionResumeBoundaryOutcome
    session_id: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in {
            "active_eligible",
            "clean_natural_eligible",
            "wait",
            "reject",
            "timeout",
        }:
            raise ValueError("resume-boundary assessment outcome is invalid")
        if self.outcome in {"active_eligible", "clean_natural_eligible"}:
            _nonempty_string(
                self.session_id,
                "resume_boundary_assessment.session_id",
            )
        elif self.session_id is not None:
            raise ValueError(
                "ineligible resume-boundary assessment forbids a session id"
            )


def _unique_session_id(
    snapshot: SessionIdentitySnapshot | None,
    *,
    terminal_seen: bool,
) -> str | None:
    if not isinstance(snapshot, SessionIdentitySnapshot):
        return None
    if (
        snapshot.status != "unique"
        or len(snapshot.session_ids) != 1
        or not isinstance(snapshot.session_ids[0], str)
        or not snapshot.session_ids[0]
        or snapshot.error is not None
        or snapshot.resume_boundary_seen is not True
        or snapshot.terminal_seen is not terminal_seen
    ):
        return None
    return snapshot.session_ids[0]


def classify_provider_supervision_resume_boundary(
    *,
    snapshot: SessionIdentitySnapshot | None,
    terminal_proof: ProviderCancellationResult | None,
    execution_promotable: bool | None,
    member_deadline_live: bool,
    whole_deadline_live: bool,
) -> ProviderSupervisionResumeBoundaryAssessment:
    """Classify the only two boundaries eligible for one native resume."""

    if snapshot is not None and not isinstance(
        snapshot,
        SessionIdentitySnapshot,
    ):
        raise TypeError("snapshot must be a SessionIdentitySnapshot or None")
    if terminal_proof is not None and not isinstance(
        terminal_proof,
        ProviderCancellationResult,
    ):
        raise TypeError(
            "terminal_proof must be a ProviderCancellationResult or None"
        )
    if execution_promotable is not None and not isinstance(
        execution_promotable,
        bool,
    ):
        raise TypeError("execution_promotable must be bool or None")
    if not isinstance(member_deadline_live, bool):
        raise TypeError("member_deadline_live must be bool")
    if not isinstance(whole_deadline_live, bool):
        raise TypeError("whole_deadline_live must be bool")

    if not whole_deadline_live:
        return ProviderSupervisionResumeBoundaryAssessment("timeout")

    if terminal_proof is None:
        if snapshot is not None and snapshot.terminal_seen is True:
            return ProviderSupervisionResumeBoundaryAssessment("wait")
        if not member_deadline_live:
            return ProviderSupervisionResumeBoundaryAssessment("timeout")
        if snapshot is None or snapshot.status == "missing":
            return ProviderSupervisionResumeBoundaryAssessment("wait")
        if snapshot.status in {"ambiguous", "invalid"}:
            return ProviderSupervisionResumeBoundaryAssessment("reject")
        if snapshot.status != "unique":
            return ProviderSupervisionResumeBoundaryAssessment("reject")
        if not snapshot.resume_boundary_seen:
            return ProviderSupervisionResumeBoundaryAssessment("wait")
        session_id = _unique_session_id(snapshot, terminal_seen=False)
        if session_id is None:
            return ProviderSupervisionResumeBoundaryAssessment("reject")
        return ProviderSupervisionResumeBoundaryAssessment(
            "active_eligible",
            session_id=session_id,
        )

    final_snapshot = terminal_proof.final_session_snapshot
    if terminal_proof.disposition == "cancelled":
        session_id = _unique_session_id(
            final_snapshot,
            terminal_seen=False,
        )
        structurally_complete_cancelled_boundary = (
            terminal_proof.proof_complete is True
            and terminal_proof.leader_reaped is True
            and terminal_proof.pgid_empty is True
            and terminal_proof.capture_threads_joined is True
            and terminal_proof.execution_joined is True
            and terminal_proof.final_identity_valid is True
            and terminal_proof.natural_exit_with_lingering_group is False
            and terminal_proof.error is None
            and execution_promotable is False
            and snapshot == final_snapshot
            and session_id is not None
        )
        if not structurally_complete_cancelled_boundary:
            return ProviderSupervisionResumeBoundaryAssessment("reject")
        if not member_deadline_live:
            return ProviderSupervisionResumeBoundaryAssessment("timeout")
        return ProviderSupervisionResumeBoundaryAssessment(
            "active_eligible",
            session_id=session_id,
        )

    session_id = _unique_session_id(final_snapshot, terminal_seen=True)
    complete_natural_boundary = (
        terminal_proof.disposition == "natural_exit"
        and terminal_proof.leader_return_code == 0
        and terminal_proof.proof_complete is True
        and terminal_proof.leader_reaped is True
        and terminal_proof.pgid_empty is True
        and terminal_proof.capture_threads_joined is True
        and terminal_proof.execution_joined is True
        and terminal_proof.final_identity_valid is True
        and terminal_proof.natural_exit_with_lingering_group is False
        and terminal_proof.error is None
        and execution_promotable is True
        and snapshot == final_snapshot
        and session_id is not None
    )
    if not complete_natural_boundary:
        return ProviderSupervisionResumeBoundaryAssessment("reject")
    return ProviderSupervisionResumeBoundaryAssessment(
        "clean_natural_eligible",
        session_id=session_id,
    )


@dataclass(frozen=True)
class ProviderSupervisionObservation:
    """The single directed supervisor-to-worker observation edge."""

    observer_member_id: str
    observed_member_id: str

    def __post_init__(self) -> None:
        _nonempty_string(self.observer_member_id, "observation.observer_member_id")
        _nonempty_string(self.observed_member_id, "observation.observed_member_id")
        if self.observer_member_id == self.observed_member_id:
            raise ValueError("observation members must be distinct")

    @classmethod
    def from_dict(cls, value: Any) -> "ProviderSupervisionObservation":
        node = _closed_mapping(
            value,
            frozenset({"observer_member_id", "observed_member_id"}),
            "observation",
        )
        return cls(
            observer_member_id=_nonempty_string(
                node["observer_member_id"],
                "observation.observer_member_id",
            ),
            observed_member_id=_nonempty_string(
                node["observed_member_id"],
                "observation.observed_member_id",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "observer_member_id": self.observer_member_id,
            "observed_member_id": self.observed_member_id,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True)
class ProviderSupervisionSourceOwnership:
    """Closed authored/compiler source-map owners for the generated group."""

    form: str
    worker_binding: str
    supervisor_binding: str
    observation: str
    settlement: str

    def __post_init__(self) -> None:
        for name in (
            "form",
            "worker_binding",
            "supervisor_binding",
            "observation",
            "settlement",
        ):
            _nonempty_string(getattr(self, name), f"source_ownership.{name}")

    @classmethod
    def from_dict(cls, value: Any) -> "ProviderSupervisionSourceOwnership":
        keys = frozenset(
            {
                "form",
                "worker_binding",
                "supervisor_binding",
                "observation",
                "settlement",
            }
        )
        node = _closed_mapping(value, keys, "source_ownership")
        return cls(
            **{
                name: _nonempty_string(node[name], f"source_ownership.{name}")
                for name in keys
            }
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "form": self.form,
            "worker_binding": self.worker_binding,
            "supervisor_binding": self.supervisor_binding,
            "observation": self.observation,
            "settlement": self.settlement,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict())
