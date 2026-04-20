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
        "evaluator_prompt_source_kind": "input_file",
        "evaluator_prompt_source": "evaluator.md",
        "evaluator_prompt_hash": "sha256:prompt",
        "rubric_source_kind": "input_file",
        "rubric_source": "rubric.md",
        "rubric_hash": None,
        "evidence_limits": {"max_item_bytes": 10, "max_packet_bytes": 100},
        "evidence_confidentiality": "same_trust_boundary",
    }

    original = scorer_identity_hash(base)
    changed = scorer_identity_hash({**base, "evaluator_params": {"model": "m2"}})
    changed_prompt_source = scorer_identity_hash({**base, "evaluator_prompt_source": "other-evaluator.md"})
    changed_rubric_source = scorer_identity_hash({**base, "rubric_source": "other-rubric.md"})

    assert original.startswith("sha256:")
    assert changed != original
    assert changed_prompt_source != original
    assert changed_rubric_source != original


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
    assert all(item["read_status"] == "embedded" for item in packet["evidence_items"])


def test_build_evaluation_packet_embeds_injected_consumed_relpath_targets(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "docs").mkdir()
    (candidate / "state/result.txt").write_text("complete result\n", encoding="utf-8")
    (candidate / "docs/source.md").write_text("consumed source\n", encoding="utf-8")

    packet = build_evaluation_packet(
        candidate_id="a",
        candidate_workspace=candidate,
        rendered_prompt="## Consumed Artifacts\n- source_doc: docs/source.md\nRead these files before acting.\n",
        expected_outputs=[{"name": "result", "path": "state/result.txt", "type": "string"}],
        output_bundle=None,
        artifacts={"result": "complete result"},
        scorer={"scorer_identity_hash": "sha256:scorer"},
        evidence_limits={"max_item_bytes": 1024, "max_packet_bytes": 4096},
        workflow_secret_values=[],
        consumed_artifacts={"source_doc": "docs/source.md"},
        consumed_relpath_targets={"source_doc": "docs/source.md"},
    )

    contents = {item["name"]: item["content"] for item in packet["evidence_items"]}
    assert contents["consume.source_doc.value"] == "docs/source.md"
    assert contents["consume.source_doc.target"] == "consumed source\n"
    assert packet["consumed_artifacts"] == {"source_doc": "docs/source.md"}


def test_consumed_relpath_target_evidence_is_score_critical(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "docs").mkdir()
    (candidate / "state/result.txt").write_text("complete result\n", encoding="utf-8")
    (candidate / "docs/source.md").write_text("token-secret\n", encoding="utf-8")

    with pytest.raises(EvidencePacketError) as exc_info:
        build_evaluation_packet(
            candidate_id="a",
            candidate_workspace=candidate,
            rendered_prompt="Prompt",
            expected_outputs=[{"name": "result", "path": "state/result.txt", "type": "string"}],
            output_bundle=None,
            artifacts={"result": "complete result"},
            scorer={"scorer_identity_hash": "sha256:scorer"},
            evidence_limits={"max_item_bytes": 1024, "max_packet_bytes": 4096},
            workflow_secret_values=["token-secret"],
            consumed_artifacts={"source_doc": "docs/source.md"},
            consumed_relpath_targets={"source_doc": "docs/source.md"},
        )

    assert exc_info.value.failure_type == "secret_detected_in_score_evidence"


def test_evaluation_packet_records_scorer_candidate_and_prompt_metadata(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "state/result.txt").write_text("complete result\n", encoding="utf-8")

    packet = build_evaluation_packet(
        candidate_id="a",
        candidate_workspace=candidate,
        rendered_prompt="Write the artifact.",
        expected_outputs=[{"name": "result", "path": "state/result.txt", "type": "string"}],
        output_bundle=None,
        artifacts={"result": "complete result"},
        scorer={
            "scorer_identity_hash": "sha256:scorer",
            "evaluator_provider": "fake_eval",
            "evaluator_model": "eval-model",
            "evaluator_params_hash": "sha256:eval-params",
            "evaluator_prompt_source_kind": "input_file",
            "evaluator_prompt_source": "evaluator.md",
            "evaluator_prompt_hash": "sha256:evaluator-prompt",
            "rubric_source_kind": None,
            "rubric_source": None,
            "rubric_hash": None,
        },
        evidence_limits={"max_item_bytes": 1024, "max_packet_bytes": 4096},
        workflow_secret_values=[],
        candidate_metadata={
            "candidate_provider": "fake_candidate",
            "candidate_model": "candidate-model",
            "candidate_params_hash": "sha256:candidate-params",
            "candidate_index": 0,
            "prompt_variant_id": "input_file:evaluator.md:sha256:prompt",
        },
        prompt_metadata={
            "prompt_source_kind": "input_file",
            "prompt_source": "prompt.md",
            "composed_prompt_hash": "sha256:prompt",
        },
    )

    assert packet["scorer"]["evaluator_provider"] == "fake_eval"
    assert packet["candidate"]["candidate_provider"] == "fake_candidate"
    assert packet["candidate"]["candidate_index"] == 0
    assert packet["prompt"]["prompt_source"] == "prompt.md"
    assert packet["artifacts"] == {"result": "complete result"}
    assert packet["evidence_valid"] is True
    assert packet["evidence_invalid_reasons"] == []


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

    later_tie = select_candidate(
        [
            {"candidate_id": "a", "candidate_status": "output_valid", "score_status": "scored", "score": 0.8},
            {"candidate_id": "b", "candidate_status": "output_valid", "score_status": "scored", "score": 0.9},
            {"candidate_id": "c", "candidate_status": "output_valid", "score_status": "scored", "score": 0.9},
        ],
        require_score_for_single_candidate=False,
    )
    assert later_tie.selected_candidate_id == "b"
    assert later_tie.selection_reason == "candidate_order_tie_break"


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


