"""Dedicated adjudicated-provider resume test selector.

The underlying resume scenarios live with the runtime integration harness in
``test_adjudicated_provider_runtime``. Re-exporting them here keeps the approved
plan's final verification selector stable while avoiding duplicate harness code.
"""

import json
from pathlib import Path

import pytest

import orchestrator.workflow.adjudication_resume as adjudication_resume_module
import orchestrator.workflow.executor as executor_module
from orchestrator.workflow.adjudication import (
    adjudication_cleanup_guard_path,
    adjudication_visit_paths,
    candidate_metadata_path,
    candidate_paths,
    candidate_visit_root,
)
from orchestrator.workflow.executor import WorkflowExecutor
from tests.test_adjudicated_provider_runtime import (
    _resume,
    _run,
    _workflow,
    test_existing_adjudication_sidecars_fail_fast_without_rebaseline,
    test_resume_after_baseline_snapshot_reuses_baseline_and_runs_candidates,
    test_resume_after_committed_promotion_finalizes_ledger_mirror_and_publication,
    test_resume_after_committed_promotion_publishes_root_result_bundle,
    test_resume_after_partial_candidate_generation_runs_remaining_candidates,
    test_resume_after_scored_candidates_promotes_without_rerunning_candidates,
    test_resume_reruns_mismatched_adjudication_sidecars,
    test_resume_reruns_scorer_unavailable_sidecars_that_no_longer_match,
    test_resume_source_mutation_reports_root_checksum_mismatch_before_adjudication,
)


def _counting_single_candidate_workflow(tmp_path: Path) -> tuple[dict, Path, Path]:
    candidate_attempts = tmp_path / "candidate_attempts.txt"
    evaluator_attempts = tmp_path / "evaluator_attempts.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({candidate_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text(f'selected attempt {attempt}', encoding='utf-8')\n"
        ),
    ]
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
            "print(json.dumps({'candidate_id': packet['candidate_id'], 'score': 0.9, 'summary': 'scored'}))\n"
        ),
    ]
    return workflow, candidate_attempts, evaluator_attempts


def test_consistent_adjudication_resume_reuses_without_invocation(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    candidate_attempts = tmp_path / "candidate_attempts.txt"
    evaluator_attempts = tmp_path / "evaluator_attempts.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({candidate_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('selected once', encoding='utf-8')\n"
        ),
    ]
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
            "print(json.dumps({'candidate_id': packet['candidate_id'], 'score': 0.9, 'summary': 'scored'}))\n"
        ),
    ]

    caplog.set_level("WARNING")
    initial = _run(tmp_path, workflow)
    initial_adjudication = initial["steps"]["Draft"]["adjudication"]
    caplog.clear()
    resumed = _resume(tmp_path, workflow)

    assert initial["status"] == "completed"
    assert resumed["status"] == "completed"
    assert resumed["step_visits"]["Draft"] == 1
    assert resumed["steps"]["Draft"]["adjudication"] == initial_adjudication
    assert candidate_attempts.read_text(encoding="utf-8") == "1"
    assert evaluator_attempts.read_text(encoding="utf-8") == "1"
    assert not [
        record
        for record in caplog.records
        if getattr(record, "orchestrator_diagnostic", None)
        == "adjudication_state_mismatch_rerun"
    ]


