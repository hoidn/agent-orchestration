from __future__ import annotations

import copy
import json
import hashlib
import importlib
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
EVALUATOR_ASSETS = REPO / "experiments/orc_effectiveness/f1_es/evaluator"
CALIBRATION_FIXTURES = REPO / "tests/experiments/fixtures/es_f1"
TASK_ASSETS = REPO / "experiments/orc_effectiveness/f1_es/task"
CALIBRATION_CASES = json.loads(
    (CALIBRATION_FIXTURES / "calibration-cases.json").read_bytes()
)["cases"]


def _evaluator():
    return importlib.import_module("scripts.experiments.es.f1_evaluator")


def test_frozen_controller_vocabularies_and_assets_are_closed() -> None:
    evaluator = _evaluator()
    assert evaluator.HARD_CLAUSE_IDS == (
        "F1-H01-FOCUSED-SUITES",
        "F1-H02-SCHEMA-CONFORMANCE",
        "F1-H03-BUILTIN-SIGNATURES",
        "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
        "F1-H05-NOMINATED-LIFECYCLE",
        "F1-H06-WITNESS-STRUCTURAL-ROUNDTRIP",
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
        expected_schema_version="es-f1-fixture-manifest.v1",
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
        "schema_version": "es-f1-calibration-cases.v2",
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


def _candidate_claims() -> dict[str, object]:
    return {
        "schema_version": "candidate-extension-evidence.v1",
        "candidate_id": "calibration-control",
        "nominated_architectures": {
            "representative": "ffno",
            "witness": "es_f1_witness",
        },
        "structural_fields": [
            {"name": "width", "baseline": 4, "alternate": 8},
        ],
        "claims": [
            {"claim_id": "PUBLIC_CONSTRUCTION", "evidence_path": "tests/control.json"},
        ],
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
                expected_schema_version="es-f1-fixture-manifest.v1",
            )["registry_baseline"]
        },
    )

    assert "candidate_claims" not in result
    assert result["candidate_claims_digest"].startswith("sha256:")
    by_id = {row["clause_id"]: row for row in result["evaluator_observations"]}
    assert by_id["F1-H09-CONSTRUCTION-REBUILD-EQUALITY"]["satisfied"] is False
    assert by_id["F1-H05-NOMINATED-LIFECYCLE"]["satisfied"] is True
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
            "schema_version": "es-f1-hard-finding.v1",
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
    ("representative", "witness", "message"),
    [
        ("not-frozen", "es_f1_witness", "representative"),
        ("ffno", "cnn", "witness"),
        ("ffno", "ffno", "witness"),
    ],
)
def test_architecture_roles_fail_closed(
    representative: str,
    witness: str,
    message: str,
) -> None:
    evaluator = _evaluator()
    claims = _candidate_claims()
    claims["nominated_architectures"] = {
        "representative": representative,
        "witness": witness,
    }
    with pytest.raises(ValueError, match=message):
        evaluator.evaluate_observations(
            candidate_claims=claims,
            evaluator_observations=_observations(),
            dispositions={},
            frozen_registry={"cnn", "ffno"},
        )


