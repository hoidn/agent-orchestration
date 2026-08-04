from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from threading import Lock
from types import ModuleType
from typing import Any, Mapping, cast

import pytest

from orchestrator.providers.executor import ProviderExecutionResult
from orchestrator.workflow.executable_ir import TrialStepConfig
from orchestrator.workflow.run_ref.bundle_transport import (
    write_bundle_capsule_directory,
)
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.run_ref.runtime import (
    RunRefChildLaunch,
    RunRefRuntimeDependencies,
    RunRefRuntimeError,
)
from orchestrator.workflow.trial.adjudication import (
    TrialEvaluationDependencies,
    evaluate_trial_execution,
)
from orchestrator.workflow.trial.config import build_trial_runtime_request
from orchestrator.workflow.trial.contracts import (
    TrialCellKey,
    build_sealed_opaque_label_map,
    derive_trial_cell_effect_scopes,
)
from orchestrator.workflow.trial.runtime import (
    TrialRuntimeDependencies,
    execute_trial_cells,
)
from orchestrator.workflow.trial.sdk import TrialRunResult
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ATTEMPTS_PATH = REPOSITORY_ROOT / "scripts/experiments/es/attempts.py"
ATTEMPT_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "experiments/orc_effectiveness/f1_es/attempt-record.schema.json"
)


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


decision_lock = _load(
    REPOSITORY_ROOT / "scripts/experiments/es/decision_lock.py",
    "es_attempts_decision_lock",
)
qa_workflows = _load(
    REPOSITORY_ROOT / "tests/experiments/test_es_qa_placement_workflows.py",
    "es_attempts_qa_workflows",
)
sys.path.insert(0, str(ATTEMPTS_PATH.parent))
try:
    attempts = cast(
        ModuleType,
        _load(ATTEMPTS_PATH, "es_attempts") if ATTEMPTS_PATH.is_file() else None,
    )
finally:
    sys.path.remove(str(ATTEMPTS_PATH.parent))


class _Registry:
    def exists(self, name: str) -> bool:
        return bool(name)

    def merge_params(self, name: str, params: dict[str, object]):
        assert name
        return dict(params)


class _Composer:
    def read_prompt_source(self, source, **_kwargs):
        assert set(source) == {"asset_file"}
        return "Judge the selected evidence against this fixed rubric.", None


class _Scorer:
    def prepare_invocation(self, provider, params, context, **kwargs):
        assert provider
        assert isinstance(params.params, dict)
        assert context == {}
        labels = tuple(
            dict.fromkeys(
                re.findall(r"opaque-[0-9a-f]{64}", kwargs["prompt_content"])
            )
        )
        assert len(labels) == 1
        return labels[0], None

    def execute(self, label, *, cwd):
        return ProviderExecutionResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "candidate_id": label,
                    "score": 0.5,
                    "summary": "the selected result satisfies the rubric",
                    "citations": ["validated_result"],
                }
            ).encode("utf-8"),
            stderr=b"",
            duration_ms=3,
        )


def _evaluation_dependencies() -> TrialEvaluationDependencies:
    return TrialEvaluationDependencies(
        provider_registry=_Registry(),
        prompt_composer=_Composer(),
        provider_executor=_Scorer(),
        check_runner=lambda command, **_kwargs: subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=b"visible checks passed\n",
            stderr=b"",
        ),
    )


def _sha(fill: str) -> str:
    return "sha256:" + fill * 64


def _lock_and_schedule() -> tuple[dict[str, Any], dict[str, Any]]:
    schedule = decision_lock.generate_randomization_manifest(_sha("a"))
    bindings = {
        "arm_workflow_sha256": _sha("1"),
        "environment_lock_sha256": _sha("2"),
        "evaluator_fixture_manifest_sha256": _sha("3"),
        "prompt_manifest_sha256": _sha("4"),
        "randomization_manifest_sha256": (
            "sha256:"
            + hashlib.sha256(decision_lock.canonical_json_bytes(schedule)).hexdigest()
        ),
        "report_schema_sha256": _sha("6"),
        "source_projection_manifest_sha256": _sha("7"),
        "task_profile_sha256": _sha("8"),
        "task_seed_manifest_sha256": _sha("9"),
    }
    return (
        decision_lock.build_decision_lock(
            bindings=bindings,
            randomization_manifest=schedule,
        ),
        schedule,
    )


