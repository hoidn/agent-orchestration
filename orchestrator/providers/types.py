"""Provider type definitions for the orchestrator."""

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


_ESCAPED_DOLLAR_SENTINEL = "\x00"
_ESCAPED_BRACED_DOLLAR_SENTINEL = "\x01{"
_PROVIDER_COMMAND_PLACEHOLDER_PATTERN = re.compile(r"\$\{([^}]+)\}")
_BARE_PROVIDER_PARAM_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CALL_POLICY_OPTION_ORDER: Tuple[str, ...] = ("model", "effort")
RUNTIME_CALL_POLICY_OPTION_ORDER: Tuple[str, ...] = (
    "delivery",
    "materialization_attempts",
)
WORKFLOW_CALL_POLICY_OPTION_ORDER: Tuple[str, ...] = (
    *CALL_POLICY_OPTION_ORDER,
    *RUNTIME_CALL_POLICY_OPTION_ORDER,
)
INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION = (
    "interactive_terminal_turn_queue.v1"
)
INTERACTIVE_TERMINAL_SUBMIT_KEYS = frozenset({"ENTER", "TAB"})
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


def canonical_workflow_call_policy(
    policy: Mapping[str, object],
) -> Dict[str, object]:
    """Validate the closed mixed-scalar workflow policy and retain key order."""

    if not isinstance(policy, Mapping):
        raise TypeError("provider call policy must be a mapping")
    unknown = set(policy) - set(WORKFLOW_CALL_POLICY_OPTION_ORDER)
    if unknown:
        keys = ", ".join(sorted(str(key) for key in unknown))
        raise ValueError(
            f"unexpected provider call policy key(s): {keys}"
        )
    for key in CALL_POLICY_OPTION_ORDER:
        if key in policy and (
            not isinstance(policy[key], str) or not policy[key]
        ):
            raise TypeError(f"{key} must be a non-empty string")
    delivery_present = "delivery" in policy
    attempts_present = "materialization_attempts" in policy
    if not delivery_present:
        if attempts_present:
            raise ValueError(
                "materialization_attempts requires explicit phased delivery"
            )
    else:
        delivery = policy["delivery"]
        if not isinstance(delivery, str):
            raise TypeError("delivery must be a string")
        if delivery not in {"composed", "phased"}:
            raise ValueError("delivery must be composed or phased")
        if delivery == "composed" and attempts_present:
            raise ValueError(
                "composed runtime carriage forbids materialization_attempts"
            )
        if delivery == "phased" and not attempts_present:
            raise ValueError(
                "phased runtime carriage requires materialization_attempts"
            )
    if attempts_present:
        attempts = policy["materialization_attempts"]
        if (
            isinstance(attempts, bool)
            or not isinstance(attempts, int)
            or attempts not in {1, 2, 3}
        ):
            raise ValueError("materialization_attempts must be in 1..3")
    return {
        key: policy[key]
        for key in WORKFLOW_CALL_POLICY_OPTION_ORDER
        if key in policy
    }


