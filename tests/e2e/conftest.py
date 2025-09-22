"""Fixtures and utilities for E2E tests."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import pytest


def has_cli(command: str) -> bool:
    """Check if a CLI command is available."""
    return shutil.which(command) is not None


def skip_if_no_cli(command: str) -> None:
    """Skip test if CLI command is not available."""
    if not has_cli(command):
        pytest.skip(f"{command} CLI not available")


def skip_if_no_e2e() -> None:
    """Skip test if E2E tests are not enabled."""
    if not os.getenv("ORCHESTRATE_E2E"):
        pytest.skip("E2E tests disabled (set ORCHESTRATE_E2E to enable)")


@pytest.fixture
def e2e_workspace(tmp_path):
    """Create a temporary workspace for E2E tests."""
    workspace = tmp_path / "e2e_workspace"
    workspace.mkdir()

    # Create standard directories
    (workspace / "workflows").mkdir()
    (workspace / "prompts").mkdir()
    (workspace / "artifacts").mkdir()
    (workspace / "inbox").mkdir()
    (workspace / "processed").mkdir()
    (workspace / "failed").mkdir()
    (workspace / ".orchestrate").mkdir()

    # Set as working directory for the test
    original_cwd = Path.cwd()
    os.chdir(workspace)

    yield workspace

    # Restore original directory
    os.chdir(original_cwd)


@pytest.fixture
def claude_available():
    """Check if claude CLI is available."""
    return has_cli("claude")


@pytest.fixture
def codex_available():
    """Check if codex CLI is available."""
    return has_cli("codex")


def create_test_workflow(workspace: Path, name: str, content: str) -> Path:
    """Create a test workflow file."""
    workflow_path = workspace / "workflows" / f"{name}.yaml"
    workflow_path.write_text(content)
    return workflow_path


def create_test_prompt(workspace: Path, name: str, content: str) -> Path:
    """Create a test prompt file."""
    prompt_path = workspace / "prompts" / f"{name}.md"
    prompt_path.write_text(content)
    return prompt_path