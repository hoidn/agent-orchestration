"""Delegated parent-side runtime primitives for durable run references."""

from __future__ import annotations

import base64
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
from typing import Any

from orchestrator._common.io_atomic import durable_atomic_write
from orchestrator.workflow.executable_ir import RunRefStepConfig
from orchestrator.workflow.references import (
    ReferenceResolutionError,
    ReferenceResolver,
)

from .config import (
    ArrayBinding,
    BundleProgram,
    InputBinding,
    LiteralBinding,
    ObjectBinding,
    PathProgram,
    ReferenceBinding,
    RunRefInput,
    encode_run_ref_static_config,
)
from .contracts import (
    PostSetupBaselineIdentity,
    RepositoryRevisionId,
    canonical_json_bytes,
    canonical_sha256,
)
from .delta import (
    DeclaredArtifact,
    RunRefDeltaError,
    build_workspace_delta,
    validate_workspace_delta,
)
from .ledger import (
    RunRefAttemptBindings,
    RunRefAttemptRecord,
    RunRefLedgerError,
    RunRefVisitKey,
    SettledRunRefResultBinding,
    advance_attempt,
    allocate_attempt,
    identify_incomplete_attempt,
    load_attempt_ledger,
    reconcile_pending_parent_commit,
    record_discarded_attempt,
    select_committed_reuse,
    settled_result_binding,
    settled_result_binding_from_record,
)
from .source import (
    MaterializedSource,
    RunRefSourceRefusal,
    canonical_source_request,
    materialize_source,
)
from .workspace import TreeManifest, freeze_tree


RUN_REF_EVIDENCE_MANIFEST_SCHEMA = "run_ref_evidence_manifest.v1"
RUN_REF_LIFECYCLE_EVENT_SCHEMA = "run_ref_lifecycle_event.v1"
_ATTEMPT_LEDGER_FILENAME = "run-ref-attempts.jsonl"
_REQUEST_FILENAME = "child-request.json"
_CHILD_RESULT_FILENAME = "child-result.json"
_WORKSPACE_DELTA_FILENAME = "workspace-delta.json"
_ACCOUNTING_FILENAME = "accounting.json"
_EVIDENCE_FILENAME = "evidence-manifest.json"
_DISPOSITION_FILENAME = "disposition.json"
_BASELINE_DIRECTORY = "baseline"
_SAFE_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CHILD_TEST_BOUNDARIES = frozenset({"mode_1_decode", "mode_2_compile"})
_RUN_REF_DURABLE_ACK_TOKEN = object()


class RunRefRuntimeError(ValueError):
    """Closed runtime refusal carrying a stable run-ref diagnostic code."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        machine_fields: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(code, str) or not code:
            raise ValueError("run_ref_runtime_error_code_invalid")
        if not isinstance(detail, str) or not detail:
            raise ValueError("run_ref_runtime_error_detail_invalid")
        if code.startswith("trial_") and machine_fields is None:
            raise ValueError("run_ref_runtime_error_machine_fields_required")
        if machine_fields is None:
            frozen_machine_fields = b"{}"
        else:
            if not isinstance(machine_fields, Mapping):
                raise TypeError("machine_fields must be a mapping or None")
            expected = {"rejected_value", "secondary_causes"}
            allowed = expected | {"compile_diagnostics"}
            if not expected.issubset(machine_fields) or not set(
                machine_fields
            ).issubset(allowed):
                raise ValueError("run_ref_runtime_error_machine_fields_invalid")
            secondary_causes = machine_fields.get("secondary_causes")
            if (
                not isinstance(secondary_causes, (tuple, list))
                or any(
                    not isinstance(cause, str) or not cause
                    for cause in secondary_causes
                )
            ):
                raise ValueError(
                    "run_ref_runtime_error_secondary_causes_invalid"
                )
            compile_diagnostics = machine_fields.get("compile_diagnostics")
            if compile_diagnostics is not None and not isinstance(
                compile_diagnostics,
                Mapping,
            ):
                raise ValueError(
                    "run_ref_runtime_error_compile_diagnostics_invalid"
                )
            try:
                frozen_machine_fields = canonical_json_bytes(
                    dict(machine_fields)
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "run_ref_runtime_error_machine_fields_not_json"
                ) from exc
        self.code = code
        self.detail = detail
        self._machine_fields_json = frozen_machine_fields
        super().__init__(f"{code}: {detail}")

    @property
    def machine_fields(self) -> dict[str, Any]:
        """Return a detached copy of immutable routing-authority fields."""

        value = json.loads(self._machine_fields_json)
        assert isinstance(value, dict)
        return value


class RunRefLifecycleDeadlineExceeded(RunRefRuntimeError):
    """The exact caller-owned lifecycle deadline elapsed between boundaries."""

    def __init__(self) -> None:
        super().__init__(
            "run_ref_child_launch_failed",
            "run_ref_lifecycle_deadline_exceeded",
        )


@dataclass(frozen=True, slots=True, init=False)
class RunRefLifecycleEvent:
    """One immutable, closed worker-to-caller lifecycle proposal."""

    sequence: int
    event_kind: str
    stage: str
    visit: RunRefVisitKey
    attempt_ordinal: int
    effect_instance_root: Path
    event_digest: str
    _payload_json: bytes

    @classmethod
    def build(
        cls,
        *,
        sequence: int,
        event_kind: str,
        stage: str,
        visit: RunRefVisitKey,
        attempt_ordinal: int,
        effect_instance_root: Path,
        payload: Mapping[str, Any],
    ) -> RunRefLifecycleEvent:
        if type(sequence) is not int or sequence < 1:
            raise ValueError("run-ref lifecycle sequence must be positive")
        expected_kind = (
            "allocation"
            if stage == "allocated"
            else "prepared"
            if stage == "completed_pending_parent_commit"
            else "progress"
        )
        if event_kind != expected_kind or stage not in {
            "allocated",
            "materialized",
            "setup_completed",
            "program_prepared",
            "launched",
            "child_completed",
            "delta_captured",
            "completed_pending_parent_commit",
        }:
            raise ValueError("run-ref lifecycle event kind/stage is invalid")
        if type(visit) is not RunRefVisitKey:
            raise TypeError("run-ref lifecycle visit must be RunRefVisitKey")
        if type(attempt_ordinal) is not int or attempt_ordinal < 1:
            raise ValueError("run-ref lifecycle attempt ordinal must be positive")
        root = _canonical_absolute(
            Path(effect_instance_root),
            field="effect_instance_root",
        )
        if not isinstance(payload, Mapping):
            raise TypeError("run-ref lifecycle payload must be a mapping")
        payload_json = canonical_json_bytes(dict(payload))
        payload_copy = json.loads(payload_json)
        if event_kind == "allocation":
            expected_payload = {"bindings"}
            binding_keys = set(RunRefAttemptBindings.__dataclass_fields__)
            bindings = payload_copy.get("bindings")
            if not isinstance(bindings, Mapping) or set(bindings) != binding_keys:
                raise ValueError("run-ref lifecycle allocation bindings are not closed")
        elif event_kind == "prepared":
            expected_payload = {
                "binding_updates",
                "result_envelope_digest",
                "artifact_projection_digest",
                "evidence_manifest_digest",
            }
            if payload_copy.get("binding_updates") != {}:
                raise ValueError("run-ref lifecycle prepared updates must be empty")
            for name in (
                "result_envelope_digest",
                "artifact_projection_digest",
                "evidence_manifest_digest",
            ):
                if (
                    not isinstance(payload_copy.get(name), str)
                    or _SHA256_RE.fullmatch(payload_copy[name]) is None
                ):
                    raise ValueError(
                        "run-ref lifecycle prepared digest is invalid"
                    )
        else:
            expected_payload = {"binding_updates"}
        if set(payload_copy) != expected_payload:
            raise ValueError("run-ref lifecycle payload is not closed")
        if event_kind == "progress":
            expected_updates = {
                "materialized": {"verified_git_tree_id"},
                "setup_completed": {
                    "setup_evidence_digest",
                    "post_setup_baseline_digest",
                },
                "program_prepared": {"program_preparation_digest"},
                "launched": {"child_launch_digest"},
                "child_completed": {
                    "child_terminal_state_digest",
                    "result_payload_digest",
                },
                "delta_captured": {
                    "workspace_delta_digest",
                    "accounting_digest",
                    "evidence_manifest_digest",
                },
            }[stage]
            updates = payload_copy.get("binding_updates")
            if not isinstance(updates, Mapping) or set(updates) != expected_updates:
                raise ValueError(
                    "run-ref lifecycle stage binding updates are not closed"
                )
        record = {
            "schema_version": RUN_REF_LIFECYCLE_EVENT_SCHEMA,
            "sequence": sequence,
            "event_kind": event_kind,
            "stage": stage,
            "visit": visit.record,
            "attempt_ordinal": attempt_ordinal,
            "effect_instance_root": root.as_posix(),
            "payload": payload_copy,
        }
        event = object.__new__(cls)
        for name, value in (
            ("sequence", sequence),
            ("event_kind", event_kind),
            ("stage", stage),
            ("visit", visit),
            ("attempt_ordinal", attempt_ordinal),
            ("effect_instance_root", root),
            ("event_digest", canonical_sha256(record)),
            ("_payload_json", payload_json),
        ):
            object.__setattr__(event, name, value)
        return event

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    @property
    def record(self) -> dict[str, Any]:
        return {
            "schema_version": RUN_REF_LIFECYCLE_EVENT_SCHEMA,
            "sequence": self.sequence,
            "event_kind": self.event_kind,
            "stage": self.stage,
            "visit": self.visit.record,
            "attempt_ordinal": self.attempt_ordinal,
            "effect_instance_root": self.effect_instance_root.as_posix(),
            "payload": self.payload,
            "event_digest": self.event_digest,
        }


@dataclass(frozen=True, slots=True)
class RunRefLifecycleAllocation:
    """Caller-selected exact E1 ordinal and effect-instance scope."""

    attempt_ordinal: int
    effect_instance_root: Path
    bindings: RunRefAttemptBindings
    effect_instance_digest: str | None = None
    expected_ledger_sequence: int = 1
    expected_previous_row_digest: str | None = None

    def __post_init__(self) -> None:
        if type(self.attempt_ordinal) is not int or self.attempt_ordinal < 1:
            raise ValueError("run-ref lifecycle attempt ordinal must be positive")
        root = _canonical_absolute(
            Path(self.effect_instance_root),
            field="effect_instance_root",
        )
        if type(self.bindings) is not RunRefAttemptBindings:
            raise TypeError("run-ref lifecycle bindings must be exact")
        if self.effect_instance_digest is not None and (
            not isinstance(self.effect_instance_digest, str)
            or _SHA256_RE.fullmatch(self.effect_instance_digest) is None
        ):
            raise ValueError("run-ref effect-instance digest is invalid")
        if type(self.expected_ledger_sequence) is not int or self.expected_ledger_sequence < 1:
            raise ValueError("run-ref expected ledger sequence is invalid")
        if self.expected_previous_row_digest is not None and (
            not isinstance(self.expected_previous_row_digest, str)
            or _SHA256_RE.fullmatch(self.expected_previous_row_digest) is None
        ):
            raise ValueError("run-ref expected previous row digest is invalid")
        if (self.expected_ledger_sequence == 1) != (
            self.expected_previous_row_digest is None
        ):
            raise ValueError("run-ref expected ledger head binding is invalid")
        object.__setattr__(self, "effect_instance_root", root)

    @property
    def ledger_path(self) -> Path:
        return self.effect_instance_root / _ATTEMPT_LEDGER_FILENAME


@dataclass(frozen=True, slots=True)
class RunRefLifecycleAcknowledgement:
    """Exact caller acknowledgement for one lifecycle event."""

    sequence: int
    stage: str
    event_digest: str
    authority: RunRefAttemptRecord
    _durability_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("run-ref lifecycle acknowledgement sequence is invalid")
        if not isinstance(self.stage, str) or not self.stage:
            raise ValueError("run-ref lifecycle acknowledgement stage is invalid")
        if not isinstance(self.event_digest, str) or _SHA256_RE.fullmatch(
            self.event_digest
        ) is None:
            raise ValueError("run-ref lifecycle acknowledgement digest is invalid")
        if type(self.authority) is not RunRefAttemptRecord:
            raise TypeError("run-ref lifecycle acknowledgement authority is invalid")
        if self._durability_token is not _RUN_REF_DURABLE_ACK_TOKEN:
            raise ValueError("run-ref lifecycle acknowledgement is not durable")

    @property
    def authority_digest(self) -> str:
        return self.authority.row_digest

    @classmethod
    def _for_durable_row(
        cls,
        event: RunRefLifecycleEvent,
        *,
        authority: RunRefAttemptRecord,
    ) -> RunRefLifecycleAcknowledgement:
        if type(event) is not RunRefLifecycleEvent:
            raise TypeError("acknowledgement event must be RunRefLifecycleEvent")
        return cls(
            sequence=event.sequence,
            stage=event.stage,
            event_digest=event.event_digest,
            authority=authority,
            _durability_token=_RUN_REF_DURABLE_ACK_TOKEN,
        )


@dataclass(frozen=True, slots=True)
class ParentBundleOrphanPreimage:
    """Exact parent output-bundle bytes observed before attempt recovery."""

    path: Path
    sha256: str
    byte_size: int

    def __post_init__(self) -> None:
        try:
            path = _canonical_absolute(
                Path(self.path),
                field="parent_bundle_orphan_preimage.path",
            )
        except TypeError as exc:
            raise RunRefRuntimeError(
                "run_ref_ledger_invalid",
                "parent_bundle_orphan_preimage_path_invalid",
            ) from exc
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(self.sha256):
            raise RunRefRuntimeError(
                "run_ref_ledger_invalid",
                "parent_bundle_orphan_preimage_sha256_invalid",
            )
        if type(self.byte_size) is not int or self.byte_size < 0:
            raise RunRefRuntimeError(
                "run_ref_ledger_invalid",
                "parent_bundle_orphan_preimage_byte_size_invalid",
            )
        object.__setattr__(self, "path", path)

    @property
    def record(self) -> dict[str, Any]:
        return {
            "path": self.path.as_posix(),
            "sha256": self.sha256,
            "byte_size": self.byte_size,
        }


@dataclass(frozen=True, slots=True)
class _RunRefRuntimeRequestPaths:
    parent_workspace: Path
    parent_run_root: Path
    run_ref_root: Path
    capsule_dir: Path | None


@dataclass(frozen=True, slots=True)
class RunRefRuntimeRequest:
    """All parent-owned authority needed to execute one exact run-ref visit."""

    step_config: RunRefStepConfig
    visit: RunRefVisitKey
    parent_state: Mapping[str, Any]
    parent_workspace: Path
    parent_run_root: Path
    run_ref_root: Path
    capsule_dir: Path | None = None
    parent_bundle_orphan_preimage: ParentBundleOrphanPreimage | None = None

    def __post_init__(self) -> None:
        paths = _validate_run_ref_runtime_request_authority(
            step_config=self.step_config,
            visit=self.visit,
            parent_state=self.parent_state,
            parent_workspace=self.parent_workspace,
            parent_run_root=self.parent_run_root,
            run_ref_root=self.run_ref_root,
            capsule_dir=self.capsule_dir,
            parent_bundle_orphan_preimage=self.parent_bundle_orphan_preimage,
            parent_run_root_must_exist=True,
        )
        object.__setattr__(self, "parent_workspace", paths.parent_workspace)
        object.__setattr__(self, "parent_run_root", paths.parent_run_root)
        object.__setattr__(self, "run_ref_root", paths.run_ref_root)
        object.__setattr__(self, "capsule_dir", paths.capsule_dir)

    @property
    def ledger_path(self) -> Path:
        return self.parent_run_root / _ATTEMPT_LEDGER_FILENAME


@dataclass(frozen=True, slots=True)
class RunRefChildLaunch:
    """Argument-bounded private child launch request."""

    mode: str
    request_path: Path
    request_document: Mapping[str, Any]
    workspace: Path
    child_run_id: str


@dataclass(frozen=True, slots=True)
class RunRefChildProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    duration_ms: int

    def __post_init__(self) -> None:
        if type(self.returncode) is not int:
            raise TypeError("child returncode must be an integer")
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise TypeError("child stdout and stderr must be bytes")
        if type(self.duration_ms) is not int or self.duration_ms < 0:
            raise ValueError("child duration_ms must be a non-negative integer")


def _default_child_launcher(launch: RunRefChildLaunch) -> RunRefChildProcessResult:
    started_ns = time.monotonic_ns()
    selector = "--request" if launch.mode == "bundle" else "--path-request"
    process_env = dict(os.environ)
    process_env.pop("PYTHONPATH", None)
    controller_root = Path(__file__).resolve(strict=True).parents[3]
    package_root = controller_root / "orchestrator"
    if not package_root.is_dir():
        raise RunRefRuntimeError(
            "run_ref_child_launch_failed",
            "controller_package_root_invalid",
        )
    bootstrap = (
        "import runpy,sys;"
        "controller_root=sys.argv.pop(1);"
        "sys.path.insert(0,controller_root);"
        "sys.argv[0]='orchestrator.workflow.run_ref.child';"
        "runpy.run_module('orchestrator.workflow.run_ref.child',"
        "run_name='__main__')"
    )
    completed = subprocess.run(
        (
            sys.executable,
            "-I",
            "-c",
            bootstrap,
            controller_root.as_posix(),
            selector,
            launch.request_path.as_posix(),
        ),
        cwd=launch.workspace,
        env=process_env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    return RunRefChildProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=(time.monotonic_ns() - started_ns) // 1_000_000,
    )


def _default_discard_workspace(workspace: Path) -> None:
    if not os.path.lexists(workspace):
        return
    identity = workspace.lstat()
    if not stat.S_ISDIR(identity.st_mode) or stat.S_ISLNK(identity.st_mode):
        raise OSError("bound run-ref workspace is not a directory")
    shutil.rmtree(workspace)


def _no_crash(_boundary: str) -> None:
    return None


@dataclass(frozen=True, slots=True)
class RunRefRuntimeDependencies:
    """Narrow effect seams used by the parent runtime and crash fixtures."""

    materialize_source: Callable[..., MaterializedSource] = materialize_source
    launch_child: Callable[[RunRefChildLaunch], RunRefChildProcessResult] = (
        _default_child_launcher
    )
    discard_workspace: Callable[[Path], None] = _default_discard_workspace
    crash_hook: Callable[[str], None] = _no_crash
    monotonic_ns: Callable[[], int] = time.monotonic_ns
    child_test_boundary: str | None = None

    def __post_init__(self) -> None:
        if (
            self.child_test_boundary is not None
            and self.child_test_boundary not in _CHILD_TEST_BOUNDARIES
        ):
            raise ValueError("child_test_boundary_invalid")


@dataclass(frozen=True, slots=True)
class PreparedRunRefSettlement:
    """Pending ledger authority ready for the caller's atomic state commit."""

    envelope: Mapping[str, Any]
    artifacts: Mapping[str, Any]
    settled_result: SettledRunRefResultBinding
    ledger_path: Path
    evidence_manifest_path: Path


