from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from orchestrator.demo.trial_runner import run_trial


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "examples" / "generic_task_plan_execute_review_loop.yaml"
NANOBRAGG_EVAL = ROOT / "scripts" / "demo" / "evaluate_nanobragg_accumulation.py"


def test_run_trial_smoke_archives_nanobragg_results(tmp_path: Path, monkeypatch):
    experiment_root = tmp_path / "experiment"
    seed_repo = tmp_path / "demo_task_nanobragg_accumulation_port"
    task_file = tmp_path / "port_nanobragg_accumulation_to_pytorch.md"
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
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="abc123\n", stderr="")
        if command[:2] == [sys.executable, str(NANOBRAGG_EVAL)]:
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
                        "soft_quality": {"score": 1.0 if verdict == "PASS" else 0.3, "findings": []},
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected subprocess.run call: {command}")

    class FakePopen:
        def __init__(self, args, cwd=None, stdout=None, stderr=None, text=None, **_):
            command = list(args)
            self.args = command
            self.cwd = cwd
            self.pid = 4242 if command[:2] == ["claude", "-p"] else 5252
            self.returncode = 0
            self._stdout = "ok\n"
            self._stderr = ""

        def communicate(self, timeout=None):
            return self._stdout, self._stderr

    monkeypatch.setattr("orchestrator.demo.trial_runner.provision_trial", fake_provision_trial)
    monkeypatch.setattr("orchestrator.demo.trial_runner.subprocess.run", fake_run)
    monkeypatch.setattr("orchestrator.demo.trial_runner.subprocess.Popen", FakePopen)

    result = run_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=WORKFLOW,
        direct_prompt="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        commitish="HEAD",
    )

    assert (archive_dir / "direct-command.json").is_file()
    assert (archive_dir / "workflow-command.json").is_file()
    assert (archive_dir / "evaluator" / "direct-result.json").is_file()
    assert (archive_dir / "evaluator" / "workflow-result.json").is_file()
    assert (archive_dir / "trial-result.json").is_file()

    persisted = json.loads((archive_dir / "trial-result.json").read_text())
    assert persisted["seed_repo"].endswith("demo_task_nanobragg_accumulation_port")
    assert persisted["direct"]["evaluation"]["verdict"] == "FAIL"
    assert persisted["workflow"]["evaluation"]["verdict"] == "PASS"
    assert result == persisted
