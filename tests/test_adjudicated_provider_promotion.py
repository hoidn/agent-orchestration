import json
import shutil
from hashlib import sha256
from pathlib import Path

import pytest

import orchestrator.workflow.adjudication as adjudication
import orchestrator.workflow.executor as executor_module
from orchestrator.contracts.output_contract import ContractViolation, OutputContractError
from orchestrator.workflow.adjudication import (
    PromotionConflictError,
    adjudication_visit_paths,
    create_baseline_snapshot,
    promote_candidate_outputs,
)
from orchestrator.workflow.adjudication.promotion import (
    derive_promotion_rollback_authority,
    discard_partial_promotion_visit,
)
from tests.test_adjudicated_provider_runtime import _resume, _run, _workflow


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


def _write_discard_manifest(
    manifest_path: Path,
    *,
    status: str,
    baseline_text: str | None,
    selected_text: str = "selected\n",
) -> tuple[Path, Path, dict[str, object]]:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_rel = "state/result.txt"
    source = manifest_path.parent / "candidate-source" / dest_rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(selected_text, encoding="utf-8")
    baseline_preimage: dict[str, object]
    if baseline_text is None:
        baseline_preimage = {"state": "absent"}
    else:
        backup = manifest_path.parent / "backups" / dest_rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(baseline_text, encoding="utf-8")
        baseline_preimage = {
            "state": "file",
            "sha256": _hash_text(baseline_text),
            "mode": backup.stat().st_mode & 0o777,
        }
    payload = {
        "schema": "adjudicated_provider.promotion.v1",
        "status": status,
        "selected_candidate_id": "candidate-a",
        "files": [
            {
                "role": "value_file",
                "artifact": "result",
                "source": source.as_posix(),
                "dest_rel": dest_rel,
                "source_sha256": _hash_text(selected_text),
                "baseline_preimage": baseline_preimage,
                "current_preimage": baseline_preimage,
            }
        ],
        "promoted_paths": {"result": dest_rel},
        "created_parent_dirs": ["state"],
    }
    manifest_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    expected_rollback = {
        "selected_candidate_id": "candidate-a",
        "files": payload["files"],
        "promoted_paths": payload["promoted_paths"],
    }
    return source, manifest_path.parent / "backups" / dest_rel, expected_rollback


