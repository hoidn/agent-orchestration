from __future__ import annotations

import importlib
import json

import pytest


def _import_transition_contract():
    return importlib.import_module("orchestrator.workflow.transition_contract")


def _primitive(name: str) -> dict[str, object]:
    return {"kind": "primitive", "name": name}


def _optional(item: dict[str, object]) -> dict[str, object]:
    return {"kind": "optional", "item": item}


def _list(item: dict[str, object]) -> dict[str, object]:
    return {"kind": "list", "item": item}


def _field(name: str, field_type: dict[str, object]) -> dict[str, object]:
    return {"name": name, "type": field_type}


def _record(name: str, fields: list[dict[str, object]]) -> dict[str, object]:
    return {"kind": "record", "name": name, "fields": fields}


def _binding(name: str) -> dict[str, object]:
    return {"kind": "binding", "name": name}


def _field_access(base: dict[str, object], field: str) -> dict[str, object]:
    return {"kind": "field_access", "base": base, "field": field}


def _string_literal(value: str) -> dict[str, object]:
    return {"kind": "literal", "type": _primitive("String"), "value": value}


def _bool_type() -> dict[str, object]:
    return _primitive("Bool")


def _history_entry_type() -> dict[str, object]:
    return _record(
        "HistoryEntry",
        [
            _field("event", _primitive("String")),
            _field("status", _primitive("String")),
            _field("reason", _optional(_primitive("String"))),
        ],
    )


def _state_type() -> dict[str, object]:
    return _record(
        "DrainRunState",
        [
            _field("drain_status", _primitive("String")),
            _field("drain_status_reason", _optional(_primitive("String"))),
            _field("history", _list(_history_entry_type())),
        ],
    )


def _request_type() -> dict[str, object]:
    return _record(
        "DrainStatusRequest",
        [
            _field("status", _primitive("String")),
            _field("reason", _optional(_primitive("String"))),
        ],
    )


def _result_type() -> dict[str, object]:
    return _record(
        "DrainStatusResult",
        [
            _field("status", _primitive("String")),
            _field("reason", _optional(_primitive("String"))),
        ],
    )


def _audit_type() -> dict[str, object]:
    return _record(
        "DrainStatusAudit",
        [
            _field("status", _primitive("String")),
            _field("reason", _optional(_primitive("String"))),
        ],
    )


def _precondition_payload(*, result_type: dict[str, object] | None = None) -> dict[str, object]:
    request_type = _request_type()
    return {
        "pure_expr_schema_version": 1,
        "result_type": result_type or _bool_type(),
        "bindings": {
            "state": {"type": _state_type()},
            "request": {"type": request_type},
        },
        "expr": {
            "kind": "op",
            "operator": "!=",
            "args": [
                _field_access(_binding("request"), "status"),
                _string_literal(""),
            ],
        },
    }


def _result_projection_payload(*, result_type: dict[str, object] | None = None) -> dict[str, object]:
    projected_type = result_type or _result_type()
    return {
        "pure_expr_schema_version": 1,
        "result_type": projected_type,
        "bindings": {
            "state": {"type": _state_type()},
            "request": {"type": _request_type()},
        },
        "expr": {
            "kind": "record",
            "type": projected_type,
            "fields": [
                {"name": "status", "value": _field_access(_binding("request"), "status")},
                {"name": "reason", "value": _field_access(_binding("request"), "reason")},
            ],
        },
    }


def _history_append_payload() -> dict[str, object]:
    return {
        "pure_expr_schema_version": 1,
        "result_type": _history_entry_type(),
        "bindings": {
            "state": {"type": _state_type()},
            "request": {"type": _request_type()},
        },
        "expr": {
            "kind": "record",
            "type": _history_entry_type(),
            "fields": [
                {"name": "event", "value": _string_literal("drain_status")},
                {"name": "status", "value": _field_access(_binding("request"), "status")},
                {"name": "reason", "value": _field_access(_binding("request"), "reason")},
            ],
        },
    }


