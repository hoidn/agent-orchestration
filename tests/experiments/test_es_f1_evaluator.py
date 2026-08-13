from __future__ import annotations

from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from typing import Any

from jsonschema import Draft202012Validator
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments.es import f1_evaluator as evaluator  # noqa: E402
from scripts.experiments.es.task_package import scan_configuration_consumers  # noqa: E402


EVALUATOR_ROOT = ROOT / "experiments/orc_effectiveness/f1_es/evaluator"
F1_ROOT = ROOT / "experiments/orc_effectiveness/f1_es"
FIXTURE_MANIFEST = EVALUATOR_ROOT / "fixture-manifest.json"
CALIBRATION_CASES = ROOT / "tests/experiments/fixtures/es_f1/calibration-cases.json"
HARD_FINDING_SCHEMA = EVALUATOR_ROOT / "hard-finding.schema.json"
FIXTURE_ADAPTER = ROOT / "tests/experiments/fixtures/es_f1/config_resolution_adapter.py"

CLAUSES = (
    "F1-H01-FOCUSED-SUITES",
    "F1-H02-SCHEMA-CONFORMANCE",
    "F1-H03-PUBLIC-RESOLUTION",
    "F1-H04-TRANSACTIONAL-APPLICATION",
    "F1-H05-STRICT-INPUT-CONTRACT",
    "F1-H06-DERIVED-PUBLIC-FIELDS",
    "F1-H07-CONSUMER-CLOSURE",
    "F1-H08-PROVENANCE-ROUNDTRIP",
    "F1-H09-CROSS-SURFACE-COHERENCE",
    "F1-H10-BYPASS-ORACLE",
)
ROLES = ("SIMULATION", "TRAINING", "INFERENCE", "RUNTIME_EXECUTION")
HOOKS = (
    "CONFIG_SURFACE",
    "CONFIG_CARRIER",
    "TORCH_TRANSACTION",
    "SIMULATION_DERIVATION",
)
BYPASSES = (
    "AMBIENT_CONFIGURATION_READ",
    "TOLERANT_OR_COMPATIBILITY_LOADER",
    "LEGACY_CONFIGURATION_STATE_MUTATION",
)
SELECTORS = ("tests/test_baseline.py",)
CANDIDATE_SELECTOR = "tests/test_es_f1_config_ownership.py"
DIGEST = "sha256:" + "1" * 64


def _candidate_claims() -> dict[str, Any]:
    return {
        "candidate_id": "candidate-a",
        "claims": [
            {
                "clause_id": clause,
                "evidence_paths": [CANDIDATE_SELECTOR],
                "scope": "IMPLEMENTED",
            }
            for clause in CLAUSES
        ],
        "configuration_decision_path": "docs/configuration-decision.md",
        "evaluation_hooks": [
            {"hook_id": hook_id, "symbol": f"candidate.hooks.{hook_id.lower()}"}
            for hook_id in HOOKS
        ],
        "fixed_outputs": {
            "adapter_path": "scripts/es_f1_config_resolution_adapter.py",
            "candidate_test_path": CANDIDATE_SELECTOR,
        },
        "migration_guide_path": "docs/configuration-migration.md",
        "public_resolution_routes": [
            {"roles": list(ROLES), "symbol": "candidate.config.resolve"}
        ],
        "schema_version": "candidate_config_evidence.v2",
    }


def _visible_result() -> dict[str, Any]:
    return {
        "copy_digest_after": DIGEST,
        "copy_digest_before": DIGEST,
        "invocations": [
            {
                "argv": [sys.executable, "-m", "pytest", *SELECTORS],
                "exit_code": 0,
                "invocation_id": "PRE_EDIT_FOCUSED",
                "selectors": list(SELECTORS),
                "stderr_sha256": DIGEST,
                "stdout_sha256": DIGEST,
            },
            {
                "argv": [sys.executable, "-m", "pytest", CANDIDATE_SELECTOR],
                "exit_code": 0,
                "invocation_id": "CANDIDATE_CONFIG",
                "selectors": [CANDIDATE_SELECTOR],
                "stderr_sha256": DIGEST,
                "stdout_sha256": DIGEST,
            },
        ],
        "schema_version": "es-f1-visible-check-result.v3",
    }


def _root_visible_result() -> dict[str, Any]:
    result = _visible_result()
    result["invocations"][0]["selectors"] = list(
        evaluator.F1_PROVIDER_VISIBLE_SELECTORS
    )
    result["invocations"][0]["argv"] = [
        sys.executable,
        "-m",
        "pytest",
        *evaluator.F1_PROVIDER_VISIBLE_SELECTORS,
    ]
    return result


def _failed(observations: list[dict[str, Any]]) -> set[str]:
    return {row["clause_id"] for row in observations if not row["satisfied"]}


