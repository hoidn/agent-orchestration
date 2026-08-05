from __future__ import annotations

import ast
import copy
import json
import hashlib
import importlib
import inspect
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.experiments.es import task_package

EVALUATOR_ASSETS = REPO / "experiments/orc_effectiveness/f1_es/evaluator"
CALIBRATION_FIXTURES = REPO / "tests/experiments/fixtures/es_f1"
TASK_ASSETS = REPO / "experiments/orc_effectiveness/f1_es/task"
CALIBRATION_CASES = json.loads(
    (CALIBRATION_FIXTURES / "calibration-cases.json").read_bytes()
)["cases"]


def _evaluator():
    return importlib.import_module("scripts.experiments.es.f1_evaluator")


def test_calibration_bundle_workflow_forwards_validated_override_mapping() -> None:
    tree = ast.parse(
        (CALIBRATION_FIXTURES / "conforming_lifecycle_adapter.py").read_text()
    )
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_cdi_example_torch"
    ]
    assert len(calls) == 1
    overrides = [
        keyword.value for keyword in calls[0].keywords if keyword.arg == "overrides"
    ]
    assert len(overrides) == 1
    assert isinstance(overrides[0], ast.Name)
    assert overrides[0].id == "bundle_overrides"


def test_frozen_controller_vocabularies_and_assets_are_closed() -> None:
    evaluator = _evaluator()
    assert evaluator.HARD_CLAUSE_IDS == (
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
    assert evaluator.DISPOSITIONS == (
        "PRODUCT_DEFECT",
        "ORACLE_DEFECT",
        "SPEC_AMBIGUITY",
        "INFRASTRUCTURE",
        "UNRESOLVED",
    )
    assert evaluator.REVIEWER_PERSPECTIVES == (
        "SCIENTIFIC_APPLICATION_SEMANTICS",
        "API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    )
    visible_contract = json.loads(
        (
            REPO
            / "experiments/orc_effectiveness/f1_es/task/visible-task-contract.json"
        ).read_bytes()
    )
    assert evaluator.HARD_CLAUSE_IDS == tuple(
        row["id"] for row in visible_contract["hard_contract"]
    )
    assert evaluator.DISPOSITIONS == tuple(visible_contract["finding_dispositions"])
    assert evaluator.REVIEWER_PERSPECTIVES == tuple(
        row["id"] for row in visible_contract["reviewer_perspectives"]
    )

    fixture_manifest = evaluator.load_controller_asset(
        EVALUATOR_ASSETS / "fixture-manifest.json",
        expected_schema_version="es-f1-fixture-manifest.v2",
    )
    assert fixture_manifest["hard_clause_ids"] == list(evaluator.HARD_CLAUSE_IDS)
    assert fixture_manifest["artifact_fixture_origin"] == {
        "generator": "scripts.experiments.es.f1_evaluator.build_artifact_fixture_pack",
        "source_projection_commit": "8f191031f233d50a4d020d8a988036e99487f570",
        "source_projection_tree": "e64f3c05f5a0894f41c047d128a9040a2cda6764",
    }
    calibration_binding = fixture_manifest["calibration_cases"]
    assert calibration_binding == {
        "path": "tests/experiments/fixtures/es_f1/calibration-cases.json",
        "schema_version": "es-f1-calibration-cases.v3",
        "sha256": "sha256:"
        + hashlib.sha256(
            (CALIBRATION_FIXTURES / "calibration-cases.json").read_bytes()
        ).hexdigest(),
    }
    assert len(fixture_manifest["registry_baseline"]) == 14
    assert {row["architecture"] for row in fixture_manifest["registry_baseline"]} == {
        "cnn",
        "ffno",
        "fno",
        "hybrid",
        "stable_hybrid",
        "fno_vanilla",
        "neuralop_uno",
        "hybrid_resnet",
        "hybrid_resnet_ffno_ptychoblock_encoder",
        "hybrid_resnet_ptychoblock_ffno_encoder",
        "spectral_resnet_bottleneck_net",
        "spectral_resnet_bottleneck_linear_decoder",
        "hybrid_resnet_ffno_bottleneck",
        "hybrid_resnet_convnext_bottleneck",
    }
    assert [
        row["N"] for row in fixture_manifest["registry_baseline"]
        if row["architecture"] == "neuralop_uno"
    ] == [128]
    assert all(
        row["N"] == 64
        for row in fixture_manifest["registry_baseline"]
        if row["architecture"] != "neuralop_uno"
    )
    applicability_domain = [
        *task_package.F1_BUILTIN_ARCHITECTURES,
        "$candidate_witness",
    ]
    ffno_eras = {
        "torch-model-spec-v1",
        "torch-model-spec-v2",
        "torch-artifact-v1",
        "torch-artifact-v2",
        "legacy-config-only-checkpoint",
        "current-model-spec-v2-checkpoint",
        "transitional-ci-entrypoints-v1-bundle",
        "torch-artifact-v1-bundle",
        "torch-artifact-v2-bundle",
    }
    for row in fixture_manifest["artifact_eras"]:
        applicable = [
            "cnn" if row["era_id"] == "metadata-free-legacy-bundle" else "ffno"
        ]
        assert row["applicable_architecture_ids"] == applicable
        assert row["rejected_architecture_ids"] == [
            architecture_id
            for architecture_id in applicability_domain
            if architecture_id not in applicable
        ]
        assert (
            row["era_id"] in ffno_eras
        ) == (applicable == ["ffno"])

    perspectives = evaluator.load_controller_asset(
        EVALUATOR_ASSETS / "reviewer-perspectives.json",
        expected_schema_version="es-f1-reviewer-perspectives.v1",
    )
    assert tuple(row["perspective_id"] for row in perspectives["perspectives"]) == (
        evaluator.REVIEWER_PERSPECTIVES
    )
    assert perspectives["perspectives"] == [
        {
            "owned_dimensions": row["owned_dimensions"],
            "perspective_id": row["id"],
            "responsibility": row["responsibility"],
        }
        for row in visible_contract["reviewer_perspectives"]
    ]
    assert set().union(
        *(set(row["owned_dimensions"]) for row in perspectives["perspectives"])
    ) == set(visible_contract["review_dimensions"])
    assert sum(
        len(row["owned_dimensions"]) for row in perspectives["perspectives"]
    ) == len(visible_contract["review_dimensions"])

    package = evaluator.load_frozen_evaluator_package(
        visible_contract_path=TASK_ASSETS / "visible-task-contract.json",
        visible_contract_schema_path=TASK_ASSETS / "visible-task-contract.schema.json",
        visible_check_path=TASK_ASSETS / "visible-check-manifest.json",
        visible_check_schema_path=TASK_ASSETS / "visible-check-manifest.schema.json",
        fixture_manifest_path=EVALUATOR_ASSETS / "fixture-manifest.json",
        reviewer_perspectives_path=EVALUATOR_ASSETS / "reviewer-perspectives.json",
    )
    assert package["visible_contract"] == visible_contract
    assert package["visible_checks"]["invocation_order"] == [
        "PRE_EDIT_FOCUSED",
        "CANDIDATE_EXTENSION",
    ]
    assert package["visible_checks"]["invocations"][0]["selectors"] == (
        visible_contract["focused_selectors"]
    )
    assert package["visible_checks"]["invocations"][1]["selectors"] == [
        "tests/torch/test_es_f1_extension_boundary.py"
    ]
    assert evaluator.F1_BUILTIN_ARCHITECTURES is task_package.F1_BUILTIN_ARCHITECTURES
    assert evaluator.HARD_CLAUSE_IDS is task_package.F1_HARD_CLAUSE_IDS


@pytest.mark.parametrize(
    "mutation",
    (
        "incomplete-partition",
        "overlapping-partition",
        "legacy-non-cnn-positive",
        "missing-historical-rejection",
    ),
)
def test_fixture_manifest_artifact_applicability_partitions_fail_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    evaluator = _evaluator()
    fixture = json.loads((EVALUATOR_ASSETS / "fixture-manifest.json").read_bytes())
    first = fixture["artifact_eras"][0]
    legacy = next(
        row for row in fixture["artifact_eras"]
        if row["era_id"] == "metadata-free-legacy-bundle"
    )
    if mutation == "incomplete-partition":
        first["rejected_architecture_ids"].pop()
    elif mutation == "overlapping-partition":
        first["rejected_architecture_ids"].insert(1, "ffno")
    elif mutation == "legacy-non-cnn-positive":
        legacy["applicable_architecture_ids"] = ["cnn", "ffno"]
        legacy["rejected_architecture_ids"].remove("ffno")
    else:
        first["rejected_architecture_ids"].remove("cnn")
    fixture_path = tmp_path / "fixture-manifest.json"
    fixture_path.write_bytes(evaluator.canonical_json_bytes(fixture))

    with pytest.raises(evaluator.EvaluatorError, match="artifact applicability"):
        evaluator.load_frozen_evaluator_package(
            visible_contract_path=TASK_ASSETS / "visible-task-contract.json",
            visible_contract_schema_path=(
                TASK_ASSETS / "visible-task-contract.schema.json"
            ),
            visible_check_path=TASK_ASSETS / "visible-check-manifest.json",
            visible_check_schema_path=TASK_ASSETS / "visible-check-manifest.schema.json",
            fixture_manifest_path=fixture_path,
            reviewer_perspectives_path=(
                EVALUATOR_ASSETS / "reviewer-perspectives.json"
            ),
        )


def test_artifact_applicability_resolves_to_exact_10_by_15_preflight_matrix(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    fixture = json.loads((EVALUATOR_ASSETS / "fixture-manifest.json").read_bytes())
    evidence_path = tmp_path / "es_f1_candidate_evidence.json"
    evidence_path.write_bytes(evaluator.canonical_json_bytes(_candidate_claims()))

    resolved = evaluator.resolve_artifact_applicability(
        fixture_manifest=fixture,
        candidate_evidence_path=evidence_path,
    )

    domain = [*task_package.F1_BUILTIN_ARCHITECTURES, "es_f1_witness"]
    assert len(resolved) == 10
    assert all("$candidate_witness" not in row["rejected_architecture_ids"] for row in resolved)
    outcomes = []
    for row in resolved:
        assert set(row["applicable_architecture_ids"]) | set(
            row["rejected_architecture_ids"]
        ) == set(domain)
        assert not set(row["applicable_architecture_ids"]) & set(
            row["rejected_architecture_ids"]
        )
        for architecture_id in domain:
            preflight = evaluator.preflight_artifact_architecture(
                artifact_row=row,
                architecture_id=architecture_id,
            )
            outcomes.append((row["era_id"], architecture_id, preflight))
            if architecture_id in row["applicable_architecture_ids"]:
                assert preflight is None
            else:
                assert preflight == {
                    "diagnostic": "UNSUPPORTED_ARTIFACT_ARCHITECTURE",
                    "implementation_identity": None,
                    "module_returned": False,
                    "strict_load": False,
                }
    assert len(outcomes) == 150
    assert sum(preflight is None for _, _, preflight in outcomes) == 10
    assert sum(preflight is not None for _, _, preflight in outcomes) == 140

    invalid_evidence = _candidate_claims()
    invalid_evidence["artifact_applicability"] = []
    evidence_path.write_bytes(evaluator.canonical_json_bytes(invalid_evidence))
    with pytest.raises(evaluator.EvaluatorError, match="candidate evidence"):
        evaluator.resolve_artifact_applicability(
            fixture_manifest=fixture,
            candidate_evidence_path=evidence_path,
        )


@pytest.mark.parametrize(
    ("fixture_version", "calibration_version"),
    [
        ("es-f1-fixture-manifest.v1", "es-f1-calibration-cases.v3"),
        ("es-f1-fixture-manifest.v999", "es-f1-calibration-cases.v3"),
        ("es-f1-fixture-manifest.v2", "es-f1-calibration-cases.v2"),
        ("es-f1-fixture-manifest.v2", "es-f1-calibration-cases.v999"),
    ],
)
def test_evaluator_package_rejects_predecessor_unknown_and_mixed_versions_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture_version: str,
    calibration_version: str,
) -> None:
    evaluator = _evaluator()
    fixture = json.loads((EVALUATOR_ASSETS / "fixture-manifest.json").read_bytes())
    fixture["schema_version"] = fixture_version
    fixture["calibration_cases"]["schema_version"] = calibration_version
    fixture_path = tmp_path / "fixture-manifest.json"
    fixture_path.write_bytes(evaluator.canonical_json_bytes(fixture))

    def forbidden_execution(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("package preflight reached candidate execution")

    monkeypatch.setattr(evaluator.subprocess, "run", forbidden_execution)
    with pytest.raises(evaluator.EvaluatorError):
        evaluator.load_frozen_evaluator_package(
            visible_contract_path=TASK_ASSETS / "visible-task-contract.json",
            visible_contract_schema_path=(
                TASK_ASSETS / "visible-task-contract.schema.json"
            ),
            visible_check_path=TASK_ASSETS / "visible-check-manifest.json",
            visible_check_schema_path=(
                TASK_ASSETS / "visible-check-manifest.schema.json"
            ),
            fixture_manifest_path=fixture_path,
            reviewer_perspectives_path=(
                EVALUATOR_ASSETS / "reviewer-perspectives.json"
            ),
        )


@pytest.mark.parametrize("mutation", ("missing-row", "reordered-row"))
def test_evaluator_package_rejects_incomplete_or_reordered_calibration_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    evaluator = _evaluator()
    calibration = json.loads(
        (CALIBRATION_FIXTURES / "calibration-cases.json").read_bytes()
    )
    if mutation == "missing-row":
        calibration["cases"].pop()
    else:
        calibration["cases"][0], calibration["cases"][1] = (
            calibration["cases"][1],
            calibration["cases"][0],
        )
    calibration_path = (
        tmp_path / "tests/experiments/fixtures/es_f1/calibration-cases.json"
    )
    calibration_path.parent.mkdir(parents=True)
    calibration_path.write_bytes(evaluator.canonical_json_bytes(calibration))

    fixture = json.loads((EVALUATOR_ASSETS / "fixture-manifest.json").read_bytes())
    fixture["calibration_cases"]["sha256"] = (
        "sha256:" + hashlib.sha256(calibration_path.read_bytes()).hexdigest()
    )
    fixture_path = tmp_path / "fixture-manifest.json"
    fixture_path.write_bytes(evaluator.canonical_json_bytes(fixture))
    monkeypatch.setattr(evaluator, "_REPOSITORY_ROOT", tmp_path)

    with pytest.raises(evaluator.EvaluatorError, match="calibration fixture"):
        evaluator.load_frozen_evaluator_package(
            visible_contract_path=TASK_ASSETS / "visible-task-contract.json",
            visible_contract_schema_path=(
                TASK_ASSETS / "visible-task-contract.schema.json"
            ),
            visible_check_path=TASK_ASSETS / "visible-check-manifest.json",
            visible_check_schema_path=(
                TASK_ASSETS / "visible-check-manifest.schema.json"
            ),
            fixture_manifest_path=fixture_path,
            reviewer_perspectives_path=(
                EVALUATOR_ASSETS / "reviewer-perspectives.json"
            ),
        )


@pytest.mark.parametrize(
    ("record_type", "predecessor", "successor"),
    (
        (
            "visible-check-result",
            "es-f1-visible-check-result.v1",
            "es-f1-visible-check-result.v2",
        ),
        (
            "preedit-lifecycle-probe",
            "es-f1-preedit-lifecycle-probe.v1",
            "es-f1-preedit-lifecycle-probe.v2",
        ),
        (
            "semantic-lifecycle",
            "es-f1-semantic-lifecycle.v1",
            "es-f1-semantic-lifecycle.v2",
        ),
        (
            "semantic-lifecycle-failure",
            "es-f1-semantic-lifecycle-failure.v1",
            "es-f1-semantic-lifecycle-failure.v2",
        ),
        (
            "artifact-fixture-input",
            "es-f1-artifact-fixture-input.v1",
            "es-f1-artifact-fixture-input.v2",
        ),
        (
            "artifact-fixture-build",
            "es-f1-artifact-fixture-build.v1",
            "es-f1-artifact-fixture-build.v2",
        ),
        (
            "artifact-fixture-verification",
            "es-f1-artifact-fixture-verification.v1",
            "es-f1-artifact-fixture-verification.v2",
        ),
    ),
)
def test_remaining_evaluator_successor_record_versions_fail_closed(
    record_type: str,
    predecessor: str,
    successor: str,
) -> None:
    evaluator = _evaluator()
    assert evaluator.EVALUATOR_SUCCESSOR_SCHEMA_VERSIONS[record_type] == (
        predecessor,
        successor,
    )
    record = {"schema_version": successor}
    assert (
        evaluator.require_evaluator_successor_schema(
            record,
            record_type=record_type,
        )
        is record
    )
    for rejected in (predecessor, f"{successor}.unknown"):
        with pytest.raises(evaluator.EvaluatorError, match="schema version"):
            evaluator.require_evaluator_successor_schema(
                {"schema_version": rejected},
                record_type=record_type,
            )


@pytest.mark.parametrize(
    ("result_key", "predecessor"),
    (
        ("visible_check_result", "es-f1-visible-check-result.v1"),
        ("artifact_report", "es-f1-artifact-fixture-verification.v1"),
    ),
)
def test_complete_observation_consumers_reject_predecessor_result_versions(
    tmp_path: Path,
    result_key: str,
    predecessor: str,
) -> None:
    evaluator = _evaluator()
    inputs = _synthetic_complete_observation_inputs(tmp_path)
    inputs[result_key]["schema_version"] = predecessor
    with pytest.raises(evaluator.EvaluatorError, match="schema version"):
        evaluator.derive_complete_observations(**inputs)


def test_lifecycle_observation_consumer_rejects_predecessor_semantic_version() -> None:
    evaluator = _evaluator()
    report = _synthetic_full_matrix_semantic_report()
    report["schema_version"] = "es-f1-semantic-lifecycle.v1"
    with pytest.raises(evaluator.EvaluatorError, match="schema version"):
        evaluator.derive_lifecycle_observations(
            semantic_report=report,
            adapter_process_id=98,
        )


def test_semantic_failure_parser_rejects_predecessor_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator()
    workspace = tmp_path / "candidate"
    workspace.mkdir()

    def emit_predecessor_report(**kwargs: Any) -> None:
        Path(kwargs["environment"]["ES_F1_REPORT"]).write_bytes(
            evaluator.canonical_json_bytes(
                {
                    "schema_version": "es-f1-semantic-lifecycle-failure.v1",
                    "stage": "PUBLIC_BUILD",
                    "exception_type": "RuntimeError",
                    "exception_detail_sha256": f"sha256:{1:064x}",
                }
            )
        )

    monkeypatch.setattr(evaluator, "_run_projection_probe", emit_predecessor_report)
    with pytest.raises(evaluator.EvaluatorError, match="schema version"):
        evaluator._run_semantic_lifecycle_probe(
            workspace=workspace,
            python_executable=Path(sys.executable),
            candidate_evidence=workspace / "unused-evidence.json",
            request_path=workspace / "unused-request.json",
            architecture_cases=[],
            adapter_observations={},
            output_root=tmp_path / "semantic-output",
            seed=1,
            timeout_seconds=5,
        )


def test_preedit_lifecycle_binds_fresh_reload_child_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    output_root = (tmp_path / "preedit-output").resolve()
    captured: dict[str, Any] = {}

    class ProductExecutionBlocked(Exception):
        pass

    def capture_callsite(**kwargs: Any) -> None:
        captured.update(kwargs)
        raise ProductExecutionBlocked

    monkeypatch.setattr(evaluator, "_run_projection_probe", capture_callsite)
    with pytest.raises(ProductExecutionBlocked):
        evaluator.run_preedit_representative_lifecycle_probe(
            workspace=workspace,
            python_executable=Path(sys.executable),
            output_root=output_root,
            timeout_seconds=5,
        )

    checkpoint_pair = (
        "checkpoint-reload-program.py",
        "checkpoint-reload-audit.json",
    )
    bundle_pair = ("bundle-reload-program.py", "bundle-reload-audit.json")
    assert captured["controlled_child_pairs"] == (checkpoint_pair, bundle_pair)
    assert captured["controlled_child_environment_updates"] == {
        checkpoint_pair: {
            "ES_F1_CHILD_REPORT": str(output_root / "checkpoint-reload.json"),
            "ES_F1_RELOAD_MODE": "checkpoint",
            "ES_F1_RELOAD_ARTIFACT": str(output_root / "representative.ckpt"),
            "ES_F1_FRESH_RELOAD": "1",
            "ES_F1_IMAGE_SIZE": "64",
            "ES_F1_SEED": "20260802",
        },
        bundle_pair: {
            "ES_F1_CHILD_REPORT": str(output_root / "bundle-reload.json"),
            "ES_F1_RELOAD_MODE": "bundle",
            "ES_F1_RELOAD_ARTIFACT": str(output_root / "training"),
            "ES_F1_FRESH_RELOAD": "1",
            "ES_F1_IMAGE_SIZE": "64",
            "ES_F1_SEED": "20260802",
        },
    }


def test_preedit_lifecycle_parser_rejects_predecessor_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator()
    workspace = tmp_path / "candidate"
    workspace.mkdir()

    def emit_predecessor_report(**kwargs: Any) -> None:
        Path(kwargs["environment"]["ES_F1_REPORT"]).write_bytes(
            evaluator.canonical_json_bytes(
                {"schema_version": "es-f1-preedit-lifecycle-probe.v1"}
            )
        )

    monkeypatch.setattr(evaluator, "_run_projection_probe", emit_predecessor_report)
    with pytest.raises(evaluator.EvaluatorError, match="schema version"):
        evaluator.run_preedit_representative_lifecycle_probe(
            workspace=workspace,
            python_executable=Path(sys.executable),
            output_root=tmp_path / "preedit-output",
            timeout_seconds=5,
        )


def test_artifact_build_parser_rejects_predecessor_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator()
    workspace = tmp_path / "candidate"
    workspace.mkdir()

    def emit_predecessor_report(**kwargs: Any) -> None:
        Path(kwargs["environment"]["ES_F1_REPORT"]).write_bytes(
            evaluator.canonical_json_bytes(
                {
                    "schema_version": "es-f1-artifact-fixture-build.v1",
                    "artifact_eras": [],
                }
            )
        )

    monkeypatch.setattr(evaluator, "_run_projection_probe", emit_predecessor_report)
    with pytest.raises(evaluator.EvaluatorError, match="schema version"):
        evaluator.build_artifact_fixture_pack(
            workspace=workspace,
            python_executable=Path(sys.executable),
            store_root=tmp_path / "fixture-store",
            timeout_seconds=5,
        )


@pytest.mark.parametrize(
    "rejected_version",
    ("es-f1-artifact-fixture-input.v1", "es-f1-artifact-fixture-input.v999"),
)
def test_artifact_probe_rejects_input_version_before_candidate_import(
    tmp_path: Path,
    rejected_version: str,
) -> None:
    evaluator = _evaluator()
    workspace = tmp_path / "candidate"
    marker = tmp_path / "candidate-imported"
    package = workspace / "ptycho"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n",
        encoding="utf-8",
    )
    rows_path = tmp_path / "rows.json"
    rows_path.write_bytes(
        evaluator.canonical_json_bytes(
            {"schema_version": rejected_version, "artifact_eras": []}
        )
    )
    process = subprocess.run(
        (sys.executable, "-c", evaluator._ARTIFACT_FIXTURE_VERIFY_PROBE),
        cwd=tmp_path,
        env={
            **os.environ,
            "ES_F1_FIXTURE_ROWS": str(rows_path),
            "ES_F1_REPORT": str(tmp_path / "report.json"),
            "ES_F1_WORKSPACE": str(workspace),
        },
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.returncode != 0
    assert "artifact fixture input schema version/shape mismatch" in process.stderr
    assert not marker.exists()


def test_controller_asset_loader_rejects_noncanonical_and_open_records(tmp_path: Path) -> None:
    evaluator = _evaluator()
    canonical = {
        "schema_version": "example.v1",
        "values": [1, 2],
    }
    path = tmp_path / "asset.json"
    path.write_bytes(evaluator.canonical_json_bytes(canonical))
    assert evaluator.load_controller_asset(path, expected_schema_version="example.v1") == canonical

    path.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="canonical"):
        evaluator.load_controller_asset(path, expected_schema_version="example.v1")

    path.write_text(
        '{"schema_version":"example.v1","schema_version":"example.v1","values":[1,2]}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        evaluator.load_controller_asset(path, expected_schema_version="example.v1")

    path.write_bytes(evaluator.canonical_json_bytes({**canonical, "unexpected": True}))
    with pytest.raises(ValueError, match="unexpected"):
        evaluator.load_controller_asset(path, expected_schema_version="example.v1")


def test_visible_check_runner_uses_frozen_invocations_and_preserves_copy(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    package = evaluator.load_frozen_evaluator_package(
        visible_contract_path=TASK_ASSETS / "visible-task-contract.json",
        visible_contract_schema_path=TASK_ASSETS / "visible-task-contract.schema.json",
        visible_check_path=TASK_ASSETS / "visible-check-manifest.json",
        visible_check_schema_path=TASK_ASSETS / "visible-check-manifest.schema.json",
        fixture_manifest_path=EVALUATOR_ASSETS / "fixture-manifest.json",
        reviewer_perspectives_path=EVALUATOR_ASSETS / "reviewer-perspectives.json",
    )
    workspace = tmp_path / "candidate"
    for invocation in package["visible_checks"]["invocations"]:
        for index, selector in enumerate(invocation["selectors"]):
            path = workspace / selector
            path.parent.mkdir(parents=True, exist_ok=True)
            if index == 0:
                path.write_text(
                    "from pathlib import Path\n\n"
                    "def test_visible_control():\n"
                    "    product_root = Path(__file__).resolve().parents[2]\n"
                    "    assert not Path.cwd().resolve().is_relative_to(product_root)\n"
                    "    assert not Path('disposable-visible-output.txt').exists()\n"
                    "    Path('disposable-visible-output.txt').write_text(\n"
                    "        'discard me', encoding='utf-8'\n"
                    "    )\n",
                    encoding="utf-8",
                )
            else:
                path.write_text("def test_visible_control():\n    pass\n", encoding="utf-8")
    result = evaluator.run_visible_checks(
        workspace=workspace.resolve(),
        visible_checks=package["visible_checks"],
    )
    assert [row["invocation_id"] for row in result["invocations"]] == [
        "PRE_EDIT_FOCUSED",
        "CANDIDATE_EXTENSION",
    ]
    assert all(row["exit_code"] == 0 for row in result["invocations"])
    assert result["copy_digest_before"] == result["copy_digest_after"]
    assert not (workspace / "disposable-visible-output.txt").exists()


def test_visible_check_runner_rejects_execution_product_mutation(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    package = evaluator.load_frozen_evaluator_package(
        visible_contract_path=TASK_ASSETS / "visible-task-contract.json",
        visible_contract_schema_path=TASK_ASSETS / "visible-task-contract.schema.json",
        visible_check_path=TASK_ASSETS / "visible-check-manifest.json",
        visible_check_schema_path=TASK_ASSETS / "visible-check-manifest.schema.json",
        fixture_manifest_path=EVALUATOR_ASSETS / "fixture-manifest.json",
        reviewer_perspectives_path=EVALUATOR_ASSETS / "reviewer-perspectives.json",
    )
    workspace = tmp_path / "candidate"
    for invocation in package["visible_checks"]["invocations"]:
        for selector in invocation["selectors"]:
            path = workspace / selector
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "from pathlib import Path\n\n"
                "def test_visible_control():\n"
                "    product_root = Path(__file__).resolve().parents[2]\n"
                "    (product_root / 'mutation-assisted-pass.txt').write_text(\n"
                "        'must be blocked', encoding='utf-8'\n"
                "    )\n",
                encoding="utf-8",
            )

    with pytest.raises(evaluator.EvaluatorObservationError) as captured:
        evaluator.run_visible_checks(
            workspace=workspace.resolve(),
            visible_checks=package["visible_checks"],
        )

    assert captured.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert captured.value.mechanism == "candidate-process-write-audit"
    assert not (workspace / "mutation-assisted-pass.txt").exists()


def test_visible_check_runner_digest_ratchet_rejects_execution_product_rename(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    package = evaluator.load_frozen_evaluator_package(
        visible_contract_path=TASK_ASSETS / "visible-task-contract.json",
        visible_contract_schema_path=TASK_ASSETS / "visible-task-contract.schema.json",
        visible_check_path=TASK_ASSETS / "visible-check-manifest.json",
        visible_check_schema_path=TASK_ASSETS / "visible-check-manifest.schema.json",
        fixture_manifest_path=EVALUATOR_ASSETS / "fixture-manifest.json",
        reviewer_perspectives_path=EVALUATOR_ASSETS / "reviewer-perspectives.json",
    )
    workspace = tmp_path / "candidate"
    for invocation in package["visible_checks"]["invocations"]:
        for selector in invocation["selectors"]:
            path = workspace / selector
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "from pathlib import Path\n\n"
                "def test_visible_control():\n"
                "    source = Path(__file__).resolve()\n"
                "    source.rename(source.with_suffix(source.suffix + '.moved'))\n",
                encoding="utf-8",
            )

    with pytest.raises(evaluator.EvaluatorObservationError) as captured:
        evaluator.run_visible_checks(
            workspace=workspace.resolve(),
            visible_checks=package["visible_checks"],
        )

    assert captured.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert captured.value.mechanism == "candidate-process-mutation-audit"


def test_visible_check_runner_rejects_restored_byte_swap_into_product(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    package = evaluator.load_frozen_evaluator_package(
        visible_contract_path=TASK_ASSETS / "visible-task-contract.json",
        visible_contract_schema_path=TASK_ASSETS / "visible-task-contract.schema.json",
        visible_check_path=TASK_ASSETS / "visible-check-manifest.json",
        visible_check_schema_path=TASK_ASSETS / "visible-check-manifest.schema.json",
        fixture_manifest_path=EVALUATOR_ASSETS / "fixture-manifest.json",
        reviewer_perspectives_path=EVALUATOR_ASSETS / "reviewer-perspectives.json",
    )
    workspace = tmp_path / "candidate"
    (workspace / "swap_target.py").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "swap_target.py").write_text(
        "VALUE = 'original'\n", encoding="utf-8"
    )
    for invocation in package["visible_checks"]["invocations"]:
        for selector in invocation["selectors"]:
            path = workspace / selector
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "import importlib\n"
                "from pathlib import Path\n"
                "import sys\n\n"
                "def test_visible_control():\n"
                "    product_root = Path(__file__).resolve().parents[2]\n"
                "    original = product_root / 'swap_target.py'\n"
                "    backup = Path.cwd() / 'swap-target.original.py'\n"
                "    replacement = Path.cwd() / 'swap-target.replacement.py'\n"
                "    replacement.write_text(\"VALUE = 'replacement'\\n\", encoding='utf-8')\n"
                "    original.rename(backup)\n"
                "    replacement.rename(original)\n"
                "    try:\n"
                "        sys.modules.pop('swap_target', None)\n"
                "        importlib.invalidate_caches()\n"
                "        assert importlib.import_module('swap_target').VALUE == 'replacement'\n"
                "    finally:\n"
                "        sys.modules.pop('swap_target', None)\n"
                "        original.rename(replacement)\n"
                "        backup.rename(original)\n",
                encoding="utf-8",
            )

    with pytest.raises(evaluator.EvaluatorObservationError) as captured:
        evaluator.run_visible_checks(
            workspace=workspace.resolve(),
            visible_checks=package["visible_checks"],
        )

    assert captured.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert captured.value.mechanism == "candidate-process-mutation-audit"
    assert (workspace / "swap_target.py").read_text(encoding="utf-8") == (
        "VALUE = 'original'\n"
    )


def test_visible_check_runner_rejects_direct_write_to_source_candidate(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    package = evaluator.load_frozen_evaluator_package(
        visible_contract_path=TASK_ASSETS / "visible-task-contract.json",
        visible_contract_schema_path=TASK_ASSETS / "visible-task-contract.schema.json",
        visible_check_path=TASK_ASSETS / "visible-check-manifest.json",
        visible_check_schema_path=TASK_ASSETS / "visible-check-manifest.schema.json",
        fixture_manifest_path=EVALUATOR_ASSETS / "fixture-manifest.json",
        reviewer_perspectives_path=EVALUATOR_ASSETS / "reviewer-perspectives.json",
    )
    workspace = tmp_path / "candidate"
    source_mutation = (workspace / "source-mutation.txt").resolve()
    for invocation in package["visible_checks"]["invocations"]:
        for selector in invocation["selectors"]:
            path = workspace / selector
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "from pathlib import Path\n\n"
                "def test_visible_control():\n"
                f"    Path({str(source_mutation)!r}).write_text(\n"
                "        'must be blocked', encoding='utf-8'\n"
                "    )\n",
                encoding="utf-8",
            )

    with pytest.raises(evaluator.EvaluatorObservationError) as captured:
        evaluator.run_visible_checks(
            workspace=workspace.resolve(),
            visible_checks=package["visible_checks"],
        )

    assert captured.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert captured.value.mechanism == "candidate-process-write-audit"
    assert captured.value.evidence_record["observed_values"] == [
        str(source_mutation)
    ]
    assert not source_mutation.exists()


def _architecture_declaration(
    public_id: str, *, witness: bool = False
) -> dict[str, object]:
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
                "name": "es_f1_depth" if witness else "architecture",
            }
        ],
    }


