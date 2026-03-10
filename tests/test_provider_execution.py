"""
Tests for provider execution per specs/providers.md and acceptance tests.

Tests provider registry, template validation, argv/stdin modes, placeholder
substitution, and error handling.
"""

import pytest
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from orchestrator.providers import (
    ProviderTemplate,
    ProviderParams,
    ProviderRegistry,
    ProviderExecutor,
    InputMode,
    ProviderSessionMetadataMode,
    ProviderSessionMode,
    ProviderSessionRequest,
    ProviderSessionSupport,
)
from orchestrator.providers.types import ProviderInvocation


class _RecordingBinaryStream:
    """Thread-safe binary stream recorder for live provider streaming assertions."""

    def __init__(self):
        self.buffer = self
        self._chunks = []
        self._lock = threading.Lock()
        self.first_write_at = None

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        with self._lock:
            if self.first_write_at is None:
                self.first_write_at = time.time()
            self._chunks.append(bytes(data))
        return len(data)

    def flush(self):
        return None

    def getvalue(self) -> bytes:
        with self._lock:
            return b"".join(self._chunks)


class TestProviderRegistry:
    """Test provider registry functionality."""

    def test_builtin_providers(self):
        """Test that built-in providers are available."""
        registry = ProviderRegistry()

        # Check built-in providers exist
        assert registry.exists("claude")
        assert registry.exists("gemini")
        assert registry.exists("codex")

        # Check claude template
        claude = registry.get("claude")
        assert claude.name == "claude"
        assert claude.input_mode == InputMode.ARGV
        assert "${PROMPT}" in " ".join(claude.command)
        assert claude.defaults.get("model") == "claude-opus-4-6"

        # Check codex template (stdin mode)
        codex = registry.get("codex")
        assert codex.name == "codex"
        assert codex.input_mode == InputMode.STDIN
        assert "${PROMPT}" not in " ".join(codex.command)
        assert codex.defaults.get("model") == "gpt-5.3-codex"
        assert codex.defaults.get("reasoning_effort") == "high"
        command_str = " ".join(codex.command)
        assert "--config" in command_str
        assert "reasoning_effort=${reasoning_effort}" in command_str
        assert codex.session_support is not None
        assert codex.session_support.metadata_mode == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
        assert "${SESSION_ID}" in " ".join(codex.session_support.resume_command or [])

    def test_register_custom_provider(self):
        """Test registering a custom provider."""
        registry = ProviderRegistry()

        custom = ProviderTemplate(
            name="custom",
            command=["custom-cli", "--prompt", "${PROMPT}"],
            defaults={"timeout": "30"},
            input_mode=InputMode.ARGV
        )

        registry.register(custom)
        assert registry.exists("custom")

        retrieved = registry.get("custom")
        assert retrieved.name == "custom"
        assert retrieved.defaults["timeout"] == "30"

    def test_at49_stdin_mode_prompt_validation(self):
        """AT-49: Provider with stdin mode cannot have ${PROMPT} in command."""
        registry = ProviderRegistry()

        # Invalid: stdin mode with ${PROMPT}
        invalid = ProviderTemplate(
            name="invalid",
            command=["tool", "-p", "${PROMPT}"],  # Not allowed in stdin
            input_mode=InputMode.STDIN
        )

        errors = invalid.validate()
        assert len(errors) > 0
        assert "${PROMPT} not allowed in stdin mode" in errors[0]

    def test_session_support_resume_command_requires_exactly_one_session_placeholder(self):
        """Resume-capable provider templates must bind exactly one ${SESSION_ID}."""
        invalid = ProviderTemplate(
            name="invalid_resume",
            command=["tool", "--model", "${model}"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json", "--model", "${model}"],
                resume_command=["tool", "resume", "--model", "${model}"],
            ),
        )

        errors = invalid.validate()

        assert any("must contain exactly one ${SESSION_ID} placeholder" in error for error in errors)

    def test_session_support_resume_command_ignores_escaped_session_placeholder(self):
        """Escaped ${SESSION_ID} literals do not satisfy the reserved resume placeholder contract."""
        escaped_only = ProviderTemplate(
            name="escaped_only_resume",
            command=["tool", "--model", "${model}"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json", "--model", "${model}"],
                resume_command=["tool", "resume", "$${SESSION_ID}"],
            ),
        )

        escaped_only_errors = escaped_only.validate()

        assert any(
            "must contain exactly one ${SESSION_ID} placeholder" in error
            for error in escaped_only_errors
        )

        one_real_one_escaped = ProviderTemplate(
            name="resume_with_literal",
            command=["tool", "--model", "${model}"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json", "--model", "${model}"],
                resume_command=["tool", "resume", "$${SESSION_ID}", "${SESSION_ID}"],
            ),
        )

        assert one_real_one_escaped.validate() == []

    def test_session_id_placeholder_is_reserved_for_resume_command(self):
        """${SESSION_ID} is rejected outside session_support.resume_command."""
        invalid = ProviderTemplate(
            name="invalid_placeholder_scope",
            command=["tool", "resume", "${SESSION_ID}"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json", "${SESSION_ID}"],
                resume_command=["tool", "resume", "${SESSION_ID}"],
            ),
        )

        errors = invalid.validate()

        assert any("${SESSION_ID} is only allowed in session_support.resume_command" in error for error in errors)

    def test_merge_params(self):
        """Test parameter merging (step params override defaults)."""
        registry = ProviderRegistry()

        # Get claude with defaults
        defaults = registry.merge_params("claude", None)
        assert defaults["model"] == "claude-opus-4-6"

        # Override with step params
        step_params = {"model": "claude-3-5-sonnet"}
        merged = registry.merge_params("claude", step_params)
        assert merged["model"] == "claude-3-5-sonnet"  # Step wins

        # Additional params
        step_params = {"model": "custom", "temperature": "0.7"}
        merged = registry.merge_params("claude", step_params)
        assert merged["model"] == "custom"
        assert merged["temperature"] == "0.7"


