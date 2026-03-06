from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from orchestrator.demo.trial_runner import run_trial


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "examples" / "generic_task_plan_execute_review_loop.yaml"
LINEAR_EVAL = ROOT / "scripts" / "demo" / "evaluate_linear_classifier.py"
NANOBRAGG_EVAL = ROOT / "scripts" / "demo" / "evaluate_nanobragg_accumulation.py"


def _install_runner_doubles(
    *,
    monkeypatch,
    experiment_root: Path,
    seed_repo: Path,
    task_file: Path,
) -> tuple[list[dict[str, object]], list[tuple[list[str], Path | None]]]:
    direct_workspace = experiment_root / "direct-run"
    workflow_workspace = experiment_root / "workflow-run"
    archive_dir = experiment_root / "archive"
    for path in (direct_workspace, workflow_workspace, archive_dir):
        path.mkdir(parents=True, exist_ok=True)

    provision_calls: list[dict[str, object]] = []
    subprocess_calls: list[tuple[list[str], Path | None]] = []

    def fake_provision_trial(**kwargs):
        provision_calls.append(kwargs)
        return {
            "seed_repo": str(seed_repo),
            "task_file": str(task_file),
            "start_commit": "abc123",
            "workspaces": {
                "seed": str(experiment_root / "seed"),
                "direct_run": str(direct_workspace),
                "workflow_run": str(workflow_workspace),
            },
        }

    def fake_run(args, cwd=None, check=False, capture_output=False, text=False, **_):
        subprocess_calls.append((list(args), Path(cwd) if cwd is not None else None))
        command = list(args)
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=" M changed.txt\n", stderr="")
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="abc123\n", stderr="")
        if command[:5] == ["env", f"PYTHONPATH={ROOT}", sys.executable, "-m", "orchestrator"]:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="workflow ok\n", stderr="")
        if command[:2] == [sys.executable, str(LINEAR_EVAL)]:
            workspace = Path(command[2])
            verdict = "PASS" if workspace == workflow_workspace else "FAIL"
            return subprocess.CompletedProcess(
                args=command,
                returncode=0 if verdict == "PASS" else 1,
                stdout=json.dumps(
                    {
                        "verdict": verdict,
                        "failure_categories": [] if verdict == "PASS" else ["hidden_acceptance_failed"],
                        "summary": {"hidden_tests_passed": verdict == "PASS"},
                        "soft_quality": {"score": 1.0 if verdict == "PASS" else 0.2, "findings": []},
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected subprocess call: {command}")

    class FakePopen:
        def __init__(self, args, cwd=None, stdout=None, stderr=None, text=None, **_):
            command = list(args)
            self.args = command
            self.cwd = cwd
            self.pid = 4242 if command[:2] == ["claude", "-p"] else 5252
            if command[:2] == ["claude", "-p"]:
                self.returncode = 0
                self._stdout = "direct ok\n"
                self._stderr = ""
            elif command[:5] == ["env", f"PYTHONPATH={ROOT}", sys.executable, "-m", "orchestrator"]:
                self.returncode = 0
                self._stdout = "workflow ok\n"
                self._stderr = ""
            else:
                raise AssertionError(f"Unexpected Popen call: {command}")

        def communicate(self, timeout=None):
            return self._stdout, self._stderr

    monkeypatch.setattr("orchestrator.demo.trial_runner.provision_trial", fake_provision_trial)
    monkeypatch.setattr("orchestrator.demo.trial_runner.subprocess.run", fake_run)
    monkeypatch.setattr("orchestrator.demo.trial_runner.subprocess.Popen", FakePopen)
    return provision_calls, subprocess_calls


def test_run_trial_writes_runner_state_and_partial_result(tmp_path: Path, monkeypatch):
    experiment_root = tmp_path / "experiment"
    seed_repo = tmp_path / "seed-repo"
    task_file = tmp_path / "port_linear_classifier_to_rust.md"
    task_file.write_text("translate the module\n")
    _install_runner_doubles(
        monkeypatch=monkeypatch,
        experiment_root=experiment_root,
        seed_repo=seed_repo,
        task_file=task_file,
    )

    run_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=WORKFLOW,
        direct_prompt="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        commitish="HEAD",
    )

    runner_state_path = experiment_root / "archive" / "runner-state.json"
    partial_result_path = experiment_root / "archive" / "partial-trial-result.json"

    assert runner_state_path.is_file()
    assert partial_result_path.is_file()

    runner_state = json.loads(runner_state_path.read_text())
    assert runner_state["status"] == "completed"
    assert runner_state["direct"]["status"] == "succeeded"
    assert runner_state["workflow"]["status"] == "succeeded"


def test_run_trial_emits_event_log(tmp_path: Path, monkeypatch):
    experiment_root = tmp_path / "experiment"
    seed_repo = tmp_path / "seed-repo"
    task_file = tmp_path / "port_linear_classifier_to_rust.md"
    task_file.write_text("translate the module\n")
    _install_runner_doubles(
        monkeypatch=monkeypatch,
        experiment_root=experiment_root,
        seed_repo=seed_repo,
        task_file=task_file,
    )

    run_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=WORKFLOW,
        direct_prompt="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        commitish="HEAD",
    )

    event_log_path = experiment_root / "archive" / "runner-events.jsonl"

    assert event_log_path.is_file()

    event_types = [json.loads(line)["event"] for line in event_log_path.read_text().splitlines()]
    assert event_types[:4] == [
        "trial_started",
        "provisioning_completed",
        "arm_started",
        "arm_completed",
    ]


def test_run_trial_writes_per_arm_process_metadata_and_logs(tmp_path: Path, monkeypatch):
    experiment_root = tmp_path / "experiment"
    seed_repo = tmp_path / "seed-repo"
    task_file = tmp_path / "port_linear_classifier_to_rust.md"
    task_file.write_text("translate the module\n")
    _install_runner_doubles(
        monkeypatch=monkeypatch,
        experiment_root=experiment_root,
        seed_repo=seed_repo,
        task_file=task_file,
    )

    run_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=WORKFLOW,
        direct_prompt="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        commitish="HEAD",
    )

    direct_process_path = experiment_root / "archive" / "direct" / "process.json"
    direct_stdout_path = experiment_root / "archive" / "direct" / "stdout.log"
    direct_stderr_path = experiment_root / "archive" / "direct" / "stderr.log"
    workflow_process_path = experiment_root / "archive" / "workflow" / "process.json"
    workflow_stdout_path = experiment_root / "archive" / "workflow" / "stdout.log"
    workflow_stderr_path = experiment_root / "archive" / "workflow" / "stderr.log"

    assert direct_process_path.is_file()
    assert direct_stdout_path.is_file()
    assert direct_stderr_path.is_file()
    assert workflow_process_path.is_file()
    assert workflow_stdout_path.is_file()
    assert workflow_stderr_path.is_file()

    direct_process = json.loads(direct_process_path.read_text())
    assert direct_process["backend"] == "subprocess"
    assert direct_process["cwd"] == str(experiment_root / "direct-run")


