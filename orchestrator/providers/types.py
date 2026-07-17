"""Provider type definitions for the orchestrator."""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


_ESCAPED_DOLLAR_SENTINEL = "\x00"
_ESCAPED_BRACED_DOLLAR_SENTINEL = "\x01{"
_PROVIDER_COMMAND_PLACEHOLDER_PATTERN = re.compile(r"\$\{([^}]+)\}")
_BARE_PROVIDER_PARAM_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CALL_POLICY_OPTION_ORDER: Tuple[str, ...] = ("model", "effort")
_RESERVED_CALL_POLICY_TARGETS = frozenset(
    {
        "PROMPT",
        "SESSION_ID",
        "run",
        "context",
        "inputs",
        "steps",
        "loop",
        "item",
        "self",
        "parent",
        "root",
    }
)


def escape_provider_command_token(token: str) -> str:
    """Apply command-template escape processing before placeholder validation."""
    processed = token.replace("$$", _ESCAPED_DOLLAR_SENTINEL)
    return processed.replace("$${", _ESCAPED_BRACED_DOLLAR_SENTINEL)


def restore_provider_command_token(token: str) -> str:
    """Restore command-template escaped literals after placeholder substitution."""
    processed = token.replace(_ESCAPED_BRACED_DOLLAR_SENTINEL, "${")
    return processed.replace(_ESCAPED_DOLLAR_SENTINEL, "$")


def extract_provider_command_placeholders(token: str) -> Tuple[str, ...]:
    """Return unescaped command placeholders without narrowing their names."""
    processed = escape_provider_command_token(token)
    return tuple(
        match.group(1)
        for match in _PROVIDER_COMMAND_PLACEHOLDER_PATTERN.finditer(processed)
    )


def is_valid_call_policy_target_param(value: object) -> bool:
    """Return whether a call-policy target is one non-reserved bare parameter."""
    return (
        isinstance(value, str)
        and _BARE_PROVIDER_PARAM_PATTERN.fullmatch(value) is not None
        and value not in _RESERVED_CALL_POLICY_TARGETS
    )


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


@dataclass(frozen=True)
class CallPolicyBinding:
    """Declarative translation from one canonical option to provider argv."""

    target_param: str
    argv_fragment: Optional[Sequence[str]] = None

    def __post_init__(self) -> None:
        """Detach valid public list input from caller-owned mutable storage."""
        if isinstance(self.argv_fragment, list):
            object.__setattr__(self, "argv_fragment", tuple(self.argv_fragment))


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
    call_policy_bindings: Mapping[str, CallPolicyBinding] = field(default_factory=dict)

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

        errors.extend(self._validate_call_policy_bindings())

        return errors

    def _validate_call_policy_bindings(self) -> List[str]:
        """Validate canonical bindings and exact placeholder consumption."""
        errors: List[str] = []
        if not isinstance(self.call_policy_bindings, Mapping):
            return [
                f"Provider '{self.name}': call_policy_bindings must be a mapping"
            ]

        targets: set[str] = set()
        variants = [("command", self.command)]
        if self.session_support is not None:
            variants.append(
                ("session_support.fresh_command", self.session_support.fresh_command)
            )
            if self.session_support.resume_command is not None:
                variants.append(
                    (
                        "session_support.resume_command",
                        self.session_support.resume_command,
                    )
                )

        for canonical_option, binding in self.call_policy_bindings.items():
            context = f"Provider '{self.name}': call_policy_bindings[{canonical_option!r}]"
            if canonical_option not in CALL_POLICY_OPTION_ORDER:
                errors.append(
                    f"{context}: canonical option must be one of "
                    f"{', '.join(CALL_POLICY_OPTION_ORDER)}"
                )
                continue
            if not isinstance(binding, CallPolicyBinding):
                errors.append(f"{context} must be a CallPolicyBinding")
                continue
            if not is_valid_call_policy_target_param(binding.target_param):
                errors.append(
                    f"{context}.target_param must be a non-reserved bare identifier"
                )
                continue
            if binding.target_param in targets:
                errors.append(
                    f"{context}.target_param must be unique across call-policy bindings"
                )
                continue
            targets.add(binding.target_param)

            target = binding.target_param
            fragment = binding.argv_fragment
            if fragment is None:
                for variant_name, command in variants:
                    if not self._is_valid_command_container(command):
                        continue
                    target_count = self._placeholder_count(command, target)
                    if target_count != 1:
                        errors.append(
                            f"{context}: {variant_name} must contain exactly one "
                            f"unescaped ${{{target}}} placeholder"
                        )
                continue

            if not isinstance(fragment, tuple) or any(
                not isinstance(token, str) for token in fragment
            ):
                errors.append(
                    f"{context}.argv_fragment must be an ordered sequence of strings"
                )
                continue

            fragment_placeholders = tuple(
                placeholder
                for token in fragment
                for placeholder in extract_provider_command_placeholders(token)
            )
            if fragment_placeholders != (target,):
                errors.append(
                    f"{context}.argv_fragment must contain exactly one dynamic "
                    f"placeholder, ${{{target}}}"
            )
            for variant_name, command in variants:
                if not self._is_valid_command_container(command):
                    continue
                if self._placeholder_count(command, target):
                    errors.append(
                        f"{context}: {variant_name} must not contain an unescaped "
                        f"${{{target}}} placeholder when argv_fragment is declared"
                    )

        return errors

    @staticmethod
    def _is_valid_command_container(command: object) -> bool:
        """Return whether structural command validation permits consumption checks."""
        return (
            isinstance(command, list)
            and bool(command)
            and all(isinstance(token, str) for token in command)
        )

    @staticmethod
    def _placeholder_count(command: object, target: str) -> int:
        """Count one target across a command after template escape processing."""
        if not isinstance(command, list):
            return 0
        return sum(
            placeholder == target
            for token in command
            if isinstance(token, str)
            for placeholder in extract_provider_command_placeholders(token)
        )

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
            if not isinstance(token, str):
                errors.append(
                    f"Provider '{self.name}': {command_label} tokens must be strings"
                )
                continue
            placeholders = extract_provider_command_placeholders(token)
            if self.input_mode == InputMode.STDIN and "PROMPT" in placeholders:
                errors.append(
                    f"Provider '{self.name}': ${{PROMPT}} not allowed in stdin mode"
                )
            token_session_ids = placeholders.count("SESSION_ID")
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
    terminate_process_tree: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
