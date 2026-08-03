from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.trial.sdk import TrialRunResult
from orchestrator.workflow.trial.settlement import (
    commit_trial_parent_settlement,
    prepare_trial_parent_settlement,
)
from scripts.experiments.es import attempts, controller_artifacts
from tests.experiments import test_es_attempts as attempt_fixtures
from tests.experiments import test_es_synthesis as synthesis_fixtures


@pytest.fixture(scope="module")
def persisted_trial(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("es-controller-artifact-replay")
    trial = attempt_fixtures._trial_fixture(root / "source")
    parent_run_root = trial["execution"].ledger_path
    while parent_run_root.name != "parent-run-root":
        parent_run_root = parent_run_root.parent
    run_id = parent_run_root.name
    state_dir = parent_run_root.parent

    workspace = trial["parent_workspace"]
    request = trial["request"]
    verdict_path = (
        workspace
        / "artifacts"
        / "trials"
        / request.digest.removeprefix("sha256:")
        / "verdict.json"
    )
    verdict = json.loads(verdict_path.read_bytes())
    envelope = {
        "outcomes": verdict["authored_outcomes"],
        "verdict": verdict["verdict"],
        "verdict_artifact": verdict_path.relative_to(workspace).as_posix(),
    }
    prepared = prepare_trial_parent_settlement(
        trial["execution"].ledger_path,
        request=request,
        parent_workspace=workspace,
        result_envelope=envelope,
    )
    artifacts = {"verdict": envelope["verdict_artifact"]}
    parent_state = {
        "run_id": request.visit.parent_run_id,
        "current_step": None,
        "steps": {
            "compare": {
                "status": "completed",
                "name": "compare",
                "step_id": request.visit.step_id,
                "visit_count": request.visit.visit_count,
                "trial": envelope,
                "artifacts": artifacts,
            }
        },
    }
    commit_trial_parent_settlement(
        trial["execution"].ledger_path,
        request=request,
        prepared=prepared,
        step_name="compare",
        expected_artifacts=artifacts,
        read_parent_state=lambda: parent_state,
    )
    result = TrialRunResult.completed(
        run_id=run_id,
        verdict_digest=verdict["verdict_digest"],
        verdict_path=verdict_path.relative_to(workspace).as_posix(),
    )
    evidence_root = (root / "evidence").resolve()
    evidence_root.mkdir()
    return {
        **trial,
        "result": result,
        "state_dir": state_dir,
        "evidence_root": evidence_root,
    }


def _replay(trial):
    return controller_artifacts.replay_trial_run_artifacts(
        trial["result"],
        workspace=trial["parent_workspace"],
        state_dir=trial["state_dir"],
        evidence_root=trial["evidence_root"],
    )


def test_completed_replay_returns_closed_immutable_canonical_authority(
    persisted_trial,
) -> None:
    replay = _replay(persisted_trial)

    request = persisted_trial["request"]
    assert replay.terminal_status == "completed"
    assert replay.trial_request_digest == request.digest
    assert replay.cell_domain == request.cell_domain
    assert replay.sealed_opaque_labels == persisted_trial["sealed"]
    assert replay.verdict is not None
    assert replay.packet_artifact_index is not None
    assert len(replay.packets) == 4
    assert len(replay.score_rows) == 4
    assert len(replay.scorer_settlement_rows) == 4
    assert replay.trial_event_ledger.path.is_file()
    assert replay.score_ledger is not None
    with pytest.raises(FrozenInstanceError):
        replay.terminal_status = "failed"  # type: ignore[misc]

    packet_index = replay.packet_artifact_index.value
    assert packet_index["trial_request_digest"] == request.digest
    assert canonical_json_bytes(packet_index) + b"\n" == (
        replay.packet_artifact_index.canonical_bytes
    )
    assert tuple(row.cell for row in replay.packets) == request.cell_domain


@pytest.mark.parametrize(
    "target",
    ["verdict", "packet_index", "packet", "score_ledger", "event_ledger"],
)
def test_completed_replay_rejects_tampered_canonical_authority(
    persisted_trial,
    tmp_path: Path,
    target: str,
) -> None:
    copied_workspace = (tmp_path / "workspace").resolve()
    copied_state = (tmp_path / "runs").resolve()
    shutil.copytree(persisted_trial["parent_workspace"], copied_workspace)
    shutil.copytree(persisted_trial["state_dir"], copied_state)
    result = persisted_trial["result"]
    run_root = copied_state / result.run_id
    ledger = next(run_root.rglob("trial-events.jsonl"))
    request_hex = persisted_trial["request"].digest.removeprefix("sha256:")
    packet_root = copied_workspace / "artifacts/trials" / request_hex / "packets"
    if target == "verdict":
        path = copied_workspace / str(result.verdict_path)
        path.write_bytes(path.read_bytes().replace(b'"verdict":', b'"verdictX":', 1))
    elif target == "packet_index":
        path = packet_root / "index.json"
        path.write_bytes(path.read_bytes().replace(b'"packet_set_digest":', b'"packet_set_digesX":', 1))
    elif target == "packet":
        path = next(path for path in packet_root.glob("*.json") if path.name != "index.json")
        path.write_bytes(path.read_bytes() + b" ")
    elif target == "score_ledger":
        path = ledger.parent / "scores.jsonl"
        path.write_bytes(path.read_bytes() + b"{}\n")
    else:
        ledger.write_bytes(ledger.read_bytes() + b"{}\n")

    with pytest.raises(controller_artifacts.ControllerArtifactError):
        controller_artifacts.replay_trial_run_artifacts(
            result,
            workspace=copied_workspace,
            state_dir=copied_state,
            evidence_root=persisted_trial["evidence_root"],
        )


def test_replay_rejects_ambiguous_ledger_and_escaped_or_aliased_paths(
    persisted_trial,
    tmp_path: Path,
) -> None:
    copied_state = (tmp_path / "runs").resolve()
    shutil.copytree(persisted_trial["state_dir"], copied_state)
    run_root = copied_state / persisted_trial["result"].run_id
    ledger = next(run_root.rglob("trial-events.jsonl"))
    duplicate = run_root / "other" / "trial-events.jsonl"
    duplicate.parent.mkdir()
    duplicate.write_bytes(ledger.read_bytes())
    with pytest.raises(controller_artifacts.ControllerArtifactError, match="ambiguous"):
        controller_artifacts.replay_trial_run_artifacts(
            persisted_trial["result"],
            workspace=persisted_trial["parent_workspace"],
            state_dir=copied_state,
            evidence_root=persisted_trial["evidence_root"],
        )

    escaped = replace(persisted_trial["result"], run_id="../outside")
    with pytest.raises((ValueError, controller_artifacts.ControllerArtifactError)):
        controller_artifacts.replay_trial_run_artifacts(
            escaped,
            workspace=persisted_trial["parent_workspace"],
            state_dir=persisted_trial["state_dir"],
            evidence_root=persisted_trial["evidence_root"],
        )

    aliased_workspace = tmp_path / "workspace-link"
    aliased_workspace.symlink_to(persisted_trial["parent_workspace"], target_is_directory=True)
    with pytest.raises(controller_artifacts.ControllerArtifactError, match="canonical"):
        controller_artifacts.replay_trial_run_artifacts(
            persisted_trial["result"],
            workspace=aliased_workspace,
            state_dir=persisted_trial["state_dir"],
            evidence_root=persisted_trial["evidence_root"],
        )


def test_failed_replay_preserves_validated_prefix_without_reconstructing_request(
    persisted_trial,
    tmp_path: Path,
) -> None:
    state_dir = (tmp_path / "runs").resolve()
    run_id = "partial-run"
    run_root = state_dir / run_id / "trial-authority"
    run_root.mkdir(parents=True)
    complete_ledger = next(
        (persisted_trial["state_dir"] / persisted_trial["result"].run_id).rglob(
            "trial-events.jsonl"
        )
    )
    first_two = b"".join(complete_ledger.read_bytes().splitlines(keepends=True)[:2])
    (run_root / "trial-events.jsonl").write_bytes(first_two)
    result = TrialRunResult.failed(
        run_id=run_id,
        code="trial_execution_interrupted",
        message="interrupted after the first allocation boundary",
    )

    replay = controller_artifacts.replay_trial_run_artifacts(
        result,
        workspace=persisted_trial["parent_workspace"],
        state_dir=state_dir,
        evidence_root=persisted_trial["evidence_root"],
    )

    assert replay.terminal_status == "failed"
    assert replay.trial_request_digest == persisted_trial["request"].digest
    assert replay.packet_artifact_index is None
    assert replay.packets == ()
    assert replay.score_ledger is None
    assert replay.score_rows == ()
    assert replay.scorer_settlement_rows == ()
    assert replay.verdict is None


def test_artifact_digest_is_raw_sha256() -> None:
    payload = b'{"a":1}\n'
    artifact = controller_artifacts.CanonicalArtifact(
        path=Path("/tmp/example.json"),
        relative_path="example.json",
        sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
        canonical_bytes=payload,
    )
    assert artifact.sha256.endswith(hashlib.sha256(payload).hexdigest())


def _failed_prefix_replay(
    persisted_trial,
    tmp_path: Path,
    *,
    run_id: str,
    evidence_root: Path,
):
    state_dir = (tmp_path / "runs").resolve()
    run_root = state_dir / run_id / "trial-authority"
    run_root.mkdir(parents=True)
    complete_ledger = next(
        (persisted_trial["state_dir"] / persisted_trial["result"].run_id).rglob(
            "trial-events.jsonl"
        )
    )
    (run_root / "trial-events.jsonl").write_bytes(
        complete_ledger.read_bytes().splitlines(keepends=True)[0]
    )
    result = TrialRunResult.failed(
        run_id=run_id,
        code="trial_execution_interrupted",
        message="interrupted before treatment allocation",
    )
    return controller_artifacts.replay_trial_run_artifacts(
        result,
        workspace=persisted_trial["parent_workspace"],
        state_dir=state_dir,
        evidence_root=evidence_root,
    )


def _finalization(
    persisted_trial,
    tmp_path: Path,
    *,
    attempt_id: str,
    prior_indexes=(),
    expected_denominator: int,
    evidence_root: Path | None = None,
):
    lock, schedule, bindings = synthesis_fixtures._lock_and_schedule()
    evidence = (tmp_path / "evidence").resolve() if evidence_root is None else evidence_root
    evidence.mkdir(parents=True, exist_ok=True)
    replay = _failed_prefix_replay(
        persisted_trial,
        tmp_path,
        run_id="run-" + attempt_id.lower(),
        evidence_root=evidence,
    )
    trial_result = TrialRunResult.failed(
        run_id=replay.run_id,
        code="trial_execution_interrupted",
        message="interrupted before treatment allocation",
    )
    frozen = attempts.freeze_trial_artifact_authority(
        persisted_trial["request"],
        persisted_trial["sealed"],
    )
    return controller_artifacts.FinalizationAssembly(
        evidence_root=evidence,
        decision_lock=canonical_json_bytes(lock),
        randomization_manifest=canonical_json_bytes(schedule),
        expected_bindings=tuple(sorted(bindings.items())),
        attempt=controller_artifacts.AttemptRecordInputs(
            attempt_id=attempt_id,
            replay=replay,
            trial_result=trial_result,
            frozen_trial_artifact_authority=frozen.canonical_bytes,
            trial_event_ledger_path=replay.trial_event_ledger_path,
            arm_route_ids=(),
            evaluation_route_id=None,
            material_disagreement=False,
            review_settlements=(),
            receipt_bindings=(),
            source_task_binding_valid=True,
            controller_launch_preallocation_failed=False,
            common_provider_outage_proven=False,
            evaluation_bytes_valid=True,
            blinding_join_valid=True,
            interrupted=True,
        ),
        index=controller_artifacts.PartialIndexInputs(
            frozen_call_authority=canonical_json_bytes(
                synthesis_fixtures._call_authority()
            ),
            receipts_by_slot=(),
            raw_jsonl_by_slot=(),
            elapsed_ms_by_slot=(),
            call_allocations=(),
            partial_evidence=None,
        ),
        prior_indexes=prior_indexes,
        expected_attempt_record=None,
        expected_absolute_call_ceiling=lock["derived"]["call_bounds"][
            "absolute_with_invalid_attempt_capacity"
        ],
        expected_denominator=expected_denominator,
    )


@pytest.mark.parametrize("ledger_kind", ["missing", "corrupt"])
def test_missing_or_corrupt_trial_ledger_finalizes_and_consumes_attempt_id(
    persisted_trial,
    tmp_path: Path,
    ledger_kind: str,
) -> None:
    assembly = _finalization(
        persisted_trial,
        tmp_path,
        attempt_id="ES-ATTEMPT-01",
        expected_denominator=1,
    )
    path: Path | None = None
    if ledger_kind == "corrupt":
        path = (tmp_path / "corrupt-trial-events.jsonl").resolve()
        path.write_bytes(b"not-json\n")
    trial_result = TrialRunResult.failed(
        run_id=persisted_trial["request"].visit.parent_run_id,
        code="trial_execution_interrupted",
        message="trial stopped without replayable ledger authority",
    )
    assembly = replace(
        assembly,
        attempt=replace(
            assembly.attempt,
            replay=None,
            trial_result=trial_result,
            trial_event_ledger_path=path,
        ),
    )

    finalized = controller_artifacts.finalize_attempt_artifacts(assembly)
    record = json.loads(finalized.attempt_record)

    assert record["attempt_id"] == "ES-ATTEMPT-01"
    assert record["status"] == "INVALID"
    assert record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"
    assert record["e2_authority"]["ledger_input_status"] == (
        "NOT_SUPPLIED" if ledger_kind == "missing" else "INVALID_SUPPLIED"
    )
    assert finalized.index_binding.attempt_id == "ES-ATTEMPT-01"
    assert finalized.next_attempt_id == "ES-ATTEMPT-02"


def _derived_prefix_bytes() -> tuple[bytes, bytes]:
    record = {
        "schema_version": "es_attempt_record.v2",
        "attempt_id": "ES-ATTEMPT-01",
    }
    index = {
        "attempt_record": record,
        "reviews": [
            {
                "call_slot_id": "EVAL.INITIAL_APPLICATION",
                "record": {"schema_version": "es.review.v1", "decision": "PASS"},
            }
        ],
        "hard_evaluations": [
            {
                "schema_version": "es.hard_evaluation_evidence.v1",
                "arm_id": "DIRECT",
                "trusted_product_freeze_status": "MISSING",
                "absence_authority": {"reason": "fixture"},
            }
        ],
    }
    return canonical_json_bytes(record), canonical_json_bytes(index)


def _partial_allocation(
    slot: str,
    *,
    sequence: int,
    receipt_sha256: str | None,
) -> bytes:
    authority = {
        "schema_version": "es.provider_call_allocation.v1",
        "attempt_id": "ES-ATTEMPT-01",
        "sequence": sequence,
        "previous_allocation_sha256": None,
        "call_slot_id": slot,
        "decision_lock_sha256": "sha256:" + "1" * 64,
        "static_call_sha256": "sha256:" + "2" * 64,
    }
    return canonical_json_bytes(
        {
            "schema_version": "es.call_allocation.v2",
            "call_slot_id": slot,
            "allocation_authority": authority,
            "allocation_sha256": canonical_sha256(authority),
            "settlement": (
                "RECEIPT_FROZEN"
                if receipt_sha256 is not None
                else "INTERRUPTED_IN_FLIGHT"
            ),
            "receipt_sha256": receipt_sha256,
        }
    )


def test_partial_index_adapter_preserves_settled_and_inflight_call_prefix() -> None:
    receipt = canonical_json_bytes(
        {"block_id": "ES-ATTEMPT-01", "call_slot_id": "ARM.DIRECT"}
    )
    receipt_sha256 = "sha256:" + hashlib.sha256(receipt + b"\n").hexdigest()
    settled = _partial_allocation(
        "ARM.DIRECT",
        sequence=1,
        receipt_sha256=receipt_sha256,
    )
    inflight = _partial_allocation(
        "ARM.RICH",
        sequence=2,
        receipt_sha256=None,
    )
    provider = controller_artifacts.ProviderEvidenceInput(
        call_slot_id="ARM.DIRECT",
        canonical_receipt=receipt,
        raw_jsonl=b'{"type":"fixture"}\n',
        elapsed_ms=7,
        call_allocation=settled,
    )

    result = controller_artifacts.build_partial_index_inputs(
        replay=None,
        private_join=None,
        review_evidence=(),
        provider_evidence=(provider,),
        frozen_call_authority=canonical_json_bytes(
            {"schema_version": "fixture.call_authority.v1"}
        ),
        call_allocations=(settled, inflight),
    )

    assert result.receipts_by_slot == (("ARM.DIRECT", receipt),)
    assert result.raw_jsonl_by_slot == (
        ("ARM.DIRECT", b'{"type":"fixture"}\n'),
    )
    assert result.elapsed_ms_by_slot == (("ARM.DIRECT", 7),)
    assert result.call_allocations == (settled, inflight)
    assert result.partial_evidence is None


def test_partial_index_adapter_allows_truthful_zero_evidence_early_fault() -> None:
    result = controller_artifacts.build_partial_index_inputs(
        replay=None,
        private_join=None,
        review_evidence=(),
        provider_evidence=(),
        frozen_call_authority=canonical_json_bytes(
            {"schema_version": "fixture.call_authority.v1"}
        ),
        call_allocations=(),
    )

    assert result == controller_artifacts.PartialIndexInputs(
        frozen_call_authority=canonical_json_bytes(
            {"schema_version": "fixture.call_authority.v1"}
        ),
        receipts_by_slot=(),
        raw_jsonl_by_slot=(),
        elapsed_ms_by_slot=(),
        call_allocations=(),
        partial_evidence=None,
    )


def test_partial_index_adapter_carries_invalidity_authority_without_packets(
    persisted_trial,
    tmp_path: Path,
) -> None:
    evidence_root = (tmp_path / "invalidity-evidence").resolve()
    evidence_root.mkdir()
    replay = _failed_prefix_replay(
        persisted_trial,
        tmp_path,
        run_id="header-only-invalidity",
        evidence_root=evidence_root,
    )
    authority_record = {
        "schema_version": "es.controller_invalidity_authority.v1",
        "attempt_id": "ES-ATTEMPT-01",
        "invalidity_code": "COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT",
        "evidence": {
            "disposition_sha256": "sha256:" + "a" * 64,
            "no_treatment_started": True,
        },
    }
    authority = canonical_json_bytes(authority_record)

    result = controller_artifacts.build_partial_index_inputs(
        replay=replay,
        private_join=None,
        review_evidence=(),
        provider_evidence=(),
        frozen_call_authority=canonical_json_bytes(
            {"schema_version": "fixture.call_authority.v1"}
        ),
        call_allocations=(),
        invalidity_authority=authority,
    )

    assert result.invalidity_authority == authority
    assert result.partial_evidence is None


def test_invalidity_carrier_preserves_packet_projection_bytes(
    persisted_trial,
) -> None:
    replay = _replay(persisted_trial)
    frozen_calls = canonical_json_bytes(
        {"schema_version": "fixture.call_authority.v1"}
    )
    authority = canonical_json_bytes(
        {
            "schema_version": "es.controller_invalidity_authority.v1",
            "attempt_id": "ES-ATTEMPT-01",
            "invalidity_code": "COMMON_EVALUATION_BYTES_INVALID",
            "evidence": {"cause_digest": "sha256:" + "b" * 64},
        }
    )

    without_authority = controller_artifacts.build_partial_index_inputs(
        replay=replay,
        private_join=None,
        review_evidence=(),
        provider_evidence=(),
        frozen_call_authority=frozen_calls,
        call_allocations=(),
    )
    with_authority = controller_artifacts.build_partial_index_inputs(
        replay=replay,
        private_join=None,
        review_evidence=(),
        provider_evidence=(),
        frozen_call_authority=frozen_calls,
        call_allocations=(),
        invalidity_authority=authority,
    )

    assert without_authority.partial_evidence is not None
    assert with_authority.partial_evidence == without_authority.partial_evidence
    assert set(json.loads(without_authority.partial_evidence)) == {
        "public_packet_replay_inputs",
        "private_blinding_replay_inputs",
        "private_blinding_join",
        "private_blinding_join_sha256",
        "packets",
        "scorer_settlements",
        "reviews",
        "integrated_prior_record_sha256s",
        "adjudication_payload",
        "adjudication_payload_sha256",
        "integrated_payload",
        "integrated_payload_sha256",
        "hard_evaluations",
        "oriented_primary",
        "oriented_primary_sha256",
        "hard_primary_outcome",
        "hard_primary_outcome_sha256",
    }


def test_partial_index_adapter_rejects_noncanonical_invalidity_authority() -> None:
    with pytest.raises(
        controller_artifacts.ControllerArtifactError,
        match="invalidity_authority is not a canonical JSON object",
    ):
        controller_artifacts.build_partial_index_inputs(
            replay=None,
            private_join=None,
            review_evidence=(),
            provider_evidence=(),
            frozen_call_authority=canonical_json_bytes(
                {"schema_version": "fixture.call_authority.v1"}
            ),
            call_allocations=(),
            invalidity_authority=(
                b'{"attempt_id":"ES-ATTEMPT-01", "invalidity_code":'
                b'"COMMON_PROVIDER_OUTAGE_BEFORE_TREATMENT",'
                b'"evidence":{},'
                b'"schema_version":"es.controller_invalidity_authority.v1"}'
            ),
        )


@pytest.mark.parametrize("mutation", ["extra_key", "wrong_schema", "evidence_not_mapping"])
def test_partial_index_adapter_rejects_invalid_authority_envelope(
    mutation: str,
) -> None:
    authority = {
        "schema_version": "es.controller_invalidity_authority.v1",
        "attempt_id": "ES-ATTEMPT-01",
        "invalidity_code": "COMMON_EVALUATION_BYTES_INVALID",
        "evidence": {},
    }
    if mutation == "extra_key":
        authority["detail"] = "top-level prose is not authority"
    elif mutation == "wrong_schema":
        authority["schema_version"] = "es.controller_invalidity_authority.v2"
    else:
        authority["evidence"] = []

    with pytest.raises(
        controller_artifacts.ControllerArtifactError,
        match="invalidity authority envelope is invalid",
    ):
        controller_artifacts.build_partial_index_inputs(
            replay=None,
            private_join=None,
            review_evidence=(),
            provider_evidence=(),
            frozen_call_authority=canonical_json_bytes(
                {"schema_version": "fixture.call_authority.v1"}
            ),
            call_allocations=(),
            invalidity_authority=canonical_json_bytes(authority),
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_evidence",
        "receipt_digest",
        "allocation_copy",
        "settled_without_evidence",
        "slot_mismatch",
    ],
)
def test_partial_index_adapter_rejects_ambiguous_or_mismatched_call_prefix(
    mutation: str,
) -> None:
    receipt = canonical_json_bytes(
        {"block_id": "ES-ATTEMPT-01", "call_slot_id": "ARM.DIRECT"}
    )
    receipt_sha256 = "sha256:" + hashlib.sha256(receipt + b"\n").hexdigest()
    settled = _partial_allocation(
        "ARM.DIRECT",
        sequence=1,
        receipt_sha256=("sha256:" + "f" * 64 if mutation == "receipt_digest" else receipt_sha256),
    )
    provider = controller_artifacts.ProviderEvidenceInput(
        call_slot_id=("ARM.RICH" if mutation == "slot_mismatch" else "ARM.DIRECT"),
        canonical_receipt=receipt,
        raw_jsonl=b"{}\n",
        elapsed_ms=1,
        call_allocation=settled,
    )
    providers = (provider, provider) if mutation == "duplicate_evidence" else (provider,)
    allocations = (settled,)
    if mutation == "allocation_copy":
        allocations = (
            _partial_allocation(
                "ARM.DIRECT",
                sequence=2,
                receipt_sha256=receipt_sha256,
            ),
        )
    elif mutation == "settled_without_evidence":
        providers = ()

    with pytest.raises(controller_artifacts.ControllerArtifactError):
        controller_artifacts.build_partial_index_inputs(
            replay=None,
            private_join=None,
            review_evidence=(),
            provider_evidence=providers,
            frozen_call_authority=canonical_json_bytes(
                {"schema_version": "fixture.call_authority.v1"}
            ),
            call_allocations=allocations,
        )


