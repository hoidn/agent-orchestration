"""Private child commands for executing one admitted ``run-ref`` program."""

from __future__ import annotations

import base64
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Mapping, Sequence

from orchestrator.run_lock import run_writer_lock
from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig
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
    PostSetupBaselineIdentity,
    RepositoryRevisionId,
    VerifiedGitTreeIdentity,
    canonical_json_bytes,
    canonical_sha256,
    compute_compiler_runtime_identity,
)
from .config import decode_run_ref_static_config
from .source import MaterializedSource, canonical_repository_revision_result
from .workspace import TreeEntry, TreeManifest, freeze_tree, manifest_from_entries


RUN_REF_CHILD_REQUEST_SCHEMA = "run_ref_child_request.v1"
RUN_REF_CHILD_RESULT_SCHEMA = "run_ref_child_result.v1"
RUN_REF_PATH_CHILD_REQUEST_SCHEMA = "run_ref_path_child_request.v1"
RUN_REF_PATH_CHILD_RESULT_SCHEMA = "run_ref_path_child_result.v1"
RUN_REF_CHILD_DIAGNOSTIC_SCHEMA = "run_ref_child_diagnostic.v1"
RUN_REF_MATERIALIZED_SOURCE_SCHEMA = "run_ref_materialized_source.v1"
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
_STRUCTURAL_REFUSAL_CODES = frozenset(
    {
        "trial_program_missing",
        "trial_program_compile_rejected",
        "trial_program_signature_mismatch",
        "trial_candidate_environment_not_admissible",
    }
)
_RUNTIME_FAILURE_REASONS = {
    "run_ref_capsule_invalid": frozenset(
        {"capsule_validation_failed", "target_not_declared"}
    ),
    "run_ref_child_launch_failed": frozenset(
        {
            "request_invalid",
            "input_binding_rejected",
            "workflow_execution_failed",
        }
    ),
    "run_ref_child_result_invalid": frozenset(
        {"workflow_outputs_invalid", "child_failure_authority_invalid"}
    ),
}
_EXIT_ONE_REASONS = frozenset(
    {
        "workflow_execution_failed",
        "workflow_outputs_invalid",
        "child_failure_authority_invalid",
    }
)
_COMPILE_DIAGNOSTIC_KEYS = frozenset(
    {
        "code",
        "diagnostic_kind",
        "severity",
        "message",
        "path",
        "line",
        "column",
        "form_path",
        "expansion_stack",
        "notes",
        "phase",
        "validation_pass",
        "authority_layer",
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


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value


def _validate_source_location(value: object) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {"path", "line", "column"}
        or not _nonempty_string(value.get("path"))
        or type(value.get("line")) is not int
        or value["line"] < 1
        or type(value.get("column")) is not int
        or value["column"] < 1
    ):
        raise ValueError("compile diagnostic expansion location is invalid")


def _validate_expansion_frame(value: object) -> None:
    base = {"macro_name", "function_name", "expansion_id"}
    if not isinstance(value, dict) or frozenset(value) not in {
        frozenset(base),
        frozenset(base | {"call"}),
        frozenset(base | {"definition"}),
        frozenset(base | {"call", "definition"}),
    }:
        raise ValueError("compile diagnostic expansion frame is invalid")
    for field in base:
        item = value[field]
        if item is not None and not _nonempty_string(item):
            raise ValueError("compile diagnostic expansion frame is invalid")
    if value["macro_name"] is None and value["function_name"] is None:
        raise ValueError("compile diagnostic expansion frame is invalid")
    for field in ("call", "definition"):
        if field in value:
            _validate_source_location(value[field])


def _validate_compile_diagnostic_row(value: object) -> None:
    if not isinstance(value, dict) or frozenset(value) not in {
        _COMPILE_DIAGNOSTIC_KEYS,
        _COMPILE_DIAGNOSTIC_KEYS | {"phased_delivery_diagnostic"},
    }:
        raise ValueError("compile diagnostic row shape is invalid")
    for field in ("code", "severity", "message", "path"):
        if not _nonempty_string(value[field]):
            raise ValueError("compile diagnostic scalar is invalid")
    for field in (
        "diagnostic_kind",
        "phase",
        "validation_pass",
        "authority_layer",
    ):
        item = value[field]
        if item is not None and not _nonempty_string(item):
            raise ValueError("compile diagnostic scalar is invalid")
    if (
        type(value["line"]) is not int
        or value["line"] < 1
        or type(value["column"]) is not int
        or value["column"] < 1
    ):
        raise ValueError("compile diagnostic position is invalid")
    for field in ("form_path", "notes"):
        items = value[field]
        if not isinstance(items, list) or any(
            not _nonempty_string(item) for item in items
        ):
            raise ValueError("compile diagnostic string vector is invalid")
    expansion_stack = value["expansion_stack"]
    if not isinstance(expansion_stack, list):
        raise ValueError("compile diagnostic expansion stack is invalid")
    for frame in expansion_stack:
        _validate_expansion_frame(frame)
    if "phased_delivery_diagnostic" in value:
        from orchestrator.workflow.provider_phased_delivery.protocol import (
            diagnostic_from_dict,
            diagnostic_to_dict,
        )

        diagnostic = diagnostic_from_dict(value["phased_delivery_diagnostic"])
        if diagnostic_to_dict(diagnostic) != value["phased_delivery_diagnostic"]:
            raise ValueError("nested phased diagnostic is not canonical")


def _validate_accepted_compile_identity(document: Mapping[str, Any]) -> None:
    selected_entry = document.get("selected_entry")
    identity = document.get("normalized_program_identity")
    if not isinstance(selected_entry, Mapping) or not isinstance(identity, Mapping):
        raise ValueError("accepted compile authority is invalid")
    identity_schema = identity.get("schema_version")
    expected_identity_fields = {
        "schema_version",
        "digest",
        "compiler_runtime_identity",
        "module_source_revisions",
        "compiler_source_revisions",
        "imported_bundle_bindings",
        "selected_entry_sha256",
        "lowering_route",
        "lowering_schema_version",
        "configuration_payload_digests",
        "configuration_revisions",
    }
    if identity_schema == "workflow_lisp_program_identity.v2":
        expected_identity_fields.add("boundary_admission_profile")
    elif identity_schema != "workflow_lisp_program_identity.v1":
        raise ValueError("accepted compile identity version is invalid")
    if set(identity) != expected_identity_fields:
        raise ValueError("accepted compile identity shape is invalid")
    from orchestrator.workflow_lisp.diagnostics import (
        build_normalized_program_identity,
    )

    rebuilt = build_normalized_program_identity(
        compiler_runtime_identity=identity["compiler_runtime_identity"],
        module_source_revisions=identity["module_source_revisions"],
        compiler_source_revisions=identity["compiler_source_revisions"],
        imported_bundle_bindings=identity["imported_bundle_bindings"],
        selected_entry=selected_entry,
        lowering_route=identity["lowering_route"],
        lowering_schema_version=identity["lowering_schema_version"],
        configuration_payload_digests=identity[
            "configuration_payload_digests"
        ],
        configuration_revisions=identity["configuration_revisions"],
        boundary_admission_profile=(
            identity.get("boundary_admission_profile")
            if identity_schema == "workflow_lisp_program_identity.v2"
            else None
        ),
    )
    if rebuilt != identity:
        raise ValueError("accepted compile identity is not canonical")


def _validated_compile_diagnostics(value: object) -> dict[str, Any]:
    document = _plain_json(value)
    if not isinstance(document, dict):
        raise ValueError("compile diagnostics must be an object")
    status = document.get("status")
    expected = {"schema_version", "status", "diagnostics"}
    if status == "accepted":
        expected |= {"selected_entry", "normalized_program_identity"}
    elif status != "rejected":
        raise ValueError("compile diagnostics status is invalid")
    if (
        set(document) != expected
        or document.get("schema_version")
        != "workflow_lisp_compile_diagnostics.v1"
        or not isinstance(document.get("diagnostics"), list)
    ):
        raise ValueError("compile diagnostics shape is invalid")
    diagnostics = document["diagnostics"]
    if status == "rejected" and not diagnostics:
        raise ValueError("rejected compile diagnostics must be non-empty")
    for row in diagnostics:
        _validate_compile_diagnostic_row(row)
    if status == "accepted":
        _validate_accepted_compile_identity(document)
    return document


def validate_child_diagnostic_document(value: object) -> dict[str, Any]:
    """Validate and copy one exact child failure authority document."""

    document = _plain_json(value)
    common = {"schema_version", "status", "code", "reason"}
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != RUN_REF_CHILD_DIAGNOSTIC_SCHEMA
        or document.get("status") != "rejected"
        or not _nonempty_string(document.get("code"))
        or not _nonempty_string(document.get("reason"))
    ):
        raise ValueError("child diagnostic common authority is invalid")
    code = document["code"]
    reason = document["reason"]
    if code in _STRUCTURAL_REFUSAL_CODES:
        allowed_shapes = {
            frozenset(common | {"rejected_value", "secondary_causes"}),
            frozenset(
                common
                | {
                    "rejected_value",
                    "secondary_causes",
                    "compile_diagnostics",
                }
            ),
        }
        if (
            frozenset(document) not in allowed_shapes
            or reason != "path_compile_rejected"
        ):
            raise ValueError("structural child diagnostic shape is invalid")
        causes = document["secondary_causes"]
        if (
            not isinstance(causes, list)
            or not causes
            or any(
                not _nonempty_string(cause) or cause.strip() != cause
                for cause in causes
            )
            or len(causes) != len(set(causes))
        ):
            raise ValueError("structural child secondary causes are invalid")
        if "compile_diagnostics" in document:
            compile_document = _validated_compile_diagnostics(
                document["compile_diagnostics"]
            )
            rejected_value = document["rejected_value"]
            if (
                isinstance(rejected_value, Mapping)
                and "compile_diagnostics" in rejected_value
                and rejected_value["compile_diagnostics"] != compile_document
            ):
                raise ValueError("compile diagnostic authority is inconsistent")
        return document
    allowed_reasons = _RUNTIME_FAILURE_REASONS.get(code)
    if (
        allowed_reasons is None
        or reason not in allowed_reasons
        or set(document) != common
    ):
        raise ValueError("runtime child diagnostic authority is invalid")
    return document


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