def _trial_fixture(
    tmp_path: Path,
    *,
    failed_arm: str | None = None,
    built: Any | None = None,
    common_inputs: Mapping[str, object] | None = None,
):
    if built is None:
        built = qa_workflows._build_trial()
    [trial_node] = [
        node
        for node in built.validated_bundle.ir.nodes.values()
        if isinstance(node.execution_config, TrialStepConfig)
    ]
    step_config = cast(TrialStepConfig, trial_node.execution_config)
    if common_inputs is None:
        common_inputs = {
            "task": "Implement the frozen F1 extension-boundary task.",
            "check_contract": "Run the frozen visible F1 check manifest.",
            "model": "gpt-5.5",
            "effort": "high",
        }
    common_inputs = dict(common_inputs)
    request = build_trial_runtime_request(
        step_config=step_config,
        visit=RunRefVisitKey(
            parent_run_id="es-attempt-fixture",
            execution_frame_id="root",
            call_frame_id=None,
            step_id=trial_node.step_id,
            visit_count=1,
        ),
        resolved_inputs_by_arm={
            arm.arm_id: common_inputs for arm in step_config.trial.arms
        },
    )
    parent_workspace = (tmp_path / "parent-workspace").resolve()
    parent_workspace.mkdir(parents=True)
    parent_run_root = (tmp_path / "parent-run-root").resolve()
    parent_run_root.mkdir(parents=True)
    run_ref_root = (tmp_path / "run-ref-root").resolve()
    capsule_dir = (tmp_path / "capsule").resolve()
    assert built.run_ref_bundle_capsule is not None
    write_bundle_capsule_directory(capsule_dir, built.run_ref_bundle_capsule)
    scopes = derive_trial_cell_effect_scopes(
        request=request,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
    )
    cell_domain = cast(tuple[TrialCellKey, ...], request.cell_domain)
    sealed = build_sealed_opaque_label_map(
        cell_domain,
        salt=b"es-task5-attempt-accounting" * 2,
    )
    replies_by_arm = {
        "DIRECT": (qa_workflows._reply("I"),),
        "DESIGN_QA": (
            qa_workflows._reply("D"),
            qa_workflows._reply("DR", decision="APPROVE"),
            qa_workflows._reply("I"),
        ),
        "PRODUCT_QA": (
            qa_workflows._reply("I"),
            qa_workflows._reply("PR", decision="APPROVE"),
        ),
        "RICH": (
            qa_workflows._reply("D"),
            qa_workflows._reply("DR", decision="APPROVE"),
            qa_workflows._reply("I"),
            qa_workflows._reply("PR", decision="APPROVE"),
        ),
    }
    child_lock = Lock()

    def dependencies_for(
        cell: TrialCellKey,
        _request: object,
    ) -> RunRefRuntimeDependencies:
        def launch(launch_request: RunRefChildLaunch):
            if cell.arm_id == failed_arm:
                raise RunRefRuntimeError(
                    "run_ref_child_launch_failed",
                    "fixture_cell_failure",
                )
            with child_lock:
                scripted = qa_workflows._scripted_runtime(
                    launch_request.workspace,
                    entry_workflow=qa_workflows.ARM_ENTRYPOINTS[cell.arm_id],
                    replies=replies_by_arm[cell.arm_id],
                    run_id=launch_request.child_run_id,
                )
            return qa_workflows._scripted_trial_child_process(
                launch_request,
                scripted_run=scripted,
            )

        return RunRefRuntimeDependencies(
            materialize_source=qa_workflows._materialize_trial_source,
            launch_child=launch,
        )

    execution = execute_trial_cells(
        request,
        parent_state={"bound_inputs": common_inputs, "steps": {}},
        parent_workspace=parent_workspace,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
        capsule_dir=capsule_dir,
        sealed_opaque_labels=sealed,
        dependencies=TrialRuntimeDependencies(
            run_ref_dependencies=dependencies_for,
        ),
    )
    evaluate_trial_execution(
        request,
        execution,
        parent_workspace=parent_workspace,
        dependencies=_evaluation_dependencies(),
    )
    return {
        "request": request,
        "parent_workspace": parent_workspace,
        "sealed": sealed,
        "execution": execution,
    }


@pytest.fixture(scope="module")
def complete_trial(tmp_path_factory: pytest.TempPathFactory):
    return _trial_fixture(tmp_path_factory.mktemp("es-attempt-complete"))


@pytest.fixture(scope="module")
def treatment_failure_trial(tmp_path_factory: pytest.TempPathFactory):
    return _trial_fixture(
        tmp_path_factory.mktemp("es-attempt-treatment-failure"),
        failed_arm="DESIGN_QA",
    )


def _route_ids(
    lock: Mapping[str, Any],
    *,
    failed_arm: str | None = None,
) -> dict[str, str]:
    routes = lock["route_contract"]["terminal_routes"]
    return {
        arm: next(
            row["route_id"]
            for row in routes
            if row["arm"] == arm
            and row["completed"] is (arm != failed_arm)
        )
        for arm in lock["route_contract"]["arms"]
    }


def _accounting(
    lock: Mapping[str, Any],
    *,
    adjudication: bool,
    failed_arm: str | None = None,
    failed_review_slot: str | None = None,
) -> tuple[dict[str, str], str, list[dict[str, object]], list[dict[str, str]]]:
    route_ids = _route_ids(lock, failed_arm=failed_arm)
    route_by_id = {
        row["route_id"]: row
        for row in lock["route_contract"]["terminal_routes"]
    }
    evaluation = next(
        row
        for row in lock["route_contract"]["evaluation_routes"]
        if row["adjudication"] is adjudication
    )
    review_slots = evaluation["call_slots"][4:]
    settlements = [
        {
            "call_slot_id": slot,
            "status": "FAILED" if slot == failed_review_slot else "SUCCEEDED",
            "record_sha256": canonical_sha256({"slot": slot, "record": True}),
            "receipt_sha256": canonical_sha256({"slot": slot, "receipt": True}),
        }
        for slot in review_slots
    ]
    receipt_slots = [
        slot
        for arm in lock["route_contract"]["arms"]
        for slot in route_by_id[route_ids[arm]]["call_slots"]
    ] + list(evaluation["call_slots"])
    receipts = [
        {
            "call_slot_id": slot,
            "receipt_sha256": canonical_sha256({"slot": slot, "receipt": True}),
        }
        for slot in receipt_slots
    ]
    return route_ids, evaluation["route_id"], settlements, receipts


