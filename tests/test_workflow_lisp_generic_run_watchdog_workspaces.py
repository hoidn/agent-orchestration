"""The generic run watchdog runs in its own workspace and names its target's.

Contract: specs/cli.md "Workspace execution ownership" (one active run per
workspace; a supervising run uses its own workspace) and workflows/README.md
"Generic Run Watchdog Launch".

The watchdog runs through the public entry (`run_workflow`) in workspace W. Its
target runs through `python -m orchestrator run|resume` in workspace T. The
target's steps are one command probe: `<step>.hold` next to it keeps the step
alive until removed, and `<step>.broken` makes it exit 3. The repair agent is a
stand-in that does what the repair prompt asks: it removes the fault, resumes
the target with T as the working directory, and reports.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.workflow_evaluated_totality_helpers import _public_run_files, _write_probe, _write_sources
from tests.test_workflow_resume_after_known_failure import SEQUENCE


REPO_ROOT = Path(__file__).resolve().parents[1]
EXTERNS = REPO_ROOT / "workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog"
ENTRY = "generic_run_watchdog/watchdog::watchdog"
WATCHDOG_FILES = (
    "workflows/library/generic_run_watchdog/watchdog.orc",
    "workflows/library/scripts/probe_orchestrator_run.py",
    "workflows/library/scripts/publish_run_watchdog_result.py",
    "workflows/library/prompts/generic_run_watchdog/repair_run_failure.md",
)
ENV = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}

TARGET_PROBE = """import json, os, sys, time
from pathlib import Path
name = sys.argv[1]
here = Path(__file__)
with open(here.with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(name + "\\n")
hold = here.with_name(name + ".hold")
if hold.exists():
    here.with_name(name + ".started").touch()
    while hold.exists():
        time.sleep(0.05)
if here.with_name(name + ".broken").exists():
    sys.exit(3)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"note": name + "+"}), encoding="utf-8")
"""

REPAIRED = {
    "repair_status": "FIXED_AND_RESUMED",
    "fix_complexity": "TRIVIAL",
    "recovery_action": "RESUME",
    "repair_report_path": "artifacts/work/watchdog/repair-report.md",
    "plan_path": "",
    "new_run_id": "",
}


# Target workspace T.


def _install_target(root: Path, *, marker: str) -> dict[str, Path]:
    """`prepare`, `check`, `finish` over one probe; `check.<marker>` is set."""

    root.mkdir()
    probe = _write_probe(root, "probe", TARGET_PROBE)
    _write_sources(root, {"grt/entry.orc": SEQUENCE.replace("TARGET", "2.33").replace("PROBE", probe.as_posix())})
    probe.with_name(f"check.{marker}").touch()
    return {**_public_run_files(root, {"probe": probe}), "probe": probe}


def _run_target(files: dict[str, Path]) -> list[str]:
    return [
        sys.executable, "-m", "orchestrator", "run", str(files["source"]), "--source-root", str(files["source_root"]),
        "--entry-workflow", "run", "--provider-externs-file", str(files["providers"]),
        "--prompt-externs-file", str(files["prompts"]), "--command-boundaries-file", str(files["commands"]),
    ]








@pytest.fixture
def active_target(tmp_path: Path):
    """A target run in T whose `check` step is alive until the test releases it."""

    files = _install_target(tmp_path / "T", marker="hold")
    process = subprocess.Popen(
        _run_target(files), cwd=files["source_root"], env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    started = files["probe"].with_name("check.started")
    deadline = time.monotonic() + 60
    while not started.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            process.kill()
            pytest.fail(f"target did not reach its held step: {process.communicate()[0]}")
        time.sleep(0.05)
    yield files
    files["probe"].with_name("check.hold").unlink(missing_ok=True)
    try:
        process.wait(timeout=60)
    finally:
        if process.poll() is None:
            process.kill()


# Watchdog workspace W.




def _install_watchdog(root: Path) -> Path:
    for relpath in WATCHDOG_FILES:
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relpath, root / relpath)
    return root










@pytest.mark.parametrize(
    "target_workspace",
    ["relative/T", "{tmp}/missing", "{tmp}/T-without-the-run", "{tmp}/W"],
    ids=["relative", "missing", "no-run-directory", "the-watchdog-workspace"],
)
def test_the_probe_refuses_a_target_workspace_it_cannot_observe(tmp_path: Path, target_workspace: str) -> None:
    watchdog = _install_watchdog(tmp_path / "W")
    (tmp_path / "T-without-the-run" / ".orchestrate" / "runs" / "other-run").mkdir(parents=True)
    (watchdog / ".orchestrate" / "runs" / "target-run").mkdir(parents=True)

    probe = subprocess.run(
        [
            sys.executable, "workflows/library/scripts/probe_orchestrator_run.py",
            "--run-id", "target-run", "--target-workspace", target_workspace.format(tmp=tmp_path),
            "--output", "state/watchdog/watch.json", "--evidence-root", "artifacts/work/watchdog",
            "--repair-result-target-path", "artifacts/work/watchdog/repair-result.json",
        ],
        cwd=watchdog, capture_output=True, text=True, check=False,
    )

    assert (probe.returncode, (watchdog / "state/watchdog/watch.json").exists()) == (1, False)


@pytest.mark.parametrize("run_id", ["..", "."])
def test_the_probe_refuses_a_run_id_that_names_a_directory_above_the_run(tmp_path: Path, run_id: str) -> None:
    watchdog = _install_watchdog(tmp_path / "W")
    runs = tmp_path / "T" / ".orchestrate" / "runs"
    runs.mkdir(parents=True)
    for state in (runs.parent / "state.json", runs / "state.json"):
        state.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    probe = subprocess.run(
        [
            sys.executable, "workflows/library/scripts/probe_orchestrator_run.py",
            "--run-id", run_id, "--target-workspace", str(tmp_path / "T"),
            "--output", "state/watchdog/watch.json", "--evidence-root", "artifacts/work/watchdog",
            "--repair-result-target-path", "artifacts/work/watchdog/repair-result.json",
        ],
        cwd=watchdog, capture_output=True, text=True, check=False,
    )

    assert (probe.returncode, (watchdog / "state/watchdog/watch.json").exists()) == (1, False)
