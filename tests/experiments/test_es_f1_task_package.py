from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments.es import task_package  # noqa: E402


F1_ROOT = ROOT / "experiments/orc_effectiveness/f1_es"
PROFILE = F1_ROOT / "task-profile.json"
CHECKS = F1_ROOT / "task/visible-check-manifest.json"
CONTRACT = F1_ROOT / "task/visible-task-contract.json"
EVIDENCE_ROOT = ROOT / "docs/plans/evidence/es-f1-large-scope-refreeze/f1v2"
CENSUS = EVIDENCE_ROOT / "configuration-consumer-census.json"
SELECTORS = EVIDENCE_ROOT / "preedit-selector-manifest.json"
PROJECTION = Path(
    "/home/ollie/.local/state/orchestrator/es-source-projections/"
    "git-sha1/8f191031f233d50a4d020d8a988036e99487f570"
)
SELECTOR_PATHS = (
    "tests/test_simulation_config.py",
    "tests/torch/test_config_bridge.py",
    "tests/torch/test_structural_config_ownership.py",
    "tests/scripts/test_training_backend_selector.py",
    "tests/scripts/test_inference_backend_selector.py",
    "tests/scripts/test_simulation_config_cli.py",
    "tests/torch/test_cli_shared.py",
    "tests/test_workflow_components.py",
    "tests/test_grid_lines_workflow.py",
    "tests/torch/test_workflows_components.py",
    "tests/torch/test_train_lightning_execution_contract.py",
    "tests/torch/test_cli_train_torch.py",
    "tests/studies/test_grid_study_dataset_builder.py",
    "tests/studies/test_tf_reference_cnn_runner.py",
    "tests/studies/test_openfwi_flatvel_a_run_config.py",
)
OUTCOMES = (
    "PUBLIC_RESOLUTION",
    "TRANSACTIONAL_TORCH_APPLICATION",
    "TOLERANT_PATH_RETIREMENT",
    "LEGACY_STATE_ISOLATION",
    "BOUNDARY_VALIDATION_AND_DERIVATION",
    "CONSUMER_MIGRATION",
)
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
BYPASSES = (
    "AMBIENT_CONFIGURATION_READ",
    "TOLERANT_OR_COMPATIBILITY_LOADER",
    "LEGACY_CONFIGURATION_STATE_MUTATION",
)
HOOKS = (
    "CONFIG_SURFACE",
    "CONFIG_CARRIER",
    "TORCH_TRANSACTION",
    "SIMULATION_DERIVATION",
)


