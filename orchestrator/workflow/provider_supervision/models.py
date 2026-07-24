"""Closed runtime-neutral records for provider-supervision executable IR."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping


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