def _write_canonical(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(evaluator.canonical_json_bytes(value))


def _candidate_workspace(tmp_path: Path, *, resolver_body: str) -> tuple[Path, Path]:
    workspace = tmp_path / "candidate"
    (workspace / "candidate").mkdir(parents=True)
    (workspace / "candidate/__init__.py").write_text("", encoding="utf-8")
    (workspace / "candidate/config.py").write_text(resolver_body, encoding="utf-8")
    (workspace / "candidate/hooks.py").write_text(
        textwrap.dedent(
            """
            import base64
            from dataclasses import asdict, dataclass, fields, is_dataclass
            import hashlib
            import json

            from candidate.config import SimulationConfig, derive_fields, resolve

            def _bytes(value):
                return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

            def _merge(left, right):
                result = dict(left)
                for key, value in right.items():
                    result[key] = _merge(result[key], value) if key in result and isinstance(result[key], dict) and isinstance(value, dict) else value
                return result

            def _sources(value, file_mapping, cli_patch, prefix=""):
                result = {}
                for key, item in value.items():
                    pointer = prefix + "/" + key
                    file_item = file_mapping.get(key)
                    patch_item = cli_patch.get(key)
                    if isinstance(item, dict):
                        result.update(_sources(item, file_item if isinstance(file_item, dict) else {}, patch_item if isinstance(patch_item, dict) else {}, pointer))
                    else:
                        result[pointer] = "CLI_PATCH" if key in cli_patch else "FILE_MAPPING" if key in file_mapping else "DEFAULT"
                return result

            def resolve_surface(file_mapping, cli_patch):
                value = resolve(file_mapping, cli_patch)
                resolved = asdict(value) if is_dataclass(value) else value
                return {"resolved": resolved, "source_by_pointer": _sources(resolved, file_mapping, cli_patch)}

            def simulation_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def core_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def torch_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def cli_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def workflow_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)
            def study_surface(file_mapping, cli_patch): return resolve_surface(file_mapping, cli_patch)

            def config_surface(request):
                if request == {"op": "DESCRIBE"}:
                    return {"surface_symbols": {
                        "SIMULATION": "candidate.hooks.simulation_surface",
                        "CORE": "candidate.hooks.core_surface",
                        "TORCH": "candidate.hooks.torch_surface",
                        "CLI": "candidate.hooks.cli_surface",
                        "WORKFLOW": "candidate.hooks.workflow_surface",
                        "STUDY": "candidate.hooks.study_surface",
                    }}
                target = {
                    "SIMULATION": simulation_surface,
                    "CORE": core_surface,
                    "TORCH": torch_surface,
                    "CLI": cli_surface,
                    "WORKFLOW": workflow_surface,
                    "STUDY": study_surface,
                }[request["surface"]]
                return target(request["file_mapping"], request["cli_patch"])

            def config_carrier(request):
                if request["op"] == "ENCODE":
                    payload = _bytes(request["carrier"])
                    return {"payload_b64": base64.b64encode(payload).decode(), "payload_sha256": "sha256:" + hashlib.sha256(payload).hexdigest()}
                return {"carrier": json.loads(base64.b64decode(request["payload_b64"], validate=True))}

            _state = {}
            def commit(value):
                _state.update(value)
            def apply(file_mapping, cli_patch):
                value = resolve_surface(file_mapping, cli_patch)
                before = dict(_state)
                try:
                    commit(value["resolved"])
                except Exception:
                    _state.clear()
                    _state.update(before)
                    raise
                return value
            def torch_transaction(request):
                if request == {"op": "DESCRIBE"}:
                    return {"apply_symbol": "candidate.hooks.apply", "commit_symbol": "candidate.hooks.commit", "state_symbols": ["candidate.hooks._state"]}
                return apply(request["file_mapping"], request["cli_patch"])

            def derive(owner):
                return derive_fields(owner)
            def simulation_derivation(request):
                if request == {"op": "DESCRIBE"}:
                    return {"resolver_symbol": "candidate.config.resolve", "owners": [{"owner_symbol": "candidate.config.SimulationConfig", "deriver_symbol": "candidate.config.derive_fields"}]}
                return {"fields": list(derive(SimulationConfig))}
            """
        ),
        encoding="utf-8",
    )
    adapter = workspace / "scripts/es_f1_config_resolution_adapter.py"
    adapter.parent.mkdir()
    shutil.copy2(FIXTURE_ADAPTER, adapter)
    evidence_path = workspace / "es_f1_candidate_evidence.json"
    _write_canonical(evidence_path, _candidate_claims())
    return workspace, evidence_path


def _conforming_protocol_workspace(tmp_path: Path) -> tuple[Path, Path]:
    return _candidate_workspace(
        tmp_path,
        resolver_body=textwrap.dedent(
            """
            from copy import deepcopy
            from dataclasses import dataclass, fields
            from types import UnionType
            from typing import get_args, get_origin

            @dataclass
            class Model:
                N: int = None
                generator_output_mode: str = None
                rect_s1s2_init: str = None

            @dataclass
            class RuntimeConfig:
                model: Model = None
                n_groups: int = None
                n_subsample: int = None
                subsample_seed: int = None
                enable_oversampling: bool = None
                neighbor_pool_size: int = None
                sequential_sampling: bool = None
                batch_size: int = None
                model_path: str = None
                test_data_file: str = None

            @dataclass
            class Probe:
                source: str = None
                ideal_scale: float = None

            @dataclass
            class Object:
                kind: str = None
                image_size: list[int] = None
                objects_per_probe: int = None
                diffractions_per_object: int = None
                set_phi: bool = None
                patch_amplitude_normalization: str = None

            @dataclass
            class Scan:
                kind: str = None
                grid_size: list[int] = None
                offset: int = None
                outer_offset_train: int = None
                outer_offset_test: int = None
                train_groups: int = None
                test_groups: int = None
                buffer: int = None
                position_layout: str = None

            @dataclass
            class Detector:
                photons_per_pattern: float = None
                beamstop_diameter: float = None

            @dataclass
            class SimulationConfig:
                N: int = None
                seed: int = None
                probe: Probe = None
                object: Object = None
                scan: Scan = None
                detector: Detector = None

            def derive_fields(owner):
                return tuple(sorted(field.name for field in fields(owner)))

            def _merge(left, right):
                result = deepcopy(left)
                for key, value in right.items():
                    if key in result and isinstance(value, dict) and isinstance(result[key], dict):
                        result[key] = _merge(result[key], value)
                    else:
                        result[key] = deepcopy(value)
                return result

            def _validate(cls, value):
                if not isinstance(value, dict):
                    raise TypeError("mapping required")
                owner_fields = {field.name: field.type for field in fields(cls)}
                declared = {name: owner_fields[name] for name in derive_fields(cls)}
                result = {}
                for key, item in value.items():
                    if key not in declared:
                        raise ValueError("unknown field")
                    expected = declared[key]
                    if hasattr(expected, "__dataclass_fields__"):
                        result[key] = _validate(expected, item)
                        continue
                    origin = get_origin(expected)
                    if origin is list:
                        args = get_args(expected)
                        if not isinstance(item, list) or any(type(part) is not args[0] for part in item):
                            raise TypeError("invalid list field")
                    elif type(item) is not expected:
                        raise TypeError("invalid scalar field")
                    if key in {"N", "n_groups", "batch_size"} and item < 1:
                        raise ValueError("non-positive field")
                    if key == "grid_size" and len(item) != 2:
                        raise ValueError("invalid grid")
                    result[key] = deepcopy(item)
                return cls(**result)

            def resolve(file_mapping, cli_patch):
                resolved = _merge(file_mapping, cli_patch)
                owner = SimulationConfig if "probe" in resolved else RuntimeConfig
                return _validate(owner, resolved)
            """
        ),
    )


def _run_direct_protocol(
    tmp_path: Path, workspace: Path, evidence_path: Path
) -> dict[str, Any]:
    return evaluator.run_direct_resolver_probe(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "direct-probe",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )


def _mutated_protocol_workspace(
    tmp_path: Path, old: str, new: str
) -> tuple[Path, Path]:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    source_path = workspace / "candidate/config.py"
    source = source_path.read_text(encoding="utf-8")
    assert source.count(old) == 1
    source_path.write_text(source.replace(old, new), encoding="utf-8")
    return workspace, evidence_path


def _request(candidate_evidence_digest: str) -> dict[str, Any]:
    return {
        "candidate_evidence_path": "es_f1_candidate_evidence.json",
        "candidate_evidence_sha256": candidate_evidence_digest,
        "candidate_id": "candidate-a",
        "operation_version": "ptychopinn_public_config_resolution.v1",
        "probe_cases": [
            {
                "case_id": "strict-precedence",
                "cli_patch": {
                    "path": "inputs/cli.json",
                    "sha256": "sha256:" + "0" * 64,
                },
                "file_mapping": {
                    "path": "inputs/file.json",
                    "sha256": "sha256:" + "0" * 64,
                },
                "role": "TRAINING",
            }
        ],
        "schema_version": "config_resolution_probe_request.v1",
    }


def test_f1v2_constants_replace_the_architecture_vocabulary() -> None:
    assert evaluator.HARD_CLAUSE_IDS == CLAUSES
    assert evaluator.CONFIG_RESOLUTION_ROLES == ROLES
    assert evaluator.BYPASS_CLASSES == BYPASSES
    for obsolete in (
        "ARTIFACT_ERA_IDS",
        "derive_lifecycle_observations",
        "classify_task0_bypass_discovery",
        "build_artifact_fixture_pack",
    ):
        assert not hasattr(evaluator, obsolete)


def test_four_declared_hooks_execute_under_strict_json_abi(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_evaluation_hooks(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "hooks",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert [row["hook_id"] for row in result["transcript"]] == list(HOOKS)
    assert [row["operations"] for row in result["transcript"]] == [
        ["DESCRIBE"],
        ["ENCODE", "ENCODE", "DECODE"],
        ["DESCRIBE"],
        ["DESCRIBE", "CATALOG"],
    ]
    assert result["facts"] == {
        "F1-H04-TRANSACTIONAL-APPLICATION": False,
        "F1-H06-DERIVED-PUBLIC-FIELDS": False,
        "F1-H08-PROVENANCE-ROUNDTRIP": False,
        "F1-H09-CROSS-SURFACE-COHERENCE": False,
    }


def test_hook_output_cannot_forge_an_evaluator_fact(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    hooks = workspace / "candidate/hooks.py"
    hooks.write_text(
        hooks.read_text(encoding="utf-8").replace(
            'return {"surface_symbols":',
            'return {"passed": True, "surface_symbols":',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(evaluator.EvaluatorError, match="authority|field set"):
        evaluator.run_evaluation_hooks(
            candidate_evidence_path=evidence_path,
            output_root=tmp_path / "hooks",
            python_executable=Path(sys.executable),
            timeout_seconds=30,
            workspace=workspace,
        )


def test_surface_and_carrier_proof_executes_real_targets_and_fresh_decode(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_surface_and_carrier_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "surface-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {
        "F1-H03-PUBLIC-RESOLUTION": True,
        "F1-H08-PROVENANCE-ROUNDTRIP": True,
        "F1-H09-CROSS-SURFACE-COHERENCE": True,
    }
    assert result["runtime_bypass_classes"] == []
    assert len(result["surface_transcript"]["rows"]) == 30


def test_surface_hook_that_does_not_forward_target_result_fails_closed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    hooks = workspace / "candidate/hooks.py"
    source = hooks.read_text(encoding="utf-8")
    hooks.write_text(
        source.replace(
            '    return target(request["file_mapping"], request["cli_patch"])',
            '    target(request["file_mapping"], request["cli_patch"])\n'
            '    return {"resolved": {}, "source_by_pointer": {}}',
        ),
        encoding="utf-8",
    )

    result = evaluator.run_surface_and_carrier_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "surface-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {
        "F1-H03-PUBLIC-RESOLUTION": False,
        "F1-H08-PROVENANCE-ROUNDTRIP": False,
        "F1-H09-CROSS-SURFACE-COHERENCE": False,
    }


def test_runtime_hidden_getenv_fails_h10_when_ast_oracle_misses_it(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    config = workspace / "candidate/config.py"
    source = config.read_text(encoding="utf-8").replace(
        "from typing import get_args, get_origin\n",
        "from typing import get_args, get_origin\n"
        "_hidden_getenv = getattr(__import__('os'), ''.join(('get', 'env')))\n",
    ).replace(
        "def resolve(file_mapping, cli_patch):\n",
        "def resolve(file_mapping, cli_patch):\n"
        "    _hidden_getenv('ES_F1_RUNTIME_ONLY')\n",
    )
    config.write_text(source, encoding="utf-8")
    assert "AMBIENT_CONFIGURATION_READ" not in evaluator.detect_ast_bypasses(source)

    observations = evaluator._evaluate_candidate(
        calibration_cases=[{
            "case_id": "nested-precedence",
            "defect_kind": "none",
            "expected_failed_clauses": [],
            "probe": {
                "cli_patch": {"model": {"N": 128}, "n_groups": 7},
                "file_mapping": _TRAINING_ROOT_INPUT,
                "role": "TRAINING",
            },
        }],
        candidate_evidence_path=evidence_path,
        consumer_census={"rows": [{
            "consumer_id": "public-resolution",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.resolve",
        }]},
        output_root=tmp_path / "evaluation",
        package_conformance={
            "candidate_evidence": "candidate_config_evidence.v2",
            "probe_request": "config_resolution_probe_request.v1",
            "probe_result": "config_resolution_probe_result.v1",
            "validated": True,
        },
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        visible_result=_root_visible_result(),
        workspace=workspace,
    )
    h10 = next(row for row in observations if row["clause_id"] == "F1-H10-BYPASS-ORACLE")
    assert h10["satisfied"] is False
    transcript = json.loads(
        (tmp_path / "evaluation/surface-proof/surface-transcript.json").read_bytes()
    )
    assert evaluator.normalize_bypass_events(transcript["runtime_bypass_events"]) == (
        "AMBIENT_CONFIGURATION_READ",
    )


def test_simulation_derivation_proof_binds_owner_and_sentinel(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_simulation_derivation_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "derivation-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {"F1-H06-DERIVED-PUBLIC-FIELDS": True}
    assert result["transcript"]["rows"][0] == {
        "called_by_resolver": True,
        "direct_fields": ["N", "detector", "object", "probe", "scan", "seed"],
        "owner_present": True,
        "owner_symbol": "candidate.config.SimulationConfig",
        "sentinel_derived": True,
    }


def test_fixed_simulation_catalog_fails_sentinel_derivation(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    source_path = workspace / "candidate/config.py"
    source = source_path.read_text(encoding="utf-8")
    source_path.write_text(
        source.replace(
            "return tuple(sorted(field.name for field in fields(owner)))",
            'return ("N", "detector", "object", "probe", "scan", "seed") if any(base.__name__ == "SimulationConfig" for base in owner.__mro__) else tuple(sorted(field.name for field in fields(owner)))',
        ),
        encoding="utf-8",
    )

    result = evaluator.run_simulation_derivation_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "derivation-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {"F1-H06-DERIVED-PUBLIC-FIELDS": False}


def test_torch_transaction_proof_counts_commit_and_rolls_back(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_torch_transaction_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "transaction-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {"F1-H04-TRANSACTIONAL-APPLICATION": True}
    assert [row["commit_count"] for row in result["transcripts"]] == [1, 0, 1]
    assert result["transcripts"][1]["before"] == result["transcripts"][1]["after"]
    assert result["transcripts"][2]["before"] == result["transcripts"][2]["after"]


def test_transaction_state_omission_cannot_hide_the_mutated_global(tmp_path: Path) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    hooks = workspace / "candidate/hooks.py"
    source = hooks.read_text(encoding="utf-8")
    hooks.write_text(
        source.replace("_state = {}", "_other = {}\n_state = {}").replace(
            '["candidate.hooks._state"]', '["candidate.hooks._other"]'
        ),
        encoding="utf-8",
    )

    result = evaluator.run_torch_transaction_proof(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "transaction-proof",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {"F1-H04-TRANSACTIONAL-APPLICATION": False}


def test_checked_in_evaluator_assets_are_one_coherent_successor() -> None:
    fixtures = evaluator.load_controller_asset(
        FIXTURE_MANIFEST,
        expected_schema_version="es-f1-fixture-manifest.v3",
    )
    calibration = evaluator.load_controller_asset(
        CALIBRATION_CASES,
        expected_schema_version="es-f1-calibration-cases.v4",
    )
    assert tuple(fixtures["hard_clause_ids"]) == CLAUSES
    assert tuple(fixtures["configuration_roles"]) == ROLES
    assert tuple(fixtures["bypass_classes"]) == BYPASSES
    assert fixtures["versions"] == {
        "candidate_evidence": "candidate_config_evidence.v2",
        "hard_evaluation": "es-f1-hard-evaluation.v3",
        "hard_finding": "es-f1-hard-finding.v3",
        "probe_request": "config_resolution_probe_request.v1",
        "probe_result": "config_resolution_probe_result.v1",
        "visible_result": "es-f1-visible-check-result.v3",
    }
    assert fixtures["calibration_cases"]["schema_version"] == calibration["schema_version"]
    assert fixtures["calibration_cases"]["sha256"] == evaluator.file_sha256(CALIBRATION_CASES)
    assert fixtures["fixture_adapter"] == {
        "path": "tests/experiments/fixtures/es_f1/config_resolution_adapter.py",
        "policy": "path-only.v1",
        "sha256": evaluator.file_sha256(FIXTURE_ADAPTER),
    }
    positives = [row for row in calibration["cases"] if row["defect_kind"] == "none"]
    assert [row["case_id"] for row in positives] == list(
        evaluator.CALIBRATION_POSITIVE_CASE_IDS
    )
    assert all(
        set(row) == {"case_id", "defect_kind", "expected_failed_clauses", "probe"}
        and set(row["probe"]) == {"cli_patch", "file_mapping", "role"}
        for row in positives
    )


def test_public_evaluation_root_has_no_package_injection_parameters() -> None:
    parameters = inspect.signature(evaluator.evaluate_candidate).parameters
    assert set(parameters) == {
        "candidate_evidence_path",
        "output_root",
        "workspace",
    }
    package = evaluator.load_checked_in_evaluator_package()
    assert package["calibration_cases"]["schema_version"] == (
        "es-f1-calibration-cases.v4"
    )


def test_frozen_evaluator_package_binds_the_task1_census_and_selectors() -> None:
    package = evaluator.load_frozen_evaluator_package(
        calibration_cases_path=CALIBRATION_CASES,
        consumer_census_path=(
            ROOT
            / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2/"
            "configuration-consumer-census.json"
        ),
        fixture_manifest_path=FIXTURE_MANIFEST,
        reviewer_perspectives_path=EVALUATOR_ROOT / "reviewer-perspectives.json",
        task_profile_path=F1_ROOT / "task-profile.json",
        visible_check_path=F1_ROOT / "task/visible-check-manifest.json",
        visible_contract_path=F1_ROOT / "task/visible-task-contract.json",
    )
    assert package["package_conformance"]["validated"] is True
    assert package["consumer_census"]["consumer_count"] == len(
        package["consumer_census"]["rows"]
    )
    assert tuple(package["visible_checks"].pre_edit_selectors) == tuple(
        package["visible_contract"]["focused_selectors"]
    )


def test_mixed_predecessor_evaluator_package_rejects_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = json.loads(FIXTURE_MANIFEST.read_bytes())
    fixture["schema_version"] = "es-f1-fixture-manifest.v2"
    path = tmp_path / "fixture.json"
    _write_canonical(path, fixture)
    calls: list[object] = []
    monkeypatch.setattr(
        evaluator,
        "_run_audited_subprocess",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    with pytest.raises(evaluator.EvaluatorError, match="successor"):
        evaluator.load_frozen_evaluator_package(
            calibration_cases_path=CALIBRATION_CASES,
            consumer_census_path=(
                ROOT
                / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2/"
                "configuration-consumer-census.json"
            ),
            fixture_manifest_path=path,
            reviewer_perspectives_path=EVALUATOR_ROOT / "reviewer-perspectives.json",
            task_profile_path=F1_ROOT / "task-profile.json",
            visible_check_path=F1_ROOT / "task/visible-check-manifest.json",
            visible_contract_path=F1_ROOT / "task/visible-task-contract.json",
        )
    assert calls == []


def test_frozen_package_rejects_fixture_adapter_digest_tamper(tmp_path: Path) -> None:
    fixture = json.loads(FIXTURE_MANIFEST.read_bytes())
    fixture["fixture_adapter"]["sha256"] = "sha256:" + "0" * 64
    path = tmp_path / "fixture.json"
    _write_canonical(path, fixture)

    with pytest.raises(evaluator.EvaluatorError, match="fixture.*binding"):
        evaluator.load_frozen_evaluator_package(
            calibration_cases_path=CALIBRATION_CASES,
            consumer_census_path=(
                ROOT
                / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2/"
                "configuration-consumer-census.json"
            ),
            fixture_manifest_path=path,
            reviewer_perspectives_path=EVALUATOR_ROOT / "reviewer-perspectives.json",
            task_profile_path=F1_ROOT / "task-profile.json",
            visible_check_path=F1_ROOT / "task/visible-check-manifest.json",
            visible_contract_path=F1_ROOT / "task/visible-task-contract.json",
        )


def test_calibration_manifest_covers_positive_surfaces_and_every_negative() -> None:
    payload = evaluator.load_controller_asset(
        CALIBRATION_CASES,
        expected_schema_version="es-f1-calibration-cases.v4",
    )
    positives = {
        row["case_id"] for row in payload["cases"] if row["defect_kind"] == "none"
    }
    assert positives == {
        "cli_patch",
        "file_mapping",
        "fresh_process_provenance",
        "precedence",
        "public_cli",
        "study_script",
        "strict_roundtrip",
        "tensorflow_backend",
        "torch_backend",
        "workflow_component",
    }
    negatives = {
        row["defect_kind"]: tuple(row["expected_failed_clauses"])
        for row in payload["cases"]
        if row["defect_kind"] != "none"
    }
    assert negatives == evaluator.CALIBRATION_DEFECT_CLAUSES


@pytest.mark.parametrize(
    "mutation",
    ["positive-shape", "positive-role", "negative-shape", "duplicate-id"],
)
def test_calibration_case_contract_is_exact(mutation: str) -> None:
    cases = deepcopy(json.loads(CALIBRATION_CASES.read_bytes())["cases"])
    if mutation == "positive-shape":
        del cases[0]["probe"]
    elif mutation == "positive-role":
        cases[0]["probe"]["role"] = "EXTRA"
    elif mutation == "negative-shape":
        cases[-1]["probe"] = {}
    else:
        cases[-1]["case_id"] = cases[-2]["case_id"]

    with pytest.raises(evaluator.EvaluatorError, match="calibration"):
        evaluator._validate_calibration_cases(cases)


def test_transitive_consumer_walk_does_not_stop_at_a_facade() -> None:
    consumers = [{"consumer_id": "consumer-a", "entry_symbol": "public.start"}]
    assert evaluator.walk_consumer_routes(
        consumer_rows=consumers,
        call_graph={"public.start": ["facade"], "facade": ["authority"]},
        authority_symbols={"authority"},
        bypass_symbols={},
    )["closed"] is True
    result = evaluator.walk_consumer_routes(
        consumer_rows=consumers,
        call_graph={"public.start": ["facade"]},
        authority_symbols={"authority"},
        bypass_symbols={},
    )
    assert result["closed"] is False
    assert result["unresolved_consumers"] == ["consumer-a"]


def test_wrapper_deep_bypass_is_not_hidden_by_an_authority_sibling() -> None:
    result = evaluator.walk_consumer_routes(
        consumer_rows=[{"consumer_id": "consumer-a", "entry_symbol": "entry"}],
        call_graph={
            "entry": ["wrapper"],
            "wrapper": ["authority", "old.path"],
            "old.path": ["authority"],
        },
        authority_symbols={"authority"},
        bypass_symbols={"old.path": "TOLERANT_OR_COMPATIBILITY_LOADER"},
    )
    assert result["closed"] is False
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


def test_ast_and_runtime_oracle_use_only_the_three_closed_classes() -> None:
    source = """
import os

def resolve(mapping, legacy_config):
    mode = os.getenv("MODE")
    value = mapping.get("value", 1)
    legacy_config.mode = mode
    return value
"""
    assert evaluator.detect_ast_bypasses(source) == BYPASSES
    with pytest.raises(evaluator.EvaluatorError, match="bypass class"):
        evaluator.normalize_bypass_events(
            [{"class_id": "NEW_CLASS", "consumer_id": "a", "symbol": "a"}]
        )


def test_explicit_scalar_conversion_is_a_tolerant_loader_bypass() -> None:
    assert evaluator.detect_ast_bypasses(
        "def resolve(mapping, patch):\n    return str(mapping['mode'])\n"
    ) == ("TOLERANT_OR_COMPATIBILITY_LOADER",)


def test_bypass_detection_is_config_tainted_and_requires_a_real_legacy_write() -> None:
    source = """
def resolve(config, telemetry, legacy_state):
    telemetry.get("mode", "quiet")
    str("constant")
    current = legacy_state.mode
    return config["mode"]
"""
    assert evaluator.detect_ast_bypasses(source) == ()


def test_swallowed_config_fallback_is_a_tolerant_bypass() -> None:
    source = """
def resolve(config):
    try:
        return strict_load(config)
    except (TypeError, ValueError):
        return {}
"""
    assert evaluator.detect_ast_bypasses(source) == (
        "TOLERANT_OR_COMPATIBILITY_LOADER",
    )


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("return os.getenv('MODE')", "AMBIENT_CONFIGURATION_READ"),
        ("return os.environ.get('MODE')", "AMBIENT_CONFIGURATION_READ"),
        ("return os.environ['MODE']", "AMBIENT_CONFIGURATION_READ"),
        ("return config.get('mode', 'safe')", "TOLERANT_OR_COMPATIBILITY_LOADER"),
        ("return str(config['mode'])", "TOLERANT_OR_COMPATIBILITY_LOADER"),
        ("return compatibility_load(config)", "TOLERANT_OR_COMPATIBILITY_LOADER"),
        ("legacy_state['mode'] = config['mode']\nreturn config", "LEGACY_CONFIGURATION_STATE_MUTATION"),
    ],
)
def test_config_tainted_bypass_forms_are_detected(
    statement: str, expected: str
) -> None:
    source = "import os\n\ndef resolve(config, legacy_state):\n    " + statement.replace("\n", "\n    ") + "\n"
    assert expected in evaluator.detect_ast_bypasses(source)


def test_nested_config_route_reaches_authority_without_external_call_dead_ends(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
            "def wrapper(config):\n"
            "    def nested(value):\n"
            "        audit(value)\n"
            "        return resolve(value, {})\n"
            "    return nested(config)\n"
        ),
    )
    row = {
        "consumer_id": "current-wrapper",
        "match_kind": "CONFIGURATION_READ",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.wrapper",
        "source_span": {"start_line": 7, "start_col": 11, "end_line": 7, "end_col": 17},
        "transitive_wrapper_chain": ["candidate.config.wrapper", "config"],
    }
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": [row]},
    )
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [dict(row, consumer_id="frozen-wrapper")]},
        workspace=workspace,
    )
    assert result["closed"] is True
    assert result["paired_consumer_count"] == 1


def test_consumer_occurrences_reconcile_as_multisets() -> None:
    def row(consumer_id: str, line: int) -> dict[str, Any]:
        return {
            "consumer_id": consumer_id,
            "match_kind": "CONFIGURATION_READ",
            "path": "ptycho/config/example.py",
            "public_entry_route": "ptycho.config.example.consume",
            "source_span": {
                "start_line": line,
                "start_col": 4,
                "end_line": line,
                "end_col": 10,
            },
            "transitive_wrapper_chain": ["ptycho.config.example.consume", "config.mode"],
        }

    result = evaluator.reconcile_consumer_occurrences(
        [row("old-a", 10), row("old-b", 20)],
        [row("current-a", 10)],
    )
    assert result["old_count"] == 2
    assert result["current_count"] == 1
    assert result["paired_count"] == 1
    assert result["removed_count"] == 1
    assert result["added_count"] == 0
    assert result["old_count"] == result["paired_count"] + result["removed_count"]
    assert result["current_count"] == result["paired_count"] + result["added_count"]


def test_fresh_added_consumer_occurrence_is_evaluated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
            "def good(config): return resolve(config, {})\n"
            "def added(config): return config.get('mode', 'safe')\n"
        ),
    )

    def row(consumer_id: str, route: str, line: int) -> dict[str, Any]:
        return {
            "consumer_id": consumer_id,
            "match_kind": "CONFIGURATION_READ",
            "path": "candidate/config.py",
            "public_entry_route": route,
            "source_span": {"start_line": line, "start_col": 4, "end_line": line, "end_col": 10},
            "transitive_wrapper_chain": [route, "config"],
        }

    old = row("old-good", "candidate.config.good", 2)
    current = [
        row("current-good", "candidate.config.good", 2),
        row("current-added", "candidate.config.added", 3),
    ]
    monkeypatch.setattr(
        evaluator,
        "scan_workspace_configuration_consumers",
        lambda workspace: {"rows": current},
    )
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census={"rows": [old]},
        workspace=workspace,
    )
    assert result["closed"] is False
    assert result["added_consumer_count"] == 1
    assert {trace["consumer_id"] for trace in result["traces"]} == {
        "current-good",
        "current-added",
    }
    assert result["bypass_classes"] == ["TOLERANT_OR_COMPATIBILITY_LOADER"]


@pytest.mark.parametrize("authority_field", ["passed", "satisfied", "decision"])
def test_candidate_authority_is_rejected_at_any_depth(authority_field: str) -> None:
    claims = _candidate_claims()
    claims["public_resolution_routes"][0][authority_field] = True
    with pytest.raises(ValueError, match="candidate.*authority"):
        evaluator.evaluate_observations(
            candidate_claims=claims,
            evaluator_observations=[
                {
                    "clause_id": clause,
                    "details": "controller observation",
                    "evidence": [DIGEST],
                    "satisfied": True,
                }
                for clause in CLAUSES
            ],
            dispositions={},
            frozen_registry=set(ROLES),
        )


def test_hard_evaluation_v3_normalizes_observations_and_findings() -> None:
    observations = [
        {
            "clause_id": clause,
            "details": "controller observation",
            "evidence": [DIGEST],
            "satisfied": True,
        }
        for clause in CLAUSES
    ]
    observations[-1]["satisfied"] = False
    result = evaluator.evaluate_observations(
        candidate_claims=_candidate_claims(),
        evaluator_observations=observations,
        dispositions={"F1-H10-BYPASS-ORACLE": "PRODUCT_DEFECT"},
        frozen_registry=set(ROLES),
    )
    assert result["schema_version"] == "es-f1-hard-evaluation.v3"
    assert result["candidate_claims_digest"].startswith("sha256:")
    assert [row["clause_id"] for row in result["hard_findings"]] == [
        "F1-H10-BYPASS-ORACLE"
    ]
    assert result["hard_findings"][0]["schema_version"] == "es-f1-hard-finding.v3"


@pytest.mark.parametrize(
    "registry",
    [set(ROLES) - {"INFERENCE"}, set(ROLES) | {"EVALUATION"}],
)
def test_hard_evaluation_rejects_nonexact_role_domain(registry: set[str]) -> None:
    observations = [
        {
            "clause_id": clause,
            "details": "controller observation",
            "evidence": [DIGEST],
            "satisfied": True,
        }
        for clause in CLAUSES
    ]
    with pytest.raises(ValueError, match="role"):
        evaluator.evaluate_observations(
            candidate_claims=_candidate_claims(),
            evaluator_observations=observations,
            dispositions={},
            frozen_registry=registry,
        )


def test_path_only_result_rejects_adapter_authored_authority(tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    adapter = workspace / "adapter.py"
    adapter.parent.mkdir()
    adapter.write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "p=Path(sys.argv[sys.argv.index('--result')+1])\n"
        "p.write_text(json.dumps({'schema_version':'config_resolution_probe_result.v1','candidate_id':'candidate-a','operation_version':'ptychopinn_public_config_resolution.v1','probe_results':[{'case_id':'strict-precedence','resolved_record_path':'artifact.json'}],'passed':True})+'\\n')\n",
        encoding="utf-8",
    )
    input_root = tmp_path / "inputs"
    candidate_bytes = evaluator.canonical_json_bytes(_candidate_claims())
    _write_canonical(input_root / "es_f1_candidate_evidence.json", _candidate_claims())
    request = _request("sha256:" + hashlib.sha256(candidate_bytes).hexdigest())
    for field in ("file_mapping", "cli_patch"):
        path = input_root / request["probe_cases"][0][field]["path"]
        _write_canonical(path, {})
        request["probe_cases"][0][field]["sha256"] = evaluator.file_sha256(path)
    request_path = input_root / "request.json"
    _write_canonical(request_path, request)
    with pytest.raises(evaluator.EvaluatorError, match="probe result"):
        evaluator.run_config_resolution_adapter(
            adapter_relative_path="adapter.py",
            expected_candidate_id="candidate-a",
            expected_case_ids=("strict-precedence",),
            output_root=tmp_path / "output",
            python_executable=Path(sys.executable),
            request_path=request_path,
            timeout_seconds=30,
            workspace=workspace,
        )


def test_adapter_authored_provenance_is_rejected() -> None:
    payload = {
        "provenance": {"sample_count": "CLI_PATCH"},
        "resolved": {"mode": "strict", "sample_count": 16},
    }
    with pytest.raises(evaluator.EvaluatorError, match="field set"):
        evaluator._load_resolution_artifact_value(payload)


def test_evaluator_derives_provenance_from_raw_resolution_facts() -> None:
    raw = evaluator._load_resolution_artifact_value(
        {"resolved": {"mode": "strict", "sample_count": 16}}
    )
    observed = evaluator._derive_resolution_observation(
        cli_patch={"sample_count": 16},
        file_mapping={"mode": "strict", "sample_count": 8},
        raw=raw,
    )
    assert observed["provenance"] == {
        "mode": "FILE_MAPPING",
        "sample_count": "CLI_PATCH",
    }


def test_evaluator_derives_nested_precedence_without_dropping_file_fields() -> None:
    raw = evaluator._load_resolution_artifact_value(
        {"resolved": {"model": {"N": 128, "generator_output_mode": "amp_phase"}}}
    )
    observed = evaluator._derive_resolution_observation(
        cli_patch={"model": {"N": 128}},
        file_mapping={"model": {"N": 64, "generator_output_mode": "amp_phase"}},
        raw=raw,
    )
    assert observed["precedence_satisfied"] is True
    assert observed["provenance"] == {
        "model.N": "CLI_PATCH",
        "model.generator_output_mode": "FILE_MAPPING",
    }


def test_adapter_calls_candidate_declared_resolver_instead_of_merging(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch):\n"
            "    return {'marker': 'CALLED', **file_mapping, **cli_patch}\n"
        ),
    )
    run = evaluator.execute_empirical_probe(
        candidate_evidence_path=evidence_path,
        cases=[{
            "case_id": "declared-route",
            "cli_patch": {"sample_count": 16},
            "file_mapping": {"mode": "strict", "sample_count": 8},
            "role": "TRAINING",
        }],
        output_root=tmp_path / "probe",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )
    assert run["observations"][0]["resolved"]["marker"] == "CALLED"
    adapter_source = FIXTURE_ADAPTER.read_text(encoding="utf-8")
    assert "{**file_mapping, **cli_patch}" not in adapter_source
    assert "provenance" not in adapter_source and "source_by_field" not in adapter_source


