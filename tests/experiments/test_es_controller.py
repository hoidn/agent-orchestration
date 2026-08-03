from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.trial import ledger as trial_ledger
from orchestrator.workflow.trial.contracts import (
    TrialCellKey,
    build_sealed_opaque_label_map,
)
from orchestrator.workflow.trial.sdk import TrialRunResult
from scripts.experiments.es import (
    attempts,
    controller,
    decision_lock,
    provider_boundary,
    reviews,
)


CONTROLLER = REPOSITORY_ROOT / "scripts/experiments/es/controller.py"
NEW_ES_MODULES = (
    CONTROLLER,
    REPOSITORY_ROOT / "scripts/experiments/es/controller_artifacts.py",
    REPOSITORY_ROOT / "scripts/experiments/es/provider_boundary.py",
)
ARMS = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _record(value: object) -> bytes:
    return canonical_json_bytes(value)


def _write(root: Path, relative: str, value: bytes) -> controller.BoundFile:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return controller.BoundFile(relative, _sha(value))


def _trial_artifact_authority() -> bytes:
    cells = [TrialCellKey(arm, 1).record for arm in ARMS]
    budget = {
        "arm_timeout_ms": 1,
        "trial_timeout_ms": 1,
        "max_evaluator_attempts": 1,
        "max_evaluator_concurrency": 1,
    }
    evaluation = {
        "checks": [
            {
                "authority": "correctness",
                "check_id": "fixture-correctness",
                "command": ["python", "-m", "pytest", "-q"],
                "required": True,
                "timeout_ms": 1,
            },
            {
                "authority": "invariant",
                "check_id": "fixture-invariant",
                "command": ["python", "-m", "pytest", "-q"],
                "required": True,
                "timeout_ms": 1,
            },
        ],
        "provider": "fixture-provider",
        "rubric_asset": "prompts/fixture-rubric.md",
        "evidence_confidentiality": "same_trust_boundary",
        "max_item_bytes": 1,
        "max_packet_bytes": 1,
        "observation_include": [
            "task_spec",
            "validated_result",
            "workspace_delta",
            "check_results",
            "declared_artifacts",
            "failure_evidence",
        ],
        "diff_cap_bytes": 1,
        "reveal_provider_identity": False,
        "aggregation_mode": "independent_rubric",
        "rep_combine": "median",
        "tie": "authored_order",
        "min_abs_improvement": 0.1,
        "max_cost_ratio": 4.0,
        "min_cost_reduction": 0.2,
        "count_failures_as_outcomes": True,
    }
    schedule = {"reps": 1, "max_concurrency": 4}
    record = {
        "schema_version": "es.frozen_trial_artifact_authority.v1",
        "parent_run_id_binding": "trial_run_result.run_id",
        "request_template": {
            "schema_version": "trial_runtime_request.v1",
            "trial_static_config_digest": "sha256:" + "1" * 64,
            "trial_step_config_digest": "sha256:" + "2" * 64,
            "arm_run_ref_authorities": [
                {
                    "arm_id": arm,
                    "run_ref_step_config_digest": "sha256:" + "3" * 64,
                    "result_contract_digest": "sha256:" + "4" * 64,
                }
                for arm in ARMS
            ],
            "evaluation_digest": canonical_sha256(evaluation),
            "budget_digest": canonical_sha256(
                {"reps": 1, "max_concurrency": 4, "budget": budget}
            ),
            "result_contract_digest": "sha256:" + "5" * 64,
            "compiler_runtime_identity_digest": "sha256:" + "6" * 64,
            "resolved_inputs_by_arm": [
                {"arm_id": arm, "inputs": {"fixture": True}} for arm in ARMS
            ],
            "cell_domain": cells,
            "cell_domain_digest": canonical_sha256(cells),
        },
        "visit_template": {
            "execution_frame_id": "root",
            "call_frame_id": None,
            "step_id": "compare",
            "visit_count": 1,
        },
        "evaluation": evaluation,
        "trial_schedule": schedule,
        "runtime_budget": budget,
        "ordered_check_specs": evaluation["checks"],
        "check_max_item_bytes": 1,
        "sealed_opaque_label_policy": {
            "schema_version": "trial_opaque_label_map.v1",
            "cell_domain": cells,
            "opaque_label_pattern": "^opaque-[0-9a-f]{64}$",
            "labels_unique": True,
            "digest_contract": "canonical_sha256(record)",
        },
    }
    return attempts.load_frozen_trial_artifact_authority(
        canonical_json_bytes(record)
    ).canonical_bytes


def _package(tmp_path: Path) -> controller.ControllerPackage:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    evidence = (tmp_path / "evidence").resolve()
    evidence.mkdir()
    state = (tmp_path / "runs").resolve()
    state.mkdir()
    children = (tmp_path / "children").resolve()
    children.mkdir()

    schedule = decision_lock.generate_randomization_manifest("sha256:" + "a" * 64)
    call_slots = tuple(
        decision_lock._receipt_call_slots(
            decision_lock.derive_terminal_routes(),
            decision_lock.derive_evaluation_routes(),
        )
    )
    argv = [
        "/opt/codex",
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        "gpt-5.5",
        "--config",
        "model_reasoning_effort=high",
        "--",
        "-",
    ]
    prompt_manifest_record = {
        "schema_version": "es.prompt_manifest.v1",
        "calls": [
            {
                "call_slot_id": slot,
                "role_id": slot,
                "prompt_sha256": "sha256:" + "3" * 64,
                "contract_sha256": "sha256:" + "4" * 64,
                "normalized_argv": argv,
            }
            for slot in call_slots
        ],
    }
    executable_chain = {
        "provider_family": "codex-cli",
        "version": "codex-cli 0.145.0",
        "launcher_path": "/opt/codex",
        "launcher_sha256": (
            "sha256:134063e133f0b4244fa3b251acf973d4f"
            "e4b4aeeacbdc135211bf480f59f1477"
        ),
        "interpreter_path": "/opt/node",
        "interpreter_sha256": "sha256:" + "6" * 64,
    }
    environment_record = {
        "schema_version": "es.environment_lock.v1",
        "provider_family": "codex-cli",
        "version": "codex-cli 0.145.0",
        "model": "gpt-5.5",
        "reasoning_effort": "high",
        "prompt_transport": "STDIN",
        "executable_chain": executable_chain,
        "evaluation_authority": {
            "schema_version": "es.evaluation_authority.v1",
            "hard_evaluator_identity_digest": "sha256:" + "7" * 64,
            "hard_task_identity_digest": "sha256:" + "8" * 64,
            "hard_fixture_identity_digest": "sha256:" + "9" * 64,
            "scorer_evaluation_digest": "sha256:" + "a" * 64,
            "scorer_identity_digest": "sha256:" + "b" * 64,
        },
    }
    workflow = _write(
        workspace,
        "workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc",
        b"(workflow placeholder)\n",
    )
    provider_externs = _write(workspace, "experiments/f1/providers.json", b"{}")
    prompt_externs = _write(workspace, "experiments/f1/prompts.json", b"{}")
    task = _write(workspace, "experiments/f1/task.md", b"neutral task\n")
    checks = _write(workspace, "experiments/f1/checks.md", b"pytest -q\n")
    source_projection = _write(workspace, "experiments/f1/projection.json", b"{}")
    task_profile = _write(workspace, "experiments/f1/profile.json", b"{}")
    task_seed = _write(workspace, "experiments/f1/seed.json", b"{}")
    evaluator = _write(workspace, "experiments/f1/evaluator.json", b"{}")
    environment = _write(
        workspace,
        "experiments/f1/environment.json",
        _record(environment_record),
    )
    prompt_manifest = _write(
        workspace,
        "experiments/f1/prompt-manifest.json",
        _record(prompt_manifest_record),
    )
    report_schema = _write(
        workspace,
        "experiments/f1/report.schema.json",
        (
            REPOSITORY_ROOT
            / "experiments/orc_effectiveness/f1_es/report.schema.json"
        ).read_bytes(),
    )
    randomization = _write(
        workspace,
        "experiments/f1/randomization.json",
        decision_lock.canonical_json_bytes(schedule),
    )
    bindings = {
        "arm_workflow_sha256": workflow.sha256,
        "environment_lock_sha256": environment.sha256,
        "evaluator_fixture_manifest_sha256": evaluator.sha256,
        "prompt_manifest_sha256": prompt_manifest.sha256,
        "randomization_manifest_sha256": decision_lock.decision_lock_digest(schedule),
        "report_schema_sha256": report_schema.sha256,
        "source_projection_manifest_sha256": source_projection.sha256,
        "task_profile_sha256": task_profile.sha256,
        "task_seed_manifest_sha256": task_seed.sha256,
    }
    lock = decision_lock.build_decision_lock(
        bindings=bindings,
        randomization_manifest=schedule,
    )
    lock_file = _write(
        workspace,
        "experiments/f1/decision-lock.json",
        decision_lock.canonical_json_bytes(lock),
    )
    call_authority = _write(
        workspace,
        "experiments/f1/call-authority.json",
        _record(
            {
                "schema_version": "es.frozen_call_authority.v1",
                "prompt_manifest": prompt_manifest_record,
                "environment_lock": environment_record,
            }
        ),
    )
    trial_artifact_authority = _write(
        workspace,
        "experiments/f1/frozen-trial-artifact-authority.json",
        _trial_artifact_authority(),
    )
    return controller.ControllerPackage(
        paths=controller.ControllerPaths(
            workspace=workspace,
            state_dir=state,
            run_ref_root=children,
            evidence_root=evidence,
        ),
        workflow=workflow,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        task=task,
        check_contract=checks,
        source_projection=source_projection,
        task_profile=task_profile,
        task_seed=task_seed,
        evaluator_fixture=evaluator,
        environment_lock=environment,
        prompt_manifest=prompt_manifest,
        report_schema=report_schema,
        randomization_manifest=randomization,
        decision_lock=lock_file,
        call_authority=call_authority,
        trial_artifact_authority=trial_artifact_authority,
        expected_bindings=tuple(sorted(bindings.items())),
        model="gpt-5.5",
        effort="high",
        consumed_attempt_ids=(),
        consumed_attempt_call_counts=(),
        invalid_attempt_count=0,
    )