def _synthetic_complete_observation_inputs(
    tmp_path: Path,
) -> dict[str, Any]:
    evaluator = _evaluator()
    candidate_id = "calibration-control"
    workspace = _candidate_copy(tmp_path, candidate_id=candidate_id)
    candidate_evidence = json.loads(
        (workspace / "es_f1_candidate_evidence.json").read_bytes()
    )
    request = _lifecycle_request(candidate_id, workspace)
    visible_checks = json.loads(
        (TASK_ASSETS / "visible-check-manifest.json").read_bytes()
    )
    runner = visible_checks["runner"]
    by_id = {row["id"]: row for row in visible_checks["invocations"]}
    copy_digest = f"sha256:{1:064x}"
    visible_result = {
        "schema_version": "es-f1-visible-check-result.v1",
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
    artifact_report = {
        "schema_version": "es-f1-artifact-fixture-verification.v1",
        "artifact_eras": [
            {
                "era_id": row["era_id"],
                "implementation_identity": "ptycho_torch.model.Control",
                "strict_load": True,
            }
            for row in fixture_manifest["artifact_eras"]
        ],
        "loaded_forbidden_modules": [],
        "outside_project_origin_rows": [],
        "cache_artifacts": [],
    }
    owner_contract = {
        "loss_function": "Poisson",
        "measurement_domain": "normalized_amplitude",
        "physics_forward_mode": "amplitude",
        "scale_contract_version": "legacy_v1",
        "torch_loss_mode": "poisson",
    }
    owners = {
        "compute_loss": "ptycho_torch.model.PtychoPINN_Lightning.compute_loss",
        "loss_forward": "ptycho_torch.model.PoissonLoss.forward",
        "model_forward": "ptycho_torch.model.PtychoPINN.forward",
        "physics_forward": "ptycho_torch.model.ForwardModel.forward",
        "scaling": "ptycho_torch.model.IntensityScalerModule.scale",
    }

    def reload(
        *, roles: list[str], pid: int, architecture: str
    ) -> dict[str, object]:
        return {
            "architecture_id": architecture,
            "boundary_contract": owner_contract,
            "boundary_input_digest_after": f"sha256:{8:064x}",
            "boundary_input_digest_before": f"sha256:{8:064x}",
            "boundary_owners": owners,
            "fresh_pid": pid,
            "implementation_identity": "ptycho_torch.model.Control",
            "inference_shape": [1, 1, 64, 64],
            "loaded_forbidden_modules": [],
            "outside_project_origin_rows": [],
            "roles": roles,
            "state_signature": f"sha256:{9:064x}",
            "structural_values": (
                {"fno_width": 4} if architecture == "es_f1_witness" else {}
            ),
        }

    def role(*, architecture: str, pid_offset: int) -> dict[str, object]:
        implementation = "ptycho_torch.model.Control"
        return {
            "architecture_id": architecture,
            "construction_route": (
                "ptycho_torch.generators.registry.resolve_generator"
            ),
            "persisted_rebuild_route": (
                "ptycho_torch.application_factory.build_ptychopinn_application"
            ),
            "boundary_contract": owner_contract,
            "boundary_input_digest_after": f"sha256:{7:064x}",
            "boundary_input_digest_before": f"sha256:{7:064x}",
            "bundle_implementation": implementation,
            "evaluator_bundle_reload": reload(
                roles=["autoencoder", "diffraction_to_obj"],
                pid=310 + pid_offset,
                architecture=architecture,
            ),
            "evaluator_checkpoint_reload": reload(
                roles=[], pid=320 + pid_offset, architecture=architecture
            ),
            "forward_shape": [1, 1, 64, 64],
            "loss_finite": True,
            "optimizer_changed_parameter": True,
            "persisted_boundary_owners": owners,
            "persisted_implementation": implementation,
            "persisted_rebuild_implementation": implementation,
            "persisted_state_signature": f"sha256:{9:064x}",
            "public_boundary_owners": owners,
            "public_implementation": implementation,
            "public_state_signature": f"sha256:{9:064x}",
            "structural_values": (
                {"fno_width": 4} if architecture == "es_f1_witness" else {}
            ),
            "adapter_bundle_reload": reload(
                roles=["autoencoder", "diffraction_to_obj"],
                pid=330 + pid_offset,
                architecture=architecture,
            ),
            "adapter_checkpoint_reload": reload(
                roles=[], pid=340 + pid_offset, architecture=architecture
            ),
        }

    def rejection(detail: str, fragment: str) -> dict[str, object]:
        return {
            "exception_detail_sha256": "sha256:"
            + hashlib.sha256(detail.encode("utf-8")).hexdigest(),
            "exception_type": "ValueError",
            "module_returned": False,
            "rejected": True,
        }

    semantic_report = {
        "schema_version": "es-f1-semantic-lifecycle.v1",
        "construction_pid": 100,
        "declared_structural_fields": ["fno_width"],
        "roles": {
            "representative": role(architecture="ffno", pid_offset=0),
            "witness": role(architecture="es_f1_witness", pid_offset=10),
        },
        "identity_rejections": {
            "missing": {
                "fno_width": rejection(
                    "missing=['fno_width']", "missing=['fno_width']"
                )
            },
            "extra": rejection(
                "unknown=['es_f1_extra_structural_field']",
                "unknown=['es_f1_extra_structural_field']",
            ),
            "unknown_architecture": rejection(
                "Unsupported generator architecture 'es_f1_unknown_architecture'",
                "Unsupported generator architecture 'es_f1_unknown_architecture'",
            ),
            "unsupported_value": rejection(
                "n_blocks must be positive, got 0.",
                "n_blocks must be positive, got 0.",
            ),
        },
        "identity_sensitivity": {
            "fno_width": {
                "alternate_digest": f"sha256:{12:064x}",
                "baseline_digest": f"sha256:{11:064x}",
                "changed": True,
                "deterministic": True,
            }
        },
        "loaded_forbidden_modules": [],
        "outside_project_origin_rows": [],
        "cache_artifacts": [],
    }
    lifecycle_observations = evaluator.derive_lifecycle_observations(
        semantic_report=semantic_report,
        adapter_process_id=200,
    )
    adapter_result = {
        "artifacts": {
            role_name: {
                "bundle_path": f"artifacts/{role_name}/wts.h5.zip",
                "checkpoint_path": f"artifacts/{role_name}/model.ckpt",
            }
            for role_name in ("representative", "witness")
        },
        "candidate_id": candidate_id,
        "operation_version": request["operation_version"],
        "schema_version": "lifecycle_probe_result.v2",
    }
    lifecycle_result = {
        "adapter_result": adapter_result,
        "audit_digest": f"sha256:{13:064x}",
        "copy_digest_after": f"sha256:{14:064x}",
        "copy_digest_before": f"sha256:{14:064x}",
        "adapter_process_id": 200,
        "semantic_observations": {
            role_name: {
                "checkpoint": semantic_report["roles"][role_name][
                    "adapter_checkpoint_reload"
                ],
                "bundle": semantic_report["roles"][role_name][
                    "adapter_bundle_reload"
                ],
            }
            for role_name in ("representative", "witness")
        },
        "semantic_report": semantic_report,
        "lifecycle_observations": lifecycle_observations,
    }
    return {
        "artifact_report": artifact_report,
        "candidate_evidence": candidate_evidence,
        "fixture_manifest": fixture_manifest,
        "lifecycle_request": request,
        "lifecycle_result": lifecycle_result,
        "registry_report": registry_report,
        "visible_check_result": visible_result,
        "visible_checks": visible_checks,
    }


def test_complete_observation_derivation_joins_all_ten_controller_facts(
    tmp_path: Path,
) -> None:
    evaluator = _evaluator()
    inputs = _synthetic_complete_observation_inputs(tmp_path)

    observations = evaluator.derive_complete_observations(**inputs)

    assert [row["clause_id"] for row in observations] == list(
        evaluator.HARD_CLAUSE_IDS
    )
    assert all(row["satisfied"] is True for row in observations)
    assert all(row["evidence"] for row in observations)


@pytest.mark.parametrize(
    "tamper",
    [
        "missing-visible-field",
        "extra-lifecycle-field",
        "candidate-schema",
        "request-binding",
        "result-binding",
        "lifecycle-observation",
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
    else:
        inputs["lifecycle_result"]["semantic_report"]["roles"]["witness"].pop(
            "construction_route"
        )

    with pytest.raises(evaluator.EvaluatorError):
        evaluator.derive_complete_observations(**inputs)


@pytest.mark.parametrize(
    "failed_clause",
    (
        "F1-H01-FOCUSED-SUITES",
        "F1-H03-BUILTIN-SIGNATURES",
        "F1-H04-ARTIFACT-ERA-COMPATIBILITY",
        "F1-H05-NOMINATED-LIFECYCLE",
        "F1-H06-WITNESS-STRUCTURAL-ROUNDTRIP",
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
        inputs["artifact_report"]["artifact_eras"][0]["strict_load"] = False
    else:
        semantic = inputs["lifecycle_result"]["semantic_report"]
        if failed_clause == "F1-H05-NOMINATED-LIFECYCLE":
            semantic["roles"]["witness"]["loss_finite"] = False
        elif failed_clause == "F1-H06-WITNESS-STRUCTURAL-ROUNDTRIP":
            semantic["roles"]["witness"]["adapter_checkpoint_reload"][
                "structural_values"
            ] = {"fno_width": 8}
        elif failed_clause == "F1-H07-STRUCTURAL-IDENTITY-REJECTION":
            rejection = semantic["identity_rejections"]["missing"]["fno_width"]
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
            semantic["identity_sensitivity"]["fno_width"]["changed"] = False
        elif failed_clause == "F1-H09-CONSTRUCTION-REBUILD-EQUALITY":
            semantic["roles"]["witness"]["public_implementation"] = (
                "candidate.DifferentImplementation"
            )
        else:
            semantic["roles"]["witness"]["public_boundary_owners"][
                "compute_loss"
            ] = "candidate.extension.compute_loss"
        inputs["lifecycle_result"]["lifecycle_observations"] = (
            evaluator.derive_lifecycle_observations(
                semantic_report=semantic,
                adapter_process_id=inputs["lifecycle_result"][
                    "adapter_process_id"
                ],
            )
        )

    observations = evaluator.derive_complete_observations(**inputs)

    assert {
        row["clause_id"] for row in observations if not row["satisfied"]
    } == {failed_clause}
    normalized = evaluator.evaluate_observations(
        candidate_claims=_candidate_claims(),
        evaluator_observations=observations,
        dispositions={failed_clause: "PRODUCT_DEFECT"},
        frozen_registry={"cnn", "ffno"},
    )
    assert [row["clause_id"] for row in normalized["hard_findings"]] == [
        failed_clause
    ]


def _candidate_copy(tmp_path: Path, *, candidate_id: str) -> Path:
    evaluator = _evaluator()
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    shutil.copy2(CALIBRATION_FIXTURES / "lifecycle_adapter.py", workspace)
    (workspace / "product.txt").write_text("pristine\n", encoding="utf-8")
    evidence = {
        "architecture_decision_path": "docs/architecture.md",
        "candidate_id": candidate_id,
        "claims": [
            {
                "clause_id": clause_id,
                "evidence_paths": ["product.txt"],
                "scope": "IMPLEMENTED",
            }
            for clause_id in evaluator.HARD_CLAUSE_IDS
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
        "representative_architecture": {
            "construction_route": "ptycho_torch.generators.registry.resolve_generator",
            "frozen_registry_member": True,
            "persisted_rebuild_route": (
                "ptycho_torch.application_factory.build_ptychopinn_application"
            ),
            "public_id": "ffno",
        },
        "schema_version": "candidate_extension_evidence.v1",
        "structural_fields": [
            {"alternate_value": 8, "baseline_value": 4, "name": "fno_width"}
        ],
        "supported_artifact_eras": ["torch-artifact-v1", "torch-artifact-v2"],
        "witness_architecture": {
            "construction_route": "ptycho_torch.generators.registry.resolve_generator",
            "frozen_registry_member": False,
            "persisted_rebuild_route": (
                "ptycho_torch.application_factory.build_ptychopinn_application"
            ),
            "public_id": "es_f1_witness",
        },
    }
    (workspace / "es_f1_candidate_evidence.json").write_bytes(
        evaluator.canonical_json_bytes(evidence)
    )
    return workspace


def _lifecycle_request(candidate_id: str, workspace: Path) -> dict[str, object]:
    evaluator = _evaluator()
    bindings, _ = evaluator.build_lifecycle_probe_inputs(seed=20260802)
    return {
        "candidate_evidence_path": "es_f1_candidate_evidence.json",
        "candidate_evidence_sha256": "sha256:"
        + hashlib.sha256(
            (workspace / "es_f1_candidate_evidence.json").read_bytes()
        ).hexdigest(),
        "candidate_id": candidate_id,
        "evaluator_inputs": bindings,
        "lifecycle_output_dir": ".es-f1/lifecycle",
        "operation_version": "ptychopinn_public_lifecycle.v1",
        "representative_architecture": "ffno",
        "schema_version": "lifecycle_probe_request.v2",
        "seed": 20260802,
        "witness_architecture": "es_f1_witness",
    }


def test_lifecycle_probe_inputs_are_deterministic_and_digest_bound() -> None:
    evaluator = _evaluator()

    bindings, payloads = evaluator.build_lifecycle_probe_inputs(seed=20260802)

    assert bindings == {
        "base_config": {
            "path": "evaluator-inputs/base-config.json",
            "sha256": "sha256:"
            + hashlib.sha256(payloads["base_config"]).hexdigest(),
        },
        "cdi_fixture": {
            "path": "evaluator-inputs/cdi-fixture.json",
            "sha256": "sha256:"
            + hashlib.sha256(payloads["cdi_fixture"]).hexdigest(),
        },
    }
    assert json.loads(payloads["base_config"])["schema_version"] == (
        "es-f1-base-config.v1"
    )
    assert json.loads(payloads["cdi_fixture"])["schema_version"] == (
        "es-f1-cdi-fixture.v1"
    )
    assert evaluator.build_lifecycle_probe_inputs(seed=20260802) == (
        bindings,
        payloads,
    )
    alternate_bindings, alternate_payloads = evaluator.build_lifecycle_probe_inputs(
        seed=20260803
    )
    assert alternate_payloads["base_config"] == payloads["base_config"]
    assert alternate_payloads["cdi_fixture"] != payloads["cdi_fixture"]
    assert alternate_bindings["cdi_fixture"] != bindings["cdi_fixture"]


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
    registry = workspace / "ptycho_torch/generators/registry.py"
    registry_extension = '\n_REGISTRY["es_f1_witness"] = FfnoGenerator\n'
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
    model.write_text(
        model.read_text(encoding="utf-8").replace(
            'if architecture == "ffno":',
            'if architecture in {"ffno", "es_f1_witness"}:',
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
                'model_fields.setdefault("fno_width", 4)'
            ),
            "extra_identity": (
                'model_fields.pop("es_f1_extra_structural_field", None)'
            ),
            "unsupported_identity": (
                'model_fields["fno_width"] = 4 '
                'if model_fields.get("fno_width") == 0 '
                'else model_fields.get("fno_width")'
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
        model_spec = workspace / "ptycho_torch/model_spec.py"
        model_spec.write_text(
            model_spec.read_text(encoding="utf-8")
            + '''
_es_f1_original_model_spec_to_payload = ModelSpec.to_payload
def _es_f1_model_spec_to_payload(self):
    payload = _es_f1_original_model_spec_to_payload(self)
    if payload["model_config"].get("architecture") == "es_f1_witness":
        payload["model_config"]["fno_width"] = 4
    return payload
ModelSpec.to_payload = _es_f1_model_spec_to_payload
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
    evidence = {
        "architecture_decision_path": "docs/architecture_torch.md",
        "candidate_id": candidate_id,
        "claims": [
            {
                "clause_id": clause_id,
                "evidence_paths": ["README.md"],
                "scope": "IMPLEMENTED",
            }
            for clause_id in evaluator.HARD_CLAUSE_IDS
        ],
        "extension_author_guide_path": "docs/architecture_torch.md",
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
            "construction_route": "ptycho_torch.generators.registry.resolve_generator",
            "frozen_registry_member": True,
            "persisted_rebuild_route": (
                "ptycho_torch.application_factory.build_ptychopinn_application"
            ),
            "public_id": "ffno",
        },
        "schema_version": "candidate_extension_evidence.v1",
        "structural_fields": [
            {"alternate_value": 8, "baseline_value": 4, "name": "fno_width"}
        ],
        "supported_artifact_eras": ["torch-artifact-v1", "torch-artifact-v2"],
        "witness_architecture": {
            "construction_route": "ptycho_torch.generators.registry.resolve_generator",
            "frozen_registry_member": False,
            "persisted_rebuild_route": (
                "ptycho_torch.application_factory.build_ptychopinn_application"
            ),
            "public_id": "es_f1_witness",
        },
    }
    if defect_kind == "candidate_local_structural_field":
        evidence["structural_fields"] = [
            {"alternate_value": 3, "baseline_value": 2, "name": "es_f1_depth"}
        ]
    if defect_kind in {
        "architecture_local_tagged_union",
        "nested_distributed_identity",
        "absent_declared_identity_binding",
        "ambiguous_declared_identity_binding",
        "absent_architecture_binding",
        "ambiguous_architecture_binding",
    }:
        evidence["structural_fields"] = [
            {"alternate_value": 8, "baseline_value": 4, "name": "fno_width"},
            {"alternate_value": 3, "baseline_value": 2, "name": "fno_modes"},
        ]
    if defect_kind == "baseline_mismatch":
        evidence["structural_fields"] = [
            {"alternate_value": 8, "baseline_value": 5, "name": "fno_width"}
        ]
    if defect_kind == "route_tamper":
        evidence["witness_architecture"]["construction_route"] = (
            "ptycho_torch.generators.registry.missing_route"
        )
    if defect_kind == "schema_version_drift":
        evidence["unexpected_schema_field"] = True
    (workspace / "es_f1_candidate_evidence.json").write_bytes(
        evaluator.canonical_json_bytes(evidence)
    )
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
    assert report["schema_version"] == "es-f1-semantic-lifecycle.v1"
    assert report["construction_pid"] != result["adapter_process_id"]
    rejections = report["identity_rejections"]
    assert set(rejections["missing"]) == {"fno_width"}
    assert all(row["rejected"] for row in rejections["missing"].values())
    assert rejections["extra"]["rejected"] is True
    assert rejections["unknown_architecture"]["rejected"] is True
    assert rejections["unsupported_value"]["rejected"] is True
    for row in (
        *rejections["missing"].values(),
        rejections["extra"],
        rejections["unknown_architecture"],
        rejections["unsupported_value"],
    ):
        assert row["module_returned"] is False
        assert isinstance(row["exception_type"], str) and row["exception_type"]
        assert row["exception_detail_sha256"].startswith("sha256:")
    assert report["identity_sensitivity"]["fno_width"]["changed"] is True
    for role in ("representative", "witness"):
        observed = report["roles"][role]
        assert observed["public_implementation"] == (
            observed["persisted_implementation"]
        )
        assert observed["public_state_signature"] == (
            observed["persisted_state_signature"]
        )
        assert observed["loss_finite"] is True
        assert observed["optimizer_changed_parameter"] is True
        expected_structural = {"fno_width": 4} if role == "witness" else {}
        assert observed["structural_values"] == expected_structural
        assert observed["evaluator_checkpoint_reload"]["fresh_pid"] != (
            report["construction_pid"]
        )
        assert observed["evaluator_bundle_reload"]["fresh_pid"] != (
            report["construction_pid"]
        )
        assert observed["adapter_checkpoint_reload"]["structural_values"] == (
            expected_structural
        )
        assert observed["adapter_bundle_reload"]["structural_values"] == (
            expected_structural
        )
    observations = {
        row["clause_id"]: row for row in result["lifecycle_observations"]
    }
    assert set(observations) == set(evaluator.HARD_CLAUSE_IDS[4:])
    assert all(row["satisfied"] is True for row in observations.values())
    assert all(row["evidence"] for row in observations.values())

    fixture_manifest = evaluator.load_controller_asset(
        EVALUATOR_ASSETS / "fixture-manifest.json",
        expected_schema_version="es-f1-fixture-manifest.v1",
    )
    visible_checks = evaluator.load_controller_asset(
        TASK_ASSETS / "visible-check-manifest.json",
        expected_schema_version="es_f1_visible_checks.v1",
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
        timeout_seconds=180,
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
        registry_report=registry_report,
        artifact_report=artifact_report,
    )
    assert [row["clause_id"] for row in complete] == list(evaluator.HARD_CLAUSE_IDS)
    assert all(row["satisfied"] is True for row in complete)


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
    for role in ("representative", "witness"):
        assert result["semantic_report"]["roles"][role][
            "persisted_boundary_owners"
        ]["compute_loss"].startswith("ptycho_torch.generators.registry.")


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
        "intended_failed_clauses": ["F1-H05-NOMINATED-LIFECYCLE"],
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
        expected_schema_version="es-f1-fixture-manifest.v1",
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
        if scenario == "candidate_local_structural_field":
            assert result["semantic_report"]["declared_structural_fields"] == [
                "es_f1_depth"
            ]
        if scenario == "nested_distributed_identity":
            semantic = result["semantic_report"]
            assert semantic["declared_structural_fields"] == [
                "fno_width",
                "fno_modes",
            ]
            assert set(semantic["identity_rejections"]["missing"]) == {
                "fno_width",
                "fno_modes",
            }
            assert all(
                row["rejected"]
                for row in semantic["identity_rejections"]["missing"].values()
            )
            assert semantic["identity_rejections"]["unsupported_value"][
                "rejected"
            ] is True
            assert all(
                row["changed"] and row["deterministic"]
                for row in semantic["identity_sensitivity"].values()
            )
        if scenario == "architecture_local_tagged_union":
            semantic = result["semantic_report"]
            assert semantic["roles"]["representative"]["structural_values"] == {}
            assert semantic["roles"]["witness"]["structural_values"] == {
                "fno_modes": 2,
                "fno_width": 4,
            }
            assert all(
                reload["structural_values"] == {}
                for name, reload in semantic["roles"]["representative"].items()
                if name.endswith("_reload")
            )
    assert evaluator._workspace_digest(workspace) == before


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
    bindings, payloads = evaluator.build_lifecycle_probe_inputs(seed=20_260_802)
    input_root = root / "binding-inputs"
    input_root.mkdir()
    for name, payload in payloads.items():
        target = input_root / bindings[name]["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return evaluator._run_semantic_lifecycle_probe(
        workspace=workspace,
        python_executable=python_executable,
        candidate_evidence=workspace / "es_f1_candidate_evidence.json",
        base_config=input_root / bindings["base_config"]["path"],
        cdi_fixture=input_root / bindings["cdi_fixture"]["path"],
        adapter_observations={},
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

    report = result["semantic_report"]
    assert report["roles"]["representative"]["architecture_id"] == "ffno"
    assert report["roles"]["witness"]["architecture_id"] == "es_f1_witness"
    observations = {
        row["clause_id"]: row["satisfied"]
        for row in result["lifecycle_observations"]
    }
    assert observations["F1-H05-NOMINATED-LIFECYCLE"] is True
    assert observations["F1-H06-WITNESS-STRUCTURAL-ROUNDTRIP"] is True
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
        expected_schema_version="es-f1-fixture-manifest.v1",
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
    report = evaluator.verify_artifact_fixture_pack(
        workspace=workspace,
        python_executable=python,
        fixture_manifest=manifest,
        timeout_seconds=180,
    )
    assert [row["era_id"] for row in report["artifact_eras"]] == [
        row["era_id"] for row in manifest["artifact_eras"]
    ]
    assert all(row["strict_load"] is True for row in report["artifact_eras"])
    assert report["loaded_forbidden_modules"] == []
    assert report["outside_project_origin_rows"] == []
    assert report["cache_artifacts"] == []