@dataclass(frozen=True, slots=True)
class RunRefExecutionResult:
    """A fully validated committed or reconciled run-ref result."""

    envelope: Mapping[str, Any]
    artifacts: Mapping[str, Any]
    settled_result: SettledRunRefResultBinding
    committed_row_digest: str
    reused: bool


def _canonical_absolute(path: Path, *, field: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise RunRefRuntimeError("run_ref_ledger_invalid", f"{field}_not_absolute")
    resolved = candidate.resolve(strict=False)
    if resolved != candidate:
        raise RunRefRuntimeError("run_ref_ledger_invalid", f"{field}_not_canonical")
    return resolved


def _canonical_directory(path: Path, *, field: str) -> Path:
    resolved = _canonical_absolute(Path(path), field=field)
    if not resolved.is_dir():
        raise RunRefRuntimeError("run_ref_ledger_invalid", f"{field}_not_directory")
    return resolved


def _validate_run_ref_runtime_request_authority(
    *,
    step_config: RunRefStepConfig,
    visit: RunRefVisitKey,
    parent_state: Mapping[str, Any],
    parent_workspace: Path,
    parent_run_root: Path,
    run_ref_root: Path,
    capsule_dir: Path | None,
    parent_bundle_orphan_preimage: ParentBundleOrphanPreimage | None,
    parent_run_root_must_exist: bool,
) -> _RunRefRuntimeRequestPaths:
    if type(step_config) is not RunRefStepConfig:
        raise TypeError("step_config must be an exact RunRefStepConfig")
    if type(visit) is not RunRefVisitKey:
        raise TypeError("visit must be an exact RunRefVisitKey")
    if not isinstance(parent_state, Mapping):
        raise TypeError("parent_state must be a mapping")
    if (
        parent_bundle_orphan_preimage is not None
        and type(parent_bundle_orphan_preimage) is not ParentBundleOrphanPreimage
    ):
        raise TypeError(
            "parent_bundle_orphan_preimage must be an exact "
            "ParentBundleOrphanPreimage or None"
        )
    normalized_workspace = _canonical_directory(
        parent_workspace,
        field="parent_workspace",
    )
    normalized_parent_root = _canonical_absolute(
        Path(parent_run_root),
        field="parent_run_root",
    )
    if parent_run_root_must_exist:
        if not normalized_parent_root.is_dir():
            raise RunRefRuntimeError(
                "run_ref_ledger_invalid",
                "parent_run_root_not_directory",
            )
    elif (
        os.path.lexists(normalized_parent_root)
        and not normalized_parent_root.is_dir()
    ):
        raise RunRefRuntimeError(
            "run_ref_ledger_invalid",
            "parent_run_root_not_directory",
        )
    normalized_run_ref_root = _canonical_absolute(
        run_ref_root,
        field="run_ref_root",
    )
    for candidate, root in (
        (normalized_run_ref_root, normalized_workspace),
        (normalized_workspace, normalized_run_ref_root),
    ):
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        raise RunRefRuntimeError(
            "run_ref_ledger_invalid",
            "run_ref_root_overlaps_parent_workspace",
        )
    if isinstance(step_config.run_ref.program, BundleProgram):
        if step_config.capsule_binding is None or capsule_dir is None:
            raise RunRefRuntimeError(
                "run_ref_capsule_invalid",
                "mode_1_capsule_binding_missing",
            )
        normalized_capsule = _canonical_directory(
            capsule_dir,
            field="capsule_dir",
        )
    else:
        if step_config.capsule_binding is not None or capsule_dir is not None:
            raise RunRefRuntimeError(
                "run_ref_child_launch_failed",
                "mode_2_capsule_binding_forbidden",
            )
        normalized_capsule = None
    return _RunRefRuntimeRequestPaths(
        parent_workspace=normalized_workspace,
        parent_run_root=normalized_parent_root,
        run_ref_root=normalized_run_ref_root,
        capsule_dir=normalized_capsule,
    )


def preflight_run_ref_runtime_request(
    *,
    step_config: RunRefStepConfig,
    visit: RunRefVisitKey,
    parent_state: Mapping[str, Any],
    parent_workspace: Path,
    prospective_parent_run_root: Path,
    run_ref_root: Path,
    capsule_dir: Path | None,
    parent_bundle_orphan_preimage: ParentBundleOrphanPreimage | None = None,
) -> None:
    """Validate E1 request authority before a nested parent root exists."""

    _validate_run_ref_runtime_request_authority(
        step_config=step_config,
        visit=visit,
        parent_state=parent_state,
        parent_workspace=parent_workspace,
        parent_run_root=prospective_parent_run_root,
        run_ref_root=run_ref_root,
        capsule_dir=capsule_dir,
        parent_bundle_orphan_preimage=parent_bundle_orphan_preimage,
        parent_run_root_must_exist=False,
    )


def build_run_ref_accounting(
    *,
    child_run_id: str,
    attempt_ordinal: int,
    terminal_status: str,
    elapsed_ms: int,
    setup_ms: int,
    compile_ms: int,
    provider_attempts: Any = "UNKNOWN",
    token_usage: Any = "UNKNOWN",
    cost: Any = "UNKNOWN",
) -> dict[str, Any]:
    """Build the fixed accounting carrier without inventing unavailable data."""

    if not isinstance(child_run_id, str) or not child_run_id:
        raise RunRefRuntimeError("run_ref_child_result_invalid", "child_run_id_invalid")
    if not isinstance(terminal_status, str) or not terminal_status:
        raise RunRefRuntimeError("run_ref_child_result_invalid", "terminal_status_invalid")
    integers = (attempt_ordinal, elapsed_ms, setup_ms, compile_ms)
    if any(type(value) is not int or value < 0 for value in integers):
        raise RunRefRuntimeError("run_ref_child_result_invalid", "accounting_invalid")
    return {
        "child_run_id": child_run_id,
        "attempt_ordinal": attempt_ordinal,
        "terminal_status": terminal_status,
        "elapsed_ms": elapsed_ms,
        "setup_ms": setup_ms,
        "compile_ms": compile_ms,
        "provider_attempts": _json_value(
            provider_attempts,
            context="provider_attempts_invalid",
        ),
        "token_usage": _json_value(token_usage, context="token_usage_invalid"),
        "cost": _json_value(cost, context="cost_invalid"),
    }


def declared_artifacts_from_value(
    value: Any,
    descriptor: Mapping[str, Any],
) -> tuple[DeclaredArtifact, ...]:
    """Derive the complete deterministic artifact catalog from path leaves."""

    rows: list[DeclaredArtifact] = []

    def visit(item: Any, shape: Mapping[str, Any], path: str) -> None:
        kind = shape.get("kind")
        if kind == "path":
            rows.append(DeclaredArtifact(path, item))
            return
        if kind == "optional":
            if item is not None:
                visit(item, shape["item"], path)
            return
        if kind == "list":
            for index, child in enumerate(item):
                visit(child, shape["item"], f"{path}[{index}]")
            return
        if kind == "map":
            for key in sorted(item, key=lambda candidate: candidate.encode("utf-8")):
                visit(item[key], shape["value"], f"{path}[{key}]")
            return
        if kind == "record":
            for field in shape["fields"]:
                name = field["name"]
                visit(item[name], field["type"], f"{path}.{name}")
            return
        if kind == "union":
            selected = next(
                variant
                for variant in shape["variants"]
                if variant["name"] == item["variant"]
            )
            for field in selected["fields"]:
                name = field["name"]
                visit(item[name], field["type"], f"{path}.{name}")

    visit(value, descriptor, "value")
    return tuple(sorted(rows, key=lambda row: (row.name.encode("utf-8"), row.path.encode("utf-8"))))


def flatten_run_ref_result_artifacts(
    value: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> dict[str, Any]:
    """Project record leaves exactly like the compiler-owned output bundle."""

    result: dict[str, Any] = {}

    def visit(item: Any, shape: Mapping[str, Any], path: tuple[str, ...]) -> None:
        if shape.get("kind") == "record":
            if not isinstance(item, Mapping):
                raise RunRefRuntimeError(
                    "run_ref_child_result_invalid",
                    "result_envelope_invalid",
                )
            fields = shape.get("fields")
            if not isinstance(fields, list):
                raise RunRefRuntimeError(
                    "run_ref_child_result_invalid",
                    "result_descriptor_invalid",
                )
            expected_names = {
                field.get("name")
                for field in fields
                if isinstance(field, Mapping)
            }
            if None in expected_names or set(item) != expected_names:
                raise RunRefRuntimeError(
                    "run_ref_child_result_invalid",
                    "result_envelope_invalid",
                )
            for field in fields:
                name = field["name"]
                field_type = field.get("type")
                if not isinstance(field_type, Mapping):
                    raise RunRefRuntimeError(
                        "run_ref_child_result_invalid",
                        "result_descriptor_invalid",
                    )
                visit(item[name], field_type, (*path, name))
            return
        name = "__".join(path)
        if not name or name in result:
            raise RunRefRuntimeError(
                "run_ref_child_result_invalid",
                "result_projection_invalid",
            )
        result[name] = item

    visit(value, descriptor, ())
    return result


def _resolve_binding(
    binding: InputBinding,
    *,
    parent_state: Mapping[str, Any],
    resolver: ReferenceResolver,
) -> Any:
    if isinstance(binding, LiteralBinding):
        return binding.value
    if isinstance(binding, ReferenceBinding):
        try:
            return resolver.resolve(binding.reference, dict(parent_state)).value
        except (ReferenceResolutionError, TypeError, ValueError) as exc:
            raise RunRefRuntimeError(
                "run_ref_child_launch_failed",
                "input_reference_unavailable",
            ) from exc
    if isinstance(binding, ArrayBinding):
        return [
            _resolve_binding(item, parent_state=parent_state, resolver=resolver)
            for item in binding.items
        ]
    if isinstance(binding, ObjectBinding):
        return {
            name: _resolve_binding(
                item,
                parent_state=parent_state,
                resolver=resolver,
            )
            for name, item in binding.entries
        }
    raise RunRefRuntimeError(
        "run_ref_child_launch_failed",
        "input_binding_invalid",
    )


def _canonical_relative_path(value: Any, *, context: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise RunRefRuntimeError("run_ref_child_result_invalid", context)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RunRefRuntimeError("run_ref_child_result_invalid", context)
    return path


def _path_is_under(path: PurePosixPath, root: PurePosixPath) -> bool:
    return path.parts[: len(root.parts)] == root.parts


def _path_content_digest(source: Path, relative: PurePosixPath) -> str:
    if not os.path.lexists(source):
        return hashlib.sha256(
            canonical_json_bytes({"absent": relative.as_posix()})
        ).hexdigest()
    identity = source.lstat()
    if stat.S_ISREG(identity.st_mode):
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
    if stat.S_ISDIR(identity.st_mode):
        return freeze_tree(source).digest.removeprefix("sha256:")
    if stat.S_ISLNK(identity.st_mode):
        target = os.readlink(source).encode("utf-8")
        return hashlib.sha256(target).hexdigest()
    raise RunRefRuntimeError(
        "run_ref_child_result_invalid",
        "input_path_special_entry",
    )


def _copy_path_value(
    value: Any,
    descriptor: Mapping[str, Any],
    *,
    parent_workspace: Path,
    child_workspace: Path,
    input_name: str,
    traversal: tuple[str, ...],
) -> str:
    relative = _canonical_relative_path(value, context="input_path_invalid")
    under = _canonical_relative_path(
        descriptor.get("under"),
        context="input_path_contract_invalid",
    )
    if not _path_is_under(relative, under):
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "input_path_outside_declared_root",
        )
    parent_root = Path(parent_workspace).resolve(strict=True)
    child_root = Path(child_workspace).resolve(strict=True)
    source = parent_root.joinpath(*relative.parts)
    try:
        source.resolve(strict=False).relative_to(parent_root)
    except ValueError as exc:
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "input_path_outside_parent_workspace",
        ) from exc
    exists = os.path.lexists(source)
    if descriptor.get("must_exist_target") is True and not exists:
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "input_path_missing",
        )
    content_digest = _path_content_digest(source, relative)
    location_digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "input": input_name,
                "traversal": list(traversal),
                "source": relative.as_posix(),
                "content": content_digest,
            }
        )
    ).hexdigest()
    leaf = relative.name or "path"
    destination_relative = (
        under
        / ".run-ref-inputs"
        / input_name
        / location_digest
        / leaf
    )
    destination = child_root.joinpath(*destination_relative.parts)
    if os.path.lexists(destination):
        raise RunRefRuntimeError(
            "run_ref_child_launch_failed",
            "input_path_destination_preexisting",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if exists:
        identity = source.lstat()
        if stat.S_ISDIR(identity.st_mode):
            shutil.copytree(source, destination, symlinks=True)
        elif stat.S_ISREG(identity.st_mode):
            shutil.copy2(source, destination, follow_symlinks=False)
        elif stat.S_ISLNK(identity.st_mode):
            destination.symlink_to(os.readlink(source))
        else:
            raise RunRefRuntimeError(
                "run_ref_child_result_invalid",
                "input_path_special_entry",
            )
    return destination_relative.as_posix()


def _validate_local_path_value(
    value: Any,
    descriptor: Mapping[str, Any],
    *,
    workspace: Path,
) -> str:
    relative = _canonical_relative_path(value, context="result_path_invalid")
    under = _canonical_relative_path(
        descriptor.get("under"),
        context="result_path_contract_invalid",
    )
    if not _path_is_under(relative, under):
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "result_path_outside_declared_root",
        )
    root = Path(workspace).resolve(strict=True)
    target = root.joinpath(*relative.parts)
    try:
        target.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "result_path_outside_child_workspace",
        ) from exc
    if descriptor.get("must_exist_target") is True and not os.path.lexists(target):
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "result_path_missing",
        )
    return relative.as_posix()