def test_derived_attempt_prefix_adopts_exact_existing_subset_and_publishes_missing(
    tmp_path: Path,
) -> None:
    root = (tmp_path / "evidence").resolve()
    review = root / "attempts/ES-ATTEMPT-01/reviews/EVAL.INITIAL_APPLICATION.json"
    review.parent.mkdir(parents=True)
    review_payload = canonical_json_bytes(
        {"schema_version": "es.review.v1", "decision": "PASS"}
    ) + b"\n"
    review.write_bytes(review_payload)
    before = review.stat()
    record, index = _derived_prefix_bytes()

    controller_artifacts.adopt_or_publish_derived_attempt_prefix(
        evidence_root=root,
        attempt_id="ES-ATTEMPT-01",
        attempt_record=record,
        attempt_index=index,
    )

    assert review.read_bytes() == review_payload
    assert review.stat().st_ino == before.st_ino
    assert (root / "attempts/ES-ATTEMPT-01/record.json").read_bytes() == (
        record + b"\n"
    )
    assert (
        root / "attempts/ES-ATTEMPT-01/hard/DIRECT.json"
    ).read_bytes() == canonical_json_bytes(
        {
            "schema_version": "es.hard_evaluation_evidence.v1",
            "arm_id": "DIRECT",
            "trusted_product_freeze_status": "MISSING",
            "absence_authority": {"reason": "fixture"},
        }
    ) + b"\n"


