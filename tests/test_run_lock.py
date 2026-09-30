"""Process-level contract tests for one writer per run root."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Iterator

import pytest

from orchestrator.run_lock import RunAlreadyActiveError, run_writer_lock


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_HOLDER_SCRIPT = """
import sys
import time
from pathlib import Path

from orchestrator.run_lock import run_writer_lock

run_root = Path(sys.argv[1])
ready_path = Path(sys.argv[2])
release_path = Path(sys.argv[3])

with run_writer_lock(run_root):
    ready_path.write_text("ready\\n", encoding="utf-8")
    while not release_path.exists():
        time.sleep(0.01)
"""


@contextmanager
def _subprocess_writer(run_root: Path) -> Iterator[subprocess.Popen[str]]:
    ready_path = run_root.parent / f".{run_root.name}.lock-ready"
    release_path = run_root.parent / f".{run_root.name}.lock-release"
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _HOLDER_SCRIPT,
            str(run_root),
            str(ready_path),
            str(release_path),
        ],
        cwd=_REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 5.0
    try:
        while not ready_path.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                pytest.fail(
                    "lock-holder subprocess exited before acquiring the lock:\n"
                    f"stdout:\n{stdout}\nstderr:\n{stderr}"
                )
            if time.monotonic() >= deadline:
                pytest.fail("lock-holder subprocess did not acquire the lock")
            time.sleep(0.01)
        yield process
    finally:
        release_path.touch()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


def test_second_writer_for_same_run_fails_fast(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "same-run"
    run_root.mkdir(parents=True)

    with _subprocess_writer(run_root):
        started_at = time.monotonic()
        with pytest.raises(RunAlreadyActiveError) as exc_info:
            with run_writer_lock(run_root):
                pytest.fail("a second writer acquired the same run lock")
        elapsed = time.monotonic() - started_at

    assert exc_info.value.code == "run_already_active"
    assert "run_already_active" in str(exc_info.value)
    assert exc_info.value.run_root == run_root
    assert elapsed < 1.0


def test_distinct_runs_can_hold_writer_locks_independently(tmp_path: Path) -> None:
    first_run_root = tmp_path / "runs" / "first-run"
    second_run_root = tmp_path / "runs" / "second-run"
    first_run_root.mkdir(parents=True)
    second_run_root.mkdir(parents=True)

    with _subprocess_writer(first_run_root):
        with run_writer_lock(second_run_root):
            assert (second_run_root / "run.lock").is_file()


def test_read_only_report_remains_available_while_writer_lock_is_held(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"
    run_root = runs_root / "reportable-run"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1",
                "run_id": "reportable-run",
                "workflow_file": "workflow.orc",
                "status": "failed",
                "started_at": "2026-07-30T00:00:00+00:00",
                "updated_at": "2026-07-30T00:00:01+00:00",
                "steps": {},
                "error": {
                    "type": "synthetic_failure",
                    "message": "read-only report fixture",
                },
            }
        ),
        encoding="utf-8",
    )
    report_script = """
import sys

from orchestrator.cli.commands.report import report_workflow

raise SystemExit(
    report_workflow(run_id=sys.argv[1], runs_root=sys.argv[2], format="json")
)
"""

    with _subprocess_writer(run_root):
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                report_script,
                "reportable-run",
                str(runs_root),
            ],
            cwd=_REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["run"]["run_id"] == "reportable-run"
    assert report["run"]["status"] == "failed"
