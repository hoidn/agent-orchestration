"""Queue management for file-based task operations (AT-5, AT-6).

Provides atomic task file creation and lifecycle management utilities.
Per specs/queue.md:
- AT-5: Write as *.tmp, then atomic rename to *.task for inbox atomicity
- AT-6: User-driven task lifecycle management (move to processed/failed)
"""

import os
import shutil
import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import json
import tempfile


class QueueManager:
    """Manages file-based queue operations with atomic guarantees."""

    def __init__(self, workspace: str = "."):
        """Initialize queue manager with workspace root.

        Args:
            workspace: Root directory for queue operations (default ".")
        """
        self.workspace = Path(workspace).resolve()

    def write_task(self,
                   target_path: str,
                   content: str,
                   encoding: str = 'utf-8') -> str:
        """Write a task file atomically (AT-5).

        Implements the inbox atomicity pattern from specs/queue.md:
        1. Write content to a temporary file (*.tmp)
        2. Atomic rename to final path (*.task)

        Args:
            target_path: Target path for the task file (e.g., "inbox/engineer/task_001.task")
            content: Content to write to the task file
            encoding: File encoding (default utf-8)

        Returns:
            Final path of the created task file

        Raises:
            OSError: If file operations fail
        """
        target = self.workspace / target_path

        # Ensure parent directory exists
        target.parent.mkdir(parents=True, exist_ok=True)

        # Create temporary file in same directory (for atomic rename)
        # Use same directory to ensure rename is atomic (same filesystem)
        temp_path = target.parent / f"{target.stem}.tmp"

        try:
            # Write content to temporary file
            temp_path.write_text(content, encoding=encoding)

            # Atomic rename to final name
            # On POSIX systems, rename() is atomic if source and dest are on same filesystem
            temp_path.rename(target)

            return str(target.relative_to(self.workspace))
        except Exception:
            # Clean up temp file if rename failed
            if temp_path.exists():
                temp_path.unlink()
            raise

    def write_task_json(self,
                        target_path: str,
                        data: Dict[str, Any]) -> str:
        """Write a JSON task file atomically.

        Args:
            target_path: Target path for the task file
            data: Dictionary to serialize as JSON

        Returns:
            Final path of the created task file
        """
        content = json.dumps(data, indent=2)
        return self.write_task(target_path, content)

    def move_task(self,
                  source_path: str,
                  dest_dir: str,
                  create_timestamp_subdir: bool = True) -> str:
        """Move a task file to a destination directory (AT-6).

        Implements user-driven task lifecycle management per specs/queue.md.
        This is a helper for workflow steps to move tasks to processed/ or failed/.

        Args:
            source_path: Path to the task file to move
            dest_dir: Destination directory (e.g., "processed" or "failed")
            create_timestamp_subdir: If True, create a timestamp subdirectory

        Returns:
            Final path of the moved task file

        Raises:
            FileNotFoundError: If source file doesn't exist
            OSError: If move operation fails
        """
        source = self.workspace / source_path

        if not source.exists():
            raise FileNotFoundError(f"Task file not found: {source_path}")

        # Construct destination path
        dest_base = self.workspace / dest_dir

        if create_timestamp_subdir:
            # Use ISO timestamp for subdirectory
            import datetime
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
            dest_parent = dest_base / timestamp
        else:
            dest_parent = dest_base

        dest_parent.mkdir(parents=True, exist_ok=True)

        # Preserve filename when moving
        dest = dest_parent / source.name

        # Move the file
        shutil.move(str(source), str(dest))

        return str(dest.relative_to(self.workspace))

    def list_tasks(self,
                   directory: str,
                   extension: str = ".task") -> list[str]:
        """List task files in a directory.

        Args:
            directory: Directory to scan (e.g., "inbox/engineer")
            extension: File extension to match (default ".task")

        Returns:
            List of task file paths relative to workspace
        """
        target_dir = self.workspace / directory

        if not target_dir.exists():
            return []

        # Find all files with the specified extension
        tasks = []
        for file in target_dir.glob(f"*{extension}"):
            if file.is_file():
                tasks.append(str(file.relative_to(self.workspace)))

        return sorted(tasks)  # Sort for deterministic ordering

    def clean_directory(self, directory: str) -> int:
        """Clean (empty) a directory within the workspace.

        This is a helper for the --clean-processed CLI flag.

        Args:
            directory: Directory to clean (must be within workspace)

        Returns:
            Number of items removed

        Raises:
            ValueError: If directory is outside workspace
        """
        target = self.workspace / directory
        target_resolved = target.resolve()

        # Ensure target is within workspace (path safety)
        try:
            target_resolved.relative_to(self.workspace)
        except ValueError:
            raise ValueError(f"Directory {directory} is outside workspace")

        if not target.exists():
            return 0

        count = 0
        for item in target.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            count += 1

        return count

    def archive_directory(self,
                         directory: str,
                         archive_path: str) -> str:
        """Create a zip archive of a directory.

        This is a helper for the --archive-processed CLI flag.

        Args:
            directory: Directory to archive (must be within workspace)
            archive_path: Path for the output zip file

        Returns:
            Path to the created archive

        Raises:
            ValueError: If directory is outside workspace
        """
        source = self.workspace / directory
        source_resolved = source.resolve()

        # Ensure source is within workspace
        try:
            source_resolved.relative_to(self.workspace)
        except ValueError:
            raise ValueError(f"Directory {directory} is outside workspace")

        if not source.exists():
            raise FileNotFoundError(f"Directory {directory} not found")

        # Create archive
        archive = self.workspace / archive_path
        archive.parent.mkdir(parents=True, exist_ok=True)

        # Remove .zip extension if present (shutil.make_archive adds it)
        if archive.suffix == '.zip':
            archive_base = str(archive.with_suffix(''))
        else:
            archive_base = str(archive)

        shutil.make_archive(archive_base, 'zip', source)

        return str(Path(f"{archive_base}.zip").relative_to(self.workspace))


# Convenience functions for common operations
def write_task(path: str, content: str, workspace: str = ".") -> str:
    """Write a task file atomically.

    Args:
        path: Target path for the task file
        content: Content to write
        workspace: Workspace root directory

    Returns:
        Final path of the created task file
    """
    manager = QueueManager(workspace)
    return manager.write_task(path, content)


def move_to_processed(task_path: str, workspace: str = ".") -> str:
    """Move a task to the processed directory with timestamp.

    Args:
        task_path: Path to the task file
        workspace: Workspace root directory

    Returns:
        Final path of the moved task file
    """
    manager = QueueManager(workspace)
    return manager.move_task(task_path, "processed", create_timestamp_subdir=True)


def move_to_failed(task_path: str, workspace: str = ".") -> str:
    """Move a task to the failed directory with timestamp.

    Args:
        task_path: Path to the task file
        workspace: Workspace root directory

    Returns:
        Final path of the moved task file
    """
    manager = QueueManager(workspace)
    return manager.move_task(task_path, "failed", create_timestamp_subdir=True)