def validate_phased_delivery_carriage(
    policy: Mapping[str, object] | None,
    *,
    prompt_attempt_identity_version: str | None,
    target_dsl_version: str | None = None,
) -> None:
    """Require exact policy/attempt-identity agreement at every carrier."""

    normalized = (
        {}
        if policy is None
        else canonical_workflow_call_policy(policy)
    )
    phased = normalized.get("delivery") == "phased"
    identity_is_phased = (
        prompt_attempt_identity_version
        == "workflow_prompt_attempt_identity.v2"
    )
    q5_policy_present = any(
        key in normalized
        for key in ("delivery", "materialization_attempts")
    )
    if q5_policy_present or identity_is_phased:
        try:
            target = tuple(
                int(part)
                for part in (target_dsl_version or "").split(".")
            )
        except (AttributeError, TypeError, ValueError):
            target = ()
        if target_dsl_version is not None and target < (2, 23):
            raise ValueError(
                "provider_phased_delivery_carriage_mismatch: "
                "phased carriage requires target DSL 2.23"
            )
    if phased != identity_is_phased:
        raise ValueError(
            "provider_phased_delivery_carriage_mismatch: "
            "call policy and prompt-attempt identity version disagree"
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
    turn_boundary_resume: bool = False


@dataclass(frozen=True)
class InteractiveSessionSupport:
    """Declared provider capability for queued interactive terminal turns."""

    schema_version: str
    turn_boundary_messages: bool
    command: Tuple[str, ...]
    message_submit_keys: Tuple[str, ...]
    graceful_close_text: str
    graceful_close_submit_keys: Tuple[str, ...]

    def __post_init__(self) -> None:
        """Detach ordered public list input from caller-owned mutable storage."""
        for field_name in (
            "command",
            "message_submit_keys",
            "graceful_close_submit_keys",
        ):
            value = getattr(self, field_name)
            if isinstance(value, list):
                object.__setattr__(self, field_name, tuple(value))


def validate_interactive_session_support_capability(
    support: InteractiveSessionSupport,
) -> Tuple[str, ...]:
    """Validate the closed structural interactive-session declaration."""
    errors: List[str] = []
    if support.schema_version != INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION:
        errors.append(
            "schema_version must be "
            f"{INTERACTIVE_TERMINAL_TURN_QUEUE_SCHEMA_VERSION!r}"
        )

    enabled = support.turn_boundary_messages
    if not isinstance(enabled, bool):
        errors.append("turn_boundary_messages must be a boolean")
    elif enabled is not True:
        errors.append("turn_boundary_messages must be true")

    command = support.command
    command_is_valid = (
        isinstance(command, tuple)
        and bool(command)
        and all(
            isinstance(token, str) and bool(token.strip())
            for token in command
        )
    )
    if not isinstance(command, tuple) or not command:
        errors.append("command must be a non-empty ordered sequence")
    elif not all(
        isinstance(token, str) and bool(token.strip())
        for token in command
    ):
        errors.append("command tokens must be non-empty strings")

    if command_is_valid:
        placeholders = tuple(
            placeholder
            for token in command
            for placeholder in extract_provider_command_placeholders(token)
        )
        if placeholders.count("PROMPT") != 1:
            errors.append(
                "command must contain exactly one unescaped ${PROMPT} placeholder"
            )
        if "SESSION_ID" in placeholders:
            errors.append(
                "command must not contain an unescaped ${SESSION_ID} placeholder"
            )

    for field_name in (
        "message_submit_keys",
        "graceful_close_submit_keys",
    ):
        key_sequence = getattr(support, field_name)
        if not isinstance(key_sequence, tuple) or not key_sequence:
            errors.append(
                f"{field_name} must be a non-empty ordered sequence"
            )
            continue
        if not all(
            isinstance(key, str) and bool(key.strip())
            for key in key_sequence
        ):
            errors.append(f"{field_name} tokens must be non-empty strings")
            continue
        for key in key_sequence:
            if key not in INTERACTIVE_TERMINAL_SUBMIT_KEYS:
                errors.append(f"{field_name} contains unsupported key {key!r}")

    close_text = support.graceful_close_text
    if not isinstance(close_text, str) or not close_text.strip():
        errors.append("graceful_close_text must be a non-empty string")

    return tuple(errors)


def validate_turn_boundary_resume_capability(
    session_support: ProviderSessionSupport,
) -> Tuple[str, ...]:
    """Validate the explicit structural contract for turn-boundary resume."""
    enabled = session_support.turn_boundary_resume
    if not isinstance(enabled, bool):
        return ("turn_boundary_resume must be a boolean",)
    if not enabled:
        return ()

    errors: List[str] = []
    commands = (
        ("fresh_command", session_support.fresh_command),
        ("resume_command", session_support.resume_command),
    )
    for command_name, command in commands:
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(token, str) for token in command)
        ):
            errors.append(
                "turn_boundary_resume requires "
                f"{command_name} to be a non-empty list of strings"
            )

    resume_command = session_support.resume_command
    if (
        isinstance(resume_command, list)
        and resume_command
        and all(isinstance(token, str) for token in resume_command)
    ):
        session_id_count = sum(
            placeholder == "SESSION_ID"
            for token in resume_command
            for placeholder in extract_provider_command_placeholders(token)
        )
        if session_id_count != 1:
            errors.append(
                "turn_boundary_resume resume_command must contain exactly one "
                "unescaped ${SESSION_ID} placeholder"
            )

    from .session_transport import supports_resume_boundary_observation

    if not supports_resume_boundary_observation(
        session_support.metadata_mode
    ):
        errors.append(
            "turn_boundary_resume requires a metadata codec with "
            "resume-boundary observation support"
        )

    for command_name, command in commands:
        if (
            isinstance(command, list)
            and "--ephemeral" in command
        ):
            errors.append(
                "turn_boundary_resume "
                f"{command_name} must not contain the exact --ephemeral argument"
            )
    return tuple(errors)


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
        interactive_session_support: Optional queued interactive-session
            capability
    """
    name: str
    command: List[str]
    defaults: Dict[str, Any] = field(default_factory=dict)
    input_mode: InputMode = InputMode.ARGV
    session_support: Optional[ProviderSessionSupport] = None
    call_policy_bindings: Mapping[str, CallPolicyBinding] = field(default_factory=dict)
    interactive_session_support: Optional[InteractiveSessionSupport] = None

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

            errors.extend(
                f"Provider '{self.name}': session_support.{error}"
                for error in validate_turn_boundary_resume_capability(
                    self.session_support
                )
            )

        if self.interactive_session_support is not None:
            if not isinstance(
                self.interactive_session_support,
                InteractiveSessionSupport,
            ):
                errors.append(
                    f"Provider '{self.name}': interactive_session_support "
                    "must be an InteractiveSessionSupport"
                )
            else:
                errors.extend(
                    f"Provider '{self.name}': interactive_session_support.{error}"
                    for error in validate_interactive_session_support_capability(
                        self.interactive_session_support
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
        if isinstance(
            self.interactive_session_support,
            InteractiveSessionSupport,
        ):
            variants.append(
                (
                    "interactive_session_support.command",
                    self.interactive_session_support.command,
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
            isinstance(command, (list, tuple))
            and bool(command)
            and all(isinstance(token, str) for token in command)
        )

    @staticmethod
    def _placeholder_count(command: object, target: str) -> int:
        """Count one target across a command after template escape processing."""
        if not isinstance(command, (list, tuple)):
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


@dataclass(frozen=True, slots=True)
class PreparedProviderPolicy:
    """Closed canonical policy selected for one prepared invocation."""

    provider_name: str
    model: Optional[str]
    effort: Optional[str]
    timeout_sec: Optional[float]
    input_mode: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider_name, str) or not self.provider_name:
            raise ValueError("prepared provider name must be non-empty")
        for field_name in ("model", "effort"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or not value
            ):
                raise ValueError(
                    f"prepared provider {field_name} must be non-empty text"
                )
        if self.timeout_sec is not None:
            timeout_sec = self.timeout_sec
            timeout_is_valid = (
                type(timeout_sec) is int and timeout_sec > 0
            ) or (
                type(timeout_sec) is float
                and math.isfinite(timeout_sec)
                and timeout_sec > 0
            )
            if not timeout_is_valid:
                raise ValueError(
                    "prepared provider timeout must be finite positive seconds"
                )
        if self.input_mode not in {InputMode.ARGV.value, InputMode.STDIN.value}:
            raise ValueError("prepared provider input mode is invalid")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "model": self.model,
            "effort": self.effort,
            "timeout_sec": self.timeout_sec,
            "input_mode": self.input_mode,
        }


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
        turn_boundary_resume: Validated structural live-resume capability
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
    turn_boundary_resume: bool = False
    prepared_prompt: Optional[str] = None
    prepared_provider_policy: Optional[PreparedProviderPolicy] = None
