from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from orchestrator.demo.provisioning import provision_trial


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_seed_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "seed-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")

    (repo / "state").mkdir()
    (repo / "docs" / "backlog" / "active").mkdir(parents=True)
    (repo / "README.md").write_text("seed\n")
    (repo / "state" / ".gitkeep").write_text("")
    (repo / "docs" / "backlog" / "active" / ".gitkeep").write_text("")

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "seed")
    commit = _git(repo, "rev-parse", "HEAD")
    return repo, commit


def test_provision_trial_creates_seed_and_run_worktrees(tmp_path: Path):
    seed_repo, commit = _init_seed_repo(tmp_path)
    task_file = tmp_path / "task.md"
    task_file.write_text("translate the module\n")
    experiment_root = tmp_path / "experiment"

    provision_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
    )

    for name in ["seed", "direct-run", "workflow-run"]:
        workspace = experiment_root / name
        assert workspace.is_dir()
        assert (workspace / ".git").exists()
        assert subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip() == commit

    assert (experiment_root / "archive").is_dir()
    assert (experiment_root / "evaluator").is_dir()


def test_provision_trial_injects_identical_task_into_both_run_workspaces(tmp_path: Path):
    seed_repo, _ = _init_seed_repo(tmp_path)
    task_file = tmp_path / "task.md"
    task_text = "port the dataset transform to rust\n"
    task_file.write_text(task_text)
    experiment_root = tmp_path / "experiment"

    provision_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
    )

    for name in ["direct-run", "workflow-run"]:
        workspace = experiment_root / name
        assert (workspace / "state" / "task.md").read_text() == task_text
        assert (workspace / "docs" / "backlog" / "active" / "task.md").read_text() == task_text


def test_provision_trial_stages_workflow_assets_into_workflow_workspace(tmp_path: Path):
    seed_repo, _ = _init_seed_repo(tmp_path)
    task_file = tmp_path / "task.md"
    task_file.write_text("task\n")
    workflow_file = tmp_path / "generic_task_plan_execute_review_loop.yaml"
    workflow_file.write_text("name: demo\n")
    prompt_root = tmp_path / "prompt-root"
    (prompt_root / "generic_task_loop").mkdir(parents=True)
    (prompt_root / "generic_task_loop" / "draft_plan.md").write_text("draft\n")
    experiment_root = tmp_path / "experiment"

    provision_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=workflow_file,
        workflow_prompts_dir=prompt_root,
    )

    workflow_workspace = experiment_root / "workflow-run"
    assert (workflow_workspace / "workflows" / "examples" / workflow_file.name).read_text() == "name: demo\n"
    assert (
        workflow_workspace / "prompts" / "workflows" / "generic_task_loop" / "draft_plan.md"
    ).read_text() == "draft\n"


def test_provision_trial_writes_metadata_with_start_commit(tmp_path: Path):
    seed_repo, commit = _init_seed_repo(tmp_path)
    task_file = tmp_path / "task.md"
    task_file.write_text("task\n")
    experiment_root = tmp_path / "experiment"

    provision_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
    )

    metadata = json.loads((experiment_root / "trial-metadata.json").read_text())
    assert metadata["start_commit"] == commit
    assert metadata["workspaces"]["seed"].endswith("/seed")
    assert metadata["workspaces"]["direct_run"].endswith("/direct-run")
    assert metadata["workspaces"]["workflow_run"].endswith("/workflow-run")



def test_provision_trial_rejects_nonempty_experiment_root(tmp_path: Path):
    seed_repo, _ = _init_seed_repo(tmp_path)
    task_file = tmp_path / "task.md"
    task_file.write_text("task\n")
    experiment_root = tmp_path / "experiment"
    experiment_root.mkdir()
    (experiment_root / "leftover.txt").write_text("x")

    with pytest.raises(ValueError, match="non-empty"):
        provision_trial(
            seed_repo=seed_repo,
            experiment_root=experiment_root,
            task_file=task_file,
        )