@pytest.mark.parametrize("existing", ["mismatch", "extra", "alias"])
def test_derived_attempt_prefix_rejects_existing_drift_before_any_publication(
    tmp_path: Path,
    existing: str,
) -> None:
    root = (tmp_path / "evidence").resolve()
    reviews = root / "attempts/ES-ATTEMPT-01/reviews"
    reviews.mkdir(parents=True)
    expected = reviews / "EVAL.INITIAL_APPLICATION.json"
    if existing == "mismatch":
        expected.write_bytes(b'{}\n')
    elif existing == "extra":
        (reviews / "EVAL.EXTRA.json").write_bytes(b'{}\n')
    else:
        target = tmp_path / "outside.json"
        target.write_bytes(b'{}\n')
        expected.symlink_to(target)
    record, index = _derived_prefix_bytes()

    with pytest.raises(controller_artifacts.ControllerArtifactError):
        controller_artifacts.adopt_or_publish_derived_attempt_prefix(
            evidence_root=root,
            attempt_id="ES-ATTEMPT-01",
            attempt_record=record,
            attempt_index=index,
        )

    assert not (root / "attempts/ES-ATTEMPT-01/record.json").exists()
    assert not (root / "attempts/ES-ATTEMPT-01/hard").exists()


@pytest.mark.parametrize("boundary", ["index", "report"])
def test_finalized_publication_adopts_exact_existing_final_boundary_after_crash(
    tmp_path: Path,
    boundary: str,
) -> None:
    root = (tmp_path / "evidence").resolve()
    root.mkdir()
    record_bytes, index_bytes = _derived_prefix_bytes()
    record = json.loads(record_bytes)
    index = json.loads(index_bytes)
    report = (
        {"schema_version": "es.study_report.v1", "stopped": True}
        if boundary == "report"
        else None
    )
    controller_artifacts._publish_finalized_evidence(
        root=root,
        attempt_id="ES-ATTEMPT-01",
        attempt_record=record,
        attempt_index=index,
        report=report,
    )
    path = (
        root / "report.json"
        if boundary == "report"
        else root / "attempts/ES-ATTEMPT-01/index.json"
    )
    before = path.stat()

    controller_artifacts._publish_finalized_evidence(
        root=root,
        attempt_id="ES-ATTEMPT-01",
        attempt_record=record,
        attempt_index=index,
        report=report,
    )

    assert path.stat().st_ino == before.st_ino


