import json
from pathlib import Path

import pytest

from orchestrator.workflow.adjudication import (
    PromotionConflictError,
    adjudication_visit_paths,
    create_baseline_snapshot,
    promote_candidate_outputs,
)


def _baseline(tmp_path: Path, parent: Path):
    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)
    manifest = create_baseline_snapshot(
        parent_workspace=parent,
        run_root=tmp_path / ".orchestrate/runs/run-1",
        visit_paths=visit,
        workflow_checksum="sha256:test",
        resolved_consumes={},
        required_path_surfaces=[],
        optional_path_surfaces=[],
    )
    return visit, manifest


def test_promotes_relpath_pointer_and_required_target_transactionally(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "docs/plans").mkdir(parents=True)
    (candidate / "state/design_path.txt").write_text("docs/plans/demo-design.md\n", encoding="utf-8")
    (candidate / "docs/plans/demo-design.md").write_text("selected\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)

    result = promote_candidate_outputs(
        expected_outputs=[
            {
                "name": "design_path",
                "path": "state/design_path.txt",
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            }
        ],
        output_bundle=None,
        candidate_workspace=candidate,
        parent_workspace=parent,
        baseline_manifest=manifest,
        promotion_manifest_path=visit.promotion_manifest_path,
    )

    assert (parent / "state/design_path.txt").read_text(encoding="utf-8") == "docs/plans/demo-design.md\n"
    assert (parent / "docs/plans/demo-design.md").read_text(encoding="utf-8") == "selected\n"
    assert result.status == "committed"
    assert result.promoted_paths == {
        "design_path": "state/design_path.txt",
        "design_path.target": "docs/plans/demo-design.md",
    }
    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["status"] == "committed"


def test_promotes_output_bundle_and_required_relpath_target(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "docs/plans").mkdir(parents=True)
    (candidate / "state/bundle.json").write_text(
        json.dumps({"design_path": "docs/plans/bundle-design.md"}),
        encoding="utf-8",
    )
    (candidate / "docs/plans/bundle-design.md").write_text("bundle selected\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)

    result = promote_candidate_outputs(
        expected_outputs=None,
        output_bundle={
            "path": "state/bundle.json",
            "fields": [
                {
                    "name": "design_path",
                    "json_pointer": "/design_path",
                    "type": "relpath",
                    "under": "docs/plans",
                    "must_exist_target": True,
                }
            ],
        },
        candidate_workspace=candidate,
        parent_workspace=parent,
        baseline_manifest=manifest,
        promotion_manifest_path=visit.promotion_manifest_path,
    )

    assert (parent / "state/bundle.json").exists()
    assert (parent / "docs/plans/bundle-design.md").read_text(encoding="utf-8") == "bundle selected\n"
    assert result.promoted_paths["design_path.target"] == "docs/plans/bundle-design.md"


def test_promotion_detects_parent_preimage_conflict(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (parent / "state").mkdir()
    (parent / "state/result.txt").write_text("baseline\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)
    (parent / "state/result.txt").write_text("changed\n", encoding="utf-8")
    (candidate / "state").mkdir()
    (candidate / "state/result.txt").write_text("selected\n", encoding="utf-8")

    with pytest.raises(PromotionConflictError):
        promote_candidate_outputs(
            expected_outputs=[
                {"name": "result", "path": "state/result.txt", "type": "string"},
            ],
            output_bundle=None,
            candidate_workspace=candidate,
            parent_workspace=parent,
            baseline_manifest=manifest,
            promotion_manifest_path=visit.promotion_manifest_path,
        )

    assert (parent / "state/result.txt").read_text(encoding="utf-8") == "changed\n"
