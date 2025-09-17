"""Unit tests for queue operations (AT-5, AT-6).

Tests atomic task file creation and user-driven lifecycle management.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from orchestrator.fsq import QueueManager, write_task, move_to_processed, move_to_failed


class TestQueueManager:
    """Test suite for QueueManager operations."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def queue_manager(self, temp_workspace):
        """Create a QueueManager instance with temp workspace."""
        return QueueManager(workspace=temp_workspace)

    def test_write_task_atomic(self, queue_manager, temp_workspace):
        """Test AT-5: Atomic task file creation with *.tmp → rename → *.task."""
        task_path = "inbox/engineer/task_001.task"
        content = "Test task content"

        # Write task atomically
        result = queue_manager.write_task(task_path, content)

        # Verify task was created at expected path
        assert result == task_path
        full_path = Path(temp_workspace) / task_path
        assert full_path.exists()
        assert full_path.read_text() == content

        # Verify parent directory was created
        assert (Path(temp_workspace) / "inbox/engineer").exists()

    def test_write_task_atomic_rename_behavior(self, queue_manager, temp_workspace):
        """Test AT-5: Verify atomic rename behavior (*.tmp intermediate file)."""
        task_path = "inbox/architect/design.task"
        content = "Design document"

        # Patch rename to verify tmp file was created
        original_rename = Path.rename
        tmp_path_used = None

        def capture_rename(self, target):
            nonlocal tmp_path_used
            tmp_path_used = str(self)
            return original_rename(self, target)

        with patch.object(Path, 'rename', capture_rename):
            queue_manager.write_task(task_path, content)

        # Verify tmp file pattern was used
        assert tmp_path_used is not None
        assert ".tmp" in tmp_path_used
        assert "design.tmp" in tmp_path_used

    def test_write_task_json(self, queue_manager, temp_workspace):
        """Test atomic JSON task file creation."""
        task_path = "inbox/qa/test_results.task"
        data = {"test": "passed", "score": 100}

        result = queue_manager.write_task_json(task_path, data)

        assert result == task_path
        full_path = Path(temp_workspace) / task_path
        assert full_path.exists()

        # Verify JSON content
        loaded_data = json.loads(full_path.read_text())
        assert loaded_data == data

    def test_write_task_cleanup_on_failure(self, queue_manager, temp_workspace):
        """Test that temp file is cleaned up if rename fails."""
        task_path = "inbox/test.task"

        # Make rename fail
        with patch.object(Path, 'rename', side_effect=OSError("rename failed")):
            with pytest.raises(OSError):
                queue_manager.write_task(task_path, "content")

        # Verify no temp file left behind
        inbox_dir = Path(temp_workspace) / "inbox"
        if inbox_dir.exists():
            temp_files = list(inbox_dir.glob("*.tmp"))
            assert len(temp_files) == 0

    def test_move_task_to_processed(self, queue_manager, temp_workspace):
        """Test AT-6: User-driven move to processed directory with timestamp."""
        # Create a task file first
        task_path = "inbox/engineer/completed.task"
        queue_manager.write_task(task_path, "Completed work")

        # Move to processed
        with patch('orchestrator.fsq.queue.datetime.datetime') as mock_datetime:
            mock_dt = MagicMock()
            mock_dt.strftime.return_value = "20240315T120000"
            mock_datetime.now.return_value = mock_dt
            result = queue_manager.move_task(task_path, "processed")

        # Verify moved to correct location with timestamp
        assert result == "processed/20240315T120000/completed.task"
        assert not (Path(temp_workspace) / task_path).exists()
        assert (Path(temp_workspace) / result).exists()

    def test_move_task_to_failed(self, queue_manager, temp_workspace):
        """Test AT-6: User-driven move to failed directory with timestamp."""
        # Create a task file
        task_path = "inbox/qa/failed_test.task"
        queue_manager.write_task(task_path, "Failed test")

        # Move to failed
        with patch('orchestrator.fsq.queue.datetime.datetime') as mock_datetime:
            mock_dt = MagicMock()
            mock_dt.strftime.return_value = "20240315T130000"
            mock_datetime.now.return_value = mock_dt
            result = queue_manager.move_task(task_path, "failed")

        # Verify moved to failed with timestamp
        assert result == "failed/20240315T130000/failed_test.task"
        assert not (Path(temp_workspace) / task_path).exists()
        assert (Path(temp_workspace) / result).exists()

    def test_move_task_without_timestamp(self, queue_manager, temp_workspace):
        """Test moving task without creating timestamp subdirectory."""
        # Create a task file
        task_path = "inbox/task.task"
        queue_manager.write_task(task_path, "content")

        # Move without timestamp
        result = queue_manager.move_task(task_path, "archive", create_timestamp_subdir=False)

        assert result == "archive/task.task"
        assert (Path(temp_workspace) / result).exists()

    def test_move_nonexistent_task(self, queue_manager):
        """Test that moving nonexistent task raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError) as exc_info:
            queue_manager.move_task("inbox/nonexistent.task", "processed")

        assert "Task file not found" in str(exc_info.value)

    def test_list_tasks(self, queue_manager, temp_workspace):
        """Test listing task files in a directory."""
        # Create several task files
        queue_manager.write_task("inbox/engineer/task1.task", "content1")
        queue_manager.write_task("inbox/engineer/task2.task", "content2")
        queue_manager.write_task("inbox/engineer/readme.txt", "not a task")

        # List tasks
        tasks = queue_manager.list_tasks("inbox/engineer")

        # Should only return .task files, sorted
        assert tasks == [
            "inbox/engineer/task1.task",
            "inbox/engineer/task2.task"
        ]

    def test_list_tasks_empty_directory(self, queue_manager):
        """Test listing tasks in non-existent directory."""
        tasks = queue_manager.list_tasks("inbox/nonexistent")
        assert tasks == []

    def test_clean_directory(self, queue_manager, temp_workspace):
        """Test cleaning (emptying) a directory."""
        # Create files and subdirectories
        queue_manager.write_task("processed/task1.task", "content")
        queue_manager.write_task("processed/subdir/task2.task", "content")

        # Clean the directory
        count = queue_manager.clean_directory("processed")

        # Verify cleaned
        assert count == 2  # task1.task and subdir/
        assert (Path(temp_workspace) / "processed").exists()  # Directory itself remains
        assert len(list((Path(temp_workspace) / "processed").iterdir())) == 0

    def test_clean_directory_path_safety(self, queue_manager):
        """Test that clean_directory rejects paths outside workspace."""
        with pytest.raises(ValueError) as exc_info:
            queue_manager.clean_directory("../outside")

        assert "outside workspace" in str(exc_info.value)

    def test_archive_directory(self, queue_manager, temp_workspace):
        """Test creating a zip archive of a directory."""
        # Create files to archive
        queue_manager.write_task("processed/task1.task", "content1")
        queue_manager.write_task("processed/subdir/task2.task", "content2")

        # Archive the directory
        archive_path = queue_manager.archive_directory("processed", "backup.zip")

        # Verify archive created
        assert archive_path == "backup.zip"
        assert (Path(temp_workspace) / archive_path).exists()

        # Verify archive contents
        import zipfile
        with zipfile.ZipFile(Path(temp_workspace) / archive_path, 'r') as zf:
            names = sorted(zf.namelist())
            # Check for task files (path separators may vary by platform)
            assert any("task1.task" in name for name in names)
            assert any("task2.task" in name for name in names)

    def test_archive_directory_path_safety(self, queue_manager):
        """Test that archive_directory rejects paths outside workspace."""
        with pytest.raises(ValueError) as exc_info:
            queue_manager.archive_directory("/etc/passwd", "archive.zip")

        assert "outside workspace" in str(exc_info.value)

    def test_archive_nonexistent_directory(self, queue_manager):
        """Test archiving non-existent directory raises error."""
        with pytest.raises(FileNotFoundError) as exc_info:
            queue_manager.archive_directory("nonexistent", "archive.zip")

        assert "not found" in str(exc_info.value)


class TestConvenienceFunctions:
    """Test convenience functions for common operations."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_write_task_convenience(self, temp_workspace):
        """Test standalone write_task function."""
        result = write_task("inbox/test.task", "content", workspace=temp_workspace)

        assert result == "inbox/test.task"
        assert (Path(temp_workspace) / result).exists()

    def test_move_to_processed_convenience(self, temp_workspace):
        """Test standalone move_to_processed function."""
        # Create task first
        write_task("inbox/done.task", "done", workspace=temp_workspace)

        with patch('orchestrator.fsq.queue.datetime.datetime') as mock_datetime:
            mock_dt = MagicMock()
            mock_dt.strftime.return_value = "20240315T140000"
            mock_datetime.now.return_value = mock_dt
            result = move_to_processed("inbox/done.task", workspace=temp_workspace)

        assert result == "processed/20240315T140000/done.task"
        assert (Path(temp_workspace) / result).exists()

    def test_move_to_failed_convenience(self, temp_workspace):
        """Test standalone move_to_failed function."""
        # Create task first
        write_task("inbox/error.task", "error", workspace=temp_workspace)

        with patch('orchestrator.fsq.queue.datetime.datetime') as mock_datetime:
            mock_dt = MagicMock()
            mock_dt.strftime.return_value = "20240315T150000"
            mock_datetime.now.return_value = mock_dt
            result = move_to_failed("inbox/error.task", workspace=temp_workspace)

        assert result == "failed/20240315T150000/error.task"
        assert (Path(temp_workspace) / result).exists()


