"""Test AT-61 and AT-62: Wait-for path safety at runtime.

AT-61: absolute paths or .. in wait_for.glob rejected with exit 2 and error context
AT-62: matches whose real path escapes WORKSPACE are excluded; returned paths are relative to WORKSPACE
"""

import pytest
import yaml
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader
from orchestrator.fsq.wait import WaitFor, WaitForConfig


class TestAT61WaitForPathSafety:
    """Test wait-for runtime path safety per AT-61."""

    def test_at61_absolute_path_rejected(self, tmp_path):
        """AT-61: Absolute path in wait_for.glob rejected with exit 2."""
        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create workflow with absolute path (invalid)
        workflow_content = {
            "version": "1.1",
            "name": "wait-absolute-test",
            "steps": [
                {
                    "name": "WaitAbsolute",
                    "wait_for": {
                        "glob": "/etc/passwd",  # Absolute path - should be rejected
                        "timeout_sec": 1
                    }
                },
                {
                    "name": "ShouldNotRun",
                    "command": ["echo", "Should not run"]
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_manager = StateManager(str(tmp_path / ".orchestrate"))
        state = state_manager.initialize(str(workflow_file))

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Execute workflow - should fail
        try:
            executor.execute()
        except SystemExit:
            pass  # Expected if strict_flow stops on failure

        # Load final state
        final_state = state_manager.load()

        # Verify wait_for step failed with exit 2 and path safety error (AT-61)
        wait_step = final_state.steps.get("WaitAbsolute", {})
        assert wait_step["status"] == "failed"
        assert wait_step["exit_code"] == 2
        assert wait_step.get("error", {}).get("type") == "path_safety_error"
        assert "Absolute paths not allowed" in wait_step.get("error", {}).get("message", "")
        assert wait_step.get("error", {}).get("context", {}).get("glob_pattern") == "/etc/passwd"

        # Verify downstream step did not run
        assert "ShouldNotRun" not in final_state.steps

    def test_at61_parent_escape_rejected(self, tmp_path):
        """AT-61: Parent directory traversal (..) in wait_for.glob rejected with exit 2."""
        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create workflow with parent escape (invalid)
        workflow_content = {
            "version": "1.1",
            "name": "wait-parent-test",
            "steps": [
                {
                    "name": "WaitParent",
                    "wait_for": {
                        "glob": "../secret.txt",  # Parent escape - should be rejected
                        "timeout_sec": 1
                    }
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_manager = StateManager(str(tmp_path / ".orchestrate"))
        state = state_manager.initialize(str(workflow_file))

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Execute workflow - should fail
        try:
            executor.execute()
        except SystemExit:
            pass  # Expected if strict_flow stops on failure

        # Load final state
        final_state = state_manager.load()

        # Verify wait_for step failed with exit 2 and path safety error (AT-61)
        wait_step = final_state.steps.get("WaitParent", {})
        assert wait_step["status"] == "failed"
        assert wait_step["exit_code"] == 2
        assert wait_step.get("error", {}).get("type") == "path_safety_error"
        assert "Parent directory traversal" in wait_step.get("error", {}).get("message", "")
        assert wait_step.get("error", {}).get("context", {}).get("glob_pattern") == "../secret.txt"

    def test_at61_nested_parent_escape_rejected(self, tmp_path):
        """AT-61: Nested parent escape (foo/../..) in wait_for.glob rejected."""
        # Create workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create workflow with nested parent escape
        workflow_content = {
            "version": "1.1",
            "name": "wait-nested-test",
            "steps": [
                {
                    "name": "WaitNested",
                    "wait_for": {
                        "glob": "foo/../../outside.txt",  # Nested parent escape
                        "timeout_sec": 1
                    }
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_manager = StateManager(str(tmp_path / ".orchestrate"))
        state = state_manager.initialize(str(workflow_file))

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Execute workflow - should fail
        try:
            executor.execute()
        except SystemExit:
            pass

        # Load final state
        final_state = state_manager.load()

        # Verify wait_for step failed with path safety error
        wait_step = final_state.steps.get("WaitNested", {})
        assert wait_step["status"] == "failed"
        assert wait_step["exit_code"] == 2
        assert wait_step.get("error", {}).get("type") == "path_safety_error"
        assert ".." in wait_step.get("error", {}).get("message", "")


class TestAT62WaitForSymlinkEscape:
    """Test wait-for symlink escape handling per AT-62."""

    def test_at62_symlink_escape_excluded(self, tmp_path):
        """AT-62: Symlinks escaping workspace are excluded from results."""
        # Create workspace and outside directory
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        # Create files outside workspace
        (outside / "secret.txt").write_text("secret data")
        (outside / "data.log").write_text("log data")

        # Create valid file inside workspace
        (workspace / "valid.txt").write_text("valid data")

        # Create symlinks in workspace pointing outside
        (workspace / "link_to_secret.txt").symlink_to(outside / "secret.txt")
        (workspace / "link_to_log.log").symlink_to(outside / "data.log")

        # Create workflow that waits for all txt files
        workflow_content = {
            "version": "1.1",
            "name": "symlink-test",
            "steps": [
                {
                    "name": "WaitForFiles",
                    "wait_for": {
                        "glob": "*.txt",  # Should match valid.txt and link_to_secret.txt
                        "timeout_sec": 2,
                        "min_count": 1  # At least one file needed
                    }
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_manager = StateManager(str(tmp_path / ".orchestrate"))
        state = state_manager.initialize(str(workflow_file))

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Execute workflow
        executor.execute()

        # Load final state
        final_state = state_manager.load()

        # Verify wait_for succeeded but excluded symlink escaping workspace (AT-62)
        wait_step = final_state.steps.get("WaitForFiles", {})
        assert wait_step["status"] == "completed"
        assert wait_step["exit_code"] == 0

        # Should only include valid.txt, not link_to_secret.txt (escapes workspace)
        assert wait_step["files"] == ["valid.txt"]
        assert "link_to_secret.txt" not in wait_step["files"]
        assert wait_step["timed_out"] is False

    def test_at62_relative_paths_returned(self, tmp_path):
        """AT-62: Returned paths are relative to WORKSPACE."""
        # Create workspace with subdirectories
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        subdir = workspace / "data"
        subdir.mkdir()

        # Create files in subdirectory
        (subdir / "file1.txt").write_text("content1")
        (subdir / "file2.txt").write_text("content2")

        # Create workflow
        workflow_content = {
            "version": "1.1",
            "name": "relative-test",
            "steps": [
                {
                    "name": "WaitForData",
                    "wait_for": {
                        "glob": "data/*.txt",
                        "timeout_sec": 2
                    }
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_manager = StateManager(str(tmp_path / ".orchestrate"))
        state = state_manager.initialize(str(workflow_file))

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Execute workflow
        executor.execute()

        # Load final state
        final_state = state_manager.load()

        # Verify paths are relative to workspace (AT-62)
        wait_step = final_state.steps.get("WaitForData", {})
        assert wait_step["status"] == "completed"
        assert wait_step["exit_code"] == 0

        # Files should be relative paths, not absolute
        expected_files = sorted(["data/file1.txt", "data/file2.txt"])
        assert sorted(wait_step["files"]) == expected_files

        # Ensure no absolute paths
        for file_path in wait_step["files"]:
            assert not os.path.isabs(file_path)
            assert not file_path.startswith(str(workspace))

    def test_at62_symlink_within_workspace_allowed(self, tmp_path):
        """AT-62: Symlinks that stay within workspace are allowed."""
        # Create workspace with subdirectories
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "data").mkdir()
        (workspace / "links").mkdir()

        # Create real files
        (workspace / "data" / "real1.txt").write_text("data1")
        (workspace / "data" / "real2.txt").write_text("data2")

        # Create symlinks within workspace
        (workspace / "links" / "link1.txt").symlink_to(workspace / "data" / "real1.txt")
        (workspace / "links" / "link2.txt").symlink_to(workspace / "data" / "real2.txt")

        # Create workflow
        workflow_content = {
            "version": "1.1",
            "name": "internal-symlink-test",
            "steps": [
                {
                    "name": "WaitForLinks",
                    "wait_for": {
                        "glob": "links/*.txt",
                        "timeout_sec": 2
                    }
                }
            ]
        }

        workflow_file = tmp_path / "workflow.yaml"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Load workflow
        loader = WorkflowLoader(workspace)
        workflow = loader.load(str(workflow_file))

        # Create state manager
        state_manager = StateManager(str(tmp_path / ".orchestrate"))
        state = state_manager.initialize(str(workflow_file))

        # Create executor
        executor = WorkflowExecutor(workflow, workspace, state_manager)

        # Execute workflow
        executor.execute()

        # Load final state
        final_state = state_manager.load()

        # Verify symlinks within workspace are included (AT-62)
        wait_step = final_state.steps.get("WaitForLinks", {})
        assert wait_step["status"] == "completed"
        assert wait_step["exit_code"] == 0

        # Both symlinks should be included since they point within workspace
        expected_files = sorted(["links/link1.txt", "links/link2.txt"])
        assert sorted(wait_step["files"]) == expected_files