def test_run_trial_writes_heartbeat_files(tmp_path: Path, monkeypatch):
    experiment_root = tmp_path / "experiment"
    seed_repo = tmp_path / "seed-repo"
    task_file = tmp_path / "port_linear_classifier_to_rust.md"
    task_file.write_text("translate the module\n")
    _install_runner_doubles(
        monkeypatch=monkeypatch,
        experiment_root=experiment_root,
        seed_repo=seed_repo,
        task_file=task_file,
    )

    run_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=WORKFLOW,
        direct_prompt="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        commitish="HEAD",
    )

    direct_heartbeat_path = experiment_root / "archive" / "direct" / "heartbeat.json"
    workflow_heartbeat_path = experiment_root / "archive" / "workflow" / "heartbeat.json"

    assert direct_heartbeat_path.is_file()
    assert workflow_heartbeat_path.is_file()

    direct_heartbeat = json.loads(direct_heartbeat_path.read_text())
    assert direct_heartbeat["alive"] is False
    assert direct_heartbeat["elapsed_sec"] >= 0


def test_run_trial_records_nanobragg_evaluator_status(tmp_path: Path, monkeypatch):
    experiment_root = tmp_path / "experiment"
    seed_repo = tmp_path / "demo_task_nanobragg_accumulation_port"
    task_file = tmp_path / "port_nanobragg_accumulation_to_pytorch.md"
    task_file.write_text("translate the module\n")
    _install_runner_doubles(
        monkeypatch=monkeypatch,
        experiment_root=experiment_root,
        seed_repo=seed_repo,
        task_file=task_file,
    )

    run_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=WORKFLOW,
        direct_prompt="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        commitish="HEAD",
    )

    evaluator_status_path = experiment_root / "archive" / "evaluator" / "status.json"
    status = json.loads(evaluator_status_path.read_text())

    assert status["status"] == "completed"
    assert status["command"] == [sys.executable, str(NANOBRAGG_EVAL)]