class TestProviderExecutor:
    """Test provider executor functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.registry = ProviderRegistry()
        self.executor = ProviderExecutor(self.workspace, self.registry)

    def test_at8_argv_mode_execution(self):
        """AT-8: Provider templates with argv mode compose correctly."""
        # Create a test prompt file
        prompt_file = self.workspace / "prompt.txt"
        prompt_file.write_text("Test prompt content")

        params = ProviderParams(
            params={"model": "test-model"},
            input_file=str(prompt_file)
        )

        context = {}
        prompt_content = "Test prompt content"

        # Prepare invocation for claude (argv mode)
        invocation, error = self.executor.prepare_invocation(
            "claude",
            params,
            context,
            prompt_content
        )

        assert error is None
        assert invocation is not None
        assert invocation.input_mode == InputMode.ARGV

        # Check command has prompt substituted
        command_str = " ".join(invocation.command)
        assert "Test prompt content" in command_str
        assert "test-model" in command_str

    def test_at9_stdin_mode_execution(self):
        """AT-9: Provider with stdin mode receives prompt via stdin."""
        params = ProviderParams(
            params={"model": "test-model"}
        )

        context = {}
        prompt_content = "Test prompt for stdin"

        # Prepare invocation for codex (stdin mode)
        invocation, error = self.executor.prepare_invocation(
            "codex",
            params,
            context,
            prompt_content
        )

        assert error is None
        assert invocation is not None
        assert invocation.input_mode == InputMode.STDIN
        assert invocation.prompt == "Test prompt for stdin"

        # Command should not have ${PROMPT}
        command_str = " ".join(invocation.command)
        assert "${PROMPT}" not in command_str
        assert "test-model" in command_str

    def test_at48_missing_placeholders(self):
        """AT-48: Missing placeholders cause exit 2 with context."""
        # Register a provider with unresolved placeholder
        custom = ProviderTemplate(
            name="custom",
            command=["tool", "--model", "${model}", "--key", "${api_key}"],
            input_mode=InputMode.ARGV
        )
        self.registry.register(custom)

        params = ProviderParams(
            params={"model": "test"}  # Missing api_key
        )

        context = {}

        invocation, error = self.executor.prepare_invocation(
            "custom",
            params,
            context,
            None
        )

        assert invocation is None
        assert error is not None
        assert error["type"] == "validation_error"
        assert "missing_placeholders" in error["context"]
        assert "api_key" in error["context"]["missing_placeholders"]

    def test_at49_invalid_prompt_placeholder(self):
        """AT-49: stdin mode with ${PROMPT} causes validation error."""
        # Register invalid provider
        invalid = ProviderTemplate(
            name="invalid",
            command=["tool", "-p", "${PROMPT}"],
            input_mode=InputMode.STDIN
        )

        # Note: This should fail at registration
        errors = invalid.validate()
        assert len(errors) > 0

        # Even if we bypass validation, executor should catch it
        self.registry._providers["invalid"] = invalid  # Force registration

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "invalid",
            params,
            context,
            "prompt"
        )

        assert invocation is None
        assert error is not None
        assert error["context"]["invalid_prompt_placeholder"] is True

    def test_at50_argv_without_prompt(self):
        """AT-50: Provider argv mode without ${PROMPT} runs without prompt."""
        # Register provider without ${PROMPT}
        no_prompt = ProviderTemplate(
            name="no_prompt",
            command=["tool", "--model", "${model}"],
            defaults={"model": "default"},
            input_mode=InputMode.ARGV
        )
        self.registry.register(no_prompt)

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "no_prompt",
            params,
            context,
            None  # No prompt
        )

        assert error is None
        assert invocation is not None
        assert "--model" in invocation.command
        assert "default" in invocation.command

    def test_at51_provider_params_substitution(self):
        """AT-51: Variable substitution in provider_params."""
        # Register provider
        custom = ProviderTemplate(
            name="custom",
            command=["tool", "--model", "${model}", "--path", "${output_path}"],
            input_mode=InputMode.ARGV
        )
        self.registry.register(custom)

        params = ProviderParams(
            params={
                "model": "${run.timestamp}",  # Variable reference
                "output_path": "${context.workspace}/output.txt"
            }
        )

        # Properly structured context with namespaces
        context = {
            "run": {
                "timestamp": "20250115T120000Z"
            },
            "context": {
                "workspace": "/workspace"
            }
        }

        invocation, error = self.executor.prepare_invocation(
            "custom",
            params,
            context,
            None
        )

        assert error is None
        assert invocation is not None

        # Check substitution worked
        command_str = " ".join(invocation.command)
        assert "20250115T120000Z" in command_str
        assert "/workspace/output.txt" in command_str

    def test_prepare_invocation_uses_fresh_command_for_provider_session(self):
        """Session-enabled fresh invocations compile the provider fresh_command variant."""
        params = ProviderParams(params={"model": "test-model"})
        invocation, error = self.executor.prepare_invocation(
            "codex",
            params,
            {},
            "Test prompt",
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        assert error is None
        assert invocation is not None
        assert invocation.command_variant == "fresh_command"
        assert invocation.metadata_mode == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
        assert "--json" in invocation.command

    def test_prepare_invocation_uses_resume_command_and_binds_session_id(self):
        """Session-enabled resume invocations bind ${SESSION_ID} through resume_command only."""
        params = ProviderParams(params={"model": "test-model"})
        invocation, error = self.executor.prepare_invocation(
            "codex",
            params,
            {},
            "Test prompt",
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id="sess-123",
            ),
        )

        assert error is None
        assert invocation is not None
        assert invocation.command_variant == "resume_command"
        assert "resume" in invocation.command
        assert "sess-123" in invocation.command

    def test_prepare_invocation_preserves_escaped_session_id_literal(self):
        """Escaped ${SESSION_ID} tokens remain literal while the unescaped token is bound."""
        custom = ProviderTemplate(
            name="custom_session",
            command=["tool"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json"],
                resume_command=["tool", "resume", "$${SESSION_ID}", "${SESSION_ID}"],
            ),
        )
        self.registry.register(custom)

        invocation, error = self.executor.prepare_invocation(
            "custom_session",
            ProviderParams(),
            {},
            "Test prompt",
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id="sess-123",
            ),
        )

        assert error is None
        assert invocation is not None
        assert invocation.command == ["tool", "resume", "${SESSION_ID}", "sess-123"]

    @patch('subprocess.run')
    def test_provider_execution_success(self, mock_run):
        """Test successful provider execution."""
        # Mock successful execution
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"Success output",
            stderr=b""
        )

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "claude",
            params,
            context,
            "Test prompt"
        )

        assert error is None

        # Execute
        result = self.executor.execute(invocation)

        assert result.exit_code == 0
        assert result.stdout == b"Success output"
        assert result.error is None

    @patch('subprocess.run')
    def test_provider_timeout(self, mock_run):
        """Test provider timeout handling (exit 124)."""
        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["claude"],
            timeout=30,
            output=b"Partial output",
            stderr=b"Timeout"
        )

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "claude",
            params,
            context,
            "Test prompt",
            timeout_sec=30
        )

        assert error is None

        # Execute with timeout
        result = self.executor.execute(invocation)

        assert result.exit_code == 124  # Timeout exit code
        assert result.stdout == b"Partial output"
        assert result.error["type"] == "timeout"

    def test_session_execution_normalizes_codex_jsonl_stdout(self):
        """Session-enabled Codex transport is parsed into normalized assistant stdout."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-123"}\n'
            '{"type":"assistant.message","role":"assistant","text":"hello "}\n'
            '{"type":"assistant.message","role":"assistant","text":"world"}\n'
            '{"type":"response.completed","session_id":"sess-123"}\n'
        )
        raw_stdout_bytes = raw_stdout.encode("utf-8")
        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write({raw_stdout!r})"],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        result = self.executor.execute(invocation)

        assert result.exit_code == 0
        assert result.stdout == b"hello world"
        assert result.raw_stdout == raw_stdout_bytes
        assert result.provider_session == {
            "session_id": "sess-123",
            "normalized_stdout": "hello world",
            "event_count": 4,
        }

    def test_session_execution_rejects_mismatched_resume_session_id(self):
        """Resume invocations fail when transport reports a different session id."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-other"}\n'
            '{"type":"assistant.message","role":"assistant","text":"hello"}\n'
            '{"type":"response.completed","session_id":"sess-other"}\n'
        )
        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write({raw_stdout!r})"],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="resume_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id="sess-123",
            ),
        )

        result = self.executor.execute(invocation)

        assert result.exit_code == 2
        assert result.error is not None
        assert result.error["type"] == "provider_session_transport_error"

    def test_session_stream_output_emits_only_normalized_assistant_text(self, capsys):
        """Session streaming surfaces assistant text, not raw JSONL metadata."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-123"}\n'
            '{"type":"assistant.message","role":"assistant","text":"hello world"}\n'
            '{"type":"response.completed","session_id":"sess-123"}\n'
        )
        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write({raw_stdout!r})"],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        result = self.executor.execute(invocation, stream_output=True)

        assert result.exit_code == 0
        captured = capsys.readouterr()
        assert captured.out == "hello world"
        assert "{\"type\"" not in captured.out

    def test_session_stream_output_emits_normalized_assistant_text_while_process_is_running(self):
        """Session-enabled streaming should surface assistant text before the provider exits."""
        script = (
            "import sys, time; "
            "sys.stdout.write('{\"type\":\"session.started\",\"session_id\":\"sess-123\"}\\n'); "
            "sys.stdout.flush(); "
            "time.sleep(0.1); "
            "sys.stdout.write('{\"type\":\"assistant.message\",\"role\":\"assistant\",\"text\":\"hello\"}\\n'); "
            "sys.stdout.flush(); "
            "time.sleep(1.0); "
            "sys.stdout.write('{\"type\":\"response.completed\",\"session_id\":\"sess-123\"}\\n'); "
            "sys.stdout.flush()"
        )
        invocation = ProviderInvocation(
            command=["python", "-c", script],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )
        stdout_recorder = _RecordingBinaryStream()
        stderr_recorder = _RecordingBinaryStream()
        result_box = {}
        started_at = time.time()

        with patch("sys.stdout", stdout_recorder), patch("sys.stderr", stderr_recorder):
            worker = threading.Thread(
                target=lambda: result_box.setdefault(
                    "result",
                    self.executor.execute(invocation, stream_output=True),
                ),
                daemon=True,
            )
            worker.start()

            deadline = time.time() + 0.6
            while time.time() < deadline and stdout_recorder.first_write_at is None:
                time.sleep(0.02)

            first_write_at = stdout_recorder.first_write_at
            worker.join(timeout=5)

        assert first_write_at is not None
        assert first_write_at - started_at < 0.6
        assert result_box["result"].exit_code == 0
        assert stdout_recorder.getvalue() == b"hello"

    def test_session_stream_output_does_not_duplicate_stderr(self):
        """Session-enabled streaming should emit provider stderr exactly once."""
        script = (
            "import sys; "
            "sys.stderr.write('ERR\\n'); sys.stderr.flush(); "
            "sys.stdout.write('{\"type\":\"session.started\",\"session_id\":\"sess-123\"}\\n'); "
            "sys.stdout.write('{\"type\":\"assistant.message\",\"role\":\"assistant\",\"text\":\"hello\"}\\n'); "
            "sys.stdout.write('{\"type\":\"response.completed\",\"session_id\":\"sess-123\"}\\n'); "
            "sys.stdout.flush()"
        )
        invocation = ProviderInvocation(
            command=["python", "-c", script],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )
        stdout_recorder = _RecordingBinaryStream()
        stderr_recorder = _RecordingBinaryStream()

        with patch("sys.stdout", stdout_recorder), patch("sys.stderr", stderr_recorder):
            result = self.executor.execute(invocation, stream_output=True)

        assert result.exit_code == 0
        assert stdout_recorder.getvalue() == b"hello"
        assert stderr_recorder.getvalue() == b"ERR\n"

    def test_session_execution_writes_masked_transport_spool(self):
        """Session transport is masked and copied to the configured spool path."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-123"}\n'
            '{"type":"assistant.message","role":"assistant","text":"secret-token"}\n'
            '{"type":"response.completed","session_id":"sess-123"}\n'
        )
        transport_spool_path = self.workspace / "session.transport.log"
        self.executor.secrets_manager._masked_values.add("secret-token")

        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write({raw_stdout!r})"],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        result = self.executor.execute(
            invocation,
            session_runtime={"transport_spool_path": transport_spool_path},
        )

        assert result.exit_code == 0
        assert transport_spool_path.exists()
        spool_text = transport_spool_path.read_text(encoding="utf-8")
        assert "***" in spool_text
        assert "secret-token" not in spool_text

    def test_session_execution_appends_transport_spool_while_process_is_running(self):
        """Session transport reaches the stable spool before the provider process exits."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-123"}\n'
            '{"type":"assistant.message","role":"assistant","text":"partial"}\n'
            '{"type":"response.completed","session_id":"sess-123"}\n'
        )
        script = (
            "import sys, time; "
            f"payload = {raw_stdout!r}.splitlines(True); "
            "sys.stdout.write(payload[0]); sys.stdout.flush(); "
            "sys.stdout.write(payload[1]); sys.stdout.flush(); "
            "time.sleep(0.8); "
            "sys.stdout.write(payload[2]); sys.stdout.flush()"
        )
        transport_spool_path = self.workspace / "session-live.transport.log"
        invocation = ProviderInvocation(
            command=["python", "-c", script],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        result_box = {}

        worker = threading.Thread(
            target=lambda: result_box.setdefault(
                "result",
                self.executor.execute(
                    invocation,
                    session_runtime={"transport_spool_path": transport_spool_path},
                ),
            ),
        )
        worker.start()

        deadline = time.time() + 5
        partial_text = ""
        while time.time() < deadline:
            if transport_spool_path.exists():
                partial_text = transport_spool_path.read_text(encoding="utf-8")
                if partial_text:
                    break
            time.sleep(0.02)

        assert partial_text
        assert "session.started" in partial_text
        assert "response.completed" not in partial_text

        worker.join(timeout=5)
        assert not worker.is_alive()
        assert result_box["result"].exit_code == 0

    def test_escape_sequences(self):
        """Test escape sequence handling ($$ and $${)."""
        # Register provider with escapes
        custom = ProviderTemplate(
            name="custom",
            command=["tool", "--text", "$${literal}", "--dollar", "$$100"],
            input_mode=InputMode.ARGV
        )
        self.registry.register(custom)

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "custom",
            params,
            context,
            None
        )

        assert error is None
        # Check escapes were processed
        assert "${literal}" in invocation.command  # $${ -> ${
        assert "$100" in invocation.command  # $$ -> $

    def test_streaming_capture_waits_for_reader_threads(self):
        """Streaming capture should return complete stdout even with slow pipe readers."""
        payload = "x" * 9000
        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write('{payload}')"],
            input_mode=InputMode.ARGV,
            prompt=None,
            output_file=None,
            env=None,
            timeout_sec=10,
        )

        def _slow_stream_pipe(pipe, buffer, out_stream):
            if pipe is None:
                return
            output = out_stream.buffer if hasattr(out_stream, "buffer") else out_stream
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                buffer.extend(chunk)
                time.sleep(1.2)
                try:
                    output.write(chunk)
                    output.flush()
                except Exception:
                    pass

        with patch.object(self.executor, "_stream_pipe", side_effect=_slow_stream_pipe):
            result = self.executor.execute(invocation, stream_output=True)

        assert result.exit_code == 0
        assert len(result.stdout) == len(payload)
        assert result.stdout == payload.encode("utf-8")