def test_checked_in_adapter_consumes_the_digest_bound_v1_request(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch):\n"
            "    return {'marker': 'CALLED', **file_mapping, **cli_patch}\n"
        ),
    )
    request_root = tmp_path / "request"
    request_root.mkdir()
    evidence_copy = request_root / "es_f1_candidate_evidence.json"
    evidence_copy.write_bytes(evidence_path.read_bytes())
    request = _request(evaluator.file_sha256(evidence_copy))
    row = request["probe_cases"][0]
    values = {
        "file_mapping": {"mode": "strict", "sample_count": 8},
        "cli_patch": {"sample_count": 16},
    }
    for binding_name, value in values.items():
        binding = row[binding_name]
        path = request_root / binding["path"]
        _write_canonical(path, value)
        binding["sha256"] = evaluator.file_sha256(path)
    request_path = request_root / "request.json"
    _write_canonical(request_path, request)

    result = evaluator.run_config_resolution_adapter(
        adapter_relative_path="scripts/es_f1_config_resolution_adapter.py",
        expected_candidate_id="candidate-a",
        expected_case_ids=("strict-precedence",),
        output_root=tmp_path / "output",
        python_executable=Path(sys.executable),
        request_path=request_path,
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["observations"] == [
        {"resolved": {"marker": "CALLED", "mode": "strict", "sample_count": 16}}
    ]


def test_root_evaluation_derives_routes_from_census_and_candidate_ast(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch):\n"
            "    return {**file_mapping, **cli_patch}\n\n"
            "def wrapper(file_mapping, cli_patch):\n"
            "    return resolve(file_mapping, cli_patch)\n"
        ),
    )
    census = {
        "rows": [{
            "consumer_id": "consumer-a",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.wrapper",
            "transitive_wrapper_chain": ["candidate.config.wrapper", "candidate.config.resolve"],
        }]
    }
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )
    assert result["closed"] is True
    (workspace / "candidate/config.py").write_text(
        "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
        "def wrapper(file_mapping, cli_patch): return legacy_load(file_mapping)\n",
        encoding="utf-8",
    )
    assert evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )["closed"] is False


