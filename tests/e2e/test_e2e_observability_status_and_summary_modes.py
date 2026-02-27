"""E2E coverage for report command and summary modes."""

import json
import time
from pathlib import Path

from orchestrator.cli.main import main


def _wait_for(path: Path, timeout_sec: float = 3.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return False


def _latest_run_dir(workspace: Path) -> Path:
    runs = workspace / ".orchestrate" / "runs"
    assert runs.exists()
    run_dirs = sorted([p for p in runs.iterdir() if p.is_dir()])
    assert run_dirs
    return run_dirs[-1]


def _write_workflow(workspace: Path) -> Path:
    (workspace / "prompts").mkdir(parents=True, exist_ok=True)
    (workspace / "prompts" / "prompt.md").write_text("Do one provider call.")

    workflow_path = workspace / "workflow.yaml"
    workflow_path.write_text(
        """
version: "1.3"
name: observability-e2e
providers:
  local_provider:
    command: ["python", "-c", "print('provider-ok')"]
    input_mode: "argv"
  summary_ok:
    command: ["python", "-c", "print('summary-ok')"]
    input_mode: "argv"
  summary_fail:
    command: ["bash", "-lc", "exit 9"]
    input_mode: "argv"
steps:
  - name: CmdStep
    command: ["bash", "-lc", "echo cmd-ok"]
    output_capture: text
  - name: ProviderStep
    provider: local_provider
    input_file: prompts/prompt.md
    output_capture: text
""".strip()
        + "\n"
    )
    return workflow_path


def test_e2e_report_and_async_summaries(monkeypatch, tmp_path, capsys):
    workspace = tmp_path
    workflow = _write_workflow(workspace)
    monkeypatch.chdir(workspace)

    rc = main(
        [
            "run",
            str(workflow),
            "--debug",
            "--step-summaries",
            "--summary-mode",
            "async",
            "--summary-provider",
            "summary_ok",
        ]
    )
    assert rc == 0

    run_dir = _latest_run_dir(workspace)
    assert _wait_for(run_dir / "summaries" / "CmdStep.summary.md")
    assert _wait_for(run_dir / "summaries" / "ProviderStep.summary.md")

    state = json.loads((run_dir / "state.json").read_text())
    assert state["steps"]["CmdStep"]["status"] == "completed"
    assert state["steps"]["ProviderStep"]["status"] == "completed"

    rc = main(["report", "--run-id", run_dir.name, "--format", "md"])
    assert rc == 0
    report_output = capsys.readouterr().out
    assert "# Workflow Status" in report_output
    assert "CmdStep" in report_output
    assert "ProviderStep" in report_output


def test_e2e_sync_summaries_are_deterministic(monkeypatch, tmp_path):
    workspace = tmp_path
    workflow = _write_workflow(workspace)
    monkeypatch.chdir(workspace)

    rc = main(
        [
            "run",
            str(workflow),
            "--step-summaries",
            "--summary-mode",
            "sync",
            "--summary-provider",
            "summary_ok",
        ]
    )
    assert rc == 0

    run_dir = _latest_run_dir(workspace)
    assert (run_dir / "summaries" / "CmdStep.summary.md").exists()
    assert (run_dir / "summaries" / "ProviderStep.summary.md").exists()


def test_e2e_async_summary_failure_does_not_fail_workflow(monkeypatch, tmp_path):
    workspace = tmp_path
    workflow = _write_workflow(workspace)
    monkeypatch.chdir(workspace)

    rc = main(
        [
            "run",
            str(workflow),
            "--step-summaries",
            "--summary-mode",
            "async",
            "--summary-provider",
            "summary_fail",
        ]
    )
    assert rc == 0

    run_dir = _latest_run_dir(workspace)
    assert _wait_for(run_dir / "summaries" / "CmdStep.error.json")

    state = json.loads((run_dir / "state.json").read_text())
    assert state["status"] == "completed"
    assert state["steps"]["CmdStep"]["status"] == "completed"