@pytest.mark.parametrize("boundary", ["index", "report"])
def test_finalized_publication_rejects_drifted_existing_final_boundary(
    tmp_path: Path,
    boundary: str,
) -> None:
    root = (tmp_path / "evidence").resolve()
    root.mkdir()
    record_bytes, index_bytes = _derived_prefix_bytes()
    record = json.loads(record_bytes)
    index = json.loads(index_bytes)
    report = (
        {"schema_version": "es.study_report.v1", "stopped": True}
        if boundary == "report"
        else None
    )
    controller_artifacts._publish_finalized_evidence(
        root=root,
        attempt_id="ES-ATTEMPT-01",
        attempt_record=record,
        attempt_index=index,
        report=report,
    )
    path = (
        root / "report.json"
        if boundary == "report"
        else root / "attempts/ES-ATTEMPT-01/index.json"
    )
    path.write_bytes(b"{}\n")

    with pytest.raises(controller_artifacts.ControllerArtifactError):
        controller_artifacts._publish_finalized_evidence(
            root=root,
            attempt_id="ES-ATTEMPT-01",
            attempt_record=record,
            attempt_index=index,
            report=report,
        )


def test_partial_finalizer_builds_validates_and_publishes_exact_stage_prefix(
    persisted_trial,
    tmp_path: Path,
) -> None:
    assembly = _finalization(
        persisted_trial,
        tmp_path,
        attempt_id="ES-ATTEMPT-01",
        expected_denominator=1,
    )

    result = controller_artifacts.finalize_attempt_artifacts(assembly)

    root = assembly.evidence_root
    record = root / "attempts/ES-ATTEMPT-01/record.json"
    index = root / "attempts/ES-ATTEMPT-01/index.json"
    assert record.read_bytes() == result.attempt_record + b"\n"
    assert index.read_bytes() == result.attempt_index + b"\n"
    assert not (root / "report.json").exists()
    assert result.stopped is False
    assert result.next_attempt_id == "ES-ATTEMPT-02"
    assert result.index_binding == controller_artifacts.AttemptIndexBinding(
        attempt_id="ES-ATTEMPT-01",
        relative_path="attempts/ES-ATTEMPT-01/index.json",
        sha256="sha256:" + hashlib.sha256(index.read_bytes()).hexdigest(),
    )


