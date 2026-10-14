"""
Test suite for retry behavior implementation.
Tests AT-20, AT-21: Timeout and retry logic for providers and commands.
"""

import time


from orchestrator.exec.retry import RetryPolicy


class TestRetryPolicy:
    """Test the RetryPolicy class logic."""

    def test_provider_default_retry_policy(self):
        """AT-21: Provider steps retry on exit codes 1 and 124 by default."""
        policy = RetryPolicy.for_provider(max_retries=3)

        assert policy.max_retries == 3
        assert policy.delay_ms == 1000
        assert policy.retryable_codes == {1, 124}

        # Should retry on codes 1 and 124
        assert policy.should_retry(1, 0) is True
        assert policy.should_retry(124, 0) is True

        # Should not retry on other codes
        assert policy.should_retry(0, 0) is False
        assert policy.should_retry(2, 0) is False

        # Should not retry after max attempts
        assert policy.should_retry(1, 3) is False

    def test_provider_retry_policy_tolerates_none_defaults(self):
        """Provider retry policy should fail safe if None slips through."""
        policy = RetryPolicy.for_provider(max_retries=None, delay_ms=None)

        assert policy.max_retries == 0
        assert policy.delay_ms == 0
        assert policy.should_retry(1, 0) is False

    def test_command_no_retry_by_default(self):
        """AT-21: Raw commands are not retried unless retries field is set."""
        policy = RetryPolicy.for_command(None)

        assert policy.max_retries == 0
        assert policy.retryable_codes == set()

        # Should not retry on any code
        assert policy.should_retry(1, 0) is False
        assert policy.should_retry(124, 0) is False

    def test_command_with_retries_config(self):
        """AT-21: Commands with retries field set use retry policy."""
        retries_config = {'max': 2, 'delay_ms': 500}
        policy = RetryPolicy.for_command(retries_config)

        assert policy.max_retries == 2
        assert policy.delay_ms == 500
        assert policy.retryable_codes == {1, 124}

        # Should retry on codes 1 and 124
        assert policy.should_retry(1, 0) is True
        assert policy.should_retry(124, 0) is True
        assert policy.should_retry(1, 1) is True

        # Should not retry after max attempts
        assert policy.should_retry(1, 2) is False

    def test_retry_wait_delay(self):
        """Test that retry policy waits for the configured delay."""
        policy = RetryPolicy(max_retries=1, delay_ms=100)

        start = time.time()
        policy.wait()
        elapsed = time.time() - start

        # Allow some tolerance for timing
        assert 0.09 < elapsed < 0.15