def _publish_package_manifest(
    package: controller.ControllerPackage,
    path: Path,
) -> tuple[Path, str]:
    raw = canonical_json_bytes(package.manifest_record) + b"\n"
    path.write_bytes(raw)
    return path.resolve(), _sha(raw)


def _authority(
    treatment_failure_arm: str | None = None,
) -> controller.PersistedTrialAuthority:
    cells = tuple(TrialCellKey(arm, 1) for arm in ARMS)
    labels = tuple(f"opaque-{index:064x}" for index in range(1, 5))
    sealed = build_sealed_opaque_label_map(cells, labels=labels)
    packets: list[controller.PersistedPacket] = []
    frozen_rows: list[dict[str, object]] = []
    for arm, cell, label in zip(ARMS, cells, labels, strict=True):
        items: list[dict[str, object]] = [
            {"id": "task_spec", "kind": "task_spec", "value": arm}
        ]
        citable_item_ids = ["task_spec"]
        if arm == treatment_failure_arm:
            items.append(
                {
                    "id": "failure_evidence",
                    "kind": "failure_evidence",
                    "value": {
                        "code": "arm_timeout",
                        "status": "failed",
                    },
                }
            )
            citable_item_ids.append("failure_evidence")
        packet = {
            "schema": "trial.evaluation_packet.v1",
            "evaluation_id": label,
            "items": items,
            "citable_item_ids": citable_item_ids,
        }
        digest = canonical_sha256(packet)
        relpath = f"artifacts/trials/{'1' * 64}/packets/{digest[7:]}.json"
        packet_bytes = _record(packet) + b"\n"
        packets.append(
            controller.PersistedPacket(
                cell=cell,
                opaque_label=label,
                artifact=controller.controller_artifacts.CanonicalArtifact(
                    path=Path("/tmp") / relpath,
                    relative_path=relpath,
                    sha256=_sha(packet_bytes),
                    canonical_bytes=packet_bytes,
                ),
                packet_sha256=digest,
            )
        )
        frozen_rows.append(
            {"cell": cell.record, "opaque_label": label, "packet_digest": digest}
        )
    index = {
        "schema_version": "trial.packet_artifact_index.v1",
        "trial_request_digest": "sha256:" + "1" * 64,
        "header_row_digest": "sha256:" + "2" * 64,
        "evidence_frozen_row_digest": "sha256:" + "3" * 64,
        "checks_frozen_row_digest": "sha256:" + "4" * 64,
        "packets_frozen_row_digest": "sha256:" + "5" * 64,
        "sealed_opaque_label_map_digest": sealed.digest,
        "packet_set_digest": canonical_sha256(frozen_rows),
        "packets": [
            {
                "cell": packet.cell.record,
                "opaque_label": packet.opaque_label,
                "packet_digest": packet.packet_sha256,
                "packet_relpath": packet.relative_path,
            }
            for packet in packets
        ],
    }
    index_bytes = _record(index) + b"\n"
    ledger_bytes = _record({"kind": "fixture"}) + b"\n"
    verdict_bytes = _record({"fixture": "verdict"}) + b"\n"
    return controller.PersistedTrialAuthority(
        run_id="run-1",
        terminal_status="completed",
        failure_code=None,
        failure_message=None,
        workspace=Path("/tmp"),
        state_dir=Path("/tmp"),
        evidence_root=Path("/tmp"),
        trial_request_digest=index["trial_request_digest"],
        header_row_digest=index["header_row_digest"],
        cell_domain=cells,
        sealed_opaque_labels=sealed,
        trial_event_ledger=controller.controller_artifacts.CanonicalByteArtifact(
            path=Path("/tmp/trial-events.jsonl"),
            relative_path="trial-events.jsonl",
            sha256=_sha(ledger_bytes),
            canonical_bytes=ledger_bytes,
        ),
        verdict=controller.controller_artifacts.CanonicalArtifact(
            path=Path("/tmp/verdict.json"),
            relative_path="verdict.json",
            sha256=_sha(verdict_bytes),
            canonical_bytes=verdict_bytes,
        ),
        packet_artifact_index=controller.controller_artifacts.CanonicalArtifact(
            path=Path("/tmp/packet-index.json"),
            relative_path="packet-index.json",
            sha256=_sha(index_bytes),
            canonical_bytes=index_bytes,
        ),
        packets=tuple(packets),
        score_ledger=None,
        score_rows=(),
        scorer_settlement_rows=(),
    )


def _materialize_header_ledger(
    authority: controller.PersistedTrialAuthority,
    package: controller.ControllerPackage,
) -> controller.PersistedTrialAuthority:
    runtime_window = {
        "schema_version": "trial_runtime_budget_window.v1",
        "opened_at_unix_ns": 0,
        "arm_deadlines": [
            {"arm_id": arm, "deadline_unix_ns": 1} for arm in ARMS
        ],
        "trial_deadline_unix_ns": 1,
    }
    payload = {
        "trial_static_config_digest": "sha256:" + "a" * 64,
        "trial_step_config_digest": "sha256:" + "b" * 64,
        "arm_run_ref_authorities": [
            {
                "arm_id": arm,
                "run_ref_step_config_digest": "sha256:" + "c" * 64,
                "result_contract_digest": "sha256:" + "d" * 64,
            }
            for arm in ARMS
        ],
        "trial_request_digest": authority.trial_request_digest,
        "evaluation_digest": "sha256:" + "e" * 64,
        "budget_digest": "sha256:" + "f" * 64,
        "result_contract_digest": "sha256:" + "1" * 64,
        "compiler_runtime_identity_digest": "sha256:" + "2" * 64,
        "visit": {
            "parent_run_id": authority.run_id,
            "execution_frame_id": "root",
            "call_frame_id": None,
            "step_id": "compare",
            "visit_count": 1,
        },
        "cell_domain": [cell.record for cell in authority.cell_domain],
        "cell_domain_digest": canonical_sha256(
            [cell.record for cell in authority.cell_domain]
        ),
        "sealed_opaque_label_map": authority.sealed_opaque_labels.record,
        "sealed_opaque_label_map_digest": authority.sealed_opaque_labels.digest,
        "runtime_budget_window": runtime_window,
        "runtime_budget_window_digest": canonical_sha256(runtime_window),
    }
    row = trial_ledger._build_row(  # pyright: ignore[reportPrivateUsage]
        sequence=1,
        previous_row_digest=None,
        kind="header",
        recorded_at="2026-01-01T00:00:00.000000Z",
        payload=payload,
    )
    raw = canonical_json_bytes(row.record) + b"\n"
    path = package.paths.state_dir / authority.run_id / "trial-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    packet_index = authority.packet_artifact_index
    if packet_index is not None:
        index_record = dict(packet_index.value)
        index_record["header_row_digest"] = row.row_digest
        index_raw = canonical_json_bytes(index_record) + b"\n"
        packet_index = controller.controller_artifacts.CanonicalArtifact(
            path=packet_index.path,
            relative_path=packet_index.relative_path,
            sha256=_sha(index_raw),
            canonical_bytes=index_raw,
        )
    return replace(
        authority,
        workspace=package.paths.workspace,
        state_dir=package.paths.state_dir,
        evidence_root=package.paths.evidence_root,
        header_row_digest=row.row_digest,
        trial_event_ledger=controller.controller_artifacts.CanonicalByteArtifact(
            path=path,
            relative_path=f"{authority.run_id}/trial-events.jsonl",
            sha256=_sha(raw),
            canonical_bytes=raw,
        ),
        packet_artifact_index=packet_index,
    )


def _append_cell_allocation_started(
    authority: controller.PersistedTrialAuthority,
) -> controller.PersistedTrialAuthority:
    ledger = trial_ledger.load_trial_event_ledger(
        authority.trial_event_ledger.path
    )
    row = trial_ledger._build_row(  # pyright: ignore[reportPrivateUsage]
        sequence=2,
        previous_row_digest=ledger.rows[-1].row_digest,
        kind="cell_allocation_started",
        recorded_at="2026-01-01T00:00:01.000000Z",
        payload={
            "cell": authority.cell_domain[0].record,
            "attempt_ordinal": 1,
            "e1_allocation_event_digest": "sha256:" + "7" * 64,
            "started_at_unix_ns": 1,
            "started_monotonic_ns": 1,
        },
    )
    raw = (
        authority.trial_event_ledger.canonical_bytes
        + canonical_json_bytes(row.record)
        + b"\n"
    )
    authority.trial_event_ledger.path.write_bytes(raw)
    trial_ledger.load_trial_event_ledger(authority.trial_event_ledger.path)
    return replace(
        authority,
        trial_event_ledger=controller.controller_artifacts.CanonicalByteArtifact(
            path=authority.trial_event_ledger.path,
            relative_path=authority.trial_event_ledger.relative_path,
            sha256=_sha(raw),
            canonical_bytes=raw,
        ),
    )


