from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from orchestrator.cli.main import create_parser


def _cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", *arguments],
        cwd=root, env=env, capture_output=True, text=True, check=False,
    )


def _plain_workflow(root: Path) -> Path:
    source = root / "workflow.py"
    source.write_text(
        "from orchestrator.py import workflow\n"
        "@workflow\n"
        "def run(limit: int) -> int:\n"
        "    return limit\n",
        encoding="utf-8",
    )
    return source


def _command_workflow(root: Path) -> tuple[Path, Path]:
    source = root / "workflow.py"
    source.write_text(
        "from orchestrator.py import Command, cont, done, loop, record, when, workflow\n"
        "@record\nclass Counter:\n    count: int\n"
        "counted = Command('counted', returns=int)\n"
        "def ignore_result(state):\n"
        "    counted('python', 'count_tool.py', state.count)\n"
        "    return cont(Counter(count=state.count + 1))\n"
        "def reuse_result(state):\n"
        "    result = counted('python', 'count_tool.py', state.count)\n"
        "    return cont(Counter(count=result + (result - result)))\n"
        "def step(state):\n"
        "    return when(state.count == 2, then=lambda: done(state.count),\n"
        "        else_=lambda: when(state.count == 0,\n"
        "            then=lambda: ignore_result(state),\n"
        "            else_=lambda: reuse_result(state)))\n"
        "def hidden_branch():\n"
        "    counted('python', 'count_tool.py', 99)\n"
        "    return 99\n"
        "@workflow\n"
        "def run(limit: int, enabled: bool) -> int:\n"
        "    return when(enabled,\n"
        "        then=lambda: loop(state=Counter(count=0), max=limit, body=step,\n"
        "            on_exhausted=lambda state: state.count),\n"
        "        else_=lambda: hidden_branch())\n",
        encoding="utf-8",
    )
    tool = root / "count_tool.py"
    tool.write_text(
        "import json, os, sys\nfrom pathlib import Path\n"
        "value = int(sys.argv[1])\n"
        "with Path('calls.jsonl').open('a', encoding='utf-8') as log:\n"
        "    log.write(json.dumps(value) + '\\n')\n"
        "Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']).write_text(str(value + 1), encoding='utf-8')\n",
        encoding="utf-8",
    )
    boundaries = root / "commands.json"
    boundaries.write_text(json.dumps({
        "counted": {
            "stable_command": ["python", "count_tool.py"],
            "closure": ["count_tool.py"],
        }
    }), encoding="utf-8")
    return source, boundaries


def _warning_workflow(root: Path) -> tuple[Path, Path]:
    source = root / "warning_workflow.py"
    source.write_text(
        "from orchestrator.py import Prompt, Provider, variant, workflow\n"
        "@variant\nclass A: pass\n"
        "@variant\nclass B: pass\n"
        "Outcome = A | B\n"
        "agent = Provider('review')\n"
        "task = Prompt(text='Return one outcome', fills={}, returns=Outcome)\n"
        "@workflow\n"
        "def run() -> Outcome:\n"
        "    return agent(task())\n",
        encoding="utf-8",
    )
    providers = root / "providers.json"
    providers.write_text('{"providers.review":"codex"}', encoding="utf-8")
    return source, providers