def test_ledger_mirror_requires_complete_owner_tuple(tmp_path: Path) -> None:
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
            {"candidate_id": "a", "candidate_index": 0, "candidate_status": "output_valid", "score_status": "scored", "score": 0.8},
        ],
        selected_candidate_id="a",
        selection_reason="highest_score",
        promotion_status="committed",
        promoted_paths={"result": "state/result.txt"},
    )

    mirror = tmp_path / "artifacts/scores.jsonl"
    mirror.parent.mkdir(parents=True)
    mirror.write_text(
        json.dumps(
            {
                "row_schema": "adjudicated_provider.score.v1",
                "run_id": "run-1",
                "execution_frame_id": "root",
                "step_id": "root.draft",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LedgerConflictError):
        materialize_score_ledger_mirror(rows, mirror)


def test_score_run_key_ignores_nondeterministic_numeric_score() -> None:
    base_candidate = {
        "candidate_id": "a",
        "candidate_index": 0,
        "candidate_status": "output_valid",
        "score_status": "scored",
        "scorer_identity_hash": "sha256:scorer",
        "evaluation_packet_hash": "sha256:packet",
        "candidate_config_hash": "sha256:candidate",
        "composed_prompt_hash": "sha256:prompt",
        "summary": "ok",
    }

    first = generate_score_ledger_rows(
        run_id="run-1",
        workflow_file="workflow.yaml",
        workflow_checksum="sha256:wf",
        dsl_version="2.11",
        execution_frame_id="root",
        call_frame_id=None,
        step_id="root.draft",
        step_name="Draft",
        visit_count=1,
        candidates=[{**base_candidate, "score": 0.4}],
        selected_candidate_id="a",
        selection_reason="highest_score",
        promotion_status="committed",
        promoted_paths={"result": "state/result.txt"},
    )
    second = generate_score_ledger_rows(
        run_id="run-1",
        workflow_file="workflow.yaml",
        workflow_checksum="sha256:wf",
        dsl_version="2.11",
        execution_frame_id="root",
        call_frame_id=None,
        step_id="root.draft",
        step_name="Draft",
        visit_count=1,
        candidates=[{**base_candidate, "score": 0.9}],
        selected_candidate_id="a",
        selection_reason="highest_score",
        promotion_status="committed",
        promoted_paths={"result": "state/result.txt"},
    )

    assert first[0]["candidate_run_key"] == second[0]["candidate_run_key"]
    assert first[0]["score_run_key"] == second[0]["score_run_key"]


def test_scorer_unavailable_score_run_key_uses_resolution_failure_key() -> None:
    base_candidate = {
        "candidate_id": "a",
        "candidate_index": 0,
        "candidate_status": "output_valid",
        "score_status": "scorer_unavailable",
        "candidate_config_hash": "sha256:candidate",
        "composed_prompt_hash": "sha256:prompt",
        "failure_type": "evaluator_params_substitution_failed",
        "failure_message": "missing variable",
    }

    first = generate_score_ledger_rows(
        run_id="run-1",
        workflow_file="workflow.yaml",
        workflow_checksum="sha256:wf",
        dsl_version="2.11",
        execution_frame_id="root",
        call_frame_id=None,
        step_id="root.draft",
        step_name="Draft",
        visit_count=1,
        candidates=[{**base_candidate, "scorer_resolution_failure_key": "sha256:first"}],
        selected_candidate_id=None,
        selection_reason="none",
        promotion_status="not_selected",
        promoted_paths={},
    )
    second = generate_score_ledger_rows(
        run_id="run-1",
        workflow_file="workflow.yaml",
        workflow_checksum="sha256:wf",
        dsl_version="2.11",
        execution_frame_id="root",
        call_frame_id=None,
        step_id="root.draft",
        step_name="Draft",
        visit_count=1,
        candidates=[{**base_candidate, "scorer_resolution_failure_key": "sha256:second"}],
        selected_candidate_id=None,
        selection_reason="none",
        promotion_status="not_selected",
        promoted_paths={},
    )

    assert first[0]["score_run_key"] != second[0]["score_run_key"]