def _evidence(*, split_routes: bool = True) -> dict[str, object]:
    routes = (
        [{"roles": list(ROLES), "symbol": "candidate.config.resolve"}]
        if not split_routes
        else [
            {"roles": ["SIMULATION", "TRAINING"], "symbol": "candidate.config.resolve"},
            {
                "roles": ["INFERENCE", "RUNTIME_EXECUTION"],
                "symbol": "candidate.config.resolve_runtime",
            },
        ]
    )
    return {
        "candidate_id": "candidate-a",
        "claims": [
            {
                "clause_id": clause,
                "evidence_paths": ["tests/test_es_f1_config_ownership.py"],
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
            "candidate_test_path": "tests/test_es_f1_config_ownership.py",
        },
        "migration_guide_path": "docs/configuration-migration.md",
        "public_resolution_routes": routes,
        "schema_version": "candidate_config_evidence.v2",
    }


def _request(
    case_ids: tuple[str, ...] = ("file_then_cli", "inference_file"),
) -> dict[str, object]:
    roles = ("TRAINING", "INFERENCE")
    return {
        "candidate_evidence_path": "es_f1_candidate_evidence.json",
        "candidate_evidence_sha256": "sha256:" + "0" * 64,
        "candidate_id": "candidate-a",
        "operation_version": "ptychopinn_public_config_resolution.v1",
        "probe_cases": [
            {
                "case_id": case_id,
                "cli_patch": {
                    "path": f"inputs/{case_id}-cli.json",
                    "sha256": "sha256:" + "c" * 64,
                },
                "file_mapping": {
                    "path": f"inputs/{case_id}-file.json",
                    "sha256": "sha256:" + "f" * 64,
                },
                "role": roles[index],
            }
            for index, case_id in enumerate(case_ids)
        ],
        "schema_version": "config_resolution_probe_request.v1",
    }


def _result(
    case_ids: tuple[str, ...] = ("file_then_cli", "inference_file"),
) -> dict[str, object]:
    return {
        "candidate_id": "candidate-a",
        "operation_version": "ptychopinn_public_config_resolution.v1",
        "probe_results": [
            {"case_id": case_id, "resolved_record_path": f"artifacts/{case_id}.json"}
            for case_id in case_ids
        ],
        "schema_version": "config_resolution_probe_result.v1",
    }


def _write_evidence_and_request(tmp_path: Path, request: dict[str, object]) -> Path:
    evidence_bytes = task_package.canonical_json_bytes(_evidence())
    (tmp_path / "es_f1_candidate_evidence.json").write_bytes(evidence_bytes)
    request["candidate_evidence_sha256"] = (
        "sha256:" + hashlib.sha256(evidence_bytes).hexdigest()
    )
    for row in cast(list[dict[str, object]], request["probe_cases"]):
        for binding_name in ("file_mapping", "cli_patch"):
            binding = cast(dict[str, str], row[binding_name])
            bound_path = tmp_path / binding["path"]
            bound_path.parent.mkdir(parents=True, exist_ok=True)
            bound_path.write_bytes(
                task_package.canonical_json_bytes(
                    {"case_id": row["case_id"], "source": binding_name}
                )
            )
            binding["sha256"] = "sha256:" + hashlib.sha256(
                bound_path.read_bytes()
            ).hexdigest()
    path = tmp_path / "request.json"
    path.write_bytes(task_package.canonical_json_bytes(request))
    return path


def test_checked_in_v3_visible_package_is_coherent() -> None:
    profile = task_package.load_task_profile(PROFILE)
    checks = task_package.load_visible_check_manifest(CHECKS)
    contract = task_package.load_visible_task_contract(CONTRACT)
    assert profile.task_id == contract["task_id"] == "F1"
    assert profile.fixed_output_paths == (
        "scripts/es_f1_config_resolution_adapter.py",
        "es_f1_candidate_evidence.json",
        "tests/test_es_f1_config_ownership.py",
    )
    assert profile.candidate_declared_output_ids == (
        "CONFIGURATION_DECISION_RECORD",
        "CONFIGURATION_MIGRATION_GUIDE",
    )
    assert profile.hard_clause_ids == CLAUSES
    assert profile.focused_selectors == checks.pre_edit_selectors == SELECTOR_PATHS
    assert checks.candidate_selector == "tests/test_es_f1_config_ownership.py"
    assert checks.invocation_order == ("PRE_EDIT_FOCUSED", "CANDIDATE_CONFIG")
    assert checks.timeout_seconds == 7200
    assert tuple(row["id"] for row in contract["visible_outcomes"]) == OUTCOMES
    assert tuple(contract["bypass_classes"]) == BYPASSES
    assert tuple(row["id"] for row in contract["hard_contract"]) == CLAUSES
    assert profile.required_task_seed_schema_version == "es_f1_task_seed.v3"
    assert contract["consumer_census"]["delivered_to_candidate"] is False
    assert contract["probe_authority"] == "path-only-adapter-plus-product-hooks.v2"


def test_provider_visible_bytes_exclude_reference_and_scale_authority() -> None:
    payload = b"".join(
        path.read_bytes()
        for path in (
            F1_ROOT / "task/neutral-task-brief.md",
            CONTRACT,
            CHECKS,
            F1_ROOT / "task/candidate-config-evidence.schema.json",
            F1_ROOT / "task/config-resolution-probe-request.schema.json",
            F1_ROOT / "task/config-resolution-probe-result.schema.json",
        )
    )
    for forbidden in (
        b"7d630bcc",
        b"015ca6e93",
        b"implementation_delta_physical_lines",
        b"reference-product",
    ):
        assert forbidden not in payload


@pytest.mark.parametrize("split_routes", [False, True])
def test_candidate_evidence_accepts_one_or_multiple_public_routes(
    tmp_path: Path, split_routes: bool
) -> None:
    path = tmp_path / "evidence.json"
    path.write_bytes(
        task_package.canonical_json_bytes(_evidence(split_routes=split_routes))
    )


def test_candidate_evidence_requires_exact_ordered_four_hook_table(
    tmp_path: Path,
) -> None:
    path = tmp_path / "evidence.json"
    payload = _evidence()
    path.write_bytes(task_package.canonical_json_bytes(payload))

    loaded = task_package.load_candidate_config_evidence(path)

    assert loaded["evaluation_hooks"] == [
        {"hook_id": hook_id, "symbol": f"candidate.hooks.{hook_id.lower()}"}
        for hook_id in HOOKS
    ]
    assert (
        task_package.load_candidate_config_evidence(path)["candidate_id"]
        == "candidate-a"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-role",
        "extra-role",
        "duplicate-role",
        "reordered-role",
        "claim",
        "authority",
        "predecessor",
    ],
)
def test_candidate_evidence_rejects_tamper(tmp_path: Path, mutation: str) -> None:
    payload = _evidence()
    routes = cast(list[dict[str, object]], payload["public_resolution_routes"])
    if mutation == "missing-role":
        cast(list[str], routes[-1]["roles"]).pop()
    elif mutation == "extra-role":
        cast(list[str], routes[-1]["roles"]).append("EXTRA")
    elif mutation == "duplicate-role":
        cast(list[str], routes[-1]["roles"])[0] = "TRAINING"
    elif mutation == "reordered-role":
        routes.reverse()
    elif mutation == "claim":
        cast(list[object], payload["claims"])[-1] = cast(
            list[object], payload["claims"]
        )[0]
    elif mutation == "authority":
        payload["passed"] = True
    else:
        payload["schema_version"] = "candidate_extension_evidence.v2"
    path = tmp_path / "evidence.json"
    path.write_bytes(task_package.canonical_json_bytes(payload))
    with pytest.raises(task_package.TaskPackageError):
        task_package.load_candidate_config_evidence(path)