def _candidate_claims(
    *, candidate_id: str = "calibration-control"
) -> dict[str, object]:
    return {
        "architecture_decision_path": "docs/architecture.md",
        "builtin_architectures": [
            _architecture_declaration(architecture_id)
            for architecture_id in task_package.F1_BUILTIN_ARCHITECTURES
        ],
        "candidate_id": candidate_id,
        "candidate_witness": _architecture_declaration(
            "es_f1_witness", witness=True
        ),
        "claims": [
            {
                "clause_id": clause_id,
                "evidence_paths": ["product.txt"],
                "scope": "IMPLEMENTED",
            }
            for clause_id in task_package.F1_HARD_CLAUSE_IDS
        ],
        "extension_author_guide_path": "docs/extension-guide.md",
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


def _observations(*, failed_clause: str | None = None) -> list[dict[str, object]]:
    evaluator = _evaluator()
    return [
        {
            "clause_id": clause_id,
            "satisfied": clause_id != failed_clause,
            "evidence": [f"sha256:{index + 1:064x}"],
            "details": "calibration observation",
        }
        for index, clause_id in enumerate(evaluator.HARD_CLAUSE_IDS)
    ]


def test_candidate_claims_are_not_evaluator_authority() -> None:
    evaluator = _evaluator()
    claims = _candidate_claims()
    result = evaluator.evaluate_observations(
        candidate_claims=claims,
        evaluator_observations=_observations(
            failed_clause="F1-H09-CONSTRUCTION-REBUILD-EQUALITY"
        ),
        dispositions={"F1-H09-CONSTRUCTION-REBUILD-EQUALITY": "PRODUCT_DEFECT"},
        frozen_registry={
            row["architecture"]
            for row in evaluator.load_controller_asset(
                EVALUATOR_ASSETS / "fixture-manifest.json",
                expected_schema_version="es-f1-fixture-manifest.v2",
            )["registry_baseline"]
        },
    )

    assert "candidate_claims" not in result
    assert result["candidate_claims_digest"].startswith("sha256:")
    by_id = {row["clause_id"]: row for row in result["evaluator_observations"]}
    assert by_id["F1-H09-CONSTRUCTION-REBUILD-EQUALITY"]["satisfied"] is False
    assert by_id["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"]["satisfied"] is True
    assert result["hard_findings"] == [
        {
            "candidate_id": "calibration-control",
            "clause_id": "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
            "details": "calibration observation",
            "disposition": "PRODUCT_DEFECT",
            "evaluator_observation": {
                "evidence_digest": by_id["F1-H09-CONSTRUCTION-REBUILD-EQUALITY"][
                    "evidence_digest"
                ],
                "satisfied": False,
            },
            "schema_version": "es-f1-hard-finding.v2",
        }
    ]

    poisoned = _candidate_claims()
    poisoned["passed"] = True
    with pytest.raises(ValueError, match="authority"):
        evaluator.evaluate_observations(
            candidate_claims=poisoned,
            evaluator_observations=_observations(),
            dispositions={},
            frozen_registry={"ffno"},
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-built-in",
        "duplicate-built-in",
        "built-in-witness",
    ],
)
def test_architecture_matrix_claims_fail_closed(mutation: str) -> None:
    evaluator = _evaluator()
    claims = _candidate_claims()
    if mutation == "missing-built-in":
        claims["builtin_architectures"].pop()
    elif mutation == "duplicate-built-in":
        claims["builtin_architectures"][1] = copy.deepcopy(
            claims["builtin_architectures"][0]
        )
    else:
        claims["candidate_witness"]["public_id"] = "ffno"
    with pytest.raises(ValueError, match="candidate architecture matrix"):
        evaluator.evaluate_observations(
            candidate_claims=claims,
            evaluator_observations=_observations(),
            dispositions={},
            frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
        )


def _synthetic_full_matrix_semantic_report() -> dict[str, Any]:
    evaluator = _evaluator()
    evidence = _candidate_claims()
    declarations = [
        *evidence["builtin_architectures"],
        evidence["candidate_witness"],
    ]
    owner_contract = copy.deepcopy(evaluator._PUBLIC_SCIENTIFIC_BOUNDARY_CONTRACT)
    owners = copy.deepcopy(evaluator._PUBLIC_SCIENTIFIC_BOUNDARY_OWNERS)

    def digest(number: int) -> str:
        return f"sha256:{number:064x}"

    def rejection(number: int) -> dict[str, object]:
        return {
            "exception_detail_sha256": digest(number),
            "exception_type": "ValueError",
            "module_returned": False,
            "rejected": True,
        }

    rows: list[dict[str, Any]] = []
    next_pid = 1000
    for ordinal, declaration in enumerate(declarations, start=1):
        architecture_id = declaration["public_id"]
        N = 128 if architecture_id == "neuralop_uno" else 64
        implementation = f"product.{architecture_id}.Implementation"
        structural_values = {
            field["name"]: field["baseline_value"]
            for field in declaration["structural_fields"]
        }
        state_signature = digest(10_000 + ordinal)
        observable_digest = digest(20_000 + ordinal)

        def reload(*, bundle: bool) -> dict[str, object]:
            nonlocal next_pid
            next_pid += 1
            return {
                "artifact_bytes": 1_000 + ordinal,
                "artifact_sha256": digest(25_000 + ordinal),
                "architecture_id": architecture_id,
                "boundary_contract": owner_contract,
                "boundary_input_digest_after": digest(30_000 + ordinal),
                "boundary_input_digest_before": digest(30_000 + ordinal),
                "boundary_owners": owners,
                "fresh_pid": next_pid,
                "implementation_identity": implementation,
                "inference_deterministic": True,
                "inference_dtype": "complex64",
                "inference_finite": True,
                "inference_max_abs_delta": 0.0,
                "inference_shape": [1, 1, N, N],
                "inference_tolerance": 0.0,
                "loaded_forbidden_modules": [],
                "observable_digest": observable_digest,
                "outside_project_origin_rows": [],
                "roles": ["autoencoder", "diffraction_to_obj"] if bundle else [],
                "state_signature": state_signature,
                "structural_values": structural_values,
            }

        sensitivities = {
            field["name"]: {
                "alternate_identity_digest": digest(40_000 + ordinal),
                "alternate_observable_digest": digest(50_000 + ordinal),
                "alternate_state_signature": digest(60_000 + ordinal),
                "baseline_identity_digest": digest(70_000 + ordinal),
                "baseline_observable_digest": observable_digest,
                "baseline_state_signature": state_signature,
                "deterministic": True,
            }
            for field in declaration["structural_fields"]
        }
        rows.append(
            {
                "N": N,
                "architecture_id": architecture_id,
                "boundary_contract": owner_contract,
                "boundary_input_digest_after": digest(30_000 + ordinal),
                "boundary_input_digest_before": digest(30_000 + ordinal),
                "bundle_implementation": implementation,
                "completed_stages": list(task_package.F1_LIFECYCLE_STAGES),
                "config_digest": digest(5_000 + ordinal),
                "construction_route": declaration["construction_route"],
                "registry_constructor_identity": (
                    f"product.{architecture_id}.RegistryConstructor"
                ),
                "evaluator_bundle_reload": reload(bundle=True),
                "evaluator_checkpoint_reload": reload(bundle=False),
                "adapter_bundle_reload": reload(bundle=True),
                "adapter_checkpoint_reload": reload(bundle=False),
                "forward_shape": [1, 1, N, N],
                "forward_deterministic": True,
                "forward_dtype": "complex64",
                "forward_finite": True,
                "forward_max_abs_delta": 0.0,
                "forward_tolerance": 0.0,
                "gradients_finite": True,
                "identity_rejections": {
                    "extra": rejection(80_000 + ordinal),
                    "missing": {
                        field["name"]: rejection(90_000 + ordinal)
                        for field in declaration["structural_fields"]
                    },
                    "unsupported_value": rejection(100_000 + ordinal),
                },
                "identity_sensitivity": sensitivities,
                "inference_digest": observable_digest,
                "input_digest": digest(6_000 + ordinal),
                "loss_finite": True,
                "loss_scalar": True,
                "optimizer_state_after": digest(110_000 + ordinal),
                "optimizer_state_before": digest(120_000 + ordinal),
                "optimizer_step_bound": evaluator.F1_MAX_OPTIMIZER_STEP_ABS_DELTA,
                "optimizer_step_max_abs_delta": 0.25,
                "optimizer_transition_bounded": True,
                "persisted_boundary_owners": owners,
                "persisted_implementation": implementation,
                "persisted_rebuild_implementation": implementation,
                "persisted_rebuild_route": declaration["persisted_rebuild_route"],
                "persisted_state_signature": state_signature,
                "public_boundary_owners": owners,
                "public_implementation": implementation,
                "public_state_signature": state_signature,
                "seed": 20_260_802,
                "structural_fields": copy.deepcopy(declaration["structural_fields"]),
                "structural_values": structural_values,
            }
        )
    return {
        "architecture_results": rows,
        "cache_artifacts": [],
        "construction_pid": 99,
        "loaded_forbidden_modules": [],
        "outside_project_origin_rows": [],
        "schema_version": "es-f1-semantic-lifecycle.v2",
        "unknown_architecture_rejection": rejection(130_000),
    }


def test_full_matrix_lifecycle_observations_cover_all_architectures_in_order() -> None:
    evaluator = _evaluator()
    report = _synthetic_full_matrix_semantic_report()

    observations = evaluator.derive_lifecycle_observations(
        semantic_report=report,
        adapter_process_id=98,
    )

    assert [row["architecture_id"] for row in report["architecture_results"]] == [
        *task_package.F1_BUILTIN_ARCHITECTURES,
        "es_f1_witness",
    ]
    assert "roles" not in report
    assert "identity_rejections" not in report
    assert all(
        "identity_rejections" in row for row in report["architecture_results"]
    )
    assert [row["clause_id"] for row in observations] == list(
        task_package.F1_HARD_CLAUSE_IDS[4:]
    )
    assert all(row["satisfied"] for row in observations)
    assert evaluator.F1_MAX_OPTIMIZER_STEP_ABS_DELTA == 1.0
    assert all(
        row["optimizer_step_bound"] == 1.0
        for row in report["architecture_results"]
    )
    assert {
        row["forward_dtype"] for row in report["architecture_results"]
    } == {"complex64"}
    assert {
        row[reload_name]["inference_dtype"]
        for row in report["architecture_results"]
        for reload_name in (
            "evaluator_checkpoint_reload",
            "evaluator_bundle_reload",
            "adapter_checkpoint_reload",
            "adapter_bundle_reload",
        )
    } == {"complex64"}