def test_checked_in_frozen_census_projects_every_slot_exactly_once() -> None:
    package = evaluator.load_frozen_evaluator_package(
        calibration_cases_path=CALIBRATION_CASES,
        consumer_census_path=(
            ROOT
            / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2/"
            "configuration-consumer-census.json"
        ),
        fixture_manifest_path=FIXTURE_MANIFEST,
        reviewer_perspectives_path=EVALUATOR_ROOT / "reviewer-perspectives.json",
        task_profile_path=F1_ROOT / "task-profile.json",
        visible_check_path=F1_ROOT / "task/visible-check-manifest.json",
        visible_contract_path=F1_ROOT / "task/visible-task-contract.json",
    )
    rows = package["consumer_census"]["rows"]
    slots = evaluator.project_frozen_consumer_slots(rows)
    assert len(rows) == len(slots) == 4255
    assert len({slot["consumer_id"] for slot in slots}) == 4255


def test_consumer_inspection_handles_class_methods_retired_paths_and_new_consumers(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch):\n"
            "    return {**file_mapping, **cli_patch}\n\n"
            "class Runner:\n"
            "    def run(self, file_mapping, cli_patch):\n"
            "        return resolve(file_mapping, cli_patch)\n\n"
            "def introduced(file_mapping, cli_patch):\n"
            "    return resolve(file_mapping, cli_patch)\n"
        ),
    )
    census = {
        "rows": [
            {
                "consumer_id": "class-method",
                "path": "candidate/config.py",
                "public_entry_route": "candidate.config.Runner.run",
            },
            {
                "consumer_id": "retired",
                "path": "candidate/deleted.py",
                "public_entry_route": "candidate.deleted.old",
            },
        ]
    }
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )
    assert result["closed"] is True
    assert result["retired_consumer_ids"] == ["retired"]
    assert "candidate.config.introduced" in result["introduced_consumer_symbols"]
    assert result["accounted_consumer_count"] == 1
    assert result["paired_consumer_count"] == 1
    assert result["removed_consumer_count"] == 1


