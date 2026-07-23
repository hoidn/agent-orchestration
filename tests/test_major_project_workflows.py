import json
from pathlib import Path

from workflows.library.scripts.major_project_scope_boundary import (
    check_completion,
    write_scope_boundary,
)


def test_neurips_execute_prompt_treats_partial_progress_as_reviewable_pass():
    prompt = Path(
        "workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md"
    ).read_text(encoding="utf-8")

    assert "Choose exactly one implementation state" not in prompt
    assert "write the execution report" in prompt
    assert "partial" in prompt.lower()
    assert "Remaining Required Plan Tasks" in prompt
    assert "Blocker Class" in prompt


def test_scope_boundary_helper_derives_selected_tranche_boundary(tmp_path: Path):
    manifest_path = tmp_path / "state/demo/tranche_manifest.json"
    brief_path = tmp_path / "docs/backlog/generated/demo/t1.md"
    boundary_path = tmp_path / "state/demo/items/t1/scope_boundary.json"
    manifest_path.parent.mkdir(parents=True)
    brief_path.parent.mkdir(parents=True)
    brief_path.write_text(
        "# T1 brief\nImplement the public behavior.\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "project_id": "demo",
                "project_brief_path": "docs/backlog/demo.md",
                "project_roadmap_path": "docs/plans/demo.md",
                "tranches": [
                    {
                        "tranche_id": "T1-public-behavior",
                        "title": "Public behavior",
                        "brief_path": brief_path.relative_to(tmp_path).as_posix(),
                        "completion_gate": "implementation_approved",
                        "status": "pending",
                        "prerequisites": [],
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = write_scope_boundary(
        root=tmp_path,
        tranche_manifest_path=manifest_path.relative_to(tmp_path).as_posix(),
        tranche_brief_path=brief_path.relative_to(tmp_path).as_posix(),
        scope_boundary_path=boundary_path.relative_to(tmp_path).as_posix(),
    )

    assert payload["tranche_id"] == "T1-public-behavior"
    assert payload["completion_gate"] == "implementation_approved"
    assert payload["required_deliverables"]
    assert boundary_path.is_file()


def test_completion_guard_rejects_approved_slice_with_unapproved_deferred_work(
    tmp_path: Path,
):
    boundary = tmp_path / "state/demo/items/t1/scope_boundary.json"
    execution_report = tmp_path / "artifacts/work/demo/execution.md"
    review_report = tmp_path / "artifacts/review/demo/review.md"
    for path in (boundary, execution_report, review_report):
        path.parent.mkdir(parents=True, exist_ok=True)
    boundary.write_text(
        json.dumps(
            {
                "tranche_id": "T1",
                "required_deliverables": ["public solver"],
                "required_evidence": [],
                "authorized_deferred_work": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    execution_report.write_text(
        "Task 3 is done. Exact public solver work remains deferred and blocked.\n",
        encoding="utf-8",
    )
    review_report.write_text(
        "Decision: APPROVE\nBroader exact-runtime blockers remain deferred.\n",
        encoding="utf-8",
    )

    result = check_completion(
        root=tmp_path,
        scope_boundary_path=boundary.relative_to(tmp_path).as_posix(),
        implementation_decision="APPROVE",
        execution_report_path=execution_report.relative_to(tmp_path).as_posix(),
        implementation_review_report_path=review_report.relative_to(tmp_path).as_posix(),
    )

    assert result["completion_status"] == "SCOPE_MISMATCH"
    assert result["recommended_route"] == "escalate_roadmap_revision"


def test_completion_guard_allows_roadmap_authorized_deferral(tmp_path: Path):
    boundary = tmp_path / "state/demo/items/t1/scope_boundary.json"
    execution_report = tmp_path / "artifacts/work/demo/execution.md"
    review_report = tmp_path / "artifacts/review/demo/review.md"
    for path in (boundary, execution_report, review_report):
        path.parent.mkdir(parents=True, exist_ok=True)
    boundary.write_text(
        json.dumps(
            {
                "tranche_id": "T1",
                "required_deliverables": ["public solver"],
                "required_evidence": [],
                "authorized_deferred_work": [
                    {
                        "work": "CUDA promotion",
                        "authority": "roadmap",
                        "handoff": "T1A",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    execution_report.write_text(
        "CPU work complete. CUDA promotion remains deferred to T1A.\n",
        encoding="utf-8",
    )
    review_report.write_text("Decision: APPROVE\n", encoding="utf-8")

    result = check_completion(
        root=tmp_path,
        scope_boundary_path=boundary.relative_to(tmp_path).as_posix(),
        implementation_decision="APPROVE",
        execution_report_path=execution_report.relative_to(tmp_path).as_posix(),
        implementation_review_report_path=review_report.relative_to(tmp_path).as_posix(),
    )

    assert result["completion_status"] == "COMPLETE"
    assert result["recommended_route"] == "complete"