def _build(
    trial: Mapping[str, Any],
    *,
    failed_arm: str | None = None,
    adjudication: bool = False,
    failed_review_slot: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    assert attempts is not None
    lock, schedule = _lock_and_schedule()
    routes, evaluation_route, reviews, receipts = _accounting(
        lock,
        adjudication=adjudication,
        failed_arm=failed_arm,
        failed_review_slot=failed_review_slot,
    )
    arguments: dict[str, Any] = {
        "attempt_id": "ES-ATTEMPT-01",
        "decision_lock": lock,
        "randomization_manifest": schedule,
        "expected_bindings": deepcopy(lock["bindings"]),
        "request": trial["request"],
        "sealed_opaque_labels": trial["sealed"],
        "trial_event_ledger_path": trial["execution"].ledger_path,
        "arm_route_ids": routes,
        "evaluation_route_id": evaluation_route,
        "material_disagreement": adjudication,
        "review_settlements": reviews,
        "receipt_bindings": receipts,
        "source_task_binding_valid": True,
        "controller_launch_preallocation_failed": False,
        "common_provider_outage_proven": False,
        "evaluation_bytes_valid": True,
        "blinding_join_valid": True,
        "interrupted": False,
    }
    arguments.update(overrides)
    return attempts.build_attempt_record(**arguments)


def _packet_artifact_index(trial: Mapping[str, Any]) -> dict[str, Any]:
    request = trial["request"]
    path = (
        trial["parent_workspace"]
        / "artifacts"
        / "trials"
        / request.digest.removeprefix("sha256:")
        / "packets"
        / "index.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _frozen_trial_authority(trial: Mapping[str, Any]) -> bytes:
    frozen = attempts.freeze_trial_artifact_authority(
        trial["request"],
        trial["sealed"],
    )
    return frozen.canonical_bytes


def _trial_result(trial: Mapping[str, Any]) -> TrialRunResult:
    return TrialRunResult.failed(
        run_id=trial["request"].visit.parent_run_id,
        code="fixture_terminal_failure",
        message="public result supplies the exact parent run identity",
    )


def _build_from_artifacts(
    trial: Mapping[str, Any],
    *,
    failed_arm: str | None = None,
    adjudication: bool = False,
    failed_review_slot: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    assert attempts is not None
    lock, schedule = _lock_and_schedule()
    routes, evaluation_route, reviews, receipts = _accounting(
        lock,
        adjudication=adjudication,
        failed_arm=failed_arm,
        failed_review_slot=failed_review_slot,
    )
    request = trial["request"]
    sealed = trial["sealed"]
    packet_index = _packet_artifact_index(trial)
    header = json.loads(
        trial["execution"].ledger_path.read_bytes().splitlines()[0]
    )
    arguments: dict[str, Any] = {
        "attempt_id": "ES-ATTEMPT-01",
        "decision_lock": lock,
        "randomization_manifest": schedule,
        "expected_bindings": deepcopy(lock["bindings"]),
        "frozen_trial_artifact_authority": _frozen_trial_authority(trial),
        "trial_result": _trial_result(trial),
        "observed_header_row_digest": header["row_digest"],
        "observed_sealed_opaque_labels": sealed,
        "trial_event_ledger_path": trial["execution"].ledger_path,
        "packet_artifact_index": packet_index,
        "arm_route_ids": routes,
        "evaluation_route_id": evaluation_route,
        "material_disagreement": adjudication,
        "review_settlements": reviews,
        "receipt_bindings": receipts,
        "source_task_binding_valid": True,
        "controller_launch_preallocation_failed": False,
        "common_provider_outage_proven": False,
        "evaluation_bytes_valid": True,
        "blinding_join_valid": True,
        "interrupted": False,
    }
    arguments.update(overrides)
    return attempts.build_attempt_record_from_artifacts(**arguments)


def test_attempt_module_and_closed_schema_exist() -> None:
    assert attempts is not None, "Task-5 attempt-accounting module is missing"
    assert ATTEMPT_SCHEMA_PATH.is_file()


def test_frozen_trial_artifact_authority_round_trips_canonical_package_bytes(
    complete_trial,
) -> None:
    request = complete_trial["request"]
    frozen = attempts.freeze_trial_artifact_authority(
        request,
        complete_trial["sealed"],
    )

    loaded = attempts.load_frozen_trial_artifact_authority(
        frozen.canonical_bytes
    )

    assert loaded == frozen
    assert loaded.digest == canonical_sha256(loaded.record)
    assert loaded.record["parent_run_id_binding"] == "trial_run_result.run_id"
    assert "parent_run_id" not in loaded.record["visit_template"]
    assert loaded.record["request_template"]["resolved_inputs_by_arm"] == (
        request.record["resolved_inputs_by_arm"]
    )
    assert loaded.record["runtime_budget"] == request.static_config.budget
    assert loaded.record["trial_schedule"] == {
        "reps": request.static_config.reps,
        "max_concurrency": request.static_config.max_concurrency,
    }
    assert loaded.record["evaluation"] == request.static_config.evaluation
    assert loaded.record["sealed_opaque_label_policy"] == {
        "schema_version": "trial_opaque_label_map.v1",
        "cell_domain": [cell.record for cell in request.cell_domain],
        "opaque_label_pattern": "^opaque-[0-9a-f]{64}$",
        "labels_unique": True,
        "digest_contract": "canonical_sha256(record)",
    }
    assert "sealed_opaque_label_map" not in loaded.record


def test_frozen_trial_authority_is_independent_of_fresh_randomized_labels(
    complete_trial,
) -> None:
    request = complete_trial["request"]
    first = attempts.freeze_trial_artifact_authority(
        request,
        complete_trial["sealed"],
    )
    second = attempts.freeze_trial_artifact_authority(
        request,
        build_sealed_opaque_label_map(
            request.cell_domain,
            salt=b"different-fresh-run-random-label-salt",
        ),
    )

    assert first.canonical_bytes == second.canonical_bytes


def test_valid_attempt_derives_exact_e2_and_evaluation_accounting(
    complete_trial,
) -> None:
    record = _build(complete_trial)

    assert record["status"] == "VALID"
    assert record["invalidity_code"] is None
    assert record["resume_policy"] == "FORBIDDEN"
    assert record["e2_authority"]["coherent_allocation"] is True
    assert record["e2_authority"]["treatment_started"] is True
    assert len(record["e2_authority"]["arm_settlements"]) == 4
    assert len(record["e2_authority"]["scorer_settlements"]) == 4
    assert record["accounting"]["terminal_authority_complete"] is True
    assert record["accounting"]["call_count"] == len(
        record["accounting"]["receipt_bindings"]
    )


def test_artifact_backed_attempt_equals_request_backed_attempt(
    complete_trial,
) -> None:
    assert _build_from_artifacts(complete_trial) == _build(complete_trial)


def _rewrite_row_digest(record: dict[str, Any]) -> None:
    preimage = {key: value for key, value in record.items() if key != "row_digest"}
    record["row_digest"] = canonical_sha256(preimage)


def _write_header_drift(
    source: Path,
    destination: Path,
    mutation: str,
) -> None:
    [header, *_] = [json.loads(line) for line in source.read_bytes().splitlines()]
    payload = header["payload"]
    if mutation == "static":
        payload["trial_static_config_digest"] = _sha("f")
    elif mutation == "step":
        payload["trial_step_config_digest"] = _sha("f")
    elif mutation == "arm":
        payload["arm_run_ref_authorities"][0][
            "run_ref_step_config_digest"
        ] = _sha("f")
    elif mutation == "evaluation":
        payload["evaluation_digest"] = _sha("f")
    elif mutation == "budget":
        payload["budget_digest"] = _sha("f")
    elif mutation == "result":
        payload["result_contract_digest"] = _sha("f")
    elif mutation == "compiler":
        payload["compiler_runtime_identity_digest"] = _sha("f")
    elif mutation == "visit":
        payload["visit"]["step_id"] += "-drifted"
    elif mutation == "request":
        payload["trial_request_digest"] = _sha("f")
    elif mutation == "window":
        payload["runtime_budget_window"]["arm_deadlines"][0][
            "deadline_unix_ns"
        ] += 1
        payload["runtime_budget_window_digest"] = canonical_sha256(
            payload["runtime_budget_window"]
        )
    else:  # pragma: no cover - closed test helper
        raise AssertionError(mutation)
    _rewrite_row_digest(header)
    destination.write_bytes(
        json.dumps(
            header,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _write_check_drift(source: Path, destination: Path) -> None:
    records = [json.loads(line) for line in source.read_bytes().splitlines()]
    check_index = next(
        index for index, record in enumerate(records) if record["kind"] == "check_settled"
    )
    prefix = records[: check_index + 1]
    prefix[-1]["payload"]["check_id"] += "-drifted"
    prefix[-1]["payload"]["check_result"]["check_id"] += "-drifted"
    _rewrite_row_digest(prefix[-1])
    destination.write_bytes(
        b"".join(
            json.dumps(
                record,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
            for record in prefix
        )
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "static",
        "step",
        "arm",
        "evaluation",
        "budget",
        "result",
        "compiler",
        "visit",
        "request",
        "window",
    ],
)
def test_artifact_backed_attempt_classifies_self_consistent_header_drift(
    complete_trial,
    tmp_path: Path,
    mutation: str,
) -> None:
    source = complete_trial["execution"].ledger_path
    drifted = tmp_path / f"{mutation}-drift.jsonl"
    _write_header_drift(source, drifted, mutation)

    record = _build_from_artifacts(
        complete_trial,
        trial_event_ledger_path=drifted,
        packet_artifact_index=None,
        arm_route_ids={},
        evaluation_route_id=None,
        material_disagreement=False,
        review_settlements=[],
        receipt_bindings=[],
        interrupted=True,
    )

    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"
    assert record["e2_authority"]["ledger_input_status"] == "INVALID_SUPPLIED"


def test_artifact_backed_attempt_classifies_authored_check_drift(
    complete_trial,
    tmp_path: Path,
) -> None:
    drifted = tmp_path / "check-drift.jsonl"
    _write_check_drift(complete_trial["execution"].ledger_path, drifted)

    record = _build_from_artifacts(
        complete_trial,
        trial_event_ledger_path=drifted,
        packet_artifact_index=None,
        arm_route_ids={},
        evaluation_route_id=None,
        material_disagreement=False,
        review_settlements=[],
        receipt_bindings=[],
        interrupted=True,
    )

    assert record["e2_authority"]["ledger_input_status"] == "INVALID_SUPPLIED"
    assert record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"


@pytest.mark.parametrize("mutation", ["freeze_digest", "packet_row", "packet_label", "missing"])
def test_artifact_backed_attempt_preserves_packet_index_crosschecks(
    complete_trial,
    mutation: str,
) -> None:
    changed = deepcopy(_packet_artifact_index(complete_trial))
    if mutation == "freeze_digest":
        changed["evidence_frozen_row_digest"] = _sha("f")
    elif mutation == "packet_row":
        changed["packets"][0]["packet_digest"] = _sha("f")
    elif mutation == "packet_label":
        changed["packets"][0]["opaque_label"] = "opaque-" + "f" * 64
    else:
        changed = None

    record = _build_from_artifacts(
        complete_trial,
        packet_artifact_index=changed,
        arm_route_ids={},
        evaluation_route_id=None,
        material_disagreement=False,
        review_settlements=[],
        receipt_bindings=[],
        interrupted=True,
    )

    assert record["e2_authority"]["ledger_input_status"] == "INVALID_SUPPLIED"
    assert record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"


def test_supplied_ledger_without_valid_durable_trial_prefix_stays_invalid(
    complete_trial,
) -> None:
    record = _build_from_artifacts(
        complete_trial,
        observed_header_row_digest=None,
        observed_sealed_opaque_labels=None,
        packet_artifact_index=None,
        arm_route_ids={},
        evaluation_route_id=None,
        material_disagreement=False,
        review_settlements=[],
        receipt_bindings=[],
        interrupted=True,
    )

    assert record["e2_authority"]["ledger_input_status"] == "INVALID_SUPPLIED"
    assert record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"


@pytest.mark.parametrize("ledger_kind", ["missing", "corrupt"])
def test_artifact_backed_missing_or_corrupt_ledger_matches_request_classification(
    complete_trial,
    tmp_path: Path,
    ledger_kind: str,
) -> None:
    path: Path | None
    if ledger_kind == "missing":
        path = None
        expected_status = "NOT_SUPPLIED"
    else:
        path = tmp_path / "corrupt-trial-events.jsonl"
        path.write_bytes(b"not-json\n")
        expected_status = "INVALID_SUPPLIED"
    overrides: dict[str, Any] = {
        "trial_event_ledger_path": path,
        "observed_header_row_digest": None,
        "observed_sealed_opaque_labels": None,
        "packet_artifact_index": None,
        "arm_route_ids": {},
        "evaluation_route_id": None,
        "material_disagreement": False,
        "review_settlements": [],
        "receipt_bindings": [],
        "interrupted": True,
    }

    artifact_backed = _build_from_artifacts(complete_trial, **overrides)
    request_backed = _build(
        complete_trial,
        **{
            key: value
            for key, value in overrides.items()
            if key
            not in {
                "packet_artifact_index",
                "observed_header_row_digest",
                "observed_sealed_opaque_labels",
            }
        },
    )

    assert artifact_backed == request_backed
    assert artifact_backed["status"] == "INVALID"
    assert artifact_backed["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"
    assert artifact_backed["e2_authority"]["ledger_input_status"] == expected_status


def test_frozen_trial_artifact_authority_rejects_internal_identity_drift(
    complete_trial,
) -> None:
    record = json.loads(_frozen_trial_authority(complete_trial))
    record["runtime_budget"]["arm_timeout_ms"] += 1
    tampered = json.dumps(
        record,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    with pytest.raises(
        attempts.AttemptAccountingError,
        match="frozen_trial_artifact_authority_invalid",
    ):
        attempts.load_frozen_trial_artifact_authority(tampered)


@pytest.mark.parametrize(
    "mutation",
    [
        "check_missing_field",
        "check_duplicate_id",
        "evaluation_missing_field",
        "evaluation_wrong_type",
    ],
)
def test_frozen_trial_artifact_authority_rejects_malformed_public_evaluation(
    complete_trial,
    mutation: str,
) -> None:
    record = json.loads(_frozen_trial_authority(complete_trial))
    evaluation = record["evaluation"]
    if mutation == "check_missing_field":
        evaluation["checks"][0].pop("command")
    elif mutation == "check_duplicate_id":
        duplicate = deepcopy(evaluation["checks"][0])
        duplicate["authority"] = "invariant"
        evaluation["checks"].append(duplicate)
    elif mutation == "evaluation_missing_field":
        evaluation.pop("provider")
    else:
        evaluation["observation_include"] = "task_spec"
    record["request_template"]["evaluation_digest"] = canonical_sha256(evaluation)
    record["ordered_check_specs"] = sorted(
        evaluation["checks"],
        key=lambda row: {"correctness": 0, "invariant": 1}[row["authority"]],
    )

    with pytest.raises(
        attempts.AttemptAccountingError,
        match="frozen_trial_artifact_authority_invalid",
    ):
        attempts.load_frozen_trial_artifact_authority(canonical_json_bytes(record))


@pytest.mark.parametrize(
    "mutation",
    [
        "incomplete_cartesian",
        "one_arm",
        "seventeen_arms",
        "sixty_five_reps",
        "too_many_cells",
        "concurrency_above_public_limit",
    ],
)
def test_frozen_trial_artifact_authority_rejects_incomplete_or_unbounded_domain(
    complete_trial,
    mutation: str,
) -> None:
    record = json.loads(_frozen_trial_authority(complete_trial))
    template = record["request_template"]
    original_arms = [row["arm_id"] for row in template["arm_run_ref_authorities"]]
    arms = original_arms
    reps = 1
    concurrency = min(4, len(arms))
    if mutation == "one_arm":
        arms = ["ONLY"]
        concurrency = 1
    elif mutation == "seventeen_arms":
        arms = [f"ARM-{index:02d}" for index in range(17)]
    elif mutation == "sixty_five_reps":
        reps = 65
    elif mutation == "too_many_cells":
        arms = [f"ARM-{index:02d}" for index in range(16)]
        reps = 17
    elif mutation == "concurrency_above_public_limit":
        reps = 9
        concurrency = 33
    elif mutation == "incomplete_cartesian":
        reps = 2

    authority_template = template["arm_run_ref_authorities"][0]
    resolved_template = template["resolved_inputs_by_arm"][0]
    template["arm_run_ref_authorities"] = [
        {**authority_template, "arm_id": arm} for arm in arms
    ]
    template["resolved_inputs_by_arm"] = [
        {**resolved_template, "arm_id": arm} for arm in arms
    ]
    domain = [
        {"arm_id": arm, "rep": rep}
        for arm in arms
        for rep in range(1, reps + 1)
    ]
    if mutation == "incomplete_cartesian":
        domain = [cell for cell in domain if cell["rep"] == 1]
    template["cell_domain"] = domain
    template["cell_domain_digest"] = canonical_sha256(domain)
    record["sealed_opaque_label_policy"]["cell_domain"] = domain
    record["trial_schedule"] = {
        "reps": reps,
        "max_concurrency": concurrency,
    }
    record["request_template"]["budget_digest"] = canonical_sha256(
        {
            "reps": reps,
            "max_concurrency": concurrency,
            "budget": record["runtime_budget"],
        }
    )

    with pytest.raises(
        attempts.AttemptAccountingError,
        match="frozen_trial_artifact_authority_invalid",
    ):
        attempts.load_frozen_trial_artifact_authority(canonical_json_bytes(record))


def test_artifact_backed_partial_interruption_matches_request_backed_classification(
    complete_trial,
    tmp_path: Path,
) -> None:
    source = complete_trial["execution"].ledger_path
    lines = source.read_bytes().splitlines(keepends=True)
    records = [json.loads(line) for line in lines]
    started_index = next(
        index
        for index, record in enumerate(records)
        if record["kind"] == "cell_allocation_started"
    )
    partial = tmp_path / "partial-trial-events.jsonl"
    partial.write_bytes(b"".join(lines[: started_index + 1]))
    overrides: dict[str, Any] = {
        "trial_event_ledger_path": partial,
        "packet_artifact_index": None,
        "arm_route_ids": {},
        "evaluation_route_id": None,
        "material_disagreement": False,
        "review_settlements": [],
        "receipt_bindings": [],
        "interrupted": True,
    }

    artifact_backed = _build_from_artifacts(complete_trial, **overrides)
    request_backed = _build(
        complete_trial,
        **{
            key: value
            for key, value in overrides.items()
            if key != "packet_artifact_index"
        },
    )

    assert artifact_backed == request_backed
    assert artifact_backed["status"] == "INVALID"
    assert artifact_backed["invalidity_code"] == (
        "APPARATUS_ACCOUNTING_INCOMPLETE"
    )
    assert artifact_backed["e2_authority"]["treatment_started"] is True


def test_artifact_backed_header_only_outage_matches_request_backed_classification(
    complete_trial,
    tmp_path: Path,
) -> None:
    source = complete_trial["execution"].ledger_path
    header_only = tmp_path / "header-only-trial-events.jsonl"
    header_only.write_bytes(source.read_bytes().splitlines(keepends=True)[0])
    overrides: dict[str, Any] = {
        "trial_event_ledger_path": header_only,
        "packet_artifact_index": None,
        "arm_route_ids": {},
        "evaluation_route_id": None,
        "material_disagreement": False,
        "review_settlements": [],
        "receipt_bindings": [],
        "common_provider_outage_proven": True,
    }

    artifact_backed = _build_from_artifacts(complete_trial, **overrides)
    request_backed = _build(
        complete_trial,
        **{
            key: value
            for key, value in overrides.items()
            if key != "packet_artifact_index"
        },
    )

    assert artifact_backed == request_backed
    assert artifact_backed["invalidity_code"] == (
        "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT"
    )


def test_artifact_backed_treatment_failure_matches_request_backed_outcome(
    treatment_failure_trial,
) -> None:
    artifact_backed = _build_from_artifacts(
        treatment_failure_trial,
        failed_arm="DESIGN_QA",
        failed_review_slot="EVAL.INTEGRATED_REVIEW",
    )
    request_backed = _build(
        treatment_failure_trial,
        failed_arm="DESIGN_QA",
        failed_review_slot="EVAL.INTEGRATED_REVIEW",
    )

    assert artifact_backed == request_backed
    assert artifact_backed["status"] == "VALID"


def test_treatment_failure_and_terminal_review_failure_remain_valid_outcomes(
    treatment_failure_trial,
) -> None:
    record = _build(
        treatment_failure_trial,
        failed_arm="DESIGN_QA",
        failed_review_slot="EVAL.INTEGRATED_REVIEW",
    )

    assert record["status"] == "VALID"
    assert record["invalidity_code"] is None
    assert {row["status"] for row in record["e2_authority"]["arm_settlements"]} == {
        "completed",
        "failed",
    }
    assert record["accounting"]["review_settlements"][-1]["status"] == "FAILED"


def _receipt_bindings_for_selected_routes(
    lock: Mapping[str, Any],
    arm_route_ids: Mapping[str, str],
    evaluation_route_id: str,
) -> list[dict[str, str]]:
    route_by_id = {
        row["route_id"]: row
        for row in lock["route_contract"]["terminal_routes"]
    }
    evaluation_by_id = {
        row["route_id"]: row
        for row in lock["route_contract"]["evaluation_routes"]
    }
    slots = [
        slot
        for arm in lock["route_contract"]["arms"]
        for slot in route_by_id[arm_route_ids[arm]]["call_slots"]
    ] + list(evaluation_by_id[evaluation_route_id]["call_slots"])
    return [
        {
            "call_slot_id": slot,
            "receipt_sha256": canonical_sha256({"slot": slot, "receipt": True}),
        }
        for slot in slots
    ]


def test_terminal_provider_failure_at_success_completing_prefix_is_valid(
    treatment_failure_trial,
) -> None:
    lock, _schedule = _lock_and_schedule()
    routes, evaluation_route, reviews, _receipts = _accounting(
        lock,
        adjudication=False,
        failed_arm="DESIGN_QA",
    )
    routes["DESIGN_QA"] = (
        "DESIGN_QA.D_DR_DREV_I.FAILED_AT_FINAL_CALL"
    )

    record = _build(
        treatment_failure_trial,
        failed_arm="DESIGN_QA",
        arm_route_ids=routes,
        evaluation_route_id=evaluation_route,
        review_settlements=reviews,
        receipt_bindings=_receipt_bindings_for_selected_routes(
            lock,
            routes,
            evaluation_route,
        ),
    )

    assert record["status"] == "VALID"
    assert record["invalidity_code"] is None


def test_completed_arm_cannot_select_final_call_failure_route(
    complete_trial,
) -> None:
    lock, _schedule = _lock_and_schedule()
    routes, evaluation_route, reviews, _receipts = _accounting(
        lock,
        adjudication=False,
    )
    routes["DESIGN_QA"] = (
        "DESIGN_QA.D_DR_DREV_I.FAILED_AT_FINAL_CALL"
    )

    record = _build(
        complete_trial,
        arm_route_ids=routes,
        evaluation_route_id=evaluation_route,
        review_settlements=reviews,
        receipt_bindings=_receipt_bindings_for_selected_routes(
            lock,
            routes,
            evaluation_route,
        ),
    )

    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"


def test_exact_optional_adjudicator_settlement_and_receipt_route_is_valid(
    complete_trial,
) -> None:
    record = _build(complete_trial, adjudication=True)

    assert record["status"] == "VALID"
    assert record["accounting"]["evaluation_route_id"] == (
        "EVALUATION.WITH_ADJUDICATION"
    )
    assert [
        row["call_slot_id"]
        for row in record["accounting"]["review_settlements"]
    ][-2:] == ["EVAL.ADJUDICATOR", "EVAL.INTEGRATED_REVIEW"]

    mismatched = _build(
        complete_trial,
        adjudication=True,
        material_disagreement=False,
    )
    assert mismatched["status"] == "INVALID"
    assert mismatched["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing_receipt", "APPARATUS_ACCOUNTING_INCOMPLETE"),
        ("missing_review", "APPARATUS_ACCOUNTING_INCOMPLETE"),
        ("blinding", "BLINDING_JOIN_INVALID"),
        ("evaluation", "COMMON_EVALUATION_BYTES_INVALID"),
    ],
)
def test_attempt_invalidity_is_derived_from_only_the_six_frozen_codes(
    complete_trial,
    mutation: str,
    expected_code: str,
) -> None:
    lock, _ = _lock_and_schedule()
    routes, evaluation_route, reviews, receipts = _accounting(
        lock,
        adjudication=False,
    )
    overrides: dict[str, Any] = {
        "arm_route_ids": routes,
        "evaluation_route_id": evaluation_route,
        "review_settlements": reviews,
        "receipt_bindings": receipts,
    }
    if mutation == "missing_receipt":
        overrides["receipt_bindings"] = receipts[:-1]
    elif mutation == "missing_review":
        overrides["review_settlements"] = reviews[:-1]
    elif mutation == "blinding":
        overrides["blinding_join_valid"] = False
    else:
        overrides["evaluation_bytes_valid"] = False

    record = _build(complete_trial, **overrides)

    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == expected_code
    assert record["invalidity_code"] in attempts.INVALIDITY_CODES


def test_interruption_after_terminal_authority_is_reportable_without_resume(
    complete_trial,
) -> None:
    record = _build(complete_trial, interrupted=True)

    assert record["status"] == "VALID"
    assert record["interrupted"] is True
    assert record["resume_policy"] == "FORBIDDEN"


def test_interruption_before_complete_accounting_freezes_apparatus_invalid(
    complete_trial,
) -> None:
    lock, _ = _lock_and_schedule()
    routes, evaluation_route, reviews, receipts = _accounting(
        lock,
        adjudication=False,
    )
    record = _build(
        complete_trial,
        interrupted=True,
        arm_route_ids=routes,
        evaluation_route_id=evaluation_route,
        review_settlements=reviews[:-1],
        receipt_bindings=receipts,
    )

    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        (
            {
                "trial_event_ledger_path": None,
                "arm_route_ids": {},
                "evaluation_route_id": None,
                "material_disagreement": False,
                "review_settlements": [],
                "receipt_bindings": [],
                "source_task_binding_valid": False,
            },
            "SOURCE_OR_TASK_BINDING_INVALID",
        ),
        (
            {
                "trial_event_ledger_path": None,
                "arm_route_ids": {},
                "evaluation_route_id": None,
                "material_disagreement": False,
                "review_settlements": [],
                "receipt_bindings": [],
                "controller_launch_preallocation_failed": True,
            },
            "CONTROLLER_LAUNCH_PREALLOCATION_FAILED",
        ),
    ],
)
def test_preallocation_invalidities_are_exact_and_need_no_invented_ledger(
    complete_trial,
    overrides: dict[str, Any],
    expected_code: str,
) -> None:
    record = _build(complete_trial, **overrides)

    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == expected_code
    assert record["e2_authority"]["coherent_allocation"] is False
    assert record["e2_authority"]["ledger_input_status"] == "NOT_SUPPLIED"


@pytest.mark.parametrize(
    ("classifier_override", "expected_code"),
    [
        ({"source_task_binding_valid": False}, "SOURCE_OR_TASK_BINDING_INVALID"),
        (
            {"controller_launch_preallocation_failed": True},
            "CONTROLLER_LAUNCH_PREALLOCATION_FAILED",
        ),
    ],
)
def test_unlaunched_artifact_attempt_uses_null_request_identity_only_for_early_fault(
    complete_trial,
    classifier_override: dict[str, Any],
    expected_code: str,
) -> None:
    record = _build_from_artifacts(
        complete_trial,
        trial_result=None,
        observed_header_row_digest=None,
        observed_sealed_opaque_labels=None,
        trial_event_ledger_path=None,
        packet_artifact_index=None,
        arm_route_ids={},
        evaluation_route_id=None,
        material_disagreement=False,
        review_settlements=[],
        receipt_bindings=[],
        interrupted=True,
        **classifier_override,
    )

    assert record["schema_version"] == "es_attempt_record.v2"
    assert record["trial_request_digest"] is None
    assert record["e2_authority"]["trial_request_digest"] is None
    assert record["e2_authority"]["ledger_input_status"] == "NOT_SUPPLIED"
    assert record["invalidity_code"] == expected_code


def test_unlaunched_null_request_identity_is_rejected_outside_exact_early_fault(
    complete_trial,
) -> None:
    with pytest.raises(
        attempts.AttemptAccountingError,
        match="attempt_unlaunched_authority_invalid",
    ):
        _build_from_artifacts(
            complete_trial,
            trial_result=None,
            observed_header_row_digest=None,
            observed_sealed_opaque_labels=None,
            trial_event_ledger_path=None,
            packet_artifact_index=None,
            arm_route_ids={},
            evaluation_route_id=None,
            material_disagreement=False,
            review_settlements=[],
            receipt_bindings=[],
            interrupted=True,
        )


@pytest.mark.parametrize(
    "classifier_override",
    [
        {"source_task_binding_valid": False},
        {"controller_launch_preallocation_failed": True},
    ],
)
def test_supplied_invalid_ledger_cannot_be_reclassified_as_preallocation(
    complete_trial,
    tmp_path: Path,
    classifier_override: dict[str, Any],
) -> None:
    corrupt = tmp_path / (
        "corrupt-source.jsonl"
        if classifier_override.get("source_task_binding_valid") is False
        else "corrupt-launch.jsonl"
    )
    corrupt.write_bytes(b"not-json\n")

    record = _build(
        complete_trial,
        trial_event_ledger_path=corrupt,
        arm_route_ids={},
        evaluation_route_id=None,
        material_disagreement=False,
        review_settlements=[],
        receipt_bindings=[],
        **classifier_override,
    )

    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"
    assert record["e2_authority"]["ledger_input_status"] == "INVALID_SUPPLIED"


def test_supplied_invalid_ledger_freezes_apparatus_before_accounting_claims(
    complete_trial,
    tmp_path: Path,
) -> None:
    corrupt = tmp_path / "corrupt-with-accounting.jsonl"
    corrupt.write_bytes(b"not-json\n")

    record = _build(
        complete_trial,
        trial_event_ledger_path=corrupt,
        source_task_binding_valid=False,
    )

    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"
    assert record["e2_authority"]["ledger_input_status"] == "INVALID_SUPPLIED"


def test_common_provider_outage_requires_a_valid_header_and_no_treatment(
    complete_trial,
    tmp_path: Path,
) -> None:
    source = complete_trial["execution"].ledger_path
    header_only = tmp_path / "trial-events.jsonl"
    header_only.write_bytes(source.read_bytes().splitlines(keepends=True)[0])

    record = _build(
        complete_trial,
        trial_event_ledger_path=header_only,
        arm_route_ids={},
        evaluation_route_id=None,
        material_disagreement=False,
        review_settlements=[],
        receipt_bindings=[],
        common_provider_outage_proven=True,
    )

    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT"
    assert record["e2_authority"]["coherent_allocation"] is True
    assert record["e2_authority"]["treatment_started"] is False


def test_unreadable_ledger_and_wrong_route_are_apparatus_invalid(
    complete_trial,
    tmp_path: Path,
) -> None:
    corrupt = tmp_path / "corrupt-ledger.jsonl"
    corrupt.write_bytes(b"not-json\n")
    unreadable = _build(complete_trial, trial_event_ledger_path=corrupt)
    assert unreadable["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"

    lock, _ = _lock_and_schedule()
    routes = _route_ids(lock)
    routes["DIRECT"] = next(
        row["route_id"]
        for row in lock["route_contract"]["terminal_routes"]
        if row["arm"] == "DESIGN_QA" and row["completed"] is True
    )
    impossible = _build(complete_trial, arm_route_ids=routes)
    assert impossible["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"


def test_multiple_explicit_invalidity_claims_fail_closed_as_ambiguous(
    complete_trial,
) -> None:
    with pytest.raises(
        attempts.AttemptAccountingError,
        match="attempt_invalidity_ambiguous",
    ):
        _build(
            complete_trial,
            evaluation_bytes_valid=False,
            blinding_join_valid=False,
        )


def test_common_outage_cannot_be_claimed_after_treatment_started(
    complete_trial,
) -> None:
    with pytest.raises(
        attempts.AttemptAccountingError,
        match="common_provider_outage_after_treatment",
    ):
        _build(complete_trial, common_provider_outage_proven=True)


def test_record_validation_rejects_schema_drift_and_post_lock_mutation(
    complete_trial,
) -> None:
    record = _build(complete_trial)
    lock, schedule = _lock_and_schedule()
    attempts.validate_attempt_record(
        record,
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=lock["bindings"],
    )
    for mutation in (
        "extra",
        "digest",
        "invalidity",
        "ledger_input_status",
        "v1",
        "null_request",
    ):
        changed = deepcopy(record)
        if mutation == "extra":
            changed["unexpected"] = True
        elif mutation == "digest":
            changed["decision_lock_sha256"] = _sha("f")
        elif mutation == "ledger_input_status":
            changed["e2_authority"]["ledger_input_status"] = "NOT_SUPPLIED"
        elif mutation == "v1":
            changed["schema_version"] = "es_attempt_record.v1"
        elif mutation == "null_request":
            changed["trial_request_digest"] = None
            changed["e2_authority"]["trial_request_digest"] = None
        else:
            changed["invalidity_code"] = "NOT_A_CODE"
        with pytest.raises(attempts.AttemptAccountingError):
            attempts.validate_attempt_record(
                changed,
                decision_lock=lock,
                randomization_manifest=schedule,
                expected_bindings=lock["bindings"],
            )


def test_attempt_contract_rebuild_rejects_route_call_and_manifest_tampering(
    complete_trial,
) -> None:
    lock, schedule = _lock_and_schedule()
    expected_bindings = deepcopy(lock["bindings"])

    tampered_route = deepcopy(lock)
    tampered_route["route_contract"]["terminal_routes"][0]["route_id"] = (
        "TAMPERED.ROUTE"
    )
    with pytest.raises(attempts.AttemptAccountingError):
        _build(complete_trial, decision_lock=tampered_route)

    tampered_calls = deepcopy(lock)
    tampered_calls["derived"]["call_bounds"][
        "absolute_with_invalid_attempt_capacity"
    ] += 1
    with pytest.raises(attempts.AttemptAccountingError):
        _build(complete_trial, decision_lock=tampered_calls)

    tampered_manifest = deepcopy(schedule)
    tampered_manifest["attempts"][0]["arm_order"].reverse()
    with pytest.raises(attempts.AttemptAccountingError):
        attempts.select_next_attempt_id(
            (),
            decision_lock=lock,
            randomization_manifest=tampered_manifest,
            expected_bindings=expected_bindings,
        )


def test_attempt_contract_rejects_self_consistent_alternate_authority(
    complete_trial,
) -> None:
    lock, _ = _lock_and_schedule()
    expected_bindings = deepcopy(lock["bindings"])
    alternate_manifest = decision_lock.generate_randomization_manifest(_sha("b"))
    alternate_bindings = deepcopy(expected_bindings)
    alternate_bindings["randomization_manifest_sha256"] = (
        "sha256:"
        + hashlib.sha256(
            decision_lock.canonical_json_bytes(alternate_manifest)
        ).hexdigest()
    )
    alternate_lock = decision_lock.build_decision_lock(
        bindings=alternate_bindings,
        randomization_manifest=alternate_manifest,
    )

    with pytest.raises(attempts.AttemptAccountingError):
        _build(
            complete_trial,
            decision_lock=alternate_lock,
            randomization_manifest=alternate_manifest,
            expected_bindings=expected_bindings,
        )


def test_next_attempt_selection_never_reuses_or_skips_a_locked_id() -> None:
    lock, schedule = _lock_and_schedule()
    assert attempts.select_next_attempt_id(
        (),
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=lock["bindings"],
    ) == "ES-ATTEMPT-01"
    assert attempts.select_next_attempt_id(
        ("ES-ATTEMPT-01",),
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=lock["bindings"],
    ) == "ES-ATTEMPT-02"
    with pytest.raises(attempts.AttemptAccountingError):
        attempts.select_next_attempt_id(
            ("ES-ATTEMPT-02",),
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=lock["bindings"],
        )
    with pytest.raises(attempts.AttemptAccountingError):
        attempts.select_next_attempt_id(
            ("ES-ATTEMPT-01", "ES-ATTEMPT-01"),
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=lock["bindings"],
        )


def test_absolute_call_ceiling_and_invalid_attempt_capacity_fail_closed() -> None:
    lock, schedule = _lock_and_schedule()
    ceiling = lock["derived"]["call_bounds"][
        "absolute_with_invalid_attempt_capacity"
    ]
    assert attempts.enforce_absolute_call_ceiling(
        (22, 22, 22, 22),
        invalid_attempt_count=1,
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=lock["bindings"],
    ) == ceiling
    with pytest.raises(
        attempts.AttemptAccountingError,
        match="attempt_call_count_exceeded",
    ):
        attempts.enforce_absolute_call_ceiling(
            (22, 22, 22, 23),
            invalid_attempt_count=1,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=lock["bindings"],
        )
    with pytest.raises(
        attempts.AttemptAccountingError,
        match="attempt_denominator_extended",
    ):
        attempts.enforce_absolute_call_ceiling(
            (1, 1, 1, 1),
            invalid_attempt_count=0,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=lock["bindings"],
        )
    with pytest.raises(
        attempts.AttemptAccountingError,
        match="invalid_attempt_capacity_exceeded",
    ):
        attempts.enforce_absolute_call_ceiling(
            (1, 1),
            invalid_attempt_count=2,
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=lock["bindings"],
        )