def _review_payload(
    request: controller.ReviewCallRequest,
    *,
    disagreement: bool,
) -> dict[str, Any]:
    labels = list(request.presentation_order)
    pairs = []
    for index, (left, right) in enumerate(reviews.canonical_pair_order(labels)):
        outcome = "A"
        if disagreement and request.call_slot_id.endswith("MAINTAINABILITY") and index == 0:
            outcome = "B"
        pairs.append(
            {
                "candidate_a_label": left,
                "candidate_b_label": right,
                "outcome": outcome,
                "rationale": "bounded result",
                "citations": [
                    {"opaque_label": left, "citable_item_id": "task_spec"},
                    {"opaque_label": right, "citable_item_id": "task_spec"},
                ],
            }
        )
    if request.review_kind != reviews.INITIAL:
        schema = (
            "es-f1-adjudicator-review.v1"
            if request.review_kind == reviews.ADJUDICATOR
            else "es-f1-integrated-review.v1"
        )
        return {"schema_version": schema, "pairwise_results": pairs}
    assert request.perspective_id is not None
    candidates = []
    for label in labels:
        candidates.append(
            {
                "opaque_label": label,
                "dimensions": [
                    {
                        "dimension": dimension,
                        "assessment": "PASS",
                        "rationale": "bounded result",
                        "citations": [
                            {"opaque_label": label, "citable_item_id": "task_spec"}
                        ],
                    }
                    for dimension in reviews.PERSPECTIVE_DIMENSIONS[
                        request.perspective_id
                    ]
                ],
            }
        )
    schema = (
        "es-f1-initial-scientific-application-semantics-review.v1"
        if request.perspective_id == reviews.SCIENTIFIC_APPLICATION_SEMANTICS
        else "es-f1-initial-api-persistence-migration-maintainability-review.v1"
    )
    return {
        "schema_version": schema,
        "candidates": candidates,
        "pairwise_results": pairs,
    }


def _dependencies(
    package: controller.ControllerPackage,
    *,
    disagreement: bool = False,
    stop: bool = False,
    calls: list[str] | None = None,
    failed_slots: frozenset[str] = frozenset(),
    hard_failure: str | None = None,
    runner_error: bool = False,
    runner_allocation_slots: tuple[str, ...] = (),
    invalid_payload_slots: frozenset[str] = frozenset(),
    trial_terminal: str = "completed",
    interrupted_provider_slots: frozenset[str] = frozenset(),
    finalizer_error: bool = False,
    blinding_invalid: bool = False,
    assemblies: list[controller.AttemptAssembly] | None = None,
    treatment_failure_arm: str | None = None,
    evaluator_fixture_after_replay: bytes | None = None,
    evaluator_fixture_after_review_slot: str | None = None,
    failed_trial_cell_started: bool = False,
) -> controller.ControllerDependencies:
    observed = calls if calls is not None else []

    def runner(**kwargs: object) -> TrialRunResult:
        observed.append("RUN")
        assert kwargs == {
            "workflow_file": package.paths.workspace / package.workflow.relative_path,
            "entry_workflow": "compare",
            "inputs": {
                "task": "neutral task\n",
                "check_contract": "pytest -q\n",
                "model": "gpt-5.5",
                "effort": "high",
            },
            "workspace": package.paths.workspace,
            "state_dir": package.paths.state_dir,
            "run_ref_root": package.paths.run_ref_root,
            "options": controller.TrialRunOptions(
                source_roots=(
                    package.paths.workspace / "workflows/experiments",
                    package.paths.workspace / "workflows/library",
                ),
                provider_externs_file=(
                    package.paths.workspace / package.provider_externs.relative_path
                ),
                prompt_externs_file=(
                    package.paths.workspace / package.prompt_externs.relative_path
                ),
                max_retries=0,
                retry_delay_ms=0,
            ),
        }
        if runner_error:
            raise RuntimeError("runner refused before allocation")
        lock = json.loads(
            (
                package.paths.workspace
                / package.decision_lock.relative_path
            ).read_text(encoding="utf-8")
        )
        journal = (
            package.paths.evidence_root
            / "attempts/ES-ATTEMPT-01/call-allocations.jsonl"
        )
        for index, slot in enumerate(runner_allocation_slots, start=1):
            provider_boundary.publish_allocation(
                journal,
                attempt_id="ES-ATTEMPT-01",
                decision_lock_sha256=decision_lock.decision_lock_digest(lock),
                call_slot_id=slot,
                static_call_sha256="sha256:" + f"{index:x}" * 64,
            )
        if trial_terminal == "failed":
            return TrialRunResult.failed(
                run_id="run-1",
                code="trial_execution_interrupted",
                message="interrupted after a committed allocation boundary",
            )
        return TrialRunResult.completed(
            run_id="run-1",
            verdict_digest="sha256:" + "9" * 64,
            verdict_path=f"artifacts/trials/{'1' * 64}/verdict.json",
        )

    def call(request: controller.ReviewCallRequest) -> controller.ProviderCallResult:
        observed.append(request.call_slot_id)
        assert request.allocation_event_path.is_file()
        if request.call_slot_id == evaluator_fixture_after_review_slot:
            (
                package.paths.workspace
                / package.evaluator_fixture.relative_path
            ).write_bytes(b'{"drift":true}')
        if request.call_slot_id in interrupted_provider_slots:
            raise RuntimeError("provider process interrupted after allocation")
        receipt = {
            "block_id": request.attempt_id,
            "call_slot_id": request.call_slot_id,
            "session_id": "session-" + request.call_slot_id,
            "provider_attempt_id": "attempt-" + request.call_slot_id,
            "exit_status": 0,
        }
        if request.call_slot_id in failed_slots:
            return controller.ProviderCallResult.failed(
                failure_code="PROVIDER_TYPED_OUTPUT_INVALID",
                receipt=_record(receipt),
                raw_jsonl=b"{}\n",
                elapsed_ms=1,
            )
        if request.call_slot_id in invalid_payload_slots:
            return controller.ProviderCallResult.succeeded(
                payload=_record({}),
                receipt=_record(receipt),
                raw_jsonl=b"{}\n",
                elapsed_ms=1,
            )
        return controller.ProviderCallResult.succeeded(
            payload=_record(_review_payload(request, disagreement=disagreement)),
            receipt=_record(receipt),
            raw_jsonl=b"{}\n",
            elapsed_ms=1,
        )

    def hard(request: controller.HardEvidenceRequest) -> controller.HardEvidenceInput:
        observed.append("HARD." + request.arm_id)
        if request.arm_id == hard_failure:
            raise RuntimeError("hard evaluator failed")
        return controller.HardEvidenceInput.missing(
            _record(
                {
                    "schema_version": "es.trusted_product_freeze_absence.v1",
                    "reason": "TERMINAL_TREATMENT_FAILURE",
                    "cell": request.cell.record,
                    "terminal_row_digest": "sha256:" + "8" * 64,
                }
            )
        )

    def finalize(assembly: controller.AttemptAssembly) -> controller.FinalizedAttempt:
        observed.append("FINALIZE")
        if assemblies is not None:
            assemblies.append(assembly)
        if finalizer_error:
            raise RuntimeError("finalizer interrupted after durable attempt prefix")
        assert assembly.attempt_id == "ES-ATTEMPT-01"
        if assembly.trial_result is None:
            assert assembly.authority is None
            assert assembly.review_records == ()
            assert assembly.private_join is None
        elif assembly.trial_result.terminal_status == "failed":
            assert assembly.review_records == ()
            assert assembly.private_join is None
        elif assembly.classifier_authority.invalidity_code is not None:
            if assembly.classifier_authority.invalidity_code == "BLINDING_JOIN_INVALID":
                assert assembly.review_records == ()
                assert assembly.private_join is None
            else:
                assert assembly.private_join is not None
            assert assembly.integrated_payload is None
        elif interrupted_provider_slots or hard_failure is not None:
            expected_prefix = tuple(
                slot
                for slot in (
                    "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
                    "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
                )
                if slot not in interrupted_provider_slots
            )
            assert tuple(row.call_slot_id for row in assembly.review_records) == (
                expected_prefix
            )
            assert assembly.integrated_payload is None
        else:
            assert tuple(row.call_slot_id for row in assembly.review_records)[-1] == (
                "EVAL.INTEGRATED_REVIEW"
            )
        return controller.FinalizedAttempt(
            attempt_record=_record({"attempt_id": assembly.attempt_id}),
            attempt_index=_record({"attempt_id": assembly.attempt_id}),
            attempt_index_sha256="sha256:" + "7" * 64,
            report=_record({"status": "STOP"}) if stop else None,
            stopped=stop,
            next_attempt_id=None if stop else "ES-ATTEMPT-02",
        )

    def replay(
        result: TrialRunResult,
        _package: controller.ControllerPackage,
    ) -> controller.PersistedTrialAuthority:
        authority = _materialize_header_ledger((
            replace(
                _authority(treatment_failure_arm),
                terminal_status="failed",
                failure_code="trial_execution_interrupted",
                failure_message="interrupted after a committed allocation boundary",
                verdict=None,
                packet_artifact_index=None,
                packets=(),
            )
            if result.terminal_status == "failed"
            else _authority(treatment_failure_arm)
        ), package)
        if result.terminal_status == "failed" and failed_trial_cell_started:
            authority = _append_cell_allocation_started(authority)
        if not blinding_invalid:
            replayed = authority
        else:
            labels = tuple(f"opaque-{index:064x}" for index in range(101, 105))
            replayed = replace(
                authority,
                sealed_opaque_labels=build_sealed_opaque_label_map(
                    authority.cell_domain,
                    labels=labels,
                ),
            )
        if evaluator_fixture_after_replay is not None:
            (
                package.paths.workspace
                / package.evaluator_fixture.relative_path
            ).write_bytes(evaluator_fixture_after_replay)
        return replayed

    return controller.ControllerDependencies(
        run_trial=runner,
        replay_trial=replay,
        call_provider=call,
        collect_hard_evidence=hard,
        finalize_attempt=finalize,
        allow_untrusted_package_for_tests=True,
    )


