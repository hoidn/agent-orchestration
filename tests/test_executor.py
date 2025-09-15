"""Tests for step executor and output capture.

Tests acceptance criteria AT-1 and AT-2 for output capture modes.
"""

import json
import tempfile
from pathlib import Path
import pytest

from orchestrator.exec.output_capture import OutputCapture, OutputCaptureMode, CaptureResult
from orchestrator.exec.step_executor import StepExecutor
from orchestrator.workflow.types import Step, OutputCapture as OutputCaptureEnum


class TestOutputCapture:
    """Test output capture modes and limits."""

    def test_text_capture_under_limit(self):
        """Test text capture within 8KB limit."""
        capture = OutputCapture(OutputCaptureMode.TEXT)
        stdout = b"Hello, world!\nThis is a test."
        stderr = b""

        result = capture.capture(stdout, stderr, "TestStep")

        assert result.mode == OutputCaptureMode.TEXT
        assert result.output == "Hello, world!\nThis is a test."
        assert not result.truncated
        assert result.json_data is None
        assert result.lines is None

    def test_text_capture_truncation(self):
        """Test text capture truncation at 8KB limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            capture = OutputCapture(OutputCaptureMode.TEXT, log_dir)

            # Create output larger than 8KB
            large_text = "x" * 10000
            stdout = large_text.encode('utf-8')
            stderr = b""

            result = capture.capture(stdout, stderr, "TestStep")

            assert result.mode == OutputCaptureMode.TEXT
            assert len(result.output) == 8192  # 8KB limit
            assert result.truncated
            assert result.stdout_file == log_dir / "TestStep.stdout"
            assert result.stdout_file.exists()
            assert result.stdout_file.read_bytes() == stdout

    def test_lines_capture_under_limit(self):
        """Test lines capture within 10,000 lines limit (AT-1)."""
        capture = OutputCapture(OutputCaptureMode.LINES)
        lines_data = ["line " + str(i) for i in range(100)]
        stdout = "\n".join(lines_data).encode('utf-8')
        stderr = b""

        result = capture.capture(stdout, stderr, "TestStep")

        assert result.mode == OutputCaptureMode.LINES
        assert result.lines == lines_data
        assert not result.truncated
        assert result.output is None
        assert result.json_data is None

    def test_lines_capture_truncation(self):
        """Test lines capture truncation at 10,000 lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            capture = OutputCapture(OutputCaptureMode.LINES, log_dir)

            # Create output with more than 10,000 lines
            lines_data = ["line " + str(i) for i in range(12000)]
            stdout = "\n".join(lines_data).encode('utf-8')
            stderr = b""

            result = capture.capture(stdout, stderr, "TestStep")

            assert result.mode == OutputCaptureMode.LINES
            assert len(result.lines) == 10000  # Limited to 10,000
            assert result.lines == lines_data[:10000]
            assert result.truncated
            assert result.stdout_file.exists()

    def test_lines_capture_crlf_normalization(self):
        """Test CRLF normalization in lines mode."""
        capture = OutputCapture(OutputCaptureMode.LINES)
        stdout = b"line1\r\nline2\r\nline3"
        stderr = b""

        result = capture.capture(stdout, stderr, "TestStep")

        assert result.lines == ["line1", "line2", "line3"]
        assert not result.truncated

    def test_json_capture_valid(self):
        """Test JSON capture with valid JSON (AT-2)."""
        capture = OutputCapture(OutputCaptureMode.JSON)
        data = {"key": "value", "number": 42, "array": [1, 2, 3]}
        stdout = json.dumps(data).encode('utf-8')
        stderr = b""

        result = capture.capture(stdout, stderr, "TestStep")

        assert result.mode == OutputCaptureMode.JSON
        assert result.json_data == data
        assert not result.truncated
        assert result.json_parse_error is None
        assert result.output is None
        assert result.lines is None

    def test_json_capture_parse_error_without_flag(self):
        """Test JSON capture with parse error and no allow_parse_error flag."""
        capture = OutputCapture(OutputCaptureMode.JSON)
        stdout = b"not valid json"
        stderr = b""

        result = capture.capture(stdout, stderr, "TestStep", allow_parse_error=False)

        assert result.mode == OutputCaptureMode.JSON
        assert result.json_data is None
        assert result.json_parse_error is not None
        # Error message should indicate parse failure
        assert result.json_parse_error  # Just check it exists

    def test_json_capture_parse_error_with_flag(self):
        """Test JSON capture with parse error and allow_parse_error=true."""
        capture = OutputCapture(OutputCaptureMode.JSON)
        stdout = b"not valid json"
        stderr = b""

        result = capture.capture(stdout, stderr, "TestStep", allow_parse_error=True)

        assert result.mode == OutputCaptureMode.JSON
        assert result.json_data is None
        assert result.json_parse_error is not None
        assert result.output == "not valid json"  # Falls back to text
        assert not result.truncated

    def test_json_capture_oversize(self):
        """Test JSON capture with data exceeding 1MB limit."""
        capture = OutputCapture(OutputCaptureMode.JSON)
        # Create JSON larger than 1MB
        large_data = {"data": "x" * (1024 * 1024 + 1000)}
        stdout = json.dumps(large_data).encode('utf-8')
        stderr = b""

        result = capture.capture(stdout, stderr, "TestStep", allow_parse_error=False)

        assert result.json_data is None
        assert result.json_parse_error is not None
        assert "1 MiB limit" in result.json_parse_error

    def test_json_capture_oversize_with_flag(self):
        """Test JSON oversize with allow_parse_error=true falls back to text."""
        capture = OutputCapture(OutputCaptureMode.JSON)
        # Create data larger than 1MB
        large_text = "x" * (1024 * 1024 + 1000)
        stdout = large_text.encode('utf-8')
        stderr = b""

        result = capture.capture(stdout, stderr, "TestStep", allow_parse_error=True)

        assert result.json_data is None
        assert result.output is not None  # Falls back to text
        assert len(result.output) == 8192  # Text mode limit
        assert result.truncated

    def test_output_file_tee(self):
        """Test that output_file receives full stream while state is limited."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            output_file = tmpdir / "output.txt"
            log_dir = tmpdir / "logs"

            capture = OutputCapture(OutputCaptureMode.TEXT, log_dir)
            large_text = "x" * 10000
            stdout = large_text.encode('utf-8')
            stderr = b""

            result = capture.capture(stdout, stderr, "TestStep", output_file=output_file)

            # State is truncated
            assert len(result.output) == 8192
            assert result.truncated

            # But output_file has full content
            assert output_file.exists()
            assert output_file.read_bytes() == stdout

    def test_stderr_capture(self):
        """Test that non-empty stderr is written to logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            capture = OutputCapture(OutputCaptureMode.TEXT, log_dir)

            stdout = b"normal output"
            stderr = b"error output"

            result = capture.capture(stdout, stderr, "TestStep")

            assert result.output == "normal output"
            assert result.stderr_file == log_dir / "TestStep.stderr"
            assert result.stderr_file.exists()
            assert result.stderr_file.read_bytes() == stderr


