"""
Retry policy helpers for step execution.
Implements AT-20,21: Timeout and retry logic for providers and commands.
"""

import time
from dataclasses import dataclass
from typing import Optional, Set


@dataclass
class RetryPolicy:
    """
    Configuration for step retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries)
        delay_ms: Delay between retries in milliseconds
        retryable_codes: Set of exit codes that trigger retries
    """
    max_retries: int = 0
    delay_ms: int = 1000
    retryable_codes: Optional[Set[int]] = None

    def __post_init__(self):
        if self.retryable_codes is None:
            # Default: no codes are retryable
            self.retryable_codes = set()

    @classmethod
    def for_provider(cls, max_retries: int = 1, delay_ms: int = 1000) -> 'RetryPolicy':
        """
        Create retry policy for provider steps.
        Per AT-21: Provider steps retry on exit codes 1 and 124 by default.
        """
        return cls(
            max_retries=max_retries,
            delay_ms=delay_ms,
            retryable_codes={1, 124}
        )

    @classmethod
    def for_command(cls, retries_config: Optional[dict] = None) -> 'RetryPolicy':
        """
        Create retry policy for command steps.
        Per AT-21: Raw commands only retry when retries field is set.
        """
        if not retries_config:
            # No retries for commands by default
            return cls(max_retries=0)

        # Handle both dict format and integer shorthand
        if isinstance(retries_config, int):
            max_retries = retries_config
            delay_ms = 1000
        else:
            max_retries = retries_config.get('max', 0)
            delay_ms = retries_config.get('delay_ms', 1000)

        # Commands with retries set also consider 1 and 124 retryable
        return cls(
            max_retries=max_retries,
            delay_ms=delay_ms,
            retryable_codes={1, 124}
        )

    def should_retry(self, exit_code: int, attempt: int) -> bool:
        """
        Determine if a retry should be attempted.

        Args:
            exit_code: Exit code from the last execution
            attempt: Current attempt number (0-based)

        Returns:
            True if should retry, False otherwise
        """
        # Check if we have retries left
        if attempt >= self.max_retries:
            return False

        # Check if exit code is retryable
        return exit_code in (self.retryable_codes or set())

    def wait(self):
        """Wait for the configured delay between retries."""
        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000.0)