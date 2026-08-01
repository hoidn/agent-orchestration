"""Private mode-1 child command for executing one compiled bundle capsule."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_context,
    workflow_public_input_contracts,
)
from orchestrator.workflow.signatures import bind_workflow_inputs

from .bundle_transport import (
    BundleCapsuleValidationError,
    decode_bundle_capsule,
    read_bundle_capsule_directory,
)
from .capsule_stage import stage_bundle_capsule
from .contracts import (
    canonical_json_bytes,
    compute_compiler_runtime_identity,
)


RUN_REF_CHILD_REQUEST_SCHEMA = "run_ref_child_request.v1"
RUN_REF_CHILD_RESULT_SCHEMA = "run_ref_child_result.v1"
RUN_REF_CHILD_DIAGNOSTIC_SCHEMA = "run_ref_child_diagnostic.v1"

_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "clone_root",
        "capsule_dir",
        "expected_capsule_digest",
        "expected_compiler_runtime_identity_digest",
        "target_workflow_name",
        "child_run_id",
        "child_state_dir",
        "inputs",
    }
)
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class RunRefChildRequest:
    """Closed request envelope accepted by the private child command."""

    clone_root: Path
    capsule_dir: Path
    expected_capsule_digest: str
    expected_compiler_runtime_identity_digest: str
    target_workflow_name: str
    child_run_id: str
    child_state_dir: Path
    inputs: Mapping[str, Any]


class _ChildCommandError(ValueError):
    def __init__(self, code: str, reason: str, *, exit_code: int = 2) -> None:
        self.code = code
        self.reason = reason
        self.exit_code = exit_code
        super().__init__(reason)


def _reject_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError("duplicate JSON object key")
        payload[key] = value
    return payload


def _reject_nonfinite_constant(_value: str) -> None:
    raise ValueError("non-finite JSON constants are not admitted")


def _plain_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite JSON number")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_json(item) for item in value]
    raise TypeError("value is not JSON-transportable")


def _canonical_existing_directory(value: object) -> Path:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("directory must be a non-empty string")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("directory must be absolute")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or resolved.as_posix() != value:
        raise ValueError("directory must be canonical and existing")
    return resolved


def _canonical_future_directory(value: object) -> Path:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("directory must be a non-empty string")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("directory must be absolute")
    resolved = path.resolve(strict=False)
    if resolved.as_posix() != value:
        raise ValueError("directory must be canonical")
    return resolved


def _request_from_payload(payload: object) -> RunRefChildRequest:
    if not isinstance(payload, dict) or set(payload) != _REQUEST_KEYS:
        raise ValueError("request shape is invalid")
    if payload.get("schema_version") != RUN_REF_CHILD_REQUEST_SCHEMA:
        raise ValueError("request schema version is invalid")
    clone_root = _canonical_existing_directory(payload.get("clone_root"))
    capsule_dir = _canonical_existing_directory(payload.get("capsule_dir"))
    child_state_dir = _canonical_future_directory(
        payload.get("child_state_dir")
    )
    try:
        child_state_dir.relative_to(clone_root)
    except ValueError as exc:
        raise ValueError("child state directory must be below clone root") from exc
    if child_state_dir != clone_root / ".orchestrate" / "runs":
        raise ValueError("child state directory is not the ordinary runs root")

    expected_capsule_digest = payload.get("expected_capsule_digest")
    expected_compiler_digest = payload.get(
        "expected_compiler_runtime_identity_digest"
    )
    if (
        not isinstance(expected_capsule_digest, str)
        or _SHA256_RE.fullmatch(expected_capsule_digest) is None
        or not isinstance(expected_compiler_digest, str)
        or _SHA256_RE.fullmatch(expected_compiler_digest) is None
    ):
        raise ValueError("request digest is invalid")
    target = payload.get("target_workflow_name")
    if (
        not isinstance(target, str)
        or not target
        or "\0" in target
        or target.strip() != target
    ):
        raise ValueError("target workflow name is invalid")
    child_run_id = payload.get("child_run_id")
    if (
        not isinstance(child_run_id, str)
        or _RUN_ID_RE.fullmatch(child_run_id) is None
    ):
        raise ValueError("child run id is invalid")
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a JSON object")
    canonical_inputs = _plain_json(inputs)
    return RunRefChildRequest(
        clone_root=clone_root,
        capsule_dir=capsule_dir,
        expected_capsule_digest=expected_capsule_digest,
        expected_compiler_runtime_identity_digest=expected_compiler_digest,
        target_workflow_name=target,
        child_run_id=child_run_id,
        child_state_dir=child_state_dir,
        inputs=canonical_inputs,
    )


def load_request(path: Path) -> RunRefChildRequest:
    """Load and validate one strict versioned request document."""

    try:
        request_bytes = Path(path).read_bytes()
        payload = json.loads(
            request_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
        return _request_from_payload(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "request_invalid",
        ) from exc


def _target_bundle(request: RunRefChildRequest):
    local_identity = compute_compiler_runtime_identity()
    if (
        local_identity.digest
        != request.expected_compiler_runtime_identity_digest
    ):
        raise BundleCapsuleValidationError(
            "run_ref_bundle_compiler_identity_invalid"
        )
    encoded = read_bundle_capsule_directory(
        request.capsule_dir,
        expected_capsule_digest=request.expected_capsule_digest,
    )
    decoded = decode_bundle_capsule(
        manifest_bytes=encoded.manifest_bytes,
        pickle_bytes=encoded.pickle_bytes,
        closure=encoded.closure,
        expected_capsule_digest=request.expected_capsule_digest,
        expected_compiler_runtime_identity_digest=(
            request.expected_compiler_runtime_identity_digest
        ),
    )
    staged = stage_bundle_capsule(decoded, clone_root=request.clone_root)
    target = request.target_workflow_name
    if (
        target not in decoded.target_workflow_names
        or target not in staged.target_workflow_names
        or target not in staged.bundles_by_name
    ):
        raise _ChildCommandError(
            "run_ref_capsule_invalid",
            "target_not_declared",
        )
    return staged.bundles_by_name[target]


def execute_request(request: RunRefChildRequest) -> dict[str, Any]:
    """Execute one decoded/staged mode-1 target through the ordinary runtime."""

    bundle = _target_bundle(request)
    try:
        bound_inputs = bind_workflow_inputs(
            workflow_public_input_contracts(bundle),
            request.inputs,
            request.clone_root,
        )
    except Exception as exc:
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "input_binding_rejected",
        ) from exc

    try:
        workflow_path = bundle.provenance.workflow_path.resolve(strict=True)
        workflow_file = workflow_path.relative_to(request.clone_root).as_posix()
        context = _plain_json(workflow_context(bundle))
        if not isinstance(context, dict):
            raise TypeError("workflow context is not an object")
        manager = StateManager(
            request.clone_root,
            run_id=request.child_run_id,
            state_dir=request.child_state_dir,
        )
        manager.initialize(
            workflow_file,
            context=context,
            bound_inputs=bound_inputs,
        )
        state = WorkflowExecutor(
            bundle,
            request.clone_root,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")
    except _ChildCommandError:
        raise
    except Exception as exc:
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "workflow_execution_failed",
            exit_code=1,
        ) from exc
    if state.get("status") != "completed":
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "workflow_execution_failed",
            exit_code=1,
        )
    try:
        workflow_outputs = _plain_json(state.get("workflow_outputs", {}))
    except TypeError as exc:
        raise _ChildCommandError(
            "run_ref_child_result_invalid",
            "workflow_outputs_invalid",
            exit_code=1,
        ) from exc
    if not isinstance(workflow_outputs, dict):
        raise _ChildCommandError(
            "run_ref_child_result_invalid",
            "workflow_outputs_invalid",
            exit_code=1,
        )
    return {
        "schema_version": RUN_REF_CHILD_RESULT_SCHEMA,
        "status": "completed",
        "capsule_digest": request.expected_capsule_digest,
        "target_workflow_name": request.target_workflow_name,
        "child_run_id": request.child_run_id,
        "workflow_outputs": workflow_outputs,
    }


def _request_path(argv: Sequence[str]) -> Path:
    if len(argv) != 2 or argv[0] != "--request" or not argv[1]:
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "request_invalid",
        )
    return Path(argv[1])


def _write_document(stream, payload: Mapping[str, Any]) -> None:
    stream.write(canonical_json_bytes(dict(payload)) + b"\n")
    stream.flush()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the private command, emitting one canonical result or diagnostic."""

    arguments = tuple(sys.argv[1:] if argv is None else argv)
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            request = load_request(_request_path(arguments))
            result = execute_request(request)
    except BundleCapsuleValidationError:
        error = _ChildCommandError(
            "run_ref_capsule_invalid",
            "capsule_validation_failed",
        )
    except _ChildCommandError as exc:
        error = exc
    except Exception:
        error = _ChildCommandError(
            "run_ref_child_launch_failed",
            "workflow_execution_failed",
            exit_code=1,
        )
    else:
        _write_document(sys.stdout.buffer, result)
        return 0
    _write_document(
        sys.stderr.buffer,
        {
            "schema_version": RUN_REF_CHILD_DIAGNOSTIC_SCHEMA,
            "status": "rejected",
            "code": error.code,
            "reason": error.reason,
        },
    )
    return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
