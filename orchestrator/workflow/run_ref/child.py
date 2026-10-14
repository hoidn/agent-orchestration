"""Private child commands for executing one admitted ``run-ref`` program."""

from __future__ import annotations

import base64
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
import io
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

from orchestrator.run_lock import run_writer_lock, workspace_run_lock
from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig


from .contracts import (
    PostSetupBaselineIdentity,
    VerifiedGitTreeIdentity,
    canonical_json_bytes,
    canonical_sha256,
    compute_compiler_runtime_identity,
)
from .config import decode_run_ref_static_config, encode_run_ref_static_config
from .source import MaterializedSource
from .workspace import freeze_tree
from .wire import (
    RUN_REF_CHILD_DIAGNOSTIC_SCHEMA,
    RUN_REF_MATERIALIZED_SOURCE_SCHEMA,
    _plain_json,
    _repository_revision_from_payload,
    _tree_manifest_from_payload,
    materialized_source_record,
    validate_child_diagnostic_document,
)


RUN_REF_CHILD_REQUEST_SCHEMA = "run_ref_child_request.v1"
RUN_REF_CHILD_RESULT_SCHEMA = "run_ref_child_result.v1"
RUN_REF_PATH_CHILD_REQUEST_SCHEMA = "run_ref_path_child_request.v1"
RUN_REF_PATH_CHILD_RESULT_SCHEMA = "run_ref_path_child_result.v1"
RUN_REF_CHILD_TEST_CONTROL_SCHEMA = "run_ref_child_test_control.v1"
RUN_REF_CHILD_BOUNDARY_PROGRESS_SCHEMA = (
    "run_ref_child_boundary_progress.v1"
)
RUN_REF_CHILD_INJECTED_CRASH_EXIT_CODE = 86

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
        "test_control",
    }
)
_PATH_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "clone_root",
        "child_state_dir",
        "child_run_id",
        "materialized_source",
        "run_ref_static_config_base64",
        "expected_step_config_digest",
        "inputs",
        "test_control",
    }
)
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT_TREE_RE = re.compile(r"git-tree:[0-9a-f]{40}\Z")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_TEST_BOUNDARIES = frozenset({"mode_1_decode", "mode_2_compile"})
_EXIT_ONE_REASONS = frozenset(
    {
        "workflow_execution_failed",
        "workflow_outputs_invalid",
        "child_failure_authority_invalid",
    }
)


@dataclass(frozen=True, slots=True)
class RunRefChildTestControl:
    """One closed request-carried crash control used only by tests."""

    boundary: str
    progress_path: Path


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
    test_control: RunRefChildTestControl | None


@dataclass(frozen=True, slots=True)
class RunRefPathChildRequest:
    """Closed request envelope for one full-compile path child."""

    clone_root: Path
    child_run_id: str
    child_state_dir: Path
    materialized_source: MaterializedSource
    step_config: RunRefStepConfig
    inputs: Mapping[str, Any]
    test_control: RunRefChildTestControl | None
    request_document: Mapping[str, Any] | None = field(default=None, compare=False, repr=False)
    parent_root_fd: int | None = field(default=None, compare=False, repr=False)


class _ChildCommandError(ValueError):
    def __init__(
        self,
        code: str,
        reason: str,
        *,
        exit_code: int = 2,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        payload = validate_child_diagnostic_document(
            {
                "schema_version": RUN_REF_CHILD_DIAGNOSTIC_SCHEMA,
                "status": "rejected",
                "code": code,
                "reason": reason,
                **({} if details is None else _plain_json(details)),
            }
        )
        expected_exit = 1 if reason in _EXIT_ONE_REASONS else 2
        if type(exit_code) is not int or exit_code != expected_exit:
            raise ValueError("child diagnostic exit code is invalid")
        self.code = code
        self.reason = reason
        self.exit_code = exit_code
        self.details = {
            key: value
            for key, value in payload.items()
            if key
            not in {"schema_version", "status", "code", "reason"}
        }
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


def _canonical_absolute_path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError("path must be a non-empty string")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("path must be absolute")
    resolved = path.resolve(strict=False)
    if resolved.as_posix() != value:
        raise ValueError("path must be canonical")
    return resolved


def _test_control_from_payload(
    value: object,
    *,
    clone_root: Path,
    expected_boundary: str,
) -> RunRefChildTestControl | None:
    if expected_boundary not in _TEST_BOUNDARIES:
        raise ValueError("test boundary is not admitted")
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "boundary", "progress_path"}
        or value.get("schema_version") != RUN_REF_CHILD_TEST_CONTROL_SCHEMA
        or value.get("boundary") != expected_boundary
    ):
        raise ValueError("child test control shape is invalid")
    progress_path = _canonical_absolute_path(value.get("progress_path"))
    expected_path = (
        clone_root.parent / "run-ref-child-boundary-progress.json"
    ).resolve(strict=False)
    if progress_path != expected_path or os.path.lexists(progress_path):
        raise ValueError("child test progress path is invalid")
    return RunRefChildTestControl(
        boundary=expected_boundary,
        progress_path=progress_path,
    )


