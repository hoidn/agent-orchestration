"""Run one direct-vs-workflow demo trial and archive comparable results."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from orchestrator.demo.provisioning import provision_trial


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_direct_command(prompt: str) -> list[str]:
    return [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        prompt,
    ]


def build_workflow_command(*, workflow_path: Path, repo_root: Path) -> list[str]:
    return [
        "env",
        f"PYTHONPATH={repo_root}",
        sys.executable,
        "-m",
        "orchestrator",
        "run",
        str(Path(workflow_path)),
    ]


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    started = time.time()
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "exit_code": result.returncode,
        "duration_ms": int((time.time() - started) * 1000),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _run_git_capture(workspace: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def archive_workspace_metadata(*, archive_dir: Path, label: str, workspace: Path, command: list[str]) -> dict[str, Any]:
    metadata = {
        "label": label,
        "workspace": str(workspace),
        "command": command,
        "git_status_short": _run_git_capture(workspace, "status", "--short"),
        "git_head": _run_git_capture(workspace, "rev-parse", "HEAD"),
    }
    (archive_dir / f"{label}-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def _write_command_record(archive_dir: Path, name: str, command: list[str]) -> None:
    (archive_dir / f"{name}.json").write_text(
        json.dumps({"command": command}, indent=2) + "\n",
        encoding="utf-8",
    )


def _select_evaluator(*, seed_repo: Path, task_file: Path) -> list[str] | None:
    if task_file.name == "port_linear_classifier_to_rust.md":
        return [sys.executable, str(_repo_root() / "scripts" / "demo" / "evaluate_linear_classifier.py")]
    if seed_repo.name == "demo_task_linear_classifier_port":
        return [sys.executable, str(_repo_root() / "scripts" / "demo" / "evaluate_linear_classifier.py")]
    return None


def _run_evaluator(base_command: list[str], workspace: Path) -> dict[str, Any]:
    result = subprocess.run(
        [*base_command, str(workspace)],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {
            "verdict": "FAIL",
            "failure_categories": ["invalid_evaluator_output"],
            "summary": {
                "hidden_tests_passed": False,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            "soft_quality": {"score": 0.0, "findings": ["evaluator did not return JSON"]},
        }
    payload["process_exit_code"] = result.returncode
    return payload


def run_trial(
    *,
    seed_repo: Path,
    experiment_root: Path,
    task_file: Path,
    workflow_path: Path,
    direct_prompt: str,
    commitish: str = "HEAD",
) -> dict[str, Any]:
    metadata = provision_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=workflow_path,
        workflow_prompts_dir=_repo_root() / "prompts" / "workflows",
        commitish=commitish,
    )
    workspaces = metadata["workspaces"]
    direct_workspace = Path(workspaces["direct_run"])
    workflow_workspace = Path(workspaces["workflow_run"])
    archive_dir = experiment_root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    staged_workflow_path = Path("workflows") / "examples" / Path(workflow_path).name

    direct_command = build_direct_command(direct_prompt)
    workflow_command = build_workflow_command(
        workflow_path=staged_workflow_path,
        repo_root=_repo_root(),
    )
    _write_command_record(archive_dir, "direct-command", direct_command)
    _write_command_record(archive_dir, "workflow-command", workflow_command)

    direct_execution = _run_command(direct_command, cwd=direct_workspace)
    workflow_execution = _run_command(workflow_command, cwd=workflow_workspace)

    direct_metadata = archive_workspace_metadata(
        archive_dir=archive_dir,
        label="direct-run",
        workspace=direct_workspace,
        command=direct_command,
    )
    workflow_metadata = archive_workspace_metadata(
        archive_dir=archive_dir,
        label="workflow-run",
        workspace=workflow_workspace,
        command=workflow_command,
    )

    evaluator_command = _select_evaluator(seed_repo=Path(seed_repo), task_file=Path(task_file))
    direct_evaluation = None
    workflow_evaluation = None
    if evaluator_command is not None:
        direct_evaluation = _run_evaluator(evaluator_command, direct_workspace)
        workflow_evaluation = _run_evaluator(evaluator_command, workflow_workspace)

    result = {
        "seed_repo": str(seed_repo),
        "task_file": str(task_file),
        "start_commit": metadata["start_commit"],
        "workflow_path": str(workflow_path),
        "direct": {
            "workspace": str(direct_workspace),
            "command": direct_command,
            "execution": direct_execution,
            "metadata": direct_metadata,
            "evaluation": direct_evaluation,
        },
        "workflow": {
            "workspace": str(workflow_workspace),
            "command": workflow_command,
            "execution": workflow_execution,
            "metadata": workflow_metadata,
            "evaluation": workflow_evaluation,
        },
    }
    (archive_dir / "trial-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one demo trial and archive the result.")
    parser.add_argument("--seed-repo", required=True, help="Path to the task seed repository.")
    parser.add_argument("--experiment-root", required=True, help="Path to the trial root directory.")
    parser.add_argument("--task-file", required=True, help="Path to the shared task markdown file.")
    parser.add_argument(
        "--workflow",
        default=str(_repo_root() / "workflows" / "examples" / "generic_task_plan_execute_review_loop.yaml"),
        help="Workflow YAML to run for the workflow arm.",
    )
    parser.add_argument(
        "--direct-prompt",
        default="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        help="Single prompt for the direct arm.",
    )
    parser.add_argument("--commitish", default="HEAD", help="Seed revision to provision. Defaults to HEAD.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_trial(
        seed_repo=Path(args.seed_repo),
        experiment_root=Path(args.experiment_root),
        task_file=Path(args.task_file),
        workflow_path=Path(args.workflow),
        direct_prompt=args.direct_prompt,
        commitish=args.commitish,
    )
    print(json.dumps(result, indent=2))
    direct_verdict = (result["direct"]["evaluation"] or {}).get("verdict")
    workflow_verdict = (result["workflow"]["evaluation"] or {}).get("verdict")
    if direct_verdict == "PASS" and workflow_verdict == "PASS":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
