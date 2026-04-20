import json
from hashlib import sha256
from pathlib import Path

import pytest

import orchestrator.workflow.adjudication as adjudication
from orchestrator.contracts.output_contract import ContractViolation, OutputContractError
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


def test_promotes_relpath_bare_basename_normalized_under_root(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "docs/plans").mkdir(parents=True)
    (candidate / "state/design_path.txt").write_text("demo-design.md\n", encoding="utf-8")
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
        selected_candidate_id="candidate_a",
    )

    assert (parent / "state/design_path.txt").read_text(encoding="utf-8") == "demo-design.md\n"
    assert (parent / "docs/plans/demo-design.md").read_text(encoding="utf-8") == "selected\n"
    assert result.promoted_paths["design_path.target"] == "docs/plans/demo-design.md"
    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["selected_candidate_id"] == "candidate_a"


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


def test_promotes_output_bundle_bare_basename_normalized_under_root(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "docs/plans").mkdir(parents=True)
    (candidate / "state/bundle.json").write_text(
        json.dumps({"design_path": "bundle-design.md"}),
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
        selected_candidate_id="candidate_a",
    )

    assert (parent / "state/bundle.json").exists()
    assert (parent / "docs/plans/bundle-design.md").read_text(encoding="utf-8") == "bundle selected\n"
    assert result.promoted_paths["design_path.target"] == "docs/plans/bundle-design.md"
    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["selected_candidate_id"] == "candidate_a"


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