def test_consumer_inspection_fails_closed_on_ambiguous_method_resolution(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body=(
            "def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n"
            "class A:\n"
            "    def run(self, file_mapping, cli_patch): return resolve(file_mapping, cli_patch)\n"
            "class B:\n"
            "    def run(self, file_mapping, cli_patch): return resolve(file_mapping, cli_patch)\n"
        ),
    )
    census = {"rows": [{
        "consumer_id": "ambiguous",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.run",
    }]}
    with pytest.raises(evaluator.EvaluatorError, match="ambiguous"):
        evaluator.inspect_candidate_consumers(
            candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
            consumer_census=census,
            workspace=workspace,
        )


def test_new_path_consumer_is_scanned_and_must_close_to_authority(tmp_path: Path) -> None:
    workspace, evidence_path = _candidate_workspace(
        tmp_path,
        resolver_body="def resolve(file_mapping, cli_patch): return {**file_mapping, **cli_patch}\n",
    )
    new_path = workspace / "scripts/new_config_consumer.py"
    new_path.parent.mkdir(exist_ok=True)
    new_path.write_text(
        "def consume(runtime_config):\n    return runtime_config.value\n",
        encoding="utf-8",
    )
    census = {"rows": [{
        "consumer_id": "authority",
        "path": "candidate/config.py",
        "public_entry_route": "candidate.config.resolve",
    }]}
    result = evaluator.inspect_candidate_consumers(
        candidate_evidence=evaluator.load_candidate_config_evidence(evidence_path),
        consumer_census=census,
        workspace=workspace,
    )
    assert result["closed"] is False
    assert "scripts.new_config_consumer.consume" in result["introduced_consumer_symbols"]