def _json_value(value: Any, *, context: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RunRefRuntimeError("run_ref_child_result_invalid", context)
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise RunRefRuntimeError("run_ref_child_result_invalid", context)
        return {key: _json_value(item, context=context) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item, context=context) for item in value]
    raise RunRefRuntimeError("run_ref_child_result_invalid", context)


def _coerce_transport_value(
    value: Any,
    descriptor: Mapping[str, Any],
    *,
    parent_workspace: Path,
    child_workspace: Path,
    input_name: str,
    traversal: tuple[str, ...] = (),
    copy_paths: bool = True,
) -> Any:
    kind = descriptor.get("kind")
    if kind == "primitive":
        name = descriptor.get("name")
        valid = (
            (name in {"String", "Symbol", "RunId"} and isinstance(value, str))
            or (name == "Bool" and type(value) is bool)
            or (name == "Int" and type(value) is int)
            or (
                name == "Float"
                and type(value) in {int, float}
                and not isinstance(value, bool)
                and math.isfinite(float(value))
            )
        )
        if name == "Value":
            return _json_value(value, context="input_value_invalid")
        if not valid:
            raise RunRefRuntimeError(
                "run_ref_child_result_invalid",
                "input_type_mismatch",
            )
        return float(value) if name == "Float" else value
    if kind == "enum":
        if not isinstance(value, str) or value not in descriptor.get("allowed", ()):
            raise RunRefRuntimeError("run_ref_child_result_invalid", "input_type_mismatch")
        return value
    if kind == "path":
        if not copy_paths:
            return _validate_local_path_value(
                value,
                descriptor,
                workspace=child_workspace,
            )
        return _copy_path_value(
            value,
            descriptor,
            parent_workspace=parent_workspace,
            child_workspace=child_workspace,
            input_name=input_name,
            traversal=traversal,
        )
    if kind == "optional":
        if value is None:
            return None
        return _coerce_transport_value(
            value,
            descriptor["item"],
            parent_workspace=parent_workspace,
            child_workspace=child_workspace,
            input_name=input_name,
            traversal=(*traversal, "optional"),
            copy_paths=copy_paths,
        )
    if kind == "list":
        if not isinstance(value, list):
            raise RunRefRuntimeError("run_ref_child_result_invalid", "input_type_mismatch")
        return [
            _coerce_transport_value(
                item,
                descriptor["item"],
                parent_workspace=parent_workspace,
                child_workspace=child_workspace,
                input_name=input_name,
                traversal=(*traversal, str(index)),
                copy_paths=copy_paths,
            )
            for index, item in enumerate(value)
        ]
    if kind == "map":
        if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
            raise RunRefRuntimeError("run_ref_child_result_invalid", "input_type_mismatch")
        return {
            key: _coerce_transport_value(
                item,
                descriptor["value"],
                parent_workspace=parent_workspace,
                child_workspace=child_workspace,
                input_name=input_name,
                traversal=(*traversal, key),
                copy_paths=copy_paths,
            )
            for key, item in value.items()
        }
    if kind == "record":
        fields = descriptor.get("fields")
        expected = {
            field["name"]: field["type"]
            for field in fields
            if isinstance(field, Mapping)
        } if isinstance(fields, list) else {}
        if not isinstance(value, Mapping) or set(value) != set(expected):
            raise RunRefRuntimeError("run_ref_child_result_invalid", "input_type_mismatch")
        return {
            name: _coerce_transport_value(
                value[name],
                field_descriptor,
                parent_workspace=parent_workspace,
                child_workspace=child_workspace,
                input_name=input_name,
                traversal=(*traversal, name),
                copy_paths=copy_paths,
            )
            for name, field_descriptor in expected.items()
        }
    if kind == "union":
        if not isinstance(value, Mapping) or not isinstance(value.get("variant"), str):
            raise RunRefRuntimeError("run_ref_child_result_invalid", "input_type_mismatch")
        variants = descriptor.get("variants")
        selected = next(
            (
                variant
                for variant in variants
                if isinstance(variant, Mapping)
                and variant.get("name") == value["variant"]
            ),
            None,
        ) if isinstance(variants, list) else None
        if not isinstance(selected, Mapping):
            raise RunRefRuntimeError("run_ref_child_result_invalid", "input_type_mismatch")
        fields = selected.get("fields")
        expected = {
            field["name"]: field["type"]
            for field in fields
            if isinstance(field, Mapping)
        } if isinstance(fields, list) else {}
        if set(value) != {"variant", *expected}:
            raise RunRefRuntimeError("run_ref_child_result_invalid", "input_type_mismatch")
        return {
            "variant": value["variant"],
            **{
                name: _coerce_transport_value(
                    value[name],
                    field_descriptor,
                    parent_workspace=parent_workspace,
                    child_workspace=child_workspace,
                    input_name=input_name,
                    traversal=(*traversal, value["variant"], name),
                    copy_paths=copy_paths,
                )
                for name, field_descriptor in expected.items()
            },
        }
    raise RunRefRuntimeError("run_ref_child_result_invalid", "input_type_mismatch")


def resolve_run_ref_inputs(
    rows: tuple[RunRefInput, ...],
    *,
    parent_state: Mapping[str, Any],
    parent_workspace: Path,
    child_workspace: Path,
) -> dict[str, Any]:
    """Resolve and validate one ordered run-ref input contract."""

    if not isinstance(rows, tuple) or any(type(row) is not RunRefInput for row in rows):
        raise TypeError("run-ref inputs must be an exact RunRefInput tuple")
    resolver = ReferenceResolver()
    resolved: dict[str, Any] = {}
    for row in rows:
        raw = _resolve_binding(
            row.binding,
            parent_state=parent_state,
            resolver=resolver,
        )
        resolved[row.name] = _coerce_transport_value(
            raw,
            row.type_descriptor,
            parent_workspace=parent_workspace,
            child_workspace=child_workspace,
            input_name=row.name,
        )
    return resolved


