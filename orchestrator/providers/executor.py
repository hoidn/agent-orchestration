"""Provider executor for running provider commands."""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from .types import (
    InputMode,
    ProviderInvocation,
    ProviderParams,
    ProviderSessionMetadataMode,
    ProviderSessionMode,
    ProviderSessionRequest,
    ProviderTemplate,
    escape_provider_command_token,
    restore_provider_command_token,
)
from .registry import ProviderRegistry
from ..security.secrets import SecretsManager
from ..variables.substitution import VariableSubstitutor


logger = logging.getLogger(__name__)


@dataclass
class ProviderExecutionResult:
    """Result from provider execution."""
    exit_code: int
    stdout: bytes
    stderr: bytes
    duration_ms: int
    error: Optional[Dict[str, Any]] = None
    missing_placeholders: Optional[List[str]] = None
    invalid_prompt_placeholder: bool = False
    raw_stdout: Optional[bytes] = None
    normalized_stdout: Optional[bytes] = None
    provider_session: Optional[Dict[str, Any]] = None


class ProviderExecutor:
    """
    Executes provider commands with proper input handling.

    Handles argv vs stdin modes, placeholder substitution, and validation
    per specs/providers.md.
    """

    def __init__(self, workspace: Path, registry: ProviderRegistry, secrets_manager: Optional[SecretsManager] = None):
        """
        Initialize provider executor.

        Args:
            workspace: Base workspace directory
            registry: Provider registry for template lookup
            secrets_manager: Manager for secrets handling and masking
        """
        self.workspace = workspace
        self.registry = registry
        self.secrets_manager = secrets_manager or SecretsManager()

    def prepare_invocation(
        self,
        provider_name: str,
        params: ProviderParams,
        context: Dict[str, str],
        prompt_content: Optional[str] = None,
        session_request: Optional[ProviderSessionRequest] = None,
        env: Optional[Dict[str, str]] = None,
        secrets: Optional[List[str]] = None,
        timeout_sec: Optional[int] = None,
    ) -> Tuple[Optional[ProviderInvocation], Optional[Dict[str, Any]]]:
        """
        Prepare a provider invocation.

        Args:
            provider_name: Name of the provider to invoke
            params: Provider parameters
            context: Variable context for substitution
            prompt_content: Composed prompt content (from input_file + injection)
            env: Additional environment variables
            secrets: List of secret env var names to validate
            timeout_sec: Execution timeout

        Returns:
            Tuple of (invocation, error_dict) - error_dict is None if successful
        """
        # Get provider template
        provider = self.registry.get(provider_name)
        if not provider:
            return None, {
                "type": "provider_not_found",
                "message": f"Provider '{provider_name}' not found",
                "context": {"provider": provider_name}
            }

        # Merge parameters (step params override defaults)
        merged_params = self.registry.merge_params(provider_name, params.params or {})

        # Substitute variables in provider_params values (AT-51)
        substituted_params, param_errors = self._substitute_params(merged_params, context)
        if param_errors:
            return None, {
                "type": "substitution_error",
                "message": "Failed to substitute provider parameters",
                "context": {"errors": param_errors}
            }

        command_template = provider.command
        command_variant = "command"
        metadata_mode = None
        if session_request is not None:
            if provider.session_support is None:
                return None, {
                    "type": "validation_error",
                    "message": f"Provider '{provider_name}' does not support provider_session",
                    "context": {"provider": provider_name},
                }
            metadata_mode = provider.session_support.metadata_mode
            if session_request.mode == ProviderSessionMode.FRESH:
                command_template = provider.session_support.fresh_command
                command_variant = "fresh_command"
            else:
                if provider.session_support.resume_command is None:
                    return None, {
                        "type": "validation_error",
                        "message": f"Provider '{provider_name}' does not support provider_session resume",
                        "context": {"provider": provider_name},
                    }
                if not isinstance(session_request.session_id, str) or not session_request.session_id:
                    return None, {
                        "type": "validation_error",
                        "message": "provider_session resume requires a non-empty session_id",
                        "context": {"provider": provider_name},
                    }
                command_template = provider.session_support.resume_command
                command_variant = "resume_command"

        # Build command with substitution
        command, missing_placeholders, invalid_prompt = self._build_command(
            command_template=command_template,
            input_mode=provider.input_mode,
            params=substituted_params,
            context=context,
            prompt=prompt_content,
            session_id=session_request.session_id if session_request is not None else None,
        )

        # Check for validation errors
        if invalid_prompt:
            return None, {
                "type": "validation_error",
                "message": "Invalid ${PROMPT} placeholder in stdin mode",
                "context": {"invalid_prompt_placeholder": True}
            }

        if missing_placeholders:
            return None, {
                "type": "validation_error",
                "message": f"Missing placeholders: {', '.join(missing_placeholders)}",
                "context": {"missing_placeholders": missing_placeholders}
            }

        # Resolve secrets and check for missing (AT-41,42,54,55)
        secrets_context = self.secrets_manager.resolve_secrets(
            declared_secrets=secrets,
            step_env=env
        )

        if secrets_context.missing_secrets:
            return None, {
                "type": "missing_secrets",
                "message": f"Missing required secrets: {', '.join(secrets_context.missing_secrets)}",
                "context": {"missing_secrets": secrets_context.missing_secrets}
            }

        invocation = ProviderInvocation(
            command=command,
            input_mode=provider.input_mode,
            prompt=prompt_content if provider.input_mode == InputMode.STDIN else None,
            output_file=params.output_file,
            env=secrets_context.child_env,  # Use composed environment
            timeout_sec=timeout_sec,
            command_variant=command_variant,
            metadata_mode=metadata_mode,
            session_request=session_request,
        )

        return invocation, None

    def execute(
        self,
        invocation: ProviderInvocation,
        cwd: Optional[Path] = None,
        stream_output: bool = False,
        session_runtime: Optional[Dict[str, Any]] = None,
    ) -> ProviderExecutionResult:
        """
        Execute a prepared provider invocation.

        Args:
            invocation: Provider invocation to execute
            cwd: Working directory (default: workspace)

        Returns:
            Execution result with output and metadata
        """
        working_dir = cwd or self.workspace
        start_time = time.time()

        # Setup environment
        process_env = os.environ.copy()
        if invocation.env:
            process_env.update(invocation.env)

        try:
            # Prepare stdin if needed
            stdin_input = None
            if invocation.input_mode == InputMode.STDIN and invocation.prompt:
                stdin_input = invocation.prompt.encode('utf-8')

            logger.debug(f"Executing command: {invocation.command}")
            if invocation.input_mode == InputMode.STDIN:
                logger.debug(f"Using stdin mode, prompt size: {len(invocation.prompt or '')} bytes")

            session_enabled = invocation.session_request is not None
            if session_enabled:
                return self._execute_session_invocation(
                    invocation=invocation,
                    working_dir=working_dir,
                    process_env=process_env,
                    stdin_input=stdin_input,
                    stream_output=stream_output,
                    start_time=start_time,
                    session_runtime=session_runtime,
                )

            if not stream_output:
                # Execute command
                # Note: We use 'input' parameter for stdin content, not both 'stdin' and 'input'
                result = subprocess.run(
                    invocation.command,
                    cwd=str(working_dir),
                    env=process_env,
                    input=stdin_input,
                    capture_output=True,
                    timeout=invocation.timeout_sec,
                )

                duration_ms = int((time.time() - start_time) * 1000)

                return ProviderExecutionResult(
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    duration_ms=duration_ms
                )

            # Streaming mode: tee provider stdout/stderr to parent streams live
            process = subprocess.Popen(
                invocation.command,
                cwd=str(working_dir),
                env=process_env,
                stdin=subprocess.PIPE if stdin_input is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            if stdin_input is not None and process.stdin is not None:
                process.stdin.write(stdin_input)
                process.stdin.close()

            stdout_buf = bytearray()
            stderr_buf = bytearray()

            stdout_thread = threading.Thread(
                target=self._stream_pipe,
                args=(process.stdout, stdout_buf, sys.stdout),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._stream_pipe,
                args=(process.stderr, stderr_buf, sys.stderr),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            try:
                exit_code = process.wait(timeout=invocation.timeout_sec)
                stdout_thread.join()
                stderr_thread.join()

                duration_ms = int((time.time() - start_time) * 1000)
                return ProviderExecutionResult(
                    exit_code=exit_code,
                    stdout=bytes(stdout_buf),
                    stderr=bytes(stderr_buf),
                    duration_ms=duration_ms
                )
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                stdout_thread.join()
                stderr_thread.join()

                duration_ms = int((time.time() - start_time) * 1000)
                return ProviderExecutionResult(
                    exit_code=124,
                    stdout=bytes(stdout_buf),
                    stderr=bytes(stderr_buf),
                    duration_ms=duration_ms,
                    error={
                        "type": "timeout",
                        "message": f"Provider timed out after {invocation.timeout_sec} seconds",
                        "context": {"timeout_sec": invocation.timeout_sec}
                    }
                )

        except subprocess.TimeoutExpired as e:
            # Timeout: exit code 124 per spec
            duration_ms = int((time.time() - start_time) * 1000)
            return ProviderExecutionResult(
                exit_code=124,
                stdout=e.stdout or b"",
                stderr=e.stderr or b"",
                duration_ms=duration_ms,
                error={
                    "type": "timeout",
                    "message": f"Provider timed out after {invocation.timeout_sec} seconds",
                    "context": {"timeout_sec": invocation.timeout_sec}
                }
            )

        except Exception as e:
            # Other execution errors
            duration_ms = int((time.time() - start_time) * 1000)
            return ProviderExecutionResult(
                exit_code=1,
                stdout=b"",
                stderr=str(e).encode('utf-8'),
                duration_ms=duration_ms,
                error={
                    "type": "execution_error",
                    "message": str(e),
                    "context": {}
                }
            )

    def _capture_pipe(
        self,
        pipe: Optional[Any],
        buffer: bytearray,
        *,
        out_stream: Any = None,
        chunk_callback: Optional[Callable[[bytes], None]] = None,
        read_mode: str = "chunks",
    ) -> None:
        """Capture bytes from a subprocess pipe with optional streaming and per-chunk hooks."""
        if pipe is None:
            return

        output = out_stream.buffer if out_stream is not None and hasattr(out_stream, "buffer") else out_stream
        try:
            while True:
                if read_mode == "lines":
                    chunk = pipe.readline()
                else:
                    chunk = pipe.read(4096)
                if not chunk:
                    break
                buffer.extend(chunk)
                if chunk_callback is not None:
                    try:
                        chunk_callback(chunk)
                    except Exception:
                        pass
                if output is not None:
                    try:
                        output.write(chunk)
                        output.flush()
                    except Exception:
                        # Streaming should never break execution/capture path.
                        pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _stream_pipe(
        self,
        pipe: Optional[Any],
        buffer: bytearray,
        out_stream: Any
    ) -> None:
        """Read bytes from a subprocess pipe, stream them to output, and buffer them."""
        self._capture_pipe(pipe, buffer, out_stream=out_stream)

    def _substitute_params(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Substitute variables in provider parameters (AT-44).

        Supports nested structures (dicts, lists) with full variable substitution.

        Args:
            params: Provider parameters (can be nested dict/list)
            context: Variable context with namespaces

        Returns:
            Tuple of (substituted_params, errors)
        """
        substitutor = VariableSubstitutor()
        errors = []

        try:
            # Use VariableSubstitutor for full nested structure support
            substituted_result = substitutor.substitute(params, context)
            # Ensure the result is a dict (since we passed in a dict)
            if not isinstance(substituted_result, dict):
                errors.append(f"Parameter substitution returned unexpected type: {type(substituted_result)}")
                return params, errors
            substituted = substituted_result

            # Check for undefined variables
            if substitutor.undefined_vars:
                for var in substitutor.undefined_vars:
                    errors.append(f"Undefined variable in provider_params: ${{{var}}}")

        except ValueError as e:
            # Catch any substitution errors
            errors.append(str(e))
            return params, errors  # Return original on error

        return substituted, errors

    def _build_command(
        self,
        command_template: List[str],
        input_mode: InputMode,
        params: Dict[str, str],
        context: Dict[str, str],
        prompt: Optional[str],
        session_id: Optional[str] = None,
    ) -> Tuple[List[str], List[str], bool]:
        """
        Build command with placeholder substitution.

        Args:
            provider: Provider template
            params: Merged and substituted parameters
            context: Variable context
            prompt: Composed prompt content

        Returns:
            Tuple of (command, missing_placeholders, invalid_prompt_placeholder)
        """
        import re

        command = []
        missing = set()
        invalid_prompt = False
        var_pattern = re.compile(r'\$\{([^}]+)\}')

        for token in command_template:
            # Apply escapes first
            processed = escape_provider_command_token(token)

            # Check for ${PROMPT} before substituting other variables
            # AT-73: Prompt content is literal and should not be scanned for variables
            has_prompt = "${PROMPT}" in processed

            if has_prompt:
                if input_mode == InputMode.STDIN:
                    # AT-49: ${PROMPT} not allowed in stdin mode
                    invalid_prompt = True
                    logger.error("${PROMPT} not allowed in stdin mode")

            # Substitute non-PROMPT placeholders first (before injecting literal prompt)
            for match in var_pattern.finditer(processed):
                var = match.group(1)
                if var == "PROMPT":
                    continue  # Handle separately to avoid scanning prompt content
                if var == "SESSION_ID":
                    if isinstance(session_id, str):
                        processed = processed.replace("${SESSION_ID}", session_id)
                    else:
                        missing.add(var)
                    continue

                # Check provider params first
                if var in params:
                    processed = processed.replace(f"${{{var}}}", params[var])
                # Then check context (run/context/loop/steps.*)
                elif var in context:
                    processed = processed.replace(f"${{{var}}}", context[var])
                else:
                    # AT-48: Missing placeholder
                    missing.add(var)

            # Now substitute ${PROMPT} with literal prompt content (AT-73)
            # This happens AFTER other substitutions to avoid scanning prompt for variables
            if has_prompt and input_mode != InputMode.STDIN and prompt:
                processed = processed.replace("${PROMPT}", prompt)

            # Restore escaped literals
            processed = restore_provider_command_token(processed)

            command.append(processed)

        return command, list(missing), invalid_prompt

    def _execute_session_invocation(
        self,
        *,
        invocation: ProviderInvocation,
        working_dir: Path,
        process_env: Dict[str, str],
        stdin_input: Optional[bytes],
        stream_output: bool,
        start_time: float,
        session_runtime: Optional[Dict[str, Any]] = None,
    ) -> ProviderExecutionResult:
        """Execute one session-enabled provider invocation and normalize transport."""
        try:
            process = subprocess.Popen(
                invocation.command,
                cwd=str(working_dir),
                env=process_env,
                stdin=subprocess.PIPE if stdin_input is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            if stdin_input is not None and process.stdin is not None:
                try:
                    process.stdin.write(stdin_input)
                    process.stdin.close()
                except BrokenPipeError:
                    pass

            stdout_buf = bytearray()
            stderr_buf = bytearray()

            stdout_thread = threading.Thread(
                target=self._capture_pipe,
                args=(process.stdout, stdout_buf),
                kwargs={
                    "chunk_callback": lambda chunk: self._append_masked_transport(chunk, session_runtime),
                    "read_mode": "lines",
                },
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._capture_pipe,
                args=(process.stderr, stderr_buf),
                kwargs={"out_stream": sys.stderr if stream_output else None},
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            try:
                exit_code = process.wait(timeout=invocation.timeout_sec)
                stdout_thread.join()
                stderr_thread.join()
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                stdout_thread.join()
                stderr_thread.join()
                duration_ms = int((time.time() - start_time) * 1000)
                return ProviderExecutionResult(
                    exit_code=124,
                    stdout=b"",
                    stderr=bytes(stderr_buf),
                    duration_ms=duration_ms,
                    raw_stdout=bytes(stdout_buf),
                    error={
                        "type": "timeout",
                        "message": f"Provider timed out after {invocation.timeout_sec} seconds",
                        "context": {"timeout_sec": invocation.timeout_sec},
                    },
                )

            duration_ms = int((time.time() - start_time) * 1000)
            return self._finalize_session_result(
                invocation=invocation,
                exit_code=exit_code,
                raw_stdout=bytes(stdout_buf),
                stderr=bytes(stderr_buf),
                duration_ms=duration_ms,
                stream_output=stream_output,
            )
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            return ProviderExecutionResult(
                exit_code=1,
                stdout=b"",
                stderr=str(exc).encode("utf-8"),
                duration_ms=duration_ms,
                raw_stdout=b"",
                error={
                    "type": "execution_error",
                    "message": str(exc),
                    "context": {},
                },
            )

    def _append_masked_transport(
        self,
        raw_stdout: bytes,
        session_runtime: Optional[Dict[str, Any]],
    ) -> None:
        """Best-effort append of masked provider transport to the stable spool path."""
        if not raw_stdout or not isinstance(session_runtime, dict):
            return
        spool_path = session_runtime.get("transport_spool_path")
        if not spool_path:
            return

        text = raw_stdout.decode("utf-8", errors="replace")
        masked_text = self.secrets_manager.mask_text(text)
        path = Path(spool_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(masked_text)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass

    def _finalize_session_result(
        self,
        *,
        invocation: ProviderInvocation,
        exit_code: int,
        raw_stdout: bytes,
        stderr: bytes,
        duration_ms: int,
        stream_output: bool,
    ) -> ProviderExecutionResult:
        """Parse session transport and emit normalized assistant text."""
        normalized_stdout = b""
        provider_session: Dict[str, Any] | None = None
        error = None
        if invocation.metadata_mode == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value:
            provider_session, error = self._parse_codex_jsonl_transport(
                raw_stdout,
                expected_session_id=(
                    invocation.session_request.session_id
                    if invocation.session_request is not None
                    and invocation.session_request.mode == ProviderSessionMode.RESUME
                    else None
                ),
            )
            if error is None and provider_session is not None:
                normalized_stdout = str(provider_session.get("normalized_stdout", "")).encode("utf-8")

        if stream_output:
            if normalized_stdout:
                output = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else sys.stdout
                output.write(normalized_stdout)
                output.flush()
            if stderr:
                err_output = sys.stderr.buffer if hasattr(sys.stderr, "buffer") else sys.stderr
                err_output.write(stderr)
                err_output.flush()

        if error is not None and exit_code == 0:
            exit_code = 2

        return ProviderExecutionResult(
            exit_code=exit_code,
            stdout=normalized_stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            raw_stdout=raw_stdout,
            normalized_stdout=normalized_stdout,
            provider_session=provider_session,
            error=error,
        )

    def _parse_codex_jsonl_transport(
        self,
        raw_stdout: bytes,
        *,
        expected_session_id: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Parse Codex JSONL stdout into normalized assistant text plus session metadata."""
        session_ids: set[str] = set()
        text_parts: List[str] = []
        terminal_seen = False
        event_count = 0

        for line_number, raw_line in enumerate(raw_stdout.decode("utf-8", errors="replace").splitlines(), start=1):
            if not raw_line.strip():
                continue
            event_count += 1
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                return None, {
                    "type": "provider_session_transport_error",
                    "message": "Session transport is not valid JSONL",
                    "context": {"line": line_number, "error": str(exc)},
                }

            if not isinstance(event, dict):
                return None, {
                    "type": "provider_session_transport_error",
                    "message": "Session transport event must be a JSON object",
                    "context": {"line": line_number},
                }

            session_id = event.get("session_id")
            if isinstance(session_id, str) and session_id:
                session_ids.add(session_id)

            event_type = event.get("type")
            if isinstance(event_type, str) and (
                event_type.endswith("completed")
                or event_type in {"completed", "done"}
            ):
                terminal_seen = True
            if event.get("status") == "completed":
                terminal_seen = True

            if event.get("role") == "assistant":
                if isinstance(event.get("text"), str):
                    text_parts.append(event["text"])
                elif isinstance(event.get("delta"), str):
                    text_parts.append(event["delta"])
                continue

            if isinstance(event.get("text"), str) and isinstance(event_type, str) and "assistant" in event_type:
                text_parts.append(event["text"])
            elif isinstance(event.get("delta"), str) and isinstance(event_type, str) and "assistant" in event_type:
                text_parts.append(event["delta"])

        if not terminal_seen:
            return None, {
                "type": "provider_session_transport_error",
                "message": "Session transport is missing a terminal completion marker",
                "context": {"events": event_count},
            }

        if not session_ids:
            return None, {
                "type": "provider_session_transport_error",
                "message": "Session transport did not expose a session_id",
                "context": {"events": event_count},
            }

        if len(session_ids) != 1:
            return None, {
                "type": "provider_session_transport_error",
                "message": "Session transport exposed conflicting session identifiers",
                "context": {"session_ids": sorted(session_ids)},
            }

        session_id = next(iter(session_ids))
        if expected_session_id is not None and session_id != expected_session_id:
            return None, {
                "type": "provider_session_transport_error",
                "message": "Session transport did not match the requested session_id",
                "context": {
                    "expected_session_id": expected_session_id,
                    "observed_session_id": session_id,
                },
            }

        return {
            "session_id": session_id,
            "normalized_stdout": "".join(text_parts),
            "event_count": event_count,
        }, None
