from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def init_git_seed_repo_from_example(*, tmp_path: Path, source_dir: Path) -> tuple[Path, str]:
    repo = tmp_path / "seed-repo"
    shutil.copytree(source_dir, repo)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "seed")
    return repo, git(repo, "rev-parse", "HEAD")


def snapshot_tree(root: Path) -> list[tuple[str, bool, int | None]]:
    entries: list[tuple[str, bool, int | None]] = []
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_file():
            entries.append((relative, True, path.stat().st_size))
        else:
            entries.append((relative, False, None))
    return entries


def write_trial_workflow(root: Path, *, name: str = "trial_workflow.yaml") -> Path:
    """Write the smallest legacy workflow needed by trial-runner mechanics tests."""
    workflow_path = root / name
    workflow_path.write_text(
        """version: "1.4"
name: "trial-runner-fixture"
context:
  workflow_model: "claude-sonnet-4-6"
  workflow_effort: "medium"
providers:
  claude:
    command:
      [
        "claude",
        "-p",
        "${PROMPT}",
        "--dangerously-skip-permissions",
        "--model",
        "${model}",
        "--effort",
        "${effort}",
      ]
    defaults:
      model: "${context.workflow_model}"
      effort: "${context.workflow_effort}"
steps:
  - name: Execute
    provider: claude
    input_file: prompts/workflows/generic_task_loop/draft_plan.md
""",
        encoding="utf-8",
    )
    return workflow_path