def _env(root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def test_python_run_parser_reuses_ordinary_run_defaults() -> None:
    parser = create_parser()
    ordinary = parser.parse_args(["run", "workflow.orc"])
    python = parser.parse_args([
        "py", "run", "workflow.py", "--entry-workflow", "run",
    ])

    for name in (
        "context", "context_file", "input", "input_file", "debug",
        "stream_output", "dry_run", "backup_state", "state_dir",
        "run_ref_root", "on_error", "max_retries", "retry_delay", "quiet",
        "verbose", "log_level", "step_summaries", "summary_mode",
        "summary_provider", "summary_timeout_sec", "summary_max_input_chars",
        "summary_profile", "live_agent_notes", "live_agent_note_provider",
        "live_agent_note_interval_sec", "live_agent_note_timeout_sec",
        "live_agent_note_max_tail_chars",
    ):
        assert getattr(python, name) == getattr(ordinary, name), name
    assert python.workflow == "workflow.py"
    assert python.entry_workflow == "run"
    assert python.frozen is False


def test_public_python_build_and_check_keep_the_closed_artifact_contract(tmp_path: Path) -> None:
    source = _plain_workflow(tmp_path)
    args = (str(source), "--entry-workflow", "run")

    checked = _cli(tmp_path, "py", "check", *args)
    assert checked.returncode == 0, checked.stderr
    check_document = json.loads(checked.stdout)
    assert check_document["entry_workflow"].endswith("::run")
    assert check_document["program_digest"].startswith("sha256:")
    assert Path(check_document["artifact_paths"]["closed_program"]).is_file()
    assert not list((tmp_path / ".orchestrate/python").glob("pin-*.json"))

    built = _cli(tmp_path, "py", "build", *args)
    assert built.returncode == 0, built.stderr
    build_document = json.loads(built.stdout)
    assert build_document["build_key"]
    pin_paths = list((tmp_path / ".orchestrate/python").glob("pin-*.json"))
    assert len(pin_paths) == 1
    pin_before = pin_paths[0].read_bytes()

    checked_again = _cli(tmp_path, "py", "check", *args)
    assert checked_again.returncode == 0, checked_again.stderr
    assert pin_paths[0].read_bytes() == pin_before


def test_public_python_frozen_build_refuses_missing_and_changed_pin(tmp_path: Path) -> None:
    source = _plain_workflow(tmp_path)
    args = (str(source), "--entry-workflow", "run")

    missing = _cli(tmp_path, "py", "build", *args, "--frozen")
    assert missing.returncode == 2
    assert "python_frozen_pin_missing" in missing.stderr

    built = _cli(tmp_path, "py", "build", *args)
    assert built.returncode == 0, built.stderr
    pin_paths = list((tmp_path / ".orchestrate/python").glob("pin-*.json"))
    assert len(pin_paths) == 1
    pin_before = pin_paths[0].read_bytes()
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    changed = _cli(tmp_path, "py", "check", *args, "--frozen")
    assert changed.returncode == 2
    assert "python_frozen_changed" in changed.stderr
    assert pin_paths[0].read_bytes() == pin_before


def test_public_python_cli_renders_compiler_warnings_at_python_locations(tmp_path: Path) -> None:
    source, providers = _warning_workflow(tmp_path)

    checked = _cli(
        tmp_path, "py", "check", str(source), "--entry-workflow", "run",
        "--provider-externs-file", str(providers),
    )

    assert checked.returncode == 0, checked.stderr
    assert "variant_output_without_variant_specific_fields" in checked.stderr
    assert str(source) in checked.stderr


@pytest.mark.parametrize("flags", [("--quiet",), ("--log-level", "error")])
def test_python_run_compile_warnings_follow_runtime_log_visibility(
    tmp_path: Path, flags: tuple[str, ...],
) -> None:
    source, providers = _warning_workflow(tmp_path)

    result = _cli(
        tmp_path, "py", "run", str(source), "--entry-workflow", "run",
        "--provider-externs-file", str(providers), "--dry-run", *flags,
    )

    assert result.returncode == 0, result.stderr
    assert "variant_output_without_variant_specific_fields" not in result.stderr


def test_public_python_run_quiet_hides_compile_warnings(
    tmp_path: Path, monkeypatch, caplog,
) -> None:
    import logging

    from orchestrator.py import run

    source, providers = _warning_workflow(tmp_path)
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING):
        result = run(
            source,
            entry_workflow="run",
            provider_externs_file=providers,
            quiet=True,
            dry_run=True,
        )

    assert result.exit_code == 0
    assert not any(
        "variant_output_without_variant_specific_fields" in record.message
        for record in caplog.records
    )


