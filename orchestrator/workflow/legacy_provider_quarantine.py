"""Read-only compatibility for pre-at-least-once provider run errors."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping


_ERROR_TYPE_BY_FAMILY = MappingProxyType(
    {
        "phased": "provider_phased_interrupted_visit_quarantined",
        "session": "provider_session_interrupted_visit_quarantined",
        "supervision": (
            "provider_supervision_interrupted_visit_quarantined"
        ),
        "peer_group": (
            "provider_peer_group_interrupted_visit_quarantined"
        ),
    }
)


def read_legacy_provider_quarantine_error(
    state: Mapping[str, Any],
    *,
    family: str,
) -> dict[str, Any] | None:
    """Return one old persisted marker for exact reconstruction only."""

    expected_type = _ERROR_TYPE_BY_FAMILY.get(family)
    error = state.get("error")
    if (
        expected_type is None
        or not isinstance(error, Mapping)
        or error.get("type") != expected_type
    ):
        return None
    if state.get("status") != "failed" or state.get("current_step") is not None:
        raise ValueError(
            "legacy provider marker requires failed state without a live cursor"
        )
    return dict(error)


__all__ = ["read_legacy_provider_quarantine_error"]