def test_identity_sensitivity_requires_state_and_observable_change_only_for_witness_fields() -> None:
    evaluator = _evaluator()
    builtin_report = _synthetic_full_matrix_semantic_report()
    builtin_sensitivity = builtin_report["architecture_results"][0][
        "identity_sensitivity"
    ]["architecture"]
    builtin_sensitivity["alternate_state_signature"] = builtin_sensitivity[
        "baseline_state_signature"
    ]
    builtin_sensitivity["alternate_observable_digest"] = builtin_sensitivity[
        "baseline_observable_digest"
    ]

    builtin_observations = evaluator.derive_lifecycle_observations(
        semantic_report=builtin_report,
        adapter_process_id=98,
    )

    assert next(
        row for row in builtin_observations
        if row["clause_id"] == "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY"
    )["satisfied"] is True

    witness_report = _synthetic_full_matrix_semantic_report()
    witness_sensitivity = witness_report["architecture_results"][-1][
        "identity_sensitivity"
    ]["es_f1_depth"]
    witness_sensitivity["alternate_state_signature"] = witness_sensitivity[
        "baseline_state_signature"
    ]
    witness_sensitivity["alternate_observable_digest"] = witness_sensitivity[
        "baseline_observable_digest"
    ]

    witness_observations = evaluator.derive_lifecycle_observations(
        semantic_report=witness_report,
        adapter_process_id=98,
    )

    assert next(
        row for row in witness_observations
        if row["clause_id"] == "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY"
    )["satisfied"] is False


def test_registry_constructor_preflight_is_bound_to_semantic_phase() -> None:
    evaluator = _evaluator()
    report = _synthetic_full_matrix_semantic_report()
    preflight = {
        row["architecture_id"]: row["registry_constructor_identity"]
        for row in report["architecture_results"]
    }
    report["architecture_results"][-1]["registry_constructor_identity"] = (
        report["architecture_results"][1]["registry_constructor_identity"]
    )

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._bind_registry_constructor_identities(
            preflight_identities=preflight,
            semantic_report=report,
        )

    assert caught.value.clause_id == "F1-H09-CONSTRUCTION-REBUILD-EQUALITY"
    assert caught.value.mechanism == "registry-constructor-phase-drift"