def test_run_trial_records_direct_timeout(tmp_path: Path, monkeypatch):
    experiment_root = tmp_path / "experiment"
    seed_repo = tmp_path / "seed-repo"
    task_file = tmp_path / "port_linear_classifier_to_rust.md"
    task_file.write_text("translate the module\n")
    direct_workspace = experiment_root / "direct-run"
    workflow_workspace = experiment_root / "workflow-run"
    archive_dir = experiment_root / "archive"
    for path in (direct_workspace, workflow_workspace, archive_dir):
        path.mkdir(parents=True, exist_ok=True)

    def fake_provision_trial(**_kwargs):
        return {
            "seed_repo": str(seed_repo),
            "task_file": str(task_file),
            "start_commit": "abc123",
            "workspaces": {
                "seed": str(experiment_root / "seed"),
                "direct_run": str(direct_workspace),
                "workflow_run": str(workflow_workspace),
            },
        }

    def fake_run(args, cwd=None, check=False, capture_output=False, text=False, **_):
        command = list(args)
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=" M changed.txt\n", stderr="")
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="abc123\n", stderr="")
        if command[:2] == [sys.executable, str(LINEAR_EVAL)]:
            return subprocess.CompletedProcess(
                args=command,
                returncode=1,
                stdout=json.dumps(
                    {
                        "verdict": "FAIL",
                        "failure_categories": ["hidden_acceptance_failed"],
                        "summary": {"hidden_tests_passed": False},
                        "soft_quality": {"score": 0.0, "findings": []},
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected subprocess call: {command}")

    class TimeoutPopen:
        def __init__(self, args, cwd=None, stdout=None, stderr=None, text=None, **_):
            command = list(args)
            self.args = command
            self.cwd = cwd
            self.pid = 4242 if command[:2] == ["claude", "-p"] else 5252
            self.returncode = None
            self._timed_out = command[:2] == ["claude", "-p"]

        def communicate(self, timeout=None):
            if self._timed_out:
                raise subprocess.TimeoutExpired(cmd=self.args, timeout=timeout or 1)
            self.returncode = 0
            return "workflow ok\n", ""

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            if self.returncode is None:
                self.returncode = -15
            return self.returncode

    monkeypatch.setattr("orchestrator.demo.trial_runner.provision_trial", fake_provision_trial)
    monkeypatch.setattr("orchestrator.demo.trial_runner.subprocess.run", fake_run)
    monkeypatch.setattr("orchestrator.demo.trial_runner.subprocess.Popen", TimeoutPopen)

    result = run_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=WORKFLOW,
        direct_prompt="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        commitish="HEAD",
        direct_timeout_sec=1,
        workflow_timeout_sec=1,
    )

    runner_state = json.loads((archive_dir / "runner-state.json").read_text())
    event_types = [json.loads(line)["event"] for line in (archive_dir / "runner-events.jsonl").read_text().splitlines()]
    partial_result = json.loads((archive_dir / "partial-trial-result.json").read_text())

    assert runner_state["direct"]["status"] == "timed_out"
    assert runner_state["direct"]["timed_out"] is True
    assert "arm_timeout" in event_types
    assert partial_result["direct"]["execution"]["timed_out"] is True
    assert result["direct"]["execution"]["timed_out"] is True


def test_run_trial_writes_freeze_and_evaluator_artifacts(tmp_path: Path, monkeypatch):
    experiment_root = tmp_path / "experiment"
    seed_repo = tmp_path / "seed-repo"
    task_file = tmp_path / "port_linear_classifier_to_rust.md"
    task_file.write_text("translate the module\n")
    _install_runner_doubles(
        monkeypatch=monkeypatch,
        experiment_root=experiment_root,
        seed_repo=seed_repo,
        task_file=task_file,
    )

    run_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=WORKFLOW,
        direct_prompt="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        commitish="HEAD",
    )

    direct_freeze_dir = experiment_root / "archive" / "direct" / "freeze"
    workflow_freeze_dir = experiment_root / "archive" / "workflow" / "freeze"
    evaluator_dir = experiment_root / "archive" / "evaluator"

    assert (direct_freeze_dir / "workspace-status.txt").is_file()
    assert (direct_freeze_dir / "workspace-head.txt").is_file()
    assert (direct_freeze_dir / "tree.txt").is_file()
    assert (workflow_freeze_dir / "workspace-status.txt").is_file()
    assert (workflow_freeze_dir / "workspace-head.txt").is_file()
    assert (workflow_freeze_dir / "tree.txt").is_file()

    assert (evaluator_dir / "status.json").is_file()
    assert (evaluator_dir / "direct-result.json").is_file()
    assert (evaluator_dir / "workflow-result.json").is_file()

    evaluator_status = json.loads((evaluator_dir / "status.json").read_text())
    assert evaluator_status["status"] == "completed"
