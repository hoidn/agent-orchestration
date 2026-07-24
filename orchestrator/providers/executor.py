"""Provider executor for running provider commands."""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from .types import (
    CALL_POLICY_OPTION_ORDER,
    InputMode,
    ProviderInvocation,
    ProviderParams,
    ProviderSessionMode,
    ProviderSessionRequest,
    escape_provider_command_token,
    extract_provider_command_placeholders,
    restore_provider_command_token,
)
from .registry import ProviderRegistry
from .control import ProviderExecutionControl
from .session_transport import (
    CodexExecJsonlAccumulator,
    SessionIdentitySnapshot,
    create_session_transport_accumulator,
    extract_codex_assistant_text,
)
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
    classification: Optional[str] = None


class ProviderExecutor:
    """
    Executes provider commands with proper input handling.

    Handles argv vs stdin modes, placeholder substitution, and validation
    per specs/providers.md.
    """

    _CONTROL_WAIT_SLICE_SEC = 0.01
    _CONTROL_CAPTURE_FAILURE_GRACE_SEC = 0.2
    _CONTROL_STDIN_FAILURE_GRACE_SEC = 0.2
    _CONTROL_TIMEOUT_GRACE_SEC = 2.0

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
        provider_call_policy: Optional[Dict[str, str]] = None,
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
            provider_call_policy: Compiler-owned canonical model/effort overrides

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

        translated_policy: Dict[str, str] = {}
        policy_fragments: Dict[str, Tuple[str, ...]] = {}
        if provider_call_policy is not None:
            for canonical_option in provider_call_policy:
                if canonical_option not in CALL_POLICY_OPTION_ORDER:
                    return None, self._unsupported_call_policy_error(
                        provider_name,
                        canonical_option,
                    )
            for canonical_option in CALL_POLICY_OPTION_ORDER:
                if canonical_option not in provider_call_policy:
                    continue
                binding = provider.call_policy_bindings.get(canonical_option)
                if binding is None:
                    return None, self._unsupported_call_policy_error(
                        provider_name,
                        canonical_option,
                    )
                translated_policy[binding.target_param] = provider_call_policy[
                    canonical_option
                ]
                if binding.argv_fragment is not None:
                    policy_fragments[canonical_option] = tuple(binding.argv_fragment)

        # Merge parameters (step params override defaults; policy overrides both)
        merged_params = self.registry.merge_params(provider_name, params.params or {})
        merged_params.update(translated_policy)

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

        if policy_fragments:
            command_template = list(command_template)
            for canonical_option in CALL_POLICY_OPTION_ORDER:
                fragment = policy_fragments.get(canonical_option)
                if fragment is not None:
                    command_template.extend(fragment)

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

    @staticmethod
    def _unsupported_call_policy_error(
        provider_name: str,
        canonical_option: str,
    ) -> Dict[str, Any]:
        """Build the bounded pre-invocation unsupported-policy failure."""
        return {
            "type": "provider_call_policy_unsupported",
            "message": "Provider call policy option is not supported",
            "context": {
                "provider": provider_name,
                "option": canonical_option,
            },
        }

    def execute(
        self,
        invocation: ProviderInvocation,
        cwd: Optional[Path] = None,
        stream_output: bool = False,
        session_runtime: Optional[Dict[str, Any]] = None,
        control: Optional[ProviderExecutionControl] = None,
    ) -> ProviderExecutionResult:
        """
        Execute a prepared provider invocation.

        Args:
            invocation: Provider invocation to execute
            cwd: Working directory (default: workspace)
            control: Optional cancellable process-group lifecycle

        Returns:
            Execution result with output and metadata
        """
        working_dir = cwd or self.workspace
        start_time = time.time()

        if control is not None:
            return self._execute_controlled_invocation(
                invocation=invocation,
                working_dir=working_dir,
                stream_output=stream_output,
                start_time=start_time,
                session_runtime=session_runtime,
                control=control,
            )

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
                if invocation.terminate_process_tree:
                    process = subprocess.Popen(
                        invocation.command,
                        cwd=str(working_dir),
                        env=process_env,
                        stdin=subprocess.PIPE if stdin_input is not None else subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        start_new_session=True,
                    )
                    try:
                        stdout, stderr = process.communicate(
                            input=stdin_input,
                            timeout=invocation.timeout_sec,
                        )
                        duration_ms = int((time.time() - start_time) * 1000)
                        return ProviderExecutionResult(
                            exit_code=process.returncode,
                            stdout=stdout,
                            stderr=stderr,
                            duration_ms=duration_ms,
                        )
                    except subprocess.TimeoutExpired as exc:
                        self._terminate_process_tree(process)
                        stdout, stderr = process.communicate()
                        duration_ms = int((time.time() - start_time) * 1000)
                        return ProviderExecutionResult(
                            exit_code=124,
                            stdout=(exc.stdout or b"") + (stdout or b""),
                            stderr=(exc.stderr or b"") + (stderr or b""),
                            duration_ms=duration_ms,
                            error={
                                "type": "timeout",
                                "message": f"Provider timed out after {invocation.timeout_sec} seconds",
                                "context": {"timeout_sec": invocation.timeout_sec},
                            },
                        )

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
                start_new_session=invocation.terminate_process_tree,
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
                if invocation.terminate_process_tree:
                    self._terminate_process_tree(process)
                else:
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

    def _execute_controlled_invocation(
        self,
        *,
        invocation: ProviderInvocation,
        working_dir: Path,
        stream_output: bool,
        start_time: float,
        session_runtime: Optional[Dict[str, Any]],
        control: ProviderExecutionControl,
    ) -> ProviderExecutionResult:
        """Execute one opt-in invocation inside a runtime-owned process group."""
        expected_session_id: Optional[str] = None
        accumulator: CodexExecJsonlAccumulator | None = None

        def _emit_assistant_text(assistant_text: str) -> None:
            if accumulator is None:
                return
            snapshot = accumulator.snapshot()
            if snapshot.status in {"ambiguous", "invalid"}:
                return
            if (
                expected_session_id is not None
                and snapshot.status == "unique"
                and snapshot.session_ids != (expected_session_id,)
            ):
                return
            self._emit_session_assistant_text(assistant_text)

        try:
            control.claim_spawn()
        except Exception as exc:
            return self._controlled_launch_failure_result(
                error=exc,
                start_time=start_time,
            )

        try:
            process_env = os.environ.copy()
            if invocation.env:
                process_env.update(invocation.env)
            stdin_input = None
            if invocation.input_mode == InputMode.STDIN and invocation.prompt:
                stdin_input = invocation.prompt.encode("utf-8")
            logger.debug(f"Executing command: {invocation.command}")
            if invocation.input_mode == InputMode.STDIN:
                logger.debug(
                    "Using stdin mode, prompt size: "
                    f"{len(invocation.prompt or '')} bytes"
                )
            expected_session_id = self._expected_session_id(invocation)
            accumulator = create_session_transport_accumulator(
                invocation.metadata_mode,
                assistant_text_callback=(
                    _emit_assistant_text if stream_output else None
                ),
            )
            if accumulator is not None:
                control.publish_session_snapshot(accumulator.snapshot())
            process = subprocess.Popen(
                invocation.command,
                cwd=str(working_dir),
                env=process_env,
                stdin=(
                    subprocess.PIPE
                    if stdin_input is not None
                    else subprocess.DEVNULL
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except Exception as exc:
            control.spawn_failed(exc)
            return self._controlled_launch_failure_result(
                error=exc,
                start_time=start_time,
            )

        # start_new_session makes the leader pid the invocation-owned PGID.
        # Binding is deliberately the first action after successful creation.
        try:
            control.bind(process, process.pid)
        except Exception as exc:
            return self._fail_control_bind(
                process=process,
                control=control,
                start_time=start_time,
                error=exc,
            )

        stdout_buf = bytearray()
        stderr_buf = bytearray()
        capture_threads: List[threading.Thread] = []
        capture_outcomes: Dict[
            str,
            Tuple[bool, Optional[str]],
        ] = {}
        capture_outcome_lock = threading.Lock()
        stdin_threads: List[threading.Thread] = []
        stdin_outcomes: Dict[
            str,
            Tuple[bool, Optional[str]],
        ] = {}
        stdin_outcome_lock = threading.Lock()
        try:
            return self._run_bound_controlled_invocation(
                invocation=invocation,
                process=process,
                stdin_input=stdin_input,
                stream_output=stream_output,
                start_time=start_time,
                session_runtime=session_runtime,
                control=control,
                accumulator=accumulator,
                expected_session_id=expected_session_id,
                stdout_buf=stdout_buf,
                stderr_buf=stderr_buf,
                capture_threads=capture_threads,
                capture_outcomes=capture_outcomes,
                capture_outcome_lock=capture_outcome_lock,
                stdin_threads=stdin_threads,
                stdin_outcomes=stdin_outcomes,
                stdin_outcome_lock=stdin_outcome_lock,
            )
        except Exception as exc:
            return self._fail_bound_controlled_invocation(
                invocation=invocation,
                process=process,
                stdin_input=stdin_input,
                start_time=start_time,
                control=control,
                accumulator=accumulator,
                expected_session_id=expected_session_id,
                stdout_buf=stdout_buf,
                stderr_buf=stderr_buf,
                capture_threads=capture_threads,
                capture_outcomes=capture_outcomes,
                capture_outcome_lock=capture_outcome_lock,
                stdin_threads=stdin_threads,
                stdin_outcomes=stdin_outcomes,
                stdin_outcome_lock=stdin_outcome_lock,
                error=exc,
            )

    @staticmethod
    def _controlled_launch_failure_result(
        *,
        error: BaseException,
        start_time: float,
    ) -> ProviderExecutionResult:
        return ProviderExecutionResult(
            exit_code=1,
            stdout=b"",
            stderr=str(error).encode("utf-8"),
            duration_ms=int((time.time() - start_time) * 1000),
            classification="failed",
            raw_stdout=b"",
            error={
                "type": "execution_error",
                "message": str(error),
                "context": {},
            },
        )

    def _fail_control_bind(
        self,
        *,
        process: subprocess.Popen,
        control: ProviderExecutionControl,
        start_time: float,
        error: Exception,
    ) -> ProviderExecutionResult:
        """Clean and reap a process whose control binding was rejected."""
        pgid = process.pid
        term_sent = True
        kill_sent = False
        cleanup_errors: List[str] = []
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as exc:
            cleanup_errors.append(f"failed to terminate process group: {exc}")

        leader_reaped = False
        return_code: int | None = None
        try:
            return_code = process.wait(timeout=0.2)
            leader_reaped = True
        except subprocess.TimeoutExpired:
            kill_sent = True
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as exc:
                cleanup_errors.append(f"failed to kill process group: {exc}")
            try:
                return_code = process.wait()
                leader_reaped = True
            except Exception as exc:
                cleanup_errors.append(f"failed to reap process leader: {exc}")
        except Exception as exc:
            cleanup_errors.append(f"failed to reap process leader: {exc}")

        if not self._wait_for_process_group_empty(pgid, timeout=0.2):
            if not kill_sent:
                kill_sent = True
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    cleanup_errors.append(
                        f"failed to kill residual process group: {exc}"
                    )
            if not self._wait_for_process_group_empty(pgid, timeout=0.2):
                cleanup_errors.append("provider process group remained non-empty")
        pgid_empty = self._process_group_is_empty(pgid)

        if process.stdin is not None:
            try:
                process.stdin.close()
            except Exception:
                pass
        stdout = b""
        stderr = b""
        for pipe, is_stdout in (
            (process.stdout, True),
            (process.stderr, False),
        ):
            if pipe is None or getattr(pipe, "closed", False):
                continue
            try:
                remainder = pipe.read() or b""
                if is_stdout:
                    stdout += remainder
                else:
                    stderr += remainder
            except Exception as exc:
                cleanup_errors.append(f"failed to read provider pipe: {exc}")
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        terminal_error = str(error)
        if cleanup_errors:
            terminal_error += "; " + "; ".join(cleanup_errors)
        terminal = control.record_bind_failure(
            process=process,
            pgid=pgid,
            return_code=return_code,
            leader_reaped=leader_reaped,
            pgid_empty=pgid_empty,
            term_sent=term_sent,
            kill_sent=kill_sent,
            error=terminal_error,
        )
        return self._controlled_boundary_failure_result(
            terminal=terminal,
            raw_stdout=stdout,
            stderr=stderr,
            duration_ms=int((time.time() - start_time) * 1000),
        )

    @staticmethod
    def _process_group_is_empty(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        return False

    def _wait_for_process_group_empty(
        self,
        pgid: int,
        *,
        timeout: float,
    ) -> bool:
        deadline = time.monotonic() + max(timeout, 0.0)
        while True:
            if self._process_group_is_empty(pgid):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def _run_bound_controlled_invocation(
        self,
        *,
        invocation: ProviderInvocation,
        process: subprocess.Popen,
        stdin_input: Optional[bytes],
        stream_output: bool,
        start_time: float,
        session_runtime: Optional[Dict[str, Any]],
        control: ProviderExecutionControl,
        accumulator: CodexExecJsonlAccumulator | None,
        expected_session_id: Optional[str],
        stdout_buf: bytearray,
        stderr_buf: bytearray,
        capture_threads: List[threading.Thread],
        capture_outcomes: Dict[str, Tuple[bool, Optional[str]]],
        capture_outcome_lock: Any,
        stdin_threads: List[threading.Thread],
        stdin_outcomes: Dict[str, Tuple[bool, Optional[str]]],
        stdin_outcome_lock: Any,
    ) -> ProviderExecutionResult:
        """Run capture, wait, transport finalization, and boundary recording."""
        stdout_callback: Optional[Callable[[bytes], None]] = None
        if accumulator is not None:
            stdout_callback = self._build_session_stdout_callback(
                invocation=invocation,
                stream_output=stream_output,
                session_runtime=session_runtime,
                accumulator=accumulator,
                identity_snapshot_callback=control.publish_session_snapshot,
            )

        stdout_thread = threading.Thread(
            target=self._capture_controlled_pipe,
            args=(process.stdout, stdout_buf),
            kwargs={
                "stream_name": "stdout",
                "capture_outcomes": capture_outcomes,
                "capture_outcome_lock": capture_outcome_lock,
                "control": control,
                "session_accumulator": accumulator,
                "out_stream": (
                    sys.stdout
                    if stream_output and accumulator is None
                    else None
                ),
                "chunk_callback": stdout_callback,
                "read_mode": "lines" if accumulator is not None else "chunks",
            },
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._capture_controlled_pipe,
            args=(process.stderr, stderr_buf),
            kwargs={
                "stream_name": "stderr",
                "capture_outcomes": capture_outcomes,
                "capture_outcome_lock": capture_outcome_lock,
                "control": control,
                "out_stream": sys.stderr if stream_output else None,
            },
            daemon=True,
        )
        capture_threads.extend((stdout_thread, stderr_thread))
        stdin_thread: threading.Thread | None = None
        if stdin_input is not None:
            stdin_thread = threading.Thread(
                target=self._write_controlled_stdin,
                args=(process.stdin, stdin_input),
                kwargs={
                    "stdin_outcomes": stdin_outcomes,
                    "stdin_outcome_lock": stdin_outcome_lock,
                    "control": control,
                },
                name=f"provider-stdin-{process.pid}",
                daemon=True,
            )
            stdin_threads.append(stdin_thread)

        stdout_thread.start()
        stderr_thread.start()
        if stdin_thread is not None:
            stdin_thread.start()

        exit_code, timed_out = self._wait_for_controlled_process(
            process=process,
            control=control,
            timeout_sec=invocation.timeout_sec,
        )

        control.record_leader_reaped(exit_code)
        for thread in stdin_threads:
            if thread.ident is not None:
                thread.join()
        stdout_thread.join()
        stderr_thread.join()
        capture_threads_joined = (
            not stdout_thread.is_alive() and not stderr_thread.is_alive()
        )

        final_identity_valid = invocation.session_request is None
        if accumulator is not None:
            _, identity_error = accumulator.finalize(
                expected_session_id=expected_session_id,
                require_terminal=False,
            )
            control.publish_session_snapshot(accumulator.snapshot())
            final_identity_valid = identity_error is None

        duration_ms = int((time.time() - start_time) * 1000)
        raw_stdout = bytes(stdout_buf)
        stderr = bytes(stderr_buf)
        natural_result: ProviderExecutionResult
        if accumulator is not None:
            natural_result = self._finalize_session_result(
                invocation=invocation,
                exit_code=exit_code,
                raw_stdout=raw_stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                stream_output=stream_output,
                accumulator=accumulator,
            )
            natural_result.classification = (
                "normal"
                if (
                    natural_result.exit_code == 0
                    and natural_result.error is None
                )
                else "failed"
            )
        else:
            natural_result = ProviderExecutionResult(
                exit_code=exit_code,
                stdout=raw_stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                classification="normal" if exit_code == 0 else "failed",
                raw_stdout=raw_stdout,
            )

        capture_errors = self._capture_outcome_errors(
            capture_outcomes,
            capture_outcome_lock,
        )
        stdin_errors = self._stdin_outcome_errors(
            stdin_required=stdin_input is not None,
            stdin_outcomes=stdin_outcomes,
            stdin_outcome_lock=stdin_outcome_lock,
        )
        boundary_errors = [*stdin_errors, *capture_errors]
        boundary = control.record_execution_boundary(
            capture_threads_joined=capture_threads_joined,
            final_identity_valid=final_identity_valid,
            transport_failed=natural_result.error is not None,
            boundary_error=(
                "; ".join(boundary_errors)
                if boundary_errors
                else None
            ),
        )

        if boundary.disposition == "boundary_failed":
            return self._controlled_boundary_failure_result(
                terminal=boundary,
                raw_stdout=raw_stdout,
                stderr=stderr,
                duration_ms=duration_ms,
            )

        if timed_out:
            return ProviderExecutionResult(
                exit_code=124,
                stdout=b"",
                stderr=stderr,
                duration_ms=duration_ms,
                classification="failed",
                raw_stdout=raw_stdout,
                error={
                    "type": "timeout",
                    "message": (
                        f"Provider timed out after "
                        f"{invocation.timeout_sec} seconds"
                    ),
                    "context": {"timeout_sec": invocation.timeout_sec},
                },
            )

        if boundary.disposition == "cancelled":
            return ProviderExecutionResult(
                exit_code=(
                    boundary.leader_return_code
                    if boundary.leader_return_code is not None
                    else 1
                ),
                stdout=b"",
                stderr=stderr,
                duration_ms=duration_ms,
                classification="cancelled_provisional",
                raw_stdout=raw_stdout,
                normalized_stdout=None,
                provider_session=None,
            )

        return natural_result

    def _wait_for_controlled_process(
        self,
        *,
        process: subprocess.Popen,
        control: ProviderExecutionControl,
        timeout_sec: Optional[int],
    ) -> Tuple[int, bool]:
        """Linearize completion and cancellation on the executor thread."""
        deadline = (
            None
            if timeout_sec is None
            else time.monotonic() + timeout_sec
        )
        timed_out = False

        while True:
            try:
                return process.wait(timeout=0), timed_out
            except subprocess.TimeoutExpired:
                pass

            now = time.monotonic()
            if (
                not timed_out
                and deadline is not None
                and now >= deadline
            ):
                timed_out = True
                control.request_cancel(
                    reason="timeout",
                    grace=self._CONTROL_TIMEOUT_GRACE_SEC,
                )

            control.apply_pending_cancellation_after_incomplete_probe()

            wait_slice = self._CONTROL_WAIT_SLICE_SEC
            if not timed_out and deadline is not None:
                wait_slice = min(
                    wait_slice,
                    max(deadline - now, 0.0),
                )
                if wait_slice == 0:
                    continue
            try:
                return process.wait(timeout=wait_slice), timed_out
            except subprocess.TimeoutExpired:
                continue

    def _fail_bound_controlled_invocation(
        self,
        *,
        invocation: ProviderInvocation,
        process: subprocess.Popen,
        stdin_input: Optional[bytes],
        start_time: float,
        control: ProviderExecutionControl,
        accumulator: CodexExecJsonlAccumulator | None,
        expected_session_id: Optional[str],
        stdout_buf: bytearray,
        stderr_buf: bytearray,
        capture_threads: List[threading.Thread],
        capture_outcomes: Dict[str, Tuple[bool, Optional[str]]],
        capture_outcome_lock: Any,
        stdin_threads: List[threading.Thread],
        stdin_outcomes: Dict[str, Tuple[bool, Optional[str]]],
        stdin_outcome_lock: Any,
        error: Exception,
    ) -> ProviderExecutionResult:
        """Fail closed after bind while preserving executor-owned wait."""
        control.request_cancel(
            reason="execution_error",
            grace=self._CONTROL_CAPTURE_FAILURE_GRACE_SEC,
        )
        exit_code, _ = self._wait_for_controlled_process(
            process=process,
            control=control,
            timeout_sec=None,
        )
        control.record_leader_reaped(exit_code)

        for thread in stdin_threads:
            if thread.ident is not None:
                thread.join()
        for thread in capture_threads:
            if thread.ident is not None:
                thread.join()

        stdin_close_error: str | None = None
        if (
            process.stdin is not None
            and not getattr(process.stdin, "closed", False)
        ):
            try:
                process.stdin.close()
            except BrokenPipeError:
                if not control.cancellation_was_applied_before_completion():
                    stdin_close_error = (
                        "stdin writer failed (BrokenPipeError) while closing"
                    )
            except BaseException as exc:
                stdin_close_error = (
                    "stdin writer failed while closing "
                    f"({type(exc).__name__}): {exc}"
                )

        for pipe, buffer in (
            (process.stdout, stdout_buf),
            (process.stderr, stderr_buf),
        ):
            if pipe is None or getattr(pipe, "closed", False):
                continue
            try:
                remainder = pipe.read()
                if remainder:
                    buffer.extend(remainder)
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        final_identity_valid = invocation.session_request is None
        if accumulator is not None:
            _, identity_error = accumulator.finalize(
                expected_session_id=expected_session_id,
                require_terminal=False,
            )
            control.publish_session_snapshot(accumulator.snapshot())
            final_identity_valid = identity_error is None

        boundary_errors = [
            f"provider execution failed after bind: {error}",
            *self._stdin_outcome_errors(
                stdin_required=stdin_input is not None,
                stdin_outcomes=stdin_outcomes,
                stdin_outcome_lock=stdin_outcome_lock,
            ),
            *self._capture_outcome_errors(
                capture_outcomes,
                capture_outcome_lock,
            ),
        ]
        if stdin_close_error is not None:
            boundary_errors.append(stdin_close_error)
        boundary = control.record_execution_boundary(
            capture_threads_joined=all(
                not thread.is_alive()
                for thread in capture_threads
            ),
            final_identity_valid=final_identity_valid,
            boundary_error="; ".join(boundary_errors),
        )
        return self._controlled_boundary_failure_result(
            terminal=boundary,
            raw_stdout=bytes(stdout_buf),
            stderr=bytes(stderr_buf),
            duration_ms=int((time.time() - start_time) * 1000),
        )

    @staticmethod
    def _controlled_boundary_failure_result(
        *,
        terminal: Any,
        raw_stdout: bytes,
        stderr: bytes,
        duration_ms: int,
    ) -> ProviderExecutionResult:
        return ProviderExecutionResult(
            exit_code=(
                terminal.leader_return_code
                if terminal.leader_return_code is not None
                else 1
            ),
            stdout=b"",
            stderr=stderr,
            duration_ms=duration_ms,
            classification="failed",
            raw_stdout=raw_stdout,
            normalized_stdout=None,
            provider_session=None,
            error={
                "type": "provider_cancellation_boundary_failed",
                "message": (
                    terminal.error
                    or "Provider cancellation boundary could not be proved"
                ),
                "context": {
                    "leader_reaped": terminal.leader_reaped,
                    "pgid_empty": terminal.pgid_empty,
                    "capture_threads_joined": (
                        terminal.capture_threads_joined
                    ),
                    "execution_joined": getattr(
                        terminal,
                        "execution_joined",
                        False,
                    ),
                    "final_identity_valid": terminal.final_identity_valid,
                },
            },
        )

    def _terminate_process_tree(self, process: subprocess.Popen) -> None:
        """Terminate a managed provider process group with a hard-kill fallback."""
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            process.terminate()
        try:
            process.wait(timeout=2)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except Exception:
            process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

    def _write_controlled_stdin(
        self,
        pipe: Optional[Any],
        stdin_input: bytes,
        *,
        stdin_outcomes: Dict[
            str,
            Tuple[bool, Optional[str]],
        ],
        stdin_outcome_lock: Any,
        control: ProviderExecutionControl,
    ) -> None:
        """Deliver controlled stdin without blocking the executor arbiter."""
        failure: str | None = None
        try:
            if pipe is None:
                raise RuntimeError("provider stdin pipe is unavailable")
            written = pipe.write(stdin_input)
            if written != len(stdin_input):
                raise OSError(
                    "provider stdin writer completed a short write "
                    f"({written!r} of {len(stdin_input)} bytes)"
                )
        except BrokenPipeError as exc:
            if not control.cancellation_was_applied_before_completion():
                failure = (
                    "stdin writer failed "
                    f"(BrokenPipeError): {exc}"
                )
        except BaseException as exc:
            failure = (
                "stdin writer failed "
                f"({type(exc).__name__}): {exc}"
            )
        finally:
            if pipe is not None:
                try:
                    pipe.close()
                except BrokenPipeError as exc:
                    if (
                        failure is None
                        and not control.cancellation_was_applied_before_completion()
                    ):
                        failure = (
                            "stdin writer failed while closing "
                            f"(BrokenPipeError): {exc}"
                        )
                except BaseException as exc:
                    if failure is None:
                        failure = (
                            "stdin writer failed while closing "
                            f"({type(exc).__name__}): {exc}"
                        )

            with stdin_outcome_lock:
                stdin_outcomes["stdin"] = (
                    failure is None,
                    failure,
                )

        if failure is not None:
            control.request_cancel(
                reason="stdin_writer_failure",
                grace=self._CONTROL_STDIN_FAILURE_GRACE_SEC,
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

        output = out_stream
        if out_stream is not None:
            try:
                output = getattr(out_stream, "buffer", out_stream)
            except BaseException:
                output = None
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
                    except BaseException:
                        pass
                if output is not None:
                    try:
                        output.write(chunk)
                        output.flush()
                    except BaseException:
                        # Streaming should never break execution/capture path.
                        pass
        finally:
            try:
                pipe.close()
            except BaseException:
                pass

    def _capture_controlled_pipe(
        self,
        pipe: Optional[Any],
        buffer: bytearray,
        *,
        stream_name: str,
        capture_outcomes: Dict[
            str,
            Tuple[bool, Optional[str]],
        ],
        capture_outcome_lock: Any,
        control: ProviderExecutionControl,
        session_accumulator: CodexExecJsonlAccumulator | None = None,
        **capture_kwargs: Any,
    ) -> None:
        """Capture one controlled pipe and retain core worker failures."""
        try:
            self._capture_pipe(
                pipe,
                buffer,
                **capture_kwargs,
            )
            if session_accumulator is not None:
                session_accumulator.finalize(
                    expected_session_id=None,
                    require_terminal=False,
                )
                snapshot = session_accumulator.snapshot()
                if not snapshot.terminal_seen:
                    control.record_missing_terminal_at_session_stdout_eof(
                        snapshot
                    )
                control.publish_session_snapshot(snapshot)
        except BaseException as exc:
            failure = (
                f"{stream_name} capture worker failed "
                f"({type(exc).__name__}): {exc}"
            )
            with capture_outcome_lock:
                capture_outcomes[stream_name] = (False, failure)
            control.request_cancel(
                reason=f"{stream_name}_capture_failure",
                grace=self._CONTROL_CAPTURE_FAILURE_GRACE_SEC,
            )
        else:
            with capture_outcome_lock:
                capture_outcomes[stream_name] = (True, None)

    @staticmethod
    def _capture_outcome_errors(
        capture_outcomes: Dict[
            str,
            Tuple[bool, Optional[str]],
        ],
        capture_outcome_lock: Any,
    ) -> List[str]:
        """Return stable errors for failed or non-reporting core workers."""
        with capture_outcome_lock:
            outcomes = dict(capture_outcomes)

        errors: List[str] = []
        for stream_name in ("stdout", "stderr"):
            outcome = outcomes.get(stream_name)
            if outcome is None:
                errors.append(
                    f"{stream_name} capture worker did not report an outcome"
                )
                continue
            succeeded, failure = outcome
            if not succeeded:
                errors.append(
                    failure
                    or f"{stream_name} capture worker failed"
                )
        return errors

    @staticmethod
    def _stdin_outcome_errors(
        *,
        stdin_required: bool,
        stdin_outcomes: Dict[
            str,
            Tuple[bool, Optional[str]],
        ],
        stdin_outcome_lock: Any,
    ) -> List[str]:
        """Return the explicit owned-writer failure, if any."""
        if not stdin_required:
            return []
        with stdin_outcome_lock:
            outcome = stdin_outcomes.get("stdin")
        if outcome is None:
            return ["stdin writer did not report an outcome"]
        succeeded, failure = outcome
        if succeeded:
            return []
        return [failure or "stdin writer failed"]

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
            missing_variables: set[str] = set()

            def substitute_value(value: Any) -> Any:
                if isinstance(value, dict):
                    return {
                        key: substitute_value(nested_value)
                        for key, nested_value in value.items()
                    }
                if isinstance(value, list):
                    return [substitute_value(item) for item in value]
                substituted_value = substitutor.substitute(
                    value,
                    context,
                    track_undefined=False,
                )
                missing_variables.update(substitutor.undefined_vars)
                return substituted_value

            # Traverse once while retaining missing variables across nested entries.
            substituted_result = substitute_value(params)
            # Ensure the result is a dict (since we passed in a dict)
            if not isinstance(substituted_result, dict):
                errors.append(f"Parameter substitution returned unexpected type: {type(substituted_result)}")
                return params, errors
            substituted = substituted_result

            # Check for undefined variables
            if missing_variables:
                for var in sorted(missing_variables):
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
        command = []
        missing = set()
        invalid_prompt = False

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
            for var in extract_provider_command_placeholders(token):
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
            expected_session_id = self._expected_session_id(invocation)
            accumulator: CodexExecJsonlAccumulator | None = None

            def _emit_assistant_text(assistant_text: str) -> None:
                if accumulator is None:
                    return
                snapshot = accumulator.snapshot()
                if snapshot.status in {"ambiguous", "invalid"}:
                    return
                if (
                    expected_session_id is not None
                    and snapshot.status == "unique"
                    and snapshot.session_ids != (expected_session_id,)
                ):
                    return
                self._emit_session_assistant_text(assistant_text)

            accumulator = create_session_transport_accumulator(
                invocation.metadata_mode,
                assistant_text_callback=(
                    _emit_assistant_text if stream_output else None
                ),
            )
            stdout_callback = self._build_session_stdout_callback(
                invocation=invocation,
                stream_output=stream_output,
                session_runtime=session_runtime,
                accumulator=accumulator,
            )

            stdout_thread = threading.Thread(
                target=self._capture_pipe,
                args=(process.stdout, stdout_buf),
                kwargs={
                    "chunk_callback": stdout_callback,
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
                accumulator=accumulator,
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

    def _build_session_stdout_callback(
        self,
        *,
        invocation: ProviderInvocation,
        stream_output: bool,
        session_runtime: Optional[Dict[str, Any]],
        accumulator: CodexExecJsonlAccumulator | None = None,
        identity_snapshot_callback: Optional[
            Callable[[SessionIdentitySnapshot], None]
        ] = None,
    ) -> Callable[[bytes], None]:
        """Build the session stdout handler used during live pipe capture."""
        if accumulator is None:
            accumulator = create_session_transport_accumulator(
                invocation.metadata_mode,
                assistant_text_callback=(
                    self._emit_session_assistant_text if stream_output else None
                ),
            )

        def _handle_chunk(chunk: bytes) -> None:
            if accumulator is not None:
                accumulator.feed(chunk)
                if identity_snapshot_callback is not None:
                    identity_snapshot_callback(accumulator.snapshot())
            self._append_masked_transport(chunk, session_runtime)

        return _handle_chunk

    def _stream_codex_jsonl_chunk(
        self,
        raw_chunk: bytes,
        *,
        expected_session_id: Optional[str],
        stream_state: Dict[str, Any],
    ) -> None:
        """Compatibility wrapper around the shared incremental JSONL codec."""
        if stream_state.get("blocked"):
            return

        accumulator = stream_state.get("accumulator")
        if not isinstance(accumulator, CodexExecJsonlAccumulator):

            def _emit_if_valid(assistant_text: str) -> None:
                active_accumulator = stream_state.get("accumulator")
                if not isinstance(active_accumulator, CodexExecJsonlAccumulator):
                    return
                snapshot = active_accumulator.snapshot()
                if snapshot.status in {"ambiguous", "invalid"}:
                    return
                if (
                    expected_session_id is not None
                    and snapshot.status == "unique"
                    and snapshot.session_ids != (expected_session_id,)
                ):
                    return
                self._emit_session_assistant_text(assistant_text)

            accumulator = CodexExecJsonlAccumulator(
                assistant_text_callback=_emit_if_valid,
            )
            stream_state["accumulator"] = accumulator

        accumulator.feed(raw_chunk)
        snapshot = accumulator.snapshot()
        stream_state["session_ids"] = set(snapshot.session_ids)
        if snapshot.status in {"ambiguous", "invalid"}:
            stream_state["blocked"] = True
        elif (
            expected_session_id is not None
            and snapshot.status == "unique"
            and snapshot.session_ids != (expected_session_id,)
        ):
            stream_state["blocked"] = True

    def _finalize_session_result(
        self,
        *,
        invocation: ProviderInvocation,
        exit_code: int,
        raw_stdout: bytes,
        stderr: bytes,
        duration_ms: int,
        stream_output: bool,
        accumulator: CodexExecJsonlAccumulator | None = None,
    ) -> ProviderExecutionResult:
        """Parse session transport and emit normalized assistant text."""
        normalized_stdout = b""
        provider_session: Dict[str, Any] | None = None
        error = None
        if accumulator is None:
            accumulator = create_session_transport_accumulator(
                invocation.metadata_mode,
            )
            if accumulator is not None:
                accumulator.feed(raw_stdout)
        if accumulator is not None:
            parsed_session, parse_error = accumulator.finalize(
                expected_session_id=self._expected_session_id(invocation),
                require_terminal=True,
            )
            provider_session = (
                dict(parsed_session) if parsed_session is not None else None
            )
            error = dict(parse_error) if parse_error is not None else None
            if error is None and provider_session is not None:
                normalized_stdout = str(
                    provider_session.get("normalized_stdout", "")
                ).encode("utf-8")

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
        """Compatibility delegator for callers of the former final parser."""
        accumulator = CodexExecJsonlAccumulator()
        accumulator.feed(raw_stdout)
        provider_session, error = accumulator.finalize(
            expected_session_id=expected_session_id,
            require_terminal=True,
        )
        return (
            dict(provider_session) if provider_session is not None else None,
            dict(error) if error is not None else None,
        )

    def _extract_assistant_text(self, event: Dict[str, Any]) -> Optional[str]:
        """Compatibility delegator for assistant-text extraction."""
        return extract_codex_assistant_text(event)

    @staticmethod
    def _expected_session_id(
        invocation: ProviderInvocation,
    ) -> Optional[str]:
        if (
            invocation.session_request is not None
            and invocation.session_request.mode == ProviderSessionMode.RESUME
        ):
            return invocation.session_request.session_id
        return None

    @staticmethod
    def _emit_session_assistant_text(assistant_text: str) -> None:
        output = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else sys.stdout
        output.write(assistant_text.encode("utf-8"))
        output.flush()