def _declaration_payload(*, backing_kind: str) -> dict[str, object]:
    resource_backing: dict[str, object]
    if backing_kind == "native":
        resource_backing = {"kind": "state_layout"}
    elif backing_kind == "bridge":
        resource_backing = {"kind": "bridge", "path_input": "run_state_path"}
    else:
        raise AssertionError(f"unexpected backing kind: {backing_kind}")

    return {
        "transition_schema_version": 1,
        "resource": {
            "resource_kind": "drain_run_state",
            "state_type": _state_type(),
            "backing": resource_backing,
        },
        "transition": {
            "name": "drain/write_status",
            "request_type": _request_type(),
            "result_type": _result_type(),
            "preconditions": [_precondition_payload()],
            "updates": [
                {
                    "op": "set_field",
                    "target": "drain_status",
                    "value": {
                        "pure_expr_schema_version": 1,
                        "result_type": _primitive("String"),
                        "bindings": {
                            "state": {"type": _state_type()},
                            "request": {"type": _request_type()},
                        },
                        "expr": _field_access(_binding("request"), "status"),
                    },
                },
                {
                    "op": "set_field",
                    "target": "drain_status_reason",
                    "value": {
                        "pure_expr_schema_version": 1,
                        "result_type": _optional(_primitive("String")),
                        "bindings": {
                            "state": {"type": _state_type()},
                            "request": {"type": _request_type()},
                        },
                        "expr": _field_access(_binding("request"), "reason"),
                    },
                },
                {
                    "op": "append_item",
                    "target": "history",
                    "value": _history_append_payload(),
                },
            ],
            "write_set": ["drain_status", "drain_status_reason", "history"],
            "idempotency_fields": ["status", "reason"],
            "result_projection": _result_projection_payload(),
            "audit_projection": _result_projection_payload(result_type=_audit_type()),
            "conflict_policy": "fail_closed",
            "backend": {"kind": "runtime_native"},
        },
    }


@pytest.mark.parametrize("backing_kind", ["native", "bridge"])
def test_validate_transition_declaration_accepts_native_and_bridge_backings(backing_kind: str) -> None:
    module = _import_transition_contract()

    declaration = module.validate_transition_declaration(_declaration_payload(backing_kind=backing_kind))

    assert declaration.resource.resource_kind == "drain_run_state"
    assert declaration.resource.backing.kind == backing_kind
    assert declaration.transition.name == "drain/write_status"


def test_validate_transition_declaration_requires_boolean_preconditions() -> None:
    module = _import_transition_contract()
    payload = _declaration_payload(backing_kind="native")
    payload["transition"]["preconditions"] = [_precondition_payload(result_type=_primitive("String"))]

    with pytest.raises(module.TransitionContractError) as excinfo:
        module.validate_transition_declaration(payload)

    assert excinfo.value.code == "transition_declaration_invalid"


def test_validate_transition_declaration_requires_declared_write_set_targets() -> None:
    module = _import_transition_contract()
    payload = _declaration_payload(backing_kind="native")
    payload["transition"]["write_set"] = ["drain_status", "history"]

    with pytest.raises(module.TransitionContractError) as excinfo:
        module.validate_transition_declaration(payload)

    assert excinfo.value.code == "transition_write_set_undeclared"


def test_validate_transition_declaration_requires_result_projection_type_match() -> None:
    module = _import_transition_contract()
    payload = _declaration_payload(backing_kind="native")
    payload["transition"]["result_projection"] = _result_projection_payload(result_type=_primitive("String"))

    with pytest.raises(module.TransitionContractError) as excinfo:
        module.validate_transition_declaration(payload)

    assert excinfo.value.code == "transition_result_projection_type_mismatch"


def test_derive_idempotency_key_is_deterministic() -> None:
    module = _import_transition_contract()
    declaration = module.validate_transition_declaration(_declaration_payload(backing_kind="native"))

    first = module.derive_idempotency_key(
        declaration,
        resource_id="drain-run-1",
        request_values={"status": "BLOCKED", "reason": "waiting"},
    )
    second = module.derive_idempotency_key(
        declaration,
        resource_id="drain-run-1",
        request_values={"reason": "waiting", "status": "BLOCKED"},
    )

    assert first == second
    assert first.startswith("sha256:")


def test_serialize_transition_audit_record_uses_canonical_shape() -> None:
    module = _import_transition_contract()
    record = {
        "transition_schema_version": 1,
        "transition_name": "drain/write_status",
        "resource_id": "drain-run-1",
        "outcome_code": "committed",
        "request_digest": "sha256:request",
        "idempotency_key": "sha256:key",
        "projection": {
            "status": "BLOCKED",
            "reason": "waiting",
        },
    }

    rendered = module.serialize_transition_audit_record(record)
    reparsed = json.loads(rendered)

    assert reparsed["transition_schema_version"] == 1
    assert reparsed["transition_name"] == "drain/write_status"
    assert reparsed["projection"] == {"status": "BLOCKED", "reason": "waiting"}
    assert rendered == module.serialize_transition_audit_record(dict(reversed(record.items())))


@pytest.mark.parametrize("backing_kind", ["native", "bridge"])
def test_version_tokens_are_opaque_strings_for_both_backings(backing_kind: str) -> None:
    module = _import_transition_contract()

    declaration = module.validate_transition_declaration(_declaration_payload(backing_kind=backing_kind))

    assert declaration.resource.version_token_type == "String"
