"""Canonical AST and pytest-capture primitives for feasibility proofs.

This module owns canonical evidence primitives, authenticated remote-free Git
object reads, deterministic addition-only tree synthesis, authenticated AST
edge facts, immutable pytest execution-ledger records, one pinned,
origin-isolated pytest subprocess producer for those records, and the closed
capture materialization, validation, review-gated purge, and tombstone
lifecycle. It intentionally owns no selector or disposition authority. Later
feasibility mechanics consume these primitives without weakening their
fail-closed evidence boundary.
"""

from __future__ import annotations

import ast
import base64
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence

import pytest


RUNNER_RELATIVE_PATH = "scripts/experiments/es/feasibility_proofs.py"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_EMPTY_GIT_TREE_OID = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_PROMISOR_CONFIG_RE = re.compile(
    r"(?:extensions\.partialclone|remote\..+\.(?:promisor|partialclonefilter))\Z"
)
_EXECUTABLE_BINDING_KEYS = frozenset(
    {"literal_path", "real_path", "sha256", "version_argv", "version_output"}
)
_EXECUTABLE_VERSION_TIMEOUT_SECONDS = 5.0
_GIT_OBJECT_BATCH_LIMIT = 64
_FEASIBILITY_CAPTURE_SCHEMA_VERSION = "es_f1_feasibility_capture_manifest.v1"
_FEASIBILITY_CAPTURE_LIFECYCLE = "retained_pending_ordered_reviews"
_FEASIBILITY_CLUSTER_DOMAIN = (
    "IDENTITY_CONFIG",
    "CONSTRUCTION_ADAPTERS",
    "TRAINING_OPTIMIZER",
    "PERSISTENCE_REBUILD",
    "INFERENCE_WORKFLOWS",
    "CONSUMER_BYPASS",
)
_FEASIBILITY_IMPLEMENTED_CLUSTERS = (
    "IDENTITY_CONFIG",
    "CONSTRUCTION_ADAPTERS",
    "PERSISTENCE_REBUILD",
    "INFERENCE_WORKFLOWS",
)
_FEASIBILITY_VARIANT_IDS = (
    "full",
    "test_only",
    *(f"remove_one:{value}" for value in _FEASIBILITY_IMPLEMENTED_CLUSTERS),
)
_FEASIBILITY_LEDGER_ROLES = (
    "collection",
    *("baseline" for _ in range(4)),
    "green",
    "green",
    *("remove_one" for _ in range(4)),
    "adjacent",
)
_FEASIBILITY_LEDGER_RELATIVE_PATHS = (
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/00-collection.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/01-baseline-identity-config.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/02-baseline-construction-adapters.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/03-baseline-persistence-rebuild.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/04-baseline-inference-workflows.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/05-green-first.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/06-green-second.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/07-remove-one-identity-config.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/08-remove-one-construction-adapters.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/09-remove-one-persistence-rebuild.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/10-remove-one-inference-workflows.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture/ledgers/11-adjacent.json",
)
_FEASIBILITY_ADJACENT_NODE_IDS = (
    "tests/torch/test_workflows_components.py::"
    "TestWorkflowsComponentsTraining::test_lightning_training_respects_gridsize",
    "tests/torch/test_workflows_components.py::"
    "TestTrainWithLightningRed::test_train_with_lightning_instantiates_module",
)
_FEASIBILITY_CAPTURE_VOLATILE_FIELDS = (
    "captured_at",
    "ledgers.*.elapsed_ns",
    "ledgers.*.sha256",
)
_FEASIBILITY_CAPTURE_MANIFEST_RELATIVE = (
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture-manifest.json"
)
_FEASIBILITY_ORDERED_REVIEW_CONTRACTS = (
    (
        "specification",
        "artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md",
        b"ES_F1_SCOPE_AMENDMENT_PLAN_SPEC_APPROVED",
    ),
    (
        "quality",
        "artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md",
        b"ES_F1_SCOPE_AMENDMENT_PLAN_QUALITY_APPROVED",
    ),
)
_FEASIBILITY_REQUIRED_REVIEW_FINDINGS = (
    b"anti_padding_accepted",
    b"non_synthetic_baseline_and_remove_one_failures_accepted",
    b"three_authenticated_ast_trace_cross_blob_edges_accepted",
    b"four_independently_unmet_clusters_accepted",
    b"non_collapse_requirement_accepted",
    b"strict_reference_size_gate_5000_10000_deferred_to_task_3a",
    b"operational_criterion_not_a_universal_provider_context_theorem",
)
_FEASIBILITY_AUTHORITY_BINDING_KEYS = frozenset(
    {
        "plan_sha256",
        "preedit_policy_sha256",
        "source_census_sha256",
        "selector_manifest_sha256",
        "a1_anchor_sha256",
    }
)
_FEASIBILITY_FROZEN_BASE = {
    "repository": (
        "/home/ollie/.local/state/orchestrator/es-source-projections/git-sha1/"
        "8f191031f233d50a4d020d8a988036e99487f570"
    ),
    "commit": "8f191031f233d50a4d020d8a988036e99487f570",
    "tree": "e64f3c05f5a0894f41c047d128a9040a2cda6764",
    "inventory_sha256": (
        "sha256:6fc936c54977d9adc7bdbae02bfa69592c55722e5cf5eddbd1b958ee1bc71404"
    ),
    "leaf_count": 1948,
}
_FEASIBILITY_GIT_IDENTITY = {
    "literal_path": "/usr/bin/git",
    "real_path": "/usr/bin/git",
    "sha256": (
        "sha256:2a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668"
    ),
    "version_argv": ["/usr/bin/git", "--version"],
    "version_output": "git version 2.43.0\n",
}
_FEASIBILITY_PYTHON_IDENTITY = {
    "literal_path": "/home/ollie/miniconda3/envs/ptycho311/bin/python",
    "real_path": "/home/ollie/miniconda3/envs/ptycho311/bin/python3.11",
    "sha256": (
        "sha256:d575ac63749e61ede79bc20518113452b114506ceec0af0cf3993b0fcc486cb0"
    ),
    "version_argv": [
        "/home/ollie/miniconda3/envs/ptycho311/bin/python",
        "--version",
    ],
    "version_output": "Python 3.11.13\n",
}
_FEASIBILITY_BWRAP_IDENTITY = {
    "literal_path": "/usr/bin/bwrap",
    "real_path": "/usr/bin/bwrap",
    "sha256": (
        "sha256:52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712"
    ),
    "version_argv": ["/usr/bin/bwrap", "--version"],
    "version_output": "bubblewrap 0.9.0\n",
}
_PYTEST_LEDGER_SCHEMA_VERSION = "pytest_execution_ledger.v1"
_PYTEST_LEDGER_ROLES = frozenset(
    {"collection", "baseline", "green", "remove_one", "adjacent"}
)
_PYTEST_LEDGER_SLICE_ROLES = frozenset({"baseline", "remove_one"})
_PYTEST_LEDGER_OUTCOMES = frozenset({"passed", "failed", "skipped", "error"})
_PYTEST_LEDGER_FAILURE_PHASES = frozenset(
    {"setup", "call", "teardown", "collection"}
)
_PYTEST_LEDGER_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "ledger_id",
        "ordinal",
        "role",
        "role_index",
        "slice_id",
        "runner_sha256",
        "git",
        "python",
        "variant_id",
        "project_root",
        "cwd",
        "argv",
        "execution_envelope",
        "environment",
        "expected_tree",
        "pre_tree",
        "post_tree",
        "collected_node_ids",
        "node_outcomes",
        "outcome_counts",
        "exit_code",
        "project_origins",
        "call_transitions",
        "elapsed_ns",
        "deterministic_sha256",
        "record_sha256",
    }
)
_PYTEST_LEDGER_EXECUTABLE_KEYS = frozenset(
    {"literal_path", "real_path", "sha256", "version_argv", "version_output"}
)
_PYTEST_LEDGER_NODE_OUTCOME_KEYS = frozenset(
    {"node_id", "outcome", "failure_phase"}
)
_PYTEST_LEDGER_OUTCOME_COUNT_KEYS = frozenset(
    {"passed", "failed", "skipped", "errors"}
)
_PYTEST_LEDGER_PROJECT_ORIGIN_KEYS = frozenset(
    {"module_name", "resolved_path"}
)
_PYTEST_LEDGER_CALL_TRANSITION_KEYS = frozenset(
    {
        "edge_id",
        "pytest_node_id",
        "outcome",
        "caller_path",
        "caller_line",
        "callee_path",
        "callee_name",
        "callee_first_line",
        "callee_line_hits",
    }
)
_PYTEST_LEDGER_EXECUTION_ENVELOPE_KEYS = frozenset(
    {
        "kind",
        "launcher",
        "launcher_argv",
        "runtime_project_root",
        "home_root",
        "tmp_root",
        "writable_mounts",
    }
)
_PYTEST_LEDGER_WRITABLE_MOUNT_KEYS = frozenset(
    {"relative_path", "host_path", "pre_tree", "post_tree"}
)
_PYTEST_CAPTURE_SCHEMA_VERSION = "pytest_capture_worker.v1"
_PYTEST_CAPTURE_REQUEST_SCHEMA_VERSION = "pytest_capture_request.v1"
_PYTEST_CAPTURE_PROTOCOL_ENV = "ORC_FEASIBILITY_PYTEST_CAPTURE_PROTOCOL"
_PYTEST_CAPTURE_PROTOCOL_VERSION = "1"
_PYTEST_CAPTURE_REQUEST_ENV = "ORC_FEASIBILITY_PYTEST_CAPTURE_REQUEST_B64"
_PYTEST_CAPTURE_PLUGIN = "scripts.experiments.es.feasibility_proofs"
_PYTEST_CAPTURE_REQUIRED_ENVIRONMENT = {
    "CUDA_VISIBLE_DEVICES": "",
    "LANG": "C",
    "LC_ALL": "C",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}
_PYTEST_CAPTURE_SENTINEL = b"__ORC_FEASIBILITY_PYTEST_CAPTURE_V1__:"
_BWRAP_RUNTIME_PROJECT_ROOT = "/run/orc-pytest-project"
_BWRAP_RUNTIME_HOME_ROOT = "/run/orc-pytest-home"
_PYTEST_CAPTURE_RESPONSE_KEYS = frozenset(
    {
        "schema_version",
        "runner_path",
        "runner_sha256",
        "project_root",
        "cwd",
        "collected_node_ids",
        "node_outcomes",
        "outcome_counts",
        "project_origins",
        "call_transitions",
        "exit_code",
        "collection_errors",
        "worker_errors",
    }
)
_PYTEST_CAPTURE_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "project_root",
        "runtime_project_root",
        "role",
        "call_trace_specs",
    }
)
_PYTEST_CAPTURE_TRACE_SPEC_KEYS = frozenset(
    {
        "edge_id",
        "pytest_node_id",
        "caller_path",
        "caller_line",
        "callee_path",
        "callee_name",
        "callee_first_line",
    }
)


class FeasibilityProofError(ValueError):
    """One feasibility evidence byte or identity check failed closed."""

    def __init__(self, code: str, detail: object = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail != "" else code)


@dataclass(frozen=True)
class GitObject:
    """One object read and independently authenticated from a bare store."""

    oid: str
    object_type: str
    payload: bytes


@dataclass(frozen=True, order=True)
class TreeLeaf:
    """One authenticated blob leaf from a Git tree."""

    path: str
    mode: str
    blob_oid: str


@dataclass(frozen=True, order=True)
class OverlayRow:
    """One closed regular-file addition supplied by the primary store."""

    path: str
    mode: str
    blob_oid: str


@dataclass(frozen=True)
class DerivedTree:
    """One deterministic tree derivation without object-store writes."""

    tree_oid: str
    leaves: tuple[TreeLeaf, ...]
    generated_tree_objects: tuple[GitObject, ...]


@dataclass(frozen=True)
class OverlaySlice:
    """One named, ordered partition slice of overlay paths."""

    slice_id: str
    ordinal: int
    paths: tuple[str, ...]


@dataclass(frozen=True)
class TreeVariant:
    """One deterministic full, test-only, or remove-one derivation."""

    variant_id: str
    included_overlay_paths: tuple[str, ...]
    omitted_cluster_id: str | None
    tree: DerivedTree


@dataclass(frozen=True, order=True)
class NumstatRow:
    """One strict-text addition-only physical-line delta row."""

    path: str
    additions: int
    deletions: int
    physical_line_count: int


@dataclass(frozen=True)
class AstSpan:
    """One exact Python AST source span using CPython coordinate semantics."""

    start_line: int
    start_column: int
    end_line: int
    end_column: int


@dataclass(frozen=True)
class AstNodeRef:
    """One authenticated Python AST node in a primary overlay blob."""

    path: str
    blob_oid: str
    node_type: str
    name: str
    span: AstSpan


@dataclass(frozen=True)
class DirectedAstEdge:
    """One directed producer-definition to consumer-callsite edge."""

    edge_id: str
    producer: AstNodeRef
    consumer: AstNodeRef
    pytest_node_id: str


@dataclass(frozen=True)
class CallTransition:
    """One passing runtime caller-to-callee observation for an AST edge."""

    edge_id: str
    pytest_node_id: str
    outcome: str
    caller_path: str
    caller_line: int
    callee_path: str
    callee_name: str
    callee_first_line: int
    callee_line_hits: tuple[int, ...]


@dataclass(frozen=True, order=True)
class CallTraceSpec:
    """One exact Python caller-to-callee transition requested from pytest."""

    edge_id: str
    pytest_node_id: str
    caller_path: str
    caller_line: int
    callee_path: str
    callee_name: str
    callee_first_line: int


@dataclass(frozen=True)
class ExecutableIdentity:
    """One exact executable identity recorded by a pytest execution."""

    literal_path: str
    real_path: str
    sha256: str
    version_argv: tuple[str, ...]
    version_output: str


@dataclass(frozen=True)
class OutcomeCounts:
    """Exact aggregate pytest outcomes for one execution."""

    passed: int
    failed: int
    skipped: int
    errors: int


@dataclass(frozen=True)
class NodeOutcome:
    """One collected pytest node's terminal outcome."""

    node_id: str
    outcome: str
    failure_phase: str | None


@dataclass(frozen=True)
class ProjectOrigin:
    """One imported project module and its resolved absolute path."""

    module_name: str
    resolved_path: str


@dataclass(frozen=True, order=True)
class WritableMountSpec:
    """One caller-declared project-relative writable mount binding."""

    relative_path: str
    host_path: str


@dataclass(frozen=True, order=True)
class WritableMountEvidence:
    """One exact external writable mount delta observed around pytest."""

    relative_path: str
    host_path: str
    pre_tree: str
    post_tree: str


@dataclass(frozen=True)
class PytestExecutionEnvelope:
    """Exact direct or read-only-project launcher used for one pytest run."""

    kind: str
    launcher: ExecutableIdentity | None
    launcher_argv: tuple[str, ...]
    runtime_project_root: str
    home_root: str | None
    tmp_root: str | None
    writable_mounts: tuple[WritableMountEvidence, ...]


@dataclass(frozen=True)
class PytestLedgerAuthority:
    """Caller-owned static authority for one sealed pytest execution ledger."""

    ledger_id: str
    ordinal: int
    role: str
    role_index: int
    slice_id: str | None
    runner_path: str
    runner_sha256: str
    git: ExecutableIdentity
    python: ExecutableIdentity
    variant_id: str
    project_root: str
    expected_tree: str
    argv: tuple[str, ...]
    execution_envelope: PytestExecutionEnvelope
    expected_project_origins: tuple[ProjectOrigin, ...]
    call_trace_specs: tuple[CallTraceSpec, ...]


@dataclass(frozen=True)
class PytestExecutionLedger:
    """Semantic fields for one immutable pytest execution ledger."""

    ledger_id: str
    ordinal: int
    role: str
    role_index: int
    slice_id: str | None
    runner_sha256: str
    git: ExecutableIdentity
    python: ExecutableIdentity
    variant_id: str
    project_root: str
    cwd: str
    argv: tuple[str, ...]
    execution_envelope: PytestExecutionEnvelope
    environment: tuple[tuple[str, str], ...]
    expected_tree: str
    pre_tree: str
    post_tree: str
    collected_node_ids: tuple[str, ...]
    node_outcomes: tuple[NodeOutcome, ...]
    outcome_counts: OutcomeCounts
    exit_code: int
    project_origins: tuple[ProjectOrigin, ...]
    call_transitions: tuple[CallTransition, ...]
    elapsed_ns: int


def _reject_float(value: str) -> NoReturn:
    raise FeasibilityProofError("feasibility_json_value_invalid", value)


def _reject_constant(value: str) -> NoReturn:
    raise FeasibilityProofError("feasibility_json_value_invalid", value)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FeasibilityProofError("feasibility_json_duplicate_key", key)
        result[key] = value
    return result


def _validate_json_value(value: object, *, label: str) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise FeasibilityProofError(
                "feasibility_json_value_invalid",
                label,
            ) from exc
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json_value(item, label=f"{label}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise FeasibilityProofError(
                    "feasibility_json_value_invalid",
                    f"{label}.key",
                )
            _validate_json_value(key, label=f"{label}.key")
            _validate_json_value(item, label=f"{label}.{key}")
        return
    raise FeasibilityProofError(
        "feasibility_json_value_invalid",
        f"{label}:{type(value).__name__}",
    )


def canonical_json_bytes(value: object) -> bytes:
    """Return sorted ASCII JSON in the integer-only domain with one final LF."""

    _validate_json_value(value, label="record")
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8", "strict")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise FeasibilityProofError(
            "feasibility_json_value_invalid",
            str(exc),
        ) from exc


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _pytest_ledger_invalid(detail: object = "") -> NoReturn:
    raise FeasibilityProofError("feasibility_pytest_ledger_invalid", detail)


def _validate_pytest_ledger_text(value: object, *, label: str) -> str:
    if type(value) is not str or not value:
        _pytest_ledger_invalid(label)
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_ledger_invalid",
            label,
        ) from exc
    return value


def _validate_pytest_ledger_int(
    value: object,
    *,
    label: str,
    minimum: int | None = None,
) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        _pytest_ledger_invalid(label)
    return value


def _validate_pytest_ledger_absolute_path(
    value: object,
    *,
    label: str,
) -> str:
    text = _validate_pytest_ledger_text(value, label=label)
    try:
        path = Path(text)
        normalized = os.path.normpath(text)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_ledger_invalid",
            label,
        ) from exc
    if (
        "\0" in text
        or not path.is_absolute()
        or text.startswith("//")
        or normalized != text
    ):
        _pytest_ledger_invalid(label)
    return text


def _validate_pytest_executable_identity(
    value: object,
    *,
    label: str,
) -> ExecutableIdentity:
    if type(value) is not ExecutableIdentity:
        _pytest_ledger_invalid(label)
    literal_path = _validate_pytest_ledger_absolute_path(
        value.literal_path,
        label=f"{label}.literal_path",
    )
    _validate_pytest_ledger_absolute_path(
        value.real_path,
        label=f"{label}.real_path",
    )
    if type(value.sha256) is not str or _SHA256_RE.fullmatch(value.sha256) is None:
        _pytest_ledger_invalid(f"{label}.sha256")
    if type(value.version_argv) is not tuple or not value.version_argv:
        _pytest_ledger_invalid(f"{label}.version_argv")
    for index, item in enumerate(value.version_argv):
        _validate_pytest_ledger_text(
            item,
            label=f"{label}.version_argv[{index}]",
        )
    if value.version_argv[0] != literal_path:
        _pytest_ledger_invalid(f"{label}.version_argv[0]")
    _validate_pytest_ledger_text(
        value.version_output,
        label=f"{label}.version_output",
    )
    return value


def _validate_pytest_outcome_counts(value: object) -> OutcomeCounts:
    if type(value) is not OutcomeCounts:
        _pytest_ledger_invalid("outcome_counts")
    for name in ("passed", "failed", "skipped", "errors"):
        _validate_pytest_ledger_int(
            getattr(value, name),
            label=f"outcome_counts.{name}",
            minimum=0,
        )
    return value


def _validate_pytest_node_outcome(
    value: object,
    *,
    label: str,
) -> NodeOutcome:
    if type(value) is not NodeOutcome:
        _pytest_ledger_invalid(label)
    _validate_pytest_ledger_text(value.node_id, label=f"{label}.node_id")
    outcome = _validate_pytest_ledger_text(
        value.outcome,
        label=f"{label}.outcome",
    )
    if outcome not in _PYTEST_LEDGER_OUTCOMES:
        _pytest_ledger_invalid(f"{label}.outcome")
    if outcome in {"passed", "skipped"}:
        if value.failure_phase is not None:
            _pytest_ledger_invalid(f"{label}.failure_phase")
    elif (
        type(value.failure_phase) is not str
        or value.failure_phase not in _PYTEST_LEDGER_FAILURE_PHASES
    ):
        _pytest_ledger_invalid(f"{label}.failure_phase")
    return value


def _expected_bwrap_launcher_argv(
    *,
    launcher_path: str,
    project_root: str,
    home_root: str,
    tmp_root: str,
    writable_mounts: tuple[WritableMountEvidence, ...],
    target_argv: tuple[str, ...],
) -> tuple[str, ...]:
    argv: list[str] = [
        launcher_path,
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--dev-bind",
        "/dev",
        "/dev",
        "--tmpfs",
        "/run",
        "--dir",
        _BWRAP_RUNTIME_HOME_ROOT,
        "--bind",
        home_root,
        _BWRAP_RUNTIME_HOME_ROOT,
        "--dir",
        _BWRAP_RUNTIME_PROJECT_ROOT,
        "--ro-bind",
        project_root,
        _BWRAP_RUNTIME_PROJECT_ROOT,
    ]
    for mount in writable_mounts:
        argv.extend(
            (
                "--bind",
                mount.host_path,
                f"{_BWRAP_RUNTIME_PROJECT_ROOT}/{mount.relative_path}",
            )
        )
    argv.extend(
        (
            "--bind",
            tmp_root,
            "/tmp",
            "--chdir",
            _BWRAP_RUNTIME_PROJECT_ROOT,
            "--",
            *target_argv,
        )
    )
    return tuple(argv)


def _validate_pytest_execution_envelope(
    value: object,
    *,
    project_root: str,
    target_argv: tuple[str, ...],
) -> PytestExecutionEnvelope:
    if type(value) is not PytestExecutionEnvelope:
        _pytest_ledger_invalid("execution_envelope")
    kind = _validate_pytest_ledger_text(
        value.kind,
        label="execution_envelope.kind",
    )
    if type(value.launcher_argv) is not tuple or not value.launcher_argv:
        _pytest_ledger_invalid("execution_envelope.launcher_argv")
    for index, item in enumerate(value.launcher_argv):
        _validate_pytest_ledger_text(
            item,
            label=f"execution_envelope.launcher_argv[{index}]",
        )
    if type(value.writable_mounts) is not tuple:
        _pytest_ledger_invalid("execution_envelope.writable_mounts")
    if kind == "direct":
        if (
            value.launcher is not None
            or value.launcher_argv != target_argv
            or value.runtime_project_root != project_root
            or value.home_root is not None
            or value.tmp_root is not None
            or value.writable_mounts
        ):
            _pytest_ledger_invalid("execution_envelope")
        return value
    if kind != "bwrap_ro_project.v1" or not value.writable_mounts:
        _pytest_ledger_invalid("execution_envelope.kind")
    launcher = _validate_pytest_executable_identity(
        value.launcher,
        label="execution_envelope.launcher",
    )
    runtime_project_root = _validate_pytest_ledger_absolute_path(
        value.runtime_project_root,
        label="execution_envelope.runtime_project_root",
    )
    if runtime_project_root != _BWRAP_RUNTIME_PROJECT_ROOT:
        _pytest_ledger_invalid("execution_envelope.runtime_project_root")
    home_root = _validate_pytest_ledger_absolute_path(
        value.home_root,
        label="execution_envelope.home_root",
    )
    tmp_root = _validate_pytest_ledger_absolute_path(
        value.tmp_root,
        label="execution_envelope.tmp_root",
    )
    if home_root == tmp_root:
        _pytest_ledger_invalid("execution_envelope.roots")
    external_paths = [home_root, tmp_root]
    mounts: list[WritableMountEvidence] = []
    for index, mount in enumerate(value.writable_mounts):
        if type(mount) is not WritableMountEvidence:
            _pytest_ledger_invalid(f"execution_envelope.writable_mounts[{index}]")
        try:
            _split_leaf_path(mount.relative_path)
        except FeasibilityProofError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_ledger_invalid",
                f"execution_envelope.writable_mounts[{index}].relative_path",
            ) from exc
        host_path = _validate_pytest_ledger_absolute_path(
            mount.host_path,
            label=f"execution_envelope.writable_mounts[{index}].host_path",
        )
        for name in ("pre_tree", "post_tree"):
            digest = getattr(mount, name)
            if type(digest) is not str or _SHA1_RE.fullmatch(digest) is None:
                _pytest_ledger_invalid(
                    f"execution_envelope.writable_mounts[{index}].{name}"
                )
        external_paths.append(host_path)
        mounts.append(mount)
    relative_paths = tuple(item.relative_path for item in mounts)
    if (
        relative_paths
        != tuple(sorted(relative_paths, key=lambda item: item.encode("utf-8", "strict")))
        or len(set(relative_paths)) != len(relative_paths)
        or len(set(external_paths)) != len(external_paths)
    ):
        _pytest_ledger_invalid("execution_envelope.writable_mounts")
    project = Path(project_root)
    for external in external_paths:
        try:
            Path(external).relative_to(project)
        except ValueError:
            try:
                project.relative_to(Path(external))
            except ValueError:
                continue
        _pytest_ledger_invalid("execution_envelope.external_root")
    for index, left in enumerate(external_paths):
        for right in external_paths[index + 1 :]:
            try:
                Path(left).relative_to(Path(right))
            except ValueError:
                try:
                    Path(right).relative_to(Path(left))
                except ValueError:
                    continue
            _pytest_ledger_invalid("execution_envelope.external_root")
    expected_launcher_argv = _expected_bwrap_launcher_argv(
        launcher_path=launcher.literal_path,
        project_root=project_root,
        home_root=home_root,
        tmp_root=tmp_root,
        writable_mounts=tuple(mounts),
        target_argv=target_argv,
    )
    if value.launcher_argv != expected_launcher_argv:
        _pytest_ledger_invalid("execution_envelope.launcher_argv")
    return value