def test_discard_partial_promotion_visit_absent_root_is_noop(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"

    discard_partial_promotion_visit(
        parent_workspace=parent,
        promotion_manifest_path=manifest_path,
        expected_rollback={
            "selected_candidate_id": None,
            "files": [],
            "promoted_paths": {},
        },
    )

    assert not manifest_path.parent.exists()


def test_discard_prepared_promotion_verifies_preimages_before_removing_visit(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    destination = parent / "state/result.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("baseline\n", encoding="utf-8")
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    _, backup, expected_rollback = _write_discard_manifest(
        manifest_path,
        status="prepared",
        baseline_text="baseline\n",
    )
    backup.chmod(destination.stat().st_mode & 0o777)

    discard_partial_promotion_visit(
        parent_workspace=parent,
        promotion_manifest_path=manifest_path,
        expected_rollback=expected_rollback,
    )

    assert destination.read_text(encoding="utf-8") == "baseline\n"
    assert not manifest_path.parent.exists()


@pytest.mark.parametrize(
    "status",
    ["committing", "rolling_back", "failed", "committed"],
)
def test_discard_partial_promotion_visit_restores_parent_preimage_idempotently(
    tmp_path: Path,
    status: str,
) -> None:
    parent = tmp_path / "parent"
    destination = parent / "state/result.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("selected\n", encoding="utf-8")
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    _, backup, expected_rollback = _write_discard_manifest(
        manifest_path,
        status=status,
        baseline_text="baseline\n",
    )
    destination.chmod(backup.stat().st_mode & 0o777)

    discard_partial_promotion_visit(
        parent_workspace=parent,
        promotion_manifest_path=manifest_path,
        expected_rollback=expected_rollback,
    )
    discard_partial_promotion_visit(
        parent_workspace=parent,
        promotion_manifest_path=manifest_path,
        expected_rollback=expected_rollback,
    )

    assert destination.read_text(encoding="utf-8") == "baseline\n"
    assert not manifest_path.parent.exists()


def test_discard_partial_promotion_removes_file_with_absent_preimage(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    destination = parent / "state/result.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("selected\n", encoding="utf-8")
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    _, _, expected_rollback = _write_discard_manifest(
        manifest_path,
        status="committing",
        baseline_text=None,
    )

    discard_partial_promotion_visit(
        parent_workspace=parent,
        promotion_manifest_path=manifest_path,
        expected_rollback=expected_rollback,
    )

    assert not destination.exists()
    assert destination.parent.is_dir()
    assert not manifest_path.parent.exists()


def test_discard_partial_promotion_accepts_exact_baseline_before_source_hash(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    destination = parent / "state/result.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("same\n", encoding="utf-8")
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    _, _, expected_rollback = _write_discard_manifest(
        manifest_path,
        status="failed",
        baseline_text="same\n",
        selected_text="same\n",
    )
    shutil.rmtree(manifest_path.parent / "backups")

    discard_partial_promotion_visit(
        parent_workspace=parent,
        promotion_manifest_path=manifest_path,
        expected_rollback=expected_rollback,
    )

    assert destination.read_text(encoding="utf-8") == "same\n"
    assert not manifest_path.parent.exists()


def test_discarded_visit_cannot_become_publication_or_lineage_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator_attempts = tmp_path / "evaluator_attempts.txt"
    workflow = _workflow()
    workflow["providers"]["evaluator"]["command"] = [
        "python",
        "-c",
        (
            "import json, sys\n"
            "from pathlib import Path\n"
            f"attempt_file = Path({evaluator_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "packet = json.loads(sys.stdin.read().split('Evaluator Packet:', 1)[1])\n"
            "old_scores = {'a': 0.9, 'b': 0.1}\n"
            "new_scores = {'a': 0.1, 'b': 0.9}\n"
            "scores = old_scores if attempt <= 2 else new_scores\n"
            "print(json.dumps({'candidate_id': packet['candidate_id'], 'score': scores[packet['candidate_id']], 'summary': 'scored'}))\n"
        ),
    ]
    original_promote = executor_module.promote_candidate_outputs

    def interrupt_after_committed_promotion(**kwargs: object) -> object:
        promotion = original_promote(**kwargs)
        assert promotion.status == "committed"
        raise SystemExit("interrupted after discarded visit promotion")

    monkeypatch.setattr(
        executor_module,
        "promote_candidate_outputs",
        interrupt_after_committed_promotion,
    )
    with pytest.raises(SystemExit):
        _run(tmp_path, workflow)

    run_root = tmp_path / ".orchestrate/runs/run-1"
    discarded_visit = adjudication_visit_paths(
        run_root,
        "root",
        "root.draft",
        1,
    )
    discarded_rows = [
        json.loads(line)
        for line in discarded_visit.run_score_ledger_path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    discarded_manifest = json.loads(
        discarded_visit.promotion_manifest_path.read_text(encoding="utf-8")
    )
    discarded_keys = {
        row[key]
        for row in discarded_rows
        for key in ("candidate_run_key", "score_run_key")
    }
    assert discarded_manifest["selected_candidate_id"] == "a"
    assert next(row for row in discarded_rows if row["selected"])["candidate_id"] == "a"
    assert (tmp_path / "state/result_path.txt").read_text(
        encoding="utf-8"
    ) == "docs/plans/a.md\n"

    (tmp_path / "evaluator.md").write_text(
        "Use the replacement scoring identity.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        executor_module,
        "promote_candidate_outputs",
        original_promote,
    )
    state = _resume(tmp_path, workflow)

    replacement_visit = adjudication_visit_paths(
        run_root,
        "root",
        "root.draft",
        2,
    )
    replacement_rows = [
        json.loads(line)
        for line in replacement_visit.run_score_ledger_path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    replacement_manifest = json.loads(
        replacement_visit.promotion_manifest_path.read_text(encoding="utf-8")
    )
    published_score_rows = [
        json.loads(line)
        for line in (
            tmp_path / "artifacts/evaluations/draft_scores.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    result = state["steps"]["Draft"]

    assert state["status"] == "completed"
    assert result["visit_count"] == 2
    assert result["artifacts"]["result_path"] == "docs/plans/b.md"
    assert result["adjudication"]["selected_candidate_id"] == "b"
    assert result["adjudication"]["selected_score"] == 0.9
    assert (
        result["adjudication"]["run_score_ledger_path"]
        == replacement_visit.run_score_ledger_path.as_posix()
    )
    assert (
        result["adjudication"]["promotion_manifest_path"]
        == replacement_visit.promotion_manifest_path.as_posix()
    )
    published_versions = state["artifact_versions"]["result_path"]
    assert len(published_versions) == 1
    assert published_versions[0]["value"] == "docs/plans/b.md"
    assert not (tmp_path / "docs/plans/a.md").exists()
    assert (tmp_path / "docs/plans/b.md").read_text(encoding="utf-8") == "better"
    assert all(row["visit_count"] == 2 for row in replacement_rows)
    assert all(
        row[key] not in discarded_keys
        for row in replacement_rows
        for key in ("candidate_run_key", "score_run_key")
    )
    assert published_score_rows == replacement_rows
    assert replacement_manifest["selected_candidate_id"] == "b"
    assert not discarded_visit.adjudication_root.exists()
    assert not discarded_visit.promotion_manifest_path.parent.exists()


@pytest.mark.parametrize("tamper", ["hash", "mode"])
def test_discard_partial_promotion_rejects_invalid_backup_and_preserves_visit(
    tmp_path: Path,
    tamper: str,
) -> None:
    parent = tmp_path / "parent"
    destination = parent / "state/result.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("selected\n", encoding="utf-8")
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    _, backup, expected_rollback = _write_discard_manifest(
        manifest_path,
        status="committing",
        baseline_text="baseline\n",
    )
    if tamper == "hash":
        backup.write_text("tampered\n", encoding="utf-8")
    else:
        backup.chmod(0o600 if backup.stat().st_mode & 0o777 != 0o600 else 0o644)

    with pytest.raises(PromotionConflictError) as exc_info:
        discard_partial_promotion_visit(
            parent_workspace=parent,
            promotion_manifest_path=manifest_path,
            expected_rollback=expected_rollback,
        )

    assert exc_info.value.failure_type == "promotion_rollback_conflict"
    assert destination.read_text(encoding="utf-8") == "selected\n"
    assert manifest_path.parent.exists()


def test_discard_prepared_promotion_rejects_parent_change_and_preserves_visit(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    destination = parent / "state/result.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("changed\n", encoding="utf-8")
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    _, _, expected_rollback = _write_discard_manifest(
        manifest_path,
        status="prepared",
        baseline_text="baseline\n",
    )

    with pytest.raises(PromotionConflictError) as exc_info:
        discard_partial_promotion_visit(
            parent_workspace=parent,
            promotion_manifest_path=manifest_path,
            expected_rollback=expected_rollback,
        )

    assert exc_info.value.failure_type == "promotion_rollback_conflict"
    assert destination.read_text(encoding="utf-8") == "changed\n"
    assert manifest_path.parent.exists()


def test_discard_partial_promotion_rejects_unrelated_created_parent_directory(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    destination = parent / "state/result.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("selected\n", encoding="utf-8")
    unrelated = parent / "unrelated-empty"
    unrelated.mkdir()
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    _, _, expected_rollback = _write_discard_manifest(
        manifest_path,
        status="committing",
        baseline_text=None,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_parent_dirs"] = ["unrelated-empty"]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(PromotionConflictError) as exc_info:
        discard_partial_promotion_visit(
            parent_workspace=parent,
            promotion_manifest_path=manifest_path,
            expected_rollback=expected_rollback,
        )

    assert exc_info.value.failure_type == "promotion_rollback_conflict"
    assert destination.read_text(encoding="utf-8") == "selected\n"
    assert unrelated.is_dir()
    assert manifest_path.parent.exists()


def test_discard_partial_promotion_rejects_valid_shaped_unrelated_destination(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    expected_destination = parent / "state/result.txt"
    expected_destination.parent.mkdir(parents=True)
    expected_destination.write_text("selected\n", encoding="utf-8")
    unrelated_destination = parent / "unrelated/result.txt"
    unrelated_destination.parent.mkdir(parents=True)
    unrelated_destination.write_text("selected\n", encoding="utf-8")
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    _, _, expected_rollback = _write_discard_manifest(
        manifest_path,
        status="committing",
        baseline_text=None,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["dest_rel"] = "unrelated/result.txt"
    manifest["created_parent_dirs"] = ["unrelated"]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(PromotionConflictError) as exc_info:
        discard_partial_promotion_visit(
            parent_workspace=parent,
            promotion_manifest_path=manifest_path,
            expected_rollback=expected_rollback,
        )

    assert exc_info.value.failure_type == "promotion_rollback_conflict"
    assert expected_destination.read_text(encoding="utf-8") == "selected\n"
    assert unrelated_destination.read_text(encoding="utf-8") == "selected\n"
    assert manifest_path.parent.exists()


def test_discard_partial_promotion_requires_authoritative_promoted_paths(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    destination = parent / "state/result.txt"
    destination.parent.mkdir(parents=True)
    destination.write_text("selected\n", encoding="utf-8")
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    _, _, expected_rollback = _write_discard_manifest(
        manifest_path,
        status="committing",
        baseline_text=None,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["promoted_paths"] = {"result": "unrelated/result.txt"}
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(PromotionConflictError) as exc_info:
        discard_partial_promotion_visit(
            parent_workspace=parent,
            promotion_manifest_path=manifest_path,
            expected_rollback=expected_rollback,
        )

    assert exc_info.value.failure_type == "promotion_rollback_conflict"
    assert destination.read_text(encoding="utf-8") == "selected\n"
    assert manifest_path.parent.exists()


def test_discard_partial_promotion_requires_authoritative_file_order(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    (parent / "state").mkdir(parents=True)
    (parent / "state/result.txt").write_text("selected\n", encoding="utf-8")
    (parent / "state/other.txt").write_text("selected\n", encoding="utf-8")
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    source, _, expected_rollback = _write_discard_manifest(
        manifest_path,
        status="committing",
        baseline_text=None,
    )
    other_row = dict(expected_rollback["files"][0])
    other_row["artifact"] = "other"
    other_row["dest_rel"] = "state/other.txt"
    other_row["source"] = source.as_posix()
    expected_rollback["files"].append(other_row)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = [other_row, manifest["files"][0]]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(PromotionConflictError) as exc_info:
        discard_partial_promotion_visit(
            parent_workspace=parent,
            promotion_manifest_path=manifest_path,
            expected_rollback=expected_rollback,
        )

    assert exc_info.value.failure_type == "promotion_rollback_conflict"
    assert (parent / "state/result.txt").exists()
    assert (parent / "state/other.txt").exists()
    assert manifest_path.parent.exists()


def test_derive_promotion_rollback_authority_binds_snapshot_and_candidate(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    (parent / "state").mkdir(parents=True)
    (parent / "state/result.txt").write_text("baseline\n", encoding="utf-8")
    (candidate / "state").mkdir(parents=True)
    (candidate / "state/result.txt").write_text("selected\n", encoding="utf-8")
    _, baseline_manifest = _baseline(tmp_path, parent)

    authority = derive_promotion_rollback_authority(
        expected_outputs=[
            {"name": "result", "path": "state/result.txt", "type": "string"}
        ],
        output_bundle=None,
        candidate_workspace=candidate,
        parent_workspace=parent,
        baseline_manifest=baseline_manifest,
        selected_candidate_id="candidate-a",
    )

    assert authority["selected_candidate_id"] == "candidate-a"
    assert authority["promoted_paths"] == {"result": "state/result.txt"}
    assert authority["files"] == [
        {
            "role": "value_file",
            "artifact": "result",
            "source": (candidate / "state/result.txt").resolve().as_posix(),
            "dest_rel": "state/result.txt",
            "source_sha256": _hash_text("selected\n"),
            "baseline_preimage": {
                "state": "file",
                "sha256": _hash_text("baseline\n"),
                "mode": (parent / "state/result.txt").stat().st_mode & 0o777,
            },
            "current_preimage": {
                "state": "file",
                "sha256": _hash_text("baseline\n"),
                "mode": (parent / "state/result.txt").stat().st_mode & 0o777,
            },
        }
    ]


def test_derive_promotion_rollback_authority_rejects_tampered_baseline_snapshot(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    (parent / "state").mkdir(parents=True)
    (parent / "state/result.txt").write_text("baseline\n", encoding="utf-8")
    (candidate / "state").mkdir(parents=True)
    (candidate / "state/result.txt").write_text("selected\n", encoding="utf-8")
    _, baseline_manifest = _baseline(tmp_path, parent)
    baseline_copy = Path(baseline_manifest.baseline_workspace) / "state/result.txt"
    baseline_copy.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(PromotionConflictError) as exc_info:
        derive_promotion_rollback_authority(
            expected_outputs=[
                {"name": "result", "path": "state/result.txt", "type": "string"}
            ],
            output_bundle=None,
            candidate_workspace=candidate,
            parent_workspace=parent,
            baseline_manifest=baseline_manifest,
            selected_candidate_id="candidate-a",
        )

    assert exc_info.value.failure_type == "promotion_rollback_conflict"


@pytest.mark.parametrize(
    "manifest_payload",
    [
        "{not json",
        json.dumps({"schema": "wrong", "status": "prepared", "files": []}),
        json.dumps(
            {
                "schema": "adjudicated_provider.promotion.v1",
                "status": "unknown",
                "files": [],
            }
        ),
    ],
)
def test_discard_partial_promotion_rejects_malformed_manifest_and_preserves_visit(
    tmp_path: Path,
    manifest_payload: str,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(manifest_payload, encoding="utf-8")

    with pytest.raises(PromotionConflictError) as exc_info:
        discard_partial_promotion_visit(
            parent_workspace=parent,
            promotion_manifest_path=manifest_path,
            expected_rollback={
                "selected_candidate_id": None,
                "files": [],
                "promoted_paths": {},
            },
        )

    assert exc_info.value.failure_type == "promotion_rollback_conflict"
    assert manifest_path.parent.exists()


def test_discard_partial_promotion_rejects_missing_manifest_in_existing_root(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    manifest_path = tmp_path / "run/promotions/root/draft/1/manifest.json"
    manifest_path.parent.mkdir(parents=True)

    with pytest.raises(PromotionConflictError) as exc_info:
        discard_partial_promotion_visit(
            parent_workspace=parent,
            promotion_manifest_path=manifest_path,
            expected_rollback={
                "selected_candidate_id": None,
                "files": [],
                "promoted_paths": {},
            },
        )

    assert exc_info.value.failure_type == "promotion_rollback_conflict"
    assert manifest_path.parent.exists()


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


def _root_result_bundle_contract() -> dict:
    return {
        "path": "state/bundle.json",
        "fields": [{"name": "__result__", "json_pointer": "", "type": "bool"}],
    }


def _write_root_bundle_resume_manifest(
    manifest_path: Path,
    *,
    status: str,
    document_text: str = "true\n",
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    source = manifest_path.parent / "candidate-source/state/bundle.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(document_text, encoding="utf-8")
    payload = {
        "schema": "adjudicated_provider.promotion.v1",
        "status": status,
        "files": [
            {
                "role": "bundle",
                "artifact": "output_bundle",
                "source": source.as_posix(),
                "dest_rel": "state/bundle.json",
                "source_sha256": _hash_text(document_text),
                "baseline_preimage": {"state": "absent"},
                "current_preimage": {"state": "absent"},
            }
        ],
        "promoted_paths": {},
        "created_parent_dirs": ["state"],
    }
    manifest_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_promotes_root_result_bundle_with_empty_pointer_document(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "state/bundle.json").write_text("true\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)

    result = promote_candidate_outputs(
        expected_outputs=None,
        output_bundle=_root_result_bundle_contract(),
        candidate_workspace=candidate,
        parent_workspace=parent,
        baseline_manifest=manifest,
        promotion_manifest_path=visit.promotion_manifest_path,
        selected_candidate_id="candidate_a",
    )

    assert result.status == "committed"
    assert json.loads((parent / "state/bundle.json").read_text(encoding="utf-8")) is True
    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["status"] == "committed"
    assert manifest_doc["selected_candidate_id"] == "candidate_a"


def test_promotion_resume_committed_root_result_manifest_revalidates_parent_document(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "state").mkdir()
    (parent / "state/bundle.json").write_text("true\n", encoding="utf-8")
    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)
    _write_root_bundle_resume_manifest(visit.promotion_manifest_path, status="committed")

    result = promote_candidate_outputs(
        expected_outputs=None,
        output_bundle=_root_result_bundle_contract(),
        candidate_workspace=tmp_path / "missing-candidate",
        parent_workspace=parent,
        baseline_manifest=_baseline(tmp_path, parent)[1],
        promotion_manifest_path=visit.promotion_manifest_path,
    )

    assert result.status == "committed"


def test_promotion_resume_committed_root_result_manifest_fails_when_parent_root_invalid(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "state").mkdir()
    (parent / "state/bundle.json").write_text('"not-a-bool"\n', encoding="utf-8")
    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)
    _write_root_bundle_resume_manifest(visit.promotion_manifest_path, status="committed")

    with pytest.raises(PromotionConflictError) as exc_info:
        promote_candidate_outputs(
            expected_outputs=None,
            output_bundle=_root_result_bundle_contract(),
            candidate_workspace=tmp_path / "missing-candidate",
            parent_workspace=parent,
            baseline_manifest=_baseline(tmp_path, parent)[1],
            promotion_manifest_path=visit.promotion_manifest_path,
        )

    assert exc_info.value.failure_type == "promotion_validation_failed"


def test_promotion_rolls_back_root_result_bundle_on_parent_validation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    candidate = tmp_path / "candidate"
    parent.mkdir()
    candidate.mkdir()
    (candidate / "state").mkdir()
    (candidate / "state/bundle.json").write_text("true\n", encoding="utf-8")
    visit, manifest = _baseline(tmp_path, parent)

    def fail_parent_validation(expected_outputs, output_bundle, workspace):
        del expected_outputs, output_bundle, workspace
        raise OutputContractError(
            [
                ContractViolation(
                    type="forced_failure",
                    message="validation failed after commit",
                    context={"path": "state/bundle.json"},
                )
            ]
        )

    monkeypatch.setattr(adjudication, "_validate_promotion_parent", fail_parent_validation, raising=False)

    with pytest.raises(PromotionConflictError) as exc_info:
        promote_candidate_outputs(
            expected_outputs=None,
            output_bundle=_root_result_bundle_contract(),
            candidate_workspace=candidate,
            parent_workspace=parent,
            baseline_manifest=manifest,
            promotion_manifest_path=visit.promotion_manifest_path,
        )

    assert exc_info.value.failure_type == "promotion_validation_failed"
    assert not (parent / "state/bundle.json").exists()
    assert not (parent / "state").exists()
    manifest_doc = json.loads(visit.promotion_manifest_path.read_text(encoding="utf-8"))
    assert manifest_doc["status"] == "failed"


def test_resolve_json_pointer_empty_pointer_parity_across_copies() -> None:
    from orchestrator.contracts.output_contract import _resolve_json_pointer as contract_resolve
    from orchestrator.workflow.adjudication.evidence import _resolve_json_pointer as evidence_resolve
    from orchestrator.workflow.adjudication.utils import _resolve_json_pointer as utils_resolve

    documents = [
        True,
        False,
        None,
        5,
        "docs/plans/demo.md",
        [1, {"a": 2}],
        {"a": {"b": [True]}, "~k": 1, "/k": 2},
    ]
    pointers = ["", "/a", "/a/b", "/a/b/0", "/0", "/1", "/2", "/-", "/nope", "x", "/~0k", "/~1k"]

    for document in documents:
        for pointer in pointers:
            expected = contract_resolve(document, pointer)
            assert evidence_resolve(document, pointer) == expected
            assert utils_resolve(document, pointer) == expected
        assert contract_resolve(document, "") == (True, document)


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
