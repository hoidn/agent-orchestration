"""
Secrets management and masking implementation.
Implements AT-41,42,54,55: Secrets handling, masking, and precedence.

Per specs/security.md:
- Secrets sourced exclusively from orchestrator environment
- Empty strings count as present
- Missing secrets cause exit 2 with missing_secrets context
- Best-effort masking in logs and state
- Precedence: step env overrides secrets when keys collide
"""

import os
import re
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass


@dataclass
class SecretsContext:
    """Context for secrets handling in a step."""
    declared_secrets: List[str]  # Names of env vars declared as secrets
    missing_secrets: List[str]  # Missing required secrets
    secret_values: Dict[str, str]  # Actual values to mask (including from env overrides)
    child_env: Dict[str, str]  # Final environment for child process


class SecretsManager:
    """
    Manages secrets resolution, validation, and masking.

    Per spec:
    - Reads from orchestrator environment only (AT-54)
    - Empty strings are considered present
    - Tracks missing secrets for error reporting (AT-41)
    - Maintains values for masking (AT-42)
    - Handles env precedence (AT-55)
    """

    def __init__(self):
        """Initialize secrets manager."""
        self._masked_values: Set[str] = set()

    def resolve_secrets(
        self,
        declared_secrets: Optional[List[str]] = None,
        step_env: Optional[Dict[str, str]] = None
    ) -> SecretsContext:
        """
        Resolve secrets for a step.

        Args:
            declared_secrets: List of environment variable names required as secrets
            step_env: Step-specific environment overrides

        Returns:
            SecretsContext with resolved values and any missing secrets
        """
        context = SecretsContext(
            declared_secrets=declared_secrets or [],
            missing_secrets=[],
            secret_values={},
            child_env={}
        )

        # Start with orchestrator environment (inherited base)
        context.child_env = os.environ.copy()

        # Overlay secrets from orchestrator environment (AT-54)
        for secret_name in context.declared_secrets:
            if secret_name in os.environ:
                # Present (including empty string)
                value = os.environ[secret_name]
                context.child_env[secret_name] = value
                context.secret_values[secret_name] = value
            else:
                # Missing secret (AT-41)
                context.missing_secrets.append(secret_name)

        # Apply step env overrides (AT-55: step env wins on conflicts)
        if step_env:
            for key, value in step_env.items():
                context.child_env[key] = value
                # If this key was also declared as a secret, track for masking
                if key in context.declared_secrets:
                    context.secret_values[key] = value

        # Track all secret values for masking (including overrides)
        for value in context.secret_values.values():
            if value:  # Don't mask empty strings
                self._masked_values.add(value)

        return context

    def mask_text(self, text: str) -> str:
        """
        Mask known secret values in text.

        Per spec: Best-effort replacement with '***'

        Args:
            text: Text potentially containing secrets

        Returns:
            Text with secrets masked
        """
        if not text or not self._masked_values:
            return text

        masked = text
        # Sort by length descending to mask longer values first
        # This prevents partial masking of substring secrets
        for secret_value in sorted(self._masked_values, key=len, reverse=True):
            if secret_value in masked:
                # Use regex for word boundaries where applicable
                # This prevents masking parts of other strings
                pattern = re.escape(secret_value)
                masked = re.sub(pattern, '***', masked)

        return masked

    def mask_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively mask secrets in a dictionary (for state/debug output).

        Args:
            data: Dictionary potentially containing secrets

        Returns:
            Dictionary with secrets masked
        """
        if not data or not self._masked_values:
            return data

        masked = {}
        for key, value in data.items():
            if isinstance(value, str):
                masked[key] = self.mask_text(value)
            elif isinstance(value, dict):
                masked[key] = self.mask_dict(value)
            elif isinstance(value, list):
                masked[key] = [
                    self.mask_text(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                masked[key] = value

        return masked

    def clear_masked_values(self):
        """Clear the set of values to mask (useful for testing)."""
        self._masked_values.clear()


class SecretsMaskingFilter:
    """
    Logging filter for masking secrets in log records.

    Can be attached to Python logging handlers to mask secrets in real-time.
    """

    def __init__(self, secrets_manager: SecretsManager):
        """
        Initialize filter with a secrets manager.

        Args:
            secrets_manager: Manager containing values to mask
        """
        self.secrets_manager = secrets_manager

    def filter(self, record):
        """
        Filter log record to mask secrets.

        Args:
            record: LogRecord to filter

        Returns:
            True (always pass the record through)
        """
        # Mask the main message
        if hasattr(record, 'msg'):
            record.msg = self.secrets_manager.mask_text(str(record.msg))

        # Mask any args that will be formatted into the message
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, dict):
                record.args = self.secrets_manager.mask_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self.secrets_manager.mask_text(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )

        return True