def _outage_disposition(
    package: controller.ControllerPackage,
    dependencies: controller.ControllerDependencies,
) -> tuple[Path, dict[str, object]]:
    failed = TrialRunResult.failed(
        run_id="run-1",
        code="trial_execution_interrupted",
        message="interrupted after a committed allocation boundary",
    )
    authority = dependencies.replay_trial(failed, package)
    preflight = controller._preflight(  # pyright: ignore[reportPrivateUsage]
        package,
        allow_untrusted_package=False,
    )
    journal = (
        package.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/call-allocations.jsonl"
    )
    disposition: dict[str, object] = {
        "schema_version": "es.controller_invalidity_authority.v1",
        "attempt_id": "ES-ATTEMPT-01",
        "invalidity_code": "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT",
        "evidence": {
            # pyright: ignore[reportPrivateUsage]
            "bindings": controller._common_invalidity_bindings(
                package=package,
                preflight=preflight,
                attempt_id="ES-ATTEMPT-01",
                authority=authority,
                journal_path=journal,
            ),
            "pre_treatment_proof": {
                "cell_allocation_started_count": 0,
                "provider_allocation_count": 0,
            },
            "evidence_status": "owner_confirmed",
            "authorized_disposition": (
                "classify_common_provider_outage_before_treatment"
            ),
            "owner": {"name": "Ollie", "role": "ES study owner"},
            "owner_adoption": {
                "adopted_at": "2026-08-03T12:00:00-07:00",
                "statement": (
                    "I confirm the shared provider was unavailable before any "
                    "treatment began and personally adopt this exact bound attempt "
                    "as COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT."
                ),
            },
        },
    }
    return journal.parent / "common-provider-outage-disposition.json", disposition


def _open_header_only_failed_prefix(
    package: controller.ControllerPackage,
) -> tuple[
    controller.ControllerDependencies,
    controller.PostIncidentDispositionRequired,
    list[str],
]:
    calls: list[str] = []
    dependencies = _dependencies(
        package,
        calls=calls,
        trial_terminal="failed",
    )
    with pytest.raises(controller.PostIncidentDispositionRequired) as raised:
        controller.execute_attempt(package, dependencies)
    assert calls == ["RUN"]
    return dependencies, raised.value, calls


def test_controller_types_are_closed_and_immutable(tmp_path: Path) -> None:
    package = _package(tmp_path)
    with pytest.raises(FrozenInstanceError):
        package.model = "other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="canonical"):
        replace(package.paths, workspace=Path("relative"))


