"""The suite-wide provider guard in `tests/conftest.py`: a provider CLI name resolved from the test process's own
PATH reaches a blocking stub, never a real CLI, and a run whose processes reached a stub fails."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_default_test_environment_resolves_claude_to_the_blocking_stub(tmp_path):
    log = tmp_path / "calls.log"           # keep this deliberate hit out of the session's log
    result = subprocess.run(["claude", "--version"], env={**os.environ, "ORC_TEST_PROVIDER_GUARD_LOG": str(log)},
                            capture_output=True, text=True, check=False, timeout=30)
    assert (result.returncode, "test provider guard" in result.stderr, log.read_text().startswith("claude argv=[--version]")
            ) == (97, True, True), result


def test_a_run_whose_test_reaches_a_stub_fails_and_names_the_test(tmp_path):
    (tmp_path / "test_leak.py").write_text(
        "import subprocess\n"
        "def test_leaks():\n"
        "    assert subprocess.run(['codex', 'exec', 'hi'], capture_output=True).returncode == 97\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "tests.conftest", "-p", "no:cacheprovider",
                             f"--basetemp={tmp_path / 'b'}", str(tmp_path / "test_leak.py")],
                            cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(ROOT)},
                            capture_output=True, text=True, check=False, timeout=120)
    assert (result.returncode, "1 passed" in result.stdout,
            "codex argv=[exec hi] test=[test_leak.py::test_leaks (call)]" in result.stdout) == (1, True, True), result.stdout