def _complete_injected_boundary(
    control: RunRefChildTestControl | None,
    *,
    boundary: str,
) -> None:
    if control is None:
        return
    if type(control) is not RunRefChildTestControl or control.boundary != boundary:
        raise _ChildCommandError(
            "run_ref_child_result_invalid",
            "child_failure_authority_invalid",
            exit_code=1,
        )
    payload = canonical_json_bytes(
        {
            "schema_version": RUN_REF_CHILD_BOUNDARY_PROGRESS_SCHEMA,
            "boundary": boundary,
        }
    ) + b"\n"
    try:
        with control.progress_path.open("xb") as stream:
            written = stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if written != len(payload):
            raise OSError("short child progress write")
    except OSError as exc:
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "workflow_execution_failed",
            exit_code=1,
        ) from exc
    os._exit(RUN_REF_CHILD_INJECTED_CRASH_EXIT_CODE)


def _materialized_source_from_payload(
    value: object,
    *,
    clone_root: Path,
) -> MaterializedSource:
    expected = {
        "schema_version",
        "repository_revision",
        "normalized_locator",
        "resolved_commit_sha",
        "verified_git_tree",
        "mirror_path",
        "mirror_seal_path",
        "workspace_path",
        "source_tree_manifest",
        "setup_evidence_path",
        "setup_evidence_digest",
        "post_setup_tree_manifest",
        "post_setup_baseline_identity",
        "digest",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("materialized source shape is invalid")
    components = {key: item for key, item in value.items() if key != "digest"}
    if (
        value["schema_version"] != RUN_REF_MATERIALIZED_SOURCE_SCHEMA
        or value["digest"] != canonical_sha256(components)
    ):
        raise ValueError("materialized source digest is invalid")
    revision = _repository_revision_from_payload(value["repository_revision"])
    normalized_locator = value["normalized_locator"]
    resolved_commit_sha = value["resolved_commit_sha"]
    if (
        normalized_locator != revision.normalized_locator
        or resolved_commit_sha != revision.resolved_commit_sha
    ):
        raise ValueError("materialized source identity is inconsistent")
    verified_git_tree = value["verified_git_tree"]
    if (
        not isinstance(verified_git_tree, str)
        or _GIT_TREE_RE.fullmatch(verified_git_tree) is None
    ):
        raise ValueError("materialized source Git tree is invalid")
    workspace_path = _canonical_existing_directory(value["workspace_path"])
    if workspace_path != clone_root:
        raise ValueError("materialized workspace does not match clone root")
    mirror_path = _canonical_absolute_path(value["mirror_path"])
    mirror_seal_path = _canonical_absolute_path(value["mirror_seal_path"])
    setup_evidence_path = _canonical_absolute_path(value["setup_evidence_path"])
    source_manifest = _tree_manifest_from_payload(value["source_tree_manifest"])
    post_setup_manifest = _tree_manifest_from_payload(
        value["post_setup_tree_manifest"]
    )
    setup_evidence_digest = value["setup_evidence_digest"]
    baseline_digest = value["post_setup_baseline_identity"]
    if (
        not isinstance(setup_evidence_digest, str)
        or _SHA256_RE.fullmatch(setup_evidence_digest) is None
        or baseline_digest != post_setup_manifest.digest
    ):
        raise ValueError("materialized source baseline facts are invalid")
    try:
        setup_bytes = setup_evidence_path.read_bytes()
        setup_document = json.loads(
            setup_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("setup evidence is unreadable") from exc
    if (
        canonical_json_bytes(setup_document) + b"\n" != setup_bytes
        or canonical_sha256(setup_document) != setup_evidence_digest
    ):
        raise ValueError("setup evidence digest is invalid")
    if freeze_tree(
        workspace_path,
        excluded_roots=(".git", ".orchestrate"),
    ) != post_setup_manifest:
        raise ValueError("materialized workspace no longer matches its baseline")
    return MaterializedSource(
        repository_revision_id=revision,
        normalized_locator=normalized_locator,
        resolved_commit_sha=resolved_commit_sha,
        verified_git_tree=VerifiedGitTreeIdentity(verified_git_tree),
        mirror_path=mirror_path,
        mirror_seal_path=mirror_seal_path,
        workspace_path=workspace_path,
        source_tree_manifest=source_manifest,
        setup_evidence_path=setup_evidence_path,
        setup_evidence_digest=setup_evidence_digest,
        post_setup_tree_manifest=post_setup_manifest,
        post_setup_baseline_identity=PostSetupBaselineIdentity(baseline_digest),
    )


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
    test_control = _test_control_from_payload(
        payload.get("test_control"),
        clone_root=clone_root,
        expected_boundary="mode_1_decode",
    )
    return RunRefChildRequest(
        clone_root=clone_root,
        capsule_dir=capsule_dir,
        expected_capsule_digest=expected_capsule_digest,
        expected_compiler_runtime_identity_digest=expected_compiler_digest,
        target_workflow_name=target,
        child_run_id=child_run_id,
        child_state_dir=child_state_dir,
        inputs=canonical_inputs,
        test_control=test_control,
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


def _path_request_authority(payload, parent_root_fd):
    from .launch_authority import PATH_REQUEST_V2, checked_parent_authority

    if not isinstance(payload, dict):
        raise ValueError("path request shape is invalid")
    schema = payload.get("schema_version")
    if schema == RUN_REF_PATH_CHILD_REQUEST_SCHEMA:
        if set(payload) != _PATH_REQUEST_KEYS or parent_root_fd is not None:
            raise ValueError("legacy path request authority is invalid")
        return None
    if schema != PATH_REQUEST_V2 or set(payload) != _PATH_REQUEST_KEYS | {"parent_authority"}:
        raise ValueError("path request schema or shape is invalid")
    if parent_root_fd is None:
        raise ValueError("checked path request has no parent descriptor")
    checked_parent_authority(payload)
    return payload


def _path_request_from_payload(payload: object, *, parent_root_fd: int | None = None) -> RunRefPathChildRequest:
    authority_document = _path_request_authority(payload, parent_root_fd)
    clone_root = _canonical_existing_directory(payload.get("clone_root"))
    child_state_dir = _canonical_future_directory(
        payload.get("child_state_dir")
    )
    if child_state_dir != clone_root / ".orchestrate" / "runs":
        raise ValueError("child state directory is not the ordinary runs root")
    child_run_id = payload.get("child_run_id")
    if (
        not isinstance(child_run_id, str)
        or _RUN_ID_RE.fullmatch(child_run_id) is None
    ):
        raise ValueError("child run id is invalid")
    encoded_config = payload.get("run_ref_static_config_base64")
    if not isinstance(encoded_config, str) or not encoded_config:
        raise ValueError("path request static config is invalid")
    try:
        static_config_bytes = base64.b64decode(
            encoded_config.encode("ascii"),
            validate=True,
        )
    except (UnicodeEncodeError, ValueError) as exc:
        raise ValueError("path request static config is invalid") from exc
    if base64.b64encode(static_config_bytes).decode("ascii") != encoded_config:
        raise ValueError("path request static config is not canonical base64")
    static_config = decode_run_ref_static_config(static_config_bytes)
    step_config = RunRefStepConfig(
        common=StepCommonConfig(),
        run_ref=static_config,
    )
    expected_step_config_digest = payload.get("expected_step_config_digest")
    if (
        not isinstance(expected_step_config_digest, str)
        or _SHA256_RE.fullmatch(expected_step_config_digest) is None
        or step_config.step_config_digest != expected_step_config_digest
    ):
        raise ValueError("path request step config digest is invalid")
    materialized_source = _materialized_source_from_payload(
        payload.get("materialized_source"),
        clone_root=clone_root,
    )
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a JSON object")
    test_control = _test_control_from_payload(
        payload.get("test_control"),
        clone_root=clone_root,
        expected_boundary="mode_2_compile",
    )
    return RunRefPathChildRequest(
        clone_root=clone_root,
        child_run_id=child_run_id,
        child_state_dir=child_state_dir,
        materialized_source=materialized_source,
        step_config=step_config,
        inputs=_plain_json(inputs),
        test_control=test_control,
        request_document=authority_document,
        parent_root_fd=parent_root_fd,
    )


def load_path_request(path: Path, *, parent_root_fd: int | None = None) -> RunRefPathChildRequest:
    """Load and validate one strict versioned path-child request."""

    try:
        request_bytes = Path(path).read_bytes()
        payload = json.loads(
            request_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
        return _path_request_from_payload(payload, parent_root_fd=parent_root_fd)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "request_invalid",
        ) from exc








def execute_request(request: RunRefChildRequest) -> dict[str, Any]:
    """Execute one decoded/staged mode-1 target through the ordinary runtime."""

    raise _ChildCommandError("workflow_execution_target_retired", "staged_execution_retired")


def execute_path_request(request: RunRefPathChildRequest) -> dict[str, Any]:
    """Full-compile and execute one exact path program in this child process."""

    _validate_path_launch_authority(request)
    try:
        admitted = _admit_path_request(request)
        _validate_closed_admission(request, admitted)
    except Exception as exc:
        from .path_compile import RunRefPathCompileRefusal

        if not isinstance(exc, RunRefPathCompileRefusal):
            raise
        details = {
                "rejected_value": exc.rejected_value,
                "secondary_causes": list(exc.secondary_causes),
        }
        if exc.compile_diagnostics_document is not None:
            details["compile_diagnostics"] = exc.compile_diagnostics_document
        try:
            refusal = _ChildCommandError(
                exc.code,
                "path_compile_rejected",
                details=details,
            )
        except (TypeError, ValueError):
            refusal = _ChildCommandError(
                "run_ref_child_result_invalid",
                "child_failure_authority_invalid",
                exit_code=1,
            )
        raise refusal from exc
    _complete_injected_boundary(
        request.test_control,
        boundary="mode_2_compile",
    )
    return _execute_closed_path(request, admitted)


def _admit_path_request(request):
    from .closed_path import compile_closed_path_if_evaluated

    return compile_closed_path_if_evaluated(materialized_source=request.materialized_source,
                                           step_config=request.step_config)


def _validate_closed_admission(request, admitted):
    from .closed_path import AdmittedClosedPathProgram
    from .path_contracts import validate_closed_path_facts

    if isinstance(admitted, AdmittedClosedPathProgram):
        validate_closed_path_facts(admitted.path_compile, program=admitted.build_result.program,
                                  materialized_source=request.materialized_source,
                                  step_config=request.step_config)


def _execute_closed_path(request, admitted):
    from orchestrator.cli.commands.evaluated import bind_program_inputs
    from orchestrator.workflow.evaluated.authority import publish_run_authority
    from orchestrator.workflow.evaluated.commands import workspace_relative_path
    from orchestrator.workflow.evaluated.runtime import execute_pure_run

    program = admitted.build_result.program
    path_program = request.step_config.run_ref.program
    recipe = {"source_roots": ["."], "entry_workflow": path_program.entry_name,
              "provider_externs_path": None, "prompt_externs_path": None,
              "imported_workflow_bundles_path": None, "command_boundaries_path": None,
              "input_file": None, "input_overrides": _plain_json(request.inputs)}
    try:
        bound = bind_program_inputs(program, request.inputs, workspace=request.clone_root)
    except Exception as exc:
        raise _ChildCommandError("run_ref_child_launch_failed", "input_binding_rejected") from exc
    with publish_run_authority(request.child_state_dir / request.child_run_id, program,
        run_id=request.child_run_id, workflow_file=path_program.path,
        workflow_checksum=admitted.workflow_checksum, bound_inputs=bound, resume_request=recipe,
        result_root=workspace_relative_path(request.clone_root, request.child_state_dir / request.child_run_id)) as authority:
        status, value = execute_pure_run(authority, bound, run_id=request.child_run_id,
                                        workspace=request.clone_root)
    if status != 0:
        raise _ChildCommandError("run_ref_child_launch_failed", "workflow_execution_failed", exit_code=1)
    return {"schema_version": "run_ref_path_child_result.v2", "status": "completed",
            "step_config_digest": request.step_config.step_config_digest,
            "target_workflow_name": program.tree["entry"], "child_run_id": request.child_run_id,
            "workflow_outputs": {"__result__": value}, "path_compile": admitted.path_compile}


def _path_request_fields(request: RunRefPathChildRequest) -> dict[str, object]:
    """Bind every executable field to the exact decoded v2 document."""
    from .launch_authority import PATH_REQUEST_V2

    control = request.test_control
    if control is not None and type(control) is not RunRefChildTestControl:
        raise TypeError("child test control must be exact")
    return {
        "schema_version": PATH_REQUEST_V2,
        "clone_root": request.clone_root.as_posix(),
        "child_run_id": request.child_run_id,
        "child_state_dir": request.child_state_dir.as_posix(),
        "materialized_source": materialized_source_record(request.materialized_source),
        "run_ref_static_config_base64": base64.b64encode(
            encode_run_ref_static_config(request.step_config.run_ref)).decode("ascii"),
        "expected_step_config_digest": request.step_config.step_config_digest,
        "inputs": _plain_json(request.inputs),
        "test_control": None if control is None else {
            "schema_version": RUN_REF_CHILD_TEST_CONTROL_SCHEMA,
            "boundary": control.boundary, "progress_path": control.progress_path.as_posix(),
        },
    }


def _validate_path_launch_authority(request: RunRefPathChildRequest) -> None:
    if request.request_document is None:
        if request.parent_root_fd is not None:
            raise _ChildCommandError("run_ref_child_launch_failed", "request_invalid")
        return
    from .launch_authority import validate_parent_launch

    try:
        fields = {key: value for key, value in request.request_document.items()
                  if key != "parent_authority"}
        if canonical_json_bytes(_path_request_fields(request)) != canonical_json_bytes(fields):
            raise ValueError("decoded executable fields disagree with the request")
        validate_parent_launch(request.request_document, parent_root_fd=request.parent_root_fd,
                               step_config=request.step_config, materialized_source=request.materialized_source)
    except (OSError, TypeError, ValueError) as exc:
        raise _ChildCommandError("run_ref_child_launch_failed", "request_invalid") from exc


def _request_selection(argv: Sequence[str]) -> tuple[str, Path, int | None]:
    descriptor = None
    if len(argv) == 4 and argv[0] == "--path-request" and argv[2] == "--parent-root-fd":
        try:
            descriptor = int(argv[3])
            if descriptor < 0 or str(descriptor) != argv[3]:
                raise ValueError("parent descriptor is not canonical")
        except ValueError as exc:
            raise _ChildCommandError("run_ref_child_launch_failed", "request_invalid") from exc
        argv = argv[:2]
    if (
        len(argv) != 2
        or argv[0] not in {"--request", "--path-request"}
        or not argv[1]
    ):
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "request_invalid",
        )
    return argv[0], Path(argv[1]), descriptor


def _write_document(stream, payload: Mapping[str, Any]) -> None:
    stream.write(canonical_json_bytes(dict(payload)) + b"\n")
    stream.flush()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the private command, emitting one canonical result or diagnostic."""

    arguments = tuple(sys.argv[1:] if argv is None else argv)
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            selection, request_path, parent_root_fd = _request_selection(arguments)
            if selection == "--request":
                request = load_request(request_path)
                execute = execute_request
            else:
                request = load_path_request(request_path, parent_root_fd=parent_root_fd)
                execute = execute_path_request
            with workspace_run_lock(request.clone_root, request.child_run_id):
                result = execute(request)
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
    diagnostic = validate_child_diagnostic_document(
        {
            "schema_version": RUN_REF_CHILD_DIAGNOSTIC_SCHEMA,
            "status": "rejected",
            "code": error.code,
            "reason": error.reason,
            **error.details,
        }
    )
    _write_document(sys.stderr.buffer, diagnostic)
    return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