class TestStepExecutor:
    """Test step executor with various step types."""

    def test_execute_simple_command(self):
        """Test executing a simple command step."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            step = Step(
                name="Echo",
                command=["echo", "Hello, World!"]
            )

            state, exec_result = executor.execute(step, {})

            assert state.status == "completed"
            assert state.exit_code == 0
            assert state.output.strip() == "Hello, World!"
            assert exec_result.exit_code == 0

    def test_execute_with_lines_capture(self):
        """Test command execution with lines capture mode (AT-1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            # Use printf to generate multiple lines
            step = Step(
                name="MultiLine",
                command=["printf", "line1\\nline2\\nline3"],
                output_capture=OutputCaptureEnum.LINES
            )

            state, exec_result = executor.execute(step, {})

            assert state.status == "completed"
            assert state.exit_code == 0
            assert state.lines == ["line1", "line2", "line3"]
            assert state.output is None  # No raw output in lines mode

    def test_execute_with_json_capture(self):
        """Test command execution with JSON capture mode (AT-2)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            json_data = {"result": "success", "value": 42}
            step = Step(
                name="JsonOutput",
                command=["echo", json.dumps(json_data)],
                output_capture=OutputCaptureEnum.JSON
            )

            state, exec_result = executor.execute(step, {})

            assert state.status == "completed"
            assert state.exit_code == 0
            assert state.json == json_data
            assert state.output is None  # No raw output in JSON mode

    def test_execute_with_json_parse_error(self):
        """Test JSON capture with invalid JSON causes exit code 2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            step = Step(
                name="InvalidJson",
                command=["echo", "not valid json"],
                output_capture=OutputCaptureEnum.JSON
            )

            state, exec_result = executor.execute(step, {})

            assert state.status == "failed"
            assert state.exit_code == 2
            assert state.json is None
            assert "JSON parse error" in state.error["message"]

    def test_execute_with_json_parse_error_allowed(self):
        """Test JSON capture with allow_parse_error=true."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            step = Step(
                name="InvalidJsonAllowed",
                command=["echo", "not valid json"],
                output_capture=OutputCaptureEnum.JSON,
                allow_parse_error=True
            )

            state, exec_result = executor.execute(step, {})

            assert state.status == "completed"
            assert state.exit_code == 0
            assert state.json is None
            assert state.output == "not valid json\n"  # Falls back to text
            assert "json_parse_error" in state.debug

    def test_execute_with_env_vars(self):
        """Test command execution with environment variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            step = Step(
                name="EnvTest",
                command=["sh", "-c", "echo $TEST_VAR"],
                env={"TEST_VAR": "test_value"}
            )

            state, exec_result = executor.execute(step, {})

            assert state.status == "completed"
            assert state.exit_code == 0
            assert state.output.strip() == "test_value"

    def test_execute_failing_command(self):
        """Test execution of a failing command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            step = Step(
                name="FailingCommand",
                command=["sh", "-c", "exit 1"]
            )

            state, exec_result = executor.execute(step, {})

            assert state.status == "failed"
            assert state.exit_code == 1
            assert exec_result.exit_code == 1

    def test_missing_secrets(self):
        """Test that missing secrets cause exit code 2."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            step = Step(
                name="SecretTest",
                command=["echo", "test"],
                secrets=["MISSING_SECRET"]
            )

            state, exec_result = executor.execute(step, {})

            assert state.status == "failed"
            assert state.exit_code == 2
            assert "missing_secrets" in state.error["context"]
            assert "MISSING_SECRET" in state.error["context"]["missing_secrets"]


