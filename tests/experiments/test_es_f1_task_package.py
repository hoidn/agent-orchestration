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
    assert len(profile.focused_selectors) == 10
    assert profile.environment_name == "ptycho311"
    assert profile.claim_limit_ids


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
    assert checks.timeout_seconds == 1_200


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
        "seed-digest-drift",
        "brief-digest-drift",
        "visible-schema-digest-drift",
        "visible-check-digest-drift",
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
    elif mutation == "seed-digest-drift":
        payload["task_seed"]["manifest_sha256"] = "sha256:" + "0" * 64
    elif mutation == "brief-digest-drift":
        payload["neutral_brief"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "visible-schema-digest-drift":
        payload["visible_schema_bindings"][0]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "visible-check-digest-drift":
        payload["visible_check"]["sha256"] = "sha256:" + "0" * 64
    elif mutation == "review-dimension-drift":
        payload["review_dimension_ids"][0] = "SUBSTITUTE_DIMENSION"
    elif mutation == "version-drift":
        payload["schema_version"] = "es_f1_task_profile.v2"
    candidate = F1_ROOT / "task-profile.json"
    schema = F1_ROOT / "task-profile.schema.json"
    if mutation == "duplicate":
        raw = TASK_PROFILE_PATH.read_bytes().replace(
            b'{"candidate_declared_output_ids":',
            b'{"task_id":"F1","task_id":"F1","candidate_declared_output_ids":',
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
    return {
        "architecture_decision_path": "docs/adr/es-f1-boundary.md",
        "candidate_id": "candidate-a",
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
        "representative_architecture": {
            "construction_route": "ptycho.torch.models.resolve_generator",
            "frozen_registry_member": True,
            "persisted_rebuild_route": "ptycho.torch.build_ptychopinn_application",
            "public_id": "unet",
        },
        "schema_version": "candidate_extension_evidence.v1",
        "structural_fields": [
            {"alternate_value": 3, "baseline_value": 2, "name": "depth"}
        ],
        "supported_artifact_eras": ["torch-artifact-v1", "torch-artifact-v2"],
        "witness_architecture": {
            "construction_route": "ptycho.torch.models.resolve_generator",
            "frozen_registry_member": False,
            "persisted_rebuild_route": "ptycho.torch.build_ptychopinn_application",
            "public_id": "es_f1_witness",
        },
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


def _lifecycle_request_payload() -> dict[str, object]:
    return {
        "candidate_evidence_path": "es_f1_candidate_evidence.json",
        "candidate_evidence_sha256": "sha256:" + "a" * 64,
        "candidate_id": "candidate-a",
        "evaluator_inputs": {
            "base_config": {
                "path": "inputs/base-config.json",
                "sha256": "sha256:" + "b" * 64,
            },
            "cdi_fixture": {
                "path": "inputs/cdi-fixture.npz",
                "sha256": "sha256:" + "c" * 64,
            },
        },
        "lifecycle_output_dir": ".es-f1/lifecycle",
        "operation_version": "ptychopinn_public_lifecycle.v1",
        "representative_architecture": "unet",
        "schema_version": "lifecycle_probe_request.v2",
        "seed": 1729,
        "witness_architecture": "es_f1_witness",
    }


def _lifecycle_result_payload() -> dict[str, object]:
    return {
        "artifacts": {
            "representative": {
                "bundle_path": "representative/bundle.json",
                "checkpoint_path": "representative/checkpoint.ckpt",
            },
            "witness": {
                "bundle_path": "witness/bundle.json",
                "checkpoint_path": "witness/checkpoint.ckpt",
            },
        },
        "candidate_id": "candidate-a",
        "operation_version": "ptychopinn_public_lifecycle.v1",
        "schema_version": "lifecycle_probe_result.v2",
    }


def test_lifecycle_loaders_accept_only_bound_inputs_and_artifact_paths(
    tmp_path: Path,
) -> None:
    task_package = _task_package_module()
    request = _lifecycle_request_payload()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(task_package.canonical_json_bytes(request))
    loaded_request = task_package.load_lifecycle_probe_request(request_path)
    assert loaded_request["seed"] == 1729
    assert loaded_request["operation_version"] == "ptychopinn_public_lifecycle.v1"
    assert loaded_request["evaluator_inputs"] == request["evaluator_inputs"]

    result = _lifecycle_result_payload()
    result_path = tmp_path / "result.json"
    result_path.write_bytes(task_package.canonical_json_bytes(result))
    loaded_result = task_package.load_lifecycle_probe_result(result_path)
    assert "passed" not in loaded_result
    assert "representative_observation" not in loaded_result
    assert loaded_result["artifacts"] == result["artifacts"]


@pytest.mark.parametrize(
    ("record_kind", "bad_path"),
    [
        ("evidence", "."),
        ("evidence", "docs/./boundary.md"),
        ("request", "."),
        ("request", ".es-f1/./lifecycle"),
        ("result", "."),
        ("result", ".es-f1/./checkpoint.ckpt"),
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
    request = _lifecycle_request_payload()
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
        artifacts = cast(dict[str, dict[str, str]], result["artifacts"])
        artifacts["representative"]["checkpoint_path"] = bad_path
        payload = result
        loader = task_package.load_lifecycle_probe_result
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
    structural_fields = cast(list[dict[str, object]], payload["structural_fields"])
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
        ("request", "same-architecture"),
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
    request = _lifecycle_request_payload()
    result = _lifecycle_result_payload()
    payload = {"evidence": evidence, "request": request, "result": result}[record_kind]
    if mutation == "extra" or mutation == "pass-bit":
        payload["passed"] = True
    elif mutation == "version":
        payload["schema_version"] = "candidate_extension_evidence.v2"
    elif mutation == "unsafe-path":
        payload["architecture_decision_path"] = "../escape.md"
    elif mutation == "duplicate-claim":
        claims = cast(list[object], payload["claims"])
        claims[-1] = claims[0]
    elif mutation == "bad-scalar":
        payload["seed"] = True
    elif mutation == "same-architecture":
        payload["witness_architecture"] = payload["representative_architecture"]
    elif mutation == "missing-input-digest":
        evaluator_inputs = cast(dict[str, dict[str, str]], payload["evaluator_inputs"])
        evaluator_inputs["base_config"].pop("sha256")
    elif mutation == "operation-version":
        payload["operation_version"] = "candidate_defined.v1"
    elif mutation == "candidate-observation":
        payload["representative_observation"] = {"candidate_claimed": True}
    elif mutation == "old-version":
        payload["schema_version"] = "lifecycle_probe_result.v1"
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
        "result": task_package.load_lifecycle_probe_result,
    }[record_kind]

    with pytest.raises(task_package.TaskPackageError):
        loader(path)


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
            ROOT / row.source_path
        ).read_bytes()


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