def test_workspace_detector_matches_git_detector_on_identical_tree(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    source = repository / "ptycho/config/example.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "def consume(runtime_config):\n    return runtime_config.value\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "commit", "-qm", "fixture",
        ],
        cwd=repository,
        check=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    git_rows = scan_configuration_consumers(repository, commit)["rows"]
    workspace_rows = evaluator.scan_workspace_configuration_consumers(repository)["rows"]
    assert git_rows == workspace_rows


def test_controller_root_ignores_caller_authored_green_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not hasattr(evaluator, "derive_complete_observations")
    assert not hasattr(evaluator, "_probe_matrix")
    assert not hasattr(evaluator, "apply_calibration_defect")
    with pytest.raises(evaluator.EvaluatorError, match="workspace"):
        evaluator._evaluate_candidate(
            calibration_cases=[],
            candidate_evidence_path=Path("missing"),
            consumer_census={"rows": []},
            output_root=Path("missing"),
            package_conformance={"validated": True},
            python_executable=Path(sys.executable),
            timeout_seconds=30,
            visible_result=_visible_result(),
            workspace=Path("missing"),
        )


def test_case_expectation_labels_cannot_green_a_nonconforming_resolver(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(
        tmp_path,
        "    return _validate(owner, resolved)\n",
        "    return {'wrong': True}\n",
    )
    case = {
        "case_id": "bad",
        "defect_kind": "none",
        "expected_failed_clauses": [],
        "probe": {
            "cli_patch": {"sample_count": 16},
            "file_mapping": {"mode": "strict", "sample_count": 8},
            "role": "TRAINING",
        },
    }
    census = {
        "rows": [{
            "consumer_id": "consumer-a",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.resolve",
        }]
    }
    observations = evaluator._evaluate_candidate(
        calibration_cases=[case],
        candidate_evidence_path=evidence_path,
        consumer_census=census,
        output_root=tmp_path / "evaluation",
        package_conformance={
            "candidate_evidence": "candidate_config_evidence.v2",
            "probe_request": "config_resolution_probe_request.v1",
            "probe_result": "config_resolution_probe_result.v1",
            "validated": True,
        },
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        visible_result=_visible_result(),
        workspace=workspace,
    )
    assert {
        "F1-H03-PUBLIC-RESOLUTION",
        "F1-H04-TRANSACTIONAL-APPLICATION",
        "F1-H05-STRICT-INPUT-CONTRACT",
        "F1-H06-DERIVED-PUBLIC-FIELDS",
        "F1-H09-CROSS-SURFACE-COHERENCE",
    } <= _failed(observations)


def test_root_evaluation_consumes_direct_facts_and_can_green_all_ten(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    observations = evaluator._evaluate_candidate(
        calibration_cases=[{
            "case_id": "nested-precedence",
            "defect_kind": "none",
            "expected_failed_clauses": [],
            "probe": {
                "cli_patch": {"model": {"N": 128}, "n_groups": 7},
                "file_mapping": _TRAINING_ROOT_INPUT,
                "role": "TRAINING",
            },
        }],
        candidate_evidence_path=evidence_path,
        consumer_census={"rows": [{
            "consumer_id": "public-resolution",
            "path": "candidate/config.py",
            "public_entry_route": "candidate.config.resolve",
        }]},
        output_root=tmp_path / "evaluation",
        package_conformance={
            "candidate_evidence": "candidate_config_evidence.v2",
            "probe_request": "config_resolution_probe_request.v1",
            "probe_result": "config_resolution_probe_result.v1",
            "validated": True,
        },
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        visible_result=_root_visible_result(),
        workspace=workspace,
    )
    assert _failed(observations) == set()


_TRAINING_ROOT_INPUT = {
    "model": {"N": 64, "generator_output_mode": "amp_phase"},
    "n_groups": 5,
    "n_subsample": 3,
    "subsample_seed": 17,
    "enable_oversampling": True,
    "neighbor_pool_size": 5,
    "sequential_sampling": True,
}


def test_direct_resolver_protocol_derives_strict_and_validation_facts(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)

    result = evaluator.run_direct_resolver_probe(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "direct-probe",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )

    assert result["facts"] == {
        "F1-H05-STRICT-INPUT-CONTRACT": True,
        "F1-H06-DERIVED-PUBLIC-FIELDS": True,
    }
    assert [row["case_id"] for row in result["transcript"]["rows"]] == list(
        evaluator.DIRECT_RESOLVER_CASE_IDS
    )
    assert all(
        set(row) == {"case_id", "input_before", "input_after", "outcome"}
        and row["outcome"]["kind"] in {"returned", "raised"}
        for row in result["transcript"]["rows"]
    )


def test_direct_resolver_transcript_order_and_digest_tamper_fail_closed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    result = evaluator.run_direct_resolver_probe(
        candidate_evidence_path=evidence_path,
        output_root=tmp_path / "direct-probe",
        python_executable=Path(sys.executable),
        timeout_seconds=30,
        workspace=workspace,
    )
    transcript_path = tmp_path / "direct-probe/transcript.json"
    rows = result["transcript"]["rows"]
    rows[0], rows[1] = rows[1], rows[0]
    _write_canonical(transcript_path, result["transcript"])

    with pytest.raises(evaluator.EvaluatorError, match="digest|order"):
        evaluator.load_direct_resolver_transcript(
            transcript_path,
            expected_sha256=result["transcript_sha256"],
        )


def test_direct_resolver_transcript_order_fails_with_a_fresh_digest(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    result = _run_direct_protocol(tmp_path, workspace, evidence_path)
    transcript_path = tmp_path / "direct-probe/transcript.json"
    rows = result["transcript"]["rows"]
    rows[0], rows[1] = rows[1], rows[0]
    _write_canonical(transcript_path, result["transcript"])

    with pytest.raises(evaluator.EvaluatorError, match="order"):
        evaluator.load_direct_resolver_transcript(
            transcript_path,
            expected_sha256=evaluator.file_sha256(transcript_path),
        )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            '            raise ValueError("unknown field")',
            "            if cls is RuntimeConfig:\n"
            "                continue\n"
            '            raise ValueError("unknown field")',
        ),
        (
            "        elif type(item) is not expected:",
            "        elif not isinstance(item, expected):",
        ),
        (
            "        result[key] = deepcopy(item)",
            "        if key != 'n_subsample':\n"
            "            result[key] = deepcopy(item)",
        ),
    ],
    ids=("accept-unknown", "coerce-bool", "drop-retained"),
)
def test_strict_input_defects_flip_only_h05(
    tmp_path: Path, old: str, new: str
) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(tmp_path, old, new)
    facts = _run_direct_protocol(tmp_path, workspace, evidence_path)["facts"]
    assert facts["F1-H05-STRICT-INPUT-CONTRACT"] is False
    assert {clause for clause, value in facts.items() if not value} == {
        "F1-H05-STRICT-INPUT-CONTRACT"
    }


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            '            raise ValueError("invalid grid")',
            "            pass",
        ),
    ],
    ids=("accept-invalid-simulation",),
)
def test_simulation_contract_defects_flip_only_h06(
    tmp_path: Path, old: str, new: str
) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(tmp_path, old, new)
    facts = _run_direct_protocol(tmp_path, workspace, evidence_path)["facts"]
    assert facts["F1-H06-DERIVED-PUBLIC-FIELDS"] is False
    assert {clause for clause, value in facts.items() if not value} == {
        "F1-H06-DERIVED-PUBLIC-FIELDS"
    }


