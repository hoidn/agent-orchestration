"""Wait-for polling primitive implementation (AT-17, AT-18, AT-19).

Provides blocking wait functionality for file system patterns with timeout support.
"""

import glob
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


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


class WaitFor:
    """Implements the wait_for blocking primitive per specs/queue.md.

    AT-17: wait_for blocks until matches or timeout
    AT-18: exits 124 and sets timed_out: true on timeout
    AT-19: records files, wait_duration_ms, poll_count in state
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

        # Convert to relative paths from workspace for consistency
        relative_matches = []
        for match in matches:
            match_path = Path(match).resolve()
            try:
                relative = match_path.relative_to(self.workspace)
                relative_matches.append(str(relative))
            except ValueError:
                # File is outside workspace, include as absolute
                relative_matches.append(str(match_path))

        # Sort for deterministic ordering
        return sorted(relative_matches)


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