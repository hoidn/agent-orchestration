"""Manifests beside the source are used without flags; help lists only the public commands."""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from orchestrator.cli.main import create_parser
from tests.test_cli_run_output import RESULT_LINE, cli, printed, shell, write_pipeline

REPO = Path(__file__).parents[1]
PUBLIC = {"run", "py", "compile", "repl", "resume", "invalidate", "input", "report", "dashboard", "monitor"}
HIDDEN = {"prompt", "trial", "explain", "workflow-lisp-route-readiness", "provider-materialization-submit",
          "provider-isolation-environment-manifest"}


def test_manifests_beside_the_source_are_used_when_flags_are_absent(tmp_path: Path) -> None:
    write_pipeline(tmp_path)

    result = cli(tmp_path, "run", "main.orc", "--input", "n=1")

    assert result.returncode == 0, result.stderr
    assert "using commands.json beside main.orc" in result.stderr.splitlines()
    assert result.stdout.splitlines()[-1] == RESULT_LINE


def test_an_explicit_flag_wins_over_the_sibling_file(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    shutil.move(tmp_path / "commands.json", tmp_path / "chosen.json")
    (tmp_path / "commands.json").write_text("{}", encoding="utf-8")

    result = cli(tmp_path, "run", "main.orc", "--command-boundaries-file", "chosen.json", "--input", "n=1")

    assert result.returncode == 0, result.stderr
    assert printed(result.stderr, "using") == []


def test_resume_uses_the_manifest_recorded_by_run(tmp_path: Path) -> None:
    (tmp_path / "fail-two").write_text("", encoding="utf-8")
    write_pipeline(tmp_path)
    failed = cli(tmp_path, "run", "main.orc", "--input", "n=1")
    assert failed.returncode == 1, failed.stderr
    (tmp_path / "fail-two").unlink()
    (resume,) = printed(failed.stderr, "resume")

    resumed = shell(tmp_path, resume)

    assert resumed.returncode == 0, resumed.stderr
    assert printed(resumed.stderr, "using") == []
    assert resumed.stdout.splitlines()[-1] == RESULT_LINE


def test_py_build_uses_sibling_manifests(tmp_path: Path) -> None:
    examples = tmp_path / "workflows" / "examples"
    examples.mkdir(parents=True)
    for name in ("python_command_loop.py", "python_command_loop_tool.py"):
        shutil.copyfile(REPO / "workflows" / "examples" / name, examples / name)
    shutil.copyfile(REPO / "workflows" / "examples" / "python_command_loop.commands.json", examples / "commands.json")

    result = cli(tmp_path, "py", "build", "workflows/examples/python_command_loop.py", "--entry-workflow", "run")

    assert result.returncode == 0, result.stderr
    assert "using workflows/examples/commands.json beside workflows/examples/python_command_loop.py" in result.stderr


def test_missing_command_boundary_message_names_the_file_and_the_flag(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    (tmp_path / "commands.json").unlink()

    result = cli(tmp_path, "compile", "main.orc")

    assert result.returncode == 2
    (first,) = [line for line in result.stderr.splitlines() if "[command_adapter_missing_contract]" in line]
    assert "commands.json" in first and "--command-boundaries-file" in first


def test_top_level_help_lists_only_public_commands(tmp_path: Path) -> None:
    result = cli(tmp_path, "--help")

    listed = {line.split()[0] for line in result.stdout.splitlines() if line[:4] == "    " and line[4:5].strip()}
    assert result.returncode == 0
    assert listed == PUBLIC
    assert result.stdout.startswith("usage: orchestrator ")


@pytest.mark.parametrize("argv", [
    ["prompt", "resume", "S1"], ["trial", "w.orc", "--entry-workflow", "e"], ["explain", "w.orc"],
    ["workflow-lisp-route-readiness"], ["provider-materialization-submit"],
    ["provider-isolation-environment-manifest", "--root", "/r", "--provider-prefix", "/p", "--output", "/o"],
    ["run", "w.orc", "--context", "k=v", "--clean-processed", "--on-error", "continue", "--max-retries", "2",
     "--step-summaries", "--summary-mode", "sync", "--live-agent-notes", "--backup-state", "--stream-output"],
    ["resume", "r1", "--repair", "--force-restart", "--max-retries", "2", "--summary-mode", "sync",
     "--live-agent-notes", "--backup-state", "--stream-output"],
    ["compile", "w.orc", "--emit-debug-yaml", "--emit-semantic-ir", "out.json"],
])
def test_hidden_commands_and_flags_still_parse(argv: list[str]) -> None:
    assert create_parser().parse_args(argv).command == argv[0]


@pytest.mark.parametrize("command", ["run", "resume", "compile"])
def test_hidden_flags_are_absent_from_command_help(tmp_path: Path, command: str) -> None:
    result = cli(tmp_path, command, "--help")

    assert result.returncode == 0
    for flag in ("--context", "--on-error", "--summary-mode", "--live-agent-notes", "--repair", "--emit-debug-yaml"):
        assert flag not in result.stdout