class TestAcceptanceCriteria:
    """Specific tests mapping to acceptance criteria."""

    def test_at5_inbox_atomicity(self, tmp_path):
        """AT-5: Inbox atomicity with *.tmp → rename() → *.task pattern."""
        workspace = tmp_path
        manager = QueueManager(workspace=str(workspace))

        # Test multiple concurrent-like writes
        for i in range(5):
            task_path = f"inbox/concurrent/task_{i:03d}.task"
            content = f"Task {i} content"

            result = manager.write_task(task_path, content)

            # Verify atomic creation
            assert result == task_path
            full_path = workspace / task_path
            assert full_path.exists()
            assert full_path.read_text() == content

            # Ensure no .tmp files remain
            tmp_files = list(full_path.parent.glob("*.tmp"))
            assert len(tmp_files) == 0

    def test_at6_user_driven_lifecycle(self, tmp_path):
        """AT-6: Queue management is user-driven with explicit moves."""
        workspace = tmp_path
        manager = QueueManager(workspace=str(workspace))

        # Create tasks
        task1 = "inbox/worker/success.task"
        task2 = "inbox/worker/failure.task"

        manager.write_task(task1, "successful work")
        manager.write_task(task2, "failed work")

        # User-driven move to processed (with timestamp)
        with patch('orchestrator.fsq.queue.datetime.datetime') as mock_datetime:
            mock_dt = MagicMock()
            mock_dt.strftime.return_value = "20240315T160000"
            mock_datetime.now.return_value = mock_dt
            processed = manager.move_task(task1, "processed")

        assert processed == "processed/20240315T160000/success.task"
        assert (workspace / processed).exists()
        assert not (workspace / task1).exists()

        # User-driven move to failed (with timestamp)
        with patch('orchestrator.fsq.queue.datetime.datetime') as mock_datetime:
            mock_dt = MagicMock()
            mock_dt.strftime.return_value = "20240315T160100"
            mock_datetime.now.return_value = mock_dt
            failed = manager.move_task(task2, "failed")

        assert failed == "failed/20240315T160100/failure.task"
        assert (workspace / failed).exists()
        assert not (workspace / task2).exists()

        # Verify orchestrator doesn't auto-move (files stay until explicitly moved)
        task3 = "inbox/worker/pending.task"
        manager.write_task(task3, "pending work")

        # Task remains in inbox until user explicitly moves it
        assert (workspace / task3).exists()
        assert (workspace / task3).read_text() == "pending work"