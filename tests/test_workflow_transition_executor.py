from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys

import pytest


def _import_transition_contract():
    return importlib.import_module("orchestrator.workflow.transition_contract")


def _import_transition_executor():
    return importlib.import_module("orchestrator.workflow.transition_executor")


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


def _history_entry_type() -> dict[str, object]:
    return _record(
        "HistoryEntry",
        [
            _field("event", _primitive("String")),
            _field("status", _primitive("String")),
            _field("reason", _optional(_primitive("String"))),
        ],
    )


def _projection_payload(result_type: dict[str, object]) -> dict[str, object]:
    return {
        "pure_expr_schema_version": 1,
        "result_type": result_type,
        "bindings": {
            "state": {"type": _state_type()},
            "request": {"type": _request_type()},
        },
        "expr": {
            "kind": "record",
            "type": result_type,
            "fields": [
                {"name": "status", "value": _field_access(_binding("request"), "status")},
                {"name": "reason", "value": _field_access(_binding("request"), "reason")},
            ],
        },
    }


def _declaration_payload(*, backing_kind: str) -> dict[str, object]:
    return {
        "transition_schema_version": 1,
        "resource": {
            "resource_kind": "drain_run_state",
            "state_type": _state_type(),
            "backing": {"kind": "state_layout"} if backing_kind == "native" else {"kind": "bridge", "path_input": "run_state_path"},
        },
        "transition": {
            "name": "drain/write_status",
            "request_type": _request_type(),
            "result_type": _result_type(),
            "preconditions": [
                {
                    "pure_expr_schema_version": 1,
                    "result_type": _primitive("Bool"),
                    "bindings": {
                        "state": {"type": _state_type()},
                        "request": {"type": _request_type()},
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
            ],
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
                    "value": {
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
                    },
                },
            ],
            "write_set": ["drain_status", "drain_status_reason", "history"],
            "idempotency_fields": ["status", "reason"],
            "result_projection": _projection_payload(_result_type()),
            "audit_projection": _projection_payload(
                _record(
                    "DrainStatusAudit",
                    [
                        _field("status", _primitive("String")),
                        _field("reason", _optional(_primitive("String"))),
                    ],
                )
            ),
            "conflict_policy": "fail_closed",
            "backend": {"kind": "runtime_native"},
        },
    }


def _bridge_state_payload() -> dict[str, object]:
    return {
        "schema": "lisp_frontend_autonomous_drain_run_state/v1",
        "completed_items": [],
        "completed_design_gaps": [],
        "blocked_items": {},
        "blocked_design_gaps": {},
        "drain_status": "CONTINUE",
        "history": [],
    }


def _native_state_payload() -> dict[str, object]:
    return {
        "drain_status": "CONTINUE",
        "drain_status_reason": None,
        "history": [],
    }


