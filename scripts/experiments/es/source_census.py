"""Deterministic source census and Task-0 authority validation for ES F1."""

from __future__ import annotations

import argparse
import ast
import copy
import fnmatch
import hashlib
import importlib
import json
import os
import re
import stat
import subprocess
import sys
import warnings
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, NoReturn, Sequence

from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PINNED_GIT = Path("/usr/bin/git")
PINNED_GIT_VERSION = "git version 2.43.0"
PINNED_GIT_SHA256 = (
    "sha256:2a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668"
)
FROZEN_PROJECTION_REPOSITORY = Path(
    "/home/ollie/.local/state/orchestrator/es-source-projections/git-sha1/"
    "8f191031f233d50a4d020d8a988036e99487f570"
)
FROZEN_PROJECTION_COMMIT = "8f191031f233d50a4d020d8a988036e99487f570"
FROZEN_PROJECTION_TREE = "e64f3c05f5a0894f41c047d128a9040a2cda6764"
FROZEN_INVENTORY_SHA256 = (
    "sha256:6fc936c54977d9adc7bdbae02bfa69592c55722e5cf5eddbd1b958ee1bc71404"
)
FROZEN_LEAF_COUNT = 1948
FROZEN_NO_CONSUMPTION_EXTERNAL_ROOTS = (
    "/home/ollie/.local/state/orchestrator/es-f1-full/runs",
    "/home/ollie/.local/state/orchestrator/es-f1-full/run-refs",
    "/home/ollie/.local/share/agent-orchestration/es-f1-full/evidence",
)
FROZEN_NO_CONSUMPTION_REPOSITORY_PATHS = (
    "experiments/orc_effectiveness/f1_es/decision-lock.json",
    "experiments/orc_effectiveness/f1_es/controller-package.json",
    "experiments/orc_effectiveness/f1_es/prelaunch-owner-adoption.json",
    "experiments/orc_effectiveness/f1_es/launch-manifest.json",
)
FROZEN_SCHEMA_BINDING_PATHS = (
    ("discovery_input", "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-discovery-input.schema.json"),
    ("preedit_policy", "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.schema.json"),
    ("source_census", "docs/plans/evidence/es-f1-large-scope-refreeze/source-census.schema.json"),
    ("selector_manifest", "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-selector-manifest.schema.json"),
    ("feasibility_capture", "docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-capture-manifest.schema.json"),
    ("post_purge_tombstone", "docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-post-purge-tombstone.schema.json"),
    ("a1_anchor", "docs/plans/evidence/es-f1-large-scope-refreeze/a1-calibration-anchor.schema.json"),
    ("review_adoption", "docs/plans/evidence/es-f1-large-scope-refreeze/task0-review-adoption.schema.json"),
)
_UPSTREAM_SOURCE = {
    "commit": "c081b7b6cd160b3da7031ee325bbf0ade1025d7a",
    "tree": "9193ae2f81116d1bac4cf3cb74395613c1220dbe",
}
_COMPLETED_CLOSURE = (
    {
        "task": "Task 2",
        "commit": "d24c1818d586ee5e082a117f4cf46d85a4fc208e",
        "tree": "5e8f84cbc688a6f56090c546bb177ed4496afc17",
    },
    {
        "task": "Task 3",
        "commit": "0d16ca364c0aeff641232dc0c0c33e445d443623",
        "tree": "ee6d60eb18ce03721898d163ad214b12f2c4098f",
    },
    {
        "task": "Task 4",
        "commit": "d72c6085a3d3fdda23ec3ce48d1dd96a3585529d",
        "tree": "4e576d09b92dd5877f8326ba057127923de8f77e",
    },
)
_TASK_INPUT_PATHS = (
    ("task_profile", "experiments/orc_effectiveness/f1_es/task-profile.json"),
    ("task_seed_manifest", "experiments/orc_effectiveness/f1_es/task-seed-manifest.json"),
)
_GENERATOR_CORE_PATHS = (
    "ptycho_torch/generators/__init__.py",
    "ptycho_torch/generators/cnn.py",
    "ptycho_torch/generators/ffno.py",
    "ptycho_torch/generators/ffno_bottleneck.py",
    "ptycho_torch/generators/fno.py",
    "ptycho_torch/generators/fno_vanilla.py",
    "ptycho_torch/generators/hybrid_resnet.py",
    "ptycho_torch/generators/hybrid_resnet_ffno_bottleneck.py",
    "ptycho_torch/generators/neuralop_uno.py",
    "ptycho_torch/generators/registry.py",
    "ptycho_torch/generators/resnet_components.py",
    "ptycho_torch/generators/schematic_manifest.py",
    "ptycho_torch/generators/schematic_render.py",
    "ptycho_torch/generators/spectral_layers.py",
    "ptycho_torch/generators/spectral_resnet_bottleneck.py",
    "ptycho_torch/generators/spectral_resnet_bottleneck_linear_decoder.py",
    "ptycho_torch/artifact_schema.py",
    "ptycho_torch/model.py",
    "ptycho_torch/model_spec.py",
)
_ORIGINAL_TEN_SELECTOR_PATHS = (
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
)
_MANDATORY_NINETEEN_SELECTOR_PATHS = _ORIGINAL_TEN_SELECTOR_PATHS + (
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
_OLD_NAMED_PRODUCTION_PATHS = _GENERATOR_CORE_PATHS + (
    "ptycho/config/config.py",
    "ptycho_torch/api/trainer_api.py",
    "ptycho_torch/application_factory.py",
    "ptycho_torch/config_bridge.py",
    "ptycho_torch/config_factory.py",
    "ptycho_torch/config_params.py",
    "ptycho_torch/inference.py",
    "ptycho_torch/model_manager.py",
    "ptycho_torch/train.py",
    "ptycho_torch/train_lightning_only.py",
    "ptycho_torch/workflows/components.py",
)
_SPECIFICATION_REVIEW_OMISSION_PATHS = (
    "ptycho_torch/api/api_helper.py",
    "ptycho_torch/api/base_api.py",
    "ptycho_torch/api/mlflow_utils.py",
    "ptycho_torch/beta_modules/model.py",
    "ptycho_torch/lightning_utils.py",
    "ptycho_torch/notebooks/analysis.py",
)
_SOURCE_DOCUMENTED_CONSUMER_PATHS = (
    "ptycho/workflows/backend_selector.py",
    "ptycho_torch/helper.py",
    "ptycho_torch/reassembly.py",
    "scripts/inference/inference.py",
    "scripts/studies/grid_lines_torch_runner.py",
    "scripts/training/train.py",
)
_DIRECT_CDI_STUDY_PATHS = (
    "scripts/studies/ablation/configuration.py",
    "scripts/studies/ablation/gain_calibration.py",
    "scripts/studies/ablation/runtime_checkpoint.py",
    "scripts/studies/ablation/runtime_execution.py",
    "scripts/studies/ablation/runtime_ladder_config.py",
    "scripts/studies/ablation/runtime_ladder_cross_eval.py",
    "scripts/studies/ablation/runtime_ladder_execution.py",
    "scripts/studies/ablation/runtime_ladder_mmap.py",
    "scripts/studies/ablation/runtime_ladder_step_parity_cli.py",
    "scripts/studies/ablation/runtime_reference_execution.py",
    "scripts/studies/ablation/runtime_reference_spec.py",
    "scripts/studies/aligned_ablation_variant_grid.py",
    "scripts/studies/cdi_natural_patch_benchmark.py",
    "scripts/studies/demo_varpro_probe_weighted_reassembly.py",
    "scripts/studies/diagnose_placement.py",
    "scripts/studies/diagnose_reconstruction.py",
    "scripts/studies/diagnose_stitching.py",
    "scripts/studies/flux_sweep_eval.py",
    "scripts/studies/fno_hyperparam_study.py",
    "scripts/studies/grid_lines_compare_wrapper.py",
    "scripts/studies/grid_lines_torch_runner.py",
    "scripts/studies/hybrid_checkpoint_inference.py",
    "scripts/studies/lines128_hybrid_resnet_encoder_fusion_variants.py",
    "scripts/studies/lines128_hybrid_resnet_skip_residual_ablation.py",
    "scripts/studies/nersc_orchestration.py",
    "scripts/studies/position_reassembly_checkpoint_replay.py",
    "scripts/studies/recon_quality_gate.py",
    "scripts/studies/varpro_probe_ablation_runner.py",
)
_SHARED_STUDY_PATHS = (
    "scripts/studies/born_rytov_dt/models.py",
    "scripts/studies/dump_forward_parity_fixtures.py",
    "scripts/studies/openfwi_flatvel_a/models.py",
    "scripts/studies/pdebench_image128/models.py",
    "scripts/studies/pdebench_swe/models.py",
    "scripts/studies/render_hybrid_resnet_schematics.py",
    "scripts/studies/wavebench_shared_encoder/models.py",
)


def _path_union(*groups: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({path for group in groups for path in group}, key=str.encode))


_FROZEN_AUDIT_GROUP_SPECS = (
    ("GENERATOR_PYTHON_PLUS_IDENTITY_CORE", _path_union(_GENERATOR_CORE_PATHS), 6776),
    ("ORIGINAL_TEN_PREEDIT_SELECTORS", _path_union(_ORIGINAL_TEN_SELECTOR_PATHS), 6833),
    ("MANDATORY_NINETEEN_PREEDIT_SELECTORS", _path_union(_MANDATORY_NINETEEN_SELECTOR_PATHS), 11800),
    ("OLD_NAMED_PRODUCTION_CORE", _path_union(_OLD_NAMED_PRODUCTION_PATHS), 16052),
    ("SPECIFICATION_REVIEW_OMISSIONS", _path_union(_SPECIFICATION_REVIEW_OMISSION_PATHS), 5645),
    ("OLD_CORE_PLUS_OMISSIONS", _path_union(_OLD_NAMED_PRODUCTION_PATHS, _SPECIFICATION_REVIEW_OMISSION_PATHS), 21697),
    ("OLD_CORE_PLUS_SOURCE_DOCUMENTED_CONSUMERS", _path_union(_OLD_NAMED_PRODUCTION_PATHS, _SPECIFICATION_REVIEW_OMISSION_PATHS, _SOURCE_DOCUMENTED_CONSUMER_PATHS), 29886),
    ("OLD_CORE_PLUS_DIRECT_CDI_STUDY_CONSUMERS", _path_union(_OLD_NAMED_PRODUCTION_PATHS, _SPECIFICATION_REVIEW_OMISSION_PATHS, _SOURCE_DOCUMENTED_CONSUMER_PATHS, _DIRECT_CDI_STUDY_PATHS), 47515),
    ("OLD_CORE_PLUS_ALL_STUDY_DETECTOR_ROWS", _path_union(_OLD_NAMED_PRODUCTION_PATHS, _SPECIFICATION_REVIEW_OMISSION_PATHS, _SOURCE_DOCUMENTED_CONSUMER_PATHS, _DIRECT_CDI_STUDY_PATHS, _SHARED_STUDY_PATHS), 50318),
)

_SHA1_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MATCH_ID_RE = re.compile(r"match-[0-9a-f]{32}\Z")
_CONSUMER_ID_RE = re.compile(r"consumer-[0-9a-f]{32}\Z")

_GIT_KEYS = frozenset({"executable", "version", "sha256", "object_controls"})
_PROJECTION_KEYS = frozenset(
    {"repository", "commit", "tree", "inventory_sha256", "leaf_count"}
)
_PRODUCER_KEYS = frozenset({"path", "sha256"})
_DISCOVERY_INPUT_KEYS = frozenset(
    {
        "schema_version",
        "authority_status",
        "git",
        "projection",
        "detectors",
        "responsibilities",
        "provider_visible_pytest_selectors",
    }
)
_DETECTOR_KEYS = frozenset(
    {"detector_id", "version", "language", "path_globs", "anchors"}
)
_ANCHOR_KEYS = frozenset(
    {"anchor_id", "form", "pattern", "responsibility_ids"}
)
_RESPONSIBILITY_KEYS = frozenset({"responsibility_id", "anchors"})
_DISCOVERY_SELECTOR_KEYS = frozenset(
    {"selector_id", "ordinal", "pytest_module_path"}
)
_SPAN_KEYS = frozenset({"line_start", "column_start", "line_end", "column_end"})
_CONSUMER_CANDIDATE_KEYS = frozenset(
    {
        "consumer_id",
        "match_id",
        "caller_path",
        "caller_object_id",
        "span",
        "detector_id",
        "detector_version",
        "anchor_id",
        "callee_or_dispatch_form",
        "responsibility_ids",
    }
)
_CONSUMER_POLICY_KEYS = frozenset(
    {
        "consumer_id",
        "match_id",
        "proposed_disposition",
        "required_proof_kind",
        "selector_id",
        "witness_kind",
        "coverage_status",
        "coverage_witness_ids",
    }
)
_POLICY_KEYS = frozenset(
    {
        "schema_version",
        "discovery",
        "git",
        "projection",
        "schema_bindings",
        "lineage",
        "detectors",
        "responsibilities",
        "consumer_policies",
        "selector_policy",
        "audit_groups",
        "legacy_bypass_consumer_ids",
        "no_consumption",
        "a1",
        "witness_observability_reviews",
        "record_sha256",
    }
)
_POLICY_CANDIDATE_BODY_KEYS = _POLICY_KEYS - frozenset(
    {"witness_observability_reviews", "record_sha256"}
)
_COMPLETE_POLICY_CANDIDATE_KEYS = frozenset(
    {"schema_version", "authority_status", "input_bindings", "counts", "policy_body"}
)
_COMPLETE_POLICY_INPUT_BINDING_KEYS = frozenset(
    {
        "discovery_input_sha256",
        "discovery_output_sha256",
        "observation_candidates_sha256",
        "reviewed_dispositions_sha256",
        "producer_sha256",
        "proof_runner_sha256",
        "projection_tree",
        "candidate_set_sha256",
        "no_consumption_captured_at",
        "a1_evidence_root",
    }
)
_COMPLETE_POLICY_COUNT_KEYS = frozenset(
    {"total", "observable", "required", "inherited", "open"}
)
_WITNESS_REVIEWS_KEYS = frozenset(
    {
        "plan",
        "plan_specification_review",
        "plan_quality_review",
        "implementation_review",
    }
)
_WITNESS_PLAN_PATH = (
    "docs/plans/2026-08-04-es-f1-witness-observability-correction-plan.md"
)
_WITNESS_PLAN_SPEC_REVIEW_PATH = (
    "artifacts/review/es-f1-witness-observability-plan-spec-review.json"
)
_WITNESS_PLAN_QUALITY_REVIEW_PATH = (
    "artifacts/review/es-f1-witness-observability-plan-quality-review.json"
)
_WITNESS_IMPLEMENTATION_REVIEW_PATH = (
    "artifacts/review/es-f1-witness-observability-implementation-review.json"
)
_WITNESS_IMPLEMENTATION_CANDIDATE_PATHS = (
    "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.schema.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-selector-manifest.schema.json",
    "docs/plans/evidence/es-f1-large-scope-refreeze/source-census.schema.json",
    "scripts/experiments/es/source_census.py",
    "scripts/experiments/es/boundary_proofs.py",
    "scripts/experiments/es/projection.py",
    "tests/experiments/test_es_source_census.py",
    "tests/experiments/test_es_boundary_proofs.py",
    "tests/experiments/test_es_f1_projection.py",
)
_SELECTOR_POLICY_KEYS = frozenset(
    {
        "sampling_rule",
        "pytest_carrier",
        "provider_visible_pytest_selectors",
        "controller_only_proof_selectors",
        "coverage_witness_specs",
        "desired_state_proof_specs",
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
_WITNESS_SPEC_KEYS = frozenset(
    {
        "witness_id",
        "witness_kind",
        "selector_id",
        "consumer_id",
        "required_proof_kind",
        "spec",
    }
)
_DESIRED_PROOF_SPEC_KEYS = frozenset(
    {"proof_spec_id", "witness_id", "proof_kind", "expected_result"}
)
_NO_CONSUMPTION_KEYS = frozenset(
    {"captured_at", "external_roots", "repository_paths", "observation_sha256"}
)
_A1_KEYS = frozenset({"evidence_root", "members", "metric"})
_A1_MEMBER_KEYS = frozenset({"member_id", "path", "byte_count", "sha256"})
_A1_METRIC_KEYS = frozenset(
    {
        "metric_version",
        "git_executable",
        "git_version",
        "git_sha256",
        "diff_controls",
        "implementation_additions",
        "implementation_deletions",
        "candidate_postimage_physical_lines",
    }
)
_DIFF_CONTROLS = [
    "--no-ext-diff",
    "--no-textconv",
    "--diff-algorithm=histogram",
    "--find-renames=100%",
    "--find-copies=100%",
    "--find-copies-harder",
]
_BASELINE_KEYS = frozenset(
    {
        "schema_version",
        "runner_sha256",
        "pre_tree",
        "post_tree",
        "aggregate_pytest_argv",
        "collected_node_ids",
        "collected_node_sha256",
        "collection_total",
        "outcomes",
        "origin_isolation",
        "selector_results",
        "controller_selector_results",
        "witness_results",
    }
)
_WITNESS_RESULT_KEYS = frozenset(
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
_RUNTIME_WITNESS_RESULT_KEYS = _WITNESS_RESULT_KEYS | frozenset({"source_event"})
_CONTROLLER_SELECTOR_RESULT_KEYS = frozenset(
    {
        "selector_id",
        "execution_kind",
        "argv",
        "collected_node_ids",
        "collected_node_sha256",
        "collection_total",
        "outcomes",
        "origin_isolation",
        "trace_sha256",
        "coverage_witness_ids",
        "coverage_witness_node_outcomes",
    }
)
_SOURCE_EVENT_COMMON_KEYS = frozenset(
    {
        "event_kind",
        "phase",
        "attribution",
        "consumer_path",
        "caller_object_id",
        "span",
        "hit_count",
    }
)
_SOURCE_EVENT_PAYLOAD_KEYS = frozenset(
    {"opcode_exact_span", "import_alias_opcode", "callable_entry"}
)
_RUNTIME_WITNESS_KINDS = frozenset(
    {"pytest_runtime", "controller_pytest_runtime", "runtime_probe"}
)
_OPCODE_EXACT_SPAN_OPNAMES = frozenset(
    {
        "CALL",
        "CALL_FUNCTION_EX",
        "LOAD_NAME",
        "LOAD_GLOBAL",
        "LOAD_FAST",
        "LOAD_DEREF",
        "LOAD_CLASSDEREF",
        "STORE_NAME",
        "STORE_GLOBAL",
        "STORE_FAST",
        "STORE_DEREF",
        "DELETE_NAME",
        "DELETE_GLOBAL",
        "DELETE_FAST",
        "DELETE_DEREF",
        "LOAD_ATTR",
        "LOAD_METHOD",
        "STORE_ATTR",
        "DELETE_ATTR",
        "LOAD_CONST",
    }
)
_DISPOSITION_PROOF = {
    "route_through_boundary": "boundary_runtime",
    "compatibility_adapter": "non_cdi_static",
    "remove": "reference_absence",
}
_COVERAGE_STATUSES = frozenset({"required", "inherited", "open"})
_WITNESS_KINDS = frozenset(
    {"pytest_runtime", "controller_pytest_runtime", "static_ast", "runtime_probe"}
)
_SAMPLING_RULE = (
    "first_observable_per_provider_and_disposition_witness_class_"
    "in_discovery_order.v1"
)
_CANDIDATE_IDENTITY_KEYS = frozenset(
    {
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
    }
)
_DRAFT_DECISION_KEYS = _CANDIDATE_IDENTITY_KEYS | frozenset(
    {
        "authority_status",
        "baseline_expected_to_pass",
        "coverage_witness_ids",
        "proposed_disposition",
        "required_proof_kind",
        "selector_id",
        "spec_strategy",
        "witness_kind",
    }
)
_REVIEWED_DISPOSITIONS_KEYS = frozenset(
    {
        "schema_version",
        "authority_status",
        "source_discovery",
        "mapping_contract",
        "detector_findings",
        "ambiguous_cases",
        "controller_selector_recommendations",
        "path_decisions",
        "consumer_decisions",
        "counts",
        "candidate_sha256",
    }
)
_REVIEWED_SOURCE_DISCOVERY_KEYS = frozenset(
    {
        "path",
        "raw_sha256",
        "discovery_input_sha256",
        "candidate_set_sha256",
        "consumer_candidate_count",
        "caller_path_count",
        "leaf_count",
        "projection_repository",
        "projection_commit",
        "projection_tree",
    }
)
_REVIEWED_MAPPING_KEYS = frozenset(
    {
        "consumer_order_preserved_from_discovery",
        "default_disposition",
        "disposition_to_proof",
        "every_discovered_consumer_explicitly_enumerated",
        "every_discovered_path_explicitly_enumerated",
        "path_set_equality_verified",
        "proof_results_claimed",
        "selector_node_feasibility_claimed",
    }
)
_REVIEWED_PATH_DECISION_KEYS = frozenset(
    {
        "anchor_ids",
        "authority_status",
        "caller_object_id",
        "caller_path",
        "candidate_count",
        "consumer_ids",
        "rationale_code",
        "recommended_disposition",
        "recommended_selector_ids",
        "recommended_witness_kinds",
        "required_proof_kind",
        "source_audit",
    }
)
_OBSERVATION_ROW_KEYS = _CANDIDATE_IDENTITY_KEYS | frozenset(
    {
        "proposed_disposition",
        "required_proof_kind",
        "selector_id",
        "witness_kind",
        "observation_status",
        "reason_code",
        "executable_choices",
    }
)
_OBSERVATION_CHOICE_KEYS = frozenset(
    {"selector_id", "proof_kind", "witness_kind", "spec"}
)
_CONTROLLER_CANDIDATE_KEYS = (
    _CONTROLLER_SELECTOR_KEYS - frozenset({"coverage_witness_ids"})
) | frozenset({"projection_bindings"})
_OBJECT_CONTROLS = [
    "rev-parse --verify <commit>^{commit}",
    "rev-parse --verify <commit>^{tree}",
    "ls-tree -rz -r --full-tree <commit>",
    "cat-file --batch",
]


class SourceCensusError(ValueError):
    """A Task-0 source-census input or relationship fails closed."""

    def __init__(self, code: str, value: object, detail: str) -> None:
        super().__init__(f"{code}: {detail}: {value!r}")
        self.code = code
        self.value = value
        self.detail = detail


def _reference_calibration_module() -> Any:
    try:
        return importlib.import_module("scripts.experiments.es.reference_calibration")
    except ModuleNotFoundError as exc:
        if exc.name != "scripts":
            raise
        return importlib.import_module("reference_calibration")


def _boundary_proofs_module() -> Any:
    try:
        return importlib.import_module("scripts.experiments.es.boundary_proofs")
    except ModuleNotFoundError as exc:
        if exc.name != "scripts":
            raise
        return importlib.import_module("boundary_proofs")


def _feasibility_proofs_module() -> Any:
    try:
        return importlib.import_module("scripts.experiments.es.feasibility_proofs")
    except ModuleNotFoundError as exc:
        if exc.name != "scripts":
            raise
        return importlib.import_module("feasibility_proofs")


def canonical_json_bytes(value: object) -> bytes:
    shared = _reference_calibration_module().canonical_json_bytes

    return shared(value)


def canonical_record_body_bytes(record: Mapping[str, object]) -> bytes:
    shared = _reference_calibration_module().canonical_record_body_bytes

    return shared(record)


def compute_record_sha256(record: Mapping[str, object]) -> str:
    shared = _reference_calibration_module().compute_record_sha256

    return shared(record)


def validate_record_sha256(record: Mapping[str, object]) -> None:
    shared = _reference_calibration_module().validate_record_sha256

    shared(record)


def raw_sha256(payload: bytes) -> str:
    if not isinstance(payload, bytes):
        raise TypeError("raw_sha256 requires bytes")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _regular_file_identity(identity: os.stat_result) -> tuple[int, ...]:
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


def _stable_regular_file_under_root(
    root: Path,
    relative: str,
    *,
    error_code: str,
    label: str,
) -> bytes:
    """Read one regular file without following any root-relative symlink."""

    root_path = _canonical_absolute_path(os.fspath(root), label=f"{label} root")
    relative_text = _relative_path(relative, label=f"{label} path")
    parts = PurePosixPath(relative_text).parts
    if not all(
        hasattr(os, flag)
        for flag in ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    ):
        _fail(
            error_code,
            os.fspath(root_path / relative_text),
            f"{label} cannot be read safely",
        )

    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        file_flags |= os.O_NONBLOCK
    directory_descriptors: list[int] = []
    file_descriptor: int | None = None
    candidate = root_path / relative_text
    try:
        root_descriptor = os.open(root_path, directory_flags)
        directory_descriptors.append(root_descriptor)
        if not stat.S_ISDIR(os.fstat(root_descriptor).st_mode):
            _fail(error_code, os.fspath(candidate), f"{label} root is not a directory")
        for component in parts[:-1]:
            descriptor = os.open(
                component,
                directory_flags,
                dir_fd=directory_descriptors[-1],
            )
            directory_descriptors.append(descriptor)
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                _fail(
                    error_code,
                    os.fspath(candidate),
                    f"{label} ancestor is not a real directory",
                )

        file_descriptor = os.open(
            parts[-1],
            file_flags,
            dir_fd=directory_descriptors[-1],
        )
        before = os.fstat(file_descriptor)
        before_identity = _regular_file_identity(before)
        if not stat.S_ISREG(before.st_mode):
            _fail(error_code, os.fspath(candidate), f"{label} is not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(file_descriptor, 1024 * 1024):
            chunks.append(chunk)
        raw = b"".join(chunks)
        after = os.fstat(file_descriptor)
        pathname_identity = os.stat(
            parts[-1],
            dir_fd=directory_descriptors[-1],
            follow_symlinks=False,
        )
        if (
            len(raw) != before.st_size
            or _regular_file_identity(after) != before_identity
            or _regular_file_identity(pathname_identity) != before_identity
        ):
            _fail(error_code, os.fspath(candidate), f"{label} changed while being read")
        return raw
    except SourceCensusError:
        raise
    except OSError as exc:
        raise SourceCensusError(
            error_code,
            os.fspath(candidate),
            f"{label} is missing, unreadable, or reached through a symlink",
        ) from exc
    finally:
        if file_descriptor is not None:
            try:
                os.close(file_descriptor)
            except OSError:
                pass
        for descriptor in reversed(directory_descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def sequence_sha256(values: Sequence[str]) -> str:
    return raw_sha256(canonical_json_bytes(list(values)))


def current_schema_bindings() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for role, relative in FROZEN_SCHEMA_BINDING_PATHS:
        path = REPOSITORY_ROOT / relative
        try:
            metadata = path.lstat()
            payload = path.read_bytes()
        except OSError as exc:
            raise SourceCensusError(
                "schema_binding_invalid", relative, "published schema is unreadable"
            ) from exc
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            _fail(
                "schema_binding_invalid",
                relative,
                "published schema must be a regular non-symlink file",
            )
        rows.append(
            {
                "role": role,
                "path": relative,
                "byte_count": len(payload),
                "sha256": raw_sha256(payload),
            }
        )
    return rows


def _require_published_schema_path(value: object, *, role: str) -> Path:
    expected_by_role = dict(FROZEN_SCHEMA_BINDING_PATHS)
    if role not in expected_by_role:
        _fail("schema_authority_invalid", role, "unknown published schema role")
    supplied = Path(_text(value, label=f"{role} schema path"))
    if not supplied.is_absolute():
        supplied = REPOSITORY_ROOT / supplied
    expected = REPOSITORY_ROOT / expected_by_role[role]
    try:
        supplied_resolved = supplied.resolve(strict=True)
        expected_resolved = expected.resolve(strict=True)
    except OSError as exc:
        raise SourceCensusError(
            "schema_authority_invalid", str(supplied), "schema path is unreadable"
        ) from exc
    if supplied_resolved != expected_resolved or supplied.is_symlink():
        _fail(
            "schema_authority_invalid",
            str(supplied),
            "authority CLI requires the exact published schema path",
        )
    return expected_resolved


def current_lineage_bindings() -> dict[str, object]:
    task_inputs: list[dict[str, object]] = []
    for role, relative in _TASK_INPUT_PATHS:
        path = REPOSITORY_ROOT / relative
        try:
            metadata = path.lstat()
            payload = path.read_bytes()
        except OSError as exc:
            raise SourceCensusError(
                "lineage_binding_invalid", relative, "task input is unreadable"
            ) from exc
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            _fail(
                "lineage_binding_invalid",
                relative,
                "task input must be a regular non-symlink file",
            )
        task_inputs.append(
            {
                "role": role,
                "path": relative,
                "byte_count": len(payload),
                "sha256": raw_sha256(payload),
            }
        )
    return {
        "upstream_source": copy.deepcopy(_UPSTREAM_SOURCE),
        "completed_closure": copy.deepcopy(list(_COMPLETED_CLOSURE)),
        "task_inputs": task_inputs,
    }


def _fail(code: str, value: object, detail: str) -> NoReturn:
    raise SourceCensusError(code, value, detail)


def _mapping(
    value: object, *, keys: frozenset[str] | None = None, label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("source_census_shape_invalid", value, f"{label} must be an object")
    if keys is not None and set(value) != keys:
        _fail(
            "source_census_shape_invalid",
            sorted(value),
            f"{label} keys must be exactly {sorted(keys)}",
        )
    return value


def _list(value: object, *, label: str, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        _fail(
            "source_census_shape_invalid",
            value,
            f"{label} must be {'a nonempty' if nonempty else 'an'} array",
        )
    return value


def _text(value: object, *, label: str, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        _fail("source_census_shape_invalid", value, f"{label} must be text")
    return value


def _integer(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(
            "source_census_shape_invalid",
            value,
            f"{label} must be an integer >= {minimum}",
        )
    return value


def _sha1(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _SHA1_RE.fullmatch(text) is None:
        _fail("source_census_shape_invalid", value, f"{label} must be Git SHA-1")
    return text


def _sha256(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    if _SHA256_RE.fullmatch(text) is None:
        _fail("source_census_shape_invalid", value, f"{label} must be SHA-256")
    return text


def _unique_texts(value: object, *, label: str, nonempty: bool = True) -> list[str]:
    rows = [_text(row, label=f"{label}[]") for row in _list(value, label=label)]
    if (nonempty and not rows) or len(rows) != len(set(rows)):
        _fail(
            "source_census_shape_invalid",
            rows,
            f"{label} must contain ordered unique text",
        )
    return rows


def _texts(value: object, *, label: str, nonempty: bool = False) -> list[str]:
    rows = [_text(row, label=f"{label}[]", nonempty=False) for row in _list(value, label=label)]
    if nonempty and not rows:
        _fail("source_census_shape_invalid", rows, f"{label} must be nonempty")
    return rows


def _relative_path(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    pure = PurePosixPath(text)
    if (
        pure.is_absolute()
        or pure.as_posix() != text
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\\" in text
        or "\n" in text
        or "\r" in text
    ):
        _fail("source_census_path_invalid", text, f"{label} is not canonical relative text")
    return text


def _canonical_absolute_path(value: object, *, label: str) -> Path:
    text = _text(value, label=label)
    path = Path(text)
    if not path.is_absolute() or os.path.normpath(text) != text:
        _fail("source_census_path_invalid", value, f"{label} is not canonical absolute")
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise SourceCensusError(
            "source_census_path_invalid", value, f"{label} cannot be resolved"
        ) from exc
    if resolved != path:
        _fail("source_census_path_invalid", value, f"{label} is not canonical absolute")
    return path


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "XDG_CONFIG_HOME": "/nonexistent",
    }


def _validate_git_contract(value: object) -> dict[str, Any]:
    git = _mapping(value, keys=_GIT_KEYS, label="git")
    executable = Path(_text(git["executable"], label="git.executable"))
    if executable != PINNED_GIT or not executable.is_absolute():
        _fail("git_executable_mismatch", str(executable), "Git executable is not pinned")
    if _text(git["version"], label="git.version") != PINNED_GIT_VERSION:
        _fail("git_version_mismatch", git["version"], "Git version is not pinned")
    if _sha256(git["sha256"], label="git.sha256") != PINNED_GIT_SHA256:
        _fail("git_digest_mismatch", git["sha256"], "Git digest is not pinned")
    try:
        actual_digest = raw_sha256(executable.read_bytes())
        version = subprocess.run(
            [str(executable), "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        ).stdout.decode("ascii", errors="strict").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        raise SourceCensusError(
            "git_executable_unreadable", str(executable), "pinned Git is unreadable"
        ) from exc
    if actual_digest != git["sha256"] or version != git["version"]:
        _fail(
            "git_identity_mismatch",
            {"version": version, "sha256": actual_digest},
            "live Git identity differs from the record",
        )
    if git["object_controls"] != _OBJECT_CONTROLS:
        _fail(
            "git_object_controls_mismatch",
            git["object_controls"],
            "Git object controls are not the frozen ordered contract",
        )
    return git


def _canonical_repository(value: object) -> Path:
    text = _text(value, label="projection.repository")
    repository = Path(text)
    try:
        metadata = repository.lstat()
        resolved = repository.resolve(strict=True)
    except OSError as exc:
        raise SourceCensusError(
            "projection_repository_unreadable", text, "projection repository is unreadable"
        ) from exc
    if (
        not repository.is_absolute()
        or resolved != repository
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        _fail(
            "projection_repository_invalid",
            text,
            "projection repository must be a canonical real absolute directory",
        )
    return repository


def _run_git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    try:
        return subprocess.run(
            [str(PINNED_GIT), f"--git-dir={repository}", *arguments],
            cwd="/",
            env=_git_environment(),
            check=True,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SourceCensusError(
            "projection_git_failed",
            list(arguments),
            "pinned Git object operation failed",
        ) from exc


def _parse_inventory(raw: bytes) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, raw_path = record.split(b"\t", 1)
            raw_mode, raw_type, raw_oid = header.split(b" ", 2)
            path = raw_path.decode("utf-8", errors="strict")
            mode = raw_mode.decode("ascii", errors="strict")
            object_type = raw_type.decode("ascii", errors="strict")
            oid = raw_oid.decode("ascii", errors="strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise SourceCensusError(
                "projection_inventory_invalid", record, "Git ls-tree row is malformed"
            ) from exc
        _relative_path(path, label="projection leaf path")
        if object_type != "blob" or mode not in {"100644", "100755", "120000"}:
            _fail(
                "projection_inventory_invalid",
                {"mode": mode, "object_type": object_type, "path": path},
                "projection leaf is not a supported blob",
            )
        _sha1(oid, label="projection leaf object_id")
        rows.append({"mode": mode, "object_type": object_type, "object_id": oid, "path": path})
    rows.sort(key=lambda row: row["path"].encode("utf-8"))
    paths = [row["path"] for row in rows]
    if len(paths) != len(set(paths)):
        _fail("projection_inventory_invalid", paths, "projection paths are duplicated")
    return rows


def _read_blobs(repository: Path, object_ids: Sequence[str]) -> dict[str, bytes]:
    unique = list(dict.fromkeys(object_ids))
    if not unique:
        return {}
    raw = _run_git(
        repository,
        "cat-file",
        "--batch",
        input_bytes=("\n".join(unique) + "\n").encode("ascii"),
    )
    offset = 0
    result: dict[str, bytes] = {}
    for expected_oid in unique:
        newline = raw.find(b"\n", offset)
        if newline < 0:
            _fail("projection_blob_batch_invalid", expected_oid, "missing batch header")
        header = raw[offset:newline]
        offset = newline + 1
        try:
            raw_oid, object_type, raw_size = header.split(b" ", 2)
            oid = raw_oid.decode("ascii", errors="strict")
            size = int(raw_size)
        except (UnicodeDecodeError, ValueError) as exc:
            raise SourceCensusError(
                "projection_blob_batch_invalid", header, "malformed batch header"
            ) from exc
        if oid != expected_oid or object_type != b"blob" or size < 0:
            _fail(
                "projection_blob_batch_invalid",
                header,
                "batch header does not match requested blob",
            )
        payload = raw[offset : offset + size]
        offset += size
        if len(payload) != size or raw[offset : offset + 1] != b"\n":
            _fail("projection_blob_batch_invalid", oid, "batch payload is truncated")
        offset += 1
        actual_oid = hashlib.sha1(
            b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
        ).hexdigest()
        if actual_oid != expected_oid:
            _fail(
                "projection_blob_digest_mismatch",
                {"expected": expected_oid, "actual": actual_oid},
                "batch payload does not hash to the requested blob ID",
            )
        result[oid] = payload
    if offset != len(raw):
        _fail("projection_blob_batch_invalid", len(raw) - offset, "unexpected trailing bytes")
    return result


def _validate_projection(value: object) -> dict[str, Any]:
    projection = _mapping(value, keys=_PROJECTION_KEYS, label="projection")
    _canonical_repository(projection["repository"])
    _sha1(projection["commit"], label="projection.commit")
    _sha1(projection["tree"], label="projection.tree")
    _sha256(projection["inventory_sha256"], label="projection.inventory_sha256")
    _integer(projection["leaf_count"], label="projection.leaf_count", minimum=1)
    return projection


def _validate_frozen_projection_authority(value: object) -> dict[str, Any]:
    projection = _validate_projection(value)
    expected = {
        "repository": str(FROZEN_PROJECTION_REPOSITORY),
        "commit": FROZEN_PROJECTION_COMMIT,
        "tree": FROZEN_PROJECTION_TREE,
        "inventory_sha256": FROZEN_INVENTORY_SHA256,
        "leaf_count": FROZEN_LEAF_COUNT,
    }
    if projection != expected:
        _fail(
            "projection_authority_mismatch",
            projection,
            "authority CLI accepts only the frozen source projection",
        )
    return projection


def _validate_discovery_input(value: object) -> dict[str, Any]:
    record = _mapping(value, keys=_DISCOVERY_INPUT_KEYS, label="discovery input")
    if record["schema_version"] != "es_f1_preedit_discovery_input.v1":
        _fail("discovery_input_version_invalid", record["schema_version"], "unsupported version")
    if record["authority_status"] != "non_authoritative_discovery_input":
        _fail(
            "discovery_input_authority_invalid",
            record["authority_status"],
            "discovery input cannot grant authority",
        )
    _validate_git_contract(record["git"])
    _validate_projection(record["projection"])

    anchor_ids: set[str] = set()
    responsibility_refs: dict[str, set[str]] = {}
    detector_ids: set[str] = set()
    for detector_value in _list(record["detectors"], label="detectors", nonempty=True):
        detector = _mapping(detector_value, keys=_DETECTOR_KEYS, label="detector")
        detector_id = _text(detector["detector_id"], label="detector.detector_id")
        if detector_id in detector_ids:
            _fail("detector_duplicate", detector_id, "detector IDs must be unique")
        detector_ids.add(detector_id)
        _text(detector["version"], label="detector.version")
        language = detector["language"]
        if language not in {"python_ast", "text_regex"}:
            _fail("detector_language_invalid", language, "unsupported detector language")
        _unique_texts(detector["path_globs"], label="detector.path_globs")
        for anchor_value in _list(detector["anchors"], label="detector.anchors", nonempty=True):
            anchor = _mapping(anchor_value, keys=_ANCHOR_KEYS, label="detector anchor")
            anchor_id = _text(anchor["anchor_id"], label="anchor.anchor_id")
            if anchor_id in anchor_ids:
                _fail("anchor_duplicate", anchor_id, "anchor IDs must be globally unique")
            anchor_ids.add(anchor_id)
            form = anchor["form"]
            allowed = (
                {"import", "call", "name", "attribute", "string"}
                if language == "python_ast"
                else {"regex"}
            )
            if form not in allowed:
                _fail("anchor_form_invalid", form, "anchor form does not match language")
            pattern = _text(anchor["pattern"], label="anchor.pattern")
            if form == "regex":
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise SourceCensusError(
                        "anchor_regex_invalid", pattern, "regex does not compile"
                    ) from exc
            responsibility_refs[anchor_id] = set(
                _unique_texts(anchor["responsibility_ids"], label="anchor.responsibility_ids")
            )

    responsibility_ids: set[str] = set()
    declared_anchor_ids: set[str] = set()
    for responsibility_value in _list(
        record["responsibilities"], label="responsibilities", nonempty=True
    ):
        responsibility = _mapping(
            responsibility_value, keys=_RESPONSIBILITY_KEYS, label="responsibility"
        )
        responsibility_id = _text(
            responsibility["responsibility_id"], label="responsibility.responsibility_id"
        )
        if responsibility_id in responsibility_ids:
            _fail("responsibility_duplicate", responsibility_id, "responsibility IDs repeat")
        responsibility_ids.add(responsibility_id)
        ids = _unique_texts(responsibility["anchors"], label="responsibility.anchors")
        declared_anchor_ids.update(ids)
        for anchor_id in ids:
            if responsibility_id not in responsibility_refs.get(anchor_id, set()):
                _fail(
                    "responsibility_anchor_mismatch",
                    {"responsibility_id": responsibility_id, "anchor_id": anchor_id},
                    "responsibility/anchor backreferences disagree",
                )
    if declared_anchor_ids != anchor_ids or any(
        not ids <= responsibility_ids for ids in responsibility_refs.values()
    ):
        _fail(
            "responsibility_anchor_mismatch",
            sorted(anchor_ids ^ declared_anchor_ids),
            "responsibility and anchor domains are not exact",
        )

    selector_ids: set[str] = set()
    selectors = _list(
        record["provider_visible_pytest_selectors"],
        label="provider_visible_pytest_selectors",
        nonempty=True,
    )
    for ordinal, selector_value in enumerate(selectors, 1):
        selector = _mapping(
            selector_value, keys=_DISCOVERY_SELECTOR_KEYS, label="discovery selector"
        )
        selector_id = _text(selector["selector_id"], label="selector.selector_id")
        if selector_id in selector_ids or selector["ordinal"] != ordinal:
            _fail(
                "selector_order_invalid",
                selector,
                "selector IDs must be unique with contiguous one-based ordinals",
            )
        selector_ids.add(selector_id)
        _relative_path(selector["pytest_module_path"], label="selector.pytest_module_path")
    return record


def _resolve_dotted(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _resolve_dotted(node.value, aliases)
        return None if base is None else f"{base}.{node.attr}"
    return None


def _span(node: ast.AST) -> dict[str, int]:
    return {
        "line_start": int(getattr(node, "lineno", 0)),
        "column_start": int(getattr(node, "col_offset", 0)),
        "line_end": int(getattr(node, "end_lineno", getattr(node, "lineno", 0))),
        "column_end": int(getattr(node, "end_col_offset", getattr(node, "col_offset", 0))),
    }


def _stable_id(prefix: str, value: Mapping[str, object]) -> str:
    return prefix + hashlib.sha256(canonical_json_bytes(value)).hexdigest()[:32]


def _ast_occurrences(text: str) -> tuple[ast.AST, dict[str, str]]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text)
    except SyntaxError as exc:
        raise SourceCensusError(
            "detector_python_syntax_invalid",
            {"line": exc.lineno, "offset": exc.offset},
            "Python source could not be parsed",
        ) from exc
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                full = f"{module}.{alias.name}" if module else alias.name
                aliases[alias.asname or alias.name] = full
    return tree, aliases


def _match_python_anchor(
    tree: ast.AST, aliases: Mapping[str, str], anchor: Mapping[str, Any]
) -> list[tuple[ast.AST, str]]:
    pattern = str(anchor["pattern"])
    form = anchor["form"]
    matches: list[tuple[ast.AST, str]] = []

    def matches_symbol(value: str, *, authored: str | None = None) -> bool:
        return (
            value == pattern
            or value.endswith(f".{pattern}")
            or authored == pattern
        )

    for node in ast.walk(tree):
        if form == "import":
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == pattern or alias.name.startswith(f"{pattern}."):
                        matches.append((alias, alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    full = f"{module}.{alias.name}" if module else alias.name
                    if (
                        module == pattern
                        or module.startswith(f"{pattern}.")
                        or full == pattern
                    ):
                        matches.append((alias, full))
        elif form == "call" and isinstance(node, ast.Call):
            dotted = _resolve_dotted(node.func, aliases)
            authored = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else None
            )
            if dotted is not None and matches_symbol(dotted, authored=authored):
                matches.append((node, dotted))
        elif form == "name" and isinstance(node, ast.Name):
            dotted = aliases.get(node.id, node.id)
            if matches_symbol(dotted, authored=node.id):
                matches.append((node, dotted))
        elif form == "attribute" and isinstance(node, ast.Attribute):
            dotted = _resolve_dotted(node, aliases)
            if dotted is not None and matches_symbol(dotted, authored=node.attr):
                matches.append((node, dotted))
        elif form == "string" and isinstance(node, ast.Constant):
            if isinstance(node.value, str) and node.value == pattern:
                matches.append((node, node.value))
    return matches


def _regex_span(text: str, match: re.Match[str]) -> dict[str, int]:
    before = text[: match.start()]
    line_start = before.count("\n") + 1
    column_start = len(before.rsplit("\n", 1)[-1])
    matched = match.group(0)
    line_end = line_start + matched.count("\n")
    column_end = (
        len(matched.rsplit("\n", 1)[-1])
        if "\n" in matched
        else column_start + len(matched)
    )
    return {
        "line_start": line_start,
        "column_start": column_start,
        "line_end": line_end,
        "column_end": column_end,
    }


def _candidate(
    *,
    path: str,
    object_id: str,
    span: Mapping[str, int],
    detector: Mapping[str, Any],
    anchor: Mapping[str, Any],
    form: str,
) -> dict[str, object]:
    identity = {
        "path": path,
        "object_id": object_id,
        "span": dict(span),
        "detector_id": detector["detector_id"],
        "detector_version": detector["version"],
        "anchor_id": anchor["anchor_id"],
        "callee_or_dispatch_form": form,
    }
    match_id = _stable_id("match-", identity)
    consumer_id = _stable_id("consumer-", {"match_id": match_id, **identity})
    return {
        "consumer_id": consumer_id,
        "match_id": match_id,
        "caller_path": path,
        "caller_object_id": object_id,
        "span": dict(span),
        "detector_id": detector["detector_id"],
        "detector_version": detector["version"],
        "anchor_id": anchor["anchor_id"],
        "callee_or_dispatch_form": form,
        "responsibility_ids": list(anchor["responsibility_ids"]),
    }


def _discover_rows(
    inventory_rows: Sequence[Mapping[str, str]],
    blobs: Mapping[str, bytes],
    detectors: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    leaves: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    for inventory in inventory_rows:
        path = inventory["path"]
        payload = blobs[inventory["object_id"]]
        is_symlink = inventory["mode"] == "120000"
        if is_symlink:
            text = None
        else:
            try:
                text = payload.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                text = None
        outcomes: list[dict[str, object]] = []
        leaf_candidates: list[dict[str, object]] = []
        for detector in detectors:
            detector_matches: list[dict[str, object]] = []
            applies = any(
                fnmatch.fnmatchcase(path, pattern)
                for pattern in detector["path_globs"]
            )
            if applies and text is not None:
                if detector["language"] == "python_ast":
                    tree, aliases = _ast_occurrences(text)
                    for anchor in detector["anchors"]:
                        for node, form in _match_python_anchor(tree, aliases, anchor):
                            detector_matches.append(
                                _candidate(
                                    path=path,
                                    object_id=inventory["object_id"],
                                    span=_span(node),
                                    detector=detector,
                                    anchor=anchor,
                                    form=form,
                                )
                            )
                else:
                    for anchor in detector["anchors"]:
                        for match in re.finditer(anchor["pattern"], text):
                            detector_matches.append(
                                _candidate(
                                    path=path,
                                    object_id=inventory["object_id"],
                                    span=_regex_span(text, match),
                                    detector=detector,
                                    anchor=anchor,
                                    form=match.group(0),
                                )
                            )
            detector_matches.sort(
                key=lambda row: (
                    row["span"]["line_start"],
                    row["span"]["column_start"],
                    row["anchor_id"],
                    row["match_id"],
                )
            )
            outcomes.append(
                {
                    "detector_id": detector["detector_id"],
                    "version": detector["version"],
                    "match_ids": [row["match_id"] for row in detector_matches],
                }
            )
            leaf_candidates.extend(detector_matches)
        leaf_candidates.sort(
            key=lambda row: (
                row["span"]["line_start"],
                row["span"]["column_start"],
                row["detector_id"],
                row["anchor_id"],
                row["match_id"],
            )
        )
        match_ids = [row["match_id"] for row in leaf_candidates]
        if len(match_ids) != len(set(match_ids)):
            _fail("detector_match_duplicate", path, "detectors emitted duplicate match IDs")
        responsibility_ids = sorted(
            {
                responsibility_id
                for row in leaf_candidates
                for responsibility_id in row["responsibility_ids"]
            }
        )
        leaf: dict[str, object] = {
            "path": path,
            "mode": inventory["mode"],
            "object_type": inventory["object_type"],
            "object_id": inventory["object_id"],
            "byte_count": len(payload),
            "text": {
                "is_strict_utf8": text is not None,
                "physical_line_count": None if text is None else len(text.splitlines()),
                "lf_octet_count": None if text is None else payload.count(b"\n"),
            },
            "detector_outcomes": outcomes,
            "responsibility_ids": responsibility_ids,
            "classification": "matched" if match_ids else "nonmatch",
        }
        if match_ids:
            leaf["match_ids"] = match_ids
        else:
            leaf["nonmatch_reason"] = (
                "symlink_leaf"
                if is_symlink
                else "non_utf8_blob"
                if text is None
                else "no_detector_match"
            )
        leaves.append(leaf)
        candidates.extend(leaf_candidates)
    return leaves, candidates


def discover_source(
    discovery_input: Mapping[str, object],
    *,
    discovery_input_sha256: str | None = None,
) -> dict[str, object]:
    """Discover all leaf and consumer candidates from exact bare Git objects."""

    record = _validate_discovery_input(copy.deepcopy(dict(discovery_input)))
    projection = record["projection"]
    repository = _canonical_repository(projection["repository"])
    if not (repository / "objects").is_dir() or not (repository / "HEAD").is_file():
        _fail(
            "projection_repository_not_bare",
            str(repository),
            "source census accepts only a bare Git repository directory",
        )
    if _run_git(repository, "rev-parse", "--is-bare-repository").strip() != b"true":
        _fail(
            "projection_repository_not_bare",
            str(repository),
            "source census refuses worktrees and non-bare repositories",
        )
    commit = projection["commit"]
    resolved_commit = _run_git(repository, "rev-parse", "--verify", f"{commit}^{{commit}}")
    resolved_tree = _run_git(repository, "rev-parse", "--verify", f"{commit}^{{tree}}")
    if resolved_commit.decode("ascii", errors="strict").strip() != commit:
        _fail("projection_commit_mismatch", resolved_commit, "commit did not resolve exactly")
    if resolved_tree.decode("ascii", errors="strict").strip() != projection["tree"]:
        _fail("projection_tree_mismatch", resolved_tree, "tree did not resolve exactly")
    raw_inventory = _run_git(
        repository, "ls-tree", "-rz", "-r", "--full-tree", commit
    )
    inventory_sha256 = raw_sha256(raw_inventory)
    inventory_rows = _parse_inventory(raw_inventory)
    if inventory_sha256 != projection["inventory_sha256"]:
        _fail(
            "projection_inventory_digest_mismatch",
            inventory_sha256,
            "ls-tree inventory digest changed",
        )
    if len(inventory_rows) != projection["leaf_count"]:
        _fail(
            "projection_leaf_count_mismatch",
            len(inventory_rows),
            "projection leaf count changed",
        )
    blobs = _read_blobs(repository, [row["object_id"] for row in inventory_rows])
    leaves, candidates = _discover_rows(inventory_rows, blobs, record["detectors"])
    source_path = Path(__file__).resolve()
    try:
        relative_source = source_path.relative_to(REPOSITORY_ROOT).as_posix()
        producer_sha256 = raw_sha256(source_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise SourceCensusError(
            "source_census_producer_unreadable", str(source_path), "producer is unreadable"
        ) from exc
    input_sha256 = discovery_input_sha256 or raw_sha256(canonical_json_bytes(record))
    _sha256(input_sha256, label="discovery_input_sha256")
    result: dict[str, object] = {
        "schema_version": "es_f1_source_census_discovery.v1",
        "authority_status": "NON_AUTHORITATIVE_DISCOVERY",
        "discovery_input_sha256": input_sha256,
        "producer": {"path": relative_source, "sha256": producer_sha256},
        "git": copy.deepcopy(record["git"]),
        "projection": copy.deepcopy(projection),
        "leaf_rows": leaves,
        "consumer_candidates": candidates,
        "candidate_set_sha256": raw_sha256(canonical_json_bytes(candidates)),
    }
    return result


def no_consumption_observation_sha256(
    external_roots: Sequence[Mapping[str, object]],
    repository_paths: Sequence[Mapping[str, object]],
) -> str:
    """Digest only repeatable finite-scope observations, never capture time."""

    return raw_sha256(
        canonical_json_bytes(
            {
                "external_roots": list(external_roots),
                "repository_paths": list(repository_paths),
            }
        )
    )


def _observe_external_root(path_value: object) -> dict[str, object]:
    path_text = _text(path_value, label="no_consumption.external_root.path")
    path = Path(path_text)
    if not path.is_absolute() or os.path.normpath(path_text) != path_text:
        _fail(
            "no_consumption_path_invalid",
            path_text,
            "external root must be an absolute normalized path",
        )
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"path": path_text, "status": "ABSENT", "immediate_entries": []}
    except OSError as exc:
        raise SourceCensusError(
            "no_consumption_root_unreadable",
            path_text,
            "external root cannot be inspected",
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail(
            "no_consumption_root_invalid",
            path_text,
            "external root must be absent or a real directory",
        )
    try:
        entries = sorted((entry.name for entry in path.iterdir()), key=lambda value: value.encode())
    except OSError as exc:
        raise SourceCensusError(
            "no_consumption_root_unreadable",
            path_text,
            "external root entries cannot be inspected",
        ) from exc
    if entries:
        _fail(
            "no_consumption_root_not_empty",
            {"path": path_text, "entries": entries},
            "external root has immediate entries",
        )
    return {
        "path": path_text,
        "status": "PRESENT_EMPTY_DIRECTORY",
        "immediate_entries": [],
    }


def _observe_repository_path(path_value: object) -> dict[str, str]:
    relative = _relative_path(path_value, label="no_consumption.repository_path.path")
    candidate = REPOSITORY_ROOT / relative
    try:
        candidate.lstat()
    except FileNotFoundError:
        return {"path": relative, "status": "ABSENT"}
    except OSError as exc:
        raise SourceCensusError(
            "no_consumption_repository_path_unreadable",
            relative,
            "repository path cannot be inspected",
        ) from exc
    _fail(
        "no_consumption_repository_path_present",
        relative,
        "prospective control path already exists",
    )


def _validate_no_consumption(
    value: object, *, reobserve: bool, enforce_frozen_scope: bool = True
) -> dict[str, Any]:
    observation = _mapping(value, keys=_NO_CONSUMPTION_KEYS, label="no_consumption")
    captured_at = _text(observation["captured_at"], label="no_consumption.captured_at")
    try:
        datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceCensusError(
            "no_consumption_timestamp_invalid",
            captured_at,
            "captured_at is not an ISO-8601 timestamp",
        ) from exc
    external_rows = _list(observation["external_roots"], label="external_roots")
    repository_rows = _list(observation["repository_paths"], label="repository_paths")
    validated_external: list[dict[str, object]] = []
    for value_row in external_rows:
        row = _mapping(
            value_row,
            keys=frozenset({"path", "status", "immediate_entries"}),
            label="external root observation",
        )
        _text(row["path"], label="external root path")
        if row["status"] not in {"ABSENT", "PRESENT_EMPTY_DIRECTORY"}:
            _fail("no_consumption_status_invalid", row, "external status is unsupported")
        if row["immediate_entries"] != []:
            _fail("no_consumption_root_not_empty", row, "immediate entries must be empty")
        validated_external.append(dict(row))
    validated_repository: list[dict[str, object]] = []
    for value_row in repository_rows:
        row = _mapping(
            value_row,
            keys=frozenset({"path", "status"}),
            label="repository path observation",
        )
        _relative_path(row["path"], label="repository path")
        if row["status"] != "ABSENT":
            _fail("no_consumption_status_invalid", row, "repository status must be ABSENT")
        validated_repository.append(dict(row))
    if enforce_frozen_scope and (
        tuple(row["path"] for row in validated_external)
        != FROZEN_NO_CONSUMPTION_EXTERNAL_ROOTS
        or tuple(row["path"] for row in validated_repository)
        != FROZEN_NO_CONSUMPTION_REPOSITORY_PATHS
    ):
        _fail(
            "no_consumption_scope_invalid",
            {
                "external_roots": [row["path"] for row in validated_external],
                "repository_paths": [row["path"] for row in validated_repository],
            },
            "finite no-consumption scope differs from the frozen ordered domain",
        )
    expected_digest = no_consumption_observation_sha256(
        validated_external, validated_repository
    )
    if _sha256(observation["observation_sha256"], label="observation_sha256") != expected_digest:
        _fail(
            "no_consumption_digest_mismatch",
            observation["observation_sha256"],
            "finite-scope observation digest drifted",
        )
    if reobserve:
        fresh_external = [_observe_external_root(row["path"]) for row in validated_external]
        fresh_repository = [
            _observe_repository_path(row["path"]) for row in validated_repository
        ]
        if fresh_external != validated_external or fresh_repository != validated_repository:
            _fail(
                "no_consumption_fact_mismatch",
                {"external_roots": fresh_external, "repository_paths": fresh_repository},
                "live finite-scope facts differ from policy",
            )
    return observation


def _validate_a1_policy(value: object) -> dict[str, Any]:
    a1 = _mapping(value, keys=_A1_KEYS, label="policy.a1")
    root = Path(_text(a1["evidence_root"], label="a1.evidence_root"))
    if not root.is_absolute():
        _fail("a1_policy_invalid", str(root), "A1 evidence root must be absolute")
    member_ids: set[str] = set()
    member_paths: set[str] = set()
    members = _list(a1["members"], label="a1.members", nonempty=True)
    for value_row in members:
        row = _mapping(value_row, keys=_A1_MEMBER_KEYS, label="a1 member")
        member_id = _text(row["member_id"], label="a1 member_id")
        path = _relative_path(row["path"], label="a1 member.path")
        if member_id in member_ids or path in member_paths:
            _fail("a1_policy_invalid", row, "A1 member IDs and paths must be unique")
        member_ids.add(member_id)
        member_paths.add(path)
        _integer(row["byte_count"], label="a1 member.byte_count")
        _sha256(row["sha256"], label="a1 member.sha256")
    metric = _mapping(a1["metric"], keys=_A1_METRIC_KEYS, label="a1.metric")
    expected = {
        "metric_version": "implementation_delta_physical_lines.v1",
        "git_executable": str(PINNED_GIT),
        "git_version": PINNED_GIT_VERSION,
        "git_sha256": PINNED_GIT_SHA256,
        "diff_controls": _DIFF_CONTROLS,
        "implementation_additions": 667,
        "implementation_deletions": 2,
        "candidate_postimage_physical_lines": 690,
    }
    if metric != expected:
        _fail("a1_policy_invalid", metric, "A1 metric contract or expected result drifted")
    return a1


def _validated_pytest_carrier(value: object, *, label: str) -> dict[str, str]:
    carrier = _mapping(
        value,
        keys=frozenset({"executable", "sha256", "version", "tmp_isolation"}),
        label=label,
    )
    boundary = _boundary_proofs_module()
    expected = {
        "executable": str(boundary.PINNED_PYTEST_CARRIER),
        "sha256": boundary.PINNED_PYTEST_CARRIER_SHA256,
        "version": boundary.PINNED_PYTEST_CARRIER_VERSION,
        "tmp_isolation": "private_tmpfs",
    }
    if carrier != expected:
        _fail(
            "pytest_carrier_identity_mismatch",
            carrier,
            f"{label} differs from the pinned private-tmp carrier",
        )
    return copy.deepcopy(expected)


def _validate_selector_policy(
    value: object,
    *,
    discovery_input: Mapping[str, object],
    consumers: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    selector_policy = _mapping(value, keys=_SELECTOR_POLICY_KEYS, label="selector_policy")
    _validated_pytest_carrier(
        selector_policy["pytest_carrier"], label="selector_policy.pytest_carrier"
    )
    if selector_policy["sampling_rule"] != _SAMPLING_RULE:
        _fail(
            "selector_sampling_rule_invalid",
            selector_policy["sampling_rule"],
            "selector policy sampling rule drifted",
        )
    consumer_witness_ids: dict[str, list[str]] = {}
    consumer_classes: dict[str, tuple[str, str]] = {}
    required_consumer_ids: set[str] = set()
    for consumer_id, consumer in consumers.items():
        disposition = consumer.get("proposed_disposition")
        proof_kind = consumer.get("required_proof_kind")
        selector_id = _text(
            consumer.get("selector_id"),
            label=f"consumer {consumer_id} selector_id",
        )
        witness_kind = _text(
            consumer.get("witness_kind"),
            label=f"consumer {consumer_id} witness_kind",
        )
        coverage_status = consumer.get("coverage_status")
        witness_ids = _unique_texts(
            consumer.get("coverage_witness_ids"),
            label=f"consumer {consumer_id} coverage_witness_ids",
            nonempty=False,
        )
        if (
            not isinstance(coverage_status, str)
            or coverage_status not in _COVERAGE_STATUSES
            or len(witness_ids) > 1
            or (coverage_status == "required") != (len(witness_ids) == 1)
        ):
            _fail(
                "consumer_coverage_status_invalid",
                {
                    "consumer_id": consumer_id,
                    "coverage_status": coverage_status,
                    "coverage_witness_ids": witness_ids,
                },
                "required consumers bind one witness and inherited/open consumers bind none",
        )
        if (
            not isinstance(disposition, str)
            or disposition not in _DISPOSITION_PROOF
            or proof_kind != _DISPOSITION_PROOF.get(disposition)
            or witness_kind not in _WITNESS_KINDS
        ):
            _fail(
                "consumer_class_assignment_invalid",
                consumer,
                "consumer disposition, proof, and witness class are incompatible",
            )
        if coverage_status == "required":
            required_consumer_ids.add(consumer_id)
        consumer_witness_ids[consumer_id] = witness_ids
        consumer_classes[consumer_id] = (str(disposition), witness_kind)
    providers = _list(
        selector_policy["provider_visible_pytest_selectors"],
        label="provider selectors",
        nonempty=True,
    )
    if providers != discovery_input["provider_visible_pytest_selectors"]:
        _fail(
            "selector_policy_mismatch",
            providers,
            "provider-visible selectors differ from discovery input",
        )
    providers_by_id = {row["selector_id"]: row for row in providers}
    provider_ids = set(providers_by_id)
    controllers = _list(
        selector_policy["controller_only_proof_selectors"],
        label="controller selectors",
        nonempty=True,
    )
    controller_ids: set[str] = set()
    controller_witnesses: dict[str, list[str]] = {}
    controller_kinds: dict[str, str] = {}
    controller_execution_kinds: dict[str, str] = {}
    controller_pytest_modules: dict[str, set[str]] = {}
    for ordinal, value_row in enumerate(controllers, 1):
        row = _mapping(value_row, keys=_CONTROLLER_SELECTOR_KEYS, label="controller selector")
        selector_id = _text(row["selector_id"], label="controller selector_id")
        if selector_id in provider_ids or selector_id in controller_ids or row["ordinal"] != ordinal:
            _fail("selector_order_invalid", row, "controller selectors must be ordered and disjoint")
        controller_ids.add(selector_id)
        proof_kind = row["proof_kind"]
        if proof_kind not in set(_DISPOSITION_PROOF.values()):
            _fail("selector_proof_kind_invalid", proof_kind, "unsupported proof kind")
        execution_kind = _text(
            row["execution_kind"], label="controller execution_kind"
        )
        allowed_proofs = {
            "pytest_aggregate": {"boundary_runtime"},
            "isolated_probe": {"boundary_runtime"},
            "static_ast": {"non_cdi_static", "reference_absence"},
        }.get(execution_kind)
        if allowed_proofs is None or proof_kind not in allowed_proofs:
            _fail(
                "selector_execution_kind_invalid",
                row,
                "controller execution kind and proof kind are incompatible",
            )
        controller_kinds[selector_id] = proof_kind
        controller_execution_kinds[selector_id] = execution_kind
        if row["runner_path"] != "scripts/experiments/es/boundary_proofs.py":
            _fail("selector_runner_invalid", row["runner_path"], "runner path drifted")
        _sha256(row["runner_sha256"], label="controller runner_sha256")
        argv = _texts(row["argv"], label="controller argv", nonempty=True)
        input_paths: set[str] = set()
        for binding_value in _list(row["input_bindings"], label="input_bindings", nonempty=True):
            binding = _mapping(
                binding_value, keys=frozenset({"path", "sha256"}), label="input binding"
            )
            input_paths.add(
                _relative_path(binding["path"], label="input binding.path")
            )
            _sha256(binding["sha256"], label="input binding.sha256")
        if execution_kind == "pytest_aggregate":
            controller_pytest_modules[selector_id] = {
                module_path
                for token in argv
                for module_path in [token.partition("::")[0]]
                if module_path.endswith(".py") and module_path in input_paths
            }
        controller_witness_ids = _unique_texts(
            row["coverage_witness_ids"],
            label="controller coverage_witness_ids",
            nonempty=False,
        )
        if len(controller_witness_ids) > 1:
            _fail(
                "coverage_witness_join_invalid",
                row,
                "controller selector may bind at most one witness",
            )
        controller_witnesses[selector_id] = controller_witness_ids

    for consumer_id, consumer in consumers.items():
        selector_id = str(consumer["selector_id"])
        witness_kind = str(consumer["witness_kind"])
        proof_kind = consumer["required_proof_kind"]
        lane_is_valid = (
            witness_kind == "pytest_runtime"
            and selector_id in provider_ids
            and proof_kind == "boundary_runtime"
        ) or (
            witness_kind == "controller_pytest_runtime"
            and controller_execution_kinds.get(selector_id) == "pytest_aggregate"
            and proof_kind == "boundary_runtime"
        ) or (
            witness_kind == "runtime_probe"
            and controller_execution_kinds.get(selector_id) == "isolated_probe"
            and proof_kind == "boundary_runtime"
        ) or (
            witness_kind == "static_ast"
            and controller_execution_kinds.get(selector_id) == "static_ast"
            and controller_kinds.get(selector_id) == proof_kind
            and proof_kind in {"non_cdi_static", "reference_absence"}
        )
        if not lane_is_valid:
            _fail(
                "consumer_class_assignment_invalid",
                consumer,
                "consumer selector does not implement its disposition/witness class",
            )

    witness_rows = _list(
        selector_policy["coverage_witness_specs"],
        label="coverage_witness_specs",
        nonempty=True,
    )
    witnesses: dict[str, dict[str, Any]] = {}
    witnesses_by_selector: dict[str, list[str]] = {
        selector_id: [] for selector_id in provider_ids | controller_ids
    }
    witnesses_by_consumer: dict[str, list[str]] = {consumer_id: [] for consumer_id in consumers}
    for value_row in witness_rows:
        row = _mapping(value_row, keys=_WITNESS_SPEC_KEYS, label="coverage witness spec")
        witness_id = _text(row["witness_id"], label="witness_id")
        consumer_id = _text(row["consumer_id"], label="witness consumer_id")
        selector_id = _text(row["selector_id"], label="witness selector_id")
        if witness_id in witnesses or consumer_id not in consumers or selector_id not in witnesses_by_selector:
            _fail("coverage_witness_join_invalid", row, "witness has a duplicate or unknown join")
        consumer = consumers[consumer_id]
        if consumer["coverage_status"] != "required":
            _fail(
                "consumer_coverage_status_invalid",
                row,
                "only required consumers may own coverage witnesses",
            )
        proof_kind = row["required_proof_kind"]
        if proof_kind != consumer["required_proof_kind"]:
            _fail("coverage_witness_proof_mismatch", row, "witness proof kind differs from consumer")
        witness_kind = row["witness_kind"]
        if witness_kind == "pytest_runtime":
            if selector_id not in provider_ids or proof_kind != "boundary_runtime":
                _fail("coverage_witness_lane_invalid", row, "pytest witness is in the wrong lane")
        elif witness_kind == "controller_pytest_runtime":
            if (
                controller_execution_kinds.get(selector_id) != "pytest_aggregate"
                or proof_kind != "boundary_runtime"
            ):
                _fail(
                    "coverage_witness_lane_invalid",
                    row,
                    "controller pytest witness is in the wrong lane",
                )
        elif witness_kind == "static_ast":
            if (
                controller_execution_kinds.get(selector_id) != "static_ast"
                or proof_kind not in {"non_cdi_static", "reference_absence"}
            ):
                _fail("coverage_witness_lane_invalid", row, "static witness is in the wrong lane")
        elif witness_kind == "runtime_probe":
            if (
                controller_execution_kinds.get(selector_id) != "isolated_probe"
                or proof_kind != "boundary_runtime"
            ):
                _fail("coverage_witness_lane_invalid", row, "runtime probe is in the wrong lane")
        else:
            _fail("coverage_witness_kind_invalid", witness_kind, "unsupported witness kind")
        if selector_id in controller_kinds and controller_kinds[selector_id] != proof_kind:
            _fail("coverage_witness_proof_mismatch", row, "controller proof kind differs")
        if (
            selector_id != consumer["selector_id"]
            or witness_kind != consumer["witness_kind"]
        ):
            _fail(
                "consumer_class_assignment_invalid",
                row,
                "witness assignment differs from its consumer class assignment",
            )
        spec = _mapping(row["spec"], label="witness spec payload")
        anchor_id = _text(spec.get("anchor_id"), label="witness spec.anchor_id")
        if anchor_id != consumer["anchor_id"]:
            _fail("coverage_witness_join_invalid", row, "witness anchor differs from consumer")
        if witness_kind in {"pytest_runtime", "controller_pytest_runtime"}:
            required_keys = {
                "anchor_id",
                "event_kind",
                "phase",
                "attribution",
                "expected_event",
            }
            if set(spec) != required_keys:
                _fail(
                    "coverage_witness_spec_incomplete",
                    spec,
                    "witness payload does not match its closed kind",
                )
            event_kind = spec["event_kind"]
            if event_kind not in {
                "opcode_exact_span",
                "import_alias_opcode",
                "callable_entry",
            }:
                _fail(
                    "coverage_witness_spec_incomplete",
                    event_kind,
                    "pytest witness event kind is unsupported",
                )
            phase = spec["phase"]
            attribution = _mapping(
                spec["attribution"], label="pytest witness attribution"
            )
            if phase in {"setup", "call", "teardown"}:
                expected_attribution_keys = {
                    "attribution_kind",
                    "pytest_node_pattern",
                }
                expected_attribution_kind = "pytest_node"
                attribution_value_key = "pytest_node_pattern"
            elif phase in {"bootstrap", "collection"}:
                expected_attribution_keys = {
                    "attribution_kind",
                    "pytest_module_path",
                }
                expected_attribution_kind = "selector_module"
                attribution_value_key = "pytest_module_path"
            else:
                _fail(
                    "coverage_witness_attribution_invalid",
                    phase,
                    "pytest witness phase is unsupported",
                )
            if (
                set(attribution) != expected_attribution_keys
                or attribution.get("attribution_kind") != expected_attribution_kind
            ):
                _fail(
                    "coverage_witness_attribution_invalid",
                    attribution,
                    "pytest phase requires its exact attribution kind",
                )
            attribution_value = _text(
                attribution[attribution_value_key],
                label=f"pytest attribution.{attribution_value_key}",
            )
            if attribution_value_key == "pytest_module_path":
                module_path = _relative_path(
                    attribution_value,
                    label="pytest attribution.pytest_module_path",
                )
                expected_modules = (
                    {providers_by_id[selector_id]["pytest_module_path"]}
                    if witness_kind == "pytest_runtime"
                    else controller_pytest_modules.get(selector_id, set())
                )
                if module_path not in expected_modules:
                    _fail(
                        "coverage_witness_attribution_invalid",
                        attribution,
                        "pytest module attribution is not bound to its selector",
                    )
        elif witness_kind == "static_ast":
            if set(spec) != {"anchor_id", "query", "expected_event"}:
                _fail(
                    "coverage_witness_spec_incomplete",
                    spec,
                    "witness payload does not match its closed kind",
                )
        else:
            required_keys = {
                "anchor_id",
                "event_kind",
                "phase",
                "attribution",
                "probe",
                "expected_event",
            }
            if set(spec) != required_keys or spec["phase"] != "residual":
                _fail(
                    "coverage_witness_spec_incomplete",
                    spec,
                    "witness payload does not match its closed kind",
                )
            if spec["event_kind"] not in {
                "opcode_exact_span",
                "import_alias_opcode",
                "callable_entry",
            }:
                _fail(
                    "coverage_witness_spec_incomplete",
                    spec["event_kind"],
                    "runtime probe event kind is unsupported",
                )
            attribution = _mapping(
                spec["attribution"],
                keys=frozenset({"attribution_kind", "action_sha256"}),
                label="runtime probe attribution",
            )
            expected_action_sha256 = raw_sha256(canonical_json_bytes(spec["probe"]))
            if (
                attribution["attribution_kind"] != "residual_action"
                or attribution["action_sha256"] != expected_action_sha256
            ):
                _fail(
                    "coverage_witness_attribution_invalid",
                    attribution,
                    "runtime probe attribution must bind the exact action",
                )
        witnesses[witness_id] = row
        witnesses_by_selector[selector_id].append(witness_id)
        witnesses_by_consumer[consumer_id].append(witness_id)
    for selector_id, expected_ids in controller_witnesses.items():
        if witnesses_by_selector[selector_id] != expected_ids:
            _fail("coverage_witness_join_invalid", selector_id, "controller witness backpointer drifted")
    for consumer_id, consumer in consumers.items():
        expected_ids = consumer_witness_ids[consumer_id]
        if witnesses_by_consumer[consumer_id] != expected_ids:
            _fail("coverage_witness_join_invalid", consumer_id, "consumer witness backpointer drifted")
    witnessed_consumer_ids = {
        consumer_id
        for consumer_id, witness_ids in witnesses_by_consumer.items()
        if witness_ids
    }
    if witnessed_consumer_ids != required_consumer_ids:
        _fail(
            "coverage_required_sample_missing",
            sorted(required_consumer_ids ^ witnessed_consumer_ids),
            "required-consumer and witness consumer domains differ",
        )
    provider_witness_counts = {
        selector_id: len(witnesses_by_selector[selector_id])
        for selector_id in provider_ids
    }
    if any(count != 1 for count in provider_witness_counts.values()):
        _fail(
            "coverage_required_sample_missing",
            provider_witness_counts,
            "every provider selector must own exactly one required witness",
        )
    populated_classes = set(consumer_classes.values())
    required_classes = {
        consumer_classes[consumer_id] for consumer_id in required_consumer_ids
    }
    if required_classes != populated_classes:
        _fail(
            "coverage_required_sample_missing",
            sorted(populated_classes - required_classes),
            "every populated disposition/witness class needs a required representative",
        )

    desired_rows = _list(
        selector_policy["desired_state_proof_specs"],
        label="desired_state_proof_specs",
        nonempty=True,
    )
    desired_witnesses: list[str] = []
    proof_ids: set[str] = set()
    for value_row in desired_rows:
        row = _mapping(value_row, keys=_DESIRED_PROOF_SPEC_KEYS, label="desired proof spec")
        proof_id = _text(row["proof_spec_id"], label="proof_spec_id")
        witness_id = _text(row["witness_id"], label="desired witness_id")
        if proof_id in proof_ids or witness_id not in witnesses:
            _fail("desired_proof_join_invalid", row, "desired proof ID or witness is invalid")
        proof_ids.add(proof_id)
        if row["proof_kind"] != witnesses[witness_id]["required_proof_kind"]:
            _fail("desired_proof_join_invalid", row, "desired proof kind drifted")
        if row["expected_result"] != witnesses[witness_id]["spec"]["expected_event"]:
            _fail("desired_proof_join_invalid", row, "desired result differs from witness contract")
        desired_witnesses.append(witness_id)
    if desired_witnesses != list(witnesses):
        _fail("desired_proof_join_invalid", desired_witnesses, "desired proofs must cover witnesses in order")
    return selector_policy


def _completion_identity(value: object, *, label: str) -> dict[str, Any]:
    row = _mapping(value, keys=_CANDIDATE_IDENTITY_KEYS, label=label)
    consumer_id = _text(row["consumer_id"], label=f"{label}.consumer_id")
    match_id = _text(row["match_id"], label=f"{label}.match_id")
    if _CONSUMER_ID_RE.fullmatch(consumer_id) is None:
        _fail("consumer_policy_mismatch", consumer_id, "consumer ID is malformed")
    if _MATCH_ID_RE.fullmatch(match_id) is None:
        _fail("consumer_policy_mismatch", match_id, "match ID is malformed")
    _relative_path(row["caller_path"], label=f"{label}.caller_path")
    _sha1(row["caller_object_id"], label=f"{label}.caller_object_id")
    _validated_source_span(row["span"], label=f"{label}.span")
    for key in (
        "anchor_id",
        "callee_or_dispatch_form",
        "detector_id",
        "detector_version",
    ):
        _text(row[key], label=f"{label}.{key}")
    _unique_texts(
        row["responsibility_ids"],
        label=f"{label}.responsibility_ids",
    )
    return row


def _completion_digest(
    value: Mapping[str, object],
    expected: object,
    *,
    label: str,
    verify_canonical: bool = True,
) -> str:
    expected_sha256 = _sha256(expected, label=f"expected {label} SHA-256")
    observed_sha256 = raw_sha256(canonical_json_bytes(value))
    if verify_canonical and observed_sha256 != expected_sha256:
        _fail(
            "policy_candidate_input_digest_mismatch",
            observed_sha256,
            f"{label} canonical digest differs from its bound digest",
        )
    return expected_sha256


def _validate_completion_discovery(
    discovery_input: Mapping[str, object],
    *,
    discovery_output: Mapping[str, object],
    expected_discovery_input_sha256: object,
    expected_discovery_output_sha256: object,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    validated_input = _validate_discovery_input(copy.deepcopy(dict(discovery_input)))
    input_sha256 = _completion_digest(
        validated_input,
        expected_discovery_input_sha256,
        label="discovery input",
        verify_canonical=False,
    )
    output = _mapping(
        copy.deepcopy(dict(discovery_output)),
        keys=frozenset(
            {
                "schema_version",
                "authority_status",
                "discovery_input_sha256",
                "producer",
                "git",
                "projection",
                "leaf_rows",
                "consumer_candidates",
                "candidate_set_sha256",
            }
        ),
        label="discovery output",
    )
    _completion_digest(
        output,
        expected_discovery_output_sha256,
        label="discovery output",
    )
    if (
        output["schema_version"] != "es_f1_source_census_discovery.v1"
        or output["authority_status"] != "NON_AUTHORITATIVE_DISCOVERY"
        or output["discovery_input_sha256"] != input_sha256
        or output["git"] != validated_input["git"]
        or output["projection"] != validated_input["projection"]
    ):
        _fail(
            "policy_candidate_discovery_invalid",
            output,
            "discovery output does not bind the exact discovery input",
        )
    _mapping(output["producer"], keys=_PRODUCER_KEYS, label="discovery producer")
    candidate_values = _list(
        output["consumer_candidates"],
        label="discovery consumer_candidates",
        nonempty=True,
    )
    candidates = [
        _completion_identity(value, label=f"discovery candidate {index}")
        for index, value in enumerate(candidate_values)
    ]
    consumer_ids = [row["consumer_id"] for row in candidates]
    match_ids = [row["match_id"] for row in candidates]
    if len(consumer_ids) != len(set(consumer_ids)) or len(match_ids) != len(
        set(match_ids)
    ):
        _fail(
            "policy_candidate_domain_invalid",
            consumer_ids,
            "discovery consumer and match IDs must be unique",
        )
    expected_candidate_set_sha256 = raw_sha256(
        canonical_json_bytes(candidate_values)
    )
    if output["candidate_set_sha256"] != expected_candidate_set_sha256:
        _fail(
            "policy_candidate_domain_invalid",
            output["candidate_set_sha256"],
            "discovery candidate-set digest drifted",
        )
    leaves = _list(output["leaf_rows"], label="discovery leaf_rows", nonempty=True)
    leaves_by_path: dict[str, Mapping[str, object]] = {}
    for value in leaves:
        leaf = _mapping(value, label="discovery leaf")
        path = _relative_path(leaf.get("path"), label="discovery leaf.path")
        if path in leaves_by_path:
            _fail("policy_candidate_domain_invalid", path, "discovery leaf repeats")
        leaves_by_path[path] = leaf
    for candidate in candidates:
        leaf = leaves_by_path.get(str(candidate["caller_path"]))
        if leaf is None or leaf.get("object_id") != candidate["caller_object_id"]:
            _fail(
                "policy_candidate_domain_invalid",
                candidate,
                "candidate caller path/blob does not join its discovery leaf",
            )
    return validated_input, output, candidates


def _validate_completion_decisions(
    value: Mapping[str, object],
    *,
    candidates: Sequence[Mapping[str, object]],
    expected_sha256: object,
    discovery_output_sha256: str,
    candidate_set_sha256: str,
    discovery_input_sha256: str,
    projection_repository: str,
    projection_commit: str,
    projection_tree: str,
    leaf_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, Any]]:
    record = _mapping(
        copy.deepcopy(dict(value)),
        keys=_REVIEWED_DISPOSITIONS_KEYS,
        label="reviewed dispositions",
    )
    _completion_digest(record, expected_sha256, label="reviewed dispositions")
    if (
        record["schema_version"]
        != "es_f1_policy_path_decisions_candidate.v1"
        or record["authority_status"]
        != "NON_AUTHORITATIVE_NEUTRAL_RECOMMENDATION"
    ):
        _fail(
            "policy_candidate_dispositions_invalid",
            record,
            "reviewed disposition candidate has unsupported status or version",
        )
    candidate_sha256 = _sha256(
        record["candidate_sha256"], label="reviewed candidate_sha256"
    )
    body = copy.deepcopy(dict(record))
    body.pop("candidate_sha256")
    if raw_sha256(canonical_json_bytes(body)) != candidate_sha256:
        _fail(
            "policy_candidate_dispositions_invalid",
            candidate_sha256,
            "reviewed disposition body digest drifted",
        )
    source_discovery = _mapping(
        record["source_discovery"],
        keys=_REVIEWED_SOURCE_DISCOVERY_KEYS,
        label="reviewed source_discovery",
    )
    _relative_path(source_discovery["path"], label="reviewed source_discovery.path")
    caller_paths = list(dict.fromkeys(str(row["caller_path"]) for row in candidates))
    if (
        source_discovery.get("raw_sha256") != discovery_output_sha256
        or source_discovery.get("discovery_input_sha256")
        != discovery_input_sha256
        or source_discovery.get("candidate_set_sha256") != candidate_set_sha256
        or source_discovery.get("consumer_candidate_count") != len(candidates)
        or source_discovery.get("caller_path_count") != len(caller_paths)
        or source_discovery.get("leaf_count") != len(leaf_rows)
        or source_discovery.get("projection_repository") != projection_repository
        or source_discovery.get("projection_commit") != projection_commit
        or source_discovery.get("projection_tree") != projection_tree
    ):
        _fail(
            "policy_candidate_dispositions_invalid",
            source_discovery,
            "reviewed disposition discovery binding drifted",
        )
    decision_values = _list(
        record["consumer_decisions"],
        label="reviewed consumer_decisions",
        nonempty=True,
    )
    if len(decision_values) != len(candidates):
        _fail(
            "policy_candidate_domain_invalid",
            len(decision_values),
            "reviewed disposition domain differs from discovery",
        )
    decisions: list[dict[str, Any]] = []
    witness_ids: set[str] = set()
    for index, (candidate, value_row) in enumerate(
        zip(candidates, decision_values, strict=True)
    ):
        row = _mapping(
            value_row,
            keys=_DRAFT_DECISION_KEYS,
            label=f"reviewed disposition {index}",
        )
        identity = _completion_identity(
            {key: row[key] for key in _CANDIDATE_IDENTITY_KEYS},
            label=f"reviewed disposition identity {index}",
        )
        if identity != candidate:
            _fail(
                "policy_candidate_join_invalid",
                index,
                "reviewed disposition identity differs from discovery",
            )
        if row["authority_status"] != "NEUTRAL_RECOMMENDATION_ONLY":
            _fail(
                "policy_candidate_dispositions_invalid",
                row["authority_status"],
                "consumer decision claims unsupported authority",
            )
        if row["baseline_expected_to_pass"] is not None and not isinstance(
            row["baseline_expected_to_pass"], bool
        ):
            _fail(
                "policy_candidate_dispositions_invalid",
                row["baseline_expected_to_pass"],
                "baseline expectation must be Boolean or null",
            )
        disposition = row["proposed_disposition"]
        if (
            disposition not in _DISPOSITION_PROOF
            or row["required_proof_kind"] != _DISPOSITION_PROOF[disposition]
            or row["witness_kind"] not in _WITNESS_KINDS
        ):
            _fail(
                "consumer_class_assignment_invalid",
                row,
                "reviewed disposition class is unsupported",
            )
        _text(row["selector_id"], label="reviewed selector_id")
        _text(row["spec_strategy"], label="reviewed spec_strategy")
        row_witness_ids = _unique_texts(
            row["coverage_witness_ids"],
            label="reviewed coverage_witness_ids",
        )
        if len(row_witness_ids) != 1 or row_witness_ids[0] in witness_ids:
            _fail(
                "coverage_witness_join_invalid",
                row_witness_ids,
                "each reviewed consumer needs one unique candidate witness ID",
            )
        witness_ids.add(row_witness_ids[0])
        decisions.append(row)
    mapping_contract = _mapping(
        record["mapping_contract"],
        keys=_REVIEWED_MAPPING_KEYS,
        label="reviewed mapping_contract",
    )
    expected_mapping_contract = {
        "consumer_order_preserved_from_discovery": True,
        "default_disposition": None,
        "disposition_to_proof": _DISPOSITION_PROOF,
        "every_discovered_consumer_explicitly_enumerated": True,
        "every_discovered_path_explicitly_enumerated": True,
        "path_set_equality_verified": True,
        "proof_results_claimed": False,
        "selector_node_feasibility_claimed": False,
    }
    if mapping_contract != expected_mapping_contract:
        _fail(
            "policy_candidate_dispositions_invalid",
            mapping_contract,
            "reviewed mapping contract drifted",
        )
    candidate_ids = {str(row["consumer_id"]) for row in candidates}
    candidate_paths = set(caller_paths)
    finding_ids: set[str] = set()
    allowed_finding_key_sets = {
        frozenset({"classification", "detail", "finding_id", "paths"}),
        frozenset(
            {
                "classification",
                "consumer_ids",
                "detail",
                "finding_id",
                "paths",
            }
        ),
        frozenset(
            {
                "classification",
                "count",
                "detail",
                "finding_id",
                "paths",
            }
        ),
        frozenset(
            {
                "classification",
                "consumer_ids",
                "count",
                "detail",
                "finding_id",
                "paths",
            }
        ),
    }
    for value_row in _list(record["detector_findings"], label="detector_findings"):
        row = _mapping(value_row, label="detector finding")
        if frozenset(row) not in allowed_finding_key_sets:
            _fail(
                "source_census_shape_invalid",
                sorted(row),
                "detector finding has an unsupported closed shape",
            )
        _text(row["classification"], label="detector finding.classification")
        _text(row["detail"], label="detector finding.detail")
        finding_id = _text(row["finding_id"], label="detector finding.finding_id")
        if finding_id in finding_ids:
            _fail("policy_candidate_dispositions_invalid", finding_id, "finding IDs repeat")
        finding_ids.add(finding_id)
        referenced_ids: list[str] = []
        if "consumer_ids" in row:
            referenced_ids = _unique_texts(
                row["consumer_ids"], label="detector finding.consumer_ids"
            )
            if not set(referenced_ids) <= candidate_ids:
                _fail(
                    "policy_candidate_dispositions_invalid",
                    referenced_ids,
                    "detector finding names an unknown consumer",
                )
        if "count" in row:
            count = _integer(row["count"], label="detector finding.count")
            if referenced_ids and count != len(referenced_ids):
                _fail(
                    "policy_candidate_dispositions_invalid",
                    row,
                    "detector finding count differs from its consumer domain",
                )
        paths_value = row["paths"]
        if isinstance(paths_value, list):
            paths = _unique_texts(paths_value, label="detector finding.paths")
            for path in paths:
                _relative_path(path, label="detector finding path")
            if not set(paths) <= candidate_paths:
                _fail(
                    "policy_candidate_dispositions_invalid",
                    paths,
                    "detector finding names a path outside the candidate domain",
                )
        else:
            _integer(paths_value, label="detector finding.paths")
    case_ids: set[str] = set()
    for value_row in _list(record["ambiguous_cases"], label="ambiguous_cases"):
        row = _mapping(
            value_row,
            keys=frozenset({"case_id", "paths", "reason", "recommended_disposition"}),
            label="ambiguous case",
        )
        case_id = _text(row["case_id"], label="ambiguous case.case_id")
        if case_id in case_ids:
            _fail("policy_candidate_dispositions_invalid", case_id, "case IDs repeat")
        case_ids.add(case_id)
        paths = _unique_texts(row["paths"], label="ambiguous case.paths")
        if not set(paths) <= candidate_paths:
            _fail(
                "policy_candidate_dispositions_invalid",
                paths,
                "ambiguous case names a path outside the candidate domain",
            )
        _text(row["reason"], label="ambiguous case.reason")
        _text(
            row["recommended_disposition"],
            label="ambiguous case.recommended_disposition",
        )
    recommendation_ids: set[str] = set()
    for value_row in _list(
        record["controller_selector_recommendations"],
        label="controller_selector_recommendations",
        nonempty=True,
    ):
        row = _mapping(
            value_row,
            keys=frozenset({"note", "proof_kind", "selector_id", "witness_kind"}),
            label="controller selector recommendation",
        )
        selector_id = _text(row["selector_id"], label="recommendation.selector_id")
        if selector_id in recommendation_ids:
            _fail(
                "policy_candidate_dispositions_invalid",
                selector_id,
                "controller recommendation IDs repeat",
            )
        recommendation_ids.add(selector_id)
        _text(row["note"], label="controller recommendation.note")
        if (
            row["proof_kind"] not in set(_DISPOSITION_PROOF.values())
            or row["witness_kind"] not in _WITNESS_KINDS
        ):
            _fail(
                "policy_candidate_dispositions_invalid",
                row,
                "controller recommendation class is unsupported",
            )
    leaves_by_path = {str(row.get("path")): row for row in leaf_rows}
    path_values = _list(record["path_decisions"], label="path_decisions", nonempty=True)
    if len(path_values) != len(caller_paths):
        _fail(
            "policy_candidate_domain_invalid",
            len(path_values),
            "reviewed path-decision domain differs from discovery",
        )
    decisions_by_path: dict[str, list[dict[str, Any]]] = {
        path: [row for row in decisions if row["caller_path"] == path]
        for path in caller_paths
    }
    validated_path_rows: list[dict[str, Any]] = []
    for index, (expected_path, value_row) in enumerate(
        zip(caller_paths, path_values, strict=True)
    ):
        row = _mapping(
            value_row,
            keys=_REVIEWED_PATH_DECISION_KEYS,
            label=f"path decision {index}",
        )
        path = _relative_path(row["caller_path"], label="path decision.caller_path")
        assigned = decisions_by_path[expected_path]
        if path != expected_path:
            _fail(
                "policy_candidate_join_invalid",
                path,
                "path decisions do not retain discovery order",
            )
        expected_object_ids = {str(value["caller_object_id"]) for value in assigned}
        if (
            len(expected_object_ids) != 1
            or row["caller_object_id"] not in expected_object_ids
            or row["candidate_count"] != len(assigned)
            or row["consumer_ids"] != [value["consumer_id"] for value in assigned]
            or row["anchor_ids"]
            != sorted({str(value["anchor_id"]) for value in assigned}, key=str.encode)
            or row["authority_status"] != "NEUTRAL_RECOMMENDATION_ONLY"
        ):
            _fail(
                "policy_candidate_join_invalid",
                row,
                "path decision identity differs from its consumer rows",
            )
        recommended_pair = (
            str(row["recommended_disposition"]),
            str(row["required_proof_kind"]),
        )
        assigned_pairs = {
            (
                str(value["proposed_disposition"]),
                str(value["required_proof_kind"]),
            )
            for value in assigned
        }
        if (
            recommended_pair not in assigned_pairs
            or row["recommended_selector_ids"]
            != list(dict.fromkeys(str(value["selector_id"]) for value in assigned))
            or row["recommended_witness_kinds"]
            != list(dict.fromkeys(str(value["witness_kind"]) for value in assigned))
        ):
            _fail(
                "policy_candidate_join_invalid",
                row,
                "path decision class differs from its consumer rows",
            )
        _text(row["rationale_code"], label="path decision.rationale_code")
        source_audit = _mapping(
            row["source_audit"],
            keys=frozenset(
                {
                    "ast_parsed",
                    "blob_id_verified",
                    "byte_count",
                    "matched_source_lines_sha256",
                    "physical_line_count",
                    "source",
                }
            ),
            label="path decision.source_audit",
        )
        leaf = _mapping(leaves_by_path.get(path), label="path decision leaf")
        text = _mapping(leaf.get("text"), label="path decision leaf text")
        if (
            not isinstance(source_audit["ast_parsed"], bool)
            or source_audit["blob_id_verified"] is not True
            or source_audit["source"] != "pinned_bare_projection_blob"
            or source_audit["byte_count"] != leaf.get("byte_count")
            or source_audit["physical_line_count"] != text.get("physical_line_count")
        ):
            _fail(
                "policy_candidate_dispositions_invalid",
                source_audit,
                "path source audit differs from its discovery leaf",
            )
        _sha256(
            source_audit["matched_source_lines_sha256"],
            label="path decision matched-source digest",
        )
        validated_path_rows.append(row)
    counts = _mapping(
        record["counts"],
        keys=frozenset({"consumers_by_disposition", "paths_by_disposition"}),
        label="reviewed counts",
    )
    disposition_keys = frozenset(_DISPOSITION_PROOF)
    consumer_counts = _mapping(
        counts["consumers_by_disposition"],
        keys=disposition_keys,
        label="reviewed consumer counts",
    )
    path_counts = _mapping(
        counts["paths_by_disposition"],
        keys=disposition_keys,
        label="reviewed path counts",
    )
    expected_consumer_counts = {
        disposition: sum(row["proposed_disposition"] == disposition for row in decisions)
        for disposition in _DISPOSITION_PROOF
    }
    expected_path_counts = {
        disposition: sum(
            row["recommended_disposition"] == disposition for row in validated_path_rows
        )
        for disposition in _DISPOSITION_PROOF
    }
    if consumer_counts != expected_consumer_counts or path_counts != expected_path_counts:
        _fail(
            "policy_candidate_dispositions_invalid",
            counts,
            "reviewed disposition totals drifted",
        )
    return decisions


def _validated_completion_choice(
    value: object,
    *,
    candidate: Mapping[str, object],
    decision: Mapping[str, object],
) -> dict[str, Any]:
    choice = _mapping(value, keys=_OBSERVATION_CHOICE_KEYS, label="executable choice")
    assignment_unchanged = (
        choice["selector_id"] == decision["selector_id"]
        and choice["witness_kind"] == decision["witness_kind"]
    )
    exact_controller_promotion = (
        choice["selector_id"] == "CO-PYTEST-01"
        and choice["witness_kind"] == "controller_pytest_runtime"
        and decision["proposed_disposition"] == "route_through_boundary"
        and decision["required_proof_kind"] == "boundary_runtime"
        and decision["witness_kind"] == "runtime_probe"
    )
    if (
        choice["proof_kind"] != decision["required_proof_kind"]
        or not (assignment_unchanged or exact_controller_promotion)
    ):
        _fail(
            "policy_candidate_join_invalid",
            choice,
            "executable choice differs from reviewed class assignment",
        )
    witness_kind = str(choice["witness_kind"])
    spec = _mapping(choice["spec"], label="executable choice spec")
    boundary = _boundary_proofs_module()
    if witness_kind == "static_ast":
        spec = _mapping(
            spec,
            keys=frozenset({"query", "expected_event"}),
            label="static executable choice spec",
        )
        try:
            boundary._validate_static_query(spec["query"])
        except Exception as exc:
            raise SourceCensusError(
                "policy_candidate_choice_invalid",
                spec,
                "static choice query is not executable",
            ) from exc
        _mapping(spec["expected_event"], label="static expected_event")
        return {
            "anchor_id": candidate["anchor_id"],
            "query": copy.deepcopy(spec["query"]),
            "expected_event": copy.deepcopy(spec["expected_event"]),
        }
    expected_keys = {
        "event_kind",
        "phase",
        "attribution",
        "expected_event",
    }
    if witness_kind == "runtime_probe":
        expected_keys.add("probe")
    elif witness_kind not in {"pytest_runtime", "controller_pytest_runtime"}:
        _fail(
            "policy_candidate_choice_invalid",
            witness_kind,
            "choice witness kind is unsupported",
        )
    spec = _mapping(
        spec,
        keys=frozenset(expected_keys),
        label="runtime executable choice spec",
    )
    event_kind = _text(spec["event_kind"], label="choice event_kind")
    phase = _text(spec["phase"], label="choice phase")
    attribution = _mapping(spec["attribution"], label="choice attribution")
    attribution_kind = attribution.get("attribution_kind")
    if phase in {"setup", "call", "teardown"}:
        attribution = _mapping(
            attribution,
            keys=frozenset({"attribution_kind", "pytest_node_id"}),
            label="choice pytest-node attribution",
        )
        if (
            attribution_kind != "pytest_node"
            or witness_kind not in {"pytest_runtime", "controller_pytest_runtime"}
        ):
            _fail(
                "policy_candidate_choice_invalid",
                attribution,
                "pytest phase requires exact node attribution",
            )
        node_id = _text(
            attribution["pytest_node_id"], label="choice pytest_node_id"
        )
        policy_attribution: dict[str, object] = {
            "attribution_kind": "pytest_node",
            "pytest_node_pattern": re.escape(node_id),
        }
    elif phase in {"bootstrap", "collection"}:
        attribution = _mapping(
            attribution,
            keys=frozenset({"attribution_kind", "pytest_module_path"}),
            label="choice selector-module attribution",
        )
        if (
            attribution_kind != "selector_module"
            or witness_kind not in {"pytest_runtime", "controller_pytest_runtime"}
        ):
            _fail(
                "policy_candidate_choice_invalid",
                attribution,
                "collection phase requires exact selector-module attribution",
            )
        policy_attribution = {
            "attribution_kind": "selector_module",
            "pytest_module_path": _relative_path(
                attribution["pytest_module_path"],
                label="choice pytest_module_path",
            ),
        }
    elif phase == "residual":
        attribution = _mapping(
            attribution,
            keys=frozenset({"attribution_kind", "action_sha256"}),
            label="choice residual attribution",
        )
        if attribution_kind != "residual_action" or witness_kind != "runtime_probe":
            _fail(
                "policy_candidate_choice_invalid",
                attribution,
                "residual phase requires exact action attribution",
            )
        probe = _mapping(spec["probe"], label="choice runtime probe")
        try:
            boundary._validate_runtime_probe(probe)
        except Exception as exc:
            raise SourceCensusError(
                "policy_candidate_choice_invalid",
                probe,
                "runtime action is not closed and executable",
            ) from exc
        action_sha256 = raw_sha256(canonical_json_bytes(probe))
        if attribution["action_sha256"] != action_sha256:
            _fail(
                "policy_candidate_choice_invalid",
                attribution,
                "runtime action digest drifted",
            )
        policy_attribution = {
            "attribution_kind": "residual_action",
            "action_sha256": action_sha256,
        }
    else:
        _fail(
            "policy_candidate_choice_invalid",
            phase,
            "choice phase is unsupported",
        )
    expected_binding = {
        "event_kind": event_kind,
        "phase": phase,
        "attribution": copy.deepcopy(dict(attribution)),
    }
    _validated_source_event(
        spec["expected_event"],
        expected_binding=expected_binding,
        consumer=candidate,
    )
    result: dict[str, Any] = {
        "anchor_id": candidate["anchor_id"],
        "event_kind": event_kind,
        "phase": phase,
        "attribution": policy_attribution,
        "expected_event": copy.deepcopy(spec["expected_event"]),
    }
    if witness_kind == "runtime_probe":
        result["probe"] = copy.deepcopy(spec["probe"])
    return result


def _validate_completion_observations(
    value: Mapping[str, object],
    *,
    candidates: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    expected_sha256: object,
    discovery_input_sha256: str,
    discovery_output_sha256: str,
    reviewed_dispositions_sha256: str,
    projection_tree: str,
    proof_runner_sha256: str,
) -> tuple[list[dict[str, Any]], Mapping[str, object]]:
    record = _mapping(
        copy.deepcopy(dict(value)),
        keys=frozenset(
            {
                "schema_version",
                "authority_status",
                "input_bindings",
                "counts",
                "candidate_rows",
            }
        ),
        label="observation candidates",
    )
    _completion_digest(record, expected_sha256, label="observation candidates")
    if (
        record["schema_version"]
        != "es_f1_witness_observation_candidates.v1"
        or record["authority_status"] != "NON_AUTHORITATIVE"
    ):
        _fail(
            "policy_candidate_observation_invalid",
            record,
            "observation candidate has unsupported status or version",
        )
    bindings = _mapping(record["input_bindings"], label="observation input_bindings")
    expected_bindings = {
        "discovery_input_sha256": discovery_input_sha256,
        "discovery_output_sha256": discovery_output_sha256,
        "draft_dispositions_sha256": reviewed_dispositions_sha256,
        "projection_tree": projection_tree,
        "runner_sha256": proof_runner_sha256,
    }
    if any(bindings.get(key) != expected for key, expected in expected_bindings.items()):
        _fail(
            "policy_candidate_observation_invalid",
            bindings,
            "observation inputs differ from the completion inputs",
        )
    _validated_pytest_carrier(
        bindings.get("pytest_carrier"),
        label="observation input_bindings.pytest_carrier",
    )
    _sha256(
        bindings.get("controller_module_order_sha256"),
        label="controller module order SHA-256",
    )
    counts = _mapping(
        record["counts"],
        keys=frozenset({"ambiguous", "observable", "open", "total"}),
        label="observation counts",
    )
    parsed_counts = {
        key: _integer(counts[key], label=f"observation counts.{key}")
        for key in counts
    }
    row_values = _list(
        record["candidate_rows"],
        label="observation candidate_rows",
        nonempty=True,
    )
    if len(row_values) != len(candidates) or parsed_counts["total"] != len(candidates):
        _fail(
            "policy_candidate_domain_invalid",
            parsed_counts,
            "observation candidate domain differs from discovery",
        )
    observations: list[dict[str, Any]] = []
    observed_counts = {"ambiguous": 0, "observable": 0, "open": 0}
    for index, (candidate, decision, value_row) in enumerate(
        zip(candidates, decisions, row_values, strict=True)
    ):
        row = _mapping(
            value_row,
            keys=_OBSERVATION_ROW_KEYS,
            label=f"observation candidate {index}",
        )
        identity = _completion_identity(
            {key: row[key] for key in _CANDIDATE_IDENTITY_KEYS},
            label=f"observation identity {index}",
        )
        if identity != candidate or any(
            row[key] != decision[decision_key]
            for key, decision_key in (
                ("proposed_disposition", "proposed_disposition"),
                ("required_proof_kind", "required_proof_kind"),
                ("selector_id", "selector_id"),
                ("witness_kind", "witness_kind"),
            )
        ):
            _fail(
                "policy_candidate_join_invalid",
                index,
                "observation candidate differs from discovery or dispositions",
            )
        status = _text(row["observation_status"], label="observation_status")
        if status not in observed_counts:
            _fail(
                "policy_candidate_observation_invalid",
                status,
                "observation status is unsupported",
            )
        _text(row["reason_code"], label="observation reason_code")
        choices = _list(row["executable_choices"], label="executable_choices")
        if (status == "observable" and len(choices) != 1) or (
            status != "observable" and choices
        ):
            _fail(
                "policy_candidate_choice_invalid",
                choices,
                "observable rows need exactly one choice and open rows need none",
            )
        normalized_spec = (
            _validated_completion_choice(
                choices[0], candidate=candidate, decision=decision
            )
            if choices
            else None
        )
        observations.append(
            {
                "observation_status": status,
                "normalized_spec": normalized_spec,
                "selector_id": (
                    choices[0]["selector_id"] if choices else decision["selector_id"]
                ),
                "witness_kind": (
                    choices[0]["witness_kind"] if choices else decision["witness_kind"]
                ),
            }
        )
        observed_counts[status] += 1
    if observed_counts != {
        "ambiguous": parsed_counts["ambiguous"],
        "observable": parsed_counts["observable"],
        "open": parsed_counts["open"],
    } or sum(observed_counts.values()) != parsed_counts["total"]:
        _fail(
            "policy_candidate_observation_invalid",
            parsed_counts,
            "observation counts do not equal the row domain",
        )
    return observations, bindings


def _completion_blob_bindings_by_path(
    discovery_input: Mapping[str, object],
    discovery_output: Mapping[str, object],
) -> dict[str, tuple[str, str]]:
    projection = _mapping(
        discovery_input["projection"], label="completion discovery projection"
    )
    repository = _canonical_repository(projection["repository"])
    leaves = _list(discovery_output["leaf_rows"], label="discovery leaf_rows")
    object_ids = [str(row["object_id"]) for row in leaves]
    blobs = _read_blobs(repository, object_ids)
    return {
        str(row["path"]): (
            raw_sha256(blobs[str(row["object_id"])]),
            str(row["object_id"]),
        )
        for row in leaves
    }


def _completion_controller_selectors(
    *,
    observation_bindings: Mapping[str, object],
    decisions: Sequence[Mapping[str, object]],
    witnesses: Sequence[Mapping[str, object]],
    provider_ids: set[str],
    blob_bindings_by_path: Mapping[str, tuple[str, str]],
    proof_runner_sha256: str,
) -> list[dict[str, object]]:
    raw_pytest_candidate = observation_bindings.get(
        "controller_pytest_selector_candidate"
    )
    pytest_candidate = _mapping(
        raw_pytest_candidate,
        keys=_CONTROLLER_CANDIDATE_KEYS,
        label="controller pytest selector candidate",
    )
    if (
        pytest_candidate["selector_id"] != "CO-PYTEST-01"
        or pytest_candidate["ordinal"] != 1
        or pytest_candidate["proof_kind"] != "boundary_runtime"
        or pytest_candidate["execution_kind"] != "pytest_aggregate"
        or pytest_candidate["runner_path"]
        != "scripts/experiments/es/boundary_proofs.py"
        or pytest_candidate["runner_sha256"] != proof_runner_sha256
    ):
        _fail(
            "policy_candidate_controller_invalid",
            pytest_candidate,
            "controller pytest declaration drifted",
        )
    argv = _texts(pytest_candidate["argv"], label="controller pytest argv")
    candidate_bindings: list[dict[str, str]] = []
    for value in _list(
        pytest_candidate["input_bindings"],
        label="controller pytest input_bindings",
        nonempty=True,
    ):
        row = _mapping(
            value,
            keys=frozenset({"path", "sha256"}),
            label="controller pytest input binding",
        )
        path = _relative_path(row["path"], label="controller pytest input path")
        sha256 = _sha256(row["sha256"], label="controller pytest input SHA-256")
        blob_binding = blob_bindings_by_path.get(path)
        if blob_binding is None or blob_binding[0] != sha256:
            _fail(
                "policy_candidate_controller_invalid",
                row,
                "controller pytest input does not bind the projection blob bytes",
            )
        candidate_bindings.append({"path": path, "sha256": sha256})
    projection_bindings: list[dict[str, str]] = []
    for value in _list(
        pytest_candidate["projection_bindings"],
        label="controller pytest projection_bindings",
        nonempty=True,
    ):
        row = _mapping(
            value,
            keys=frozenset({"path", "projection_blob_id"}),
            label="controller pytest projection binding",
        )
        path = _relative_path(
            row["path"], label="controller pytest projection path"
        )
        projection_blob_id = _sha1(
            row["projection_blob_id"],
            label="controller pytest projection blob ID",
        )
        blob_binding = blob_bindings_by_path.get(path)
        if blob_binding is None or blob_binding[1] != projection_blob_id:
            _fail(
                "policy_candidate_controller_invalid",
                row,
                "controller pytest projection does not bind the discovery blob",
            )
        projection_bindings.append(
            {"path": path, "projection_blob_id": projection_blob_id}
        )
    if [row["path"] for row in projection_bindings] != [
        row["path"] for row in candidate_bindings
    ] or argv[-len(candidate_bindings) :] != [
        row["path"] for row in candidate_bindings
    ]:
        _fail(
            "policy_candidate_controller_invalid",
            pytest_candidate,
            "controller pytest argv and input path order differ",
        )
    witness_ids_by_selector: dict[str, list[str]] = {}
    for witness in witnesses:
        witness_ids_by_selector.setdefault(str(witness["selector_id"]), []).append(
            str(witness["witness_id"])
        )
    ordered_controller_ids = ["CO-PYTEST-01"]
    for decision in decisions:
        selector_id = str(decision["selector_id"])
        if (
            selector_id not in provider_ids
            and selector_id not in ordered_controller_ids
        ):
            ordered_controller_ids.append(selector_id)
    selectors: list[dict[str, object]] = []
    for ordinal, selector_id in enumerate(ordered_controller_ids, 1):
        backpointers = witness_ids_by_selector.get(selector_id, [])
        if len(backpointers) > 1:
            _fail(
                "coverage_witness_join_invalid",
                {"selector_id": selector_id, "witness_ids": backpointers},
                "controller selector may own at most one witness",
            )
        if selector_id == "CO-PYTEST-01":
            selectors.append(
                {
                    "selector_id": selector_id,
                    "ordinal": ordinal,
                    "proof_kind": "boundary_runtime",
                    "execution_kind": "pytest_aggregate",
                    "runner_path": "scripts/experiments/es/boundary_proofs.py",
                    "runner_sha256": proof_runner_sha256,
                    "argv": argv,
                    "input_bindings": candidate_bindings,
                    "coverage_witness_ids": backpointers,
                }
            )
            continue
        assigned = [
            decision
            for decision in decisions
            if decision["selector_id"] == selector_id
        ]
        proof_kinds = {str(row["required_proof_kind"]) for row in assigned}
        witness_kinds = {str(row["witness_kind"]) for row in assigned}
        if len(proof_kinds) != 1 or len(witness_kinds) != 1:
            _fail(
                "policy_candidate_controller_invalid",
                selector_id,
                "controller selector has incompatible consumer classes",
            )
        proof_kind = next(iter(proof_kinds))
        witness_kind = next(iter(witness_kinds))
        execution_kind = {
            "runtime_probe": "isolated_probe",
            "static_ast": "static_ast",
        }.get(witness_kind)
        if execution_kind is None:
            _fail(
                "policy_candidate_controller_invalid",
                witness_kind,
                "controller selector kind lacks an executable declaration",
            )
        paths = list(
            dict.fromkeys(str(row["caller_path"]) for row in assigned)
        )
        try:
            input_bindings = [
                {"path": path, "sha256": blob_bindings_by_path[path][0]}
                for path in paths
            ]
        except KeyError as exc:
            _fail(
                "policy_candidate_controller_invalid",
                str(exc),
                "controller selector path is absent from the discovery projection",
            )
        selectors.append(
            {
                "selector_id": selector_id,
                "ordinal": ordinal,
                "proof_kind": proof_kind,
                "execution_kind": execution_kind,
                "runner_path": "scripts/experiments/es/boundary_proofs.py",
                "runner_sha256": proof_runner_sha256,
                "argv": [execution_kind, "--selector-id", selector_id],
                "input_bindings": input_bindings,
                "coverage_witness_ids": backpointers,
            }
        )
    return selectors


def complete_policy_candidate(
    discovery_input: Mapping[str, object],
    *,
    discovery_output: Mapping[str, object],
    observation_candidates: Mapping[str, object],
    reviewed_dispositions: Mapping[str, object],
    expected_discovery_input_sha256: str,
    expected_discovery_output_sha256: str,
    expected_observation_candidates_sha256: str,
    expected_reviewed_dispositions_sha256: str,
    producer_sha256: str,
    proof_runner_sha256: str,
    no_consumption_captured_at: str,
    a1_evidence_root: str,
) -> dict[str, object]:
    """Classify every discovered consumer without publishing policy authority."""

    producer_digest = _sha256(producer_sha256, label="producer_sha256")
    runner_digest = _sha256(proof_runner_sha256, label="proof_runner_sha256")
    actual_producer_digest = raw_sha256(Path(__file__).resolve().read_bytes())
    actual_runner_digest = raw_sha256(
        (REPOSITORY_ROOT / "scripts/experiments/es/boundary_proofs.py").read_bytes()
    )
    if producer_digest != actual_producer_digest:
        _fail(
            "producer_digest_mismatch",
            producer_digest,
            "policy candidate producer bytes drifted",
        )
    if runner_digest != actual_runner_digest:
        _fail(
            "selector_runner_invalid",
            runner_digest,
            "policy candidate proof-runner bytes drifted",
        )
    validated_input, validated_output, candidates = _validate_completion_discovery(
        discovery_input,
        discovery_output=discovery_output,
        expected_discovery_input_sha256=expected_discovery_input_sha256,
        expected_discovery_output_sha256=expected_discovery_output_sha256,
    )
    input_digest = _sha256(
        expected_discovery_input_sha256,
        label="expected discovery input SHA-256",
    )
    output_digest = _sha256(
        expected_discovery_output_sha256,
        label="expected discovery output SHA-256",
    )
    disposition_digest = _sha256(
        expected_reviewed_dispositions_sha256,
        label="expected reviewed dispositions SHA-256",
    )
    observation_digest = _sha256(
        expected_observation_candidates_sha256,
        label="expected observation candidates SHA-256",
    )
    projection_tree = _sha1(
        validated_input["projection"]["tree"], label="projection tree"
    )
    decisions = _validate_completion_decisions(
        reviewed_dispositions,
        candidates=candidates,
        expected_sha256=disposition_digest,
        discovery_output_sha256=output_digest,
        candidate_set_sha256=str(validated_output["candidate_set_sha256"]),
        discovery_input_sha256=input_digest,
        projection_repository=str(validated_input["projection"]["repository"]),
        projection_commit=str(validated_input["projection"]["commit"]),
        projection_tree=projection_tree,
        leaf_rows=_list(validated_output["leaf_rows"], label="discovery leaf_rows"),
    )
    observations, observation_bindings = _validate_completion_observations(
        observation_candidates,
        candidates=candidates,
        decisions=decisions,
        expected_sha256=observation_digest,
        discovery_input_sha256=input_digest,
        discovery_output_sha256=output_digest,
        reviewed_dispositions_sha256=disposition_digest,
        projection_tree=projection_tree,
        proof_runner_sha256=runner_digest,
    )
    provider_rows = copy.deepcopy(
        validated_input["provider_visible_pytest_selectors"]
    )
    provider_ids = {str(row["selector_id"]) for row in provider_rows}
    first_by_provider: dict[str, int] = {}
    first_by_class: dict[tuple[str, str], int] = {}
    populated_classes: set[tuple[str, str]] = set()
    effective_decisions = [
        {
            **decision,
            "selector_id": observation["selector_id"],
            "witness_kind": observation["witness_kind"],
        }
        for decision, observation in zip(decisions, observations, strict=True)
    ]
    for index, (decision, observation) in enumerate(
        zip(effective_decisions, observations, strict=True)
    ):
        candidate_class = (
            str(decision["proposed_disposition"]),
            str(decision["witness_kind"]),
        )
        populated_classes.add(candidate_class)
        if observation["observation_status"] != "observable":
            continue
        first_by_class.setdefault(candidate_class, index)
        selector_id = str(decision["selector_id"])
        if (
            selector_id in provider_ids
            and decision["witness_kind"] == "pytest_runtime"
        ):
            first_by_provider.setdefault(selector_id, index)
    missing_providers = provider_ids - set(first_by_provider)
    missing_classes = populated_classes - set(first_by_class)
    if missing_providers or missing_classes:
        _fail(
            "coverage_required_sample_missing",
            {
                "provider_selectors": sorted(missing_providers),
                "classes": sorted(missing_classes),
            },
            "every provider selector and populated class needs an observable sample",
        )
    selected_indexes = set(first_by_provider.values()) | set(first_by_class.values())
    consumer_policies: list[dict[str, object]] = []
    witnesses: list[dict[str, object]] = []
    desired_specs: list[dict[str, object]] = []
    for index, (candidate, decision, observation) in enumerate(
        zip(candidates, effective_decisions, observations, strict=True)
    ):
        status = (
            "required"
            if index in selected_indexes
            else "inherited"
            if observation["observation_status"] == "observable"
            else "open"
        )
        candidate_witness_ids = list(decision["coverage_witness_ids"])
        coverage_witness_ids = candidate_witness_ids if status == "required" else []
        consumer_policies.append(
            {
                "consumer_id": candidate["consumer_id"],
                "match_id": candidate["match_id"],
                "proposed_disposition": decision["proposed_disposition"],
                "required_proof_kind": decision["required_proof_kind"],
                "selector_id": decision["selector_id"],
                "witness_kind": decision["witness_kind"],
                "coverage_status": status,
                "coverage_witness_ids": coverage_witness_ids,
            }
        )
        if status != "required":
            continue
        normalized_spec = observation["normalized_spec"]
        if normalized_spec is None:
            _fail(
                "coverage_required_sample_missing",
                candidate["consumer_id"],
                "required consumer lacks an executable witness payload",
            )
        witness_id = candidate_witness_ids[0]
        witnesses.append(
            {
                "witness_id": witness_id,
                "witness_kind": decision["witness_kind"],
                "selector_id": decision["selector_id"],
                "consumer_id": candidate["consumer_id"],
                "required_proof_kind": decision["required_proof_kind"],
                "spec": copy.deepcopy(normalized_spec),
            }
        )
        desired_specs.append(
            {
                "proof_spec_id": "proof-" + str(candidate["consumer_id"]),
                "witness_id": witness_id,
                "proof_kind": decision["required_proof_kind"],
                "expected_result": copy.deepcopy(normalized_spec["expected_event"]),
            }
        )
    blob_bindings_by_path = _completion_blob_bindings_by_path(
        validated_input, validated_output
    )
    controllers = _completion_controller_selectors(
        observation_bindings=observation_bindings,
        decisions=effective_decisions,
        witnesses=witnesses,
        provider_ids=provider_ids,
        blob_bindings_by_path=blob_bindings_by_path,
        proof_runner_sha256=runner_digest,
    )
    selector_policy: dict[str, object] = {
        "sampling_rule": _SAMPLING_RULE,
        "pytest_carrier": _validated_pytest_carrier(
            observation_bindings.get("pytest_carrier"),
            label="observation input_bindings.pytest_carrier",
        ),
        "provider_visible_pytest_selectors": provider_rows,
        "controller_only_proof_selectors": controllers,
        "coverage_witness_specs": witnesses,
        "desired_state_proof_specs": desired_specs,
    }
    consumers = {
        str(candidate["consumer_id"]): {
            **candidate,
            **consumer_policy,
        }
        for candidate, consumer_policy in zip(
            candidates, consumer_policies, strict=True
        )
    }
    _validate_selector_policy(
        selector_policy,
        discovery_input=validated_input,
        consumers=consumers,
    )
    observable_count = sum(
        row["observation_status"] == "observable" for row in observations
    )
    counts = {
        "total": len(candidates),
        "observable": observable_count,
        "required": len(selected_indexes),
        "inherited": observable_count - len(selected_indexes),
        "open": len(candidates) - observable_count,
    }
    captured_at = _text(
        no_consumption_captured_at,
        label="no-consumption captured_at",
    )
    try:
        parsed_captured_at = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceCensusError(
            "no_consumption_timestamp_invalid",
            captured_at,
            "captured_at is not an ISO-8601 timestamp",
        ) from exc
    if parsed_captured_at.tzinfo is None or parsed_captured_at.utcoffset() is None:
        _fail(
            "no_consumption_timestamp_invalid",
            captured_at,
            "captured_at must include an explicit UTC offset",
        )
    external_observations = [
        _observe_external_root(path) for path in FROZEN_NO_CONSUMPTION_EXTERNAL_ROOTS
    ]
    repository_observations = [
        _observe_repository_path(path)
        for path in FROZEN_NO_CONSUMPTION_REPOSITORY_PATHS
    ]
    no_consumption = {
        "captured_at": captured_at,
        "external_roots": external_observations,
        "repository_paths": repository_observations,
        "observation_sha256": no_consumption_observation_sha256(
            external_observations,
            repository_observations,
        ),
    }
    _validate_no_consumption(no_consumption, reobserve=True)
    calibration = _reference_calibration_module()
    root = _canonical_absolute_path(a1_evidence_root, label="A1 evidence root")
    if root != calibration.A1_EVIDENCE_ROOT:
        _fail(
            "a1_policy_invalid",
            str(root),
            "A1 evidence root differs from the accepted explicit root",
        )
    git_contract = calibration.GitContract(
        executable=calibration.PINNED_GIT_EXECUTABLE,
        version=calibration.PINNED_GIT_VERSION,
        executable_sha256=calibration.PINNED_GIT_EXECUTABLE_SHA256,
        diff_controls=tuple(calibration.PINNED_GIT_DIFF_CONTROLS),
        policy_sha256=raw_sha256(canonical_json_bytes(validated_input["git"])),
    )
    try:
        calibration.verify_git_contract(git_contract)
        anchor = calibration.build_a1_anchor(
            evidence_root=root,
            preedit_policy_sha256=input_digest,
            git_contract=git_contract,
        )
    except Exception as exc:
        raise SourceCensusError(
            "a1_policy_invalid",
            str(root),
            "A1 evidence members, bindings, or fresh metric failed validation",
        ) from exc
    a1 = {
        "evidence_root": str(root),
        "members": copy.deepcopy(anchor["members"]),
        "metric": {
            "metric_version": "implementation_delta_physical_lines.v1",
            "git_executable": str(PINNED_GIT),
            "git_version": PINNED_GIT_VERSION,
            "git_sha256": PINNED_GIT_SHA256,
            "diff_controls": copy.deepcopy(_DIFF_CONTROLS),
            "implementation_additions": anchor["metric"]["implementation_additions"],
            "implementation_deletions": anchor["metric"]["implementation_deletions"],
            "candidate_postimage_physical_lines": anchor["metric"][
                "candidate_postimage_physical_lines"
            ],
        },
    }
    _validate_a1_policy(a1)
    leaf_rows = _list(validated_output["leaf_rows"], label="discovery leaf_rows")
    if validated_input["projection"]["commit"] == FROZEN_PROJECTION_COMMIT:
        audit_groups = frozen_audit_groups(leaf_rows)
    else:
        leaves_by_path = {str(row["path"]): row for row in leaf_rows}
        fixture_paths = list(
            dict.fromkeys(str(row["caller_path"]) for row in candidates)
        )
        audit_groups = [
            {
                "group_id": "NON_FROZEN_TEST_PROJECTION",
                "paths": fixture_paths,
                "expected_physical_line_count": sum(
                    int(leaves_by_path[path]["text"]["physical_line_count"])
                    for path in fixture_paths
                ),
            }
        ]
    policy_body = {
        "schema_version": "es_f1_preedit_policy.v1",
        "discovery": {
            "input_sha256": input_digest,
            "output_sha256": output_digest,
            "candidate_set_sha256": validated_output["candidate_set_sha256"],
        },
        "git": copy.deepcopy(validated_input["git"]),
        "projection": copy.deepcopy(validated_input["projection"]),
        "schema_bindings": current_schema_bindings(),
        "lineage": current_lineage_bindings(),
        "detectors": copy.deepcopy(validated_input["detectors"]),
        "responsibilities": copy.deepcopy(validated_input["responsibilities"]),
        "consumer_policies": consumer_policies,
        "selector_policy": selector_policy,
        "audit_groups": audit_groups,
        "legacy_bypass_consumer_ids": [
            row["consumer_id"]
            for row in candidates
            if "LEGACY_BYPASS_RETIREMENT" in row["responsibility_ids"]
        ],
        "no_consumption": no_consumption,
        "a1": a1,
    }
    return {
        "schema_version": "es_f1_complete_policy_candidate.v1",
        "authority_status": "NON_AUTHORITATIVE",
        "input_bindings": {
            "discovery_input_sha256": input_digest,
            "discovery_output_sha256": output_digest,
            "observation_candidates_sha256": observation_digest,
            "reviewed_dispositions_sha256": disposition_digest,
            "producer_sha256": producer_digest,
            "proof_runner_sha256": runner_digest,
            "projection_tree": projection_tree,
            "candidate_set_sha256": validated_output["candidate_set_sha256"],
            "no_consumption_captured_at": captured_at,
            "a1_evidence_root": str(root),
        },
        "counts": counts,
        "policy_body": policy_body,
    }


def _offset_datetime(value: object, *, label: str) -> datetime:
    text = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceCensusError(
            "witness_review_timestamp_invalid",
            text,
            f"{label} is not an ISO-8601 timestamp",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(
            "witness_review_timestamp_invalid",
            text,
            f"{label} must include an explicit UTC offset",
        )
    return parsed


def _validated_witness_review_record(
    value: Mapping[str, object],
    *,
    expected_sha256: str,
    expected_kind: str,
    expected_verdict: str,
    label: str,
) -> tuple[dict[str, Any], datetime]:
    record = _mapping(
        copy.deepcopy(dict(value)),
        keys=frozenset(
            {
                "schema_version",
                "review_kind",
                "verdict",
                "reviewer",
                "reviewed_at",
                "candidate_files",
                "candidate_set_sha256",
                "findings",
            }
        ),
        label=label,
    )
    if raw_sha256(canonical_json_bytes(record)) != _sha256(
        expected_sha256, label=f"expected {label} SHA-256"
    ):
        _fail("witness_review_digest_mismatch", label, "review raw digest drifted")
    if (
        record["schema_version"] != "es_f1_witness_observability_review.v1"
        or record["review_kind"] != expected_kind
        or record["verdict"] != expected_verdict
        or record["findings"] != []
    ):
        _fail(
            "witness_review_status_invalid",
            record,
            f"{label} is not the exact approved review",
        )
    _text(record["reviewer"], label=f"{label}.reviewer")
    reviewed_at = _offset_datetime(record["reviewed_at"], label=f"{label}.reviewed_at")
    candidate_files: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for value_row in _list(
        record["candidate_files"], label=f"{label}.candidate_files", nonempty=True
    ):
        row = _mapping(
            value_row,
            keys=frozenset({"path", "sha256"}),
            label=f"{label} candidate file",
        )
        path = _relative_path(row["path"], label=f"{label} candidate path")
        if path in seen_paths:
            _fail("witness_review_candidate_invalid", path, "candidate paths repeat")
        seen_paths.add(path)
        candidate_files.append(
            {
                "path": path,
                "sha256": _sha256(
                    row["sha256"], label=f"{label} candidate sha256"
                ),
            }
        )
    candidate_set_sha256 = _sha256(
        record["candidate_set_sha256"],
        label=f"{label}.candidate_set_sha256",
    )
    if raw_sha256(canonical_json_bytes(candidate_files)) != candidate_set_sha256:
        _fail(
            "witness_review_candidate_invalid",
            candidate_set_sha256,
            "review candidate-set digest drifted",
        )
    record["candidate_files"] = candidate_files
    return record, reviewed_at


def _validate_complete_policy_candidate(
    value: Mapping[str, object], *, expected_sha256: str
) -> dict[str, Any]:
    candidate = _mapping(
        copy.deepcopy(dict(value)),
        keys=_COMPLETE_POLICY_CANDIDATE_KEYS,
        label="complete policy candidate",
    )
    if raw_sha256(canonical_json_bytes(candidate)) != _sha256(
        expected_sha256, label="expected complete candidate SHA-256"
    ):
        _fail(
            "policy_candidate_digest_mismatch",
            expected_sha256,
            "complete candidate raw digest drifted",
        )
    if (
        candidate["schema_version"] != "es_f1_complete_policy_candidate.v1"
        or candidate["authority_status"] != "NON_AUTHORITATIVE"
    ):
        _fail(
            "policy_candidate_status_invalid",
            candidate,
            "complete candidate is not the closed non-authoritative v1 shape",
        )
    bindings = _mapping(
        candidate["input_bindings"],
        keys=_COMPLETE_POLICY_INPUT_BINDING_KEYS,
        label="complete candidate input_bindings",
    )
    for key in (
        "discovery_input_sha256",
        "discovery_output_sha256",
        "observation_candidates_sha256",
        "reviewed_dispositions_sha256",
        "producer_sha256",
        "proof_runner_sha256",
        "candidate_set_sha256",
    ):
        _sha256(bindings[key], label=f"complete candidate {key}")
    _sha1(bindings["projection_tree"], label="complete candidate projection_tree")
    _offset_datetime(
        bindings["no_consumption_captured_at"],
        label="complete candidate no-consumption captured_at",
    )
    a1_root = _canonical_absolute_path(
        bindings["a1_evidence_root"], label="complete candidate A1 root"
    )
    counts = _mapping(
        candidate["counts"],
        keys=_COMPLETE_POLICY_COUNT_KEYS,
        label="complete candidate counts",
    )
    for key, count in counts.items():
        _integer(count, label=f"complete candidate counts.{key}")
    if (
        counts["observable"] != counts["required"] + counts["inherited"]
        or counts["total"] != counts["observable"] + counts["open"]
    ):
        _fail(
            "policy_candidate_counts_invalid",
            counts,
            "complete candidate counts do not partition the domain",
        )
    body = _mapping(
        candidate["policy_body"],
        keys=_POLICY_CANDIDATE_BODY_KEYS,
        label="complete candidate policy_body",
    )
    if body["schema_version"] != "es_f1_preedit_policy.v1":
        _fail("policy_version_invalid", body["schema_version"], "unsupported policy version")
    discovery = _mapping(
        body["discovery"],
        keys=frozenset({"input_sha256", "output_sha256", "candidate_set_sha256"}),
        label="complete candidate discovery",
    )
    if discovery != {
        "input_sha256": bindings["discovery_input_sha256"],
        "output_sha256": bindings["discovery_output_sha256"],
        "candidate_set_sha256": bindings["candidate_set_sha256"],
    }:
        _fail(
            "policy_candidate_binding_mismatch",
            discovery,
            "policy body discovery bindings drifted",
        )
    projection = _mapping(body["projection"], keys=_PROJECTION_KEYS, label="projection")
    if projection["tree"] != bindings["projection_tree"]:
        _fail(
            "policy_candidate_binding_mismatch",
            projection["tree"],
            "policy body projection tree drifted",
        )
    if body["schema_bindings"] != current_schema_bindings():
        _fail(
            "schema_binding_invalid",
            body["schema_bindings"],
            "complete candidate schema bindings are stale",
        )
    if body["lineage"] != current_lineage_bindings():
        _fail(
            "lineage_binding_invalid",
            body["lineage"],
            "complete candidate lineage bindings are stale",
        )
    try:
        actual_producer = raw_sha256(Path(__file__).resolve().read_bytes())
        actual_runner = raw_sha256(
            (REPOSITORY_ROOT / "scripts/experiments/es/boundary_proofs.py").read_bytes()
        )
    except OSError as exc:
        raise SourceCensusError(
            "producer_unreadable", None, "candidate producers cannot be reread"
        ) from exc
    if (
        bindings["producer_sha256"] != actual_producer
        or bindings["proof_runner_sha256"] != actual_runner
    ):
        _fail(
            "producer_digest_mismatch",
            bindings,
            "complete candidate producer bytes drifted",
        )
    policies = _list(body["consumer_policies"], label="consumer_policies", nonempty=True)
    if len(policies) != counts["total"]:
        _fail(
            "policy_candidate_counts_invalid",
            len(policies),
            "consumer policy count differs from complete candidate total",
        )
    observed_status_counts = {status: 0 for status in _COVERAGE_STATUSES}
    for value_row in policies:
        row = _mapping(value_row, keys=_CONSUMER_POLICY_KEYS, label="consumer policy")
        status = row["coverage_status"]
        if status not in observed_status_counts:
            _fail("consumer_coverage_status_invalid", status, "unsupported coverage status")
        observed_status_counts[status] += 1
    if any(
        observed_status_counts[status] != counts[status]
        for status in _COVERAGE_STATUSES
    ):
        _fail(
            "policy_candidate_counts_invalid",
            observed_status_counts,
            "coverage statuses differ from candidate counts",
        )
    no_consumption = _validate_no_consumption(body["no_consumption"], reobserve=True)
    if no_consumption["captured_at"] != bindings["no_consumption_captured_at"]:
        _fail(
            "policy_candidate_binding_mismatch",
            no_consumption["captured_at"],
            "no-consumption timestamp differs from candidate binding",
        )
    a1 = _validate_a1_policy(body["a1"])
    if Path(a1["evidence_root"]) != a1_root:
        _fail(
            "policy_candidate_binding_mismatch",
            a1["evidence_root"],
            "A1 root differs from candidate binding",
        )
    calibration = _reference_calibration_module()
    try:
        calibration.validate_a1_member_files(a1_root, a1["members"])
    except Exception as exc:
        raise SourceCensusError(
            "a1_policy_invalid",
            str(a1_root),
            "A1 member bytes drifted before publication",
        ) from exc
    return candidate


def publish_policy_candidate(
    candidate: Mapping[str, object],
    *,
    expected_candidate_sha256: str,
    current_plan_sha256: str,
    plan_specification_review: Mapping[str, object],
    expected_plan_specification_review_sha256: str,
    plan_quality_review: Mapping[str, object],
    expected_plan_quality_review_sha256: str,
    implementation_review: Mapping[str, object],
    expected_implementation_review_sha256: str,
    policy_schema: str | Path,
) -> dict[str, object]:
    """Promote one exact reviewed candidate into the sole canonical policy shape."""

    validated_candidate = _validate_complete_policy_candidate(
        candidate, expected_sha256=expected_candidate_sha256
    )
    plan_sha256 = _sha256(current_plan_sha256, label="current correction plan SHA-256")
    plan_spec, spec_time = _validated_witness_review_record(
        plan_specification_review,
        expected_sha256=expected_plan_specification_review_sha256,
        expected_kind="plan_specification",
        expected_verdict="ES_F1_WITNESS_PLAN_SPEC_APPROVED",
        label="plan specification review",
    )
    plan_quality, quality_time = _validated_witness_review_record(
        plan_quality_review,
        expected_sha256=expected_plan_quality_review_sha256,
        expected_kind="plan_quality",
        expected_verdict="ES_F1_WITNESS_PLAN_QUALITY_APPROVED",
        label="plan quality review",
    )
    implementation, implementation_time = _validated_witness_review_record(
        implementation_review,
        expected_sha256=expected_implementation_review_sha256,
        expected_kind="implementation",
        expected_verdict="ES_F1_WITNESS_IMPLEMENTATION_APPROVED",
        label="implementation review",
    )
    expected_plan_paths = [
        _WITNESS_PLAN_PATH,
        "docs/plans/2026-08-03-es-f1-large-scope-refreeze-execution-plan.md",
    ]
    if (
        [row["path"] for row in plan_spec["candidate_files"]]
        != expected_plan_paths
        or plan_quality["candidate_files"] != plan_spec["candidate_files"]
    ):
        _fail(
            "witness_review_candidate_invalid",
            plan_quality["candidate_files"],
            "plan reviews do not bind the exact same historical plan pair",
        )
    current_implementation_files = [
        {
            "path": path,
            "sha256": raw_sha256(_stable_regular_file_under_root(
                REPOSITORY_ROOT,
                path,
                error_code="witness_review_candidate_invalid",
                label="implementation review candidate",
            )),
        }
        for path in _WITNESS_IMPLEMENTATION_CANDIDATE_PATHS
    ]
    if implementation["candidate_files"] != current_implementation_files:
        _fail(
            "witness_review_candidate_invalid",
            implementation["candidate_files"],
            "implementation review does not bind the exact current candidate set",
        )
    captured_at = _offset_datetime(
        validated_candidate["input_bindings"]["no_consumption_captured_at"],
        label="complete candidate no-consumption captured_at",
    )
    if quality_time < spec_time or implementation_time < quality_time or implementation_time < captured_at:
        _fail(
            "witness_review_order_invalid",
            {
                "plan_specification": plan_spec["reviewed_at"],
                "plan_quality": plan_quality["reviewed_at"],
                "implementation": implementation["reviewed_at"],
                "candidate_capture": validated_candidate["input_bindings"][
                    "no_consumption_captured_at"
                ],
            },
            "review timestamps violate the required order",
        )
    reviews = {
        "plan": {"path": _WITNESS_PLAN_PATH, "sha256": plan_sha256},
        "plan_specification_review": {
            "path": _WITNESS_PLAN_SPEC_REVIEW_PATH,
            "sha256": _sha256(
                expected_plan_specification_review_sha256,
                label="plan specification review SHA-256",
            ),
            "verdict": plan_spec["verdict"],
        },
        "plan_quality_review": {
            "path": _WITNESS_PLAN_QUALITY_REVIEW_PATH,
            "sha256": _sha256(
                expected_plan_quality_review_sha256,
                label="plan quality review SHA-256",
            ),
            "verdict": plan_quality["verdict"],
        },
        "implementation_review": {
            "path": _WITNESS_IMPLEMENTATION_REVIEW_PATH,
            "sha256": _sha256(
                expected_implementation_review_sha256,
                label="implementation review SHA-256",
            ),
            "verdict": implementation["verdict"],
            "candidate_set_sha256": implementation["candidate_set_sha256"],
        },
    }
    _validate_witness_observability_reviews(reviews)
    policy: dict[str, object] = {
        **copy.deepcopy(validated_candidate["policy_body"]),
        "witness_observability_reviews": reviews,
    }
    policy["record_sha256"] = compute_record_sha256(policy)
    _validate_schema(policy, policy_schema, label="pre-edit policy")
    return policy


def frozen_audit_groups(
    leaf_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Materialize and independently verify the nine plan-frozen audit slices."""

    by_path = {str(row.get("path")): row for row in leaf_rows}
    if len(by_path) != len(leaf_rows):
        _fail("audit_group_invalid", None, "leaf paths repeat")
    groups: list[dict[str, object]] = []
    for group_id, paths, expected_total in _FROZEN_AUDIT_GROUP_SPECS:
        missing = [path for path in paths if path not in by_path]
        if missing:
            _fail("audit_group_invalid", missing, f"{group_id} paths are missing")
        observed_total = 0
        for path in paths:
            text = _mapping(by_path[path].get("text"), label=f"{group_id} text")
            physical = text.get("physical_line_count")
            if isinstance(physical, bool) or not isinstance(physical, int):
                _fail(
                    "audit_group_invalid",
                    {"path": path, "physical_line_count": physical},
                    f"{group_id} contains a non-text leaf",
                )
            observed_total += physical
        if observed_total != expected_total:
            _fail(
                "audit_group_invalid",
                {"group_id": group_id, "expected": expected_total, "actual": observed_total},
                "frozen physical-line subtotal drifted",
            )
        groups.append(
            {
                "group_id": group_id,
                "paths": list(paths),
                "expected_physical_line_count": expected_total,
            }
        )
    return groups


def _validate_witness_observability_reviews(value: object) -> dict[str, Any]:
    reviews = _mapping(
        value,
        keys=_WITNESS_REVIEWS_KEYS,
        label="witness_observability_reviews",
    )
    plan = _mapping(
        reviews["plan"],
        keys=frozenset({"path", "sha256"}),
        label="witness review plan binding",
    )
    if plan["path"] != _WITNESS_PLAN_PATH:
        _fail("witness_review_binding_invalid", plan, "current plan path drifted")
    _sha256(plan["sha256"], label="witness review plan sha256")
    expected = (
        (
            "plan_specification_review",
            _WITNESS_PLAN_SPEC_REVIEW_PATH,
            "ES_F1_WITNESS_PLAN_SPEC_APPROVED",
            False,
        ),
        (
            "plan_quality_review",
            _WITNESS_PLAN_QUALITY_REVIEW_PATH,
            "ES_F1_WITNESS_PLAN_QUALITY_APPROVED",
            False,
        ),
        (
            "implementation_review",
            _WITNESS_IMPLEMENTATION_REVIEW_PATH,
            "ES_F1_WITNESS_IMPLEMENTATION_APPROVED",
            True,
        ),
    )
    for key, path, verdict, carries_candidate_set in expected:
        keys = {"path", "sha256", "verdict"}
        if carries_candidate_set:
            keys.add("candidate_set_sha256")
        row = _mapping(
            reviews[key],
            keys=frozenset(keys),
            label=f"witness review {key}",
        )
        if row["path"] != path or row["verdict"] != verdict:
            _fail(
                "witness_review_binding_invalid",
                row,
                f"{key} path or verdict drifted",
            )
        _sha256(row["sha256"], label=f"{key}.sha256")
        if carries_candidate_set:
            _sha256(
                row["candidate_set_sha256"],
                label=f"{key}.candidate_set_sha256",
            )
    return reviews


def _validate_policy(
    value: Mapping[str, object],
    *,
    discovery_input: Mapping[str, object],
    discovery_output: Mapping[str, object],
    discovery_input_sha256: str | None = None,
) -> dict[str, Any]:
    policy = _mapping(copy.deepcopy(dict(value)), keys=_POLICY_KEYS, label="pre-edit policy")
    if policy["schema_version"] != "es_f1_preedit_policy.v1":
        _fail("policy_version_invalid", policy["schema_version"], "unsupported policy version")
    try:
        validate_record_sha256(policy)
    except Exception as exc:
        raise SourceCensusError(
            "policy_record_sha256_invalid", policy.get("record_sha256"), "policy digest failed"
        ) from exc
    input_digest = discovery_input_sha256 or raw_sha256(
        canonical_json_bytes(discovery_input)
    )
    discovery_binding = _mapping(
        policy["discovery"],
        keys=frozenset({"input_sha256", "output_sha256", "candidate_set_sha256"}),
        label="policy.discovery",
    )
    expected_discovery = {
        "input_sha256": input_digest,
        "output_sha256": raw_sha256(canonical_json_bytes(discovery_output)),
        "candidate_set_sha256": discovery_output.get("candidate_set_sha256"),
    }
    if discovery_binding != expected_discovery:
        _fail(
            "policy_discovery_binding_mismatch",
            discovery_binding,
            "policy does not bind exact discovery input/output/candidate set",
        )
    if (
        policy["git"] != discovery_input["git"]
        or policy["projection"] != discovery_input["projection"]
        or policy["detectors"] != discovery_input["detectors"]
        or policy["responsibilities"] != discovery_input["responsibilities"]
    ):
        _fail(
            "policy_source_binding_mismatch",
            policy,
            "policy source contracts differ from discovery input",
        )
    expected_schema_bindings = current_schema_bindings()
    if policy["schema_bindings"] != expected_schema_bindings:
        _fail(
            "schema_binding_invalid",
            policy["schema_bindings"],
            "policy does not bind the exact retained closed-schema bytes",
        )
    expected_lineage = current_lineage_bindings()
    if policy["lineage"] != expected_lineage:
        _fail(
            "lineage_binding_invalid",
            policy["lineage"],
            "policy source/closure/task-input lineage drifted",
        )
    _validate_git_contract(policy["git"])
    _validate_projection(policy["projection"])
    candidate_rows = _list(
        discovery_output.get("consumer_candidates"),
        label="discovery consumer_candidates",
        nonempty=True,
    )
    candidates = {str(row["consumer_id"]): row for row in candidate_rows}
    if len(candidates) != len(candidate_rows):
        _fail("consumer_policy_mismatch", candidate_rows, "discovery consumer IDs repeat")
    policies: dict[str, dict[str, Any]] = {}
    for value_row in _list(policy["consumer_policies"], label="consumer_policies", nonempty=True):
        row = _mapping(value_row, keys=_CONSUMER_POLICY_KEYS, label="consumer policy")
        consumer_id = _text(row["consumer_id"], label="consumer policy.consumer_id")
        match_id = _text(row["match_id"], label="consumer policy.match_id")
        if consumer_id in policies or consumer_id not in candidates:
            _fail("consumer_policy_mismatch", row, "consumer policy is duplicate or unknown")
        if match_id != candidates[consumer_id]["match_id"]:
            _fail("consumer_policy_mismatch", row, "consumer/match binding drifted")
        disposition = row["proposed_disposition"]
        if disposition not in _DISPOSITION_PROOF:
            _fail("consumer_policy_mismatch", row, "unsupported proposed disposition")
        if row["required_proof_kind"] != _DISPOSITION_PROOF[disposition]:
            _fail("consumer_policy_mismatch", row, "disposition/proof mapping drifted")
        _unique_texts(
            row["coverage_witness_ids"],
            label="coverage_witness_ids",
            nonempty=False,
        )
        policies[consumer_id] = row
    if set(policies) != set(candidates):
        _fail(
            "consumer_policy_mismatch",
            sorted(set(candidates) ^ set(policies)),
            "policy consumer domain is not exact",
        )
    if list(policies) != list(candidates):
        _fail(
            "consumer_policy_mismatch",
            list(policies),
            "policy consumers must retain discovery order",
        )
    selector_consumers = {
        consumer_id: {**candidates[consumer_id], **policy_row}
        for consumer_id, policy_row in policies.items()
    }
    _validate_selector_policy(
        policy["selector_policy"],
        discovery_input=discovery_input,
        consumers=selector_consumers,
    )
    group_ids: set[str] = set()
    audit_rows: list[dict[str, Any]] = []
    for value_row in _list(policy["audit_groups"], label="audit_groups", nonempty=True):
        row = _mapping(
            value_row,
            keys=frozenset({"group_id", "paths", "expected_physical_line_count"}),
            label="audit group",
        )
        group_id = _text(row["group_id"], label="audit group.group_id")
        if group_id in group_ids:
            _fail("audit_group_invalid", group_id, "audit group IDs repeat")
        group_ids.add(group_id)
        for path in _unique_texts(row["paths"], label="audit group.paths"):
            _relative_path(path, label="audit group path")
        _integer(
            row["expected_physical_line_count"],
            label="audit group.expected_physical_line_count",
        )
        audit_rows.append(row)
    if policy["projection"].get("commit") == FROZEN_PROJECTION_COMMIT:
        expected_audit_rows = frozen_audit_groups(
            _list(discovery_output.get("leaf_rows"), label="discovery leaf_rows")
        )
        if audit_rows != expected_audit_rows:
            _fail(
                "audit_group_invalid",
                audit_rows,
                "policy audit groups differ from the exact frozen nine-row contract",
            )
    legacy_ids = _unique_texts(
        policy["legacy_bypass_consumer_ids"],
        label="legacy_bypass_consumer_ids",
        nonempty=False,
    )
    if not set(legacy_ids) <= set(policies):
        _fail("legacy_bypass_inventory_invalid", legacy_ids, "legacy IDs are not consumers")
    expected_legacy_ids = [
        row["consumer_id"]
        for row in candidate_rows
        if "LEGACY_BYPASS_RETIREMENT" in row["responsibility_ids"]
    ]
    if legacy_ids != expected_legacy_ids:
        _fail(
            "legacy_bypass_inventory_invalid",
            legacy_ids,
            "legacy inventory must exactly equal the ordered detector-derived domain",
        )
    _validate_no_consumption(
        policy["no_consumption"],
        reobserve=True,
        enforce_frozen_scope=(
            policy["projection"].get("repository")
            == str(FROZEN_PROJECTION_REPOSITORY)
            and policy["projection"].get("commit") == FROZEN_PROJECTION_COMMIT
        ),
    )
    _validate_a1_policy(policy["a1"])
    _validate_witness_observability_reviews(
        policy["witness_observability_reviews"]
    )
    return policy


def _physical_line_total(
    paths: Sequence[str], *, leaves_by_path: Mapping[str, Mapping[str, object]], label: str
) -> int:
    total = 0
    for path in paths:
        leaf = leaves_by_path.get(path)
        if leaf is None:
            _fail("census_subtotal_path_invalid", path, f"{label} path is absent")
        line_count = leaf["text"]["physical_line_count"]  # type: ignore[index]
        if line_count is None:
            _fail("census_subtotal_path_invalid", path, f"{label} path is not strict UTF-8")
        total += int(line_count)
    return total


def build_source_census(
    *,
    discovery_input: Mapping[str, object],
    discovery_output: Mapping[str, object],
    policy: Mapping[str, object],
    producer: Mapping[str, object],
    discovery_input_sha256: str | None = None,
) -> dict[str, object]:
    """Re-scan exact source objects and join every candidate to reviewed policy."""

    validated_input = _validate_discovery_input(copy.deepcopy(dict(discovery_input)))
    input_digest = discovery_input_sha256 or raw_sha256(
        canonical_json_bytes(validated_input)
    )
    fresh = discover_source(
        validated_input, discovery_input_sha256=input_digest
    )
    published = _mapping(
        copy.deepcopy(dict(discovery_output)),
        keys=frozenset(fresh),
        label="published discovery",
    )
    historical_producer = _mapping(
        published["producer"],
        keys=_PRODUCER_KEYS,
        label="published discovery producer",
    )
    current_discovery_producer = _mapping(
        copy.deepcopy(fresh).pop("producer"),
        keys=_PRODUCER_KEYS,
        label="fresh discovery producer",
    )
    if historical_producer["path"] != current_discovery_producer["path"]:
        _fail(
            "discovery_producer_invalid",
            historical_producer,
            "published discovery producer path drifted",
        )
    _sha256(
        historical_producer["sha256"],
        label="published discovery producer.sha256",
    )
    fresh_projection_data = copy.deepcopy(fresh)
    fresh_projection_data.pop("producer")
    published_projection_data = copy.deepcopy(published)
    published_projection_data.pop("producer")
    if canonical_json_bytes(fresh_projection_data) != canonical_json_bytes(
        published_projection_data
    ):
        _fail(
            "discovery_recompute_mismatch",
            discovery_output,
            "published projection-derived discovery differs from independent object rescan",
        )
    validated_policy = _validate_policy(
        policy,
        discovery_input=validated_input,
        discovery_output=published,
        discovery_input_sha256=input_digest,
    )
    producer_row = _mapping(producer, keys=_PRODUCER_KEYS, label="census producer")
    producer_path = _relative_path(producer_row["path"], label="producer.path")
    if producer_path != "scripts/experiments/es/source_census.py":
        _fail("producer_path_invalid", producer_path, "census producer path drifted")
    _sha256(producer_row["sha256"], label="producer.sha256")
    try:
        actual_producer_sha = raw_sha256((REPOSITORY_ROOT / producer_path).read_bytes())
    except OSError as exc:
        raise SourceCensusError(
            "producer_unreadable", producer_path, "census producer cannot be read"
        ) from exc
    if producer_row["sha256"] != actual_producer_sha:
        _fail("producer_digest_mismatch", producer_row, "census producer digest drifted")

    policy_by_consumer = {
        row["consumer_id"]: row for row in validated_policy["consumer_policies"]
    }
    consumer_rows: list[dict[str, object]] = []
    for candidate in fresh["consumer_candidates"]:
        policy_row = policy_by_consumer[candidate["consumer_id"]]
        consumer_rows.append(
            {
                **copy.deepcopy(candidate),
                "proposed_disposition": policy_row["proposed_disposition"],
                "required_proof_kind": policy_row["required_proof_kind"],
                "selector_id": policy_row["selector_id"],
                "witness_kind": policy_row["witness_kind"],
                "coverage_status": policy_row["coverage_status"],
                "coverage_witness_ids": copy.deepcopy(policy_row["coverage_witness_ids"]),
            }
        )
    leaves = copy.deepcopy(fresh["leaf_rows"])
    leaves_by_path = {row["path"]: row for row in leaves}
    group_subtotals: list[dict[str, object]] = []
    responsibility_paths: set[str] = {row["caller_path"] for row in consumer_rows}
    for group in validated_policy["audit_groups"]:
        paths = list(group["paths"])
        observed = _physical_line_total(
            paths, leaves_by_path=leaves_by_path, label=f"audit group {group['group_id']}"
        )
        if observed != group["expected_physical_line_count"]:
            _fail(
                "census_subtotal_mismatch",
                {"group_id": group["group_id"], "observed": observed},
                "audit group physical line count drifted",
            )
        group_subtotals.append(
            {
                "group_id": group["group_id"],
                "paths": paths,
                "physical_line_count": observed,
            }
        )
        responsibility_paths.update(paths)
    ordered_responsibility_paths = sorted(responsibility_paths, key=lambda path: path.encode())
    responsibility_total = {
        "paths": ordered_responsibility_paths,
        "physical_line_count": _physical_line_total(
            ordered_responsibility_paths,
            leaves_by_path=leaves_by_path,
            label="responsibility total",
        ),
    }
    body: dict[str, object] = {
        "schema_version": "es_f1_source_census.v1",
        "preedit_policy_sha256": validated_policy["record_sha256"],
        "discovery_candidate_set_sha256": fresh["candidate_set_sha256"],
        "producer": dict(producer_row),
        "git": copy.deepcopy(validated_policy["git"]),
        "projection": copy.deepcopy(validated_policy["projection"]),
        "schema_bindings": copy.deepcopy(validated_policy["schema_bindings"]),
        "lineage": copy.deepcopy(validated_policy["lineage"]),
        "leaf_rows": leaves,
        "consumer_rows": consumer_rows,
        "group_subtotals": group_subtotals,
        "responsibility_total": responsibility_total,
        "legacy_bypass_inventory": copy.deepcopy(
            validated_policy["legacy_bypass_consumer_ids"]
        ),
        "no_consumption": copy.deepcopy(validated_policy["no_consumption"]),
    }
    body["record_sha256"] = compute_record_sha256(body)
    return body


def projection_blob(census: Mapping[str, object], path: str) -> dict[str, object]:
    """Return immutable metadata for one census-bound projection blob."""

    relative = _relative_path(path, label="projection blob path")
    rows = _list(census.get("leaf_rows"), label="census leaf_rows")
    matches = [row for row in rows if row.get("path") == relative]
    if len(matches) != 1:
        _fail("projection_blob_missing", relative, "projection path is not unique")
    row = matches[0]
    return {
        "path": relative,
        "object_id": row["object_id"],
        "mode": row["mode"],
        "physical_line_count": row["text"]["physical_line_count"],
    }


def _validated_outcomes(
    value: object,
    *,
    label: str,
    collection_total: int,
    allow_disclosed_nonpass: bool = False,
) -> dict[str, Any]:
    outcomes = _mapping(
        value,
        keys=frozenset({"passed", "failed", "errors", "skipped"}),
        label=label,
    )
    for key, count in outcomes.items():
        _integer(count, label=f"{label}.{key}")
    if outcomes["errors"] != 0 or (
        not allow_disclosed_nonpass and outcomes["failed"] != 0
    ):
        _fail("baseline_pytest_failed", outcomes, f"{label} is not green")
    if sum(outcomes.values()) != collection_total:
        _fail(
            "baseline_outcomes_mismatch",
            outcomes,
            f"{label} does not cover collected nodes",
        )
    return outcomes


def _validated_coverage_witness_node_outcomes(
    value: object, *, collected_nodes: Sequence[str], label: str
) -> list[dict[str, str]]:
    raw_rows = _list(value, label=label)
    if len(raw_rows) > 1:
        _fail(
            "coverage_witness_join_invalid",
            raw_rows,
            f"{label} may bind at most one sampled witness",
        )
    rows: list[dict[str, str]] = []
    for index, raw_row in enumerate(raw_rows):
        row = _mapping(
            raw_row,
            keys=frozenset({"witness_id", "pytest_node_id", "outcome"}),
            label=f"{label}[{index}]",
        )
        parsed = {
            "witness_id": _text(
                row["witness_id"], label=f"{label}[{index}].witness_id"
            ),
            "pytest_node_id": _text(
                row["pytest_node_id"], label=f"{label}[{index}].pytest_node_id"
            ),
            "outcome": _text(row["outcome"], label=f"{label}[{index}].outcome"),
        }
        if (
            parsed["outcome"] != "passed"
            or parsed["pytest_node_id"] not in collected_nodes
        ):
            _fail(
                "coverage_witness_join_invalid",
                parsed,
                f"{label} must bind a collected passing node",
            )
        rows.append(parsed)
    return rows


_NORMALIZED_AUTOGRAPH_MODULE_ORIGIN_PAIRS = frozenset(
    (
        (
            f"<normalized-runtime-owned:autograph-generated-module:{ordinal:04d}>",
            f"<normalized-runtime-owned:autograph-generated-origin:{ordinal:04d}>",
        )
        for ordinal in range(1, 18)
    )
)
_RUNTIME_OWNED_MODULE_ORIGIN_PAIRS = frozenset(
    {
        (
            "es_boundary_probe_plugin",
            "<runtime-owned:es-boundary-probe-plugin>",
        ),
        (
            "es_exact_source_event_observer",
            "<runtime-owned:es-exact-source-event-observer>",
        ),
        (
            "_remote_module_non_scriptable",
            "<normalized-runtime-owned:torch-remote-module-non-scriptable-origin>",
        ),
    }
) | _NORMALIZED_AUTOGRAPH_MODULE_ORIGIN_PAIRS


def _validated_origin_isolation(
    value: object,
    *,
    boundary: Any,
    expected_pytest_carrier: Mapping[str, str],
    label: str,
) -> dict[str, Any]:
    isolation = _mapping(
        value,
        keys=frozenset(
            {
                "report_sha256",
                "python_executable",
                "pytest_carrier",
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
                "cache_artifacts",
            }
        ),
        label=label,
    )
    _sha256(isolation["report_sha256"], label=f"{label}.report_sha256")
    python_executable = _text(
        isolation["python_executable"], label=f"{label}.python_executable"
    )
    if python_executable != str(boundary.PINNED_PYTHON_TARGET):
        _fail(
            "baseline_origin_isolation_failed",
            isolation,
            f"{label} Python executable is not the pinned Task-0 target",
        )
    carrier = _validated_pytest_carrier(
        isolation["pytest_carrier"], label=f"{label}.pytest_carrier"
    )
    if carrier != expected_pytest_carrier:
        _fail(
            "baseline_origin_isolation_failed",
            isolation,
            f"{label} carrier differs from selector policy",
        )
    if isolation["plugin_autoload_disabled"] is not True:
        _fail(
            "baseline_origin_isolation_failed",
            isolation,
            f"{label} did not disable plugin autoload",
        )
    for key in (
        "removed_editable_hooks",
        "forbidden_roots",
        "forbidden_module_prefixes",
        "project_owned_module_prefixes",
        "loaded_forbidden_modules",
        "cache_artifacts",
    ):
        values = _unique_texts(
            isolation[key],
            label=f"{label}.{key}",
            nonempty=key == "project_owned_module_prefixes",
        )
        if key == "forbidden_roots" and any(
            not Path(path).is_absolute() for path in values
        ):
            _fail(
                "baseline_origin_isolation_failed",
                values,
                f"{label} contains a relative forbidden root",
            )
    for key in (
        "forbidden_origin_rows",
        "outside_project_origin_rows",
        "projected_origin_rows",
        "module_origin_rows",
    ):
        for index, pair in enumerate(_list(isolation[key], label=f"{label}.{key}")):
            values = _list(pair, label=f"{label}.{key}[{index}]")
            if len(values) != 2:
                _fail(
                    "source_census_shape_invalid",
                    values,
                    f"{label}.{key}[{index}] must be a pair",
                )
            module_name = _text(
                values[0], label=f"{label}.{key}[{index}][0]", nonempty=False
            )
            origin = _text(values[1], label=f"{label}.{key}[{index}][1]")
            if not Path(origin).is_absolute() and not (
                key == "module_origin_rows"
                and (module_name, origin) in _RUNTIME_OWNED_MODULE_ORIGIN_PAIRS
            ):
                _fail(
                    "baseline_origin_isolation_failed",
                    origin,
                    f"{label}.{key}[{index}] origin is not absolute",
                )
    if any(
        isolation[key] != []
        for key in (
            "loaded_forbidden_modules",
            "forbidden_origin_rows",
            "outside_project_origin_rows",
            "cache_artifacts",
        )
    ):
        _fail(
            "baseline_origin_isolation_failed",
            isolation,
            f"{label} origin/cache isolation failed",
        )
    return isolation


def _validated_source_span(value: object, *, label: str) -> dict[str, Any]:
    span = _mapping(
        value,
        keys=frozenset({"line_start", "column_start", "line_end", "column_end"}),
        label=label,
    )
    line_start = _integer(span["line_start"], label=f"{label}.line_start", minimum=1)
    column_start = _integer(span["column_start"], label=f"{label}.column_start")
    line_end = _integer(span["line_end"], label=f"{label}.line_end", minimum=1)
    column_end = _integer(span["column_end"], label=f"{label}.column_end")
    if line_end < line_start or (
        line_end == line_start and column_end < column_start
    ):
        _fail("coverage_source_event_invalid", span, f"{label} is reversed")
    return span


def _expected_source_event_binding(
    compact: Mapping[str, object],
    *,
    selector_results: Mapping[str, Mapping[str, object]],
    controller_selector_results: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    spec = _mapping(compact["spec"], label="coverage witness spec")
    event_kind = _text(spec.get("event_kind"), label="source event kind")
    if event_kind not in _SOURCE_EVENT_PAYLOAD_KEYS:
        _fail(
            "coverage_source_event_invalid",
            event_kind,
            "source event kind is unsupported",
        )
    phase = _text(spec.get("phase"), label="source event phase")
    attribution = _mapping(spec.get("attribution"), label="source event attribution")
    witness_kind = compact["witness_kind"]
    if phase in {"setup", "call", "teardown"}:
        attribution = _mapping(
            attribution,
            keys=frozenset({"attribution_kind", "pytest_node_pattern"}),
            label="source event pytest attribution",
        )
        if attribution["attribution_kind"] != "pytest_node" or witness_kind not in {
            "pytest_runtime",
            "controller_pytest_runtime",
        }:
            _fail(
                "coverage_source_event_invalid",
                attribution,
                "pytest phase requires a pytest witness and node attribution",
            )
        selector_id = str(compact["selector_id"])
        if witness_kind == "pytest_runtime":
            selector_result = selector_results.get(selector_id)
            node_key = "pytest_node_ids"
        else:
            selector_result = controller_selector_results.get(selector_id)
            node_key = "collected_node_ids"
        if selector_result is None:
            _fail(
                "coverage_source_event_invalid",
                selector_id,
                "pytest attribution has no result in its own lane",
            )
        resolved_attribution: dict[str, object] = {
            "attribution_kind": "pytest_node",
            "pytest_node_id": _select_pytest_node(
                attribution["pytest_node_pattern"],
                selector_result[node_key],
                witness_id=str(compact["witness_id"]),
            ),
        }
    elif phase in {"bootstrap", "collection"}:
        attribution = _mapping(
            attribution,
            keys=frozenset({"attribution_kind", "pytest_module_path"}),
            label="source event module attribution",
        )
        if attribution["attribution_kind"] != "selector_module" or witness_kind not in {
            "pytest_runtime",
            "controller_pytest_runtime",
        }:
            _fail(
                "coverage_source_event_invalid",
                attribution,
                "bootstrap/collection requires a pytest selector module",
            )
        resolved_attribution = {
            "attribution_kind": "selector_module",
            "pytest_module_path": _relative_path(
                attribution["pytest_module_path"],
                label="source event pytest_module_path",
            ),
        }
    elif phase == "residual":
        attribution = _mapping(
            attribution,
            keys=frozenset({"attribution_kind", "action_sha256"}),
            label="source event residual attribution",
        )
        if (
            attribution["attribution_kind"] != "residual_action"
            or witness_kind != "runtime_probe"
        ):
            _fail(
                "coverage_source_event_invalid",
                attribution,
                "residual phase requires runtime-probe action attribution",
            )
        resolved_attribution = {
            "attribution_kind": "residual_action",
            "action_sha256": _sha256(
                attribution["action_sha256"],
                label="source event action_sha256",
            ),
        }
    else:
        _fail(
            "coverage_source_event_invalid",
            phase,
            "source event phase is unsupported",
        )
    return {
        "event_kind": event_kind,
        "phase": phase,
        "attribution": resolved_attribution,
    }


def _validated_source_event(
    value: object,
    *,
    expected_binding: Mapping[str, object],
    consumer: Mapping[str, object],
) -> dict[str, Any]:
    event = _mapping(value, label="source event")
    event_kind = event.get("event_kind")
    if event_kind not in _SOURCE_EVENT_PAYLOAD_KEYS:
        _fail(
            "coverage_source_event_invalid",
            event_kind,
            "source event kind is unsupported",
        )
    event = _mapping(
        event,
        keys=_SOURCE_EVENT_COMMON_KEYS | frozenset({str(event_kind)}),
        label="source event",
    )
    observed_binding = {
        "event_kind": event["event_kind"],
        "phase": event["phase"],
        "attribution": event["attribution"],
    }
    if observed_binding != expected_binding:
        _fail(
            "coverage_source_event_binding_invalid",
            observed_binding,
            "observed source event does not equal the resolved witness binding",
        )
    consumer_path = _relative_path(
        event["consumer_path"], label="source event consumer_path"
    )
    caller_object_id = _sha1(
        event["caller_object_id"], label="source event caller_object_id"
    )
    if (
        consumer_path != consumer["caller_path"]
        or caller_object_id != consumer["caller_object_id"]
    ):
        _fail(
            "coverage_source_event_invalid",
            event,
            "source event consumer binding drifted",
        )
    span = _validated_source_span(event["span"], label="source event span")
    if "span" in consumer and span != consumer["span"]:
        _fail(
            "coverage_source_event_invalid",
            span,
            "source event span differs from the census consumer",
        )
    _integer(event["hit_count"], label="source event hit_count", minimum=1)
    payload = event[str(event_kind)]
    if event_kind == "opcode_exact_span":
        row = _mapping(
            payload,
            keys=frozenset(
                {
                    "code_qualname",
                    "code_firstlineno",
                    "instruction_offset",
                    "opname",
                    "argrepr_sha256",
                }
            ),
            label="opcode_exact_span event",
        )
        _text(row["code_qualname"], label="opcode code_qualname")
        _integer(row["code_firstlineno"], label="opcode code_firstlineno", minimum=1)
        _integer(row["instruction_offset"], label="opcode instruction_offset")
        if row["opname"] not in _OPCODE_EXACT_SPAN_OPNAMES:
            _fail("coverage_source_event_invalid", row["opname"], "opcode is unsupported")
        _sha256(row["argrepr_sha256"], label="opcode argrepr_sha256")
    elif event_kind == "import_alias_opcode":
        row = _mapping(
            payload,
            keys=frozenset(
                {
                    "code_qualname",
                    "code_firstlineno",
                    "statement_span",
                    "alias_ordinal",
                    "module",
                    "name",
                    "asname",
                    "level",
                    "instruction_offset",
                    "opname",
                    "argval",
                }
            ),
            label="import_alias_opcode event",
        )
        _text(row["code_qualname"], label="import code_qualname")
        _integer(row["code_firstlineno"], label="import code_firstlineno", minimum=1)
        _validated_source_span(row["statement_span"], label="import statement_span")
        _integer(row["alias_ordinal"], label="import alias_ordinal")
        for key in ("module", "name", "asname"):
            if row[key] is not None:
                _text(row[key], label=f"import {key}", nonempty=False)
        _integer(row["level"], label="import level")
        _integer(row["instruction_offset"], label="import instruction_offset")
        if row["opname"] not in {"IMPORT_NAME", "IMPORT_FROM", "IMPORT_STAR"}:
            _fail("coverage_source_event_invalid", row["opname"], "import opcode is unsupported")
        _text(row["argval"], label="import argval", nonempty=False)
    else:
        row = _mapping(
            payload,
            keys=frozenset(
                {"code_qualname", "code_name", "code_firstlineno", "definition_span"}
            ),
            label="callable_entry event",
        )
        _text(row["code_qualname"], label="callable code_qualname")
        _text(row["code_name"], label="callable code_name")
        _integer(row["code_firstlineno"], label="callable code_firstlineno", minimum=1)
        _validated_source_span(row["definition_span"], label="callable definition_span")
    return event


def _validate_baseline_characterization(
    value: Mapping[str, object],
    *,
    policy: Mapping[str, object],
    census: Mapping[str, object],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    baseline = _mapping(
        copy.deepcopy(dict(value)), keys=_BASELINE_KEYS, label="baseline characterization"
    )
    if baseline["schema_version"] != "es_f1_boundary_baseline.v1":
        _fail("baseline_version_invalid", baseline["schema_version"], "unsupported baseline")
    runner_sha = _sha256(baseline["runner_sha256"], label="baseline.runner_sha256")
    projection = census["projection"]
    if baseline["pre_tree"] != projection["tree"] or baseline["post_tree"] != projection["tree"]:
        _fail("baseline_tree_mismatch", baseline, "baseline changed or missed projection tree")
    provider_policy = policy["selector_policy"]["provider_visible_pytest_selectors"]
    argv = [_text(item, label="aggregate_pytest_argv[]", nonempty=False) for item in _list(
        baseline["aggregate_pytest_argv"], label="aggregate_pytest_argv", nonempty=True
    )]
    boundary = _boundary_proofs_module()
    expected_pytest_carrier = _validated_pytest_carrier(
        policy["selector_policy"]["pytest_carrier"],
        label="selector_policy.pytest_carrier",
    )
    expected_argv = [
        str(boundary.PINNED_PYTHON),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *_MANDATORY_NINETEEN_SELECTOR_PATHS,
    ]
    if argv != expected_argv:
        _fail(
            "baseline_argv_mismatch",
            argv,
            "aggregate argv is not the exact pinned Task-0 provider invocation",
        )
    controller_tokens = {
        token
        for row in policy["selector_policy"]["controller_only_proof_selectors"]
        for token in [row["selector_id"], row["runner_path"]]
    }
    if any(token in argv for token in controller_tokens):
        _fail("baseline_lane_mixed", argv, "controller-only selector leaked into pytest argv")
    node_ids = _unique_texts(baseline["collected_node_ids"], label="collected_node_ids")
    if baseline["collected_node_sha256"] != sequence_sha256(node_ids):
        _fail("baseline_node_digest_mismatch", baseline["collected_node_sha256"], "node digest drifted")
    collection_total = _integer(
        baseline["collection_total"], label="collection_total"
    )
    if collection_total != len(node_ids):
        _fail("baseline_collection_total_mismatch", baseline["collection_total"], "node total drifted")
    _validated_outcomes(
        baseline["outcomes"],
        label="baseline outcomes",
        collection_total=collection_total,
    )
    _validated_origin_isolation(
        baseline["origin_isolation"],
        boundary=boundary,
        expected_pytest_carrier=expected_pytest_carrier,
        label="origin isolation",
    )

    selector_results: dict[str, dict[str, Any]] = {}
    result_rows = _list(baseline["selector_results"], label="selector_results", nonempty=True)
    for value_row in result_rows:
        row = _mapping(
            value_row,
            keys=frozenset({"selector_id", "pytest_node_ids", "coverage_witness_ids"}),
            label="selector result",
        )
        selector_id = _text(row["selector_id"], label="selector result.selector_id")
        if selector_id in selector_results:
            _fail("baseline_selector_result_invalid", row, "selector result repeats")
        result_nodes = _unique_texts(row["pytest_node_ids"], label="pytest_node_ids")
        if not set(result_nodes) <= set(node_ids):
            _fail("baseline_unknown_node", result_nodes, "selector references uncollected node")
        result_witness_ids = _unique_texts(
            row["coverage_witness_ids"], label="selector coverage_witness_ids"
        )
        if len(result_witness_ids) != 1:
            _fail(
                "coverage_witness_join_invalid",
                row,
                "provider selector result must bind exactly one witness",
            )
        selector_results[selector_id] = row
    expected_selector_ids = [row["selector_id"] for row in provider_policy]
    if list(selector_results) != expected_selector_ids:
        _fail("baseline_selector_result_invalid", list(selector_results), "selector result order/domain drifted")

    controller_policy = [
        row
        for row in policy["selector_policy"]["controller_only_proof_selectors"]
        if row.get("execution_kind") == "pytest_aggregate"
    ]
    controller_policy_by_id = {row["selector_id"]: row for row in controller_policy}
    controller_selector_results: dict[str, dict[str, Any]] = {}
    for value_row in _list(
        baseline["controller_selector_results"],
        label="controller_selector_results",
        nonempty=True,
    ):
        row = _mapping(
            value_row,
            keys=_CONTROLLER_SELECTOR_RESULT_KEYS,
            label="controller selector result",
        )
        selector_id = _text(
            row["selector_id"], label="controller selector result.selector_id"
        )
        expected_controller = controller_policy_by_id.get(selector_id)
        if (
            expected_controller is None
            or selector_id in controller_selector_results
            or not selector_id.startswith("CO-")
            or row["execution_kind"] != "pytest_aggregate"
        ):
            _fail(
                "baseline_controller_result_invalid",
                row,
                "controller result is duplicate, cross-lane, or not pytest aggregate",
            )
        controller_argv = _texts(
            row["argv"], label="controller result argv", nonempty=True
        )
        if controller_argv != expected_controller["argv"]:
            _fail(
                "baseline_controller_result_invalid",
                row,
                "controller argv differs from its policy selector",
            )
        collected_nodes = _unique_texts(
            row["collected_node_ids"], label="controller collected_node_ids"
        )
        if row["collected_node_sha256"] != sequence_sha256(collected_nodes):
            _fail(
                "baseline_node_digest_mismatch",
                row["collected_node_sha256"],
                "controller node digest drifted",
            )
        controller_total = _integer(
            row["collection_total"], label="controller collection_total", minimum=1
        )
        if controller_total != len(collected_nodes):
            _fail(
                "baseline_collection_total_mismatch",
                row["collection_total"],
                "controller node total drifted",
            )
        _validated_outcomes(
            row["outcomes"],
            label="controller outcomes",
            collection_total=controller_total,
            allow_disclosed_nonpass=True,
        )
        _validated_origin_isolation(
            row["origin_isolation"],
            boundary=boundary,
            expected_pytest_carrier=expected_pytest_carrier,
            label=f"controller origin isolation {selector_id}",
        )
        _sha256(row["trace_sha256"], label="controller trace_sha256")
        witness_ids = _unique_texts(
            row["coverage_witness_ids"],
            label="controller coverage_witness_ids",
            nonempty=False,
        )
        if (
            len(witness_ids) > 1
            or witness_ids != expected_controller["coverage_witness_ids"]
        ):
            _fail(
                "coverage_witness_join_invalid",
                row,
                "controller result witness backpointer drifted",
            )
        row["coverage_witness_node_outcomes"] = (
            _validated_coverage_witness_node_outcomes(
                row["coverage_witness_node_outcomes"],
                collected_nodes=collected_nodes,
                label="controller coverage_witness_node_outcomes",
            )
        )
        controller_selector_results[selector_id] = row
    expected_controller_ids = [row["selector_id"] for row in controller_policy]
    if list(controller_selector_results) != expected_controller_ids:
        _fail(
            "baseline_controller_result_invalid",
            list(controller_selector_results),
            "controller result order/domain drifted",
        )

    consumers = {row["consumer_id"]: row for row in census["consumer_rows"]}
    policy_specs = policy["selector_policy"]["coverage_witness_specs"]
    policy_specs_by_id = {row["witness_id"]: row for row in policy_specs}
    witness_results: dict[str, dict[str, Any]] = {}
    for value_row in _list(baseline["witness_results"], label="witness_results", nonempty=True):
        raw_row = _mapping(value_row, label="witness result")
        witness_kind = raw_row.get("witness_kind")
        result_keys = (
            _RUNTIME_WITNESS_RESULT_KEYS
            if witness_kind in _RUNTIME_WITNESS_KINDS
            else _WITNESS_RESULT_KEYS
        )
        row = _mapping(raw_row, keys=result_keys, label="witness result")
        witness_id = _text(row["witness_id"], label="witness result.witness_id")
        consumer_id = _text(row["consumer_id"], label="witness result.consumer_id")
        compact = policy_specs_by_id.get(witness_id)
        if (
            witness_id in witness_results
            or consumer_id not in consumers
            or compact is None
        ):
            _fail("coverage_witness_result_invalid", row, "witness result is duplicate or unknown")
        consumer = consumers[consumer_id]
        if (
            row["target_tree"] != projection["tree"]
            or row["target_path"] != consumer["caller_path"]
            or row["target_blob_id"] != consumer["caller_object_id"]
            or row["proof_kind"] != consumer["required_proof_kind"]
        ):
            _fail("coverage_witness_result_invalid", row, "witness target/join drifted")
        if row["mechanically_observed"] is not True:
            _fail("coverage_witness_unobserved", row, "witness was not mechanically observed")
        if row["observation_sha256"] != raw_sha256(canonical_json_bytes(row["observation"])):
            _fail("coverage_witness_observation_digest_invalid", row, "observation digest drifted")
        if not isinstance(row["passed"], bool):
            _fail("coverage_witness_result_invalid", row, "passed must be Boolean")
        if witness_kind in _RUNTIME_WITNESS_KINDS:
            expected_binding = _expected_source_event_binding(
                compact,
                selector_results=selector_results,
                controller_selector_results=controller_selector_results,
            )
            _validated_source_event(
                row["source_event"],
                expected_binding=expected_binding,
                consumer=consumer,
            )
        witness_results[witness_id] = row
    if list(witness_results) != [row["witness_id"] for row in policy_specs]:
        _fail("coverage_witness_result_invalid", list(witness_results), "witness result order/domain drifted")
    for spec in policy_specs:
        result = witness_results[spec["witness_id"]]
        if (
            result["selector_id"] != spec["selector_id"]
            or result["consumer_id"] != spec["consumer_id"]
            or result["proof_kind"] != spec["required_proof_kind"]
            or result["witness_kind"] != spec["witness_kind"]
        ):
            _fail("coverage_witness_result_invalid", result, "witness assignment drifted")
        expected_passed = canonical_json_bytes(result["observation"]) == (
            canonical_json_bytes(spec["spec"]["expected_event"])
        )
        if result["passed"] is not expected_passed:
            _fail(
                "coverage_witness_truth_mismatch",
                result,
                "passed does not equal the canonical observation/expectation comparison",
            )
    for selector_id, result in controller_selector_results.items():
        trace_rows: list[dict[str, object]] = []
        expected_node_outcomes: list[dict[str, str]] = []
        for witness_id in result["coverage_witness_ids"]:
            witness_result = witness_results.get(witness_id)
            if (
                witness_result is None
                or witness_result["selector_id"] != selector_id
                or witness_result["witness_kind"] != "controller_pytest_runtime"
            ):
                _fail(
                    "coverage_witness_join_invalid",
                    result,
                    "controller trace backpointer has no controller runtime witness",
                )
            trace_row: dict[str, object] = {
                "witness_id": witness_id,
                "source_event": copy.deepcopy(witness_result["source_event"]),
            }
            attribution = witness_result["source_event"]["attribution"]
            if attribution["attribution_kind"] == "pytest_node":
                node_outcome = {
                    "witness_id": witness_id,
                    "pytest_node_id": attribution["pytest_node_id"],
                    "outcome": "passed",
                }
                expected_node_outcomes.append(node_outcome)
                trace_row["node_outcome"] = copy.deepcopy(node_outcome)
            trace_rows.append(trace_row)
        if result["coverage_witness_node_outcomes"] != expected_node_outcomes:
            _fail(
                "coverage_witness_join_invalid",
                result["coverage_witness_node_outcomes"],
                "controller witness node outcomes differ from source attribution",
            )
        expected_trace_sha256 = raw_sha256(canonical_json_bytes(trace_rows))
        if result["trace_sha256"] != expected_trace_sha256:
            _fail(
                "baseline_controller_trace_digest_mismatch",
                result["trace_sha256"],
                "controller trace digest does not bind its labelled source events",
            )
    for selector_id, result in selector_results.items():
        expected_witness_ids = [
            spec["witness_id"] for spec in policy_specs if spec["selector_id"] == selector_id
        ]
        if result["coverage_witness_ids"] != expected_witness_ids:
            _fail("coverage_witness_join_invalid", result, "pytest selector backpointer drifted")
    for controller in policy["selector_policy"]["controller_only_proof_selectors"]:
        if controller["runner_sha256"] != runner_sha:
            _fail("selector_runner_digest_mismatch", controller, "controller runner digest drifted")
    return baseline, selector_results, witness_results


def _select_pytest_node(pattern: object, node_ids: Sequence[str], *, witness_id: str) -> str:
    if pattern is None:
        if len(node_ids) == 1:
            return node_ids[0]
        _fail("coverage_witness_node_ambiguous", witness_id, "pytest witness needs a node pattern")
    pattern_text = _text(pattern, label="pytest_node_pattern")
    try:
        matches = [node_id for node_id in node_ids if re.fullmatch(pattern_text, node_id)]
    except re.error as exc:
        raise SourceCensusError(
            "coverage_witness_node_pattern_invalid", pattern_text, "node regex is invalid"
        ) from exc
    if len(matches) != 1:
        _fail("coverage_witness_node_ambiguous", {"pattern": pattern_text, "matches": matches}, "node pattern must select exactly one collected node")
    return matches[0]


def _rich_coverage_witnesses(
    *,
    policy: Mapping[str, object],
    census: Mapping[str, object],
    baseline: Mapping[str, object],
    selector_results: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    consumers = {row["consumer_id"]: row for row in census["consumer_rows"]}
    runner_sha = baseline["runner_sha256"]
    controller_selector_results = {
        row["selector_id"]: row
        for row in baseline["controller_selector_results"]
    }
    rows: list[dict[str, object]] = []
    for compact in policy["selector_policy"]["coverage_witness_specs"]:
        consumer = consumers[compact["consumer_id"]]
        spec = compact["spec"]
        common: dict[str, object] = {
            "witness_id": compact["witness_id"],
            "selector_id": compact["selector_id"],
            "consumer_id": compact["consumer_id"],
            "proof_kind": compact["required_proof_kind"],
            "witness_kind": compact["witness_kind"],
            "runner_sha256": runner_sha,
            "consumer_path": consumer["caller_path"],
            "caller_object_id": consumer["caller_object_id"],
            "start_line": consumer["span"]["line_start"],
            "column_start": consumer["span"]["column_start"],
            "end_line": consumer["span"]["line_end"],
            "column_end": consumer["span"]["column_end"],
            "match_id": consumer["match_id"],
        }
        if compact["witness_kind"] in {
            "pytest_runtime",
            "controller_pytest_runtime",
        }:
            common.update(
                {
                    "source_event_binding": _expected_source_event_binding(
                        compact,
                        selector_results=selector_results,
                        controller_selector_results=controller_selector_results,
                    ),
                    "expected_event": copy.deepcopy(spec["expected_event"]),
                }
            )
        elif compact["witness_kind"] == "static_ast":
            if "query" not in spec or "expected_event" not in spec:
                _fail("coverage_witness_spec_incomplete", compact, "static witness lacks query/expected result")
            common.update(
                {
                    "query": copy.deepcopy(spec["query"]),
                    "expected_result": copy.deepcopy(spec["expected_event"]),
                }
            )
        else:
            if "probe" not in spec or "expected_event" not in spec:
                _fail("coverage_witness_spec_incomplete", compact, "runtime witness lacks probe/expected event")
            common.update(
                {
                    "probe": copy.deepcopy(spec["probe"]),
                    "source_event_binding": _expected_source_event_binding(
                        compact,
                        selector_results=selector_results,
                        controller_selector_results=controller_selector_results,
                    ),
                    "expected_event": copy.deepcopy(spec["expected_event"]),
                }
            )
        rows.append(common)
    return rows


def _validate_feasibility_spike(
    value: Mapping[str, object],
    *,
    policy: Mapping[str, object],
    census: Mapping[str, object],
    capture_manifest: Mapping[str, object],
) -> dict[str, Any]:
    keys = frozenset(
        {
            "schema_version",
            "capture_manifest_path",
            "capture_manifest_sha256",
            "capture_deterministic_sha256",
            "capture_lifecycle",
            "source_tree_before",
            "source_tree_after",
            "cluster_domain",
            "unmet_clusters",
            "integration_edges",
            "delta",
            "non_collapse",
        }
    )
    spike = _mapping(copy.deepcopy(dict(value)), keys=keys, label="feasibility spike")
    expected_domain = [
        "IDENTITY_CONFIG",
        "CONSTRUCTION_ADAPTERS",
        "TRAINING_OPTIMIZER",
        "PERSISTENCE_REBUILD",
        "INFERENCE_WORKFLOWS",
        "CONSUMER_BYPASS",
    ]
    if (
        spike["schema_version"] != "es_f1_structural_multi_context_feasibility.v1"
        or spike["capture_manifest_path"] != _CAPTURE_MANIFEST_RELATIVE
        or spike["capture_manifest_sha256"] != capture_manifest.get("record_sha256")
        or spike["capture_deterministic_sha256"]
        != capture_manifest.get("deterministic_sha256")
        or spike["capture_lifecycle"] != "retained_pending_ordered_reviews"
        or spike["capture_lifecycle"] != capture_manifest.get("lifecycle")
        or spike["cluster_domain"] != expected_domain
    ):
        _fail(
            "feasibility_contract_invalid",
            spike,
            "capture-derived structural proxy contract drifted",
        )
    _sha256(spike["capture_manifest_sha256"], label="capture manifest SHA-256")
    _sha256(
        spike["capture_deterministic_sha256"],
        label="capture deterministic SHA-256",
    )
    if spike["source_tree_before"] != census["projection"]["tree"]:
        _fail("feasibility_tree_invalid", spike, "spike does not start from projection tree")
    _sha1(spike["source_tree_after"], label="feasibility source_tree_after")
    if spike["source_tree_after"] == spike["source_tree_before"]:
        _fail("feasibility_tree_invalid", spike, "spike did not change its disposable tree")
    responsibility_domain = {
        row["responsibility_id"] for row in policy["responsibilities"]
    }
    clusters = _list(spike["unmet_clusters"], label="unmet_clusters")
    if len(clusters) < 4:
        _fail("feasibility_cluster_count_invalid", len(clusters), "at least four clusters are required")
    cluster_ids: set[str] = set()
    baseline_ledger_ids: set[str] = set()
    remove_one_ledger_ids: set[str] = set()
    primary_owner: dict[str, str] = {}
    changed_paths: list[str] = []
    for value_row in clusters:
        row = _mapping(
            value_row,
            keys=frozenset(
                {
                    "cluster_id",
                    "baseline_ledger_id",
                    "remove_one_ledger_id",
                    "primary_production_paths",
                    "changed_production_paths",
                    "responsibility_ids",
                }
            ),
            label="unmet cluster",
        )
        cluster_id = _text(row["cluster_id"], label="cluster_id")
        if cluster_id not in expected_domain or cluster_id in cluster_ids:
            _fail("feasibility_cluster_invalid", row, "cluster ID is unknown or repeated")
        cluster_ids.add(cluster_id)
        baseline_ledger_id = _text(
            row["baseline_ledger_id"], label="baseline_ledger_id"
        )
        remove_one_ledger_id = _text(
            row["remove_one_ledger_id"], label="remove_one_ledger_id"
        )
        if (
            baseline_ledger_id in baseline_ledger_ids
            or remove_one_ledger_id in remove_one_ledger_ids
        ):
            _fail(
                "feasibility_ledger_invalid",
                row,
                "cluster proof ledgers are not one-to-one",
            )
        baseline_ledger_ids.add(baseline_ledger_id)
        remove_one_ledger_ids.add(remove_one_ledger_id)
        for path in _unique_texts(row["primary_production_paths"], label="primary_production_paths"):
            _relative_path(path, label="primary production path")
            if path in primary_owner:
                _fail("feasibility_cluster_not_disjoint", path, "primary path belongs to two clusters")
            primary_owner[path] = cluster_id
        for path in _unique_texts(row["changed_production_paths"], label="changed_production_paths"):
            _relative_path(path, label="changed production path")
            changed_paths.append(path)
        ids = set(_unique_texts(row["responsibility_ids"], label="responsibility_ids"))
        if not ids <= responsibility_domain:
            _fail("feasibility_responsibility_invalid", sorted(ids), "cluster responsibility is unknown")
    edges = _list(spike["integration_edges"], label="integration_edges")
    if len(edges) < 3:
        _fail("feasibility_edge_count_invalid", len(edges), "at least three edges are required")
    edge_ids: set[str] = set()
    for value_row in edges:
        row = _mapping(
            value_row,
            keys=frozenset(
                {
                    "edge_id",
                    "from_cluster",
                    "to_cluster",
                    "producer_blob_oid",
                    "consumer_blob_oid",
                    "ledger_id",
                    "pytest_node_id",
                }
            ),
            label="integration edge",
        )
        edge_id = _text(row["edge_id"], label="edge_id")
        if edge_id in edge_ids or row["from_cluster"] not in cluster_ids or row["to_cluster"] not in cluster_ids or row["from_cluster"] == row["to_cluster"]:
            _fail("feasibility_edge_invalid", row, "edge is duplicate or outside unmet clusters")
        edge_ids.add(edge_id)
        producer_blob = _sha1(row["producer_blob_oid"], label="producer_blob_oid")
        consumer_blob = _sha1(row["consumer_blob_oid"], label="consumer_blob_oid")
        if producer_blob == consumer_blob:
            _fail("feasibility_edge_invalid", row, "edge blobs are not distinct")
        _text(row["ledger_id"], label="edge ledger_id")
        _text(row["pytest_node_id"], label="edge pytest_node_id")
    delta = _mapping(
        spike["delta"],
        keys=frozenset(
            {
                "implementation_additions",
                "implementation_deletions",
                "physical_line_count",
                "changed_production_paths",
            }
        ),
        label="feasibility delta",
    )
    _integer(delta["implementation_additions"], label="delta additions", minimum=1)
    _integer(delta["implementation_deletions"], label="delta deletions")
    _integer(delta["physical_line_count"], label="delta physical_line_count", minimum=1)
    delta_paths = _unique_texts(delta["changed_production_paths"], label="delta changed paths")
    if len(delta_paths) < 4 or set(delta_paths) != set(changed_paths):
        _fail("feasibility_delta_invalid", delta, "delta paths do not equal cluster changes")
    non_collapse = _mapping(
        spike["non_collapse"],
        keys=frozenset(
            {"distinct_production_blob_count", "distinct_cluster_path_sets"}
        ),
        label="feasibility non_collapse",
    )
    _integer(
        non_collapse["distinct_production_blob_count"],
        label="distinct_production_blob_count",
        minimum=4,
    )
    distinct_cluster_path_sets = _integer(
        non_collapse["distinct_cluster_path_sets"],
        label="distinct_cluster_path_sets",
        minimum=4,
    )
    if distinct_cluster_path_sets != len(cluster_ids):
        _fail(
            "feasibility_non_collapse_invalid",
            non_collapse,
            "cluster path-set count is not derived from the unmet clusters",
        )
    return spike


def provider_visible_selector_projection(
    *,
    policy: Mapping[str, object],
    census: Mapping[str, object],
    baseline_characterization: Mapping[str, object],
    selector_results: Mapping[str, Mapping[str, object]],
    projection_blobs: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Project only provider-visible pytest authority from validated inputs."""

    providers: list[dict[str, object]] = []
    for selector in policy["selector_policy"]["provider_visible_pytest_selectors"]:
        path = selector["pytest_module_path"]
        census_blob = projection_blob(census, path)
        supplied = projection_blobs.get(path)
        if supplied is None or supplied != census_blob:
            _fail(
                "projection_blob_binding_mismatch",
                {"path": path, "supplied": supplied},
                "selector projection blob drifted",
            )
        if census_blob["physical_line_count"] is None:
            _fail(
                "projection_blob_binding_mismatch",
                path,
                "pytest module is not strict UTF-8",
            )
        result = selector_results[selector["selector_id"]]
        providers.append(
            {
                "selector_id": selector["selector_id"],
                "ordinal": selector["ordinal"],
                "pytest_module_path": path,
                "projection_blob_id": census_blob["object_id"],
                "mode": census_blob["mode"],
                "physical_line_count": census_blob["physical_line_count"],
                "pytest_node_ids": copy.deepcopy(result["pytest_node_ids"]),
                "coverage_witness_ids": copy.deepcopy(
                    result["coverage_witness_ids"]
                ),
            }
        )
    return {
        "aggregate_pytest_argv": copy.deepcopy(
            baseline_characterization["aggregate_pytest_argv"]
        ),
        "provider_visible_pytest_selectors": providers,
    }


def build_selector_manifest(
    *,
    policy: Mapping[str, object],
    census: Mapping[str, object],
    baseline_characterization: Mapping[str, object],
    feasibility_capture_manifest: Mapping[str, object],
    projection_blobs: Mapping[str, Mapping[str, object]],
    reobserve_capture_roots: bool = True,
) -> dict[str, object]:
    """Join immutable baseline observations into the reviewed selector authority."""

    try:
        validate_record_sha256(policy)
        validate_record_sha256(census)
    except Exception as exc:
        raise SourceCensusError(
            "selector_input_digest_invalid", None, "policy or census self digest failed"
        ) from exc
    if census.get("preedit_policy_sha256") != policy.get("record_sha256"):
        _fail("selector_policy_binding_mismatch", census, "census binds another policy")
    baseline, selector_results, witness_results = _validate_baseline_characterization(
        baseline_characterization, policy=policy, census=census
    )
    provider_projection = provider_visible_selector_projection(
        policy=policy,
        census=census,
        baseline_characterization=baseline,
        selector_results=selector_results,
        projection_blobs=projection_blobs,
    )
    baseline["aggregate_pytest_argv"] = copy.deepcopy(
        provider_projection["aggregate_pytest_argv"]
    )
    rich_witnesses = _rich_coverage_witnesses(
        policy=policy,
        census=census,
        baseline=baseline,
        selector_results=selector_results,
    )
    compact_by_witness = {
        row["witness_id"]: row
        for row in policy["selector_policy"]["coverage_witness_specs"]
    }
    desired_rows: list[dict[str, object]] = []
    for ordinal, compact in enumerate(
        policy["selector_policy"]["desired_state_proof_specs"], 1
    ):
        witness = compact_by_witness[compact["witness_id"]]
        desired_rows.append(
            {
                "proof_id": compact["proof_spec_id"],
                "ordinal": ordinal,
                "selector_id": witness["selector_id"],
                "witness_id": compact["witness_id"],
                "consumer_id": witness["consumer_id"],
                "proof_kind": compact["proof_kind"],
                "expected_result": copy.deepcopy(compact["expected_result"]),
            }
        )
    feasibility_module = _feasibility_proofs_module()
    try:
        validated_capture = (
            feasibility_module.validate_feasibility_capture_manifest_record(
                feasibility_capture_manifest,
                reobserve_roots=reobserve_capture_roots,
            )
        )
        feasibility_spike = feasibility_module.derive_feasibility_facts(
            validated_capture
        )
    except Exception as exc:
        raise SourceCensusError(
            "feasibility_capture_invalid",
            None,
            "capture validation or fact derivation failed",
        ) from exc
    validated_feasibility = _validate_feasibility_spike(
        feasibility_spike,
        policy=policy,
        census=census,
        capture_manifest=validated_capture,
    )
    body: dict[str, object] = {
        "schema_version": "es_f1_preedit_selector_manifest.v1",
        "preedit_policy_sha256": policy["record_sha256"],
        "source_census_sha256": census["record_sha256"],
        "provider_visible_pytest_selectors": copy.deepcopy(
            provider_projection["provider_visible_pytest_selectors"]
        ),
        "controller_only_proof_selectors": copy.deepcopy(
            policy["selector_policy"]["controller_only_proof_selectors"]
        ),
        "coverage_witnesses": rich_witnesses,
        "baseline_characterization": baseline,
        "desired_state_proof_specs": desired_rows,
        "feasibility_spike": validated_feasibility,
    }
    body["record_sha256"] = compute_record_sha256(body)
    try:
        _boundary_proofs_module().validate_contract(
            body,
            consumer_rows=census["consumer_rows"],
            expected_runner_sha256=baseline["runner_sha256"],
        )
    except Exception as exc:
        raise SourceCensusError(
            "selector_runner_contract_invalid",
            None,
            "selector output disagrees with the immutable proof runner",
        ) from exc
    return body


_AUTHORITY_BINDING_KEYS = frozenset(
    {
        "plan_sha256",
        "preedit_policy_sha256",
        "source_census_sha256",
        "selector_manifest_sha256",
        "a1_anchor_sha256",
    }
)
_ADOPTION_BINDING_KEYS = _AUTHORITY_BINDING_KEYS | frozenset(
    {"post_purge_tombstone_sha256"}
)
_REVIEW_VIEW_PATHS = {
    "specification": (
        "artifacts/review/"
        "es-f1-large-scope-amendment-plan-specification-review.md"
    ),
    "quality": (
        "artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md"
    ),
}
_REVIEW_KEYS = frozenset(
    {
        "review_kind",
        "reviewer",
        "verdict",
        "reviewed_at",
        "review_view_path",
        "review_view_sha256",
        "bindings",
    }
)
_TASK0_REVIEW_REQUIRED_FINDINGS = (
    "anti_padding_accepted",
    "non_synthetic_baseline_and_remove_one_failures_accepted",
    "three_authenticated_ast_trace_cross_blob_edges_accepted",
    "four_independently_unmet_clusters_accepted",
    "non_collapse_requirement_accepted",
    "strict_reference_size_gate_5000_10000_deferred_to_task_3a",
    "operational_criterion_not_a_universal_provider_context_theorem",
)
_POST_PURGE_TOMBSTONE_KEYS = frozenset(
    {
        "schema_version",
        "evidence_status",
        "purged_at",
        "capture_manifest",
        "reviews",
        "absent_roots",
        "record_sha256",
    }
)
_FILE_DIGEST_BINDING_KEYS = frozenset({"path", "sha256"})
_TOMBSTONE_REVIEW_KEYS = frozenset({"review_kind", "path", "sha256"})
_ABSENT_ROOT_KEYS = frozenset({"root_id", "canonical_path", "lstat"})
_CAPTURE_SOURCE_ROOT_KEYS = frozenset(
    {
        "root_id",
        "root_kind",
        "canonical_path",
        "variant_id",
        "pre_purge_lstat",
        "tree_oid",
    }
)
_CAPTURE_OBJECT_STORE_ROOT_KEYS = frozenset(
    {
        "root_id",
        "root_kind",
        "canonical_path",
        "pre_purge_lstat",
        "snapshot_sha256",
    }
)
_CAPTURE_MANIFEST_RELATIVE = (
    "docs/plans/evidence/es-f1-large-scope-refreeze/"
    "feasibility-capture-manifest.json"
)


def validate_post_purge_tombstone(
    tombstone: Mapping[str, object],
    *,
    capture_manifest: Mapping[str, object],
    review_view_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Validate the one-way post-review purge record and fresh root absence."""

    record = _mapping(
        copy.deepcopy(dict(tombstone)),
        keys=_POST_PURGE_TOMBSTONE_KEYS,
        label="post-purge tombstone",
    )
    if (
        record["schema_version"]
        != "es_f1_feasibility_post_purge_tombstone.v1"
        or record["evidence_status"] != "purged_after_ordered_reviews"
    ):
        _fail(
            "post_purge_status_invalid",
            record,
            "post-purge tombstone lifecycle is not closed",
        )
    timestamp = _text(record["purged_at"], label="purged_at")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceCensusError(
            "post_purge_timestamp_invalid", timestamp, "purged_at is invalid"
        ) from exc
    if parsed.tzinfo is None:
        _fail(
            "post_purge_timestamp_invalid",
            timestamp,
            "purged_at must include an offset",
        )
    try:
        validate_record_sha256(record)
        validate_record_sha256(capture_manifest)
    except Exception as exc:
        raise SourceCensusError(
            "post_purge_digest_invalid",
            record.get("record_sha256"),
            "tombstone or capture manifest digest failed",
        ) from exc

    capture_binding = _mapping(
        record["capture_manifest"],
        keys=_FILE_DIGEST_BINDING_KEYS,
        label="capture manifest binding",
    )
    if (
        capture_binding["path"] != _CAPTURE_MANIFEST_RELATIVE
        or _sha256(capture_binding["sha256"], label="capture manifest SHA-256")
        != capture_manifest["record_sha256"]
    ):
        _fail(
            "post_purge_capture_invalid",
            capture_binding,
            "tombstone binds another capture manifest",
        )

    capture_roots = _list(
        capture_manifest.get("disposable_roots"), label="capture disposable_roots"
    )
    expected_roots: list[dict[str, object]] = []
    canonical_paths: list[Path] = []
    root_ids: set[str] = set()
    if len(capture_roots) != 7:
        _fail(
            "post_purge_root_set_invalid",
            len(capture_roots),
            "capture must bind exactly six source roots and one object store",
        )
    for ordinal, value_row in enumerate(capture_roots):
        keys = (
            _CAPTURE_SOURCE_ROOT_KEYS
            if ordinal < 6
            else _CAPTURE_OBJECT_STORE_ROOT_KEYS
        )
        row = _mapping(value_row, keys=keys, label="capture root")
        if ordinal < 6:
            if row["root_kind"] != "source_tree":
                _fail(
                    "post_purge_root_set_invalid",
                    row,
                    "the first six capture roots must be source trees",
                )
            _sha1(row["tree_oid"], label="capture source root tree_oid")
            _text(row["variant_id"], label="capture source root variant_id")
        else:
            if row["root_kind"] != "git_object_store":
                _fail(
                    "post_purge_root_set_invalid",
                    row,
                    "the seventh capture root must be the object store",
                )
            _sha256(
                row["snapshot_sha256"],
                label="capture object-store snapshot_sha256",
            )
        if row["pre_purge_lstat"] != "directory":
            _fail(
                "post_purge_root_set_invalid",
                row,
                "capture pre-purge root identity is not a directory",
            )
        root_id = _text(row["root_id"], label="capture root_id")
        path = _canonical_absolute_path(
            row["canonical_path"], label="capture canonical_path"
        )
        if root_id in root_ids or path in canonical_paths:
            _fail(
                "post_purge_root_set_invalid",
                {"root_id": root_id, "path": os.fspath(path)},
                "capture roots are duplicated",
            )
        if any(
            path.is_relative_to(other) or other.is_relative_to(path)
            for other in canonical_paths
        ):
            _fail(
                "post_purge_root_set_invalid",
                os.fspath(path),
                "capture roots may not overlap",
            )
        root_ids.add(root_id)
        canonical_paths.append(path)
        expected_roots.append(
            {
                "root_id": root_id,
                "canonical_path": os.fspath(path),
                "lstat": "absent",
            }
        )
    absent_roots = [
        _mapping(row, keys=_ABSENT_ROOT_KEYS, label="absent root")
        for row in _list(record["absent_roots"], label="absent_roots")
    ]
    if absent_roots != expected_roots:
        _fail(
            "post_purge_root_set_invalid",
            absent_roots,
            "tombstone root set does not match capture order",
        )

    review_rows = _list(record["reviews"], label="post-purge reviews")
    if len(review_rows) != 2:
        _fail(
            "post_purge_review_invalid",
            review_rows,
            "exactly two ordered review bindings are required",
        )
    for value_row, review_kind in zip(
        review_rows, ("specification", "quality"), strict=True
    ):
        row = _mapping(
            value_row,
            keys=_TOMBSTONE_REVIEW_KEYS,
            label=f"post-purge {review_kind} review",
        )
        relative = _REVIEW_VIEW_PATHS[review_kind]
        if row["review_kind"] != review_kind or row["path"] != relative:
            _fail(
                "post_purge_review_invalid",
                row,
                "review order or path drifted",
            )
        raw = _stable_regular_file_under_root(
            Path(review_view_root),
            relative,
            error_code="post_purge_review_invalid",
            label="review view",
        )
        if (
            _sha256(row["sha256"], label=f"{review_kind} review SHA-256")
            != raw_sha256(raw)
        ):
            _fail(
                "post_purge_review_invalid",
                row,
                "review bytes do not match the tombstone",
            )

    for path in canonical_paths:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SourceCensusError(
                "post_purge_root_probe_failed",
                os.fspath(path),
                "root lstat failed closed",
            ) from exc
        _fail(
            "post_purge_root_present",
            os.fspath(path),
            "captured disposable root still exists",
        )
    return record


def _validate_task0_review_view_contract(
    raw: bytes,
    *,
    review_kind: str,
    verdict: str,
    expected_bindings: Mapping[str, object],
) -> tuple[str, str, datetime]:
    """Parse only the closed machine header of one retained review view."""

    try:
        lines = raw.decode("utf-8", "strict").splitlines()
    except UnicodeError as exc:
        raise SourceCensusError(
            "review_adoption_view_invalid",
            review_kind,
            "review view is not strict UTF-8",
        ) from exc

    def exact_prefixed(prefix: str) -> str:
        matches = [line for line in lines if line.startswith(prefix)]
        if len(matches) != 1:
            _fail(
                "review_adoption_view_invalid",
                review_kind,
                f"review view requires exactly one {prefix.rstrip()} line",
            )
        value = matches[0].removeprefix(prefix)
        if not value or value != value.strip():
            _fail(
                "review_adoption_view_invalid",
                review_kind,
                f"review view has a noncanonical {prefix.rstrip()} value",
            )
        return value

    if exact_prefixed("verdict: ") != verdict:
        _fail(
            "review_adoption_view_invalid",
            review_kind,
            "review-view verdict differs from the adopted verdict",
        )
    reviewer = exact_prefixed("reviewer: ")
    reviewed_at_text = exact_prefixed("reviewed_at: ")
    try:
        reviewed_at = datetime.fromisoformat(
            reviewed_at_text.replace("Z", "+00:00")
        )
    except (OverflowError, ValueError) as exc:
        raise SourceCensusError(
            "review_adoption_view_invalid",
            review_kind,
            "review-view reviewed_at is invalid",
        ) from exc
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        _fail(
            "review_adoption_view_invalid",
            review_kind,
            "review-view reviewed_at must include an offset",
        )
    for key, expected in expected_bindings.items():
        if exact_prefixed(f"{key}: ") != expected:
            _fail(
                "review_adoption_view_invalid",
                review_kind,
                f"review-view {key} differs from the adopted binding",
            )
    for finding in _TASK0_REVIEW_REQUIRED_FINDINGS:
        if lines.count(finding) != 1:
            _fail(
                "review_adoption_view_invalid",
                review_kind,
                f"review view requires exactly one {finding} finding",
            )
    return reviewer, reviewed_at_text, reviewed_at


def validate_review_adoption(
    adoption: Mapping[str, object],
    *,
    expected_bindings: Mapping[str, object],
    expected_post_purge_tombstone_sha256: str,
    post_purge_tombstone: Mapping[str, object],
    review_view_root: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Require the sole closed, ordered machine adoption of Task-0 reviews."""

    record = _mapping(
        copy.deepcopy(dict(adoption)),
        keys=frozenset(
            {"schema_version", "evidence_status", "bindings", "reviews", "record_sha256"}
        ),
        label="review adoption",
    )
    if (
        record["schema_version"] != "es_f1_task0_review_adoption.v1"
        or record["evidence_status"] != "approved"
    ):
        _fail("review_adoption_status_invalid", record, "review adoption is not approved v1")
    try:
        validate_record_sha256(record)
    except Exception as exc:
        raise SourceCensusError(
            "review_adoption_digest_invalid",
            record.get("record_sha256"),
            "review adoption digest failed",
        ) from exc
    expected = _mapping(
        copy.deepcopy(dict(expected_bindings)),
        keys=_AUTHORITY_BINDING_KEYS,
        label="expected review bindings",
    )
    for key, digest in expected.items():
        _sha256(digest, label=f"expected bindings.{key}")
    tombstone_sha256 = _sha256(
        expected_post_purge_tombstone_sha256,
        label="expected post-purge tombstone SHA-256",
    )
    tombstone = copy.deepcopy(dict(post_purge_tombstone))
    try:
        validate_record_sha256(tombstone)
    except Exception as exc:
        raise SourceCensusError(
            "review_adoption_binding_mismatch",
            tombstone.get("record_sha256"),
            "post-purge tombstone digest failed",
        ) from exc
    if tombstone.get("record_sha256") != tombstone_sha256:
        _fail(
            "review_adoption_binding_mismatch",
            tombstone.get("record_sha256"),
            "adoption binds another post-purge tombstone",
        )
    purged_at_text = _text(tombstone.get("purged_at"), label="purged_at")
    try:
        purged_at = datetime.fromisoformat(purged_at_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceCensusError(
            "review_adoption_timestamp_invalid",
            purged_at_text,
            "purged_at is invalid",
        ) from exc
    if purged_at.tzinfo is None or purged_at.utcoffset() is None:
        _fail(
            "review_adoption_timestamp_invalid",
            purged_at_text,
            "purged_at must include an offset",
        )
    try:
        bindings = _mapping(
            record["bindings"], keys=_ADOPTION_BINDING_KEYS, label="bindings"
        )
    except SourceCensusError as exc:
        raise SourceCensusError(
            "review_adoption_binding_mismatch",
            record.get("bindings"),
            "top-level bindings are not exact",
        ) from exc
    if bindings != {
        **expected,
        "post_purge_tombstone_sha256": tombstone_sha256,
    }:
        _fail("review_adoption_binding_mismatch", bindings, "top-level bindings are stale")
    reviews = _list(record["reviews"], label="reviews")
    if len(reviews) != 2:
        _fail("review_adoption_order_invalid", reviews, "exactly two reviews are required")
    expected_rows = (
        ("specification", "ES_F1_SCOPE_AMENDMENT_PLAN_SPEC_APPROVED"),
        ("quality", "ES_F1_SCOPE_AMENDMENT_PLAN_QUALITY_APPROVED"),
    )
    reviewers: set[str] = set()
    reviewed_times: list[datetime] = []
    for value_row, (review_kind, verdict) in zip(reviews, expected_rows, strict=True):
        row = _mapping(value_row, keys=_REVIEW_KEYS, label=f"{review_kind} review")
        reviewer = _text(row["reviewer"], label="reviewer")
        if reviewer in reviewers:
            _fail("review_adoption_reviewer_duplicate", reviewer, "reviewers must be distinct")
        reviewers.add(reviewer)
        if row["review_kind"] != review_kind or row["verdict"] != verdict:
            _fail("review_adoption_order_invalid", row, "review order or verdict drifted")
        timestamp = _text(row["reviewed_at"], label="reviewed_at")
        try:
            reviewed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SourceCensusError(
                "review_adoption_timestamp_invalid", timestamp, "reviewed_at is invalid"
            ) from exc
        if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
            _fail(
                "review_adoption_timestamp_invalid",
                timestamp,
                "reviewed_at must include an offset",
            )
        reviewed_times.append(reviewed_at)
        review_view_relative = _REVIEW_VIEW_PATHS[review_kind]
        if row["review_view_path"] != review_view_relative:
            _fail("review_adoption_view_invalid", row["review_view_path"], "review view path drifted")
        review_view_raw = _stable_regular_file_under_root(
            Path(review_view_root),
            review_view_relative,
            error_code="review_adoption_view_invalid",
            label="review view",
        )
        review_view_digest = raw_sha256(review_view_raw)
        if (
            _sha256(row["review_view_sha256"], label="review_view_sha256")
            != review_view_digest
        ):
            _fail(
                "review_adoption_view_invalid",
                row["review_view_sha256"],
                "review row does not bind the retained review-view bytes",
            )
        row_bindings = _mapping(
            row["bindings"], keys=_AUTHORITY_BINDING_KEYS, label="review row bindings"
        )
        if row_bindings != expected:
            _fail("review_adoption_binding_mismatch", row_bindings, "review row bindings are stale")
        view_reviewer, view_timestamp, view_time = (
            _validate_task0_review_view_contract(
                review_view_raw,
                review_kind=review_kind,
                verdict=verdict,
                expected_bindings=expected,
            )
        )
        if (
            view_reviewer != reviewer
            or view_timestamp != timestamp
            or view_time != reviewed_at
        ):
            _fail(
                "review_adoption_view_invalid",
                review_kind,
                "review-view reviewer or timestamp differs from adoption",
            )
    if reviewed_times[1] < reviewed_times[0]:
        _fail("review_adoption_order_invalid", reviewed_times, "quality review predates specification")
    if purged_at < reviewed_times[1]:
        _fail(
            "review_adoption_order_invalid",
            [*reviewed_times, purged_at],
            "captured roots were purged before the ordered reviews completed",
        )
    tombstone_reviews = _list(tombstone.get("reviews"), label="tombstone reviews")
    expected_tombstone_reviews = [
        {
            "review_kind": row["review_kind"],
            "path": row["review_view_path"],
            "sha256": row["review_view_sha256"],
        }
        for row in reviews
    ]
    if tombstone_reviews != expected_tombstone_reviews:
        _fail(
            "review_adoption_binding_mismatch",
            tombstone_reviews,
            "tombstone review bindings differ from the adopted review rows",
        )
    return record


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key", key, "JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> NoReturn:
    _fail("json_nonfinite_value", value, "JSON non-finite constants are forbidden")


def _load_json(path_value: str | Path, *, label: str) -> tuple[Any, bytes]:
    path = Path(path_value)
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=_reject_json_constant,
        )
    except SourceCensusError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceCensusError("json_unreadable", str(path), f"{label} is unreadable JSON") from exc
    return value, raw


def _validate_schema(value: object, schema_path: str | Path, *, label: str) -> None:
    schema, _ = _load_json(schema_path, label=f"{label} schema")
    if not isinstance(schema, dict):
        _fail("schema_invalid", schema_path, f"{label} schema must be an object")
    try:
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    except Exception as exc:
        raise SourceCensusError("schema_invalid", str(schema_path), f"{label} schema failed") from exc
    if errors:
        first = errors[0]
        _fail(
            "schema_validation_failed",
            {"path": list(first.absolute_path), "message": first.message},
            f"{label} does not satisfy its closed schema",
        )


def _load_raw_bound_json(
    path: str | Path,
    *,
    schema_path: str | Path | None,
    expected_sha256: str,
    label: str,
    require_canonical: bool,
) -> dict[str, Any]:
    value, raw = _load_json(path, label=label)
    if not isinstance(value, dict):
        _fail("json_shape_invalid", value, f"{label} must be an object")
    if raw_sha256(raw) != _sha256(expected_sha256, label=f"expected {label} SHA-256"):
        _fail("raw_digest_mismatch", str(path), f"{label} raw digest drifted")
    if require_canonical and raw != canonical_json_bytes(value):
        _fail("record_noncanonical", str(path), f"{label} is not canonical JSON")
    if schema_path is not None:
        _validate_schema(value, schema_path, label=label)
    return value


def _load_authority_record(
    path: str | Path,
    *,
    schema_path: str | Path,
    expected_sha256: str,
    label: str,
) -> dict[str, Any]:
    load_canonical_record = _reference_calibration_module().load_canonical_record

    try:
        return load_canonical_record(
            Path(path),
            schema_path=Path(schema_path),
            expected_record_sha256=expected_sha256,
        )
    except Exception as exc:
        raise SourceCensusError(
            "authority_record_invalid", str(path), f"{label} failed canonical/schema validation"
        ) from exc


def _publish_json(path_value: str | Path, value: object) -> None:
    path = Path(path_value)
    payload = canonical_json_bytes(value)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                _fail("output_collision", str(path), "existing output bytes differ")
            return
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    except SourceCensusError:
        raise
    except OSError as exc:
        raise SourceCensusError("output_unwritable", str(path), "output cannot be published") from exc


def _publish_json_exclusive(path_value: str | Path, value: object) -> None:
    path = Path(path_value)
    payload = canonical_json_bytes(value)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as exc:
        raise SourceCensusError(
            "output_collision",
            str(path),
            "exclusive authority output already exists",
        ) from exc
    except OSError as exc:
        raise SourceCensusError(
            "output_unwritable", str(path), "exclusive authority output cannot be published"
        ) from exc


def _add_discovery_arguments(parser: argparse.ArgumentParser, *, output: bool) -> None:
    parser.add_argument("--discovery-input", required=True)
    parser.add_argument("--discovery-input-schema", required=True)
    parser.add_argument("--expected-discovery-input-sha256", required=True)
    parser.add_argument("--projection-repository", required=True)
    parser.add_argument("--projection-commit", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument("--expected-inventory-sha256", required=True)
    parser.add_argument("--expected-leaf-count", required=True, type=int)
    if output:
        parser.add_argument("--output", required=True)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover")
    _add_discovery_arguments(discover, output=True)

    complete = subparsers.add_parser("complete-policy-candidate")
    complete.add_argument("--discovery-input", required=True)
    complete.add_argument("--expected-discovery-input-sha256", required=True)
    complete.add_argument("--discovery-output", required=True)
    complete.add_argument("--expected-discovery-output-sha256", required=True)
    complete.add_argument("--observation-candidates", required=True)
    complete.add_argument("--expected-observation-candidates-sha256", required=True)
    complete.add_argument("--reviewed-dispositions", required=True)
    complete.add_argument("--expected-reviewed-dispositions-sha256", required=True)
    complete.add_argument("--producer-sha256", required=True)
    complete.add_argument("--proof-runner-sha256", required=True)
    complete.add_argument("--no-consumption-captured-at", required=True)
    complete.add_argument("--a1-evidence-root", required=True)
    complete.add_argument("--output", required=True)

    publish = subparsers.add_parser("publish-policy")
    publish.add_argument("--candidate", required=True)
    publish.add_argument("--expected-candidate-sha256", required=True)
    publish.add_argument("--plan", required=True)
    publish.add_argument("--expected-plan-sha256", required=True)
    publish.add_argument("--plan-spec-review", required=True)
    publish.add_argument("--expected-plan-spec-review-sha256", required=True)
    publish.add_argument("--plan-quality-review", required=True)
    publish.add_argument("--expected-plan-quality-review-sha256", required=True)
    publish.add_argument("--implementation-review", required=True)
    publish.add_argument("--expected-implementation-review-sha256", required=True)
    publish.add_argument("--policy-schema", required=True)
    publish.add_argument("--output", required=True)

    census = subparsers.add_parser("build-census")
    _add_discovery_arguments(census, output=False)
    census.add_argument("--discovery-output", required=True)
    census.add_argument("--expected-discovery-output-sha256", required=True)
    census.add_argument("--policy", required=True)
    census.add_argument("--policy-schema", required=True)
    census.add_argument("--expected-policy-sha256", required=True)
    census.add_argument("--producer-sha256", required=True)
    census.add_argument("--census-schema", required=True)
    census.add_argument("--output", required=True)

    selector = subparsers.add_parser("build-selector")
    selector.add_argument("--policy", required=True)
    selector.add_argument("--policy-schema", required=True)
    selector.add_argument("--expected-policy-sha256", required=True)
    selector.add_argument("--census", required=True)
    selector.add_argument("--census-schema", required=True)
    selector.add_argument("--expected-census-sha256", required=True)
    selector.add_argument("--baseline-characterization", required=True)
    selector.add_argument("--expected-baseline-sha256", required=True)
    selector.add_argument("--feasibility-capture-manifest", required=True)
    selector.add_argument("--feasibility-capture-manifest-schema", required=True)
    selector.add_argument(
        "--expected-feasibility-capture-manifest-sha256", required=True
    )
    selector.add_argument("--selector-schema", required=True)
    selector.add_argument("--output", required=True)

    validate = subparsers.add_parser("validate")
    _add_discovery_arguments(validate, output=False)
    for name in ("discovery-output", "policy", "census", "selector-manifest", "a1-anchor"):
        validate.add_argument(f"--{name}", required=True)
        if name != "discovery-output":
            validate.add_argument(f"--{name}-schema", required=True)
        validate.add_argument(f"--expected-{name}-sha256", required=True)
    validate.add_argument("--plan", required=True)
    validate.add_argument("--expected-plan-sha256", required=True)
    validate.add_argument("--proposal-state", choices=("proposed", "adopted"), required=True)
    validate.add_argument("--review-adoption")
    validate.add_argument("--review-adoption-schema")
    validate.add_argument("--expected-review-adoption-sha256")
    validate.add_argument("--feasibility-capture-manifest", required=True)
    validate.add_argument("--feasibility-capture-manifest-schema", required=True)
    validate.add_argument("--expected-feasibility-capture-manifest-sha256", required=True)
    validate.add_argument("--post-purge-tombstone")
    validate.add_argument("--post-purge-tombstone-schema")
    validate.add_argument("--expected-post-purge-tombstone-sha256")
    return parser


def _verify_projection_arguments(args: argparse.Namespace, record: Mapping[str, object]) -> None:
    projection = record["projection"]
    expected = {
        "repository": args.projection_repository,
        "commit": args.projection_commit,
        "tree": args.expected_tree,
        "inventory_sha256": args.expected_inventory_sha256,
        "leaf_count": args.expected_leaf_count,
    }
    if projection != expected:
        _fail("projection_cli_binding_mismatch", expected, "CLI projection bindings differ")


def _load_discovery_input_from_args(args: argparse.Namespace) -> dict[str, Any]:
    _require_published_schema_path(
        args.discovery_input_schema, role="discovery_input"
    )
    record = _load_raw_bound_json(
        args.discovery_input,
        schema_path=args.discovery_input_schema,
        expected_sha256=args.expected_discovery_input_sha256,
        label="discovery input",
        require_canonical=False,
    )
    _validate_discovery_input(record)
    _validate_frozen_projection_authority(record["projection"])
    _verify_projection_arguments(args, record)
    return record


def _command_discover(args: argparse.Namespace) -> None:
    discovery_input = _load_discovery_input_from_args(args)
    output = discover_source(
        discovery_input,
        discovery_input_sha256=args.expected_discovery_input_sha256,
    )
    _publish_json(args.output, output)


def _command_complete_policy_candidate(args: argparse.Namespace) -> None:
    discovery_input = _load_raw_bound_json(
        args.discovery_input,
        schema_path=None,
        expected_sha256=args.expected_discovery_input_sha256,
        label="discovery input",
        require_canonical=False,
    )
    discovery_output = _load_raw_bound_json(
        args.discovery_output,
        schema_path=None,
        expected_sha256=args.expected_discovery_output_sha256,
        label="discovery output",
        require_canonical=True,
    )
    observation_candidates = _load_raw_bound_json(
        args.observation_candidates,
        schema_path=None,
        expected_sha256=args.expected_observation_candidates_sha256,
        label="observation candidates",
        require_canonical=True,
    )
    reviewed_dispositions = _load_raw_bound_json(
        args.reviewed_dispositions,
        schema_path=None,
        expected_sha256=args.expected_reviewed_dispositions_sha256,
        label="reviewed dispositions",
        require_canonical=True,
    )
    candidate = complete_policy_candidate(
        discovery_input,
        discovery_output=discovery_output,
        observation_candidates=observation_candidates,
        reviewed_dispositions=reviewed_dispositions,
        expected_discovery_input_sha256=args.expected_discovery_input_sha256,
        expected_discovery_output_sha256=args.expected_discovery_output_sha256,
        expected_observation_candidates_sha256=(
            args.expected_observation_candidates_sha256
        ),
        expected_reviewed_dispositions_sha256=(
            args.expected_reviewed_dispositions_sha256
        ),
        producer_sha256=args.producer_sha256,
        proof_runner_sha256=args.proof_runner_sha256,
        no_consumption_captured_at=args.no_consumption_captured_at,
        a1_evidence_root=args.a1_evidence_root,
    )
    _publish_json(args.output, candidate)


def _require_exact_repository_input(
    value: str | Path, *, relative: str, label: str
) -> Path:
    supplied = Path(value)
    if not supplied.is_absolute():
        supplied = REPOSITORY_ROOT / supplied
    expected = REPOSITORY_ROOT / relative
    try:
        if supplied.resolve(strict=True) != expected.resolve(strict=True):
            _fail(
                "publication_input_path_invalid",
                str(value),
                f"{label} is not the exact repository path",
            )
    except OSError as exc:
        raise SourceCensusError(
            "publication_input_path_invalid",
            str(value),
            f"{label} is missing or unreadable",
        ) from exc
    return expected


def _require_exact_repository_output(value: str | Path, *, relative: str) -> Path:
    supplied = Path(value)
    if not supplied.is_absolute():
        supplied = REPOSITORY_ROOT / supplied
    expected = REPOSITORY_ROOT / relative
    if supplied != expected:
        _fail(
            "publication_output_path_invalid",
            str(value),
            "policy output is not the exact canonical authority path",
        )
    return expected


def _command_publish_policy(args: argparse.Namespace) -> None:
    candidate = _load_raw_bound_json(
        args.candidate,
        schema_path=None,
        expected_sha256=args.expected_candidate_sha256,
        label="complete policy candidate",
        require_canonical=True,
    )
    plan_path = _require_exact_repository_input(
        args.plan,
        relative=_WITNESS_PLAN_PATH,
        label="correction plan",
    )
    try:
        plan_raw = plan_path.read_bytes()
    except OSError as exc:
        raise SourceCensusError(
            "publication_input_unreadable",
            str(plan_path),
            "correction plan cannot be read",
        ) from exc
    if raw_sha256(plan_raw) != _sha256(
        args.expected_plan_sha256, label="expected correction plan SHA-256"
    ):
        _fail("raw_digest_mismatch", str(plan_path), "correction plan raw digest drifted")
    spec_path = _require_exact_repository_input(
        args.plan_spec_review,
        relative=_WITNESS_PLAN_SPEC_REVIEW_PATH,
        label="plan specification review",
    )
    quality_path = _require_exact_repository_input(
        args.plan_quality_review,
        relative=_WITNESS_PLAN_QUALITY_REVIEW_PATH,
        label="plan quality review",
    )
    implementation_path = _require_exact_repository_input(
        args.implementation_review,
        relative=_WITNESS_IMPLEMENTATION_REVIEW_PATH,
        label="implementation review",
    )
    plan_specification_review = _load_raw_bound_json(
        spec_path,
        schema_path=None,
        expected_sha256=args.expected_plan_spec_review_sha256,
        label="plan specification review",
        require_canonical=True,
    )
    plan_quality_review = _load_raw_bound_json(
        quality_path,
        schema_path=None,
        expected_sha256=args.expected_plan_quality_review_sha256,
        label="plan quality review",
        require_canonical=True,
    )
    implementation_review = _load_raw_bound_json(
        implementation_path,
        schema_path=None,
        expected_sha256=args.expected_implementation_review_sha256,
        label="implementation review",
        require_canonical=True,
    )
    policy_schema = _require_published_schema_path(
        args.policy_schema, role="preedit_policy"
    )
    policy = publish_policy_candidate(
        candidate,
        expected_candidate_sha256=args.expected_candidate_sha256,
        current_plan_sha256=args.expected_plan_sha256,
        plan_specification_review=plan_specification_review,
        expected_plan_specification_review_sha256=(
            args.expected_plan_spec_review_sha256
        ),
        plan_quality_review=plan_quality_review,
        expected_plan_quality_review_sha256=(
            args.expected_plan_quality_review_sha256
        ),
        implementation_review=implementation_review,
        expected_implementation_review_sha256=(
            args.expected_implementation_review_sha256
        ),
        policy_schema=policy_schema,
    )
    output = _require_exact_repository_output(
        args.output,
        relative=(
            "docs/plans/evidence/es-f1-large-scope-refreeze/"
            "preedit-policy-manifest.json"
        ),
    )
    _publish_json_exclusive(output, policy)


def _command_build_census(args: argparse.Namespace) -> None:
    discovery_input = _load_discovery_input_from_args(args)
    _require_published_schema_path(args.policy_schema, role="preedit_policy")
    _require_published_schema_path(args.census_schema, role="source_census")
    discovery_output = _load_raw_bound_json(
        args.discovery_output,
        schema_path=None,
        expected_sha256=args.expected_discovery_output_sha256,
        label="discovery output",
        require_canonical=True,
    )
    policy = _load_authority_record(
        args.policy,
        schema_path=args.policy_schema,
        expected_sha256=args.expected_policy_sha256,
        label="pre-edit policy",
    )
    census = build_source_census(
        discovery_input=discovery_input,
        discovery_output=discovery_output,
        policy=policy,
        producer={
            "path": "scripts/experiments/es/source_census.py",
            "sha256": args.producer_sha256,
        },
        discovery_input_sha256=args.expected_discovery_input_sha256,
    )
    _validate_schema(census, args.census_schema, label="source census")
    _publish_json(args.output, census)


def _command_build_selector(args: argparse.Namespace) -> None:
    _require_published_schema_path(args.policy_schema, role="preedit_policy")
    _require_published_schema_path(args.census_schema, role="source_census")
    _require_published_schema_path(args.selector_schema, role="selector_manifest")
    _require_published_schema_path(
        args.feasibility_capture_manifest_schema, role="feasibility_capture"
    )
    policy = _load_authority_record(
        args.policy,
        schema_path=args.policy_schema,
        expected_sha256=args.expected_policy_sha256,
        label="pre-edit policy",
    )
    census = _load_authority_record(
        args.census,
        schema_path=args.census_schema,
        expected_sha256=args.expected_census_sha256,
        label="source census",
    )
    baseline = _load_raw_bound_json(
        args.baseline_characterization,
        schema_path=None,
        expected_sha256=args.expected_baseline_sha256,
        label="baseline characterization",
        require_canonical=True,
    )
    feasibility_capture = _load_authority_record(
        args.feasibility_capture_manifest,
        schema_path=args.feasibility_capture_manifest_schema,
        expected_sha256=args.expected_feasibility_capture_manifest_sha256,
        label="feasibility capture manifest",
    )
    projection_blobs = {
        row["pytest_module_path"]: projection_blob(census, row["pytest_module_path"])
        for row in policy["selector_policy"]["provider_visible_pytest_selectors"]
    }
    manifest = build_selector_manifest(
        policy=policy,
        census=census,
        baseline_characterization=baseline,
        feasibility_capture_manifest=feasibility_capture,
        projection_blobs=projection_blobs,
    )
    _validate_schema(manifest, args.selector_schema, label="selector manifest")
    _publish_json(args.output, manifest)


def _validate_a1(
    *,
    args: argparse.Namespace,
    policy: Mapping[str, object],
) -> dict[str, Any]:
    _require_published_schema_path(args.a1_anchor_schema, role="a1_anchor")
    calibration_module = _reference_calibration_module()
    GitContract = calibration_module.GitContract
    validate_a1_anchor = calibration_module.validate_a1_anchor

    metric = policy["a1"]["metric"]
    contract = GitContract(
        executable=Path(metric["git_executable"]),
        version=str(metric["git_version"]).removeprefix("git version "),
        executable_sha256=metric["git_sha256"],
        diff_controls=tuple(metric["diff_controls"]),
        policy_sha256=policy["record_sha256"],
    )
    try:
        calibration = validate_a1_anchor(
            Path(args.a1_anchor),
            schema_path=Path(args.a1_anchor_schema),
            expected_record_sha256=args.expected_a1_anchor_sha256,
            expected_preedit_policy_sha256=policy["record_sha256"],
            git_contract=contract,
        )
    except Exception as exc:
        raise SourceCensusError(
            "a1_anchor_invalid", args.a1_anchor, "A1 calibration replay failed"
        ) from exc
    anchor = calibration.record
    if (
        policy["a1"]["evidence_root"] != anchor["evidence_root"]
        or policy["a1"]["members"] != anchor["members"]
        or policy["a1"]["metric"]["implementation_additions"]
        != anchor["metric"]["implementation_additions"]
        or policy["a1"]["metric"]["implementation_deletions"]
        != anchor["metric"]["implementation_deletions"]
        or policy["a1"]["metric"]["candidate_postimage_physical_lines"]
        != anchor["metric"]["candidate_postimage_physical_lines"]
    ):
        _fail("a1_policy_binding_mismatch", policy["a1"], "policy and A1 anchor differ")
    return anchor


def _command_validate(args: argparse.Namespace) -> None:
    _require_published_schema_path(args.policy_schema, role="preedit_policy")
    _require_published_schema_path(args.census_schema, role="source_census")
    _require_published_schema_path(
        args.selector_manifest_schema, role="selector_manifest"
    )
    _require_published_schema_path(
        args.feasibility_capture_manifest_schema, role="feasibility_capture"
    )
    discovery_input = _load_discovery_input_from_args(args)
    discovery_output = _load_raw_bound_json(
        args.discovery_output,
        schema_path=None,
        expected_sha256=args.expected_discovery_output_sha256,
        label="discovery output",
        require_canonical=True,
    )
    policy = _load_authority_record(
        args.policy,
        schema_path=args.policy_schema,
        expected_sha256=args.expected_policy_sha256,
        label="pre-edit policy",
    )
    census = _load_authority_record(
        args.census,
        schema_path=args.census_schema,
        expected_sha256=args.expected_census_sha256,
        label="source census",
    )
    selector = _load_authority_record(
        args.selector_manifest,
        schema_path=args.selector_manifest_schema,
        expected_sha256=args.expected_selector_manifest_sha256,
        label="selector manifest",
    )
    feasibility_capture = _load_authority_record(
        args.feasibility_capture_manifest,
        schema_path=args.feasibility_capture_manifest_schema,
        expected_sha256=args.expected_feasibility_capture_manifest_sha256,
        label="feasibility capture manifest",
    )
    fresh_census = build_source_census(
        discovery_input=discovery_input,
        discovery_output=discovery_output,
        policy=policy,
        producer=census["producer"],
        discovery_input_sha256=args.expected_discovery_input_sha256,
    )
    if canonical_json_bytes(fresh_census) != canonical_json_bytes(census):
        _fail("census_replay_mismatch", census, "source census is not reproducible")
    projection_blobs = {
        row["pytest_module_path"]: projection_blob(census, row["pytest_module_path"])
        for row in policy["selector_policy"]["provider_visible_pytest_selectors"]
    }
    fresh_selector = build_selector_manifest(
        policy=policy,
        census=census,
        baseline_characterization=selector["baseline_characterization"],
        feasibility_capture_manifest=feasibility_capture,
        projection_blobs=projection_blobs,
        reobserve_capture_roots=args.proposal_state == "proposed",
    )
    if canonical_json_bytes(fresh_selector) != canonical_json_bytes(selector):
        _fail("selector_replay_mismatch", selector, "selector manifest is not reproducible")
    anchor = _validate_a1(args=args, policy=policy)
    _, plan_raw = _load_json(args.plan, label="plan") if str(args.plan).endswith(".json") else (None, Path(args.plan).read_bytes())
    if raw_sha256(plan_raw) != _sha256(args.expected_plan_sha256, label="expected plan SHA-256"):
        _fail("plan_digest_mismatch", args.plan, "plan raw digest drifted")
    bindings = {
        "plan_sha256": args.expected_plan_sha256,
        "preedit_policy_sha256": policy["record_sha256"],
        "source_census_sha256": census["record_sha256"],
        "selector_manifest_sha256": selector["record_sha256"],
        "a1_anchor_sha256": anchor["record_sha256"],
    }
    if args.proposal_state == "proposed":
        if any(
            value is not None
            for value in (
                args.review_adoption,
                args.review_adoption_schema,
                args.expected_review_adoption_sha256,
                args.post_purge_tombstone,
                args.post_purge_tombstone_schema,
                args.expected_post_purge_tombstone_sha256,
            )
        ):
            _fail(
                "review_adoption_unexpected",
                None,
                "proposed validation cannot adopt reviews or a purge tombstone",
            )
        return
    if not all(
        value is not None
        for value in (
            args.review_adoption,
            args.review_adoption_schema,
            args.expected_review_adoption_sha256,
            args.post_purge_tombstone,
            args.post_purge_tombstone_schema,
            args.expected_post_purge_tombstone_sha256,
        )
    ):
        _fail(
            "review_adoption_missing",
            None,
            "adopted validation requires the review record and purge tombstone",
        )
    _require_published_schema_path(
        args.post_purge_tombstone_schema, role="post_purge_tombstone"
    )
    tombstone = _load_authority_record(
        args.post_purge_tombstone,
        schema_path=args.post_purge_tombstone_schema,
        expected_sha256=args.expected_post_purge_tombstone_sha256,
        label="post-purge tombstone",
    )
    validate_post_purge_tombstone(
        tombstone,
        capture_manifest=feasibility_capture,
    )
    _require_published_schema_path(
        args.review_adoption_schema, role="review_adoption"
    )
    adoption = _load_authority_record(
        # The closed review schema is part of the policy-bound schema set.
        args.review_adoption,
        schema_path=args.review_adoption_schema,
        expected_sha256=args.expected_review_adoption_sha256,
        label="review adoption",
    )
    validate_review_adoption(
        adoption,
        expected_bindings=bindings,
        expected_post_purge_tombstone_sha256=tombstone["record_sha256"],
        post_purge_tombstone=tombstone,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    commands = {
        "discover": _command_discover,
        "complete-policy-candidate": _command_complete_policy_candidate,
        "publish-policy": _command_publish_policy,
        "build-census": _command_build_census,
        "build-selector": _command_build_selector,
        "validate": _command_validate,
    }
    try:
        commands[args.command](args)
    except SourceCensusError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