def test_probe_request_and_result_are_path_only_and_context_bound(
    tmp_path: Path,
) -> None:
    case_ids = ("file_then_cli", "inference_file")
    request_path = _write_evidence_and_request(tmp_path, _request(case_ids))
    assert (
        task_package.load_config_resolution_probe_request(
            request_path,
            expected_candidate_id="candidate-a",
            expected_case_ids=case_ids,
        )["candidate_id"]
        == "candidate-a"
    )
    result_path = tmp_path / "result.json"
    result_path.write_bytes(task_package.canonical_json_bytes(_result(case_ids)))
    loaded = task_package.load_config_resolution_probe_result(
        result_path, expected_candidate_id="candidate-a", expected_case_ids=case_ids
    )
    assert tuple(row["case_id"] for row in loaded["probe_results"]) == case_ids
    assert (
        "passed" not in loaded
        and "observations" not in loaded
        and "provenance" not in loaded
    )


@pytest.mark.parametrize("binding_name", ["file_mapping", "cli_patch"])
def test_probe_request_rejects_bound_input_byte_tamper(
    tmp_path: Path, binding_name: str
) -> None:
    case_ids = ("file_then_cli", "inference_file")
    request = _request(case_ids)
    request_path = _write_evidence_and_request(tmp_path, request)
    first = cast(list[dict[str, object]], request["probe_cases"])[0]
    binding = cast(dict[str, str], first[binding_name])
    (tmp_path / binding["path"]).write_bytes(b"{}\n")

    with pytest.raises(
        task_package.TaskPackageError,
        match="input.*digest|digest.*input",
    ):
        task_package.load_config_resolution_probe_request(
            request_path,
            expected_candidate_id="candidate-a",
            expected_case_ids=case_ids,
        )