def _write_native_resource(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "transition_schema_version": 1,
                "resource_id": "drain-run-1",
                "resource_kind": "drain_run_state",
                "state_version": "native:0",
                "state": _native_state_payload(),
                "provenance": {"source": "test"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_bridge_resource(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_bridge_state_payload(), indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_audit_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _resource_runtime(tmp_path: Path, *, backing_kind: str, with_mirror: bool = False) -> tuple[dict[str, object], Path, Path]:
    audit_path = tmp_path / f"{backing_kind}-transition-audit.jsonl"
    if backing_kind == "native":
        state_path = tmp_path / "state" / "resource.json"
        _write_native_resource(state_path)
        resource = {
            "resource_id": "drain-run-1",
            "resource_kind": "drain_run_state",
            "state_path": state_path,
            "audit_path": audit_path,
        }
        if with_mirror:
            mirror_path = tmp_path / "state" / "resource.mirror.json"
            resource["secondary_state_paths"] = [mirror_path]
        return resource, state_path, audit_path
    bridge_path = tmp_path / "state" / "run-state.json"
    _write_bridge_resource(bridge_path)
    resource = {
        "resource_id": "drain-run-1",
        "resource_kind": "drain_run_state",
        "bridge_path": bridge_path,
        "audit_path": audit_path,
    }
    return resource, bridge_path, audit_path


def _validated_declaration(backing_kind: str):
    contract = _import_transition_contract()
    return contract.validate_transition_declaration(_declaration_payload(backing_kind=backing_kind))


def _write_certified_adapter_script(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "from pathlib import Path",
                "",
                "payload = json.loads(sys.argv[1])",
                "run_state_path = Path(payload['run_state_path'])",
                "state = json.loads(run_state_path.read_text(encoding='utf-8'))",
                "request = payload['request']",
                "state['drain_status'] = request['status']",
                "state['drain_status_reason'] = request['reason']",
                "run_state_path.write_text(json.dumps(state, indent=2) + '\\n', encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _bridge_backend_equivalence_payload() -> dict[str, object]:
    payload = _declaration_payload(backing_kind="bridge")
    payload["transition"]["updates"] = payload["transition"]["updates"][:2]
    payload["transition"]["write_set"] = ["drain_status", "drain_status_reason"]
    return payload


@pytest.mark.parametrize("backing_kind", ["native", "bridge"])
def test_execute_transition_rejects_expected_version_mismatch_without_bumping_version(
    tmp_path: Path,
    backing_kind: str,
) -> None:
    declaration = _validated_declaration(backing_kind)
    executor = _import_transition_executor()
    resource, state_path, audit_path = _resource_runtime(tmp_path, backing_kind=backing_kind)
    before = state_path.read_text(encoding="utf-8")

    with pytest.raises(executor.TransitionExecutionError) as excinfo:
        executor.execute_transition(
            declaration,
            resource,
            {"status": "BLOCKED", "reason": "waiting"},
            expected_version="wrong-version",
            backend="runtime_native",
            runtime_env={},
        )

    assert excinfo.value.code == "transition_version_mismatch"
    assert state_path.read_text(encoding="utf-8") == before
    assert _read_audit_rows(audit_path)[-1]["outcome_code"] == "rejected_version"
    assert _read_audit_rows(audit_path)[-1]["resource_kind"] == "drain_run_state"


def test_execute_transition_detects_bridge_digest_drift_from_audit(tmp_path: Path) -> None:
    declaration = _validated_declaration("bridge")
    executor = _import_transition_executor()
    resource, state_path, audit_path = _resource_runtime(tmp_path, backing_kind="bridge")
    current_digest = hashlib.sha256(state_path.read_bytes()).hexdigest()
    audit_path.write_text(
        json.dumps(
            {
                "transition_schema_version": 1,
                "transition_name": "drain/write_status",
                "resource_id": "drain-run-1",
                "outcome_code": "committed",
                "bridge_digest": f"sha256:{'0' * 64}",
                "observed_bridge_digest": f"sha256:{current_digest}",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(executor.TransitionExecutionError) as excinfo:
        executor.execute_transition(
            declaration,
            resource,
            {"status": "BLOCKED", "reason": "waiting"},
            expected_version=None,
            backend="runtime_native",
            runtime_env={},
        )

    assert excinfo.value.code == "transition_conflict_detected"
    assert _read_audit_rows(audit_path)[-1]["outcome_code"] == "rejected_conflict"
    assert _read_audit_rows(audit_path)[-1]["resource_kind"] == "drain_run_state"


def test_execute_transition_initializes_missing_native_state_on_first_write(tmp_path: Path) -> None:
    declaration = _validated_declaration("native")
    executor = _import_transition_executor()
    state_path = tmp_path / "state" / "resource.json"
    audit_path = tmp_path / "native-transition-audit.jsonl"
    resource = {
        "resource_id": "drain-run-1",
        "resource_kind": "drain_run_state",
        "state_path": state_path,
        "audit_path": audit_path,
    }

    result = executor.execute_transition(
        declaration,
        resource,
        {"status": "DONE", "reason": "complete"},
        expected_version=None,
        backend="runtime_native",
        runtime_env={},
    )

    assert result["version"].startswith("native:1:")
    assert result["replayed"] is False
    assert _read_json(state_path)["state"] == {
        "drain_status": "DONE",
        "drain_status_reason": "complete",
        "history": [
            {"event": "drain_status", "status": "DONE", "reason": "complete"}
        ],
    }
    assert _read_audit_rows(audit_path)[-1]["outcome_code"] == "committed"


@pytest.mark.parametrize("backing_kind", ["native", "bridge"])
def test_execute_transition_replays_idempotent_requests_without_reapplying(
    tmp_path: Path,
    backing_kind: str,
) -> None:
    declaration = _validated_declaration(backing_kind)
    executor = _import_transition_executor()
    resource, _state_path, audit_path = _resource_runtime(tmp_path, backing_kind=backing_kind)

    first = executor.execute_transition(
        declaration,
        resource,
        {"status": "BLOCKED", "reason": "waiting"},
        expected_version=None,
        backend="runtime_native",
        runtime_env={},
    )
    second = executor.execute_transition(
        declaration,
        resource,
        {"reason": "waiting", "status": "BLOCKED"},
        expected_version=first["version"],
        backend="runtime_native",
        runtime_env={},
    )

    assert second["replayed"] is True
    assert second["result"] == first["result"]
    assert _read_audit_rows(audit_path)[-1]["outcome_code"] == "replayed"
    assert _read_audit_rows(audit_path)[-1]["resource_kind"] == "drain_run_state"


@pytest.mark.parametrize("backing_kind", ["native", "bridge"])
def test_execute_transition_leaves_prior_state_intact_when_faulted_before_commit(
    tmp_path: Path,
    backing_kind: str,
) -> None:
    declaration = _validated_declaration(backing_kind)
    executor = _import_transition_executor()
    resource, state_path, _audit_path = _resource_runtime(tmp_path, backing_kind=backing_kind)
    before = state_path.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError, match="before_commit"):
        executor.execute_transition(
            declaration,
            resource,
            {"status": "BLOCKED", "reason": "waiting"},
            expected_version=None,
            backend="runtime_native",
            runtime_env={"fault_injection": "before_commit"},
        )

    assert state_path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("backing_kind", ["native", "bridge"])
def test_execute_transition_resume_replays_committed_state_after_crash_after_commit(
    tmp_path: Path,
    backing_kind: str,
) -> None:
    declaration = _validated_declaration(backing_kind)
    executor = _import_transition_executor()
    resource, _state_path, audit_path = _resource_runtime(tmp_path, backing_kind=backing_kind)

    with pytest.raises(RuntimeError, match="after_commit"):
        executor.execute_transition(
            declaration,
            resource,
            {"status": "BLOCKED", "reason": "waiting"},
            expected_version=None,
            backend="runtime_native",
            runtime_env={"fault_injection": "after_commit"},
        )

    resumed = executor.execute_transition(
        declaration,
        resource,
        {"status": "BLOCKED", "reason": "waiting"},
        expected_version=None,
        backend="runtime_native",
        runtime_env={},
    )

    assert resumed["replayed"] is True
    assert _read_audit_rows(audit_path)[-1]["outcome_code"] == "replayed"
    assert _read_audit_rows(audit_path)[-1]["resource_kind"] == "drain_run_state"


def test_execute_transition_audits_rejected_preconditions_with_explicit_outcome_codes(tmp_path: Path) -> None:
    contract = _import_transition_contract()
    executor = _import_transition_executor()
    payload = _declaration_payload(backing_kind="native")
    payload["transition"]["preconditions"] = [
        {
            "pure_expr_schema_version": 1,
            "result_type": _primitive("Bool"),
            "bindings": {
                "state": {"type": _state_type()},
                "request": {"type": _request_type()},
            },
            "expr": {
                "kind": "op",
                "operator": "=",
                "args": [
                    _field_access(_binding("request"), "status"),
                    _string_literal("ALLOWED"),
                ],
            },
        }
    ]
    declaration = contract.validate_transition_declaration(payload)
    resource, _state_path, audit_path = _resource_runtime(tmp_path, backing_kind="native")

    with pytest.raises(executor.TransitionExecutionError) as excinfo:
        executor.execute_transition(
            declaration,
            resource,
            {"status": "BLOCKED", "reason": "waiting"},
            expected_version=None,
            backend="runtime_native",
            runtime_env={},
        )

    assert excinfo.value.code == "transition_precondition_failed"
    assert _read_audit_rows(audit_path)[-1]["outcome_code"] == "rejected_precondition"
    assert _read_audit_rows(audit_path)[-1]["resource_kind"] == "drain_run_state"


def test_execute_transition_surfaces_audit_append_failure_after_commit(tmp_path: Path) -> None:
    declaration = _validated_declaration("native")
    executor = _import_transition_executor()
    resource, state_path, audit_path = _resource_runtime(tmp_path, backing_kind="native")

    with pytest.raises(executor.TransitionExecutionError) as excinfo:
        executor.execute_transition(
            declaration,
            resource,
            {"status": "BLOCKED", "reason": "waiting"},
            expected_version=None,
            backend="runtime_native",
            runtime_env={"fault_injection": "audit_append"},
        )

    assert excinfo.value.code == "transition_audit_append_failed"
    assert _read_json(state_path)["state"]["drain_status"] == "BLOCKED"
    assert _read_audit_rows(audit_path) == []


@pytest.mark.parametrize("backing_kind", ["native", "bridge"])
def test_execute_transition_replays_committed_result_after_audit_append_failure(
    tmp_path: Path,
    backing_kind: str,
) -> None:
    declaration = _validated_declaration(backing_kind)
    executor = _import_transition_executor()
    resource, state_path, audit_path = _resource_runtime(tmp_path, backing_kind=backing_kind)

    with pytest.raises(executor.TransitionExecutionError) as excinfo:
        executor.execute_transition(
            declaration,
            resource,
            {"status": "BLOCKED", "reason": "waiting"},
            expected_version=None,
            backend="runtime_native",
            runtime_env={"fault_injection": "audit_append"},
        )

    assert excinfo.value.code == "transition_audit_append_failed"

    if backing_kind == "native":
        committed_version = str(_read_json(state_path)["state_version"])
    else:
        committed_version = f"sha256:{hashlib.sha256(state_path.read_bytes()).hexdigest()}"

    replayed = executor.execute_transition(
        declaration,
        resource,
        {"status": "BLOCKED", "reason": "waiting"},
        expected_version=None,
        backend="runtime_native",
        runtime_env={},
    )

    assert replayed == {
        "result": {"status": "BLOCKED", "reason": "waiting"},
        "version": committed_version,
        "replayed": True,
    }
    if backing_kind == "native":
        assert _read_json(state_path)["state"]["history"] == [
            {"event": "drain_status", "status": "BLOCKED", "reason": "waiting"}
        ]
    else:
        assert _read_json(state_path)["history"] == [
            {"event": "drain_status", "status": "BLOCKED", "reason": "waiting"}
        ]
    assert [row["outcome_code"] for row in _read_audit_rows(audit_path)] == ["committed", "replayed"]
    assert _read_audit_rows(audit_path)[0]["version"] == committed_version


def test_execute_transition_records_partial_failure_for_multi_target_abort(tmp_path: Path) -> None:
    declaration = _validated_declaration("native")
    executor = _import_transition_executor()
    resource, _state_path, audit_path = _resource_runtime(tmp_path, backing_kind="native", with_mirror=True)

    with pytest.raises(RuntimeError, match="target_commit_1"):
        executor.execute_transition(
            declaration,
            resource,
            {"status": "BLOCKED", "reason": "waiting"},
            expected_version=None,
            backend="runtime_native",
            runtime_env={"fault_injection": "target_commit_1"},
        )

    assert _read_audit_rows(audit_path)[-1]["outcome_code"] == "partial_failure"
    assert _read_audit_rows(audit_path)[-1]["partial_failure"]["committed_target_count"] == 1
    assert _read_audit_rows(audit_path)[-1]["resource_kind"] == "drain_run_state"


def test_execute_transition_supports_certified_adapter_backend_with_bridge_equivalence(
    tmp_path: Path,
) -> None:
    contract = _import_transition_contract()
    executor = _import_transition_executor()

    runtime_native_payload = _bridge_backend_equivalence_payload()
    adapter_payload = _bridge_backend_equivalence_payload()
    adapter_script = tmp_path / "write_drain_status_adapter.py"
    _write_certified_adapter_script(adapter_script)
    adapter_payload["transition"]["backend"] = {
        "kind": "write_drain_status_adapter",
        "stable_command": [sys.executable, str(adapter_script)],
        "invocation_protocol": "json_object_positional_arg",
    }

    runtime_native_declaration = contract.validate_transition_declaration(runtime_native_payload)
    certified_adapter_declaration = contract.validate_transition_declaration(adapter_payload)
    native_resource, native_state_path, native_audit_path = _resource_runtime(
        tmp_path / "native",
        backing_kind="bridge",
    )
    adapter_resource, adapter_state_path, adapter_audit_path = _resource_runtime(
        tmp_path / "adapter",
        backing_kind="bridge",
    )
    request = {"status": "BLOCKED", "reason": "waiting"}

    native_result = executor.execute_transition(
        runtime_native_declaration,
        native_resource,
        request,
        expected_version=None,
        backend="runtime_native",
        runtime_env={},
    )
    adapter_result = executor.execute_transition(
        certified_adapter_declaration,
        adapter_resource,
        request,
        expected_version=None,
        backend="write_drain_status_adapter",
        runtime_env={},
    )

    assert adapter_result == native_result
    assert _read_json(adapter_state_path) == _read_json(native_state_path)
    assert _read_audit_rows(adapter_audit_path)[-1]["outcome_code"] == "committed"
    assert _read_audit_rows(adapter_audit_path)[-1]["resource_kind"] == "drain_run_state"
    assert _read_audit_rows(adapter_audit_path)[-1]["version"] == _read_audit_rows(native_audit_path)[-1]["version"]


def test_transition_committed_result_lookup_returns_committed_result_evidence(tmp_path: Path) -> None:
    declaration = _validated_declaration("native")
    executor = _import_transition_executor()
    resource, _state_path, audit_path = _resource_runtime(tmp_path, backing_kind="native")

    committed = executor.execute_transition(
        declaration,
        resource,
        {"status": "BLOCKED", "reason": "waiting"},
        expected_version=None,
        backend="runtime_native",
        runtime_env={},
    )

    lookup = executor.lookup_committed_transition_result(
        declaration,
        resource,
        {"status": "BLOCKED", "reason": "waiting"},
    )

    assert lookup is not None
    assert lookup["result"] == committed["result"]
    assert lookup["version"] == committed["version"]
    assert lookup["audit_path"] == audit_path
    assert lookup["audit_digest"].startswith("sha256:")
    assert lookup["audit_row_index"] == 0
    assert lookup["audit_row_digest"].startswith("sha256:")
    assert lookup["outcome_code"] == "committed"


def test_transition_committed_result_lookup_reports_pending_replay_when_unresolved(tmp_path: Path) -> None:
    declaration = _validated_declaration("native")
    executor = _import_transition_executor()
    resource, _state_path, audit_path = _resource_runtime(tmp_path, backing_kind="native")

    with pytest.raises(executor.TransitionExecutionError, match="transition audit append failed after commit"):
        executor.execute_transition(
            declaration,
            resource,
            {"status": "BLOCKED", "reason": "waiting"},
            expected_version=None,
            backend="runtime_native",
            runtime_env={"fault_injection": "audit_append"},
        )

    lookup = executor.lookup_committed_transition_result(
        declaration,
        resource,
        {"status": "BLOCKED", "reason": "waiting"},
    )

    assert lookup is not None
    assert lookup["pending_replay"] is True
    assert lookup["audit_path"] == audit_path
