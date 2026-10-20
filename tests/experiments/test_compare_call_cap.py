"""The comparison shim refuses excess calls before running a scripted CLI."""

import json
from pathlib import Path

import pytest

from tests.experiments.compare_harness_support import call, skip_without_sandbox, start, world  # noqa: F401

skip_without_sandbox()


@pytest.mark.parametrize("binary", ["claude", "codex"])
def test_cap_refuses_excess_call_and_hides_controller_cap(world, monkeypatch, binary):
    _, record = start(world, "direct_task")
    monkeypatch.setenv("COMPARE_MAX_CALLS", "1")
    first = call(world, record, 'test -z "${COMPARE_MAX_CALLS+set}"', binary=binary)
    assert first.returncode == 0, first.stderr
    second = call(world, record, 'echo should-not-run', binary=binary)
    assert second.returncode == 75
    assert "should-not-run" not in second.stdout
    assert "COMPARE_MAX_CALLS" in second.stderr
    assert (Path(record["records"]) / "calls/2/stderr.txt").read_text() == second.stderr


@pytest.mark.parametrize("cap", ["0", "invalid", "-1", "1.5", ""])
def test_zero_or_malformed_cap_fails_closed(world, monkeypatch, cap):
    _, record = start(world, "direct_task")
    monkeypatch.setenv("COMPARE_MAX_CALLS", cap)
    result = call(world, record, 'echo should-not-run')
    assert result.returncode == 75
    assert "should-not-run" not in result.stdout