@pytest.mark.parametrize(
    "kind,mutation",
    [
        ("request", "missing"),
        ("request", "extra"),
        ("request", "duplicate"),
        ("request", "reordered"),
        ("request", "digest"),
        ("request", "candidate"),
        ("request", "predecessor"),
        ("result", "missing"),
        ("result", "extra"),
        ("result", "duplicate"),
        ("result", "reordered"),
        ("result", "unsafe"),
        ("result", "duplicate-path"),
        ("result", "candidate"),
        ("result", "predecessor"),
    ],
)
def test_probe_records_reject_tamper(tmp_path: Path, kind: str, mutation: str) -> None:
    case_ids = ("file_then_cli", "inference_file")
    request = _request(case_ids)
    request_path = _write_evidence_and_request(tmp_path, request)
    result = _result(case_ids)
    if kind == "request":
        payload, rows = request, cast(list[dict[str, object]], request["probe_cases"])
        if mutation == "digest":
            payload["candidate_evidence_sha256"] = "sha256:" + "0" * 64
        elif mutation == "candidate":
            payload["candidate_id"] = "candidate-b"
        elif mutation == "predecessor":
            payload["schema_version"] = "lifecycle_probe_request.v3"
        elif mutation == "missing":
            rows.pop()
        elif mutation == "extra":
            rows.append(dict(rows[-1], case_id="extra"))
        elif mutation == "duplicate":
            rows[-1] = dict(rows[0])
        else:
            rows.reverse()
        request_path.write_bytes(task_package.canonical_json_bytes(payload))
        with pytest.raises(task_package.TaskPackageError):
            task_package.load_config_resolution_probe_request(
                request_path,
                expected_candidate_id="candidate-a",
                expected_case_ids=case_ids,
            )
    else:
        payload, rows = result, cast(list[dict[str, object]], result["probe_results"])
        if mutation == "candidate":
            payload["candidate_id"] = "candidate-b"
        elif mutation == "predecessor":
            payload["schema_version"] = "lifecycle_probe_result.v3"
        elif mutation == "missing":
            rows.pop()
        elif mutation == "extra":
            rows.append(
                {"case_id": "extra", "resolved_record_path": "artifacts/extra.json"}
            )
        elif mutation == "duplicate":
            rows[-1] = dict(rows[0])
        elif mutation == "reordered":
            rows.reverse()
        elif mutation == "unsafe":
            rows[0]["resolved_record_path"] = "../escape.json"
        else:
            rows[-1]["resolved_record_path"] = rows[0]["resolved_record_path"]
        result_path = tmp_path / "result.json"
        result_path.write_bytes(task_package.canonical_json_bytes(payload))
        with pytest.raises(task_package.TaskPackageError):
            task_package.load_config_resolution_probe_result(
                result_path,
                expected_candidate_id="candidate-a",
                expected_case_ids=case_ids,
            )


def test_probe_loaders_require_evaluator_context(tmp_path: Path) -> None:
    request_path = _write_evidence_and_request(tmp_path, _request())
    result_path = tmp_path / "result.json"
    result_path.write_bytes(task_package.canonical_json_bytes(_result()))
    for loader in (
        lambda: task_package.load_config_resolution_probe_request(request_path),
        lambda: task_package.load_config_resolution_probe_result(result_path),
    ):
        with pytest.raises(task_package.TaskPackageError):
            loader()


def test_census_is_two_identical_fresh_projection_scans() -> None:
    census = task_package.load_configuration_consumer_census(CENSUS)
    first = task_package.scan_configuration_consumers(
        PROJECTION, "8f191031f233d50a4d020d8a988036e99487f570"
    )
    second = task_package.scan_configuration_consumers(
        PROJECTION, "8f191031f233d50a4d020d8a988036e99487f570"
    )
    assert first == second
    assert first["rows"] == census["rows"]
    assert census["projection"] == {
        "commit": "8f191031f233d50a4d020d8a988036e99487f570",
        "tree": "e64f3c05f5a0894f41c047d128a9040a2cda6764",
    }
    assert census["first_scan_sha256"] == census["second_scan_sha256"]
    assert census["consumer_count"] == len(census["rows"]) > 0
    assert census["production_responsibility_paths"] == sorted(
        set(census["production_responsibility_paths"])
    )
    assert census["production_responsibility_physical_lines"] > 0


def test_census_rows_are_closed_and_assigned() -> None:
    census = task_package.load_configuration_consumer_census(CENSUS)
    domains = {
        "CORE_CONFIGURATION",
        "TENSORFLOW_BACKEND",
        "TORCH_BACKEND",
        "CLI_ENTRY_POINT",
        "WORKFLOW_COMPONENT",
        "STUDY_SCRIPT",
    }
    seen = set()
    for row in census["rows"]:
        assert row["consumer_domain"] in domains
        assert row["match_kind"] in {"CONFIGURATION_READ", "CONFIGURATION_CONSTRUCTION"}
        assert set(row["bypass_classes"]) <= set(BYPASSES)
        assert row["responsibility_ids"]
        span = row["source_span"]
        key = (row["path"], span["start_line"], span["start_col"], row["match_kind"])
        assert key not in seen
        seen.add(key)


