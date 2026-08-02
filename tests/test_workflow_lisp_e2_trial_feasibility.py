from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import re
import shutil
from statistics import median
from typing import Any, Mapping

import pytest

from orchestrator.workflow.adjudication import (
    EvaluatorOutputError,
    load_score_ledger_rows,
    materialize_run_score_ledger,
    parse_evaluator_output,
    scorer_identity_hash,
    select_candidate,
)
from orchestrator.workflow.pure_result_replay import (
    PureReplayVisitWitness,
    build_pure_completion_shell,
    validate_pure_completion_shell,
)
from orchestrator.workflow.run_ref.contracts import (
    RepositoryRevisionId,
    SetupPolicy,
    authored_setup_identity,
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.delta import (
    DeclaredArtifact,
    build_workspace_delta,
    validate_workspace_delta,
)
from orchestrator.workflow.run_ref.ledger import (
    RunRefAttemptBindings,
    RunRefVisitKey,
    advance_attempt,
    allocate_attempt,
    identify_incomplete_attempt,
    load_attempt_ledger,
    reconcile_pending_parent_commit,
    record_discarded_attempt,
    select_committed_reuse,
    settled_result_binding,
)
from orchestrator.workflow.run_ref.result_contract import (
    is_transportable_type_descriptor,
)
from orchestrator.workflow.run_ref.runtime import build_run_ref_accounting
from orchestrator.workflow.run_ref.workspace import TreeManifest, freeze_tree
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


class _TrialFeasibilityError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _BlindCell:
    arm_id: str
    source_locator: str
    source_commit: str
    source_filename: str
    provider_model: str
    completion_order: int
    sidecar_path: str
    envelope: Mapping[str, Any] | None
    failure: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class _DurableCellFact:
    arm_id: str
    rep: int
    attempt_ordinal: int
    settlement_digest: str
    score: float


@dataclass(frozen=True)
class _EvidenceAuthority:
    envelope: Mapping[str, Any]
    base: RepositoryRevisionId
    baseline_root: Path
    baseline_manifest: TreeManifest
    workspace_root: Path
    declared_artifacts: tuple[DeclaredArtifact, ...]


def _digest(marker: str) -> str:
    assert len(marker) == 1 and marker in "0123456789abcdef"
    return "sha256:" + marker * 64


def _failed_arm_evidence(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "phase": "child_execution",
        "retryable": False,
        "secondary_causes": [],
    }


def _build_e1_envelope_authority(
    tmp_path: Path,
    *,
    label: str,
    bindings: RunRefAttemptBindings,
    ordinal: int,
) -> _EvidenceAuthority:
    baseline_root = (tmp_path / label / f"baseline-{ordinal}").resolve()
    baseline_root.mkdir(parents=True)
    (baseline_root / "input.txt").write_text("fixed input\n", encoding="utf-8")
    baseline_manifest = freeze_tree(baseline_root)

    workspace_root = bindings.workspace_path
    workspace_root.mkdir(parents=True)
    (workspace_root / "input.txt").write_text("fixed input\n", encoding="utf-8")
    artifact = workspace_root / "artifacts" / "result.txt"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(f"validated result {label} {ordinal}\n", encoding="utf-8")
    declared = (DeclaredArtifact("value", "artifacts/result.txt"),)
    base = RepositoryRevisionId.build(
        normalized_locator=f"file:///sealed/{label}",
        resolved_commit_sha="0123456789abcdef0123456789abcdef01234567",
        materializer_version="git-worktree.v1",
        submodule_policy="reject",
        lfs_policy="reject",
        authored_setup_identity=authored_setup_identity(SetupPolicy()),
    )
    delta = build_workspace_delta(
        base=base,
        baseline_root=baseline_root,
        baseline_manifest=baseline_manifest,
        workspace_root=workspace_root,
        declared_artifacts=declared,
    )
    accounting = build_run_ref_accounting(
        child_run_id=bindings.child_run_id,
        attempt_ordinal=ordinal,
        terminal_status="completed",
        elapsed_ms=30,
        setup_ms=5,
        compile_ms=7,
    )
    envelope = {
        "value": "artifacts/result.txt",
        "workspace_delta": delta.record,
        "accounting": accounting,
    }
    assert set(envelope) == {"value", "workspace_delta", "accounting"}
    return _EvidenceAuthority(
        envelope=envelope,
        base=base,
        baseline_root=baseline_root,
        baseline_manifest=baseline_manifest,
        workspace_root=workspace_root,
        declared_artifacts=declared,
    )


def _packet_item(item_id: str, kind: str, value: Any) -> dict[str, Any]:
    return {"id": item_id, "kind": kind, "value": value}


def _build_opaque_packet(
    cell: _BlindCell,
    *,
    evaluation_id: str,
    max_item_bytes: int = 4096,
    max_packet_bytes: int = 16384,
) -> dict[str, Any]:
    items = [
        _packet_item(
            "task_spec",
            "task_spec",
            {"objective": "judge the validated whole-run evidence"},
        )
    ]
    if cell.envelope is not None:
        assert cell.failure is None
        workspace_delta = cell.envelope["workspace_delta"]
        items.extend(
            (
                _packet_item(
                    "validated_result",
                    "validated_result",
                    cell.envelope["value"],
                ),
                _packet_item(
                    "workspace_delta",
                    "workspace_delta",
                    {
                        "normalized_diff": workspace_delta["normalized_diff"],
                        "declared_artifacts": workspace_delta[
                            "declared_artifacts"
                        ],
                    },
                ),
                _packet_item(
                    "check_results",
                    "check_results",
                    [{"id": "fixture", "passed": True}],
                ),
            )
        )
    else:
        assert cell.failure is not None
        items.append(
            _packet_item(
                "failure_evidence",
                "failure_evidence",
                cell.failure,
            )
        )

    for item in items:
        if len(canonical_json_bytes(item)) > max_item_bytes:
            raise _TrialFeasibilityError(
                "trial_packet_limit_invalid",
                f"item {item['id']} exceeds the item byte limit",
            )
    packet = {
        "schema": "trial.evaluation_packet.v1",
        "evaluation_id": evaluation_id,
        "items": items,
        "citable_item_ids": [item["id"] for item in items],
    }
    if len(canonical_json_bytes(packet)) > max_packet_bytes:
        raise _TrialFeasibilityError(
            "trial_packet_limit_invalid",
            "packet exceeds the packet byte limit",
        )
    return packet


def _parse_cited_score(raw: str, packet: Mapping[str, Any]) -> dict[str, Any]:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EvaluatorOutputError("trial evaluator output must be JSON") from exc
    if not isinstance(document, dict) or set(document) != {
        "candidate_id",
        "score",
        "summary",
        "citations",
    }:
        raise EvaluatorOutputError("trial evaluator output fields are invalid")
    parsed = parse_evaluator_output(
        raw,
        expected_candidate_id=str(packet["evaluation_id"]),
    )
    citations = document["citations"]
    citable = set(packet["citable_item_ids"])
    if (
        not isinstance(citations, list)
        or any(not isinstance(item, str) for item in citations)
        or any(item not in citable for item in citations)
    ):
        raise _TrialFeasibilityError(
            "trial_packet_citation_invalid",
            "every citation must resolve inside the exact packet",
        )
    return {
        "evaluation_id": parsed["candidate_id"],
        "score": parsed["score"],
        "summary": parsed["summary"],
        "citations": citations,
    }


_TRIAL_SCORE_ROW_KEYS = frozenset(
    {
        "schema",
        "trial_request_digest",
        "evaluation_id",
        "packet_digest",
        "scorer_identity_hash",
        "score",
        "summary",
        "citations",
    }
)
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _validate_trial_score_row(row: Mapping[str, Any]) -> None:
    if set(row) != _TRIAL_SCORE_ROW_KEYS or row["schema"] != "trial.score.v1":
        raise _TrialFeasibilityError(
            "trial_score_row_invalid",
            "trial score row fields are not closed",
        )
    for field in (
        "trial_request_digest",
        "packet_digest",
        "scorer_identity_hash",
    ):
        if not isinstance(row[field], str) or _SHA256_RE.fullmatch(row[field]) is None:
            raise _TrialFeasibilityError(
                "trial_score_row_invalid",
                f"{field} is not a canonical digest",
            )
    if (
        not isinstance(row["evaluation_id"], str)
        or not row["evaluation_id"].startswith("opaque-")
        or type(row["score"]) is not float
        or not isinstance(row["summary"], str)
        or not isinstance(row["citations"], list)
        or any(not isinstance(item, str) for item in row["citations"])
    ):
        raise _TrialFeasibilityError(
            "trial_score_row_invalid",
            "trial score row values are invalid",
        )


def _trial_score_row(
    parsed: Mapping[str, Any],
    *,
    packet: Mapping[str, Any],
    scorer_digest: str,
) -> dict[str, Any]:
    row = {
        "schema": "trial.score.v1",
        "trial_request_digest": _digest("f"),
        "evaluation_id": parsed["evaluation_id"],
        "packet_digest": canonical_sha256(packet),
        "scorer_identity_hash": scorer_digest,
        "score": parsed["score"],
        "summary": parsed["summary"],
        "citations": list(parsed["citations"]),
    }
    _validate_trial_score_row(row)
    return row


def _mapping_keys_and_scalar_values(value: Any) -> tuple[set[str], set[Any]]:
    keys: set[str] = set()
    scalars: set[Any] = set()

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                keys.add(str(key))
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
        elif isinstance(item, (str, int, float, bool, type(None))):
            scalars.add(item)

    visit(value)
    return keys, scalars


def _visit(label: str) -> RunRefVisitKey:
    return RunRefVisitKey(
        parent_run_id="trial-parent",
        execution_frame_id="root",
        call_frame_id=None,
        step_id=f"root.{label}",
        visit_count=1,
    )


def _bindings(tmp_path: Path, label: str, *, ordinal: int = 1) -> RunRefAttemptBindings:
    root = (tmp_path / label / "run-ref-root").resolve()
    return RunRefAttemptBindings(
        run_ref_root=root,
        workspace_path=(root / "runs" / label / str(ordinal) / "workspace"),
        source_digest=_digest("1"),
        program_digest=_digest("2"),
        input_digest=_digest("3"),
        policy_digest=_digest("4"),
        step_config_digest=_digest("5"),
        capsule_or_compiler_digest=_digest("6"),
        child_run_id=f"trial-parent--{label}--{ordinal}",
        result_contract_digest=_digest("7"),
    )


_LAUNCH_TRANSITIONS = (
    ("materialized", {"verified_git_tree_id": "git-tree:" + "a" * 40}),
    (
        "setup_completed",
        {
            "setup_evidence_digest": _digest("8"),
            "post_setup_baseline_digest": _digest("9"),
        },
    ),
    ("program_prepared", {"program_preparation_digest": _digest("a")}),
    ("launched", {"child_launch_digest": _digest("b")}),
)


def _settlement_transitions(
    authority: _EvidenceAuthority,
) -> tuple[tuple[str, dict[str, str]], ...]:
    envelope = authority.envelope
    accounting = envelope["accounting"]
    return (
        *_LAUNCH_TRANSITIONS,
        (
            "child_completed",
            {
                "child_terminal_state_digest": canonical_sha256(
                    {
                        "child_run_id": accounting["child_run_id"],
                        "status": "completed",
                    }
                ),
                "result_payload_digest": canonical_sha256(envelope["value"]),
            },
        ),
        (
            "delta_captured",
            {
                "workspace_delta_digest": canonical_sha256(
                    envelope["workspace_delta"]
                ),
                "accounting_digest": canonical_sha256(accounting),
                "evidence_manifest_digest": canonical_sha256(envelope),
            },
        ),
        ("completed_pending_parent_commit", {}),
    )


def _advance_transitions(
    path: Path,
    *,
    visit: RunRefVisitKey,
    ordinal: int,
    transitions: tuple[tuple[str, dict[str, str]], ...],
):
    row = None
    for stage, updates in transitions:
        row = advance_attempt(
            path,
            visit=visit,
            attempt_ordinal=ordinal,
            stage=stage,
            binding_updates=updates,
        )
    assert row is not None
    return row


def _authority_validator(authority: _EvidenceAuthority):
    envelope = authority.envelope

    def validate(row) -> None:
        validate_workspace_delta(
            envelope["workspace_delta"],
            expected_digest=row.bindings.workspace_delta_digest,
            base=authority.base,
            baseline_root=authority.baseline_root,
            baseline_manifest=authority.baseline_manifest,
            workspace_root=authority.workspace_root,
            declared_artifacts=authority.declared_artifacts,
        )
        accounting = envelope["accounting"]
        assert accounting == build_run_ref_accounting(**accounting)
        assert row.bindings.accounting_digest == canonical_sha256(accounting)
        assert row.bindings.result_payload_digest == canonical_sha256(
            envelope["value"]
        )
        assert row.bindings.evidence_manifest_digest == canonical_sha256(envelope)

    return validate


def _settle(
    path: Path,
    *,
    visit: RunRefVisitKey,
    bindings: RunRefAttemptBindings,
):
    allocated = allocate_attempt(path, visit=visit, bindings=bindings)
    authority = _build_e1_envelope_authority(
        bindings.run_ref_root.parent.parent,
        label=visit.step_id.replace(".", "-"),
        bindings=bindings,
        ordinal=allocated.attempt_ordinal,
    )
    pending = _advance_transitions(
        path,
        visit=visit,
        ordinal=allocated.attempt_ordinal,
        transitions=_settlement_transitions(authority),
    )
    settlement = settled_result_binding(pending)
    committed = reconcile_pending_parent_commit(
        path,
        settled_result=settlement,
        current_step_config_digest=bindings.step_config_digest,
        validate_bound_authority=_authority_validator(authority),
    )
    return settlement, committed, authority


def _transient_view(facts: tuple[_DurableCellFact, ...]) -> dict[str, Any]:
    authored_order = tuple(dict.fromkeys(fact.arm_id for fact in facts))
    return {
        "authored_order": authored_order,
        "medians": {
            arm_id: median(
                fact.score for fact in facts if fact.arm_id == arm_id
            )
            for arm_id in authored_order
        },
    }


def test_whole_run_evidence_composes_with_neutral_scoring_without_identity_leaks(
    tmp_path: Path,
) -> None:
    authority_a = _build_e1_envelope_authority(
        tmp_path,
        label="packet-a",
        bindings=_bindings(tmp_path, "packet-a"),
        ordinal=1,
    )
    authority_b = _build_e1_envelope_authority(
        tmp_path,
        label="packet-b",
        bindings=_bindings(tmp_path, "packet-b"),
        ordinal=1,
    )
    cells = (
        _BlindCell(
            "DIRECT",
            "/secret/direct/repo",
            "0123456789" * 4,
            "secret-direct.orc",
            "secret-provider-a",
            917,
            ".orchestrate/runs/direct/state.json",
            authority_a.envelope,
        ),
        _BlindCell(
            "ORC",
            "/secret/orc/repo",
            "fedcba9876" * 4,
            "secret-orc.orc",
            "secret-provider-b",
            918,
            ".orchestrate/runs/orc/state.json",
            authority_b.envelope,
        ),
        _BlindCell(
            "COORDINATOR",
            "/secret/coordinator/repo",
            "13579bdf02" * 4,
            "secret-coordinator.orc",
            "secret-provider-c",
            919,
            ".orchestrate/runs/coordinator/state.json",
            None,
            _failed_arm_evidence("child_result_invalid"),
        ),
    )
    scorer = {
        "evaluator_provider": "secret-scorer-provider",
        "evaluator_params": {"temperature": 0},
        "evaluator_prompt_source_kind": "asset",
        "evaluator_prompt_source": "secret/rubric-prompt.md",
        "evaluator_prompt_hash": _digest("1"),
        "rubric_source_kind": "asset",
        "rubric_source": "secret/rubric.md",
        "rubric_hash": _digest("2"),
        "evidence_limits": {"max_item_bytes": 4096, "max_packet_bytes": 16384},
        "evidence_confidentiality": "same_trust_boundary",
    }
    scorer_digest = scorer_identity_hash(scorer)
    assert scorer_digest == scorer_identity_hash(dict(scorer))
    changed_scorer = dict(scorer, rubric_hash=_digest("3"))
    assert scorer_digest != scorer_identity_hash(changed_scorer)

    packets = []
    rows = []
    for index, cell in enumerate(cells, start=1):
        evaluation_id = f"opaque-{index:02d}"
        packet = _build_opaque_packet(cell, evaluation_id=evaluation_id)
        packets.append(packet)
        citation = (
            "workspace_delta"
            if cell.envelope is not None
            else "failure_evidence"
        )
        parsed = _parse_cited_score(
            json.dumps(
                {
                    "candidate_id": evaluation_id,
                    "score": 0.5 + index / 10,
                    "summary": f"opaque assessment {index}",
                    "citations": [citation],
                }
            ),
            packet,
        )
        rows.append(
            _trial_score_row(
                parsed,
                packet=packet,
                scorer_digest=scorer_digest,
            )
        )

    for packet, cell in zip(packets, cells, strict=True):
        assert packet["citable_item_ids"] == [
            item["id"] for item in packet["items"]
        ]
        if cell.envelope is not None:
            workspace_item = next(
                item for item in packet["items"] if item["id"] == "workspace_delta"
            )
            assert set(workspace_item["value"]) == {
                "normalized_diff",
                "declared_artifacts",
            }
        packet_keys, packet_scalars = _mapping_keys_and_scalar_values(packet)
        assert packet_keys.isdisjoint(
            {
                "arm_id",
                "treatment",
                "source_locator",
                "source_commit",
                "source_filename",
                "provider_model",
                "completion_order",
                "sidecar_path",
                "base",
                "accounting",
            }
        )
        for secret in (
            cell.arm_id,
            cell.source_locator,
            cell.source_commit,
            cell.source_filename,
            cell.provider_model,
            cell.completion_order,
            cell.sidecar_path,
        ):
            assert secret not in packet_scalars

    ledger_path = tmp_path / "trial-scores.jsonl"
    materialize_run_score_ledger(rows, ledger_path)
    loaded_rows = load_score_ledger_rows(ledger_path)
    assert loaded_rows == rows
    for row in loaded_rows:
        _validate_trial_score_row(row)
        row_keys, row_scalars = _mapping_keys_and_scalar_values(row)
        assert row_keys == _TRIAL_SCORE_ROW_KEYS
        assert not any(
            key.startswith(("candidate_", "provider_", "source_", "promotion_"))
            for key in row_keys
        )
        assert {"DIRECT", "ORC", "COORDINATOR", ".orchestrate"}.isdisjoint(
            row_scalars
        )


def test_opaque_packet_and_score_adapter_fail_closed(tmp_path: Path) -> None:
    authority = _build_e1_envelope_authority(
        tmp_path,
        label="negative-packet",
        bindings=_bindings(tmp_path, "negative-packet"),
        ordinal=1,
    )
    cell = _BlindCell(
        "SECRET-ARM",
        "/secret/repo",
        "a" * 40,
        "secret.orc",
        "secret-provider",
        1,
        ".orchestrate/runs/secret/state.json",
        authority.envelope,
    )
    packet = _build_opaque_packet(cell, evaluation_id="opaque-01")

    wrong_identity = json.dumps(
        {
            "candidate_id": "opaque-wrong",
            "score": 0.7,
            "summary": "wrong identity",
            "citations": ["workspace_delta"],
        }
    )
    with pytest.raises(EvaluatorOutputError, match="candidate_id"):
        _parse_cited_score(wrong_identity, packet)

    unknown_citation = json.dumps(
        {
            "candidate_id": "opaque-01",
            "score": 0.7,
            "summary": "unknown citation",
            "citations": ["sealed_sidecar"],
        }
    )
    with pytest.raises(_TrialFeasibilityError) as excinfo:
        _parse_cited_score(unknown_citation, packet)
    assert excinfo.value.code == "trial_packet_citation_invalid"

    with pytest.raises(_TrialFeasibilityError) as excinfo:
        _build_opaque_packet(
            replace(
                cell,
                envelope={
                    **cell.envelope,
                    "value": {"oversized": "x" * 128},
                },
            ),
            evaluation_id="opaque-01",
            max_item_bytes=64,
        )
    assert excinfo.value.code == "trial_packet_limit_invalid"


def test_existing_single_winner_selection_is_not_trial_aggregation() -> None:
    legacy_candidates = (
        {
            "candidate_id": "opaque-a1",
            "candidate_status": "output_valid",
            "score_status": "scored",
            "score": 0.9,
        },
        {
            "candidate_id": "opaque-a2",
            "candidate_status": "output_valid",
            "score_status": "scored",
            "score": 0.1,
        },
        {
            "candidate_id": "opaque-b1",
            "candidate_status": "output_valid",
            "score_status": "scored",
            "score": 0.6,
        },
        {
            "candidate_id": "opaque-b2",
            "candidate_status": "output_valid",
            "score_status": "scored",
            "score": 0.6,
        },
    )

    legacy = select_candidate(
        legacy_candidates,
        require_score_for_single_candidate=True,
    )
    trial_medians = {"arm-a": median((0.9, 0.1)), "arm-b": median((0.6, 0.6))}

    assert legacy.selected_candidate_id == "opaque-a1"
    assert max(trial_medians, key=trial_medians.__getitem__) == "arm-b"


def test_trial_durable_fact_model_fits_clean_and_crash_resume_without_memo(
    tmp_path: Path,
) -> None:
    clean_a_path = tmp_path / "clean-a.jsonl"
    clean_b_path = tmp_path / "clean-b.jsonl"
    clean_a_binding = _bindings(tmp_path, "clean-a")
    clean_b_binding = _bindings(tmp_path, "clean-b")
    clean_a_settlement, _, _ = _settle(
        clean_a_path,
        visit=_visit("clean-a"),
        bindings=clean_a_binding,
    )
    clean_b_settlement, _, _ = _settle(
        clean_b_path,
        visit=_visit("clean-b"),
        bindings=clean_b_binding,
    )

    resumed_a_path = tmp_path / "resumed-a.jsonl"
    resumed_b_path = tmp_path / "resumed-b.jsonl"
    resumed_a_binding = _bindings(tmp_path, "resumed-a")
    resumed_b_binding = _bindings(tmp_path, "resumed-b")
    resumed_a_settlement, _, resumed_a_authority = _settle(
        resumed_a_path,
        visit=_visit("resumed-a"),
        bindings=resumed_a_binding,
    )
    a_bytes_before_reuse = resumed_a_path.read_bytes()
    reused_a = select_committed_reuse(
        resumed_a_path,
        settled_result=resumed_a_settlement,
        current_step_config_digest=resumed_a_binding.step_config_digest,
        validate_bound_authority=_authority_validator(resumed_a_authority),
    )
    assert reused_a.attempt_ordinal == 1
    assert resumed_a_path.read_bytes() == a_bytes_before_reuse
    assert sum(
        row.stage == "launched" and row.status == "in_progress"
        for row in load_attempt_ledger(resumed_a_path).rows
    ) == 1

    resumed_b_visit = _visit("resumed-b")
    first = allocate_attempt(
        resumed_b_path,
        visit=resumed_b_visit,
        bindings=resumed_b_binding,
    )
    resumed_b_binding.workspace_path.mkdir(parents=True)
    (resumed_b_binding.workspace_path / "incident.txt").write_text(
        "launched then interrupted\n",
        encoding="utf-8",
    )
    _advance_transitions(
        resumed_b_path,
        visit=resumed_b_visit,
        ordinal=first.attempt_ordinal,
        transitions=_LAUNCH_TRANSITIONS,
    )
    incomplete = identify_incomplete_attempt(
        resumed_b_path,
        visit=resumed_b_visit,
        current_step_config_digest=resumed_b_binding.step_config_digest,
    )
    assert incomplete is not None and incomplete.stage == "launched"
    assert resumed_b_binding.workspace_path.is_dir()
    assert sum(
        row.stage == "launched" and row.status == "in_progress"
        for row in load_attempt_ledger(resumed_b_path).rows
    ) == 1
    shutil.rmtree(resumed_b_binding.workspace_path)
    assert not resumed_b_binding.workspace_path.exists()
    record_discarded_attempt(
        resumed_b_path,
        visit=resumed_b_visit,
        attempt_ordinal=1,
        workspace_path=resumed_b_binding.workspace_path,
        disposition_digest=_digest("1"),
    )
    retry_binding = replace(
        resumed_b_binding,
        workspace_path=(
            resumed_b_binding.run_ref_root / "runs" / "resumed-b" / "2" / "workspace"
        ),
        child_run_id="trial-parent--resumed-b--2",
    )
    retry = allocate_attempt(
        resumed_b_path,
        visit=resumed_b_visit,
        bindings=retry_binding,
    )
    assert retry.attempt_ordinal == 2
    resumed_b_authority = _build_e1_envelope_authority(
        tmp_path,
        label="resumed-b-retry",
        bindings=retry_binding,
        ordinal=2,
    )
    pending = _advance_transitions(
        resumed_b_path,
        visit=resumed_b_visit,
        ordinal=2,
        transitions=_settlement_transitions(resumed_b_authority),
    )
    resumed_b_settlement = settled_result_binding(pending)
    reconcile_pending_parent_commit(
        resumed_b_path,
        settled_result=resumed_b_settlement,
        current_step_config_digest=retry_binding.step_config_digest,
        validate_bound_authority=_authority_validator(resumed_b_authority),
    )

    clean_facts = (
        _DurableCellFact("a", 1, 1, clean_a_settlement.pending_row_digest, 0.7),
        _DurableCellFact("b", 1, 1, clean_b_settlement.pending_row_digest, 0.6),
    )
    resumed_facts = (
        _DurableCellFact("a", 1, 1, resumed_a_settlement.pending_row_digest, 0.7),
        _DurableCellFact("b", 1, 2, resumed_b_settlement.pending_row_digest, 0.6),
    )
    assert _transient_view(clean_facts) == _transient_view(resumed_facts)
    forbidden_derived_keys = {
        "authored_order",
        "median",
        "ranking",
        "cache",
        "memo",
        "memo_key",
        "derived_value",
    }
    durable_keys, _ = _mapping_keys_and_scalar_values(
        [asdict(fact) for fact in resumed_facts]
    )
    assert durable_keys.isdisjoint(forbidden_derived_keys)
    resumed_b_rows = load_attempt_ledger(resumed_b_path).rows
    assert any(row.attempt_ordinal == 1 and row.status == "discarded" for row in resumed_b_rows)
    assert any(row.attempt_ordinal == 2 and row.status == "committed" for row in resumed_b_rows)
    assert sum(
        row.stage == "launched" and row.status == "in_progress"
        for row in resumed_b_rows
    ) == 2

    witness = PureReplayVisitWitness(
        presentation_key="trial-score-view",
        step_index=1,
        step_id="root.trial-score-view",
        visit_count=1,
    )
    shell = build_pure_completion_shell(witness)
    validate_pure_completion_shell(shell, witness=witness)
    shell_keys, _ = _mapping_keys_and_scalar_values(shell)
    assert shell_keys.isdisjoint(
        forbidden_derived_keys | {"value", "result", "output", "outputs"}
    )


@pytest.mark.parametrize(
    ("definition", "name", "descriptor"),
    (
        (
            ("  (defrecord NestedPayload", "    (value String))"),
            "NestedPayload",
            {
                "kind": "record",
                "name": "NestedPayload",
                "fields": [
                    {
                        "name": "value",
                        "type": {"kind": "primitive", "name": "String"},
                    }
                ],
            },
        ),
        (
            (
                "  (defunion NestedPayload",
                "    (VALUE",
                "      (value String)))",
            ),
            "NestedPayload",
            {
                "kind": "union",
                "name": "NestedPayload",
                "variants": [
                    {
                        "name": "VALUE",
                        "fields": [
                            {
                                "name": "value",
                                "type": {"kind": "primitive", "name": "String"},
                            }
                        ],
                    }
                ],
            },
        ),
    ),
)
def test_target_224_rejects_record_and_union_elements_below_list(
    tmp_path: Path,
    definition: tuple[str, ...],
    name: str,
    descriptor: dict[str, Any],
) -> None:
    workflow_path = tmp_path / "nested_transport_rejection.orc"
    workflow_path.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.24")',
                *definition,
                "  (defrecord InvalidResult",
                f"    (payloads List[{name}]))",
                "  (defrecord WorkflowOutput",
                "    (report String))",
                "  (defworkflow orchestrate",
                "    ()",
                "    -> WorkflowOutput",
                "    (let* ((result",
                "             (provider-result providers.execute",
                "               :prompt prompts.execute",
                "               :inputs ()",
                "               :returns InvalidResult)))",
                '      (record WorkflowOutput :report "ok"))))',
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            workflow_path,
            provider_externs={"providers.execute": "fake"},
            prompt_externs={"prompts.execute": "prompts/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "collection_element_type_unsupported"
    assert not is_transportable_type_descriptor(
        {"kind": "list", "item": descriptor}
    )
