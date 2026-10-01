"""Default values for hidden runtime-context parameters."""

from __future__ import annotations

from typing import Any


def _field_descriptor(
    type_descriptor: dict[str, Any] | None,
    name: str,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if isinstance(type_descriptor, dict):
        for row in type_descriptor.get("fields", ()):
            if isinstance(row, dict) and row.get("name") == name and isinstance(row.get("type"), dict):
                return row["type"]
    return fallback


def run_context_value(type_descriptor: dict[str, Any] | None = None) -> dict[str, Any]:
    """The run context supplied by the executor at the entry boundary."""

    value = {
        "k": "record",
        "fields": [
            ["run-id", {"k": "context", "field": "run-id"}],
            [
                "state-root",
                {
                    "k": "lit",
                    "v": "state/run",
                    "type": _field_descriptor(
                        type_descriptor,
                        "state-root",
                        {"kind": "path", "name": "Path.state-root", "under": "state", "must_exist_target": False},
                    ),
                },
            ],
            [
                "artifact-root",
                {
                    "k": "lit",
                    "v": "artifacts/run",
                    "type": _field_descriptor(
                        type_descriptor,
                        "artifact-root",
                        {"kind": "path", "name": "Path.artifact-root", "under": "artifacts", "must_exist_target": False},
                    ),
                },
            ],
        ],
    }
    if type_descriptor is not None:
        value["type"] = type_descriptor
    return value


def phase_context_value(
    run: dict[str, Any],
    phase_name: str,
    type_descriptor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A phase context derived from the caller's already-bound run context."""

    value = {
        "k": "record",
        "fields": [
            ["run", run],
            [
                "phase-name",
                {
                    "k": "lit",
                    "v": phase_name,
                    "type": _field_descriptor(
                        type_descriptor,
                        "phase-name",
                        {"kind": "primitive", "name": "Symbol"},
                    ),
                },
            ],
            [
                "state-root",
                {
                    "k": "lit",
                    "v": f"state/{phase_name}",
                    "type": _field_descriptor(
                        type_descriptor,
                        "state-root",
                        {"kind": "path", "name": "Path.state-root", "under": "state", "must_exist_target": False},
                    ),
                },
            ],
            [
                "artifact-root",
                {
                    "k": "lit",
                    "v": f"artifacts/{phase_name}",
                    "type": _field_descriptor(
                        type_descriptor,
                        "artifact-root",
                        {"kind": "path", "name": "Path.artifact-root", "under": "artifacts", "must_exist_target": False},
                    ),
                },
            ],
        ],
    }
    if type_descriptor is not None:
        value["type"] = type_descriptor
    return value