@pytest.mark.parametrize("field", ["ceiling", "denominator"])
def test_finalizer_rejects_injected_transition_drift_before_publication(
    persisted_trial,
    tmp_path: Path,
    field: str,
) -> None:
    assembly = _finalization(
        persisted_trial,
        tmp_path,
        attempt_id="ES-ATTEMPT-01",
        expected_denominator=1,
    )
    if field == "ceiling":
        assembly = replace(
            assembly,
            expected_absolute_call_ceiling=assembly.expected_absolute_call_ceiling - 1,
        )
    else:
        assembly = replace(assembly, expected_denominator=2)

    with pytest.raises(controller_artifacts.ControllerArtifactError):
        controller_artifacts.finalize_attempt_artifacts(assembly)

    assert not (assembly.evidence_root / "attempts/ES-ATTEMPT-01").exists()


def test_second_invalid_attempt_rejects_at_locked_invalid_capacity(
    persisted_trial,
    tmp_path: Path,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    first = controller_artifacts.finalize_attempt_artifacts(
        _finalization(
            persisted_trial,
            tmp_path / "first",
            attempt_id="ES-ATTEMPT-01",
            expected_denominator=1,
            evidence_root=evidence_root,
        )
    )
    with pytest.raises(
        controller_artifacts.ControllerArtifactError,
        match="call ceiling",
    ):
        controller_artifacts.finalize_attempt_artifacts(
            _finalization(
                persisted_trial,
                tmp_path / "second",
                attempt_id="ES-ATTEMPT-02",
                prior_indexes=(first.index_binding,),
                expected_denominator=2,
                evidence_root=evidence_root,
            )
        )

    assert not (evidence_root / "attempts/ES-ATTEMPT-02").exists()
    assert not (evidence_root / "report.json").exists()


def test_finalizer_rejects_tampered_history_raw_digest_before_new_publication(
    persisted_trial,
    tmp_path: Path,
) -> None:
    evidence_root = (tmp_path / "evidence").resolve()
    evidence_root.mkdir()
    first = controller_artifacts.finalize_attempt_artifacts(
        _finalization(
            persisted_trial,
            tmp_path / "first",
            attempt_id="ES-ATTEMPT-01",
            expected_denominator=1,
            evidence_root=evidence_root,
        )
    )
    index_path = evidence_root / first.index_binding.relative_path
    index_path.write_bytes(index_path.read_bytes() + b" ")

    with pytest.raises(controller_artifacts.ControllerArtifactError, match="history"):
        controller_artifacts.finalize_attempt_artifacts(
            _finalization(
                persisted_trial,
                tmp_path / "second",
                attempt_id="ES-ATTEMPT-02",
                prior_indexes=(first.index_binding,),
                expected_denominator=2,
                evidence_root=evidence_root,
            )
        )