@pytest.mark.parametrize(
    ("defect", "failed_clause"),
    [
        ("same-process", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("incomplete-stage", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("optimizer-no-transition", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("forward-nondeterministic", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("forward-nonfinite", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("loss-nonscalar", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("gradient-nonfinite", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("optimizer-unbounded", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("reload-artifact-empty", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("reload-inference-nondeterministic", "F1-H05-FULL-ARCHITECTURE-LIFECYCLE"),
        ("structural-loss", "F1-H06-STRUCTURAL-ROUNDTRIP"),
        ("missing-rejection", "F1-H07-STRUCTURAL-IDENTITY-REJECTION"),
        ("unknown-rejection", "F1-H07-STRUCTURAL-IDENTITY-REJECTION"),
        ("identity-insensitive", "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY"),
        ("construction-rebuild-disagreement", "F1-H09-CONSTRUCTION-REBUILD-EQUALITY"),
        ("witness_builtin_alias", "F1-H09-CONSTRUCTION-REBUILD-EQUALITY"),
        ("ownership-crossing", "F1-H10-OWNERSHIP-BOUNDARY"),
    ],
)
def test_full_matrix_lifecycle_defects_fail_only_the_owning_clause(
    defect: str,
    failed_clause: str,
) -> None:
    evaluator = _evaluator()
    report = _synthetic_full_matrix_semantic_report()
    witness = report["architecture_results"][-1]
    if defect == "same-process":
        witness["adapter_checkpoint_reload"]["fresh_pid"] = report["construction_pid"]
    elif defect == "incomplete-stage":
        witness["completed_stages"].pop()
    elif defect == "optimizer-no-transition":
        witness["optimizer_state_after"] = witness["optimizer_state_before"]
    elif defect == "forward-nondeterministic":
        witness["forward_deterministic"] = False
    elif defect == "forward-nonfinite":
        witness["forward_finite"] = False
    elif defect == "loss-nonscalar":
        witness["loss_scalar"] = False
    elif defect == "gradient-nonfinite":
        witness["gradients_finite"] = False
    elif defect == "optimizer-unbounded":
        witness["optimizer_transition_bounded"] = False
    elif defect == "reload-artifact-empty":
        witness["adapter_checkpoint_reload"]["artifact_bytes"] = 0
    elif defect == "reload-inference-nondeterministic":
        witness["adapter_bundle_reload"]["inference_deterministic"] = False
    elif defect == "structural-loss":
        witness["adapter_bundle_reload"]["structural_values"]["es_f1_depth"] = 3
        witness["adapter_bundle_reload"]["state_signature"] = (
            "sha256:" + "f" * 64
        )
    elif defect == "missing-rejection":
        witness["identity_rejections"]["missing"]["es_f1_depth"].update(
            {
                "exception_detail_sha256": "sha256:"
                + hashlib.sha256(b"").hexdigest(),
                "exception_type": None,
                "module_returned": True,
                "rejected": False,
            }
        )
    elif defect == "unknown-rejection":
        report["unknown_architecture_rejection"].update(
            {
                "exception_detail_sha256": "sha256:"
                + hashlib.sha256(b"").hexdigest(),
                "exception_type": None,
                "module_returned": True,
                "rejected": False,
            }
        )
    elif defect == "identity-insensitive":
        sensitivity = witness["identity_sensitivity"]["es_f1_depth"]
        sensitivity["alternate_observable_digest"] = sensitivity[
            "baseline_observable_digest"
        ]
    elif defect == "construction-rebuild-disagreement":
        witness["persisted_rebuild_implementation"] = "product.OtherImplementation"
    elif defect == "witness_builtin_alias":
        witness["registry_constructor_identity"] = report[
            "architecture_results"
        ][1]["registry_constructor_identity"]
    else:
        witness["public_boundary_owners"]["compute_loss"] = (
            "candidate.extension.compute_loss"
        )

    observations = evaluator.derive_lifecycle_observations(
        semantic_report=report,
        adapter_process_id=98,
    )

    assert {
        row["clause_id"] for row in observations if not row["satisfied"]
    } == {failed_clause}


@pytest.mark.parametrize("location", ("unknown", "missing"))
@pytest.mark.parametrize(
    "malformation",
    ("missing-key", "contradictory-flags", "exception-mismatch"),
)
def test_full_matrix_lifecycle_malformed_rejection_record_fails_closed(
    location: str,
    malformation: str,
) -> None:
    evaluator = _evaluator()
    report = _synthetic_full_matrix_semantic_report()
    if location == "unknown":
        rejection = report["unknown_architecture_rejection"]
    else:
        rejection = report["architecture_results"][-1]["identity_rejections"][
            "missing"
        ]["es_f1_depth"]
    if malformation == "missing-key":
        rejection.pop("exception_type")
    elif malformation == "contradictory-flags":
        rejection.update(
            {
                "exception_type": None,
                "module_returned": False,
                "rejected": False,
            }
        )
    else:
        rejection["exception_type"] = None

    with pytest.raises(evaluator.EvaluatorError, match="rejection.*malformed"):
        evaluator.derive_lifecycle_observations(
            semantic_report=report,
            adapter_process_id=98,
        )


def test_full_matrix_lifecycle_row_and_reload_fact_shapes_are_closed() -> None:
    evaluator = _evaluator()
    report = _synthetic_full_matrix_semantic_report()
    report["architecture_results"][0].pop("forward_dtype")
    with pytest.raises(evaluator.EvaluatorError, match="record is not exact"):
        evaluator.derive_lifecycle_observations(
            semantic_report=report,
            adapter_process_id=98,
        )

    report = _synthetic_full_matrix_semantic_report()
    report["architecture_results"][0]["adapter_checkpoint_reload"].pop(
        "artifact_sha256"
    )
    with pytest.raises(evaluator.EvaluatorError, match="reload record is not exact"):
        evaluator.derive_lifecycle_observations(
            semantic_report=report,
            adapter_process_id=98,
        )


def test_task0_bypass_authority_loads_frozen_pretty_printed_schemas() -> None:
    evaluator = _evaluator()
    evaluator._task0_bypass_authority.cache_clear()

    authority = evaluator._task0_bypass_authority()

    assert authority["bindings"]["legacy_bypass_inventory_sha256"] == (
        "sha256:3701ca66235df5733ceb5bb54fa0c118519a9ae0e3acd5515bef7af9e78c119c"
    )
    assert len(authority["partition"]["required_consumer_ids"]) == 5
    assert len(authority["partition"]["inherited_consumer_ids"]) == 84
    assert len(authority["partition"]["open_consumer_ids"]) == 626
    assert len(authority["contract"].desired_specs) == 23


def _synthetic_complete_observation_inputs(
    tmp_path: Path,
) -> dict[str, Any]:
    evaluator = _evaluator()
    candidate_id = "calibration-control"
    workspace = _candidate_copy(tmp_path, candidate_id=candidate_id)
    task0_candidate = _task0_discovery_from_bare_commit(
        tmp_path / "task0-authenticated",
        source_workspace=workspace,
    )
    candidate_evidence = json.loads(
        (workspace / "es_f1_candidate_evidence.json").read_bytes()
    )
    request = _lifecycle_request(candidate_id, workspace)
    visible_checks = json.loads(
        (TASK_ASSETS / "visible-check-manifest.json").read_bytes()
    )
    runner = visible_checks["runner"]
    by_id = {row["id"]: row for row in visible_checks["invocations"]}
    copy_digest = evaluator._workspace_digest(workspace)
    visible_result = {
        "schema_version": "es-f1-visible-check-result.v2",
        "copy_digest_after": copy_digest,
        "copy_digest_before": copy_digest,
        "invocations": [
            {
                "argv": [
                    runner["python_executable"],
                    *runner["argv_prefix"],
                    *by_id[invocation_id]["selectors"],
                ],
                "exit_code": 0,
                "invocation_id": invocation_id,
                "stderr_sha256": f"sha256:{index + 2:064x}",
                "stdout_sha256": f"sha256:{index + 4:064x}",
            }
            for index, invocation_id in enumerate(visible_checks["invocation_order"])
        ],
    }
    fixture_manifest = json.loads(
        (EVALUATOR_ASSETS / "fixture-manifest.json").read_bytes()
    )
    registry_report = {
        "schema_version": "es-f1-registry-signature-probe.v1",
        "registry_baseline": copy.deepcopy(fixture_manifest["registry_baseline"]),
        "loaded_forbidden_modules": [],
        "outside_project_origin_rows": [],
        "cache_artifacts": [],
    }
    artifact_domain = [
        *task_package.F1_BUILTIN_ARCHITECTURES,
        "es_f1_witness",
    ]
    artifact_report = {
        "schema_version": "es-f1-artifact-fixture-verification.v2",
        "artifact_eras": [
            {
                "architecture_results": [
                    {
                        "architecture_id": architecture_id,
                        "diagnostic": (
                            None
                            if architecture_id
                            in [
                                "es_f1_witness"
                                if value == "$candidate_witness"
                                else value
                                for value in row["applicable_architecture_ids"]
                            ]
                            else "UNSUPPORTED_ARTIFACT_ARCHITECTURE"
                        ),
                        "implementation_identity": (
                            next(
                                baseline["implementation_identity"]
                                for baseline in fixture_manifest["registry_baseline"]
                                if baseline["architecture"] == architecture_id
                            )
                            if architecture_id
                            in [
                                "es_f1_witness"
                                if value == "$candidate_witness"
                                else value
                                for value in row["applicable_architecture_ids"]
                            ]
                            else None
                        ),
                        "module_returned": architecture_id
                        in [
                            "es_f1_witness"
                            if value == "$candidate_witness"
                            else value
                            for value in row["applicable_architecture_ids"]
                        ],
                        "strict_load": architecture_id
                        in [
                            "es_f1_witness"
                            if value == "$candidate_witness"
                            else value
                            for value in row["applicable_architecture_ids"]
                        ],
                    }
                    for architecture_id in artifact_domain
                ],
                "era_id": row["era_id"],
            }
            for row in fixture_manifest["artifact_eras"]
        ],
        "loaded_forbidden_modules": [],
        "outside_project_origin_rows": [],
        "cache_artifacts": [],
    }
    semantic_report = _synthetic_full_matrix_semantic_report()
    for semantic_row, request_case in zip(
        semantic_report["architecture_results"],
        request["architecture_cases"],
        strict=True,
    ):
        semantic_row["config_digest"] = request_case["config"]["sha256"]
        semantic_row["input_digest"] = request_case["input"]["sha256"]
        semantic_row["seed"] = request["seed"]
    lifecycle_observations = evaluator.derive_lifecycle_observations(
        semantic_report=semantic_report,
        adapter_process_id=200,
    )
    adapter_result = {
        "architecture_results": [
            {
                "architecture_id": row["architecture_id"],
                "bundle_path": (
                    f"artifacts/{index:02d}-{row['architecture_id']}/wts.h5.zip"
                ),
                "checkpoint_path": (
                    f"artifacts/{index:02d}-{row['architecture_id']}/model.ckpt"
                ),
            }
            for index, row in enumerate(
                semantic_report["architecture_results"], start=1
            )
        ],
        "candidate_id": candidate_id,
        "operation_version": request["operation_version"],
        "schema_version": "lifecycle_probe_result.v3",
    }
    semantic_observations = {
        row["architecture_id"]: {
            "checkpoint": row["adapter_checkpoint_reload"],
            "bundle": row["adapter_bundle_reload"],
        }
        for row in semantic_report["architecture_results"]
    }
    lifecycle_result = {
        "adapter_result": adapter_result,
        "audit_digest": f"sha256:{13:064x}",
        "copy_digest_after": copy_digest,
        "copy_digest_before": copy_digest,
        "adapter_process_id": 200,
        "semantic_observations": semantic_observations,
        "semantic_report": semantic_report,
        "lifecycle_observations": lifecycle_observations,
    }
    return {
        "artifact_report": artifact_report,
        "candidate_evidence": candidate_evidence,
        "candidate_tree": task0_candidate["tree"],
        "candidate_workspace": task0_candidate["workspace"],
        "fixture_manifest": fixture_manifest,
        "legacy_bypass_discovery_input": task0_candidate["input"],
        "lifecycle_request": request,
        "lifecycle_result": lifecycle_result,
        "registry_report": registry_report,
        "visible_check_result": visible_result,
        "visible_checks": visible_checks,
    }


def test_complete_observation_derivation_keeps_pre_task3a_h05_unresolved(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    inputs = _synthetic_complete_observation_inputs(tmp_path)

    observations = evaluator.derive_complete_observations(**inputs)

    assert [row["clause_id"] for row in observations] == list(
        evaluator.HARD_CLAUSE_IDS
    )
    assert {
        row["clause_id"] for row in observations if not row["satisfied"]
    } == {"F1-H05-FULL-ARCHITECTURE-LIFECYCLE"}
    assert all(row["evidence"] for row in observations)


def test_h04_rejects_cross_architecture_historical_implementation_fallback(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    inputs = _synthetic_complete_observation_inputs(tmp_path)
    identities = {
        row["architecture"]: row["implementation_identity"]
        for row in inputs["fixture_manifest"]["registry_baseline"]
    }
    first_era = inputs["artifact_report"]["artifact_eras"][0]
    applicable = next(
        row
        for row in first_era["architecture_results"]
        if row["architecture_id"] == "ffno"
    )
    applicable["implementation_identity"] = identities["cnn"]

    observations = evaluator.derive_complete_observations(**inputs)

    assert {
        row["clause_id"] for row in observations if not row["satisfied"]
    } == {
        "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
        "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
    }


def _task0_discovery_from_bare_commit(
    tmp_path: Path,
    *,
    payloads: dict[str, bytes] | None = None,
    source_workspace: Path | None = None,
) -> dict[str, Any]:
    from scripts.experiments.es import source_census

    if (payloads is None) == (source_workspace is None):
        raise ValueError("provide exactly one Task0 candidate source")
    worktree = tmp_path / "worktree"
    repository = tmp_path / "projection.git"
    git = Path("/usr/bin/git")
    if source_workspace is not None:
        source = source_workspace.resolve(strict=True)
        if not source.is_dir():
            raise ValueError("Task0 candidate source must be a directory")

        def ignore_root_git(directory: str, names: list[str]) -> set[str]:
            if Path(directory) == source and ".git" in names:
                return {".git"}
            return set()

        shutil.copytree(
            source,
            worktree,
            copy_function=shutil.copy2,
            ignore=ignore_root_git,
            symlinks=True,
        )
    else:
        worktree.mkdir(parents=True)
        assert payloads is not None
        for relative, payload in payloads.items():
            path = worktree / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    subprocess.run([str(git), "init", "-q", str(worktree)], check=True)
    commit_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "F1 fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_AUTHOR_DATE": "1700000000 +0000",
        "GIT_COMMITTER_NAME": "F1 fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_DATE": "1700000000 +0000",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "HOME": str(tmp_path),
        "LANG": "C",
        "LC_ALL": "C",
    }
    subprocess.run(
        [str(git), "-C", str(worktree), "add", "-f", "--all"],
        check=True,
        env=commit_env,
    )
    subprocess.run(
        [str(git), "-C", str(worktree), "commit", "-q", "-m", "fixture"],
        check=True,
        env=commit_env,
    )
    subprocess.run(
        [str(git), "clone", "--bare", "-q", str(worktree), str(repository)],
        check=True,
        env=commit_env,
    )

    def git_output(*arguments: str) -> bytes:
        return subprocess.run(
            [str(git), f"--git-dir={repository}", *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=commit_env,
        ).stdout

    commit = git_output("rev-parse", "HEAD").decode().strip()
    tree = git_output("rev-parse", f"{commit}^{{tree}}").decode().strip()
    inventory = git_output("ls-tree", "-rz", "-r", "--full-tree", commit)
    discovery_input = json.loads(
        (
            REPO
            / "docs/plans/evidence/es-f1-large-scope-refreeze/"
            "preedit-discovery-input.json"
        ).read_bytes()
    )
    discovery_input["projection"] = {
        "repository": str(repository.resolve()),
        "commit": commit,
        "tree": tree,
        "inventory_sha256": "sha256:" + hashlib.sha256(inventory).hexdigest(),
        "leaf_count": sum(1 for record in inventory.split(b"\0") if record),
    }
    discovery_output = source_census.discover_source(
        discovery_input,
        discovery_input_sha256=source_census.raw_sha256(
            source_census.canonical_json_bytes(discovery_input)
        ),
    )
    return {
        "input": discovery_input,
        "output": discovery_output,
        "tree": tree,
        "workspace": worktree.resolve(),
    }


def test_task0_discovery_force_adds_complete_payload_inventory(
    tmp_path: Path,
) -> None:
    discovery = _task0_discovery_from_bare_commit(
        tmp_path,
        payloads={
            ".gitignore": b"ignored.py\n",
            "ignored.py": b"raise RuntimeError('must not be committed')\n",
            "tracked.py": b"VALUE = 1\n",
        },
    )

    projection = discovery["input"]["projection"]
    assert projection["leaf_count"] == 3
    assert discovery["output"]["projection"] == projection
    assert {row["path"] for row in discovery["output"]["leaf_rows"]} == {
        ".gitignore",
        "ignored.py",
        "tracked.py",
    }


def test_task0_discovery_exact_copy_preserves_workspace_digest_and_git_kinds(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    source = tmp_path / "candidate-source"
    (source / "bin").mkdir(parents=True)
    (source / "empty-directory").mkdir()
    (source / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (source / "ignored.py").write_text("VALUE = 1\n", encoding="utf-8")
    executable = source / "bin/run.sh"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o751)
    (source / "empty-directory").chmod(0o750)
    (source / "run-link").symlink_to("bin/run.sh")

    discovery = _task0_discovery_from_bare_commit(
        tmp_path / "authenticated",
        source_workspace=source,
    )

    assert evaluator._workspace_digest(source) == evaluator._workspace_digest(
        discovery["workspace"]
    )
    assert (discovery["workspace"] / "bin/run.sh").stat().st_mode & 0o777 == 0o751
    assert (
        discovery["workspace"] / "empty-directory"
    ).stat().st_mode & 0o777 == 0o750
    assert (discovery["workspace"] / "run-link").is_symlink()
    assert os.readlink(discovery["workspace"] / "run-link") == "bin/run.sh"
    leaf_modes = {
        row["path"]: row["mode"] for row in discovery["output"]["leaf_rows"]
    }
    assert leaf_modes == {
        ".gitignore": "100644",
        "bin/run.sh": "100755",
        "ignored.py": "100644",
        "run-link": "120000",
    }


def test_complete_observation_requires_authenticated_task0_candidate_context() -> None:
    evaluator = _evaluator()

    parameters = inspect.signature(evaluator.derive_complete_observations).parameters

    assert "legacy_bypass_report" not in parameters
    assert {
        "candidate_workspace",
        "candidate_tree",
        "legacy_bypass_discovery_input",
    } <= set(parameters)


def test_complete_observation_rejects_authenticated_task0_candidate_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator()
    inputs = _synthetic_complete_observation_inputs(tmp_path)
    evaluated_digest = evaluator._workspace_digest(inputs["candidate_workspace"])
    inputs["visible_check_result"]["copy_digest_before"] = evaluated_digest
    inputs["visible_check_result"]["copy_digest_after"] = evaluated_digest
    inputs["lifecycle_result"]["copy_digest_before"] = evaluated_digest
    inputs["lifecycle_result"]["copy_digest_after"] = evaluated_digest
    candidate_b_root = tmp_path / "candidate-b-source"
    candidate_b_root.mkdir()
    candidate_b_workspace = _candidate_copy(
        candidate_b_root,
        candidate_id="different-candidate",
    )
    candidate_b = _task0_discovery_from_bare_commit(
        tmp_path / "candidate-b-task0",
        source_workspace=candidate_b_workspace,
    )
    inputs["candidate_workspace"] = candidate_b["workspace"]
    inputs["candidate_tree"] = candidate_b["tree"]
    inputs["legacy_bypass_discovery_input"] = candidate_b["input"]
    task0_called = False

    def observe_task0(**kwargs: Any) -> dict[str, Any]:
        nonlocal task0_called
        task0_called = True
        return {
            "clause_id": "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
            "details": "stubbed Task-0 result",
            "evidence": f"sha256:{31:064x}",
            "satisfied": True,
        }

    monkeypatch.setattr(
        evaluator,
        "derive_authenticated_task0_bypass_observation",
        observe_task0,
    )

    with pytest.raises(
        evaluator.EvaluatorError,
        match=(
            "candidate workspace digest does not match visible and lifecycle evidence"
        ),
    ):
        evaluator.derive_complete_observations(**inputs)
    assert task0_called is False


def test_authenticated_task0_observation_runs_fresh_discovery_and_pinned_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator()
    from scripts.experiments.es import boundary_proofs, source_census

    discovery = _task0_discovery_from_bare_commit(
        tmp_path / "authenticated",
        payloads={
            "scripts/new_resolver_consumer.py": (
                b"from ptycho_torch.generators.registry import resolve_generator\n"
                b"constructor = resolve_generator('ffno')\n"
            )
        },
    )
    real_discover = source_census.discover_source
    discovery_calls: list[dict[str, Any]] = []
    runner_calls: list[dict[str, Any]] = []

    def observe_fresh_discovery(
        discovery_input: dict[str, Any],
        *,
        discovery_input_sha256: str,
    ) -> dict[str, Any]:
        discovery_calls.append(copy.deepcopy(discovery_input))
        return real_discover(
            discovery_input,
            discovery_input_sha256=discovery_input_sha256,
        )

    def fail_desired_state(
        selector_manifest: dict[str, Any],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        runner_calls.append(
            {"selector_manifest": selector_manifest, "kwargs": dict(kwargs)}
        )
        raise boundary_proofs.BoundaryProofError(
            "proof_desired_state_failed",
            "proof-pre-task3a",
        )

    monkeypatch.setattr(source_census, "discover_source", observe_fresh_discovery)
    monkeypatch.setattr(boundary_proofs, "execute_desired_state", fail_desired_state)

    observation = evaluator.derive_authenticated_task0_bypass_observation(
        candidate_workspace=discovery["workspace"],
        candidate_tree=discovery["tree"],
        discovery_input=discovery["input"],
    )

    assert observation["satisfied"] is False
    assert observation["proof_error_code"] == "proof_desired_state_failed"
    assert len(discovery_calls) == 1
    assert len(runner_calls) == 1
    runner_kwargs = runner_calls[0]["kwargs"]
    assert "expected_result_rows" not in runner_kwargs
    assert runner_kwargs["workspace"] == discovery["workspace"]
    assert runner_kwargs["expected_tree"] == discovery["tree"]
    assert runner_kwargs["python"] == boundary_proofs.PINNED_PYTHON
    assert runner_kwargs["pytest_carrier"] == boundary_proofs.PINNED_PYTEST_CARRIER


def test_task0_classifier_restored_reference_absence_fails_h05(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    discovery = _task0_discovery_from_bare_commit(
        tmp_path / "discovery",
        payloads={
            "archive/root_scripts/analysis/extract_reconstructions.py": (
                b"from ptycho.config.config import ModelConfig\n"
                b"restored = ModelConfig()\n"
            )
        },
    )
    classification = evaluator.classify_task0_bypass_discovery(
        discovery_input=discovery["input"],
        discovery_output=discovery["output"],
        verified_construction_route=evaluator.F1_PUBLIC_CONSTRUCTION_ROUTE,
    )
    assert classification["restored_required_consumer_ids"] == [
        "consumer-3d5ba8fb56b5dd7fc5a44edf1a3a1982"
    ]


@pytest.mark.parametrize(
    ("caller_path", "expected_bucket"),
    (
        ("scripts/new_direct.py", "novel_direct_matches"),
        (
            "ptycho_torch/generators/es_f1_witness.py",
            "allowed_boundary_matches",
        ),
    ),
)
def test_task0_classifier_owns_novel_direct_generator_imports(
    tmp_path: Path,
    caller_path: str,
    expected_bucket: str,
) -> None:
    evaluator = _evaluator()
    discovery = _task0_discovery_from_bare_commit(
        tmp_path / expected_bucket,
        payloads={
            caller_path: (
                b"from ptycho_torch.generators.ffno import FfnoGenerator\n"
                b"implementation = FfnoGenerator\n"
            )
        },
    )
    classification = evaluator.classify_task0_bypass_discovery(
        discovery_input=discovery["input"],
        discovery_output=discovery["output"],
        verified_construction_route=evaluator.F1_PUBLIC_CONSTRUCTION_ROUTE,
    )

    assert [
        row["caller_path"] for row in classification[expected_bucket]
    ] == [caller_path]
    assert bool(classification["novel_direct_matches"]) is (
        expected_bucket == "novel_direct_matches"
    )


def test_task0_classifier_allows_new_verified_resolver_consumer(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    discovery = _task0_discovery_from_bare_commit(
        tmp_path / "resolver",
        payloads={
            "scripts/new_resolver_consumer.py": (
                b"from ptycho_torch.generators.registry import resolve_generator\n"
                b"constructor = resolve_generator('ffno')\n"
            )
        },
    )

    classification = evaluator.classify_task0_bypass_discovery(
        discovery_input=discovery["input"],
        discovery_output=discovery["output"],
        verified_construction_route=evaluator.F1_PUBLIC_CONSTRUCTION_ROUTE,
    )

    assert classification["novel_direct_matches"] == []
    assert {
        row["anchor_id"] for row in classification["allowed_boundary_matches"]
    } == {"GENERATOR_PACKAGE_IMPORT", "GENERATOR_REGISTRY_IMPORT"}


def test_task0_public_classifier_rejects_omitted_discovery_row(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    discovery = _task0_discovery_from_bare_commit(
        tmp_path / "subset",
        payloads={
            "scripts/new_direct.py": (
                b"from ptycho_torch.generators.ffno import FfnoGenerator\n"
                b"implementation = FfnoGenerator\n"
            )
        },
    )
    partial = copy.deepcopy(discovery["output"])
    partial["consumer_candidates"].clear()
    partial["candidate_set_sha256"] = evaluator._digest([])

    with pytest.raises(evaluator.EvaluatorError, match="incomplete or drifted"):
        evaluator.classify_task0_bypass_discovery(
            discovery_input=discovery["input"],
            discovery_output=partial,
            verified_construction_route=evaluator.F1_PUBLIC_CONSTRUCTION_ROUTE,
        )


@pytest.mark.parametrize(
    ("tamper", "diagnostic"),
    (
        ("tree", "tree binding"),
        ("workspace", "workspace is not canonical"),
        ("discovery-authority", "detector authority"),
    ),
)
def test_authenticated_task0_candidate_context_fails_closed(
    tmp_path: Path,
    tamper: str,
    diagnostic: str,
) -> None:
    evaluator = _evaluator()
    discovery = _task0_discovery_from_bare_commit(
        tmp_path / "context",
        payloads={"README.md": b"authenticated candidate\n"},
    )
    workspace = discovery["workspace"]
    tree = discovery["tree"]
    discovery_input = copy.deepcopy(discovery["input"])
    if tamper == "tree":
        tree = "f" * 40
    elif tamper == "workspace":
        workspace = workspace / ".."
    else:
        discovery_input["caller_authored_authority"] = True

    with pytest.raises(evaluator.EvaluatorError, match=diagnostic):
        evaluator.derive_authenticated_task0_bypass_observation(
            candidate_workspace=workspace,
            candidate_tree=tree,
            discovery_input=discovery_input,
        )


@pytest.mark.parametrize(
    "tamper",
    [
        "missing-visible-field",
        "extra-lifecycle-field",
        "candidate-schema",
        "request-binding",
        "result-binding",
        "lifecycle-observation",
        "semantic-config-binding",
        "semantic-input-binding",
        "semantic-seed-binding",
        "semantic-shape",
    ],
)
def test_complete_observation_derivation_fails_closed(
    tmp_path: Path,
    tamper: str,
) -> None:
    evaluator = _evaluator()
    inputs = _synthetic_complete_observation_inputs(tmp_path)
    if tamper == "missing-visible-field":
        inputs["visible_check_result"].pop("copy_digest_after")
    elif tamper == "extra-lifecycle-field":
        inputs["lifecycle_result"]["candidate_claim"] = True
    elif tamper == "candidate-schema":
        inputs["candidate_evidence"]["unexpected"] = True
    elif tamper == "request-binding":
        inputs["lifecycle_request"]["candidate_id"] = "drifted"
    elif tamper == "result-binding":
        inputs["lifecycle_result"]["adapter_result"]["operation_version"] = "drifted"
    elif tamper == "lifecycle-observation":
        inputs["lifecycle_result"]["lifecycle_observations"][0][
            "satisfied"
        ] = False
    elif tamper == "semantic-config-binding":
        inputs["lifecycle_result"]["semantic_report"]["architecture_results"][
            0
        ]["config_digest"] = f"sha256:{98:064x}"
    elif tamper == "semantic-input-binding":
        inputs["lifecycle_result"]["semantic_report"]["architecture_results"][
            0
        ]["input_digest"] = f"sha256:{97:064x}"
    elif tamper == "semantic-seed-binding":
        inputs["lifecycle_result"]["semantic_report"]["architecture_results"][
            0
        ]["seed"] += 1
    else:
        inputs["lifecycle_result"]["semantic_report"]["architecture_results"][
            -1
        ].pop("construction_route")

    if tamper in {
        "semantic-config-binding",
        "semantic-input-binding",
        "semantic-seed-binding",
    }:
        inputs["lifecycle_result"]["lifecycle_observations"] = (
            evaluator.derive_lifecycle_observations(
                semantic_report=inputs["lifecycle_result"]["semantic_report"],
                adapter_process_id=inputs["lifecycle_result"]["adapter_process_id"],
            )
        )

    with pytest.raises(evaluator.EvaluatorError):
        evaluator.derive_complete_observations(**inputs)


@pytest.mark.parametrize(
    "failed_clause",
    (
        "F1-H01-FOCUSED-SUITES",
        "F1-H03-BUILTIN-SIGNATURES",
        "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
        "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
        "F1-H06-STRUCTURAL-ROUNDTRIP",
        "F1-H07-STRUCTURAL-IDENTITY-REJECTION",
        "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY",
        "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
        "F1-H10-OWNERSHIP-BOUNDARY",
    ),
)
def test_complete_observation_derivation_preserves_trusted_product_failures(
    tmp_path: Path,
    failed_clause: str,
) -> None:
    evaluator = _evaluator()
    inputs = _synthetic_complete_observation_inputs(tmp_path)
    if failed_clause == "F1-H01-FOCUSED-SUITES":
        inputs["visible_check_result"]["invocations"][0]["exit_code"] = 1
    elif failed_clause == "F1-H03-BUILTIN-SIGNATURES":
        inputs["registry_report"]["registry_baseline"][0]["parameter_count"] += 1
    elif failed_clause == "F1-H04-ARTIFACT-ERA-COMPATIBILITY":
        false_positive = inputs["artifact_report"]["artifact_eras"][0][
            "architecture_results"
        ][0]
        false_positive.update(
            {
                "diagnostic": None,
                "implementation_identity": "ptycho_torch.model.Control",
                "module_returned": True,
                "strict_load": True,
            }
        )
    else:
        semantic = inputs["lifecycle_result"]["semantic_report"]
        witness = semantic["architecture_results"][-1]
        if failed_clause == "F1-H05-FULL-ARCHITECTURE-LIFECYCLE":
            witness["loss_finite"] = False
        elif failed_clause == "F1-H06-STRUCTURAL-ROUNDTRIP":
            witness["adapter_checkpoint_reload"][
                "structural_values"
            ] = {"es_f1_depth": 3}
        elif failed_clause == "F1-H07-STRUCTURAL-IDENTITY-REJECTION":
            rejection = witness["identity_rejections"]["missing"]["es_f1_depth"]
            rejection.update(
                {
                    "exception_detail_sha256": "sha256:"
                    + hashlib.sha256(b"").hexdigest(),
                    "exception_type": None,
                    "module_returned": True,
                    "rejected": False,
                }
            )
        elif failed_clause == "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY":
            sensitivity = witness["identity_sensitivity"]["es_f1_depth"]
            sensitivity["alternate_observable_digest"] = sensitivity[
                "baseline_observable_digest"
            ]
        elif failed_clause == "F1-H09-CONSTRUCTION-REBUILD-EQUALITY":
            witness["public_implementation"] = "candidate.DifferentImplementation"
        else:
            witness["public_boundary_owners"]["compute_loss"] = (
                "candidate.extension.compute_loss"
            )
        inputs["lifecycle_result"]["lifecycle_observations"] = (
            evaluator.derive_lifecycle_observations(
                semantic_report=semantic,
                adapter_process_id=inputs["lifecycle_result"][
                    "adapter_process_id"
                ],
            )
        )

    observations = evaluator.derive_complete_observations(**inputs)

    expected_failures = {
        failed_clause,
        "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
    }
    assert {
        row["clause_id"] for row in observations if not row["satisfied"]
    } == expected_failures
    dispositions = {
        clause_id: (
            "PRODUCT_DEFECT" if clause_id == failed_clause else "UNRESOLVED"
        )
        for clause_id in expected_failures
    }
    normalized = evaluator.evaluate_observations(
        candidate_claims=_candidate_claims(),
        evaluator_observations=observations,
        dispositions=dispositions,
        frozen_registry=set(task_package.F1_BUILTIN_ARCHITECTURES),
    )
    assert [row["clause_id"] for row in normalized["hard_findings"]] == [
        clause_id
        for clause_id in evaluator.HARD_CLAUSE_IDS
        if clause_id in expected_failures
    ]


def _candidate_copy(tmp_path: Path, *, candidate_id: str) -> Path:
    evaluator = _evaluator()
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    shutil.copy2(CALIBRATION_FIXTURES / "lifecycle_adapter.py", workspace)
    (workspace / "product.txt").write_text("pristine\n", encoding="utf-8")
    evidence = _candidate_claims(candidate_id=candidate_id)
    (workspace / "es_f1_candidate_evidence.json").write_bytes(
        evaluator.canonical_json_bytes(evidence)
    )
    for package in ("ptycho", "ptycho/config", "ptycho_torch", "ptycho_torch/generators"):
        package_path = workspace / package
        package_path.mkdir(parents=True, exist_ok=True)
        (package_path / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "ptycho/config/config.py").write_text(
        "class ModelConfig:\n"
        "    def __init__(self, *, architecture): self.architecture = architecture\n\n"
        "class TrainingConfig:\n"
        "    def __init__(self, *, model): self.model = model\n",
        encoding="utf-8",
    )
    (workspace / "ptycho_torch/generators/registry.py").write_text(
        "_CONSTRUCTORS = {}\n\n"
        "def resolve_generator(config):\n"
        "    architecture = config.model.architecture\n"
        "    constructor = _CONSTRUCTORS.get(architecture)\n"
        "    if constructor is None:\n"
        "        constructor = type('Constructor_' + architecture, (), {})\n"
        "        _CONSTRUCTORS[architecture] = constructor\n"
        "    return constructor()\n",
        encoding="utf-8",
    )
    return workspace


def _lifecycle_request(candidate_id: str, workspace: Path) -> dict[str, object]:
    evaluator = _evaluator()
    evidence = json.loads(
        (workspace / "es_f1_candidate_evidence.json").read_bytes()
    )
    architecture_rows = [
        *evidence["builtin_architectures"],
        evidence["candidate_witness"],
    ]
    architecture_cases, _ = evaluator.build_lifecycle_probe_inputs(
        architecture_rows=architecture_rows,
        seed=20260802,
    )
    return {
        "architecture_cases": architecture_cases,
        "candidate_evidence_path": "es_f1_candidate_evidence.json",
        "candidate_evidence_sha256": "sha256:"
        + hashlib.sha256(
            (workspace / "es_f1_candidate_evidence.json").read_bytes()
        ).hexdigest(),
        "candidate_id": candidate_id,
        "lifecycle_output_dir": ".es-f1/lifecycle",
        "operation_version": "ptychopinn_public_lifecycle.v2",
        "required_lifecycle_stages": list(task_package.F1_LIFECYCLE_STAGES),
        "schema_version": "lifecycle_probe_request.v3",
        "seed": 20260802,
    }


def test_lifecycle_probe_inputs_are_deterministic_and_digest_bound() -> None:
    evaluator = _evaluator()
    evidence = _candidate_claims()
    architecture_rows = [
        *evidence["builtin_architectures"],
        evidence["candidate_witness"],
    ]

    cases, payloads = evaluator.build_lifecycle_probe_inputs(
        architecture_rows=architecture_rows,
        seed=20260802,
    )

    assert [row["architecture_id"] for row in cases] == [
        *task_package.F1_BUILTIN_ARCHITECTURES,
        "es_f1_witness",
    ]
    assert [row["N"] for row in cases] == [
        *(
            128 if architecture_id == "neuralop_uno" else 64
            for architecture_id in task_package.F1_BUILTIN_ARCHITECTURES
        ),
        64,
    ]
    assert len(payloads) == 30
    assert len({binding["path"] for row in cases for binding in (row["config"], row["input"])}) == 30
    for row in cases:
        config_payload = payloads[row["config"]["path"]]
        input_payload = payloads[row["input"]["path"]]
        assert row["config"]["sha256"] == "sha256:" + hashlib.sha256(
            config_payload
        ).hexdigest()
        assert row["input"]["sha256"] == "sha256:" + hashlib.sha256(
            input_payload
        ).hexdigest()
        assert json.loads(config_payload)["schema_version"] == "es-f1-base-config.v1"
        assert json.loads(input_payload)["schema_version"] == "es-f1-cdi-fixture.v1"
        assert json.loads(config_payload)["N"] == row["N"]
        assert json.loads(input_payload)["image_size"] == row["N"]
    assert evaluator.build_lifecycle_probe_inputs(
        architecture_rows=architecture_rows,
        seed=20260802,
    ) == (
        cases,
        payloads,
    )
    alternate_cases, alternate_payloads = evaluator.build_lifecycle_probe_inputs(
        architecture_rows=architecture_rows,
        seed=20260803,
    )
    for row, alternate in zip(cases, alternate_cases, strict=True):
        assert alternate_payloads[alternate["config"]["path"]] == payloads[
            row["config"]["path"]
        ]
        assert alternate_payloads[alternate["input"]["path"]] != payloads[
            row["input"]["path"]
        ]


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        ("missing-built-in", "schema violation"),
        ("duplicate-built-in", "architecture matrix"),
        ("wrong-neuralop-N", "image size"),
        ("wrong-nonneuralop-N", "image size"),
        ("wrong-witness-N", "image size"),
        ("builtin-field-substitution", "built-in structural"),
        ("construction-route-substitution", "public route"),
        ("persisted-route-substitution", "public route"),
        ("candidate-authored-applicability", "schema"),
        ("candidate-authored-authority", "schema"),
    ],
)
def test_lifecycle_package_rejects_matrix_and_authority_before_adapter_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    diagnostic: str,
) -> None:
    evaluator = _evaluator()
    candidate_id = f"preflight-{mutation}"
    workspace = _candidate_copy(tmp_path, candidate_id=candidate_id)
    request = _lifecycle_request(candidate_id, workspace)
    cases = request["architecture_cases"]
    if mutation == "missing-built-in":
        cases.pop(0)
    elif mutation == "duplicate-built-in":
        cases[1] = copy.deepcopy(cases[0])
    elif mutation == "wrong-neuralop-N":
        next(row for row in cases if row["architecture_id"] == "neuralop_uno")[
            "N"
        ] = 64
    elif mutation == "wrong-nonneuralop-N":
        cases[0]["N"] = 128
    elif mutation == "wrong-witness-N":
        cases[-1]["N"] = 128
    elif mutation == "builtin-field-substitution":
        evidence_path = workspace / "es_f1_candidate_evidence.json"
        evidence = json.loads(evidence_path.read_bytes())
        replacement = [
            {"alternate_value": 2, "baseline_value": 1, "name": "fno_width"}
        ]
        evidence["builtin_architectures"][0]["structural_fields"] = replacement
        evidence_path.write_bytes(evaluator.canonical_json_bytes(evidence))
        request["candidate_evidence_sha256"] = "sha256:" + hashlib.sha256(
            evidence_path.read_bytes()
        ).hexdigest()
        cases[0]["structural_fields"] = replacement
    elif mutation in {
        "construction-route-substitution",
        "persisted-route-substitution",
    }:
        evidence_path = workspace / "es_f1_candidate_evidence.json"
        evidence = json.loads(evidence_path.read_bytes())
        route_field = (
            "construction_route"
            if mutation == "construction-route-substitution"
            else "persisted_rebuild_route"
        )
        substituted_route = f"candidate.private.{route_field}"
        evidence["candidate_witness"][route_field] = substituted_route
        evidence_path.write_bytes(evaluator.canonical_json_bytes(evidence))
        request["candidate_evidence_sha256"] = "sha256:" + hashlib.sha256(
            evidence_path.read_bytes()
        ).hexdigest()
        cases[-1][route_field] = substituted_route
    else:
        evidence_path = workspace / "es_f1_candidate_evidence.json"
        evidence = json.loads(evidence_path.read_bytes())
        if mutation == "candidate-authored-applicability":
            evidence["artifact_applicability"] = []
        else:
            evidence["evaluator_observations"] = []
        evidence_path.write_bytes(evaluator.canonical_json_bytes(evidence))
        request["candidate_evidence_sha256"] = "sha256:" + hashlib.sha256(
            evidence_path.read_bytes()
        ).hexdigest()

    def forbidden_adapter(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid lifecycle package reached candidate code")

    monkeypatch.setattr(evaluator.subprocess, "Popen", forbidden_adapter)
    with pytest.raises(evaluator.EvaluatorError, match=diagnostic):
        evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="lifecycle_adapter.py",
            request=request,
            python_executable=Path(sys.executable),
            timeout_seconds=20,
        )


def test_lifecycle_driver_rejects_placeholder_candidate_artifacts(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    candidate_id = "calibration-control"
    workspace = _candidate_copy(tmp_path, candidate_id=candidate_id)
    with pytest.raises(evaluator.EvaluatorError, match="fresh-artifact-reload"):
        evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="lifecycle_adapter.py",
            request=_lifecycle_request(candidate_id, workspace),
            python_executable=Path(sys.executable),
            timeout_seconds=20,
        )


def test_full_matrix_reference_adapter_materializes_only_exact_30_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    candidate_id = "reference-adapter-path-control"
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id=candidate_id,
    )
    adapter = workspace / "scripts/es_f1_lifecycle_adapter.py"
    adapter.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        CALIBRATION_FIXTURES / "full_matrix_reference_adapter.py",
        adapter,
    )
    request = _lifecycle_request(candidate_id, workspace)
    observed: dict[str, Any] = {}

    def stop_after_materialization(**kwargs: Any) -> dict[str, Any]:
        artifacts = kwargs["artifacts"]
        assert list(artifacts) == [
            *task_package.F1_BUILTIN_ARCHITECTURES,
            "es_f1_witness",
        ]
        paths = [
            path
            for architecture_artifacts in artifacts.values()
            for path in architecture_artifacts.values()
        ]
        assert len(paths) == 30
        assert len({path.resolve() for path in paths}) == 30
        assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
        observed["content_digests"] = {
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }
        raise evaluator.EvaluatorError("reference adapter path control complete")

    monkeypatch.setattr(
        evaluator,
        "_verify_adapter_artifacts",
        stop_after_materialization,
    )
    with pytest.raises(
        evaluator.EvaluatorError,
        match="reference adapter path control complete",
    ):
        evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="scripts/es_f1_lifecycle_adapter.py",
            request=request,
            python_executable=python,
            timeout_seconds=30,
        )
    assert len(observed["content_digests"]) == 30


def test_full_matrix_reference_adapter_is_absent_from_provider_visible_inputs() -> None:
    reference_path = (
        "tests/experiments/fixtures/es_f1/full_matrix_reference_adapter.py"
    )
    reference_digest = "sha256:" + hashlib.sha256(
        (REPO / reference_path).read_bytes()
    ).hexdigest()
    profile = json.loads(
        (REPO / "experiments/orc_effectiveness/f1_es/task-profile.json").read_bytes()
    )
    profile_bindings = [
        profile["neutral_brief"],
        profile["visible_check"],
        profile["visible_contract"],
        *profile["visible_schema_bindings"],
    ]
    provider_visible_paths = {
        value
        for binding in profile_bindings
        for key, value in binding.items()
        if key.endswith("path") and isinstance(value, str)
    }
    provider_visible_digests = {
        value
        for binding in profile_bindings
        for key, value in binding.items()
        if key.endswith("sha256") and isinstance(value, str)
    }

    seed = json.loads(
        (REPO / profile["task_seed"]["manifest_path"]).read_bytes()
    )
    seed_rows = seed["visible_assets"]["rows"]
    provider_visible_paths.update(
        value
        for row in seed_rows
        for key, value in row.items()
        if key in {"source_path", "target_path"}
    )
    provider_visible_digests.update(row["sha256"] for row in seed_rows)

    assert reference_path not in provider_visible_paths
    assert reference_digest not in provider_visible_digests


def test_lifecycle_driver_rejects_a_missing_full_matrix_artifact_before_reload(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    candidate_id = "calibration-missing-artifact"
    workspace = _candidate_copy(tmp_path, candidate_id=candidate_id)

    with pytest.raises(evaluator.EvaluatorError, match="missing lifecycle artifact"):
        evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="lifecycle_adapter.py",
            request=_lifecycle_request(candidate_id, workspace),
            python_executable=Path(sys.executable),
            timeout_seconds=20,
        )


def test_lifecycle_candidate_evidence_path_is_request_root_relative(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    candidate_id = "calibration-request-root"
    workspace = _candidate_copy(tmp_path, candidate_id=candidate_id)
    nested_adapter = workspace / "scripts/lifecycle_adapter.py"
    nested_adapter.parent.mkdir(parents=True)
    shutil.copy2(workspace / "lifecycle_adapter.py", nested_adapter)
    decoy = workspace / "scripts/es_f1_candidate_evidence.json"
    decoy.parent.mkdir(parents=True, exist_ok=True)
    decoy.write_bytes(
        evaluator.canonical_json_bytes(
            {
                **json.loads(
                    (workspace / "es_f1_candidate_evidence.json").read_bytes()
                ),
                "candidate_id": "workspace-decoy-must-not-be-read",
            }
        )
    )

    with pytest.raises(evaluator.EvaluatorError, match="fresh-artifact-reload"):
        evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="scripts/lifecycle_adapter.py",
            request=_lifecycle_request(candidate_id, workspace),
            python_executable=Path(sys.executable),
            timeout_seconds=20,
        )


def _real_product_candidate(
    tmp_path: Path, *, candidate_id: str, defect_kind: str = "none"
) -> Path:
    evaluator = _evaluator()
    witness_declaration = _architecture_declaration(
        "es_f1_witness", witness=True
    )
    witness_structural_fields = witness_declaration["structural_fields"]
    assert isinstance(witness_structural_fields, list)
    assert len(witness_structural_fields) == 1
    witness_structural_field = witness_structural_fields[0]
    assert isinstance(witness_structural_field, dict)
    witness_field_name = witness_structural_field["name"]
    witness_baseline_value = witness_structural_field["baseline_value"]
    if type(witness_baseline_value) is bool:
        witness_unsupported_value: object = None
    elif isinstance(witness_baseline_value, (int, float)):
        witness_unsupported_value = 0 if witness_baseline_value != 0 else -1
    elif isinstance(witness_baseline_value, str):
        witness_unsupported_value = "es_f1_unsupported_value"
    else:
        raise AssertionError("calibration witness field has no unsupported value")
    tmp_path.mkdir(parents=True, exist_ok=True)
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    workspace = (tmp_path / "candidate-product").resolve()
    subprocess.run(
        ("git", "clone", "--quiet", "--no-local", str(projection), str(workspace)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    witness_module = workspace / "ptycho_torch/generators/es_f1_witness.py"
    witness_module.write_text(
        '''from __future__ import annotations

import torch

from ptycho_torch.generators.ffno import FfnoGenerator, FfnoGeneratorModule


class EsF1WitnessGeneratorModule(FfnoGeneratorModule):
    def __init__(self, *, es_f1_depth: int, **kwargs):
        if es_f1_depth <= 0:
            raise ValueError("es_f1_depth must be positive")
        super().__init__(**kwargs)
        self.es_f1_depth = int(es_f1_depth)
        self.es_f1_depth_scale = torch.nn.Parameter(
            torch.linspace(1.0, 1.0 + 0.1 * (self.es_f1_depth - 1), self.es_f1_depth)
        )

    def forward(self, value):
        result = super().forward(value)
        scale = self.es_f1_depth_scale.mean()
        if isinstance(result, tuple):
            return tuple(item * scale for item in result)
        return result * scale


class EsF1WitnessGenerator(FfnoGenerator):
    name = "es_f1_witness"
''',
        encoding="utf-8",
    )
    registry = workspace / "ptycho_torch/generators/registry.py"
    registry_extension = '''
from ptycho_torch.generators.es_f1_witness import EsF1WitnessGenerator
_REGISTRY["es_f1_witness"] = EsF1WitnessGenerator
'''
    if defect_kind == "route_disagreement":
        registry_extension = '''
class _EsF1MismatchedWitnessGenerator:
    def __init__(self, config):
        self.config = config

    def build_model(self, pt_configs):
        import copy
        from ptycho_torch.application_factory import build_ptychopinn_from_configs
        mismatched = copy.deepcopy(pt_configs)
        mismatched["model_config"].architecture = "cnn"
        return build_ptychopinn_from_configs(mismatched)

_REGISTRY["es_f1_witness"] = _EsF1MismatchedWitnessGenerator
'''
    elif defect_kind == "witness_registry_constructor_alias":
        registry_extension = '''
from ptycho_torch.generators.ffno import FfnoGenerator
_REGISTRY["es_f1_witness"] = FfnoGenerator
'''
    elif defect_kind == "architecture_owned_boundary":
        registry_extension += '''
from ptycho_torch.model import PtychoPINN_Lightning
_es_f1_shared_compute_loss = PtychoPINN_Lightning.compute_loss
def _es_f1_architecture_owned_compute_loss(self, batch):
    return _es_f1_shared_compute_loss(self, batch)
PtychoPINN_Lightning.compute_loss = _es_f1_architecture_owned_compute_loss
'''
    elif defect_kind == "forbidden_path":
        registry_extension += '''
import os as _es_f1_os
from pathlib import Path as _EsF1Path
if _es_f1_os.environ.get("ES_F1_FRESH_RELOAD") == "1":
    _EsF1Path("/home/ollie/Documents/PtychoPINN/README.md").read_bytes()
'''
    elif defect_kind == "changed_builtin_signature":
        registry_extension += ""
    elif defect_kind == "unknown_identity":
        registry_extension += '\n_REGISTRY["es_f1_unknown_architecture"] = FfnoGenerator\n'
    elif defect_kind == "candidate_local_structural_field":
        registry_extension = '''
class _EsF1CandidateLocalGenerator:
    def __init__(self, config):
        self.config = config

    def build_model(self, pt_configs):
        if pt_configs["model_config"].es_f1_depth <= 0:
            raise RuntimeError("candidate-local depth must be positive")
        return FfnoGenerator(self.config).build_model(pt_configs)

_REGISTRY["es_f1_witness"] = _EsF1CandidateLocalGenerator
'''
    registry.write_text(
        registry.read_text(encoding="utf-8") + registry_extension,
        encoding="utf-8",
    )
    model = workspace / "ptycho_torch/model.py"
    witness_branch = '''if architecture == "es_f1_witness":
        from ptycho_torch.generators.es_f1_witness import EsF1WitnessGeneratorModule

        return EsF1WitnessGeneratorModule(
            **common_kwargs,
            n_blocks=getattr(model_config, "fno_blocks", 4),
            cnn_blocks=getattr(model_config, "fno_cnn_blocks", 2),
            es_f1_depth=getattr(model_config, "es_f1_depth", 2),
        )

    if architecture == "ffno":'''
    model.write_text(
        model.read_text(encoding="utf-8").replace(
            'if architecture == "ffno":',
            witness_branch,
            1,
        ),
        encoding="utf-8",
    )
    config_params = workspace / "ptycho_torch/config_params.py"
    config_text = config_params.read_text(encoding="utf-8")
    assert "    fno_width: int = 32\n" in config_text
    config_params.write_text(
        config_text.replace(
            "    fno_width: int = 32\n",
            "    fno_width: int = 32\n    es_f1_depth: int = 2\n",
            1,
        ),
        encoding="utf-8",
    )
    model_spec = workspace / "ptycho_torch/model_spec.py"
    model_spec_text = model_spec.read_text(encoding="utf-8")
    assert 'CURRENT_MODEL_SPEC_VERSION = "torch-model-spec-v2"' in model_spec_text
    model_spec_text = model_spec_text.replace(
        'CURRENT_MODEL_SPEC_VERSION = "torch-model-spec-v2"',
        'CURRENT_MODEL_SPEC_VERSION = "torch-model-spec-v3"',
        1,
    )
    current_v2_branch = '''        elif schema_version == CURRENT_MODEL_SPEC_VERSION:
            values = dict(model_fields)
'''
    assert model_spec_text.count(current_v2_branch) == 1
    model_spec_text = model_spec_text.replace(
        current_v2_branch,
        '''        elif schema_version == "torch-model-spec-v2":
            values = dict(model_fields)
        elif schema_version == CURRENT_MODEL_SPEC_VERSION:
            values = dict(model_fields)
''',
        1,
    )
    return_anchor = '''        return cls(
            schema_version=CURRENT_MODEL_SPEC_VERSION,
'''
    assert model_spec_text.count(return_anchor) == 1
    model_spec_text = model_spec_text.replace(
        return_anchor,
        '''        if schema_version in {MODEL_SPEC_V1_VERSION, "torch-model-spec-v2"}:
            values.setdefault("es_f1_depth", 2)
        return cls(
            schema_version=CURRENT_MODEL_SPEC_VERSION,
''',
        1,
    )
    model_spec.write_text(model_spec_text, encoding="utf-8")
    model_text = model.read_text(encoding="utf-8")
    checkpoint_migration_anchor = '''        # Handle checkpoint loading: convert dict kwargs back to dataclass instances
        # (Lightning passes saved hyperparameters as dicts during load_from_checkpoint)
'''
    assert model_text.count(checkpoint_migration_anchor) == 1
    model_text = model_text.replace(
        checkpoint_migration_anchor,
        '''        if (
            isinstance(model_spec, dict)
            and model_spec.get("schema_version") == "torch-model-spec-v2"
            and isinstance(model_config, dict)
        ):
            model_config = dict(model_config)
            model_config.setdefault("es_f1_depth", 2)

        # Handle checkpoint loading: convert dict kwargs back to dataclass instances
        # (Lightning passes saved hyperparameters as dicts during load_from_checkpoint)
''',
        1,
    )
    model.write_text(model_text, encoding="utf-8")
    artifact_schema = workspace / "ptycho_torch/artifact_schema.py"
    artifact_schema_text = artifact_schema.read_text(encoding="utf-8")
    unversioned_model_anchor = '''    raw_model = copy.deepcopy(dict(model_config))
    received_model_fields = set(raw_model)
'''
    assert artifact_schema_text.count(unversioned_model_anchor) == 1
    artifact_schema.write_text(
        artifact_schema_text.replace(
            unversioned_model_anchor,
            '''    raw_model = copy.deepcopy(dict(model_config))
    raw_model.setdefault("es_f1_depth", 2)
    received_model_fields = set(raw_model)
''',
            1,
        ),
        encoding="utf-8",
    )
    if defect_kind == "changed_builtin_signature":
        model_text = model.read_text(encoding="utf-8")
        changed_builtin_anchor = (
            "        #Configs\n"
            "        self.model_config = model_config\n"
            "        self.data_config = data_config\n"
            "        self.training_config = training_config\n"
            "        self.inference_config = inference_config\n"
            "        self._ci_mode = (\n"
        )
        assert model_text.count(changed_builtin_anchor) == 1
        model.write_text(
            model_text.replace(
                changed_builtin_anchor,
                "        #Configs\n"
                "        self.model_config = model_config\n"
                "        if model_config.architecture == 'ffno':\n"
                "            self.register_parameter(\n"
                "                '_es_f1_changed_builtin_parameter',\n"
                "                torch.nn.Parameter(torch.zeros(1)),\n"
                "            )\n"
                "        self.data_config = data_config\n"
                "        self.training_config = training_config\n"
                "        self.inference_config = inference_config\n"
                "        self._ci_mode = (\n",
                1,
            ),
            encoding="utf-8",
        )
    if defect_kind == "candidate_local_structural_field":
        model_spec = workspace / "ptycho_torch/model_spec.py"
        model_spec.write_text(
            model_spec.read_text(encoding="utf-8")
            + '''
_es_f1_original_model_spec_post_init = ModelSpec.__post_init__
def _es_f1_model_spec_post_init(self):
    _es_f1_original_model_spec_post_init(self)
    if self.to_model_config().es_f1_depth <= 0:
        raise ValueError("candidate-local depth must be positive")
ModelSpec.__post_init__ = _es_f1_model_spec_post_init
''',
            encoding="utf-8",
        )
    if defect_kind == "same_process_reload":
        model.write_text(
            model.read_text(encoding="utf-8")
            + "\nimport os as _es_f1_os\n_es_f1_os.getpid = lambda: 1\n",
            encoding="utf-8",
        )
    elif defect_kind == "injection_dependent_reload":
        model.write_text(
            model.read_text(encoding="utf-8")
            + '''
@classmethod
def _es_f1_injection_dependent_load(cls, *args, **kwargs):
    raise RuntimeError("calibration reload requires forbidden object injection")
PtychoPINN_Lightning.load_from_checkpoint = _es_f1_injection_dependent_load
''',
            encoding="utf-8",
        )
    if defect_kind == "missing_persisted_builder":
        factory = workspace / "ptycho_torch/application_factory.py"
        factory.write_text(
            factory.read_text(encoding="utf-8")
            + '''
_es_f1_original_build_application = build_ptychopinn_application
def build_ptychopinn_application(model_spec, data_config, training_config, inference_config):
    if model_spec.architecture == "es_f1_witness":
        raise RuntimeError("calibration persisted witness builder is absent")
    return _es_f1_original_build_application(
        model_spec, data_config, training_config, inference_config
    )
''',
            encoding="utf-8",
        )
    artifact_schema = workspace / "ptycho_torch/artifact_schema.py"
    if defect_kind in {
        "missing_identity",
        "extra_identity",
        "unsupported_identity",
    }:
        repairs = {
            "missing_identity": (
                f"model_fields.setdefault({witness_field_name!r}, "
                f"{witness_baseline_value!r})"
            ),
            "extra_identity": (
                'model_fields.pop("es_f1_extra_structural_field", None)'
            ),
            "unsupported_identity": (
                f"model_fields.update({{{witness_field_name!r}: "
                f"{witness_baseline_value!r}}}) if "
                f"{witness_field_name!r} in model_fields and "
                f"model_fields[{witness_field_name!r}] == "
                f"{witness_unsupported_value!r} else None"
            ),
        }
        model_spec = workspace / "ptycho_torch/model_spec.py"
        model_spec.write_text(
            model_spec.read_text(encoding="utf-8")
            + f'''
_es_f1_original_model_spec_from_payload = ModelSpec.from_payload.__func__
@classmethod
def _es_f1_model_spec_from_payload(cls, payload):
    repaired = copy.deepcopy(payload)
    model_fields = repaired.get("model_config", {{}})
    {repairs[defect_kind]}
    return _es_f1_original_model_spec_from_payload(cls, repaired)
ModelSpec.from_payload = _es_f1_model_spec_from_payload
''',
            encoding="utf-8",
        )
    elif defect_kind == "identity_insensitive":
        artifact_schema.write_text(
            artifact_schema.read_text(encoding="utf-8")
            + f'''
_es_f1_original_encode_artifact_identity = encode_artifact_identity
def encode_artifact_identity(
    model_spec,
    data_config,
    training_config,
    inference_config,
    *,
    ci_statistics=None,
):
    payload = _es_f1_original_encode_artifact_identity(
        model_spec,
        data_config,
        training_config,
        inference_config,
        ci_statistics=ci_statistics,
    )
    if model_spec.architecture == {witness_declaration["public_id"]!r}:
        payload["model_spec"]["model_config"][{witness_field_name!r}] = {witness_baseline_value!r}
    return payload
''',
            encoding="utf-8",
        )
    elif defect_kind == "nonlegacy_identity_envelope":
        model_spec = workspace / "ptycho_torch/model_spec.py"
        model_spec.write_text(
            model_spec.read_text(encoding="utf-8")
            + '''
_es_f1_original_model_spec_to_payload = ModelSpec.to_payload
_es_f1_original_model_spec_from_payload = ModelSpec.from_payload.__func__
def _es_f1_model_spec_to_payload(self):
    payload = _es_f1_original_model_spec_to_payload(self)
    payload["es_f1_structural_envelope"] = payload.pop("model_config")
    return payload
@classmethod
def _es_f1_model_spec_from_payload(cls, payload):
    payload = copy.deepcopy(payload)
    if "es_f1_structural_envelope" in payload:
        payload["model_config"] = payload.pop("es_f1_structural_envelope")
    return _es_f1_original_model_spec_from_payload(cls, payload)
ModelSpec.to_payload = _es_f1_model_spec_to_payload
ModelSpec.from_payload = _es_f1_model_spec_from_payload
''',
            encoding="utf-8",
        )
    elif defect_kind == "architecture_local_tagged_union":
        model_spec = workspace / "ptycho_torch/model_spec.py"
        model_spec.write_text(
            model_spec.read_text(encoding="utf-8")
            + '''
_es_f1_original_model_spec_to_payload = ModelSpec.to_payload
_es_f1_original_model_spec_from_payload = ModelSpec.from_payload.__func__
def _es_f1_model_spec_to_payload(self):
    payload = _es_f1_original_model_spec_to_payload(self)
    remaining = payload.pop("model_config")
    architecture = remaining.pop("architecture")
    fno_width = remaining.pop("fno_width")
    fno_modes = remaining.pop("fno_modes")
    if architecture == "es_f1_witness":
        payload["witness_case"] = {
            "witness_kind": architecture,
            "declarations": {"fno_width": fno_width, "fno_modes": fno_modes},
            "distributed": [{"fno_width": fno_width, "fno_modes": fno_modes}],
            "configuration": remaining,
        }
    else:
        payload["representative_case"] = {
            "representative_kind": architecture,
            "positional_identity": [fno_width, fno_modes],
            "configuration": remaining,
        }
    return payload
@classmethod
def _es_f1_model_spec_from_payload(cls, payload):
    payload = copy.deepcopy(payload)
    if "witness_case" in payload:
        case = payload.pop("witness_case")
        if set(case) != {"witness_kind", "declarations", "distributed", "configuration"}:
            raise ValueError("witness case fields are not exact")
        declared = case["declarations"]
        distributed = case["distributed"]
        if set(declared) != {"fno_width", "fno_modes"}:
            raise ValueError("witness declarations are not exact")
        if distributed != [{"fno_width": declared["fno_width"], "fno_modes": declared["fno_modes"]}]:
            raise ValueError("witness declarations are inconsistent")
        remaining = case["configuration"]
        remaining["architecture"] = case["witness_kind"]
        remaining["fno_width"] = declared["fno_width"]
        remaining["fno_modes"] = declared["fno_modes"]
        payload["model_config"] = remaining
    elif "representative_case" in payload:
        case = payload.pop("representative_case")
        if set(case) != {"representative_kind", "positional_identity", "configuration"}:
            raise ValueError("representative case fields are not exact")
        if not isinstance(case["positional_identity"], list) or len(case["positional_identity"]) != 2:
            raise ValueError("representative positional identity is malformed")
        remaining = case["configuration"]
        remaining["architecture"] = case["representative_kind"]
        remaining["fno_width"], remaining["fno_modes"] = case["positional_identity"]
        payload["model_config"] = remaining
    return _es_f1_original_model_spec_from_payload(cls, payload)
ModelSpec.to_payload = _es_f1_model_spec_to_payload
ModelSpec.from_payload = _es_f1_model_spec_from_payload
''',
            encoding="utf-8",
        )
    elif defect_kind in {
        "nested_distributed_identity",
        "absent_declared_identity_binding",
        "ambiguous_declared_identity_binding",
        "absent_architecture_binding",
        "ambiguous_architecture_binding",
    }:
        field_name = (
            "width_identity"
            if defect_kind == "absent_declared_identity_binding"
            else "fno_width"
        )
        secondary_value = (
            "fno_width + 1"
            if defect_kind == "ambiguous_declared_identity_binding"
            else "fno_width"
        )
        validate_distributed = defect_kind == "nested_distributed_identity"
        architecture_field = (
            "architecture_identity"
            if defect_kind == "absent_architecture_binding"
            else "architecture"
        )
        secondary_architecture = (
            "architecture + '_shadow'"
            if defect_kind == "ambiguous_architecture_binding"
            else "architecture"
        )
        model_spec = workspace / "ptycho_torch/model_spec.py"
        model_spec.write_text(
            model_spec.read_text(encoding="utf-8")
            + f'''
_es_f1_original_model_spec_to_payload = ModelSpec.to_payload
_es_f1_original_model_spec_from_payload = ModelSpec.from_payload.__func__
def _es_f1_model_spec_to_payload(self):
    payload = _es_f1_original_model_spec_to_payload(self)
    remaining = payload.pop("model_config")
    architecture = remaining.pop("architecture")
    fno_width = remaining.pop("fno_width")
    fno_modes = remaining.pop("fno_modes")
    payload["es_f1_primary_identity"] = {{
        "route": {{"{architecture_field}": architecture}},
        "structural": {{"{field_name}": fno_width, "fno_modes": fno_modes}},
    }}
    payload["es_f1_secondary_identity"] = {{
        "route": [{{"{architecture_field}": {secondary_architecture}}}],
        "structural": [{{"{field_name}": {secondary_value}, "fno_modes": fno_modes}}],
    }}
    payload["es_f1_remaining_fields"] = remaining
    return payload
@classmethod
def _es_f1_model_spec_from_payload(cls, payload):
    payload = copy.deepcopy(payload)
    if "es_f1_primary_identity" in payload:
        primary = payload.pop("es_f1_primary_identity")
        secondary = payload.pop("es_f1_secondary_identity")
        remaining = payload.pop("es_f1_remaining_fields")
        if {validate_distributed!r}:
            # Deliberately repair one-sided mutations. The evaluator can prove
            # rejection/sensitivity only by mutating every bound occurrence.
            primary_structural = primary["structural"]
            secondary_structural = secondary["structural"][0]
            for field, default in (("fno_width", 4), ("fno_modes", 2)):
                primary_has = field in primary_structural
                secondary_has = field in secondary_structural
                if primary_has != secondary_has:
                    source = primary_structural if primary_has else secondary_structural
                    target = secondary_structural if primary_has else primary_structural
                    target[field] = source[field]
                elif primary_has and primary_structural[field] != secondary_structural[field]:
                    if default in (primary_structural[field], secondary_structural[field]):
                        primary_structural[field] = default
                        secondary_structural[field] = default
            extra = "es_f1_extra_structural_field"
            if (extra in primary_structural) != (extra in secondary_structural):
                primary_structural.pop(extra, None)
                secondary_structural.pop(extra, None)
            primary_route = primary["route"]
            secondary_route = secondary["route"][0]
            if primary_route.get("architecture") != secondary_route.get("architecture"):
                known = next(
                    (
                        value
                        for value in (
                            primary_route.get("architecture"),
                            secondary_route.get("architecture"),
                        )
                        if value in {{"ffno", "es_f1_witness"}}
                    ),
                    None,
                )
                if known is not None:
                    primary_route["architecture"] = known
                    secondary_route["architecture"] = known
            if set(primary) != {{"route", "structural"}}:
                raise ValueError("primary identity fields are not exact")
            if set(secondary) != {{"route", "structural"}}:
                raise ValueError("secondary identity fields are not exact")
            if set(primary["route"]) != {{"architecture"}}:
                raise ValueError("primary route fields are not exact")
            if set(primary["structural"]) != {{"fno_width", "fno_modes"}}:
                raise ValueError("primary structural fields are not exact")
            if secondary["route"] != [
                {{"architecture": primary["route"]["architecture"]}}
            ]:
                raise ValueError("distributed architecture identity is inconsistent")
            if secondary["structural"] != [
                {{
                    "fno_width": primary["structural"]["fno_width"],
                    "fno_modes": primary["structural"]["fno_modes"],
                }}
            ]:
                raise ValueError("distributed structural identity is inconsistent")
        remaining["architecture"] = primary["route"]["{architecture_field}"]
        remaining["fno_width"] = primary["structural"]["{field_name}"]
        remaining["fno_modes"] = primary["structural"]["fno_modes"]
        payload["model_config"] = remaining
    return _es_f1_original_model_spec_from_payload(cls, payload)
ModelSpec.to_payload = _es_f1_model_spec_to_payload
ModelSpec.from_payload = _es_f1_model_spec_from_payload
''',
            encoding="utf-8",
        )
    adapter = workspace / "scripts/es_f1_lifecycle_adapter.py"
    adapter.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CALIBRATION_FIXTURES / "conforming_lifecycle_adapter.py", adapter)
    evidence = _candidate_claims(candidate_id=candidate_id)
    if defect_kind in {
        "architecture_local_tagged_union",
        "nested_distributed_identity",
        "absent_declared_identity_binding",
        "ambiguous_declared_identity_binding",
        "absent_architecture_binding",
        "ambiguous_architecture_binding",
    }:
        evidence["candidate_witness"]["structural_fields"] = [
            {"alternate_value": 8, "baseline_value": 4, "name": "fno_width"},
            {"alternate_value": 3, "baseline_value": 2, "name": "fno_modes"},
        ]
    if defect_kind == "baseline_mismatch":
        evidence["candidate_witness"]["structural_fields"] = [
            {"alternate_value": 8, "baseline_value": 5, "name": "fno_width"}
        ]
    if defect_kind == "route_tamper":
        evidence["candidate_witness"]["construction_route"] = (
            "ptycho_torch.generators.registry.missing_route"
        )
    if defect_kind == "schema_version_drift":
        evidence["unexpected_schema_field"] = True
    (workspace / "es_f1_candidate_evidence.json").write_bytes(
        evaluator.canonical_json_bytes(evidence)
    )
    visible_model_spec_assertion_migrations = {
        "tests/torch/test_model_spec.py": (
            (
                '    assert payload.model_spec.schema_version == "torch-model-spec-v2"\n',
                '    assert payload.model_spec.schema_version == "torch-model-spec-v3"\n',
            ),
        ),
        "tests/torch/test_model_spec_v2.py": (
            (
                '    assert CURRENT_MODEL_SPEC_VERSION == "torch-model-spec-v2"\n',
                '    assert CURRENT_MODEL_SPEC_VERSION == "torch-model-spec-v3"\n',
            ),
            (
                '    assert payload["schema_version"] == "torch-model-spec-v2"\n',
                '    assert payload["schema_version"] == "torch-model-spec-v3"\n',
            ),
            (
                '    assert upgraded.schema_version == "torch-model-spec-v2"\n',
                '    assert upgraded.schema_version == "torch-model-spec-v3"\n',
            ),
            (
                '    assert upgraded.to_payload()["schema_version"] == "torch-model-spec-v2"\n',
                '    assert upgraded.to_payload()["schema_version"] == "torch-model-spec-v3"\n',
            ),
        ),
        "tests/torch/test_artifact_schema.py": (
            (
                '        "torch-model-spec-v2"\n',
                '        "torch-model-spec-v3"\n',
            ),
        ),
        "tests/torch/test_artifact_schema_v2.py": (
            (
                '    assert payload["model_spec"]["schema_version"] == "torch-model-spec-v2"\n',
                '    assert payload["model_spec"]["schema_version"] == "torch-model-spec-v3"\n',
            ),
            (
                '    assert decoded.model_spec.schema_version == "torch-model-spec-v2"\n',
                '    assert decoded.model_spec.schema_version == "torch-model-spec-v3"\n',
            ),
        ),
    }
    for relative_path, replacements in visible_model_spec_assertion_migrations.items():
        test_path = workspace / relative_path
        test_text = test_path.read_text(encoding="utf-8")
        for predecessor, successor in replacements:
            if test_text.count(predecessor) != 1:
                raise AssertionError(
                    f"visible ModelSpec assertion drifted: {relative_path}: "
                    f"{predecessor!r}"
                )
            test_text = test_text.replace(predecessor, successor, 1)
        test_path.write_text(test_text, encoding="utf-8")
    candidate_test = workspace / "tests/torch/test_es_f1_extension_boundary.py"
    candidate_test.write_text(
        '''from ptycho.config.config import ModelConfig, TrainingConfig
from ptycho_torch.generators.registry import resolve_generator


def test_candidate_witness_resolves_through_public_registry():
    config = TrainingConfig(model=ModelConfig(architecture="es_f1_witness"))
    assert resolve_generator(config).__class__.__name__
''',
        encoding="utf-8",
    )
    return workspace


def test_real_product_candidate_passes_exact_visible_invocations(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id="visible-invocation-control",
    )
    visible_checks = json.loads(
        (TASK_ASSETS / "visible-check-manifest.json").read_bytes()
    )

    result = evaluator.run_visible_checks(
        workspace=workspace,
        visible_checks=visible_checks,
    )

    assert [
        (row["invocation_id"], row["exit_code"])
        for row in result["invocations"]
    ] == [
        ("PRE_EDIT_FOCUSED", 0),
        ("CANDIDATE_EXTENSION", 0),
    ]


def test_candidate_product_migrates_historical_v2_model_spec_before_strict_validation(
    tmp_path: Path,
) -> None:
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id="historical-model-spec-migration",
    )
    manifest = json.loads(
        (EVALUATOR_ASSETS / "fixture-manifest.json").read_bytes()
    )
    era = next(
        row
        for row in manifest["artifact_eras"]
        if row["era_id"] == "torch-model-spec-v2"
    )
    historical = (
        Path(manifest["external_fixture_store"]["root"])
        / era["cas_relative_path"]
    )
    code = r'''
import json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from ptycho_torch.artifact_schema import from_json_payload
from ptycho_torch.model_spec import ModelSpec
historical=from_json_payload(json.loads(pathlib.Path(sys.argv[2]).read_bytes()))
migrated=ModelSpec.from_payload(historical).to_payload()
assert migrated["schema_version"]=="torch-model-spec-v3"
assert migrated["model_config"]["es_f1_depth"]==2
migrated["model_config"].pop("es_f1_depth")
try: ModelSpec.from_payload(migrated)
except ValueError as exc: assert "es_f1_depth" in str(exc)
else: raise AssertionError("current candidate ModelSpec accepted a missing witness field")
'''

    process = subprocess.run(
        (str(python), "-I", "-B", "-c", code, str(workspace), str(historical)),
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PTYCHO_DISABLE_MEMOIZE": "1",
        },
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert process.returncode == 0, process.stderr


@pytest.mark.parametrize(
    "defect_kind,scenario",
    (
        ("missing_identity", "missing"),
        ("extra_identity", "extra"),
        ("unknown_identity", "unknown"),
        ("unsupported_identity", "unsupported"),
        ("identity_insensitive", "insensitive"),
    ),
)
def test_structural_identity_calibration_fault_targets_declared_witness_field(
    tmp_path: Path,
    defect_kind: str,
    scenario: str,
) -> None:
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    workspace = _real_product_candidate(
        tmp_path / defect_kind,
        candidate_id=f"calibration-{defect_kind}",
        defect_kind=defect_kind,
    )
    manifest = json.loads(
        (EVALUATOR_ASSETS / "fixture-manifest.json").read_bytes()
    )
    era = next(
        row
        for row in manifest["artifact_eras"]
        if row["era_id"] == "torch-artifact-v2"
    )
    historical = (
        Path(manifest["external_fixture_store"]["root"])
        / era["cas_relative_path"]
    )
    code = r'''
import copy,json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from ptycho_torch.artifact_schema import (
    decode_artifact_identity,
    encode_artifact_identity,
    from_json_payload,
    to_json_payload,
)
from ptycho.config.config import ModelConfig as CanonicalModelConfig
from ptycho.config.config import TrainingConfig as CanonicalTrainingConfig
from ptycho_torch.generators.registry import resolve_generator
from ptycho_torch.model_spec import ModelSpec
scenario=sys.argv[3]
historical=from_json_payload(json.loads(pathlib.Path(sys.argv[2]).read_bytes()))
decoded=decode_artifact_identity(historical)
baseline=decoded.model_spec.to_payload()
baseline["model_config"]["architecture"]="es_f1_witness"
baseline=ModelSpec.from_payload(baseline).to_payload()
mutated=copy.deepcopy(baseline)
if scenario=="missing":
    mutated["model_config"].pop("es_f1_depth")
    assert ModelSpec.from_payload(mutated).to_payload()==baseline
elif scenario=="extra":
    mutated["model_config"]["es_f1_extra_structural_field"]=1
    assert ModelSpec.from_payload(mutated).to_payload()==baseline
elif scenario=="unknown":
    config=CanonicalTrainingConfig(
        model=CanonicalModelConfig(architecture="es_f1_unknown_architecture")
    )
    assert resolve_generator(config).__class__.__name__
elif scenario=="unsupported":
    mutated["model_config"]["es_f1_depth"]=0
    assert ModelSpec.from_payload(mutated).to_payload()==baseline
elif scenario=="insensitive":
    mutated["model_config"]["es_f1_depth"]=3
    assert ModelSpec.from_payload(mutated).to_payload()["model_config"]["es_f1_depth"]==3
    baseline_identity=to_json_payload(encode_artifact_identity(
        ModelSpec.from_payload(baseline),
        decoded.data_config,
        decoded.training_config,
        decoded.inference_config,
    ))
    alternate_identity=to_json_payload(encode_artifact_identity(
        ModelSpec.from_payload(mutated),
        decoded.data_config,
        decoded.training_config,
        decoded.inference_config,
    ))
    assert alternate_identity==baseline_identity
else:
    raise AssertionError(f"unknown scenario: {scenario}")
'''

    process = subprocess.run(
        (
            str(python),
            "-I",
            "-B",
            "-c",
            code,
            str(workspace),
            str(historical),
            scenario,
        ),
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PTYCHO_DISABLE_MEMOIZE": "1",
        },
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert process.returncode == 0, process.stderr


def test_real_registry_constructor_alias_fails_h09_before_candidate_adapter(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    candidate_id = "registry-constructor-alias"
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id=candidate_id,
        defect_kind="witness_registry_constructor_alias",
    )
    (workspace / "scripts/es_f1_lifecycle_adapter.py").write_text(
        "raise RuntimeError('registry alias must fail before adapter execution')\n",
        encoding="utf-8",
    )

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="scripts/es_f1_lifecycle_adapter.py",
            request=_lifecycle_request(candidate_id, workspace),
            python_executable=python,
            timeout_seconds=30,
        )

    assert caught.value.clause_id == "F1-H09-CONSTRUCTION-REBUILD-EQUALITY"
    assert caught.value.mechanism == "registry-constructor-identity-alias"
    identities = caught.value.evidence_record["registry_constructor_identities"]
    assert identities["es_f1_witness"] == identities["ffno"]


def test_real_product_lifecycle_is_evaluator_observed_through_public_apis(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    candidate_id = "calibration-public-control"
    workspace = _real_product_candidate(tmp_path, candidate_id=candidate_id)
    request = _lifecycle_request(candidate_id, workspace)

    result = evaluator.run_lifecycle_adapter(
        workspace=workspace,
        adapter_path="scripts/es_f1_lifecycle_adapter.py",
        request=request,
        python_executable=python,
        timeout_seconds=240,
    )

    report = result["semantic_report"]
    assert report["schema_version"] == "es-f1-semantic-lifecycle.v2"
    assert report["construction_pid"] != result["adapter_process_id"]
    architecture_rows = report["architecture_results"]
    assert [row["architecture_id"] for row in architecture_rows] == [
        *task_package.F1_BUILTIN_ARCHITECTURES,
        "es_f1_witness",
    ]
    assert "roles" not in report
    assert "identity_rejections" not in report
    for observed, declaration in zip(
        architecture_rows,
        [
            *_candidate_claims()["builtin_architectures"],
            _candidate_claims()["candidate_witness"],
        ],
        strict=True,
    ):
        field_names = {
            field["name"] for field in declaration["structural_fields"]
        }
        rejections = observed["identity_rejections"]
        assert set(rejections["missing"]) == field_names
        assert all(row["rejected"] for row in rejections["missing"].values())
        assert rejections["extra"]["rejected"] is True
        assert rejections["unsupported_value"]["rejected"] is True
        for row in (
            *rejections["missing"].values(),
            rejections["extra"],
            rejections["unsupported_value"],
        ):
            assert row["module_returned"] is False
            assert isinstance(row["exception_type"], str) and row["exception_type"]
            assert row["exception_detail_sha256"].startswith("sha256:")
        assert set(observed["identity_sensitivity"]) == field_names
        assert all(
            sensitivity["deterministic"] is True
            and sensitivity["baseline_identity_digest"]
            != sensitivity["alternate_identity_digest"]
            for sensitivity in observed["identity_sensitivity"].values()
        )
        assert observed["public_implementation"] == (
            observed["persisted_implementation"]
        )
        assert observed["public_state_signature"] == (
            observed["persisted_state_signature"]
        )
        assert observed["loss_finite"] is True
        assert observed["optimizer_state_before"] != observed["optimizer_state_after"]
        expected_structural = {
            field["name"]: field["baseline_value"]
            for field in declaration["structural_fields"]
        }
        assert observed["structural_values"] == expected_structural
        for reload_name in (
            "evaluator_checkpoint_reload",
            "evaluator_bundle_reload",
            "adapter_checkpoint_reload",
            "adapter_bundle_reload",
        ):
            reload = observed[reload_name]
            assert reload["fresh_pid"] != report["construction_pid"]
            assert reload["structural_values"] == expected_structural
    unknown_rejection = report["unknown_architecture_rejection"]
    assert unknown_rejection["rejected"] is True
    assert unknown_rejection["module_returned"] is False
    assert isinstance(unknown_rejection["exception_type"], str)
    assert unknown_rejection["exception_detail_sha256"].startswith("sha256:")
    observations = {
        row["clause_id"]: row for row in result["lifecycle_observations"]
    }
    assert set(observations) == set(evaluator.HARD_CLAUSE_IDS[4:])
    assert all(row["satisfied"] is True for row in observations.values())
    assert all(row["evidence"] for row in observations.values())

    fixture_manifest = evaluator.load_controller_asset(
        EVALUATOR_ASSETS / "fixture-manifest.json",
        expected_schema_version="es-f1-fixture-manifest.v2",
    )
    visible_checks = evaluator.load_controller_asset(
        TASK_ASSETS / "visible-check-manifest.json",
        expected_schema_version="es_f1_visible_checks.v2",
    )
    visible_result = evaluator.run_visible_checks(
        workspace=workspace,
        visible_checks=visible_checks,
    )
    registry_report = evaluator.run_registry_signature_probe(
        workspace=workspace,
        python_executable=python,
        expected_registry_baseline=fixture_manifest["registry_baseline"],
        timeout_seconds=180,
    )
    artifact_report = evaluator.verify_artifact_fixture_pack(
        workspace=workspace,
        python_executable=python,
        fixture_manifest=fixture_manifest,
        candidate_evidence_path=(workspace / "es_f1_candidate_evidence.json"),
        timeout_seconds=180,
    )
    task0_candidate = _task0_discovery_from_bare_commit(
        tmp_path / "task0-real-product",
        source_workspace=workspace,
    )
    complete = evaluator.derive_complete_observations(
        visible_checks=visible_checks,
        visible_check_result=visible_result,
        candidate_evidence=json.loads(
            (workspace / "es_f1_candidate_evidence.json").read_bytes()
        ),
        lifecycle_request=request,
        lifecycle_result=result,
        fixture_manifest=fixture_manifest,
        candidate_workspace=task0_candidate["workspace"],
        candidate_tree=task0_candidate["tree"],
        legacy_bypass_discovery_input=task0_candidate["input"],
        registry_report=registry_report,
        artifact_report=artifact_report,
    )
    assert [row["clause_id"] for row in complete] == list(evaluator.HARD_CLAUSE_IDS)
    assert {
        row["clause_id"] for row in complete if not row["satisfied"]
    } == {"F1-H05-FULL-ARCHITECTURE-LIFECYCLE"}


def test_architecture_extension_cannot_own_public_scientific_boundary(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    candidate_id = "calibration-architecture_owned_boundary"
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id=candidate_id,
        defect_kind="architecture_owned_boundary",
    )

    result = evaluator.run_lifecycle_adapter(
        workspace=workspace,
        adapter_path="scripts/es_f1_lifecycle_adapter.py",
        request=_lifecycle_request(candidate_id, workspace),
        python_executable=python,
        timeout_seconds=240,
    )

    observations = {
        row["clause_id"]: row["satisfied"]
        for row in result["lifecycle_observations"]
    }
    assert {clause for clause, satisfied in observations.items() if not satisfied} == {
        "F1-H10-OWNERSHIP-BOUNDARY"
    }
    architecture_rows = result["semantic_report"]["architecture_results"]
    assert len(architecture_rows) == 15
    assert all(
        row["persisted_boundary_owners"]["compute_loss"].startswith(
            "ptycho_torch.generators.registry."
        )
        for row in architecture_rows
    )


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ("operation-drift", "schema"),
        ("mutate-copy", "attempted to mutate"),
        ("forbidden-import", "forbidden import"),
        ("forbidden-path", "forbidden path"),
        ("pass-bit", "schema"),
    ],
)
def test_lifecycle_driver_rejects_nonfresh_mutating_or_excluded_behavior(
    tmp_path: Path,
    scenario: str,
    message: str,
) -> None:
    evaluator = _evaluator()
    candidate_id = f"calibration-{scenario}"
    workspace = _candidate_copy(tmp_path, candidate_id=candidate_id)
    with pytest.raises(evaluator.EvaluatorError, match=message):
        evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="lifecycle_adapter.py",
            request=_lifecycle_request(candidate_id, workspace),
            python_executable=Path(sys.executable),
            timeout_seconds=20,
        )


def test_adapter_wrapper_bootstraps_outside_candidate_before_imports(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    candidate_id = "calibration-adapter-bootstrap"
    workspace = _candidate_copy(tmp_path, candidate_id=candidate_id)
    sentinel = (tmp_path / "adapter-pre-audit-shadow.txt").resolve()
    (workspace / "platform.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('shadowed', encoding='utf-8')\n"
        "def processor(): return 'shadowed'\n",
        encoding="utf-8",
    )

    with pytest.raises(evaluator.EvaluatorObservationError):
        evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="lifecycle_adapter.py",
            request=_lifecycle_request(candidate_id, workspace),
            python_executable=Path(sys.executable),
            timeout_seconds=20,
        )

    assert not sentinel.exists()


def test_adapter_wrapper_rejects_restored_byte_product_swap(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    candidate_id = "calibration-adapter-restored-swap"
    workspace = _candidate_copy(tmp_path, candidate_id=candidate_id)
    adapter = workspace / "lifecycle_adapter.py"
    source = adapter.read_text(encoding="utf-8")
    anchor = "os.chdir(Path(__file__).resolve().parent)\n"
    assert source.count(anchor) == 1
    adapter.write_text(
        source.replace(
            anchor,
            anchor
            + "product = Path('product.txt')\n"
            + "backup = Path(args.result).parent / 'product.original'\n"
            + "replacement = Path(args.result).parent / 'product.replacement'\n"
            + "replacement.write_text('replacement\\n', encoding='utf-8')\n"
            + "product.rename(backup)\n"
            + "replacement.rename(product)\n"
            + "product.rename(replacement)\n"
            + "backup.rename(product)\n",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="lifecycle_adapter.py",
            request=_lifecycle_request(candidate_id, workspace),
            python_executable=Path(sys.executable),
            timeout_seconds=20,
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "adapter-mutation-audit"
    assert (workspace / "product.txt").read_text(encoding="utf-8") == "pristine\n"


@pytest.mark.parametrize(
    "probe_label",
    (
        "registry signature probe",
        "artifact fixture verification",
        "semantic lifecycle",
        "fresh artifact verification",
    ),
)
def test_projection_subprocess_audits_forbidden_live_source_reads(
    tmp_path: Path,
    probe_label: str,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()

    with pytest.raises(
        evaluator.EvaluatorObservationError,
        match="candidate-process-path-audit",
    ) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            python_executable=Path(sys.executable),
            code=(
                "from pathlib import Path\n"
                "Path('/home/ollie/Documents/PtychoPINN/README.md').read_bytes()\n"
            ),
            environment={},
            timeout_seconds=20,
            label=probe_label,
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"


def test_projection_wrapper_bootstraps_outside_candidate_before_imports(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    sentinel = (tmp_path / "pre-audit-shadow-import.txt").resolve()
    (workspace / "platform.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('shadowed', encoding='utf-8')\n"
        "def processor(): return 'shadowed'\n",
        encoding="utf-8",
    )

    evaluator._run_projection_probe(
        workspace=workspace,
        python_executable=Path(sys.executable),
        code="pass\n",
        environment={"PYTHONPATH": str(workspace)},
        timeout_seconds=20,
        label="external bootstrap import",
    )

    assert not sentinel.exists()


@pytest.mark.parametrize(
    "operation",
    (
        "os.rename(existing, scratch / 'renamed')",
        "os.replace(scratch_file, workspace / 'replaced')",
        "os.remove(existing)",
        "existing.unlink()",
        "os.link(existing, scratch / 'hard-link')",
        "os.link(scratch_file, workspace / 'hard-link')",
        "os.symlink(existing, scratch / 'symbolic-link')",
        "os.mkdir(workspace / 'new-directory')",
        "os.rmdir(empty_dir)",
        "os.chmod(existing, 0o600)",
        "os.chown(existing, os.getuid(), os.getgid())",
        "os.utime(existing, None)",
        "os.truncate(existing, 0)",
        "fd = os.open(existing, os.O_RDONLY); os.ftruncate(fd, 0); os.close(fd)",
        "os.setxattr(existing, b'user.es_f1', b'value')",
        (
            "fd = os.open(workspace, os.O_RDONLY); "
            "os.rename('existing.txt', 'renamed.txt', src_dir_fd=fd, dst_dir_fd=fd); "
            "os.close(fd)"
        ),
    ),
)
def test_projection_subprocess_rejects_each_protected_path_mutation(
    tmp_path: Path,
    operation: str,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    existing = workspace / "existing.txt"
    existing.write_text("original\n", encoding="utf-8")
    empty_dir = workspace / "empty-directory"
    empty_dir.mkdir()
    scratch = (tmp_path / "external-scratch").resolve()
    scratch.mkdir()
    scratch_file = scratch / "scratch.txt"
    scratch_file.write_text("scratch\n", encoding="utf-8")

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            python_executable=Path(sys.executable),
            code=(
                "import os\n"
                "from pathlib import Path\n"
                f"workspace=Path({str(workspace)!r})\n"
                f"existing=Path({str(existing)!r})\n"
                f"empty_dir=Path({str(empty_dir)!r})\n"
                f"scratch=Path({str(scratch)!r})\n"
                f"scratch_file=Path({str(scratch_file)!r})\n"
                f"{operation}\n"
            ),
            environment={},
            timeout_seconds=20,
            label="protected mutation event",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-mutation-audit"


def test_projection_subprocess_allows_python_path_mutations_in_external_scratch(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    scratch = (tmp_path / "external-scratch").resolve()
    scratch.mkdir()

    evaluator._run_projection_probe(
        workspace=workspace,
        python_executable=Path(sys.executable),
        code=(
            "import os\n"
            "from pathlib import Path\n"
            "root=Path(os.environ['ES_F1_EXTERNAL_SCRATCH'])\n"
            "source=root/'source'; source.write_text('payload',encoding='utf-8')\n"
            "renamed=root/'renamed'; os.rename(source,renamed)\n"
            "replaced=root/'replaced'; replaced.write_text('old',encoding='utf-8')\n"
            "os.replace(renamed,replaced)\n"
            "hard=root/'hard'; os.link(replaced,hard); hard.unlink()\n"
            "symbolic=root/'symbolic'; os.symlink(replaced,symbolic); symbolic.unlink()\n"
            "directory=root/'directory'; os.mkdir(directory); os.rmdir(directory)\n"
            "os.chmod(replaced,0o600); os.chown(replaced,os.getuid(),os.getgid())\n"
            "os.utime(replaced,None); os.truncate(replaced,1)\n"
            "fd=os.open(replaced,os.O_RDWR); os.ftruncate(fd,0); os.close(fd)\n"
            "os.setxattr(replaced,b'user.es_f1',b'value')\n"
            "os.removexattr(replaced,b'user.es_f1')\n"
            "replaced.unlink()\n"
        ),
        environment={"ES_F1_EXTERNAL_SCRATCH": str(scratch)},
        timeout_seconds=20,
        label="external scratch mutation control",
    )

    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize(
    "code",
    (
        (
            "import subprocess, sys\n"
            "subprocess.run([\n"
            "    sys.executable, '-c',\n"
            "    \"from pathlib import Path; "
            "Path('/home/ollie/Documents/PtychoPINN/README.md').read_bytes()\",\n"
            "], check=True)\n"
        ),
        "import subprocess\nsubprocess.run(['/bin/sh', '-c', 'true'], check=True)\n",
        "import os\nos.system('true')\n",
    ),
    ids=("child-forbidden-live-path", "alternate-binary", "os-system"),
)
def test_projection_subprocess_rejects_unaudited_child_processes(
    tmp_path: Path,
    code: str,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            python_executable=Path(sys.executable),
            code=code,
            environment={},
            timeout_seconds=20,
            label="transitive candidate-process audit",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"


def test_projection_subprocess_denial_prevents_external_child_side_effect(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    sentinel = (tmp_path / "child-side-effect.txt").resolve()
    child = (
        "from pathlib import Path; "
        f"Path({str(sentinel)!r}).write_text('escaped', encoding='utf-8')"
    )

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            python_executable=Path(sys.executable),
            code=(
                "import subprocess,sys\n"
                f"subprocess.run([sys.executable,'-c',{child!r}],check=True)\n"
            ),
            environment={},
            timeout_seconds=20,
            label="external child side-effect denial",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"
    assert not sentinel.exists()


def test_projection_subprocess_allows_exact_once_bound_audited_child(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()
    result = child_root / "result.txt"
    sentinel = (tmp_path / "nested-pre-audit-shadow.txt").resolve()
    (workspace / "platform.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('shadowed', encoding='utf-8')\n"
        "def processor(): return 'shadowed'\n",
        encoding="utf-8",
    )
    child_code = (
        "import platform\n"
        "from pathlib import Path\n"
        f"Path({str(result)!r}).write_text(str(Path.cwd()),encoding='utf-8')\n"
    )

    evaluator._run_projection_probe(
        workspace=workspace,
        controlled_child_root=child_root,
        controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
        controlled_child_environment_updates={
            ("expected-program.py", "expected-audit.json"): {}
        },
        python_executable=Path(sys.executable),
        code=(
            "import json,os,pathlib,subprocess,sys\n"
            "root=pathlib.Path(os.environ['ES_F1_CONTROLLED_CHILD_ROOT'])\n"
            "program=root/'expected-program.py'\n"
            "audit=root/'expected-audit.json'\n"
            "program.write_text(os.environ['ES_F1_CHILD_CODE'],encoding='utf-8')\n"
            "spec=json.loads(os.environ['ES_F1_CONTROLLED_CHILD_SPECS'])[str(program)]\n"
            "env=dict(os.environ); env.update(spec['environment_updates'])\n"
            "subprocess.run([sys.executable,'-B','-c',"
            "os.environ['ES_F1_NESTED_WRAPPER'],"
            "os.environ['ES_F1_PROTECTED_ROOTS'],str(program),str(audit),"
            "os.environ['ES_F1_WORKSPACE'],spec['cwd']],"
            "cwd=spec['cwd'],env=env,check=True)\n"
        ),
        environment={
            "ES_F1_CHILD_CODE": child_code,
            "ES_F1_NESTED_WRAPPER": "raise SystemExit(99)",
            "ES_F1_PROTECTED_ROOTS": "[]",
            "ES_F1_CONTROLLED_CHILD_ROOT": str(workspace),
            "ES_F1_CONTROLLED_CHILD_SHA256": "candidate-substitution",
        },
        timeout_seconds=20,
        label="exact controlled audited child",
    )

    child_cwd = Path(result.read_text(encoding="utf-8"))
    assert not child_cwd.is_relative_to(workspace)
    assert child_cwd.name.startswith(".evaluator-bootstrap-")
    assert not sentinel.exists()


def _controlled_child_launch_code(environment_setup: str) -> str:
    return (
        "import json,os,pathlib,subprocess,sys\n"
        "root=pathlib.Path(os.environ['ES_F1_CONTROLLED_CHILD_ROOT'])\n"
        "program=root/'expected-program.py'\n"
        "audit=root/'expected-audit.json'\n"
        "program.write_text(os.environ['ES_F1_CHILD_CODE'],encoding='utf-8')\n"
        "spec=json.loads(os.environ['ES_F1_CONTROLLED_CHILD_SPECS'])[str(program)]\n"
        "env=dict(os.environ); env.update(spec['environment_updates'])\n"
        "argv=[sys.executable,'-B','-c',os.environ['ES_F1_NESTED_WRAPPER'],"
        "os.environ['ES_F1_PROTECTED_ROOTS'],str(program),str(audit),"
        "os.environ['ES_F1_WORKSPACE'],spec['cwd']]\n"
        "child_executable=sys.executable\n"
        "child_cwd=spec['cwd']\n"
        "child_env=env\n"
        f"{environment_setup}"
        "subprocess.run(argv,executable=child_executable,"
        "cwd=child_cwd,env=child_env,check=True)\n"
    )


def test_projection_subprocess_rejects_noncanonical_environment_mapping(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()
    result = child_root / "noncanonical-env-result.txt"
    child_code = (
        "import os\n"
        "from pathlib import Path\n"
        f"Path({str(result)!r}).write_text("
        "os.environ['ES_F1_UNAPPROVED'],encoding='utf-8')\n"
    )

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
            controlled_child_environment_updates={
                ("expected-program.py", "expected-audit.json"): {}
            },
            python_executable=Path(sys.executable),
            code=_controlled_child_launch_code(
                "class EqualityMaskingDict(dict):\n"
                "    def __eq__(self,other): return True\n"
                "    def __ne__(self,other): return False\n"
                "child_env=EqualityMaskingDict(child_env)\n"
                "child_env['ES_F1_UNAPPROVED']='reached-child'\n"
            ),
            environment={"ES_F1_CHILD_CODE": child_code},
            timeout_seconds=20,
            label="noncanonical controlled-child environment mapping",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"
    assert not result.exists()


def test_projection_subprocess_rejects_noncanonical_environment_string(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()
    result = child_root / "noncanonical-string-result.txt"
    unapproved_path = "/tmp/es-f1-unapproved-path"
    child_code = (
        "import os\n"
        "from pathlib import Path\n"
        f"Path({str(result)!r}).write_text(os.environ['PATH'],encoding='utf-8')\n"
    )

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
            controlled_child_environment_updates={
                ("expected-program.py", "expected-audit.json"): {}
            },
            python_executable=Path(sys.executable),
            code=_controlled_child_launch_code(
                "class EqualityMaskingString(str):\n"
                "    def __eq__(self,other): return True\n"
                "    __hash__=str.__hash__\n"
                f"child_env['PATH']=EqualityMaskingString({unapproved_path!r})\n"
            ),
            environment={"ES_F1_CHILD_CODE": child_code},
            timeout_seconds=20,
            label="noncanonical controlled-child environment string",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"
    assert not result.exists()


def test_projection_subprocess_rejects_noncanonical_wrapper_argv_string(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()
    result = child_root / "noncanonical-wrapper-result.txt"
    replacement_wrapper = (
        "from pathlib import Path; "
        f"Path({str(result)!r}).write_text('replacement-ran',encoding='utf-8')"
    )

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
            controlled_child_environment_updates={
                ("expected-program.py", "expected-audit.json"): {}
            },
            python_executable=Path(sys.executable),
            code=_controlled_child_launch_code(
                "class EqualityMaskingString(str):\n"
                "    def __eq__(self,other): return True\n"
                "    __hash__=str.__hash__\n"
                f"argv[3]=EqualityMaskingString({replacement_wrapper!r})\n"
            ),
            environment={"ES_F1_CHILD_CODE": "pass\n"},
            timeout_seconds=20,
            label="noncanonical controlled-child wrapper argument",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"
    assert not result.exists()


@pytest.mark.parametrize("argument_index", range(9))
def test_projection_subprocess_rejects_noncanonical_argv_element(
    tmp_path: Path,
    argument_index: int,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
            controlled_child_environment_updates={
                ("expected-program.py", "expected-audit.json"): {}
            },
            python_executable=Path(sys.executable),
            code=_controlled_child_launch_code(
                "class StringSubclass(str): pass\n"
                f"argv[{argument_index}]=StringSubclass(argv[{argument_index}])\n"
            ),
            environment={"ES_F1_CHILD_CODE": "pass\n"},
            timeout_seconds=20,
            label=f"noncanonical controlled-child argv element {argument_index}",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"


@pytest.mark.parametrize(
    "boundary_setup",
    (
            (
                "class StringSubclass(str): pass\n"
                "child_executable=StringSubclass(child_executable)\n"
            ),
            (
                "class ListSubclass(list): pass\n"
                "sys.audit('subprocess.Popen',child_executable,"
                "ListSubclass(argv),child_cwd,child_env)\n"
            ),
        "class StringSubclass(str): pass\nchild_cwd=StringSubclass(child_cwd)\n",
        (
            "class StringSubclass(str): pass\n"
            "path_value=child_env.pop('PATH')\n"
            "child_env[StringSubclass('PATH')]=path_value\n"
        ),
    ),
    ids=("executable", "argv-container", "cwd", "environment-key"),
)
def test_projection_subprocess_rejects_noncanonical_child_boundary_value(
    tmp_path: Path,
    boundary_setup: str,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
            controlled_child_environment_updates={
                ("expected-program.py", "expected-audit.json"): {}
            },
            python_executable=Path(sys.executable),
            code=_controlled_child_launch_code(boundary_setup),
            environment={"ES_F1_CHILD_CODE": "pass\n"},
            timeout_seconds=20,
            label="noncanonical controlled-child boundary value",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"


def test_projection_subprocess_binds_child_executable_before_candidate_code(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
            controlled_child_environment_updates={
                ("expected-program.py", "expected-audit.json"): {}
            },
            python_executable=Path(sys.executable),
            code=_controlled_child_launch_code(
                "alternate=root/'alternate-python'\n"
                "os.symlink(sys.executable,alternate)\n"
                "sys.executable=str(alternate)\n"
                "child_executable=sys.executable\n"
                "argv[0]=sys.executable\n"
            ),
            environment={"ES_F1_CHILD_CODE": "pass\n"},
            timeout_seconds=20,
            label="captured controlled-child executable",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"


@pytest.mark.parametrize(
    "environment_setup",
    (
        "child_env['ES_F1_UNAPPROVED']='added'\n",
        "child_env.pop('PATH')\n",
        "child_env['PATH']='/tmp/es-f1-changed-path'\n",
        "child_env=None\n",
    ),
    ids=("added", "removed", "changed", "none"),
)
def test_projection_subprocess_rejects_nonmatching_child_environment(
    tmp_path: Path,
    environment_setup: str,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
            controlled_child_environment_updates={
                ("expected-program.py", "expected-audit.json"): {}
            },
            python_executable=Path(sys.executable),
            code=_controlled_child_launch_code(environment_setup),
            environment={"ES_F1_CHILD_CODE": "pass\n"},
            timeout_seconds=20,
            label="nonmatching controlled-child environment",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"


@pytest.mark.parametrize(
    "input_kind",
    (
        "environment-mapping",
        "environment-key",
        "environment-value",
        "pairs-outer-tuple",
        "pair-tuple",
        "pair-program",
        "pair-audit",
        "updates-outer-mapping",
        "updates-inner-mapping",
        "updates-key",
        "updates-value",
    ),
)
def test_projection_probe_rejects_noncanonical_parent_capability_input(
    tmp_path: Path,
    input_kind: str,
) -> None:
    evaluator = _evaluator()

    class StringSubclass(str):
        pass

    class TupleSubclass(tuple):
        pass

    class DictSubclass(dict):
        pass

    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()
    pair: tuple[str, str] = ("expected-program.py", "expected-audit.json")
    environment: dict[str, str] = {"ES_F1_CHILD_CODE": "pass\n"}
    updates: dict[tuple[str, str], dict[str, str]] = {
        pair: {"ES_F1_CHILD_VALUE": "expected"}
    }
    if input_kind == "environment-mapping":
        environment = DictSubclass(environment)
    elif input_kind == "environment-key":
        environment = {StringSubclass("ES_F1_CHILD_CODE"): "pass\n"}
    elif input_kind == "environment-value":
        environment = {"ES_F1_CHILD_CODE": StringSubclass("pass\n")}
    elif input_kind == "pair-tuple":
        pair = TupleSubclass(pair)
        updates = {pair: {"ES_F1_CHILD_VALUE": "expected"}}
    elif input_kind == "pair-program":
        pair = (StringSubclass(pair[0]), pair[1])
        updates = {pair: {"ES_F1_CHILD_VALUE": "expected"}}
    elif input_kind == "pair-audit":
        pair = (pair[0], StringSubclass(pair[1]))
        updates = {pair: {"ES_F1_CHILD_VALUE": "expected"}}
    elif input_kind == "updates-outer-mapping":
        updates = DictSubclass(updates)
    elif input_kind == "updates-inner-mapping":
        updates = {pair: DictSubclass(updates[pair])}
    elif input_kind == "updates-key":
        updates = {pair: {StringSubclass("ES_F1_CHILD_VALUE"): "expected"}}
    elif input_kind == "updates-value":
        updates = {pair: {"ES_F1_CHILD_VALUE": StringSubclass("expected")}}
    controlled_pairs = (pair,)
    if input_kind == "pairs-outer-tuple":
        controlled_pairs = TupleSubclass(controlled_pairs)

    with pytest.raises(evaluator.EvaluatorError, match="exact built-in"):
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=controlled_pairs,
            controlled_child_environment_updates=updates,
            python_executable=Path(sys.executable),
            code="pass\n",
            environment=environment,
            timeout_seconds=20,
            label="noncanonical parent capability input",
        )


def test_projection_subprocess_rejects_bound_child_with_substituted_environment(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()
    child_code = "pass\n"

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
            controlled_child_environment_updates={
                ("expected-program.py", "expected-audit.json"): {}
            },
            python_executable=Path(sys.executable),
            code=(
                "import json,os,pathlib,subprocess,sys\n"
                "root=pathlib.Path(os.environ['ES_F1_CONTROLLED_CHILD_ROOT'])\n"
                "program=root/'expected-program.py'\n"
                "audit=root/'expected-audit.json'\n"
                "program.write_text(os.environ['ES_F1_CHILD_CODE'],encoding='utf-8')\n"
                "spec=json.loads(os.environ['ES_F1_CONTROLLED_CHILD_SPECS'])[str(program)]\n"
                "env=dict(os.environ); env.update(spec['environment_updates'])\n"
                "env['ES_F1_SUBSTITUTED_CHILD_FIELD']='candidate-controlled'\n"
                "subprocess.run([sys.executable,'-B','-c',"
                "os.environ['ES_F1_NESTED_WRAPPER'],"
                "os.environ['ES_F1_PROTECTED_ROOTS'],str(program),str(audit),"
                "os.environ['ES_F1_WORKSPACE'],spec['cwd']],"
                "cwd=spec['cwd'],env=env,check=True)\n"
            ),
            environment={"ES_F1_CHILD_CODE": child_code},
            timeout_seconds=20,
            label="substituted controlled-child environment",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"


def test_projection_subprocess_rejects_declared_child_fixed_env_override(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()
    pair = ("expected-program.py", "expected-audit.json")

    with pytest.raises(evaluator.EvaluatorError, match="overrides a fixed field"):
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(pair,),
            controlled_child_environment_updates={
                pair: {"PYTHONPATH": str(workspace)}
            },
            python_executable=Path(sys.executable),
            code="pass\n",
            environment={"ES_F1_CHILD_CODE": "pass\n"},
            timeout_seconds=20,
            label="fixed controlled-child environment",
        )


def test_projection_subprocess_rejects_candidate_minted_wrapper_lookalike(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    workspace = (tmp_path / "candidate").resolve()
    workspace.mkdir()
    child_root = (tmp_path / "controlled-child").resolve()
    child_root.mkdir()
    child_code = "pass\n"

    with pytest.raises(evaluator.EvaluatorObservationError) as caught:
        evaluator._run_projection_probe(
            workspace=workspace,
            controlled_child_root=child_root,
            controlled_child_pairs=(("expected-program.py", "expected-audit.json"),),
            controlled_child_environment_updates={
                ("expected-program.py", "expected-audit.json"): {}
            },
            python_executable=Path(sys.executable),
            code=(
                "import json,os,pathlib,subprocess,sys\n"
                "root=pathlib.Path(os.environ['ES_F1_CONTROLLED_CHILD_ROOT'])\n"
                "program=root/'candidate-lookalike.py'\n"
                "audit=root/'candidate-lookalike-audit.json'\n"
                "program.write_text(os.environ['ES_F1_CHILD_CODE'],encoding='utf-8')\n"
                "spec=next(iter(json.loads(os.environ['ES_F1_CONTROLLED_CHILD_SPECS']).values()))\n"
                "env=dict(os.environ); env.update(spec['environment_updates'])\n"
                "subprocess.run([sys.executable,'-B','-c',"
                "os.environ['ES_F1_NESTED_WRAPPER'],"
                "os.environ['ES_F1_PROTECTED_ROOTS'],str(program),str(audit),"
                "os.environ['ES_F1_WORKSPACE'],spec['cwd']],"
                "cwd=spec['cwd'],env=env,check=True)\n"
            ),
            environment={"ES_F1_CHILD_CODE": child_code},
            timeout_seconds=20,
            label="candidate-minted controlled-wrapper lookalike",
        )

    assert caught.value.clause_id == "F1-H10-OWNERSHIP-BOUNDARY"
    assert caught.value.mechanism == "candidate-process-child-launch-audit"


@pytest.mark.parametrize(
    "case",
    CALIBRATION_CASES,
    ids=[case["case_id"] for case in CALIBRATION_CASES],
)
def test_calibration_matrix_is_complete_and_each_defect_isolated(
    tmp_path: Path,
    case: dict[str, Any],
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    evaluator.validate_calibration_case(case)
    candidate_id = f"calibration-{case['defect_kind']}"
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id=candidate_id,
        defect_kind=str(case["defect_kind"]),
    )
    before = evaluator._workspace_digest(workspace)

    try:
        result = evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="scripts/es_f1_lifecycle_adapter.py",
            request=_lifecycle_request(candidate_id, workspace),
            python_executable=python,
            timeout_seconds=240,
        )
    except evaluator.EvaluatorObservationError as error:
        if case["defect_kind"] == "forbidden_path":
            assert error.mechanism == "nested-candidate-process-audit"
        observations = [
            evaluator.derive_calibration_error_observation(case, error)
        ]
    else:
        observations = result["lifecycle_observations"]
        assert result["copy_digest_before"] == result["copy_digest_after"] == before

    assert evaluator._workspace_digest(workspace) == before
    failed = {
        row["clause_id"] for row in observations if not row["satisfied"]
    }
    assert failed == set(case["intended_failed_clauses"]), case["case_id"]
    assert all(row["evidence"] for row in observations)


def test_calibration_declarations_reject_fact_overrides() -> None:
    evaluator = _evaluator()
    base = {
        "case_id": "bad",
        "defect_kind": "same_process_reload",
        "fact_overrides": {"invented_fact": False},
        "intended_failed_clauses": ["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"],
        "operation_fixture": "public-lifecycle:same_process_reload",
    }
    with pytest.raises(ValueError, match="field set"):
        evaluator.validate_calibration_case(base)


def test_calibration_failure_clause_comes_from_typed_mechanism() -> None:
    evaluator = _evaluator()
    case = next(
        row for row in CALIBRATION_CASES if row["defect_kind"] == "same_process_reload"
    )
    mechanism_error = evaluator.EvaluatorObservationError(
        clause_id="F1-H10-OWNERSHIP-BOUNDARY",
        mechanism="controlled-mechanism",
        evidence={"observed": "boundary-crossing"},
        detail="controlled mechanism observation",
    )

    observation = evaluator.derive_calibration_error_observation(
        case, mechanism_error
    )

    assert observation["clause_id"] == "F1-H10-OWNERSHIP-BOUNDARY"
    with pytest.raises(ValueError, match="typed mechanism"):
        evaluator.derive_calibration_error_observation(
            case, evaluator.EvaluatorError("untyped")
        )


def test_actual_preedit_registry_signatures_match_closed_fixture_manifest(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    workspace = (tmp_path / "preedit").resolve()
    subprocess.run(
        ("git", "clone", "--quiet", "--no-local", str(projection), str(workspace)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    report = evaluator.run_registry_signature_probe(
        workspace=workspace,
        python_executable=python,
        expected_registry_baseline=json.loads(
            (EVALUATOR_ASSETS / "fixture-manifest.json").read_bytes()
        )["registry_baseline"],
        timeout_seconds=180,
    )
    manifest = evaluator.load_controller_asset(
        EVALUATOR_ASSETS / "fixture-manifest.json",
        expected_schema_version="es-f1-fixture-manifest.v2",
    )
    assert report["registry_baseline"] == manifest["registry_baseline"]
    assert report["loaded_forbidden_modules"] == []
    assert report["outside_project_origin_rows"] == []
    assert report["cache_artifacts"] == []


def test_registry_probe_selects_exact_frozen_builtins_and_reports_real_drift(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    expected = json.loads(
        (EVALUATOR_ASSETS / "fixture-manifest.json").read_bytes()
    )["registry_baseline"]

    extension = _real_product_candidate(
        tmp_path / "extension", candidate_id="registry-extension"
    )
    extension_report = evaluator.run_registry_signature_probe(
        workspace=extension,
        python_executable=python,
        expected_registry_baseline=expected,
        timeout_seconds=180,
    )
    extension_observation = evaluator.derive_registry_observation(
        expected_registry_baseline=expected,
        registry_report=extension_report,
    )
    assert extension_observation["satisfied"] is True
    assert [row["architecture"] for row in extension_report["registry_baseline"]] == [
        row["architecture"] for row in expected
    ]

    changed = _real_product_candidate(
        tmp_path / "changed",
        candidate_id="registry-changed-builtin",
        defect_kind="changed_builtin_signature",
    )
    changed_report = evaluator.run_registry_signature_probe(
        workspace=changed,
        python_executable=python,
        expected_registry_baseline=expected,
        timeout_seconds=180,
    )
    changed_observation = evaluator.derive_registry_observation(
        expected_registry_baseline=expected,
        registry_report=changed_report,
    )
    assert changed_observation["satisfied"] is False
    assert [row["architecture"] for row in changed_report["registry_baseline"]] == [
        row["architecture"] for row in expected
    ]


@pytest.mark.parametrize(
    ("scenario", "expected_failed_clause"),
    [
        ("candidate_local_structural_field", None),
        ("nonlegacy_identity_envelope", None),
        ("nested_distributed_identity", None),
        ("architecture_local_tagged_union", None),
        ("route_tamper", "F1-H09-CONSTRUCTION-REBUILD-EQUALITY"),
    ],
)
def test_declared_routes_and_structural_identity_are_representation_independent(
    tmp_path: Path,
    scenario: str,
    expected_failed_clause: str | None,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    candidate_id = f"calibration-{scenario}"
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id=candidate_id,
        defect_kind=scenario,
    )
    before = evaluator._workspace_digest(workspace)

    if expected_failed_clause is not None:
        with pytest.raises(evaluator.EvaluatorObservationError) as caught:
            evaluator.run_lifecycle_adapter(
                workspace=workspace,
                adapter_path="scripts/es_f1_lifecycle_adapter.py",
                request=_lifecycle_request(candidate_id, workspace),
                python_executable=python,
                timeout_seconds=240,
            )
        assert caught.value.clause_id == expected_failed_clause
    else:
        result = evaluator.run_lifecycle_adapter(
            workspace=workspace,
            adapter_path="scripts/es_f1_lifecycle_adapter.py",
            request=_lifecycle_request(candidate_id, workspace),
            python_executable=python,
            timeout_seconds=240,
        )
        assert all(row["satisfied"] for row in result["lifecycle_observations"])
        architecture_rows = {
            row["architecture_id"]: row
            for row in result["semantic_report"]["architecture_results"]
        }
        witness = architecture_rows["es_f1_witness"]
        if scenario == "candidate_local_structural_field":
            assert [field["name"] for field in witness["structural_fields"]] == [
                "es_f1_depth"
            ]
        if scenario == "nested_distributed_identity":
            assert [field["name"] for field in witness["structural_fields"]] == [
                "fno_width",
                "fno_modes",
            ]
            assert set(witness["identity_rejections"]["missing"]) == {
                "fno_width",
                "fno_modes",
            }
            assert all(
                row["rejected"]
                for row in witness["identity_rejections"]["missing"].values()
            )
            assert witness["identity_rejections"]["unsupported_value"][
                "rejected"
            ] is True
            assert all(
                row["deterministic"]
                and row["baseline_identity_digest"]
                != row["alternate_identity_digest"]
                and row["baseline_state_signature"]
                != row["alternate_state_signature"]
                and row["baseline_observable_digest"]
                != row["alternate_observable_digest"]
                for row in witness["identity_sensitivity"].values()
            )
        if scenario == "architecture_local_tagged_union":
            assert witness["structural_values"] == {
                "fno_modes": 2,
                "fno_width": 4,
            }
            for architecture_id in task_package.F1_BUILTIN_ARCHITECTURES:
                builtin = architecture_rows[architecture_id]
                expected = {"architecture": architecture_id}
                assert builtin["structural_values"] == expected
                assert all(
                    builtin[name]["structural_values"] == expected
                    for name in (
                        "evaluator_checkpoint_reload",
                        "evaluator_bundle_reload",
                        "adapter_checkpoint_reload",
                        "adapter_bundle_reload",
                    )
                )
    assert evaluator._workspace_digest(workspace) == before


def _declared_structural_binding_resolver(evaluator: Any) -> Any:
    namespace: dict[str, Any] = {}
    exec(evaluator._DECLARED_STRUCTURAL_BINDING_PROBE, namespace)
    return namespace["declared_structural_binding"]


def test_observed_structural_value_reports_consistent_nonbaseline_value() -> None:
    evaluator = _evaluator()
    namespace: dict[str, Any] = {}
    exec(evaluator._DECLARED_STRUCTURAL_BINDING_PROBE, namespace)

    assert namespace["observed_structural_value"](
        "es_f1_witness",
        {
            "primary": {"es_f1_depth": 3},
            "secondary": [{"es_f1_depth": 3}],
        },
        {"alternate_value": 3, "baseline_value": 2, "name": "es_f1_depth"},
    ) == 3


@pytest.mark.parametrize(
    ("baseline_payload", "alternate_payload", "expected_paths"),
    [
        (
            {
                "representative_case": {
                    "representative_kind": "cnn",
                    "configuration": {},
                }
            },
            {
                "representative_case": {
                    "representative_kind": "cnn-alternate",
                    "configuration": {},
                }
            },
            [("representative_case", "representative_kind")],
        ),
        (
            {
                "primary": {"architecture_identity": "cnn"},
                "secondary": [{"architecture_identity": "cnn"}],
            },
            {
                "primary": {"architecture_identity": "cnn-alternate"},
                "secondary": [{"architecture_identity": "cnn-alternate"}],
            },
            [
                ("primary", "architecture_identity"),
                ("secondary", 0, "architecture_identity"),
            ],
        ),
        (
            {
                "primary": {"architecture": "cnn"},
                "secondary": [{"architecture": "cnn-shadow"}],
            },
            {
                "primary": {"architecture": "cnn-alternate"},
                "secondary": [{"architecture": "cnn-alternate-shadow"}],
            },
            [
                ("primary", "architecture"),
                ("secondary", 0, "architecture"),
            ],
        ),
    ],
)
def test_declared_architecture_binding_uses_authoritative_model_spec_value(
    baseline_payload: dict[str, Any],
    alternate_payload: dict[str, Any],
    expected_paths: list[tuple[str | int, ...]],
) -> None:
    evaluator = _evaluator()
    resolve = _declared_structural_binding_resolver(evaluator)

    paths, value = resolve(
        "cnn",
        baseline_payload,
        {
            "alternate_value": "cnn-alternate",
            "baseline_value": "cnn",
            "name": "architecture",
        },
        alternate_payload,
    )

    assert paths == expected_paths
    assert value == "cnn"


@pytest.mark.parametrize(
    ("payload", "declaration"),
    [
        (
            {"model_config": {"fno_width": 4}},
            {"alternate_value": 8, "baseline_value": 5, "name": "fno_width"},
        ),
        (
            {"model_config": {"width_identity": 4}},
            {"alternate_value": 8, "baseline_value": 4, "name": "fno_width"},
        ),
        (
            {
                "primary": {"fno_width": 4},
                "secondary": [{"fno_width": 5}],
            },
            {"alternate_value": 8, "baseline_value": 4, "name": "fno_width"},
        ),
    ],
)
def test_declared_named_structural_binding_fails_closed(
    payload: dict[str, Any], declaration: dict[str, Any]
) -> None:
    evaluator = _evaluator()
    resolve = _declared_structural_binding_resolver(evaluator)

    with pytest.raises(
        RuntimeError,
        match="declared structural field location is absent or ambiguous",
    ):
        resolve("es_f1_witness", payload, declaration, None)


@pytest.mark.parametrize(
    "scenario",
    ("absent_declared_identity_binding", "ambiguous_declared_identity_binding"),
)
def test_declared_identity_binding_fails_closed_when_absent_or_ambiguous(
    tmp_path: Path,
    scenario: str,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    candidate_id = f"calibration-{scenario}"
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id=candidate_id,
        defect_kind=scenario,
    )
    before = evaluator._workspace_digest(workspace)

    with pytest.raises(
        evaluator.EvaluatorError,
        match="declared structural field location is absent or ambiguous",
    ):
        _run_representation_binding_probe(
            evaluator=evaluator,
            workspace=workspace,
            python_executable=python,
            root=tmp_path,
        )

    assert evaluator._workspace_digest(workspace) == before


def _run_representation_binding_probe(
    *,
    evaluator: Any,
    workspace: Path,
    python_executable: Path,
    root: Path,
) -> dict[str, Any]:
    evidence = json.loads(
        (workspace / "es_f1_candidate_evidence.json").read_bytes()
    )
    architecture_rows = [
        *evidence["builtin_architectures"],
        evidence["candidate_witness"],
    ]
    cases, payloads = evaluator.build_lifecycle_probe_inputs(
        architecture_rows=architecture_rows,
        seed=20_260_802,
    )
    input_root = root / "binding-inputs"
    input_root.mkdir()
    for relative, payload in payloads.items():
        target = input_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    request = _lifecycle_request(evidence["candidate_id"], workspace)
    assert request["architecture_cases"] == cases
    request_path = input_root / "lifecycle-request.json"
    request_path.write_bytes(evaluator.canonical_json_bytes(request))
    synthetic_rows = {
        row["architecture_id"]: row
        for row in _synthetic_full_matrix_semantic_report()[
            "architecture_results"
        ]
    }
    adapter_observations = {
        architecture_id: {
            "checkpoint": row["adapter_checkpoint_reload"],
            "bundle": row["adapter_bundle_reload"],
        }
        for architecture_id, row in synthetic_rows.items()
    }
    return evaluator._run_semantic_lifecycle_probe(
        workspace=workspace,
        python_executable=python_executable,
        candidate_evidence=workspace / "es_f1_candidate_evidence.json",
        request_path=request_path,
        architecture_cases=cases,
        adapter_observations=adapter_observations,
        output_root=root / "binding-output",
        seed=20_260_802,
        timeout_seconds=240,
    )


@pytest.mark.parametrize(
    "scenario",
    ("absent_architecture_binding", "ambiguous_architecture_binding"),
)
def test_public_model_spec_architecture_does_not_require_a_literal_payload_tag(
    tmp_path: Path,
    scenario: str,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    candidate_id = f"calibration-{scenario}"
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id=candidate_id,
        defect_kind=scenario,
    )
    before = evaluator._workspace_digest(workspace)

    result = evaluator.run_lifecycle_adapter(
        workspace=workspace,
        adapter_path="scripts/es_f1_lifecycle_adapter.py",
        request=_lifecycle_request(candidate_id, workspace),
        python_executable=python,
        timeout_seconds=240,
    )

    architecture_ids = [
        row["architecture_id"]
        for row in result["semantic_report"]["architecture_results"]
    ]
    assert architecture_ids == [
        *task_package.F1_BUILTIN_ARCHITECTURES,
        "es_f1_witness",
    ]
    observations = {
        row["clause_id"]: row["satisfied"]
        for row in result["lifecycle_observations"]
    }
    assert observations["F1-H05-FULL-ARCHITECTURE-LIFECYCLE"] is True
    assert observations["F1-H06-STRUCTURAL-ROUNDTRIP"] is True
    assert observations["F1-H09-CONSTRUCTION-REBUILD-EQUALITY"] is True

    assert evaluator._workspace_digest(workspace) == before


def test_declared_structural_baseline_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    candidate_id = "calibration-baseline_mismatch"
    workspace = _real_product_candidate(
        tmp_path,
        candidate_id=candidate_id,
        defect_kind="baseline_mismatch",
    )
    before = evaluator._workspace_digest(workspace)

    with pytest.raises(
        evaluator.EvaluatorError,
        match="declared structural field location is absent or ambiguous",
    ):
        _run_representation_binding_probe(
            evaluator=evaluator,
            workspace=workspace,
            python_executable=python,
            root=tmp_path,
        )

    assert evaluator._workspace_digest(workspace) == before


def test_actual_preedit_representative_completes_production_lifecycle(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    workspace = (tmp_path / "preedit-lifecycle").resolve()
    subprocess.run(
        ("git", "clone", "--quiet", "--no-local", str(projection), str(workspace)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    report = evaluator.run_preedit_representative_lifecycle_probe(
        workspace=workspace,
        python_executable=python,
        output_root=(tmp_path / "probe-output").resolve(),
        timeout_seconds=180,
    )
    assert report["architecture"] == "ffno"
    assert report["public_implementation"] == report["persisted_implementation"]
    assert report["public_state_signature"] == report["persisted_state_signature"]
    assert report["structural_identity"].startswith("sha256:")
    assert report["loss_finite"] is True
    assert report["optimizer_changed_parameter"] is True
    assert report["bundle_persistence_route"] == (
        "ptycho_torch.workflows.components.run_cdi_example_torch"
    )
    assert report["bundle_implementation"] == report["persisted_implementation"]
    assert report["checkpoint_reload"]["fresh_pid"] != report["construction_pid"]
    assert report["bundle_reload"]["fresh_pid"] != report["construction_pid"]
    assert report["checkpoint_reload"]["inference_shape"]
    assert report["bundle_reload"]["inference_shape"]
    assert report["bundle_reload"]["roles"] == ["autoencoder", "diffraction_to_obj"]
    assert report["loaded_forbidden_modules"] == []
    assert report["outside_project_origin_rows"] == []
    assert report["cache_artifacts"] == []


def test_frozen_artifact_era_pack_decodes_and_strict_loads_in_projection(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    projection = Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections/"
        "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
    )
    if not python.is_file() or not projection.is_dir():
        pytest.skip("frozen ptycho311 interpreter or F1 projection unavailable")
    workspace = (tmp_path / "preedit-artifacts").resolve()
    subprocess.run(
        ("git", "clone", "--quiet", "--no-local", str(projection), str(workspace)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    manifest = evaluator.load_controller_asset(
        EVALUATOR_ASSETS / "fixture-manifest.json",
        expected_schema_version="es-f1-fixture-manifest.v2",
    )
    assert [row["era_id"] for row in manifest["artifact_eras"]] == [
        "torch-model-spec-v1",
        "torch-model-spec-v2",
        "torch-artifact-v1",
        "torch-artifact-v2",
        "legacy-config-only-checkpoint",
        "current-model-spec-v2-checkpoint",
        "metadata-free-legacy-bundle",
        "transitional-ci-entrypoints-v1-bundle",
        "torch-artifact-v1-bundle",
        "torch-artifact-v2-bundle",
    ]
    candidate_evidence_path = tmp_path / "es_f1_candidate_evidence.json"
    candidate_evidence_path.write_bytes(
        evaluator.canonical_json_bytes(_candidate_claims())
    )
    report = evaluator.verify_artifact_fixture_pack(
        workspace=workspace,
        python_executable=python,
        fixture_manifest=manifest,
        candidate_evidence_path=candidate_evidence_path,
        timeout_seconds=180,
    )
    assert [row["era_id"] for row in report["artifact_eras"]] == [
        row["era_id"] for row in manifest["artifact_eras"]
    ]
    assert all(
        len(row["architecture_results"]) == 15
        for row in report["artifact_eras"]
    )
    assert all(
        sum(outcome["strict_load"] for outcome in row["architecture_results"])
        == 1
        for row in report["artifact_eras"]
    )
    assert all(
        outcome["diagnostic"] == "UNSUPPORTED_ARTIFACT_ARCHITECTURE"
        and outcome["module_returned"] is False
        for row in report["artifact_eras"]
        for outcome in row["architecture_results"]
        if not outcome["strict_load"]
    )
    assert report["loaded_forbidden_modules"] == []
    assert report["outside_project_origin_rows"] == []
    assert report["cache_artifacts"] == []
