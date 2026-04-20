from pathlib import Path

import pytest

from orchestrator.workflow.adjudication import (
    BaselineExcludedPathError,
    PathSurface,
    adjudication_visit_paths,
    candidate_paths,
    create_baseline_snapshot,
    prepare_candidate_workspace_from_baseline,
)


def test_adjudication_runtime_helpers_are_split_into_public_submodules() -> None:
    import orchestrator.workflow.adjudication.baseline as baseline
    import orchestrator.workflow.adjudication.evidence as evidence
    import orchestrator.workflow.adjudication.ledger as ledger
    import orchestrator.workflow.adjudication.models as models
    import orchestrator.workflow.adjudication.paths as paths
    import orchestrator.workflow.adjudication.promotion as promotion
    import orchestrator.workflow.adjudication.resume as resume
    import orchestrator.workflow.adjudication.scoring as scoring

    assert baseline.create_baseline_snapshot is create_baseline_snapshot
    assert evidence.build_evaluation_packet
    assert ledger.generate_score_ledger_rows
    assert models.BASELINE_COPY_POLICY == "adjudicated_provider.baseline_copy.v1"
    assert paths.adjudication_visit_paths is adjudication_visit_paths
    assert promotion.promote_candidate_outputs
    assert resume.adjudication_sidecars_exist
    assert scoring.select_candidate


def test_visit_and_candidate_paths_are_frame_visit_scoped(tmp_path: Path) -> None:
    run_root = tmp_path / ".orchestrate" / "runs" / "run-1"

    visit = adjudication_visit_paths(run_root, "root", "root.draft", 1)
    candidate = candidate_paths(run_root, "root", "root.draft", 1, "fake_a")

    assert visit.baseline_workspace == run_root / "adjudication/root/root.draft/1/baseline/workspace"
    assert visit.run_score_ledger_path == run_root / "adjudication/root/root.draft/1/candidate_scores.jsonl"
    assert candidate.workspace == run_root / "candidates/root/root.draft/1/fake_a/workspace"
    assert candidate.evaluation_packet_path == run_root / "candidates/root/root.draft/1/fake_a/evaluation_packet.json"
    assert visit.promotion_manifest_path == run_root / "promotions/root/root.draft/1/manifest.json"


@pytest.mark.parametrize("bad_id", ["../x", "x/y", "", "x..y", "x y", ".hidden"])
def test_path_helpers_reject_unsafe_tokens(tmp_path: Path, bad_id: str) -> None:
    run_root = tmp_path / ".orchestrate" / "runs" / "run-1"

    with pytest.raises(ValueError):
        candidate_paths(run_root, "root", "root.draft", 1, bad_id)


def test_baseline_snapshot_uses_fixed_copy_policy_and_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "docs").mkdir()
    (workspace / "docs/source.md").write_text("source\n", encoding="utf-8")
    (workspace / "state").mkdir()
    (workspace / "state/input.txt").write_text("input\n", encoding="utf-8")
    (workspace / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (workspace / ".env.example").write_text("SECRET=\n", encoding="utf-8")
    (workspace / ".git").mkdir()
    (workspace / ".git/config").write_text("ignored\n", encoding="utf-8")
    (workspace / "node_modules/pkg").mkdir(parents=True)
    (workspace / "node_modules/pkg/index.js").write_text("ignored\n", encoding="utf-8")
    (workspace / "__pycache__").mkdir()
    (workspace / "__pycache__/x.pyc").write_bytes(b"ignored")
    (workspace / ".gitignore").write_text("docs/source.md\n", encoding="utf-8")
    (workspace / "relative-ok-symlink").symlink_to("docs/source.md")
    (workspace / "absolute-bad-symlink").symlink_to("/tmp/outside")
    (workspace / "escaping-bad-symlink").symlink_to("../outside")

    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)
    manifest = create_baseline_snapshot(
        parent_workspace=workspace,
        run_root=tmp_path / ".orchestrate/runs/run-1",
        visit_paths=visit,
        workflow_checksum="sha256:test",
        resolved_consumes={},
        required_path_surfaces=[PathSurface("input_file", Path("state/input.txt"))],
        optional_path_surfaces=[],
    )

    assert (visit.baseline_workspace / "docs/source.md").read_text(encoding="utf-8") == "source\n"
    assert (visit.baseline_workspace / ".env.example").exists()
    assert (visit.baseline_workspace / "relative-ok-symlink").is_symlink()
    assert not (visit.baseline_workspace / ".env").exists()
    assert not (visit.baseline_workspace / ".git").exists()
    assert not (visit.baseline_workspace / "node_modules").exists()
    assert not (visit.baseline_workspace / "__pycache__").exists()
    assert not (visit.baseline_workspace / "absolute-bad-symlink").exists()
    assert not (visit.baseline_workspace / "escaping-bad-symlink").exists()
    assert manifest.copy_policy == "adjudicated_provider.baseline_copy.v1"
    assert manifest.local_secret_denylist == "adjudicated_provider.local_secret_denylist.v1"
    assert manifest.baseline_digest.startswith("sha256:")
    assert any(entry.path == "docs/source.md" for entry in manifest.included)
    assert any(entry.path == ".env" and entry.reason == "secret_denylist" for entry in manifest.excluded)
    assert any(entry.path == ".git" and entry.reason == "excluded_root" for entry in manifest.excluded)
    assert visit.baseline_manifest_path.exists()


def test_required_excluded_path_fails_before_candidate_launch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text("SECRET=1\n", encoding="utf-8")
    visit = adjudication_visit_paths(tmp_path / ".orchestrate/runs/run-1", "root", "root.draft", 1)

    with pytest.raises(BaselineExcludedPathError) as exc_info:
        create_baseline_snapshot(
            parent_workspace=workspace,
            run_root=tmp_path / ".orchestrate/runs/run-1",
            visit_paths=visit,
            workflow_checksum="sha256:test",
            resolved_consumes={},
            required_path_surfaces=[PathSurface("input_file", Path(".env"))],
            optional_path_surfaces=[],
        )

    assert exc_info.value.failure_type == "baseline_excluded_required_path"


def test_candidate_workspace_is_copied_from_immutable_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    baseline.mkdir()
    (baseline / "state").mkdir()
    (baseline / "state/input.txt").write_text("baseline\n", encoding="utf-8")

    prepare_candidate_workspace_from_baseline(baseline_workspace=baseline, candidate_workspace=candidate)
    (candidate / "state/input.txt").write_text("mutated\n", encoding="utf-8")
    prepare_candidate_workspace_from_baseline(baseline_workspace=baseline, candidate_workspace=candidate)

    assert (candidate / "state/input.txt").read_text(encoding="utf-8") == "baseline\n"
