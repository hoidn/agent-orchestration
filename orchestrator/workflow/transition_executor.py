"""File-backed transition execution for runtime-native resources."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

from .pure_expr import evaluate_pure_expr
from .transition_contract import (
    TRANSITION_SCHEMA_VERSION,
    TransitionUpdate,
    ValidatedTransitionDeclaration,
    canonical_transition_digest,
    canonical_transition_json,
    coerce_transition_value,
    derive_idempotency_key,
    serialize_transition_audit_record,
)

_MISSING_STATE_VALUE = object()


class TransitionExecutionError(RuntimeError):
    """Raised when runtime transition execution fails with a typed code."""

    def __init__(self, code: str, message: str, *, metadata: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = dict(metadata or {})


@dataclass(frozen=True)
class LoadedResourceState:
    state_value: dict[str, Any]
    version: str
    raw_document: dict[str, Any]
    state_path: Path
    secondary_state_paths: tuple[Path, ...]
    audit_path: Path
    bridge_backing: bool


def execute_transition(
    declaration: ValidatedTransitionDeclaration,
    resource: Mapping[str, Any],
    request_values: Mapping[str, Any],
    expected_version: str | None,
    *,
    backend: str,
    runtime_env: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_env = dict(runtime_env or {})
    request = coerce_transition_value(request_values, declaration.transition.request_type, context="request_values")
    resource_state = _load_resource_state(declaration, resource)
    audit_rows = _read_audit_rows(resource_state.audit_path)
    resource_id = _resource_id(resource)

    if expected_version is not None and expected_version != resource_state.version:
        _append_rejection_audit(
            resource_state.audit_path,
            declaration=declaration,
            resource_id=resource_id,
            request=request,
            outcome_code="rejected_version",
            metadata={"expected_version": expected_version, "observed_version": resource_state.version},
        )
        raise TransitionExecutionError("transition_version_mismatch", "transition expected_version did not match the loaded resource version")

    request_digest = canonical_transition_digest(request)
    idempotency_key = derive_idempotency_key(
        declaration,
        resource_id=resource_id,
        request_values=request,
    )
    pending_row = _read_pending_replay(resource_state.audit_path)
    replay_row = _find_committed_replay(
        audit_rows,
        transition_name=declaration.transition.name,
        idempotency_key=idempotency_key,
        request_digest=request_digest,
    )
    if replay_row is not None and pending_row is not None and _pending_row_matches_replay_row(pending_row, replay_row):
        _clear_pending_replay(resource_state.audit_path)
        pending_row = None
    if pending_row is not None:
        replay_row = _recover_pending_replay(
            audit_path=resource_state.audit_path,
            declaration=declaration,
            resource_id=resource_id,
            resource_state=resource_state,
            pending_row=pending_row,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
        )
        _append_audit_row(
            resource_state.audit_path,
            {
                "transition_schema_version": TRANSITION_SCHEMA_VERSION,
                "transition_name": declaration.transition.name,
                "resource_kind": declaration.resource.resource_kind,
                "resource_id": resource_id,
                "outcome_code": "replayed",
                "idempotency_key": idempotency_key,
                "request_digest": request_digest,
                "version": replay_row["version"],
            },
        )
        return {
            "result": replay_row["result"],
            "version": replay_row["version"],
            "replayed": True,
        }

    if resource_state.bridge_backing:
        last_committed_digest = _last_committed_bridge_digest(audit_rows)
        if last_committed_digest and last_committed_digest != resource_state.version:
            _append_rejection_audit(
                resource_state.audit_path,
                declaration=declaration,
                resource_id=resource_id,
                request=request,
                outcome_code="rejected_conflict",
                metadata={
                    "expected_bridge_digest": last_committed_digest,
                    "observed_bridge_digest": resource_state.version,
                },
            )
            raise TransitionExecutionError("transition_conflict_detected", "bridge-backed resource digest drifted outside the audit ledger")

    if replay_row is not None:
        _append_audit_row(
            resource_state.audit_path,
            {
                "transition_schema_version": TRANSITION_SCHEMA_VERSION,
                "transition_name": declaration.transition.name,
                "resource_kind": declaration.resource.resource_kind,
                "resource_id": resource_id,
                "outcome_code": "replayed",
                "idempotency_key": idempotency_key,
                "request_digest": request_digest,
                "version": replay_row["version"],
            },
        )
        return {
            "result": replay_row["result"],
            "version": replay_row["version"],
            "replayed": True,
        }

    resolved_bindings = {"state": resource_state.state_value, "request": request}
    for payload in declaration.transition.preconditions:
        if not evaluate_pure_expr(payload, resolved_bindings=resolved_bindings):
            _append_rejection_audit(
                resource_state.audit_path,
                declaration=declaration,
                resource_id=resource_id,
                request=request,
                outcome_code="rejected_precondition",
                metadata={},
            )
            raise TransitionExecutionError("transition_precondition_failed", "transition precondition evaluated to false")

    if runtime_env.get("fault_injection") == "before_commit":
        raise RuntimeError("before_commit")

    new_state = _apply_updates(
        declaration.transition.updates,
        resource_state.state_value,
        resolved_bindings=resolved_bindings,
    )
    result = coerce_transition_value(
        evaluate_pure_expr(declaration.transition.result_projection, resolved_bindings={"state": new_state, "request": request}),
        declaration.transition.result_type,
        context="transition.result",
    )
    audit_projection = evaluate_pure_expr(
        declaration.transition.audit_projection,
        resolved_bindings={"state": new_state, "request": request},
    )
    new_version = _apply_backend(
        declaration=declaration,
        resource=resource,
        resource_state=resource_state,
        request=request,
        new_state=new_state,
        backend=backend,
        runtime_env=runtime_env,
    )
    committed_row = {
        "transition_schema_version": TRANSITION_SCHEMA_VERSION,
        "transition_name": declaration.transition.name,
        "resource_kind": declaration.resource.resource_kind,
        "resource_id": resource_id,
        "outcome_code": "committed",
        "idempotency_key": idempotency_key,
        "request_digest": request_digest,
        "version": new_version,
        "result": result,
        "projection": audit_projection,
    }
    if resource_state.bridge_backing:
        committed_row["bridge_digest"] = new_version

    _write_pending_replay(resource_state.audit_path, committed_row)
    if runtime_env.get("fault_injection") == "audit_append":
        raise TransitionExecutionError("transition_audit_append_failed", "transition audit append failed after commit")

    try:
        _append_audit_row(resource_state.audit_path, committed_row)
    except OSError as exc:
        raise TransitionExecutionError(
            "transition_audit_append_failed",
            "transition audit append failed after commit",
            metadata={"audit_path": str(resource_state.audit_path), "error": str(exc)},
        ) from exc
    _clear_pending_replay(resource_state.audit_path)

    if runtime_env.get("fault_injection") == "after_commit":
        raise RuntimeError("after_commit")

    return {
        "result": result,
        "version": new_version,
        "replayed": False,
    }


def _apply_updates(
    updates: tuple[TransitionUpdate, ...],
    state_value: Mapping[str, Any],
    *,
    resolved_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(state_value)
    for update in updates:
        if update.op == "clear_field":
            result[update.target] = None
            continue
        if update.value is None:
            raise TransitionExecutionError("transition_backend_result_invalid", f"update `{update.target}` is missing its value payload")
        value = evaluate_pure_expr(update.value, resolved_bindings=resolved_bindings)
        if update.op == "set_field":
            result[update.target] = value
        elif update.op == "append_item":
            items = list(result.get(update.target, []))
            items.append(value)
            result[update.target] = items
        else:
            raise TransitionExecutionError("transition_backend_result_invalid", f"unsupported update op `{update.op}`")
    return result


def _apply_backend(
    *,
    declaration: ValidatedTransitionDeclaration,
    resource: Mapping[str, Any],
    resource_state: LoadedResourceState,
    request: Mapping[str, Any],
    new_state: Mapping[str, Any],
    backend: str,
    runtime_env: Mapping[str, Any],
) -> str:
    if backend == "runtime_native":
        return _apply_runtime_native_backend(
            declaration=declaration,
            resource=resource,
            resource_state=resource_state,
            request=request,
            new_state=new_state,
            runtime_env=runtime_env,
        )
    return _apply_certified_adapter_backend(
        declaration=declaration,
        resource=resource,
        resource_state=resource_state,
        request=request,
        new_state=new_state,
        backend=backend,
    )


def _apply_runtime_native_backend(
    *,
    declaration: ValidatedTransitionDeclaration,
    resource: Mapping[str, Any],
    resource_state: LoadedResourceState,
    request: Mapping[str, Any],
    new_state: Mapping[str, Any],
    runtime_env: Mapping[str, Any],
) -> str:
    new_version = _next_version(resource_state, new_state)
    state_targets = [resource_state.state_path, *resource_state.secondary_state_paths]

    if resource_state.bridge_backing:
        new_document = dict(resource_state.raw_document)
        new_document.update(new_state)
        _commit_targets(
            state_targets,
            json.dumps(new_document, indent=2, ensure_ascii=False) + "\n",
            runtime_env=runtime_env,
            audit_path=resource_state.audit_path,
            declaration=declaration,
            resource_id=_resource_id(resource),
            request=request,
        )
        return _bridge_digest(resource_state.state_path)

    new_document = {
        "transition_schema_version": TRANSITION_SCHEMA_VERSION,
        "resource_id": _resource_id(resource),
        "resource_kind": declaration.resource.resource_kind,
        "state_version": new_version,
        "state": new_state,
        "provenance": resource_state.raw_document.get("provenance", {}),
    }
    _commit_targets(
        state_targets,
        json.dumps(new_document, indent=2, ensure_ascii=False) + "\n",
        runtime_env=runtime_env,
        audit_path=resource_state.audit_path,
        declaration=declaration,
        resource_id=_resource_id(resource),
        request=request,
    )
    return new_version


def _apply_certified_adapter_backend(
    *,
    declaration: ValidatedTransitionDeclaration,
    resource: Mapping[str, Any],
    resource_state: LoadedResourceState,
    request: Mapping[str, Any],
    new_state: Mapping[str, Any],
    backend: str,
) -> str:
    backend_payload = declaration.transition.backend
    stable_command = backend_payload.get("stable_command")
    invocation_protocol = backend_payload.get("invocation_protocol")
    if not isinstance(stable_command, list) or not stable_command or not all(
        isinstance(token, str) and token for token in stable_command
    ):
        raise TransitionExecutionError(
            "transition_backend_result_invalid",
            f"backend `{backend}` is missing a valid stable_command",
        )
    if invocation_protocol != "json_object_positional_arg":
        raise TransitionExecutionError(
            "transition_backend_result_invalid",
            f"backend `{backend}` uses unsupported invocation_protocol `{invocation_protocol}`",
        )

    completed = subprocess.run(
        [*stable_command, canonical_transition_json(_adapter_request_payload(declaration, resource, request))],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        _append_failed_audit(
            resource_state.audit_path,
            declaration=declaration,
            resource_id=_resource_id(resource),
            request=request,
            metadata={
                "backend": backend,
                "returncode": completed.returncode,
            },
        )
        raise TransitionExecutionError(
            "transition_backend_result_invalid",
            f"backend `{backend}` exited {completed.returncode}",
            metadata={
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )

    observed_state = _load_resource_state(declaration, resource)
    try:
        _validate_adapter_state_effects(
            declaration=declaration,
            before_state=resource_state.state_value,
            expected_state=new_state,
            observed_state=observed_state.state_value,
        )
    except TransitionExecutionError as exc:
        _append_failed_audit(
            resource_state.audit_path,
            declaration=declaration,
            resource_id=_resource_id(resource),
            request=request,
            metadata={"backend": backend},
        )
        raise exc
    return observed_state.version


def _adapter_request_payload(
    declaration: ValidatedTransitionDeclaration,
    resource: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "transition_name": declaration.transition.name,
        "resource_id": _resource_id(resource),
        "resource_kind": declaration.resource.resource_kind,
        "request": dict(request),
        **dict(request),
    }
    if declaration.resource.backing.kind == "bridge":
        path_input = declaration.resource.backing.path_input or "bridge_path"
        payload[path_input] = str(resource["bridge_path"])
    else:
        payload["state_path"] = str(resource["state_path"])
    return payload


def _validate_adapter_state_effects(
    *,
    declaration: ValidatedTransitionDeclaration,
    before_state: Mapping[str, Any],
    expected_state: Mapping[str, Any],
    observed_state: Mapping[str, Any],
) -> None:
    declared_fields = tuple(
        str(field["name"])
        for field in declaration.resource.state_type.get("fields", ())
        if isinstance(field, Mapping) and isinstance(field.get("name"), str)
    )
    write_set = set(declaration.transition.write_set)
    for field_name in declared_fields:
        before_value = before_state.get(field_name, _MISSING_STATE_VALUE)
        observed_value = observed_state.get(field_name, _MISSING_STATE_VALUE)
        if field_name in write_set:
            expected_value = expected_state.get(field_name, _MISSING_STATE_VALUE)
            if observed_value != expected_value:
                raise TransitionExecutionError(
                    "transition_backend_result_invalid",
                    f"backend write for `{field_name}` did not match the declared transition result",
                )
            continue
        if observed_value != before_value:
            raise TransitionExecutionError(
                "transition_backend_result_invalid",
                f"backend mutated undeclared field `{field_name}`",
            )


def _load_resource_state(
    declaration: ValidatedTransitionDeclaration,
    resource: Mapping[str, Any],
) -> LoadedResourceState:
    if resource.get("resource_kind") != declaration.resource.resource_kind:
        raise TransitionExecutionError("transition_backend_result_invalid", "resource kind does not match the validated declaration")
    audit_path = Path(resource["audit_path"])
    if declaration.resource.backing.kind == "bridge":
        state_path = Path(resource["bridge_path"])
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        state_value = dict(raw)
        version = _bridge_digest(state_path)
        return LoadedResourceState(
            state_value=state_value,
            version=version,
            raw_document=dict(raw),
            state_path=state_path,
            secondary_state_paths=(),
            audit_path=audit_path,
            bridge_backing=True,
        )
    state_path = Path(resource["state_path"])
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    state_value = dict(raw["state"])
    secondary_state_paths = tuple(Path(path) for path in resource.get("secondary_state_paths", []))
    return LoadedResourceState(
        state_value=state_value,
        version=str(raw["state_version"]),
        raw_document=dict(raw),
        state_path=state_path,
        secondary_state_paths=secondary_state_paths,
        audit_path=audit_path,
        bridge_backing=False,
    )


def _next_version(resource_state: LoadedResourceState, new_state: Mapping[str, Any]) -> str:
    digest = canonical_transition_digest(new_state)
    if resource_state.bridge_backing:
        return digest
    current = resource_state.version
    counter = 0
    if current.startswith("native:"):
        prefix = current.removeprefix("native:")
        counter_token = prefix.split(":", 1)[0]
        if counter_token.isdigit():
            counter = int(counter_token)
    return f"native:{counter + 1}:{digest.removeprefix('sha256:')[:16]}"


def _commit_targets(
    targets: list[Path],
    text: str,
    *,
    runtime_env: Mapping[str, Any],
    audit_path: Path,
    declaration: ValidatedTransitionDeclaration,
    resource_id: str,
    request: Mapping[str, Any],
) -> None:
    committed_count = 0
    for index, target in enumerate(targets):
        if index > 0 and runtime_env.get("fault_injection") == f"target_commit_{index}":
            _append_audit_row(
                audit_path,
                {
                    "transition_schema_version": TRANSITION_SCHEMA_VERSION,
                    "transition_name": declaration.transition.name,
                    "resource_kind": declaration.resource.resource_kind,
                    "resource_id": resource_id,
                    "outcome_code": "partial_failure",
                    "request_digest": canonical_transition_digest(request),
                    "partial_failure": {"committed_target_count": committed_count},
                },
            )
            raise RuntimeError(f"target_commit_{index}")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(target)
        committed_count += 1


def _append_rejection_audit(
    audit_path: Path,
    *,
    declaration: ValidatedTransitionDeclaration,
    resource_id: str,
    request: Mapping[str, Any],
    outcome_code: str,
    metadata: Mapping[str, Any],
) -> None:
    row = {
        "transition_schema_version": TRANSITION_SCHEMA_VERSION,
        "transition_name": declaration.transition.name,
        "resource_kind": declaration.resource.resource_kind,
        "resource_id": resource_id,
        "outcome_code": outcome_code,
        "request_digest": canonical_transition_digest(request),
    }
    row.update(dict(metadata))
    _append_audit_row(audit_path, row)


def _append_failed_audit(
    audit_path: Path,
    *,
    declaration: ValidatedTransitionDeclaration,
    resource_id: str,
    request: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> None:
    row = {
        "transition_schema_version": TRANSITION_SCHEMA_VERSION,
        "transition_name": declaration.transition.name,
        "resource_kind": declaration.resource.resource_kind,
        "resource_id": resource_id,
        "outcome_code": "failed",
        "request_digest": canonical_transition_digest(request),
    }
    row.update(dict(metadata))
    _append_audit_row(audit_path, row)


def _append_audit_row(audit_path: Path, row: Mapping[str, Any]) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(serialize_transition_audit_record(row))
        handle.write("\n")


def _read_audit_rows(audit_path: Path) -> list[dict[str, Any]]:
    if not audit_path.exists():
        return []
    return [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _pending_replay_path(audit_path: Path) -> Path:
    return audit_path.with_name(f"{audit_path.name}.pending.json")


def _write_pending_replay(audit_path: Path, row: Mapping[str, Any]) -> None:
    pending_path = _pending_replay_path(audit_path)
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = pending_path.with_suffix(f"{pending_path.suffix}.tmp")
    tmp_path.write_text(serialize_transition_audit_record(row) + "\n", encoding="utf-8")
    tmp_path.replace(pending_path)


def _read_pending_replay(audit_path: Path) -> dict[str, Any] | None:
    pending_path = _pending_replay_path(audit_path)
    if not pending_path.exists():
        return None
    return json.loads(pending_path.read_text(encoding="utf-8"))


def _clear_pending_replay(audit_path: Path) -> None:
    _pending_replay_path(audit_path).unlink(missing_ok=True)


def _pending_row_matches_replay_row(pending_row: Mapping[str, Any], replay_row: Mapping[str, Any]) -> bool:
    return (
        pending_row.get("transition_name") == replay_row.get("transition_name")
        and pending_row.get("idempotency_key") == replay_row.get("idempotency_key")
        and pending_row.get("request_digest") == replay_row.get("request_digest")
        and pending_row.get("version") == replay_row.get("version")
    )


def _recover_pending_replay(
    *,
    audit_path: Path,
    declaration: ValidatedTransitionDeclaration,
    resource_id: str,
    resource_state: LoadedResourceState,
    pending_row: Mapping[str, Any],
    idempotency_key: str,
    request_digest: str,
) -> dict[str, Any]:
    if pending_row.get("version") != resource_state.version:
        raise TransitionExecutionError(
            "transition_audit_append_failed",
            "transition audit recovery is pending for a different committed resource version",
            metadata={"pending_version": pending_row.get("version"), "observed_version": resource_state.version},
        )
    if (
        pending_row.get("transition_name") != declaration.transition.name
        or pending_row.get("resource_kind") != declaration.resource.resource_kind
        or pending_row.get("resource_id") != resource_id
        or pending_row.get("idempotency_key") != idempotency_key
        or pending_row.get("request_digest") != request_digest
    ):
        raise TransitionExecutionError(
            "transition_audit_append_failed",
            "transition audit recovery is pending for a different committed request",
            metadata={
                "pending_transition_name": pending_row.get("transition_name"),
                "pending_resource_id": pending_row.get("resource_id"),
                "pending_request_digest": pending_row.get("request_digest"),
            },
        )
    try:
        _append_audit_row(audit_path, pending_row)
    except OSError as exc:
        raise TransitionExecutionError(
            "transition_audit_append_failed",
            "transition audit append failed after commit",
            metadata={"audit_path": str(audit_path), "error": str(exc)},
        ) from exc
    _clear_pending_replay(audit_path)
    return dict(pending_row)


def _find_committed_replay(
    rows: list[dict[str, Any]],
    *,
    transition_name: str,
    idempotency_key: str,
    request_digest: str,
) -> dict[str, Any] | None:
    for row in reversed(rows):
        if (
            row.get("transition_name") == transition_name
            and row.get("outcome_code") == "committed"
            and row.get("idempotency_key") == idempotency_key
            and row.get("request_digest") == request_digest
        ):
            return row
    return None


def _last_committed_bridge_digest(rows: list[dict[str, Any]]) -> str | None:
    for row in reversed(rows):
        if row.get("outcome_code") == "committed" and isinstance(row.get("bridge_digest"), str):
            return row["bridge_digest"]
    return None


def _bridge_digest(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _resource_id(resource: Mapping[str, Any]) -> str:
    value = resource.get("resource_id")
    if not isinstance(value, str) or not value:
        raise TransitionExecutionError("transition_backend_result_invalid", "resource_id must be a non-empty string")
    return value