def _tree_manifest_record(manifest: TreeManifest) -> dict[str, object]:
    if type(manifest) is not TreeManifest:
        raise TypeError("tree manifest authority must be exact")
    return {
        "schema_version": manifest.schema_version,
        "entries": [
            {
                "path": entry.path,
                "kind": entry.kind,
                "mode": entry.mode,
                "size": entry.size,
                "sha256": entry.sha256,
                "link_target": entry.link_target,
            }
            for entry in manifest.entries
        ],
        "digest": manifest.digest,
    }


def _tree_entry_from_payload(value: object) -> TreeEntry:
    expected = {"path", "kind", "mode", "size", "sha256", "link_target"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("tree manifest entry shape is invalid")
    path = value["path"]
    if not isinstance(path, str) or not path or "\\" in path or "\0" in path:
        raise ValueError("tree manifest path is invalid")
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != path
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise ValueError("tree manifest path is not canonical")
    kind = value["kind"]
    if kind not in {"directory", "file", "symlink"}:
        raise ValueError("tree manifest kind is invalid")
    mode = value["mode"]
    size = value["size"]
    if (
        isinstance(mode, bool)
        or not isinstance(mode, int)
        or mode < 0
        or mode > 0o7777
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise ValueError("tree manifest numeric facts are invalid")
    digest = value["sha256"]
    if digest is not None and (
        not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None
    ):
        raise ValueError("tree manifest digest is invalid")
    link_target = value["link_target"]
    if link_target is not None and (
        not isinstance(link_target, str) or "\0" in link_target
    ):
        raise ValueError("tree manifest link target is invalid")
    if kind == "directory" and (
        size != 0 or digest is not None or link_target is not None
    ):
        raise ValueError("tree directory facts are invalid")
    if kind == "file" and (digest is None or link_target is not None):
        raise ValueError("tree file facts are invalid")
    if kind == "symlink" and (digest is None or link_target is None):
        raise ValueError("tree symlink facts are invalid")
    return TreeEntry(
        path=path,
        kind=kind,
        mode=mode,
        size=size,
        sha256=digest,
        link_target=link_target,
    )


def _tree_manifest_from_payload(value: object) -> TreeManifest:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "entries",
        "digest",
    }:
        raise ValueError("tree manifest shape is invalid")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("tree manifest schema is invalid")
    entries = value["entries"]
    if not isinstance(entries, list):
        raise ValueError("tree manifest entries are invalid")
    manifest = manifest_from_entries(
        _tree_entry_from_payload(entry) for entry in entries
    )
    if _tree_manifest_record(manifest) != value:
        raise ValueError("tree manifest does not match its canonical digest")
    return manifest


def materialized_source_record(source: MaterializedSource) -> dict[str, object]:
    """Encode exact reconstructible materialization facts for the path child."""

    if type(source) is not MaterializedSource:
        raise TypeError("materialized source authority must be exact")
    components: dict[str, object] = {
        "schema_version": RUN_REF_MATERIALIZED_SOURCE_SCHEMA,
        "repository_revision": canonical_repository_revision_result(
            source.repository_revision_id
        ),
        "normalized_locator": source.normalized_locator,
        "resolved_commit_sha": source.resolved_commit_sha,
        "verified_git_tree": source.verified_git_tree.value,
        "mirror_path": source.mirror_path.as_posix(),
        "mirror_seal_path": source.mirror_seal_path.as_posix(),
        "workspace_path": source.workspace_path.as_posix(),
        "source_tree_manifest": _tree_manifest_record(
            source.source_tree_manifest
        ),
        "setup_evidence_path": source.setup_evidence_path.as_posix(),
        "setup_evidence_digest": source.setup_evidence_digest,
        "post_setup_tree_manifest": _tree_manifest_record(
            source.post_setup_tree_manifest
        ),
        "post_setup_baseline_identity": (
            source.post_setup_baseline_identity.digest
        ),
    }
    return {**components, "digest": canonical_sha256(components)}


def _repository_revision_from_payload(value: object) -> RepositoryRevisionId:
    expected = {
        "schema_version",
        "digest",
        "normalized_locator",
        "resolved_commit_sha",
        "materializer_version",
        "submodule_policy",
        "lfs_policy",
        "authored_setup_identity",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("repository revision shape is invalid")
    if value["schema_version"] != "run_ref_repository_revision.v1":
        raise ValueError("repository revision schema is invalid")
    revision = RepositoryRevisionId(
        digest=value["digest"],
        normalized_locator=value["normalized_locator"],
        resolved_commit_sha=value["resolved_commit_sha"],
        materializer_version=value["materializer_version"],
        submodule_policy=value["submodule_policy"],
        lfs_policy=value["lfs_policy"],
        authored_setup_identity=value["authored_setup_identity"],
    )
    if canonical_repository_revision_result(revision) != value:
        raise ValueError("repository revision is not canonical")
    return revision


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


def _path_request_from_payload(payload: object) -> RunRefPathChildRequest:
    if not isinstance(payload, dict) or set(payload) != _PATH_REQUEST_KEYS:
        raise ValueError("path request shape is invalid")
    if payload.get("schema_version") != RUN_REF_PATH_CHILD_REQUEST_SCHEMA:
        raise ValueError("path request schema version is invalid")
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
    )


def load_path_request(path: Path) -> RunRefPathChildRequest:
    """Load and validate one strict versioned path-child request."""

    try:
        request_bytes = Path(path).read_bytes()
        payload = json.loads(
            request_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
        return _path_request_from_payload(payload)
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
    _complete_injected_boundary(
        request.test_control,
        boundary="mode_1_decode",
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


def compile_and_admit_path_program(*, materialized_source, step_config):
    """Load the full compiler only when the private path command is selected."""

    from .path_compile import compile_and_admit_path_program as compile_path

    return compile_path(
        materialized_source=materialized_source,
        step_config=step_config,
    )


def _execute_bundle(
    bundle: Any,
    *,
    clone_root: Path,
    child_run_id: str,
    child_state_dir: Path,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute one admitted bundle while owning its run-lifetime writer lock."""

    try:
        bound_inputs = bind_workflow_inputs(
            workflow_public_input_contracts(bundle),
            inputs,
            clone_root,
        )
    except Exception as exc:
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "input_binding_rejected",
        ) from exc

    try:
        workflow_path = bundle.provenance.workflow_path.resolve(strict=True)
        workflow_file = workflow_path.relative_to(clone_root).as_posix()
        context = _plain_json(workflow_context(bundle))
        if not isinstance(context, dict):
            raise TypeError("workflow context is not an object")
        manager = StateManager(
            clone_root,
            run_id=child_run_id,
            state_dir=child_state_dir,
        )
        manager.run_root.mkdir(parents=True, exist_ok=False)
        with run_writer_lock(manager.run_root):
            manager.initialize(
                workflow_file,
                context=context,
                bound_inputs=bound_inputs,
            )
            state = WorkflowExecutor(
                bundle,
                clone_root,
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
    return workflow_outputs


def execute_request(request: RunRefChildRequest) -> dict[str, Any]:
    """Execute one decoded/staged mode-1 target through the ordinary runtime."""

    workflow_outputs = _execute_bundle(
        _target_bundle(request),
        clone_root=request.clone_root,
        child_run_id=request.child_run_id,
        child_state_dir=request.child_state_dir,
        inputs=request.inputs,
    )
    return {
        "schema_version": RUN_REF_CHILD_RESULT_SCHEMA,
        "status": "completed",
        "capsule_digest": request.expected_capsule_digest,
        "target_workflow_name": request.target_workflow_name,
        "child_run_id": request.child_run_id,
        "workflow_outputs": workflow_outputs,
    }


def execute_path_request(request: RunRefPathChildRequest) -> dict[str, Any]:
    """Full-compile and execute one exact path program in this child process."""

    try:
        admitted = compile_and_admit_path_program(
            materialized_source=request.materialized_source,
            step_config=request.step_config,
        )
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
    workflow_outputs = _execute_bundle(
        admitted.build_result.validated_bundle,
        clone_root=request.clone_root,
        child_run_id=request.child_run_id,
        child_state_dir=request.child_state_dir,
        inputs=request.inputs,
    )
    return {
        "schema_version": RUN_REF_PATH_CHILD_RESULT_SCHEMA,
        "status": "completed",
        "step_config_digest": request.step_config.step_config_digest,
        "target_workflow_name": admitted.build_result.selected_workflow_name,
        "child_run_id": request.child_run_id,
        "workflow_outputs": workflow_outputs,
        "path_compile": {
            "diagnostics": admitted.diagnostics_document,
            "program_identity": admitted.program_identity,
            "signature": admitted.signature,
            "effect_facts": admitted.effect_facts,
            "evidence": admitted.evidence,
        },
    }


def _request_selection(argv: Sequence[str]) -> tuple[str, Path]:
    if (
        len(argv) != 2
        or argv[0] not in {"--request", "--path-request"}
        or not argv[1]
    ):
        raise _ChildCommandError(
            "run_ref_child_launch_failed",
            "request_invalid",
        )
    return argv[0], Path(argv[1])


def _write_document(stream, payload: Mapping[str, Any]) -> None:
    stream.write(canonical_json_bytes(dict(payload)) + b"\n")
    stream.flush()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the private command, emitting one canonical result or diagnostic."""

    arguments = tuple(sys.argv[1:] if argv is None else argv)
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            selection, request_path = _request_selection(arguments)
            if selection == "--request":
                result = execute_request(load_request(request_path))
            else:
                result = execute_path_request(load_path_request(request_path))
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
