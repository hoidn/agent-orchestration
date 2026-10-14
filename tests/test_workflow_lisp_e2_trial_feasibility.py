from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
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
from orchestrator.workflow.run_ref.contracts import (
    RepositoryRevisionId,
    SetupPolicy,
    authored_setup_identity,
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.delta import DeclaredArtifact, build_workspace_delta
from orchestrator.workflow.run_ref.ledger import RunRefAttemptBindings
from orchestrator.workflow.run_ref.runtime import build_run_ref_accounting
from orchestrator.workflow.run_ref.workspace import TreeManifest, freeze_tree


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
