import json
from pathlib import Path

import pytest

from workflows.library.scripts.update_major_project_tranche_manifest import update_manifest
from workflows.library.scripts.validate_major_project_tranche_manifest import validate_manifest


def _write_valid_project(tmp_path: Path) -> tuple[dict, str, str, str]:
    project_brief = "docs/backlog/project.md"
    project_roadmap = "docs/plans/project-roadmap.md"
    manifest_path = "state/project/tranche_manifest.json"
    tranche_brief = "docs/backlog/generated/project/tranche-a.md"

    for relpath, content in [
        (project_brief, "# Project\n"),
        (project_roadmap, "# Roadmap\n"),
        (tranche_brief, "# Tranche A\n"),
    ]:
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    manifest = {
        "project_id": "project",
        "project_brief_path": project_brief,
        "project_roadmap_path": project_roadmap,
        "tranches": [
            {
                "tranche_id": "tranche-a",
                "title": "Tranche A",
                "brief_path": tranche_brief,
                "design_target_path": "docs/plans/project/tranche-a-design.md",
                "design_review_report_target_path": "artifacts/review/project/tranche-a-design-review.json",
                "plan_target_path": "docs/plans/project/tranche-a-plan.md",
                "plan_review_report_target_path": "artifacts/review/project/tranche-a-plan-review.json",
                "execution_report_target_path": "artifacts/work/project/tranche-a-execution-report.md",
                "implementation_review_report_target_path": "artifacts/review/project/tranche-a-implementation-review.md",
                "item_summary_target_path": "artifacts/work/project/tranche-a-summary.json",
                "prerequisites": [],
                "status": "pending",
                "design_depth": "big",
                "completion_gate": "implementation_approved",
            }
        ],
    }
    path = tmp_path / manifest_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest, project_brief, project_roadmap, manifest_path


def _validate(tmp_path: Path, project_brief: str, project_roadmap: str, manifest_path: str):
    return validate_manifest(
        root=tmp_path,
        project_brief_path=project_brief,
        project_roadmap_path=project_roadmap,
        tranche_manifest_path=manifest_path,
    )