def _validate_pytest_execution_ledger_value(
    ledger: object,
) -> PytestExecutionLedger:
    if type(ledger) is not PytestExecutionLedger:
        _pytest_ledger_invalid("ledger")
    _validate_pytest_ledger_text(ledger.ledger_id, label="ledger_id")
    _validate_pytest_ledger_int(ledger.ordinal, label="ordinal", minimum=0)
    role = _validate_pytest_ledger_text(ledger.role, label="role")
    if role not in _PYTEST_LEDGER_ROLES:
        _pytest_ledger_invalid("role")
    _validate_pytest_ledger_int(
        ledger.role_index,
        label="role_index",
        minimum=0,
    )
    if role in _PYTEST_LEDGER_SLICE_ROLES:
        _validate_pytest_ledger_text(ledger.slice_id, label="slice_id")
    elif ledger.slice_id is not None:
        _pytest_ledger_invalid("slice_id")
    if (
        type(ledger.runner_sha256) is not str
        or _SHA256_RE.fullmatch(ledger.runner_sha256) is None
    ):
        _pytest_ledger_invalid("runner_sha256")
    _validate_pytest_executable_identity(ledger.git, label="git")
    _validate_pytest_executable_identity(ledger.python, label="python")
    _validate_pytest_ledger_text(ledger.variant_id, label="variant_id")
    project_root = _validate_pytest_ledger_absolute_path(
        ledger.project_root,
        label="project_root",
    )
    cwd = _validate_pytest_ledger_absolute_path(ledger.cwd, label="cwd")

    if type(ledger.argv) is not tuple or not ledger.argv:
        _pytest_ledger_invalid("argv")
    for index, item in enumerate(ledger.argv):
        _validate_pytest_ledger_text(item, label=f"argv[{index}]")
    execution_envelope = _validate_pytest_execution_envelope(
        ledger.execution_envelope,
        project_root=project_root,
        target_argv=ledger.argv,
    )
    if cwd != execution_envelope.runtime_project_root:
        _pytest_ledger_invalid("cwd")
    if type(ledger.environment) is not tuple:
        _pytest_ledger_invalid("environment")
    environment_keys: list[str] = []
    for index, item in enumerate(ledger.environment):
        if type(item) is not tuple or len(item) != 2:
            _pytest_ledger_invalid(f"environment[{index}]")
        key = _validate_pytest_ledger_text(
            item[0],
            label=f"environment[{index}].key",
        )
        if key == "CUDA_VISIBLE_DEVICES" and item[1] == "":
            pass
        else:
            _validate_pytest_ledger_text(
                item[1],
                label=f"environment[{index}].value",
            )
        environment_keys.append(key)
    expected_environment_keys = sorted(
        environment_keys,
        key=lambda item: item.encode("utf-8", "strict"),
    )
    if (
        environment_keys != expected_environment_keys
        or len(set(environment_keys)) != len(environment_keys)
    ):
        _pytest_ledger_invalid("environment")
    environment_values = dict(ledger.environment)
    for key, expected_value in _PYTEST_CAPTURE_REQUIRED_ENVIRONMENT.items():
        if environment_values.get(key) != expected_value:
            _pytest_ledger_invalid(f"environment.{key}")
    if execution_envelope.kind == "bwrap_ro_project.v1" and (
        environment_values.get("HOME") != _BWRAP_RUNTIME_HOME_ROOT
        or environment_values.get("TMPDIR") != "/tmp"
    ):
        _pytest_ledger_invalid("execution_envelope.environment")

    for name in ("expected_tree", "pre_tree", "post_tree"):
        value = getattr(ledger, name)
        if type(value) is not str or _SHA1_RE.fullmatch(value) is None:
            _pytest_ledger_invalid(name)
    if not (
        ledger.expected_tree == ledger.pre_tree == ledger.post_tree
    ):
        _pytest_ledger_invalid("tree_immutability")

    if type(ledger.collected_node_ids) is not tuple:
        _pytest_ledger_invalid("collected_node_ids")
    collected_node_ids: list[str] = []
    for index, node_id in enumerate(ledger.collected_node_ids):
        collected_node_ids.append(
            _validate_pytest_ledger_text(
                node_id,
                label=f"collected_node_ids[{index}]",
            )
        )
    if len(set(collected_node_ids)) != len(collected_node_ids):
        _pytest_ledger_invalid("collected_node_ids")

    if type(ledger.node_outcomes) is not tuple:
        _pytest_ledger_invalid("node_outcomes")
    node_outcomes: list[NodeOutcome] = []
    for index, value in enumerate(ledger.node_outcomes):
        node_outcomes.append(
            _validate_pytest_node_outcome(
                value,
                label=f"node_outcomes[{index}]",
            )
        )
    outcome_node_ids = [item.node_id for item in node_outcomes]
    if len(set(outcome_node_ids)) != len(outcome_node_ids):
        _pytest_ledger_invalid("node_outcomes")
    if any(item not in collected_node_ids for item in outcome_node_ids):
        _pytest_ledger_invalid("node_outcomes")
    outcome_node_id_set = set(outcome_node_ids)
    if outcome_node_ids != [
        item for item in collected_node_ids if item in outcome_node_id_set
    ]:
        _pytest_ledger_invalid("node_outcomes")

    outcome_counts = _validate_pytest_outcome_counts(ledger.outcome_counts)
    recomputed_counts = OutcomeCounts(
        passed=sum(item.outcome == "passed" for item in node_outcomes),
        failed=sum(item.outcome == "failed" for item in node_outcomes),
        skipped=sum(item.outcome == "skipped" for item in node_outcomes),
        errors=sum(item.outcome == "error" for item in node_outcomes),
    )
    if outcome_counts != recomputed_counts:
        _pytest_ledger_invalid("outcome_counts")
    _validate_pytest_ledger_int(ledger.exit_code, label="exit_code")

    if type(ledger.project_origins) is not tuple or not ledger.project_origins:
        _pytest_ledger_invalid("project_origins")
    origin_names: list[str] = []
    project_root_path = Path(project_root)
    for index, value in enumerate(ledger.project_origins):
        if type(value) is not ProjectOrigin:
            _pytest_ledger_invalid(f"project_origins[{index}]")
        module_name = _validate_pytest_ledger_text(
            value.module_name,
            label=f"project_origins[{index}].module_name",
        )
        resolved_path = _validate_pytest_ledger_absolute_path(
            value.resolved_path,
            label=f"project_origins[{index}].resolved_path",
        )
        try:
            Path(resolved_path).relative_to(project_root_path)
        except ValueError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_ledger_invalid",
                f"project_origins[{index}].resolved_path",
            ) from exc
        origin_names.append(module_name)
    expected_origin_names = sorted(
        origin_names,
        key=lambda item: item.encode("utf-8", "strict"),
    )
    if (
        origin_names != expected_origin_names
        or len(set(origin_names)) != len(origin_names)
    ):
        _pytest_ledger_invalid("project_origins")

    if type(ledger.call_transitions) is not tuple:
        _pytest_ledger_invalid("call_transitions")
    transitions: list[CallTransition] = []
    for index, value in enumerate(ledger.call_transitions):
        try:
            transition = _validate_call_transition(
                value,
                label=f"call_transitions[{index}]",
            )
        except FeasibilityProofError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_ledger_invalid",
                f"call_transitions[{index}]",
            ) from exc
        if transition.outcome != "passed":
            _pytest_ledger_invalid(f"call_transitions[{index}].outcome")
        transitions.append(transition)
    transition_keys = [
        (
            item.pytest_node_id.encode("utf-8", "strict"),
            item.edge_id.encode("utf-8", "strict"),
        )
        for item in transitions
    ]
    if (
        transition_keys != sorted(transition_keys)
        or len(set(transition_keys)) != len(transition_keys)
    ):
        _pytest_ledger_invalid("call_transitions")
    passed_node_ids = {
        item.node_id for item in node_outcomes if item.outcome == "passed"
    }
    if any(item.pytest_node_id not in passed_node_ids for item in transitions):
        _pytest_ledger_invalid("call_transitions")

    _validate_pytest_ledger_int(
        ledger.elapsed_ns,
        label="elapsed_ns",
        minimum=1,
    )
    if role == "collection":
        if (
            ledger.exit_code != 0
            or not collected_node_ids
            or node_outcomes
            or transitions
            or outcome_counts != OutcomeCounts(0, 0, 0, 0)
        ):
            _pytest_ledger_invalid("collection")
    elif not node_outcomes:
        _pytest_ledger_invalid("node_outcomes")
    return ledger


def _executable_identity_record(value: ExecutableIdentity) -> dict[str, object]:
    return {
        "literal_path": value.literal_path,
        "real_path": value.real_path,
        "sha256": value.sha256,
        "version_argv": list(value.version_argv),
        "version_output": value.version_output,
    }


def _call_transition_record(value: CallTransition) -> dict[str, object]:
    return {
        "edge_id": value.edge_id,
        "pytest_node_id": value.pytest_node_id,
        "outcome": value.outcome,
        "caller_path": value.caller_path,
        "caller_line": value.caller_line,
        "callee_path": value.callee_path,
        "callee_name": value.callee_name,
        "callee_first_line": value.callee_first_line,
        "callee_line_hits": list(value.callee_line_hits),
    }


def _pytest_execution_envelope_record(
    value: PytestExecutionEnvelope,
) -> dict[str, object]:
    return {
        "kind": value.kind,
        "launcher": (
            None
            if value.launcher is None
            else _executable_identity_record(value.launcher)
        ),
        "launcher_argv": list(value.launcher_argv),
        "runtime_project_root": value.runtime_project_root,
        "home_root": value.home_root,
        "tmp_root": value.tmp_root,
        "writable_mounts": [
            {
                "relative_path": item.relative_path,
                "host_path": item.host_path,
                "pre_tree": item.pre_tree,
                "post_tree": item.post_tree,
            }
            for item in value.writable_mounts
        ],
    }


def _pytest_execution_ledger_body(
    ledger: PytestExecutionLedger,
) -> dict[str, object]:
    return {
        "schema_version": _PYTEST_LEDGER_SCHEMA_VERSION,
        "ledger_id": ledger.ledger_id,
        "ordinal": ledger.ordinal,
        "role": ledger.role,
        "role_index": ledger.role_index,
        "slice_id": ledger.slice_id,
        "runner_sha256": ledger.runner_sha256,
        "git": _executable_identity_record(ledger.git),
        "python": _executable_identity_record(ledger.python),
        "variant_id": ledger.variant_id,
        "project_root": ledger.project_root,
        "cwd": ledger.cwd,
        "argv": list(ledger.argv),
        "execution_envelope": _pytest_execution_envelope_record(
            ledger.execution_envelope
        ),
        "environment": [list(item) for item in ledger.environment],
        "expected_tree": ledger.expected_tree,
        "pre_tree": ledger.pre_tree,
        "post_tree": ledger.post_tree,
        "collected_node_ids": list(ledger.collected_node_ids),
        "node_outcomes": [
            {
                "node_id": item.node_id,
                "outcome": item.outcome,
                "failure_phase": item.failure_phase,
            }
            for item in ledger.node_outcomes
        ],
        "outcome_counts": {
            "passed": ledger.outcome_counts.passed,
            "failed": ledger.outcome_counts.failed,
            "skipped": ledger.outcome_counts.skipped,
            "errors": ledger.outcome_counts.errors,
        },
        "exit_code": ledger.exit_code,
        "project_origins": [
            {
                "module_name": item.module_name,
                "resolved_path": item.resolved_path,
            }
            for item in ledger.project_origins
        ],
        "call_transitions": [
            _call_transition_record(item) for item in ledger.call_transitions
        ],
        "elapsed_ns": ledger.elapsed_ns,
    }


def _seal_pytest_execution_ledger_body(
    body: dict[str, object],
) -> dict[str, object]:
    deterministic_projection = dict(body)
    deterministic_projection.pop("elapsed_ns")
    body["deterministic_sha256"] = _sha256(
        canonical_json_bytes(deterministic_projection)
    )
    body["record_sha256"] = _sha256(canonical_json_bytes(body))
    return body


@pytest.hookimpl(optionalhook=True)
def pytest_execution_ledger_record(
    ledger: PytestExecutionLedger,
) -> dict[str, object]:
    """Build one canonical digest-bearing pytest execution-ledger record."""

    try:
        normalized = _validate_pytest_execution_ledger_value(ledger)
        return _seal_pytest_execution_ledger_body(
            _pytest_execution_ledger_body(normalized)
        )
    except FeasibilityProofError as exc:
        if exc.code == "feasibility_pytest_ledger_invalid":
            raise
        raise FeasibilityProofError(
            "feasibility_pytest_ledger_invalid",
            "ledger",
        ) from exc
    except (AttributeError, KeyError, TypeError, UnicodeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_ledger_invalid",
            "ledger",
        ) from exc


def _pytest_ledger_record_object(
    value: object,
    *,
    keys: frozenset[str],
    label: str,
) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        _pytest_ledger_invalid(label)
    return value


def _pytest_ledger_record_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        _pytest_ledger_invalid(label)
    return value


def _executable_identity_from_record(
    value: object,
    *,
    label: str,
) -> ExecutableIdentity:
    row = _pytest_ledger_record_object(
        value,
        keys=_PYTEST_LEDGER_EXECUTABLE_KEYS,
        label=label,
    )
    argv = _pytest_ledger_record_list(
        row["version_argv"],
        label=f"{label}.version_argv",
    )
    return ExecutableIdentity(
        literal_path=row["literal_path"],
        real_path=row["real_path"],
        sha256=row["sha256"],
        version_argv=tuple(argv),
        version_output=row["version_output"],
    )


def _pytest_execution_envelope_from_record(
    value: object,
) -> PytestExecutionEnvelope:
    row = _pytest_ledger_record_object(
        value,
        keys=_PYTEST_LEDGER_EXECUTION_ENVELOPE_KEYS,
        label="execution_envelope",
    )
    launcher_raw = row["launcher"]
    launcher = (
        None
        if launcher_raw is None
        else _executable_identity_from_record(
            launcher_raw,
            label="execution_envelope.launcher",
        )
    )
    launcher_argv = _pytest_ledger_record_list(
        row["launcher_argv"],
        label="execution_envelope.launcher_argv",
    )
    mount_rows = _pytest_ledger_record_list(
        row["writable_mounts"],
        label="execution_envelope.writable_mounts",
    )
    mounts: list[WritableMountEvidence] = []
    for index, value in enumerate(mount_rows):
        mount = _pytest_ledger_record_object(
            value,
            keys=_PYTEST_LEDGER_WRITABLE_MOUNT_KEYS,
            label=f"execution_envelope.writable_mounts[{index}]",
        )
        mounts.append(
            WritableMountEvidence(
                relative_path=mount["relative_path"],
                host_path=mount["host_path"],
                pre_tree=mount["pre_tree"],
                post_tree=mount["post_tree"],
            )
        )
    return PytestExecutionEnvelope(
        kind=row["kind"],
        launcher=launcher,
        launcher_argv=tuple(launcher_argv),
        runtime_project_root=row["runtime_project_root"],
        home_root=row["home_root"],
        tmp_root=row["tmp_root"],
        writable_mounts=tuple(mounts),
    )


def _pytest_execution_ledger_from_record(
    record: dict[str, object],
) -> PytestExecutionLedger:
    argv = _pytest_ledger_record_list(record["argv"], label="argv")
    environment_rows = _pytest_ledger_record_list(
        record["environment"],
        label="environment",
    )
    environment: list[tuple[object, object]] = []
    for index, value in enumerate(environment_rows):
        row = _pytest_ledger_record_list(
            value,
            label=f"environment[{index}]",
        )
        if len(row) != 2:
            _pytest_ledger_invalid(f"environment[{index}]")
        environment.append((row[0], row[1]))

    collected_node_ids = _pytest_ledger_record_list(
        record["collected_node_ids"],
        label="collected_node_ids",
    )
    outcome_rows = _pytest_ledger_record_list(
        record["node_outcomes"],
        label="node_outcomes",
    )
    node_outcomes: list[NodeOutcome] = []
    for index, value in enumerate(outcome_rows):
        row = _pytest_ledger_record_object(
            value,
            keys=_PYTEST_LEDGER_NODE_OUTCOME_KEYS,
            label=f"node_outcomes[{index}]",
        )
        node_outcomes.append(
            NodeOutcome(
                node_id=row["node_id"],
                outcome=row["outcome"],
                failure_phase=row["failure_phase"],
            )
        )
    count_row = _pytest_ledger_record_object(
        record["outcome_counts"],
        keys=_PYTEST_LEDGER_OUTCOME_COUNT_KEYS,
        label="outcome_counts",
    )

    origin_rows = _pytest_ledger_record_list(
        record["project_origins"],
        label="project_origins",
    )
    project_origins: list[ProjectOrigin] = []
    for index, value in enumerate(origin_rows):
        row = _pytest_ledger_record_object(
            value,
            keys=_PYTEST_LEDGER_PROJECT_ORIGIN_KEYS,
            label=f"project_origins[{index}]",
        )
        project_origins.append(
            ProjectOrigin(
                module_name=row["module_name"],
                resolved_path=row["resolved_path"],
            )
        )

    transition_rows = _pytest_ledger_record_list(
        record["call_transitions"],
        label="call_transitions",
    )
    transitions: list[CallTransition] = []
    for index, value in enumerate(transition_rows):
        row = _pytest_ledger_record_object(
            value,
            keys=_PYTEST_LEDGER_CALL_TRANSITION_KEYS,
            label=f"call_transitions[{index}]",
        )
        line_hits = _pytest_ledger_record_list(
            row["callee_line_hits"],
            label=f"call_transitions[{index}].callee_line_hits",
        )
        transitions.append(
            CallTransition(
                edge_id=row["edge_id"],
                pytest_node_id=row["pytest_node_id"],
                outcome=row["outcome"],
                caller_path=row["caller_path"],
                caller_line=row["caller_line"],
                callee_path=row["callee_path"],
                callee_name=row["callee_name"],
                callee_first_line=row["callee_first_line"],
                callee_line_hits=tuple(line_hits),
            )
        )
    return PytestExecutionLedger(
        ledger_id=record["ledger_id"],
        ordinal=record["ordinal"],
        role=record["role"],
        role_index=record["role_index"],
        slice_id=record["slice_id"],
        runner_sha256=record["runner_sha256"],
        git=_executable_identity_from_record(record["git"], label="git"),
        python=_executable_identity_from_record(record["python"], label="python"),
        variant_id=record["variant_id"],
        project_root=record["project_root"],
        cwd=record["cwd"],
        argv=tuple(argv),
        execution_envelope=_pytest_execution_envelope_from_record(
            record["execution_envelope"]
        ),
        environment=tuple(environment),
        expected_tree=record["expected_tree"],
        pre_tree=record["pre_tree"],
        post_tree=record["post_tree"],
        collected_node_ids=tuple(collected_node_ids),
        node_outcomes=tuple(node_outcomes),
        outcome_counts=OutcomeCounts(
            passed=count_row["passed"],
            failed=count_row["failed"],
            skipped=count_row["skipped"],
            errors=count_row["errors"],
        ),
        exit_code=record["exit_code"],
        project_origins=tuple(project_origins),
        call_transitions=tuple(transitions),
        elapsed_ns=record["elapsed_ns"],
    )


def validate_pytest_execution_ledger_record(
    record: dict[str, object],
) -> dict[str, object]:
    """Validate and return a deep canonical pytest ledger record copy."""

    try:
        row = _pytest_ledger_record_object(
            record,
            keys=_PYTEST_LEDGER_RECORD_KEYS,
            label="record",
        )
        if row["schema_version"] != _PYTEST_LEDGER_SCHEMA_VERSION:
            _pytest_ledger_invalid("schema_version")
        ledger = _validate_pytest_execution_ledger_value(
            _pytest_execution_ledger_from_record(row)
        )
        expected = _seal_pytest_execution_ledger_body(
            _pytest_execution_ledger_body(ledger)
        )
        for name in ("deterministic_sha256", "record_sha256"):
            digest = row[name]
            if (
                type(digest) is not str
                or _SHA256_RE.fullmatch(digest) is None
                or digest != expected[name]
            ):
                _pytest_ledger_invalid(name)
        return expected
    except FeasibilityProofError as exc:
        if exc.code == "feasibility_pytest_ledger_invalid":
            raise
        raise FeasibilityProofError(
            "feasibility_pytest_ledger_invalid",
            "record",
        ) from exc
    except (AttributeError, KeyError, TypeError, UnicodeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_ledger_invalid",
            "record",
        ) from exc


def _regular_file_metadata(identity: os.stat_result) -> tuple[int, ...]:
    """Return stable identity and mutation metadata, excluding access times."""

    return (
        identity.st_dev,
        identity.st_ino,
        identity.st_mode,
        identity.st_nlink,
        identity.st_uid,
        identity.st_gid,
        identity.st_size,
        identity.st_mtime_ns,
        identity.st_ctime_ns,
    )


def _read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _stable_regular_file_bytes(
    path: Path,
    *,
    error_code: str,
    detail: object,
) -> tuple[bytes, tuple[int, ...]]:
    """Read bytes only while one regular-file pathname binding stays stable."""

    if not hasattr(os, "O_CLOEXEC") or not hasattr(os, "O_NOFOLLOW"):
        raise FeasibilityProofError(error_code, detail)
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        # Avoid blocking if an adversarial pathname resolves to a FIFO at open.
        flags |= os.O_NONBLOCK
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        before_metadata = _regular_file_metadata(before)
        if not stat.S_ISREG(before.st_mode):
            raise FeasibilityProofError(error_code, detail)

        raw = _read_descriptor(descriptor)
        after_first_read = os.fstat(descriptor)
        if (
            _regular_file_metadata(after_first_read) != before_metadata
            or len(raw) != before.st_size
        ):
            raise FeasibilityProofError(error_code, detail)

        os.lseek(descriptor, 0, os.SEEK_SET)
        repeated_raw = _read_descriptor(descriptor)
        after_second_read = os.fstat(descriptor)
        if (
            repeated_raw != raw
            or len(repeated_raw) != before.st_size
            or _regular_file_metadata(after_second_read) != before_metadata
        ):
            raise FeasibilityProofError(error_code, detail)

        pathname_identity = os.lstat(path)
        if _regular_file_metadata(pathname_identity) != before_metadata:
            raise FeasibilityProofError(error_code, detail)
        return raw, before_metadata
    except FeasibilityProofError:
        raise
    except OSError as exc:
        raise FeasibilityProofError(error_code, detail) from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _pytest_capture_invalid(detail: object = "") -> NoReturn:
    raise FeasibilityProofError("feasibility_pytest_capture_invalid", detail)


def _canonical_project_root(path: Path) -> Path:
    candidate = Path(path)
    try:
        identity = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            "project_root",
        ) from exc
    if (
        not candidate.is_absolute()
        or candidate != resolved
        or candidate.is_symlink()
        or not stat.S_ISDIR(identity.st_mode)
    ):
        _pytest_capture_invalid("project_root")
    return candidate


def _git_blob_oid(payload: bytes) -> str:
    framed = f"blob {len(payload)}\0".encode("ascii") + payload
    return hashlib.sha1(framed, usedforsecurity=False).hexdigest()


def _stable_symlink_bytes(path: Path) -> bytes:
    try:
        before = path.lstat()
        raw_path = os.fsencode(path)
        first = os.readlink(raw_path)
        second = os.readlink(raw_path)
        after = path.lstat()
    except (OSError, UnicodeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            "project_tree",
        ) from exc
    if (
        not stat.S_ISLNK(before.st_mode)
        or type(first) is not bytes
        or first != second
        or _regular_file_metadata(before) != _regular_file_metadata(after)
    ):
        _pytest_capture_invalid("project_tree")
    return first


def _snapshot_directory_tree_oid(
    project_root: Path,
    *,
    allow_empty: bool,
) -> str:

    root = _canonical_project_root(Path(project_root))
    leaves: list[TreeLeaf] = []

    def visit(directory: Path, prefix: tuple[str, ...]) -> None:
        try:
            before = directory.lstat()
            entries = tuple(os.scandir(directory))
        except OSError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_capture_invalid",
                "project_tree",
            ) from exc
        if not stat.S_ISDIR(before.st_mode) or directory.is_symlink():
            _pytest_capture_invalid("project_tree")
        try:
            ordered_entries = tuple(
                sorted(
                    entries,
                    key=lambda item: item.name.encode("utf-8", "strict"),
                )
            )
        except UnicodeError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_capture_invalid",
                "project_tree",
            ) from exc
        for entry in ordered_entries:
            try:
                entry.name.encode("utf-8", "strict")
                path = Path(entry.path)
                identity = path.lstat()
            except (OSError, UnicodeError, ValueError) as exc:
                raise FeasibilityProofError(
                    "feasibility_pytest_capture_invalid",
                    "project_tree",
                ) from exc
            parts = (*prefix, entry.name)
            relative = "/".join(parts)
            try:
                _split_leaf_path(relative)
            except FeasibilityProofError as exc:
                raise FeasibilityProofError(
                    "feasibility_pytest_capture_invalid",
                    "project_tree",
                ) from exc
            if stat.S_ISDIR(identity.st_mode):
                visit(path, parts)
                continue
            if stat.S_ISREG(identity.st_mode):
                raw, stable_identity = _stable_regular_file_bytes(
                    path,
                    error_code="feasibility_pytest_capture_invalid",
                    detail="project_tree",
                )
                if stable_identity != _regular_file_metadata(identity):
                    _pytest_capture_invalid("project_tree")
                mode = "100755" if identity.st_mode & 0o111 else "100644"
            elif stat.S_ISLNK(identity.st_mode):
                raw = _stable_symlink_bytes(path)
                mode = "120000"
            else:
                _pytest_capture_invalid("project_tree")
            leaves.append(
                TreeLeaf(
                    path=relative,
                    mode=mode,
                    blob_oid=_git_blob_oid(raw),
                )
            )
        try:
            after = directory.lstat()
        except OSError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_capture_invalid",
                "project_tree",
            ) from exc
        if _regular_file_metadata(before) != _regular_file_metadata(after):
            _pytest_capture_invalid("project_tree")

    visit(root, ())
    if not leaves and allow_empty:
        return _EMPTY_GIT_TREE_OID
    if not leaves:
        _pytest_capture_invalid("project_tree")
    try:
        tree_oid, _ = _synthesize_tree_objects(
            tuple(sorted(leaves, key=lambda leaf: leaf.path.encode("utf-8")))
        )
    except FeasibilityProofError as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            "project_tree",
        ) from exc
    return tree_oid


