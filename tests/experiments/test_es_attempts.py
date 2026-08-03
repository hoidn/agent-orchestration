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
from orchestrator.workflow.run_ref.contracts import canonical_sha256
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
    attempts = (
        _load(ATTEMPTS_PATH, "es_attempts") if ATTEMPTS_PATH.is_file() else None
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


def _lock_and_schedule() -> tuple[dict[str, Any], dict[str, object]]:
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


def _trial_fixture(tmp_path: Path, *, failed_arm: str | None = None):
    built = qa_workflows._build_trial()
    [trial_node] = [
        node
        for node in built.validated_bundle.ir.nodes.values()
        if isinstance(node.execution_config, TrialStepConfig)
    ]
    step_config = cast(TrialStepConfig, trial_node.execution_config)
    common_inputs: dict[str, object] = {
        "task": "Implement the frozen F1 extension-boundary task.",
        "check_contract": "Run the frozen visible F1 check manifest.",
        "model": "gpt-5.5",
        "effort": "high",
    }
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
    trial: Mapping[str, object],
    *,
    failed_arm: str | None = None,
    adjudication: bool = False,
    failed_review_slot: str | None = None,
    **overrides: object,
) -> dict[str, object]:
    assert attempts is not None
    lock, schedule = _lock_and_schedule()
    routes, evaluation_route, reviews, receipts = _accounting(
        lock,
        adjudication=adjudication,
        failed_arm=failed_arm,
        failed_review_slot=failed_review_slot,
    )
    arguments: dict[str, object] = {
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


def test_attempt_module_and_closed_schema_exist() -> None:
    assert attempts is not None, "Task-5 attempt-accounting module is missing"
    assert ATTEMPT_SCHEMA_PATH.is_file()


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
    overrides: dict[str, object] = {
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
    overrides: dict[str, object],
    expected_code: str,
) -> None:
    record = _build(complete_trial, **overrides)

    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == expected_code
    assert record["e2_authority"]["coherent_allocation"] is False
    assert record["e2_authority"]["ledger_input_status"] == "NOT_SUPPLIED"


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
    classifier_override: dict[str, object],
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
    for mutation in ("extra", "digest", "invalidity", "ledger_input_status"):
        changed = deepcopy(record)
        if mutation == "extra":
            changed["unexpected"] = True
        elif mutation == "digest":
            changed["decision_lock_sha256"] = _sha("f")
        elif mutation == "ledger_input_status":
            changed["e2_authority"]["ledger_input_status"] = "NOT_SUPPLIED"
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