def extract_run_ref_value(
    workflow_outputs: Mapping[str, Any],
    value_descriptor: Mapping[str, Any],
    *,
    workspace: Path,
) -> Any:
    """Reconstruct and validate one direct language return from child outputs."""

    if not isinstance(workflow_outputs, Mapping):
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "workflow_outputs_invalid",
        )
    consumed: set[str] = set()

    def key_for(path: tuple[str, ...]) -> str:
        return "__result__" if not path else f"return__{'__'.join(path)}"

    def build(descriptor: Mapping[str, Any], path: tuple[str, ...]) -> Any:
        kind = descriptor.get("kind")
        if kind == "record":
            fields = descriptor.get("fields")
            if not isinstance(fields, list):
                raise RunRefRuntimeError(
                    "run_ref_child_result_invalid",
                    "result_descriptor_invalid",
                )
            result: dict[str, Any] = {}
            for field in fields:
                if not isinstance(field, Mapping):
                    raise RunRefRuntimeError(
                        "run_ref_child_result_invalid",
                        "result_descriptor_invalid",
                    )
                name = field.get("name")
                field_type = field.get("type")
                if not isinstance(name, str) or not isinstance(field_type, Mapping):
                    raise RunRefRuntimeError(
                        "run_ref_child_result_invalid",
                        "result_descriptor_invalid",
                    )
                result[name] = build(field_type, (*path, name))
            return result
        if kind == "union":
            variant_key = key_for((*path, "variant"))
            variant_name = workflow_outputs.get(variant_key)
            if not isinstance(variant_name, str):
                raise RunRefRuntimeError(
                    "run_ref_child_result_invalid",
                    "result_union_variant_missing",
                )
            consumed.add(variant_key)
            variants = descriptor.get("variants")
            selected = next(
                (
                    variant
                    for variant in variants
                    if isinstance(variant, Mapping)
                    and variant.get("name") == variant_name
                ),
                None,
            ) if isinstance(variants, list) else None
            if not isinstance(selected, Mapping):
                raise RunRefRuntimeError(
                    "run_ref_child_result_invalid",
                    "result_union_variant_invalid",
                )
            result = {"variant": variant_name}
            fields = selected.get("fields")
            if not isinstance(fields, list):
                raise RunRefRuntimeError(
                    "run_ref_child_result_invalid",
                    "result_descriptor_invalid",
                )
            for field in fields:
                if not isinstance(field, Mapping):
                    raise RunRefRuntimeError(
                        "run_ref_child_result_invalid",
                        "result_descriptor_invalid",
                    )
                name = field.get("name")
                field_type = field.get("type")
                if not isinstance(name, str) or not isinstance(field_type, Mapping):
                    raise RunRefRuntimeError(
                        "run_ref_child_result_invalid",
                        "result_descriptor_invalid",
                    )
                result[name] = build(field_type, (*path, name))
            return result
        output_key = key_for(path)
        if output_key not in workflow_outputs:
            raise RunRefRuntimeError(
                "run_ref_child_result_invalid",
                "workflow_output_missing",
            )
        consumed.add(output_key)
        return _coerce_transport_value(
            workflow_outputs[output_key],
            descriptor,
            parent_workspace=workspace,
            child_workspace=workspace,
            input_name="result",
            traversal=path,
            copy_paths=False,
        )

    value = build(value_descriptor, ())
    if set(workflow_outputs) != consumed:
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "workflow_outputs_extra",
        )
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _decode_json(payload: bytes, *, canonical: bool, label: str) -> Any:
    framed = payload
    if canonical:
        if not payload.endswith(b"\n") or payload == b"\n":
            raise RunRefRuntimeError(
                "run_ref_evidence_invalid",
                f"{label}_not_canonical",
            )
        framed = payload[:-1]
    try:
        value = json.loads(
            framed.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            f"{label}_invalid_json",
        ) from exc
    if canonical and canonical_json_bytes(value) != framed:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            f"{label}_not_canonical",
        )
    return value


def _read_canonical_document(path: Path, *, label: str) -> Any:
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            f"{label}_unreadable",
        ) from exc
    return _decode_json(payload, canonical=True, label=label)


