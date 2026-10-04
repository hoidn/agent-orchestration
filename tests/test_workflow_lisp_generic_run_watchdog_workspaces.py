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
from contextlib import ExitStack, chdir
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.providers.executor import ProviderExecutor
from tests.test_workflow_lisp_generic_union_provider_results import _Provider
from tests.test_workflow_lisp_generic_unions_runtime import _log, _public_run_files, _write_probe, _write_sources
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args
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


def _orchestrator(workspace: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        cwd=workspace, env=ENV, capture_output=True, text=True, timeout=120, check=False,
    )


def _target_run_ids(root: Path) -> list[str]:
    return sorted(path.name for path in (root / ".orchestrate" / "runs").iterdir())


def _target_status(root: Path) -> str:
    [run_id] = _target_run_ids(root)
    return json.loads((root / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8"))["status"]


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


class _RepairAgent(_Provider):
    """Does what the repair prompt asks: repair the fault, resume the target from its workspace, report."""

    def __init__(self) -> None:
        super().__init__(REPAIRED)
        self.resumes: list[int] = []

    def execute(self, invocation, **kwargs):
        watch = json.loads(Path("state/watchdog/watch.json").read_text(encoding="utf-8"))
        target = Path(watch["target_workspace"])
        (target / "check.broken").unlink()
        self.resumes.append(
            _orchestrator(target, sys.executable, "-m", "orchestrator", "resume", watch["target_run_id"]).returncode
        )
        report = Path(REPAIRED["repair_report_path"])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("# Repair report\n", encoding="utf-8")
        report.with_name("repair-result.json").write_text(json.dumps(REPAIRED), encoding="utf-8")
        return super().execute(invocation, **kwargs)


def _install_watchdog(root: Path) -> Path:
    for relpath in WATCHDOG_FILES:
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relpath, root / relpath)
    return root


def _watchdog(workspace: Path, *, target: Path, agent: _Provider):
    """The documented launch (workflows/README.md), run from `workspace`."""

    library = _install_watchdog(workspace) / "workflows/library"
    files = {
        "source": library / "generic_run_watchdog/watchdog.orc",
        "source_root": library,
        "providers": Path(f"{EXTERNS}.providers.json"),
        "prompts": Path(f"{EXTERNS}.prompts.json"),
    }
    inputs = workspace / "inputs.json"
    inputs.write_text(
        json.dumps(
            {
                "target_run_id": _target_run_ids(target)[0],
                "target_workspace": str(target),
                "state_root": "state/watchdog",
                "evidence_root": "artifacts/work/watchdog",
                "repair_result_target_path": "artifacts/work/watchdog/repair-result.json",
            }
        ),
        encoding="utf-8",
    )
    args = _run_args(files, input_file=inputs)
    args.entry_workflow = ENTRY
    args.command_boundaries_file = f"{EXTERNS}.commands.json"
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"PYTHONPATH": str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")}))
        stack.enter_context(chdir(workspace))
        stack.enter_context(patch.object(ProviderExecutor, "prepare_invocation", agent.prepare_invocation))
        stack.enter_context(patch.object(ProviderExecutor, "execute", agent.execute))
        stack.enter_context(patch.object(sys, "argv", ["orchestrator", "run", str(files["source"])]))
        return run_workflow(args)


def test_a_watchdog_in_its_own_workspace_reports_an_active_target_as_running(tmp_path: Path, active_target) -> None:
    agent = _Provider(REPAIRED)

    result = _watchdog(tmp_path / "W", target=active_target["source_root"], agent=agent)

    assert (result.exit_code, dict(result.workflow_outputs), agent.calls) == (
        0,
        {
            "return__watch_status": "RUNNING_OK",
            "return__repair_status": "NO_ACTION",
            "return__recovery_action": "NONE",
            "return__watchdog_result_path": "state/watchdog/watchdog-result.json",
        },
        0,
    )


def test_the_repair_resumes_a_failed_target_from_its_workspace_and_the_target_completes(tmp_path: Path) -> None:
    target = _install_target(tmp_path / "T", marker="broken")
    assert _orchestrator(target["source_root"], *_run_target(target)).returncode == 1
    [target_run] = _target_run_ids(target["source_root"])
    agent = _RepairAgent()

    result = _watchdog(tmp_path / "W", target=target["source_root"], agent=agent)

    assert {
        "watchdog": (result.exit_code, result.workflow_outputs["return__repair_status"]),
        "resumes": agent.resumes,
        "target": (_target_status(target["source_root"]), _log(target["probe"])),
        "runs in T": _target_run_ids(target["source_root"]),
        "watchdog run in W": (tmp_path / "W/.orchestrate/runs" / result.run_id / "state.json").is_file(),
    } == {
        "watchdog": (0, "FIXED_AND_RESUMED"),
        "resumes": [0],
        "target": ("completed", ["prepare", "check", "check", "finish"]),
        "runs in T": [target_run],
        "watchdog run in W": True,
    }


def test_a_watchdog_started_in_the_target_workspace_while_the_target_is_active_is_refused(
    tmp_path: Path, active_target, caplog: pytest.LogCaptureFixture
) -> None:
    agent = _Provider(REPAIRED)

    result = _watchdog(active_target["source_root"], target=active_target["source_root"], agent=agent)

    assert (result.exit_code, "workspace_run_already_active" in caplog.text, agent.calls) == (2, True, 0)


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