def test_kill_during_exact_cleanup_fails_closed_without_new_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow, candidate_attempts, evaluator_attempts = (
        _counting_single_candidate_workflow(tmp_path)
    )
    original_promote = executor_module.promote_candidate_outputs

    def interrupt_before_promotion(**_: object) -> object:
        raise SystemExit("interrupted before promotion")

    monkeypatch.setattr(
        executor_module,
        "promote_candidate_outputs",
        interrupt_before_promotion,
    )
    with pytest.raises(SystemExit):
        _run(tmp_path, workflow)
    monkeypatch.setattr(
        executor_module,
        "promote_candidate_outputs",
        original_promote,
    )

    run_root = tmp_path / ".orchestrate/runs/run-1"
    discarded_visit = adjudication_visit_paths(
        run_root,
        "root",
        "root.draft",
        1,
    )
    discarded_candidate_root = candidate_visit_root(
        run_root,
        "root",
        "root.draft",
        1,
    )
    metadata_path = candidate_metadata_path(
        candidate_paths(run_root, "root", "root.draft", 1, "a")
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["candidate_config_hash"] = "sha256:" + ("0" * 64)
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    original_rmtree = adjudication_resume_module.shutil.rmtree

    def interrupt_after_candidate_cleanup(path: object, *args: object, **kwargs: object) -> None:
        original_rmtree(path, *args, **kwargs)
        if Path(path) == discarded_candidate_root:
            raise SystemExit("interrupted during exact adjudication cleanup")

    monkeypatch.setattr(
        adjudication_resume_module.shutil,
        "rmtree",
        interrupt_after_candidate_cleanup,
    )
    with pytest.raises(SystemExit):
        _resume(tmp_path, workflow)
    monkeypatch.setattr(
        adjudication_resume_module.shutil,
        "rmtree",
        original_rmtree,
    )
    cleanup_guard = adjudication_cleanup_guard_path(
        run_root,
        "root",
        "root.draft",
    )
    cleanup_guard_bytes = cleanup_guard.read_bytes()
    assert json.loads(cleanup_guard_bytes) == {
        "schema": "adjudication.rerun_cleanup_guard.v1",
        "mismatch_class": "sidecar_reconciliation_mismatch",
        "frame_scope": "root",
        "step_id": "root.draft",
        "discarded_visit": 1,
        "next_visit": 2,
    }

    state = _resume(tmp_path, workflow)

    assert state["status"] == "failed"
    assert state["steps"]["Draft"]["status"] == "failed"
    assert (
        state["steps"]["Draft"]["error"]["type"]
        == "adjudication_state_integrity_error"
    )
    assert candidate_attempts.read_text(encoding="utf-8") == "1"
    assert evaluator_attempts.read_text(encoding="utf-8") == "1"
    assert cleanup_guard.read_bytes() == cleanup_guard_bytes
    assert discarded_visit.adjudication_root.is_dir()
    assert not discarded_candidate_root.exists()
    assert not adjudication_visit_paths(
        run_root,
        "root",
        "root.draft",
        2,
    ).adjudication_root.exists()
    assert not adjudication_visit_paths(
        run_root,
        "root",
        "root.draft",
        3,
    ).adjudication_root.exists()
    assert not (tmp_path / "state/result_path.txt").exists()
    assert not (tmp_path / "docs/plans/a.md").exists()
    assert "result_path" not in state.get("artifact_versions", {})


def test_kill_during_fresh_mismatch_rerun_converges_through_one_exact_visit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow, candidate_attempts, evaluator_attempts = (
        _counting_single_candidate_workflow(tmp_path)
    )
    original_promote = executor_module.promote_candidate_outputs

    def interrupt_before_promotion(**_: object) -> object:
        raise SystemExit("interrupted before promotion")

    monkeypatch.setattr(
        executor_module,
        "promote_candidate_outputs",
        interrupt_before_promotion,
    )
    with pytest.raises(SystemExit):
        _run(tmp_path, workflow)
    monkeypatch.setattr(
        executor_module,
        "promote_candidate_outputs",
        original_promote,
    )

    run_root = tmp_path / ".orchestrate/runs/run-1"
    first_visit = adjudication_visit_paths(run_root, "root", "root.draft", 1)
    metadata_path = candidate_metadata_path(
        candidate_paths(run_root, "root", "root.draft", 1, "a")
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["candidate_config_hash"] = "sha256:" + ("0" * 64)
    metadata_path.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    original_execute_provider = WorkflowExecutor._execute_provider_invocation

    def execute_then_interrupt(
        self: WorkflowExecutor,
        *args: object,
        **kwargs: object,
    ) -> object:
        original_execute_provider(self, *args, **kwargs)
        raise SystemExit("interrupted during fresh adjudication provider rerun")

    monkeypatch.setattr(
        WorkflowExecutor,
        "_execute_provider_invocation",
        execute_then_interrupt,
    )
    with pytest.raises(SystemExit):
        _resume(tmp_path, workflow)
    monkeypatch.setattr(
        WorkflowExecutor,
        "_execute_provider_invocation",
        original_execute_provider,
    )

    state = _resume(tmp_path, workflow)
    second_visit = adjudication_visit_paths(run_root, "root", "root.draft", 2)
    terminal_visit = adjudication_visit_paths(run_root, "root", "root.draft", 3)

    assert state["status"] == "completed"
    assert state["steps"]["Draft"]["status"] == "completed"
    assert state["steps"]["Draft"]["visit_count"] == 3
    assert state["step_visits"]["Draft"] == 3
    assert candidate_attempts.read_text(encoding="utf-8") == "3"
    assert evaluator_attempts.read_text(encoding="utf-8") == "2"
    assert not first_visit.adjudication_root.exists()
    assert not second_visit.adjudication_root.exists()
    assert terminal_visit.adjudication_root.is_dir()
    assert terminal_visit.run_score_ledger_path.is_file()
    assert terminal_visit.promotion_manifest_path.is_file()
    assert (
        tmp_path / "docs/plans/a.md"
    ).read_text(encoding="utf-8") == "selected attempt 3"
    assert [
        version["value"]
        for version in state["artifact_versions"]["result_path"]
    ] == ["docs/plans/a.md"]