def snapshot_project_tree_oid(project_root: Path) -> str:
    """Hash one nonempty stable extract using canonical Git tree rules."""

    return _snapshot_directory_tree_oid(Path(project_root), allow_empty=False)


def snapshot_writable_mount_tree_oid(writable_root: Path) -> str:
    """Hash one stable external writable root, including an empty root."""

    return _snapshot_directory_tree_oid(Path(writable_root), allow_empty=True)


def runner_sha256(path: Path | None = None) -> str:
    """Return the exact regular-file SHA-256 of this runner or an explicit path."""

    candidate = Path(__file__) if path is None else Path(path)
    raw, _ = _stable_regular_file_bytes(
        candidate,
        error_code="feasibility_runner_unreadable",
        detail=str(candidate),
    )
    return _sha256(raw)


def _canonical_absolute(path: Path) -> Path:
    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FeasibilityProofError(
            "feasibility_record_path_invalid",
            str(candidate),
        ) from exc
    if not candidate.is_absolute() or candidate != resolved:
        raise FeasibilityProofError(
            "feasibility_record_path_invalid",
            str(candidate),
        )
    return candidate


def load_pinned_canonical_json(
    path: Path,
    *,
    expected_sha256: str,
) -> dict[str, object]:
    """Load one exact canonical object from a digest-bound regular file."""

    candidate = _canonical_absolute(Path(path))
    if not isinstance(expected_sha256, str) or _SHA256_RE.fullmatch(expected_sha256) is None:
        raise FeasibilityProofError(
            "feasibility_record_digest_mismatch",
            "expected_sha256",
        )
    raw, _ = _stable_regular_file_bytes(
        candidate,
        error_code="feasibility_record_path_invalid",
        detail=str(candidate),
    )
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except FeasibilityProofError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_record_invalid",
            str(candidate),
        ) from exc
    if _sha256(raw) != expected_sha256:
        raise FeasibilityProofError(
            "feasibility_record_digest_mismatch",
            str(candidate),
        )
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise FeasibilityProofError(
            "feasibility_record_noncanonical",
            str(candidate),
        )
    return value


def verify_executable_binding(
    binding: Mapping[str, object],
    *,
    role: str,
) -> dict[str, object]:
    """Verify one exact executable and its deterministic version invocation."""

    if not isinstance(role, str) or not role:
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            "role",
        )
    if not isinstance(binding, Mapping) or set(binding) != _EXECUTABLE_BINDING_KEYS:
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        )
    scalar_keys = ("literal_path", "real_path", "sha256", "version_output")
    if any(
        not isinstance(binding[key], str) or not binding[key]
        for key in scalar_keys
    ):
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        )
    argv_value = binding["version_argv"]
    if (
        not isinstance(argv_value, list)
        or not argv_value
        or any(not isinstance(item, str) or not item for item in argv_value)
    ):
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        )
    literal_text = binding["literal_path"]
    real_text = binding["real_path"]
    digest = binding["sha256"]
    version_output = binding["version_output"]
    assert isinstance(literal_text, str)
    assert isinstance(real_text, str)
    assert isinstance(digest, str)
    assert isinstance(version_output, str)
    literal = Path(literal_text)
    declared_real = Path(real_text)
    if (
        not literal.is_absolute()
        or not declared_real.is_absolute()
        or _SHA256_RE.fullmatch(digest) is None
        or argv_value[0] != literal_text
    ):
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        )
    try:
        resolved = literal.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        ) from exc
    if resolved != declared_real:
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        )
    raw, pre_invocation_metadata = _stable_regular_file_bytes(
        declared_real,
        error_code="feasibility_executable_binding_invalid",
        detail=role,
    )
    if _sha256(raw) != digest:
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        )
    env = {
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }
    try:
        completed = subprocess.run(
            tuple(argv_value),
            cwd=Path("/"),
            env=env,
            check=False,
            shell=False,
            timeout=_EXECUTABLE_VERSION_TIMEOUT_SECONDS,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        observed_output = completed.stdout.decode("utf-8", "strict")
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        ) from exc
    try:
        resolved_after_invocation = literal.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        ) from exc
    if resolved_after_invocation != declared_real:
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        )
    post_invocation_raw, post_invocation_metadata = _stable_regular_file_bytes(
        declared_real,
        error_code="feasibility_executable_binding_invalid",
        detail=role,
    )
    if (
        post_invocation_metadata != pre_invocation_metadata
        or post_invocation_raw != raw
        or _sha256(post_invocation_raw) != digest
    ):
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        )
    if completed.returncode != 0 or observed_output != version_output:
        raise FeasibilityProofError(
            "feasibility_executable_binding_invalid",
            role,
        )
    normalized = {
        "literal_path": literal_text,
        "real_path": str(resolved),
        "sha256": _sha256(raw),
        "version_argv": list(argv_value),
        "version_output": observed_output,
    }
    canonical_json_bytes(normalized)
    return normalized


def _call_trace_spec_record(value: CallTraceSpec) -> dict[str, object]:
    return {
        "edge_id": value.edge_id,
        "pytest_node_id": value.pytest_node_id,
        "caller_path": value.caller_path,
        "caller_line": value.caller_line,
        "callee_path": value.callee_path,
        "callee_name": value.callee_name,
        "callee_first_line": value.callee_first_line,
    }


def _validate_call_trace_spec(value: object, *, label: str) -> CallTraceSpec:
    if type(value) is not CallTraceSpec:
        _pytest_capture_invalid(label)
    for name in ("edge_id", "pytest_node_id", "callee_name"):
        _validate_pytest_ledger_text(
            getattr(value, name),
            label=f"{label}.{name}",
        )
    for name in ("caller_path", "callee_path"):
        try:
            _split_leaf_path(getattr(value, name))
        except FeasibilityProofError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_capture_invalid",
                f"{label}.{name}",
            ) from exc
    for name in ("caller_line", "callee_first_line"):
        value_int = getattr(value, name)
        if type(value_int) is not int or value_int < 1:
            _pytest_capture_invalid(f"{label}.{name}")
    return value


def _validate_call_trace_specs(
    values: object,
) -> tuple[CallTraceSpec, ...]:
    if type(values) is not tuple:
        _pytest_capture_invalid("call_trace_specs")
    result = tuple(
        _validate_call_trace_spec(value, label=f"call_trace_specs[{index}]")
        for index, value in enumerate(values)
    )
    keys = tuple(
        (
            value.pytest_node_id.encode("utf-8", "strict"),
            value.edge_id.encode("utf-8", "strict"),
        )
        for value in result
    )
    if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
        _pytest_capture_invalid("call_trace_specs")
    return result


def _validate_expected_project_origins(
    values: object,
    *,
    project_root: Path,
) -> tuple[ProjectOrigin, ...]:
    if type(values) is not tuple or not values:
        _pytest_capture_invalid("expected_project_origins")
    result: list[ProjectOrigin] = []
    for index, value in enumerate(values):
        if type(value) is not ProjectOrigin:
            _pytest_capture_invalid(f"expected_project_origins[{index}]")
        module_name = _validate_pytest_ledger_text(
            value.module_name,
            label=f"expected_project_origins[{index}].module_name",
        )
        resolved_path = _validate_pytest_ledger_absolute_path(
            value.resolved_path,
            label=f"expected_project_origins[{index}].resolved_path",
        )
        try:
            Path(resolved_path).relative_to(project_root)
        except ValueError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_capture_invalid",
                f"expected_project_origins[{index}]",
            ) from exc
        result.append(ProjectOrigin(module_name, resolved_path))
    names = tuple(item.module_name for item in result)
    if (
        names
        != tuple(sorted(names, key=lambda item: item.encode("utf-8", "strict")))
        or len(set(names)) != len(names)
    ):
        _pytest_capture_invalid("expected_project_origins")
    return tuple(result)


def _executable_identity_from_binding(
    binding: Mapping[str, object],
) -> ExecutableIdentity:
    return ExecutableIdentity(
        literal_path=binding["literal_path"],
        real_path=binding["real_path"],
        sha256=binding["sha256"],
        version_argv=tuple(binding["version_argv"]),
        version_output=binding["version_output"],
    )


def _pytest_capture_request_bytes(
    *,
    project_root: str,
    runtime_project_root: str,
    role: str,
    call_trace_specs: tuple[CallTraceSpec, ...],
) -> bytes:
    return canonical_json_bytes(
        {
            "schema_version": _PYTEST_CAPTURE_REQUEST_SCHEMA_VERSION,
            "project_root": project_root,
            "runtime_project_root": runtime_project_root,
            "role": role,
            "call_trace_specs": [
                _call_trace_spec_record(value) for value in call_trace_specs
            ],
        }
    )


def _pytest_capture_environment(
    runner_path: Path,
    request: bytes,
    *,
    sandboxed: bool,
) -> tuple[tuple[str, str], ...]:
    repository_root = runner_path.parents[3]
    values = {
        "HOME": _BWRAP_RUNTIME_HOME_ROOT if sandboxed else "/",
        "LANG": "C",
        "LC_ALL": "C",
        _PYTEST_CAPTURE_PROTOCOL_ENV: _PYTEST_CAPTURE_PROTOCOL_VERSION,
        _PYTEST_CAPTURE_REQUEST_ENV: base64.b64encode(request).decode("ascii"),
        "PATH": "/usr/bin:/bin",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_PLUGINS": _PYTEST_CAPTURE_PLUGIN,
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONPATH": str(repository_root),
        "CUDA_VISIBLE_DEVICES": "",
    }
    if sandboxed:
        values["TMPDIR"] = "/tmp"
    return tuple(sorted(values.items(), key=lambda item: item[0].encode("utf-8")))


def _pytest_ledger_authority_mismatch(detail: object = "") -> NoReturn:
    raise FeasibilityProofError(
        "feasibility_pytest_ledger_authority_mismatch",
        detail,
    )


def _validate_pytest_ledger_authority(
    authority: object,
) -> PytestLedgerAuthority:
    try:
        if type(authority) is not PytestLedgerAuthority:
            _pytest_ledger_authority_mismatch("authority")
        _validate_pytest_ledger_text(authority.ledger_id, label="ledger_id")
        _validate_pytest_ledger_int(authority.ordinal, label="ordinal", minimum=0)
        role = _validate_pytest_ledger_text(authority.role, label="role")
        if role not in _PYTEST_LEDGER_ROLES:
            _pytest_ledger_invalid("role")
        _validate_pytest_ledger_int(
            authority.role_index,
            label="role_index",
            minimum=0,
        )
        if role in _PYTEST_LEDGER_SLICE_ROLES:
            _validate_pytest_ledger_text(authority.slice_id, label="slice_id")
        elif authority.slice_id is not None:
            _pytest_ledger_invalid("slice_id")
        runner_path = _validate_pytest_ledger_absolute_path(
            authority.runner_path,
            label="runner_path",
        )
        if tuple(Path(runner_path).parts[-4:]) != tuple(
            Path(RUNNER_RELATIVE_PATH).parts
        ):
            _pytest_ledger_invalid("runner_path")
        if (
            type(authority.runner_sha256) is not str
            or _SHA256_RE.fullmatch(authority.runner_sha256) is None
        ):
            _pytest_ledger_invalid("runner_sha256")
        _validate_pytest_executable_identity(authority.git, label="git")
        python = _validate_pytest_executable_identity(
            authority.python,
            label="python",
        )
        _validate_pytest_ledger_text(authority.variant_id, label="variant_id")
        project_root = _validate_pytest_ledger_absolute_path(
            authority.project_root,
            label="project_root",
        )
        if type(authority.expected_tree) is not str or _SHA1_RE.fullmatch(
            authority.expected_tree
        ) is None:
            _pytest_ledger_invalid("expected_tree")
        if type(authority.argv) is not tuple or not authority.argv:
            _pytest_ledger_invalid("argv")
        for index, value in enumerate(authority.argv):
            _validate_pytest_ledger_text(value, label=f"argv[{index}]")
        if authority.argv[:3] != (python.literal_path, "-m", "pytest"):
            _pytest_ledger_invalid("argv")
        _validate_pytest_execution_envelope(
            authority.execution_envelope,
            project_root=project_root,
            target_argv=authority.argv,
        )
        _validate_expected_project_origins(
            authority.expected_project_origins,
            project_root=Path(project_root),
        )
        trace_specs = _validate_call_trace_specs(authority.call_trace_specs)
        if role == "collection" and trace_specs:
            _pytest_ledger_invalid("call_trace_specs")
        return authority
    except FeasibilityProofError as exc:
        if exc.code == "feasibility_pytest_ledger_authority_mismatch":
            raise
        raise FeasibilityProofError(
            "feasibility_pytest_ledger_authority_mismatch",
            exc.detail,
        ) from exc
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_ledger_authority_mismatch",
            "authority",
        ) from exc


def validate_authorized_pytest_execution_ledger_record(
    record: dict[str, object],
    *,
    authority: PytestLedgerAuthority,
    reobserve_executables: bool,
) -> dict[str, object]:
    """Validate one sealed ledger against caller-owned execution authority."""

    normalized_record = validate_pytest_execution_ledger_record(record)
    normalized = _validate_pytest_ledger_authority(authority)
    if type(reobserve_executables) is not bool:
        _pytest_ledger_authority_mismatch("reobserve_executables")
    ledger = _pytest_execution_ledger_from_record(normalized_record)
    observed_trace_specs = tuple(
        CallTraceSpec(
            edge_id=value.edge_id,
            pytest_node_id=value.pytest_node_id,
            caller_path=value.caller_path,
            caller_line=value.caller_line,
            callee_path=value.callee_path,
            callee_name=value.callee_name,
            callee_first_line=value.callee_first_line,
        )
        for value in ledger.call_transitions
    )
    expected_request = _pytest_capture_request_bytes(
        project_root=normalized.project_root,
        runtime_project_root=normalized.execution_envelope.runtime_project_root,
        role=normalized.role,
        call_trace_specs=normalized.call_trace_specs,
    )
    expected_environment = _pytest_capture_environment(
        Path(normalized.runner_path),
        expected_request,
        sandboxed=normalized.execution_envelope.kind == "bwrap_ro_project.v1",
    )
    bindings: tuple[tuple[str, object, object], ...] = (
        ("ledger_id", ledger.ledger_id, normalized.ledger_id),
        ("ordinal", ledger.ordinal, normalized.ordinal),
        ("role", ledger.role, normalized.role),
        ("role_index", ledger.role_index, normalized.role_index),
        ("slice_id", ledger.slice_id, normalized.slice_id),
        ("runner_sha256", ledger.runner_sha256, normalized.runner_sha256),
        ("git", ledger.git, normalized.git),
        ("python", ledger.python, normalized.python),
        ("variant_id", ledger.variant_id, normalized.variant_id),
        ("project_root", ledger.project_root, normalized.project_root),
        ("argv", ledger.argv, normalized.argv),
        (
            "execution_envelope",
            ledger.execution_envelope,
            normalized.execution_envelope,
        ),
        ("environment", ledger.environment, expected_environment),
        ("expected_tree", ledger.expected_tree, normalized.expected_tree),
        ("pre_tree", ledger.pre_tree, normalized.expected_tree),
        ("post_tree", ledger.post_tree, normalized.expected_tree),
        (
            "project_origins",
            ledger.project_origins,
            normalized.expected_project_origins,
        ),
        ("call_transitions", observed_trace_specs, normalized.call_trace_specs),
    )
    for label, observed, expected in bindings:
        if observed != expected:
            _pytest_ledger_authority_mismatch(label)
    if reobserve_executables:
        try:
            candidate_runner = Path(normalized.runner_path)
            if (
                candidate_runner.resolve(strict=True) != candidate_runner
                or candidate_runner.is_symlink()
                or runner_sha256(candidate_runner) != normalized.runner_sha256
            ):
                _pytest_ledger_authority_mismatch("runner_sha256")
            for role, identity in (
                ("git", normalized.git),
                ("python", normalized.python),
            ):
                verify_executable_binding(
                    _executable_identity_record(identity),
                    role=role,
                )
            launcher = normalized.execution_envelope.launcher
            if launcher is not None:
                verify_executable_binding(
                    _executable_identity_record(launcher),
                    role="bwrap",
                )
        except FeasibilityProofError as exc:
            if exc.code == "feasibility_pytest_ledger_authority_mismatch":
                raise
            raise FeasibilityProofError(
                "feasibility_pytest_ledger_authority_mismatch",
                "executable_identity",
            ) from exc
        except (OSError, RuntimeError, ValueError) as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_ledger_authority_mismatch",
                "runner_path",
            ) from exc
    return normalized_record


def _strict_json_object(raw: bytes, *, detail: str) -> dict[str, object]:
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (FeasibilityProofError, UnicodeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            detail,
        ) from exc
    if type(value) is not dict or canonical_json_bytes(value) != raw:
        _pytest_capture_invalid(detail)
    return value


def _decode_pytest_capture_response(
    stdout: bytes,
    stderr: bytes,
) -> dict[str, object]:
    """Extract exactly one canonical worker response from process output."""

    if type(stdout) is not bytes or type(stderr) is not bytes:
        _pytest_capture_invalid("worker_response")
    candidates = [
        line[len(_PYTEST_CAPTURE_SENTINEL) :]
        for stream in (stdout, stderr)
        for line in stream.splitlines()
        if line.startswith(_PYTEST_CAPTURE_SENTINEL)
    ]
    if len(candidates) != 1 or not candidates[0]:
        _pytest_capture_invalid("worker_response")
    try:
        raw = base64.b64decode(candidates[0], validate=True)
    except (ValueError, TypeError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            "worker_response",
        ) from exc
    return _strict_json_object(raw, detail="worker_response")


def _run_pytest_capture_process(
    *,
    argv: tuple[str, ...],
    project_root: Path,
    environment: tuple[tuple[str, str], ...],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            argv,
            cwd=project_root,
            env=dict(environment),
            check=False,
            shell=False,
            timeout=timeout_seconds,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            "process",
        ) from exc


def _worker_response_rows(
    response: dict[str, object],
    *,
    project_root: Path,
) -> tuple[
    tuple[str, ...],
    tuple[NodeOutcome, ...],
    OutcomeCounts,
    tuple[ProjectOrigin, ...],
    tuple[CallTransition, ...],
]:
    if set(response) != _PYTEST_CAPTURE_RESPONSE_KEYS:
        _pytest_capture_invalid("worker_response")
    if response["schema_version"] != _PYTEST_CAPTURE_SCHEMA_VERSION:
        _pytest_capture_invalid("worker_response")
    for name in ("collection_errors", "worker_errors"):
        value = response[name]
        if type(value) is not list or value:
            _pytest_capture_invalid(name)

    collected_raw = response["collected_node_ids"]
    if type(collected_raw) is not list:
        _pytest_capture_invalid("collected_node_ids")
    collected = tuple(
        _validate_pytest_ledger_text(
            item,
            label=f"collected_node_ids[{index}]",
        )
        for index, item in enumerate(collected_raw)
    )
    if not collected or len(set(collected)) != len(collected):
        _pytest_capture_invalid("collected_node_ids")

    outcomes_raw = response["node_outcomes"]
    if type(outcomes_raw) is not list:
        _pytest_capture_invalid("node_outcomes")
    outcomes: list[NodeOutcome] = []
    for index, value in enumerate(outcomes_raw):
        if type(value) is not dict or set(value) != _PYTEST_LEDGER_NODE_OUTCOME_KEYS:
            _pytest_capture_invalid(f"node_outcomes[{index}]")
        outcomes.append(
            _validate_pytest_node_outcome(
                NodeOutcome(
                    node_id=value["node_id"],
                    outcome=value["outcome"],
                    failure_phase=value["failure_phase"],
                ),
                label=f"node_outcomes[{index}]",
            )
        )

    counts_raw = response["outcome_counts"]
    if type(counts_raw) is not dict or set(counts_raw) != _PYTEST_LEDGER_OUTCOME_COUNT_KEYS:
        _pytest_capture_invalid("outcome_counts")
    counts = _validate_pytest_outcome_counts(
        OutcomeCounts(
            passed=counts_raw["passed"],
            failed=counts_raw["failed"],
            skipped=counts_raw["skipped"],
            errors=counts_raw["errors"],
        )
    )

    origins_raw = response["project_origins"]
    if type(origins_raw) is not list:
        _pytest_capture_invalid("project_origins")
    origins: list[ProjectOrigin] = []
    for index, value in enumerate(origins_raw):
        if type(value) is not dict or set(value) != _PYTEST_LEDGER_PROJECT_ORIGIN_KEYS:
            _pytest_capture_invalid(f"project_origins[{index}]")
        origin = ProjectOrigin(value["module_name"], value["resolved_path"])
        _validate_pytest_ledger_text(
            origin.module_name,
            label=f"project_origins[{index}].module_name",
        )
        resolved = _validate_pytest_ledger_absolute_path(
            origin.resolved_path,
            label=f"project_origins[{index}].resolved_path",
        )
        try:
            Path(resolved).relative_to(project_root)
        except ValueError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_capture_invalid",
                "project_origins",
            ) from exc
        origins.append(origin)

    transitions_raw = response["call_transitions"]
    if type(transitions_raw) is not list:
        _pytest_capture_invalid("call_transitions")
    transitions: list[CallTransition] = []
    for index, value in enumerate(transitions_raw):
        if type(value) is not dict or set(value) != _PYTEST_LEDGER_CALL_TRANSITION_KEYS:
            _pytest_capture_invalid(f"call_transitions[{index}]")
        line_hits = value["callee_line_hits"]
        if type(line_hits) is not list:
            _pytest_capture_invalid(f"call_transitions[{index}]")
        try:
            transitions.append(
                _validate_call_transition(
                    CallTransition(
                        edge_id=value["edge_id"],
                        pytest_node_id=value["pytest_node_id"],
                        outcome=value["outcome"],
                        caller_path=value["caller_path"],
                        caller_line=value["caller_line"],
                        callee_path=value["callee_path"],
                        callee_name=value["callee_name"],
                        callee_first_line=value["callee_first_line"],
                        callee_line_hits=tuple(line_hits),
                    ),
                    label=f"call_transitions[{index}]",
                )
            )
        except FeasibilityProofError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_capture_invalid",
                f"call_transitions[{index}]",
            ) from exc
    return collected, tuple(outcomes), counts, tuple(origins), tuple(transitions)


def _canonical_empty_external_root(
    path: Path,
    *,
    project_root: Path,
    label: str,
) -> Path:
    candidate = Path(path)
    try:
        identity = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        entries = tuple(os.scandir(candidate))
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            label,
        ) from exc
    if (
        not candidate.is_absolute()
        or candidate != resolved
        or candidate.is_symlink()
        or not stat.S_ISDIR(identity.st_mode)
        or entries
    ):
        _pytest_capture_invalid(label)
    try:
        candidate.relative_to(project_root)
    except ValueError:
        return candidate
    _pytest_capture_invalid(label)


def _validate_writable_mount_specs(
    values: object,
    *,
    project_root: Path,
) -> tuple[tuple[WritableMountSpec, Path], ...]:
    if type(values) is not tuple or not values:
        _pytest_capture_invalid("writable_mounts")
    result: list[tuple[WritableMountSpec, Path]] = []
    for index, value in enumerate(values):
        if type(value) is not WritableMountSpec:
            _pytest_capture_invalid(f"writable_mounts[{index}]")
        try:
            parts = _split_leaf_path(value.relative_path)
        except FeasibilityProofError as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_capture_invalid",
                f"writable_mounts[{index}].relative_path",
            ) from exc
        target = project_root.joinpath(*parts)
        try:
            target_identity = target.lstat()
            target_resolved = target.resolve(strict=True)
            target_entries = tuple(os.scandir(target))
        except (OSError, RuntimeError, ValueError) as exc:
            raise FeasibilityProofError(
                "feasibility_pytest_capture_invalid",
                f"writable_mounts[{index}].relative_path",
            ) from exc
        if (
            target.is_symlink()
            or not stat.S_ISDIR(target_identity.st_mode)
            or target_resolved != target
            or target_entries
        ):
            _pytest_capture_invalid(f"writable_mounts[{index}].relative_path")
        host = _canonical_empty_external_root(
            Path(value.host_path),
            project_root=project_root,
            label=f"writable_mounts[{index}].host_path",
        )
        result.append((value, host))
    relative_paths = tuple(item[0].relative_path for item in result)
    host_paths = tuple(item[1] for item in result)
    if (
        relative_paths
        != tuple(sorted(relative_paths, key=lambda item: item.encode("utf-8", "strict")))
        or len(set(relative_paths)) != len(relative_paths)
        or len(set(host_paths)) != len(host_paths)
    ):
        _pytest_capture_invalid("writable_mounts")
    for left_index, left in enumerate(relative_paths):
        left_parts = left.split("/")
        for right in relative_paths[left_index + 1 :]:
            right_parts = right.split("/")
            if (
                left_parts == right_parts[: len(left_parts)]
                or right_parts == left_parts[: len(right_parts)]
            ):
                _pytest_capture_invalid("writable_mounts")
    return tuple(result)