def _rewrite_manifest(tmp_path: Path, manifest_path: str, manifest: dict) -> None:
    (tmp_path / manifest_path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_major_project_manifest_validator_accepts_valid_manifest(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)

    result = _validate(tmp_path, project_brief, project_roadmap, manifest_path)

    assert result.tranche_count == len(manifest["tranches"])
    assert result.ready_tranche_count == 1


def test_major_project_manifest_validator_excludes_incomplete_prerequisite_from_ready_count(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    tranche_b = dict(manifest["tranches"][0])
    tranche_b["tranche_id"] = "tranche-b"
    tranche_b["brief_path"] = "docs/backlog/generated/project/tranche-b.md"
    (tmp_path / tranche_b["brief_path"]).write_text("# Tranche B\n", encoding="utf-8")
    manifest["tranches"][0]["prerequisites"] = ["tranche-b"]
    tranche_b["prerequisites"] = []
    tranche_b["status"] = "pending"
    manifest["tranches"].append(tranche_b)
    _rewrite_manifest(tmp_path, manifest_path, manifest)

    result = _validate(tmp_path, project_brief, project_roadmap, manifest_path)

    assert result.tranche_count == 2
    assert result.ready_tranche_count == 1


def test_major_project_manifest_validator_rejects_duplicate_tranche_ids(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    manifest["tranches"].append(dict(manifest["tranches"][0]))
    _rewrite_manifest(tmp_path, manifest_path, manifest)

    with pytest.raises(ValueError, match="Duplicate tranche_id"):
        _validate(tmp_path, project_brief, project_roadmap, manifest_path)


def test_major_project_manifest_validator_rejects_unknown_prerequisites(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    manifest["tranches"][0]["prerequisites"] = ["missing-tranche"]
    _rewrite_manifest(tmp_path, manifest_path, manifest)

    with pytest.raises(ValueError, match="unknown prerequisites"):
        _validate(tmp_path, project_brief, project_roadmap, manifest_path)


def test_major_project_manifest_validator_rejects_cyclic_prerequisites(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    tranche_b = dict(manifest["tranches"][0])
    tranche_b["tranche_id"] = "tranche-b"
    tranche_b["brief_path"] = "docs/backlog/generated/project/tranche-b.md"
    (tmp_path / tranche_b["brief_path"]).write_text("# Tranche B\n", encoding="utf-8")
    manifest["tranches"][0]["prerequisites"] = ["tranche-b"]
    tranche_b["prerequisites"] = ["tranche-a"]
    manifest["tranches"].append(tranche_b)
    _rewrite_manifest(tmp_path, manifest_path, manifest)

    with pytest.raises(ValueError, match="cycle"):
        _validate(tmp_path, project_brief, project_roadmap, manifest_path)


def test_major_project_manifest_validator_rejects_path_escape(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    manifest["tranches"][0]["brief_path"] = "../outside.md"
    _rewrite_manifest(tmp_path, manifest_path, manifest)

    with pytest.raises(ValueError, match="escapes workspace"):
        _validate(tmp_path, project_brief, project_roadmap, manifest_path)


def test_major_project_manifest_validator_rejects_missing_brief(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    (tmp_path / manifest["tranches"][0]["brief_path"]).unlink()

    with pytest.raises(ValueError, match="brief_path target does not exist"):
        _validate(tmp_path, project_brief, project_roadmap, manifest_path)


def test_major_project_manifest_validator_rejects_bad_status(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    manifest["tranches"][0]["status"] = "maybe"
    _rewrite_manifest(tmp_path, manifest_path, manifest)

    with pytest.raises(ValueError, match="status"):
        _validate(tmp_path, project_brief, project_roadmap, manifest_path)


def test_major_project_manifest_validator_accepts_superseded_status(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    manifest["tranches"][0]["status"] = "superseded"
    _rewrite_manifest(tmp_path, manifest_path, manifest)

    result = _validate(tmp_path, project_brief, project_roadmap, manifest_path)

    assert result.tranche_count == 1
    assert result.ready_tranche_count == 0
    assert result.superseded_count == 1


def test_superseded_prerequisite_does_not_make_dependent_ready(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    tranche_b = dict(manifest["tranches"][0])
    tranche_b["tranche_id"] = "tranche-b"
    tranche_b["brief_path"] = "docs/backlog/generated/project/tranche-b.md"
    (tmp_path / tranche_b["brief_path"]).write_text("# Tranche B\n", encoding="utf-8")
    manifest["tranches"][0]["status"] = "superseded"
    tranche_b["prerequisites"] = ["tranche-a"]
    tranche_b["status"] = "pending"
    manifest["tranches"].append(tranche_b)
    _rewrite_manifest(tmp_path, manifest_path, manifest)

    result = _validate(tmp_path, project_brief, project_roadmap, manifest_path)

    assert result.ready_tranche_count == 0
    assert result.superseded_count == 1


def test_manifest_update_rejects_roadmap_escalation_without_revision_dispatch(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    item_root = "state/project/drain/items/project/tranche-a"
    selection_bundle = {
        "selected_tranche_id": "tranche-a",
        "item_state_root": item_root,
    }
    selection_path = tmp_path / "state/project/drain/selected-tranche.json"
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text(json.dumps(selection_bundle, indent=2) + "\n", encoding="utf-8")
    report_path = tmp_path / "artifacts/work/project/tranche-a-execution-report.md"
    summary_path = tmp_path / "artifacts/work/project/tranche-a-summary.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# report\n", encoding="utf-8")
    summary_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="roadmap-revision route"):
        update_manifest(
            root=tmp_path,
            selection_bundle_path=selection_path.relative_to(tmp_path).as_posix(),
            tranche_manifest_path=manifest_path,
            item_outcome="ESCALATE_ROADMAP_REVISION",
            execution_report_path=report_path.relative_to(tmp_path).as_posix(),
            item_summary_path=summary_path.relative_to(tmp_path).as_posix(),
        )

    assert json.loads((tmp_path / manifest_path).read_text(encoding="utf-8")) == manifest


def test_major_project_manifest_validator_rejects_bad_completion_gate(tmp_path: Path):
    manifest, project_brief, project_roadmap, manifest_path = _write_valid_project(tmp_path)
    manifest["tranches"][0]["completion_gate"] = "manual"
    _rewrite_manifest(tmp_path, manifest_path, manifest)

    with pytest.raises(ValueError, match="completion_gate"):
        _validate(tmp_path, project_brief, project_roadmap, manifest_path)