def test_path_only_adapter_cannot_establish_direct_resolver_facts(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    (workspace / "scripts/es_f1_config_resolution_adapter.py").write_text(
        "raise RuntimeError('adapter must not run during direct probe')\n",
        encoding="utf-8",
    )
    assert all(_run_direct_protocol(tmp_path, workspace, evidence_path)["facts"].values())


def test_opaque_direct_resolver_return_fails_closed(tmp_path: Path) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(
        tmp_path,
        "    return _validate(owner, resolved)",
        "    return object()",
    )
    with pytest.raises(evaluator.EvaluatorError, match="opaque"):
        _run_direct_protocol(tmp_path, workspace, evidence_path)


def test_direct_resolver_input_mutation_fails_closed(tmp_path: Path) -> None:
    workspace, evidence_path = _mutated_protocol_workspace(
        tmp_path,
        "def resolve(file_mapping, cli_patch):\n",
        "def resolve(file_mapping, cli_patch):\n"
        "    file_mapping['mutated'] = True\n",
    )
    with pytest.raises(evaluator.EvaluatorError, match="mutated probe input"):
        _run_direct_protocol(tmp_path, workspace, evidence_path)


def test_direct_resolver_transcript_authority_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    workspace, evidence_path = _conforming_protocol_workspace(tmp_path)
    result = _run_direct_protocol(tmp_path, workspace, evidence_path)
    transcript_path = tmp_path / "direct-probe/transcript.json"
    result["transcript"]["rows"][0]["outcome"]["passed"] = True
    _write_canonical(transcript_path, result["transcript"])
    with pytest.raises(evaluator.EvaluatorError, match="outcome"):
        evaluator.load_direct_resolver_transcript(
            transcript_path,
            expected_sha256=evaluator.file_sha256(transcript_path),
        )


def test_roundtrip_uses_a_true_second_audited_process(tmp_path: Path) -> None:
    protected = tmp_path / "candidate"
    protected.mkdir()
    value = {
        "provenance": {"mode": "FILE_MAPPING"},
        "resolved": {"mode": "strict"},
    }
    observed = evaluator.fresh_process_roundtrip(
        value,
        output_root=tmp_path / "roundtrip",
        python_executable=Path(sys.executable),
        protected_workspace=protected,
        timeout_seconds=30,
    )
    assert observed == value
    assert observed is not value


def test_audited_probe_rejects_forbidden_import_and_outside_project_origin(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "candidate"
    workspace.mkdir()
    with pytest.raises(evaluator.EvaluatorError, match="forbidden import"):
        evaluator.run_candidate_probe(
            code="import ptycho.evaluation\n",
            environment={},
            label="forbidden",
            python_executable=Path(sys.executable),
            timeout_seconds=30,
            workspace=workspace,
        )
    outside = tmp_path / "outside"
    (outside / "ptycho").mkdir(parents=True)
    (outside / "ptycho/__init__.py").write_text("", encoding="utf-8")
    (outside / "ptycho/bad.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(evaluator.EvaluatorError, match="outside.*origin"):
        evaluator.run_candidate_probe(
            code="import ptycho.bad\n",
            environment={"PYTHONPATH": str(outside)},
            label="outside-origin",
            python_executable=Path(sys.executable),
            timeout_seconds=30,
            workspace=workspace,
        )


def test_visible_checks_use_one_audited_subprocess_route_and_v3_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "candidate"
    tests = workspace / "tests"
    tests.mkdir(parents=True)
    (tests / "test_baseline.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    (tests / "test_es_f1_config_ownership.py").write_text(
        "def test_contract(): assert True\n", encoding="utf-8"
    )
    visible_checks = {
        "invocation_order": ["PRE_EDIT_FOCUSED", "CANDIDATE_CONFIG"],
        "invocations": [
            {
                "candidate_owned": False,
                "id": "PRE_EDIT_FOCUSED",
                "required": True,
                "selectors": list(SELECTORS),
            },
            {
                "candidate_owned": True,
                "id": "CANDIDATE_CONFIG",
                "required": True,
                "selectors": [CANDIDATE_SELECTOR],
            },
        ],
        "runner": {
            "argv_prefix": ["-m", "pytest", "-q", "-p", "no:cacheprovider"],
            "execution_copy_policy": "disposable-exact-extract.v1",
            "install_policy": "no-install-build-or-editable.v1",
            "mutation_policy": "verify-product-digest-before-after.v1",
            "python_executable": sys.executable,
            "python_executable_sha256": evaluator.file_sha256(Path(sys.executable)),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "required_environment": [
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                {"name": "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "value": "1"},
            ],
            "result_policy": "every-required-invocation-exit-zero.v1",
            "timeout_seconds": 30,
            "working_directory_policy": "external-disposable-invocation-root.v1",
        },
        "schema_version": "es_f1_visible_checks.v3",
        "task_id": "F1",
    }
    calls: list[str] = []
    original = evaluator.run_candidate_probe

    def audited(**kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs["label"])
        return original(**kwargs)

    monkeypatch.setattr(evaluator, "run_candidate_probe", audited)
    before = evaluator.directory_digest(workspace)
    result = evaluator.run_visible_checks(workspace=workspace, visible_checks=visible_checks)
    assert result["schema_version"] == "es-f1-visible-check-result.v3"
    assert result["copy_digest_before"] == result["copy_digest_after"] == before
    assert [row["invocation_id"] for row in result["invocations"]] == [
        "PRE_EDIT_FOCUSED",
        "CANDIDATE_CONFIG",
    ]
    assert all(row["exit_code"] == 0 for row in result["invocations"])
    assert evaluator.directory_digest(workspace) == before
    assert calls == [
        "visible invocation PRE_EDIT_FOCUSED",
        "visible invocation CANDIDATE_CONFIG",
    ]


def test_visible_check_mutation_fails_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "candidate"
    tests = workspace / "tests"
    tests.mkdir(parents=True)
    (tests / "test_baseline.py").write_text(
        textwrap.dedent(
            """
            from pathlib import Path

            def test_mutates():
                Path(__file__).with_name("leak.txt").write_text("leak")
            """
        ),
        encoding="utf-8",
    )
    checks = {
        "invocation_order": ["PRE_EDIT_FOCUSED"],
        "invocations": [{
            "candidate_owned": False,
            "id": "PRE_EDIT_FOCUSED",
            "required": True,
            "selectors": list(SELECTORS),
        }],
        "runner": {
            "argv_prefix": ["-m", "pytest", "-q", "-p", "no:cacheprovider"],
            "execution_copy_policy": "disposable-exact-extract.v1",
            "install_policy": "no-install-build-or-editable.v1",
            "mutation_policy": "verify-product-digest-before-after.v1",
            "python_executable": sys.executable,
            "python_executable_sha256": evaluator.file_sha256(Path(sys.executable)),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "required_environment": [
                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                {"name": "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "value": "1"},
            ],
            "result_policy": "every-required-invocation-exit-zero.v1",
            "timeout_seconds": 30,
            "working_directory_policy": "external-disposable-invocation-root.v1",
        },
        "schema_version": "es_f1_visible_checks.v3",
        "task_id": "F1",
    }
    with pytest.raises(evaluator.EvaluatorError, match="mutated"):
        evaluator.run_visible_checks(workspace=workspace, visible_checks=checks)


def test_hard_finding_schema_is_exact_v3() -> None:
    schema = json.loads(HARD_FINDING_SCHEMA.read_bytes())
    Draft202012Validator.check_schema(schema)
    finding = {
        "candidate_id": "candidate-a",
        "clause_id": "F1-H10-BYPASS-ORACLE",
        "details": "controller observation",
        "disposition": "PRODUCT_DEFECT",
        "evaluator_observation": {"evidence_digest": DIGEST, "satisfied": False},
        "schema_version": "es-f1-hard-finding.v3",
    }
    Draft202012Validator(schema).validate(finding)
    predecessor = deepcopy(finding)
    predecessor["schema_version"] = "es-f1-hard-finding.v2"
    assert list(Draft202012Validator(schema).iter_errors(predecessor))


def test_evaluator_source_contains_no_superseded_task0_or_architecture_authority() -> None:
    source = Path(evaluator.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "ARTIFACT_ERA_IDS",
        "architecture_results",
        "classify_task0_bypass_discovery",
        "lifecycle_probe_result",
        "_LEGACY_BYPASS_AUTHORITY",
    ):
        assert forbidden not in source
