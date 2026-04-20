import json
from pathlib import Path

import pytest

from orchestrator.workflow.adjudication import (
    EvidencePacketError,
    EvaluatorOutputError,
    LedgerConflictError,
    build_evaluation_packet,
    generate_score_ledger_rows,
    materialize_score_ledger_mirror,
    parse_evaluator_output,
    select_candidate,
    scorer_identity_hash,
)


def test_scorer_identity_hash_changes_when_contract_inputs_change() -> None:
    base = {
        "evaluator_provider": "fake",
        "evaluator_params": {"model": "m1"},
        "evaluator_prompt_hash": "sha256:prompt",
        "rubric_hash": None,
        "evidence_limits": {"max_item_bytes": 10, "max_packet_bytes": 100},
        "evidence_confidentiality": "same_trust_boundary",
    }

    original = scorer_identity_hash(base)
    changed = scorer_identity_hash({**base, "evaluator_params": {"model": "m2"}})

    assert original.startswith("sha256:")
    assert changed != original


def test_build_evaluation_packet_embeds_complete_text_evidence(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "docs").mkdir()
    (candidate / "state/result_path.txt").write_text("docs/result.md\n", encoding="utf-8")
    (candidate / "docs/result.md").write_text("complete result\n", encoding="utf-8")

    packet = build_evaluation_packet(
        candidate_id="a",
        candidate_workspace=candidate,
        rendered_prompt="Write the artifact.",
        expected_outputs=[
            {
                "name": "result_path",
                "path": "state/result_path.txt",
                "type": "relpath",
                "must_exist_target": True,
            }
        ],
        output_bundle=None,
        artifacts={"result_path": "docs/result.md"},
        scorer={"scorer_identity_hash": "sha256:scorer"},
        evidence_limits={"max_item_bytes": 1024, "max_packet_bytes": 4096},
        workflow_secret_values=[],
    )

    assert packet["candidate_id"] == "a"
    assert packet["evaluation_packet_hash"].startswith("sha256:")
    contents = {item["name"]: item["content"] for item in packet["evidence_items"]}
    assert contents["candidate_prompt"] == "Write the artifact."
    assert contents["result_path.value_file"] == "docs/result.md\n"
    assert contents["result_path.target"] == "complete result\n"


@pytest.mark.parametrize(
    ("content", "limits", "secrets", "failure_type"),
    [
        ("too long", {"max_item_bytes": 3, "max_packet_bytes": 100}, [], "evidence_item_too_large"),
        ("secret text", {"max_item_bytes": 100, "max_packet_bytes": 100}, ["secret"], "secret_detected_in_score_evidence"),
    ],
)
def test_build_evaluation_packet_rejects_incomplete_or_secret_evidence(
    tmp_path: Path,
    content: str,
    limits: dict,
    secrets: list[str],
    failure_type: str,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "state/result.txt").write_text(content, encoding="utf-8")

    with pytest.raises(EvidencePacketError) as exc_info:
        build_evaluation_packet(
            candidate_id="a",
            candidate_workspace=candidate,
            rendered_prompt="Prompt",
            expected_outputs=[{"name": "result", "path": "state/result.txt", "type": "string"}],
            output_bundle=None,
            artifacts={"result": content},
            scorer={"scorer_identity_hash": "sha256:scorer"},
            evidence_limits=limits,
            workflow_secret_values=secrets,
        )

    assert exc_info.value.failure_type == failure_type


@pytest.mark.parametrize(
    "stdout",
    [
        b"[]",
        b'{"candidate_id":"b","score":0.5,"summary":"ok"}',
        b'{"candidate_id":"a","score":"0.5","summary":"ok"}',
        b'{"candidate_id":"a","score":2,"summary":"ok"}',
        b'{"candidate_id":"a","score":NaN,"summary":"ok"}',
        b'{"candidate_id":"a","score":0.5,"summary":""}',
        b'{"candidate_id":"a","score":0.5,"summary":"ok"} trailing',
    ],
)
def test_parse_evaluator_output_rejects_non_strict_score_json(stdout: bytes) -> None:
    with pytest.raises(EvaluatorOutputError):
        parse_evaluator_output(stdout, expected_candidate_id="a")


def test_parse_evaluator_output_accepts_strict_json() -> None:
    parsed = parse_evaluator_output(
        b'{"candidate_id":"a","score":0.75,"summary":"strong"}',
        expected_candidate_id="a",
    )

    assert parsed == {"candidate_id": "a", "score": 0.75, "summary": "strong"}


def test_selection_rules_cover_single_optional_multi_partial_and_ties() -> None:
    no_valid = select_candidate([], require_score_for_single_candidate=False)
    assert no_valid.error_type == "adjudication_no_valid_candidates"

    single = select_candidate(
        [{"candidate_id": "a", "candidate_status": "output_valid", "score_status": "evaluation_failed"}],
        require_score_for_single_candidate=False,
    )
    assert single.selected_candidate_id == "a"
    assert single.selection_reason == "single_candidate_contract_valid"

    required = select_candidate(
        [{"candidate_id": "a", "candidate_status": "output_valid", "score_status": "evaluation_failed"}],
        require_score_for_single_candidate=True,
    )
    assert required.error_type == "adjudication_partial_scoring_failed"

    partial = select_candidate(
        [
            {"candidate_id": "a", "candidate_status": "output_valid", "score_status": "scored", "score": 0.8},
            {"candidate_id": "b", "candidate_status": "output_valid", "score_status": "evaluation_failed"},
        ],
        require_score_for_single_candidate=False,
    )
    assert partial.error_type == "adjudication_partial_scoring_failed"

    tie = select_candidate(
        [
            {"candidate_id": "a", "candidate_status": "output_valid", "score_status": "scored", "score": 0.9},
            {"candidate_id": "b", "candidate_status": "output_valid", "score_status": "scored", "score": 0.9},
        ],
        require_score_for_single_candidate=False,
    )
    assert tie.selected_candidate_id == "a"
    assert tie.selection_reason == "candidate_order_tie_break"


def test_ledger_rows_are_one_per_candidate_and_mirror_checks_owner(tmp_path: Path) -> None:
    rows = generate_score_ledger_rows(
        run_id="run-1",
        workflow_file="workflow.yaml",
        workflow_checksum="sha256:wf",
        dsl_version="2.11",
        execution_frame_id="root",
        call_frame_id=None,
        step_id="root.draft",
        step_name="Draft",
        visit_count=1,
        candidates=[
            {"candidate_id": "a", "candidate_index": 0, "candidate_status": "output_valid", "score_status": "scored", "score": 0.8, "summary": "ok"},
            {"candidate_id": "b", "candidate_index": 1, "candidate_status": "contract_failed", "score_status": "not_evaluated"},
        ],
        selected_candidate_id="a",
        selection_reason="highest_score",
        promotion_status="committed",
        promoted_paths={"result": "state/result.txt"},
    )

    assert len(rows) == 2
    assert rows[0]["row_schema"] == "adjudicated_provider.score.v1"
    assert rows[0]["selected"] is True
    assert rows[0]["candidate_run_key"].startswith("sha256:")
    assert rows[0]["score_run_key"].startswith("sha256:")

    mirror = tmp_path / "artifacts/scores.jsonl"
    materialize_score_ledger_mirror(rows, mirror)
    assert len(mirror.read_text(encoding="utf-8").splitlines()) == 2

    mirror.write_text(json.dumps({**rows[0], "run_id": "other"}) + "\n", encoding="utf-8")
    with pytest.raises(LedgerConflictError):
        materialize_score_ledger_mirror(rows, mirror)