def test_python_run_debug_shows_captured_author_traceback(tmp_path: Path) -> None:
    source = tmp_path / "workflow.py"
    source.write_text(
        "raise RuntimeError('traceback marker')\n"
        "from orchestrator.py import workflow\n"
        "@workflow\n"
        "def run() -> int:\n"
        "    return 0\n",
        encoding="utf-8",
    )

    failed = _cli(
        tmp_path, "py", "run", str(source), "--entry-workflow", "run", "--debug",
    )

    assert failed.returncode == 2
    assert "python_import_or_trace_error" in failed.stderr
    assert "RuntimeError: traceback marker" in failed.stderr


def test_python_run_executes_branch_loop_commands_in_order_with_typed_result(tmp_path: Path) -> None:
    source, boundaries = _command_workflow(tmp_path)

    checked = _cli(
        tmp_path, "py", "check", str(source), "--entry-workflow", "run",
        "--command-boundaries-file", str(boundaries),
    )

    assert checked.returncode == 0, checked.stderr
    assert not (tmp_path / "calls.jsonl").exists()
    assert not (tmp_path / ".orchestrate" / "runs").exists()

    result = _cli(
        tmp_path, "py", "run", str(source), "--entry-workflow", "run",
        "--command-boundaries-file", str(boundaries), "--input", "limit=3",
        "--input", "enabled=true", "--stream-output",
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines() == ["0", "1"]
    from tests.test_workflow_evaluated_resume_kills import _run_root, _snapshot, _rows
    snapshot = _snapshot(_run_root(tmp_path))
    assert [row["value"] for row in _rows(snapshot, "committed")] == [1, 2]
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["value"] == 2


def test_python_run_zero_loop_budget_has_no_command_attempts(tmp_path: Path) -> None:
    source, boundaries = _command_workflow(tmp_path)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"limit": 0, "enabled": True}), encoding="utf-8")

    result = _cli(
        tmp_path, "py", "run", str(source), "--entry-workflow", "run",
        "--command-boundaries-file", str(boundaries), "--input-file", str(inputs),
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "calls.jsonl").exists()
    from tests.test_workflow_evaluated_resume_kills import _run_root, _snapshot, _rows
    snapshot = _snapshot(_run_root(tmp_path))
    assert _rows(snapshot, "started") == []
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["value"] == 0