def capture_pytest_execution_ledger(
    *,
    ledger_id: str,
    ordinal: int,
    role: str,
    role_index: int,
    slice_id: str | None,
    runner_path: Path,
    git_binding: Mapping[str, object],
    python_binding: Mapping[str, object],
    variant_id: str,
    project_root: Path,
    expected_tree: str,
    pytest_args: tuple[str, ...],
    expected_project_origins: tuple[ProjectOrigin, ...],
    call_trace_specs: tuple[CallTraceSpec, ...] = (),
    bwrap_binding: Mapping[str, object] | None = None,
    writable_mounts: tuple[WritableMountSpec, ...] = (),
    sandbox_home_root: Path | None = None,
    sandbox_tmp_root: Path | None = None,
    timeout_seconds: int = 300,
) -> dict[str, object]:
    """Run one exact pytest subprocess and return its sealed immutable ledger."""

    root = _canonical_project_root(Path(project_root))
    candidate_runner = Path(runner_path)
    try:
        resolved_runner = candidate_runner.resolve(strict=True)
        module_runner = Path(__file__).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            "runner_path",
        ) from exc
    if (
        not candidate_runner.is_absolute()
        or candidate_runner != resolved_runner
        or candidate_runner.is_symlink()
        or resolved_runner != module_runner
    ):
        _pytest_capture_invalid("runner_path")
    if type(expected_tree) is not str or _SHA1_RE.fullmatch(expected_tree) is None:
        _pytest_capture_invalid("expected_tree")
    if (
        type(pytest_args) is not tuple
        or not pytest_args
        or any(type(value) is not str or not value or "\0" in value for value in pytest_args)
    ):
        _pytest_capture_invalid("pytest_args")
    if not any(
        pytest_args[index : index + 2] == ("-p", "no:cacheprovider")
        for index in range(max(0, len(pytest_args) - 1))
    ):
        _pytest_capture_invalid("pytest_args")
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        _pytest_capture_invalid("timeout_seconds")
    if role == "collection":
        if "--collect-only" not in pytest_args:
            _pytest_capture_invalid("pytest_args")
    elif "--collect-only" in pytest_args:
        _pytest_capture_invalid("pytest_args")

    trace_specs = _validate_call_trace_specs(call_trace_specs)
    if role == "collection" and trace_specs:
        _pytest_capture_invalid("call_trace_specs")
    expected_origins = _validate_expected_project_origins(
        expected_project_origins,
        project_root=root,
    )
    sandboxed = bwrap_binding is not None
    normalized_bwrap: dict[str, object] | None = None
    mount_bindings: tuple[tuple[WritableMountSpec, Path], ...] = ()
    home_root: Path | None = None
    tmp_root: Path | None = None
    if not sandboxed:
        if (
            writable_mounts
            or sandbox_home_root is not None
            or sandbox_tmp_root is not None
        ):
            _pytest_capture_invalid("execution_envelope")
    else:
        if sandbox_home_root is None or sandbox_tmp_root is None:
            _pytest_capture_invalid("execution_envelope")
        mount_bindings = _validate_writable_mount_specs(
            writable_mounts,
            project_root=root,
        )
        home_root = _canonical_empty_external_root(
            Path(sandbox_home_root),
            project_root=root,
            label="sandbox_home_root",
        )
        tmp_root = _canonical_empty_external_root(
            Path(sandbox_tmp_root),
            project_root=root,
            label="sandbox_tmp_root",
        )
        external_roots = (home_root, tmp_root, *(item[1] for item in mount_bindings))
        if len(set(external_roots)) != len(external_roots):
            _pytest_capture_invalid("execution_envelope")
        for index, left in enumerate(external_roots):
            for right in external_roots[index + 1 :]:
                try:
                    left.relative_to(right)
                except ValueError:
                    try:
                        right.relative_to(left)
                    except ValueError:
                        continue
                _pytest_capture_invalid("execution_envelope")
        assert bwrap_binding is not None
        normalized_bwrap = verify_executable_binding(
            bwrap_binding,
            role="bwrap",
        )
    normalized_git = verify_executable_binding(git_binding, role="git")
    normalized_python = verify_executable_binding(python_binding, role="python")
    pinned_runner_sha256 = runner_sha256(candidate_runner)
    pre_tree = snapshot_project_tree_oid(root)
    if pre_tree != expected_tree:
        _pytest_capture_invalid("expected_tree")

    python_path = normalized_python["literal_path"]
    assert isinstance(python_path, str)
    argv = (python_path, "-m", "pytest", *pytest_args)
    runtime_project_root = (
        _BWRAP_RUNTIME_PROJECT_ROOT if sandboxed else str(root)
    )
    request = _pytest_capture_request_bytes(
        project_root=str(root),
        runtime_project_root=runtime_project_root,
        role=role,
        call_trace_specs=trace_specs,
    )
    environment = _pytest_capture_environment(
        candidate_runner,
        request,
        sandboxed=sandboxed,
    )
    preliminary_mounts = tuple(
        WritableMountEvidence(
            relative_path=spec.relative_path,
            host_path=str(host),
            pre_tree=snapshot_writable_mount_tree_oid(host),
            post_tree=_EMPTY_GIT_TREE_OID,
        )
        for spec, host in mount_bindings
    )
    if sandboxed:
        assert normalized_bwrap is not None and home_root is not None and tmp_root is not None
        bwrap_path = normalized_bwrap["literal_path"]
        assert isinstance(bwrap_path, str)
        process_argv = _expected_bwrap_launcher_argv(
            launcher_path=bwrap_path,
            project_root=str(root),
            home_root=str(home_root),
            tmp_root=str(tmp_root),
            writable_mounts=preliminary_mounts,
            target_argv=argv,
        )
    else:
        process_argv = argv
    started = time.monotonic_ns()
    process_error: FeasibilityProofError | None = None
    completed: subprocess.CompletedProcess[bytes] | None = None
    try:
        completed = _run_pytest_capture_process(
            argv=process_argv,
            project_root=root,
            environment=environment,
            timeout_seconds=timeout_seconds,
        )
    except FeasibilityProofError as exc:
        process_error = exc
    elapsed_ns = max(1, time.monotonic_ns() - started)

    post_tree = snapshot_project_tree_oid(root)
    post_runner_sha256 = runner_sha256(candidate_runner)
    post_git = verify_executable_binding(git_binding, role="git")
    post_python = verify_executable_binding(python_binding, role="python")
    post_bwrap = (
        None
        if bwrap_binding is None
        else verify_executable_binding(bwrap_binding, role="bwrap")
    )
    observed_mounts = tuple(
        WritableMountEvidence(
            relative_path=before.relative_path,
            host_path=before.host_path,
            pre_tree=before.pre_tree,
            post_tree=snapshot_writable_mount_tree_oid(host),
        )
        for before, (_, host) in zip(preliminary_mounts, mount_bindings)
    )
    if pre_tree != expected_tree or post_tree != expected_tree:
        _pytest_capture_invalid("tree_immutability")
    if (
        post_runner_sha256 != pinned_runner_sha256
        or post_git != normalized_git
        or post_python != normalized_python
        or post_bwrap != normalized_bwrap
    ):
        _pytest_capture_invalid("executable_identity")
    if process_error is not None:
        raise process_error
    assert completed is not None
    response = _decode_pytest_capture_response(completed.stdout, completed.stderr)
    if completed.returncode not in {0, 1} or response.get("exit_code") != completed.returncode:
        _pytest_capture_invalid("process")
    if (
        response.get("runner_path") != str(candidate_runner)
        or response.get("runner_sha256") != pinned_runner_sha256
        or response.get("project_root") != str(root)
        or response.get("cwd") != runtime_project_root
    ):
        _pytest_capture_invalid("worker_binding")
    collected, outcomes, counts, origins, transitions = _worker_response_rows(
        response,
        project_root=root,
    )
    if role == "collection":
        if outcomes or transitions or counts != OutcomeCounts(0, 0, 0, 0):
            _pytest_capture_invalid("collection")
    elif tuple(item.node_id for item in outcomes) != collected:
        _pytest_capture_invalid("node_outcomes")
    if origins != expected_origins:
        _pytest_capture_invalid("project_origins")
    if len(transitions) != len(trace_specs):
        _pytest_capture_invalid("call_transitions")
    for transition, spec in zip(transitions, trace_specs):
        if (
            transition.edge_id != spec.edge_id
            or transition.pytest_node_id != spec.pytest_node_id
            or transition.outcome != "passed"
            or transition.caller_path != spec.caller_path
            or transition.caller_line != spec.caller_line
            or transition.callee_path != spec.callee_path
            or transition.callee_name != spec.callee_name
            or transition.callee_first_line != spec.callee_first_line
        ):
            _pytest_capture_invalid("call_transitions")

    if sandboxed:
        assert normalized_bwrap is not None and home_root is not None and tmp_root is not None
        execution_envelope = PytestExecutionEnvelope(
            kind="bwrap_ro_project.v1",
            launcher=_executable_identity_from_binding(normalized_bwrap),
            launcher_argv=process_argv,
            runtime_project_root=_BWRAP_RUNTIME_PROJECT_ROOT,
            home_root=str(home_root),
            tmp_root=str(tmp_root),
            writable_mounts=observed_mounts,
        )
    else:
        execution_envelope = PytestExecutionEnvelope(
            kind="direct",
            launcher=None,
            launcher_argv=argv,
            runtime_project_root=str(root),
            home_root=None,
            tmp_root=None,
            writable_mounts=(),
        )

    ledger = PytestExecutionLedger(
        ledger_id=ledger_id,
        ordinal=ordinal,
        role=role,
        role_index=role_index,
        slice_id=slice_id,
        runner_sha256=pinned_runner_sha256,
        git=_executable_identity_from_binding(normalized_git),
        python=_executable_identity_from_binding(normalized_python),
        variant_id=variant_id,
        project_root=str(root),
        cwd=runtime_project_root,
        argv=argv,
        execution_envelope=execution_envelope,
        environment=environment,
        expected_tree=expected_tree,
        pre_tree=pre_tree,
        post_tree=post_tree,
        collected_node_ids=collected,
        node_outcomes=outcomes,
        outcome_counts=counts,
        exit_code=completed.returncode,
        project_origins=origins,
        call_transitions=transitions,
        elapsed_ns=elapsed_ns,
    )
    try:
        record = pytest_execution_ledger_record(ledger)
        return validate_authorized_pytest_execution_ledger_record(
            record,
            authority=PytestLedgerAuthority(
                ledger_id=ledger_id,
                ordinal=ordinal,
                role=role,
                role_index=role_index,
                slice_id=slice_id,
                runner_path=str(candidate_runner),
                runner_sha256=pinned_runner_sha256,
                git=ledger.git,
                python=ledger.python,
                variant_id=variant_id,
                project_root=str(root),
                expected_tree=expected_tree,
                argv=argv,
                execution_envelope=execution_envelope,
                expected_project_origins=expected_origins,
                call_trace_specs=trace_specs,
            ),
            reobserve_executables=False,
        )
    except FeasibilityProofError as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            "ledger",
        ) from exc


class _PytestCaptureState:
    """Process-local pytest observations; serialized only at session finish."""

    def __init__(
        self,
        *,
        project_root: Path,
        runtime_project_root: Path,
        role: str,
        trace_specs: tuple[CallTraceSpec, ...],
    ) -> None:
        self.project_root = project_root
        self.runtime_project_root = runtime_project_root
        self.role = role
        self.trace_specs = trace_specs
        self.collected_node_ids: list[str] = []
        self.reports: dict[str, dict[str, str]] = {}
        self.collection_errors: list[str] = []
        self.worker_errors: list[str] = []
        self.current_node_id: str | None = None
        self.active_frames: dict[int, tuple[object, CallTraceSpec, set[int]]] = {}
        self.transitions: list[dict[str, object]] = []


_PYTEST_CAPTURE_STATE: _PytestCaptureState | None = None


def _pytest_capture_request_from_environment() -> _PytestCaptureState:
    try:
        encoded = os.environ[_PYTEST_CAPTURE_REQUEST_ENV]
        raw = base64.b64decode(encoded.encode("ascii", "strict"), validate=True)
    except (KeyError, UnicodeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_pytest_capture_invalid",
            "worker_request",
        ) from exc
    request = _strict_json_object(raw, detail="worker_request")
    if (
        set(request) != _PYTEST_CAPTURE_REQUEST_KEYS
        or request["schema_version"] != _PYTEST_CAPTURE_REQUEST_SCHEMA_VERSION
        or type(request["project_root"]) is not str
        or type(request["runtime_project_root"]) is not str
        or type(request["role"]) is not str
        or request["role"] not in _PYTEST_LEDGER_ROLES
        or type(request["call_trace_specs"]) is not list
    ):
        _pytest_capture_invalid("worker_request")
    evidence_root_text = _validate_pytest_ledger_absolute_path(
        request["project_root"],
        label="worker_request.project_root",
    )
    root = Path(evidence_root_text)
    runtime_root = _canonical_project_root(Path(request["runtime_project_root"]))
    specs: list[CallTraceSpec] = []
    for index, row in enumerate(request["call_trace_specs"]):
        if type(row) is not dict or set(row) != _PYTEST_CAPTURE_TRACE_SPEC_KEYS:
            _pytest_capture_invalid(f"worker_request.call_trace_specs[{index}]")
        specs.append(
            CallTraceSpec(
                edge_id=row["edge_id"],
                pytest_node_id=row["pytest_node_id"],
                caller_path=row["caller_path"],
                caller_line=row["caller_line"],
                callee_path=row["callee_path"],
                callee_name=row["callee_name"],
                callee_first_line=row["callee_first_line"],
            )
        )
    trace_specs = _validate_call_trace_specs(tuple(specs))
    if request["role"] == "collection" and trace_specs:
        _pytest_capture_invalid("worker_request.call_trace_specs")
    return _PytestCaptureState(
        project_root=root,
        runtime_project_root=runtime_root,
        role=request["role"],
        trace_specs=trace_specs,
    )


def pytest_configure(config: object) -> None:
    """Initialize the explicit worker protocol when loaded as its pytest plugin."""

    del config
    global _PYTEST_CAPTURE_STATE
    if os.environ.get(_PYTEST_CAPTURE_PROTOCOL_ENV) != _PYTEST_CAPTURE_PROTOCOL_VERSION:
        return
    if _PYTEST_CAPTURE_STATE is not None:
        _PYTEST_CAPTURE_STATE.worker_errors.append("duplicate_configure")
        return
    _PYTEST_CAPTURE_STATE = _pytest_capture_request_from_environment()


def pytest_collection_finish(session: object) -> None:
    state = _PYTEST_CAPTURE_STATE
    if state is None:
        return
    try:
        node_ids = [item.nodeid for item in session.items]
    except (AttributeError, TypeError) as exc:
        state.worker_errors.append("collection_shape")
        return
    if (
        any(type(value) is not str or not value for value in node_ids)
        or len(set(node_ids)) != len(node_ids)
    ):
        state.worker_errors.append("collection_shape")
        return
    state.collected_node_ids = node_ids


def pytest_collectreport(report: object) -> None:
    state = _PYTEST_CAPTURE_STATE
    if state is None:
        return
    try:
        if report.failed:
            state.collection_errors.append(str(report.nodeid))
    except AttributeError:
        state.worker_errors.append("collection_report_shape")


def pytest_runtest_logreport(report: object) -> None:
    state = _PYTEST_CAPTURE_STATE
    if state is None:
        return
    try:
        node_id = report.nodeid
        phase = report.when
        outcome = report.outcome
    except AttributeError:
        state.worker_errors.append("test_report_shape")
        return
    if (
        type(node_id) is not str
        or phase not in {"setup", "call", "teardown"}
        or outcome not in {"passed", "failed", "skipped"}
    ):
        state.worker_errors.append("test_report_shape")
        return
    phases = state.reports.setdefault(node_id, {})
    if phase in phases:
        state.worker_errors.append("duplicate_test_report")
        return
    phases[phase] = outcome


def _worker_relative_path(state: _PytestCaptureState, filename: str) -> str | None:
    try:
        candidate = Path(filename)
        if not candidate.is_absolute():
            candidate = state.runtime_project_root / candidate
        resolved = candidate.resolve(strict=True)
        return resolved.relative_to(state.runtime_project_root).as_posix()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _pytest_capture_trace(frame: object, event: str, arg: object) -> object:
    del arg
    state = _PYTEST_CAPTURE_STATE
    if state is None or state.current_node_id is None:
        return None
    frame_id = id(frame)
    active = state.active_frames.get(frame_id)
    if active is not None:
        _, spec, line_hits = active
        if event == "line":
            line_hits.add(frame.f_lineno)
        elif event == "return":
            state.active_frames.pop(frame_id, None)
            state.transitions.append(
                {
                    "edge_id": spec.edge_id,
                    "pytest_node_id": spec.pytest_node_id,
                    "outcome": "passed",
                    "caller_path": spec.caller_path,
                    "caller_line": spec.caller_line,
                    "callee_path": spec.callee_path,
                    "callee_name": spec.callee_name,
                    "callee_first_line": spec.callee_first_line,
                    "callee_line_hits": sorted(line_hits),
                }
            )
        return _pytest_capture_trace
    if event != "call":
        return None
    caller = frame.f_back
    if caller is None:
        return None
    callee_path = _worker_relative_path(state, frame.f_code.co_filename)
    caller_path = _worker_relative_path(state, caller.f_code.co_filename)
    if callee_path is None or caller_path is None:
        return None
    matches = [
        spec
        for spec in state.trace_specs
        if spec.pytest_node_id == state.current_node_id
        and spec.caller_path == caller_path
        and spec.caller_line == caller.f_lineno
        and spec.callee_path == callee_path
        and spec.callee_name == frame.f_code.co_name
        and spec.callee_first_line == frame.f_code.co_firstlineno
    ]
    if len(matches) > 1:
        state.worker_errors.append("ambiguous_trace")
        return None
    if not matches:
        return None
    state.active_frames[frame_id] = (frame, matches[0], set())
    return _pytest_capture_trace


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item: object) -> object:
    state = _PYTEST_CAPTURE_STATE
    if state is None:
        yield
        return
    previous = sys.gettrace()
    if previous is not None:
        state.worker_errors.append("existing_trace")
    try:
        state.current_node_id = item.nodeid
        if previous is None:
            sys.settrace(_pytest_capture_trace)
        yield
    finally:
        sys.settrace(previous)
        state.current_node_id = None
        if state.active_frames:
            state.worker_errors.append("unterminated_trace")
            state.active_frames.clear()


def _worker_node_outcomes(
    state: _PytestCaptureState,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    if state.role == "collection":
        if state.reports:
            state.worker_errors.append("collection_executed_tests")
        return [], {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    rows: list[dict[str, object]] = []
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for node_id in state.collected_node_ids:
        phases = state.reports.get(node_id, {})
        failed_phases = [
            phase for phase in ("setup", "call", "teardown") if phases.get(phase) == "failed"
        ]
        if len(failed_phases) > 1:
            state.worker_errors.append("multiple_terminal_failures")
            continue
        if failed_phases:
            phase = failed_phases[0]
            outcome = "failed" if phase == "call" else "error"
            failure_phase: str | None = phase
        elif any(phases.get(phase) == "skipped" for phase in ("setup", "call", "teardown")):
            outcome = "skipped"
            failure_phase = None
        elif phases.get("call") == "passed":
            outcome = "passed"
            failure_phase = None
        else:
            state.worker_errors.append("missing_terminal_report")
            continue
        rows.append(
            {
                "node_id": node_id,
                "outcome": outcome,
                "failure_phase": failure_phase,
            }
        )
        counts["errors" if outcome == "error" else outcome] += 1
    unknown_reports = set(state.reports) - set(state.collected_node_ids)
    if unknown_reports:
        state.worker_errors.append("unknown_test_report")
    return rows, counts


def _worker_project_origins(state: _PytestCaptureState) -> list[dict[str, str]]:
    origins: list[dict[str, str]] = []
    for module_name, module in sys.modules.items():
        raw_path = getattr(module, "__file__", None)
        if type(module_name) is not str or not module_name or type(raw_path) is not str:
            continue
        try:
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = state.runtime_project_root / candidate
            resolved = candidate.resolve(strict=True)
            relative = resolved.relative_to(state.runtime_project_root)
        except (OSError, RuntimeError, ValueError):
            continue
        origins.append(
            {
                "module_name": module_name,
                "resolved_path": str(state.project_root / relative),
            }
        )
    origins.sort(key=lambda row: row["module_name"].encode("utf-8", "strict"))
    if len({row["module_name"] for row in origins}) != len(origins):
        state.worker_errors.append("duplicate_project_origin")
    return origins


def pytest_sessionfinish(session: object, exitstatus: object) -> None:
    del session
    state = _PYTEST_CAPTURE_STATE
    if state is None:
        return
    node_outcomes, outcome_counts = _worker_node_outcomes(state)
    transitions = sorted(
        state.transitions,
        key=lambda row: (
            row["pytest_node_id"].encode("utf-8", "strict"),
            row["edge_id"].encode("utf-8", "strict"),
        ),
    )
    transition_keys = [
        (row["pytest_node_id"], row["edge_id"]) for row in transitions
    ]
    if len(set(transition_keys)) != len(transition_keys):
        state.worker_errors.append("duplicate_trace")
    expected_trace_keys = [
        (spec.pytest_node_id, spec.edge_id) for spec in state.trace_specs
    ]
    if transition_keys != expected_trace_keys:
        state.worker_errors.append("trace_coverage")
    try:
        exit_code = int(exitstatus)
    except (TypeError, ValueError):
        exit_code = -1
        state.worker_errors.append("exit_status")
    response = {
        "schema_version": _PYTEST_CAPTURE_SCHEMA_VERSION,
        "runner_path": str(Path(__file__).resolve()),
        "runner_sha256": runner_sha256(Path(__file__).resolve()),
        "project_root": str(state.project_root),
        "cwd": str(Path.cwd().resolve()),
        "collected_node_ids": state.collected_node_ids,
        "node_outcomes": node_outcomes,
        "outcome_counts": outcome_counts,
        "project_origins": _worker_project_origins(state),
        "call_transitions": transitions,
        "exit_code": exit_code,
        "collection_errors": state.collection_errors,
        "worker_errors": state.worker_errors,
    }
    encoded = base64.b64encode(canonical_json_bytes(response))
    try:
        os.write(1, b"\n" + _PYTEST_CAPTURE_SENTINEL + encoded + b"\n")
    except OSError:
        pass


def _canonical_bare_repository(path: Path) -> tuple[Path, tuple[int, int, int]]:
    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=True)
        identity = candidate.lstat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_git_store_invalid",
            str(candidate),
        ) from exc
    if (
        not candidate.is_absolute()
        or candidate != resolved
        or candidate.is_symlink()
        or not stat.S_ISDIR(identity.st_mode)
    ):
        raise FeasibilityProofError(
            "feasibility_git_store_invalid",
            str(candidate),
        )
    for relative in ("objects/info/alternates", "objects/info/http-alternates"):
        if (candidate / relative).exists() or (candidate / relative).is_symlink():
            raise FeasibilityProofError(
                "feasibility_git_store_invalid",
                str(candidate),
            )
    return candidate, (identity.st_dev, identity.st_ino, identity.st_mode)


