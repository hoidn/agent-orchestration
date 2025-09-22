"""Tests for wait-for functionality (AT-17, AT-18, AT-19)."""

import os
import pytest
import tempfile
import time
import threading
from pathlib import Path

from orchestrator.fsq.wait import WaitFor, WaitForConfig, wait_for_files


class TestWaitFor:
    """Test wait_for blocking primitive."""

    def test_at17_wait_for_blocks_until_match(self):
        """AT-17: wait_for blocks until matches or timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file after a delay
            test_file = Path(tmpdir) / "test.task"

            def create_file_delayed():
                time.sleep(0.5)  # 500ms delay
                test_file.write_text("test content")

            # Start file creation in background
            thread = threading.Thread(target=create_file_delayed)
            thread.start()

            # Wait for the file
            config = WaitForConfig(
                glob_pattern="*.task",
                timeout_sec=2,
                poll_ms=100,
                min_count=1,
                workspace=tmpdir
            )
            waiter = WaitFor(config)
            result = waiter.execute()

            thread.join()

            # Verify results
            assert result.exit_code == 0
            assert not result.timed_out
            assert len(result.files) == 1
            assert result.files[0] == "test.task"
            assert result.wait_duration_ms >= 500  # At least 500ms
            assert result.wait_duration_ms < 2000  # Less than timeout
            assert result.poll_count >= 5  # At least 5 polls (500ms / 100ms)

    def test_at18_wait_timeout_exit_124(self):
        """AT-18: wait_for exits 124 and sets timed_out: true on timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Wait for a file that will never appear
            config = WaitForConfig(
                glob_pattern="*.nonexistent",
                timeout_sec=1,  # Short timeout for test speed
                poll_ms=100,
                min_count=1,
                workspace=tmpdir
            )
            waiter = WaitFor(config)
            result = waiter.execute()

            # Verify timeout behavior
            assert result.exit_code == 124  # Standard timeout exit code
            assert result.timed_out is True
            assert len(result.files) == 0
            assert result.wait_duration_ms >= 1000  # At least timeout duration
            assert result.wait_duration_ms < 1500  # Not much more than timeout
            assert result.poll_count >= 10  # About 1000ms / 100ms

    def test_at19_wait_state_tracking(self):
        """AT-19: wait_for records files, wait_duration_ms, poll_count in state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple files
            (Path(tmpdir) / "file1.task").write_text("content1")
            (Path(tmpdir) / "file2.task").write_text("content2")
            (Path(tmpdir) / "other.txt").write_text("other")

            # Wait for task files
            config = WaitForConfig(
                glob_pattern="*.task",
                timeout_sec=5,
                poll_ms=50,
                min_count=2,
                workspace=tmpdir
            )
            waiter = WaitFor(config)
            result = waiter.execute()

            # Verify all state fields are present and correct
            assert result.exit_code == 0
            assert not result.timed_out

            # Files should be found and sorted
            assert len(result.files) == 2
            assert "file1.task" in result.files
            assert "file2.task" in result.files

            # Duration and poll count should be recorded
            assert result.wait_duration_ms > 0
            assert result.wait_duration_ms < 100  # Should be almost instant
            assert result.poll_count == 1  # Should find on first poll

    def test_wait_min_count_requirement(self):
        """Test that wait_for respects min_count parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create only one file
            (Path(tmpdir) / "file1.task").write_text("content")

            # Wait for 2 files (will timeout)
            config = WaitForConfig(
                glob_pattern="*.task",
                timeout_sec=1,
                poll_ms=100,
                min_count=2,  # Require 2 files
                workspace=tmpdir
            )
            waiter = WaitFor(config)
            result = waiter.execute()

            # Should timeout because min_count not met
            assert result.exit_code == 124
            assert result.timed_out
            assert len(result.files) == 1  # Found 1 but needed 2

    def test_wait_immediate_success(self):
        """Test that wait_for succeeds immediately when files already exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files before waiting
            (Path(tmpdir) / "ready.task").write_text("ready")

            # Wait should succeed immediately
            result = wait_for_files(
                glob_pattern="*.task",
                timeout_sec=5,
                poll_ms=100,
                min_count=1,
                workspace=tmpdir
            )

            assert result.exit_code == 0
            assert not result.timed_out
            assert len(result.files) == 1
            assert result.poll_count == 1  # First poll finds it
            assert result.wait_duration_ms < 100  # Very quick

    def test_wait_glob_patterns(self):
        """Test various glob patterns work correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            inbox = Path(tmpdir) / "inbox"
            inbox.mkdir()
            (inbox / "task1.task").write_text("1")
            (inbox / "task2.task").write_text("2")
            (Path(tmpdir) / "other.task").write_text("3")

            # Test nested glob
            result = wait_for_files(
                glob_pattern="inbox/*.task",
                timeout_sec=1,
                poll_ms=100,
                min_count=2,
                workspace=tmpdir
            )

            assert result.exit_code == 0
            assert len(result.files) == 2
            assert all("inbox" in f for f in result.files)

    def test_wait_files_created_during_polling(self):
        """Test files created during polling are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file1 = Path(tmpdir) / "file1.task"
            test_file2 = Path(tmpdir) / "file2.task"

            def create_files_staggered():
                time.sleep(0.2)
                test_file1.write_text("1")
                time.sleep(0.2)
                test_file2.write_text("2")

            thread = threading.Thread(target=create_files_staggered)
            thread.start()

            # Wait for 2 files
            result = wait_for_files(
                glob_pattern="*.task",
                timeout_sec=3,
                poll_ms=100,
                min_count=2,
                workspace=tmpdir
            )

            thread.join()

            assert result.exit_code == 0
            assert len(result.files) == 2
            assert result.wait_duration_ms >= 400  # Both files created
            assert result.poll_count >= 4  # Multiple polls needed

    def test_wait_deterministic_ordering(self):
        """Test that files are returned in sorted order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files in reverse order
            (Path(tmpdir) / "zzz.task").write_text("z")
            (Path(tmpdir) / "aaa.task").write_text("a")
            (Path(tmpdir) / "mmm.task").write_text("m")

            result = wait_for_files(
                glob_pattern="*.task",
                timeout_sec=1,
                poll_ms=100,
                min_count=3,
                workspace=tmpdir
            )

            # Should be sorted
            assert result.files == ["aaa.task", "mmm.task", "zzz.task"]

    def test_step_executor_wait_integration(self):
        """Test wait_for integration with step executor."""
        from orchestrator.exec.step_executor import StepExecutor

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create a test file
            (workspace / "ready.task").write_text("content")

            # Execute wait step
            executor = StepExecutor(workspace)
            result = executor.execute_wait_for(
                step_name="WaitForFile",
                wait_config={
                    "glob": "*.task",
                    "timeout_sec": 2,
                    "poll_ms": 100,
                    "min_count": 1
                }
            )

            # Check result format matches spec
            state = result.to_state_dict()
            assert state["exit_code"] == 0
            assert "files" in state
            assert len(state["files"]) == 1
            assert "wait_duration_ms" in state
            assert "poll_count" in state
            assert state["timed_out"] is False

    def test_step_executor_wait_timeout(self):
        """Test wait_for timeout through step executor."""
        from orchestrator.exec.step_executor import StepExecutor

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Execute wait step that will timeout
            executor = StepExecutor(workspace)
            result = executor.execute_wait_for(
                step_name="WaitTimeout",
                wait_config={
                    "glob": "*.missing",
                    "timeout_sec": 1,
                    "poll_ms": 100,
                    "min_count": 1
                }
            )

            # Check timeout result
            state = result.to_state_dict()
            assert state["exit_code"] == 124
            assert state["timed_out"] is True
            assert "error" in state
            assert state["error"]["type"] == "timeout"