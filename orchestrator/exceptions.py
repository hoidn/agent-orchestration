"""Orchestrator exceptions."""

from typing import List, Optional
from dataclasses import dataclass


@dataclass
class ValidationError:
    """Single validation error."""
    message: str
    path: str = ""
    exit_code: int = 2


class WorkflowValidationError(Exception):
    """Raised when workflow validation fails.

    This exception is raised by the loader when validation errors occur,
    allowing the CLI to catch it and map to appropriate exit codes.
    """

    def __init__(self, errors: List[ValidationError]):
        self.errors = errors
        self.exit_code = 2  # Default validation exit code

        # Construct error message
        messages = []
        for error in errors:
            messages.append(f"Validation error: {error.message}")

        super().__init__("\n".join(messages))