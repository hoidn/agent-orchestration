from __future__ import annotations

import importlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import cast

import pytest


ROOT = Path(__file__).resolve().parents[2]
F1_ROOT = ROOT / "experiments" / "orc_effectiveness" / "f1_es"
TASK_PROFILE_PATH = F1_ROOT / "task-profile.json"
TASK_SEED_MANIFEST_PATH = F1_ROOT / "task-seed-manifest.json"
VISIBLE_CHECK_PATH = F1_ROOT / "task" / "visible-check-manifest.json"

BUILTIN_ARCHITECTURES = (
    "cnn",
    "ffno",
    "fno",
    "fno_vanilla",
    "hybrid",
    "hybrid_resnet",
    "hybrid_resnet_convnext_bottleneck",
    "hybrid_resnet_ffno_bottleneck",
    "hybrid_resnet_ffno_ptychoblock_encoder",
    "hybrid_resnet_ptychoblock_ffno_encoder",
    "neuralop_uno",
    "spectral_resnet_bottleneck_linear_decoder",
    "spectral_resnet_bottleneck_net",
    "stable_hybrid",
)

PROVIDER_VISIBLE_SELECTORS = (
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

HARD_CLAUSE_IDS = (
    "F1-H01-FOCUSED-SUITES",
    "F1-H02-SCHEMA-CONFORMANCE",
    "F1-H03-BUILTIN-SIGNATURES",
    "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
    "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
    "F1-H06-STRUCTURAL-ROUNDTRIP",
    "F1-H07-STRUCTURAL-IDENTITY-REJECTION",
    "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY",
    "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
    "F1-H10-OWNERSHIP-BOUNDARY",
)

LIFECYCLE_STAGES = (
    "CONFIGURATION",
    "CONSTRUCTION",
    "FORWARD",
    "BACKWARD",
    "OPTIMIZER_STEP",
    "CHECKPOINT_PERSISTENCE",
    "CHECKPOINT_FRESH_RELOAD",
    "BUNDLE_PERSISTENCE",
    "BUNDLE_FRESH_RELOAD",
    "POST_RELOAD_INFERENCE",
    "STRUCTURAL_IDENTITY",
    "ROUND_TRIP_RECONSTRUCTION",
)


def _task_package_module():
    return importlib.import_module("scripts.experiments.es.task_package")


def test_checked_in_profile_freezes_the_complete_visible_f1_contract() -> None:
    task_package = _task_package_module()

    profile = task_package.load_task_profile(TASK_PROFILE_PATH)

    assert profile.task_id == "F1"
    assert profile.fixed_output_paths == (
        "scripts/es_f1_lifecycle_adapter.py",
        "es_f1_candidate_evidence.json",
        "tests/torch/test_es_f1_extension_boundary.py",
    )
    assert profile.candidate_declared_output_ids == (
        "ARCHITECTURE_DECISION_RECORD",
        "EXTENSION_AUTHOR_GUIDE",
    )
    assert len(profile.hard_clause_ids) == 10
    assert profile.finding_dispositions == (
        "PRODUCT_DEFECT",
        "ORACLE_DEFECT",
        "SPEC_AMBIGUITY",
        "INFRASTRUCTURE",
        "UNRESOLVED",
    )
    assert profile.reviewer_perspective_ids == (
        "SCIENTIFIC_APPLICATION_SEMANTICS",
        "API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    )
    assert profile.focused_selectors == PROVIDER_VISIBLE_SELECTORS
    assert profile.builtin_architectures == BUILTIN_ARCHITECTURES
    assert profile.required_task_seed_schema_version == "es_f1_task_seed.v2"
    selector_authority = json.loads(
        (
            ROOT
            / "docs/plans/evidence/es-f1-large-scope-refreeze/preedit-selector-manifest.json"
        ).read_bytes()
    )
    assert profile.selector_manifest_record_digest == selector_authority["record_sha256"]
    assert len(selector_authority["controller_only_proof_selectors"]) > 0
    profile_bytes = TASK_PROFILE_PATH.read_bytes()
    assert b"es_f1_task_seed.v1" not in profile_bytes
    assert b"93e0eb08e092fed177316517328b7effc2893399" not in profile_bytes
    assert b"6bc1aff56b7273fcf02e81b7c37cd63efa8250eb" not in profile_bytes
    assert profile.hard_clause_ids == HARD_CLAUSE_IDS
    assert profile.environment_name == "ptycho311"
    assert profile.claim_limit_ids


def test_selector_authority_reload_revalidates_changed_bytes(tmp_path: Path) -> None:
    task_package = _task_package_module()
    authority_root = (
        ROOT / "docs/plans/evidence/es-f1-large-scope-refreeze"
    )
    authority_path = tmp_path / "preedit-selector-manifest.json"
    schema_path = tmp_path / "preedit-selector-manifest.schema.json"
    authority_path.write_bytes(
        (authority_root / authority_path.name).read_bytes()
    )
    schema_path.write_bytes((authority_root / schema_path.name).read_bytes())

    task_package._load_preedit_selector_authority(authority_path, schema_path)
    tampered = json.loads(authority_path.read_bytes())
    tampered["provider_visible_pytest_selectors"] = []
    authority_path.write_bytes(task_package.canonical_json_bytes(tampered))

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package._load_preedit_selector_authority(authority_path, schema_path)

    assert caught.value.code == "task_package_selector_authority_mismatch"


def test_unchanged_selector_authority_load_reuses_only_exact_byte_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_package = _task_package_module()
    authority_root = (
        ROOT / "docs/plans/evidence/es-f1-large-scope-refreeze"
    )
    authority_path = tmp_path / "preedit-selector-manifest.json"
    schema_path = tmp_path / "preedit-selector-manifest.schema.json"
    authority_path.write_bytes(
        (authority_root / authority_path.name).read_bytes()
    )
    schema_path.write_bytes((authority_root / schema_path.name).read_bytes())
    validation_calls = 0
    original_validator = task_package.Draft202012Validator

    def counting_validator(schema):
        nonlocal validation_calls
        validation_calls += 1
        return original_validator(schema)

    monkeypatch.setattr(
        task_package,
        "Draft202012Validator",
        counting_validator,
    )

    first = task_package._load_preedit_selector_authority(
        authority_path,
        schema_path,
    )
    second = task_package._load_preedit_selector_authority(
        authority_path,
        schema_path,
    )

    assert validation_calls == 1
    assert first == second
    assert first is not second
    original_digest = second["record_sha256"]
    first["record_sha256"] = "mutated-after-load"
    assert second["record_sha256"] == original_digest


def test_visible_check_manifest_freezes_exact_runner_and_candidate_selector() -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)

    checks = task_package.load_visible_check_manifest(VISIBLE_CHECK_PATH)

    assert checks.python_executable == Path(
        "/home/ollie/miniconda3/envs/ptycho311/bin/python3.11"
    )
    assert checks.argv_prefix == (
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
    )
    assert (
        checks.working_directory_policy
        == "external-disposable-invocation-root.v1"
    )
    assert checks.pre_edit_selectors == profile.focused_selectors
    assert checks.candidate_selector == "tests/torch/test_es_f1_extension_boundary.py"
    assert checks.invocation_order == ("PRE_EDIT_FOCUSED", "CANDIDATE_EXTENSION")
    assert checks.required_environment == (
        ("PYTHONPATH", ""),
        ("PYTHONDONTWRITEBYTECODE", "1"),
        ("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1"),
    )
    assert checks.timeout_seconds == 7_200
    assert all(
        "controller_only_proof_selectors" not in invocation
        for invocation in checks.raw["invocations"]
    )


def test_visible_contract_freezes_full_matrix_lifecycle_and_claim_boundaries() -> None:
    contract = json.loads(
        (F1_ROOT / "task" / "visible-task-contract.json").read_bytes()
    )

    assert contract["schema_version"] == "es_f1_visible_task_contract.v2"
    assert tuple(contract["builtin_architectures"]) == BUILTIN_ARCHITECTURES
    assert tuple(contract["required_lifecycle_stages"]) == LIFECYCLE_STAGES
    assert tuple(row["id"] for row in contract["hard_contract"]) == HARD_CLAUSE_IDS
    assert tuple(contract["focused_selectors"]) == PROVIDER_VISIBLE_SELECTORS
    assert contract["claim_boundaries"] == {
        "no_f2_quantitative_claims": [
            "EDIT_LOCALITY",
            "SCHEMA_EVOLUTION",
            "CROSS_TASK_GENERALIZATION",
        ],
        "projected_f1_scope": "complete-frozen-projected-f1-closure.v1",
    }
    assert contract["legacy_architecture_aliases"] == {
        "aliases": [],
        "authority": "frozen-source-registry-and-adopted-proposal.v1",
    }
    assert contract["witness_identity_proof"] == {
        "authority": "evaluator-owned.v1",
        "built_in_relation": "distinct-from-all-fourteen.v1",
        "equality": "all-identities-equal.v1",
        "identity_roles": [
            "REGISTRY_CONSTRUCTOR",
            "PUBLIC_CONSTRUCTION",
            "CHECKPOINT_RELOAD",
            "BUNDLE_RELOAD",
            "PERSISTED_REBUILD",
        ],
    }
    assert contract["construction_boundary_policy"] == {
        "legacy_direct_bypass": "forbidden.v1",
        "policy": "public-extension-boundary-only.v1",
    }

    forbidden_acceptance_fields = {
        "churn",
        "file_count",
        "loc",
        "maximum_diff",
        "minimum_diff",
    }

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden_acceptance_fields.isdisjoint(value)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(contract)


def test_checked_in_seed_manifest_binds_sorted_visible_assets_and_exact_git_vectors() -> None:
    task_package = _task_package_module()

    manifest = task_package.load_task_seed_manifest(TASK_SEED_MANIFEST_PATH)

    assert manifest.parent_commit == "8f191031f233d50a4d020d8a988036e99487f570"
    assert manifest.parent_tree == "e64f3c05f5a0894f41c047d128a9040a2cda6764"
    assert manifest.visible_assets_digest == (
        "sha256:e0a1749b712bf6f7326889c04863e2224f70a60c748d60794f483dd47efebced"
    )
    assert tuple((row.source_path, row.target_path) for row in manifest.visible_assets) == tuple(
        sorted((row.source_path, row.target_path) for row in manifest.visible_assets)
    )
    assert all(row.target_path.startswith("benchmark/es_f1/") for row in manifest.visible_assets)
    assert manifest.tree == "6bc1aff56b7273fcf02e81b7c37cd63efa8250eb"
    assert manifest.commit == "93e0eb08e092fed177316517328b7effc2893399"
    assert len(manifest.commit_message) == 222
    assert manifest.commit_content_bytes == 496
    assert manifest.object_count == 2_216
    assert manifest.locator == Path(
        "/home/ollie/.local/state/orchestrator/es-task-seeds/"
        "git-sha1/93e0eb08e092fed177316517328b7effc2893399"
    )
    assert manifest.e1_source_manifest_digest == (
        "sha256:13ebfe2226072e750be6311ec7d6eb67d6796b5538736e84a69560eb75375c39"
    )
    assert manifest.e1_post_setup_manifest_digest == manifest.e1_source_manifest_digest


def test_every_checked_in_task_schema_is_valid_and_closes_nested_records() -> None:
    from jsonschema import Draft202012Validator

    schemas = tuple((F1_ROOT / "task").glob("*.schema.json")) + (
        F1_ROOT / "task-profile.schema.json",
        F1_ROOT / "task-seed-manifest.schema.json",
    )
    assert len(schemas) == 7

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
                assert "required" in value
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    for schema_path in schemas:
        schema = json.loads(schema_path.read_bytes())
        Draft202012Validator.check_schema(schema)
        walk(schema)


def test_profile_freezes_exact_twelve_imported_soft_review_dimensions() -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)

    assert profile.review_dimension_ids == (
        "SEMANTIC_AND_SCIENTIFIC_CORRECTNESS",
        "TASK_INTENT_COMPLETENESS",
        "DIAGNOSIS_OF_CURRENT_DESIGN_SMELL",
        "OWNERSHIP_AND_BOUNDARY_COHERENCE",
        "ARTIFACT_RELOAD_AND_MIGRATION_REASONING",
        "MAINTAINABILITY_AND_SIMPLICITY",
        "EXTENSION_EDIT_LOCALITY",
        "TEST_AND_EVIDENCE_QUALITY",
        "SCOPE_DISCIPLINE",
        "FAILURE_DIAGNOSTICS",
        "DOCUMENTATION_SUFFICIENCY",
        "LIKELY_LATENT_DEFECTS",
    )
    contract = json.loads(
        (F1_ROOT / "task" / "visible-task-contract.json").read_bytes()
    )
    owned = {
        dimension
        for perspective in contract["reviewer_perspectives"]
        for dimension in perspective["owned_dimensions"]
    }
    assert owned == set(profile.review_dimension_ids)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "pretty",
        "bad-scalar",
        "unsafe-path",
        "dot-path",
        "internal-dot-path",
        "digest-drift",
        "seed-version-drift",
        "brief-digest-drift",
        "visible-schema-digest-drift",
        "visible-check-digest-drift",
        "selector-authority-drift",
        "review-dimension-drift",
        "version-drift",
    ],
)
def test_profile_loader_fails_closed_on_noncanonical_shape_and_binding_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    task_package = _task_package_module()
    payload = json.loads(TASK_PROFILE_PATH.read_bytes())
    if mutation == "missing":
        payload.pop("task_id")
    elif mutation == "extra":
        payload["unexpected"] = None
    elif mutation == "bad-scalar":
        payload["environment"]["python_version"] = 3.11
    elif mutation == "unsafe-path":
        payload["neutral_brief"]["source_path"] = "../neutral-task-brief.md"
    elif mutation == "dot-path":
        payload["neutral_brief"]["source_path"] = "."
    elif mutation == "internal-dot-path":
        payload["neutral_brief"]["source_path"] = (
            "experiments/orc_effectiveness/./f1_es/task/neutral-task-brief.md"
        )
    elif mutation == "digest-drift":
        payload["visible_contract"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "seed-version-drift":
        payload["task_seed"]["required_schema_version"] = "es_f1_task_seed.v1"
    elif mutation == "brief-digest-drift":
        payload["neutral_brief"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "visible-schema-digest-drift":
        payload["visible_schema_bindings"][0]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "visible-check-digest-drift":
        payload["visible_check"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "selector-authority-drift":
        payload["selector_authority"]["record_sha256"] = "sha256:" + "0" * 64
    elif mutation == "review-dimension-drift":
        payload["review_dimension_ids"][0] = "SUBSTITUTE_DIMENSION"
    elif mutation == "version-drift":
        payload["schema_version"] = "es_f1_task_profile.v1"
    candidate = F1_ROOT / "task-profile.json"
    schema = F1_ROOT / "task-profile.schema.json"
    if mutation == "duplicate":
        raw = TASK_PROFILE_PATH.read_bytes().replace(
            b'{"builtin_architectures":',
            b'{"task_id":"F1","task_id":"F1","builtin_architectures":',
            1,
        )
    elif mutation == "pretty":
        raw = json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
    else:
        raw = task_package.canonical_json_bytes(payload)
    candidate_copy = tmp_path / candidate.name
    schema_copy = tmp_path / schema.name
    candidate_copy.write_bytes(raw)
    schema_copy.write_bytes(schema.read_bytes())

    with pytest.raises(task_package.TaskPackageError):
        task_package.load_task_profile(candidate_copy)


def _candidate_evidence_payload(profile) -> dict[str, object]:
    def architecture(public_id: str, *, witness: bool = False) -> dict[str, object]:
        field_name = "witness_depth" if witness else "architecture"
        return {
            "construction_route": "ptycho_torch.generators.registry.resolve_generator",
            "persisted_rebuild_route": (
                "ptycho_torch.application_factory.build_ptychopinn_application"
            ),
            "public_id": public_id,
            "structural_fields": [
                {
                    "alternate_value": 3 if witness else f"{public_id}-alternate",
                    "baseline_value": 2 if witness else public_id,
                    "name": field_name,
                }
            ],
        }

    return {
        "architecture_decision_path": "docs/adr/es-f1-boundary.md",
        "builtin_architectures": [
            architecture(public_id) for public_id in BUILTIN_ARCHITECTURES
        ],
        "candidate_id": "candidate-a",
        "candidate_witness": architecture("novel_witness", witness=True),
        "claims": [
            {
                "clause_id": clause_id,
                "evidence_paths": ["tests/torch/test_es_f1_extension_boundary.py"],
                "scope": "IMPLEMENTED",
            }
            for clause_id in profile.hard_clause_ids
        ],
        "extension_author_guide_path": "docs/guides/es-f1-extension.md",
        "fixed_outputs": {
            "candidate_test_path": "tests/torch/test_es_f1_extension_boundary.py",
            "lifecycle_adapter_path": "scripts/es_f1_lifecycle_adapter.py",
        },
        "ownership": {
            "excludes": ["PHYSICS", "LOSS", "SCALING", "DATA_OWNERSHIP"],
            "owns": [
                "ARCHITECTURE_IDENTITY",
                "STRUCTURAL_CONFIGURATION",
                "CONSTRUCTION",
                "PERSISTENCE_MIGRATION",
            ],
        },
        "schema_version": "candidate_extension_evidence.v2",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "pretty",
        "dot-selector",
        "candidate-selector",
        "runner-digest",
        "working-directory-policy",
        "invocation-order",
    ],
)
def test_visible_check_loader_rejects_open_or_drifted_runner_contracts(
    tmp_path: Path,
    mutation: str,
) -> None:
    task_package = _task_package_module()
    payload = json.loads(VISIBLE_CHECK_PATH.read_bytes())
    if mutation == "missing":
        payload.pop("task_id")
    elif mutation == "extra":
        payload["unexpected"] = None
    elif mutation == "dot-selector":
        payload["invocations"][1]["selectors"][0] = "tests/torch/./candidate.py"
    elif mutation == "candidate-selector":
        payload["invocations"][1]["selectors"][0] = "tests/torch/other.py"
    elif mutation == "runner-digest":
        payload["runner"]["python_executable_sha256"] = "sha256:" + "0" * 64
    elif mutation == "working-directory-policy":
        payload["runner"]["working_directory_policy"] = "candidate-root.v1"
    elif mutation == "invocation-order":
        payload["invocation_order"].reverse()
    if mutation == "duplicate":
        raw = VISIBLE_CHECK_PATH.read_bytes().replace(
            b'{"invocation_order":',
            b'{"task_id":"F1","task_id":"F1","invocation_order":',
            1,
        )
    elif mutation == "pretty":
        raw = json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
    else:
        raw = task_package.canonical_json_bytes(payload)
    candidate = tmp_path / "visible-check-manifest.json"
    candidate.write_bytes(raw)
    candidate.with_name("visible-check-manifest.schema.json").write_bytes(
        VISIBLE_CHECK_PATH.with_name("visible-check-manifest.schema.json").read_bytes()
    )

    with pytest.raises(task_package.TaskPackageError):
        task_package.load_visible_check_manifest(candidate)


def _lifecycle_request_payload(
    evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    evidence = evidence or _candidate_evidence_payload(
        type("Profile", (), {"hard_clause_ids": HARD_CLAUSE_IDS})()
    )
    architectures = cast(list[dict[str, object]], evidence["builtin_architectures"])
    witness = cast(dict[str, object], evidence["candidate_witness"])
    cases = []
    for architecture in (*architectures, witness):
        architecture_id = cast(str, architecture["public_id"])
        cases.append(
            {
                "N": 128 if architecture_id == "neuralop_uno" else 64,
                "architecture_id": architecture_id,
                "config": {
                    "path": f"inputs/{architecture_id}-config.json",
                    "sha256": "sha256:" + "b" * 64,
                },
                "construction_route": architecture["construction_route"],
                "input": {
                    "path": f"inputs/{architecture_id}-cdi.npz",
                    "sha256": "sha256:" + "c" * 64,
                },
                "persisted_rebuild_route": architecture["persisted_rebuild_route"],
                "structural_fields": architecture["structural_fields"],
            }
        )
    return {
        "architecture_cases": cases,
        "candidate_evidence_path": "es_f1_candidate_evidence.json",
        "candidate_evidence_sha256": "sha256:__BOUND_BY_TEST__",
        "candidate_id": "candidate-a",
        "lifecycle_output_dir": ".es-f1/lifecycle",
        "operation_version": "ptychopinn_public_lifecycle.v2",
        "required_lifecycle_stages": list(LIFECYCLE_STAGES),
        "schema_version": "lifecycle_probe_request.v3",
        "seed": 1729,
    }


def _lifecycle_result_payload() -> dict[str, object]:
    return {
        "architecture_results": [
            {
                "architecture_id": architecture_id,
                "bundle_path": f"artifacts/{ordinal:02d}-{architecture_id}/wts.h5.zip",
                "checkpoint_path": (
                    f"artifacts/{ordinal:02d}-{architecture_id}/checkpoint.ckpt"
                ),
            }
            for ordinal, architecture_id in enumerate(
                (*BUILTIN_ARCHITECTURES, "novel_witness"), start=1
            )
        ],
        "candidate_id": "candidate-a",
        "operation_version": "ptychopinn_public_lifecycle.v2",
        "schema_version": "lifecycle_probe_result.v3",
    }


def _write_bound_candidate_evidence(
    tmp_path: Path,
    task_package,
    evidence: dict[str, object],
    request: dict[str, object],
) -> None:
    evidence_bytes = task_package.canonical_json_bytes(evidence)
    (tmp_path / "es_f1_candidate_evidence.json").write_bytes(evidence_bytes)
    request["candidate_evidence_sha256"] = (
        "sha256:" + hashlib.sha256(evidence_bytes).hexdigest()
    )


def test_lifecycle_loaders_accept_only_bound_inputs_and_artifact_paths(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    evidence = _candidate_evidence_payload(profile)
    request = _lifecycle_request_payload(evidence)
    _write_bound_candidate_evidence(tmp_path, task_package, evidence, request)
    request_path = tmp_path / "request.json"
    request_path.write_bytes(task_package.canonical_json_bytes(request))
    loaded_request = task_package.load_lifecycle_probe_request(request_path)
    assert loaded_request["seed"] == 1729
    assert loaded_request["operation_version"] == "ptychopinn_public_lifecycle.v2"
    cases = cast(list[dict[str, object]], loaded_request["architecture_cases"])
    assert tuple(row["architecture_id"] for row in cases) == (
        *BUILTIN_ARCHITECTURES,
        "novel_witness",
    )
    assert tuple(row["N"] for row in cases) == tuple(
        128 if architecture_id == "neuralop_uno" else 64
        for architecture_id in (*BUILTIN_ARCHITECTURES, "novel_witness")
    )

    result = _lifecycle_result_payload()
    result_path = tmp_path / "result.json"
    result_path.write_bytes(task_package.canonical_json_bytes(result))
    loaded_result = task_package.load_lifecycle_probe_result(
        result_path,
        expected_architecture_ids=(*BUILTIN_ARCHITECTURES, "novel_witness"),
        expected_candidate_id=cast(str, loaded_request["candidate_id"]),
    )
    assert "passed" not in loaded_result
    assert "representative_observation" not in loaded_result
    rows = cast(list[dict[str, str]], loaded_result["architecture_results"])
    assert len(rows) == 15
    artifact_paths = tuple(
        path
        for row in rows
        for path in (row["checkpoint_path"], row["bundle_path"])
    )
    assert len(artifact_paths) == len(set(artifact_paths)) == 30


def test_lifecycle_request_leaves_candidate_witness_size_evaluator_bound(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    evidence = _candidate_evidence_payload(profile)
    request = _lifecycle_request_payload(evidence)
    cases = cast(list[dict[str, object]], request["architecture_cases"])
    cases[-1]["N"] = 128
    _write_bound_candidate_evidence(tmp_path, task_package, evidence, request)
    request_path = tmp_path / "request.json"
    request_path.write_bytes(task_package.canonical_json_bytes(request))

    loaded_request = task_package.load_lifecycle_probe_request(request_path)

    loaded_cases = cast(
        list[dict[str, object]], loaded_request["architecture_cases"]
    )
    assert loaded_cases[-1]["architecture_id"] == "novel_witness"
    assert loaded_cases[-1]["N"] == 128


@pytest.mark.parametrize(
    ("record_kind", "bad_path"),
    [
        ("evidence", "."),
        ("evidence", "docs/./boundary.md"),
        ("request", "."),
        ("request", ".es-f1/./lifecycle"),
        ("result", "."),
        ("result", ".es-f1/./checkpoint.ckpt"),
        ("result", "benchmark/es_f1/checkpoint.ckpt"),
    ],
)
def test_safe_product_relative_paths_reject_dot_segments(
    tmp_path: Path,
    record_kind: str,
    bad_path: str,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    evidence = _candidate_evidence_payload(profile)
    request = _lifecycle_request_payload(evidence)
    _write_bound_candidate_evidence(tmp_path, task_package, evidence, request)
    result = _lifecycle_result_payload()
    if record_kind == "evidence":
        evidence["architecture_decision_path"] = bad_path
        payload = evidence
        loader = task_package.load_candidate_extension_evidence
    elif record_kind == "request":
        request["lifecycle_output_dir"] = bad_path
        payload = request
        loader = task_package.load_lifecycle_probe_request
    else:
        rows = cast(list[dict[str, str]], result["architecture_results"])
        rows[0]["checkpoint_path"] = bad_path
        payload = result
        loader = lambda path: task_package.load_lifecycle_probe_result(
            path,
            expected_architecture_ids=(*BUILTIN_ARCHITECTURES, "novel_witness"),
            expected_candidate_id="candidate-a",
        )
    path = tmp_path / f"{record_kind}.json"
    path.write_bytes(task_package.canonical_json_bytes(payload))

    with pytest.raises(task_package.TaskPackageError):
        loader(path)


@pytest.mark.parametrize("constant", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_emission_rejects_nonfinite_numbers(constant: float) -> None:
    task_package = _task_package_module()

    with pytest.raises(ValueError):
        task_package.canonical_json_bytes({"value": constant})


@pytest.mark.parametrize(
    "constant",
    [
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_closed_loader_rejects_nonfinite_structural_values(
    tmp_path: Path,
    constant: str,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    payload = _candidate_evidence_payload(profile)
    witness = cast(dict[str, object], payload["candidate_witness"])
    structural_fields = cast(list[dict[str, object]], witness["structural_fields"])
    structural_fields[0]["baseline_value"] = 2.0
    raw = task_package.canonical_json_bytes(payload).replace(
        b"2.0", constant.encode(), 1
    )
    loader = task_package.load_candidate_extension_evidence
    path = tmp_path / "evidence.json"
    path.write_bytes(raw)

    with pytest.raises(task_package.TaskPackageError):
        loader(path)


@pytest.mark.parametrize(
    ("record_kind", "mutation"),
    [
        ("evidence", "extra"),
        ("evidence", "duplicate"),
        ("evidence", "version"),
        ("evidence", "unsafe-path"),
        ("evidence", "duplicate-claim"),
        ("request", "bad-scalar"),
        ("request", "duplicate-architecture"),
        ("request", "missing-input-digest"),
        ("request", "operation-version"),
        ("result", "pass-bit"),
        ("result", "candidate-observation"),
        ("result", "old-version"),
    ],
)
def test_candidate_and_lifecycle_loaders_reject_open_or_ambiguous_records(
    tmp_path: Path,
    record_kind: str,
    mutation: str,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    evidence = _candidate_evidence_payload(profile)
    request = _lifecycle_request_payload(evidence)
    result = _lifecycle_result_payload()
    payload = {"evidence": evidence, "request": request, "result": result}[record_kind]
    if mutation == "extra" or mutation == "pass-bit":
        payload["passed"] = True
    elif mutation == "version":
        payload["schema_version"] = "candidate_extension_evidence.v1"
    elif mutation == "unsafe-path":
        payload["architecture_decision_path"] = "../escape.md"
    elif mutation == "duplicate-claim":
        claims = cast(list[object], payload["claims"])
        claims[-1] = claims[0]
    elif mutation == "bad-scalar":
        payload["seed"] = True
    elif mutation == "duplicate-architecture":
        cases = cast(list[dict[str, object]], payload["architecture_cases"])
        cases[-1]["architecture_id"] = cases[0]["architecture_id"]
    elif mutation == "missing-input-digest":
        cases = cast(list[dict[str, object]], payload["architecture_cases"])
        config = cast(dict[str, str], cases[0]["config"])
        config.pop("sha256")
    elif mutation == "operation-version":
        payload["operation_version"] = "candidate_defined.v1"
    elif mutation == "candidate-observation":
        payload["implementation_identity"] = "candidate.claimed.Identity"
    elif mutation == "old-version":
        payload["schema_version"] = "lifecycle_probe_result.v2"
    if record_kind == "request":
        _write_bound_candidate_evidence(tmp_path, task_package, evidence, request)
    path = tmp_path / f"{record_kind}.json"
    raw = task_package.canonical_json_bytes(payload)
    if mutation == "duplicate":
        raw = raw.replace(
            b'{"architecture_decision_path":',
            b'{"candidate_id":"candidate-a","candidate_id":"candidate-a","architecture_decision_path":',
            1,
        )
    path.write_bytes(raw)
    loader = {
        "evidence": task_package.load_candidate_extension_evidence,
        "request": task_package.load_lifecycle_probe_request,
        "result": lambda path: task_package.load_lifecycle_probe_result(
            path,
            expected_architecture_ids=(*BUILTIN_ARCHITECTURES, "novel_witness"),
            expected_candidate_id="candidate-a",
        ),
    }[record_kind]

    with pytest.raises(task_package.TaskPackageError):
        loader(path)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "task_package_schema_invalid"),
        ("extra", "task_package_schema_invalid"),
        ("duplicate", "candidate_evidence_builtin_matrix_mismatch"),
        ("reordered", "candidate_evidence_builtin_matrix_mismatch"),
        ("unknown", "candidate_evidence_builtin_matrix_mismatch"),
        ("builtin-collision", "candidate_evidence_witness_identity_invalid"),
    ],
)
def test_candidate_evidence_rejects_incomplete_or_aliased_architecture_domains(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    payload = _candidate_evidence_payload(profile)
    builtins = cast(list[dict[str, object]], payload["builtin_architectures"])
    witness = cast(dict[str, object], payload["candidate_witness"])
    if mutation == "missing":
        builtins.pop()
    elif mutation == "extra":
        builtins.append(dict(builtins[-1], public_id="extra_architecture"))
    elif mutation == "duplicate":
        builtins[-1] = dict(builtins[0])
    elif mutation == "reordered":
        builtins[0], builtins[1] = builtins[1], builtins[0]
    elif mutation == "unknown":
        builtins[-1] = dict(builtins[-1], public_id="unknown_architecture")
    elif mutation == "builtin-collision":
        witness["public_id"] = BUILTIN_ARCHITECTURES[0]
    path = tmp_path / "evidence.json"
    path.write_bytes(task_package.canonical_json_bytes(payload))

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_candidate_extension_evidence(path)

    assert caught.value.code == expected_code


def test_candidate_evidence_requires_a_witness_only_structural_field(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    payload = _candidate_evidence_payload(profile)
    witness = cast(dict[str, object], payload["candidate_witness"])
    structural_fields = cast(
        list[dict[str, object]], witness["structural_fields"]
    )
    structural_fields[0]["name"] = "architecture"
    path = tmp_path / "candidate-evidence.json"
    path.write_bytes(task_package.canonical_json_bytes(payload))

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_candidate_extension_evidence(path)

    assert caught.value.code == "candidate_evidence_witness_structural_field_invalid"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "task_package_schema_invalid"),
        ("extra", "task_package_schema_invalid"),
        ("duplicate", "lifecycle_probe_architecture_matrix_mismatch"),
        ("reordered", "lifecycle_probe_architecture_matrix_mismatch"),
        ("wrong-neuralop-N", "lifecycle_probe_image_size_mismatch"),
        ("wrong-builtin-N", "lifecycle_probe_image_size_mismatch"),
        ("route", "lifecycle_probe_case_binding_mismatch"),
        ("structural-fields", "lifecycle_probe_case_binding_mismatch"),
        ("stages", "task_package_schema_invalid"),
        ("evidence-digest", "lifecycle_probe_evidence_mismatch"),
    ],
)
def test_lifecycle_request_rejects_matrix_and_binding_tamper_before_execution(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    evidence = _candidate_evidence_payload(profile)
    request = _lifecycle_request_payload(evidence)
    _write_bound_candidate_evidence(tmp_path, task_package, evidence, request)
    cases = cast(list[dict[str, object]], request["architecture_cases"])
    if mutation == "missing":
        cases.pop()
    elif mutation == "extra":
        cases.append(dict(cases[-1], architecture_id="extra_architecture"))
    elif mutation == "duplicate":
        cases[-1] = dict(cases[0])
    elif mutation == "reordered":
        cases[0], cases[1] = cases[1], cases[0]
    elif mutation == "wrong-neuralop-N":
        cases[BUILTIN_ARCHITECTURES.index("neuralop_uno")]["N"] = 64
    elif mutation == "wrong-builtin-N":
        cases[0]["N"] = 128
    elif mutation == "route":
        cases[0]["construction_route"] = "candidate.private.construct"
    elif mutation == "structural-fields":
        fields = cast(list[dict[str, object]], cases[0]["structural_fields"])
        fields[0]["alternate_value"] = "tampered-alternate"
    elif mutation == "stages":
        stages = cast(list[str], request["required_lifecycle_stages"])
        stages.pop()
    else:
        request["candidate_evidence_sha256"] = "sha256:" + "0" * 64
    path = tmp_path / "request.json"
    path.write_bytes(task_package.canonical_json_bytes(request))

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_lifecycle_probe_request(path)

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "task_package_schema_invalid"),
        ("extra", "task_package_schema_invalid"),
        ("duplicate", "lifecycle_probe_result_matrix_mismatch"),
        ("reordered", "lifecycle_probe_result_matrix_mismatch"),
        ("duplicate-artifact", "lifecycle_probe_artifact_path_invalid"),
    ],
)
def test_lifecycle_result_rejects_row_and_artifact_path_tamper(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    task_package = _task_package_module()
    payload = _lifecycle_result_payload()
    rows = cast(list[dict[str, str]], payload["architecture_results"])
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(dict(rows[-1], architecture_id="extra_architecture"))
    elif mutation == "duplicate":
        rows[-1] = dict(rows[0])
    elif mutation == "reordered":
        rows[0], rows[1] = rows[1], rows[0]
    else:
        rows[-1]["bundle_path"] = rows[0]["bundle_path"]
    path = tmp_path / "result.json"
    path.write_bytes(task_package.canonical_json_bytes(payload))

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_lifecycle_probe_result(
            path,
            expected_architecture_ids=(*BUILTIN_ARCHITECTURES, "novel_witness"),
            expected_candidate_id="candidate-a",
        )

    assert caught.value.code == expected_code


def test_lifecycle_result_binds_candidate_id_to_request_context(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    request = _lifecycle_request_payload()
    payload = _lifecycle_result_payload()
    path = tmp_path / "result.json"
    path.write_bytes(task_package.canonical_json_bytes(payload))

    loaded = task_package.load_lifecycle_probe_result(
        path,
        expected_architecture_ids=(*BUILTIN_ARCHITECTURES, "novel_witness"),
        expected_candidate_id=cast(str, request["candidate_id"]),
    )
    assert loaded["candidate_id"] == request["candidate_id"]

    payload["candidate_id"] = "different-candidate"
    path.write_bytes(task_package.canonical_json_bytes(payload))
    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_lifecycle_probe_result(
            path,
            expected_architecture_ids=(
                *BUILTIN_ARCHITECTURES,
                "novel_witness",
            ),
            expected_candidate_id=cast(str, request["candidate_id"]),
        )

    assert caught.value.code == "lifecycle_probe_result_candidate_mismatch"


def test_lifecycle_result_requires_public_h5_zip_bundle_paths(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    payload = _lifecycle_result_payload()
    rows = cast(list[dict[str, str]], payload["architecture_results"])
    for row in rows:
        artifact_root = row["checkpoint_path"].rsplit("/", 1)[0]
        row["bundle_path"] = f"{artifact_root}/wts.h5.zip"
    path = tmp_path / "result.json"
    path.write_bytes(task_package.canonical_json_bytes(payload))

    loaded = task_package.load_lifecycle_probe_result(
        path,
        expected_architecture_ids=(*BUILTIN_ARCHITECTURES, "novel_witness"),
        expected_candidate_id="candidate-a",
    )
    loaded_rows = cast(list[dict[str, str]], loaded["architecture_results"])
    assert all(row["bundle_path"].endswith("/wts.h5.zip") for row in loaded_rows)

    rows[0]["bundle_path"] = "artifacts/01-cnn/bundle.json"
    path.write_bytes(task_package.canonical_json_bytes(payload))
    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_lifecycle_probe_result(
            path,
            expected_architecture_ids=(
                *BUILTIN_ARCHITECTURES,
                "novel_witness",
            ),
            expected_candidate_id="candidate-a",
        )

    assert caught.value.code == "task_package_schema_invalid"


@pytest.mark.parametrize(
    ("expected_architecture_ids", "expected_candidate_id"),
    [
        (None, "candidate-a"),
        ((*BUILTIN_ARCHITECTURES, "novel_witness"), None),
    ],
)
def test_lifecycle_result_fails_closed_when_request_context_is_missing(
    tmp_path: Path,
    expected_architecture_ids: tuple[str, ...] | None,
    expected_candidate_id: str | None,
) -> None:
    task_package = _task_package_module()
    path = tmp_path / "result.json"
    path.write_bytes(
        task_package.canonical_json_bytes(_lifecycle_result_payload())
    )

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_lifecycle_probe_result(
            path,
            expected_architecture_ids=expected_architecture_ids,
            expected_candidate_id=expected_candidate_id,
        )

    assert caught.value.code == "lifecycle_probe_result_context_missing"


@pytest.mark.parametrize(
    ("record_kind", "field"),
    [
        ("evidence", "registry_constructor_identity"),
        ("evidence", "checkpoint_reload_identity"),
        ("evidence", "supported_artifact_eras"),
        ("result", "implementation_identity"),
        ("result", "passed"),
    ],
)
def test_candidate_visible_records_cannot_author_evaluator_identity_or_verdicts(
    tmp_path: Path,
    record_kind: str,
    field: str,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    payload = (
        _candidate_evidence_payload(profile)
        if record_kind == "evidence"
        else _lifecycle_result_payload()
    )
    payload[field] = (
        ["candidate-claimed-era"]
        if field == "supported_artifact_eras"
        else "candidate.claimed"
        if "identity" in field
        else True
    )
    path = tmp_path / f"{record_kind}.json"
    path.write_bytes(task_package.canonical_json_bytes(payload))
    loader = (
        task_package.load_candidate_extension_evidence
        if record_kind == "evidence"
        else lambda path: task_package.load_lifecycle_probe_result(
            path,
            expected_architecture_ids=(*BUILTIN_ARCHITECTURES, "novel_witness"),
            expected_candidate_id="candidate-a",
        )
    )

    with pytest.raises(task_package.TaskPackageError) as caught:
        loader(path)

    assert caught.value.code == "task_package_schema_invalid"


@pytest.mark.parametrize(
    "seed_path",
    [None, TASK_SEED_MANIFEST_PATH],
    ids=["missing", "predecessor-v1"],
)
def test_execution_ready_loader_rejects_missing_or_predecessor_seed_before_checks(
    seed_path: Path | None,
) -> None:
    task_package = _task_package_module()

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_execution_ready_task_profile(
            TASK_PROFILE_PATH,
            task_seed_manifest_path=seed_path,
        )

    assert caught.value.code == "task_package_seed_not_ready"


@pytest.mark.parametrize(
    ("record_kind", "version_field", "version"),
    [
        ("profile", "schema_version", "es_f1_task_profile.v1"),
        ("profile", "schema_version", "es_f1_task_profile.v999"),
        ("contract", "schema_version", "es_f1_visible_task_contract.v1"),
        ("contract", "schema_version", "es_f1_visible_task_contract.v999"),
        ("checks", "schema_version", "es_f1_visible_checks.v1"),
        ("checks", "schema_version", "es_f1_visible_checks.v999"),
        ("evidence", "schema_version", "candidate_extension_evidence.v1"),
        ("evidence", "schema_version", "candidate_extension_evidence.v999"),
        ("request", "schema_version", "lifecycle_probe_request.v2"),
        ("request", "schema_version", "lifecycle_probe_request.v999"),
        ("request", "operation_version", "ptychopinn_public_lifecycle.v1"),
        ("request", "operation_version", "ptychopinn_public_lifecycle.v999"),
        ("result", "schema_version", "lifecycle_probe_result.v2"),
        ("result", "schema_version", "lifecycle_probe_result.v999"),
        ("result", "operation_version", "ptychopinn_public_lifecycle.v1"),
        ("result", "operation_version", "ptychopinn_public_lifecycle.v999"),
    ],
)
def test_asset_loaders_reject_every_predecessor_and_unknown_successor_version(
    tmp_path: Path,
    record_kind: str,
    version_field: str,
    version: str,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    evidence = _candidate_evidence_payload(profile)
    sources = {
        "profile": (TASK_PROFILE_PATH, task_package.load_task_profile),
        "contract": (
            F1_ROOT / "task" / "visible-task-contract.json",
            task_package.load_visible_task_contract,
        ),
        "checks": (VISIBLE_CHECK_PATH, task_package.load_visible_check_manifest),
        "evidence": (
            F1_ROOT / "task" / "candidate-extension-evidence.json",
            task_package.load_candidate_extension_evidence,
        ),
        "request": (
            F1_ROOT / "task" / "lifecycle-probe-request.json",
            task_package.load_lifecycle_probe_request,
        ),
        "result": (
            F1_ROOT / "task" / "lifecycle-probe-result.json",
            lambda path: task_package.load_lifecycle_probe_result(
                path,
                expected_architecture_ids=(*BUILTIN_ARCHITECTURES, "novel_witness"),
                expected_candidate_id="candidate-a",
            ),
        ),
    }
    source, loader = sources[record_kind]
    if record_kind == "profile":
        payload = json.loads(TASK_PROFILE_PATH.read_bytes())
        schema_source = F1_ROOT / "task-profile.schema.json"
    elif record_kind == "contract":
        payload = json.loads(
            (F1_ROOT / "task" / "visible-task-contract.json").read_bytes()
        )
        schema_source = F1_ROOT / "task" / "visible-task-contract.schema.json"
    elif record_kind == "checks":
        payload = json.loads(VISIBLE_CHECK_PATH.read_bytes())
        schema_source = VISIBLE_CHECK_PATH.with_name(
            "visible-check-manifest.schema.json"
        )
    elif record_kind == "evidence":
        payload = evidence
        schema_source = F1_ROOT / "task" / "candidate-extension-evidence.schema.json"
    elif record_kind == "request":
        payload = _lifecycle_request_payload(evidence)
        schema_source = F1_ROOT / "task" / "lifecycle-probe-request.schema.json"
    else:
        payload = _lifecycle_result_payload()
        schema_source = F1_ROOT / "task" / "lifecycle-probe-result.schema.json"
    payload[version_field] = version
    candidate = tmp_path / source.name
    candidate.write_bytes(task_package.canonical_json_bytes(payload))
    candidate.with_name(schema_source.name).write_bytes(schema_source.read_bytes())

    with pytest.raises(task_package.TaskPackageError) as caught:
        loader(candidate)

    assert caught.value.code == "task_package_schema_invalid"


def test_execution_ready_loader_rejects_unknown_seed_version_before_checks(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    payload = json.loads(TASK_SEED_MANIFEST_PATH.read_bytes())
    payload["schema_version"] = "es_f1_task_seed.v999"
    candidate = tmp_path / "task-seed-manifest.json"
    candidate.write_bytes(task_package.canonical_json_bytes(payload))

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_execution_ready_task_profile(
            TASK_PROFILE_PATH,
            task_seed_manifest_path=candidate,
        )

    assert caught.value.code == "task_package_seed_not_ready"


def test_successor_request_rejects_predecessor_candidate_evidence_as_mixed_package(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    profile = task_package.load_task_profile(TASK_PROFILE_PATH)
    evidence = _candidate_evidence_payload(profile)
    evidence["schema_version"] = "candidate_extension_evidence.v1"
    request = _lifecycle_request_payload(evidence)
    _write_bound_candidate_evidence(tmp_path, task_package, evidence, request)
    request_path = tmp_path / "request.json"
    request_path.write_bytes(task_package.canonical_json_bytes(request))

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_lifecycle_probe_request(request_path)

    assert caught.value.code == "task_package_schema_invalid"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "pretty",
        "bad-scalar",
        "unsafe-path",
        "dot-path",
        "internal-dot-path",
        "asset-digest",
        "asset-order",
        "recipe-version",
        "recipe-message",
        "locator",
    ],
)
def test_seed_loader_rejects_noncanonical_drift_before_git_materialization(
    tmp_path: Path,
    mutation: str,
) -> None:
    task_package = _task_package_module()
    payload = json.loads(TASK_SEED_MANIFEST_PATH.read_bytes())
    if mutation == "missing":
        payload.pop("policies")
    elif mutation == "extra":
        payload["unexpected"] = None
    elif mutation == "bad-scalar":
        payload["recipe"]["message_bytes"] = "222"
    elif mutation == "unsafe-path":
        payload["visible_assets"]["rows"][0]["source_path"] = "../escape.json"
    elif mutation == "dot-path":
        payload["visible_assets"]["rows"][0]["source_path"] = "."
    elif mutation == "internal-dot-path":
        payload["visible_assets"]["rows"][0]["source_path"] = (
            "experiments/orc_effectiveness/./f1_es/task/"
            "candidate-extension-evidence.schema.json"
        )
    elif mutation == "asset-digest":
        payload["visible_assets"]["rows"][0]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "asset-order":
        payload["visible_assets"]["rows"].reverse()
    elif mutation == "recipe-version":
        payload["recipe"]["policy"] = "es-f1-task-seed.v2"
    elif mutation == "recipe-message":
        payload["recipe"]["message"] = payload["recipe"]["message"].replace(
            "deterministic", "changed"
        )
    elif mutation == "locator":
        payload["repository"]["relative_path"] = (
            "git-sha1/" + "0" * 40
        )
    if mutation == "duplicate":
        raw = TASK_SEED_MANIFEST_PATH.read_bytes().replace(
            b'{"actual_e1":',
            b'{"schema_version":"es_f1_task_seed.v1","schema_version":"es_f1_task_seed.v1","actual_e1":',
            1,
        )
    elif mutation == "pretty":
        raw = json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
    else:
        raw = task_package.canonical_json_bytes(payload)
    candidate = tmp_path / "task-seed-manifest.json"
    candidate.write_bytes(raw)
    candidate.with_name("task-seed-manifest.schema.json").write_bytes(
        (F1_ROOT / "task-seed-manifest.schema.json").read_bytes()
    )

    with pytest.raises(task_package.TaskPackageError):
        task_package.load_task_seed_manifest(candidate)


def test_seed_loader_rejects_self_consistent_controller_only_overlay_rows(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    manifest = task_package.load_task_seed_manifest(TASK_SEED_MANIFEST_PATH)
    payload = json.loads(TASK_SEED_MANIFEST_PATH.read_bytes())
    controller_sources = (
        ROOT / "scripts/experiments/es/f1_evaluator.py",
        F1_ROOT / "evaluator/fixture-manifest.json",
        F1_ROOT / "evaluator/reviewer-perspectives.json",
    )
    assert all(path.is_file() for path in controller_sources)
    rows = list(payload["visible_assets"]["rows"])
    for source in controller_sources:
        asset_bytes = source.read_bytes()
        rows.append(
            {
                "bytes": len(asset_bytes),
                "mode": "100644",
                "object_type": "blob",
                "oid": hashlib.sha1(
                    f"blob {len(asset_bytes)}".encode() + b"\0" + asset_bytes
                ).hexdigest(),
                "sha256": "sha256:" + hashlib.sha256(asset_bytes).hexdigest(),
                "source_path": source.relative_to(ROOT).as_posix(),
                "target_path": f"benchmark/es_f1/{source.name}",
            }
        )
    rows.sort(key=lambda row: (row["source_path"], row["target_path"]))
    rows_digest = "sha256:" + hashlib.sha256(
        task_package.canonical_json_bytes(rows)
    ).hexdigest()
    scratch_parent = (tmp_path / "parent.git").resolve()
    shutil.copytree(manifest.parent_locator, scratch_parent, symlinks=True)
    index_path = tmp_path / "controller-overlay.index"
    environment = os.environ.copy()
    environment["GIT_INDEX_FILE"] = str(index_path)
    subprocess.run(
        ("git", "-C", str(scratch_parent), "read-tree", manifest.parent_commit),
        check=True,
        env=environment,
    )
    for row in rows:
        subprocess.run(
            (
                "git",
                "-C",
                str(scratch_parent),
                "update-index",
                "--add",
                "--cacheinfo",
                f"100644,{row['oid']},{row['target_path']}",
            ),
            check=True,
            env=environment,
        )
    tree = subprocess.run(
        (
            "git",
            "-C",
            str(scratch_parent),
            "write-tree",
            "--missing-ok",
        ),
        check=True,
        env=environment,
        stdout=subprocess.PIPE,
    ).stdout.decode().strip()
    message = (
        "E-series F1 deterministic task seed\n\n"
        f"Projection-Commit: {manifest.parent_commit}\n"
        f"Visible-Assets-SHA256: {rows_digest.removeprefix('sha256:')}\n"
        "Task-Seed-Policy: es-f1-task-seed.v1\n"
    ).encode()
    recipe = payload["recipe"]
    author = recipe["author"]
    identity = (
        f"{author['name']} <{author['email']}> "
        f"{author['timestamp']} {author['timezone']}"
    )
    content = (
        f"tree {tree}\nparent {manifest.parent_commit}\n"
        f"author {identity}\ncommitter {identity}\n\n"
    ).encode() + message
    commit = hashlib.sha1(
        f"commit {len(content)}".encode() + b"\0" + content
    ).hexdigest()
    payload["visible_assets"] = {
        "row_count": len(rows),
        "rows": rows,
        "serialization": "canonical-json-lf.v1",
        "sha256": rows_digest,
    }
    payload["recipe"].update(
        {
            "commit": commit,
            "commit_content_bytes": len(content),
            "commit_content_sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "message": message.decode(),
            "message_bytes": len(message),
            "message_sha256": "sha256:" + hashlib.sha256(message).hexdigest(),
            "tree": tree,
        }
    )
    payload["repository"].update(
        {
            "locator": (
                "/home/ollie/.local/state/orchestrator/es-task-seeds/git-sha1/"
                + commit
            ),
            "object_count": 2_219,
            "relative_path": "git-sha1/" + commit,
        }
    )
    payload["actual_e1"].update(
        {
            "post_setup_tree_manifest_sha256": "sha256:" + "0" * 64,
            "resolved_commit": commit,
            "source_tree_manifest_sha256": "sha256:" + "0" * 64,
            "verified_git_tree": "git-tree:" + tree,
        }
    )
    candidate = tmp_path / "task-seed-manifest.json"
    candidate.write_bytes(task_package.canonical_json_bytes(payload))
    candidate.with_name("task-seed-manifest.schema.json").write_bytes(
        (F1_ROOT / "task-seed-manifest.schema.json").read_bytes()
    )

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_task_seed_manifest(candidate)

    assert caught.value.code == "task_seed_asset_allowlist_mismatch"


def _git(repository: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ("git", "-C", str(repository), *args),
        check=True,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def test_task_seed_creation_is_parent_preserving_and_actual_e1_materializes_child(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    manifest = task_package.load_task_seed_manifest(TASK_SEED_MANIFEST_PATH)
    parent_before = task_package.directory_snapshot_digest(manifest.parent_locator)

    created = task_package.materialize_task_seed(
        manifest,
        storage_root=(tmp_path / "task-seeds").resolve(),
    )
    verified = task_package.verify_task_seed(created.locator, manifest)

    assert created.reused is False
    assert verified.commit == manifest.commit
    assert verified.tree == manifest.tree
    assert verified.parent_commit == manifest.parent_commit
    assert verified.commit_count == 2
    assert verified.object_count == manifest.object_count
    assert verified.unreachable_object_count == 0
    assert task_package.directory_snapshot_digest(manifest.parent_locator) == parent_before
    assert parent_before == manifest.parent_snapshot_digest
    assert task_package.materialize_task_seed(
        manifest,
        storage_root=(tmp_path / "task-seeds").resolve(),
    ).reused is True

    from orchestrator.workflow.run_ref.source import SourceRequest, materialize_source

    materialized = materialize_source(
        SourceRequest(locator=str(created.locator), commit=manifest.commit),
        run_ref_root=(tmp_path / "run-ref").resolve(),
        workspace=(tmp_path / "workspace").resolve(),
    )
    assert materialized.resolved_commit_sha == manifest.commit
    assert materialized.verified_git_tree.value == f"git-tree:{manifest.tree}"
    assert materialized.source_tree_manifest.digest == manifest.e1_source_manifest_digest
    assert (
        materialized.post_setup_tree_manifest.digest
        == manifest.e1_post_setup_manifest_digest
    )
    for row in manifest.visible_assets:
        assert (materialized.workspace_path / row.target_path).read_bytes() == (
            _git(manifest.locator, "show", f"{manifest.commit}:{row.target_path}")
        )


def test_checked_in_seed_repository_has_closed_history_and_object_storage() -> None:
    task_package = _task_package_module()
    manifest = task_package.load_task_seed_manifest(TASK_SEED_MANIFEST_PATH)

    verified = task_package.verify_task_seed(manifest.locator, manifest)

    assert verified.commit == manifest.commit
    assert task_package.directory_snapshot_digest(manifest.locator) == (
        manifest.repository_snapshot_digest
    )
    assert _git(manifest.locator, "remote") == b""
    assert _git(manifest.locator, "diff-tree", "--no-commit-id", "--name-only", "-r", manifest.commit).splitlines() == [
        row.target_path.encode() for row in manifest.visible_assets
    ]


def test_git_subprocesses_ignore_inherited_repository_and_config_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_package = _task_package_module()
    manifest = task_package.load_task_seed_manifest(TASK_SEED_MANIFEST_PATH)
    poisoned = {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(manifest.parent_locator / "objects"),
        "GIT_OBJECT_DIRECTORY": str(tmp_path / "objects"),
        "GIT_COMMON_DIR": str(tmp_path / "common"),
        "GIT_DIR": str(tmp_path / "wrong.git"),
        "GIT_WORK_TREE": str(tmp_path / "wrong-worktree"),
        "GIT_INDEX_FILE": str(tmp_path / "ambient.index"),
        "GIT_REPLACE_REF_BASE": "refs/replace/injected",
        "GIT_SHALLOW_FILE": str(tmp_path / "shallow"),
        "GIT_CEILING_DIRECTORIES": str(tmp_path),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.repositoryformatversion",
        "GIT_CONFIG_VALUE_0": "99",
        "GIT_CONFIG_PARAMETERS": "'core.repositoryformatversion'='99'",
    }
    for name, value in poisoned.items():
        monkeypatch.setenv(name, value)

    verified = task_package.verify_task_seed(manifest.locator, manifest)
    created = task_package.materialize_task_seed(
        manifest,
        storage_root=(tmp_path / "sanitized-seeds").resolve(),
    )

    assert verified.object_count == manifest.object_count
    assert created.commit == manifest.commit
    assert created.reused is False


def test_task_seed_materialization_propagates_parent_projection_verifier_failure(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    task_package = _task_package_module()
    manifest = task_package.load_task_seed_manifest(TASK_SEED_MANIFEST_PATH)
    parent = (tmp_path / "corrupt-parent.git").resolve()
    shutil.copytree(manifest.parent_locator, parent, symlinks=True)
    _git(parent, "update-ref", "refs/heads/unexpected", manifest.parent_commit)
    corrupted = replace(
        manifest,
        parent_locator=parent,
        parent_snapshot_digest=task_package.directory_snapshot_digest(parent),
    )

    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.materialize_task_seed(
            corrupted,
            storage_root=(tmp_path / "task-seeds").resolve(),
        )

    assert caught.value.code == "task_seed_parent_verification_failed"


def test_inherited_alternate_cannot_supply_missing_seed_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_package = _task_package_module()
    manifest = task_package.load_task_seed_manifest(TASK_SEED_MANIFEST_PATH)
    with tempfile.TemporaryDirectory(
        prefix=".pytest-missing-pack-", dir=manifest.locator.parent
    ) as temporary:
        candidate = (Path(temporary) / "seed.git").resolve()
        shutil.copytree(manifest.locator, candidate, copy_function=os.link, symlinks=True)
        for pack_path in (candidate / "objects" / "pack").iterdir():
            pack_path.unlink()
        monkeypatch.setenv(
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            str(manifest.parent_locator / "objects"),
        )

        with pytest.raises(task_package.TaskPackageError) as caught:
            task_package.verify_task_seed(candidate, manifest)

        assert caught.value.code == "task_seed_git_failed"


@pytest.mark.parametrize("mutation", ["extra-ref", "unreachable-object", "alternates"])
def test_seed_verifier_rejects_extra_identity_and_object_sources(
    tmp_path: Path,
    mutation: str,
) -> None:
    del tmp_path
    task_package = _task_package_module()
    manifest = task_package.load_task_seed_manifest(TASK_SEED_MANIFEST_PATH)
    with tempfile.TemporaryDirectory(
        prefix=f".pytest-{mutation}-", dir=manifest.locator.parent
    ) as temporary:
        candidate = (Path(temporary) / "seed.git").resolve()
        shutil.copytree(manifest.locator, candidate, copy_function=os.link, symlinks=True)
        if mutation == "extra-ref":
            _git(candidate, "update-ref", "refs/heads/extra", manifest.parent_commit)
        elif mutation == "unreachable-object":
            _git(candidate, "hash-object", "-w", "--stdin", input_bytes=b"unreachable\n")
        else:
            alternates = candidate / "objects" / "info" / "alternates"
            alternates.write_text(str(manifest.parent_locator / "objects") + "\n")

        with pytest.raises(task_package.TaskPackageError):
            task_package.verify_task_seed(candidate, manifest)