def test_promotion_records_file_and_absent_preimages_and_rejects_unavailable(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (parent / "state").mkdir()
    (parent / "state/existing.txt").write_text("baseline\n", encoding="utf-8")
    (candidate / "state").mkdir()
    (candidate / "state/existing.txt").write_text("selected existing\n", encoding="utf-8")
    (candidate / "state/new.txt").write_text("selected new\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)

    promote_candidate_outputs(
        expected_outputs=[
            {"name": "existing", "path": "state/existing.txt", "type": "string"},
            {"name": "new", "path": "state/new.txt", "type": "string"},
        ],
        output_bundle=None,
        candidate_workspace=candidate,
        parent_workspace=parent,
        baseline_manifest=manifest,
        promotion_manifest_path=visit.promotion_manifest_path,
    )

    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    preimages = {entry["dest_rel"]: entry["baseline_preimage"]["state"] for entry in manifest_doc["files"]}
    assert preimages == {
        "state/existing.txt": "file",
        "state/new.txt": "absent",
    }

    blocked_parent = tmp_path / "blocked-parent"
    blocked_candidate = tmp_path / "blocked-candidate"
    blocked_parent.mkdir()
    blocked_candidate.mkdir()
    (blocked_parent / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (blocked_candidate / ".env").mkdir()
    (blocked_candidate / ".env/result.txt").write_text("selected\n", encoding="utf-8")
    blocked_visit, blocked_manifest = _baseline(tmp_path / "blocked", blocked_parent)

    with pytest.raises(PromotionConflictError) as exc_info:
        promote_candidate_outputs(
            expected_outputs=[
                {"name": "result", "path": ".env/result.txt", "type": "string"},
            ],
            output_bundle=None,
            candidate_workspace=blocked_candidate,
            parent_workspace=blocked_parent,
            baseline_manifest=blocked_manifest,
            promotion_manifest_path=blocked_visit.promotion_manifest_path,
        )

    assert exc_info.value.failure_type == "promotion_conflict"
    assert not (blocked_parent / ".env/result.txt").exists()


def test_promotion_rejects_destination_directory_removed_after_baseline(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (parent / "state/result.txt").mkdir(parents=True)
    visit, manifest = _baseline(tmp_path, parent)
    (parent / "state/result.txt").rmdir()
    (candidate / "state").mkdir()
    (candidate / "state/result.txt").write_text("selected\n", encoding="utf-8")

    with pytest.raises(PromotionConflictError) as exc_info:
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

    assert exc_info.value.failure_type == "promotion_conflict"
    assert not (parent / "state/result.txt").exists()


def test_promotion_rejects_duplicate_destination_with_different_roles(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "state/dup.txt").write_text("state/dup.txt\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)

    with pytest.raises(PromotionConflictError) as exc_info:
        promote_candidate_outputs(
            expected_outputs=[
                {
                    "name": "dup",
                    "path": "state/dup.txt",
                    "type": "relpath",
                    "must_exist_target": True,
                },
            ],
            output_bundle=None,
            candidate_workspace=candidate,
            parent_workspace=parent,
            baseline_manifest=manifest,
            promotion_manifest_path=visit.promotion_manifest_path,
        )

    assert "duplicate promotion destination" in str(exc_info.value)
    assert not (parent / "state/dup.txt").exists()


def test_promotion_detects_parent_change_between_staging_and_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "state/result.txt").write_text("selected\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)

    def mutate_parent_after_staging(expected_outputs, output_bundle, workspace):
        del expected_outputs, output_bundle, workspace
        (parent / "state").mkdir(parents=True, exist_ok=True)
        (parent / "state/result.txt").write_text("concurrent\n", encoding="utf-8")

    monkeypatch.setattr(adjudication, "_validate_promotion_staging", mutate_parent_after_staging)

    with pytest.raises(PromotionConflictError) as exc_info:
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

    assert exc_info.value.failure_type == "promotion_conflict"
    assert (parent / "state/result.txt").read_text(encoding="utf-8") == "concurrent\n"


def test_promotion_rollback_removes_only_manifest_created_empty_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state/nested").mkdir(parents=True)
    (candidate / "state/nested/result.txt").write_text("selected\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)

    def fail_parent_validation(expected_outputs, output_bundle, workspace):
        del expected_outputs, output_bundle, workspace
        raise OutputContractError(
            [
                ContractViolation(
                    type="forced_failure",
                    message="validation failed after commit",
                    context={"path": "state/nested/result.txt"},
                )
            ]
        )

    monkeypatch.setattr(adjudication, "_validate_promotion_parent", fail_parent_validation, raising=False)

    with pytest.raises(PromotionConflictError) as exc_info:
        promote_candidate_outputs(
            expected_outputs=[
                {"name": "result", "path": "state/nested/result.txt", "type": "string"},
            ],
            output_bundle=None,
            candidate_workspace=candidate,
            parent_workspace=parent,
            baseline_manifest=manifest,
            promotion_manifest_path=visit.promotion_manifest_path,
        )

    assert exc_info.value.failure_type == "promotion_validation_failed"
    assert not (parent / "state/nested/result.txt").exists()
    assert not (parent / "state/nested").exists()
    assert not (parent / "state").exists()
    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["status"] == "failed"


def test_promotion_rollback_conflict_preserves_concurrent_parent_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "state/result.txt").write_text("selected\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)

    def fail_after_concurrent_change(expected_outputs, output_bundle, workspace):
        del expected_outputs, output_bundle
        (workspace / "state/result.txt").write_text("concurrent\n", encoding="utf-8")
        raise OutputContractError(
            [
                ContractViolation(
                    type="forced_failure",
                    message="validation failed after concurrent write",
                    context={"path": "state/result.txt"},
                )
            ]
        )

    monkeypatch.setattr(adjudication, "_validate_promotion_parent", fail_after_concurrent_change)

    with pytest.raises(PromotionConflictError) as exc_info:
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

    assert exc_info.value.failure_type == "promotion_rollback_conflict"
    assert (parent / "state/result.txt").read_text(encoding="utf-8") == "concurrent\n"
    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["status"] == "rolling_back"
    assert manifest_doc["failure_type"] == "promotion_rollback_conflict"


def _hash_text(text: str) -> str:
    return f"sha256:{sha256(text.encode('utf-8')).hexdigest()}"


def _write_resume_manifest(
    manifest_path: Path,
    *,
    status: str,
    dest_rel: str = "state/result.txt",
    source_text: str = "selected\n",
    baseline_preimage: dict | None = None,
    failure_type: str | None = None,
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    source = manifest_path.parent / "candidate-source" / dest_rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(source_text, encoding="utf-8")
    payload = {
        "schema": "adjudicated_provider.promotion.v1",
        "status": status,
        "files": [
            {
                "role": "value_file",
                "artifact": "result",
                "source": source.as_posix(),
                "dest_rel": dest_rel,
                "source_sha256": _hash_text(source_text),
                "baseline_preimage": baseline_preimage or {"state": "absent"},
                "current_preimage": baseline_preimage or {"state": "absent"},
            }
        ],
        "promoted_paths": {"result": dest_rel},
        "created_parent_dirs": ["state"],
    }
    if failure_type is not None:
        payload["failure_type"] = failure_type
        payload["failure_message"] = "recorded failure"
    manifest_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_promotion_resumes_committing_manifest_without_candidate_workspace(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)
    _write_resume_manifest(visit.promotion_manifest_path, status="committing")
    staged = visit.promotion_manifest_path.parent / "staging/state/result.txt"
    staged.parent.mkdir(parents=True)
    staged.write_text("selected\n", encoding="utf-8")

    result = promote_candidate_outputs(
        expected_outputs=[{"name": "result", "path": "state/result.txt", "type": "string"}],
        output_bundle=None,
        candidate_workspace=tmp_path / "missing-candidate",
        parent_workspace=parent,
        baseline_manifest=_baseline(tmp_path, parent)[1],
        promotion_manifest_path=visit.promotion_manifest_path,
    )

    assert result.status == "committed"
    assert (parent / "state/result.txt").read_text(encoding="utf-8") == "selected\n"
    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["status"] == "committed"


def test_promotion_resumes_committing_manifest_when_destination_already_committed(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "state").mkdir()
    (parent / "state/result.txt").write_text("selected\n", encoding="utf-8")
    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)
    _write_resume_manifest(visit.promotion_manifest_path, status="committing")
    source = visit.promotion_manifest_path.parent / "candidate-source"
    for child in sorted(source.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    source.rmdir()

    result = promote_candidate_outputs(
        expected_outputs=[{"name": "result", "path": "state/result.txt", "type": "string"}],
        output_bundle=None,
        candidate_workspace=tmp_path / "missing-candidate",
        parent_workspace=parent,
        baseline_manifest=_baseline(tmp_path, parent)[1],
        promotion_manifest_path=visit.promotion_manifest_path,
    )

    assert result.status == "committed"
    assert (parent / "state/result.txt").read_text(encoding="utf-8") == "selected\n"


def test_promotion_resume_committed_manifest_revalidates_parent_outputs(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "state").mkdir()
    (parent / "state/result.txt").write_text("selected\n", encoding="utf-8")
    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)
    _write_resume_manifest(visit.promotion_manifest_path, status="committed")

    result = promote_candidate_outputs(
        expected_outputs=[{"name": "result", "path": "state/result.txt", "type": "string"}],
        output_bundle=None,
        candidate_workspace=tmp_path / "missing-candidate",
        parent_workspace=parent,
        baseline_manifest=_baseline(tmp_path, parent)[1],
        promotion_manifest_path=visit.promotion_manifest_path,
    )

    assert result.status == "committed"


def test_promotion_resume_failed_manifest_returns_recorded_failure(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)
    _write_resume_manifest(
        visit.promotion_manifest_path,
        status="failed",
        failure_type="promotion_validation_failed",
    )

    with pytest.raises(PromotionConflictError) as exc_info:
        promote_candidate_outputs(
            expected_outputs=[{"name": "result", "path": "state/result.txt", "type": "string"}],
            output_bundle=None,
            candidate_workspace=tmp_path / "missing-candidate",
            parent_workspace=parent,
            baseline_manifest=_baseline(tmp_path, parent)[1],
            promotion_manifest_path=visit.promotion_manifest_path,
        )

    assert exc_info.value.failure_type == "promotion_validation_failed"


def test_promotion_resume_rolling_back_completes_rollback_and_returns_failure(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "state").mkdir()
    (parent / "state/result.txt").write_text("selected\n", encoding="utf-8")
    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)
    _write_resume_manifest(
        visit.promotion_manifest_path,
        status="rolling_back",
        failure_type="promotion_validation_failed",
    )

    with pytest.raises(PromotionConflictError) as exc_info:
        promote_candidate_outputs(
            expected_outputs=[{"name": "result", "path": "state/result.txt", "type": "string"}],
            output_bundle=None,
            candidate_workspace=tmp_path / "missing-candidate",
            parent_workspace=parent,
            baseline_manifest=_baseline(tmp_path, parent)[1],
            promotion_manifest_path=visit.promotion_manifest_path,
        )

    assert exc_info.value.failure_type == "promotion_validation_failed"
    assert not (parent / "state/result.txt").exists()
    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["status"] == "failed"
