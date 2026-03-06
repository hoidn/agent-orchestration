"""Provision fresh direct-vs-workflow demo workspaces from one git commit."""

from __future__ import annotations

import argparse
import json
import subprocess
from shutil import copy2, copytree
from pathlib import Path


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _ensure_empty_dir(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"Experiment root is not a directory: {path}")
        if any(path.iterdir()):
            raise ValueError(f"Refusing to provision into non-empty experiment root: {path}")
    else:
        path.mkdir(parents=True)


def _add_worktree(seed_repo: Path, destination: Path, commit: str) -> None:
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(destination), commit],
        cwd=seed_repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_task(workspace: Path, task_text: str) -> None:
    state_task = workspace / "state" / "task.md"
    state_task.parent.mkdir(parents=True, exist_ok=True)
    state_task.write_text(task_text)

    backlog_task = workspace / "docs" / "backlog" / "active" / "task.md"
    if backlog_task.parent.exists():
        backlog_task.write_text(task_text)


def _stage_workflow_assets(*, workflow_workspace: Path, workflow_path: Path, workflow_prompts_dir: Path) -> None:
    workflow_dst = workflow_workspace / "workflows" / "examples" / workflow_path.name
    workflow_dst.parent.mkdir(parents=True, exist_ok=True)
    copy2(workflow_path, workflow_dst)

    prompts_dst = workflow_workspace / "prompts" / "workflows"
    prompts_dst.parent.mkdir(parents=True, exist_ok=True)
    copytree(workflow_prompts_dir, prompts_dst, dirs_exist_ok=True)


def provision_trial(
    *,
    seed_repo: Path,
    experiment_root: Path,
    task_file: Path,
    workflow_path: Path | None = None,
    workflow_prompts_dir: Path | None = None,
    commitish: str = "HEAD",
) -> dict[str, str]:
    seed_repo = seed_repo.resolve()
    experiment_root = experiment_root.resolve()
    task_file = task_file.resolve()
    workflow_path = workflow_path.resolve() if workflow_path is not None else None
    workflow_prompts_dir = workflow_prompts_dir.resolve() if workflow_prompts_dir is not None else None

    if not (seed_repo / ".git").exists():
        raise ValueError(f"Seed repo is not a git repository: {seed_repo}")
    if not task_file.is_file():
        raise ValueError(f"Task file does not exist: {task_file}")
    if workflow_path is not None and not workflow_path.is_file():
        raise ValueError(f"Workflow file does not exist: {workflow_path}")
    if workflow_prompts_dir is not None and not workflow_prompts_dir.is_dir():
        raise ValueError(f"Workflow prompts directory does not exist: {workflow_prompts_dir}")
    if (workflow_path is None) != (workflow_prompts_dir is None):
        raise ValueError("workflow_path and workflow_prompts_dir must be provided together")

    _ensure_empty_dir(experiment_root)

    start_commit = _run_git(seed_repo, "rev-parse", commitish)
    task_text = task_file.read_text()

    workspaces = {
        "seed": experiment_root / "seed",
        "direct_run": experiment_root / "direct-run",
        "workflow_run": experiment_root / "workflow-run",
    }
    for workspace in workspaces.values():
        _add_worktree(seed_repo, workspace, start_commit)

    (experiment_root / "archive").mkdir()
    (experiment_root / "evaluator").mkdir()

    for name in ("direct_run", "workflow_run"):
        _write_task(workspaces[name], task_text)

    if workflow_path is not None and workflow_prompts_dir is not None:
        _stage_workflow_assets(
            workflow_workspace=workspaces["workflow_run"],
            workflow_path=workflow_path,
            workflow_prompts_dir=workflow_prompts_dir,
        )

    metadata = {
        "seed_repo": str(seed_repo),
        "task_file": str(task_file),
        "start_commit": start_commit,
        "workspaces": {name: str(path) for name, path in workspaces.items()},
    }
    (experiment_root / "trial-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision direct-run and workflow-run demo workspaces from one seed commit."
    )
    parser.add_argument("--seed-repo", required=True, help="Path to the git seed repository.")
    parser.add_argument(
        "--experiment-root",
        required=True,
        help="Directory that will receive seed/, direct-run/, workflow-run/, archive/, evaluator/.",
    )
    parser.add_argument("--task-file", required=True, help="Path to the shared task markdown file.")
    parser.add_argument(
        "--workflow-path",
        help="Optional workflow YAML to stage into workflow-run/workflows/examples/.",
    )
    parser.add_argument(
        "--workflow-prompts-dir",
        help="Optional prompts/workflows directory to stage into workflow-run/prompts/workflows/.",
    )
    parser.add_argument(
        "--commitish",
        default="HEAD",
        help="Git revision to provision from. Defaults to HEAD.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    metadata = provision_trial(
        seed_repo=Path(args.seed_repo),
        experiment_root=Path(args.experiment_root),
        task_file=Path(args.task_file),
        workflow_path=Path(args.workflow_path) if args.workflow_path else None,
        workflow_prompts_dir=Path(args.workflow_prompts_dir) if args.workflow_prompts_dir else None,
        commitish=args.commitish,
    )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