def test_python_run_resume_uses_retained_snapshot_after_source_removal(tmp_path: Path) -> None:
    source, boundaries = _command_workflow(tmp_path)
    arguments = [
        "py", "run", str(source), "--entry-workflow", "run",
        "--command-boundaries-file", str(boundaries), "--input", "limit=3",
        "--input", "enabled=true",
    ]
    from tests.test_workflow_evaluated_resume_kills import (
        _kill_after_first_commit, _rows, _run_root, _snapshot,
    )
    identity = _kill_after_first_commit(tmp_path, arguments, _env(tmp_path))
    run_root = _run_root(tmp_path)
    before = _snapshot(run_root)
    (first_commit,) = _rows(before, "committed")
    assert first_commit["identity"] == identity
    assert before.terminal is None
    assert (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines() == ["0"]

    source.unlink()
    resumed = _cli(tmp_path, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    after = _snapshot(run_root)
    assert len(_rows(after, "committed")) == 2
    assert _rows(after, "committed")[0] == first_commit
    assert after.terminal is not None
    assert after.terminal.data["value"] == 2
    assert (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines() == ["0", "1"]

    from orchestrator.workflow.evaluated.authority import load_run_authority
    authority = load_run_authority(run_root)
    memo_before = authority.memo_path.read_bytes()
    attempts_before = {
        path.relative_to(run_root).as_posix(): path.read_bytes()
        for path in (run_root / "effects").rglob("*") if path.is_file()
    }
    completed_resume = _cli(tmp_path, "resume", run_root.name)
    assert completed_resume.returncode == 0, completed_resume.stderr
    assert authority.memo_path.read_bytes() == memo_before
    assert {
        path.relative_to(run_root).as_posix(): path.read_bytes()
        for path in (run_root / "effects").rglob("*") if path.is_file()
    } == attempts_before


def test_maintained_python_command_loop_example_runs_two_commands_and_zero(tmp_path: Path) -> None:
    examples = Path(__file__).parents[1] / "workflows/examples"

    def copy_example(root: Path) -> None:
        target = root / "workflows/examples"
        target.mkdir(parents=True)
        for name in (
            "python_command_loop.py",
            "python_command_loop.commands.json",
            "python_command_loop_tool.py",
        ):
            shutil.copyfile(examples / name, target / name)

    run_root = tmp_path / "three"
    copy_example(run_root)
    run = _cli(
        run_root, "py", "run", "workflows/examples/python_command_loop.py",
        "--entry-workflow", "run", "--command-boundaries-file",
        "workflows/examples/python_command_loop.commands.json", "--input", "limit=3",
    )
    assert run.returncode == 0, run.stderr
    from tests.test_workflow_evaluated_resume_kills import _run_root, _rows, _snapshot
    completed_root = _run_root(run_root)
    completed = _snapshot(completed_root)
    commits = _rows(completed, "committed")
    assert len(commits) == 2
    assert [
        (completed_root / Path(commit["result_path"]).parent / "stdout.txt").read_text(encoding="utf-8").strip()
        for commit in commits
    ] == ["work item 0", "work item 1"]
    assert completed.terminal is not None
    assert completed.terminal.data["value"] == 2

    zero_root = tmp_path / "zero"
    copy_example(zero_root)
    zero = _cli(
        zero_root, "py", "run", "workflows/examples/python_command_loop.py",
        "--entry-workflow", "run", "--command-boundaries-file",
        "workflows/examples/python_command_loop.commands.json", "--input", "limit=0",
    )
    assert zero.returncode == 0, zero.stderr
    assert zero.stdout == ""
    exhausted = _snapshot(_run_root(zero_root))
    assert _rows(exhausted, "started") == []
    assert exhausted.terminal is not None
    assert exhausted.terminal.data["value"] == 0


def test_public_python_run_preserves_typed_inputs_and_returns_runtime_result(
    tmp_path: Path, monkeypatch,
) -> None:
    from orchestrator.cli.commands.run import RunWorkflowResult
    from orchestrator.py import run

    source = tmp_path / "typed_workflow.py"
    source.write_text(
        "from orchestrator.py import record, workflow\n"
        "@record\n"
        "class Echo:\n"
        "    enabled: bool\n"
        "    label: str\n"
        "    values: list[int]\n"
        "    note: str\n"
        "@workflow\n"
        "def run(enabled: bool, label: str, values: list[int], note: str) -> Echo:\n"
        "    return Echo(enabled=enabled, label=label, values=values, note=note)\n",
        encoding="utf-8",
    )
    input_file = tmp_path / "inputs.json"
    input_file.write_text(
        json.dumps({"enabled": False, "label": "from file", "values": [1], "note": "from file"}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = run(
        source,
        entry_workflow="run",
        inputs={"enabled": True, "label": "true", "values": [2, 5, 8]},
        input_file=input_file,
    )

    assert isinstance(result, RunWorkflowResult)
    assert result.exit_code == 0
    assert dict(result.workflow_outputs) == {
        "enabled": True,
        "label": "true",
        "values": (2, 5, 8),
        "note": "from file",
    }


def test_public_python_run_rejects_workspace_override_before_build_effects(
    tmp_path: Path, monkeypatch,
) -> None:
    import pytest

    from orchestrator.py import run

    source = _plain_workflow(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(TypeError, match="workspace_root"):
        run(source, entry_workflow="run", workspace_root=tmp_path / "elsewhere")

    assert not (tmp_path / ".orchestrate").exists()
