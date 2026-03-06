from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from orchestrator.demo.trial_runner import _select_evaluator, build_direct_command, build_workflow_command, run_trial


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflows" / "examples" / "generic_task_plan_execute_review_loop.yaml"
LINEAR_EVAL = ROOT / "scripts" / "demo" / "evaluate_linear_classifier.py"
NANOBRAGG_EVAL = ROOT / "scripts" / "demo" / "evaluate_nanobragg_accumulation.py"


def test_build_direct_command_matches_expected_cli_shape():
    prompt = "Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md."

    command = build_direct_command(prompt)

    assert command == [
        "claude",
        "-p",
        prompt,
        "--dangerously-skip-permissions",
        "--model",
        "claude-sonnet-4-6",
    ]


def test_build_workflow_command_matches_expected_cli_shape():
    local_workflow = Path("workflows/examples/generic_task_plan_execute_review_loop.yaml")
    command = build_workflow_command(
        workflow_path=local_workflow,
        repo_root=ROOT,
    )

    assert command == [
        "env",
        f"PYTHONPATH={ROOT}",
        sys.executable,
        "-m",
        "orchestrator",
        "run",
        str(local_workflow),
    ]


def test_select_evaluator_picks_nanobragg_hidden_evaluator_for_seed_and_task_names():
    by_task = _select_evaluator(
        seed_repo=Path("/tmp/other-seed"),
        task_file=Path("/tmp/port_nanobragg_accumulation_to_pytorch.md"),
    )
    by_seed = _select_evaluator(
        seed_repo=Path("/tmp/demo_task_nanobragg_accumulation_port"),
        task_file=Path("/tmp/other-task.md"),
    )

    assert by_task == [sys.executable, str(NANOBRAGG_EVAL)]
    assert by_seed == [sys.executable, str(NANOBRAGG_EVAL)]


def test_run_trial_provisions_launches_archives_and_evaluates(tmp_path: Path, monkeypatch):
    experiment_root = tmp_path / "experiment"
    seed_repo = tmp_path / "seed-repo"
    task_file = tmp_path / "port_linear_classifier_to_rust.md"
    task_file.write_text("translate the module\n")
    direct_workspace = experiment_root / "direct-run"
    workflow_workspace = experiment_root / "workflow-run"
    archive_dir = experiment_root / "archive"
    for path in (direct_workspace, workflow_workspace, archive_dir):
        path.mkdir(parents=True, exist_ok=True)

    provision_calls: list[dict[str, object]] = []
    subprocess_calls: list[tuple[list[str], Path | None]] = []
    popen_calls: list[tuple[list[str], Path | None]] = []

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
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout=" M changed.txt\n", stderr="")
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="abc123\n", stderr="")
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
            popen_calls.append((command, Path(cwd) if cwd is not None else None))
            self.args = command
            self.cwd = cwd
            self.pid = 4242 if command[:2] == ["claude", "-p"] else 5252
            if command[:2] == ["claude", "-p"]:
                self.returncode = 0
                self._stdout = "direct ok\n"
                self._stderr = ""
            elif command[:2] == ["env", f"PYTHONPATH={ROOT}"]:
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

    result = run_trial(
        seed_repo=seed_repo,
        experiment_root=experiment_root,
        task_file=task_file,
        workflow_path=WORKFLOW,
        direct_prompt="Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
        commitish="HEAD",
    )

    assert provision_calls == [
        {
            "seed_repo": seed_repo,
            "experiment_root": experiment_root,
            "task_file": task_file,
            "workflow_path": WORKFLOW,
            "workflow_prompts_dir": ROOT / "prompts" / "workflows",
            "commitish": "HEAD",
        }
    ]
    assert subprocess_calls == [
        (["git", "status", "--short"], direct_workspace),
        (["git", "rev-parse", "HEAD"], direct_workspace),
        (["git", "status", "--short"], direct_workspace),
        (["git", "rev-parse", "HEAD"], direct_workspace),
        (["git", "status", "--short"], workflow_workspace),
        (["git", "rev-parse", "HEAD"], workflow_workspace),
        (["git", "status", "--short"], workflow_workspace),
        (["git", "rev-parse", "HEAD"], workflow_workspace),
        ([sys.executable, str(LINEAR_EVAL), str(direct_workspace)], ROOT),
        ([sys.executable, str(LINEAR_EVAL), str(workflow_workspace)], ROOT),
    ]
    assert popen_calls == [
        (
            [
                "claude",
                "-p",
                "Complete the repository task described in state/task.md. Follow AGENTS.md and docs/index.md.",
                "--dangerously-skip-permissions",
                "--model",
                "claude-sonnet-4-6",
            ],
            direct_workspace,
        ),
        (
            [
                "env",
                f"PYTHONPATH={ROOT}",
                sys.executable,
                "-m",
                "orchestrator",
                "run",
                "workflows/examples/generic_task_plan_execute_review_loop.yaml",
            ],
            workflow_workspace,
        ),
    ]

    direct_command_path = archive_dir / "direct-command.json"
    workflow_command_path = archive_dir / "workflow-command.json"
    trial_result_path = archive_dir / "trial-result.json"
    direct_metadata_path = archive_dir / "direct-run-metadata.json"
    workflow_metadata_path = archive_dir / "workflow-run-metadata.json"

    assert direct_command_path.is_file()
    assert workflow_command_path.is_file()
    assert direct_metadata_path.is_file()
    assert workflow_metadata_path.is_file()
    assert trial_result_path.is_file()

    assert json.loads(direct_command_path.read_text())["command"][:2] == ["claude", "-p"]
    assert json.loads(workflow_command_path.read_text())["command"][:5] == [
        "env",
        f"PYTHONPATH={ROOT}",
        sys.executable,
        "-m",
        "orchestrator",
    ]

    persisted_result = json.loads(trial_result_path.read_text())
    assert persisted_result == result
    assert result["direct"]["evaluation"]["verdict"] == "FAIL"
    assert result["workflow"]["evaluation"]["verdict"] == "PASS"