class GitObjectStore:
    """Read authenticated objects from exactly one bare Git repository."""

    def __init__(
        self,
        repository: Path,
        git_binding: Mapping[str, object],
    ) -> None:
        self._git_binding = verify_executable_binding(git_binding, role="git")
        self.repository, self._repository_identity = _canonical_bare_repository(
            Path(repository)
        )
        try:
            completed = self._run(("rev-parse", "--is-bare-repository"))
        except FeasibilityProofError as exc:
            raise FeasibilityProofError(
                "feasibility_git_store_invalid",
                str(self.repository),
            ) from exc
        if completed.stdout != b"true\n":
            raise FeasibilityProofError(
                "feasibility_git_store_invalid",
                str(self.repository),
            )
        config = self._run(("config", "--local", "--null", "--name-only", "--list"))
        if config.stdout and not config.stdout.endswith(b"\0"):
            raise FeasibilityProofError(
                "feasibility_git_store_invalid",
                str(self.repository),
            )
        try:
            config_keys = tuple(
                item.decode("utf-8", "strict").casefold()
                for item in config.stdout.split(b"\0")
                if item
            )
        except UnicodeError as exc:
            raise FeasibilityProofError(
                "feasibility_git_store_invalid",
                str(self.repository),
            ) from exc
        if any(_PROMISOR_CONFIG_RE.fullmatch(key) for key in config_keys):
            raise FeasibilityProofError(
                "feasibility_git_store_invalid",
                str(self.repository),
            )

    def _validate_repository_identity(self) -> None:
        repository, identity = _canonical_bare_repository(self.repository)
        if repository != self.repository or identity != self._repository_identity:
            raise FeasibilityProofError(
                "feasibility_git_store_invalid",
                str(self.repository),
            )

    @property
    def executable_binding_sha256(self) -> str:
        """Return a stable identity for the already-verified Git binding."""

        return _sha256(canonical_json_bytes(self._git_binding))

    def _run(
        self,
        argv: tuple[str, ...],
        *,
        input_bytes: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        self._validate_repository_identity()
        verified_before = verify_executable_binding(self._git_binding, role="git")
        if verified_before != self._git_binding:
            raise FeasibilityProofError(
                "feasibility_git_command_failed",
                str(self.repository),
            )
        literal_path = self._git_binding["literal_path"]
        assert isinstance(literal_path, str)
        environment = {
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": "",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "HOME": "/",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
        }
        try:
            completed = subprocess.run(
                (
                    literal_path,
                    "--no-replace-objects",
                    f"--git-dir={self.repository}",
                    *argv,
                ),
                cwd=Path("/"),
                env=environment,
                check=False,
                shell=False,
                timeout=5.0,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FeasibilityProofError(
                "feasibility_git_command_failed",
                str(self.repository),
            ) from exc
        verified_after = verify_executable_binding(self._git_binding, role="git")
        if verified_after != self._git_binding:
            raise FeasibilityProofError(
                "feasibility_git_command_failed",
                str(self.repository),
            )
        self._validate_repository_identity()
        if completed.returncode != 0 or completed.stderr:
            raise FeasibilityProofError(
                "feasibility_git_command_failed",
                str(self.repository),
            )
        return completed

    @staticmethod
    def _validate_batch_oids(oids: tuple[str, ...]) -> None:
        if (
            not isinstance(oids, tuple)
            or not oids
            or len(oids) > _GIT_OBJECT_BATCH_LIMIT
            or len(set(oids)) != len(oids)
        ):
            raise FeasibilityProofError("feasibility_git_batch_invalid")
        for oid in oids:
            if not isinstance(oid, str) or _SHA1_RE.fullmatch(oid) is None:
                raise FeasibilityProofError("feasibility_git_oid_invalid", oid)

    def _read_optional_many(
        self,
        oids: tuple[str, ...],
    ) -> tuple[GitObject | None, ...]:
        self._validate_batch_oids(oids)
        completed = self._run(
            ("cat-file", "--batch"),
            input_bytes=("\n".join(oids) + "\n").encode("ascii"),
        )
        raw = completed.stdout
        cursor = 0
        results: list[GitObject | None] = []
        for oid in oids:
            line_end = raw.find(b"\n", cursor)
            if line_end < cursor:
                raise FeasibilityProofError("feasibility_git_object_invalid", oid)
            header = raw[cursor:line_end]
            cursor = line_end + 1
            if header == f"{oid} missing".encode("ascii"):
                results.append(None)
                continue
            fields = header.split(b" ")
            if len(fields) != 3:
                raise FeasibilityProofError("feasibility_git_object_invalid", oid)
            try:
                actual_oid = fields[0].decode("ascii", "strict")
                object_type = fields[1].decode("ascii", "strict")
                size_text = fields[2].decode("ascii", "strict")
                size = int(size_text, 10)
            except (UnicodeError, ValueError) as exc:
                raise FeasibilityProofError(
                    "feasibility_git_object_invalid",
                    oid,
                ) from exc
            payload_end = cursor + size
            if (
                actual_oid != oid
                or object_type not in {"blob", "tree", "commit", "tag"}
                or size < 0
                or str(size) != size_text
                or payload_end >= len(raw)
                or raw[payload_end : payload_end + 1] != b"\n"
            ):
                raise FeasibilityProofError("feasibility_git_object_invalid", oid)
            payload = raw[cursor:payload_end]
            cursor = payload_end + 1
            framed = f"{object_type} {size}\0".encode("ascii") + payload
            observed_oid = hashlib.sha1(
                framed,
                usedforsecurity=False,
            ).hexdigest()
            if observed_oid != oid:
                raise FeasibilityProofError("feasibility_git_object_invalid", oid)
            results.append(GitObject(oid, object_type, payload))
        if cursor != len(raw):
            detail = oids[-1]
            raise FeasibilityProofError("feasibility_git_object_invalid", detail)
        return tuple(results)

    def read_many(self, oids: tuple[str, ...]) -> tuple[GitObject, ...]:
        """Read one bounded ordered batch, rejecting any missing object."""

        optional = self._read_optional_many(oids)
        for oid, value in zip(oids, optional):
            if value is None:
                raise FeasibilityProofError("feasibility_git_object_missing", oid)
        return tuple(value for value in optional if value is not None)

    def read(self, oid: str) -> GitObject:
        """Read one exact object and verify its Git object identity."""

        return self.read_many((oid,))[0]


class GitObjectPair:
    """Read from one explicit primary store, then one explicit fallback store."""

    def __init__(self, primary: GitObjectStore, fallback: GitObjectStore) -> None:
        if (
            not isinstance(primary, GitObjectStore)
            or not isinstance(fallback, GitObjectStore)
            or primary.repository == fallback.repository
            or primary.executable_binding_sha256
            != fallback.executable_binding_sha256
        ):
            raise FeasibilityProofError("feasibility_git_store_pair_invalid")
        self._primary = primary
        self._fallback = fallback

    def read_primary(self, oid: str) -> GitObject:
        return self._primary.read(oid)

    def read_fallback(self, oid: str) -> GitObject:
        return self._fallback.read(oid)

    def read_primary_many(self, oids: tuple[str, ...]) -> tuple[GitObject, ...]:
        return self._primary.read_many(oids)

    def read_fallback_many(self, oids: tuple[str, ...]) -> tuple[GitObject, ...]:
        return self._fallback.read_many(oids)

    def read(self, oid: str) -> GitObject:
        try:
            return self.read_primary(oid)
        except FeasibilityProofError as exc:
            if exc.code != "feasibility_git_object_missing":
                raise
        return self.read_fallback(oid)

    def read_many(self, oids: tuple[str, ...]) -> tuple[GitObject, ...]:
        """Read one bounded batch, falling back only for primary misses."""

        primary_values = self._primary._read_optional_many(oids)
        missing_oids = tuple(
            oid for oid, value in zip(oids, primary_values) if value is None
        )
        fallback_by_oid: dict[str, GitObject] = {}
        if missing_oids:
            fallback_values = self._fallback.read_many(missing_oids)
            fallback_by_oid = dict(zip(missing_oids, fallback_values))
        return tuple(
            value if value is not None else fallback_by_oid[oid]
            for oid, value in zip(oids, primary_values)
        )


def _tree_component(raw: bytes, *, tree_oid: str) -> str:
    try:
        value = raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise FeasibilityProofError("feasibility_git_tree_invalid", tree_oid) from exc
    if (
        not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\0" in value
    ):
        raise FeasibilityProofError("feasibility_git_tree_invalid", tree_oid)
    return value


def _parse_tree_entries(tree_object: GitObject) -> tuple[tuple[str, str, str], ...]:
    if tree_object.object_type != "tree":
        raise FeasibilityProofError(
            "feasibility_git_tree_invalid",
            tree_object.oid,
        )
    entries: list[tuple[str, str, str]] = []
    sort_keys: list[bytes] = []
    names: set[str] = set()
    cursor = 0
    payload = tree_object.payload
    while cursor < len(payload):
        space = payload.find(b" ", cursor)
        if space <= cursor:
            raise FeasibilityProofError(
                "feasibility_git_tree_invalid",
                tree_object.oid,
            )
        nul = payload.find(b"\0", space + 1)
        if nul <= space + 1 or nul + 21 > len(payload):
            raise FeasibilityProofError(
                "feasibility_git_tree_invalid",
                tree_object.oid,
            )
        try:
            mode = payload[cursor:space].decode("ascii", "strict")
        except UnicodeError as exc:
            raise FeasibilityProofError(
                "feasibility_git_tree_invalid",
                tree_object.oid,
            ) from exc
        if mode not in {"100644", "100755", "120000", "40000"}:
            raise FeasibilityProofError(
                "feasibility_git_tree_invalid",
                tree_object.oid,
            )
        raw_name = payload[space + 1 : nul]
        name = _tree_component(raw_name, tree_oid=tree_object.oid)
        if name in names:
            raise FeasibilityProofError(
                "feasibility_git_tree_invalid",
                tree_object.oid,
            )
        names.add(name)
        entry_oid = payload[nul + 1 : nul + 21].hex()
        sort_keys.append(raw_name + (b"/" if mode == "40000" else b"\0"))
        entries.append((mode, name, entry_oid))
        cursor = nul + 21
    if cursor != len(payload) or any(
        left >= right for left, right in zip(sort_keys, sort_keys[1:])
    ):
        raise FeasibilityProofError(
            "feasibility_git_tree_invalid",
            tree_object.oid,
        )
    return tuple(entries)


def read_tree_leaves(
    reader: GitObjectStore | GitObjectPair,
    tree_oid: str,
) -> tuple[TreeLeaf, ...]:
    """Recursively authenticate one tree and return path-sorted regular leaves."""

    if not isinstance(reader, (GitObjectStore, GitObjectPair)):
        raise FeasibilityProofError("feasibility_git_tree_invalid", "reader")
    leaves: list[TreeLeaf] = []
    blob_rows: list[tuple[str, str, str, str]] = []
    frontier: list[tuple[str, tuple[str, ...], frozenset[str]]] = [
        (tree_oid, (), frozenset())
    ]
    while frontier:
        for oid, _, ancestors in frontier:
            if oid in ancestors:
                raise FeasibilityProofError("feasibility_git_tree_invalid", oid)
        unique_tree_oids = tuple(dict.fromkeys(oid for oid, _, _ in frontier))
        trees_by_oid: dict[str, GitObject] = {}
        for offset in range(0, len(unique_tree_oids), _GIT_OBJECT_BATCH_LIMIT):
            chunk = unique_tree_oids[offset : offset + _GIT_OBJECT_BATCH_LIMIT]
            trees_by_oid.update(zip(chunk, reader.read_many(chunk)))
        next_frontier: list[tuple[str, tuple[str, ...], frozenset[str]]] = []
        for oid, prefix, ancestors in frontier:
            entries = _parse_tree_entries(trees_by_oid[oid])
            next_ancestors = ancestors | {oid}
            for mode, name, entry_oid in entries:
                path_parts = (*prefix, name)
                if mode == "40000":
                    next_frontier.append(
                        (entry_oid, path_parts, next_ancestors)
                    )
                    continue
                blob_rows.append(("/".join(path_parts), mode, entry_oid, oid))
        frontier = next_frontier

    unique_blob_oids = tuple(dict.fromkeys(oid for _, _, oid, _ in blob_rows))
    blob_types: dict[str, str] = {}
    for offset in range(0, len(unique_blob_oids), _GIT_OBJECT_BATCH_LIMIT):
        chunk = unique_blob_oids[offset : offset + _GIT_OBJECT_BATCH_LIMIT]
        blob_types.update(
            (oid, value.object_type)
            for oid, value in zip(chunk, reader.read_many(chunk))
        )
    for path, mode, blob_oid, parent_oid in blob_rows:
        if blob_types[blob_oid] != "blob":
            raise FeasibilityProofError(
                "feasibility_git_tree_invalid",
                parent_oid,
            )
        leaves.append(TreeLeaf(path=path, mode=mode, blob_oid=blob_oid))

    ordered = tuple(sorted(leaves, key=lambda leaf: leaf.path.encode("utf-8")))
    if len({leaf.path for leaf in ordered}) != len(ordered):
        raise FeasibilityProofError("feasibility_git_tree_invalid", tree_oid)
    return ordered


def _split_leaf_path(path: object) -> tuple[str, ...]:
    if not isinstance(path, str) or not path or path.startswith("/"):
        raise FeasibilityProofError("feasibility_git_overlay_invalid", path)
    try:
        path.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise FeasibilityProofError("feasibility_git_overlay_invalid", path) from exc
    if "\\" in path or "\0" in path:
        raise FeasibilityProofError("feasibility_git_overlay_invalid", path)
    parts = tuple(path.split("/"))
    if any(not part or part in {".", ".."} for part in parts):
        raise FeasibilityProofError("feasibility_git_overlay_invalid", path)
    return parts


def _validate_leaf_rows(
    rows: tuple[TreeLeaf, ...],
    *,
    overlay: bool,
) -> tuple[tuple[str, ...], ...]:
    expected_type = OverlayRow if overlay else TreeLeaf
    if not isinstance(rows, tuple) or not rows:
        raise FeasibilityProofError("feasibility_git_overlay_invalid", "rows")
    if any(not isinstance(row, expected_type) for row in rows):
        raise FeasibilityProofError("feasibility_git_overlay_invalid", "row_type")
    if any(
        not isinstance(row.path, str)
        or not isinstance(row.mode, str)
        or not isinstance(row.blob_oid, str)
        for row in rows
    ):
        raise FeasibilityProofError(
            "feasibility_git_overlay_invalid",
            "row_field_type",
        )
    parts = tuple(_split_leaf_path(row.path) for row in rows)
    paths = tuple(row.path for row in rows)
    if (
        paths != tuple(sorted(paths, key=lambda value: value.encode("utf-8")))
        or len(set(paths)) != len(paths)
    ):
        raise FeasibilityProofError("feasibility_git_overlay_invalid", "row_order")
    for row in rows:
        allowed_modes = {"100644"} if overlay else {"100644", "100755", "120000"}
        if row.mode not in allowed_modes or _SHA1_RE.fullmatch(row.blob_oid) is None:
            raise FeasibilityProofError(
                "feasibility_git_overlay_invalid",
                row.path,
            )
    return parts


def _synthesize_tree_objects(
    leaves: tuple[TreeLeaf, ...],
) -> tuple[str, tuple[GitObject, ...]]:
    leaf_parts = _validate_leaf_rows(leaves, overlay=False)
    file_paths = set(leaf_parts)
    directories: set[tuple[str, ...]] = {()}
    for parts in leaf_parts:
        directories.update(parts[:depth] for depth in range(1, len(parts)))
    if file_paths & directories:
        conflict = "/".join(next(iter(file_paths & directories)))
        raise FeasibilityProofError("feasibility_git_overlay_invalid", conflict)
    entries_by_directory: dict[tuple[str, ...], list[tuple[str, str, str]]] = {
        directory: [] for directory in directories
    }
    for leaf, parts in zip(leaves, leaf_parts):
        entries_by_directory[parts[:-1]].append(
            (leaf.mode, parts[-1], leaf.blob_oid)
        )
    objects_by_directory: dict[tuple[str, ...], GitObject] = {}
    deepest_first = sorted(
        directories,
        key=lambda parts: (-len(parts), "/".join(parts).encode("utf-8")),
    )
    for directory in deepest_first:
        entries = entries_by_directory[directory]
        entries.sort(
            key=lambda item: item[1].encode("utf-8")
            + (b"/" if item[0] == "40000" else b"\0")
        )
        if len({name for _, name, _ in entries}) != len(entries):
            raise FeasibilityProofError(
                "feasibility_git_overlay_invalid",
                "/".join(directory),
            )
        payload = b"".join(
            mode.encode("ascii")
            + b" "
            + name.encode("utf-8")
            + b"\0"
            + bytes.fromhex(oid)
            for mode, name, oid in entries
        )
        framed = f"tree {len(payload)}\0".encode("ascii") + payload
        oid = hashlib.sha1(framed, usedforsecurity=False).hexdigest()
        tree_object = GitObject(oid=oid, object_type="tree", payload=payload)
        objects_by_directory[directory] = tree_object
        if directory:
            entries_by_directory[directory[:-1]].append(
                ("40000", directory[-1], oid)
            )
    root = objects_by_directory[()]
    ordered_objects = tuple(
        objects_by_directory[directory]
        for directory in sorted(
            directories,
            key=lambda parts: "/".join(parts).encode("utf-8"),
        )
    )
    return root.oid, ordered_objects


def derive_overlay_tree(
    reader: GitObjectPair,
    *,
    base_leaves: tuple[TreeLeaf, ...],
    overlay: tuple[OverlayRow, ...],
    expected_tree_oid: str | None,
) -> DerivedTree:
    """Derive one addition-only tree from authenticated base and overlay rows."""

    if not isinstance(reader, GitObjectPair):
        raise FeasibilityProofError("feasibility_git_overlay_invalid", "reader")
    _validate_leaf_rows(base_leaves, overlay=False)
    _validate_leaf_rows(overlay, overlay=True)
    base_paths = {row.path for row in base_leaves}
    if base_paths & {row.path for row in overlay}:
        raise FeasibilityProofError("feasibility_git_overlay_invalid", "base_overlap")
    overlay_oids = tuple(dict.fromkeys(row.blob_oid for row in overlay))
    overlay_objects: dict[str, GitObject] = {}
    try:
        for offset in range(0, len(overlay_oids), _GIT_OBJECT_BATCH_LIMIT):
            chunk = overlay_oids[offset : offset + _GIT_OBJECT_BATCH_LIMIT]
            overlay_objects.update(zip(chunk, reader.read_primary_many(chunk)))
    except FeasibilityProofError as exc:
        raise FeasibilityProofError(
            "feasibility_git_overlay_invalid",
            "overlay_object",
        ) from exc
    if any(value.object_type != "blob" for value in overlay_objects.values()):
        raise FeasibilityProofError(
            "feasibility_git_overlay_invalid",
            "overlay_object_type",
        )
    leaves = tuple(
        sorted(
            (
                *base_leaves,
                *(
                    TreeLeaf(row.path, row.mode, row.blob_oid)
                    for row in overlay
                ),
            ),
            key=lambda row: row.path.encode("utf-8"),
        )
    )
    tree_oid, tree_objects = _synthesize_tree_objects(leaves)
    if expected_tree_oid is not None:
        if (
            not isinstance(expected_tree_oid, str)
            or _SHA1_RE.fullmatch(expected_tree_oid) is None
            or tree_oid != expected_tree_oid
        ):
            raise FeasibilityProofError(
                "feasibility_git_overlay_invalid",
                "expected_tree_oid",
            )
    return DerivedTree(
        tree_oid=tree_oid,
        leaves=leaves,
        generated_tree_objects=tree_objects,
    )


def validate_overlay_partition(
    overlay: tuple[OverlayRow, ...],
    *,
    test_slice: OverlaySlice,
    cluster_slices: tuple[OverlaySlice, ...],
) -> None:
    """Validate one exact disjoint, exhaustive overlay partition."""

    try:
        _validate_leaf_rows(overlay, overlay=True)
    except FeasibilityProofError as exc:
        raise FeasibilityProofError("feasibility_git_partition_invalid") from exc
    if (
        not isinstance(test_slice, OverlaySlice)
        or not isinstance(cluster_slices, tuple)
        or not cluster_slices
        or any(not isinstance(item, OverlaySlice) for item in cluster_slices)
    ):
        raise FeasibilityProofError("feasibility_git_partition_invalid")
    slices = (test_slice, *cluster_slices)
    ordinals = tuple(item.ordinal for item in slices)
    if any(type(value) is not int for value in ordinals) or ordinals != tuple(
        range(len(slices))
    ):
        raise FeasibilityProofError("feasibility_git_partition_invalid")
    slice_ids: list[str] = []
    assigned_paths: list[str] = []
    overlay_paths = {row.path for row in overlay}
    for item in slices:
        if not isinstance(item.slice_id, str) or not item.slice_id:
            raise FeasibilityProofError("feasibility_git_partition_invalid")
        try:
            item.slice_id.encode("utf-8", "strict")
        except UnicodeError as exc:
            raise FeasibilityProofError(
                "feasibility_git_partition_invalid"
            ) from exc
        if (
            not isinstance(item.paths, tuple)
            or not item.paths
            or any(not isinstance(path, str) for path in item.paths)
        ):
            raise FeasibilityProofError("feasibility_git_partition_invalid")
        try:
            for path in item.paths:
                _split_leaf_path(path)
        except FeasibilityProofError as exc:
            raise FeasibilityProofError(
                "feasibility_git_partition_invalid"
            ) from exc
        if (
            item.paths
            != tuple(sorted(item.paths, key=lambda path: path.encode("utf-8")))
            or len(set(item.paths)) != len(item.paths)
            or any(path not in overlay_paths for path in item.paths)
        ):
            raise FeasibilityProofError("feasibility_git_partition_invalid")
        slice_ids.append(item.slice_id)
        assigned_paths.extend(item.paths)
    if (
        len(set(slice_ids)) != len(slice_ids)
        or len(set(assigned_paths)) != len(assigned_paths)
        or set(assigned_paths) != overlay_paths
    ):
        raise FeasibilityProofError("feasibility_git_partition_invalid")


def derive_overlay_variants(
    reader: GitObjectPair,
    *,
    base_leaves: tuple[TreeLeaf, ...],
    overlay: tuple[OverlayRow, ...],
    test_slice: OverlaySlice,
    cluster_slices: tuple[OverlaySlice, ...],
    expected_full_tree_oid: str | None,
) -> tuple[TreeVariant, ...]:
    """Derive full, test-only, and every remove-one cluster tree."""

    validate_overlay_partition(
        overlay,
        test_slice=test_slice,
        cluster_slices=cluster_slices,
    )
    rows_by_path = {row.path: row for row in overlay}

    def derive(
        variant_id: str,
        paths: tuple[str, ...],
        *,
        omitted_cluster_id: str | None,
        expected_tree_oid: str | None,
    ) -> TreeVariant:
        included = tuple(sorted(paths, key=lambda path: path.encode("utf-8")))
        tree = derive_overlay_tree(
            reader,
            base_leaves=base_leaves,
            overlay=tuple(rows_by_path[path] for path in included),
            expected_tree_oid=expected_tree_oid,
        )
        return TreeVariant(
            variant_id=variant_id,
            included_overlay_paths=included,
            omitted_cluster_id=omitted_cluster_id,
            tree=tree,
        )

    all_paths = tuple(row.path for row in overlay)
    variants: list[TreeVariant] = [
        derive(
            "full",
            all_paths,
            omitted_cluster_id=None,
            expected_tree_oid=expected_full_tree_oid,
        ),
        derive(
            "test_only",
            test_slice.paths,
            omitted_cluster_id=None,
            expected_tree_oid=None,
        ),
    ]
    for cluster in cluster_slices:
        omitted = set(cluster.paths)
        included = tuple(path for path in all_paths if path not in omitted)
        variants.append(
            derive(
                f"remove_one:{cluster.slice_id}",
                included,
                omitted_cluster_id=cluster.slice_id,
                expected_tree_oid=None,
            )
        )
    return tuple(variants)


def _node_span(node: ast.AST) -> tuple[int | None, ...]:
    return (
        getattr(node, "lineno", None),
        getattr(node, "col_offset", None),
        getattr(node, "end_lineno", None),
        getattr(node, "end_col_offset", None),
    )


def _declared_span(span: AstSpan) -> tuple[int, int, int, int]:
    return (
        span.start_line,
        span.start_column,
        span.end_line,
        span.end_column,
    )


def _terminal_call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _ast_edge_invalid(detail: object = "") -> NoReturn:
    raise FeasibilityProofError("feasibility_ast_edge_invalid", detail)


def _validate_ast_text(value: object, *, label: str) -> str:
    if type(value) is not str or not value:
        _ast_edge_invalid(label)
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise FeasibilityProofError(
            "feasibility_ast_edge_invalid",
            label,
        ) from exc
    return value


def _validate_ast_path(value: object, *, label: str) -> str:
    path = _validate_ast_text(value, label=label)
    try:
        _split_leaf_path(path)
    except FeasibilityProofError as exc:
        raise FeasibilityProofError(
            "feasibility_ast_edge_invalid",
            label,
        ) from exc
    return path


def _validate_ast_span(value: object, *, label: str) -> AstSpan:
    if type(value) is not AstSpan:
        _ast_edge_invalid(label)
    coordinates = (
        value.start_line,
        value.start_column,
        value.end_line,
        value.end_column,
    )
    if (
        any(type(item) is not int for item in coordinates)
        or value.start_line < 1
        or value.end_line < 1
        or value.start_column < 0
        or value.end_column < 0
        or (value.start_line, value.start_column)
        >= (value.end_line, value.end_column)
    ):
        _ast_edge_invalid(label)
    return value


def _validate_ast_node_ref(
    value: object,
    *,
    producer: bool,
    label: str,
) -> AstNodeRef:
    if type(value) is not AstNodeRef:
        _ast_edge_invalid(label)
    _validate_ast_path(value.path, label=f"{label}.path")
    if type(value.blob_oid) is not str or _SHA1_RE.fullmatch(value.blob_oid) is None:
        _ast_edge_invalid(f"{label}.blob_oid")
    node_type = _validate_ast_text(value.node_type, label=f"{label}.node_type")
    allowed_types = {"FunctionDef", "AsyncFunctionDef"} if producer else {"Call"}
    if node_type not in allowed_types:
        _ast_edge_invalid(f"{label}.node_type")
    _validate_ast_text(value.name, label=f"{label}.name")
    _validate_ast_span(value.span, label=f"{label}.span")
    return value


def _validate_call_transition(value: object, *, label: str) -> CallTransition:
    if type(value) is not CallTransition:
        _ast_edge_invalid(label)
    _validate_ast_text(value.edge_id, label=f"{label}.edge_id")
    _validate_ast_text(value.pytest_node_id, label=f"{label}.pytest_node_id")
    _validate_ast_text(value.outcome, label=f"{label}.outcome")
    _validate_ast_path(value.caller_path, label=f"{label}.caller_path")
    _validate_ast_path(value.callee_path, label=f"{label}.callee_path")
    _validate_ast_text(value.callee_name, label=f"{label}.callee_name")
    if (
        type(value.caller_line) is not int
        or value.caller_line < 1
        or type(value.callee_first_line) is not int
        or value.callee_first_line < 1
        or type(value.callee_line_hits) is not tuple
        or not value.callee_line_hits
        or any(type(line) is not int or line < 1 for line in value.callee_line_hits)
        or any(
            left >= right
            for left, right in zip(
                value.callee_line_hits,
                value.callee_line_hits[1:],
            )
        )
    ):
        _ast_edge_invalid(label)
    return value


def validate_directed_ast_edges(
    reader: GitObjectPair,
    *,
    edges: tuple[DirectedAstEdge, ...],
    transitions: tuple[CallTransition, ...],
) -> None:
    """Validate authenticated definition-to-call edges and runtime transitions."""

    if type(reader) is not GitObjectPair:
        _ast_edge_invalid("reader")
    if type(edges) is not tuple or not edges:
        _ast_edge_invalid("edges")
    if type(transitions) is not tuple or not transitions:
        _ast_edge_invalid("transitions")

    for index, edge in enumerate(edges):
        if type(edge) is not DirectedAstEdge:
            _ast_edge_invalid(f"edges[{index}]")
        _validate_ast_text(edge.edge_id, label=f"edges[{index}].edge_id")
        _validate_ast_text(
            edge.pytest_node_id,
            label=f"edges[{index}].pytest_node_id",
        )
        _validate_ast_node_ref(
            edge.producer,
            producer=True,
            label=f"edges[{index}].producer",
        )
        _validate_ast_node_ref(
            edge.consumer,
            producer=False,
            label=f"edges[{index}].consumer",
        )
        if (
            edge.producer.path == edge.consumer.path
            or edge.producer.blob_oid == edge.consumer.blob_oid
        ):
            _ast_edge_invalid(f"edges[{index}].endpoints")
    for index, transition in enumerate(transitions):
        _validate_call_transition(transition, label=f"transitions[{index}]")

    edge_ids = tuple(edge.edge_id for edge in edges)
    ordered_edge_ids = tuple(
        sorted(edge_ids, key=lambda value: value.encode("utf-8", "strict"))
    )
    if (
        edge_ids != ordered_edge_ids
        or len(set(edge_ids)) != len(edge_ids)
        or tuple(item.edge_id for item in transitions) != edge_ids
    ):
        _ast_edge_invalid("edge_order")
    endpoint_oids = tuple(
        dict.fromkeys(
            node.blob_oid
            for edge in edges
            for node in (edge.producer, edge.consumer)
        )
    )
    try:
        objects_by_oid: dict[str, GitObject] = {}
        for offset in range(0, len(endpoint_oids), _GIT_OBJECT_BATCH_LIMIT):
            chunk = endpoint_oids[offset : offset + _GIT_OBJECT_BATCH_LIMIT]
            objects = reader.read_primary_many(chunk)
            if len(objects) != len(chunk):
                raise ValueError("object_count")
            for oid, value in zip(chunk, objects):
                if (
                    type(value) is not GitObject
                    or value.oid != oid
                    or value.object_type != "blob"
                    or type(value.payload) is not bytes
                ):
                    raise ValueError(oid)
                framed = f"blob {len(value.payload)}\0".encode("ascii") + value.payload
                if hashlib.sha1(
                    framed,
                    usedforsecurity=False,
                ).hexdigest() != oid:
                    raise ValueError(oid)
                objects_by_oid[oid] = value
        parsed_by_oid: dict[str, ast.Module] = {}
        for oid in endpoint_oids:
            source = objects_by_oid[oid].payload.decode("utf-8", "strict")
            parsed_by_oid[oid] = ast.parse(source)
    except (
        FeasibilityProofError,
        KeyError,
        TypeError,
        UnicodeError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise FeasibilityProofError("feasibility_ast_edge_invalid") from exc

    for edge, transition in zip(edges, transitions):
        producer_matches = [
            node
            for node in ast.walk(parsed_by_oid[edge.producer.blob_oid])
            if type(node) in {ast.FunctionDef, ast.AsyncFunctionDef}
            and type(node).__name__ == edge.producer.node_type
            and node.name == edge.producer.name
            and _node_span(node) == _declared_span(edge.producer.span)
        ]
        consumer_matches = [
            node
            for node in ast.walk(parsed_by_oid[edge.consumer.blob_oid])
            if type(node) is ast.Call
            and edge.consumer.node_type == "Call"
            and _terminal_call_name(node) == edge.consumer.name
            and _node_span(node) == _declared_span(edge.consumer.span)
        ]
        if len(producer_matches) != 1 or len(consumer_matches) != 1:
            _ast_edge_invalid(edge.edge_id)
        producer = producer_matches[0]
        decorator_lines = tuple(item.lineno for item in producer.decorator_list)
        first_line = min((producer.lineno, *decorator_lines))
        body_statement_spans = tuple(
            (statement.lineno, statement.end_lineno)
            for statement in producer.body
        )
        if (
            transition.edge_id != edge.edge_id
            or transition.pytest_node_id != edge.pytest_node_id
            or transition.outcome != "passed"
            or transition.caller_path != edge.consumer.path
            or not (
                edge.consumer.span.start_line
                <= transition.caller_line
                <= edge.consumer.span.end_line
            )
            or transition.callee_path != edge.producer.path
            or transition.callee_name != edge.producer.name
            or transition.callee_first_line != first_line
            or not any(
                statement_start <= line <= statement_end
                for line in transition.callee_line_hits
                for statement_start, statement_end in body_statement_spans
            )
        ):
            _ast_edge_invalid(edge.edge_id)


def derive_addition_numstat(
    reader: GitObjectPair,
    *,
    base_leaves: tuple[TreeLeaf, ...],
    overlay: tuple[OverlayRow, ...],
) -> tuple[NumstatRow, ...]:
    """Derive Git additions and physical text lines from primary blobs."""

    if not isinstance(reader, GitObjectPair):
        raise FeasibilityProofError("feasibility_git_numstat_invalid", "reader")
    try:
        _validate_leaf_rows(base_leaves, overlay=False)
        _validate_leaf_rows(overlay, overlay=True)
    except FeasibilityProofError as exc:
        raise FeasibilityProofError("feasibility_git_numstat_invalid") from exc
    if {row.path for row in base_leaves} & {row.path for row in overlay}:
        raise FeasibilityProofError("feasibility_git_numstat_invalid", "overlap")
    unique_oids = tuple(dict.fromkeys(row.blob_oid for row in overlay))
    objects: dict[str, GitObject] = {}
    try:
        for offset in range(0, len(unique_oids), _GIT_OBJECT_BATCH_LIMIT):
            chunk = unique_oids[offset : offset + _GIT_OBJECT_BATCH_LIMIT]
            objects.update(zip(chunk, reader.read_primary_many(chunk)))
    except FeasibilityProofError as exc:
        raise FeasibilityProofError("feasibility_git_numstat_invalid") from exc
    rows: list[NumstatRow] = []
    for item in overlay:
        value = objects[item.blob_oid]
        if value.object_type != "blob" or b"\0" in value.payload:
            raise FeasibilityProofError(
                "feasibility_git_numstat_invalid",
                item.path,
            )
        try:
            text = value.payload.decode("utf-8", "strict")
        except UnicodeError as exc:
            raise FeasibilityProofError(
                "feasibility_git_numstat_invalid",
                item.path,
            ) from exc
        additions = value.payload.count(b"\n")
        if value.payload and not value.payload.endswith(b"\n"):
            additions += 1
        physical_line_count = len(text.splitlines())
        rows.append(
            NumstatRow(
                path=item.path,
                additions=additions,
                deletions=0,
                physical_line_count=physical_line_count,
            )
        )
    return tuple(rows)


_FEASIBILITY_CAPTURE_KEYS = frozenset(
    {
        "schema_version",
        "capture_id",
        "captured_at",
        "lifecycle",
        "bindings",
        "disposable_roots",
        "tree_algebra",
        "ledgers",
        "directed_ast_edges",
        "volatile_fields",
        "deterministic_sha256",
        "record_sha256",
    }
)


def _capture_invalid(detail: object = "") -> NoReturn:
    raise FeasibilityProofError("feasibility_capture_manifest_invalid", detail)


def _capture_object(
    value: object,
    *,
    keys: frozenset[str],
    label: str,
) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        _capture_invalid(label)
    return value


def _capture_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        _capture_invalid(label)
    return value


def _capture_text(value: object, *, label: str) -> str:
    if type(value) is not str or not value:
        _capture_invalid(label)
    try:
        value.encode("utf-8", "strict")
    except UnicodeError as exc:
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            label,
        ) from exc
    return value


def _capture_int(
    value: object,
    *,
    label: str,
    minimum: int = 0,
) -> int:
    if type(value) is not int or value < minimum:
        _capture_invalid(label)
    return value


def _capture_sha1(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA1_RE.fullmatch(value) is None:
        _capture_invalid(label)
    return value


def _capture_sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        _capture_invalid(label)
    return value


def _capture_absolute_path(value: object, *, label: str) -> str:
    path = _capture_text(value, label=label)
    candidate = Path(path)
    if (
        not candidate.is_absolute()
        or os.path.normpath(path) != path
        or "\0" in path
    ):
        _capture_invalid(label)
    return path


def _capture_relative_path(value: object, *, label: str) -> str:
    path = _capture_text(value, label=label)
    try:
        _split_leaf_path(path)
    except FeasibilityProofError as exc:
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            label,
        ) from exc
    return path


def _capture_string_list(
    value: object,
    *,
    label: str,
    minimum: int = 0,
    relative_paths: bool = False,
) -> tuple[str, ...]:
    rows = _capture_list(value, label=label)
    if len(rows) < minimum:
        _capture_invalid(label)
    result = tuple(
        (
            _capture_relative_path(item, label=f"{label}[{index}]")
            if relative_paths
            else _capture_text(item, label=f"{label}[{index}]")
        )
        for index, item in enumerate(rows)
    )
    if len(set(result)) != len(result):
        _capture_invalid(label)
    return result


def _capture_timestamp(value: object) -> str:
    text = _capture_text(value, label="captured_at")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            "captured_at",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _capture_invalid("captured_at")
    return text


def _capture_executable(value: object, *, label: str) -> ExecutableIdentity:
    try:
        return _executable_identity_from_record(value, label=label)
    except FeasibilityProofError as exc:
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            label,
        ) from exc


def _capture_project_origins(
    value: object,
    *,
    label: str,
) -> tuple[ProjectOrigin, ...]:
    rows = _capture_list(value, label=label)
    result: list[ProjectOrigin] = []
    for index, item in enumerate(rows):
        row = _capture_object(
            item,
            keys=_PYTEST_LEDGER_PROJECT_ORIGIN_KEYS,
            label=f"{label}[{index}]",
        )
        result.append(
            ProjectOrigin(
                module_name=_capture_text(
                    row["module_name"],
                    label=f"{label}[{index}].module_name",
                ),
                resolved_path=_capture_absolute_path(
                    row["resolved_path"],
                    label=f"{label}[{index}].resolved_path",
                ),
            )
        )
    return tuple(result)


def _capture_trace_specs(
    value: object,
    *,
    label: str,
) -> tuple[CallTraceSpec, ...]:
    rows = _capture_list(value, label=label)
    result: list[CallTraceSpec] = []
    for index, item in enumerate(rows):
        row = _capture_object(
            item,
            keys=_PYTEST_CAPTURE_TRACE_SPEC_KEYS,
            label=f"{label}[{index}]",
        )
        result.append(
            CallTraceSpec(
                edge_id=_capture_text(
                    row["edge_id"], label=f"{label}[{index}].edge_id"
                ),
                pytest_node_id=_capture_text(
                    row["pytest_node_id"],
                    label=f"{label}[{index}].pytest_node_id",
                ),
                caller_path=_capture_relative_path(
                    row["caller_path"],
                    label=f"{label}[{index}].caller_path",
                ),
                caller_line=_capture_int(
                    row["caller_line"],
                    label=f"{label}[{index}].caller_line",
                    minimum=1,
                ),
                callee_path=_capture_relative_path(
                    row["callee_path"],
                    label=f"{label}[{index}].callee_path",
                ),
                callee_name=_capture_text(
                    row["callee_name"],
                    label=f"{label}[{index}].callee_name",
                ),
                callee_first_line=_capture_int(
                    row["callee_first_line"],
                    label=f"{label}[{index}].callee_first_line",
                    minimum=1,
                ),
            )
        )
    return tuple(result)


def _capture_authority(value: object, *, label: str) -> PytestLedgerAuthority:
    keys = frozenset(
        {
            "slice_id",
            "runner_path",
            "runner_sha256",
            "git",
            "python",
            "variant_id",
            "project_root",
            "expected_tree",
            "argv",
            "execution_envelope",
            "expected_project_origins",
            "call_trace_specs",
        }
    )
    row = _capture_object(value, keys=keys, label=label)
    argv = _capture_string_list(row["argv"], label=f"{label}.argv", minimum=1)
    try:
        envelope = _pytest_execution_envelope_from_record(
            _capture_object(
                row["execution_envelope"],
                keys=_PYTEST_LEDGER_EXECUTION_ENVELOPE_KEYS,
                label=f"{label}.execution_envelope",
            )
        )
    except FeasibilityProofError as exc:
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            f"{label}.execution_envelope",
        ) from exc
    slice_value = row["slice_id"]
    if slice_value is not None:
        slice_value = _capture_text(slice_value, label=f"{label}.slice_id")
    authority = PytestLedgerAuthority(
        ledger_id="",
        ordinal=0,
        role="collection",
        role_index=0,
        slice_id=slice_value,
        runner_path=_capture_absolute_path(
            row["runner_path"], label=f"{label}.runner_path"
        ),
        runner_sha256=_capture_sha256(
            row["runner_sha256"], label=f"{label}.runner_sha256"
        ),
        git=_capture_executable(row["git"], label=f"{label}.git"),
        python=_capture_executable(row["python"], label=f"{label}.python"),
        variant_id=_capture_text(
            row["variant_id"], label=f"{label}.variant_id"
        ),
        project_root=_capture_absolute_path(
            row["project_root"], label=f"{label}.project_root"
        ),
        expected_tree=_capture_sha1(
            row["expected_tree"], label=f"{label}.expected_tree"
        ),
        argv=argv,
        execution_envelope=envelope,
        expected_project_origins=_capture_project_origins(
            row["expected_project_origins"],
            label=f"{label}.expected_project_origins",
        ),
        call_trace_specs=_capture_trace_specs(
            row["call_trace_specs"], label=f"{label}.call_trace_specs"
        ),
    )
    try:
        if authority.argv[:3] != (
            authority.python.literal_path,
            "-m",
            "pytest",
        ):
            _capture_invalid(f"{label}.argv")
        _validate_pytest_execution_envelope(
            authority.execution_envelope,
            project_root=authority.project_root,
            target_argv=authority.argv,
        )
        _validate_expected_project_origins(
            authority.expected_project_origins,
            project_root=Path(authority.project_root),
        )
        _validate_call_trace_specs(authority.call_trace_specs)
    except FeasibilityProofError as exc:
        if exc.code == "feasibility_capture_manifest_invalid":
            raise
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            label,
        ) from exc
    return authority


