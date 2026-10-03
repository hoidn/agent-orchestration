"""
Tests for output capture module.
Covers AT-1, AT-2, AT-45, AT-52: Output capture modes and truncation.
"""

import json
import sys
import pytest
from pathlib import Path
import tempfile
import shutil

from orchestrator.exec import OutputCapture, CaptureMode, CaptureResult, StepExecutor
from orchestrator.workflow.workspace_files import WorkspaceFiles


class TestOutputCapture:
    """Test output capture modes and limits."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        workspace = Path(tempfile.mkdtemp())
        yield workspace
        shutil.rmtree(workspace, ignore_errors=True)

    @pytest.fixture
    def capture(self, temp_workspace):
        """Create OutputCapture instance."""
        return OutputCapture(temp_workspace)

    def test_at1_lines_capture(self, capture):
        """AT-1: Lines capture - output_capture: lines → steps.X.lines[] populated."""
        # Test normal lines capture
        stdout = b"line1\nline2\nline3\n"
        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.LINES,
        )

        assert result.mode == CaptureMode.LINES
        assert result.lines == ["line1", "line2", "line3"]
        assert result.truncated is False
        assert result.exit_code == 0

        # Verify state format (no raw output for lines mode)
        state = result.to_state_dict()
        assert "lines" in state
        assert "output" not in state  # Per spec: omit raw output for lines mode

    def test_at1_lines_capture_crlf_normalization(self, capture):
        """AT-1: Lines mode normalizes CRLF to LF."""
        stdout = b"line1\r\nline2\r\nline3"
        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.LINES,
        )

        assert result.lines == ["line1", "line2", "line3"]

    def test_at1_lines_capture_truncation(self, capture):
        """AT-1: Lines mode truncates at 10,000 lines."""
        # Generate 10,001 lines
        lines = [f"line{i}" for i in range(10001)]
        stdout = "\n".join(lines).encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.LINES,
        )

        assert result.truncated is True
        assert len(result.lines) == 10000
        assert result.lines[0] == "line0"
        assert result.lines[-1] == "line9999"

        # Verify full output written to logs
        logs_file = capture.logs_dir / "test_step.stdout"
        assert logs_file.exists()
        assert logs_file.read_bytes() == stdout

    def test_at2_json_capture_success(self, capture):
        """AT-2: JSON capture - output_capture: json → steps.X.json object available."""
        data = {"key": "value", "number": 42, "array": [1, 2, 3]}
        stdout = json.dumps(data).encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
        )

        assert result.mode == CaptureMode.JSON
        assert result.json_data == data
        assert result.truncated is False
        assert result.exit_code == 0

        # Verify state format (no raw output for successful JSON)
        state = result.to_state_dict()
        assert "json" in state
        assert "output" not in state

    def test_at14_json_oversize_fails(self, capture):
        """AT-14: JSON >1 MiB fails with exit 2."""
        # Create JSON larger than 1 MiB
        large_data = {"data": "x" * (1024 * 1024 + 1)}
        stdout = json.dumps(large_data).encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
            allow_parse_error=False,
        )

        assert result.exit_code == 2
        assert result.error is not None
        assert result.error["type"] == "json_overflow"
        assert "1 MiB limit" in result.error["message"]

    def test_at15_json_parse_error_allowed(self, capture):
        """AT-15: JSON parse error with allow_parse_error: true succeeds."""
        stdout = b"not valid json"

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
            allow_parse_error=True,
        )

        assert result.mode == CaptureMode.JSON
        assert result.exit_code == 0  # Success despite parse error
        assert result.output == "not valid json"  # Raw output stored
        assert result.json_data is None
        assert result.debug is not None
        assert "json_parse_error" in result.debug

    def test_at15_json_oversize_with_allow_parse_error(self, capture):
        """AT-15: JSON overflow with allow_parse_error stores truncated text."""
        # Create oversized non-JSON data
        large_text = "x" * (1024 * 1024 + 1)
        stdout = large_text.encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
            allow_parse_error=True,
        )

        assert result.exit_code == 0
        assert result.truncated is True
        assert result.output is not None
        assert len(result.output.encode('utf-8')) <= 8 * 1024
        assert result.debug is not None
        assert "json_parse_error" in result.debug

    def test_at52_json_overflow_spills_to_logs(self, capture):
        """AT-52: JSON overflow with allow_parse_error spills full stdout to logs (regression test)."""
        # Create oversized data that triggers JSON buffer overflow
        large_text = "not json " * (128 * 1024)  # ~1.2 MiB of text
        stdout = large_text.encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="json_overflow_step",
            mode=CaptureMode.JSON,
            allow_parse_error=True,
        )

        # Verify result state
        assert result.exit_code == 0
        assert result.truncated is True
        assert result.output is not None
        assert len(result.output.encode('utf-8')) <= 8 * 1024
        assert result.debug is not None
        assert "JSON buffer overflow" in result.debug["json_parse_error"]

        # CRITICAL: Verify full output was spilled to logs (AT-52 consistency)
        logs_file = capture.logs_dir / "json_overflow_step.stdout"
        assert logs_file.exists(), "JSON overflow must spill full stdout to logs"
        assert logs_file.read_bytes() == stdout, "Spilled log must contain complete original output"

    def test_at45_text_capture_truncation(self, capture):
        """AT-45: Text mode truncates at 8 KiB and spills to logs."""
        # Create text larger than 8 KiB
        large_text = "x" * (8 * 1024 + 100)
        stdout = large_text.encode('utf-8')

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.TEXT,
        )

        assert result.mode == CaptureMode.TEXT
        assert result.truncated is True
        assert len(result.output.encode('utf-8')) <= 8 * 1024
        assert result.exit_code == 0

        # Verify full output written to logs
        logs_file = capture.logs_dir / "test_step.stdout"
        assert logs_file.exists()
        assert logs_file.read_bytes() == stdout

    def test_at52_output_tee_semantics(self, capture, temp_workspace):
        """AT-52: output_file receives full stdout while limits apply to state."""
        # Create large output that will be truncated
        large_text = "x" * (8 * 1024 + 100)
        stdout = large_text.encode('utf-8')
        output_file = temp_workspace / "output.txt"

        result = capture.capture(
            stdout=stdout,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.TEXT,
            output_file=output_file,
        )

        # State should be truncated
        assert result.truncated is True
        assert len(result.output.encode('utf-8')) <= 8 * 1024

        # But output_file should have full content
        assert output_file.exists()
        assert output_file.read_bytes() == stdout

    def test_at67_tee_on_json_parse_failure(self, capture, temp_workspace):
        """AT-67: Tee on JSON parse failure - output_file still receives full stdout when JSON parsing fails."""
        # Test with invalid JSON that will fail to parse
        invalid_json = b"{ invalid json content }"
        output_file = temp_workspace / "output.txt"

        # Test without allow_parse_error (should fail with exit 2)
        result = capture.capture(
            stdout=invalid_json,
            stderr=b"",
            step_name="test_step",
            mode=CaptureMode.JSON,
            output_file=output_file,
            allow_parse_error=False,
        )

        # Should fail with exit code 2
        assert result.exit_code == 2
        assert result.error is not None
        assert result.error["type"] == "json_parse_error"

        # But output_file should still have received the full stdout
        assert output_file.exists()
        assert output_file.read_bytes() == invalid_json

        # Test with truncated JSON that will fail to parse
        large_invalid_json = b"{ " + b"x" * (8 * 1024) + b" not valid json"
        output_file2 = temp_workspace / "output2.txt"

        result2 = capture.capture(
            stdout=large_invalid_json,
            stderr=b"",
            step_name="test_step2",
            mode=CaptureMode.JSON,
            output_file=output_file2,
            allow_parse_error=False,
        )

        # Should fail with exit code 2
        assert result2.exit_code == 2
        assert result2.error is not None
        assert result2.error["type"] == "json_parse_error"

        # output_file should have full content even though parsing failed
        assert output_file2.exists()
        assert output_file2.read_bytes() == large_invalid_json

        # Test with JSON buffer overflow (>1 MiB)
        oversized_json = b"[" + b"1," * (512 * 1024) + b"2]"  # Over 1 MiB
        output_file3 = temp_workspace / "output3.txt"

        result3 = capture.capture(
            stdout=oversized_json,
            stderr=b"",
            step_name="test_step3",
            mode=CaptureMode.JSON,
            output_file=output_file3,
            allow_parse_error=False,
        )

        # Should fail with exit code 2 due to buffer overflow
        assert result3.exit_code == 2
        assert result3.error is not None
        assert result3.error["type"] == "json_overflow"

        # output_file should still have the full content
        assert output_file3.exists()
        assert output_file3.read_bytes() == oversized_json

    def test_stderr_capture(self, capture):
        """Stderr is always written to logs when non-empty."""
        stdout = b"stdout content"
        stderr = b"error message"

        result = capture.capture(
            stdout=stdout,
            stderr=stderr,
            step_name="test_step",
            mode=CaptureMode.TEXT,
        )

        # Check stderr was written to logs
        stderr_file = capture.logs_dir / "test_step.stderr"
        assert stderr_file.exists()
        assert stderr_file.read_bytes() == stderr

    def test_long_step_name_log_paths_are_bounded(self, capture):
        """Generated nested step names should not exceed filesystem filename limits."""
        step_name = (
            "review_revise_design_docs::review-revise-design-docs__review__"
            "%proc-ref-call.%parametric_call.std.phase.review_revise_loop_proc."
            "d15c114978f5.d5df4f219296_1__body.REVISE."
            "review_revise_design_docs::review-revise-design-docs__review__"
            "%proc-ref-call.%parametric_call.std.phase.review_revise_loop_proc."
            "d15c114978f5.d5df4f219296_1__body__revise__fixed-completed__"
            "fix_1__revision"
        )
        stderr = b"long nested provider stderr"

        capture.capture(
            stdout=b"",
            stderr=stderr,
            step_name=step_name,
            mode=CaptureMode.TEXT,
        )

        stderr_files = list(capture.logs_dir.glob("*.stderr"))
        assert len(stderr_files) == 1
        stderr_file = stderr_files[0]
        assert len(stderr_file.name.encode("utf-8")) <= 255
        assert stderr_file.name.endswith(".stderr")
        assert stderr_file.read_bytes() == stderr


class TestStepExecutor:
    """Test step executor with real command execution."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        workspace = Path(tempfile.mkdtemp())
        yield workspace
        shutil.rmtree(workspace, ignore_errors=True)

    @pytest.fixture
    def executor(self, temp_workspace):
        """Create StepExecutor instance."""
        return StepExecutor(temp_workspace)

    @pytest.fixture
    def attempt_capture_files(self, temp_workspace):
        attempt_dir = temp_workspace / "attempt"
        attempt_dir.mkdir()
        files = WorkspaceFiles(attempt_dir)
        yield files
        files.close()

    def test_command_execution_text_mode(self, executor):
        """Test basic command execution with text capture."""
        result = executor.execute_command(
            step_name="echo_test",
            command="echo 'Hello World'",
            output_capture=CaptureMode.TEXT,
        )

        assert result.exit_code == 0
        assert result.capture_result.output.strip() == "Hello World"
        assert result.capture_result.truncated is False
        assert result.duration_ms > 0

    def test_command_execution_lines_mode(self, executor):
        """Test command execution with lines capture."""
        result = executor.execute_command(
            step_name="lines_test",
            command="printf 'line1\\nline2\\nline3'",
            output_capture=CaptureMode.LINES,
        )

        assert result.exit_code == 0
        assert result.capture_result.lines == ["line1", "line2", "line3"]
        assert result.capture_result.truncated is False

    def test_command_execution_json_mode(self, executor):
        """Test command execution with JSON capture."""
        result = executor.execute_command(
            step_name="json_test",
            command='echo \'{"key": "value", "number": 42}\'',
            output_capture=CaptureMode.JSON,
        )

        assert result.exit_code == 0
        assert result.capture_result.json_data == {"key": "value", "number": 42}
        assert result.capture_result.truncated is False

    def test_command_timeout(self, executor):
        """Test command timeout handling."""
        result = executor.execute_command(
            step_name="timeout_test",
            command="sleep 10",
            timeout_sec=1,
            output_capture=CaptureMode.TEXT,
        )

        assert result.exit_code == 124  # Timeout exit code per spec
        assert result.error is not None
        assert result.error["type"] == "timeout"

    def test_command_with_env_vars(self, executor):
        """Test command execution with environment variables."""
        result = executor.execute_command(
            step_name="env_test",
            command="printenv TEST_VAR",  # Use printenv which doesn't need shell expansion
            env={"TEST_VAR": "test_value"},
            output_capture=CaptureMode.TEXT,
        )

        assert result.exit_code == 0
        assert result.capture_result.output.strip() == "test_value"

    def test_failed_command(self, executor):
        """Test handling of failed commands."""
        result = executor.execute_command(
            step_name="fail_test",
            command="false",  # Use 'false' command which returns exit code 1
            output_capture=CaptureMode.TEXT,
        )

        assert result.exit_code == 1
        assert result.error is None  # Normal non-zero exit, not an error

    def test_to_state_dict(self, executor):
        """Test conversion to state dictionary format."""
        result = executor.execute_command(
            step_name="state_test",
            command="echo 'test'",
            output_capture=CaptureMode.TEXT,
        )

        state = result.to_state_dict()
        assert "exit_code" in state
        assert "duration_ms" in state
        assert "output" in state
        assert "truncated" in state

    def test_attempt_capture_creates_empty_stream_files(self, temp_workspace, attempt_capture_files):
        executor = StepExecutor(temp_workspace, attempt_capture_files=attempt_capture_files)

        result = executor.execute_command(
            step_name="empty_attempt",
            command=[sys.executable, "-c", "pass"],
        )

        assert result.exit_code == 0
        assert (attempt_capture_files.workspace / "stdout.txt").read_bytes() == b""
        assert (attempt_capture_files.workspace / "stderr.txt").read_bytes() == b""
        assert sorted(path.name for path in attempt_capture_files.workspace.iterdir()) == [
            "stderr.txt",
            "stdout.txt",
        ]
        assert not (temp_workspace / "logs").exists()

    def test_attempt_capture_keeps_nonzero_bytes_and_existing_stderr_redaction(
        self, temp_workspace, attempt_capture_files
    ):
        executor = StepExecutor(temp_workspace, attempt_capture_files=attempt_capture_files)
        token = "attempt-secret-token"
        script = (
            "import os, sys; os.write(1, b'\\x00stdout'); "
            "os.write(2, b'prefix-\\x00attempt-secret-token-suffix'); sys.exit(7)"
        )

        result = executor.execute_command(
            step_name="failed_attempt",
            command=[sys.executable, "-c", script],
            env={"OMP_AUTH_BROKER_TOKEN": token},
        )

        assert result.exit_code == 7
        assert (attempt_capture_files.workspace / "stdout.txt").read_bytes() == b"\x00stdout"
        assert (attempt_capture_files.workspace / "stderr.txt").read_bytes() == (
            b"prefix-\x00[redacted]-suffix"
        )

    def test_attempt_capture_keeps_timeout_partial_bytes(self, temp_workspace, attempt_capture_files):
        executor = StepExecutor(temp_workspace, attempt_capture_files=attempt_capture_files)
        script = (
            "import os, threading; os.write(1, b'partial-out'); "
            "os.write(2, b'partial-err'); threading.Event().wait()"
        )

        result = executor.execute_command(
            step_name="timed_attempt",
            command=[sys.executable, "-c", script],
            timeout_sec=1,
        )

        assert result.exit_code == 124
        assert result.error is not None and result.error["type"] == "timeout"
        assert (attempt_capture_files.workspace / "stdout.txt").read_bytes() == b"partial-out"
        assert (attempt_capture_files.workspace / "stderr.txt").read_bytes() == b"partial-err"

    @pytest.mark.parametrize(
        ("mode", "script", "expected", "allow_parse_error"),
        [
            (
                CaptureMode.TEXT,
                "import os; os.write(1, b'x' * 8300)",
                b"x" * 8300,
                False,
            ),
            (
                CaptureMode.LINES,
                "import os; os.write(1, b'x\\n' * 10001)",
                b"x\n" * 10001,
                False,
            ),
            (
                CaptureMode.JSON,
                "import os; os.write(1, b'x' * 8300)",
                b"x" * 8300,
                True,
            ),
            (
                CaptureMode.JSON,
                "import os; os.write(1, b'x' * 1048577)",
                b"x" * 1048577,
                True,
            ),
        ],
        ids=["text", "lines", "json-parse-spill", "json-overflow"],
    )
    def test_attempt_capture_oversize_has_only_complete_attempt_files(
        self,
        temp_workspace,
        attempt_capture_files,
        mode,
        script,
        expected,
        allow_parse_error,
    ):
        executor = StepExecutor(temp_workspace, attempt_capture_files=attempt_capture_files)

        result = executor.execute_command(
            step_name="oversize_attempt",
            command=[sys.executable, "-c", script],
            output_capture=mode,
            allow_parse_error=allow_parse_error,
        )

        assert result.capture_result.truncated is True
        assert (attempt_capture_files.workspace / "stdout.txt").read_bytes() == expected
        assert (attempt_capture_files.workspace / "stderr.txt").read_bytes() == b""
        assert sorted(path.name for path in attempt_capture_files.workspace.iterdir()) == [
            "stderr.txt",
            "stdout.txt",
        ]

    def test_attempt_capture_rejects_output_file_before_dispatch(
        self, temp_workspace, attempt_capture_files
    ):
        executor = StepExecutor(temp_workspace, attempt_capture_files=attempt_capture_files)
        marker = temp_workspace / "dispatched"
        script = "from pathlib import Path; Path('dispatched').write_text('ran')"

        with pytest.raises(ValueError, match="output_file"):
            executor.execute_command(
                step_name="conflicting_attempt",
                command=[sys.executable, "-c", script],
                output_file=temp_workspace / "tee.txt",
            )

        assert not marker.exists()
        assert not (temp_workspace / "logs").exists()

    def test_direct_capture_rejects_output_file_with_attempt_owner(self, temp_workspace, attempt_capture_files):
        capture = OutputCapture(temp_workspace, attempt_capture_files=attempt_capture_files)

        with pytest.raises(ValueError, match="output_file"):
            capture.capture(
                stdout=b"out",
                stderr=b"err",
                step_name="direct_attempt",
                output_file=temp_workspace / "tee.txt",
            )

        assert list(attempt_capture_files.workspace.iterdir()) == []

    def test_attempt_capture_writes_through_pinned_owner_after_path_swap(
        self, temp_workspace, attempt_capture_files
    ):
        attempt_dir = attempt_capture_files.workspace
        moved_attempt = temp_workspace / "moved_attempt"
        external_dir = temp_workspace / "external"
        external_dir.mkdir()
        attempt_dir.rename(moved_attempt)
        attempt_dir.symlink_to(external_dir, target_is_directory=True)
        capture = OutputCapture(temp_workspace, attempt_capture_files=attempt_capture_files)

        capture.capture(stdout=b"pinned", stderr=b"", step_name="pinned_attempt")

        assert (moved_attempt / "stdout.txt").read_bytes() == b"pinned"
        assert (moved_attempt / "stderr.txt").read_bytes() == b""
        assert list(external_dir.iterdir()) == []
        assert not (temp_workspace / "logs").exists()

    def test_attempt_capture_does_not_follow_existing_file_symlink(
        self, temp_workspace, attempt_capture_files
    ):
        sentinel = temp_workspace / "sentinel.txt"
        sentinel.write_bytes(b"unchanged")
        (attempt_capture_files.workspace / "stdout.txt").symlink_to(sentinel)
        capture = OutputCapture(temp_workspace, attempt_capture_files=attempt_capture_files)

        with pytest.raises(FileExistsError):
            capture.capture(stdout=b"replace", stderr=b"err", step_name="symlink_attempt")

        assert sentinel.read_bytes() == b"unchanged"
        assert not (attempt_capture_files.workspace / "stderr.txt").exists()