def test_package_manifest_requires_external_digest_and_reconstructs_closed_package(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    path, digest = _publish_package_manifest(package, tmp_path / "controller.json")

    loaded = controller.load_controller_package(path, expected_sha256=digest)

    assert loaded.manifest_sha256 == digest
    assert loaded.manifest_record == package.manifest_record


def test_package_manifest_rejects_self_consistent_substitution_against_frozen_digest(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    path, frozen_digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    substitute = package.manifest_record
    substitute["history"]["invalid_attempt_count"] = 1
    path.write_bytes(canonical_json_bytes(substitute) + b"\n")

    with pytest.raises(controller.ControllerError, match="manifest_digest_mismatch"):
        controller.load_controller_package(path, expected_sha256=frozen_digest)


def test_package_manifest_derives_history_from_bound_immutable_attempt_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path)
    attempt_id = "ES-ATTEMPT-01"
    index = {
        "index_sha256": "sha256:" + "d" * 64,
        "attempt_record": {
            "attempt_id": attempt_id,
            "status": "INVALID",
            "accounting": {"call_count": 3},
        },
    }
    index_raw = canonical_json_bytes(index) + b"\n"
    relative_path = f"attempts/{attempt_id}/index.json"
    path = package.paths.evidence_root / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(index_raw)
    bound = controller.AttemptIndexBinding(attempt_id, relative_path, _sha(index_raw))
    package = replace(
        package,
        consumed_attempt_ids=(attempt_id,),
        consumed_attempt_call_counts=(3,),
        invalid_attempt_count=1,
        attempt_indexes=(bound,),
    )
    monkeypatch.setattr(
        controller.synthesis,
        "validate_attempt_evidence_index",
        lambda value, **_kwargs: value,
    )
    manifest, digest = _publish_package_manifest(package, tmp_path / "controller.json")

    loaded = controller.load_controller_package(manifest, expected_sha256=digest)

    assert loaded.consumed_attempt_ids == (attempt_id,)
    assert loaded.consumed_attempt_call_counts == (3,)
    assert loaded.invalid_attempt_count == 1


def test_package_manifest_rejects_hidden_consumed_attempt_index(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    hidden = (
        package.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/index.json"
    )
    hidden.parent.mkdir(parents=True)
    hidden.write_bytes(b"{}\n")
    manifest, digest = _publish_package_manifest(package, tmp_path / "controller.json")

    with pytest.raises(controller.ControllerError, match="inventory_mismatch"):
        controller.load_controller_package(manifest, expected_sha256=digest)


def test_package_manifest_rejects_declared_history_that_disagrees_with_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path)
    attempt_id = "ES-ATTEMPT-01"
    index = {
        "index_sha256": "sha256:" + "d" * 64,
        "attempt_record": {
            "attempt_id": attempt_id,
            "status": "VALID",
            "accounting": {"call_count": 3},
        },
    }
    index_raw = canonical_json_bytes(index) + b"\n"
    relative_path = f"attempts/{attempt_id}/index.json"
    path = package.paths.evidence_root / relative_path
    path.parent.mkdir(parents=True)
    path.write_bytes(index_raw)
    package = replace(
        package,
        consumed_attempt_ids=(attempt_id,),
        consumed_attempt_call_counts=(4,),
        attempt_indexes=(
            controller.AttemptIndexBinding(attempt_id, relative_path, _sha(index_raw)),
        ),
    )
    monkeypatch.setattr(
        controller.synthesis,
        "validate_attempt_evidence_index",
        lambda value, **_kwargs: value,
    )
    manifest, digest = _publish_package_manifest(package, tmp_path / "controller.json")

    with pytest.raises(controller.ControllerError, match="history_mismatch"):
        controller.load_controller_package(manifest, expected_sha256=digest)


def test_production_dependencies_reject_direct_untrusted_package_before_runner(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    calls: list[str] = []
    dependencies = replace(
        _dependencies(package, calls=calls),
        allow_untrusted_package_for_tests=False,
    )

    with pytest.raises(controller.ControllerError, match="manifest_required"):
        controller.execute_attempt(package, dependencies)

    assert calls == []


def test_default_dependencies_carry_only_an_exact_optional_outage_digest() -> None:
    digest = "sha256:" + "a" * 64
    dependencies = controller.default_controller_dependencies(
        call_provider=lambda _request: pytest.fail("provider must not run"),
        collect_hard_evidence=lambda _request: pytest.fail("hard must not run"),
        common_provider_outage_disposition_sha256=digest,
    )

    assert dependencies.common_provider_outage_disposition_sha256 == digest
    with pytest.raises(controller.ControllerError, match="binding_invalid"):
        replace(
            dependencies,
            common_provider_outage_disposition_sha256="sha256:not-a-digest",
        )


@pytest.mark.parametrize(
    "role",
    [
        "workflow",
        "provider_externs",
        "prompt_externs",
        "task",
        "check_contract",
        "source_projection",
        "task_profile",
        "task_seed",
        "evaluator_fixture",
        "environment_lock",
        "prompt_manifest",
        "report_schema",
        "randomization_manifest",
        "decision_lock",
        "call_authority",
        "trial_artifact_authority",
    ],
)
def test_every_bound_input_mismatch_rejects_before_runner(
    tmp_path: Path,
    role: str,
) -> None:
    package = _package(tmp_path)
    bound = getattr(package, role)
    (package.paths.workspace / bound.relative_path).write_bytes(b"tampered")
    calls: list[str] = []

    with pytest.raises(controller.ControllerError, match="binding"):
        controller.execute_attempt(package, _dependencies(package, calls=calls))

    assert calls == []


def test_canonical_but_invalid_trial_artifact_authority_rejects_before_runner(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    path = (
        package.paths.workspace
        / package.trial_artifact_authority.relative_path
    )
    payload = canonical_json_bytes({"schema_version": "unsupported"})
    path.write_bytes(payload)
    package = replace(
        package,
        trial_artifact_authority=controller.BoundFile(
            package.trial_artifact_authority.relative_path,
            _sha(payload),
        ),
    )
    calls: list[str] = []

    with pytest.raises(controller.ControllerError, match="authority_invalid"):
        controller.execute_attempt(package, _dependencies(package, calls=calls))

    assert calls == []


def test_route_selection_rejects_swapped_slots_within_one_locked_domain(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    preflight = controller._preflight(  # pyright: ignore[reportPrivateUsage]
        package,
        allow_untrusted_package=True,
    )
    lock_digest = decision_lock.decision_lock_digest(preflight.decision_lock)
    first = provider_boundary.AllocationEvent(
        attempt_id="ES-ATTEMPT-01",
        sequence=1,
        previous_allocation_sha256=None,
        call_slot_id="DESIGN_QA.DR",
        decision_lock_sha256=lock_digest,
        static_call_sha256="sha256:" + "1" * 64,
    )
    second = provider_boundary.AllocationEvent(
        attempt_id="ES-ATTEMPT-01",
        sequence=2,
        previous_allocation_sha256=first.sha256,
        call_slot_id="DESIGN_QA.D",
        decision_lock_sha256=lock_digest,
        static_call_sha256="sha256:" + "2" * 64,
    )

    with pytest.raises(controller.ControllerError, match="route_sequence_invalid"):
        controller._selected_routes(  # pyright: ignore[reportPrivateUsage]
            preflight=preflight,
            allocations=(first, second),
        )


def test_route_selection_accepts_permuted_concurrent_scorer_tranche(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    preflight = controller._preflight(  # pyright: ignore[reportPrivateUsage]
        package,
        allow_untrusted_package=True,
    )
    slots = (
        "EVAL.SCORER_RICH",
        "EVAL.SCORER_DIRECT",
        "EVAL.SCORER_PRODUCT_QA",
        "EVAL.SCORER_DESIGN_QA",
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
        "EVAL.INTEGRATED_REVIEW",
    )
    lock_digest = decision_lock.decision_lock_digest(preflight.decision_lock)
    allocations: list[provider_boundary.AllocationEvent] = []
    previous: str | None = None
    for sequence, slot in enumerate(slots, start=1):
        row = provider_boundary.AllocationEvent(
            attempt_id="ES-ATTEMPT-01",
            sequence=sequence,
            previous_allocation_sha256=previous,
            call_slot_id=slot,
            decision_lock_sha256=lock_digest,
            static_call_sha256="sha256:" + f"{sequence:x}" * 64,
        )
        allocations.append(row)
        previous = row.sha256

    _arm_routes, evaluation_route = controller._selected_routes(  # pyright: ignore[reportPrivateUsage]
        preflight=preflight,
        allocations=allocations,
    )

    assert evaluation_route == "EVALUATION.NO_ADJUDICATION"


def test_canonical_finalizer_closes_preallocation_failure_from_frozen_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(
        manifest,
        expected_sha256=digest,
    )
    calls: list[str] = []
    dependencies = replace(
        _dependencies(loaded, calls=calls, runner_error=True),
        finalize_attempt=controller.canonical_finalize_attempt,
        allow_untrusted_package_for_tests=False,
    )
    observed: dict[str, object] = {}

    def finalize(
        assembly: controller.controller_artifacts.FinalizationAssembly,
    ) -> controller.controller_artifacts.FinalizedArtifacts:
        observed["assembly"] = assembly
        assert isinstance(
            assembly.index,
            controller.controller_artifacts.PartialIndexInputs,
        )
        assert assembly.index.call_allocations == ()
        assert assembly.attempt.controller_launch_preallocation_failed is True
        assert assembly.attempt.replay is None
        return controller.controller_artifacts.FinalizedArtifacts(
            attempt_record=_record(
                {
                    "attempt_id": "ES-ATTEMPT-01",
                    "status": "INVALID",
                    "invalidity_reason": "CONTROLLER_LAUNCH_PREALLOCATION_FAILED",
                }
            ),
            attempt_index=_record({"attempt_id": "ES-ATTEMPT-01"}),
            attempt_index_sha256="sha256:" + "7" * 64,
            index_binding=controller.AttemptIndexBinding(
                "ES-ATTEMPT-01",
                "attempts/ES-ATTEMPT-01/index.json",
                "sha256:" + "7" * 64,
            ),
            report=None,
            stopped=False,
            next_attempt_id="ES-ATTEMPT-02",
        )

    monkeypatch.setattr(
        controller.controller_artifacts,
        "finalize_attempt_artifacts",
        finalize,
    )

    result = controller.execute_attempt(loaded, dependencies)

    record = json.loads(result.attempt_record)
    assert result.trial_result is None
    assert record["attempt_id"] == "ES-ATTEMPT-01"
    assert record["status"] == "INVALID"
    assert record["invalidity_reason"] == "CONTROLLER_LAUNCH_PREALLOCATION_FAILED"
    assert isinstance(
        observed["assembly"],
        controller.controller_artifacts.FinalizationAssembly,
    )
    assert calls == ["RUN"]


def test_canonical_finalizer_forwards_exact_blinding_invalidity_classifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(
        manifest,
        expected_sha256=digest,
    )
    captured: dict[str, object] = {}

    def finalize(
        assembly: controller.controller_artifacts.FinalizationAssembly,
    ) -> controller.controller_artifacts.FinalizedArtifacts:
        captured["attempt"] = assembly.attempt
        return controller.controller_artifacts.FinalizedArtifacts(
            attempt_record=_record(
                {
                    "attempt_id": "ES-ATTEMPT-01",
                    "status": "INVALID",
                    "invalidity_code": "BLINDING_JOIN_INVALID",
                }
            ),
            attempt_index=_record({"attempt_id": "ES-ATTEMPT-01"}),
            attempt_index_sha256="sha256:" + "7" * 64,
            index_binding=controller.AttemptIndexBinding(
                "ES-ATTEMPT-01",
                "attempts/ES-ATTEMPT-01/index.json",
                "sha256:" + "7" * 64,
            ),
            report=None,
            stopped=False,
            next_attempt_id="ES-ATTEMPT-02",
        )

    monkeypatch.setattr(
        controller.controller_artifacts,
        "finalize_attempt_artifacts",
        finalize,
    )
    dependencies = replace(
        _dependencies(loaded, blinding_invalid=True),
        finalize_attempt=controller.canonical_finalize_attempt,
        allow_untrusted_package_for_tests=False,
    )

    result = controller.execute_attempt(loaded, dependencies)

    attempt = captured["attempt"]
    assert isinstance(
        attempt,
        controller.controller_artifacts.AttemptRecordInputs,
    )
    assert attempt.common_provider_outage_proven is False
    assert attempt.evaluation_bytes_valid is True
    assert attempt.blinding_join_valid is False
    assert json.loads(result.attempt_record)["invalidity_code"] == (
        "BLINDING_JOIN_INVALID"
    )


def test_canonical_finalizer_forwards_exact_evaluator_invalidity_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    captured: dict[str, object] = {}

    def finalize(
        assembly: controller.controller_artifacts.FinalizationAssembly,
    ) -> controller.controller_artifacts.FinalizedArtifacts:
        captured["attempt"] = assembly.attempt
        captured["index"] = assembly.index
        return controller.controller_artifacts.FinalizedArtifacts(
            attempt_record=_record(
                {
                    "attempt_id": "ES-ATTEMPT-01",
                    "status": "INVALID",
                    "invalidity_code": "COMMON_EVALUATION_BYTES_INVALID",
                }
            ),
            attempt_index=_record({"attempt_id": "ES-ATTEMPT-01"}),
            attempt_index_sha256="sha256:" + "7" * 64,
            index_binding=controller.AttemptIndexBinding(
                "ES-ATTEMPT-01",
                "attempts/ES-ATTEMPT-01/index.json",
                "sha256:" + "7" * 64,
            ),
            report=None,
            stopped=False,
            next_attempt_id="ES-ATTEMPT-02",
        )

    monkeypatch.setattr(
        controller.controller_artifacts,
        "finalize_attempt_artifacts",
        finalize,
    )
    dependencies = replace(
        _dependencies(
            loaded,
            evaluator_fixture_after_replay=b'{"drift":true}',
        ),
        finalize_attempt=controller.canonical_finalize_attempt,
        allow_untrusted_package_for_tests=False,
    )

    result = controller.execute_attempt(loaded, dependencies)

    attempt = captured["attempt"]
    index = captured["index"]
    assert isinstance(
        attempt,
        controller.controller_artifacts.AttemptRecordInputs,
    )
    assert isinstance(
        index,
        controller.controller_artifacts.PartialIndexInputs,
    )
    assert attempt.common_provider_outage_proven is False
    assert attempt.evaluation_bytes_valid is False
    assert attempt.blinding_join_valid is True
    assert index.invalidity_authority is not None
    assert json.loads(index.invalidity_authority)["invalidity_code"] == (
        "COMMON_EVALUATION_BYTES_INVALID"
    )
    assert json.loads(result.attempt_record)["invalidity_code"] == (
        "COMMON_EVALUATION_BYTES_INVALID"
    )


def test_canonical_finalizer_forwards_exact_outage_disposition_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    first, _boundary, _calls = _open_header_only_failed_prefix(loaded)
    path, disposition = _outage_disposition(loaded, first)
    raw = canonical_json_bytes(disposition) + b"\n"
    path.write_bytes(raw)
    captured: dict[str, object] = {}

    def finalize(
        assembly: controller.controller_artifacts.FinalizationAssembly,
    ) -> controller.controller_artifacts.FinalizedArtifacts:
        captured["attempt"] = assembly.attempt
        captured["index"] = assembly.index
        return controller.controller_artifacts.FinalizedArtifacts(
            attempt_record=_record(
                {
                    "attempt_id": "ES-ATTEMPT-01",
                    "status": "INVALID",
                    "invalidity_code": (
                        "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT"
                    ),
                }
            ),
            attempt_index=_record({"attempt_id": "ES-ATTEMPT-01"}),
            attempt_index_sha256="sha256:" + "7" * 64,
            index_binding=controller.AttemptIndexBinding(
                "ES-ATTEMPT-01",
                "attempts/ES-ATTEMPT-01/index.json",
                "sha256:" + "7" * 64,
            ),
            report=None,
            stopped=False,
            next_attempt_id="ES-ATTEMPT-02",
        )

    monkeypatch.setattr(
        controller.controller_artifacts,
        "finalize_attempt_artifacts",
        finalize,
    )
    dependencies = replace(
        _dependencies(loaded),
        finalize_attempt=controller.canonical_finalize_attempt,
        allow_untrusted_package_for_tests=False,
        common_provider_outage_disposition_sha256=_sha(raw),
    )

    result = controller.execute_attempt(loaded, dependencies)

    attempt = captured["attempt"]
    index = captured["index"]
    assert isinstance(
        attempt,
        controller.controller_artifacts.AttemptRecordInputs,
    )
    assert isinstance(
        index,
        controller.controller_artifacts.PartialIndexInputs,
    )
    assert attempt.common_provider_outage_proven is True
    assert attempt.evaluation_bytes_valid is True
    assert attempt.blinding_join_valid is True
    assert index.invalidity_authority == canonical_json_bytes(disposition)
    assert json.loads(result.attempt_record)["invalidity_code"] == (
        "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT"
    )


def test_exact_public_entry_invocation_and_agreement_stage_order(tmp_path: Path) -> None:
    package = _package(tmp_path)
    calls: list[str] = []

    result = controller.execute_attempt(package, _dependencies(package, calls=calls))

    assert result.attempt_id == "ES-ATTEMPT-01"
    assert calls == [
        "RUN",
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
        "HARD.DIRECT",
        "HARD.DESIGN_QA",
        "HARD.PRODUCT_QA",
        "HARD.RICH",
        "EVAL.INTEGRATED_REVIEW",
        "FINALIZE",
    ]
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_completed_e2_arm_timeout_remains_treatment_outcome_without_retry(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    result = controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=calls,
            assemblies=assemblies,
            treatment_failure_arm="DESIGN_QA",
        ),
    )

    assert calls.count("RUN") == 1
    assert calls.count("EVAL.INTEGRATED_REVIEW") == 1
    assert calls.count("FINALIZE") == 1
    assert all(calls.count(f"HARD.{arm}") == 1 for arm in ARMS)
    assert "EVAL.ADJUDICATOR" not in calls
    assert result.trial_result is not None
    assert result.trial_result.terminal_status == "completed"
    assert assemblies[0].classifier_authority.invalidity_code is None
    authority = assemblies[0].authority
    assert authority is not None
    failed_packet = next(
        packet
        for packet in authority.packets
        if packet.arm_id == "DESIGN_QA"
    )
    citable_item_ids = failed_packet.artifact.value["citable_item_ids"]
    assert isinstance(citable_item_ids, list)
    assert "failure_evidence" in citable_item_ids


def test_exact_public_entry_runs_under_frozen_provider_boundary_then_restores_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _package(tmp_path)
    dependencies = _dependencies(package)
    original = dependencies.run_trial
    observed: dict[str, object] = {}
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.delenv(provider_boundary.MANIFEST_PATH_ENV, raising=False)
    monkeypatch.delenv(provider_boundary.MANIFEST_SHA256_ENV, raising=False)

    def runner(**kwargs: object) -> TrialRunResult:
        manifest_path = Path(os.environ[provider_boundary.MANIFEST_PATH_ENV])
        manifest = provider_boundary.load_manifest(
            manifest_path,
            expected_sha256=os.environ[provider_boundary.MANIFEST_SHA256_ENV],
        )
        observed["manifest"] = manifest
        observed["path"] = os.environ["PATH"]
        return original(**kwargs)

    controller.execute_attempt(
        package,
        replace(dependencies, run_trial=runner),
    )

    manifest = observed["manifest"]
    assert isinstance(manifest, provider_boundary.BoundaryManifest)
    assert [call.call_slot_id for call in manifest.calls] == list(
        decision_lock._receipt_call_slots(
            decision_lock.derive_terminal_routes(),
            decision_lock.derive_evaluation_routes(),
        )[:18]
    )
    assert all(
        call.outer_argv
        == (
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--model",
            "gpt-5.5",
            "--config",
            "reasoning_effort=high",
        )
        for call in manifest.calls
    )
    assert str(observed["path"]).endswith(":/usr/local/bin:/usr/bin")
    assert os.environ["PATH"] == "/usr/local/bin:/usr/bin"
    assert provider_boundary.MANIFEST_PATH_ENV not in os.environ
    assert provider_boundary.MANIFEST_SHA256_ENV not in os.environ


def test_disagreement_runs_one_adjudicator_before_hard_and_integrated(tmp_path: Path) -> None:
    package = _package(tmp_path)
    calls: list[str] = []

    controller.execute_attempt(
        package,
        _dependencies(package, disagreement=True, calls=calls),
    )

    assert calls.index("EVAL.ADJUDICATOR") < calls.index("HARD.DIRECT")
    assert calls.index("HARD.RICH") < calls.index("EVAL.INTEGRATED_REVIEW")
    assert calls.count("EVAL.ADJUDICATOR") == 1


@pytest.mark.parametrize(
    "failed_slot",
    [
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    ],
)
def test_failed_initial_is_an_outcome_without_adjudication(
    tmp_path: Path,
    failed_slot: str,
) -> None:
    package = _package(tmp_path)
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=calls,
            assemblies=assemblies,
            failed_slots=frozenset({failed_slot}),
        ),
    )

    assert "EVAL.ADJUDICATOR" not in calls
    assert "EVAL.INTEGRATED_REVIEW" in calls
    assert calls[-1] == "FINALIZE"
    assert assemblies[0].classifier_authority.invalidity_code is None


def test_failed_adjudicator_is_sealed_before_hard_and_integrated(tmp_path: Path) -> None:
    package = _package(tmp_path)
    calls: list[str] = []

    controller.execute_attempt(
        package,
        _dependencies(
            package,
            disagreement=True,
            calls=calls,
            failed_slots=frozenset({"EVAL.ADJUDICATOR"}),
        ),
    )

    assert calls.index("EVAL.ADJUDICATOR") < calls.index("HARD.DIRECT")
    assert calls[-2:] == ["EVAL.INTEGRATED_REVIEW", "FINALIZE"]


def test_failed_integrated_review_is_sealed_and_finalized(tmp_path: Path) -> None:
    package = _package(tmp_path)
    calls: list[str] = []

    controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=calls,
            failed_slots=frozenset({"EVAL.INTEGRATED_REVIEW"}),
        ),
    )

    assert calls[-2:] == ["EVAL.INTEGRATED_REVIEW", "FINALIZE"]


