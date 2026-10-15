"""Public resume preserves the final committed generic-record loop update."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.workflow.executor import WorkflowExecutor
from tests.test_workflow_lisp_generic_state_exhaustion import PROBE, SOURCE


class _PostCommitInterruption(BaseException):
    pass


def _fixture(workspace: Path) -> list[str]:
    probe = workspace / "probe_review.py"
    probe.write_text(
        PROBE + '\nwith Path("calls.txt").open("a") as calls:\n'
        '    calls.write(sys.argv[1] + "\\n")\n',
        encoding="utf-8",
    )
    source = workspace / "generic_exhaustion.orc"
    source.write_text(
        SOURCE.replace(
            '(:target-dsl "2.32")',
            '(:target-dsl "2.32")\n  (defmodule generic_exhaustion)\n'
            '  (export improve-status)',
        ).replace("PROBE_PATH", probe.as_posix()).replace("MAX_ITERATIONS", "3"),
        encoding="utf-8",
    )
    commands = workspace / "commands.json"
    commands.write_text(json.dumps({
        "probe_review": {
            "kind": "external_tool",
            "stable_command": ["python", probe.as_posix()],
        },
    }), encoding="utf-8")
    return [
        "run", str(source), "--source-root", str(workspace),
        "--entry-workflow", "improve-status",
        "--command-boundaries-file", str(commands), "--quiet",
    ]


def test_public_resume_preserves_final_generic_continue_without_replaying_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv = _fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["orchestrator", *argv])
    original = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_repeat_until_commit

    def interrupt_after_final_commit(self, step, progress):
        original(self, step, progress)
        if (progress.get("current_iteration") == 2
                and progress.get("condition_evaluated_for_iteration") == 2
                and progress.get("last_condition_result") is False):
            raise _PostCommitInterruption

    with monkeypatch.context() as interrupted:
        interrupted.setattr(
            WorkflowExecutor,
            "_emit_lexical_checkpoint_shadow_after_repeat_until_commit",
            interrupt_after_final_commit,
        )
        with pytest.raises(_PostCommitInterruption):
            run_workflow(create_parser().parse_args(argv))

    expected_calls = ["seed", "revised-seed", "revised-revised-seed"]
    calls = tmp_path / "calls.txt"
    assert calls.read_text().splitlines() == expected_calls
    run_root, = (tmp_path / ".orchestrate" / "runs").iterdir()
    checkpoint = json.loads((run_root / "state.json").read_text())
    assert not checkpoint.get("workflow_outputs")
    assert resume_workflow(run_id=run_root.name, retry_delay_ms=0) == 0
    assert calls.read_text().splitlines() == expected_calls
    resumed = json.loads((run_root / "state.json").read_text())
    expected = {"return__title": "revised-revised-revised-seed", "return__score": 3}
    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == expected

    clean_workspace = tmp_path / "clean"
    clean_workspace.mkdir()
    clean_argv = _fixture(clean_workspace)
    monkeypatch.chdir(clean_workspace)
    monkeypatch.setattr(sys, "argv", ["orchestrator", *clean_argv])
    clean = run_workflow(create_parser().parse_args(clean_argv))
    assert clean.exit_code == 0
    assert dict(clean.workflow_outputs) == expected
    assert (clean_workspace / "calls.txt").read_text().splitlines() == expected_calls
