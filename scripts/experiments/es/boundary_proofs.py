"""Immutable Task-0 boundary-proof runner for the ES F1 refreeze.

The pre-edit policy and census can bootstrap the baseline needed to build the
final selector manifest.  That manifest pins this file's raw SHA-256 and remains
mandatory for desired-state replay; later tasks supply trees and rows, not code.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tokenize
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NoReturn, Sequence

from jsonschema import Draft202012Validator


RUNNER_RELATIVE_PATH = "scripts/experiments/es/boundary_proofs.py"
PROOF_KINDS = frozenset(
    {"boundary_runtime", "non_cdi_static", "reference_absence"}
)
WITNESS_KINDS = frozenset(
    {
        "pytest_runtime",
        "controller_pytest_runtime",
        "static_ast",
        "runtime_probe",
    }
)
COVERAGE_STATUSES = frozenset({"required", "inherited", "open"})
CONTROLLER_EXECUTION_KINDS = frozenset(
    {"pytest_aggregate", "isolated_probe", "static_ast"}
)
_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
_DOTTED_IDENTIFIER_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z"
)
_EDITABLE_PREFIX = "__editable___ptychopinn_"
PINNED_GIT = Path("/usr/bin/git")
PINNED_GIT_VERSION = "git version 2.43.0"
PINNED_GIT_SHA256 = (
    "sha256:2a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668"
)
PINNED_PYTHON = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
PINNED_PYTHON_LINK_TARGET = "python3.11"
PINNED_PYTHON_TARGET = Path(
    "/home/ollie/miniconda3/envs/ptycho311/bin/python3.11"
)
PINNED_PYTHON_VERSION = "Python 3.11.13"
PINNED_PYTHON_SHA256 = (
    "sha256:d575ac63749e61ede79bc20518113452b114506ceec0af0cf3993b0fcc486cb0"
)
PINNED_PYTEST_CARRIER = Path("/usr/bin/bwrap")
PINNED_PYTEST_CARRIER_VERSION = "bubblewrap 0.9.0"
PINNED_PYTEST_CARRIER_SHA256 = (
    "sha256:52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712"
)
_FORBIDDEN_MODULE_PREFIXES = (
    "PtychoNN",
    "notebooks.archive.ePIE_recon_simulation",
    "ptycho.FRC",
    "ptycho.evaluation",
    "scripts.orchestration",
)
_GENERATED_PYTEST_PLUGIN_MODULE = "es_boundary_probe_plugin"
_GENERATED_PYTEST_PLUGIN_ORIGIN = "<runtime-owned:es-boundary-probe-plugin>"
_GENERATED_SOURCE_EVENT_OBSERVER_MODULE = "es_exact_source_event_observer"
_GENERATED_SOURCE_EVENT_OBSERVER_ORIGIN = (
    "<runtime-owned:es-exact-source-event-observer>"
)
_AUTOGRAPH_GENERATED_MODULE_RE = re.compile(
    r"__autograph_generated_file[a-z0-9_]{8}\Z"
)
_TORCH_REMOTE_MODULE = "_remote_module_non_scriptable"
_TORCH_REMOTE_TEMP_ORIGIN_RE = re.compile(
    r"/tmp/tmp[a-z0-9_]{8}/_remote_module_non_scriptable\.py\Z"
)
_NORMALIZED_AUTOGRAPH_MODULE = (
    "<normalized-runtime-owned:autograph-generated-module:{ordinal:04d}>"
)
_NORMALIZED_AUTOGRAPH_ORIGIN = (
    "<normalized-runtime-owned:autograph-generated-origin:{ordinal:04d}>"
)
_NORMALIZED_AUTOGRAPH_ORDINAL_LIMIT = 17
_NORMALIZED_TORCH_REMOTE_ORIGIN = (
    "<normalized-runtime-owned:torch-remote-module-non-scriptable-origin>"
)
_SELECTOR_SAMPLING_RULE = (
    "first_observable_per_provider_and_disposition_witness_class_"
    "in_discovery_order.v1"
)
_MANDATORY_PROVIDER_MODULES = (
    "tests/torch/test_generator_registry.py",
    "tests/torch/test_construction_consolidation.py",
    "tests/torch/test_generator_adapter.py",
    "tests/torch/test_config_bridge.py",
    "tests/torch/test_model_spec.py",
    "tests/torch/test_model_spec_v2.py",
    "tests/torch/test_lightning_checkpoint.py",
    "tests/torch/test_artifact_schema.py",
    "tests/torch/test_artifact_schema_v2.py",
    "tests/torch/test_workflows_components.py",
    "tests/torch/test_fno_generators.py",
    "tests/torch/test_fno_lightning_integration.py",
    "tests/torch/test_neuralop_uno_generator.py",
    "tests/torch/test_model_output_modes.py",
    "tests/torch/test_model_manager.py",
    "tests/torch/test_model_training.py",
    "tests/torch/test_train_lightning_execution_contract.py",
    "tests/torch/test_object_big_generator_contract.py",
    "tests/torch/test_structural_config_ownership.py",
)

_BOOTSTRAP_SELECTOR_POLICY_KEYS = frozenset(
    {
        "sampling_rule",
        "pytest_carrier",
        "provider_visible_pytest_selectors",
        "controller_only_proof_selectors",
        "coverage_witness_specs",
        "desired_state_proof_specs",
    }
)
_BOOTSTRAP_PROVIDER_KEYS = frozenset(
    {"selector_id", "ordinal", "pytest_module_path"}
)
_BOOTSTRAP_WITNESS_KEYS = frozenset(
    {
        "witness_id",
        "witness_kind",
        "selector_id",
        "consumer_id",
        "required_proof_kind",
        "spec",
    }
)
_BOOTSTRAP_DESIRED_KEYS = frozenset(
    {"proof_spec_id", "witness_id", "proof_kind", "expected_result"}
)

_PROVIDER_SELECTOR_KEYS = frozenset(
    {
        "selector_id",
        "ordinal",
        "pytest_module_path",
        "projection_blob_id",
        "mode",
        "physical_line_count",
        "pytest_node_ids",
        "coverage_witness_ids",
    }
)
_CONTROLLER_SELECTOR_KEYS = frozenset(
    {
        "selector_id",
        "ordinal",
        "proof_kind",
        "execution_kind",
        "runner_path",
        "runner_sha256",
        "argv",
        "input_bindings",
        "coverage_witness_ids",
    }
)
_COMMON_WITNESS_KEYS = frozenset(
    {
        "witness_id",
        "selector_id",
        "consumer_id",
        "proof_kind",
        "witness_kind",
        "runner_sha256",
        "consumer_path",
        "caller_object_id",
        "start_line",
        "column_start",
        "end_line",
        "column_end",
        "match_id",
    }
)
_PYTEST_WITNESS_KEYS = _COMMON_WITNESS_KEYS | {
    "source_event_binding",
    "expected_event",
}
_CONTROLLER_PYTEST_WITNESS_KEYS = _COMMON_WITNESS_KEYS | {
    "source_event_binding",
    "expected_event",
}
_STATIC_WITNESS_KEYS = _COMMON_WITNESS_KEYS | {"query", "expected_result"}
_RUNTIME_WITNESS_KEYS = _COMMON_WITNESS_KEYS | {
    "probe",
    "source_event_binding",
    "expected_event",
}
_SPEC_KEYS = frozenset(
    {
        "proof_id",
        "ordinal",
        "selector_id",
        "witness_id",
        "consumer_id",
        "proof_kind",
        "expected_result",
    }
)
_INPUT_BINDING_KEYS = frozenset({"path", "sha256"})
_BASELINE_RESULT_KEYS = frozenset(
    {
        "witness_id",
        "selector_id",
        "consumer_id",
        "proof_kind",
        "witness_kind",
        "target_tree",
        "target_path",
        "target_blob_id",
        "mechanically_observed",
        "observation",
        "observation_sha256",
        "passed",
    }
)
_DESIRED_RESULT_KEYS = _BASELINE_RESULT_KEYS | {"proof_id", "ordinal"}
_RUNTIME_BASELINE_RESULT_KEYS = _BASELINE_RESULT_KEYS | {"source_event"}
_RUNTIME_DESIRED_RESULT_KEYS = _DESIRED_RESULT_KEYS | {"source_event"}


class BoundaryProofError(ValueError):
    """One selector, witness, observation, tree, or result failed closed."""

    def __init__(self, code: str, detail: object = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail != "" else code)


@dataclass(frozen=True)
class PytestCarrier:
    """Verified process carrier providing a private tmpfs at /tmp."""

    executable: Path
    sha256: str
    version: str

    def wrap(
        self,
        argv: Sequence[str],
        *,
        preserved_paths: Sequence[Path] = (),
    ) -> tuple[str, ...]:
        bindings = tuple(
            value
            for path in preserved_paths
            for value in ("--bind", str(path), str(path))
        )
        return (
            str(self.executable),
            "--die-with-parent",
            "--dev-bind",
            "/",
            "/",
            "--tmpfs",
            "/tmp",
            *bindings,
            "--",
            *argv,
        )

    def as_record(self) -> dict[str, str]:
        return {
            "executable": str(self.executable),
            "sha256": self.sha256,
            "version": self.version,
            "tmp_isolation": "private_tmpfs",
        }


def _reject_float(value: str) -> NoReturn:
    raise BoundaryProofError("proof_json_number_noncanonical", value)


def _reject_constant(value: str) -> NoReturn:
    raise BoundaryProofError("proof_json_number_noncanonical", value)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BoundaryProofError("proof_json_duplicate_key", key)
        result[key] = value
    return result


def _validate_json_value(value: object, *, label: str) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise BoundaryProofError("proof_json_not_utf8", label) from exc
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, label=f"{label}[{index}]")
        return
    if isinstance(value, tuple):
        for index, item in enumerate(value):
            _validate_json_value(item, label=f"{label}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise BoundaryProofError("proof_json_key_invalid", label)
            _validate_json_value(key, label=f"{label}.key")
            _validate_json_value(item, label=f"{label}.{key}")
        return
    raise BoundaryProofError(
        "proof_json_value_invalid", f"{label}:{type(value).__name__}"
    )


def canonical_json_bytes(value: object) -> bytes:
    """Return Task-0 canonical JSON: ASCII, sorted, compact, and one LF."""

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
        raise BoundaryProofError("proof_json_value_invalid", str(exc)) from exc


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def compute_record_sha256(record: Mapping[str, object]) -> str:
    if not isinstance(record, Mapping):
        raise BoundaryProofError("proof_record_digest_invalid", "record")
    body = dict(record)
    body.pop("record_sha256", None)
    return _sha256(canonical_json_bytes(body))


def validate_record_sha256(record: Mapping[str, object]) -> str:
    if not isinstance(record, Mapping):
        raise BoundaryProofError("proof_record_digest_invalid", "record")
    actual = _require_sha256(
        record.get("record_sha256"),
        code="proof_record_digest_invalid",
        label="record_sha256",
    )
    expected = compute_record_sha256(record)
    if actual != expected:
        raise BoundaryProofError(
            "proof_record_digest_invalid",
            {"actual": actual, "expected": expected},
        )
    return actual


def validate_authority_bindings(
    selector_manifest: Mapping[str, object],
    source_census: Mapping[str, object],
) -> None:
    manifest = _require_mapping(
        selector_manifest,
        code="proof_authority_binding_mismatch",
        label="selector_manifest",
    )
    census = _require_mapping(
        source_census,
        code="proof_authority_binding_mismatch",
        label="source_census",
    )
    manifest_census = _require_sha256(
        manifest.get("source_census_sha256"),
        code="proof_authority_binding_mismatch",
        label="selector_manifest.source_census_sha256",
    )
    census_digest = _require_sha256(
        census.get("record_sha256"),
        code="proof_authority_binding_mismatch",
        label="source_census.record_sha256",
    )
    manifest_policy = _require_sha256(
        manifest.get("preedit_policy_sha256"),
        code="proof_authority_binding_mismatch",
        label="selector_manifest.preedit_policy_sha256",
    )
    census_policy = _require_sha256(
        census.get("preedit_policy_sha256"),
        code="proof_authority_binding_mismatch",
        label="source_census.preedit_policy_sha256",
    )
    if manifest_census != census_digest or manifest_policy != census_policy:
        raise BoundaryProofError(
            "proof_authority_binding_mismatch",
            {
                "manifest_source_census": manifest_census,
                "source_census": census_digest,
                "manifest_policy": manifest_policy,
                "source_census_policy": census_policy,
            },
        )


def runner_sha256(path: Path | None = None) -> str:
    """Return the raw-file SHA-256 pinned by every proof witness."""

    candidate = Path(__file__) if path is None else Path(path)
    try:
        identity = candidate.lstat()
        raw = candidate.read_bytes()
    except OSError as exc:
        raise BoundaryProofError("proof_runner_unreadable", str(candidate)) from exc
    if candidate.is_symlink() or not candidate.is_file() or identity.st_size != len(raw):
        raise BoundaryProofError("proof_runner_unreadable", str(candidate))
    return _sha256(raw)


def _verify_expected_runner_sha256(expected_runner_sha256: object) -> str:
    expected = _require_sha256(
        expected_runner_sha256,
        code="proof_runner_digest_mismatch",
        label="expected_runner_sha256",
    )
    actual = runner_sha256()
    if expected != actual:
        raise BoundaryProofError("proof_runner_digest_mismatch", actual)
    return actual


def _require_mapping(value: object, *, code: str, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BoundaryProofError(code, label)
    return value


def _require_exact_keys(
    value: object,
    keys: frozenset[str] | set[str],
    *,
    code: str,
    label: str,
) -> Mapping[str, object]:
    row = _require_mapping(value, code=code, label=label)
    if set(row) != set(keys):
        raise BoundaryProofError(code, f"{label}:{sorted(row)}")
    return row


def _require_list(value: object, *, code: str, label: str) -> list[object]:
    if not isinstance(value, list):
        raise BoundaryProofError(code, label)
    return value


def _require_string(value: object, *, code: str, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BoundaryProofError(code, label)
    return value


def _require_identifier(value: object, *, code: str, label: str) -> str:
    text = _require_string(value, code=code, label=label)
    if _SAFE_ID_RE.fullmatch(text) is None:
        raise BoundaryProofError(code, label)
    return text


def _require_int(value: object, *, code: str, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise BoundaryProofError(code, label)
    return value


def _require_sha1(value: object, *, code: str, label: str) -> str:
    text = _require_string(value, code=code, label=label)
    if _SHA1_RE.fullmatch(text) is None:
        raise BoundaryProofError(code, label)
    return text


def _require_sha256(value: object, *, code: str, label: str) -> str:
    text = _require_string(value, code=code, label=label)
    if _SHA256_RE.fullmatch(text) is None:
        raise BoundaryProofError(code, label)
    return text


def _safe_relative_path(value: object, *, code: str, label: str) -> str:
    text = _require_string(value, code=code, label=label)
    path = PurePosixPath(text)
    if path.is_absolute() or text != path.as_posix() or ".." in path.parts or "." in path.parts:
        raise BoundaryProofError(code, label)
    return text


def _string_list(
    value: object,
    *,
    code: str,
    label: str,
    nonempty: bool = True,
) -> tuple[str, ...]:
    raw = _require_list(value, code=code, label=label)
    if (nonempty and not raw) or any(not isinstance(item, str) or not item for item in raw):
        raise BoundaryProofError(code, label)
    result = tuple(item for item in raw if isinstance(item, str))
    if len(set(result)) != len(result):
        raise BoundaryProofError(code, label)
    return result


@dataclass(frozen=True, slots=True)
class ConsumerContract:
    consumer_id: str
    match_id: str
    caller_path: str
    caller_object_id: str
    start_line: int
    column_start: int
    end_line: int
    column_end: int
    selector_id: str
    witness_kind: str
    coverage_status: str
    coverage_witness_ids: tuple[str, ...]
    required_proof_kind: str


@dataclass(frozen=True, slots=True)
class SelectorContract:
    selector_id: str
    ordinal: int
    lane: str
    proof_kind: str
    coverage_witness_ids: tuple[str, ...]
    execution_kind: str | None = None
    pytest_module_path: str | None = None
    projection_blob_id: str | None = None
    mode: str | None = None
    physical_line_count: int | None = None
    pytest_node_ids: tuple[str, ...] = ()
    argv: tuple[str, ...] = ()
    input_bindings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class WitnessContract:
    witness_id: str
    selector_id: str
    consumer_id: str
    proof_kind: str
    witness_kind: str
    consumer_path: str
    caller_object_id: str
    start_line: int
    column_start: int
    end_line: int
    column_end: int
    match_id: str
    expected_result: object
    source_event_binding: Mapping[str, object] | None = None
    pytest_node_id: str | None = None
    query: Mapping[str, object] | None = None
    probe: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class DesiredSpec:
    proof_id: str
    ordinal: int
    selector_id: str
    witness_id: str
    consumer_id: str
    proof_kind: str
    expected_result: object


@dataclass(frozen=True, slots=True)
class ProofContract:
    provider_selectors: tuple[SelectorContract, ...]
    controller_selectors: tuple[SelectorContract, ...]
    witnesses: tuple[WitnessContract, ...]
    desired_specs: tuple[DesiredSpec, ...]
    consumers: tuple[ConsumerContract, ...]
    runner_sha256: str


def _parse_consumers(consumer_rows: Sequence[Mapping[str, object]]) -> tuple[ConsumerContract, ...]:
    if not isinstance(consumer_rows, Sequence) or isinstance(consumer_rows, (str, bytes)):
        raise BoundaryProofError("proof_consumer_rows_invalid")
    parsed: list[ConsumerContract] = []
    seen: set[str] = set()
    for index, raw in enumerate(consumer_rows):
        row = _require_mapping(raw, code="proof_consumer_rows_invalid", label=str(index))
        required = {
            "consumer_id",
            "match_id",
            "caller_path",
            "caller_object_id",
            "span",
            "selector_id",
            "witness_kind",
            "coverage_status",
            "coverage_witness_ids",
            "required_proof_kind",
        }
        if not required.issubset(row):
            raise BoundaryProofError("proof_consumer_rows_invalid", index)
        consumer_id = _require_identifier(
            row["consumer_id"], code="proof_consumer_rows_invalid", label="consumer_id"
        )
        if consumer_id in seen:
            raise BoundaryProofError("proof_consumer_rows_invalid", consumer_id)
        seen.add(consumer_id)
        span = _require_exact_keys(
            row["span"],
            {"line_start", "column_start", "line_end", "column_end"},
            code="proof_consumer_rows_invalid",
            label="span",
        )
        start = _require_int(
            span["line_start"],
            code="proof_consumer_rows_invalid",
            label="line_start",
            minimum=1,
        )
        column_start = _require_int(
            span["column_start"],
            code="proof_consumer_rows_invalid",
            label="column_start",
            minimum=0,
        )
        end = _require_int(
            span["line_end"],
            code="proof_consumer_rows_invalid",
            label="line_end",
            minimum=start,
        )
        column_end = _require_int(
            span["column_end"],
            code="proof_consumer_rows_invalid",
            label="column_end",
            minimum=0,
        )
        if end == start and column_end < column_start:
            raise BoundaryProofError("proof_consumer_rows_invalid", "span")
        proof_kind = _require_string(
            row["required_proof_kind"],
            code="proof_consumer_rows_invalid",
            label="required_proof_kind",
        )
        if proof_kind not in PROOF_KINDS:
            raise BoundaryProofError("proof_consumer_rows_invalid", proof_kind)
        witness_kind = _require_string(
            row["witness_kind"],
            code="proof_consumer_rows_invalid",
            label="witness_kind",
        )
        if witness_kind not in WITNESS_KINDS:
            raise BoundaryProofError("proof_consumer_rows_invalid", witness_kind)
        coverage_status = _require_string(
            row["coverage_status"],
            code="proof_consumer_rows_invalid",
            label="coverage_status",
        )
        if coverage_status not in COVERAGE_STATUSES:
            raise BoundaryProofError("proof_consumer_rows_invalid", coverage_status)
        coverage_witness_ids = _string_list(
            row["coverage_witness_ids"],
            code="proof_witness_backpointer_mismatch",
            label=consumer_id,
            nonempty=False,
        )
        if len(coverage_witness_ids) > 1:
            raise BoundaryProofError(
                "proof_required_consumer_domain_mismatch", consumer_id
            )
        if coverage_status == "required":
            if len(coverage_witness_ids) != 1:
                raise BoundaryProofError(
                    "proof_required_consumer_domain_mismatch", consumer_id
                )
        elif coverage_witness_ids:
            raise BoundaryProofError(
                f"proof_witness_attached_to_{coverage_status}_consumer",
                consumer_id,
            )
        parsed.append(
            ConsumerContract(
                consumer_id=consumer_id,
                match_id=_require_identifier(
                    row["match_id"], code="proof_consumer_rows_invalid", label="match_id"
                ),
                caller_path=_safe_relative_path(
                    row["caller_path"], code="proof_consumer_rows_invalid", label="caller_path"
                ),
                caller_object_id=_require_sha1(
                    row["caller_object_id"],
                    code="proof_consumer_rows_invalid",
                    label="caller_object_id",
                ),
                start_line=start,
                column_start=column_start,
                end_line=end,
                column_end=column_end,
                selector_id=_require_identifier(
                    row["selector_id"],
                    code="proof_consumer_rows_invalid",
                    label="selector_id",
                ),
                witness_kind=witness_kind,
                coverage_status=coverage_status,
                coverage_witness_ids=coverage_witness_ids,
                required_proof_kind=proof_kind,
            )
        )
    return tuple(parsed)


def _parse_provider_selectors(value: object) -> tuple[SelectorContract, ...]:
    raw_rows = _require_list(value, code="proof_provider_selectors_invalid", label="rows")
    if len(raw_rows) != 19:
        raise BoundaryProofError("proof_provider_selector_count_invalid", len(raw_rows))
    parsed: list[SelectorContract] = []
    all_nodes: set[str] = set()
    for index, raw in enumerate(raw_rows, start=1):
        row = _require_exact_keys(
            raw,
            _PROVIDER_SELECTOR_KEYS,
            code="proof_provider_selectors_invalid",
            label=str(index),
        )
        ordinal = _require_int(
            row["ordinal"], code="proof_provider_selectors_invalid", label="ordinal", minimum=1
        )
        if ordinal != index:
            raise BoundaryProofError("proof_selector_order_invalid", index)
        module = _safe_relative_path(
            row["pytest_module_path"],
            code="proof_provider_selectors_invalid",
            label="pytest_module_path",
        )
        if not module.endswith(".py"):
            raise BoundaryProofError("proof_provider_selectors_invalid", module)
        nodes = _string_list(
            row["pytest_node_ids"], code="proof_provider_selectors_invalid", label="pytest_node_ids"
        )
        if any(not node.startswith(module + "::") for node in nodes):
            raise BoundaryProofError("proof_pytest_node_unknown", module)
        if all_nodes.intersection(nodes):
            raise BoundaryProofError("proof_pytest_node_duplicate", module)
        all_nodes.update(nodes)
        mode = _require_string(
            row["mode"], code="proof_provider_selectors_invalid", label="mode"
        )
        if mode not in {"100644", "100755"}:
            raise BoundaryProofError("proof_provider_selectors_invalid", mode)
        coverage_witness_ids = _string_list(
            row["coverage_witness_ids"],
            code="proof_provider_selectors_invalid",
            label="coverage_witness_ids",
        )
        if len(coverage_witness_ids) != 1:
            raise BoundaryProofError(
                "proof_provider_selectors_invalid", "coverage_witness_ids"
            )
        parsed.append(
            SelectorContract(
                selector_id=_require_identifier(
                    row["selector_id"], code="proof_provider_selectors_invalid", label="selector_id"
                ),
                ordinal=ordinal,
                lane="provider_visible_pytest",
                proof_kind="boundary_runtime",
                coverage_witness_ids=coverage_witness_ids,
                pytest_module_path=module,
                projection_blob_id=_require_sha1(
                    row["projection_blob_id"],
                    code="proof_provider_selectors_invalid",
                    label="projection_blob_id",
                ),
                mode=mode,
                physical_line_count=_require_int(
                    row["physical_line_count"],
                    code="proof_provider_selectors_invalid",
                    label="physical_line_count",
                ),
                pytest_node_ids=nodes,
            )
        )
    return tuple(parsed)


def _parse_controller_selectors(
    value: object,
    *,
    actual_runner_sha256: str,
) -> tuple[SelectorContract, ...]:
    raw_rows = _require_list(value, code="proof_controller_selectors_invalid", label="rows")
    if not raw_rows:
        raise BoundaryProofError("proof_controller_selectors_invalid", "empty")
    parsed: list[SelectorContract] = []
    for index, raw in enumerate(raw_rows, start=1):
        row = _require_exact_keys(
            raw,
            _CONTROLLER_SELECTOR_KEYS,
            code="proof_controller_selectors_invalid",
            label=str(index),
        )
        ordinal = _require_int(
            row["ordinal"], code="proof_controller_selectors_invalid", label="ordinal", minimum=1
        )
        if ordinal != index:
            raise BoundaryProofError("proof_selector_order_invalid", index)
        proof_kind = _require_string(
            row["proof_kind"], code="proof_controller_selectors_invalid", label="proof_kind"
        )
        if proof_kind not in PROOF_KINDS:
            raise BoundaryProofError("proof_kind_mismatch", proof_kind)
        execution_kind = _require_string(
            row["execution_kind"],
            code="proof_controller_selectors_invalid",
            label="execution_kind",
        )
        if execution_kind not in CONTROLLER_EXECUTION_KINDS:
            raise BoundaryProofError(
                "proof_controller_selectors_invalid", execution_kind
            )
        allowed_proof_kinds = (
            {"boundary_runtime"}
            if execution_kind in {"pytest_aggregate", "isolated_probe"}
            else {"non_cdi_static", "reference_absence"}
        )
        if proof_kind not in allowed_proof_kinds:
            raise BoundaryProofError("proof_kind_mismatch", proof_kind)
        runner_path = _require_string(
            row["runner_path"], code="proof_controller_selectors_invalid", label="runner_path"
        )
        if runner_path != RUNNER_RELATIVE_PATH:
            raise BoundaryProofError("proof_runner_path_mismatch", runner_path)
        digest = _require_sha256(
            row["runner_sha256"],
            code="proof_controller_selectors_invalid",
            label="runner_sha256",
        )
        if digest != actual_runner_sha256:
            raise BoundaryProofError("proof_runner_digest_mismatch", digest)
        argv = _string_list(
            row["argv"], code="proof_controller_selectors_invalid", label="argv"
        )
        bindings_raw = _require_list(
            row["input_bindings"], code="proof_controller_selectors_invalid", label="input_bindings"
        )
        if not bindings_raw:
            raise BoundaryProofError("proof_controller_selectors_invalid", "input_bindings")
        bindings: list[tuple[str, str]] = []
        for binding_index, binding_raw in enumerate(bindings_raw):
            binding = _require_exact_keys(
                binding_raw,
                _INPUT_BINDING_KEYS,
                code="proof_controller_selectors_invalid",
                label=f"input_bindings.{binding_index}",
            )
            path = _require_string(
                binding["path"], code="proof_controller_selectors_invalid", label="binding.path"
            )
            pure = PurePosixPath(path)
            if not pure.is_absolute():
                path = _safe_relative_path(
                    path, code="proof_controller_selectors_invalid", label="binding.path"
                )
            bindings.append(
                (
                    path,
                    _require_sha256(
                        binding["sha256"],
                        code="proof_controller_selectors_invalid",
                        label="binding.sha256",
                    ),
                )
            )
        if len({path for path, _ in bindings}) != len(bindings):
            raise BoundaryProofError("proof_controller_selectors_invalid", "duplicate binding")
        coverage_witness_ids = _string_list(
            row["coverage_witness_ids"],
            code="proof_controller_selectors_invalid",
            label="coverage_witness_ids",
            nonempty=False,
        )
        if len(coverage_witness_ids) > 1:
            raise BoundaryProofError(
                "proof_controller_selectors_invalid", "coverage_witness_ids"
            )
        parsed.append(
            SelectorContract(
                selector_id=_require_identifier(
                    row["selector_id"], code="proof_controller_selectors_invalid", label="selector_id"
                ),
                ordinal=ordinal,
                lane="controller_only",
                proof_kind=proof_kind,
                coverage_witness_ids=coverage_witness_ids,
                execution_kind=execution_kind,
                argv=argv,
                input_bindings=tuple(bindings),
            )
        )
    return tuple(parsed)


def _parse_witnesses(value: object, *, runner_digest: str) -> tuple[WitnessContract, ...]:
    raw_rows = _require_list(value, code="proof_witnesses_invalid", label="rows")
    if not raw_rows:
        raise BoundaryProofError("proof_witnesses_invalid", "empty")
    parsed: list[WitnessContract] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_rows):
        mapping = _require_mapping(raw, code="proof_witnesses_invalid", label=str(index))
        kind = _require_string(
            mapping.get("witness_kind"), code="proof_witnesses_invalid", label="witness_kind"
        )
        if kind == "pytest_runtime":
            keys = _PYTEST_WITNESS_KEYS
        elif kind == "controller_pytest_runtime":
            keys = _CONTROLLER_PYTEST_WITNESS_KEYS
        elif kind == "static_ast":
            keys = _STATIC_WITNESS_KEYS
        elif kind == "runtime_probe":
            keys = _RUNTIME_WITNESS_KEYS
        else:
            raise BoundaryProofError("proof_witnesses_invalid", kind)
        selector_id = _require_identifier(
            mapping.get("selector_id"),
            code="proof_witnesses_invalid",
            label="selector_id",
        )
        if kind == "pytest_runtime" and selector_id.startswith("CO-"):
            raise BoundaryProofError("proof_selector_cross_lane_duplicate", selector_id)
        row = _require_exact_keys(
            mapping, keys, code="proof_witnesses_invalid", label=str(index)
        )
        witness_id = _require_identifier(
            row["witness_id"], code="proof_witnesses_invalid", label="witness_id"
        )
        if witness_id in seen:
            raise BoundaryProofError("proof_witnesses_invalid", witness_id)
        seen.add(witness_id)
        digest = _require_sha256(
            row["runner_sha256"], code="proof_witnesses_invalid", label="runner_sha256"
        )
        if digest != runner_digest:
            raise BoundaryProofError("proof_runner_digest_mismatch", witness_id)
        start = _require_int(
            row["start_line"], code="proof_witnesses_invalid", label="start_line", minimum=1
        )
        column_start = _require_int(
            row["column_start"],
            code="proof_witnesses_invalid",
            label="column_start",
            minimum=0,
        )
        end = _require_int(
            row["end_line"], code="proof_witnesses_invalid", label="end_line", minimum=start
        )
        column_end = _require_int(
            row["column_end"],
            code="proof_witnesses_invalid",
            label="column_end",
            minimum=0,
        )
        if end == start and column_end < column_start:
            raise BoundaryProofError("proof_witnesses_invalid", "span")
        proof_kind = _require_string(
            row["proof_kind"], code="proof_witnesses_invalid", label="proof_kind"
        )
        if proof_kind not in PROOF_KINDS:
            raise BoundaryProofError("proof_kind_mismatch", witness_id)
        common: dict[str, Any] = {
            "witness_id": witness_id,
            "selector_id": selector_id,
            "consumer_id": _require_identifier(
                row["consumer_id"], code="proof_witnesses_invalid", label="consumer_id"
            ),
            "proof_kind": proof_kind,
            "witness_kind": kind,
            "consumer_path": _safe_relative_path(
                row["consumer_path"], code="proof_witnesses_invalid", label="consumer_path"
            ),
            "caller_object_id": _require_sha1(
                row["caller_object_id"],
                code="proof_witnesses_invalid",
                label="caller_object_id",
            ),
            "start_line": start,
            "column_start": column_start,
            "end_line": end,
            "column_end": column_end,
            "match_id": _require_identifier(
                row["match_id"], code="proof_witnesses_invalid", label="match_id"
            ),
        }
        if kind == "pytest_runtime":
            binding = _parse_source_event_binding(row["source_event_binding"])
            attribution = binding["attribution"]
            assert isinstance(attribution, Mapping)
            _validate_json_value(row["expected_event"], label="expected_event")
            parsed.append(
                WitnessContract(
                    **common,
                    expected_result=copy.deepcopy(row["expected_event"]),
                    source_event_binding=binding,
                    pytest_node_id=(
                        str(attribution["pytest_node_id"])
                        if attribution["attribution_kind"] == "pytest_node"
                        else None
                    ),
                )
            )
        elif kind == "controller_pytest_runtime":
            binding = _parse_source_event_binding(row["source_event_binding"])
            _validate_json_value(row["expected_event"], label="expected_event")
            parsed.append(
                WitnessContract(
                    **common,
                    expected_result=copy.deepcopy(row["expected_event"]),
                    source_event_binding=binding,
                )
            )
        elif kind == "static_ast":
            query = _require_mapping(
                row["query"], code="proof_witnesses_invalid", label="query"
            )
            _validate_static_query(query)
            _validate_json_value(row["expected_result"], label="expected_result")
            parsed.append(
                WitnessContract(
                    **common,
                    expected_result=copy.deepcopy(row["expected_result"]),
                    query=copy.deepcopy(query),
                )
            )
        else:
            probe = _require_mapping(
                row["probe"], code="proof_witnesses_invalid", label="probe"
            )
            binding = _parse_source_event_binding(row["source_event_binding"])
            _validate_runtime_probe(probe)
            _validate_json_value(row["expected_event"], label="expected_event")
            parsed.append(
                WitnessContract(
                    **common,
                    expected_result=copy.deepcopy(row["expected_event"]),
                    source_event_binding=binding,
                    probe=copy.deepcopy(probe),
                )
            )
    return tuple(parsed)


def _validate_static_query(query: Mapping[str, object]) -> None:
    kind = query.get("query_kind")
    if kind == "path_absent":
        if set(query) != {"query_kind"}:
            raise BoundaryProofError("proof_static_query_invalid", kind)
        return
    if kind != "forbidden_syntax_absent" or set(query) != {
        "query_kind",
        "forbidden_names",
        "forbidden_attributes",
        "forbidden_string_literals",
    }:
        raise BoundaryProofError("proof_static_query_invalid", kind)
    for key in ("forbidden_names", "forbidden_attributes", "forbidden_string_literals"):
        _string_list(query[key], code="proof_static_query_invalid", label=key, nonempty=False)


def _validate_runtime_probe(probe: Mapping[str, object]) -> None:
    action = probe.get("action")
    if action == "import_module":
        row = _require_exact_keys(
            probe,
            {"action", "module", "expected_outcome"},
            code="proof_runtime_probe_invalid",
            label="probe",
        )
    elif action == "call":
        row = _require_exact_keys(
            probe,
            {
                "action",
                "module",
                "callable",
                "args",
                "kwargs",
                "return_value",
                "expected_outcome",
            },
            code="proof_runtime_probe_invalid",
            label="probe",
        )
        _require_dotted_identifier(row["callable"], label="callable")
        if not isinstance(row["args"], list) or not isinstance(
            row["kwargs"], Mapping
        ):
            raise BoundaryProofError("proof_runtime_probe_invalid")
        _validate_transport_json_value(row["args"], label="probe.args")
        _validate_transport_json_value(row["kwargs"], label="probe.kwargs")
        if row["return_value"] != "ignore":
            raise BoundaryProofError("proof_runtime_probe_invalid", "return_value")
    else:
        raise BoundaryProofError("proof_runtime_probe_invalid", "action")
    _require_dotted_identifier(row["module"], label="module")
    _validate_expected_outcome(row["expected_outcome"])


def _require_dotted_identifier(value: object, *, label: str) -> str:
    text = _require_string(
        value, code="proof_runtime_probe_invalid", label=label
    )
    if _DOTTED_IDENTIFIER_RE.fullmatch(text) is None:
        raise BoundaryProofError("proof_runtime_probe_invalid", label)
    return text


def _validate_expected_outcome(value: object) -> None:
    outcome = _require_mapping(
        value, code="proof_runtime_probe_invalid", label="expected_outcome"
    )
    status = outcome.get("status")
    if status == "returned":
        _require_exact_keys(
            outcome,
            {"status"},
            code="proof_runtime_probe_invalid",
            label="expected_outcome",
        )
        return
    if status == "raised":
        row = _require_exact_keys(
            outcome,
            {"status", "exception_type"},
            code="proof_runtime_probe_invalid",
            label="expected_outcome",
        )
        _require_dotted_identifier(row["exception_type"], label="exception_type")
        return
    raise BoundaryProofError("proof_runtime_probe_invalid", "expected_outcome")


def _validate_transport_json_value(value: object, *, label: str) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise BoundaryProofError("proof_runtime_probe_invalid", label) from exc
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_transport_json_value(item, label=f"{label}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise BoundaryProofError("proof_runtime_probe_invalid", label)
            _validate_transport_json_value(item, label=f"{label}.{key}")
        return
    raise BoundaryProofError("proof_runtime_probe_invalid", label)


def _parse_source_event_binding(value: object) -> Mapping[str, object]:
    row = _require_exact_keys(
        value,
        {"event_kind", "phase", "attribution"},
        code="proof_witnesses_invalid",
        label="source_event_binding",
    )
    event_kind = _require_string(
        row["event_kind"], code="proof_witnesses_invalid", label="event_kind"
    )
    if event_kind not in {"opcode_exact_span", "import_alias_opcode", "callable_entry"}:
        raise BoundaryProofError("proof_witnesses_invalid", "event_kind")
    phase = _require_string(
        row["phase"], code="proof_witnesses_invalid", label="phase"
    )
    attribution = _require_mapping(
        row["attribution"], code="proof_witnesses_invalid", label="attribution"
    )
    attribution_kind = attribution.get("attribution_kind")
    if attribution_kind == "pytest_node":
        parsed_attribution = _require_exact_keys(
            attribution,
            {"attribution_kind", "pytest_node_id"},
            code="proof_witnesses_invalid",
            label="attribution",
        )
        _require_string(
            parsed_attribution["pytest_node_id"],
            code="proof_witnesses_invalid",
            label="pytest_node_id",
        )
        allowed_phases = {"setup", "call", "teardown"}
    elif attribution_kind == "selector_module":
        parsed_attribution = _require_exact_keys(
            attribution,
            {"attribution_kind", "pytest_module_path"},
            code="proof_witnesses_invalid",
            label="attribution",
        )
        _require_string(
            parsed_attribution["pytest_module_path"],
            code="proof_witnesses_invalid",
            label="pytest_module_path",
        )
        allowed_phases = {"bootstrap", "collection"}
    elif attribution_kind == "residual_action":
        parsed_attribution = _require_exact_keys(
            attribution,
            {"attribution_kind", "action_sha256"},
            code="proof_witnesses_invalid",
            label="attribution",
        )
        _require_sha256(
            parsed_attribution["action_sha256"],
            code="proof_witnesses_invalid",
            label="action_sha256",
        )
        allowed_phases = {"residual"}
    else:
        raise BoundaryProofError("proof_witnesses_invalid", "attribution_kind")
    if phase not in allowed_phases:
        raise BoundaryProofError("proof_witnesses_invalid", "phase")
    return copy.deepcopy(row)


def _parse_specs(value: object) -> tuple[DesiredSpec, ...]:
    rows = _require_list(value, code="proof_specs_invalid", label="rows")
    if not rows:
        raise BoundaryProofError("proof_specs_invalid", "empty")
    parsed: list[DesiredSpec] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows, start=1):
        row = _require_exact_keys(
            raw, _SPEC_KEYS, code="proof_specs_invalid", label=str(index)
        )
        ordinal = _require_int(
            row["ordinal"], code="proof_specs_invalid", label="ordinal", minimum=1
        )
        if ordinal != index:
            raise BoundaryProofError("proof_spec_reordered", index)
        proof_id = _require_identifier(
            row["proof_id"], code="proof_specs_invalid", label="proof_id"
        )
        if proof_id in seen:
            raise BoundaryProofError("proof_specs_invalid", proof_id)
        seen.add(proof_id)
        proof_kind = _require_string(
            row["proof_kind"], code="proof_specs_invalid", label="proof_kind"
        )
        if proof_kind not in PROOF_KINDS:
            raise BoundaryProofError("proof_kind_mismatch", proof_id)
        _validate_json_value(row["expected_result"], label="expected_result")
        parsed.append(
            DesiredSpec(
                proof_id=proof_id,
                ordinal=ordinal,
                selector_id=_require_identifier(
                    row["selector_id"], code="proof_specs_invalid", label="selector_id"
                ),
                witness_id=_require_identifier(
                    row["witness_id"], code="proof_specs_invalid", label="witness_id"
                ),
                consumer_id=_require_identifier(
                    row["consumer_id"], code="proof_specs_invalid", label="consumer_id"
                ),
                proof_kind=proof_kind,
                expected_result=copy.deepcopy(row["expected_result"]),
            )
        )
    return tuple(parsed)


def _validate_consumer_selector_class(
    consumer: ConsumerContract,
    selector: SelectorContract,
) -> None:
    if consumer.required_proof_kind != selector.proof_kind:
        raise BoundaryProofError("proof_kind_mismatch", consumer.consumer_id)
    if selector.lane == "provider_visible_pytest":
        expected_witness_kind = "pytest_runtime"
    elif selector.execution_kind == "pytest_aggregate":
        expected_witness_kind = "controller_pytest_runtime"
    elif selector.execution_kind == "isolated_probe":
        expected_witness_kind = "runtime_probe"
    elif selector.execution_kind == "static_ast":
        expected_witness_kind = "static_ast"
    else:
        raise BoundaryProofError("proof_consumer_class_mismatch", consumer.consumer_id)
    if consumer.witness_kind != expected_witness_kind:
        raise BoundaryProofError("proof_consumer_class_mismatch", consumer.consumer_id)


def validate_contract(
    selector_manifest: Mapping[str, object],
    *,
    consumer_rows: Sequence[Mapping[str, object]],
    expected_runner_sha256: str,
) -> ProofContract:
    """Validate the closed selector/witness/proof join without executing it."""

    manifest = _require_mapping(
        selector_manifest, code="proof_selector_manifest_invalid", label="manifest"
    )
    required_sections = {
        "provider_visible_pytest_selectors",
        "controller_only_proof_selectors",
        "coverage_witnesses",
        "desired_state_proof_specs",
    }
    if not required_sections.issubset(manifest):
        raise BoundaryProofError("proof_selector_manifest_invalid", "sections")
    actual_digest = _verify_expected_runner_sha256(expected_runner_sha256)
    providers = _parse_provider_selectors(
        manifest["provider_visible_pytest_selectors"]
    )
    controllers = _parse_controller_selectors(
        manifest["controller_only_proof_selectors"],
        actual_runner_sha256=actual_digest,
    )
    provider_ids = tuple(row.selector_id for row in providers)
    controller_ids = tuple(row.selector_id for row in controllers)
    if len(set(provider_ids)) != len(provider_ids) or len(set(controller_ids)) != len(controller_ids):
        raise BoundaryProofError("proof_selector_duplicate")
    if set(provider_ids).intersection(controller_ids):
        raise BoundaryProofError("proof_selector_cross_lane_duplicate")
    provider_nodes = {node for row in providers for node in row.pytest_node_ids}
    if any(token in provider_nodes for row in controllers for token in row.argv):
        raise BoundaryProofError("proof_selector_cross_lane_duplicate", "argv")

    consumers = _parse_consumers(consumer_rows)
    consumers_by_id = {row.consumer_id: row for row in consumers}
    witnesses = _parse_witnesses(
        manifest["coverage_witnesses"], runner_digest=actual_digest
    )
    witnesses_by_id = {row.witness_id: row for row in witnesses}
    selectors_by_id = {row.selector_id: row for row in (*providers, *controllers)}
    for consumer in consumers:
        selector = selectors_by_id.get(consumer.selector_id)
        if selector is None:
            raise BoundaryProofError(
                "proof_consumer_class_mismatch", consumer.consumer_id
            )
        _validate_consumer_selector_class(consumer, selector)
    for witness in witnesses:
        selector = selectors_by_id.get(witness.selector_id)
        if selector is None:
            raise BoundaryProofError("proof_witness_backpointer_mismatch", witness.witness_id)
        consumer = consumers_by_id.get(witness.consumer_id)
        if consumer is None:
            raise BoundaryProofError("proof_consumer_unmapped", witness.consumer_id)
        if consumer.coverage_status != "required":
            raise BoundaryProofError(
                f"proof_witness_attached_to_{consumer.coverage_status}_consumer",
                witness.consumer_id,
            )
        if (
            consumer.selector_id != witness.selector_id
            or consumer.witness_kind != witness.witness_kind
        ):
            raise BoundaryProofError(
                "proof_consumer_class_mismatch", witness.consumer_id
            )
        if (
            consumer.match_id != witness.match_id
            or consumer.caller_path != witness.consumer_path
            or consumer.caller_object_id != witness.caller_object_id
            or consumer.start_line != witness.start_line
            or consumer.column_start != witness.column_start
            or consumer.end_line != witness.end_line
            or consumer.column_end != witness.column_end
        ):
            raise BoundaryProofError("proof_witness_consumer_binding_mismatch", witness.witness_id)
        if consumer.required_proof_kind != witness.proof_kind:
            raise BoundaryProofError("proof_kind_mismatch", witness.witness_id)
        if selector.proof_kind != witness.proof_kind:
            raise BoundaryProofError("proof_kind_mismatch", witness.witness_id)
        if selector.lane == "provider_visible_pytest":
            if witness.witness_kind != "pytest_runtime" or witness.proof_kind != "boundary_runtime":
                raise BoundaryProofError("proof_kind_mismatch", witness.witness_id)
            binding = witness.source_event_binding
            assert binding is not None
            attribution = binding["attribution"]
            assert isinstance(attribution, Mapping)
            if attribution["attribution_kind"] == "pytest_node":
                if attribution["pytest_node_id"] not in selector.pytest_node_ids:
                    raise BoundaryProofError("proof_pytest_node_unknown", witness.witness_id)
            elif attribution["pytest_module_path"] != selector.pytest_module_path:
                raise BoundaryProofError("proof_pytest_node_unknown", witness.witness_id)
        elif witness.witness_kind == "pytest_runtime":
            raise BoundaryProofError("proof_selector_cross_lane_duplicate", witness.witness_id)
        elif witness.witness_kind == "controller_pytest_runtime":
            if (
                selector.execution_kind != "pytest_aggregate"
                or witness.proof_kind != "boundary_runtime"
            ):
                raise BoundaryProofError("proof_kind_mismatch", witness.witness_id)
        elif witness.witness_kind == "runtime_probe":
            if (
                selector.execution_kind != "isolated_probe"
                or witness.proof_kind != "boundary_runtime"
            ):
                raise BoundaryProofError("proof_kind_mismatch", witness.witness_id)
        elif witness.witness_kind == "static_ast":
            if selector.execution_kind != "static_ast" or witness.proof_kind not in {
                "non_cdi_static",
                "reference_absence",
            }:
                raise BoundaryProofError("proof_kind_mismatch", witness.witness_id)

    required_consumer_ids = {
        row.consumer_id for row in consumers if row.coverage_status == "required"
    }
    witnessed_consumer_ids = {row.consumer_id for row in witnesses}
    if required_consumer_ids != witnessed_consumer_ids:
        raise BoundaryProofError(
            "proof_required_consumer_domain_mismatch",
            sorted(required_consumer_ids.symmetric_difference(witnessed_consumer_ids)),
        )
    for consumer in consumers:
        actual = tuple(
            row.witness_id for row in witnesses if row.consumer_id == consumer.consumer_id
        )
        if consumer.coverage_status == "required":
            if actual != consumer.coverage_witness_ids or len(actual) != 1:
                raise BoundaryProofError(
                    "proof_witness_backpointer_mismatch", consumer.consumer_id
                )
        elif actual:
            raise BoundaryProofError(
                f"proof_witness_attached_to_{consumer.coverage_status}_consumer",
                consumer.consumer_id,
            )
    for selector in (*providers, *controllers):
        actual = tuple(
            row.witness_id for row in witnesses if row.selector_id == selector.selector_id
        )
        if actual != selector.coverage_witness_ids or any(
            witness_id not in witnesses_by_id for witness_id in selector.coverage_witness_ids
        ):
            raise BoundaryProofError("proof_witness_backpointer_mismatch", selector.selector_id)

    specs = _parse_specs(manifest["desired_state_proof_specs"])
    if len(specs) != len(witnesses):
        raise BoundaryProofError("proof_spec_witness_mismatch")
    for spec, witness in zip(specs, witnesses, strict=True):
        if (
            spec.witness_id != witness.witness_id
            or spec.selector_id != witness.selector_id
            or spec.consumer_id != witness.consumer_id
            or spec.proof_kind != witness.proof_kind
            or spec.expected_result != witness.expected_result
        ):
            raise BoundaryProofError("proof_kind_mismatch", spec.proof_id)
    return ProofContract(
        provider_selectors=providers,
        controller_selectors=controllers,
        witnesses=witnesses,
        desired_specs=specs,
        consumers=consumers,
        runner_sha256=actual_digest,
    )


def _canonical_absolute(path: Path, *, code: str, must_exist: bool) -> Path:
    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except OSError as exc:
        raise BoundaryProofError(code, str(candidate)) from exc
    if not candidate.is_absolute() or candidate != resolved:
        raise BoundaryProofError(code, str(candidate))
    return candidate


def _git_environment() -> dict[str, str]:
    return {
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
    }


def _verify_pinned_git() -> None:
    candidate = Path(PINNED_GIT)
    try:
        identity = candidate.lstat()
        raw = candidate.read_bytes()
    except OSError as exc:
        raise BoundaryProofError("proof_git_identity_mismatch", str(candidate)) from exc
    if (
        candidate != Path("/usr/bin/git")
        or candidate.is_symlink()
        or not candidate.is_file()
        or identity.st_size != len(raw)
        or _sha256(raw) != PINNED_GIT_SHA256
    ):
        raise BoundaryProofError("proof_git_identity_mismatch", str(candidate))
    try:
        completed = subprocess.run(
            (str(candidate), "--version"),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        )
    except OSError as exc:
        raise BoundaryProofError("proof_git_identity_mismatch", str(candidate)) from exc
    try:
        observed_version = completed.stdout.decode("ascii", "strict").strip()
    except UnicodeError as exc:
        raise BoundaryProofError("proof_git_identity_mismatch", "version") from exc
    if completed.returncode != 0 or observed_version != PINNED_GIT_VERSION:
        raise BoundaryProofError(
            "proof_git_identity_mismatch",
            {"version": observed_version, "returncode": completed.returncode},
        )


def _verify_pinned_python(python: Path) -> tuple[Path, Path]:
    candidate = Path(python)
    if candidate != PINNED_PYTHON or not candidate.is_absolute():
        raise BoundaryProofError("proof_python_identity_mismatch", str(candidate))
    try:
        link_identity = candidate.lstat()
        link_target = os.readlink(candidate)
        resolved = candidate.resolve(strict=True)
        target_identity = resolved.lstat()
        raw = resolved.read_bytes()
    except OSError as exc:
        raise BoundaryProofError(
            "proof_python_identity_mismatch",
            str(candidate),
        ) from exc
    if (
        not candidate.is_symlink()
        or link_identity.st_size != len(PINNED_PYTHON_LINK_TARGET)
        or link_target != PINNED_PYTHON_LINK_TARGET
        or resolved != PINNED_PYTHON_TARGET
        or resolved.is_symlink()
        or not resolved.is_file()
        or target_identity.st_size != len(raw)
        or _sha256(raw) != PINNED_PYTHON_SHA256
    ):
        raise BoundaryProofError("proof_python_identity_mismatch", str(candidate))
    env = {
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
    }
    try:
        completed = subprocess.run(
            (str(candidate), "--version"),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as exc:
        raise BoundaryProofError(
            "proof_python_identity_mismatch",
            str(candidate),
        ) from exc
    try:
        observed_version = (completed.stdout or completed.stderr).decode(
            "ascii",
            "strict",
        ).strip()
    except UnicodeError as exc:
        raise BoundaryProofError(
            "proof_python_identity_mismatch",
            "version",
        ) from exc
    if completed.returncode != 0 or observed_version != PINNED_PYTHON_VERSION:
        raise BoundaryProofError(
            "proof_python_identity_mismatch",
            {"version": observed_version, "returncode": completed.returncode},
        )
    return candidate, resolved


def _pytest_carrier_environment() -> dict[str, str]:
    return {
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }


def _verify_pytest_carrier(
    pytest_carrier: Path,
    *,
    expected_sha256: str,
) -> PytestCarrier:
    candidate = Path(pytest_carrier)
    expected = _require_sha256(
        expected_sha256,
        code="proof_pytest_carrier_identity_mismatch",
        label="expected_pytest_carrier_sha256",
    )
    try:
        identity = candidate.lstat()
        raw = candidate.read_bytes()
    except OSError as exc:
        raise BoundaryProofError(
            "proof_pytest_carrier_identity_mismatch", str(candidate)
        ) from exc
    if (
        candidate != PINNED_PYTEST_CARRIER
        or not candidate.is_absolute()
        or candidate.is_symlink()
        or not candidate.is_file()
        or identity.st_size != len(raw)
        or expected != PINNED_PYTEST_CARRIER_SHA256
        or _sha256(raw) != expected
    ):
        raise BoundaryProofError(
            "proof_pytest_carrier_identity_mismatch", str(candidate)
        )
    env = _pytest_carrier_environment()
    try:
        version_result = subprocess.run(
            (str(candidate), "--version"),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as exc:
        raise BoundaryProofError(
            "proof_pytest_carrier_identity_mismatch", str(candidate)
        ) from exc
    try:
        version = (version_result.stdout or version_result.stderr).decode(
            "ascii", "strict"
        ).strip()
    except UnicodeError as exc:
        raise BoundaryProofError(
            "proof_pytest_carrier_identity_mismatch", "version"
        ) from exc
    if version_result.returncode != 0 or version != PINNED_PYTEST_CARRIER_VERSION:
        raise BoundaryProofError(
            "proof_pytest_carrier_identity_mismatch",
            {"version": version, "returncode": version_result.returncode},
        )
    carrier = PytestCarrier(candidate, expected, version)
    try:
        setup_result = subprocess.run(
            carrier.wrap(("/usr/bin/true",)),
            cwd=Path("/"),
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise BoundaryProofError(
            "proof_pytest_carrier_setup_failed", str(candidate)
        ) from exc
    if setup_result.returncode != 0:
        raise BoundaryProofError(
            "proof_pytest_carrier_setup_failed",
            {
                "returncode": setup_result.returncode,
                "stderr": setup_result.stderr[-2000:].decode("utf-8", "replace"),
            },
        )
    return carrier


def _run_private_tmp_child(
    carrier: PytestCarrier,
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    preserved_paths: Sequence[Path] = (),
) -> subprocess.CompletedProcess[bytes]:
    tmp_root = Path("/tmp")
    candidates: list[Path] = []
    for raw_path in preserved_paths:
        candidate = _canonical_absolute(
            Path(raw_path),
            code="proof_pytest_carrier_setup_failed",
            must_exist=True,
        )
        if candidate.is_symlink() or not candidate.is_dir() or candidate == tmp_root:
            raise BoundaryProofError(
                "proof_pytest_carrier_setup_failed", str(candidate)
            )
        if candidate.is_relative_to(tmp_root):
            candidates.append(candidate)
    bound_paths: list[Path] = []
    for candidate in sorted(set(candidates), key=lambda path: len(path.parts)):
        if not any(candidate.is_relative_to(parent) for parent in bound_paths):
            bound_paths.append(candidate)
    try:
        return subprocess.run(
            carrier.wrap(tuple(argv), preserved_paths=bound_paths),
            cwd=cwd,
            env=dict(env),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise BoundaryProofError(
            "proof_pytest_carrier_execution_failed", str(carrier.executable)
        ) from exc


def _run_git(workspace: Path, *args: str) -> bytes:
    _verify_pinned_git()
    try:
        completed = subprocess.run(
            (str(PINNED_GIT), "-C", str(workspace), *args),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        )
    except OSError as exc:
        raise BoundaryProofError("proof_git_failed", args) from exc
    if completed.returncode != 0:
        raise BoundaryProofError(
            "proof_git_failed",
            {"argv": args, "stderr": completed.stderr[-2000:].decode("utf-8", "replace")},
        )
    return completed.stdout


def _verify_tree(workspace: Path, expected_tree: str) -> tuple[Path, str]:
    root = _canonical_absolute(
        Path(workspace), code="proof_workspace_invalid", must_exist=True
    )
    if not root.is_dir() or root.is_symlink():
        raise BoundaryProofError("proof_workspace_invalid", str(root))
    expected = _require_sha1(
        expected_tree, code="proof_tree_identity_mismatch", label="expected_tree"
    )
    tree = _run_git(root, "rev-parse", "HEAD^{tree}").decode("ascii", "strict").strip()
    if tree != expected:
        raise BoundaryProofError("proof_tree_identity_mismatch", (tree, expected))
    if _run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise BoundaryProofError("proof_tree_dirty", str(root))
    return root, tree


def _frozen_tree_leaf_metadata(
    workspace: Path,
    expected_tree: str,
) -> dict[str, tuple[int, ...]]:
    """Snapshot mutation metadata for frozen leaves, excluding read-only atime."""

    raw_paths = _run_git(
        workspace,
        "ls-tree",
        "-r",
        "-z",
        "--name-only",
        "--full-tree",
        expected_tree,
    )
    if raw_paths and not raw_paths.endswith(b"\0"):
        raise BoundaryProofError("proof_tree_dirty", "frozen leaf listing")
    records = raw_paths[:-1].split(b"\0") if raw_paths else []
    result: dict[str, tuple[int, ...]] = {}
    for raw_path in records:
        try:
            relative = _safe_relative_path(
                raw_path.decode("utf-8", "strict"),
                code="proof_tree_dirty",
                label="frozen leaf path",
            )
            identity = (workspace / relative).lstat()
        except (OSError, UnicodeError) as exc:
            raise BoundaryProofError("proof_tree_dirty", "frozen leaf identity") from exc
        if relative in result:
            raise BoundaryProofError("proof_tree_dirty", "duplicate frozen leaf")
        result[relative] = (
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
    return result


def _verify_frozen_source_identity(
    workspace: Path,
    expected_tree: str,
    expected_leaf_metadata: Mapping[str, tuple[int, ...]],
) -> None:
    _verify_tree(workspace, expected_tree)
    observed = _frozen_tree_leaf_metadata(workspace, expected_tree)
    if observed != expected_leaf_metadata:
        changed = sorted(
            set(observed).symmetric_difference(expected_leaf_metadata)
            | {
                path
                for path in set(observed).intersection(expected_leaf_metadata)
                if observed[path] != expected_leaf_metadata[path]
            }
        )
        raise BoundaryProofError("proof_tree_dirty", changed)


def _workspace_path(workspace: Path, relative: str, *, may_be_absent: bool) -> Path:
    candidate = workspace / relative
    try:
        resolved = candidate.resolve(strict=not may_be_absent)
    except OSError as exc:
        if may_be_absent and not os.path.lexists(candidate):
            resolved = candidate.resolve(strict=False)
        else:
            raise BoundaryProofError("proof_target_path_invalid", relative) from exc
    if not resolved.is_relative_to(workspace) or os.path.islink(candidate):
        raise BoundaryProofError("proof_target_path_invalid", relative)
    return candidate


def _target_blob(workspace: Path, relative: str) -> str | None:
    candidate = _workspace_path(workspace, relative, may_be_absent=True)
    if not os.path.lexists(candidate):
        return None
    if candidate.is_symlink() or not candidate.is_file():
        raise BoundaryProofError("proof_target_path_invalid", relative)
    try:
        return _run_git(workspace, "hash-object", "--no-filters", "--", relative).decode(
            "ascii", "strict"
        ).strip()
    except BoundaryProofError:
        raise


def _verify_provider_assets(contract: ProofContract, workspace: Path) -> None:
    for selector in contract.provider_selectors:
        assert selector.pytest_module_path is not None
        assert selector.projection_blob_id is not None
        assert selector.mode is not None
        assert selector.physical_line_count is not None
        path = _workspace_path(workspace, selector.pytest_module_path, may_be_absent=False)
        if path.is_symlink() or not path.is_file():
            raise BoundaryProofError("proof_selector_blob_drift", selector.selector_id)
        blob = _target_blob(workspace, selector.pytest_module_path)
        if blob != selector.projection_blob_id:
            raise BoundaryProofError("proof_selector_blob_drift", selector.selector_id)
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError) as exc:
            raise BoundaryProofError("proof_selector_blob_drift", selector.selector_id) from exc
        if len(text.splitlines()) != selector.physical_line_count:
            raise BoundaryProofError("proof_selector_blob_drift", selector.selector_id)
        indexed = _run_git(workspace, "ls-files", "-s", "--", selector.pytest_module_path)
        parts = indexed.decode("ascii", "strict").strip().split()
        if len(parts) < 3 or parts[0] != selector.mode or parts[1] != selector.projection_blob_id:
            raise BoundaryProofError("proof_selector_blob_drift", selector.selector_id)


def _verify_baseline_consumer_assets(
    contract: ProofContract,
    workspace: Path,
) -> None:
    for consumer in contract.consumers:
        observed = _target_blob(workspace, consumer.caller_path)
        if observed != consumer.caller_object_id:
            raise BoundaryProofError(
                "proof_witness_blob_drift",
                consumer.consumer_id,
            )


def _verify_input_bindings(contract: ProofContract, workspace: Path) -> None:
    observed: dict[str, str] = {}
    for selector in contract.controller_selectors:
        for raw_path, expected in selector.input_bindings:
            if PurePosixPath(raw_path).is_absolute():
                path = _canonical_absolute(
                    Path(raw_path), code="proof_input_binding_invalid", must_exist=True
                )
            else:
                path = _workspace_path(workspace, raw_path, may_be_absent=False)
            try:
                identity = path.lstat()
                raw = path.read_bytes()
            except OSError as exc:
                raise BoundaryProofError("proof_input_binding_invalid", raw_path) from exc
            if path.is_symlink() or not path.is_file() or identity.st_size != len(raw):
                raise BoundaryProofError("proof_input_binding_invalid", raw_path)
            digest = _sha256(raw)
            prior = observed.setdefault(raw_path, digest)
            if prior != digest or digest != expected:
                raise BoundaryProofError("proof_input_binding_drift", raw_path)


_EXACT_SOURCE_EVENT_OBSERVER = r'''
from __future__ import annotations

import ast
import copy
import dis
import hashlib
import io
import pathlib
import sys
import threading
import tokenize
import types


class SourceEventObserverError(ValueError):
    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail != "" else code)


def _observer_fail(code, detail=""):
    raise SourceEventObserverError(code, detail)


def _ast_span(node):
    values = (
        getattr(node, "lineno", None),
        getattr(node, "col_offset", None),
        getattr(node, "end_lineno", None),
        getattr(node, "end_col_offset", None),
    )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        _observer_fail("proof_source_event_target_invalid", "AST span")
    return {
        "line_start": values[0],
        "column_start": values[1],
        "line_end": values[2],
        "column_end": values[3],
    }


def _git_blob_id(raw):
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _code_identity(code):
    return (
        code.co_qualname,
        code.co_name,
        code.co_firstlineno,
    )


def _instruction_span(instruction):
    position = instruction.positions
    if position is None:
        return None
    values = (
        position.lineno,
        position.col_offset,
        position.end_lineno,
        position.end_col_offset,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return None
    return {
        "line_start": values[0],
        "column_start": values[1],
        "line_end": values[2],
        "column_end": values[3],
    }


def _opcode_contract(node):
    if isinstance(node, ast.Call):
        return frozenset({"CALL", "CALL_FUNCTION_EX"}), None
    if isinstance(node, ast.Name):
        if isinstance(node.ctx, ast.Load):
            names = {
                "LOAD_NAME", "LOAD_GLOBAL", "LOAD_FAST", "LOAD_DEREF",
                "LOAD_CLASSDEREF",
            }
        elif isinstance(node.ctx, ast.Store):
            names = {"STORE_NAME", "STORE_GLOBAL", "STORE_FAST", "STORE_DEREF"}
        elif isinstance(node.ctx, ast.Del):
            names = {"DELETE_NAME", "DELETE_GLOBAL", "DELETE_FAST", "DELETE_DEREF"}
        else:
            return None
        return frozenset(names), node.id
    if isinstance(node, ast.Attribute):
        if isinstance(node.ctx, ast.Load):
            names = {"LOAD_ATTR", "LOAD_METHOD"}
        elif isinstance(node.ctx, ast.Store):
            names = {"STORE_ATTR"}
        elif isinstance(node.ctx, ast.Del):
            names = {"DELETE_ATTR"}
        else:
            return None
        return frozenset(names), node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return frozenset({"LOAD_CONST"}), node.value
    return None


def _instruction_has_semantics(instruction, semantic_value):
    return semantic_value is None or instruction.argval == semantic_value


def _token_byte_span(source_lines, token):
    start_line, start_column = token.start
    end_line, end_column = token.end
    try:
        start_text = source_lines[start_line - 1]
        end_text = source_lines[end_line - 1]
    except IndexError:
        _observer_fail("proof_source_event_source_invalid", "token span")
    return {
        "line_start": start_line,
        "column_start": len(start_text[:start_column].encode("utf-8")),
        "line_end": end_line,
        "column_end": len(end_text[:end_column].encode("utf-8")),
    }


class ExactSourceEventObserver:
    def __init__(self, workspace, targets):
        root = pathlib.Path(workspace)
        try:
            resolved = root.resolve(strict=True)
        except OSError as exc:
            raise SourceEventObserverError(
                "proof_source_event_workspace_invalid", workspace
            ) from exc
        if not root.is_absolute() or root != resolved or not root.is_dir():
            _observer_fail("proof_source_event_workspace_invalid", workspace)
        if not isinstance(targets, list):
            _observer_fail("proof_source_event_target_invalid", "targets")
        self._workspace = root
        self._prepared = []
        self._events = {}
        self._phase = "bootstrap"
        self._attribution = None
        self._installed = False
        self._previous_sys_trace = None
        self._previous_thread_trace = None
        self._lock = threading.RLock()
        self._files = {}
        seen = set()
        for target in targets:
            prepared = self._prepare_target(target)
            witness_id = prepared["target"]["witness_id"]
            if witness_id in seen:
                _observer_fail("proof_source_event_target_invalid", witness_id)
            seen.add(witness_id)
            self._prepared.append(prepared)
        self._prepared_by_filename = {}
        for prepared in self._prepared:
            filename = str(prepared["file"]["path"])
            self._prepared_by_filename.setdefault(filename, []).append(prepared)

    def install(self):
        if self._installed:
            _observer_fail("proof_source_event_observer_state_invalid", "installed")
        self._previous_sys_trace = sys.gettrace()
        get_thread_trace = getattr(threading, "gettrace", None)
        self._previous_thread_trace = (
            get_thread_trace() if get_thread_trace is not None else None
        )
        sys.settrace(self._trace)
        threading.settrace(self._trace)
        self._installed = True

    def set_attribution(self, *, phase, attribution):
        if not isinstance(phase, str) or not isinstance(attribution, dict):
            _observer_fail("proof_source_event_attribution_invalid")
        with self._lock:
            self._phase = phase
            self._attribution = copy.deepcopy(attribution)

    def uninstall(self):
        if not self._installed:
            return
        sys.settrace(self._previous_sys_trace)
        threading.settrace(self._previous_thread_trace)
        self._installed = False

    def source_events(self):
        with self._lock:
            return copy.deepcopy(self._events)

    def _prepare_target(self, target):
        if not isinstance(target, dict) or set(target) != {
            "witness_id",
            "consumer_path",
            "caller_object_id",
            "span",
            "source_event_binding",
        }:
            _observer_fail("proof_source_event_target_invalid", "shape")
        witness_id = target["witness_id"]
        if not isinstance(witness_id, str) or not witness_id:
            _observer_fail("proof_source_event_target_invalid", "witness_id")
        relative = target["consumer_path"]
        if not isinstance(relative, str) or not relative:
            _observer_fail("proof_source_event_target_invalid", witness_id)
        pure = pathlib.PurePosixPath(relative)
        if (
            pure.is_absolute()
            or pure.as_posix() != relative
            or ".." in pure.parts
            or "." in pure.parts
        ):
            _observer_fail("proof_source_event_target_invalid", witness_id)
        logical = self._workspace.joinpath(*pure.parts)
        try:
            path = logical.resolve(strict=True)
            raw = logical.read_bytes()
        except OSError as exc:
            raise SourceEventObserverError(
                "proof_source_event_source_invalid", witness_id
            ) from exc
        if (
            logical.is_symlink()
            or not logical.is_file()
            or path != logical
            or not path.is_relative_to(self._workspace)
        ):
            _observer_fail("proof_source_event_source_invalid", witness_id)
        expected_blob = target["caller_object_id"]
        if (
            not isinstance(expected_blob, str)
            or _git_blob_id(raw) != expected_blob
        ):
            _observer_fail("proof_source_event_blob_mismatch", witness_id)
        span = target["span"]
        if not isinstance(span, dict) or set(span) != {
            "line_start",
            "column_start",
            "line_end",
            "column_end",
        }:
            _observer_fail("proof_source_event_target_invalid", witness_id)
        values = tuple(span[key] for key in (
            "line_start", "column_start", "line_end", "column_end"
        ))
        if (
            any(isinstance(value, bool) or not isinstance(value, int) for value in values)
            or values[0] < 1
            or values[1] < 0
            or values[2] < values[0]
            or values[3] < 0
            or (values[2] == values[0] and values[3] < values[1])
        ):
            _observer_fail("proof_source_event_target_invalid", witness_id)
        binding = target["source_event_binding"]
        if not isinstance(binding, dict) or set(binding) != {
            "event_kind", "phase", "attribution"
        }:
            _observer_fail("proof_source_event_target_invalid", witness_id)
        if not isinstance(binding["phase"], str) or not isinstance(
            binding["attribution"], dict
        ):
            _observer_fail("proof_source_event_target_invalid", witness_id)
        file_data = self._files.get(relative)
        if file_data is None:
            try:
                source = raw.decode("utf-8", "strict")
                tree = ast.parse(source, filename=str(path))
                root_code = compile(
                    source, str(path), "exec", dont_inherit=True, optimize=0
                )
            except (UnicodeError, SyntaxError, ValueError) as exc:
                raise SourceEventObserverError(
                    "proof_source_event_source_invalid", witness_id
                ) from exc
            codes = []
            pending = [root_code]
            while pending:
                code = pending.pop(0)
                codes.append(code)
                pending.extend(
                    value for value in code.co_consts
                    if isinstance(value, types.CodeType)
                )
            file_data = {
                "path": path,
                "raw": raw,
                "source": source,
                "source_lines": source.splitlines(keepends=True),
                "tokens": tuple(tokenize.generate_tokens(io.StringIO(source).readline)),
                "tree": tree,
                "codes": tuple(codes),
                "instructions": {
                    code: tuple(dis.get_instructions(code)) for code in codes
                },
            }
            self._files[relative] = file_data
        normalized = {
            "witness_id": witness_id,
            "consumer_path": relative,
            "caller_object_id": expected_blob,
            "span": copy.deepcopy(span),
            "source_event_binding": copy.deepcopy(binding),
        }
        event_kind = binding["event_kind"]
        if event_kind == "opcode_exact_span":
            match = self._prepare_opcode(normalized, file_data)
        elif event_kind == "import_alias_opcode":
            match = self._prepare_import(normalized, file_data)
        elif event_kind == "callable_entry":
            match = self._prepare_callable(normalized, file_data)
        else:
            _observer_fail("proof_source_event_kind_unsupported", witness_id)
        return {
            "target": normalized,
            "file": file_data,
            "match": match,
        }

    def _prepare_opcode(self, target, file_data):
        span = target["span"]
        nodes = []
        for node in ast.walk(file_data["tree"]):
            if not hasattr(node, "lineno"):
                continue
            if _ast_span(node) != span:
                continue
            contract = _opcode_contract(node)
            if contract is not None:
                nodes.append((node, contract))
        if len(nodes) != 1:
            _observer_fail(
                "proof_source_event_opcode_unsupported", target["witness_id"]
            )
        _, (allowed_opnames, semantic_value) = nodes[0]
        missing_position = False
        matches = []
        for code in file_data["codes"]:
            for instruction in file_data["instructions"][code]:
                if instruction.opname not in allowed_opnames or not _instruction_has_semantics(
                    instruction, semantic_value
                ):
                    continue
                instruction_span = _instruction_span(instruction)
                if instruction_span is None:
                    missing_position = True
                elif instruction_span == span:
                    matches.append((code, instruction))
        if missing_position:
            _observer_fail(
                "proof_source_event_position_missing", target["witness_id"]
            )
        if not matches:
            return None
        if len(matches) != 1:
            _observer_fail(
                "proof_source_event_position_ambiguous", target["witness_id"]
            )
        code, instruction = matches[0]
        return {
            "event_kind": "opcode_exact_span",
            "code_identity": _code_identity(code),
            "instruction_offset": instruction.offset,
            "payload": {
                "code_qualname": code.co_qualname,
                "code_firstlineno": code.co_firstlineno,
                "instruction_offset": instruction.offset,
                "opname": instruction.opname,
                "argrepr_sha256": "sha256:" + hashlib.sha256(
                    instruction.argrepr.encode("utf-8")
                ).hexdigest(),
            },
        }

    def _prepare_import(self, target, file_data):
        alias_span = target["span"]
        aliases = []
        for statement in ast.walk(file_data["tree"]):
            if not isinstance(statement, (ast.Import, ast.ImportFrom)):
                continue
            for ordinal, alias in enumerate(statement.names):
                if _ast_span(alias) == alias_span:
                    aliases.append((statement, ordinal, alias))
        if len(aliases) != 1:
            _observer_fail(
                "proof_source_event_import_mapping_ambiguous",
                target["witness_id"],
            )
        statement, alias_ordinal, alias = aliases[0]
        statement_span = _ast_span(statement)
        expected = []
        alias_instruction_indexes = []
        if isinstance(statement, ast.Import):
            for imported in statement.names:
                alias_instruction_indexes.append(len(expected))
                expected.append(("IMPORT_NAME", imported.name))
            module = alias.name
            name = None
            level = 0
        else:
            expected.append(("IMPORT_NAME", statement.module or ""))
            for imported in statement.names:
                alias_instruction_indexes.append(len(expected))
                if imported.name == "*":
                    expected.append(("IMPORT_STAR", None))
                else:
                    expected.append(("IMPORT_FROM", imported.name))
            module = statement.module
            name = alias.name
            level = statement.level
        mappings = []
        missing_position = False
        import_opnames = {"IMPORT_NAME", "IMPORT_FROM", "IMPORT_STAR"}
        for code in file_data["codes"]:
            statement_instructions = []
            for instruction in file_data["instructions"][code]:
                if instruction.opname not in import_opnames:
                    continue
                instruction_span = _instruction_span(instruction)
                if instruction_span is None:
                    missing_position = True
                elif instruction_span == statement_span:
                    statement_instructions.append(instruction)
            actual = [
                (instruction.opname, instruction.argval)
                for instruction in statement_instructions
            ]
            if actual == expected:
                mappings.append((code, statement_instructions))
        if missing_position:
            _observer_fail(
                "proof_source_event_position_missing", target["witness_id"]
            )
        if len(mappings) != 1:
            _observer_fail(
                "proof_source_event_import_mapping_ambiguous",
                target["witness_id"],
            )
        code, instructions = mappings[0]
        instruction = instructions[alias_instruction_indexes[alias_ordinal]]
        argval = "*" if instruction.opname == "IMPORT_STAR" else instruction.argval
        if not isinstance(argval, str):
            _observer_fail(
                "proof_source_event_import_mapping_ambiguous",
                target["witness_id"],
            )
        return {
            "event_kind": "import_alias_opcode",
            "code_identity": _code_identity(code),
            "instruction_offset": instruction.offset,
            "payload": {
                "code_qualname": code.co_qualname,
                "code_firstlineno": code.co_firstlineno,
                "statement_span": statement_span,
                "alias_ordinal": alias_ordinal,
                "module": module,
                "name": name,
                "asname": alias.asname,
                "level": level,
                "instruction_offset": instruction.offset,
                "opname": instruction.opname,
                "argval": argval,
            },
        }

    def _prepare_callable(self, target, file_data):
        span = target["span"]
        definitions = []
        tokens = file_data["tokens"]
        source_lines = file_data["source_lines"]
        for node in ast.walk(file_data["tree"]):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name_tokens = []
            for index, token in enumerate(tokens[:-1]):
                if token.type != tokenize.NAME or token.string != "def":
                    continue
                if token.start[0] != node.lineno:
                    continue
                following = tokens[index + 1]
                if following.type == tokenize.NAME and following.string == node.name:
                    name_tokens.append(following)
            if len(name_tokens) == 1 and _token_byte_span(
                source_lines, name_tokens[0]
            ) == span:
                definitions.append(node)
        if not definitions:
            return None
        if len(definitions) != 1:
            _observer_fail(
                "proof_source_event_callable_mapping_ambiguous",
                target["witness_id"],
            )
        definition = definitions[0]
        expected_first_line = min(
            [definition.lineno]
            + [decorator.lineno for decorator in definition.decorator_list]
        )
        codes = [
            code
            for code in file_data["codes"]
            if code.co_name == definition.name
            and code.co_firstlineno == expected_first_line
        ]
        if len(codes) != 1:
            _observer_fail(
                "proof_source_event_callable_mapping_ambiguous",
                target["witness_id"],
            )
        code = codes[0]
        return {
            "event_kind": "callable_entry",
            "code_identity": _code_identity(code),
            "payload": {
                "code_qualname": code.co_qualname,
                "code_name": code.co_name,
                "code_firstlineno": code.co_firstlineno,
                "definition_span": _ast_span(definition),
            },
        }

    def _attribution_matches(self, target):
        binding = target["source_event_binding"]
        with self._lock:
            if self._phase == "bootstrap" and self._attribution is None:
                attribution = binding["attribution"]
                return (
                    binding["phase"] == "bootstrap"
                    and attribution.get("attribution_kind") == "selector_module"
                    and attribution.get("pytest_module_path")
                    == target["consumer_path"]
                )
            return (
                self._phase == binding["phase"]
                and self._attribution == binding["attribution"]
            )

    def _record(self, prepared):
        match = prepared["match"]
        if match is None or not self._attribution_matches(prepared["target"]):
            return
        target = prepared["target"]
        binding = target["source_event_binding"]
        event = {
            "event_kind": binding["event_kind"],
            "phase": binding["phase"],
            "attribution": copy.deepcopy(binding["attribution"]),
            "consumer_path": target["consumer_path"],
            "caller_object_id": target["caller_object_id"],
            "span": copy.deepcopy(target["span"]),
            "hit_count": 1,
            match["event_kind"]: copy.deepcopy(match["payload"]),
        }
        witness_id = target["witness_id"]
        with self._lock:
            prior = self._events.get(witness_id)
            if prior is None:
                self._events[witness_id] = event
                return
            comparable = copy.deepcopy(prior)
            comparable["hit_count"] = 1
            if comparable != event:
                _observer_fail(
                    "proof_source_event_nondeterministic", witness_id
                )
            prior["hit_count"] += 1

    def _trace(self, frame, event, arg):
        prepared_rows = self._prepared_by_filename.get(frame.f_code.co_filename)
        if prepared_rows is None:
            return self._trace
        frame.f_trace_opcodes = True
        code_identity = _code_identity(frame.f_code)
        if event == "call":
            for prepared in prepared_rows:
                match = prepared["match"]
                if (
                    match is not None
                    and match["event_kind"] == "callable_entry"
                    and match["code_identity"] == code_identity
                ):
                    self._record(prepared)
        elif event == "opcode":
            for prepared in prepared_rows:
                match = prepared["match"]
                if (
                    match is not None
                    and match["event_kind"] in {
                        "opcode_exact_span", "import_alias_opcode"
                    }
                    and match["code_identity"] == code_identity
                    and match["instruction_offset"] == frame.f_lasti
                ):
                    self._record(prepared)
        return self._trace
'''


def _exact_source_event_observer_source() -> str:
    """Return the byte-identical source shared by every runtime observer lane."""

    return _EXACT_SOURCE_EVENT_OBSERVER


def _exact_source_event_observer_sha256() -> str:
    return _sha256(_EXACT_SOURCE_EVENT_OBSERVER.encode("utf-8"))


def _write_exact_source_event_observer(path: Path) -> str:
    artifact = _canonical_absolute(
        Path(path),
        code="proof_source_event_observer_artifact_invalid",
        must_exist=False,
    )
    parent = _canonical_absolute(
        artifact.parent,
        code="proof_source_event_observer_artifact_invalid",
        must_exist=True,
    )
    if artifact.parent != parent or not parent.is_dir() or os.path.lexists(artifact):
        raise BoundaryProofError(
            "proof_source_event_observer_artifact_invalid", str(artifact)
        )
    raw = _EXACT_SOURCE_EVENT_OBSERVER.encode("utf-8")
    try:
        with artifact.open("xb") as stream:
            stream.write(raw)
    except OSError as exc:
        raise BoundaryProofError(
            "proof_source_event_observer_artifact_invalid", str(artifact)
        ) from exc
    try:
        identity = artifact.lstat()
        observed = artifact.read_bytes()
    except OSError as exc:
        raise BoundaryProofError(
            "proof_source_event_observer_artifact_invalid", str(artifact)
        ) from exc
    if artifact.is_symlink() or not artifact.is_file() or identity.st_size != len(raw) or observed != raw:
        raise BoundaryProofError(
            "proof_source_event_observer_artifact_invalid", str(artifact)
        )
    return _sha256(observed)


_PYTEST_PLUGIN = r'''
import hashlib
import importlib
import json
import os
import pathlib
import sys

import pytest
import es_exact_source_event_observer as source_event_observer_module

config_path = pathlib.Path(os.environ["ES_BOUNDARY_CONFIG"])
report_path = pathlib.Path(os.environ["ES_BOUNDARY_REPORT"])
config = json.loads(config_path.read_text(encoding="utf-8"))
workspace = pathlib.Path(config["workspace"]).resolve(strict=True)
observer_origin = pathlib.Path(source_event_observer_module.__file__).resolve(strict=True)
observer_digest = "sha256:" + hashlib.sha256(observer_origin.read_bytes()).hexdigest()
if observer_digest != config["source_event_observer_sha256"]:
    raise RuntimeError("source-event observer digest mismatch")
forbidden_roots = tuple(pathlib.Path(value).resolve(strict=False) for value in config["forbidden_roots"])
project_prefixes = tuple(config["project_owned_module_prefixes"])
forbidden_prefixes = tuple(config["forbidden_module_prefixes"])
editable_prefix = config["editable_prefix"]

removed_hooks = set()
mapping_paths = []
for hook in (*sys.meta_path, *sys.path_hooks):
    module_name = getattr(hook, "__module__", "")
    if module_name.startswith(editable_prefix):
        removed_hooks.add(module_name)
        module = sys.modules.get(module_name)
        if module is None:
            module = importlib.import_module(module_name)
        mapping = getattr(module, "MAPPING", {})
        namespaces = getattr(module, "NAMESPACES", {})
        mapping_paths.extend(str(value) for value in mapping.values())
        for values in namespaces.values():
            mapping_paths.extend(str(value) for value in values)
if mapping_paths:
    forbidden_roots = (*forbidden_roots, pathlib.Path(os.path.commonpath(mapping_paths)).resolve(strict=False))
forbidden_roots = tuple(dict.fromkeys(forbidden_roots))
sys.meta_path[:] = [
    hook for hook in sys.meta_path
    if not getattr(hook, "__module__", "").startswith(editable_prefix)
]
sys.path_hooks[:] = [
    hook for hook in sys.path_hooks
    if not getattr(hook, "__module__", "").startswith(editable_prefix)
]
sys.path[:] = [value for value in sys.path if not str(value).startswith("__editable__.ptychopinn-")]
sys.path_importer_cache.clear()
for module_name in tuple(sys.modules):
    if module_name.startswith(editable_prefix):
        sys.modules.pop(module_name, None)

observer = source_event_observer_module.ExactSourceEventObserver(
    workspace=str(workspace),
    targets=config["source_event_targets"],
)
module_bindings = {}
for target in config["source_event_targets"]:
    binding = target["source_event_binding"]
    attribution = binding["attribution"]
    if attribution["attribution_kind"] == "selector_module":
        module_bindings.setdefault(attribution["pytest_module_path"], []).append(binding)
observer.install()


class BoundaryPlugin:
    def __init__(self):
        self.collected = []
        self.outcomes = {}

    def _set_node(self, phase, item):
        observer.set_attribution(
            phase=phase,
            attribution={
                "attribution_kind": "pytest_node",
                "pytest_node_id": item.nodeid,
            },
        )

    def pytest_collectstart(self, collector):
        raw_path = getattr(collector, "path", None)
        if raw_path is None:
            return
        path = pathlib.Path(str(raw_path)).resolve(strict=False)
        if not path.is_relative_to(workspace):
            return
        relative = path.relative_to(workspace).as_posix()
        bindings = module_bindings.get(relative, ())
        binding = next(
            (candidate for candidate in bindings if candidate["phase"] == "collection"),
            None,
        )
        if binding is not None:
            observer.set_attribution(
                phase="collection",
                attribution=binding["attribution"],
            )

    def pytest_collection_finish(self, session):
        self.collected = [item.nodeid for item in session.items]

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_setup(self, item):
        self._set_node("setup", item)
        yield

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_call(self, item):
        self._set_node("call", item)
        yield

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_teardown(self, item):
        self._set_node("teardown", item)
        yield

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            if report.passed:
                self.outcomes[report.nodeid] = "passed"
            elif report.failed:
                self.outcomes[report.nodeid] = "failed"
            elif report.skipped:
                self.outcomes[report.nodeid] = "skipped"
        elif report.when == "setup" and report.skipped:
            self.outcomes[report.nodeid] = "skipped"
        elif report.failed:
            self.outcomes[report.nodeid] = "errors"

    def pytest_sessionfinish(self, session, exitstatus):
        observer.set_attribution(phase="session_finish", attribution={})
        source_events = observer.source_events()
        observer.uninstall()
        rows = set()
        for name, module in tuple(sys.modules.items()):
            origins = []
            spec = getattr(module, "__spec__", None)
            origin = getattr(spec, "origin", None)
            if isinstance(origin, str):
                origins.append(origin)
            module_file = getattr(module, "__file__", None)
            if isinstance(module_file, str):
                origins.append(module_file)
            locations = getattr(spec, "submodule_search_locations", None)
            if locations is not None:
                origins.extend(str(value) for value in locations)
            for value in origins:
                path = pathlib.Path(value)
                if path.is_absolute():
                    rows.add((name, str(path.resolve(strict=False))))
        ordered = sorted(rows)
        forbidden_origins = []
        outside_origins = []
        projected = []
        for name, value in ordered:
            path = pathlib.Path(value)
            if path.is_relative_to(workspace):
                projected.append([name, value])
            if any(path.is_relative_to(root) for root in forbidden_roots):
                forbidden_origins.append([name, value])
            if (
                any(name == prefix or name.startswith(prefix + ".") for prefix in project_prefixes)
                and not path.is_relative_to(workspace)
            ):
                outside_origins.append([name, value])
        origins_by_module = {}
        for name, value in ordered:
            origins_by_module.setdefault(name, []).append(pathlib.Path(value))
        loaded_forbidden = sorted(
            name for name in sys.modules
            if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
            and (
                name not in origins_by_module
                or any(
                    not path.is_relative_to(workspace)
                    for path in origins_by_module[name]
                )
            )
        )
        outcome_counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        for node_id in self.collected:
            outcome_counts[self.outcomes.get(node_id, "errors")] += 1
        node_outcomes = [
            {
                "pytest_node_id": node_id,
                "outcome": self.outcomes.get(node_id, "errors"),
            }
            for node_id in self.collected
        ]
        payload = {
            "schema_version": "es_f1_boundary_pytest_observation.v1",
            "source_event_observer_sha256": observer_digest,
            "python_executable": str(pathlib.Path(sys.executable).resolve(strict=True)),
            "workspace": str(workspace),
            "selectors": config["selectors"],
            "pytest_node_ids": self.collected,
            "node_outcomes": node_outcomes,
            "exit_code": int(exitstatus),
            "outcomes": outcome_counts,
            "plugin_autoload_disabled": os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1",
            "removed_editable_hooks": sorted(removed_hooks),
            "forbidden_roots": [str(path) for path in forbidden_roots],
            "forbidden_module_prefixes": list(forbidden_prefixes),
            "project_owned_module_prefixes": list(project_prefixes),
            "loaded_forbidden_modules": loaded_forbidden,
            "forbidden_origin_rows": forbidden_origins,
            "outside_project_origin_rows": outside_origins,
            "projected_origin_rows": projected,
            "module_origin_rows": [list(row) for row in ordered],
            "source_events": source_events,
        }
        report_path.write_bytes(
            json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            + b"\n"
        )


plugin = BoundaryPlugin()


def pytest_configure(config):
    config.pluginmanager.register(plugin, "es-boundary-observer")
'''


def _project_prefixes_for_witnesses(
    witnesses: Sequence[WitnessContract],
) -> tuple[str, ...]:
    values = ["ptycho", "ptycho_torch", "conftest"]
    for witness in witnesses:
        first = PurePosixPath(witness.consumer_path).parts[0]
        if first.endswith(".py"):
            first = first[:-3]
        if first.isidentifier():
            values.append(first)
    return tuple(dict.fromkeys(values))


def _project_prefixes(contract: ProofContract) -> tuple[str, ...]:
    return _project_prefixes_for_witnesses(contract.witnesses)


def _parse_pair_rows(value: object, *, label: str) -> list[list[str]]:
    rows = _require_list(value, code="proof_pytest_report_invalid", label=label)
    result: list[list[str]] = []
    for row in rows:
        if (
            not isinstance(row, list)
            or len(row) != 2
            or not all(isinstance(item, str) for item in row)
        ):
            raise BoundaryProofError("proof_pytest_report_invalid", label)
        result.append([row[0], row[1]])
    return result


def _normalize_runtime_owned_temporary_origins(
    rows: Sequence[Sequence[str]],
) -> list[list[str]]:
    """Normalize only verified runtime-generated tempfile origin families."""

    normalized: list[list[str]] = []
    autograph_ordinal = 0
    for raw_name, raw_origin in rows:
        name = str(raw_name)
        origin = str(raw_origin)
        if (
            _AUTOGRAPH_GENERATED_MODULE_RE.fullmatch(name) is not None
            and origin == f"/tmp/{name}.py"
        ):
            autograph_ordinal += 1
            if autograph_ordinal > _NORMALIZED_AUTOGRAPH_ORDINAL_LIMIT:
                raise BoundaryProofError(
                    "proof_pytest_report_invalid",
                    "autograph temporary-origin cardinality",
                )
            normalized.append(
                [
                    _NORMALIZED_AUTOGRAPH_MODULE.format(
                        ordinal=autograph_ordinal
                    ),
                    _NORMALIZED_AUTOGRAPH_ORIGIN.format(
                        ordinal=autograph_ordinal
                    ),
                ]
            )
        elif (
            name == _TORCH_REMOTE_MODULE
            and _TORCH_REMOTE_TEMP_ORIGIN_RE.fullmatch(origin) is not None
        ):
            normalized.append([name, _NORMALIZED_TORCH_REMOTE_ORIGIN])
        else:
            normalized.append([name, origin])
    return normalized


def _source_event_targets(
    witnesses: Sequence[WitnessContract],
) -> list[dict[str, object]]:
    return [
        {
            "witness_id": witness.witness_id,
            "consumer_path": witness.consumer_path,
            "caller_object_id": witness.caller_object_id,
            "span": {
                "line_start": witness.start_line,
                "column_start": witness.column_start,
                "line_end": witness.end_line,
                "column_end": witness.column_end,
            },
            "source_event_binding": copy.deepcopy(witness.source_event_binding),
        }
        for witness in witnesses
    ]


def _run_pytest_child(
    *,
    python: Path,
    workspace: Path,
    report_path: Path,
    forbidden_roots: tuple[Path, ...],
    selectors: tuple[str, ...],
    source_event_targets: Sequence[Mapping[str, object]],
    project_owned_module_prefixes: tuple[str, ...],
    pytest_argv: tuple[str, ...],
    expected_node_ids: tuple[str, ...] | None,
    pytest_carrier: PytestCarrier,
    python_target: Path | None = None,
    collect_only: bool = False,
    reject_skipped: bool = False,
    allow_disclosed_nonpass: bool = False,
) -> dict[str, object]:
    if reject_skipped and allow_disclosed_nonpass:
        raise BoundaryProofError(
            "proof_pytest_report_invalid", "incompatible outcome policy"
        )
    if python_target is None:
        interpreter, verified_target = _verify_pinned_python(Path(python))
    else:
        interpreter = Path(python)
        verified_target = Path(python_target)
        if interpreter != PINNED_PYTHON or verified_target != PINNED_PYTHON_TARGET:
            raise BoundaryProofError("proof_python_identity_mismatch", str(interpreter))
    report = _canonical_absolute(
        Path(report_path), code="proof_report_path_invalid", must_exist=False
    )
    if report.is_relative_to(workspace) or os.path.lexists(report):
        raise BoundaryProofError("proof_report_path_invalid", str(report))
    bound_forbidden = tuple(
        _canonical_absolute(Path(path), code="proof_forbidden_root_invalid", must_exist=False)
        for path in forbidden_roots
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="es-boundary-plugin-", dir=report.parent) as raw_temp:
        temp = Path(raw_temp).resolve(strict=True)
        plugin_path = temp / "es_boundary_probe_plugin.py"
        observer_path = temp / f"{_GENERATED_SOURCE_EVENT_OBSERVER_MODULE}.py"
        config_path = temp / "config.json"
        plugin_path.write_text(_PYTEST_PLUGIN, encoding="utf-8", errors="strict")
        observer_digest = _write_exact_source_event_observer(observer_path)
        config_path.write_bytes(
            canonical_json_bytes(
                {
                    "workspace": str(workspace),
                    "selectors": list(selectors),
                    "source_event_targets": source_event_targets,
                    "source_event_observer_sha256": observer_digest,
                    "forbidden_roots": [str(path) for path in bound_forbidden],
                    "forbidden_module_prefixes": list(_FORBIDDEN_MODULE_PREFIXES),
                    "project_owned_module_prefixes": list(
                        project_owned_module_prefixes
                    ),
                    "editable_prefix": _EDITABLE_PREFIX,
                }
            )
        )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONPYCACHEPREFIX", None)
        env.update(
            {
                "PYTHONPATH": str(temp),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTEST_PLUGINS": _GENERATED_PYTEST_PLUGIN_MODULE,
                "XDG_CACHE_HOME": str(temp / "xdg-cache"),
                "MPLCONFIGDIR": str(temp / "mpl-cache"),
                "ES_BOUNDARY_CONFIG": str(config_path),
                "ES_BOUNDARY_REPORT": str(report),
            }
        )
        argv = (
            (*pytest_argv[:3], "--collect-only", *pytest_argv[3:])
            if collect_only
            else pytest_argv
        )
        completed = _run_private_tmp_child(
            pytest_carrier,
            argv,
            cwd=workspace,
            env=env,
            preserved_paths=(workspace, report.parent),
        )
        try:
            raw = report.read_bytes()
            payload = json.loads(
                raw.decode("utf-8", "strict"),
                object_pairs_hook=_strict_object,
                parse_float=_reject_float,
                parse_constant=_reject_constant,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BoundaryProofError(
                "proof_pytest_report_invalid",
                {
                    "stdout": completed.stdout[-2000:].decode("utf-8", "replace"),
                    "stderr": completed.stderr[-2000:].decode("utf-8", "replace"),
                },
            ) from exc
        if not isinstance(payload, dict) or canonical_json_bytes(payload) != raw:
            raise BoundaryProofError("proof_pytest_report_invalid", str(report))
        if payload.get("source_event_observer_sha256") != observer_digest:
            raise BoundaryProofError(
                "proof_source_event_observer_digest_mismatch", "pytest"
            )
        module_origin_rows = _parse_pair_rows(
            payload.get("module_origin_rows"), label="module"
        )
        expected_plugin_row = [
            _GENERATED_PYTEST_PLUGIN_MODULE,
            str(plugin_path.resolve(strict=True)),
        ]
        plugin_rows = [
            row
            for row in module_origin_rows
            if row[0] == _GENERATED_PYTEST_PLUGIN_MODULE
        ]
        if plugin_rows != [expected_plugin_row]:
            raise BoundaryProofError(
                "proof_pytest_plugin_identity_invalid", plugin_rows
            )
        expected_observer_row = [
            _GENERATED_SOURCE_EVENT_OBSERVER_MODULE,
            str(observer_path.resolve(strict=True)),
        ]
        observer_rows = [
            row
            for row in module_origin_rows
            if row[0] == _GENERATED_SOURCE_EVENT_OBSERVER_MODULE
        ]
        if observer_rows != [expected_observer_row]:
            raise BoundaryProofError(
                "proof_source_event_observer_digest_mismatch", observer_rows
            )
        payload["module_origin_rows"] = _normalize_runtime_owned_temporary_origins(
            [
                [
                    name,
                    (
                        _GENERATED_PYTEST_PLUGIN_ORIGIN
                        if [name, value] == expected_plugin_row
                        else _GENERATED_SOURCE_EVENT_OBSERVER_ORIGIN
                        if [name, value] == expected_observer_row
                        else value
                    ),
                ]
                for name, value in module_origin_rows
            ]
        )
        raw = canonical_json_bytes(payload)
        try:
            report.write_bytes(raw)
        except OSError as exc:
            raise BoundaryProofError("proof_pytest_report_invalid", str(report)) from exc
    required = {
        "schema_version",
        "source_event_observer_sha256",
        "python_executable",
        "workspace",
        "selectors",
        "pytest_node_ids",
        "node_outcomes",
        "exit_code",
        "outcomes",
        "plugin_autoload_disabled",
        "removed_editable_hooks",
        "forbidden_roots",
        "forbidden_module_prefixes",
        "project_owned_module_prefixes",
        "loaded_forbidden_modules",
        "forbidden_origin_rows",
        "outside_project_origin_rows",
        "projected_origin_rows",
        "module_origin_rows",
        "source_events",
    }
    if set(payload) != required or payload["schema_version"] != "es_f1_boundary_pytest_observation.v1":
        raise BoundaryProofError("proof_pytest_report_invalid", "shape")
    if completed.returncode != payload["exit_code"]:
        raise BoundaryProofError("proof_pytest_report_invalid", "exit")
    if payload["python_executable"] != str(verified_target):
        raise BoundaryProofError("proof_python_identity_mismatch", "pytest report")
    reported_selectors = _string_list(
        payload["selectors"],
        code="proof_pytest_report_invalid",
        label="selectors",
    )
    if reported_selectors != selectors or payload["workspace"] != str(workspace):
        raise BoundaryProofError("proof_pytest_report_invalid", "execution echo")
    node_ids = _string_list(
        payload["pytest_node_ids"], code="proof_pytest_report_invalid", label="pytest_node_ids"
    )
    if len(set(node_ids)) != len(node_ids):
        raise BoundaryProofError("proof_pytest_report_invalid", "duplicate node")
    if not collect_only and expected_node_ids is not None:
        expected_nodes = expected_node_ids
        if set(node_ids) != set(expected_nodes):
            unknown = sorted(set(node_ids) - set(expected_nodes))
            missing = sorted(set(expected_nodes) - set(node_ids))
            raise BoundaryProofError(
                "proof_pytest_node_unknown" if unknown else "proof_pytest_node_missing",
                unknown or missing,
            )
        if node_ids != expected_nodes:
            raise BoundaryProofError("proof_pytest_node_reordered")
    outcomes = _require_exact_keys(
        payload["outcomes"],
        {"passed", "failed", "skipped", "errors"},
        code="proof_pytest_report_invalid",
        label="outcomes",
    )
    parsed_outcomes = {
        key: _require_int(
            outcomes[key], code="proof_pytest_report_invalid", label=f"outcomes.{key}"
        )
        for key in ("errors", "failed", "passed", "skipped")
    }
    raw_node_outcomes = _require_list(
        payload["node_outcomes"],
        code="proof_pytest_report_invalid",
        label="node_outcomes",
    )
    node_outcomes: list[dict[str, str]] = []
    for index, raw_row in enumerate(raw_node_outcomes):
        row = _require_exact_keys(
            raw_row,
            {"pytest_node_id", "outcome"},
            code="proof_pytest_report_invalid",
            label=f"node_outcomes[{index}]",
        )
        node_id = _require_string(
            row["pytest_node_id"],
            code="proof_pytest_report_invalid",
            label=f"node_outcomes[{index}].pytest_node_id",
        )
        outcome = _require_string(
            row["outcome"],
            code="proof_pytest_report_invalid",
            label=f"node_outcomes[{index}].outcome",
        )
        if outcome not in {"passed", "failed", "skipped", "errors"}:
            raise BoundaryProofError(
                "proof_pytest_report_invalid", f"node_outcomes[{index}].outcome"
            )
        node_outcomes.append({"pytest_node_id": node_id, "outcome": outcome})
    if [row["pytest_node_id"] for row in node_outcomes] != list(node_ids):
        raise BoundaryProofError("proof_pytest_report_invalid", "node outcome order")
    derived_outcomes = {"errors": 0, "failed": 0, "passed": 0, "skipped": 0}
    for row in node_outcomes:
        derived_outcomes[row["outcome"]] += 1
    if (
        sum(parsed_outcomes.values()) != len(node_ids)
        or derived_outcomes != parsed_outcomes
    ):
        raise BoundaryProofError("proof_pytest_report_invalid", "outcome total")
    disclosed_nonpass_invalid = allow_disclosed_nonpass and (
        collect_only or completed.returncode not in {0, 1} or parsed_outcomes["errors"]
    )
    strict_outcome_invalid = not allow_disclosed_nonpass and (
        completed.returncode != 0
        or (
            not collect_only
            and (
                parsed_outcomes["failed"]
                or parsed_outcomes["errors"]
                or (reject_skipped and parsed_outcomes["skipped"])
            )
        )
    )
    if disclosed_nonpass_invalid or strict_outcome_invalid:
        raise BoundaryProofError(
            "proof_pytest_failed",
            {
                "returncode": completed.returncode,
                "outcomes": parsed_outcomes,
                "stdout": completed.stdout[-2000:].decode("utf-8", "replace"),
                "stderr": completed.stderr[-2000:].decode("utf-8", "replace"),
            },
        )
    forbidden_origins = _parse_pair_rows(payload["forbidden_origin_rows"], label="forbidden")
    outside_origins = _parse_pair_rows(
        payload["outside_project_origin_rows"], label="outside"
    )
    projected_origins = _parse_pair_rows(payload["projected_origin_rows"], label="projected")
    module_origins = _parse_pair_rows(payload["module_origin_rows"], label="module")
    loaded = _string_list(
        payload["loaded_forbidden_modules"],
        code="proof_pytest_report_invalid",
        label="loaded_forbidden_modules",
        nonempty=False,
    )
    if payload["plugin_autoload_disabled"] is not True:
        raise BoundaryProofError("proof_origin_isolation_failed", "plugin autoload")
    cache_artifacts = sorted(
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.name in {"__pycache__", ".pytest_cache"}
        or path.suffix in {".pyc", ".pyo"}
    )
    if loaded or forbidden_origins or outside_origins or cache_artifacts:
        raise BoundaryProofError(
            "proof_origin_isolation_failed",
            {
                "loaded": loaded,
                "forbidden": forbidden_origins,
                "outside": outside_origins,
                "cache": cache_artifacts,
            },
        )
    source_events_raw = _require_mapping(
        payload["source_events"],
        code="proof_pytest_report_invalid",
        label="source_events",
    )
    source_events: dict[str, object] = {}
    for raw_witness_id, raw_event in source_events_raw.items():
        witness_id = _require_identifier(
            raw_witness_id,
            code="proof_pytest_report_invalid",
            label="source_event.witness_id",
        )
        event = _require_mapping(
            raw_event,
            code="proof_pytest_report_invalid",
            label=f"source_event.{witness_id}",
        )
        _validate_json_value(event, label=f"source_event.{witness_id}")
        source_events[witness_id] = copy.deepcopy(event)
    expected_source_event_ids = {
        str(target["witness_id"]) for target in source_event_targets
    }
    unknown_source_event_ids = set(source_events) - expected_source_event_ids
    if unknown_source_event_ids:
        raise BoundaryProofError(
            "proof_pytest_report_invalid", sorted(unknown_source_event_ids)
        )
    result: dict[str, object] = {
        "raw_sha256": _sha256(raw),
        "argv": list(argv),
        "python_executable": _require_string(
            payload["python_executable"], code="proof_pytest_report_invalid", label="python"
        ),
        "node_ids": list(node_ids),
        "node_outcomes": node_outcomes,
        "exit_code": completed.returncode,
        "outcomes": parsed_outcomes,
        "source_events": source_events,
        "origin": {
            "report_sha256": _sha256(raw),
            "python_executable": payload["python_executable"],
            "pytest_carrier": pytest_carrier.as_record(),
            "plugin_autoload_disabled": True,
            "removed_editable_hooks": list(
                _string_list(
                    payload["removed_editable_hooks"],
                    code="proof_pytest_report_invalid",
                    label="removed_editable_hooks",
                    nonempty=False,
                )
            ),
            "forbidden_roots": list(
                _string_list(
                    payload["forbidden_roots"],
                    code="proof_pytest_report_invalid",
                    label="forbidden_roots",
                    nonempty=False,
                )
            ),
            "forbidden_module_prefixes": list(
                _string_list(
                    payload["forbidden_module_prefixes"],
                    code="proof_pytest_report_invalid",
                    label="forbidden_module_prefixes",
                    nonempty=False,
                )
            ),
            "project_owned_module_prefixes": list(
                _string_list(
                    payload["project_owned_module_prefixes"],
                    code="proof_pytest_report_invalid",
                    label="project_owned_module_prefixes",
                )
            ),
            "loaded_forbidden_modules": list(loaded),
            "forbidden_origin_rows": forbidden_origins,
            "outside_project_origin_rows": outside_origins,
            "projected_origin_rows": projected_origins,
            "module_origin_rows": module_origins,
            "cache_artifacts": cache_artifacts,
        },
    }
    result["pytest_carrier"] = pytest_carrier.as_record()
    return result


def _run_pytest_observation(
    contract: ProofContract,
    *,
    python: Path,
    workspace: Path,
    report_path: Path,
    forbidden_roots: tuple[Path, ...],
    pytest_carrier: PytestCarrier,
    python_target: Path | None = None,
    collect_only: bool = False,
) -> dict[str, object]:
    """Run only the frozen provider-visible pytest lane."""

    selectors = tuple(
        selector.pytest_module_path for selector in contract.provider_selectors
    )
    assert all(selector is not None for selector in selectors)
    provider_selectors = tuple(str(selector) for selector in selectors)
    witnesses = tuple(
        witness
        for witness in contract.witnesses
        if witness.witness_kind == "pytest_runtime"
    )
    expected_nodes = tuple(
        node
        for selector in contract.provider_selectors
        for node in selector.pytest_node_ids
    )
    return _run_pytest_child(
        python=python,
        workspace=workspace,
        report_path=report_path,
        forbidden_roots=forbidden_roots,
        selectors=provider_selectors,
        source_event_targets=_source_event_targets(witnesses),
        project_owned_module_prefixes=_project_prefixes_for_witnesses(witnesses),
        pytest_argv=(
            str(python),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *provider_selectors,
        ),
        expected_node_ids=expected_nodes,
        pytest_carrier=pytest_carrier,
        python_target=python_target,
        collect_only=collect_only,
    )


def _controller_pytest_modules(selector: SelectorContract) -> tuple[str, ...]:
    prefix = (
        str(PINNED_PYTHON),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
    )
    if selector.execution_kind != "pytest_aggregate" or selector.argv[:6] != prefix:
        raise BoundaryProofError("proof_controller_argv_invalid", selector.selector_id)
    raw_modules = selector.argv[6:]
    if not raw_modules:
        raise BoundaryProofError("proof_controller_argv_invalid", selector.selector_id)
    modules = tuple(
        _safe_relative_path(
            value,
            code="proof_controller_argv_invalid",
            label=selector.selector_id,
        )
        for value in raw_modules
    )
    if len(set(modules)) != len(modules) or any(
        not module.endswith(".py") for module in modules
    ):
        raise BoundaryProofError("proof_controller_argv_invalid", selector.selector_id)
    bound_paths = {
        path for path, _ in selector.input_bindings if not PurePosixPath(path).is_absolute()
    }
    if not set(modules).issubset(bound_paths):
        raise BoundaryProofError(
            "proof_controller_module_binding_mismatch", selector.selector_id
        )
    return modules


def _run_controller_pytest_observation(
    contract: ProofContract,
    selector: SelectorContract,
    *,
    python: Path,
    workspace: Path,
    report_path: Path,
    forbidden_roots: tuple[Path, ...],
    pytest_carrier: PytestCarrier,
    python_target: Path,
) -> dict[str, object]:
    modules = _controller_pytest_modules(selector)
    witnesses = tuple(
        witness
        for witness in contract.witnesses
        if witness.selector_id == selector.selector_id
        and witness.witness_kind == "controller_pytest_runtime"
    )
    if tuple(witness.witness_id for witness in witnesses) != tuple(
        selector.coverage_witness_ids
    ):
        raise BoundaryProofError(
            "proof_witness_backpointer_mismatch", selector.selector_id
        )
    report = _run_pytest_child(
        python=python,
        workspace=workspace,
        report_path=report_path,
        forbidden_roots=forbidden_roots,
        selectors=modules,
        source_event_targets=_source_event_targets(witnesses),
        project_owned_module_prefixes=_project_prefixes_for_witnesses(witnesses),
        pytest_argv=selector.argv,
        expected_node_ids=None,
        pytest_carrier=pytest_carrier,
        python_target=python_target,
        allow_disclosed_nonpass=True,
    )
    _validate_controller_pytest_nodes(
        selector.selector_id, modules, report["node_ids"]
    )
    return report


def _validate_controller_pytest_nodes(
    selector_id: str,
    modules: tuple[str, ...],
    value: object,
) -> tuple[str, ...]:
    node_ids = _string_list(
        value,
        code="proof_pytest_report_invalid",
        label=f"{selector_id}.pytest_node_ids",
    )
    owners: list[int] = []
    for node_id in node_ids:
        matching = [
            index
            for index, module in enumerate(modules)
            if node_id.startswith(module + "::")
        ]
        if len(matching) != 1:
            raise BoundaryProofError("proof_pytest_node_unknown", node_id)
        owners.append(matching[0])
    if not node_ids or set(owners) != set(range(len(modules))):
        raise BoundaryProofError("proof_pytest_node_missing", selector_id)
    if owners != sorted(owners):
        raise BoundaryProofError("proof_pytest_node_reordered", selector_id)
    return node_ids


def _collect_controller_pytest_nodes(
    selector: SelectorContract,
    *,
    python: Path,
    workspace: Path,
    report_path: Path,
    forbidden_roots: tuple[Path, ...],
    pytest_carrier: PytestCarrier,
    python_target: Path,
) -> tuple[str, ...]:
    modules = _controller_pytest_modules(selector)
    report = _run_pytest_child(
        python=python,
        workspace=workspace,
        report_path=report_path,
        forbidden_roots=forbidden_roots,
        selectors=modules,
        source_event_targets=(),
        project_owned_module_prefixes=("ptycho", "ptycho_torch", "conftest"),
        pytest_argv=selector.argv,
        expected_node_ids=None,
        pytest_carrier=pytest_carrier,
        python_target=python_target,
        collect_only=True,
    )
    return _validate_controller_pytest_nodes(
        selector.selector_id, modules, report["node_ids"]
    )


def _controller_selector_result(
    selector: SelectorContract,
    report: Mapping[str, object],
) -> dict[str, object]:
    source_events = report["source_events"]
    assert isinstance(source_events, Mapping)
    trace_rows: list[dict[str, object]] = []
    witness_node_outcomes: list[dict[str, str]] = []
    for witness_id in selector.coverage_witness_ids:
        source_event = source_events.get(witness_id)
        if source_event is None:
            raise BoundaryProofError("proof_witness_unobserved", witness_id)
        source_event_row = _require_mapping(
            source_event,
            code="proof_witness_unobserved",
            label=witness_id,
        )
        attribution = _require_mapping(
            source_event_row.get("attribution"),
            code="proof_witness_unobserved",
            label=f"{witness_id}.attribution",
        )
        trace_row: dict[str, object] = {
            "witness_id": witness_id,
            "source_event": copy.deepcopy(source_event),
        }
        if attribution.get("attribution_kind") == "pytest_node":
            node_id = _require_string(
                attribution.get("pytest_node_id"),
                code="proof_witness_unobserved",
                label=f"{witness_id}.pytest_node_id",
            )
            node_outcome = _pytest_node_outcome(report, node_id)
            if node_outcome != "passed":
                raise BoundaryProofError("proof_witness_unobserved", witness_id)
            outcome_row = {
                "witness_id": witness_id,
                "pytest_node_id": node_id,
                "outcome": node_outcome,
            }
            witness_node_outcomes.append(outcome_row)
            trace_row["node_outcome"] = copy.deepcopy(outcome_row)
        elif attribution.get("attribution_kind") != "selector_module":
            raise BoundaryProofError("proof_witness_unobserved", witness_id)
        trace_rows.append(trace_row)
    node_ids = report["node_ids"]
    outcomes = report["outcomes"]
    assert isinstance(node_ids, list) and isinstance(outcomes, Mapping)
    return {
        "selector_id": selector.selector_id,
        "execution_kind": "pytest_aggregate",
        "argv": list(selector.argv),
        "collected_node_ids": list(node_ids),
        "collected_node_sha256": _sha256(canonical_json_bytes(node_ids)),
        "collection_total": len(node_ids),
        "outcomes": copy.deepcopy(dict(outcomes)),
        "origin_isolation": copy.deepcopy(report["origin"]),
        "trace_sha256": _sha256(canonical_json_bytes(trace_rows)),
        "coverage_witness_ids": list(selector.coverage_witness_ids),
        "coverage_witness_node_outcomes": witness_node_outcomes,
    }


def _run_controller_pytest_observations(
    contract: ProofContract,
    *,
    python: Path,
    workspace: Path,
    report_directory: Path,
    forbidden_roots: tuple[Path, ...],
    pytest_carrier: PytestCarrier,
    python_target: Path,
) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
    reports: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []
    for selector in contract.controller_selectors:
        if selector.execution_kind != "pytest_aggregate":
            continue
        report = _run_controller_pytest_observation(
            contract,
            selector,
            python=python,
            workspace=workspace,
            report_path=(report_directory / f"{selector.ordinal:04d}.json").resolve(),
            forbidden_roots=forbidden_roots,
            pytest_carrier=pytest_carrier,
            python_target=python_target,
        )
        reports[selector.selector_id] = report
        results.append(_controller_selector_result(selector, report))
    return reports, results


def _static_observation(witness: WitnessContract, workspace: Path) -> tuple[object, str | None]:
    assert witness.query is not None
    query_kind = witness.query["query_kind"]
    path = _workspace_path(workspace, witness.consumer_path, may_be_absent=True)
    exists = os.path.lexists(path)
    if query_kind == "path_absent":
        if exists and (path.is_symlink() or not path.is_file()):
            raise BoundaryProofError("proof_target_path_invalid", witness.consumer_path)
        return {"path_absent": not exists}, _target_blob(workspace, witness.consumer_path)
    if not exists or path.is_symlink() or not path.is_file():
        raise BoundaryProofError("proof_witness_unobserved", witness.witness_id)
    try:
        source = path.read_text(encoding="utf-8", errors="strict")
        tree = ast.parse(source, filename=witness.consumer_path)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise BoundaryProofError("proof_static_parse_failed", witness.witness_id) from exc
    forbidden_names = set(_string_list(
        witness.query["forbidden_names"], code="proof_static_query_invalid", label="names", nonempty=False
    ))
    forbidden_attributes = set(_string_list(
        witness.query["forbidden_attributes"], code="proof_static_query_invalid", label="attrs", nonempty=False
    ))
    forbidden_strings = set(_string_list(
        witness.query["forbidden_string_literals"], code="proof_static_query_invalid", label="strings", nonempty=False
    ))
    matches: list[dict[str, object]] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        column = getattr(node, "col_offset", None)
        end_line = getattr(node, "end_lineno", line)
        end_column = getattr(node, "end_col_offset", column)
        if (
            not isinstance(line, int)
            or not isinstance(column, int)
            or not isinstance(end_line, int)
            or not isinstance(end_column, int)
            or (line, column) < (witness.start_line, witness.column_start)
            or (end_line, end_column) > (witness.end_line, witness.column_end)
        ):
            continue
        value: str | None = None
        kind: str | None = None
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            kind, value = "name", node.id
        elif isinstance(node, ast.Attribute) and node.attr in forbidden_attributes:
            kind, value = "attribute", node.attr
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in forbidden_strings:
            kind, value = "string_literal", node.value
        if kind is not None and value is not None:
            matches.append(
                {
                    "column": column,
                    "kind": kind,
                    "line": line,
                    "value": value,
                }
            )
    matches.sort(key=lambda row: (row["line"], row["column"], row["kind"], row["value"]))
    return {"matches": matches}, _target_blob(workspace, witness.consumer_path)


_RUNTIME_PROBE_CHILD = r'''
import contextlib
import hashlib
import importlib
import io
import json
import os
import pathlib
import sys

import es_exact_source_event_observer as source_event_observer_module

config_path = pathlib.Path(os.environ["ES_BOUNDARY_RUNTIME_CONFIG"])
result_path = pathlib.Path(os.environ["ES_BOUNDARY_RUNTIME_RESULT"])
config = json.loads(config_path.read_text(encoding="utf-8"))
workspace = pathlib.Path(config["workspace"]).resolve(strict=True)
observer_origin = pathlib.Path(source_event_observer_module.__file__).resolve(strict=True)
observer_digest = "sha256:" + hashlib.sha256(observer_origin.read_bytes()).hexdigest()
if observer_digest != config["source_event_observer_sha256"]:
    raise RuntimeError("source-event observer digest mismatch")
forbidden_roots = tuple(
    pathlib.Path(value).resolve(strict=False) for value in config["forbidden_roots"]
)
project_prefixes = tuple(config["project_owned_module_prefixes"])
forbidden_prefixes = tuple(config["forbidden_module_prefixes"])
editable_prefix = config["editable_prefix"]

removed_hooks = set()
mapping_paths = []
for hook in (*sys.meta_path, *sys.path_hooks):
    module_name = getattr(hook, "__module__", "")
    if module_name.startswith(editable_prefix):
        removed_hooks.add(module_name)
        module = sys.modules.get(module_name)
        if module is None:
            module = importlib.import_module(module_name)
        mapping = getattr(module, "MAPPING", {})
        namespaces = getattr(module, "NAMESPACES", {})
        mapping_paths.extend(str(value) for value in mapping.values())
        for values in namespaces.values():
            mapping_paths.extend(str(value) for value in values)
if mapping_paths:
    forbidden_roots = (
        *forbidden_roots,
        pathlib.Path(os.path.commonpath(mapping_paths)).resolve(strict=False),
    )
forbidden_roots = tuple(dict.fromkeys(forbidden_roots))
sys.meta_path[:] = [
    hook for hook in sys.meta_path
    if not getattr(hook, "__module__", "").startswith(editable_prefix)
]
sys.path_hooks[:] = [
    hook for hook in sys.path_hooks
    if not getattr(hook, "__module__", "").startswith(editable_prefix)
]
sys.path[:] = [
    value for value in sys.path
    if not str(value).startswith("__editable__.ptychopinn-")
]
sys.path_importer_cache.clear()
for module_name in tuple(sys.modules):
    if module_name.startswith(editable_prefix):
        sys.modules.pop(module_name, None)

observer = source_event_observer_module.ExactSourceEventObserver(
    workspace=str(workspace),
    targets=[config["source_event_target"]],
)
binding = config["source_event_target"]["source_event_binding"]
sys.path.insert(0, str(workspace))
stdout = io.StringIO()
stderr = io.StringIO()
action_outcome = None
module_origin = None
observer.install()
observer.set_attribution(
    phase=binding["phase"],
    attribution=binding["attribution"],
)
try:
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        module = importlib.import_module(config["probe"]["module"])
        origin = getattr(getattr(module, "__spec__", None), "origin", None)
        if isinstance(origin, str):
            module_origin = str(pathlib.Path(origin).resolve(strict=False))
        if config["probe"]["action"] == "call":
            target = module
            for part in config["probe"]["callable"].split("."):
                target = getattr(target, part)
            target(*config["probe"]["args"], **config["probe"]["kwargs"])
        action_outcome = {"status": "returned"}
except BaseException as exc:
    exception_type = type(exc)
    action_outcome = {
        "exception_type": f"{exception_type.__module__}.{exception_type.__qualname__}",
        "status": "raised",
    }
finally:
    source_events = observer.source_events()
    observer.uninstall()

origin_rows = set()
for name, module in tuple(sys.modules.items()):
    origins = []
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None)
    if isinstance(origin, str):
        origins.append(origin)
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str):
        origins.append(module_file)
    locations = getattr(spec, "submodule_search_locations", None)
    if locations is not None:
        origins.extend(str(value) for value in locations)
    for value in origins:
        path = pathlib.Path(value)
        if path.is_absolute():
            origin_rows.add((name, str(path.resolve(strict=False))))
ordered_origins = sorted(origin_rows)
forbidden_origins = []
outside_origins = []
projected_origins = []
for name, value in ordered_origins:
    path = pathlib.Path(value)
    if path.is_relative_to(workspace):
        projected_origins.append([name, value])
    if any(path.is_relative_to(root) for root in forbidden_roots):
        forbidden_origins.append([name, value])
    if (
        any(name == prefix or name.startswith(prefix + ".") for prefix in project_prefixes)
        and not path.is_relative_to(workspace)
    ):
        outside_origins.append([name, value])
origins_by_module = {}
for name, value in ordered_origins:
    origins_by_module.setdefault(name, []).append(pathlib.Path(value))
loaded_forbidden = sorted(
    name for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
    and (
        name not in origins_by_module
        or any(
            not path.is_relative_to(workspace)
            for path in origins_by_module[name]
        )
    )
)
cache_artifacts = sorted(
    path.relative_to(workspace).as_posix()
    for path in workspace.rglob("*")
    if path.name in {"__pycache__", ".pytest_cache"}
    or path.suffix in {".pyc", ".pyo"}
)
payload = {
    "action_outcome": action_outcome,
    "source_events": source_events,
    "source_event_observer_sha256": observer_digest,
    "python_executable": str(pathlib.Path(sys.executable).resolve(strict=True)),
    "workspace": str(workspace),
    "module_origin": module_origin,
    "removed_editable_hooks": sorted(removed_hooks),
    "forbidden_roots": [str(path) for path in forbidden_roots],
    "forbidden_module_prefixes": list(forbidden_prefixes),
    "project_owned_module_prefixes": list(project_prefixes),
    "loaded_forbidden_modules": loaded_forbidden,
    "forbidden_origin_rows": forbidden_origins,
    "outside_project_origin_rows": outside_origins,
    "projected_origin_rows": projected_origins,
    "module_origin_rows": [list(row) for row in ordered_origins],
    "cache_artifacts": cache_artifacts,
    "stderr_sha256": "sha256:" + hashlib.sha256(stderr.getvalue().encode("utf-8")).hexdigest(),
    "stdout_sha256": "sha256:" + hashlib.sha256(stdout.getvalue().encode("utf-8")).hexdigest(),
}
result_path.write_bytes(
    json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
)
'''


def _runtime_observation(
    witness: WitnessContract,
    *,
    python: Path,
    workspace: Path,
    forbidden_roots: tuple[Path, ...],
    project_owned_module_prefixes: tuple[str, ...],
    python_target: Path | None = None,
) -> tuple[object, str]:
    assert witness.probe is not None
    if python_target is None:
        interpreter, verified_target = _verify_pinned_python(Path(python))
    else:
        interpreter = Path(python)
        verified_target = Path(python_target)
        if interpreter != PINNED_PYTHON or verified_target != PINNED_PYTHON_TARGET:
            raise BoundaryProofError("proof_python_identity_mismatch", str(interpreter))
    target = _workspace_path(workspace, witness.consumer_path, may_be_absent=False)
    if target.is_symlink() or not target.is_file():
        raise BoundaryProofError("proof_witness_unobserved", witness.witness_id)
    bound_forbidden = tuple(
        _canonical_absolute(
            Path(path),
            code="proof_forbidden_root_invalid",
            must_exist=False,
        )
        for path in forbidden_roots
    )
    if witness.source_event_binding is None:
        raise BoundaryProofError("proof_witness_unobserved", witness.witness_id)
    source_event_target = {
        "witness_id": witness.witness_id,
        "consumer_path": witness.consumer_path,
        "caller_object_id": witness.caller_object_id,
        "span": {
            "line_start": witness.start_line,
            "column_start": witness.column_start,
            "line_end": witness.end_line,
            "column_end": witness.column_end,
        },
        "source_event_binding": copy.deepcopy(witness.source_event_binding),
    }
    with tempfile.TemporaryDirectory(prefix="es-boundary-runtime-") as raw_temp:
        temp = Path(raw_temp).resolve(strict=True)
        config_path = temp / "config.json"
        result_path = temp / "result.json"
        observer_path = temp / f"{_GENERATED_SOURCE_EVENT_OBSERVER_MODULE}.py"
        observer_digest = _write_exact_source_event_observer(observer_path)
        config_path.write_bytes(
            canonical_json_bytes(
                {
                    "workspace": str(workspace),
                    "probe": witness.probe,
                    "source_event_target": source_event_target,
                    "source_event_observer_sha256": observer_digest,
                    "forbidden_roots": [str(path) for path in bound_forbidden],
                    "forbidden_module_prefixes": list(_FORBIDDEN_MODULE_PREFIXES),
                    "project_owned_module_prefixes": list(
                        project_owned_module_prefixes
                    ),
                    "editable_prefix": _EDITABLE_PREFIX,
                }
            )
        )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONPYCACHEPREFIX", None)
        env.update(
            {
                "PYTHONPATH": str(temp),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONSAFEPATH": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "XDG_CACHE_HOME": str(temp / "xdg-cache"),
                "MPLCONFIGDIR": str(temp / "mpl-cache"),
                "ES_BOUNDARY_RUNTIME_CONFIG": str(config_path),
                "ES_BOUNDARY_RUNTIME_RESULT": str(result_path),
            }
        )
        completed = subprocess.run(
            (str(interpreter), "-P", "-c", _RUNTIME_PROBE_CHILD),
            cwd=workspace,
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            raw = result_path.read_bytes()
            payload = json.loads(
                raw.decode("utf-8", "strict"),
                object_pairs_hook=_strict_object,
                parse_float=_reject_float,
                parse_constant=_reject_constant,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BoundaryProofError(
                "proof_runtime_probe_failed",
                {
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-1000:].decode("utf-8", "replace"),
                    "stderr": completed.stderr[-1000:].decode("utf-8", "replace"),
                },
            ) from exc
        if payload.get("source_event_observer_sha256") != observer_digest:
            raise BoundaryProofError(
                "proof_source_event_observer_digest_mismatch", "residual"
            )
        module_origin_rows = _parse_pair_rows(
            payload.get("module_origin_rows"), label="runtime module"
        )
        expected_observer_row = [
            _GENERATED_SOURCE_EVENT_OBSERVER_MODULE,
            str(observer_path.resolve(strict=True)),
        ]
        observer_rows = [
            row
            for row in module_origin_rows
            if row[0] == _GENERATED_SOURCE_EVENT_OBSERVER_MODULE
        ]
        if observer_rows != [expected_observer_row]:
            raise BoundaryProofError(
                "proof_source_event_observer_digest_mismatch", observer_rows
            )
        payload["module_origin_rows"] = _normalize_runtime_owned_temporary_origins(
            [
                [
                    name,
                    (
                        _GENERATED_SOURCE_EVENT_OBSERVER_ORIGIN
                        if [name, value] == expected_observer_row
                        else value
                    ),
                ]
                for name, value in module_origin_rows
            ]
        )
        raw = canonical_json_bytes(payload)
    row = _require_exact_keys(
        payload,
        {
            "action_outcome",
            "source_events",
            "source_event_observer_sha256",
            "python_executable",
            "workspace",
            "module_origin",
            "removed_editable_hooks",
            "forbidden_roots",
            "forbidden_module_prefixes",
            "project_owned_module_prefixes",
            "loaded_forbidden_modules",
            "forbidden_origin_rows",
            "outside_project_origin_rows",
            "projected_origin_rows",
            "module_origin_rows",
            "cache_artifacts",
            "stderr_sha256",
            "stdout_sha256",
        },
        code="proof_runtime_probe_failed",
        label="result",
    )
    if completed.returncode != 0:
        raise BoundaryProofError("proof_runtime_probe_failed", completed.returncode)
    if row["python_executable"] != str(verified_target) or row["workspace"] != str(workspace):
        raise BoundaryProofError("proof_runtime_probe_failed", "process binding")
    origin = _require_string(
        row["module_origin"], code="proof_runtime_probe_failed", label="module_origin"
    )
    if not Path(origin).resolve(strict=False).is_relative_to(workspace):
        raise BoundaryProofError("proof_origin_isolation_failed", origin)
    reported_forbidden = _string_list(
        row["forbidden_roots"],
        code="proof_runtime_probe_failed",
        label="forbidden_roots",
        nonempty=False,
    )
    if not set(str(path) for path in bound_forbidden).issubset(reported_forbidden):
        raise BoundaryProofError("proof_runtime_probe_failed", "forbidden roots")
    forbidden_prefixes = _string_list(
        row["forbidden_module_prefixes"],
        code="proof_runtime_probe_failed",
        label="forbidden_module_prefixes",
        nonempty=False,
    )
    project_prefixes = _string_list(
        row["project_owned_module_prefixes"],
        code="proof_runtime_probe_failed",
        label="project_owned_module_prefixes",
    )
    if forbidden_prefixes != _FORBIDDEN_MODULE_PREFIXES or project_prefixes != project_owned_module_prefixes:
        raise BoundaryProofError("proof_runtime_probe_failed", "module prefixes")
    loaded = _string_list(
        row["loaded_forbidden_modules"],
        code="proof_runtime_probe_failed",
        label="loaded_forbidden_modules",
        nonempty=False,
    )
    forbidden_origins = _parse_pair_rows(
        row["forbidden_origin_rows"],
        label="runtime forbidden",
    )
    outside_origins = _parse_pair_rows(
        row["outside_project_origin_rows"],
        label="runtime outside",
    )
    _parse_pair_rows(row["projected_origin_rows"], label="runtime projected")
    _parse_pair_rows(row["module_origin_rows"], label="runtime module")
    _string_list(
        row["removed_editable_hooks"],
        code="proof_runtime_probe_failed",
        label="removed_editable_hooks",
        nonempty=False,
    )
    cache_artifacts = _string_list(
        row["cache_artifacts"],
        code="proof_runtime_probe_failed",
        label="cache_artifacts",
        nonempty=False,
    )
    _require_sha256(
        row["stdout_sha256"],
        code="proof_runtime_probe_failed",
        label="stdout_sha256",
    )
    _require_sha256(
        row["stderr_sha256"],
        code="proof_runtime_probe_failed",
        label="stderr_sha256",
    )
    if loaded or forbidden_origins or outside_origins or cache_artifacts:
        raise BoundaryProofError(
            "proof_origin_isolation_failed",
            {
                "loaded": loaded,
                "forbidden": forbidden_origins,
                "outside": outside_origins,
                "cache": cache_artifacts,
            },
        )
    action_outcome = _require_mapping(
        row["action_outcome"],
        code="proof_runtime_probe_failed",
        label="action_outcome",
    )
    if action_outcome != witness.probe["expected_outcome"]:
        raise BoundaryProofError(
            "proof_runtime_probe_failed", "unexpected action outcome"
        )
    source_events = _require_mapping(
        row["source_events"],
        code="proof_runtime_probe_failed",
        label="source_events",
    )
    if set(source_events) != {witness.witness_id}:
        raise BoundaryProofError("proof_witness_unobserved", witness.witness_id)
    source_event = _validated_source_event(
        witness,
        source_events[witness.witness_id],
        code="proof_witness_unobserved",
    )
    return source_event, _target_blob(workspace, witness.consumer_path) or ""


def _validated_source_event(
    witness: WitnessContract,
    value: object,
    *,
    code: str,
) -> dict[str, object]:
    binding = witness.source_event_binding
    if binding is None:
        raise BoundaryProofError(code, witness.witness_id)
    event_kind = str(binding["event_kind"])
    event = _require_exact_keys(
        value,
        {
            "event_kind",
            "phase",
            "attribution",
            "consumer_path",
            "caller_object_id",
            "span",
            "hit_count",
            event_kind,
        },
        code=code,
        label=witness.witness_id,
    )
    span = _require_exact_keys(
        event["span"],
        {"line_start", "column_start", "line_end", "column_end"},
        code=code,
        label=f"{witness.witness_id}.span",
    )
    expected_span = {
        "line_start": witness.start_line,
        "column_start": witness.column_start,
        "line_end": witness.end_line,
        "column_end": witness.column_end,
    }
    if (
        {
            "event_kind": event["event_kind"],
            "phase": event["phase"],
            "attribution": event["attribution"],
        }
        != binding
        or event["consumer_path"] != witness.consumer_path
        or event["caller_object_id"] != witness.caller_object_id
        or span != expected_span
    ):
        raise BoundaryProofError(code, witness.witness_id)
    _require_int(
        event["hit_count"],
        code=code,
        label=f"{witness.witness_id}.hit_count",
        minimum=1,
    )
    _require_mapping(
        event[event_kind],
        code=code,
        label=f"{witness.witness_id}.{event_kind}",
    )
    _validate_json_value(event, label=f"source_event.{witness.witness_id}")
    return copy.deepcopy(dict(event))


def _pytest_node_outcome(
    pytest_report: Mapping[str, object], node_id: str
) -> str:
    rows = _require_list(
        pytest_report.get("node_outcomes"),
        code="proof_pytest_report_invalid",
        label="node_outcomes",
    )
    matches: list[str] = []
    for index, raw_row in enumerate(rows):
        row = _require_exact_keys(
            raw_row,
            {"pytest_node_id", "outcome"},
            code="proof_pytest_report_invalid",
            label=f"node_outcomes[{index}]",
        )
        if row["pytest_node_id"] == node_id:
            matches.append(
                _require_string(
                    row["outcome"],
                    code="proof_pytest_report_invalid",
                    label=f"node_outcomes[{index}].outcome",
                )
            )
    if len(matches) != 1 or matches[0] not in {
        "passed",
        "failed",
        "skipped",
        "errors",
    }:
        raise BoundaryProofError("proof_pytest_report_invalid", node_id)
    return matches[0]


def _pytest_witness_outcome_passes(
    witness: WitnessContract, pytest_report: Mapping[str, object]
) -> bool:
    binding = _require_mapping(
        witness.source_event_binding,
        code="proof_witness_unobserved",
        label=f"{witness.witness_id}.source_event_binding",
    )
    attribution = _require_mapping(
        binding.get("attribution"),
        code="proof_witness_unobserved",
        label=f"{witness.witness_id}.attribution",
    )
    attribution_kind = attribution.get("attribution_kind")
    if attribution_kind == "pytest_node":
        node_id = _require_string(
            attribution.get("pytest_node_id"),
            code="proof_witness_unobserved",
            label=f"{witness.witness_id}.pytest_node_id",
        )
        return _pytest_node_outcome(pytest_report, node_id) == "passed"
    if attribution_kind == "selector_module":
        outcomes = _require_exact_keys(
            pytest_report.get("outcomes"),
            {"passed", "failed", "skipped", "errors"},
            code="proof_pytest_report_invalid",
            label="outcomes",
        )
        errors = _require_int(
            outcomes["errors"],
            code="proof_pytest_report_invalid",
            label="outcomes.errors",
        )
        exit_code = _require_int(
            pytest_report.get("exit_code"),
            code="proof_pytest_report_invalid",
            label="exit_code",
        )
        return errors == 0 and exit_code in {0, 1}
    raise BoundaryProofError("proof_witness_unobserved", witness.witness_id)


def _pytest_observation(
    witness: WitnessContract,
    pytest_report: Mapping[str, object],
    *,
    workspace: Path,
) -> tuple[object, str]:
    source_events = pytest_report["source_events"]
    assert isinstance(source_events, Mapping)
    raw_event = source_events.get(witness.witness_id)
    if raw_event is None:
        raise BoundaryProofError("proof_witness_unobserved", witness.witness_id)
    source_event = _validated_source_event(
        witness, raw_event, code="proof_witness_unobserved"
    )
    if not _pytest_witness_outcome_passes(witness, pytest_report):
        raise BoundaryProofError("proof_witness_unobserved", witness.witness_id)
    blob = _target_blob(workspace, witness.consumer_path)
    if blob is None:
        raise BoundaryProofError("proof_witness_unobserved", witness.witness_id)
    return source_event, blob


def _baseline_witness_results(
    contract: ProofContract,
    *,
    python: Path,
    workspace: Path,
    tree: str,
    pytest_report: Mapping[str, object],
    controller_pytest_reports: Mapping[str, Mapping[str, object]],
    forbidden_roots: tuple[Path, ...],
    python_target: Path,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for witness in contract.witnesses:
        if witness.witness_kind == "pytest_runtime":
            observation, blob = _pytest_observation(
                witness, pytest_report, workspace=workspace
            )
        elif witness.witness_kind == "controller_pytest_runtime":
            controller_report = controller_pytest_reports.get(witness.selector_id)
            if controller_report is None:
                raise BoundaryProofError(
                    "proof_witness_unobserved", witness.witness_id
                )
            observation, blob = _pytest_observation(
                witness, controller_report, workspace=workspace
            )
        elif witness.witness_kind == "static_ast":
            observation, blob = _static_observation(witness, workspace)
        else:
            observation, blob = _runtime_observation(
                witness,
                python=python,
                workspace=workspace,
                forbidden_roots=forbidden_roots,
                project_owned_module_prefixes=_project_prefixes(contract),
                python_target=python_target,
            )
        _validate_json_value(observation, label="observation")
        row: dict[str, object] = {
            "witness_id": witness.witness_id,
            "selector_id": witness.selector_id,
            "consumer_id": witness.consumer_id,
            "proof_kind": witness.proof_kind,
            "witness_kind": witness.witness_kind,
            "target_tree": tree,
            "target_path": witness.consumer_path,
            "target_blob_id": blob,
            "mechanically_observed": True,
            "observation": copy.deepcopy(observation),
            "observation_sha256": _sha256(canonical_json_bytes(observation)),
            "passed": observation == witness.expected_result,
        }
        if witness.witness_kind in {
            "pytest_runtime",
            "controller_pytest_runtime",
            "runtime_probe",
        }:
            row["source_event"] = copy.deepcopy(observation)
        rows.append(row)
    return rows


def _bootstrap_authority_inputs(
    preedit_policy: Mapping[str, object],
    source_census: Mapping[str, object],
    *,
    runner_digest: str,
) -> tuple[
    Mapping[str, object],
    tuple[Mapping[str, object], ...],
    tuple[SelectorContract, ...],
    list[Mapping[str, object]],
]:
    policy = _require_mapping(
        preedit_policy, code="proof_bootstrap_policy_invalid", label="preedit_policy"
    )
    census = _require_mapping(
        source_census, code="proof_bootstrap_census_invalid", label="source_census"
    )
    policy_digest = validate_record_sha256(policy)
    validate_record_sha256(census)
    if census.get("preedit_policy_sha256") != policy_digest:
        raise BoundaryProofError(
            "proof_authority_binding_mismatch", "source census binds another policy"
        )
    selector_policy = _require_exact_keys(
        policy.get("selector_policy"),
        _BOOTSTRAP_SELECTOR_POLICY_KEYS,
        code="proof_bootstrap_policy_invalid",
        label="selector_policy",
    )
    sampling_rule = _require_string(
        selector_policy["sampling_rule"],
        code="proof_selector_sampling_rule_invalid",
        label="sampling_rule",
    )
    if sampling_rule != _SELECTOR_SAMPLING_RULE:
        raise BoundaryProofError(
            "proof_selector_sampling_rule_invalid", sampling_rule
        )
    carrier = _require_exact_keys(
        selector_policy["pytest_carrier"],
        {"executable", "sha256", "version", "tmp_isolation"},
        code="proof_pytest_carrier_identity_mismatch",
        label="selector_policy.pytest_carrier",
    )
    if carrier != {
        "executable": str(PINNED_PYTEST_CARRIER),
        "sha256": PINNED_PYTEST_CARRIER_SHA256,
        "version": PINNED_PYTEST_CARRIER_VERSION,
        "tmp_isolation": "private_tmpfs",
    }:
        raise BoundaryProofError(
            "proof_pytest_carrier_identity_mismatch", carrier
        )
    raw_providers = _require_list(
        selector_policy["provider_visible_pytest_selectors"],
        code="proof_provider_selector_modules_invalid",
        label="provider selectors",
    )
    if len(raw_providers) != len(_MANDATORY_PROVIDER_MODULES):
        raise BoundaryProofError(
            "proof_provider_selector_modules_invalid", len(raw_providers)
        )
    providers: list[Mapping[str, object]] = []
    provider_ids: set[str] = set()
    modules: list[str] = []
    for ordinal, raw in enumerate(raw_providers, start=1):
        row = _require_exact_keys(
            raw,
            _BOOTSTRAP_PROVIDER_KEYS,
            code="proof_provider_selector_modules_invalid",
            label=str(ordinal),
        )
        selector_id = _require_identifier(
            row["selector_id"],
            code="proof_provider_selector_modules_invalid",
            label="selector_id",
        )
        if selector_id in provider_ids or _require_int(
            row["ordinal"],
            code="proof_provider_selector_modules_invalid",
            label="ordinal",
            minimum=1,
        ) != ordinal:
            raise BoundaryProofError(
                "proof_provider_selector_modules_invalid", selector_id
            )
        provider_ids.add(selector_id)
        modules.append(
            _safe_relative_path(
                row["pytest_module_path"],
                code="proof_provider_selector_modules_invalid",
                label="pytest_module_path",
            )
        )
        providers.append(row)
    if tuple(modules) != _MANDATORY_PROVIDER_MODULES:
        raise BoundaryProofError(
            "proof_provider_selector_modules_invalid", modules
        )
    controllers = _parse_controller_selectors(
        selector_policy["controller_only_proof_selectors"],
        actual_runner_sha256=runner_digest,
    )
    controller_ids = {row.selector_id for row in controllers}
    if provider_ids.intersection(controller_ids):
        raise BoundaryProofError("proof_selector_cross_lane_duplicate")
    raw_consumers = _require_list(
        census.get("consumer_rows"),
        code="proof_consumer_rows_invalid",
        label="consumer_rows",
    )
    consumers = [
        _require_mapping(
            row, code="proof_consumer_rows_invalid", label=str(index)
        )
        for index, row in enumerate(raw_consumers)
    ]
    return selector_policy, tuple(providers), controllers, consumers


def _bootstrap_collection_contract(
    providers: Sequence[Mapping[str, object]],
    *,
    runner_digest: str,
) -> ProofContract:
    return ProofContract(
        provider_selectors=tuple(
            SelectorContract(
                selector_id=str(row["selector_id"]),
                ordinal=index,
                lane="provider_visible_pytest",
                proof_kind="boundary_runtime",
                coverage_witness_ids=(),
                pytest_module_path=str(row["pytest_module_path"]),
            )
            for index, row in enumerate(providers, start=1)
        ),
        controller_selectors=(),
        witnesses=(),
        desired_specs=(),
        consumers=(),
        runner_sha256=runner_digest,
    )


def _bootstrap_nodes_by_selector(
    providers: Sequence[Mapping[str, object]],
    collected_node_ids: Sequence[str],
) -> dict[str, tuple[str, ...]]:
    if not collected_node_ids or len(set(collected_node_ids)) != len(collected_node_ids):
        raise BoundaryProofError("proof_pytest_node_missing", "collection")
    modules = [str(row["pytest_module_path"]) for row in providers]
    nodes_by_module: dict[str, list[str]] = {module: [] for module in modules}
    for node_id in collected_node_ids:
        owners = [module for module in modules if node_id.startswith(module + "::")]
        if len(owners) != 1:
            raise BoundaryProofError("proof_pytest_node_unknown", node_id)
        nodes_by_module[owners[0]].append(node_id)
    if any(not nodes for nodes in nodes_by_module.values()):
        missing = [module for module, nodes in nodes_by_module.items() if not nodes]
        raise BoundaryProofError("proof_pytest_node_missing", missing)
    ordered = [node for module in modules for node in nodes_by_module[module]]
    if ordered != list(collected_node_ids):
        raise BoundaryProofError("proof_pytest_node_reordered")
    return {
        str(row["selector_id"]): tuple(nodes_by_module[str(row["pytest_module_path"])])
        for row in providers
    }


def _bootstrap_provider_rows(
    providers: Sequence[Mapping[str, object]],
    *,
    source_census: Mapping[str, object],
    nodes_by_selector: Mapping[str, tuple[str, ...]],
    witness_ids_by_selector: Mapping[str, list[str]],
) -> list[dict[str, object]]:
    leaf_values = _require_list(
        source_census.get("leaf_rows"),
        code="proof_bootstrap_census_invalid",
        label="leaf_rows",
    )
    leaves = [
        _require_mapping(
            row, code="proof_bootstrap_census_invalid", label=str(index)
        )
        for index, row in enumerate(leaf_values)
    ]
    result: list[dict[str, object]] = []
    for policy_row in providers:
        selector_id = str(policy_row["selector_id"])
        path = str(policy_row["pytest_module_path"])
        matches = [row for row in leaves if row.get("path") == path]
        if len(matches) != 1:
            raise BoundaryProofError("proof_bootstrap_census_invalid", path)
        leaf = matches[0]
        text = _require_mapping(
            leaf.get("text"), code="proof_bootstrap_census_invalid", label=path
        )
        if text.get("is_strict_utf8") is not True:
            raise BoundaryProofError("proof_bootstrap_census_invalid", path)
        coverage_ids = tuple(witness_ids_by_selector.get(selector_id, ()))
        if len(coverage_ids) != 1:
            raise BoundaryProofError("proof_selector_unused", selector_id)
        result.append(
            {
                "selector_id": selector_id,
                "ordinal": policy_row["ordinal"],
                "pytest_module_path": path,
                "projection_blob_id": _require_sha1(
                    leaf.get("object_id"),
                    code="proof_bootstrap_census_invalid",
                    label=f"{path}.object_id",
                ),
                "mode": _require_string(
                    leaf.get("mode"),
                    code="proof_bootstrap_census_invalid",
                    label=f"{path}.mode",
                ),
                "physical_line_count": _require_int(
                    text.get("physical_line_count"),
                    code="proof_bootstrap_census_invalid",
                    label=f"{path}.physical_line_count",
                ),
                "pytest_node_ids": list(nodes_by_selector[selector_id]),
                "coverage_witness_ids": list(coverage_ids),
            }
        )
    return result


def _build_bootstrap_contract(
    *,
    selector_policy: Mapping[str, object],
    providers: Sequence[Mapping[str, object]],
    controllers: tuple[SelectorContract, ...],
    source_census: Mapping[str, object],
    consumer_rows: list[Mapping[str, object]],
    collected_node_ids: Sequence[str],
    runner_digest: str,
    controller_collected_node_ids: Mapping[str, Sequence[str]] | None = None,
) -> ProofContract:
    nodes_by_selector = _bootstrap_nodes_by_selector(providers, collected_node_ids)
    parsed_consumers = _parse_consumers(consumer_rows)
    consumers_by_id = {row.consumer_id: row for row in parsed_consumers}
    raw_consumers_by_id = {
        _require_identifier(
            row.get("consumer_id"),
            code="proof_consumer_rows_invalid",
            label="consumer_id",
        ): row
        for row in consumer_rows
    }
    if len(raw_consumers_by_id) != len(consumer_rows):
        raise BoundaryProofError("proof_consumer_rows_invalid", "duplicate")
    provider_ids = {str(row["selector_id"]) for row in providers}
    provider_by_id = {str(row["selector_id"]): row for row in providers}
    controller_by_id = {row.selector_id: row for row in controllers}
    selector_ids = provider_ids | set(controller_by_id)
    raw_witnesses = _require_list(
        selector_policy["coverage_witness_specs"],
        code="proof_witnesses_invalid",
        label="coverage_witness_specs",
    )
    rich_witnesses: list[dict[str, object]] = []
    witness_ids: set[str] = set()
    witness_expected: dict[str, object] = {}
    witness_ids_by_selector: dict[str, list[str]] = {
        selector_id: [] for selector_id in selector_ids
    }
    witness_ids_by_consumer: dict[str, list[str]] = {
        consumer_id: [] for consumer_id in consumers_by_id
    }
    for index, raw in enumerate(raw_witnesses):
        row = _require_exact_keys(
            raw,
            _BOOTSTRAP_WITNESS_KEYS,
            code="proof_witnesses_invalid",
            label=str(index),
        )
        witness_id = _require_identifier(
            row["witness_id"], code="proof_witnesses_invalid", label="witness_id"
        )
        selector_id = _require_identifier(
            row["selector_id"], code="proof_witnesses_invalid", label="selector_id"
        )
        consumer_id = _require_identifier(
            row["consumer_id"], code="proof_witnesses_invalid", label="consumer_id"
        )
        if (
            witness_id in witness_ids
            or selector_id not in selector_ids
            or consumer_id not in consumers_by_id
        ):
            raise BoundaryProofError("proof_witness_backpointer_mismatch", witness_id)
        witness_ids.add(witness_id)
        witness_kind = _require_string(
            row["witness_kind"],
            code="proof_witnesses_invalid",
            label="witness_kind",
        )
        proof_kind = _require_string(
            row["required_proof_kind"],
            code="proof_witnesses_invalid",
            label="required_proof_kind",
        )
        consumer = consumers_by_id[consumer_id]
        raw_consumer = raw_consumers_by_id[consumer_id]
        if consumer.coverage_status != "required":
            raise BoundaryProofError(
                f"proof_witness_attached_to_{consumer.coverage_status}_consumer",
                consumer_id,
            )
        if (
            selector_id != consumer.selector_id
            or witness_kind != consumer.witness_kind
        ):
            raise BoundaryProofError("proof_consumer_class_mismatch", consumer_id)
        if proof_kind != consumer.required_proof_kind:
            raise BoundaryProofError("proof_kind_mismatch", witness_id)
        spec = _require_mapping(
            row["spec"], code="proof_witnesses_invalid", label=f"{witness_id}.spec"
        )
        if spec.get("anchor_id") != raw_consumer.get("anchor_id"):
            raise BoundaryProofError("proof_witness_consumer_binding_mismatch", witness_id)
        common: dict[str, object] = {
            "witness_id": witness_id,
            "selector_id": selector_id,
            "consumer_id": consumer_id,
            "proof_kind": proof_kind,
            "witness_kind": witness_kind,
            "runner_sha256": runner_digest,
            "consumer_path": consumer.caller_path,
            "caller_object_id": consumer.caller_object_id,
            "start_line": consumer.start_line,
            "column_start": consumer.column_start,
            "end_line": consumer.end_line,
            "column_end": consumer.column_end,
            "match_id": consumer.match_id,
        }
        if witness_kind == "pytest_runtime":
            spec = _require_exact_keys(
                spec,
                {
                    "anchor_id",
                    "event_kind",
                    "phase",
                    "attribution",
                    "expected_event",
                },
                code="proof_witnesses_invalid",
                label=f"{witness_id}.spec",
            )
            if selector_id not in provider_ids or proof_kind != "boundary_runtime":
                raise BoundaryProofError("proof_selector_cross_lane_duplicate", witness_id)
            attribution = _require_mapping(
                spec["attribution"],
                code="proof_witnesses_invalid",
                label=f"{witness_id}.attribution",
            )
            if attribution.get("attribution_kind") == "pytest_node":
                attribution = _require_exact_keys(
                    attribution,
                    {"attribution_kind", "pytest_node_pattern"},
                    code="proof_witnesses_invalid",
                    label=f"{witness_id}.attribution",
                )
                pattern = _require_string(
                    attribution["pytest_node_pattern"],
                    code="proof_pytest_node_pattern_invalid",
                    label=witness_id,
                )
                try:
                    matches = [
                        node_id
                        for node_id in nodes_by_selector[selector_id]
                        if re.fullmatch(pattern, node_id)
                    ]
                except re.error as exc:
                    raise BoundaryProofError(
                        "proof_pytest_node_pattern_invalid", witness_id
                    ) from exc
                if not matches:
                    raise BoundaryProofError("proof_pytest_node_missing", witness_id)
                if len(matches) != 1:
                    raise BoundaryProofError("proof_pytest_node_ambiguous", witness_id)
                resolved_attribution = {
                    "attribution_kind": "pytest_node",
                    "pytest_node_id": matches[0],
                }
            elif attribution.get("attribution_kind") == "selector_module":
                attribution = _require_exact_keys(
                    attribution,
                    {"attribution_kind", "pytest_module_path"},
                    code="proof_witnesses_invalid",
                    label=f"{witness_id}.attribution",
                )
                module_path = _safe_relative_path(
                    attribution["pytest_module_path"],
                    code="proof_witnesses_invalid",
                    label=f"{witness_id}.pytest_module_path",
                )
                if module_path != provider_by_id[selector_id]["pytest_module_path"]:
                    raise BoundaryProofError("proof_pytest_node_unknown", witness_id)
                resolved_attribution = {
                    "attribution_kind": "selector_module",
                    "pytest_module_path": module_path,
                }
            else:
                raise BoundaryProofError("proof_witnesses_invalid", witness_id)
            source_event_binding = _parse_source_event_binding(
                {
                    "event_kind": spec["event_kind"],
                    "phase": spec["phase"],
                    "attribution": resolved_attribution,
                }
            )
            expected = copy.deepcopy(spec["expected_event"])
            common.update(
                {
                    "source_event_binding": source_event_binding,
                    "expected_event": expected,
                }
            )
        elif witness_kind == "controller_pytest_runtime":
            spec = _require_exact_keys(
                spec,
                {
                    "anchor_id",
                    "event_kind",
                    "phase",
                    "attribution",
                    "expected_event",
                },
                code="proof_witnesses_invalid",
                label=f"{witness_id}.spec",
            )
            selector = controller_by_id.get(selector_id)
            if (
                selector is None
                or selector.execution_kind != "pytest_aggregate"
                or proof_kind != "boundary_runtime"
            ):
                raise BoundaryProofError(
                    "proof_selector_cross_lane_duplicate", witness_id
                )
            attribution = _require_mapping(
                spec["attribution"],
                code="proof_witnesses_invalid",
                label=f"{witness_id}.attribution",
            )
            if attribution.get("attribution_kind") == "pytest_node":
                attribution = _require_exact_keys(
                    attribution,
                    {"attribution_kind", "pytest_node_pattern"},
                    code="proof_witnesses_invalid",
                    label=f"{witness_id}.attribution",
                )
                pattern = _require_string(
                    attribution["pytest_node_pattern"],
                    code="proof_pytest_node_pattern_invalid",
                    label=witness_id,
                )
                if controller_collected_node_ids is None:
                    owned_nodes = [
                        node_id
                        for node_id in collected_node_ids
                        if any(
                            node_id.startswith(argument + "::")
                            for argument in selector.argv
                        )
                    ]
                else:
                    owned_nodes = list(
                        controller_collected_node_ids.get(selector_id, ())
                    )
                try:
                    matches = [
                        node_id
                        for node_id in owned_nodes
                        if re.fullmatch(pattern, node_id)
                    ]
                except re.error as exc:
                    raise BoundaryProofError(
                        "proof_pytest_node_pattern_invalid", witness_id
                    ) from exc
                if not matches:
                    raise BoundaryProofError(
                        "proof_pytest_node_missing", witness_id
                    )
                if len(matches) != 1:
                    raise BoundaryProofError(
                        "proof_pytest_node_ambiguous", witness_id
                    )
                resolved_attribution = {
                    "attribution_kind": "pytest_node",
                    "pytest_node_id": matches[0],
                }
            elif attribution.get("attribution_kind") == "selector_module":
                attribution = _require_exact_keys(
                    attribution,
                    {"attribution_kind", "pytest_module_path"},
                    code="proof_witnesses_invalid",
                    label=f"{witness_id}.attribution",
                )
                module_path = _safe_relative_path(
                    attribution["pytest_module_path"],
                    code="proof_witnesses_invalid",
                    label=f"{witness_id}.pytest_module_path",
                )
                if module_path not in selector.argv:
                    raise BoundaryProofError(
                        "proof_pytest_node_unknown", witness_id
                    )
                resolved_attribution = {
                    "attribution_kind": "selector_module",
                    "pytest_module_path": module_path,
                }
            else:
                raise BoundaryProofError("proof_witnesses_invalid", witness_id)
            source_event_binding = _parse_source_event_binding(
                {
                    "event_kind": spec["event_kind"],
                    "phase": spec["phase"],
                    "attribution": resolved_attribution,
                }
            )
            expected = copy.deepcopy(spec["expected_event"])
            common.update(
                {
                    "source_event_binding": source_event_binding,
                    "expected_event": expected,
                }
            )
        elif witness_kind == "static_ast":
            spec = _require_exact_keys(
                spec,
                {"anchor_id", "query", "expected_event"},
                code="proof_witnesses_invalid",
                label=f"{witness_id}.spec",
            )
            if selector_id not in controller_by_id:
                raise BoundaryProofError("proof_selector_cross_lane_duplicate", witness_id)
            expected = copy.deepcopy(spec["expected_event"])
            common.update(
                {"query": copy.deepcopy(spec["query"]), "expected_result": expected}
            )
        elif witness_kind == "runtime_probe":
            spec = _require_exact_keys(
                spec,
                {
                    "anchor_id",
                    "event_kind",
                    "phase",
                    "attribution",
                    "probe",
                    "expected_event",
                },
                code="proof_witnesses_invalid",
                label=f"{witness_id}.spec",
            )
            if selector_id not in controller_by_id:
                raise BoundaryProofError("proof_selector_cross_lane_duplicate", witness_id)
            source_event_binding = _parse_source_event_binding(
                {
                    "event_kind": spec["event_kind"],
                    "phase": spec["phase"],
                    "attribution": copy.deepcopy(spec["attribution"]),
                }
            )
            expected = copy.deepcopy(spec["expected_event"])
            common.update(
                {
                    "probe": copy.deepcopy(spec["probe"]),
                    "source_event_binding": source_event_binding,
                    "expected_event": expected,
                }
            )
        else:
            raise BoundaryProofError("proof_witnesses_invalid", witness_kind)
        _validate_json_value(expected, label=f"{witness_id}.expected")
        rich_witnesses.append(common)
        witness_expected[witness_id] = expected
        witness_ids_by_selector[selector_id].append(witness_id)
        witness_ids_by_consumer[consumer_id].append(witness_id)

    required_consumer_ids = {
        row.consumer_id
        for row in parsed_consumers
        if row.coverage_status == "required"
    }
    witnessed_consumer_ids = {
        consumer_id
        for consumer_id, witness_ids in witness_ids_by_consumer.items()
        if witness_ids
    }
    if required_consumer_ids != witnessed_consumer_ids:
        raise BoundaryProofError(
            "proof_required_consumer_domain_mismatch",
            sorted(required_consumer_ids.symmetric_difference(witnessed_consumer_ids)),
        )
    for consumer_id, consumer in consumers_by_id.items():
        actual = tuple(witness_ids_by_consumer[consumer_id])
        if consumer.coverage_status == "required":
            if actual != consumer.coverage_witness_ids or len(actual) != 1:
                raise BoundaryProofError(
                    "proof_witness_backpointer_mismatch", consumer_id
                )
        elif actual:
            raise BoundaryProofError(
                f"proof_witness_attached_to_{consumer.coverage_status}_consumer",
                consumer_id,
            )

    provider_rows = _bootstrap_provider_rows(
        providers,
        source_census=source_census,
        nodes_by_selector=nodes_by_selector,
        witness_ids_by_selector=witness_ids_by_selector,
    )
    raw_desired = _require_list(
        selector_policy["desired_state_proof_specs"],
        code="proof_specs_invalid",
        label="desired_state_proof_specs",
    )
    if len(raw_desired) != len(rich_witnesses):
        raise BoundaryProofError("proof_spec_witness_mismatch")
    desired_rows: list[dict[str, object]] = []
    for ordinal, (raw, witness) in enumerate(
        zip(raw_desired, rich_witnesses, strict=True), start=1
    ):
        row = _require_exact_keys(
            raw,
            _BOOTSTRAP_DESIRED_KEYS,
            code="proof_specs_invalid",
            label=str(ordinal),
        )
        witness_id = _require_identifier(
            row["witness_id"], code="proof_specs_invalid", label="witness_id"
        )
        if (
            witness_id != witness["witness_id"]
            or row["proof_kind"] != witness["proof_kind"]
            or row["expected_result"] != witness_expected.get(witness_id)
        ):
            raise BoundaryProofError("proof_spec_witness_mismatch", witness_id)
        desired_rows.append(
            {
                "proof_id": _require_identifier(
                    row["proof_spec_id"],
                    code="proof_specs_invalid",
                    label="proof_spec_id",
                ),
                "ordinal": ordinal,
                "selector_id": witness["selector_id"],
                "witness_id": witness_id,
                "consumer_id": witness["consumer_id"],
                "proof_kind": witness["proof_kind"],
                "expected_result": copy.deepcopy(row["expected_result"]),
            }
        )
    manifest = {
        "provider_visible_pytest_selectors": provider_rows,
        "controller_only_proof_selectors": copy.deepcopy(
            selector_policy["controller_only_proof_selectors"]
        ),
        "coverage_witnesses": rich_witnesses,
        "desired_state_proof_specs": desired_rows,
    }
    return validate_contract(
        manifest,
        consumer_rows=consumer_rows,
        expected_runner_sha256=runner_digest,
    )


def _capture_baseline_contract(
    contract: ProofContract,
    *,
    python: Path,
    workspace: Path,
    expected_tree: str,
    report_path: Path,
    forbidden_roots: tuple[Path, ...],
    pytest_carrier: PytestCarrier,
) -> dict[str, object]:
    """Run the single baseline capture path for either final or bootstrap authority."""

    interpreter, interpreter_target = _verify_pinned_python(Path(python))
    root, pre_tree = _verify_tree(Path(workspace), expected_tree)
    _verify_baseline_consumer_assets(contract, root)
    _verify_provider_assets(contract, root)
    _verify_input_bindings(contract, root)
    pytest_report = _run_pytest_observation(
        contract,
        python=interpreter,
        workspace=root,
        report_path=Path(report_path),
        forbidden_roots=forbidden_roots,
        pytest_carrier=pytest_carrier,
        python_target=interpreter_target,
    )
    with tempfile.TemporaryDirectory(
        prefix="es-boundary-controller-", dir=Path(report_path).parent
    ) as raw_controller_reports:
        controller_pytest_reports, controller_selector_results = (
            _run_controller_pytest_observations(
                contract,
                python=interpreter,
                workspace=root,
                report_directory=Path(raw_controller_reports).resolve(strict=True),
                forbidden_roots=forbidden_roots,
                pytest_carrier=pytest_carrier,
                python_target=interpreter_target,
            )
        )
    witness_results = _baseline_witness_results(
        contract,
        python=interpreter,
        workspace=root,
        tree=pre_tree,
        pytest_report=pytest_report,
        controller_pytest_reports=controller_pytest_reports,
        forbidden_roots=forbidden_roots,
        python_target=interpreter_target,
    )
    _, post_tree = _verify_tree(root, expected_tree)
    node_ids = pytest_report["node_ids"]
    outcomes = pytest_report["outcomes"]
    assert isinstance(node_ids, list) and isinstance(outcomes, dict)
    return {
        "schema_version": "es_f1_boundary_baseline.v1",
        "runner_sha256": contract.runner_sha256,
        "pre_tree": pre_tree,
        "post_tree": post_tree,
        "aggregate_pytest_argv": pytest_report["argv"],
        "collected_node_ids": node_ids,
        "collected_node_sha256": _sha256(canonical_json_bytes(node_ids)),
        "collection_total": len(node_ids),
        "outcomes": outcomes,
        "origin_isolation": pytest_report["origin"],
        "selector_results": [
            {
                "selector_id": selector.selector_id,
                "pytest_node_ids": list(selector.pytest_node_ids),
                "coverage_witness_ids": list(selector.coverage_witness_ids),
            }
            for selector in contract.provider_selectors
        ],
        "controller_selector_results": controller_selector_results,
        "witness_results": witness_results,
    }


def capture_baseline(
    selector_manifest: Mapping[str, object],
    *,
    consumer_rows: Sequence[Mapping[str, object]],
    python: Path,
    workspace: Path,
    expected_tree: str,
    report_path: Path,
    expected_runner_sha256: str,
    pytest_carrier: Path,
    expected_pytest_carrier_sha256: str,
    forbidden_roots: tuple[Path, ...] = (),
) -> dict[str, object]:
    """Capture one exact aggregate baseline and every truthful witness result."""

    carrier = _verify_pytest_carrier(
        Path(pytest_carrier), expected_sha256=expected_pytest_carrier_sha256
    )
    contract = validate_contract(
        selector_manifest,
        consumer_rows=consumer_rows,
        expected_runner_sha256=expected_runner_sha256,
    )
    return _capture_baseline_contract(
        contract,
        python=python,
        workspace=workspace,
        expected_tree=expected_tree,
        report_path=Path(report_path),
        forbidden_roots=forbidden_roots,
        pytest_carrier=carrier,
    )


def capture_bootstrap_baseline(
    preedit_policy: Mapping[str, object],
    *,
    source_census: Mapping[str, object],
    python: Path,
    workspace: Path,
    expected_tree: str,
    report_path: Path,
    expected_runner_sha256: str,
    pytest_carrier: Path,
    expected_pytest_carrier_sha256: str,
    forbidden_roots: tuple[Path, ...] = (),
) -> dict[str, object]:
    """Capture the pre-edit baseline before the final selector can exist."""

    carrier = _verify_pytest_carrier(
        Path(pytest_carrier), expected_sha256=expected_pytest_carrier_sha256
    )
    digest = _verify_expected_runner_sha256(expected_runner_sha256)
    selector_policy, providers, controllers, consumers = _bootstrap_authority_inputs(
        preedit_policy,
        source_census,
        runner_digest=digest,
    )
    interpreter, interpreter_target = _verify_pinned_python(Path(python))
    root, _ = _verify_tree(Path(workspace), expected_tree)
    collection_contract = _bootstrap_collection_contract(
        providers, runner_digest=digest
    )
    with tempfile.TemporaryDirectory(prefix="es-boundary-bootstrap-") as raw_temp:
        temp = Path(raw_temp).resolve(strict=True)
        collection = _run_pytest_observation(
            collection_contract,
            python=interpreter,
            workspace=root,
            report_path=(temp / "provider-collection-origin.json").resolve(),
            forbidden_roots=forbidden_roots,
            pytest_carrier=carrier,
            python_target=interpreter_target,
            collect_only=True,
        )
        controller_collected_node_ids = {
            selector.selector_id: _collect_controller_pytest_nodes(
                selector,
                python=interpreter,
                workspace=root,
                report_path=(
                    temp / f"controller-{selector.ordinal:04d}-collection.json"
                ).resolve(),
                forbidden_roots=forbidden_roots,
                pytest_carrier=carrier,
                python_target=interpreter_target,
            )
            for selector in controllers
            if selector.execution_kind == "pytest_aggregate"
        }
    node_ids = collection["node_ids"]
    assert isinstance(node_ids, list)
    contract = _build_bootstrap_contract(
        selector_policy=selector_policy,
        providers=providers,
        controllers=controllers,
        source_census=source_census,
        consumer_rows=consumers,
        collected_node_ids=node_ids,
        runner_digest=digest,
        controller_collected_node_ids=controller_collected_node_ids,
    )
    return _capture_baseline_contract(
        contract,
        python=interpreter,
        workspace=root,
        expected_tree=expected_tree,
        report_path=Path(report_path),
        forbidden_roots=forbidden_roots,
        pytest_carrier=carrier,
    )


def _validate_expected_result_rows(
    expected_rows: Sequence[Mapping[str, object]],
    *,
    contract: ProofContract,
    workspace: Path,
    tree: str,
) -> None:
    if not isinstance(expected_rows, Sequence) or isinstance(expected_rows, (str, bytes)):
        raise BoundaryProofError("proof_result_missing")
    rows = list(expected_rows)
    if len(rows) < len(contract.desired_specs):
        raise BoundaryProofError("proof_result_missing")
    if len(rows) > len(contract.desired_specs):
        raise BoundaryProofError("proof_result_extra")
    actual_ids: list[str] = []
    for index, (raw, spec, witness) in enumerate(
        zip(rows, contract.desired_specs, contract.witnesses, strict=True), start=1
    ):
        expected_keys = (
            _RUNTIME_DESIRED_RESULT_KEYS
            if witness.witness_kind
            in {"pytest_runtime", "controller_pytest_runtime", "runtime_probe"}
            else _DESIRED_RESULT_KEYS
        )
        row = _require_exact_keys(
            raw,
            expected_keys,
            code="proof_result_shape_invalid",
            label=str(index),
        )
        proof_id = _require_string(
            row["proof_id"], code="proof_result_shape_invalid", label="proof_id"
        )
        ordinal = _require_int(
            row["ordinal"],
            code="proof_result_shape_invalid",
            label="ordinal",
            minimum=1,
        )
        actual_ids.append(proof_id)
        if proof_id != spec.proof_id:
            expected_ids = [candidate.proof_id for candidate in contract.desired_specs]
            supplied = [
                candidate.get("proof_id") if isinstance(candidate, Mapping) else None
                for candidate in rows
            ]
            if set(supplied) == set(expected_ids):
                raise BoundaryProofError("proof_result_reordered")
            raise BoundaryProofError("proof_result_unmapped", proof_id)
        if (
            ordinal != spec.ordinal
            or row["selector_id"] != spec.selector_id
            or row["witness_id"] != spec.witness_id
            or row["consumer_id"] != spec.consumer_id
            or row["proof_kind"] != spec.proof_kind
            or row["witness_kind"] != witness.witness_kind
            or row["target_tree"] != tree
            or row["target_path"] != witness.consumer_path
        ):
            raise BoundaryProofError("proof_result_unmapped", proof_id)
        if row["mechanically_observed"] is not True:
            raise BoundaryProofError("proof_result_unobserved", proof_id)
        _validate_json_value(row["observation"], label="observation")
        if "source_event" in row:
            _validated_source_event(
                witness,
                row["source_event"],
                code="proof_result_shape_invalid",
            )
            if row["source_event"] != row["observation"]:
                raise BoundaryProofError("proof_result_mismatch", proof_id)
        expected_observation_digest = _sha256(canonical_json_bytes(row["observation"]))
        if row["observation_sha256"] != expected_observation_digest:
            raise BoundaryProofError("proof_result_digest_mismatch", proof_id)
        current_blob = _target_blob(workspace, witness.consumer_path)
        if row["target_blob_id"] != current_blob:
            raise BoundaryProofError("proof_result_blob_drift", proof_id)
        if row["passed"] is not True:
            raise BoundaryProofError("proof_result_failed", proof_id)


def execute_desired_state(
    selector_manifest: Mapping[str, object],
    *,
    consumer_rows: Sequence[Mapping[str, object]],
    python: Path,
    workspace: Path,
    expected_tree: str,
    expected_runner_sha256: str,
    pytest_carrier: Path,
    expected_pytest_carrier_sha256: str,
    expected_result_rows: Sequence[Mapping[str, object]] | None = None,
    forbidden_roots: tuple[Path, ...] = (),
) -> list[dict[str, object]]:
    """Execute every desired proof against an explicit tree and optionally replay rows."""

    carrier = _verify_pytest_carrier(
        Path(pytest_carrier), expected_sha256=expected_pytest_carrier_sha256
    )
    contract = validate_contract(
        selector_manifest,
        consumer_rows=consumer_rows,
        expected_runner_sha256=expected_runner_sha256,
    )
    interpreter, interpreter_target = _verify_pinned_python(Path(python))
    root, pre_tree = _verify_tree(Path(workspace), expected_tree)
    _verify_provider_assets(contract, root)
    _verify_input_bindings(contract, root)
    if expected_result_rows is not None:
        _validate_expected_result_rows(
            expected_result_rows, contract=contract, workspace=root, tree=pre_tree
        )
    with tempfile.TemporaryDirectory(prefix="es-boundary-desired-") as raw_temp:
        pytest_report = _run_pytest_observation(
            contract,
            python=interpreter,
            workspace=root,
            report_path=(Path(raw_temp) / "pytest-origin.json").resolve(),
            forbidden_roots=forbidden_roots,
            pytest_carrier=carrier,
            python_target=interpreter_target,
        )
        controller_pytest_reports, _ = _run_controller_pytest_observations(
            contract,
            python=interpreter,
            workspace=root,
            report_directory=Path(raw_temp).resolve(strict=True),
            forbidden_roots=forbidden_roots,
            pytest_carrier=carrier,
            python_target=interpreter_target,
        )
    baseline_rows = _baseline_witness_results(
        contract,
        python=interpreter,
        workspace=root,
        tree=pre_tree,
        pytest_report=pytest_report,
        controller_pytest_reports=controller_pytest_reports,
        forbidden_roots=forbidden_roots,
        python_target=interpreter_target,
    )
    desired_rows: list[dict[str, object]] = []
    for spec, witness, observed in zip(
        contract.desired_specs, contract.witnesses, baseline_rows, strict=True
    ):
        row = {
            "proof_id": spec.proof_id,
            "ordinal": spec.ordinal,
            **observed,
            "passed": observed["observation"] == spec.expected_result,
        }
        expected_keys = (
            _RUNTIME_DESIRED_RESULT_KEYS
            if witness.witness_kind
            in {"pytest_runtime", "controller_pytest_runtime", "runtime_probe"}
            else _DESIRED_RESULT_KEYS
        )
        if set(row) != expected_keys:
            raise BoundaryProofError("proof_result_shape_invalid", spec.proof_id)
        if row["passed"] is not True:
            raise BoundaryProofError("proof_desired_state_failed", spec.proof_id)
        desired_rows.append(row)
    _verify_tree(root, expected_tree)
    if expected_result_rows is not None and desired_rows != list(expected_result_rows):
        raise BoundaryProofError("proof_result_mismatch")
    return desired_rows


_CANDIDATE_IDENTITY_KEYS = (
    "anchor_id",
    "callee_or_dispatch_form",
    "caller_object_id",
    "caller_path",
    "consumer_id",
    "detector_id",
    "detector_version",
    "match_id",
    "responsibility_ids",
    "span",
)
_FROZEN_CONTROLLER_MODULE_ORDER_SHA256 = (
    "sha256:3fa404d5a7b653218d77a884c0c363c8216a4b016343df2391777a9ed71bb62e"
)
_FROZEN_CONTROLLER_MODULE_ORDER = (
    "tests/torch/test_generator_registry.py",
    "tests/torch/test_construction_consolidation.py",
    "tests/torch/test_generator_adapter.py",
    "tests/torch/test_config_bridge.py",
    "tests/torch/test_model_spec.py",
    "tests/torch/test_model_spec_v2.py",
    "tests/torch/test_lightning_checkpoint.py",
    "tests/torch/test_artifact_schema.py",
    "tests/torch/test_artifact_schema_v2.py",
    "tests/torch/test_workflows_components.py",
    "tests/torch/test_fno_generators.py",
    "tests/torch/test_fno_lightning_integration.py",
    "tests/torch/test_neuralop_uno_generator.py",
    "tests/torch/test_model_output_modes.py",
    "tests/torch/test_model_manager.py",
    "tests/torch/test_model_training.py",
    "tests/torch/test_train_lightning_execution_contract.py",
    "tests/torch/test_object_big_generator_contract.py",
    "tests/torch/test_structural_config_ownership.py",
    "tests/scripts/test_inference_backend_selector.py",
    "tests/scripts/test_training_backend_selector.py",
    "tests/studies/test_gain_calibration.py",
    "tests/studies/test_grid_lines_bridge_ladder.py",
    "tests/studies/test_position_reassembly_checkpoint_replay.py",
    "tests/studies/test_torch_ablation_configuration.py",
    "tests/test_acquisition_record.py",
    "tests/test_legacy_params_lifecycle.py",
    "tests/test_model_config_architecture.py",
    "tests/test_workflow_generator_integration.py",
    "tests/torch/test_absolute_scaling_contract.py",
    "tests/torch/test_absolute_scaling_dict.py",
    "tests/torch/test_absolute_scaling_entrypoints.py",
    "tests/torch/test_absolute_scaling_mmap.py",
    "tests/torch/test_amplitude_physics_gain.py",
    "tests/torch/test_ci_profile.py",
    "tests/torch/test_cli_inference_torch.py",
    "tests/torch/test_cli_train_torch.py",
    "tests/torch/test_compute_loss_c4_regression.py",
    "tests/torch/test_config_factory.py",
    "tests/torch/test_debug_fno_activations.py",
    "tests/torch/test_dict_container_physics_scale.py",
    "tests/torch/test_fno_integration.py",
    "tests/torch/test_grid_lines_c4_ci_integration.py",
    "tests/torch/test_grid_lines_ci_probe_roundtrip_integration.py",
    "tests/torch/test_grid_lines_position_reassembly_strategy.py",
    "tests/torch/test_grid_lines_torch_runner.py",
    "tests/torch/test_grid_lines_torch_runner_ci_inference.py",
    "tests/torch/test_grid_lines_torch_runner_grad_norm_flag.py",
    "tests/torch/test_hybres_extension_preconditions.py",
    "tests/torch/test_hybrid_checkpoint_cross_dataset_inference.py",
    "tests/torch/test_inference_cli_reassembly.py",
    "tests/torch/test_inference_normalization.py",
    "tests/torch/test_inference_reassembly_aggregation.py",
    "tests/torch/test_inference_reassembly_parity.py",
    "tests/torch/test_inline_dataset_amplitude_scaling_regression.py",
    "tests/torch/test_inline_dataset_rectangular_scaled_batched.py",
    "tests/torch/test_integration_workflow_torch.py",
    "tests/torch/test_lightning_dataloader_coords_guard.py",
    "tests/torch/test_loss_modes.py",
    "tests/torch/test_mlflow_recon_logging.py",
    "tests/torch/test_nphotons_resolution.py",
    "tests/torch/test_patch_stats_cli.py",
    "tests/torch/test_physics_scale_bundle.py",
    "tests/torch/test_physics_scale_container.py",
    "tests/torch/test_physics_scale_loss.py",
    "tests/torch/test_rect_probe_scale_double_div.py",
    "tests/torch/test_rect_s1s2_initialization.py",
    "tests/torch/test_rect_scaling.py",
    "tests/torch/test_rectangular_scaled_forward.py",
    "tests/torch/test_scale_parity.py",
    "tests/torch/test_varpro_probe_ablation_runner.py",
)


def _verify_frozen_controller_module_order() -> str:
    observed = _sha256(canonical_json_bytes(list(_FROZEN_CONTROLLER_MODULE_ORDER)))
    if observed != _FROZEN_CONTROLLER_MODULE_ORDER_SHA256:
        raise BoundaryProofError("proof_controller_module_order_mismatch", observed)
    return observed


def _candidate_input_digest(value: object, *, label: str) -> str:
    return _require_sha256(
        value,
        code="proof_candidate_input_binding_mismatch",
        label=label,
    )


def _candidate_identity(value: object, *, label: str) -> dict[str, object]:
    row = _require_mapping(
        value,
        code="proof_candidate_join_mismatch",
        label=label,
    )
    if not set(_CANDIDATE_IDENTITY_KEYS).issubset(row):
        raise BoundaryProofError("proof_candidate_join_mismatch", label)
    identity = {key: copy.deepcopy(row[key]) for key in _CANDIDATE_IDENTITY_KEYS}
    _require_identifier(
        identity["consumer_id"],
        code="proof_candidate_join_mismatch",
        label=f"{label}.consumer_id",
    )
    _require_sha1(
        identity["caller_object_id"],
        code="proof_candidate_join_mismatch",
        label=f"{label}.caller_object_id",
    )
    _safe_relative_path(
        identity["caller_path"],
        code="proof_candidate_join_mismatch",
        label=f"{label}.caller_path",
    )
    _require_exact_keys(
        identity["span"],
        {"line_start", "column_start", "line_end", "column_end"},
        code="proof_candidate_join_mismatch",
        label=f"{label}.span",
    )
    _validate_json_value(identity, label=label)
    return identity


def _validate_candidate_inputs(
    discovery_input: Mapping[str, object],
    *,
    discovery_output: Mapping[str, object],
    draft_dispositions: Mapping[str, object],
    expected_discovery_input_sha256: str,
    expected_discovery_output_sha256: str,
    expected_draft_dispositions_sha256: str,
    expected_tree: str,
) -> tuple[list[dict[str, object]], list[Mapping[str, object]]]:
    input_digest = _candidate_input_digest(
        expected_discovery_input_sha256, label="discovery_input"
    )
    discovery_digest = _candidate_input_digest(
        expected_discovery_output_sha256, label="discovery_output"
    )
    draft_digest = _candidate_input_digest(
        expected_draft_dispositions_sha256, label="draft_dispositions"
    )
    if (
        discovery_output.get("schema_version")
        != "es_f1_source_census_discovery.v1"
        or discovery_output.get("authority_status")
        != "NON_AUTHORITATIVE_DISCOVERY"
        or discovery_output.get("discovery_input_sha256") != input_digest
        or _sha256(canonical_json_bytes(discovery_output)) != discovery_digest
    ):
        raise BoundaryProofError("proof_candidate_input_binding_mismatch", "discovery")
    if (
        draft_dispositions.get("schema_version")
        != "es_f1_policy_path_decisions_candidate.v1"
        or draft_dispositions.get("authority_status")
        != "NON_AUTHORITATIVE_NEUTRAL_RECOMMENDATION"
        or _sha256(canonical_json_bytes(draft_dispositions)) != draft_digest
    ):
        raise BoundaryProofError("proof_candidate_input_binding_mismatch", "draft")
    candidate_sha256 = _candidate_input_digest(
        draft_dispositions.get("candidate_sha256"), label="candidate_sha256"
    )
    candidate_body = copy.deepcopy(dict(draft_dispositions))
    candidate_body.pop("candidate_sha256", None)
    if _sha256(canonical_json_bytes(candidate_body)) != candidate_sha256:
        raise BoundaryProofError("proof_candidate_input_binding_mismatch", "candidate")
    input_projection = _require_mapping(
        discovery_input.get("projection"),
        code="proof_candidate_input_binding_mismatch",
        label="discovery_input.projection",
    )
    output_projection = _require_mapping(
        discovery_output.get("projection"),
        code="proof_candidate_input_binding_mismatch",
        label="discovery_output.projection",
    )
    if (
        input_projection.get("tree") != expected_tree
        or output_projection.get("tree") != expected_tree
    ):
        raise BoundaryProofError("proof_candidate_input_binding_mismatch", "tree")
    raw_candidates = _require_list(
        discovery_output.get("consumer_candidates"),
        code="proof_candidate_join_mismatch",
        label="consumer_candidates",
    )
    candidates = [
        _candidate_identity(row, label=f"candidate.{index}")
        for index, row in enumerate(raw_candidates)
    ]
    if (
        not candidates
        or discovery_output.get("candidate_set_sha256")
        != _sha256(canonical_json_bytes(raw_candidates))
    ):
        raise BoundaryProofError("proof_candidate_input_binding_mismatch", "candidate_set")
    source_discovery = _require_mapping(
        draft_dispositions.get("source_discovery"),
        code="proof_candidate_input_binding_mismatch",
        label="source_discovery",
    )
    if (
        source_discovery.get("raw_sha256") != discovery_digest
        or source_discovery.get("candidate_set_sha256")
        != discovery_output.get("candidate_set_sha256")
        or source_discovery.get("consumer_candidate_count") != len(candidates)
        or source_discovery.get("projection_tree") != expected_tree
    ):
        raise BoundaryProofError("proof_candidate_input_binding_mismatch", "join")
    raw_decisions = _require_list(
        draft_dispositions.get("consumer_decisions"),
        code="proof_candidate_join_mismatch",
        label="consumer_decisions",
    )
    if len(raw_decisions) != len(candidates):
        raise BoundaryProofError("proof_candidate_join_mismatch", "domain")
    decisions: list[Mapping[str, object]] = []
    for index, (identity, raw_decision) in enumerate(
        zip(candidates, raw_decisions, strict=True)
    ):
        decision = _require_mapping(
            raw_decision,
            code="proof_candidate_join_mismatch",
            label=f"decision.{index}",
        )
        if _candidate_identity(decision, label=f"decision.{index}") != identity:
            raise BoundaryProofError("proof_candidate_join_mismatch", index)
        decisions.append(decision)
    return candidates, decisions


def _static_candidate_choice(
    identity: Mapping[str, object],
    *,
    selector_id: str,
    proof_kind: str,
    witness_kind: str,
    workspace: Path,
) -> dict[str, object] | None:
    caller_path = str(identity["caller_path"])
    if _target_blob(workspace, caller_path) != identity["caller_object_id"]:
        raise BoundaryProofError(
            "proof_candidate_input_binding_mismatch", caller_path
        )
    path = _workspace_path(workspace, caller_path, may_be_absent=False)
    try:
        source = path.read_text(encoding="utf-8", errors="strict")
        tree = ast.parse(source, filename=caller_path)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise BoundaryProofError("proof_candidate_static_parse_failed", caller_path) from exc
    span = identity["span"]
    assert isinstance(span, Mapping)
    expected_position = (
        span["line_start"],
        span["column_start"],
        span["line_end"],
        span["column_end"],
    )
    exact_nodes = [
        node
        for node in ast.walk(tree)
        if (
            getattr(node, "lineno", None),
            getattr(node, "col_offset", None),
            getattr(node, "end_lineno", None),
            getattr(node, "end_col_offset", None),
        )
        == expected_position
    ]
    if len(exact_nodes) != 1:
        return None
    target = exact_nodes[0]
    if isinstance(target, ast.Call):
        target = target.func
    names: list[str] = []
    attributes: list[str] = []
    strings: list[str] = []
    if isinstance(target, ast.Name):
        names.append(target.id)
    elif isinstance(target, ast.Attribute):
        attributes.append(target.attr)
    elif isinstance(target, ast.Constant) and isinstance(target.value, str):
        strings.append(target.value)
    else:
        return None
    return {
        "selector_id": selector_id,
        "proof_kind": proof_kind,
        "witness_kind": witness_kind,
        "spec": {
            "query": {
                "query_kind": "forbidden_syntax_absent",
                "forbidden_names": names,
                "forbidden_attributes": attributes,
                "forbidden_string_literals": strings,
            },
            "expected_event": {"matches": []},
        },
    }


_PROVIDER_OBSERVATION_TARGET_WINDOW = 16
_CONTROLLER_OBSERVATION_CANDIDATE_WINDOW = 8
_PYTEST_DIAGNOSTIC_PHASES = ("bootstrap", "collection", "setup", "call", "teardown")


def _candidate_event_kind(
    identity: Mapping[str, object], *, workspace: Path
) -> str | None:
    """Return the one source-event family structurally supported by a candidate."""

    caller_path = str(identity["caller_path"])
    if _target_blob(workspace, caller_path) != identity["caller_object_id"]:
        raise BoundaryProofError(
            "proof_candidate_input_binding_mismatch", caller_path
        )
    path = _workspace_path(workspace, caller_path, may_be_absent=False)
    try:
        source = path.read_text(encoding="utf-8", errors="strict")
        tree = ast.parse(source, filename=caller_path)
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise BoundaryProofError(
            "proof_candidate_source_parse_failed", caller_path
        ) from exc
    span = identity["span"]
    assert isinstance(span, Mapping)
    expected = {
        "line_start": span["line_start"],
        "column_start": span["column_start"],
        "line_end": span["line_end"],
        "column_end": span["column_end"],
    }
    aliases = [
        alias
        for statement in ast.walk(tree)
        if isinstance(statement, (ast.Import, ast.ImportFrom))
        for alias in statement.names
        if {
            "line_start": alias.lineno,
            "column_start": alias.col_offset,
            "line_end": alias.end_lineno,
            "column_end": alias.end_col_offset,
        }
        == expected
    ]
    if len(aliases) == 1:
        return "import_alias_opcode"
    if aliases:
        return None

    supported_nodes = []
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue
        node_span = {
            "line_start": getattr(node, "lineno", None),
            "column_start": getattr(node, "col_offset", None),
            "line_end": getattr(node, "end_lineno", None),
            "column_end": getattr(node, "end_col_offset", None),
        }
        if node_span != expected:
            continue
        if isinstance(node, ast.Call):
            supported_nodes.append(node)
        elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(
            node.ctx, (ast.Load, ast.Store, ast.Del)
        ):
            supported_nodes.append(node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            supported_nodes.append(node)
    if len(supported_nodes) == 1:
        return "opcode_exact_span"
    if supported_nodes:
        return None

    source_lines = source.splitlines(keepends=True)
    try:
        tokens = tuple(tokenize.generate_tokens(io.StringIO(source).readline))
    except (IndentationError, tokenize.TokenError) as exc:
        raise BoundaryProofError(
            "proof_candidate_source_parse_failed", caller_path
        ) from exc
    callable_matches = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name_tokens = []
        for index, token in enumerate(tokens[:-1]):
            if token.type != tokenize.NAME or token.string != "def":
                continue
            following = tokens[index + 1]
            if (
                token.start[0] == node.lineno
                and following.type == tokenize.NAME
                and following.string == node.name
            ):
                name_tokens.append(following)
        if len(name_tokens) != 1:
            continue
        token = name_tokens[0]
        start_line, start_column = token.start
        end_line, end_column = token.end
        token_span = {
            "line_start": start_line,
            "column_start": len(
                source_lines[start_line - 1][:start_column].encode("utf-8")
            ),
            "line_end": end_line,
            "column_end": len(
                source_lines[end_line - 1][:end_column].encode("utf-8")
            ),
        }
        if token_span == expected:
            callable_matches.append(node)
    return "callable_entry" if len(callable_matches) == 1 else None


def _candidate_provider_selectors(
    discovery_input: Mapping[str, object], *, required: bool
) -> tuple[tuple[str, str], ...]:
    raw = _require_list(
        discovery_input.get("provider_visible_pytest_selectors"),
        code="proof_candidate_provider_selector_invalid",
        label="provider_visible_pytest_selectors",
    )
    if not raw and not required:
        return ()
    rows: list[tuple[str, str]] = []
    for ordinal, value in enumerate(raw, start=1):
        row = _require_exact_keys(
            value,
            {"selector_id", "ordinal", "pytest_module_path"},
            code="proof_candidate_provider_selector_invalid",
            label=str(ordinal),
        )
        selector_id = _require_identifier(
            row["selector_id"],
            code="proof_candidate_provider_selector_invalid",
            label=f"{ordinal}.selector_id",
        )
        module = _safe_relative_path(
            row["pytest_module_path"],
            code="proof_candidate_provider_selector_invalid",
            label=f"{ordinal}.pytest_module_path",
        )
        if row["ordinal"] != ordinal or selector_id != f"PV-{ordinal:02d}":
            raise BoundaryProofError(
                "proof_candidate_provider_selector_invalid", selector_id
            )
        rows.append((selector_id, module))
    if tuple(module for _, module in rows) != _MANDATORY_PROVIDER_MODULES:
        raise BoundaryProofError(
            "proof_candidate_provider_selector_invalid", "provider modules"
        )
    return tuple(rows)


def _candidate_project_prefixes(
    identities: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    prefixes = ["ptycho", "ptycho_torch", "conftest"]
    for identity in identities:
        first = PurePosixPath(str(identity["caller_path"])).parts[0]
        if first.endswith(".py"):
            first = first[:-3]
        if first.isidentifier():
            prefixes.append(first)
    return tuple(dict.fromkeys(prefixes))


def _candidate_pytest_target(
    identity: Mapping[str, object],
    *,
    witness_id: str,
    event_kind: str,
    phase: str,
    attribution: Mapping[str, object],
) -> dict[str, object]:
    return {
        "witness_id": witness_id,
        "consumer_path": identity["caller_path"],
        "caller_object_id": identity["caller_object_id"],
        "span": copy.deepcopy(identity["span"]),
        "source_event_binding": {
            "event_kind": event_kind,
            "phase": phase,
            "attribution": copy.deepcopy(dict(attribution)),
        },
    }


def _candidate_event_witness(
    identity: Mapping[str, object],
    decision: Mapping[str, object],
    *,
    witness_id: str,
    binding: Mapping[str, object],
    probe: Mapping[str, object] | None = None,
) -> WitnessContract:
    span = identity["span"]
    assert isinstance(span, Mapping)
    return WitnessContract(
        witness_id=witness_id,
        selector_id=str(decision["selector_id"]),
        consumer_id=str(identity["consumer_id"]),
        proof_kind=str(decision["required_proof_kind"]),
        witness_kind=str(decision["witness_kind"]),
        consumer_path=str(identity["caller_path"]),
        caller_object_id=str(identity["caller_object_id"]),
        start_line=int(span["line_start"]),
        column_start=int(span["column_start"]),
        end_line=int(span["line_end"]),
        column_end=int(span["column_end"]),
        match_id=str(identity["match_id"]),
        expected_result=None,
        source_event_binding=copy.deepcopy(dict(binding)),
        probe=copy.deepcopy(dict(probe)) if probe is not None else None,
    )


def _pytest_reports_match_except_events(
    first: Mapping[str, object], second: Mapping[str, object]
) -> bool:
    def normalized(value: Mapping[str, object]) -> dict[str, object]:
        result = copy.deepcopy(dict(value))
        result.pop("raw_sha256", None)
        result.pop("source_events", None)
        origin = result.get("origin")
        if isinstance(origin, dict):
            origin.pop("report_sha256", None)
            origin.pop("project_owned_module_prefixes", None)
            origin.pop("module_origin_rows", None)
        return result

    return normalized(first) == normalized(second)


def _observe_provider_candidate_choices(
    discovery_input: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    *,
    python: Path,
    python_target: Path,
    pytest_carrier: PytestCarrier,
    workspace: Path,
    forbidden_roots: tuple[Path, ...],
) -> dict[int, dict[str, object]]:
    provider_indexes = [
        index
        for index, decision in enumerate(decisions)
        if decision.get("witness_kind") == "pytest_runtime"
    ]
    selectors = _candidate_provider_selectors(
        discovery_input, required=bool(provider_indexes)
    )
    if not provider_indexes:
        return {}
    selector_modules = dict(selectors)
    indexes_by_selector: dict[str, list[int]] = {
        selector_id: [] for selector_id, _ in selectors
    }
    for index in provider_indexes:
        selector_id = str(decisions[index]["selector_id"])
        if selector_id not in indexes_by_selector:
            raise BoundaryProofError(
                "proof_candidate_provider_selector_invalid", selector_id
            )
        indexes_by_selector[selector_id].append(index)
    modules = tuple(module for _, module in selectors)
    pytest_argv = (
        str(python),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *modules,
    )
    choices: dict[int, dict[str, object]] = {}
    selected_by_selector: dict[str, tuple[int, dict[str, object], dict[str, object]]] = {}
    offsets = {selector_id: 0 for selector_id, _ in selectors}
    with tempfile.TemporaryDirectory(
        prefix="es-candidate-pytest-", dir=workspace.parent
    ) as raw_temp:
        temp = Path(raw_temp).resolve(strict=True)
        collected = _run_pytest_child(
            python=python,
            workspace=workspace,
            report_path=temp / "collect.json",
            forbidden_roots=forbidden_roots,
            selectors=modules,
            source_event_targets=(),
            project_owned_module_prefixes=("ptycho", "ptycho_torch", "conftest"),
            pytest_argv=pytest_argv,
            expected_node_ids=None,
            python_target=python_target,
            pytest_carrier=pytest_carrier,
            collect_only=True,
        )
        raw_node_ids = collected["node_ids"]
        assert isinstance(raw_node_ids, list)
        node_ids = _validate_controller_pytest_nodes(
            "provider-candidate-observation", modules, raw_node_ids
        )
        nodes_by_module = {
            module: tuple(
                node_id for node_id in node_ids if node_id.startswith(module + "::")
            )
            for module in modules
        }
        round_ordinal = 0
        while len(selected_by_selector) < len(
            [selector for selector, rows in indexes_by_selector.items() if rows]
        ):
            round_ordinal += 1
            unresolved_count = sum(
                selector_id not in selected_by_selector
                and offsets[selector_id] < len(indexes_by_selector[selector_id])
                for selector_id, _ in selectors
            )
            batch_size = max(
                1,
                min(
                    8,
                    _PROVIDER_OBSERVATION_TARGET_WINDOW
                    // max(1, unresolved_count),
                ),
            )
            targets: list[dict[str, object]] = []
            metadata: dict[str, tuple[int, dict[str, object]]] = {}
            attempted_indexes: list[int] = []
            progress = False
            for selector_id, module in selectors:
                if selector_id in selected_by_selector:
                    continue
                indexes = indexes_by_selector[selector_id]
                start = offsets[selector_id]
                stop = min(start + batch_size, len(indexes))
                offsets[selector_id] = stop
                if stop > start:
                    progress = True
                for candidate_index in indexes[start:stop]:
                    identity = candidates[candidate_index]
                    event_kind = _candidate_event_kind(identity, workspace=workspace)
                    if event_kind is None:
                        continue
                    attempted_indexes.append(candidate_index)
                    hypotheses: list[tuple[str, Mapping[str, object]]] = []
                    if identity["caller_path"] == module:
                        hypotheses.append(
                            (
                                "bootstrap",
                                {
                                    "attribution_kind": "selector_module",
                                    "pytest_module_path": module,
                                },
                            )
                        )
                    hypotheses.append(
                        (
                            "collection",
                            {
                                "attribution_kind": "selector_module",
                                "pytest_module_path": module,
                            },
                        )
                    )
                    for phase in _PYTEST_DIAGNOSTIC_PHASES[2:]:
                        for node_id in nodes_by_module[module]:
                            hypotheses.append(
                                (
                                    phase,
                                    {
                                        "attribution_kind": "pytest_node",
                                        "pytest_node_id": node_id,
                                    },
                                )
                            )
                    for hypothesis_ordinal, (phase, attribution) in enumerate(
                        hypotheses
                    ):
                        witness_id = (
                            f"candidate-{candidate_index}-{hypothesis_ordinal}"
                        )
                        target = _candidate_pytest_target(
                            identity,
                            witness_id=witness_id,
                            event_kind=event_kind,
                            phase=phase,
                            attribution=attribution,
                        )
                        targets.append(target)
                        binding = _require_mapping(
                            target["source_event_binding"],
                            code="proof_candidate_event_invalid",
                            label=witness_id,
                        )
                        metadata[witness_id] = (
                            candidate_index,
                            copy.deepcopy(dict(binding)),
                        )
            if not targets:
                if not progress:
                    break
                continue
            observed = _run_pytest_child(
                python=python,
                workspace=workspace,
                report_path=temp / f"diagnostic-{round_ordinal}.json",
                forbidden_roots=forbidden_roots,
                selectors=modules,
                source_event_targets=targets,
                project_owned_module_prefixes=_candidate_project_prefixes(
                    [candidates[index] for index in attempted_indexes]
                ),
                pytest_argv=pytest_argv,
                expected_node_ids=node_ids,
                python_target=python_target,
                pytest_carrier=pytest_carrier,
                reject_skipped=True,
            )
            source_events = observed["source_events"]
            assert isinstance(source_events, Mapping)
            observed_by_index: dict[
                int, list[tuple[str, dict[str, object], dict[str, object]]]
            ] = {}
            for witness_id, (candidate_index, binding) in metadata.items():
                raw_event = source_events.get(witness_id)
                if raw_event is None:
                    continue
                witness = _candidate_event_witness(
                    candidates[candidate_index],
                    decisions[candidate_index],
                    witness_id=witness_id,
                    binding=binding,
                )
                event = _validated_source_event(
                    witness, raw_event, code="proof_candidate_event_invalid"
                )
                observed_by_index.setdefault(candidate_index, []).append(
                    (witness_id, binding, event)
                )
            for selector_id, _ in selectors:
                if selector_id in selected_by_selector:
                    continue
                for candidate_index in indexes_by_selector[selector_id]:
                    events = observed_by_index.get(candidate_index)
                    if events:
                        witness_id, binding, event = events[0]
                        selected_by_selector[selector_id] = (
                            candidate_index,
                            {
                                "witness_id": witness_id,
                                "binding": binding,
                                "event": event,
                            },
                            observed,
                        )
                        break
            if not progress:
                break

        if selected_by_selector:
            replay_targets = []
            for candidate_index, selected, _ in selected_by_selector.values():
                binding = selected["binding"]
                assert isinstance(binding, Mapping)
                replay_targets.append(
                    _candidate_pytest_target(
                        candidates[candidate_index],
                        witness_id=str(selected["witness_id"]),
                        event_kind=str(binding["event_kind"]),
                        phase=str(binding["phase"]),
                        attribution=_require_mapping(
                            binding["attribution"],
                            code="proof_candidate_event_invalid",
                            label="attribution",
                        ),
                    )
                )
            replay = _run_pytest_child(
                python=python,
                workspace=workspace,
                report_path=temp / "replay.json",
                forbidden_roots=forbidden_roots,
                selectors=modules,
                source_event_targets=replay_targets,
                project_owned_module_prefixes=_candidate_project_prefixes(
                    [
                        candidates[candidate_index]
                        for candidate_index, _, _ in selected_by_selector.values()
                    ]
                ),
                pytest_argv=pytest_argv,
                expected_node_ids=node_ids,
                python_target=python_target,
                pytest_carrier=pytest_carrier,
                reject_skipped=True,
            )
            replay_events = replay["source_events"]
            assert isinstance(replay_events, Mapping)
            for selector_id, (
                candidate_index,
                selected,
                observed,
            ) in selected_by_selector.items():
                witness_id = str(selected["witness_id"])
                event = selected["event"]
                if (
                    replay_events.get(witness_id) != event
                    or not _pytest_reports_match_except_events(observed, replay)
                ):
                    raise BoundaryProofError(
                        "proof_candidate_event_replay_mismatch", selector_id
                    )
                binding = selected["binding"]
                assert isinstance(binding, Mapping)
                decision = decisions[candidate_index]
                choices[candidate_index] = {
                    "selector_id": selector_id,
                    "proof_kind": decision["required_proof_kind"],
                    "witness_kind": decision["witness_kind"],
                    "spec": {
                        "event_kind": binding["event_kind"],
                        "phase": binding["phase"],
                        "attribution": copy.deepcopy(binding["attribution"]),
                        "expected_event": copy.deepcopy(event),
                    },
                }
    return choices


def _controller_candidate_module_bindings(
    workspace: Path,
) -> list[dict[str, object]]:
    bindings: list[dict[str, object]] = []
    for module in _FROZEN_CONTROLLER_MODULE_ORDER:
        try:
            path = _workspace_path(workspace, module, may_be_absent=False)
            raw = path.read_bytes()
            committed_blob = _run_git(
                workspace, "rev-parse", f"HEAD:{module}"
            ).decode("ascii", "strict").strip()
        except (OSError, UnicodeError, BoundaryProofError) as exc:
            raise BoundaryProofError(
                "proof_controller_module_binding_mismatch", module
            ) from exc
        observed_blob = _target_blob(workspace, module)
        if (
            path.is_symlink()
            or not path.is_file()
            or observed_blob is None
            or observed_blob != committed_blob
        ):
            raise BoundaryProofError(
                "proof_controller_module_binding_mismatch", module
            )
        bindings.append(
            {
                "path": module,
                "projection_blob_id": _require_sha1(
                    committed_blob,
                    code="proof_controller_module_binding_mismatch",
                    label=module,
                ),
                "sha256": _sha256(raw),
            }
        )
    return bindings


def _controller_candidate_selector(
    *,
    python: Path,
    runner_digest: str,
    module_bindings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    argv = (
        str(python),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *_FROZEN_CONTROLLER_MODULE_ORDER,
    )
    return {
        "selector_id": "CO-PYTEST-01",
        "ordinal": 1,
        "proof_kind": "boundary_runtime",
        "execution_kind": "pytest_aggregate",
        "runner_path": RUNNER_RELATIVE_PATH,
        "runner_sha256": runner_digest,
        "argv": list(argv),
        "input_bindings": [
            {"path": row["path"], "sha256": row["sha256"]}
            for row in module_bindings
        ],
        "projection_bindings": [
            {
                "path": row["path"],
                "projection_blob_id": row["projection_blob_id"],
            }
            for row in module_bindings
        ],
    }


def _observe_controller_candidate_choices(
    candidates: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    *,
    python: Path,
    python_target: Path,
    pytest_carrier: PytestCarrier,
    workspace: Path,
    forbidden_roots: tuple[Path, ...],
    runner_digest: str,
) -> tuple[
    dict[int, dict[str, object]],
    list[dict[str, object]],
    dict[str, object] | None,
]:
    module_set = set(_FROZEN_CONTROLLER_MODULE_ORDER)
    candidate_indexes = [
        index
        for index, (identity, decision) in enumerate(
            zip(candidates, decisions, strict=True)
        )
        if decision.get("proposed_disposition") == "route_through_boundary"
        and decision.get("required_proof_kind") == "boundary_runtime"
        and decision.get("witness_kind") != "pytest_runtime"
        and identity.get("caller_path") in module_set
    ]
    if not candidate_indexes:
        return {}, [], None

    module_bindings = _controller_candidate_module_bindings(workspace)
    selector_candidate = _controller_candidate_selector(
        python=python,
        runner_digest=runner_digest,
        module_bindings=module_bindings,
    )
    modules = tuple(_FROZEN_CONTROLLER_MODULE_ORDER)
    pytest_argv = _string_list(
        selector_candidate["argv"],
        code="proof_controller_argv_invalid",
        label="CO-PYTEST-01",
    )
    selected: tuple[
        int,
        str,
        dict[str, object],
        dict[str, object],
        dict[str, object],
    ] | None = None
    with tempfile.TemporaryDirectory(
        prefix="es-controller-candidate-pytest-", dir=workspace.parent
    ) as raw_temp:
        temp = Path(raw_temp).resolve(strict=True)
        collected = _run_pytest_child(
            python=python,
            workspace=workspace,
            report_path=temp / "collect.json",
            forbidden_roots=forbidden_roots,
            selectors=modules,
            source_event_targets=(),
            project_owned_module_prefixes=("ptycho", "ptycho_torch", "conftest"),
            pytest_argv=pytest_argv,
            expected_node_ids=None,
            python_target=python_target,
            pytest_carrier=pytest_carrier,
            collect_only=True,
            reject_skipped=True,
        )
        raw_node_ids = collected["node_ids"]
        assert isinstance(raw_node_ids, list)
        node_ids = _validate_controller_pytest_nodes(
            "CO-PYTEST-01", modules, raw_node_ids
        )
        nodes_by_module = {
            module: tuple(
                node_id for node_id in node_ids if node_id.startswith(module + "::")
            )
            for module in modules
        }

        for start in range(
            0, len(candidate_indexes), _CONTROLLER_OBSERVATION_CANDIDATE_WINDOW
        ):
            batch = candidate_indexes[
                start : start + _CONTROLLER_OBSERVATION_CANDIDATE_WINDOW
            ]
            targets: list[dict[str, object]] = []
            metadata: dict[
                int, list[tuple[str, dict[str, object]]]
            ] = {index: [] for index in batch}
            for candidate_index in batch:
                identity = candidates[candidate_index]
                module = str(identity["caller_path"])
                event_kind = _candidate_event_kind(identity, workspace=workspace)
                if event_kind is None:
                    continue
                hypotheses: list[tuple[str, Mapping[str, object]]] = [
                    (
                        "bootstrap",
                        {
                            "attribution_kind": "selector_module",
                            "pytest_module_path": module,
                        },
                    ),
                    (
                        "collection",
                        {
                            "attribution_kind": "selector_module",
                            "pytest_module_path": module,
                        },
                    ),
                ]
                for phase in _PYTEST_DIAGNOSTIC_PHASES[2:]:
                    for node_id in nodes_by_module[module]:
                        hypotheses.append(
                            (
                                phase,
                                {
                                    "attribution_kind": "pytest_node",
                                    "pytest_node_id": node_id,
                                },
                            )
                        )
                for hypothesis_ordinal, (phase, attribution) in enumerate(
                    hypotheses
                ):
                    witness_id = (
                        f"controller-candidate-{candidate_index}-{hypothesis_ordinal}"
                    )
                    target = _candidate_pytest_target(
                        identity,
                        witness_id=witness_id,
                        event_kind=event_kind,
                        phase=phase,
                        attribution=attribution,
                    )
                    targets.append(target)
                    binding = _require_mapping(
                        target["source_event_binding"],
                        code="proof_candidate_event_invalid",
                        label=witness_id,
                    )
                    metadata[candidate_index].append(
                        (witness_id, copy.deepcopy(dict(binding)))
                    )
            if not targets:
                continue
            diagnostic = _run_pytest_child(
                python=python,
                workspace=workspace,
                report_path=temp / f"diagnostic-{start:06d}.json",
                forbidden_roots=forbidden_roots,
                selectors=modules,
                source_event_targets=targets,
                project_owned_module_prefixes=_candidate_project_prefixes(
                    [candidates[index] for index in batch]
                ),
                pytest_argv=pytest_argv,
                expected_node_ids=node_ids,
                python_target=python_target,
                pytest_carrier=pytest_carrier,
                allow_disclosed_nonpass=True,
            )
            source_events = diagnostic["source_events"]
            assert isinstance(source_events, Mapping)
            for candidate_index in batch:
                identity = candidates[candidate_index]
                decision = {
                    **dict(decisions[candidate_index]),
                    "selector_id": "CO-PYTEST-01",
                    "witness_kind": "controller_pytest_runtime",
                }
                for witness_id, binding in metadata[candidate_index]:
                    raw_event = source_events.get(witness_id)
                    if raw_event is None:
                        continue
                    witness = _candidate_event_witness(
                        identity,
                        decision,
                        witness_id=witness_id,
                        binding=binding,
                    )
                    event = _validated_source_event(
                        witness, raw_event, code="proof_candidate_event_invalid"
                    )
                    if not _pytest_witness_outcome_passes(witness, diagnostic):
                        continue
                    selected = (
                        candidate_index,
                        witness_id,
                        binding,
                        event,
                        diagnostic,
                    )
                    break
                if selected is not None:
                    break
            if selected is not None:
                break

        if selected is None:
            return {}, module_bindings, selector_candidate
        candidate_index, witness_id, binding, event, diagnostic = selected
        replay_target = _candidate_pytest_target(
            candidates[candidate_index],
            witness_id=witness_id,
            event_kind=str(binding["event_kind"]),
            phase=str(binding["phase"]),
            attribution=_require_mapping(
                binding["attribution"],
                code="proof_candidate_event_invalid",
                label="controller replay attribution",
            ),
        )
        replay = _run_pytest_child(
            python=python,
            workspace=workspace,
            report_path=temp / "replay.json",
            forbidden_roots=forbidden_roots,
            selectors=modules,
            source_event_targets=(replay_target,),
            project_owned_module_prefixes=_candidate_project_prefixes(
                (candidates[candidate_index],)
            ),
            pytest_argv=pytest_argv,
            expected_node_ids=node_ids,
            python_target=python_target,
            pytest_carrier=pytest_carrier,
            allow_disclosed_nonpass=True,
        )
        replay_events = replay["source_events"]
        assert isinstance(replay_events, Mapping)
        replay_witness = _candidate_event_witness(
            candidates[candidate_index],
            {
                **dict(decisions[candidate_index]),
                "selector_id": "CO-PYTEST-01",
                "witness_kind": "controller_pytest_runtime",
            },
            witness_id=witness_id,
            binding=binding,
        )
        if (
            replay_events.get(witness_id) != event
            or not _pytest_witness_outcome_passes(replay_witness, replay)
            or not _pytest_reports_match_except_events(diagnostic, replay)
        ):
            raise BoundaryProofError(
                "proof_candidate_event_replay_mismatch", "CO-PYTEST-01"
            )
        return (
            {
                candidate_index: {
                    "selector_id": "CO-PYTEST-01",
                    "proof_kind": "boundary_runtime",
                    "witness_kind": "controller_pytest_runtime",
                    "spec": {
                        "event_kind": binding["event_kind"],
                        "phase": binding["phase"],
                        "attribution": copy.deepcopy(binding["attribution"]),
                        "expected_event": copy.deepcopy(event),
                    },
                }
            },
            module_bindings,
            selector_candidate,
        )


def _candidate_import_module(
    identity: Mapping[str, object], *, workspace: Path, event_kind: str
) -> str | None:
    if event_kind not in {"opcode_exact_span", "import_alias_opcode"}:
        return None
    caller_path = str(identity["caller_path"])
    pure = PurePosixPath(caller_path)
    if pure.suffix != ".py":
        return None
    module_parts = list(pure.with_suffix("").parts)
    if module_parts[-1] == "__init__":
        module_parts.pop()
    if not module_parts or any(not part.isidentifier() for part in module_parts):
        return None
    path = _workspace_path(workspace, caller_path, may_be_absent=False)
    try:
        tree = ast.parse(
            path.read_text(encoding="utf-8", errors="strict"),
            filename=caller_path,
        )
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise BoundaryProofError(
            "proof_candidate_source_parse_failed", caller_path
        ) from exc
    span = identity["span"]
    assert isinstance(span, Mapping)
    expected = (
        span["line_start"],
        span["column_start"],
        span["line_end"],
        span["column_end"],
    )
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    matches: list[ast.AST] = []
    for node in ast.walk(tree):
        position = (
            getattr(node, "lineno", None),
            getattr(node, "col_offset", None),
            getattr(node, "end_lineno", None),
            getattr(node, "end_col_offset", None),
        )
        if position != expected:
            continue
        if event_kind == "import_alias_opcode" and isinstance(node, ast.alias):
            matches.append(node)
        elif event_kind == "opcode_exact_span" and isinstance(
            node, (ast.Call, ast.Name, ast.Attribute, ast.Constant)
        ):
            matches.append(node)
    if len(matches) != 1:
        return None
    cursor = parents.get(matches[0])
    while cursor is not None:
        if isinstance(
            cursor,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda),
        ):
            return None
        cursor = parents.get(cursor)
    return ".".join(module_parts)


def _observe_residual_candidate_choices(
    candidates: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    *,
    python: Path,
    python_target: Path,
    workspace: Path,
    forbidden_roots: tuple[Path, ...],
) -> dict[int, dict[str, object]]:
    choices: dict[int, dict[str, object]] = {}
    selected_classes: set[tuple[str, str]] = set()
    for index, (identity, decision) in enumerate(
        zip(candidates, decisions, strict=True)
    ):
        if decision.get("witness_kind") != "runtime_probe":
            continue
        candidate_class = (
            str(decision["proposed_disposition"]),
            str(decision["witness_kind"]),
        )
        if candidate_class in selected_classes:
            continue
        event_kind = _candidate_event_kind(identity, workspace=workspace)
        if event_kind is None:
            continue
        module = _candidate_import_module(
            identity, workspace=workspace, event_kind=event_kind
        )
        if module is None:
            continue
        probe: dict[str, object] = {
            "action": "import_module",
            "module": module,
            "expected_outcome": {"status": "returned"},
        }
        binding: dict[str, object] = {
            "event_kind": event_kind,
            "phase": "residual",
            "attribution": {
                "attribution_kind": "residual_action",
                "action_sha256": _sha256(canonical_json_bytes(probe)),
            },
        }
        witness_id = f"residual-candidate-{index}"
        witness = _candidate_event_witness(
            identity,
            decision,
            witness_id=witness_id,
            binding=binding,
            probe=probe,
        )
        prefixes = _candidate_project_prefixes((identity,))
        try:
            first_event, first_blob = _runtime_observation(
                witness,
                python=python,
                workspace=workspace,
                forbidden_roots=forbidden_roots,
                project_owned_module_prefixes=prefixes,
                python_target=python_target,
            )
            second_event, second_blob = _runtime_observation(
                witness,
                python=python,
                workspace=workspace,
                forbidden_roots=forbidden_roots,
                project_owned_module_prefixes=prefixes,
                python_target=python_target,
            )
        except BoundaryProofError as exc:
            if exc.code == "proof_witness_unobserved":
                continue
            raise
        if (
            first_event != second_event
            or first_blob != identity["caller_object_id"]
            or second_blob != identity["caller_object_id"]
        ):
            raise BoundaryProofError(
                "proof_candidate_event_replay_mismatch", identity["consumer_id"]
            )
        choices[index] = {
            "selector_id": decision["selector_id"],
            "proof_kind": decision["required_proof_kind"],
            "witness_kind": decision["witness_kind"],
            "spec": {
                "event_kind": event_kind,
                "phase": "residual",
                "attribution": copy.deepcopy(binding["attribution"]),
                "probe": probe,
                "expected_event": first_event,
            },
        }
        selected_classes.add(candidate_class)
    return choices


def _observe_candidates_unprotected(
    discovery_input: Mapping[str, object],
    *,
    discovery_output: Mapping[str, object],
    draft_dispositions: Mapping[str, object],
    expected_discovery_input_sha256: str,
    expected_discovery_output_sha256: str,
    expected_draft_dispositions_sha256: str,
    python: Path,
    workspace: Path,
    expected_tree: str,
    expected_runner_sha256: str,
    pytest_carrier: Path,
    expected_pytest_carrier_sha256: str,
    forbidden_roots: tuple[Path, ...],
) -> dict[str, object]:
    """Emit diagnostic witness choices without creating policy authority."""

    runner_digest = _verify_expected_runner_sha256(expected_runner_sha256)
    controller_order_digest = _verify_frozen_controller_module_order()
    interpreter, python_target = _verify_pinned_python(Path(python))
    carrier = _verify_pytest_carrier(
        Path(pytest_carrier), expected_sha256=expected_pytest_carrier_sha256
    )
    root, pre_tree = _verify_tree(Path(workspace), expected_tree)
    canonical_forbidden_roots = tuple(
        _canonical_absolute(
            Path(forbidden_root),
            code="proof_forbidden_root_invalid",
            must_exist=False,
        )
        for forbidden_root in forbidden_roots
    )
    candidates, decisions = _validate_candidate_inputs(
        discovery_input,
        discovery_output=discovery_output,
        draft_dispositions=draft_dispositions,
        expected_discovery_input_sha256=expected_discovery_input_sha256,
        expected_discovery_output_sha256=expected_discovery_output_sha256,
        expected_draft_dispositions_sha256=expected_draft_dispositions_sha256,
        expected_tree=expected_tree,
    )
    for identity in candidates:
        caller_path = str(identity["caller_path"])
        if _target_blob(root, caller_path) != identity["caller_object_id"]:
            raise BoundaryProofError(
                "proof_candidate_input_binding_mismatch", caller_path
            )
    provider_choices = _observe_provider_candidate_choices(
        discovery_input,
        candidates,
        decisions,
        python=interpreter,
        python_target=python_target,
        pytest_carrier=carrier,
        workspace=root,
        forbidden_roots=canonical_forbidden_roots,
    )
    (
        controller_choices,
        controller_module_bindings,
        controller_selector_candidate,
    ) = _observe_controller_candidate_choices(
        candidates,
        decisions,
        python=interpreter,
        python_target=python_target,
        pytest_carrier=carrier,
        workspace=root,
        forbidden_roots=canonical_forbidden_roots,
        runner_digest=runner_digest,
    )
    residual_choices = _observe_residual_candidate_choices(
        candidates,
        decisions,
        python=interpreter,
        python_target=python_target,
        workspace=root,
        forbidden_roots=canonical_forbidden_roots,
    )
    rows: list[dict[str, object]] = []
    counts = {"ambiguous": 0, "observable": 0, "open": 0, "total": len(candidates)}
    for index, (identity, decision) in enumerate(
        zip(candidates, decisions, strict=True)
    ):
        disposition = _require_string(
            decision.get("proposed_disposition"),
            code="proof_candidate_join_mismatch",
            label="proposed_disposition",
        )
        proof_kind = _require_string(
            decision.get("required_proof_kind"),
            code="proof_candidate_join_mismatch",
            label="required_proof_kind",
        )
        selector_id = _require_identifier(
            decision.get("selector_id"),
            code="proof_candidate_join_mismatch",
            label="selector_id",
        )
        witness_kind = _require_string(
            decision.get("witness_kind"),
            code="proof_candidate_join_mismatch",
            label="witness_kind",
        )
        choices: list[dict[str, object]] = []
        provider_choice = provider_choices.get(index)
        controller_choice = controller_choices.get(index)
        residual_choice = residual_choices.get(index)
        if provider_choice is not None:
            choices.append(provider_choice)
            status = "observable"
            reason_code = "provider_exact_event_replayed"
        elif controller_choice is not None:
            choices.append(controller_choice)
            status = "observable"
            reason_code = "controller_exact_event_replayed"
        elif residual_choice is not None:
            choices.append(residual_choice)
            status = "observable"
            reason_code = "residual_exact_event_replayed"
        elif (
            disposition == "remove"
            and proof_kind == "reference_absence"
            and witness_kind == "static_ast"
        ):
            choices.append(
                {
                    "selector_id": selector_id,
                    "proof_kind": proof_kind,
                    "witness_kind": witness_kind,
                    "spec": {
                        "query": {"query_kind": "path_absent"},
                        "expected_event": {"path_absent": True},
                    },
                }
            )
            status = "observable"
            reason_code = "path_absence_query_executable"
        elif (
            disposition == "compatibility_adapter"
            and proof_kind == "non_cdi_static"
            and witness_kind == "static_ast"
        ):
            static_choice = _static_candidate_choice(
                identity,
                selector_id=selector_id,
                proof_kind=proof_kind,
                witness_kind=witness_kind,
                workspace=root,
            )
            if static_choice is None:
                status = "open"
                reason_code = "exact_static_query_unavailable"
            else:
                choices.append(static_choice)
                status = "observable"
                reason_code = "nonvacuous_static_query_executable"
        elif witness_kind == "runtime_probe" and "probe" not in decision:
            status = "open"
            reason_code = "explicit_runtime_action_missing"
        else:
            status = "open"
            reason_code = "executable_candidate_unobserved"
        counts[status] += 1
        rows.append(
            {
                **copy.deepcopy(identity),
                "proposed_disposition": disposition,
                "required_proof_kind": proof_kind,
                "selector_id": selector_id,
                "witness_kind": witness_kind,
                "observation_status": status,
                "reason_code": reason_code,
                "executable_choices": choices,
            }
        )
    _, post_tree = _verify_tree(root, expected_tree)
    if post_tree != pre_tree:
        raise BoundaryProofError("proof_tree_drift", post_tree)
    return {
        "schema_version": "es_f1_witness_observation_candidates.v1",
        "authority_status": "NON_AUTHORITATIVE",
        "input_bindings": {
            "discovery_input_sha256": expected_discovery_input_sha256,
            "discovery_output_sha256": expected_discovery_output_sha256,
            "draft_dispositions_sha256": expected_draft_dispositions_sha256,
            "projection_tree": expected_tree,
            "runner_sha256": runner_digest,
            "forbidden_roots": [str(path) for path in canonical_forbidden_roots],
            "python_execution": {
                "executable": str(interpreter),
                "link_target": PINNED_PYTHON_LINK_TARGET,
                "resolved_executable": str(python_target),
                "sha256": PINNED_PYTHON_SHA256,
                "version": PINNED_PYTHON_VERSION,
            },
            "pytest_carrier": carrier.as_record(),
            "controller_module_order_sha256": controller_order_digest,
            "controller_module_input_bindings": controller_module_bindings,
            "controller_pytest_selector_candidate": controller_selector_candidate,
        },
        "counts": counts,
        "candidate_rows": rows,
    }


def observe_candidates(
    discovery_input: Mapping[str, object],
    *,
    discovery_output: Mapping[str, object],
    draft_dispositions: Mapping[str, object],
    expected_discovery_input_sha256: str,
    expected_discovery_output_sha256: str,
    expected_draft_dispositions_sha256: str,
    python: Path,
    workspace: Path,
    expected_tree: str,
    expected_runner_sha256: str,
    pytest_carrier: Path,
    expected_pytest_carrier_sha256: str,
    forbidden_roots: tuple[Path, ...],
) -> dict[str, object]:
    """Emit candidates while preserving the frozen tracked source identity."""

    root, _ = _verify_tree(Path(workspace), expected_tree)
    frozen_leaf_metadata = _frozen_tree_leaf_metadata(root, expected_tree)
    try:
        return _observe_candidates_unprotected(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft_dispositions,
            expected_discovery_input_sha256=expected_discovery_input_sha256,
            expected_discovery_output_sha256=expected_discovery_output_sha256,
            expected_draft_dispositions_sha256=expected_draft_dispositions_sha256,
            python=python,
            workspace=root,
            expected_tree=expected_tree,
            expected_runner_sha256=expected_runner_sha256,
            pytest_carrier=pytest_carrier,
            expected_pytest_carrier_sha256=expected_pytest_carrier_sha256,
            forbidden_roots=forbidden_roots,
        )
    finally:
        _verify_frozen_source_identity(
            root,
            expected_tree,
            frozen_leaf_metadata,
        )


def load_pinned_canonical_json(path: Path, *, expected_sha256: str) -> dict[str, object]:
    candidate = _canonical_absolute(
        Path(path), code="proof_record_path_invalid", must_exist=True
    )
    expected = _require_sha256(
        expected_sha256, code="proof_record_digest_mismatch", label="expected_sha256"
    )
    try:
        identity = candidate.lstat()
        raw = candidate.read_bytes()
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except BoundaryProofError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryProofError("proof_record_invalid", str(candidate)) from exc
    if candidate.is_symlink() or not candidate.is_file() or identity.st_size != len(raw):
        raise BoundaryProofError("proof_record_invalid", str(candidate))
    if _sha256(raw) != expected:
        raise BoundaryProofError("proof_record_digest_mismatch", str(candidate))
    if not isinstance(value, dict) or canonical_json_bytes(value) != raw:
        raise BoundaryProofError("proof_record_noncanonical", str(candidate))
    return value


def load_closed_canonical_record(
    path: Path,
    *,
    schema_path: Path,
    expected_sha256: str,
) -> dict[str, object]:
    value = load_pinned_canonical_json(path, expected_sha256=expected_sha256)
    schema_candidate = _canonical_absolute(
        Path(schema_path),
        code="proof_record_schema_invalid",
        must_exist=True,
    )
    try:
        identity = schema_candidate.lstat()
        raw = schema_candidate.read_bytes()
        schema = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except BoundaryProofError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryProofError(
            "proof_record_schema_invalid",
            str(schema_candidate),
        ) from exc
    if (
        schema_candidate.is_symlink()
        or not schema_candidate.is_file()
        or identity.st_size != len(raw)
        or not isinstance(schema, dict)
    ):
        raise BoundaryProofError("proof_record_schema_invalid", str(schema_candidate))
    validate_record_sha256(value)
    try:
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    except Exception as exc:
        raise BoundaryProofError(
            "proof_record_schema_invalid",
            str(schema_candidate),
        ) from exc
    if errors:
        first = errors[0]
        raise BoundaryProofError(
            "proof_record_schema_invalid",
            {"path": list(first.absolute_path), "message": first.message},
        )
    return value


def _publish_exclusive(path: Path, value: object) -> None:
    candidate = _canonical_absolute(
        Path(path), code="proof_output_path_invalid", must_exist=False
    )
    candidate.parent.mkdir(parents=True, exist_ok=True)
    try:
        with candidate.open("xb") as handle:
            handle.write(canonical_json_bytes(value))
    except OSError as exc:
        raise BoundaryProofError("proof_output_exists", str(candidate)) from exc


def _runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-census", required=True, type=Path)
    parser.add_argument("--expected-source-census-sha256", required=True)
    parser.add_argument("--source-census-schema", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--pytest-carrier", required=True, type=Path)
    parser.add_argument("--expected-pytest-carrier-sha256", required=True)
    parser.add_argument("--forbidden-root", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--selector-manifest", required=True, type=Path)
    parser.add_argument("--expected-selector-manifest-sha256", required=True)
    parser.add_argument("--selector-manifest-schema", required=True, type=Path)
    _runtime_arguments(parser)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="boundary_proofs")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser("bootstrap-baseline")
    bootstrap.add_argument("--preedit-policy", required=True, type=Path)
    bootstrap.add_argument("--expected-preedit-policy-sha256", required=True)
    bootstrap.add_argument("--preedit-policy-schema", required=True, type=Path)
    _runtime_arguments(bootstrap)
    bootstrap.add_argument("--report-path", required=True, type=Path)
    baseline = subparsers.add_parser("baseline")
    _common_arguments(baseline)
    baseline.add_argument("--report-path", required=True, type=Path)
    desired = subparsers.add_parser("desired-state")
    _common_arguments(desired)
    desired.add_argument("--expected-results", type=Path)
    desired.add_argument("--expected-results-sha256")
    observe = subparsers.add_parser("observe-candidates")
    observe.add_argument("--discovery-input", required=True, type=Path)
    observe.add_argument("--expected-discovery-input-sha256", required=True)
    observe.add_argument("--discovery-output", required=True, type=Path)
    observe.add_argument("--expected-discovery-output-sha256", required=True)
    observe.add_argument("--draft-dispositions", required=True, type=Path)
    observe.add_argument("--expected-draft-dispositions-sha256", required=True)
    observe.add_argument("--python", required=True, type=Path)
    observe.add_argument("--workspace", required=True, type=Path)
    observe.add_argument("--expected-tree", required=True)
    observe.add_argument("--expected-runner-sha256", required=True)
    observe.add_argument("--pytest-carrier", required=True, type=Path)
    observe.add_argument("--expected-pytest-carrier-sha256", required=True)
    observe.add_argument("--forbidden-root", action="append", default=[], type=Path)
    observe.add_argument("--report-path", required=True, type=Path)
    observe.add_argument("--output", required=True, type=Path)
    return parser


def _load_digest_bound_json(
    path: Path,
    *,
    expected_sha256: str,
    require_canonical: bool,
) -> dict[str, object]:
    expected = _require_sha256(
        expected_sha256,
        code="proof_record_digest_mismatch",
        label="expected_sha256",
    )
    candidate = Path(path).resolve(strict=True)
    try:
        identity = candidate.lstat()
        raw = candidate.read_bytes()
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BoundaryProofError("proof_record_invalid", str(candidate)) from exc
    if (
        candidate.is_symlink()
        or not candidate.is_file()
        or identity.st_size != len(raw)
        or _sha256(raw) != expected
    ):
        raise BoundaryProofError("proof_record_digest_mismatch", str(candidate))
    if require_canonical and canonical_json_bytes(value) != raw:
        raise BoundaryProofError("proof_record_noncanonical", str(candidate))
    if not isinstance(value, dict):
        raise BoundaryProofError("proof_record_invalid", str(candidate))
    return value


def _main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _verify_expected_runner_sha256(args.expected_runner_sha256)
    if args.command == "observe-candidates":
        discovery_input = _load_digest_bound_json(
            args.discovery_input,
            expected_sha256=args.expected_discovery_input_sha256,
            require_canonical=False,
        )
        discovery_output = _load_digest_bound_json(
            args.discovery_output,
            expected_sha256=args.expected_discovery_output_sha256,
            require_canonical=True,
        )
        draft_dispositions = _load_digest_bound_json(
            args.draft_dispositions,
            expected_sha256=args.expected_draft_dispositions_sha256,
            require_canonical=True,
        )
        result = observe_candidates(
            discovery_input,
            discovery_output=discovery_output,
            draft_dispositions=draft_dispositions,
            expected_discovery_input_sha256=args.expected_discovery_input_sha256,
            expected_discovery_output_sha256=args.expected_discovery_output_sha256,
            expected_draft_dispositions_sha256=(
                args.expected_draft_dispositions_sha256
            ),
            python=args.python,
            workspace=args.workspace,
            expected_tree=args.expected_tree,
            expected_runner_sha256=args.expected_runner_sha256,
            pytest_carrier=args.pytest_carrier,
            expected_pytest_carrier_sha256=(
                args.expected_pytest_carrier_sha256
            ),
            forbidden_roots=tuple(args.forbidden_root),
        )
        report = {
            "schema_version": "es_f1_witness_observation_report.v1",
            "authority_status": "NON_AUTHORITATIVE",
            "counts": copy.deepcopy(result["counts"]),
            "candidate_output_sha256": _sha256(canonical_json_bytes(result)),
        }
        _publish_exclusive(args.report_path, report)
        _publish_exclusive(args.output, result)
        return 0
    if args.command == "bootstrap-baseline":
        policy = load_closed_canonical_record(
            args.preedit_policy,
            schema_path=args.preedit_policy_schema,
            expected_sha256=args.expected_preedit_policy_sha256,
        )
        census = load_closed_canonical_record(
            args.source_census,
            schema_path=args.source_census_schema,
            expected_sha256=args.expected_source_census_sha256,
        )
        result = capture_bootstrap_baseline(
            policy,
            source_census=census,
            python=args.python,
            workspace=args.workspace,
            expected_tree=args.expected_tree,
            report_path=args.report_path,
            expected_runner_sha256=args.expected_runner_sha256,
            pytest_carrier=args.pytest_carrier,
            expected_pytest_carrier_sha256=(
                args.expected_pytest_carrier_sha256
            ),
            forbidden_roots=tuple(args.forbidden_root),
        )
        _publish_exclusive(args.output, result)
        return 0
    manifest = load_closed_canonical_record(
        args.selector_manifest,
        schema_path=args.selector_manifest_schema,
        expected_sha256=args.expected_selector_manifest_sha256,
    )
    census = load_closed_canonical_record(
        args.source_census,
        schema_path=args.source_census_schema,
        expected_sha256=args.expected_source_census_sha256,
    )
    validate_authority_bindings(manifest, census)
    consumer_rows = census.get("consumer_rows")
    if not isinstance(consumer_rows, list):
        raise BoundaryProofError("proof_consumer_rows_invalid")
    common = {
        "consumer_rows": consumer_rows,
        "python": args.python,
        "workspace": args.workspace,
        "expected_tree": args.expected_tree,
        "expected_runner_sha256": args.expected_runner_sha256,
        "pytest_carrier": args.pytest_carrier,
        "expected_pytest_carrier_sha256": args.expected_pytest_carrier_sha256,
        "forbidden_roots": tuple(args.forbidden_root),
    }
    if args.command == "baseline":
        result = capture_baseline(
            manifest,
            report_path=args.report_path,
            **common,
        )
    else:
        if (args.expected_results is None) != (args.expected_results_sha256 is None):
            raise BoundaryProofError("proof_expected_results_binding_invalid")
        expected_rows = None
        if args.expected_results is not None:
            expected_record = load_pinned_canonical_json(
                args.expected_results,
                expected_sha256=args.expected_results_sha256,
            )
            expected_rows = expected_record.get("result_rows")
            if not isinstance(expected_rows, list):
                raise BoundaryProofError("proof_result_shape_invalid")
        rows = execute_desired_state(
            manifest,
            expected_result_rows=expected_rows,
            **common,
        )
        result = {
            "schema_version": "es_f1_boundary_desired_state.v1",
            "runner_sha256": runner_sha256(),
            "target_tree": args.expected_tree,
            "result_rows": rows,
        }
    _publish_exclusive(args.output, result)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _main(argv)
    except BoundaryProofError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BoundaryProofError",
    "ProofContract",
    "RUNNER_RELATIVE_PATH",
    "canonical_json_bytes",
    "compute_record_sha256",
    "capture_baseline",
    "capture_bootstrap_baseline",
    "execute_desired_state",
    "observe_candidates",
    "load_pinned_canonical_json",
    "load_closed_canonical_record",
    "main",
    "runner_sha256",
    "validate_record_sha256",
    "validate_contract",
    "validate_authority_bindings",
]
