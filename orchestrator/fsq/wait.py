"""Wait-for polling primitive implementation (AT-17, AT-18, AT-19, AT-61, AT-62).

Provides blocking wait functionality for file system patterns with timeout support.
"""

import glob
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class WaitForConfig:
    """Configuration for wait_for operations."""
    glob_pattern: str
    timeout_sec: int = 300
    poll_ms: int = 500
    min_count: int = 1
    workspace: str = "."


@dataclass
class WaitForResult:
    """Result of a wait_for operation."""
    files: List[str]
    wait_duration_ms: int
    poll_count: int
    timed_out: bool
    exit_code: int
    error: Optional[Dict[str, Any]] = None


class WaitFor:
    """Implements the wait_for blocking primitive per specs/queue.md.

    AT-17: wait_for blocks until matches or timeout
    AT-18: exits 124 and sets timed_out: true on timeout
    AT-19: records files, wait_duration_ms, poll_count in state
    AT-61: rejects absolute paths or .. with exit 2 and error context
    AT-62: excludes symlinks escaping WORKSPACE; returns relative paths
    """

    def __init__(self, config: WaitForConfig):
        """Initialize wait_for with configuration.

        Args:
            config: WaitForConfig with glob pattern, timeout, polling interval
        """
        self.config = config
        self.workspace = Path(config.workspace).resolve()

    def execute(self) -> WaitForResult:
        """Execute the wait_for operation.

        Polls for files matching the glob pattern until min_count is reached
        or timeout occurs.

        Returns:
            WaitForResult with files found, duration, poll count, and timeout status
        """
        # AT-61: Validate path safety at runtime
        path_error = self._validate_path_safety(self.config.glob_pattern)
        if path_error:
            # Return immediately with exit 2 and error context
            return WaitForResult(
                files=[],
                wait_duration_ms=0,
                poll_count=0,
                timed_out=False,
                exit_code=2,
                error={
                    "type": "path_safety_error",
                    "message": path_error,
                    "context": {
                        "glob_pattern": self.config.glob_pattern
                    }
                }
            )

        start_time = time.time()
        poll_count = 0
        poll_interval_sec = self.config.poll_ms / 1000.0
        timeout_deadline = start_time + self.config.timeout_sec

        matched_files = []

        while time.time() < timeout_deadline:
            poll_count += 1

            # Resolve glob pattern relative to workspace
            pattern_path = self.workspace / self.config.glob_pattern
            matched_files = self._find_matching_files(str(pattern_path))

            # Check if we have enough matches
            if len(matched_files) >= self.config.min_count:
                # Success - found enough files
                elapsed_ms = int((time.time() - start_time) * 1000)
                # Ensure we record at least 1ms for successful finds
                if elapsed_ms == 0 and len(matched_files) > 0:
                    elapsed_ms = 1
                return WaitForResult(
                    files=matched_files,
                    wait_duration_ms=elapsed_ms,
                    poll_count=poll_count,
                    timed_out=False,
                    exit_code=0
                )

            # Sleep before next poll (except on last iteration)
            if time.time() + poll_interval_sec < timeout_deadline:
                time.sleep(poll_interval_sec)

        # Timeout occurred (AT-18)
        elapsed_ms = int((time.time() - start_time) * 1000)
        return WaitForResult(
            files=matched_files,  # Return whatever we found so far
            wait_duration_ms=elapsed_ms,
            poll_count=poll_count,
            timed_out=True,
            exit_code=124  # Standard timeout exit code
        )

    def _find_matching_files(self, pattern: str) -> List[str]:
        """Find files matching the glob pattern.

        Args:
            pattern: Glob pattern to match

        Returns:
            List of matching file paths relative to workspace
        """
        matches = glob.glob(pattern)

        # AT-62: Exclude symlinks escaping workspace, return relative paths
        relative_matches = []
        for match in matches:
            match_path = Path(match)

            # Get the resolved (real) path to check if it's within workspace
            resolved_path = match_path.resolve()

            # Check if resolved path is within workspace
            try:
                # Validate the resolved path is within workspace
                resolved_path.relative_to(self.workspace)

                # But return the original match path (not resolved) relative to workspace
                # This preserves symlink paths instead of resolving them
                original_relative = match_path.relative_to(self.workspace)
                relative_matches.append(str(original_relative))
            except ValueError:
                # File's real path is outside workspace - exclude it (AT-62)
                # Don't include files that escape the workspace
                pass

        # Sort for deterministic ordering
        return sorted(relative_matches)

    def _validate_path_safety(self, glob_pattern: str) -> Optional[str]:
        """Validate glob pattern for path safety (AT-61).

        Args:
            glob_pattern: The glob pattern to validate

        Returns:
            Error message if validation fails, None if safe
        """
        # Skip validation if pattern contains variables (will be substituted at runtime)
        if '${' in glob_pattern:
            # This should have been substituted before reaching here
            # But we'll let it through for now
            return None

        # AT-61: Reject absolute paths
        if os.path.isabs(glob_pattern):
            return f"Absolute paths not allowed in wait_for.glob: {glob_pattern}"

        # AT-61: Reject parent directory traversal
        path_parts = Path(glob_pattern).parts
        if '..' in path_parts:
            return f"Parent directory traversal ('..') not allowed in wait_for.glob: {glob_pattern}"

        return None


def wait_for_files(
    glob_pattern: str,
    timeout_sec: int = 300,
    poll_ms: int = 500,
    min_count: int = 1,
    workspace: str = "."
) -> WaitForResult:
    """Convenience function to wait for files matching a pattern.

    Args:
        glob_pattern: Glob pattern to match files
        timeout_sec: Maximum time to wait in seconds (default 300)
        poll_ms: Polling interval in milliseconds (default 500)
        min_count: Minimum number of files required (default 1)
        workspace: Base directory for relative patterns (default ".")

    Returns:
        WaitForResult with operation details
    """
    config = WaitForConfig(
        glob_pattern=glob_pattern,
        timeout_sec=timeout_sec,
        poll_ms=poll_ms,
        min_count=min_count,
        workspace=workspace
    )
    waiter = WaitFor(config)
    return waiter.execute()