@pytest.mark.parametrize(
    "slot",
    [
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.ADJUDICATOR",
        "EVAL.INTEGRATED_REVIEW",
    ],
)
def test_invalid_typed_review_payload_is_terminalized_without_rerun(
    tmp_path: Path,
    slot: str,
) -> None:
    package = _package(tmp_path)
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=calls,
            assemblies=assemblies,
            disagreement=slot == "EVAL.ADJUDICATOR",
            invalid_payload_slots=frozenset({slot}),
        ),
    )

    assert calls.count(slot) == 1
    assert calls[-1] == "FINALIZE"
    assert assemblies[0].classifier_authority.invalidity_code is None


def test_hard_evaluator_failure_finalizes_partial_without_integrated_review(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    result = controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=calls,
            assemblies=assemblies,
            hard_failure="PRODUCT_QA",
        ),
    )

    assert "EVAL.INTEGRATED_REVIEW" not in calls
    assert calls[-1] == "FINALIZE"
    assert assemblies[0].classifier_authority.invalidity_code is None
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_blinding_join_invalidity_is_explicit_and_consumes_attempt_once(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    result = controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=calls,
            blinding_invalid=True,
            assemblies=assemblies,
        ),
    )

    assert calls == ["RUN", "FINALIZE"]
    assert len(assemblies) == 1
    assert assemblies[0].classifier_authority.invalidity_code == (
        "BLINDING_JOIN_INVALID"
    )
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_blinding_invalidity_reentry_runs_no_runner_provider_or_hard_work(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            package,
            _dependencies(
                package,
                blinding_invalid=True,
                finalizer_error=True,
            ),
        )
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    result = controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=calls,
            blinding_invalid=True,
            assemblies=assemblies,
        ),
    )

    assert calls == ["FINALIZE"]
    assert assemblies[0].classifier_authority.invalidity_code == (
        "BLINDING_JOIN_INVALID"
    )
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_evaluator_fixture_drift_finalizes_before_target_provider_allocation(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(
        manifest,
        expected_sha256=digest,
    )
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    result = controller.execute_attempt(
        loaded,
        _dependencies(
            loaded,
            calls=calls,
            assemblies=assemblies,
            evaluator_fixture_after_replay=b'{"drift":true}',
        ),
    )

    assert calls == ["RUN", "FINALIZE"]
    assert len(assemblies) == 1
    classifier = assemblies[0].classifier_authority
    assert classifier.invalidity_code == "COMMON_EVALUATION_BYTES_INVALID"
    assert classifier.invalidity_authority is not None
    authority_path = (
        loaded.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/invalidity-authority.json"
    )
    authority = json.loads(authority_path.read_bytes())
    assert authority["invalidity_code"] == "COMMON_EVALUATION_BYTES_INVALID"
    assert authority["evidence"]["target_call_slot"] == (
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS"
    )
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_evaluator_fixture_drift_after_reviews_finalizes_before_hard_collector(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    result = controller.execute_attempt(
        loaded,
        _dependencies(
            loaded,
            calls=calls,
            assemblies=assemblies,
            evaluator_fixture_after_review_slot=(
                "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
            ),
        ),
    )

    assert calls == [
        "RUN",
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
        "FINALIZE",
    ]
    assert tuple(row.call_slot_id for row in assemblies[0].review_records) == (
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    )
    assert assemblies[0].classifier_authority.invalidity_code == (
        "COMMON_EVALUATION_BYTES_INVALID"
    )
    authority = json.loads(
        (
            loaded.paths.evidence_root
            / "attempts/ES-ATTEMPT-01/invalidity-authority.json"
        ).read_bytes()
    )
    assert authority["evidence"]["target_call_slot"] == "HARD.DIRECT"
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_evaluator_invalidity_reentry_uses_frozen_record_after_fixture_restore(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    fixture_path = loaded.paths.workspace / loaded.evaluator_fixture.relative_path
    original_fixture = fixture_path.read_bytes()

    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            loaded,
            _dependencies(
                loaded,
                evaluator_fixture_after_review_slot=(
                    "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
                ),
                finalizer_error=True,
            ),
        )
    fixture_path.write_bytes(original_fixture)
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    result = controller.execute_attempt(
        loaded,
        _dependencies(loaded, calls=calls, assemblies=assemblies),
    )

    assert calls == ["FINALIZE"]
    assert assemblies[0].classifier_authority.invalidity_code == (
        "COMMON_EVALUATION_BYTES_INVALID"
    )
    assert assemblies[0].classifier_authority.invalidity_authority is not None
    assert tuple(row.call_slot_id for row in assemblies[0].review_records) == (
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
    )
    assert result.next_attempt_id == "ES-ATTEMPT-02"


@pytest.mark.parametrize(
    "mutation",
    ["attempt", "binding", "target", "frontier"],
)
def test_evaluator_invalidity_record_tamper_fails_closed_without_provider_call(
    tmp_path: Path,
    mutation: str,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    fixture_path = loaded.paths.workspace / loaded.evaluator_fixture.relative_path
    original_fixture = fixture_path.read_bytes()
    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            loaded,
            _dependencies(
                loaded,
                evaluator_fixture_after_review_slot=(
                    "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
                ),
                finalizer_error=True,
            ),
        )
    fixture_path.write_bytes(original_fixture)
    path = (
        loaded.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/invalidity-authority.json"
    )
    record = json.loads(path.read_bytes())
    if mutation == "attempt":
        record["attempt_id"] = "ES-ATTEMPT-02"
    elif mutation == "binding":
        record["evidence"]["bindings"]["run_id"] = "wrong-run"
    elif mutation == "target":
        record["evidence"]["target_call_slot"] = (
            "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS"
        )
    else:
        record["evidence"]["allocation_frontier"]["allocation_count"] += 1
    path.write_bytes(canonical_json_bytes(record) + b"\n")
    calls: list[str] = []

    with pytest.raises(controller.ControllerError, match="invalidity"):
        controller.execute_attempt(loaded, _dependencies(loaded, calls=calls))

    assert calls == []


def test_missing_evaluator_invalidity_record_remains_ordinary_partial_attempt(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    fixture_path = loaded.paths.workspace / loaded.evaluator_fixture.relative_path
    original_fixture = fixture_path.read_bytes()
    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            loaded,
            _dependencies(
                loaded,
                evaluator_fixture_after_review_slot=(
                    "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
                ),
                finalizer_error=True,
            ),
        )
    fixture_path.write_bytes(original_fixture)
    (
        loaded.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/invalidity-authority.json"
    ).unlink()
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    result = controller.execute_attempt(
        loaded,
        _dependencies(
            loaded,
            calls=calls,
            assemblies=assemblies,
            interrupted_provider_slots=frozenset({"EVAL.INTEGRATED_REVIEW"}),
        ),
    )

    assert calls == ["FINALIZE"]
    assert assemblies[0].classifier_authority.invalidity_code is None
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_owner_disposition_classifies_recovered_header_only_common_outage(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    first, boundary, first_calls = _open_header_only_failed_prefix(loaded)

    expected_path = (
        loaded.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/common-provider-outage-disposition.json"
    )
    assert boundary.attempt_id == "ES-ATTEMPT-01"
    assert boundary.disposition_path == expected_path
    assert boundary.binding_sha256 == _sha(boundary.binding)
    assert json.loads(boundary.binding) == {
        "schema_version": "es.post_incident_disposition_boundary.v1",
        "attempt_id": "ES-ATTEMPT-01",
        "disposition_path": expected_path.as_posix(),
        "bindings": json.loads(
            canonical_json_bytes(_outage_disposition(loaded, first)[1])
        )["evidence"]["bindings"],
        "pre_treatment_proof": {
            "cell_allocation_started_count": 0,
            "provider_allocation_count": 0,
        },
    }
    assert first_calls == ["RUN"]

    disposition_path, disposition = _outage_disposition(loaded, first)
    raw = canonical_json_bytes(disposition) + b"\n"
    disposition_path.write_bytes(raw)
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []
    dependencies = replace(
        _dependencies(loaded, calls=calls, assemblies=assemblies),
        common_provider_outage_disposition_sha256=_sha(raw),
    )

    result = controller.execute_attempt(loaded, dependencies)

    assert calls == ["FINALIZE"]
    assert assemblies[0].classifier_authority.invalidity_code == (
        "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT"
    )
    assert assemblies[0].classifier_authority.invalidity_authority == (
        canonical_json_bytes(disposition)
    )
    assert result.next_attempt_id == "ES-ATTEMPT-02"


@pytest.mark.parametrize(
    "mutation",
    ["digest_after_write", "wrong_run_binding", "circular_owner_statement"],
)
def test_outage_disposition_tamper_fails_closed_without_any_relaunch(
    tmp_path: Path,
    mutation: str,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    first, _boundary, _calls = _open_header_only_failed_prefix(loaded)
    path, disposition = _outage_disposition(loaded, first)
    original = canonical_json_bytes(disposition) + b"\n"
    expected = _sha(original)
    if mutation == "wrong_run_binding":
        evidence = disposition["evidence"]
        assert isinstance(evidence, dict)
        bindings = evidence["bindings"]
        assert isinstance(bindings, dict)
        bindings["run_id"] = "wrong-run"
        original = canonical_json_bytes(disposition) + b"\n"
        expected = _sha(original)
    elif mutation == "circular_owner_statement":
        evidence = disposition["evidence"]
        assert isinstance(evidence, dict)
        adoption = evidence["owner_adoption"]
        assert isinstance(adoption, dict)
        adoption["statement"] = "I adopt this disposition."
        original = canonical_json_bytes(disposition) + b"\n"
        expected = _sha(original)
    path.write_bytes(original)
    if mutation == "digest_after_write":
        path.write_bytes(original.replace(b"owner_confirmed", b"owner_rejected"))
    calls: list[str] = []
    dependencies = replace(
        _dependencies(loaded, calls=calls),
        common_provider_outage_disposition_sha256=expected,
    )

    with pytest.raises(controller.ControllerError, match="outage_disposition"):
        controller.execute_attempt(loaded, dependencies)

    assert calls == []


def test_outage_disposition_binding_is_required_and_missing_file_fails_closed(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    first, _boundary, _calls = _open_header_only_failed_prefix(loaded)
    path, disposition = _outage_disposition(loaded, first)
    raw = canonical_json_bytes(disposition) + b"\n"
    path.write_bytes(raw)

    with pytest.raises(controller.ControllerError, match="binding_required"):
        controller.execute_attempt(loaded, _dependencies(loaded))

    path.unlink()
    with pytest.raises(controller.ControllerError, match="unreadable"):
        controller.execute_attempt(
            loaded,
            replace(
                _dependencies(loaded),
                common_provider_outage_disposition_sha256=_sha(raw),
            ),
        )


def test_outage_disposition_rejects_a_started_provider_allocation(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    first = _dependencies(
        loaded,
        trial_terminal="failed",
        runner_allocation_slots=("DIRECT.D",),
        finalizer_error=True,
    )
    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(loaded, first)
    path, disposition = _outage_disposition(loaded, first)
    raw = canonical_json_bytes(disposition) + b"\n"
    path.write_bytes(raw)

    with pytest.raises(
        controller.ControllerError,
        match="allocation_invalid|prefix_invalid",
    ):
        controller.execute_attempt(
            loaded,
            replace(
                _dependencies(loaded),
                common_provider_outage_disposition_sha256=_sha(raw),
            ),
        )


def test_runner_preallocation_failure_consumes_attempt_without_review_or_hard_call(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    calls: list[str] = []

    result = controller.execute_attempt(
        package,
        _dependencies(package, calls=calls, runner_error=True),
    )

    assert calls == ["RUN", "FINALIZE"]
    assert result.trial_result is None
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_process_reentry_seals_preallocation_prefix_without_rerunning_entry(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            package,
            _dependencies(
                package,
                runner_error=True,
                finalizer_error=True,
            ),
        )
    calls: list[str] = []

    result = controller.execute_attempt(
        package,
        _dependencies(package, calls=calls),
    )

    assert calls == ["FINALIZE"]
    assert result.trial_result is None
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_failed_trial_is_replayed_and_finalized_once_without_resume_or_reviews(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    calls: list[str] = []

    result = controller.execute_attempt(
        package,
        _dependencies(package, calls=calls, trial_terminal="failed"),
    )

    assert calls == ["RUN", "FINALIZE"]
    assert result.trial_result is not None
    assert result.trial_result.terminal_status == "failed"
    assert result.attempt_id == "ES-ATTEMPT-01"
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_non_header_only_failed_trial_continues_to_finalize_normally(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    result = controller.execute_attempt(
        loaded,
        _dependencies(
            loaded,
            calls=calls,
            assemblies=assemblies,
            trial_terminal="failed",
            failed_trial_cell_started=True,
        ),
    )

    assert calls == ["RUN", "FINALIZE"]
    assert assemblies[0].classifier_authority.invalidity_code is None
    assert result.trial_result is not None
    assert result.trial_result.terminal_status == "failed"


def test_recovered_failed_trial_without_outage_disposition_stays_ordinary_partial(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    manifest, digest = _publish_package_manifest(
        package,
        tmp_path / "controller.json",
    )
    loaded = controller.load_controller_package(manifest, expected_sha256=digest)
    _first, boundary, first_calls = _open_header_only_failed_prefix(loaded)
    assert not boundary.disposition_path.exists()
    calls: list[str] = []
    assemblies: list[controller.AttemptAssembly] = []

    def finalize(
        assembly: controller.AttemptAssembly,
    ) -> controller.FinalizedAttempt:
        calls.append("FINALIZE")
        assemblies.append(assembly)
        return controller.canonical_finalize_attempt(assembly)

    dependencies = replace(
        _dependencies(loaded, calls=calls),
        finalize_attempt=finalize,
        allow_untrusted_package_for_tests=False,
    )

    result = controller.execute_attempt(
        loaded,
        dependencies,
    )

    assert first_calls == ["RUN"]
    assert calls == ["FINALIZE"]
    assert assemblies[0].classifier_authority.invalidity_code is None
    assert json.loads(result.attempt_record)["invalidity_code"] == (
        "APPARATUS_ACCOUNTING_INCOMPLETE"
    )
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_review_process_interruption_freezes_durable_prefix_once_and_advances_id(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    calls: list[str] = []
    interrupted = "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"

    result = controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=calls,
            interrupted_provider_slots=frozenset({interrupted}),
        ),
    )

    assert calls == [
        "RUN",
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        interrupted,
        "FINALIZE",
    ]
    assert result.attempt_id == "ES-ATTEMPT-01"
    assert result.next_attempt_id == "ES-ATTEMPT-02"
    journal = (
        package.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/call-allocations.jsonl"
    )
    before = journal.read_bytes()
    assert before.count(b"\n") == 2
    assert journal.read_bytes() == before


def test_process_reentry_closes_existing_interrupted_prefix_without_replaying_calls(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    interrupted = "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
    first_calls: list[str] = []

    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            package,
            _dependencies(
                package,
                calls=first_calls,
                interrupted_provider_slots=frozenset({interrupted}),
                finalizer_error=True,
            ),
        )

    attempt_root = package.paths.evidence_root / "attempts/ES-ATTEMPT-01"
    assert (attempt_root / "trial-prefix.json").is_file()
    assert (
        attempt_root
        / "review-prefix/EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS.json"
    ).is_file()
    frozen = {
        path.relative_to(attempt_root).as_posix(): path.read_bytes()
        for path in attempt_root.rglob("*")
        if path.is_file()
    }
    second_calls: list[str] = []

    result = controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=second_calls,
            interrupted_provider_slots=frozenset({interrupted}),
        ),
    )

    assert second_calls == ["FINALIZE"]
    assert result.attempt_id == "ES-ATTEMPT-01"
    assert result.next_attempt_id == "ES-ATTEMPT-02"
    assert {
        path.relative_to(attempt_root).as_posix(): path.read_bytes()
        for path in attempt_root.rglob("*")
        if path.is_file()
    } == frozen


def test_process_reentry_rejects_tampered_trial_binding_without_relaunch(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    interrupted = "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            package,
            _dependencies(
                package,
                interrupted_provider_slots=frozenset({interrupted}),
                finalizer_error=True,
            ),
        )
    trial_prefix = (
        package.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/trial-prefix.json"
    )
    value = json.loads(trial_prefix.read_bytes())
    value["replay_binding"]["header_row_digest"] = "sha256:" + "0" * 64
    trial_prefix.write_bytes(_record(value) + b"\n")
    calls: list[str] = []

    with pytest.raises(controller.ControllerError, match="binding_mismatch"):
        controller.execute_attempt(package, _dependencies(package, calls=calls))

    assert calls == []


def test_process_reentry_rejects_extra_review_prefix_without_relaunch(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    interrupted = "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            package,
            _dependencies(
                package,
                interrupted_provider_slots=frozenset({interrupted}),
                finalizer_error=True,
            ),
        )
    review_root = (
        package.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/review-prefix"
    )
    source = review_root / "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS.json"
    (review_root / "EVAL.ADJUDICATOR.json").write_bytes(source.read_bytes())
    calls: list[str] = []

    with pytest.raises(controller.ControllerError, match="inventory_invalid"):
        controller.execute_attempt(package, _dependencies(package, calls=calls))

    assert calls == []


def test_process_reentry_rejects_missing_prior_settlement_with_later_allocation(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    interrupted = "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            package,
            _dependencies(
                package,
                interrupted_provider_slots=frozenset({interrupted}),
                finalizer_error=True,
            ),
        )
    (
        package.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/call-settlements.jsonl"
    ).unlink()
    calls: list[str] = []

    with pytest.raises(controller.ControllerError, match="noncontiguous"):
        controller.execute_attempt(package, _dependencies(package, calls=calls))

    assert calls == []


def test_process_reentry_after_hard_failure_never_replays_runner_provider_or_hard(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    with pytest.raises(RuntimeError, match="finalizer interrupted"):
        controller.execute_attempt(
            package,
            _dependencies(
                package,
                hard_failure="PRODUCT_QA",
                finalizer_error=True,
            ),
        )
    calls: list[str] = []

    result = controller.execute_attempt(
        package,
        _dependencies(
            package,
            calls=calls,
            hard_failure="PRODUCT_QA",
        ),
    )

    assert calls == ["FINALIZE"]
    assert result.next_attempt_id == "ES-ATTEMPT-02"


def test_review_allocations_continue_the_same_durable_chain_as_e2_calls(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    controller.execute_attempt(
        package,
        _dependencies(
            package,
            runner_allocation_slots=("DIRECT.I", "EVAL.SCORER_DIRECT"),
        ),
    )
    lock = json.loads(
        (package.paths.workspace / package.decision_lock.relative_path).read_text()
    )
    journal = (
        package.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/call-allocations.jsonl"
    )

    rows = provider_boundary.load_allocation_journal(
        journal,
        attempt_id="ES-ATTEMPT-01",
        decision_lock_sha256=decision_lock.decision_lock_digest(lock),
    )

    assert [row.call_slot_id for row in rows] == [
        "DIRECT.I",
        "EVAL.SCORER_DIRECT",
        "EVAL.INITIAL_SCIENTIFIC_APPLICATION_SEMANTICS",
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY",
        "EVAL.INTEGRATED_REVIEW",
    ]
    assert [row.sequence for row in rows] == list(range(1, 6))


def test_final_report_is_forbidden_before_stop(tmp_path: Path) -> None:
    package = _package(tmp_path)

    def invalid_finalize(_assembly: controller.AttemptAssembly) -> controller.FinalizedAttempt:
        return controller.FinalizedAttempt(
            attempt_record=b"{}",
            attempt_index=b"{}",
            attempt_index_sha256="sha256:" + "7" * 64,
            report=b"{}",
            stopped=False,
            next_attempt_id="ES-ATTEMPT-02",
        )

    dependencies = replace(
        _dependencies(package),
        finalize_attempt=invalid_finalize,
    )
    with pytest.raises(ValueError, match="report"):
        controller.execute_attempt(package, dependencies)


def test_consumed_or_interrupted_attempt_is_never_reused(tmp_path: Path) -> None:
    package = replace(
        _package(tmp_path),
        consumed_attempt_ids=("ES-ATTEMPT-01",),
        consumed_attempt_call_counts=(1,),
        invalid_attempt_count=1,
    )
    seen: list[str] = []
    dependencies = _dependencies(package, calls=seen)
    dependencies = replace(
        dependencies,
        finalize_attempt=lambda assembly: controller.FinalizedAttempt(
            attempt_record=_record({"attempt_id": assembly.attempt_id}),
            attempt_index=_record({"attempt_id": assembly.attempt_id}),
            attempt_index_sha256="sha256:" + "7" * 64,
            report=None,
            stopped=False,
            next_attempt_id="ES-ATTEMPT-03",
        ),
    )

    result = controller.execute_attempt(package, dependencies)

    assert result.attempt_id == "ES-ATTEMPT-02"


def test_unvalidated_existing_attempt_prefix_is_never_reopened(tmp_path: Path) -> None:
    package = _package(tmp_path)
    prefix = (
        package.paths.evidence_root
        / "attempts/ES-ATTEMPT-01/call-allocations.jsonl"
    )
    prefix.parent.mkdir(parents=True)
    prefix.write_text("existing\n", encoding="utf-8")
    calls: list[str] = []

    with pytest.raises(controller.ControllerError, match="prefix_manifest_invalid"):
        controller.execute_attempt(package, _dependencies(package, calls=calls))

    assert calls == []


def test_absolute_denominator_ceiling_rejects_before_runner(tmp_path: Path) -> None:
    package = replace(
        _package(tmp_path),
        consumed_attempt_ids=(
            "ES-ATTEMPT-01",
            "ES-ATTEMPT-02",
            "ES-ATTEMPT-03",
        ),
        consumed_attempt_call_counts=(1, 1, 1),
        invalid_attempt_count=0,
    )
    calls: list[str] = []

    with pytest.raises(ValueError, match="denominator"):
        controller.execute_attempt(package, _dependencies(package, calls=calls))

    assert calls == []


def test_wrong_next_attempt_id_fails_closed(tmp_path: Path) -> None:
    package = _package(tmp_path)
    dependencies = _dependencies(package)
    dependencies = replace(
        dependencies,
        finalize_attempt=lambda assembly: controller.FinalizedAttempt(
            attempt_record=_record({"attempt_id": assembly.attempt_id}),
            attempt_index=_record({"attempt_id": assembly.attempt_id}),
            attempt_index_sha256="sha256:" + "7" * 64,
            report=None,
            stopped=False,
            next_attempt_id="ES-ATTEMPT-04",
        ),
    )

    with pytest.raises(controller.ControllerError, match="next_attempt_mismatch"):
        controller.execute_attempt(package, dependencies)


def test_report_is_returned_only_at_locked_stop(tmp_path: Path) -> None:
    package = _package(tmp_path)

    result = controller.execute_attempt(package, _dependencies(package, stop=True))

    assert result.stopped is True
    assert result.report == _record({"status": "STOP"})
    assert result.next_attempt_id is None


def test_default_replay_rejects_missing_multiple_tamper_and_path_escape(
    tmp_path: Path,
) -> None:
    package = _package(tmp_path)
    result = TrialRunResult.completed(
        run_id="run-1",
        verdict_digest="sha256:" + "9" * 64,
        verdict_path=f"artifacts/trials/{'1' * 64}/verdict.json",
    )
    with pytest.raises(controller.ControllerError, match="artifact_replay"):
        controller.replay_persisted_trial_authority(result, package)

    with pytest.raises(ValueError):
        replace(result, verdict_path="artifacts/trials/../outside/verdict.json")


def test_import_guard_forbids_private_runtime_and_retired_surfaces() -> None:
    trees = tuple(ast.parse(path.read_text(encoding="utf-8")) for path in NEW_ES_MODULES)
    imported = {
        alias.name
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or ""
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    forbidden_modules = (
        "orchestrator.experiments",
        "orchestrator.workflow.trial.runtime",
        "orchestrator.workflow.trial.adjudication",
        "orchestrator.workflow_lisp.build",
        "orchestrator.state",
        "orchestrator.workflow.executor",
    )
    assert not any(
        name == forbidden or name.startswith(forbidden + ".")
        for name in imported
        for forbidden in forbidden_modules
    )
    forbidden_names = {
        "execute_trial_cells",
        "build_frontend_bundle",
        "StateManager",
        "WorkflowExecutor",
    }
    assert not {
        alias.name
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    } & forbidden_names