def test_census_does_not_misclassify_payload_or_framework_config() -> None:
    rows = task_package.load_configuration_consumer_census(CENSUS)["rows"]
    assert all(
        "TOLERANT_OR_COMPATIBILITY_LOADER" not in row["bypass_classes"]
        for row in rows
        if "payload." in row["transitive_wrapper_chain"][-1]
    )
    assert all(
        not row["transitive_wrapper_chain"][-1].startswith("tf.config.") for row in rows
    )


def test_census_marks_only_explicit_ambient_configuration_reads(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    source = repository / "scripts/example.py"
    source.parent.mkdir()
    source.write_text(
        "import os\n"
        "config = {'local': True}\n"
        "def resolve(args):\n"
        "    local = args.config\n"
        "    return local, os.environ['APP_CONFIG_PATH']\n",
        encoding="utf-8",
    )
    subprocess.run(("git", "init", "-q", str(repository)), check=True)
    subprocess.run(("git", "-C", str(repository), "add", "."), check=True)
    subprocess.run(
        (
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=Task Test",
            "-c",
            "user.email=task@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ),
        check=True,
    )
    commit = subprocess.check_output(
        ("git", "-C", str(repository), "rev-parse", "HEAD"), text=True
    ).strip()
    rows = task_package.scan_configuration_consumers(repository, commit)["rows"]
    ambient = [
        row for row in rows if "AMBIENT_CONFIGURATION_READ" in row["bypass_classes"]
    ]
    assert len(ambient) == 1
    assert ambient[0]["transitive_wrapper_chain"][-1] == "os.environ"


@pytest.mark.parametrize("mutation", ["row", "wrapper", "bypass", "digest"])
def test_census_rejects_tamper(tmp_path: Path, mutation: str) -> None:
    payload = json.loads(CENSUS.read_bytes())
    if mutation == "row":
        payload["rows"].pop()
    elif mutation == "wrapper":
        payload["rows"][0]["transitive_wrapper_chain"] = []
    elif mutation == "bypass":
        payload["rows"][0]["bypass_classes"] = ["EXTRA"]
    else:
        payload["record_sha256"] = "sha256:" + "0" * 64
    path = tmp_path / CENSUS.name
    path.write_bytes(task_package.canonical_json_bytes(payload))
    path.with_name("configuration-consumer-census.schema.json").write_bytes(
        CENSUS.with_name("configuration-consumer-census.schema.json").read_bytes()
    )
    with pytest.raises(task_package.TaskPackageError):
        task_package.load_configuration_consumer_census(path)


def test_selector_manifest_freezes_exact_green_projection_baseline() -> None:
    manifest = task_package.load_f1v2_selector_manifest(SELECTORS)
    assert tuple(manifest["selectors"]) == SELECTOR_PATHS
    assert manifest["selector_count"] == 15
    assert manifest["collected_test_count"] == 386
    assert manifest["outcomes"] == {
        "error": 0,
        "failed": 0,
        "passed": 386,
        "skipped": 0,
    }
    assert (
        manifest["ordered_module_list_sha256"]
        == "sha256:fd9b06bd75d8caba9c7f4088279f1cbde500879019e6f5431aaf8708f7bb51ea"
    )
    assert (
        manifest["configuration_consumer_census_sha256"]
        == json.loads(CENSUS.read_bytes())["record_sha256"]
    )


def test_predecessor_seed_is_not_execution_ready_during_task1() -> None:
    with pytest.raises(task_package.TaskPackageError) as caught:
        task_package.load_execution_ready_task_profile(
            PROFILE,
            task_seed_manifest_path=F1_ROOT / "task-seed-manifest.json",
        )
    assert caught.value.code == "task_package_seed_not_ready"


def test_all_task1_schemas_are_closed_and_valid() -> None:
    from jsonschema import Draft202012Validator

    schemas = tuple((F1_ROOT / "task").glob("*.schema.json")) + (
        F1_ROOT / "task-profile.schema.json",
        CENSUS.with_name("configuration-consumer-census.schema.json"),
        SELECTORS.with_name("preedit-selector-manifest.schema.json"),
    )
    for path in schemas:
        schema = json.loads(path.read_bytes())
        Draft202012Validator.check_schema(schema)
        stack = [schema]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if value.get("type") == "object":
                    assert value.get("additionalProperties") is False
                    assert "required" in value
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