class TestAcceptanceCriteria:
    """Test specific acceptance criteria."""

    def test_acceptance_at1_lines_capture(self):
        """AT-1: Lines capture populates steps.X.lines[] correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            # Generate 100 lines
            lines_to_generate = 100
            command = ["sh", "-c", f"for i in $(seq 1 {lines_to_generate}); do echo Line $i; done"]

            step = Step(
                name="ListGenerator",
                command=command,
                output_capture=OutputCaptureEnum.LINES
            )

            state, _ = executor.execute(step, {})

            assert state.status == "completed"
            assert state.lines is not None
            assert len(state.lines) == lines_to_generate
            assert state.lines[0] == "Line 1"
            assert state.lines[-1] == f"Line {lines_to_generate}"
            assert not state.truncated

    def test_acceptance_at2_json_capture(self):
        """AT-2: JSON capture populates steps.X.json object correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            run_root = Path(tmpdir) / "run"
            run_root.mkdir()

            executor = StepExecutor(workspace, run_root)

            test_data = {
                "status": "success",
                "results": [
                    {"id": 1, "value": "first"},
                    {"id": 2, "value": "second"}
                ],
                "metadata": {
                    "timestamp": "2025-01-15T10:00:00Z",
                    "version": "1.0"
                }
            }

            step = Step(
                name="JsonGenerator",
                command=["echo", json.dumps(test_data)],
                output_capture=OutputCaptureEnum.JSON
            )

            state, _ = executor.execute(step, {})

            assert state.status == "completed"
            assert state.json == test_data
            assert state.json["status"] == "success"
            assert len(state.json["results"]) == 2
            assert state.json["metadata"]["version"] == "1.0"
            assert not state.truncated