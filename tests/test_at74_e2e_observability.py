"""Test for AT-74: E2E test observability.

This test validates that E2E tests display agent I/O when ORCHESTRATE_E2E_VERBOSE=1.
"""

import os
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest


def test_at74_e2e_reporter_disabled_by_default():
    """AT-74: Reporter should be disabled by default."""
    from tests.e2e.reporter import E2ETestReporter

    # Without env var set, reporter should be disabled
    with patch.dict(os.environ, {}, clear=True):
        reporter = E2ETestReporter()
        assert not reporter.enabled

        # Verify nothing is printed when disabled
        with patch('sys.stdout', new=StringIO()) as fake_out:
            reporter.section("Test Section")
            reporter.info("Test Info")
            reporter.command(["test", "command"])
            assert fake_out.getvalue() == ""


def test_at74_e2e_reporter_enabled_with_env_var():
    """AT-74: Reporter should be enabled when ORCHESTRATE_E2E_VERBOSE=1."""
    from tests.e2e.reporter import E2ETestReporter

    # With env var set, reporter should be enabled
    with patch.dict(os.environ, {"ORCHESTRATE_E2E_VERBOSE": "1"}):
        reporter = E2ETestReporter()
        assert reporter.enabled


def test_at74_e2e_reporter_section_output():
    """AT-74: Reporter should display clear section headers."""
    from tests.e2e.reporter import E2ETestReporter

    reporter = E2ETestReporter(enabled=True)

    with patch('sys.stdout', new=StringIO()) as fake_out:
        reporter.section("Test Section")
        output = fake_out.getvalue()
        assert "=" * 60 in output
        assert "Test Section" in output


def test_at74_e2e_reporter_subsection_output():
    """AT-74: Reporter should display subsection headers."""
    from tests.e2e.reporter import E2ETestReporter

    reporter = E2ETestReporter(enabled=True)

    with patch('sys.stdout', new=StringIO()) as fake_out:
        reporter.subsection("Test Subsection")
        output = fake_out.getvalue()
        assert "-" * 40 in output
        assert "Test Subsection" in output


def test_at74_e2e_reporter_command_display():
    """AT-74: Reporter should display commands being executed."""
    from tests.e2e.reporter import E2ETestReporter

    reporter = E2ETestReporter(enabled=True)

    with patch('sys.stdout', new=StringIO()) as fake_out:
        reporter.command(["python", "orchestrate", "run", "test.yaml"], cwd="/tmp/workspace")
        output = fake_out.getvalue()
        assert "Command Execution" in output
        assert "python orchestrate run test.yaml" in output
        assert "Working dir: /tmp/workspace" in output


def test_at74_e2e_reporter_prompt_display():
    """AT-74: Reporter should display prompt content."""
    from tests.e2e.reporter import E2ETestReporter
    import tempfile

    reporter = E2ETestReporter(enabled=True)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("Test prompt content\nLine 2")
        prompt_file = Path(f.name)

    try:
        with patch('sys.stdout', new=StringIO()) as fake_out:
            reporter.prompt(prompt_file)
            output = fake_out.getvalue()
            assert "Agent Input (Prompt)" in output
            assert f"File: {prompt_file}" in output
            assert "Test prompt content" in output
            assert "Line 2" in output
    finally:
        prompt_file.unlink()


def test_at74_e2e_reporter_agent_output_truncation():
    """AT-74: Reporter should truncate long agent output."""
    from tests.e2e.reporter import E2ETestReporter

    reporter = E2ETestReporter(enabled=True)

    # Create long output
    lines = [f"Line {i}" for i in range(100)]
    long_output = "\n".join(lines)

    with patch('sys.stdout', new=StringIO()) as fake_out:
        reporter.agent_output(long_output, truncate=500)
        output = fake_out.getvalue()
        assert "Agent Response" in output
        assert "Line 0" in output  # First line
        assert "Line 99" in output  # Last line
        assert "lines omitted" in output  # Truncation message


def test_at74_e2e_reporter_state_update():
    """AT-74: Reporter should display state updates."""
    from tests.e2e.reporter import E2ETestReporter

    reporter = E2ETestReporter(enabled=True)

    state = {
        "steps": {
            "TestStep": {
                "exit_code": 0,
                "output": "Test output"
            }
        }
    }

    with patch('sys.stdout', new=StringIO()) as fake_out:
        reporter.state_update("TestStep", state)
        output = fake_out.getvalue()
        assert "State Update: TestStep" in output
        assert "Exit code: 0" in output
        assert "Output length: 11 chars" in output


def test_at74_e2e_reporter_artifacts_display():
    """AT-74: Reporter should display created artifacts."""
    from tests.e2e.reporter import E2ETestReporter
    import tempfile
    import glob

    reporter = E2ETestReporter(enabled=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create test artifacts
        artifacts_dir = workspace / "artifacts" / "test"
        artifacts_dir.mkdir(parents=True)
        (artifacts_dir / "file1.txt").write_text("content1")
        (artifacts_dir / "file2.json").write_text('{"key": "value"}')

        with patch('sys.stdout', new=StringIO()) as fake_out:
            reporter.artifacts(workspace)
            output = fake_out.getvalue()
            assert "Created Artifacts" in output
            assert "artifacts/test/file1.txt" in output
            assert "artifacts/test/file2.json" in output
            assert "bytes)" in output  # Size information