def _write_canonical_document(path: Path, value: Mapping[str, Any]) -> None:
    durable_atomic_write(Path(path), canonical_json_bytes(dict(value)) + b"\n")


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def resolve_run_ref_parent_input_values_for_config(
    step_config: RunRefStepConfig,
    parent_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve E1 parent values before a filesystem-bound request is built."""

    if type(step_config) is not RunRefStepConfig:
        raise TypeError("step_config must be an exact RunRefStepConfig")
    if not isinstance(parent_state, Mapping):
        raise TypeError("parent_state must be a mapping")
    resolver = ReferenceResolver()
    result: dict[str, Any] = {}
    for row in step_config.run_ref.inputs:
        raw = _resolve_binding(
            row.binding,
            parent_state=parent_state,
            resolver=resolver,
        )
        result[row.name] = _json_value(raw, context="input_value_invalid")
    return result


def _resolved_parent_input_values(request: RunRefRuntimeRequest) -> dict[str, Any]:
    return resolve_run_ref_parent_input_values_for_config(
        request.step_config,
        request.parent_state,
    )


def resolve_run_ref_parent_input_values(
    request: RunRefRuntimeRequest,
) -> dict[str, Any]:
    """Resolve the exact parent values used by E1 identity without effects."""

    if type(request) is not RunRefRuntimeRequest:
        raise TypeError("request must be an exact RunRefRuntimeRequest")
    return _resolved_parent_input_values(request)


def _input_digest(
    request: RunRefRuntimeRequest,
    parent_values: Mapping[str, Any],
) -> str:
    return canonical_sha256(
        {
            "schema_version": "run_ref_input_binding.v1",
            "inputs": [row.record for row in request.step_config.run_ref.inputs],
            "resolved_parent_values": dict(parent_values),
        }
    )


def _policy_digest(request: RunRefRuntimeRequest) -> str:
    source = canonical_source_request(request.step_config.run_ref.source)
    program = request.step_config.run_ref.program
    return canonical_sha256(
        {
            "schema_version": "run_ref_runtime_policy.v1",
            "authored_setup": source["authored_setup"],
            "environment": (
                program.environment if isinstance(program, PathProgram) else None
            ),
            "reuse_policy": "reuse_validated_run_ref_result",
        }
    )


def _safe_workspace_segment(value: str, *, fallback: str) -> str:
    if _SAFE_SEGMENT_RE.fullmatch(value) is not None:
        return value
    return f"{fallback}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _workspace_for_ordinal(
    request: RunRefRuntimeRequest,
    attempt_ordinal: int,
    *,
    effect_instance_digest: str | None = None,
) -> Path:
    parent_segment = _safe_workspace_segment(
        request.visit.parent_run_id,
        fallback="parent",
    )
    step_segment = _safe_workspace_segment(
        request.visit.step_id,
        fallback="step",
    )
    visit_segment = "visit-" + canonical_sha256(
        {
            "schema_version": "run_ref_workspace_visit_identity.v1",
            "visit": request.visit.record,
        }
    ).removeprefix("sha256:")
    workspace_root = request.run_ref_root
    if effect_instance_digest is not None:
        if _SHA256_RE.fullmatch(effect_instance_digest) is None:
            raise RunRefRuntimeError(
                "run_ref_ledger_invalid",
                "effect_instance_digest_invalid",
            )
        workspace_root = (
            workspace_root
            / "effect-instances"
            / effect_instance_digest.removeprefix("sha256:")
        )
    return (
        workspace_root
        / "runs"
        / parent_segment
        / step_segment
        / visit_segment
        / str(attempt_ordinal)
        / "workspace"
    )


def _child_run_id(
    request: RunRefRuntimeRequest,
    attempt_ordinal: int,
    *,
    effect_instance_digest: str | None = None,
) -> str:
    identity = {
        "schema_version": "run_ref_child_run_identity.v1",
        "visit": request.visit.record,
        "attempt_ordinal": attempt_ordinal,
        "step_config_digest": request.step_config.step_config_digest,
    }
    if effect_instance_digest is not None:
        identity = {
            **identity,
            "schema_version": "run_ref_child_run_identity.v2",
            "effect_instance_digest": effect_instance_digest,
        }
    digest = canonical_sha256(identity).removeprefix("sha256:")
    return f"run-ref-{digest[:40]}"


def _attempt_bindings(
    request: RunRefRuntimeRequest,
    *,
    attempt_ordinal: int,
    workspace: Path,
    parent_values: Mapping[str, Any],
    effect_instance_digest: str | None = None,
) -> RunRefAttemptBindings:
    static = request.step_config.run_ref
    program = static.program
    capsule_or_compiler_digest = (
        request.step_config.capsule_binding.capsule_digest
        if request.step_config.capsule_binding is not None
        else static.compiler_runtime_identity_digest
    )
    return RunRefAttemptBindings(
        run_ref_root=request.run_ref_root,
        workspace_path=workspace,
        source_digest=canonical_sha256(canonical_source_request(static.source)),
        program_digest=canonical_sha256(program.record),
        input_digest=_input_digest(request, parent_values),
        policy_digest=_policy_digest(request),
        step_config_digest=request.step_config.step_config_digest,
        capsule_or_compiler_digest=capsule_or_compiler_digest,
        child_run_id=_child_run_id(
            request,
            attempt_ordinal,
            effect_instance_digest=effect_instance_digest,
        ),
        result_contract_digest=static.result_digest,
    )


def select_run_ref_lifecycle_allocation(
    request: RunRefRuntimeRequest,
    *,
    effect_instance_root: Path | None = None,
    effect_instance_digest: str | None = None,
) -> RunRefLifecycleAllocation:
    """Caller-side selection of one exact fresh ordinal and binding set."""

    if type(request) is not RunRefRuntimeRequest:
        raise TypeError("request must be an exact RunRefRuntimeRequest")
    if (effect_instance_root is None) != (effect_instance_digest is None):
        raise ValueError(
            "effect_instance_root and effect_instance_digest must be supplied together"
        )
    root = _canonical_absolute(
        effect_instance_root or request.parent_run_root,
        field="effect_instance_root",
    )
    ledger_path = root / _ATTEMPT_LEDGER_FILENAME
    ledger = load_attempt_ledger(ledger_path)
    matching = [row for row in ledger.rows if row.visit == request.visit]
    ordinal = max((row.attempt_ordinal for row in matching), default=0) + 1
    parent_values = _resolved_parent_input_values(request)
    workspace = _workspace_for_ordinal(
        request,
        ordinal,
        effect_instance_digest=effect_instance_digest,
    )
    return RunRefLifecycleAllocation(
        attempt_ordinal=ordinal,
        effect_instance_root=root,
        bindings=_attempt_bindings(
            request,
            attempt_ordinal=ordinal,
            workspace=workspace,
            parent_values=parent_values,
            effect_instance_digest=effect_instance_digest,
        ),
        effect_instance_digest=effect_instance_digest,
        expected_ledger_sequence=len(ledger.rows) + 1,
        expected_previous_row_digest=(
            ledger.rows[-1].row_digest if ledger.rows else None
        ),
    )


def _validate_run_ref_lifecycle_attempt_authority(
    request: RunRefRuntimeRequest,
    *,
    authority: RunRefAttemptRecord,
    effect_instance_root: Path,
    effect_instance_digest: str,
    disagreement_reason: str,
) -> None:
    if type(request) is not RunRefRuntimeRequest:
        raise TypeError("request must be an exact RunRefRuntimeRequest")
    if type(authority) is not RunRefAttemptRecord:
        raise TypeError("authority must be an exact RunRefAttemptRecord")
    root = _canonical_absolute(
        Path(effect_instance_root),
        field="effect_instance_root",
    )
    try:
        ledger = load_attempt_ledger(root / _ATTEMPT_LEDGER_FILENAME)
    except RunRefLedgerError as exc:
        raise RunRefRuntimeError("run_ref_ledger_invalid", str(exc)) from exc
    parent_values = _resolved_parent_input_values(request)
    expected = _attempt_bindings(
        request,
        attempt_ordinal=authority.attempt_ordinal,
        workspace=_workspace_for_ordinal(
            request,
            authority.attempt_ordinal,
            effect_instance_digest=effect_instance_digest,
        ),
        parent_values=parent_values,
        effect_instance_digest=effect_instance_digest,
    )
    identity_fields = (
        "run_ref_root",
        "workspace_path",
        "source_digest",
        "program_digest",
        "input_digest",
        "policy_digest",
        "step_config_digest",
        "capsule_or_compiler_digest",
        "child_run_id",
        "result_contract_digest",
    )
    if (
        authority.visit != request.visit
        or authority.status != "in_progress"
        or not ledger.rows
        or ledger.rows[-1] != authority
        or any(
            getattr(authority.bindings, field) != getattr(expected, field)
            for field in identity_fields
        )
    ):
        raise RunRefRuntimeError(
            "run_ref_ledger_invalid",
            disagreement_reason,
        )


def validate_run_ref_lifecycle_attempt_authority(
    request: RunRefRuntimeRequest,
    *,
    authority: RunRefAttemptRecord,
    effect_instance_root: Path,
    effect_instance_digest: str,
) -> None:
    """Validate one durable nested E1 head against the complete current identity."""

    _validate_run_ref_lifecycle_attempt_authority(
        request,
        authority=authority,
        effect_instance_root=effect_instance_root,
        effect_instance_digest=effect_instance_digest,
        disagreement_reason="lifecycle_attempt_authority_disagrees",
    )


def validate_run_ref_lifecycle_allocation(
    request: RunRefRuntimeRequest,
    *,
    authority: RunRefAttemptRecord,
    effect_instance_root: Path,
    effect_instance_digest: str,
) -> None:
    """Validate one already-durable nested E1 allocation against current input."""

    _validate_run_ref_lifecycle_attempt_authority(
        request,
        authority=authority,
        effect_instance_root=effect_instance_root,
        effect_instance_digest=effect_instance_digest,
        disagreement_reason="lifecycle_allocation_authority_disagrees",
    )
    if authority.stage != "allocated" or authority.status != "in_progress":
        raise RunRefRuntimeError(
            "run_ref_ledger_invalid",
            "lifecycle_allocation_authority_disagrees",
        )


def _discard_incomplete_attempt(
    request: RunRefRuntimeRequest,
    dependencies: RunRefRuntimeDependencies,
) -> None:
    incomplete = identify_incomplete_attempt(
        request.ledger_path,
        visit=request.visit,
        current_step_config_digest=request.step_config.step_config_digest,
    )
    if incomplete is None:
        if request.parent_bundle_orphan_preimage is not None:
            raise RunRefRuntimeError(
                "run_ref_workspace_discard_failed",
                "parent_bundle_orphan_preimage_without_incomplete_attempt",
            )
        return
    workspace = incomplete.bindings.workspace_path
    try:
        dependencies.discard_workspace(workspace)
    except Exception as exc:
        raise RunRefRuntimeError(
            "run_ref_workspace_discard_failed",
            "bound_workspace_delete_failed",
        ) from exc
    if os.path.lexists(workspace):
        raise RunRefRuntimeError(
            "run_ref_workspace_discard_failed",
            "bound_workspace_still_exists",
        )
    disposition_record = {
        "schema_version": "run_ref_attempt_disposition.v1",
        "visit": request.visit.record,
        "attempt_ordinal": incomplete.attempt_ordinal,
        "incomplete_row_digest": incomplete.row_digest,
        "workspace_path": workspace.as_posix(),
        "disposition": "discard_incomplete_attempt_and_rerun_fresh",
        "workspace_deletion": {
            "status": "deleted_or_confirmed_absent",
            "workspace_absent": True,
        },
        "parent_bundle_orphan_preimage": (
            None
            if request.parent_bundle_orphan_preimage is None
            else request.parent_bundle_orphan_preimage.record
        ),
    }
    disposition_path = workspace.parent / _DISPOSITION_FILENAME
    try:
        if os.path.lexists(disposition_path):
            existing = _read_canonical_document(
                disposition_path,
                label="attempt_disposition",
            )
            if existing != disposition_record:
                raise RunRefRuntimeError(
                    "run_ref_workspace_discard_failed",
                    "attempt_disposition_preexisting_mismatch",
                )
        else:
            _write_canonical_document(disposition_path, disposition_record)
    except RunRefRuntimeError:
        raise
    except Exception as exc:
        raise RunRefRuntimeError(
            "run_ref_workspace_discard_failed",
            "attempt_disposition_write_failed",
        ) from exc
    disposition = canonical_sha256(disposition_record)
    record_discarded_attempt(
        request.ledger_path,
        visit=request.visit,
        attempt_ordinal=incomplete.attempt_ordinal,
        workspace_path=workspace,
        disposition_digest=disposition,
    )
    if (
        _read_canonical_document(
            disposition_path,
            label="attempt_disposition",
        )
        != disposition_record
    ):
        raise RunRefRuntimeError(
            "run_ref_workspace_discard_failed",
            "attempt_disposition_changed_after_record",
        )


def _snapshot_post_input_baseline(
    materialized: MaterializedSource,
) -> tuple[MaterializedSource, Path, TreeManifest]:
    workspace = materialized.workspace_path
    baseline = workspace.parent / _BASELINE_DIRECTORY
    if os.path.lexists(baseline):
        raise RunRefRuntimeError(
            "run_ref_delta_capture_failed",
            "baseline_snapshot_preexisting",
        )

    def ignored(directory: str, names: list[str]) -> set[str]:
        if Path(directory).resolve(strict=False) == workspace:
            return {name for name in names if name in {".git", ".orchestrate"}}
        return set()

    try:
        shutil.copytree(
            workspace,
            baseline,
            symlinks=True,
            copy_function=shutil.copy2,
            ignore=ignored,
        )
        manifest = freeze_tree(
            workspace,
            excluded_roots=(".git", ".orchestrate"),
        )
        if freeze_tree(baseline) != manifest:
            raise RunRefRuntimeError(
                "run_ref_delta_capture_failed",
                "baseline_snapshot_mismatch",
            )
    except RunRefRuntimeError:
        raise
    except Exception as exc:
        raise RunRefRuntimeError(
            "run_ref_delta_capture_failed",
            "baseline_snapshot_failed",
        ) from exc
    adjusted = replace(
        materialized,
        post_setup_tree_manifest=manifest,
        post_setup_baseline_identity=PostSetupBaselineIdentity(manifest.digest),
    )
    return adjusted, baseline, manifest


def _build_child_request(
    request: RunRefRuntimeRequest,
    *,
    materialized: MaterializedSource,
    child_run_id: str,
    resolved_inputs: Mapping[str, Any],
    child_test_boundary: str | None,
) -> tuple[str, dict[str, Any]]:
    static = request.step_config.run_ref
    child_state_dir = materialized.workspace_path / ".orchestrate" / "runs"
    expected_test_boundary = (
        "mode_1_decode"
        if isinstance(static.program, BundleProgram)
        else "mode_2_compile"
    )
    if (
        child_test_boundary is not None
        and child_test_boundary != expected_test_boundary
    ):
        raise RunRefRuntimeError(
            "run_ref_child_launch_failed",
            "child_test_boundary_mode_mismatch",
        )
    test_control = (
        None
        if child_test_boundary is None
        else {
            "schema_version": "run_ref_child_test_control.v1",
            "boundary": child_test_boundary,
            "progress_path": (
                materialized.workspace_path.parent
                / "run-ref-child-boundary-progress.json"
            ).as_posix(),
        }
    )
    if isinstance(static.program, BundleProgram):
        assert request.step_config.capsule_binding is not None
        assert request.capsule_dir is not None
        return "bundle", {
            "schema_version": "run_ref_child_request.v1",
            "clone_root": materialized.workspace_path.as_posix(),
            "capsule_dir": request.capsule_dir.as_posix(),
            "expected_capsule_digest": (
                request.step_config.capsule_binding.capsule_digest
            ),
            "expected_compiler_runtime_identity_digest": (
                static.compiler_runtime_identity_digest
            ),
            "target_workflow_name": static.program.workflow_name,
            "child_run_id": child_run_id,
            "child_state_dir": child_state_dir.as_posix(),
            "inputs": dict(resolved_inputs),
            "test_control": test_control,
        }
    from .child import materialized_source_record

    return "path", {
        "schema_version": "run_ref_path_child_request.v1",
        "clone_root": materialized.workspace_path.as_posix(),
        "child_state_dir": child_state_dir.as_posix(),
        "child_run_id": child_run_id,
        "materialized_source": materialized_source_record(materialized),
        "run_ref_static_config_base64": base64.b64encode(
            encode_run_ref_static_config(static)
        ).decode("ascii"),
        "expected_step_config_digest": request.step_config.step_config_digest,
        "inputs": dict(resolved_inputs),
        "test_control": test_control,
    }


def _program_preparation_digest(
    request: RunRefRuntimeRequest,
    *,
    mode: str,
    child_request: Mapping[str, Any],
) -> str:
    return canonical_sha256(
        {
            "schema_version": "run_ref_program_preparation.v1",
            "mode": mode,
            "step_config_digest": request.step_config.step_config_digest,
            "child_request_digest": canonical_sha256(dict(child_request)),
        }
    )


def _child_result_document(
    request: RunRefRuntimeRequest,
    *,
    launch: RunRefChildLaunch,
    process: RunRefChildProcessResult,
) -> dict[str, Any]:
    if process.returncode != 0:
        try:
            if process.stdout:
                raise ValueError("failed_child_wrote_stdout")
            decoded_diagnostic = _decode_json(
                process.stderr,
                canonical=True,
                label="child_diagnostic",
            )
            from .child import validate_child_diagnostic_document

            diagnostic = validate_child_diagnostic_document(
                decoded_diagnostic
            )
        except (RunRefRuntimeError, TypeError, ValueError) as exc:
            raise RunRefRuntimeError(
                "run_ref_child_launch_failed",
                "child_process_failed_without_diagnostic",
            ) from exc
        code = diagnostic["code"]
        machine_fields = (
            {
                key: diagnostic[key]
                for key in (
                    "rejected_value",
                    "secondary_causes",
                    "compile_diagnostics",
                )
                if key in diagnostic
            }
            if code.startswith("trial_")
            else None
        )
        raise RunRefRuntimeError(
            code,
            diagnostic["reason"],
            machine_fields=machine_fields,
        )
    if process.stderr:
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "successful_child_wrote_stderr",
        )
    result = _decode_json(process.stdout, canonical=True, label="child_result")
    if not isinstance(result, dict):
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "child_result_not_object",
        )
    common = {
        "schema_version",
        "status",
        "target_workflow_name",
        "child_run_id",
        "workflow_outputs",
    }
    if launch.mode == "bundle":
        if set(result) != common | {"capsule_digest"}:
            raise RunRefRuntimeError(
                "run_ref_child_result_invalid",
                "child_result_shape_invalid",
            )
        program = request.step_config.run_ref.program
        assert isinstance(program, BundleProgram)
        if (
            result["schema_version"] != "run_ref_child_result.v1"
            or result["target_workflow_name"] != program.workflow_name
            or result["capsule_digest"]
            != request.step_config.capsule_binding.capsule_digest
        ):
            raise RunRefRuntimeError(
                "run_ref_child_result_invalid",
                "child_result_binding_invalid",
            )
    else:
        if set(result) != common | {"step_config_digest", "path_compile"}:
            raise RunRefRuntimeError(
                "run_ref_child_result_invalid",
                "child_result_shape_invalid",
            )
        if (
            result["schema_version"] != "run_ref_path_child_result.v1"
            or result["step_config_digest"]
            != request.step_config.step_config_digest
            or not isinstance(result["path_compile"], Mapping)
        ):
            raise RunRefRuntimeError(
                "run_ref_child_result_invalid",
                "child_result_binding_invalid",
            )
    if (
        result.get("status") != "completed"
        or result.get("child_run_id") != launch.child_run_id
        or not isinstance(result.get("target_workflow_name"), str)
        or not isinstance(result.get("workflow_outputs"), Mapping)
    ):
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "child_result_binding_invalid",
        )
    return result


def _child_terminal_state(
    *,
    workspace: Path,
    child_run_id: str,
    workflow_outputs: Mapping[str, Any],
) -> tuple[dict[str, Any], Path, str]:
    path = workspace / ".orchestrate" / "runs" / child_run_id / "state.json"
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "child_terminal_state_unreadable",
        ) from exc
    state = _decode_json(payload, canonical=False, label="child_terminal_state")
    if (
        not isinstance(state, dict)
        or state.get("run_id") != child_run_id
        or state.get("status") != "completed"
        or state.get("workflow_outputs") != dict(workflow_outputs)
    ):
        raise RunRefRuntimeError(
            "run_ref_child_result_invalid",
            "child_terminal_state_invalid",
        )
    return state, path, _sha256_bytes(payload)


def _setup_duration_ms(materialized: MaterializedSource) -> int:
    evidence = _read_canonical_document(
        materialized.setup_evidence_path,
        label="setup_evidence",
    )
    if (
        not isinstance(evidence, Mapping)
        or evidence.get("status") != "passed"
        or not isinstance(evidence.get("commands"), list)
        or canonical_sha256(dict(evidence)) != materialized.setup_evidence_digest
    ):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "setup_evidence_binding_invalid",
        )
    total = 0
    for row in evidence["commands"]:
        duration = row.get("duration_ms") if isinstance(row, Mapping) else None
        if type(duration) is not int or duration < 0:
            raise RunRefRuntimeError(
                "run_ref_evidence_invalid",
                "setup_evidence_duration_invalid",
            )
        total += duration
    return total


def _evidence_manifest_record(
    request: RunRefRuntimeRequest,
    *,
    row: RunRefAttemptRecord,
    mode: str,
    baseline_path: Path,
    setup_evidence_path: Path,
    child_state_path: Path,
    request_path: Path,
    child_result_path: Path,
    delta_path: Path,
    accounting_path: Path,
    result_envelope_digest: str,
    final_workspace_digest: str,
) -> dict[str, Any]:
    bindings = row.bindings
    return {
        "schema_version": RUN_REF_EVIDENCE_MANIFEST_SCHEMA,
        "visit": request.visit.record,
        "attempt_ordinal": row.attempt_ordinal,
        "mode": mode,
        "step_config_digest": request.step_config.step_config_digest,
        "source_digest": bindings.source_digest,
        "program_digest": bindings.program_digest,
        "input_digest": bindings.input_digest,
        "policy_digest": bindings.policy_digest,
        "capsule_or_compiler_digest": bindings.capsule_or_compiler_digest,
        "result_contract_digest": bindings.result_contract_digest,
        "repository_revision_digest": canonical_sha256(
            {
                key: value
                for key, value in canonical_source_request(
                    request.step_config.run_ref.source
                ).items()
                if key
                in {
                    "normalized_locator",
                    "resolved_commit_sha",
                    "materializer_version",
                    "submodule_policy",
                    "lfs_policy",
                    "authored_setup_identity",
                }
            }
        ),
        "verified_git_tree_id": bindings.verified_git_tree_id,
        "setup_evidence_digest": bindings.setup_evidence_digest,
        "post_setup_baseline_digest": bindings.post_setup_baseline_digest,
        "program_preparation_digest": bindings.program_preparation_digest,
        "child_launch_digest": bindings.child_launch_digest,
        "child_run_id": bindings.child_run_id,
        "child_terminal_state_digest": bindings.child_terminal_state_digest,
        "result_payload_digest": bindings.result_payload_digest,
        "workspace_delta_digest": bindings.workspace_delta_digest,
        "accounting_digest": bindings.accounting_digest,
        "result_envelope_digest": result_envelope_digest,
        "final_workspace_digest": final_workspace_digest,
        "paths": {
            "workspace": bindings.workspace_path.as_posix(),
            "baseline": baseline_path.as_posix(),
            "setup_evidence": setup_evidence_path.as_posix(),
            "child_state": child_state_path.as_posix(),
            "child_request": request_path.as_posix(),
            "child_result": child_result_path.as_posix(),
            "workspace_delta": delta_path.as_posix(),
            "accounting": accounting_path.as_posix(),
        },
    }


def _validate_lifecycle_acknowledgement_authority(
    *,
    event: RunRefLifecycleEvent,
    acknowledgement: RunRefLifecycleAcknowledgement,
) -> None:
    """Validate the exact row the caller reports durably applying."""

    row = acknowledgement.authority
    row_payload = dict(row.record)
    row_payload.pop("row_digest")
    if canonical_sha256(row_payload) != row.row_digest:
        raise ValueError("run-ref lifecycle acknowledgement row is not canonical")
    if (
        row.visit != event.visit
        or row.attempt_ordinal != event.attempt_ordinal
        or row.stage != event.stage
    ):
        raise ValueError("run-ref lifecycle acknowledgement authority disagrees")
    payload = event.payload
    if event.stage == "allocated":
        if row.bindings.record != payload["bindings"]:
            raise ValueError(
                "run-ref lifecycle allocation acknowledgement disagrees"
            )
        return
    for name, value in payload["binding_updates"].items():
        observed = getattr(row.bindings, name)
        if isinstance(observed, Path):
            observed = observed.as_posix()
        if observed != value:
            raise ValueError("run-ref lifecycle progress acknowledgement disagrees")


def acknowledge_persisted_run_ref_lifecycle_event(
    event: RunRefLifecycleEvent,
    *,
    expected_row_digest: str,
) -> RunRefLifecycleAcknowledgement:
    """Reload the exact durable ledger head before acknowledging one event."""

    if type(event) is not RunRefLifecycleEvent:
        raise TypeError("event must be an exact RunRefLifecycleEvent")
    if not isinstance(expected_row_digest, str) or _SHA256_RE.fullmatch(
        expected_row_digest
    ) is None:
        raise ValueError("expected durable row digest is invalid")
    ledger_path = event.effect_instance_root / _ATTEMPT_LEDGER_FILENAME
    try:
        ledger = load_attempt_ledger(ledger_path)
    except RunRefLedgerError as exc:
        raise ValueError("run-ref lifecycle authority is not durable") from exc
    if not ledger.rows:
        raise ValueError("run-ref lifecycle authority is not durable")
    row = ledger.rows[-1]
    if row.row_digest != expected_row_digest:
        if any(
            candidate.row_digest == expected_row_digest
            for candidate in ledger.rows
        ):
            raise ValueError("run-ref lifecycle authority is not the ledger head")
        raise ValueError("run-ref lifecycle authority is not durable")
    acknowledgement = RunRefLifecycleAcknowledgement._for_durable_row(
        event,
        authority=row,
    )
    _validate_lifecycle_acknowledgement_authority(
        event=event,
        acknowledgement=acknowledgement,
    )
    return acknowledgement


def drive_run_ref_lifecycle(
    request: RunRefRuntimeRequest,
    *,
    allocation: RunRefLifecycleAllocation,
    acknowledge: Callable[
        [RunRefLifecycleEvent], RunRefLifecycleAcknowledgement
    ],
    dependencies: RunRefRuntimeDependencies | None = None,
    deadline_monotonic_ns: int | None = None,
    started_monotonic_ns: int | None = None,
) -> PreparedRunRefSettlement:
    """Perform blocking E1 work through caller-acknowledged immutable events.

    This driver never writes an attempt ledger.  The caller owns each event's
    durable projection and must return its exact authority digest before the
    driver may cross the next lifecycle boundary.
    """

    if type(request) is not RunRefRuntimeRequest:
        raise TypeError("request must be an exact RunRefRuntimeRequest")
    if type(allocation) is not RunRefLifecycleAllocation:
        raise TypeError("allocation must be an exact RunRefLifecycleAllocation")
    effects = dependencies or RunRefRuntimeDependencies()
    if type(effects) is not RunRefRuntimeDependencies:
        raise TypeError("dependencies must be exact RunRefRuntimeDependencies")
    if not callable(acknowledge):
        raise TypeError("acknowledge must be callable")
    if deadline_monotonic_ns is not None and (
        type(deadline_monotonic_ns) is not int or deadline_monotonic_ns < 0
    ):
        raise ValueError("deadline_monotonic_ns must be non-negative or None")
    if started_monotonic_ns is not None and (
        type(started_monotonic_ns) is not int or started_monotonic_ns < 0
    ):
        raise ValueError("started_monotonic_ns must be non-negative or None")

    child_started = False

    def require_before_deadline() -> None:
        if (
            not child_started
            and
            deadline_monotonic_ns is not None
            and effects.monotonic_ns() >= deadline_monotonic_ns
        ):
            raise RunRefLifecycleDeadlineExceeded()

    next_sequence = 1
    previous_authority: RunRefAttemptRecord | None = None

    def emit(
        *,
        stage: str,
        event_kind: str,
        attempt_ordinal: int,
        payload: Mapping[str, Any],
    ) -> RunRefLifecycleAcknowledgement:
        nonlocal next_sequence, previous_authority
        require_before_deadline()
        event = RunRefLifecycleEvent.build(
            sequence=next_sequence,
            event_kind=event_kind,
            stage=stage,
            visit=request.visit,
            attempt_ordinal=attempt_ordinal,
            effect_instance_root=allocation.effect_instance_root,
            payload=payload,
        )
        acknowledgement = acknowledge(event)
        if (
            type(acknowledgement) is not RunRefLifecycleAcknowledgement
            or acknowledgement.sequence != event.sequence
            or acknowledgement.stage != event.stage
            or acknowledgement.event_digest != event.event_digest
        ):
            raise ValueError("run-ref lifecycle acknowledgement is invalid")
        _validate_lifecycle_acknowledgement_authority(
            event=event,
            acknowledgement=acknowledgement,
        )
        authority = acknowledgement.authority
        if previous_authority is None:
            if (
                authority.sequence != allocation.expected_ledger_sequence
                or authority.previous_row_digest
                != allocation.expected_previous_row_digest
            ):
                raise ValueError(
                    "run-ref lifecycle allocation acknowledgement is not adjacent"
                )
        elif (
            authority.sequence != previous_authority.sequence + 1
            or authority.previous_row_digest != previous_authority.row_digest
        ):
            raise ValueError(
                "run-ref lifecycle progress acknowledgement is not adjacent"
            )
        previous_authority = authority
        next_sequence += 1
        require_before_deadline()
        return acknowledgement

    started_ns = (
        effects.monotonic_ns()
        if started_monotonic_ns is None
        else started_monotonic_ns
    )
    try:
        require_before_deadline()
        ordinal = allocation.attempt_ordinal
        workspace = allocation.bindings.workspace_path
        parent_values = _resolved_parent_input_values(request)
        expected_bindings = _attempt_bindings(
            request,
            attempt_ordinal=ordinal,
            workspace=workspace,
            parent_values=parent_values,
            effect_instance_digest=allocation.effect_instance_digest,
        )
        if allocation.bindings != expected_bindings:
            raise RunRefRuntimeError(
                "run_ref_ledger_invalid",
                "lifecycle_allocation_authority_disagrees",
            )
        bindings = allocation.bindings
        emit(
            stage="allocated",
            event_kind="allocation",
            attempt_ordinal=ordinal,
            payload={"bindings": bindings.record},
        )
        effects.crash_hook("allocation")

        def source_progress(stage: str) -> None:
            if stage == "materialized":
                effects.crash_hook("materialize")
                return
            if stage == "setup_completed":
                effects.crash_hook("setup")
                return
            raise RunRefRuntimeError(
                "run_ref_child_launch_failed",
                "materializer_progress_stage_invalid",
            )

        try:
            require_before_deadline()
            materialized = effects.materialize_source(
                request.step_config.run_ref.source,
                run_ref_root=request.run_ref_root,
                workspace=workspace,
                progress_hook=source_progress,
            )
        except RunRefSourceRefusal as exc:
            raise RunRefRuntimeError(
                exc.code,
                "source_materialization_refused",
                machine_fields={
                    "rejected_value": exc.rejected_value,
                    "secondary_causes": list(exc.secondary_causes),
                },
            ) from exc
        if type(materialized) is not MaterializedSource or materialized.workspace_path != workspace:
            raise RunRefRuntimeError(
                "run_ref_child_launch_failed",
                "materializer_authority_invalid",
            )
        bindings = replace(
            bindings,
            verified_git_tree_id=materialized.verified_git_tree.value,
        )
        emit(
            stage="materialized",
            event_kind="progress",
            attempt_ordinal=ordinal,
            payload={"binding_updates": {
                "verified_git_tree_id": materialized.verified_git_tree.value,
            }},
        )

        resolved_inputs = resolve_run_ref_inputs(
            request.step_config.run_ref.inputs,
            parent_state=request.parent_state,
            parent_workspace=request.parent_workspace,
            child_workspace=workspace,
        )
        materialized, baseline_path, baseline_manifest = (
            _snapshot_post_input_baseline(materialized)
        )
        setup_updates = {
            "setup_evidence_digest": materialized.setup_evidence_digest,
            "post_setup_baseline_digest": baseline_manifest.digest,
        }
        bindings = replace(bindings, **setup_updates)
        emit(
            stage="setup_completed",
            event_kind="progress",
            attempt_ordinal=ordinal,
            payload={"binding_updates": setup_updates},
        )

        mode, child_request = _build_child_request(
            request,
            materialized=materialized,
            child_run_id=bindings.child_run_id,
            resolved_inputs=resolved_inputs,
            child_test_boundary=effects.child_test_boundary,
        )
        attempt_root = workspace.parent
        request_path = attempt_root / _REQUEST_FILENAME
        _write_canonical_document(request_path, child_request)
        preparation_digest = _program_preparation_digest(
            request,
            mode=mode,
            child_request=child_request,
        )
        preparation_updates = {"program_preparation_digest": preparation_digest}
        bindings = replace(bindings, **preparation_updates)
        emit(
            stage="program_prepared",
            event_kind="progress",
            attempt_ordinal=ordinal,
            payload={"binding_updates": preparation_updates},
        )
        launch_digest = canonical_sha256(child_request)
        launch_updates = {"child_launch_digest": launch_digest}
        bindings = replace(bindings, **launch_updates)
        emit(
            stage="launched",
            event_kind="progress",
            attempt_ordinal=ordinal,
            payload={"binding_updates": launch_updates},
        )
        effects.crash_hook("launch")
        launch = RunRefChildLaunch(
            mode=mode,
            request_path=request_path,
            request_document=child_request,
            workspace=workspace,
            child_run_id=bindings.child_run_id,
        )
        try:
            require_before_deadline()
            child_started = True
            process = effects.launch_child(launch)
        except RunRefRuntimeError:
            raise
        except Exception as exc:
            raise RunRefRuntimeError(
                "run_ref_child_launch_failed",
                "child_process_launch_failed",
            ) from exc
        if type(process) is not RunRefChildProcessResult:
            raise RunRefRuntimeError(
                "run_ref_child_launch_failed",
                "child_launcher_result_invalid",
            )
        child_result = _child_result_document(
            request,
            launch=launch,
            process=process,
        )
        _, child_state_path, child_state_digest = _child_terminal_state(
            workspace=workspace,
            child_run_id=bindings.child_run_id,
            workflow_outputs=child_result["workflow_outputs"],
        )
        child_result_path = attempt_root / _CHILD_RESULT_FILENAME
        _write_canonical_document(child_result_path, child_result)
        result_payload_digest = canonical_sha256(child_result)
        child_updates = {
            "child_terminal_state_digest": child_state_digest,
            "result_payload_digest": result_payload_digest,
        }
        bindings = replace(bindings, **child_updates)
        emit(
            stage="child_completed",
            event_kind="progress",
            attempt_ordinal=ordinal,
            payload={"binding_updates": child_updates},
        )
        effects.crash_hook("child_completion")

        value_descriptor = request.step_config.run_ref.result_descriptor[
            "envelope"
        ]["fields"][0]["type"]
        value = extract_run_ref_value(
            child_result["workflow_outputs"],
            value_descriptor,
            workspace=workspace,
        )
        declared_artifacts = declared_artifacts_from_value(value, value_descriptor)
        delta = build_workspace_delta(
            base=materialized.repository_revision_id,
            baseline_root=baseline_path,
            baseline_manifest=baseline_manifest,
            workspace_root=workspace,
            declared_artifacts=declared_artifacts,
        )
        accounting = build_run_ref_accounting(
            child_run_id=bindings.child_run_id,
            attempt_ordinal=ordinal,
            terminal_status="completed",
            elapsed_ms=max(0, (effects.monotonic_ns() - started_ns) // 1_000_000),
            setup_ms=_setup_duration_ms(materialized),
            compile_ms=0,
        )
        delta_path = attempt_root / _WORKSPACE_DELTA_FILENAME
        accounting_path = attempt_root / _ACCOUNTING_FILENAME
        _write_canonical_document(delta_path, delta.record)
        _write_canonical_document(accounting_path, accounting)
        accounting_digest = canonical_sha256(accounting)
        envelope = {
            "value": value,
            "workspace_delta": delta.record,
            "accounting": accounting,
        }
        result_envelope_digest = canonical_sha256(envelope)

        evidence_path = attempt_root / _EVIDENCE_FILENAME
        delta_updates = {
            "workspace_delta_digest": delta.digest,
            "accounting_digest": accounting_digest,
        }
        provisional_bindings = replace(bindings, **delta_updates)
        provisional = RunRefAttemptRecord(
            sequence=0,
            previous_row_digest=None,
            row_digest=canonical_sha256(
                {
                    "schema_version": "run_ref_lifecycle_provisional_row.v1",
                    "visit": request.visit.record,
                    "attempt_ordinal": ordinal,
                }
            ),
            visit=request.visit,
            attempt_ordinal=ordinal,
            stage="delta_captured",
            status="in_progress",
            recorded_at="1970-01-01T00:00:00.000000Z",
            bindings=provisional_bindings,
        )
        evidence = _evidence_manifest_record(
            request,
            row=provisional,
            mode=mode,
            baseline_path=baseline_path,
            setup_evidence_path=materialized.setup_evidence_path,
            child_state_path=child_state_path,
            request_path=request_path,
            child_result_path=child_result_path,
            delta_path=delta_path,
            accounting_path=accounting_path,
            result_envelope_digest=result_envelope_digest,
            final_workspace_digest=delta.final_manifest.digest,
        )
        evidence_digest = canonical_sha256(evidence)
        _write_canonical_document(evidence_path, evidence)
        delta_updates["evidence_manifest_digest"] = evidence_digest
        bindings = replace(bindings, **delta_updates)
        emit(
            stage="delta_captured",
            event_kind="progress",
            attempt_ordinal=ordinal,
            payload={"binding_updates": delta_updates},
        )
        effects.crash_hook("delta")
        artifact_projection = flatten_run_ref_result_artifacts(
            envelope,
            request.step_config.run_ref.result_descriptor["envelope"],
        )
        pending_ack = emit(
            stage="completed_pending_parent_commit",
            event_kind="prepared",
            attempt_ordinal=ordinal,
            payload={
                "binding_updates": {},
                "result_envelope_digest": result_envelope_digest,
                "artifact_projection_digest": canonical_sha256(artifact_projection),
                "evidence_manifest_digest": evidence_digest,
            },
        )
    except RunRefLedgerError as exc:
        raise RunRefRuntimeError("run_ref_ledger_invalid", str(exc)) from exc
    except RunRefDeltaError as exc:
        raise RunRefRuntimeError(
            "run_ref_delta_capture_failed",
            ",".join(exc.secondary_causes),
        ) from exc

    return PreparedRunRefSettlement(
        envelope=envelope,
        artifacts=artifact_projection,
        settled_result=SettledRunRefResultBinding(
            visit=request.visit,
            attempt_ordinal=ordinal,
            step_config_digest=bindings.step_config_digest,
            run_ref_root=bindings.run_ref_root,
            workspace_path=bindings.workspace_path,
            child_run_id=bindings.child_run_id,
            pending_row_digest=pending_ack.authority_digest,
            child_terminal_state_digest=bindings.child_terminal_state_digest,
            result_contract_digest=bindings.result_contract_digest,
            result_payload_digest=bindings.result_payload_digest,
            workspace_delta_digest=bindings.workspace_delta_digest,
            accounting_digest=bindings.accounting_digest,
            evidence_manifest_digest=bindings.evidence_manifest_digest,
        ),
        ledger_path=allocation.ledger_path,
        evidence_manifest_path=evidence_path,
    )


def persist_run_ref_lifecycle_event(
    request: RunRefRuntimeRequest,
    event: RunRefLifecycleEvent,
) -> RunRefLifecycleAcknowledgement:
    """Apply one exact driver event to the E1 ledger as its caller."""

    if type(request) is not RunRefRuntimeRequest:
        raise TypeError("request must be an exact RunRefRuntimeRequest")
    if type(event) is not RunRefLifecycleEvent:
        raise TypeError("event must be an exact RunRefLifecycleEvent")
    if (
        event.visit != request.visit
    ):
        raise RunRefRuntimeError(
            "run_ref_ledger_invalid",
            "lifecycle_event_scope_disagrees",
        )
    payload = event.payload
    ledger_path = event.effect_instance_root / _ATTEMPT_LEDGER_FILENAME
    try:
        if event.stage == "allocated":
            bindings = RunRefAttemptBindings(**payload["bindings"])
            row = allocate_attempt(
                ledger_path,
                visit=request.visit,
                bindings=bindings,
            )
            if row.attempt_ordinal != event.attempt_ordinal:
                raise RunRefLedgerError(
                    "lifecycle allocation ordinal disagrees"
                )
        else:
            row = advance_attempt(
                ledger_path,
                visit=request.visit,
                attempt_ordinal=event.attempt_ordinal,
                stage=event.stage,
                binding_updates=payload["binding_updates"],
            )
    except RunRefLedgerError as exc:
        raise RunRefRuntimeError("run_ref_ledger_invalid", str(exc)) from exc
    return acknowledge_persisted_run_ref_lifecycle_event(
        event,
        expected_row_digest=row.row_digest,
    )


def prepare_run_ref_settlement(
    request: RunRefRuntimeRequest,
    *,
    dependencies: RunRefRuntimeDependencies | None = None,
) -> PreparedRunRefSettlement:
    """Synchronous compatibility wrapper over the acknowledged E1 driver."""

    if type(request) is not RunRefRuntimeRequest:
        raise TypeError("request must be an exact RunRefRuntimeRequest")
    effects = dependencies or RunRefRuntimeDependencies()
    if type(effects) is not RunRefRuntimeDependencies:
        raise TypeError("dependencies must be exact RunRefRuntimeDependencies")
    started_ns = effects.monotonic_ns()
    try:
        _discard_incomplete_attempt(request, effects)
        allocation = select_run_ref_lifecycle_allocation(request)
    except RunRefLedgerError as exc:
        raise RunRefRuntimeError("run_ref_ledger_invalid", str(exc)) from exc
    return drive_run_ref_lifecycle(
        request,
        allocation=allocation,
        dependencies=effects,
        started_monotonic_ns=started_ns,
        acknowledge=lambda event: persist_run_ref_lifecycle_event(
            request,
            event,
        ),
    )


def _repository_revision(request: RunRefRuntimeRequest) -> RepositoryRevisionId:
    source = canonical_source_request(request.step_config.run_ref.source)
    return RepositoryRevisionId.build(
        normalized_locator=source["normalized_locator"],
        resolved_commit_sha=source["resolved_commit_sha"],
        materializer_version=source["materializer_version"],
        submodule_policy=source["submodule_policy"],
        lfs_policy=source["lfs_policy"],
        authored_setup_identity=source["authored_setup_identity"],
    )


def _validate_child_request_document(
    request: RunRefRuntimeRequest,
    *,
    row: RunRefAttemptRecord,
    document: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    workspace = row.bindings.workspace_path
    child_state_dir = workspace / ".orchestrate" / "runs"
    program = request.step_config.run_ref.program
    common = {
        "schema_version",
        "clone_root",
        "child_state_dir",
        "child_run_id",
        "inputs",
        "test_control",
    }
    if isinstance(program, BundleProgram):
        expected_keys = common | {
            "capsule_dir",
            "expected_capsule_digest",
            "expected_compiler_runtime_identity_digest",
            "target_workflow_name",
        }
        if (
            set(document) != expected_keys
            or document.get("schema_version") != "run_ref_child_request.v1"
            or document.get("test_control") is not None
            or document.get("capsule_dir") != request.capsule_dir.as_posix()
            or document.get("expected_capsule_digest")
            != request.step_config.capsule_binding.capsule_digest
            or document.get("expected_compiler_runtime_identity_digest")
            != request.step_config.run_ref.compiler_runtime_identity_digest
            or document.get("target_workflow_name") != program.workflow_name
        ):
            raise RunRefRuntimeError(
                "run_ref_evidence_invalid",
                "child_request_binding_invalid",
            )
        mode = "bundle"
    else:
        expected_keys = common | {
            "materialized_source",
            "run_ref_static_config_base64",
            "expected_step_config_digest",
        }
        expected_static = base64.b64encode(
            encode_run_ref_static_config(request.step_config.run_ref)
        ).decode("ascii")
        materialized_record = document.get("materialized_source")
        if (
            set(document) != expected_keys
            or document.get("schema_version") != "run_ref_path_child_request.v1"
            or document.get("test_control") is not None
            or document.get("run_ref_static_config_base64") != expected_static
            or document.get("expected_step_config_digest")
            != request.step_config.step_config_digest
            or not isinstance(materialized_record, Mapping)
            or materialized_record.get("workspace_path") != workspace.as_posix()
            or materialized_record.get("verified_git_tree")
            != row.bindings.verified_git_tree_id
            or materialized_record.get("setup_evidence_digest")
            != row.bindings.setup_evidence_digest
            or materialized_record.get("post_setup_baseline_identity")
            != row.bindings.post_setup_baseline_digest
        ):
            raise RunRefRuntimeError(
                "run_ref_evidence_invalid",
                "child_request_binding_invalid",
            )
        mode = "path"
    inputs = document.get("inputs")
    if (
        document.get("clone_root") != workspace.as_posix()
        or document.get("child_state_dir") != child_state_dir.as_posix()
        or document.get("child_run_id") != row.bindings.child_run_id
        or not isinstance(inputs, Mapping)
        or set(inputs) != {item.name for item in request.step_config.run_ref.inputs}
    ):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "child_request_binding_invalid",
        )
    canonical_inputs: dict[str, Any] = {}
    for input_row in request.step_config.run_ref.inputs:
        canonical_inputs[input_row.name] = _coerce_transport_value(
            inputs[input_row.name],
            input_row.type_descriptor,
            parent_workspace=workspace,
            child_workspace=workspace,
            input_name=input_row.name,
            copy_paths=False,
        )
    if canonical_inputs != dict(inputs):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "child_request_inputs_invalid",
        )
    return mode, dict(document)


def _validate_bound_authority(
    request: RunRefRuntimeRequest,
    row: RunRefAttemptRecord,
    *,
    effect_instance_digest: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if row.visit != request.visit:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "visit_binding_invalid",
        )
    parent_values = _resolved_parent_input_values(request)
    expected = _attempt_bindings(
        request,
        attempt_ordinal=row.attempt_ordinal,
        workspace=_workspace_for_ordinal(
            request,
            row.attempt_ordinal,
            effect_instance_digest=effect_instance_digest,
        ),
        parent_values=parent_values,
        effect_instance_digest=effect_instance_digest,
    )
    for name in (
        "run_ref_root",
        "workspace_path",
        "source_digest",
        "program_digest",
        "input_digest",
        "policy_digest",
        "step_config_digest",
        "capsule_or_compiler_digest",
        "child_run_id",
        "result_contract_digest",
    ):
        if getattr(row.bindings, name) != getattr(expected, name):
            raise RunRefRuntimeError(
                "run_ref_evidence_invalid",
                f"{name}_binding_invalid",
            )
    attempt_root = row.bindings.workspace_path.parent
    request_path = attempt_root / _REQUEST_FILENAME
    child_result_path = attempt_root / _CHILD_RESULT_FILENAME
    delta_path = attempt_root / _WORKSPACE_DELTA_FILENAME
    accounting_path = attempt_root / _ACCOUNTING_FILENAME
    evidence_path = attempt_root / _EVIDENCE_FILENAME
    baseline_path = attempt_root / _BASELINE_DIRECTORY

    request_document = _read_canonical_document(
        request_path,
        label="child_request",
    )
    if not isinstance(request_document, Mapping):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "child_request_not_object",
        )
    mode, request_document = _validate_child_request_document(
        request,
        row=row,
        document=request_document,
    )
    if (
        canonical_sha256(request_document) != row.bindings.child_launch_digest
        or _program_preparation_digest(
            request,
            mode=mode,
            child_request=request_document,
        )
        != row.bindings.program_preparation_digest
    ):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "child_request_digest_invalid",
        )

    child_result_document = _read_canonical_document(
        child_result_path,
        label="child_result",
    )
    if not isinstance(child_result_document, Mapping):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "child_result_not_object",
        )
    child_result = _child_result_document(
        request,
        launch=RunRefChildLaunch(
            mode=mode,
            request_path=request_path,
            request_document=request_document,
            workspace=row.bindings.workspace_path,
            child_run_id=row.bindings.child_run_id,
        ),
        process=RunRefChildProcessResult(
            returncode=0,
            stdout=canonical_json_bytes(child_result_document) + b"\n",
            stderr=b"",
            duration_ms=0,
        ),
    )
    if canonical_sha256(child_result) != row.bindings.result_payload_digest:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "result_payload_digest_invalid",
        )
    _, child_state_path, child_state_digest = _child_terminal_state(
        workspace=row.bindings.workspace_path,
        child_run_id=row.bindings.child_run_id,
        workflow_outputs=child_result["workflow_outputs"],
    )
    if child_state_digest != row.bindings.child_terminal_state_digest:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "child_terminal_state_digest_invalid",
        )

    try:
        baseline_manifest = freeze_tree(baseline_path)
    except Exception as exc:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "baseline_snapshot_invalid",
        ) from exc
    if baseline_manifest.digest != row.bindings.post_setup_baseline_digest:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "baseline_digest_invalid",
        )
    value_descriptor = request.step_config.run_ref.result_descriptor[
        "envelope"
    ]["fields"][0]["type"]
    value = extract_run_ref_value(
        child_result["workflow_outputs"],
        value_descriptor,
        workspace=row.bindings.workspace_path,
    )
    declared_artifacts = declared_artifacts_from_value(value, value_descriptor)
    delta_record = _read_canonical_document(delta_path, label="workspace_delta")
    if not isinstance(delta_record, Mapping):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "workspace_delta_not_object",
        )
    final_manifest = validate_workspace_delta(
        delta_record,
        expected_digest=row.bindings.workspace_delta_digest,
        base=_repository_revision(request),
        baseline_root=baseline_path,
        baseline_manifest=baseline_manifest,
        workspace_root=row.bindings.workspace_path,
        declared_artifacts=declared_artifacts,
    )
    accounting = _read_canonical_document(accounting_path, label="accounting")
    if not isinstance(accounting, Mapping):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "accounting_not_object",
        )
    required_accounting = {
        "child_run_id",
        "attempt_ordinal",
        "terminal_status",
        "elapsed_ms",
        "setup_ms",
        "compile_ms",
        "provider_attempts",
        "token_usage",
        "cost",
    }
    if (
        set(accounting) != required_accounting
        or canonical_sha256(dict(accounting)) != row.bindings.accounting_digest
        or accounting.get("child_run_id") != row.bindings.child_run_id
        or accounting.get("attempt_ordinal") != row.attempt_ordinal
        or accounting.get("terminal_status") != "completed"
        or build_run_ref_accounting(**dict(accounting)) != dict(accounting)
    ):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "accounting_binding_invalid",
        )
    envelope = {
        "value": value,
        "workspace_delta": dict(delta_record),
        "accounting": dict(accounting),
    }
    artifacts = flatten_run_ref_result_artifacts(
        envelope,
        request.step_config.run_ref.result_descriptor["envelope"],
    )

    evidence = _read_canonical_document(evidence_path, label="evidence_manifest")
    if not isinstance(evidence, Mapping):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "evidence_manifest_not_object",
        )
    paths = evidence.get("paths")
    setup_evidence_path = (
        Path(paths["setup_evidence"])
        if isinstance(paths, Mapping) and isinstance(paths.get("setup_evidence"), str)
        else Path()
    )
    setup_evidence = _read_canonical_document(
        setup_evidence_path,
        label="setup_evidence",
    )
    if (
        not isinstance(setup_evidence, Mapping)
        or canonical_sha256(dict(setup_evidence))
        != row.bindings.setup_evidence_digest
        or setup_evidence.get("repository_revision_digest")
        != _repository_revision(request).digest
    ):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "setup_evidence_binding_invalid",
        )
    expected_evidence = _evidence_manifest_record(
        request,
        row=row,
        mode=mode,
        baseline_path=baseline_path,
        setup_evidence_path=setup_evidence_path,
        child_state_path=child_state_path,
        request_path=request_path,
        child_result_path=child_result_path,
        delta_path=delta_path,
        accounting_path=accounting_path,
        result_envelope_digest=canonical_sha256(envelope),
        final_workspace_digest=final_manifest.digest,
    )
    if (
        dict(evidence) != expected_evidence
        or canonical_sha256(dict(evidence)) != row.bindings.evidence_manifest_digest
    ):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "evidence_manifest_binding_invalid",
        )
    return envelope, artifacts


def validate_completed_run_ref_authority(
    request: RunRefRuntimeRequest,
    *,
    settled_result: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    reconcile_pending: bool,
) -> RunRefExecutionResult:
    """Validate exact completed authority and select it for zero-launch reuse."""

    if type(request) is not RunRefRuntimeRequest:
        raise TypeError("request must be an exact RunRefRuntimeRequest")
    if not isinstance(settled_result, Mapping) or not isinstance(artifacts, Mapping):
        raise TypeError("settled_result and artifacts must be mappings")
    if type(reconcile_pending) is not bool:
        raise TypeError("reconcile_pending must be a bool")
    try:
        settled = settled_result_binding_from_record(settled_result)
        observed: list[tuple[dict[str, Any], dict[str, Any]]] = []

        def validate(row: RunRefAttemptRecord) -> None:
            observed.append(_validate_bound_authority(request, row))

        if reconcile_pending:
            reconcile_pending_parent_commit(
                request.ledger_path,
                settled_result=settled,
                current_step_config_digest=request.step_config.step_config_digest,
                validate_bound_authority=validate,
            )
        committed = select_committed_reuse(
            request.ledger_path,
            settled_result=settled,
            current_step_config_digest=request.step_config.step_config_digest,
            validate_bound_authority=validate,
        )
    except RunRefLedgerError as exc:
        raise RunRefRuntimeError("run_ref_ledger_invalid", str(exc)) from exc
    except RunRefDeltaError as exc:
        raise RunRefRuntimeError(
            "run_ref_delta_capture_failed",
            ",".join(exc.secondary_causes),
        ) from exc
    if not observed:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "authority_validation_not_executed",
        )
    envelope, rebuilt_artifacts = observed[-1]
    if dict(artifacts) != rebuilt_artifacts:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "persisted_artifacts_binding_invalid",
        )
    return RunRefExecutionResult(
        envelope=envelope,
        artifacts=rebuilt_artifacts,
        settled_result=settled,
        committed_row_digest=committed.row_digest,
        reused=True,
    )


def recover_run_ref_settlement(
    request: RunRefRuntimeRequest,
    *,
    settled_result: Mapping[str, Any],
    reconcile_pending: bool,
    effect_instance_digest: str | None = None,
) -> RunRefExecutionResult:
    """Rebuild exact E1 result authority for a durable nested caller boundary."""

    if type(request) is not RunRefRuntimeRequest:
        raise TypeError("request must be an exact RunRefRuntimeRequest")
    if not isinstance(settled_result, Mapping):
        raise TypeError("settled_result must be a mapping")
    if type(reconcile_pending) is not bool:
        raise TypeError("reconcile_pending must be a bool")
    try:
        settled = settled_result_binding_from_record(settled_result)
        observed: list[tuple[dict[str, Any], dict[str, Any]]] = []

        def validate(row: RunRefAttemptRecord) -> None:
            observed.append(
                _validate_bound_authority(
                    request,
                    row,
                    effect_instance_digest=effect_instance_digest,
                )
            )

        if reconcile_pending:
            reconcile_pending_parent_commit(
                request.ledger_path,
                settled_result=settled,
                current_step_config_digest=request.step_config.step_config_digest,
                validate_bound_authority=validate,
            )
        committed = select_committed_reuse(
            request.ledger_path,
            settled_result=settled,
            current_step_config_digest=request.step_config.step_config_digest,
            validate_bound_authority=validate,
        )
    except RunRefLedgerError as exc:
        raise RunRefRuntimeError("run_ref_ledger_invalid", str(exc)) from exc
    except RunRefDeltaError as exc:
        raise RunRefRuntimeError(
            "run_ref_delta_capture_failed",
            ",".join(exc.secondary_causes),
        ) from exc
    if not observed:
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "authority_validation_not_executed",
        )
    envelope, artifacts = observed[-1]
    return RunRefExecutionResult(
        envelope=envelope,
        artifacts=artifacts,
        settled_result=settled,
        committed_row_digest=committed.row_digest,
        reused=True,
    )


def finalize_run_ref_parent_commit(
    request: RunRefRuntimeRequest,
    prepared: PreparedRunRefSettlement,
    *,
    persisted_settled_result: Mapping[str, Any],
    dependencies: RunRefRuntimeDependencies | None = None,
    effect_instance_digest: str | None = None,
) -> RunRefExecutionResult:
    """Validate the caller's atomic settlement and append the commit edge."""

    if type(request) is not RunRefRuntimeRequest:
        raise TypeError("request must be an exact RunRefRuntimeRequest")
    if type(prepared) is not PreparedRunRefSettlement:
        raise TypeError("prepared must be an exact PreparedRunRefSettlement")
    if not isinstance(persisted_settled_result, Mapping):
        raise TypeError("persisted_settled_result must be a mapping")
    effects = dependencies or RunRefRuntimeDependencies()
    try:
        persisted = settled_result_binding_from_record(persisted_settled_result)
    except RunRefLedgerError as exc:
        raise RunRefRuntimeError("run_ref_ledger_invalid", str(exc)) from exc
    if (
        persisted != prepared.settled_result
        or prepared.ledger_path != request.ledger_path
        or prepared.evidence_manifest_path
        != prepared.settled_result.workspace_path.parent / _EVIDENCE_FILENAME
    ):
        raise RunRefRuntimeError(
            "run_ref_ledger_invalid",
            "persisted_parent_settlement_disagrees",
        )
    try:
        ledger = load_attempt_ledger(request.ledger_path)
    except RunRefLedgerError as exc:
        raise RunRefRuntimeError("run_ref_ledger_invalid", str(exc)) from exc
    pending = [
        row
        for row in ledger.rows
        if row.row_digest == persisted.pending_row_digest
    ]
    if len(pending) != 1:
        raise RunRefRuntimeError(
            "run_ref_ledger_invalid",
            "pending_parent_settlement_ambiguous",
        )
    envelope, artifacts = _validate_bound_authority(
        request,
        pending[0],
        effect_instance_digest=effect_instance_digest,
    )
    if envelope != dict(prepared.envelope) or artifacts != dict(prepared.artifacts):
        raise RunRefRuntimeError(
            "run_ref_evidence_invalid",
            "prepared_parent_settlement_disagrees",
        )
    effects.crash_hook("parent_commit")
    try:
        committed = reconcile_pending_parent_commit(
            request.ledger_path,
            settled_result=persisted,
            current_step_config_digest=request.step_config.step_config_digest,
            validate_bound_authority=lambda row: _validate_bound_authority(
                request,
                row,
                effect_instance_digest=effect_instance_digest,
            ),
        )
    except RunRefLedgerError as exc:
        raise RunRefRuntimeError("run_ref_ledger_invalid", str(exc)) from exc
    return RunRefExecutionResult(
        envelope=envelope,
        artifacts=artifacts,
        settled_result=persisted,
        committed_row_digest=committed.row_digest,
        reused=False,
    )


def reuse_run_ref_settlement(
    request: RunRefRuntimeRequest,
    *,
    settled_result: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    reconcile_pending: bool = True,
) -> RunRefExecutionResult:
    """Compatibility spelling for completed-authority validation and reuse."""

    return validate_completed_run_ref_authority(
        request,
        settled_result=settled_result,
        artifacts=artifacts,
        reconcile_pending=reconcile_pending,
    )


__all__ = [
    "RUN_REF_EVIDENCE_MANIFEST_SCHEMA",
    "RUN_REF_LIFECYCLE_EVENT_SCHEMA",
    "ParentBundleOrphanPreimage",
    "PreparedRunRefSettlement",
    "RunRefChildLaunch",
    "RunRefChildProcessResult",
    "RunRefExecutionResult",
    "RunRefLifecycleAcknowledgement",
    "RunRefLifecycleAllocation",
    "RunRefLifecycleDeadlineExceeded",
    "RunRefLifecycleEvent",
    "RunRefRuntimeDependencies",
    "RunRefRuntimeError",
    "RunRefRuntimeRequest",
    "acknowledge_persisted_run_ref_lifecycle_event",
    "build_run_ref_accounting",
    "declared_artifacts_from_value",
    "drive_run_ref_lifecycle",
    "extract_run_ref_value",
    "finalize_run_ref_parent_commit",
    "flatten_run_ref_result_artifacts",
    "persist_run_ref_lifecycle_event",
    "preflight_run_ref_runtime_request",
    "prepare_run_ref_settlement",
    "recover_run_ref_settlement",
    "resolve_run_ref_inputs",
    "resolve_run_ref_parent_input_values",
    "resolve_run_ref_parent_input_values_for_config",
    "reuse_run_ref_settlement",
    "select_run_ref_lifecycle_allocation",
    "validate_completed_run_ref_authority",
    "validate_run_ref_lifecycle_attempt_authority",
    "validate_run_ref_lifecycle_allocation",
]
