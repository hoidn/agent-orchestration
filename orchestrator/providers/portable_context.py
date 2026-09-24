"""Closed portable provider-context.v1 value validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from orchestrator.workflow.type_descriptor import validate_transport_value


def _primitive(name: str) -> dict[str, str]:
    return {"kind": "primitive", "name": name}


def _fields(**fields: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"name": name, "type": descriptor} for name, descriptor in fields.items()]


_STRING = _primitive("String")
_INT = _primitive("Int")
_ORIGIN = {
    "kind": "union",
    "name": "ContextOrigin",
    "variants": [
        {"name": "CAPTURED", "fields": _fields(provider=_STRING, attempt=_STRING)},
        {"name": "AUTHORED", "fields": _fields(label=_STRING)},
    ],
}
_FILE_CHANGE = {
    "kind": "record",
    "name": "ContextFileChange",
    "fields": _fields(path=_STRING, kind=_STRING),
}
_EVENT = {
    "kind": "union",
    "name": "ContextEvent",
    "variants": [
        {"name": "TASK", "fields": _fields(origin=_ORIGIN, sequence=_INT, text=_STRING)},
        {
            "name": "ASSISTANT",
            "fields": _fields(origin=_ORIGIN, sequence=_INT, item_id=_STRING, text=_STRING),
        },
        {
            "name": "COMMAND",
            "fields": _fields(
                origin=_ORIGIN,
                call_sequence=_INT,
                result_sequence=_INT,
                item_id=_STRING,
                command=_STRING,
                output=_STRING,
                exit_code=_INT,
            ),
        },
        {
            "name": "FILE_CHANGE",
            "fields": _fields(
                origin=_ORIGIN,
                sequence=_INT,
                item_id=_STRING,
                status=_STRING,
                changes={"kind": "list", "item": _FILE_CHANGE},
            ),
        },
    ],
}
PORTABLE_CONTEXT_V1_DESCRIPTOR: dict[str, Any] = {
    "kind": "record",
    "name": "Context",
    "fields": _fields(
        schema=_STRING,
        events={"kind": "list", "item": _EVENT},
        coverage={
            "kind": "list",
            "item": {
                "kind": "record",
                "name": "ContextCoverage",
                "fields": _fields(
                    origin=_ORIGIN,
                    scope=_STRING,
                    retained_kinds={"kind": "list", "item": _STRING},
                    omitted_kinds={"kind": "list", "item": _STRING},
                    conversions={"kind": "list", "item": _STRING},
                ),
            },
        },
        lineage={
            "kind": "list",
            "item": {
                "kind": "record",
                "name": "ContextTransform",
                "fields": _fields(
                    sources={"kind": "list", "item": _ORIGIN},
                    operation=_STRING,
                    loss={"kind": "list", "item": _STRING},
                ),
            },
        },
    ),
}


def _origin_key(origin: Mapping[str, Any]) -> str:
    return json.dumps(origin, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _nonempty(value: Any, *, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"portable context {field} must be non-empty")


def _validate_origin(origin: Mapping[str, Any], *, field: str) -> str:
    for key, value in origin.items():
        if key != "variant":
            _nonempty(value, field=f"{field}.{key}")
    return _origin_key(origin)


def _validate_kind_list(kinds: list[str], *, field: str) -> set[str]:
    if any(not kind for kind in kinds) or len(set(kinds)) != len(kinds):
        raise ValueError(f"portable context {field} must contain unique non-empty kinds")
    return set(kinds)


def validate_portable_context_v1(value: Any) -> dict[str, Any]:
    """Validate the fixed portable-context.v1 schema and event relationships."""

    context = validate_transport_value(
        value,
        PORTABLE_CONTEXT_V1_DESCRIPTOR,
        allow_nested_structures=True,
    )
    if context["schema"] != "portable-context.v1":
        raise ValueError("portable context schema must be `portable-context.v1`")

    positions: set[tuple[str, int]] = set()
    item_ids: set[tuple[str, str]] = set()
    event_origins: set[str] = set()
    event_kinds_by_origin: dict[str, set[str]] = {}
    for event in context["events"]:
        origin = event["origin"]
        origin_key = _validate_origin(origin, field="event.origin")
        event_origins.add(origin_key)
        variant = event["variant"]
        event_kinds_by_origin.setdefault(origin_key, set()).add(variant)
        if variant in {"TASK", "ASSISTANT", "FILE_CHANGE"}:
            sequence = event["sequence"]
            if sequence < 0 or (origin_key, sequence) in positions:
                raise ValueError("portable context event sequences must be unique and non-negative")
            positions.add((origin_key, sequence))
        elif variant == "COMMAND":
            call_sequence = event["call_sequence"]
            result_sequence = event["result_sequence"]
            if call_sequence < 0 or result_sequence <= call_sequence:
                raise ValueError("portable context command completion must follow its call")
            for sequence in (call_sequence, result_sequence):
                if (origin_key, sequence) in positions:
                    raise ValueError("portable context event sequences must be unique")
                positions.add((origin_key, sequence))
        else:
            raise ValueError("portable context event kind is unsupported")
        if variant == "FILE_CHANGE":
            if event["status"] not in {"completed", "failed"}:
                raise ValueError("portable context file change status is unsupported")
            if any(change["kind"] not in {"add", "delete", "update"} for change in event["changes"]):
                raise ValueError("portable context file change kind is unsupported")
        if variant in {"ASSISTANT", "COMMAND", "FILE_CHANGE"}:
            item_key = (origin_key, event["item_id"])
            if not event["item_id"] or item_key in item_ids:
                raise ValueError("portable context item identities must be unique per origin")
            item_ids.add(item_key)

    coverage_origins: set[str] = set()
    for coverage in context["coverage"]:
        _nonempty(coverage["scope"], field="coverage.scope")
        origin_key = _validate_origin(coverage["origin"], field="coverage.origin")
        if origin_key in coverage_origins:
            raise ValueError("portable context coverage origins must be unique")
        coverage_origins.add(origin_key)
        retained_kinds = _validate_kind_list(
            coverage["retained_kinds"],
            field="coverage retained kinds",
        )
        omitted_kinds = _validate_kind_list(
            coverage["omitted_kinds"],
            field="coverage omitted kinds",
        )
        _validate_kind_list(coverage["conversions"], field="coverage conversions")
        if retained_kinds & omitted_kinds:
            raise ValueError("portable context coverage cannot retain and omit one kind")
        if not event_kinds_by_origin.get(origin_key, set()).issubset(
            retained_kinds
        ):
            raise ValueError("portable context coverage omits retained event kinds")
    if not event_origins.issubset(coverage_origins):
        raise ValueError("portable context coverage must account for every event origin")

    for transform in context["lineage"]:
        source_origins = {
            _validate_origin(source, field="lineage.source")
            for source in transform["sources"]
        }
        if len(source_origins) != len(transform["sources"]):
            raise ValueError("portable context lineage sources must be unique")
        _nonempty(transform["operation"], field="lineage.operation")
        _validate_kind_list(transform["loss"], field="lineage loss")
    return context


__all__ = ["PORTABLE_CONTEXT_V1_DESCRIPTOR", "validate_portable_context_v1"]
