"""Every refusal keeps its first line, names what changed and prints commands that recover."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import sys

import pytest

from orchestrator.cli.recovery import COMMAND_INDENT, REFUSAL_CODES, recovery_lines
from tests.test_cli_run_output import (
    IDENTITIES, RESULT_LINE, cli, effect_rows, failed_run, run_pipeline, shell, write_pipeline,
)


def commands(stderr: str) -> list[str]:
    """The recovery commands: lines indented by the command indent."""
    return [line.strip() for line in stderr.splitlines()
            if line.startswith(COMMAND_INDENT + shlex.quote(sys.executable) + " -m orchestrator ")]


def run_id_of(stderr: str) -> str:
    return stderr.splitlines()[0].split()[1]


def edit_script(root: Path) -> None:
    with (root / "step.py").open("a", encoding="utf-8") as stream:
        stream.write("# edited\n")


def refused(root: Path, run_id: str, code: str):
    result = cli(root, "resume", run_id)
    assert result.returncode == 2, result.stderr
    assert result.stderr.startswith(f"[{code}] "), result.stderr
    return result


def test_program_edit_refusal_names_the_changed_step_and_a_run_command_that_works(tmp_path: Path) -> None:
    run_id = run_id_of(failed_run(tmp_path).stderr)
    source = tmp_path / "main.orc"
    source.write_text(source.read_text(encoding="utf-8").replace('"three" b', '"three" b "extra"'), encoding="utf-8")
    (tmp_path / "step.py").write_text((tmp_path / "step.py").read_text(encoding="utf-8").replace(
        "int(sys.argv[2])", "int(sys.argv[2]) + len(sys.argv[3:])"), encoding="utf-8")
    (tmp_path / "fail-two").unlink()

    result = refused(tmp_path, run_id, "resume_program_changed")

    assert f"  changed {IDENTITIES[2]}" in result.stderr.splitlines()
    (accept, _resume, fresh_run) = commands(result.stderr)
    assert accept.split()[-1].startswith("--accept-changes=plan-")
    rerun = shell(tmp_path, fresh_run)
    assert rerun.returncode == 0, rerun.stderr
    assert rerun.stdout.splitlines()[-1] == '{"first":2,"total":5}'


def test_committed_script_edit_refusal_prints_invalidate_and_resume_that_recover(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    run_id = run_id_of(run_pipeline(tmp_path).stderr)
    edit_script(tmp_path)

    result = refused(tmp_path, run_id, "effect_input_diverged")

    assert f"step {IDENTITIES[0]} was committed with other inputs" in result.stderr
    assert "step.py" in result.stderr
    accept, invalidate, resume = commands(result.stderr)
    one_command = tmp_path.parent / f"{tmp_path.name}-accepted"
    shutil.copytree(tmp_path, one_command, symlinks=True)
    accepted = shell(one_command, accept)               # the token command does what the two commands below do
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout.splitlines()[-1] == RESULT_LINE
    assert shell(tmp_path, invalidate).returncode == 0
    resumed = shell(tmp_path, resume)
    assert resumed.returncode == 0, resumed.stderr
    assert ("commit", IDENTITIES[0]) in effect_rows(resumed.stderr)
    assert f"commit  {IDENTITIES[0]}  attempt 2" in resumed.stderr.splitlines()
    assert resumed.stdout.splitlines()[-1] == RESULT_LINE


def test_committed_script_edit_refusal_warns_once_before_its_commands(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    run_id = run_id_of(run_pipeline(tmp_path).stderr)
    edit_script(tmp_path)

    lines = refused(tmp_path, run_id, "effect_input_diverged").stderr.splitlines()

    warning = lines[next(index for index, line in enumerate(lines) if line.startswith(COMMAND_INDENT)
                         and " invalidate " in line) - 1]
    assert (warning.count("every later one"), warning.count("workspace files are not rolled back")) == (1, 1)


def test_failed_step_script_edit_resumes_with_the_edited_script(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    (tmp_path / "fail-one").write_text("", encoding="utf-8")
    failed = run_pipeline(tmp_path)
    assert failed.returncode == 1, failed.stderr
    edit_script(tmp_path)
    (tmp_path / "fail-one").unlink()

    resumed = cli(tmp_path, "resume", run_id_of(failed.stderr))

    assert resumed.returncode == 0, resumed.stderr
    assert resumed.stdout.splitlines()[-1] == RESULT_LINE
    assert f"start   {IDENTITIES[0]}  attempt 2" in resumed.stderr.splitlines()


def test_input_change_refusal_names_the_input(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    (tmp_path / "fail-two").write_text("", encoding="utf-8")
    inputs = tmp_path / "inputs.json"
    inputs.write_text('{"n": 1}', encoding="utf-8")
    failed = cli(tmp_path, "run", "main.orc", "--command-boundaries-file", "commands.json", "--input-file", "inputs.json")
    assert failed.returncode == 1, failed.stderr
    inputs.write_text('{"n": 2}', encoding="utf-8")

    result = refused(tmp_path, run_id_of(failed.stderr), "resume_inputs_changed")

    assert "inputs whose value differs from the recorded run: n" in result.stderr.splitlines()


def test_invalidate_of_an_unknown_identity_lists_the_committed_ones(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    run_id = run_id_of(run_pipeline(tmp_path).stderr)

    result = cli(tmp_path, "invalidate", run_id, "workflow:main::run / zzz")

    assert result.returncode == 2
    assert result.stderr.splitlines()[0] == "[invalidate_not_committed] workflow:main::run / zzz"
    listed = [command.split(run_id, 1)[1].strip() for command in commands(result.stderr)]
    assert listed == [f"'{identity}'" for identity in IDENTITIES]


HEADER = {
    "workflow_file": "main.orc", "result_root": "runs/r1", "run_ref_root": "/runs/ref",
    "resume_request": {
        "source_roots": [], "entry_workflow": None, "input_file": None, "input_overrides": {"n": "1"},
        "provider_externs_path": None, "prompt_externs_path": None,
        "imported_workflow_bundles_path": None, "command_boundaries_path": "commands.json",
    },
}


class _Refusal(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("detail")


@pytest.mark.parametrize("code", REFUSAL_CODES)
def test_every_refusal_code_has_recovery_lines(code: str) -> None:
    lines = recovery_lines(_Refusal(code), run_id="r1", launcher="orchestrator", state_dir=None, header=HEADER)

    assert lines and all(line.strip() for line in lines)


def test_a_shared_script_edit_after_invalidating_later_steps_offers_invalidate_that_recovers(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    run_id = run_id_of(run_pipeline(tmp_path).stderr)
    assert cli(tmp_path, "invalidate", run_id, IDENTITIES[1]).returncode == 0
    edit_script(tmp_path)

    result = refused(tmp_path, run_id, "effect_input_diverged")

    _accept, invalidate, resume = commands(result.stderr)
    assert shell(tmp_path, invalidate).returncode == 0
    resumed = shell(tmp_path, resume)
    assert resumed.returncode == 0, resumed.stderr
    assert resumed.stdout.splitlines()[-1] == RESULT_LINE


BRANCHED = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defworkflow run ((n Int)) -> Int
    (let* ((a (command-result step :argv ("python" "step.py" "one" n) :returns Int))
           (b (command-result other :argv ("python" "two.py" a) :returns Int)))
      b)))
'''


def test_a_failed_step_whose_closure_lost_a_file_is_not_called_committed(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    (tmp_path / "main.orc").write_text(BRANCHED, encoding="utf-8")
    (tmp_path / "two.py").write_text("import sys; sys.exit(4)\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("", encoding="utf-8")
    (tmp_path / "commands.json").write_text(json.dumps({
        "step": {"stable_command": ["python", "step.py"], "closure": ["step.py"]},
        "other": {"stable_command": ["python", "two.py"], "closure": ["two.py", "helper.py"]}}), encoding="utf-8")
    failed = run_pipeline(tmp_path)
    assert failed.returncode == 1, failed.stderr
    (tmp_path / "helper.py").unlink()

    result = refused(tmp_path, run_id_of(failed.stderr), "effect_input_diverged")

    assert "committed" not in result.stderr.split("\n", 1)[1]
    assert not any(" invalidate " in command for command in commands(result.stderr))
    assert any(command.endswith(" resume " + run_id_of(failed.stderr)) for command in commands(result.stderr))


def test_invalidate_of_a_failed_step_offers_resume_and_warns_before_listing(tmp_path: Path) -> None:
    run_id = run_id_of(failed_run(tmp_path).stderr)

    result = cli(tmp_path, "invalidate", run_id, IDENTITIES[1])

    assert result.returncode == 2
    lines = result.stderr.splitlines()
    assert f"step {IDENTITIES[1]} failed and has no commit to invalidate; resume runs it again:" in lines
    assert commands(result.stderr)[0].endswith(f" resume {run_id}")
    warning = next(index for index, line in enumerate(lines) if "workspace files are not rolled back" in line)
    first_listed = next(index for index, line in enumerate(lines)
                        if line.startswith(COMMAND_INDENT) and " invalidate " in line)
    assert warning < first_listed


def test_invalidate_of_an_invalidated_step_says_it_was_invalidated(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    run_id = run_id_of(run_pipeline(tmp_path).stderr)
    assert cli(tmp_path, "invalidate", run_id, IDENTITIES[1]).returncode == 0

    result = cli(tmp_path, "invalidate", run_id, IDENTITIES[2])

    assert result.returncode == 2
    assert f"step {IDENTITIES[2]} was invalidated and has no active commit; resume runs it again:" in result.stderr.splitlines()
    assert "failed" not in result.stderr


def test_a_refusal_without_an_identity_does_not_print_none() -> None:
    from orchestrator.workflow.evaluated.effect_inputs import _PreflightRefusal

    lines = recovery_lines(_PreflightRefusal("lexical_restore_pending_effect_unsafe", "detail"),
                           run_id="r1", launcher="orchestrator", state_dir=None, header=HEADER)

    assert not any("None" in line for line in lines)