def _capture_deterministic_projection(
    record: Mapping[str, object],
) -> dict[str, object]:
    projection = copy.deepcopy(dict(record))
    projection.pop("captured_at", None)
    projection.pop("deterministic_sha256", None)
    projection.pop("record_sha256", None)
    ledgers = projection.get("ledgers")
    if type(ledgers) is list:
        for value in ledgers:
            if type(value) is dict:
                value.pop("elapsed_ns", None)
                value.pop("sha256", None)
    return projection


def _capture_record_sha256(record: Mapping[str, object]) -> str:
    body = copy.deepcopy(dict(record))
    body.pop("record_sha256", None)
    return _sha256(canonical_json_bytes(body))


def _capture_expected_id(record: Mapping[str, object]) -> str:
    bindings = record["bindings"]
    algebra = record["tree_algebra"]
    ledgers = record["ledgers"]
    assert type(bindings) is dict
    assert type(algebra) is dict
    assert type(ledgers) is list
    identity = {
        "frozen_base": bindings["frozen_base"],
        "object_store": bindings["object_store"],
        "variants": algebra["variants"],
        "ledger_deterministic_sha256": [
            value["deterministic_sha256"] for value in ledgers
        ],
    }
    return "capture-" + hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:32]


def build_feasibility_capture_manifest(
    *,
    captured_at: str,
    bindings: Mapping[str, object],
    disposable_roots: Sequence[Mapping[str, object]],
    tree_algebra: Mapping[str, object],
    ledgers: Sequence[Mapping[str, object]],
    directed_ast_edges: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Seal and reobserve one canonical retained feasibility capture."""

    try:
        record: dict[str, object] = {
            "schema_version": _FEASIBILITY_CAPTURE_SCHEMA_VERSION,
            "capture_id": "",
            "captured_at": captured_at,
            "lifecycle": _FEASIBILITY_CAPTURE_LIFECYCLE,
            "bindings": copy.deepcopy(dict(bindings)),
            "disposable_roots": copy.deepcopy(list(disposable_roots)),
            "tree_algebra": copy.deepcopy(dict(tree_algebra)),
            "ledgers": copy.deepcopy(list(ledgers)),
            "directed_ast_edges": copy.deepcopy(list(directed_ast_edges)),
            "volatile_fields": list(_FEASIBILITY_CAPTURE_VOLATILE_FIELDS),
            "deterministic_sha256": "",
            "record_sha256": "",
        }
        record["capture_id"] = _capture_expected_id(record)
        record["deterministic_sha256"] = _sha256(
            canonical_json_bytes(_capture_deterministic_projection(record))
        )
        record["record_sha256"] = _capture_record_sha256(record)
        return validate_feasibility_capture_manifest_record(
            record,
            reobserve_roots=True,
        )
    except FeasibilityProofError as exc:
        if exc.code == "feasibility_capture_manifest_invalid":
            raise
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            exc.detail,
        ) from exc
    except (AssertionError, AttributeError, KeyError, TypeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            "record",
        ) from exc


def _capture_root_id(
    *,
    root_kind: str,
    canonical_path: str,
    variant_id: str | None,
    content_name: str,
    content_value: str,
) -> str:
    identity = {
        "root_kind": root_kind,
        "canonical_path": canonical_path,
        "variant_id": variant_id,
        content_name: content_value,
    }
    return "root-" + hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:32]


def snapshot_directory_sha256(root: Path) -> str:
    """Hash one stable directory as ordered path/kind/mode/content rows."""

    candidate = Path(root)
    try:
        resolved = candidate.resolve(strict=True)
        before = candidate.lstat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_capture_root_invalid",
            str(candidate),
        ) from exc
    if (
        not candidate.is_absolute()
        or candidate != resolved
        or candidate.is_symlink()
        or not stat.S_ISDIR(before.st_mode)
    ):
        raise FeasibilityProofError(
            "feasibility_capture_root_invalid",
            str(candidate),
        )
    rows: list[dict[str, object]] = []
    try:
        paths = sorted(
            candidate.rglob("*"),
            key=lambda value: os.fsencode(value.relative_to(candidate)),
        )
        for path in paths:
            relative = path.relative_to(candidate).as_posix()
            identity = path.lstat()
            mode = stat.S_IMODE(identity.st_mode)
            if stat.S_ISDIR(identity.st_mode) and not path.is_symlink():
                rows.append(
                    {"path": relative, "kind": "directory", "mode": mode}
                )
                continue
            if stat.S_ISREG(identity.st_mode) and not path.is_symlink():
                raw, after_identity = _stable_regular_file_bytes(
                    path,
                    error_code="feasibility_capture_root_invalid",
                    detail=relative,
                )
                if _regular_file_metadata(identity) != after_identity:
                    raise FeasibilityProofError(
                        "feasibility_capture_root_invalid",
                        relative,
                    )
                rows.append(
                    {
                        "path": relative,
                        "kind": "file",
                        "mode": mode,
                        "sha256": _sha256(raw),
                    }
                )
                continue
            raise FeasibilityProofError(
                "feasibility_capture_root_invalid",
                relative,
            )
        after = candidate.lstat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_capture_root_invalid",
            str(candidate),
        ) from exc
    if (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise FeasibilityProofError(
            "feasibility_capture_root_invalid",
            str(candidate),
        )
    return _sha256(
        canonical_json_bytes(
            {"schema_version": "directory_snapshot.v1", "rows": rows}
        )
    )


def _remove_owned_materialization(
    destination: Path,
    *,
    identity: tuple[int, int],
) -> None:
    try:
        observed = destination.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise FeasibilityProofError(
            "feasibility_materialization_cleanup_failed",
            str(destination),
        ) from exc
    if (
        destination.is_symlink()
        or not stat.S_ISDIR(observed.st_mode)
        or (observed.st_dev, observed.st_ino) != identity
    ):
        raise FeasibilityProofError(
            "feasibility_materialization_cleanup_failed",
            str(destination),
        )
    try:
        shutil.rmtree(destination)
    except OSError as exc:
        raise FeasibilityProofError(
            "feasibility_materialization_cleanup_failed",
            str(destination),
        ) from exc


def materialize_tree_variant(
    reader: GitObjectStore | GitObjectPair,
    variant: TreeVariant,
    destination: Path,
) -> dict[str, object]:
    """Materialize one authenticated tree into one previously absent root."""

    if not isinstance(reader, (GitObjectStore, GitObjectPair)) or type(
        variant
    ) is not TreeVariant:
        raise FeasibilityProofError(
            "feasibility_materialization_invalid",
            "input",
        )
    candidate = Path(destination)
    try:
        parent = candidate.parent.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_materialization_destination_invalid",
            str(candidate),
        ) from exc
    if (
        not candidate.is_absolute()
        or candidate.parent != parent
        or not candidate.name
        or candidate.name in {".", ".."}
        or os.path.normpath(os.fspath(candidate)) != os.fspath(candidate)
        or candidate.exists()
        or candidate.is_symlink()
    ):
        raise FeasibilityProofError(
            "feasibility_materialization_destination_invalid",
            str(candidate),
        )
    if not stat.S_ISDIR(parent.lstat().st_mode) or parent.is_symlink():
        raise FeasibilityProofError(
            "feasibility_materialization_destination_invalid",
            str(candidate),
        )
    leaves = variant.tree.leaves
    try:
        synthesized_oid, _ = _synthesize_tree_objects(leaves)
    except FeasibilityProofError as exc:
        raise FeasibilityProofError(
            "feasibility_materialization_invalid",
            variant.variant_id,
        ) from exc
    if synthesized_oid != variant.tree.tree_oid:
        raise FeasibilityProofError(
            "feasibility_materialization_invalid",
            variant.variant_id,
        )
    unique_oids = tuple(dict.fromkeys(leaf.blob_oid for leaf in leaves))
    objects: dict[str, GitObject] = {}
    try:
        for offset in range(0, len(unique_oids), _GIT_OBJECT_BATCH_LIMIT):
            chunk = unique_oids[offset : offset + _GIT_OBJECT_BATCH_LIMIT]
            objects.update(zip(chunk, reader.read_many(chunk)))
    except FeasibilityProofError as exc:
        raise FeasibilityProofError(
            "feasibility_materialization_invalid",
            variant.variant_id,
        ) from exc
    if any(value.object_type != "blob" for value in objects.values()):
        raise FeasibilityProofError(
            "feasibility_materialization_invalid",
            variant.variant_id,
        )
    try:
        candidate.mkdir(mode=0o700)
        root_identity = candidate.lstat()
    except OSError as exc:
        raise FeasibilityProofError(
            "feasibility_materialization_destination_invalid",
            str(candidate),
        ) from exc
    ownership = (root_identity.st_dev, root_identity.st_ino)
    try:
        for leaf in leaves:
            parts = _split_leaf_path(leaf.path)
            parent_path = candidate
            for component in parts[:-1]:
                parent_path = parent_path / component
                try:
                    parent_path.mkdir(mode=0o755)
                except FileExistsError:
                    identity = parent_path.lstat()
                    if parent_path.is_symlink() or not stat.S_ISDIR(identity.st_mode):
                        raise FeasibilityProofError(
                            "feasibility_materialization_invalid",
                            leaf.path,
                        )
            target = parent_path / parts[-1]
            payload = objects[leaf.blob_oid].payload
            if leaf.mode == "120000":
                if not payload or b"\0" in payload:
                    raise FeasibilityProofError(
                        "feasibility_materialization_invalid",
                        leaf.path,
                    )
                os.symlink(payload, os.fsencode(target))
                continue
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(target, flags, 0o600)
            try:
                remaining = memoryview(payload)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        raise OSError("short write")
                    remaining = remaining[written:]
                os.fchmod(descriptor, 0o755 if leaf.mode == "100755" else 0o644)
            finally:
                os.close(descriptor)
        observed_tree = snapshot_project_tree_oid(candidate)
        if observed_tree != variant.tree.tree_oid:
            raise FeasibilityProofError(
                "feasibility_materialization_tree_mismatch",
                variant.variant_id,
            )
    except Exception:
        _remove_owned_materialization(candidate, identity=ownership)
        raise
    return {
        "canonical_path": str(candidate),
        "tree_oid": observed_tree,
        "st_dev": ownership[0],
        "st_ino": ownership[1],
    }


def materialize_capture_roots(
    reader: GitObjectPair,
    *,
    variants: tuple[TreeVariant, ...],
    source_destinations: tuple[Path, ...],
    object_store_root: Path,
) -> tuple[dict[str, object], ...]:
    """Materialize six executable variants and bind the existing primary store."""

    if (
        type(reader) is not GitObjectPair
        or type(variants) is not tuple
        or type(source_destinations) is not tuple
        or len(variants) != 6
        or len(source_destinations) != 6
        or tuple(value.variant_id for value in variants)
        != _FEASIBILITY_VARIANT_IDS
    ):
        raise FeasibilityProofError(
            "feasibility_capture_root_set_invalid",
            "inputs",
        )
    store = Path(object_store_root)
    try:
        canonical_store = store.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_capture_root_set_invalid",
            str(store),
        ) from exc
    if (
        store != canonical_store
        or store != reader._primary.repository
        or store.is_symlink()
        or not stat.S_ISDIR(store.lstat().st_mode)
    ):
        raise FeasibilityProofError(
            "feasibility_capture_root_set_invalid",
            str(store),
        )
    destinations = tuple(Path(value) for value in source_destinations)
    if len(set(destinations)) != 6:
        raise FeasibilityProofError(
            "feasibility_capture_root_set_invalid",
            "source_destinations",
        )
    all_paths = (*destinations, store)
    for index, left in enumerate(all_paths):
        for right in all_paths[index + 1 :]:
            try:
                left.relative_to(right)
            except ValueError:
                try:
                    right.relative_to(left)
                except ValueError:
                    continue
            raise FeasibilityProofError(
                "feasibility_capture_root_set_invalid",
                "overlap",
            )
    store_snapshot_before = snapshot_directory_sha256(store)
    created: list[tuple[Path, tuple[int, int]]] = []
    declarations: list[dict[str, object]] = []
    try:
        for variant, destination in zip(variants, destinations):
            ownership = materialize_tree_variant(reader, variant, destination)
            identity = (int(ownership["st_dev"]), int(ownership["st_ino"]))
            created.append((destination, identity))
            tree_oid = str(ownership["tree_oid"])
            path = str(destination)
            declarations.append(
                {
                    "root_id": _capture_root_id(
                        root_kind="source_tree",
                        canonical_path=path,
                        variant_id=variant.variant_id,
                        content_name="tree_oid",
                        content_value=tree_oid,
                    ),
                    "root_kind": "source_tree",
                    "canonical_path": path,
                    "variant_id": variant.variant_id,
                    "pre_purge_lstat": "directory",
                    "tree_oid": tree_oid,
                }
            )
        store_snapshot_after = snapshot_directory_sha256(store)
        if store_snapshot_after != store_snapshot_before:
            raise FeasibilityProofError(
                "feasibility_capture_root_set_invalid",
                "object_store_mutated",
            )
    except Exception:
        for path, identity in reversed(created):
            _remove_owned_materialization(path, identity=identity)
        raise
    store_path = str(store)
    declarations.append(
        {
            "root_id": _capture_root_id(
                root_kind="git_object_store",
                canonical_path=store_path,
                variant_id=None,
                content_name="snapshot_sha256",
                content_value=store_snapshot_before,
            ),
            "root_kind": "git_object_store",
            "canonical_path": store_path,
            "pre_purge_lstat": "directory",
            "snapshot_sha256": store_snapshot_before,
        }
    )
    return tuple(declarations)


def _validate_capture_review_bindings(
    reviews: object,
    *,
    review_root: Path,
    expected_authority_bindings: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    if type(reviews) not in {list, tuple} or len(reviews) != 2:
        raise FeasibilityProofError(
            "feasibility_purge_review_invalid",
            "reviews",
        )
    root = Path(review_root)
    try:
        canonical_root = root.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_purge_review_invalid",
            str(root),
        ) from exc
    if root != canonical_root or root.is_symlink() or not root.is_dir():
        raise FeasibilityProofError(
            "feasibility_purge_review_invalid",
            str(root),
        )
    authority = _capture_object(
        dict(expected_authority_bindings),
        keys=_FEASIBILITY_AUTHORITY_BINDING_KEYS,
        label="expected_authority_bindings",
    )
    for key, value in authority.items():
        _capture_sha256(value, label=f"expected_authority_bindings.{key}")
    normalized: list[dict[str, object]] = []
    reviewers: list[str] = []
    reviewed_times: list[datetime] = []
    for index, (value, contract) in enumerate(
        zip(reviews, _FEASIBILITY_ORDERED_REVIEW_CONTRACTS)
    ):
        review_kind, relative, verdict = contract
        row = _capture_object(
            value,
            keys=frozenset({"review_kind", "path", "sha256"}),
            label=f"reviews[{index}]",
        )
        if row["review_kind"] != review_kind or row["path"] != relative:
            raise FeasibilityProofError(
                "feasibility_purge_review_invalid",
                f"reviews[{index}]",
            )
        digest = _capture_sha256(
            row["sha256"], label=f"reviews[{index}].sha256"
        )
        path = root.joinpath(*_split_leaf_path(relative))
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
            raw, _ = _stable_regular_file_bytes(
                path,
                error_code="feasibility_purge_review_invalid",
                detail=relative,
            )
            lines = raw.decode("utf-8", "strict").splitlines()
        except (
            FeasibilityProofError,
            OSError,
            RuntimeError,
            UnicodeError,
            ValueError,
        ) as exc:
            raise FeasibilityProofError(
                "feasibility_purge_review_invalid",
                relative,
            ) from exc
        if (
            resolved != path
            or path.is_symlink()
            or _sha256(raw) != digest
            or [line for line in lines if line.startswith("verdict: ")]
            != ["verdict: " + verdict.decode("ascii")]
            or any(
                lines.count(finding.decode("ascii")) != 1
                for finding in _FEASIBILITY_REQUIRED_REVIEW_FINDINGS
            )
            or any(
                [line for line in lines if line.startswith(f"{key}: ")]
                != [f"{key}: {value}"]
                for key, value in authority.items()
            )
        ):
            raise FeasibilityProofError(
                "feasibility_purge_review_invalid",
                relative,
            )
        reviewer_lines = [
            line for line in lines if line.startswith("reviewer: ")
        ]
        reviewed_at_lines = [
            line for line in lines if line.startswith("reviewed_at: ")
        ]
        if len(reviewer_lines) != 1 or len(reviewed_at_lines) != 1:
            raise FeasibilityProofError(
                "feasibility_purge_review_invalid",
                relative,
            )
        reviewer = reviewer_lines[0].removeprefix("reviewer: ")
        reviewed_at_text = reviewed_at_lines[0].removeprefix("reviewed_at: ")
        try:
            if (
                not reviewer
                or reviewer != reviewer.strip()
                or not reviewed_at_text
                or reviewed_at_text != reviewed_at_text.strip()
            ):
                raise ValueError("noncanonical review metadata")
            reviewed_at = datetime.fromisoformat(
                reviewed_at_text.replace("Z", "+00:00")
            )
            if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
                raise ValueError("reviewed_at lacks offset")
        except (OverflowError, ValueError) as exc:
            raise FeasibilityProofError(
                "feasibility_purge_review_invalid",
                relative,
            ) from exc
        reviewers.append(reviewer)
        reviewed_times.append(reviewed_at)
        normalized.append(copy.deepcopy(row))
    if len(set(reviewers)) != 2 or reviewed_times[0] > reviewed_times[1]:
        raise FeasibilityProofError(
            "feasibility_purge_review_invalid",
            "ordered_distinct_reviews",
        )
    return tuple(normalized)


def validate_purge_preconditions(
    capture_manifest: dict[str, object],
    *,
    reviews: tuple[dict[str, object], ...] | list[dict[str, object]],
    expected_authority_bindings: Mapping[str, object],
    review_root: Path = _REPOSITORY_ROOT,
) -> dict[str, object]:
    """Revalidate the retained capture and ordered review authority before purge."""

    capture = validate_feasibility_capture_manifest_record(
        capture_manifest,
        reobserve_roots=True,
    )
    review_rows = _validate_capture_review_bindings(
        reviews,
        review_root=Path(review_root),
        expected_authority_bindings=expected_authority_bindings,
    )
    roots = capture["disposable_roots"]
    assert type(roots) is list
    identities: list[dict[str, object]] = []
    for index, row in enumerate(roots):
        assert type(row) is dict
        path = Path(str(row["canonical_path"]))
        try:
            identity = path.lstat()
        except OSError as exc:
            raise FeasibilityProofError(
                "feasibility_purge_root_invalid",
                str(path),
            ) from exc
        if path.is_symlink() or not stat.S_ISDIR(identity.st_mode):
            raise FeasibilityProofError(
                "feasibility_purge_root_invalid",
                str(path),
            )
        content = (
            snapshot_project_tree_oid(path)
            if index < 6
            else snapshot_directory_sha256(path)
        )
        expected = row["tree_oid"] if index < 6 else row["snapshot_sha256"]
        if content != expected:
            raise FeasibilityProofError(
                "feasibility_purge_root_invalid",
                str(path),
            )
        identities.append(
            {
                "root_id": row["root_id"],
                "canonical_path": str(path),
                "st_dev": identity.st_dev,
                "st_ino": identity.st_ino,
                "content": content,
            }
        )
    return {
        "capture_manifest_sha256": capture["record_sha256"],
        "reviews": [copy.deepcopy(value) for value in review_rows],
        "roots": identities,
    }


def purge_capture_bound_roots(
    capture_manifest: dict[str, object],
    *,
    reviews: tuple[dict[str, object], ...] | list[dict[str, object]],
    expected_authority_bindings: Mapping[str, object],
    review_root: Path = _REPOSITORY_ROOT,
) -> tuple[dict[str, object], ...]:
    """Delete exactly the revalidated seven-root capture set, once."""

    authorization = validate_purge_preconditions(
        capture_manifest,
        reviews=reviews,
        expected_authority_bindings=expected_authority_bindings,
        review_root=review_root,
    )
    roots = authorization["roots"]
    assert type(roots) is list
    absent: list[dict[str, object]] = []
    for index, row in enumerate(roots):
        assert type(row) is dict
        path = Path(str(row["canonical_path"]))
        try:
            identity = path.lstat()
        except OSError as exc:
            raise FeasibilityProofError(
                "feasibility_purge_root_invalid",
                str(path),
            ) from exc
        if (
            path.is_symlink()
            or not stat.S_ISDIR(identity.st_mode)
            or identity.st_dev != row["st_dev"]
            or identity.st_ino != row["st_ino"]
        ):
            raise FeasibilityProofError(
                "feasibility_purge_root_invalid",
                str(path),
            )
        content = (
            snapshot_project_tree_oid(path)
            if index < 6
            else snapshot_directory_sha256(path)
        )
        if content != row["content"]:
            raise FeasibilityProofError(
                "feasibility_purge_root_invalid",
                str(path),
            )
        try:
            shutil.rmtree(path)
            path.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise FeasibilityProofError(
                "feasibility_purge_failed",
                str(path),
            ) from exc
        else:
            raise FeasibilityProofError(
                "feasibility_purge_failed",
                str(path),
            )
        absent.append(
            {
                "root_id": row["root_id"],
                "canonical_path": str(path),
                "lstat": "absent",
            }
        )
    return tuple(absent)


def build_post_purge_tombstone(
    capture_manifest: dict[str, object],
    *,
    reviews: tuple[dict[str, object], ...] | list[dict[str, object]],
    expected_authority_bindings: Mapping[str, object],
    purged_at: str,
    review_root: Path = _REPOSITORY_ROOT,
) -> dict[str, object]:
    """Build a sealed tombstone only after all capture roots are absent."""

    capture = validate_feasibility_capture_manifest_record(
        capture_manifest,
        reobserve_roots=False,
    )
    _capture_timestamp(purged_at)
    review_rows = _validate_capture_review_bindings(
        reviews,
        review_root=Path(review_root),
        expected_authority_bindings=expected_authority_bindings,
    )
    roots = capture["disposable_roots"]
    assert type(roots) is list
    absent: list[dict[str, object]] = []
    for row in roots:
        assert type(row) is dict
        path = Path(str(row["canonical_path"]))
        try:
            path.lstat()
        except FileNotFoundError:
            absent.append(
                {
                    "root_id": row["root_id"],
                    "canonical_path": str(path),
                    "lstat": "absent",
                }
            )
            continue
        except OSError as exc:
            raise FeasibilityProofError(
                "feasibility_post_purge_probe_failed",
                str(path),
            ) from exc
        raise FeasibilityProofError(
            "feasibility_post_purge_root_present",
            str(path),
        )
    body: dict[str, object] = {
        "schema_version": "es_f1_feasibility_post_purge_tombstone.v1",
        "evidence_status": "purged_after_ordered_reviews",
        "purged_at": purged_at,
        "capture_manifest": {
            "path": _FEASIBILITY_CAPTURE_MANIFEST_RELATIVE,
            "sha256": capture["record_sha256"],
        },
        "reviews": [copy.deepcopy(value) for value in review_rows],
        "absent_roots": absent,
    }
    body["record_sha256"] = _capture_record_sha256(body)
    return body


def _capture_repository_record_path(relative: str) -> Path:
    try:
        parts = _split_leaf_path(relative)
        root = Path(_REPOSITORY_ROOT)
        canonical_root = root.resolve(strict=True)
        root_identity = root.lstat()
        if (
            root != canonical_root
            or root.is_symlink()
            or not stat.S_ISDIR(root_identity.st_mode)
        ):
            raise ValueError("repository root is not canonical")
        candidate = root
        for index, component in enumerate(parts):
            candidate = candidate / component
            identity = candidate.lstat()
            if candidate.is_symlink() or (
                index < len(parts) - 1 and not stat.S_ISDIR(identity.st_mode)
            ):
                raise ValueError("record path contains a symlink or non-directory")
        candidate.relative_to(root)
        if candidate.resolve(strict=True) != candidate:
            raise ValueError("record path is not canonical")
    except (FeasibilityProofError, OSError, RuntimeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            "ledger.path",
        ) from exc
    return candidate


def _capture_inventory_sha256(leaves: tuple[TreeLeaf, ...]) -> str:
    raw = b"".join(
        f"{leaf.mode} blob {leaf.blob_oid}\t{leaf.path}".encode("utf-8", "strict")
        + b"\0"
        for leaf in leaves
    )
    return _sha256(raw)


def _validate_capture_bindings(
    value: object,
    *,
    reobserve: bool,
) -> tuple[
    dict[str, object],
    ExecutableIdentity,
    ExecutableIdentity,
    ExecutableIdentity,
]:
    keys = frozenset(
        {
            "runner_path",
            "runner_sha256",
            "git",
            "python",
            "execution_wrapper",
            "frozen_base",
            "object_store",
        }
    )
    row = _capture_object(value, keys=keys, label="bindings")
    if row["runner_path"] != RUNNER_RELATIVE_PATH:
        _capture_invalid("bindings.runner_path")
    runner_digest = _capture_sha256(
        row["runner_sha256"], label="bindings.runner_sha256"
    )
    git = _capture_executable(row["git"], label="bindings.git")
    python = _capture_executable(row["python"], label="bindings.python")
    wrapper = _capture_executable(
        row["execution_wrapper"], label="bindings.execution_wrapper"
    )
    frozen = _capture_object(
        row["frozen_base"],
        keys=frozenset(
            {"repository", "commit", "tree", "inventory_sha256", "leaf_count"}
        ),
        label="bindings.frozen_base",
    )
    _capture_absolute_path(
        frozen["repository"], label="bindings.frozen_base.repository"
    )
    _capture_sha1(frozen["commit"], label="bindings.frozen_base.commit")
    _capture_sha1(frozen["tree"], label="bindings.frozen_base.tree")
    _capture_sha256(
        frozen["inventory_sha256"],
        label="bindings.frozen_base.inventory_sha256",
    )
    _capture_int(
        frozen["leaf_count"],
        label="bindings.frozen_base.leaf_count",
        minimum=1,
    )
    store = _capture_object(
        row["object_store"],
        keys=frozenset({"canonical_path", "snapshot_sha256"}),
        label="bindings.object_store",
    )
    _capture_absolute_path(
        store["canonical_path"], label="bindings.object_store.canonical_path"
    )
    _capture_sha256(
        store["snapshot_sha256"], label="bindings.object_store.snapshot_sha256"
    )
    if (
        frozen != _FEASIBILITY_FROZEN_BASE
        or _executable_identity_record(git) != _FEASIBILITY_GIT_IDENTITY
        or _executable_identity_record(python) != _FEASIBILITY_PYTHON_IDENTITY
        or _executable_identity_record(wrapper) != _FEASIBILITY_BWRAP_IDENTITY
    ):
        _capture_invalid("bindings.pinned_authority")
    if reobserve:
        runner_path = _REPOSITORY_ROOT / RUNNER_RELATIVE_PATH
        if runner_sha256(runner_path) != runner_digest:
            _capture_invalid("bindings.runner_sha256")
        for role, identity in (
            ("git", git),
            ("python", python),
            ("bwrap", wrapper),
        ):
            try:
                observed = verify_executable_binding(
                    _executable_identity_record(identity), role=role
                )
            except FeasibilityProofError as exc:
                raise FeasibilityProofError(
                    "feasibility_capture_manifest_invalid",
                    f"bindings.{role}",
                ) from exc
            if observed != _executable_identity_record(identity):
                _capture_invalid(f"bindings.{role}")
    return row, git, python, wrapper


def _validate_capture_tree_algebra(
    value: object,
) -> tuple[
    tuple[OverlayRow, ...],
    OverlaySlice,
    tuple[OverlaySlice, ...],
    tuple[dict[str, object], ...],
    tuple[dict[str, object], ...],
    tuple[NumstatRow, ...],
]:
    row = _capture_object(
        value,
        keys=frozenset({"overlay", "cluster_contracts", "variants", "numstat"}),
        label="tree_algebra",
    )
    overlay_values = _capture_list(row["overlay"], label="tree_algebra.overlay")
    if len(overlay_values) != 5:
        _capture_invalid("tree_algebra.overlay")
    overlay: list[OverlayRow] = []
    slices: list[OverlaySlice] = []
    for index, item in enumerate(overlay_values):
        value_row = _capture_object(
            item,
            keys=frozenset({"slice_id", "ordinal", "path", "mode", "blob_oid"}),
            label=f"tree_algebra.overlay[{index}]",
        )
        slice_id = _capture_text(
            value_row["slice_id"], label=f"tree_algebra.overlay[{index}].slice_id"
        )
        ordinal = _capture_int(
            value_row["ordinal"],
            label=f"tree_algebra.overlay[{index}].ordinal",
        )
        path = _capture_relative_path(
            value_row["path"], label=f"tree_algebra.overlay[{index}].path"
        )
        if value_row["mode"] != "100644":
            _capture_invalid(f"tree_algebra.overlay[{index}].mode")
        blob_oid = _capture_sha1(
            value_row["blob_oid"],
            label=f"tree_algebra.overlay[{index}].blob_oid",
        )
        overlay.append(OverlayRow(path, "100644", blob_oid))
        slices.append(OverlaySlice(slice_id, ordinal, (path,)))
    if (
        tuple(item.ordinal for item in slices) != tuple(range(5))
        or tuple(item.slice_id for item in slices[1:])
        != _FEASIBILITY_IMPLEMENTED_CLUSTERS
        or slices[0].slice_id in _FEASIBILITY_CLUSTER_DOMAIN
        or not slices[0].paths[0].startswith("tests/")
        or len({item.slice_id for item in slices}) != 5
        or len({item.paths[0] for item in slices}) != 5
        or len({item.blob_oid for item in overlay}) != 5
    ):
        _capture_invalid("tree_algebra.overlay")

    contract_values = _capture_list(
        row["cluster_contracts"], label="tree_algebra.cluster_contracts"
    )
    if len(contract_values) != 4:
        _capture_invalid("tree_algebra.cluster_contracts")
    contracts: list[dict[str, object]] = []
    primary_paths: set[str] = set()
    for index, item in enumerate(contract_values):
        contract = _capture_object(
            item,
            keys=frozenset(
                {
                    "cluster_id",
                    "ordinal",
                    "primary_production_paths",
                    "responsibility_ids",
                    "baseline_ledger_id",
                    "remove_one_ledger_id",
                }
            ),
            label=f"tree_algebra.cluster_contracts[{index}]",
        )
        cluster_id = _capture_text(
            contract["cluster_id"],
            label=f"tree_algebra.cluster_contracts[{index}].cluster_id",
        )
        ordinal = _capture_int(
            contract["ordinal"],
            label=f"tree_algebra.cluster_contracts[{index}].ordinal",
            minimum=1,
        )
        if cluster_id != _FEASIBILITY_IMPLEMENTED_CLUSTERS[index] or ordinal != index + 1:
            _capture_invalid(f"tree_algebra.cluster_contracts[{index}]")
        primary = _capture_string_list(
            contract["primary_production_paths"],
            label=f"tree_algebra.cluster_contracts[{index}].primary_production_paths",
            minimum=1,
            relative_paths=True,
        )
        responsibilities = _capture_string_list(
            contract["responsibility_ids"],
            label=f"tree_algebra.cluster_contracts[{index}].responsibility_ids",
            minimum=1,
        )
        if primary_paths & set(primary):
            _capture_invalid("tree_algebra.cluster_contracts.primary_paths")
        primary_paths.update(primary)
        _capture_text(
            contract["baseline_ledger_id"],
            label=f"tree_algebra.cluster_contracts[{index}].baseline_ledger_id",
        )
        _capture_text(
            contract["remove_one_ledger_id"],
            label=f"tree_algebra.cluster_contracts[{index}].remove_one_ledger_id",
        )
        contracts.append(contract)

    variant_values = _capture_list(
        row["variants"], label="tree_algebra.variants"
    )
    if len(variant_values) != 6:
        _capture_invalid("tree_algebra.variants")
    variants: list[dict[str, object]] = []
    slice_ids = tuple(item.slice_id for item in slices)
    for index, item in enumerate(variant_values):
        variant = _capture_object(
            item,
            keys=frozenset(
                {"variant_id", "tree_oid", "leaf_count", "included_slice_ids"}
            ),
            label=f"tree_algebra.variants[{index}]",
        )
        variant_id = _capture_text(
            variant["variant_id"],
            label=f"tree_algebra.variants[{index}].variant_id",
        )
        if variant_id != _FEASIBILITY_VARIANT_IDS[index]:
            _capture_invalid(f"tree_algebra.variants[{index}].variant_id")
        _capture_sha1(
            variant["tree_oid"],
            label=f"tree_algebra.variants[{index}].tree_oid",
        )
        _capture_int(
            variant["leaf_count"],
            label=f"tree_algebra.variants[{index}].leaf_count",
            minimum=1,
        )
        included = _capture_string_list(
            variant["included_slice_ids"],
            label=f"tree_algebra.variants[{index}].included_slice_ids",
            minimum=1,
        )
        expected_included = (
            slice_ids
            if index == 0
            else (slice_ids[0],)
            if index == 1
            else tuple(
                value
                for value in slice_ids
                if value != _FEASIBILITY_IMPLEMENTED_CLUSTERS[index - 2]
            )
        )
        if included != expected_included:
            _capture_invalid(f"tree_algebra.variants[{index}].included_slice_ids")
        variants.append(variant)

    numstat_values = _capture_list(row["numstat"], label="tree_algebra.numstat")
    if len(numstat_values) != 5:
        _capture_invalid("tree_algebra.numstat")
    numstat: list[NumstatRow] = []
    for index, item in enumerate(numstat_values):
        value_row = _capture_object(
            item,
            keys=frozenset(
                {"path", "additions", "deletions", "physical_line_count"}
            ),
            label=f"tree_algebra.numstat[{index}]",
        )
        path = _capture_relative_path(
            value_row["path"], label=f"tree_algebra.numstat[{index}].path"
        )
        if path != overlay[index].path or value_row["deletions"] != 0:
            _capture_invalid(f"tree_algebra.numstat[{index}]")
        numstat.append(
            NumstatRow(
                path=path,
                additions=_capture_int(
                    value_row["additions"],
                    label=f"tree_algebra.numstat[{index}].additions",
                    minimum=1,
                ),
                deletions=0,
                physical_line_count=_capture_int(
                    value_row["physical_line_count"],
                    label=f"tree_algebra.numstat[{index}].physical_line_count",
                    minimum=1,
                ),
            )
        )
    return (
        tuple(sorted(overlay, key=lambda value: value.path.encode("utf-8"))),
        slices[0],
        tuple(slices[1:]),
        tuple(contracts),
        tuple(variants),
        tuple(numstat),
    )


def _validate_capture_roots(
    value: object,
    *,
    bindings: Mapping[str, object],
    variants: tuple[dict[str, object], ...],
    reobserve: bool,
) -> tuple[dict[str, object], ...]:
    values = _capture_list(value, label="disposable_roots")
    if len(values) != 7:
        _capture_invalid("disposable_roots")
    roots: list[dict[str, object]] = []
    paths: list[Path] = []
    for index, item in enumerate(values):
        if index < 6:
            row = _capture_object(
                item,
                keys=frozenset(
                    {
                        "root_id",
                        "root_kind",
                        "canonical_path",
                        "variant_id",
                        "pre_purge_lstat",
                        "tree_oid",
                    }
                ),
                label=f"disposable_roots[{index}]",
            )
            if (
                row["root_kind"] != "source_tree"
                or row["pre_purge_lstat"] != "directory"
                or row["variant_id"] != variants[index]["variant_id"]
                or row["tree_oid"] != variants[index]["tree_oid"]
            ):
                _capture_invalid(f"disposable_roots[{index}]")
            content_name = "tree_oid"
            content_value = _capture_sha1(
                row["tree_oid"], label=f"disposable_roots[{index}].tree_oid"
            )
            variant_id: str | None = str(row["variant_id"])
        else:
            row = _capture_object(
                item,
                keys=frozenset(
                    {
                        "root_id",
                        "root_kind",
                        "canonical_path",
                        "pre_purge_lstat",
                        "snapshot_sha256",
                    }
                ),
                label="disposable_roots[6]",
            )
            object_store = bindings["object_store"]
            assert type(object_store) is dict
            if (
                row["root_kind"] != "git_object_store"
                or row["pre_purge_lstat"] != "directory"
                or row["canonical_path"] != object_store["canonical_path"]
                or row["snapshot_sha256"] != object_store["snapshot_sha256"]
            ):
                _capture_invalid("disposable_roots[6]")
            content_name = "snapshot_sha256"
            content_value = _capture_sha256(
                row["snapshot_sha256"],
                label="disposable_roots[6].snapshot_sha256",
            )
            variant_id = None
        canonical_path = _capture_absolute_path(
            row["canonical_path"],
            label=f"disposable_roots[{index}].canonical_path",
        )
        expected_root_id = _capture_root_id(
            root_kind=str(row["root_kind"]),
            canonical_path=canonical_path,
            variant_id=variant_id,
            content_name=content_name,
            content_value=content_value,
        )
        if row["root_id"] != expected_root_id:
            _capture_invalid(f"disposable_roots[{index}].root_id")
        paths.append(Path(canonical_path))
        roots.append(row)
    if len(set(paths)) != 7:
        _capture_invalid("disposable_roots.canonical_path")
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            try:
                left.relative_to(right)
            except ValueError:
                try:
                    right.relative_to(left)
                except ValueError:
                    continue
            _capture_invalid("disposable_roots.overlap")
    if reobserve:
        for index, (root, path) in enumerate(zip(roots, paths)):
            try:
                identity = path.lstat()
            except OSError as exc:
                raise FeasibilityProofError(
                    "feasibility_capture_root_invalid",
                    str(path),
                ) from exc
            if path.is_symlink() or not stat.S_ISDIR(identity.st_mode):
                raise FeasibilityProofError(
                    "feasibility_capture_root_invalid",
                    str(path),
                )
            observed = (
                snapshot_project_tree_oid(path)
                if index < 6
                else snapshot_directory_sha256(path)
            )
            expected = root["tree_oid"] if index < 6 else root["snapshot_sha256"]
            if observed != expected:
                raise FeasibilityProofError(
                    "feasibility_capture_root_invalid",
                    str(path),
                )
    return tuple(roots)


def _reobserve_capture_tree_algebra(
    *,
    bindings: Mapping[str, object],
    git: ExecutableIdentity,
    overlay: tuple[OverlayRow, ...],
    test_slice: OverlaySlice,
    cluster_slices: tuple[OverlaySlice, ...],
    variants: tuple[dict[str, object], ...],
    numstat: tuple[NumstatRow, ...],
) -> GitObjectPair:
    frozen = bindings["frozen_base"]
    object_store = bindings["object_store"]
    assert type(frozen) is dict and type(object_store) is dict
    try:
        primary = GitObjectStore(
            Path(str(object_store["canonical_path"])),
            _executable_identity_record(git),
        )
        fallback = GitObjectStore(
            Path(str(frozen["repository"])),
            _executable_identity_record(git),
        )
        reader = GitObjectPair(primary, fallback)
        commit = fallback.read(str(frozen["commit"]))
        if commit.object_type != "commit":
            _capture_invalid("bindings.frozen_base.commit")
        first_line = commit.payload.split(b"\n", 1)[0]
        if first_line != f"tree {frozen['tree']}".encode("ascii"):
            _capture_invalid("bindings.frozen_base.tree")
        base_leaves = read_tree_leaves(fallback, str(frozen["tree"]))
        if (
            len(base_leaves) != frozen["leaf_count"]
            or _capture_inventory_sha256(base_leaves) != frozen["inventory_sha256"]
        ):
            _capture_invalid("bindings.frozen_base.inventory")
        derived = derive_overlay_variants(
            reader,
            base_leaves=base_leaves,
            overlay=overlay,
            test_slice=test_slice,
            cluster_slices=cluster_slices,
            expected_full_tree_oid=str(variants[0]["tree_oid"]),
        )
        if tuple(value.variant_id for value in derived) != _FEASIBILITY_VARIANT_IDS:
            _capture_invalid("tree_algebra.variants")
        for index, (observed, expected) in enumerate(zip(derived, variants)):
            if observed.variant_id == "full":
                included_slice_ids = [
                    test_slice.slice_id,
                    *(item.slice_id for item in cluster_slices),
                ]
            elif observed.variant_id == "test_only":
                included_slice_ids = [test_slice.slice_id]
            else:
                included_slice_ids = [
                    test_slice.slice_id,
                    *(
                        item.slice_id
                        for item in cluster_slices
                        if observed.omitted_cluster_id != item.slice_id
                    ),
                ]
            if (
                observed.tree.tree_oid != expected["tree_oid"]
                or len(observed.tree.leaves) != expected["leaf_count"]
                or included_slice_ids != expected["included_slice_ids"]
            ):
                _capture_invalid(f"tree_algebra.variants[{index}]")
        observed_numstat = derive_addition_numstat(
            reader,
            base_leaves=base_leaves,
            overlay=overlay,
        )
        if {value.path: value for value in observed_numstat} != {
            value.path: value for value in numstat
        }:
            _capture_invalid("tree_algebra.numstat")
        return reader
    except FeasibilityProofError as exc:
        if exc.code == "feasibility_capture_manifest_invalid":
            raise
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            "tree_algebra",
        ) from exc


def _ledger_all_outcomes(
    record: Mapping[str, object],
    outcome: str,
) -> bool:
    rows = record.get("node_outcomes")
    return (
        type(rows) is list
        and bool(rows)
        and all(type(value) is dict and value.get("outcome") == outcome for value in rows)
    )


def _green_repeat_projection(record: Mapping[str, object]) -> dict[str, object]:
    value = copy.deepcopy(dict(record))
    for key in (
        "ledger_id",
        "ordinal",
        "role_index",
        "elapsed_ns",
        "deterministic_sha256",
        "record_sha256",
    ):
        value.pop(key, None)
    return value


def _validate_capture_ledgers(
    value: object,
    *,
    bindings: Mapping[str, object],
    git: ExecutableIdentity,
    python: ExecutableIdentity,
    wrapper: ExecutableIdentity,
    roots: tuple[dict[str, object], ...],
    variants: tuple[dict[str, object], ...],
    contracts: tuple[dict[str, object], ...],
    reobserve: bool,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    values = _capture_list(value, label="ledgers")
    if len(values) != 12:
        _capture_invalid("ledgers")
    normalized_records: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []
    ledger_ids: set[str] = set()
    ledger_paths: set[str] = set()
    variant_by_id = {str(row["variant_id"]): row for row in variants}
    root_by_variant = {str(row["variant_id"]): row for row in roots[:6]}
    expected_role_indices = (0, 0, 1, 2, 3, 0, 1, 0, 1, 2, 3, 0)
    expected_variants = (
        "test_only",
        *("test_only" for _ in range(4)),
        "full",
        "full",
        *(f"remove_one:{value}" for value in _FEASIBILITY_IMPLEMENTED_CLUSTERS),
        "full",
    )
    expected_slices: tuple[str | None, ...] = (
        None,
        *_FEASIBILITY_IMPLEMENTED_CLUSTERS,
        None,
        None,
        *_FEASIBILITY_IMPLEMENTED_CLUSTERS,
        None,
    )
    for index, item in enumerate(values):
        row = _capture_object(
            item,
            keys=frozenset(
                {
                    "ledger_id",
                    "ordinal",
                    "role",
                    "role_index",
                    "path",
                    "sha256",
                    "deterministic_sha256",
                    "elapsed_ns",
                    "authority",
                }
            ),
            label=f"ledgers[{index}]",
        )
        ledger_id = _capture_text(
            row["ledger_id"], label=f"ledgers[{index}].ledger_id"
        )
        path = _capture_relative_path(row["path"], label=f"ledgers[{index}].path")
        ordinal = _capture_int(
            row["ordinal"], label=f"ledgers[{index}].ordinal"
        )
        role = _capture_text(row["role"], label=f"ledgers[{index}].role")
        role_index = _capture_int(
            row["role_index"],
            label=f"ledgers[{index}].role_index",
            minimum=0,
        )
        digest = _capture_sha256(row["sha256"], label=f"ledgers[{index}].sha256")
        deterministic_digest = _capture_sha256(
            row["deterministic_sha256"],
            label=f"ledgers[{index}].deterministic_sha256",
        )
        elapsed_ns = _capture_int(
            row["elapsed_ns"],
            label=f"ledgers[{index}].elapsed_ns",
            minimum=1,
        )
        if (
            ordinal != index
            or role != _FEASIBILITY_LEDGER_ROLES[index]
            or role_index != expected_role_indices[index]
            or path != _FEASIBILITY_LEDGER_RELATIVE_PATHS[index]
            or ledger_id in ledger_ids
            or path in ledger_paths
        ):
            _capture_invalid(f"ledgers[{index}]")
        ledger_ids.add(ledger_id)
        ledger_paths.add(path)
        partial = _capture_authority(
            row["authority"], label=f"ledgers[{index}].authority"
        )
        expected_variant = expected_variants[index]
        expected_slice = expected_slices[index]
        root = root_by_variant[expected_variant]
        variant = variant_by_id[expected_variant]
        expected_runner_path = str(_REPOSITORY_ROOT / RUNNER_RELATIVE_PATH)
        launcher = partial.execution_envelope.launcher
        adjacent_mounts = partial.execution_envelope.writable_mounts
        expected_adjacent_argv = (
            python.literal_path,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *_FEASIBILITY_ADJACENT_NODE_IDS,
        )
        adjacent_mount_paths = tuple(
            mount.relative_path for mount in adjacent_mounts
        )
        if (
            partial.slice_id != expected_slice
            or partial.runner_path != expected_runner_path
            or partial.runner_sha256 != bindings["runner_sha256"]
            or partial.git != git
            or partial.python != python
            or partial.variant_id != expected_variant
            or partial.project_root != root["canonical_path"]
            or partial.expected_tree != variant["tree_oid"]
            or (
                partial.execution_envelope.kind == "bwrap_ro_project.v1"
                and launcher != wrapper
            )
            or (
                index == 11
                and partial.execution_envelope.kind != "bwrap_ro_project.v1"
            )
            or (
                index == 11
                and (
                    partial.argv != expected_adjacent_argv
                    or adjacent_mount_paths
                    != ("memoized_data", "training_outputs")
                    or any(
                        mount.pre_tree != _EMPTY_GIT_TREE_OID
                        for mount in adjacent_mounts
                    )
                    or adjacent_mounts[1].post_tree == _EMPTY_GIT_TREE_OID
                )
            )
            or (index != 11 and partial.execution_envelope.kind != "direct")
        ):
            _capture_invalid(f"ledgers[{index}].authority")
        authority = replace(
            partial,
            ledger_id=ledger_id,
            ordinal=ordinal,
            role=role,
            role_index=role_index,
        )
        try:
            record_path = _capture_repository_record_path(path)
            record = load_pinned_canonical_json(
                record_path,
                expected_sha256=digest,
            )
            normalized = validate_authorized_pytest_execution_ledger_record(
                record,
                authority=authority,
                reobserve_executables=reobserve,
            )
        except FeasibilityProofError as exc:
            raise FeasibilityProofError(
                "feasibility_capture_manifest_invalid",
                f"ledgers[{index}]",
            ) from exc
        if (
            normalized.get("ledger_id") != ledger_id
            or normalized.get("ordinal") != ordinal
            or normalized.get("role") != role
            or normalized.get("role_index") != role_index
            or normalized.get("variant_id") != expected_variant
            or normalized.get("slice_id") != expected_slice
            or normalized.get("deterministic_sha256") != deterministic_digest
            or normalized.get("elapsed_ns") != elapsed_ns
        ):
            _capture_invalid(f"ledgers[{index}].binding")
        counts = normalized.get("outcome_counts")
        exit_code = normalized.get("exit_code")
        if type(counts) is not dict:
            _capture_invalid(f"ledgers[{index}].outcomes")
        if role == "collection":
            if exit_code != 0 or counts != {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
            }:
                _capture_invalid(f"ledgers[{index}].outcomes")
        elif role in {"baseline", "remove_one"}:
            if (
                type(exit_code) is not int
                or exit_code == 0
                or counts.get("failed", 0) < 1
                or counts.get("errors") != 0
                or not _ledger_all_outcomes(normalized, "failed")
            ):
                _capture_invalid(f"ledgers[{index}].outcomes")
        elif (
            exit_code != 0
            or counts.get("failed") != 0
            or counts.get("errors") != 0
            or not _ledger_all_outcomes(normalized, "passed")
        ):
            _capture_invalid(f"ledgers[{index}].outcomes")
        if role == "adjacent" and tuple(normalized["collected_node_ids"]) != (
            _FEASIBILITY_ADJACENT_NODE_IDS
        ):
            _capture_invalid(f"ledgers[{index}].adjacent_nodes")
        normalized_records.append(normalized)
        ledger_rows.append(row)

    cluster_witness_domains: list[frozenset[str]] = []
    for offset, contract in enumerate(contracts):
        baseline = normalized_records[1 + offset]
        removal = normalized_records[7 + offset]
        if (
            contract["baseline_ledger_id"] != baseline["ledger_id"]
            or contract["remove_one_ledger_id"] != removal["ledger_id"]
            or baseline["collected_node_ids"] != removal["collected_node_ids"]
            or baseline["node_outcomes"] != removal["node_outcomes"]
        ):
            _capture_invalid(f"tree_algebra.cluster_contracts[{offset}]")
        baseline_nodes = set(baseline["collected_node_ids"])
        cluster_witness_domains.append(frozenset(baseline_nodes))
        for green in normalized_records[5:7]:
            green_passes = {
                row["node_id"]
                for row in green["node_outcomes"]
                if row["outcome"] == "passed"
            }
            if not baseline_nodes <= green_passes:
                _capture_invalid(f"ledgers.green[{offset}]")
    if any(
        left & right
        for index, left in enumerate(cluster_witness_domains)
        for right in cluster_witness_domains[index + 1 :]
    ):
        _capture_invalid("ledgers.cluster_witness_independence")
    closed_witness_nodes = [
        node_id
        for record in normalized_records[1:5]
        for node_id in record["collected_node_ids"]
    ]
    if (
        normalized_records[0]["collected_node_ids"] != closed_witness_nodes
        or any(
            record["collected_node_ids"] != closed_witness_nodes
            for record in normalized_records[5:7]
        )
    ):
        _capture_invalid("ledgers.closed_witness_collection")
    if _green_repeat_projection(normalized_records[5]) != _green_repeat_projection(
        normalized_records[6]
    ):
        _capture_invalid("ledgers.green_repeat")
    return tuple(ledger_rows), tuple(normalized_records)


def _capture_ast_span(value: object, *, label: str) -> AstSpan:
    row = _capture_object(
        value,
        keys=frozenset({"start_line", "start_column", "end_line", "end_column"}),
        label=label,
    )
    span = AstSpan(
        start_line=_capture_int(
            row["start_line"], label=f"{label}.start_line", minimum=1
        ),
        start_column=_capture_int(
            row["start_column"], label=f"{label}.start_column"
        ),
        end_line=_capture_int(
            row["end_line"], label=f"{label}.end_line", minimum=1
        ),
        end_column=_capture_int(
            row["end_column"], label=f"{label}.end_column"
        ),
    )
    if (span.start_line, span.start_column) >= (span.end_line, span.end_column):
        _capture_invalid(label)
    return span


def _capture_ast_node(value: object, *, label: str) -> AstNodeRef:
    row = _capture_object(
        value,
        keys=frozenset({"path", "blob_oid", "node_type", "name", "span"}),
        label=label,
    )
    return AstNodeRef(
        path=_capture_relative_path(row["path"], label=f"{label}.path"),
        blob_oid=_capture_sha1(row["blob_oid"], label=f"{label}.blob_oid"),
        node_type=_capture_text(row["node_type"], label=f"{label}.node_type"),
        name=_capture_text(row["name"], label=f"{label}.name"),
        span=_capture_ast_span(row["span"], label=f"{label}.span"),
    )


def _transition_from_capture_record(value: object, *, label: str) -> CallTransition:
    row = _capture_object(
        value,
        keys=_PYTEST_LEDGER_CALL_TRANSITION_KEYS,
        label=label,
    )
    hits = _capture_list(row["callee_line_hits"], label=f"{label}.callee_line_hits")
    return CallTransition(
        edge_id=_capture_text(row["edge_id"], label=f"{label}.edge_id"),
        pytest_node_id=_capture_text(
            row["pytest_node_id"], label=f"{label}.pytest_node_id"
        ),
        outcome=_capture_text(row["outcome"], label=f"{label}.outcome"),
        caller_path=_capture_relative_path(
            row["caller_path"], label=f"{label}.caller_path"
        ),
        caller_line=_capture_int(
            row["caller_line"], label=f"{label}.caller_line", minimum=1
        ),
        callee_path=_capture_relative_path(
            row["callee_path"], label=f"{label}.callee_path"
        ),
        callee_name=_capture_text(
            row["callee_name"], label=f"{label}.callee_name"
        ),
        callee_first_line=_capture_int(
            row["callee_first_line"],
            label=f"{label}.callee_first_line",
            minimum=1,
        ),
        callee_line_hits=tuple(
            _capture_int(
                item,
                label=f"{label}.callee_line_hits[{index}]",
                minimum=1,
            )
            for index, item in enumerate(hits)
        ),
    )


def _validate_capture_edges(
    value: object,
    *,
    overlay: tuple[OverlayRow, ...],
    test_slice: OverlaySlice,
    cluster_slices: tuple[OverlaySlice, ...],
    ledger_rows: tuple[dict[str, object], ...],
    ledger_records: tuple[dict[str, object], ...],
    reader: GitObjectPair | None,
) -> tuple[tuple[dict[str, object], ...], tuple[DirectedAstEdge, ...]]:
    values = _capture_list(value, label="directed_ast_edges")
    if len(values) != 3:
        _capture_invalid("directed_ast_edges")
    overlay_by_path = {item.path: item for item in overlay}
    cluster_by_path = {
        path: cluster.slice_id
        for cluster in cluster_slices
        for path in cluster.paths
    }
    if test_slice.paths[0] in cluster_by_path:
        _capture_invalid("tree_algebra.overlay")
    ledgers_by_id = {
        str(binding["ledger_id"]): (binding, record)
        for binding, record in zip(ledger_rows, ledger_records, strict=True)
    }
    edge_rows: list[dict[str, object]] = []
    edges: list[DirectedAstEdge] = []
    transitions: list[CallTransition] = []
    edge_ids: set[str] = set()
    endpoints: set[tuple[str, str]] = set()
    for index, item in enumerate(values):
        row = _capture_object(
            item,
            keys=frozenset(
                {
                    "edge_id",
                    "from_cluster",
                    "to_cluster",
                    "producer",
                    "consumer",
                    "pytest_node_id",
                    "ledger_id",
                }
            ),
            label=f"directed_ast_edges[{index}]",
        )
        edge_id = _capture_text(
            row["edge_id"], label=f"directed_ast_edges[{index}].edge_id"
        )
        from_cluster = _capture_text(
            row["from_cluster"],
            label=f"directed_ast_edges[{index}].from_cluster",
        )
        to_cluster = _capture_text(
            row["to_cluster"], label=f"directed_ast_edges[{index}].to_cluster"
        )
        producer = _capture_ast_node(
            row["producer"], label=f"directed_ast_edges[{index}].producer"
        )
        consumer = _capture_ast_node(
            row["consumer"], label=f"directed_ast_edges[{index}].consumer"
        )
        pytest_node_id = _capture_text(
            row["pytest_node_id"],
            label=f"directed_ast_edges[{index}].pytest_node_id",
        )
        ledger_id = _capture_text(
            row["ledger_id"], label=f"directed_ast_edges[{index}].ledger_id"
        )
        producer_overlay = overlay_by_path.get(producer.path)
        consumer_overlay = overlay_by_path.get(consumer.path)
        endpoint = (producer.path, consumer.path)
        if (
            edge_id in edge_ids
            or endpoint in endpoints
            or producer_overlay is None
            or consumer_overlay is None
            or producer.path == consumer.path
            or producer.blob_oid != producer_overlay.blob_oid
            or consumer.blob_oid != consumer_overlay.blob_oid
            or cluster_by_path.get(producer.path) != from_cluster
            or cluster_by_path.get(consumer.path) != to_cluster
            or from_cluster == to_cluster
            or producer.node_type not in {"FunctionDef", "AsyncFunctionDef"}
            or consumer.node_type != "Call"
            or ledger_id not in ledgers_by_id
        ):
            _capture_invalid(f"directed_ast_edges[{index}]")
        binding, ledger = ledgers_by_id[ledger_id]
        if binding["role"] != "green":
            _capture_invalid(f"directed_ast_edges[{index}].ledger_id")
        matches = [
            _transition_from_capture_record(
                transition,
                label=f"directed_ast_edges[{index}].transition",
            )
            for transition in ledger["call_transitions"]
            if type(transition) is dict
            and transition.get("edge_id") == edge_id
            and transition.get("pytest_node_id") == pytest_node_id
        ]
        if len(matches) != 1:
            _capture_invalid(f"directed_ast_edges[{index}].transition")
        transition = matches[0]
        if (
            transition.outcome != "passed"
            or transition.caller_path != consumer.path
            or not (
                consumer.span.start_line
                <= transition.caller_line
                <= consumer.span.end_line
            )
            or transition.callee_path != producer.path
            or transition.callee_name != producer.name
        ):
            _capture_invalid(f"directed_ast_edges[{index}].transition")
        edge_ids.add(edge_id)
        endpoints.add(endpoint)
        edge_rows.append(row)
        edges.append(
            DirectedAstEdge(
                edge_id=edge_id,
                producer=producer,
                consumer=consumer,
                pytest_node_id=pytest_node_id,
            )
        )
        transitions.append(transition)
    if reader is not None:
        try:
            validate_directed_ast_edges(
                reader,
                edges=tuple(edges),
                transitions=tuple(transitions),
            )
        except FeasibilityProofError as exc:
            raise FeasibilityProofError(
                "feasibility_capture_manifest_invalid",
                "directed_ast_edges",
            ) from exc
    return tuple(edge_rows), tuple(edges)


def validate_feasibility_capture_manifest_record(
    record: dict[str, object],
    *,
    reobserve_roots: bool,
) -> dict[str, object]:
    """Validate one closed feasibility capture and every retained binding."""

    try:
        if type(reobserve_roots) is not bool:
            _capture_invalid("reobserve_roots")
        row = _capture_object(
            copy.deepcopy(record),
            keys=_FEASIBILITY_CAPTURE_KEYS,
            label="record",
        )
        if (
            row["schema_version"] != _FEASIBILITY_CAPTURE_SCHEMA_VERSION
            or row["lifecycle"] != _FEASIBILITY_CAPTURE_LIFECYCLE
        ):
            _capture_invalid("schema_version")
        capture_id = _capture_text(row["capture_id"], label="capture_id")
        if re.fullmatch(r"capture-[0-9a-f]{32}", capture_id) is None:
            _capture_invalid("capture_id")
        _capture_timestamp(row["captured_at"])
        volatile = _capture_string_list(
            row["volatile_fields"], label="volatile_fields"
        )
        if volatile != _FEASIBILITY_CAPTURE_VOLATILE_FIELDS:
            _capture_invalid("volatile_fields")
        deterministic_digest = _capture_sha256(
            row["deterministic_sha256"], label="deterministic_sha256"
        )
        record_digest = _capture_sha256(
            row["record_sha256"], label="record_sha256"
        )
        if deterministic_digest != _sha256(
            canonical_json_bytes(_capture_deterministic_projection(row))
        ):
            _capture_invalid("deterministic_sha256")
        if record_digest != _capture_record_sha256(row):
            _capture_invalid("record_sha256")

        bindings, git, python, wrapper = _validate_capture_bindings(
            row["bindings"], reobserve=reobserve_roots
        )
        (
            overlay,
            test_slice,
            cluster_slices,
            contracts,
            variants,
            numstat,
        ) = _validate_capture_tree_algebra(row["tree_algebra"])
        roots = _validate_capture_roots(
            row["disposable_roots"],
            bindings=bindings,
            variants=variants,
            reobserve=reobserve_roots,
        )
        reader = (
            _reobserve_capture_tree_algebra(
                bindings=bindings,
                git=git,
                overlay=overlay,
                test_slice=test_slice,
                cluster_slices=cluster_slices,
                variants=variants,
                numstat=numstat,
            )
            if reobserve_roots
            else None
        )
        ledger_rows, ledger_records = _validate_capture_ledgers(
            row["ledgers"],
            bindings=bindings,
            git=git,
            python=python,
            wrapper=wrapper,
            roots=roots,
            variants=variants,
            contracts=contracts,
            reobserve=reobserve_roots,
        )
        _validate_capture_edges(
            row["directed_ast_edges"],
            overlay=overlay,
            test_slice=test_slice,
            cluster_slices=cluster_slices,
            ledger_rows=ledger_rows,
            ledger_records=ledger_records,
            reader=reader,
        )
        if capture_id != _capture_expected_id(row):
            _capture_invalid("capture_id")
        return row
    except FeasibilityProofError as exc:
        if exc.code == "feasibility_capture_manifest_invalid":
            raise
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            exc.detail,
        ) from exc
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise FeasibilityProofError(
            "feasibility_capture_manifest_invalid",
            "record",
        ) from exc


def derive_feasibility_facts(
    record: dict[str, object],
) -> dict[str, object]:
    """Derive selector-facing structural facts from authenticated records."""

    validated = validate_feasibility_capture_manifest_record(
        record,
        reobserve_roots=False,
    )
    bindings = validated["bindings"]
    algebra = validated["tree_algebra"]
    assert type(bindings) is dict and type(algebra) is dict
    frozen = bindings["frozen_base"]
    assert type(frozen) is dict
    overlay_values = algebra["overlay"]
    contract_values = algebra["cluster_contracts"]
    variant_values = algebra["variants"]
    numstat_values = algebra["numstat"]
    edge_values = validated["directed_ast_edges"]
    assert (
        type(overlay_values) is list
        and type(contract_values) is list
        and type(variant_values) is list
        and type(numstat_values) is list
        and type(edge_values) is list
    )
    overlay_by_slice = {
        str(value["slice_id"]): value for value in overlay_values if type(value) is dict
    }
    numstat_by_path = {
        str(value["path"]): value for value in numstat_values if type(value) is dict
    }
    changed_paths = [
        str(overlay_by_slice[cluster]["path"])
        for cluster in _FEASIBILITY_IMPLEMENTED_CLUSTERS
    ]
    unmet_clusters = []
    for contract, changed_path in zip(contract_values, changed_paths):
        assert type(contract) is dict
        unmet_clusters.append(
            {
                "cluster_id": contract["cluster_id"],
                "baseline_ledger_id": contract["baseline_ledger_id"],
                "remove_one_ledger_id": contract["remove_one_ledger_id"],
                "primary_production_paths": copy.deepcopy(
                    contract["primary_production_paths"]
                ),
                "changed_production_paths": [changed_path],
                "responsibility_ids": copy.deepcopy(contract["responsibility_ids"]),
            }
        )
    integration_edges = []
    for value in edge_values:
        assert type(value) is dict
        producer = value["producer"]
        consumer = value["consumer"]
        assert type(producer) is dict and type(consumer) is dict
        integration_edges.append(
            {
                "edge_id": value["edge_id"],
                "from_cluster": value["from_cluster"],
                "to_cluster": value["to_cluster"],
                "producer_blob_oid": producer["blob_oid"],
                "consumer_blob_oid": consumer["blob_oid"],
                "ledger_id": value["ledger_id"],
                "pytest_node_id": value["pytest_node_id"],
            }
        )
    production_numstat = [numstat_by_path[path] for path in changed_paths]
    full_variant = variant_values[0]
    assert type(full_variant) is dict
    return {
        "schema_version": "es_f1_structural_multi_context_feasibility.v1",
        "capture_manifest_path": (
            "docs/plans/evidence/es-f1-large-scope-refreeze/"
            "feasibility-capture-manifest.json"
        ),
        "capture_manifest_sha256": validated["record_sha256"],
        "capture_deterministic_sha256": validated["deterministic_sha256"],
        "capture_lifecycle": validated["lifecycle"],
        "source_tree_before": frozen["tree"],
        "source_tree_after": full_variant["tree_oid"],
        "cluster_domain": list(_FEASIBILITY_CLUSTER_DOMAIN),
        "unmet_clusters": unmet_clusters,
        "integration_edges": integration_edges,
        "delta": {
            "implementation_additions": sum(
                int(value["additions"]) for value in production_numstat
            ),
            "implementation_deletions": 0,
            "physical_line_count": sum(
                int(value["physical_line_count"]) for value in production_numstat
            ),
            "changed_production_paths": changed_paths,
        },
        "non_collapse": {
            "distinct_production_blob_count": len(
                {
                    str(overlay_by_slice[cluster]["blob_oid"])
                    for cluster in _FEASIBILITY_IMPLEMENTED_CLUSTERS
                }
            ),
            "distinct_cluster_path_sets": len(unmet_clusters),
        },
    }


__all__ = [
    "AstNodeRef",
    "AstSpan",
    "CallTraceSpec",
    "CallTransition",
    "DirectedAstEdge",
    "ExecutableIdentity",
    "FeasibilityProofError",
    "DerivedTree",
    "GitObject",
    "GitObjectPair",
    "GitObjectStore",
    "NumstatRow",
    "NodeOutcome",
    "OutcomeCounts",
    "OverlayRow",
    "OverlaySlice",
    "ProjectOrigin",
    "PytestExecutionEnvelope",
    "PytestExecutionLedger",
    "PytestLedgerAuthority",
    "RUNNER_RELATIVE_PATH",
    "TreeLeaf",
    "TreeVariant",
    "WritableMountEvidence",
    "WritableMountSpec",
    "canonical_json_bytes",
    "capture_pytest_execution_ledger",
    "build_feasibility_capture_manifest",
    "build_post_purge_tombstone",
    "derive_overlay_tree",
    "derive_overlay_variants",
    "derive_addition_numstat",
    "derive_feasibility_facts",
    "load_pinned_canonical_json",
    "materialize_capture_roots",
    "materialize_tree_variant",
    "purge_capture_bound_roots",
    "pytest_execution_ledger_record",
    "runner_sha256",
    "snapshot_directory_sha256",
    "snapshot_project_tree_oid",
    "snapshot_writable_mount_tree_oid",
    "read_tree_leaves",
    "validate_overlay_partition",
    "validate_purge_preconditions",
    "validate_directed_ast_edges",
    "validate_feasibility_capture_manifest_record",
    "validate_authorized_pytest_execution_ledger_record",
    "validate_pytest_execution_ledger_record",
    "verify_executable_binding",
]
