"""Provider type definitions for the orchestrator."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class InputMode(str, Enum):
    """Provider input mode for prompt delivery."""
    ARGV = "argv"
    STDIN = "stdin"


class ProviderSessionMode(str, Enum):
    """Supported provider-session invocation modes."""
    FRESH = "fresh"
    RESUME = "resume"


class ProviderSessionMetadataMode(str, Enum):
    """Supported provider-session metadata transport modes."""
    CODEX_EXEC_JSONL_STDOUT = "codex_exec_jsonl_stdout"


@dataclass
class ProviderSessionSupport:
    """Provider template command variants for session-enabled execution."""

    metadata_mode: str
    fresh_command: List[str]
    resume_command: Optional[List[str]] = None


@dataclass
class ProviderSessionRequest:
    """Resolved session request for one provider invocation."""

    mode: ProviderSessionMode
    session_id: Optional[str] = None
    publish_artifact: Optional[str] = None
    session_id_from: Optional[str] = None


@dataclass
class ProviderTemplate:
    """
    Provider template definition.

    Attributes:
        name: Provider identifier (e.g., 'claude', 'gemini')
        command: Command template array with placeholders
        defaults: Default parameter values (supports nested for AT-44)
        input_mode: How to deliver the prompt (argv or stdin)
        session_support: Optional session-capable command variants
    """
    name: str
    command: List[str]
    defaults: Dict[str, Any] = field(default_factory=dict)
    input_mode: InputMode = InputMode.ARGV
    session_support: Optional[ProviderSessionSupport] = None

    def validate(self) -> List[str]:
        """
        Validate provider template configuration.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Command must not be empty
        if not self.command:
            errors.append(f"Provider '{self.name}': command cannot be empty")

        errors.extend(
            self._validate_command_tokens(
                self.command,
                command_label="command",
                allow_session_id=False,
                require_session_id=False,
            )
        )

        if self.session_support is not None:
            if not self.session_support.fresh_command:
                errors.append(
                    f"Provider '{self.name}': session_support.fresh_command cannot be empty"
                )
            errors.extend(
                self._validate_command_tokens(
                    self.session_support.fresh_command,
                    command_label="session_support.fresh_command",
                    allow_session_id=False,
                    require_session_id=False,
                )
            )

            resume_command = self.session_support.resume_command
            if resume_command is not None:
                errors.extend(
                    self._validate_command_tokens(
                        resume_command,
                        command_label="session_support.resume_command",
                        allow_session_id=True,
                        require_session_id=True,
                    )
                )

        return errors

    def _validate_command_tokens(
        self,
        command: List[str],
        *,
        command_label: str,
        allow_session_id: bool,
        require_session_id: bool,
    ) -> List[str]:
        """Validate placeholder usage within one provider command template."""
        errors: List[str] = []
        if not isinstance(command, list) or not command:
            errors.append(f"Provider '{self.name}': {command_label} cannot be empty")
            return errors

        session_id_count = 0
        for token in command:
            if self.input_mode == InputMode.STDIN and "${PROMPT}" in token:
                errors.append(
                    f"Provider '{self.name}': ${{PROMPT}} not allowed in stdin mode"
                )
            token_session_ids = token.count("${SESSION_ID}")
            session_id_count += token_session_ids
            if token_session_ids and not allow_session_id:
                errors.append(
                    f"Provider '{self.name}': ${{SESSION_ID}} is only allowed in session_support.resume_command"
                )

        if require_session_id and session_id_count != 1:
            errors.append(
                f"Provider '{self.name}': {command_label} must contain exactly one ${{SESSION_ID}} placeholder"
            )
        if not require_session_id and session_id_count:
            errors.append(
                f"Provider '{self.name}': {command_label} must not contain ${{SESSION_ID}}"
            )
        return errors


@dataclass
class ProviderParams:
    """
    Parameters for provider invocation.

    Attributes:
        params: Parameter mapping (supports nested structures for AT-44)
        input_file: Optional file containing the prompt
        output_file: Optional file to capture stdout
    """
    params: Dict[str, Any] = field(default_factory=dict)
    input_file: Optional[str] = None
    output_file: Optional[str] = None


@dataclass
class ProviderInvocation:
    """
    Resolved provider invocation ready for execution.

    Attributes:
        command: Fully resolved command array
        input_mode: How to deliver prompt
        prompt: The composed prompt (if any)
        output_file: File to capture stdout (if any)
        env: Additional environment variables
        timeout_sec: Execution timeout
        command_variant: Selected provider command template
        metadata_mode: Session metadata transport mode for session-enabled invocations
        session_request: Resolved provider-session request, if any
    """
    command: List[str]
    input_mode: InputMode
    prompt: Optional[str] = None
    output_file: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    timeout_sec: Optional[int] = None
    command_variant: str = "command"
    metadata_mode: Optional[str] = None
    session_request: Optional[ProviderSessionRequest] = None
