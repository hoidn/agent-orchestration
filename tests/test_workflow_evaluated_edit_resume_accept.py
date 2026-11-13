"""Phase 3b T7: `resume RUN_ID --accept-changes=TOKEN` accepts the plan the token names, and nothing else.

The token is compared with the plan recomputed now, at one place, before any write (Edit And Continue §6). An
accepted plan stores the edited program, appends one `rebased` record (or, under the run's own program, the
`invalidated` range `invalidate` writes) and continues as a fresh `resume` would under the program in force. Every
refusal leaves the run tree byte for byte as it was. Commands are local Python stand-ins; no model is called.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from tests import rebased_fixture as fx
from tests.test_workflow_evaluated_edit_resume_plan import (
    COMMANDS, NEW, P, REFUSALS, SERIAL, STEP, S, _copy, assert_unchanged, body, cmd, completed, edit, host_base,  # noqa: F401
    own_tools, printed_plan, refused, run, serial, short, tree, workspace)
from tests.workflow_inprocess_cli_helpers import cli_inprocess

TOKEN = "plan-00000000-00000000-00000000-00000000"


def accept_command(stderr: str) -> list[str]:
    """The printed command that accepts the plan: `resume RUN_ID --accept-changes=plan-…`, as CLI arguments."""
    (line,) = [line.strip() for line in stderr.splitlines()
               if line.startswith("    ") and " --accept-changes=plan-" in line]
    words = shlex.split(line)
    return words[words.index("resume"):]


def token_in(stderr: str) -> str:
    return accept_command(stderr)[-1].removeprefix("--accept-changes=")


def log(root: Path) -> list[str]:
    path = root / "log.txt"
    return path.read_text().split() if path.exists() else []


def records(run_root: Path, kind: str) -> list[dict]:
    return [row for row in fx.rows(run_root) if row["record"] == kind]


def artifacts(run_root: Path) -> list[str]:
    return sorted(path.name for path in run_root.glob("closed_program.*.json"))


def accepted(root: Path, words: list[str]):
    done = cli_inprocess(root, *words)
    assert done.returncode == 0, done.stderr
    return done


def refused_with(root: Path, run_root: Path, code: str, token: str):
    """`resume RUN_ID --accept-changes=TOKEN` exits 2 with `code` first and changes no byte."""
    return refused(root, run_root, code, f"--accept-changes={token}")


# ---- the one door ---------------------------------------------------------------------------------------------------

def test_printed_command_accepts_and_a_second_resume_writes_nothing(completed, tmp_path):
    root, run_root = _copy(completed(serial), tmp_path)
    edit(root, "           (s2 ", f"           (x {NEW})\n           (s2 ")
    printed = refused(root, run_root).stderr
    (root / "log.txt").write_text("")

    done = accepted(root, accept_command(printed))

    assert log(root) == ["x", "s2", "s3", "s4"]
    assert [short(row["identity"]) for row in records(run_root, "started")[-4:]] == ["x", "s2", "s3", "s4"]
    assert [row["attempt"] for row in records(run_root, "started")[-3:]] == [2, 2, 2]
    assert len(records(run_root, "rebased")) == 1 and len(artifacts(run_root)) == 1
    assert done.stdout.splitlines()[-1] == "4"
    before = tree(root)
    again = cli_inprocess(root, "resume", run_root.name)
    assert again.returncode == 0, again.stderr
    assert_unchanged(root, before)
    refused_with(root, run_root, "resume_preflight_failed", token_in(printed))


STALE = ["journal", "program", "cut", "sets"]


@pytest.mark.parametrize("field", STALE)
def test_stale_token_is_refused_and_names_what_changed(tmp_path, field):
    root = own_tools(tmp_path / "ws")
    (root / "fail-s4").write_text("")
    (root / "dirty-s4").write_text("")                         # s4 fails after changing its own script: unproven
    run_root = run(root, code=1)
    (root / "fail-s4").unlink()
    (root / "dirty-s4").unlink()
    edit(root, cmd("s3", "s2").replace("step", "t3").replace('"t.py"', '"t3.py"'),
         cmd("s3", "(+ s2 0)").replace("step", "t3").replace('"t.py"', '"t3.py"'))
    old = token_in(refused(root, run_root).stderr)            # every commit kept; s4 retried, reached now
    if field == "journal":
        assert cli_inprocess(root, "invalidate", run_root.name, P + "s2").returncode == 0
    elif field == "program":
        edit(root, "(+ s2 0)", "(+ s2 1)")
    elif field == "cut":
        (root / "t2.py").write_text(STEP + "# declared script of a kept commit\n")
    else:
        (root / "t4.py").write_text(STEP + "# fixed again\n")

    stale = refused_with(root, run_root, "resume_program_changed", old).stderr

    assert stale.splitlines()[0].startswith("[resume_program_changed] the plan token names another plan: ")
    assert {"journal": "the journal has new records", "program": "the program changed again", "cut": "the cut moved",
            "sets": "the unfinished steps"}[field] in stale.splitlines()[0]
    assert token_in(stale) not in {old, TOKEN} and printed_plan(stale)["kept"] is not None


def test_bare_flag_and_a_token_for_another_run_accept_nothing(completed, tmp_path):
    root, run_root = _copy(completed(serial), tmp_path)
    other_root = serial(tmp_path / "other")
    other_run = run(other_root)                                   # its own run id: the same plan of another run
    for workspace_root in (root, other_root):
        edit(workspace_root, "           (s2 ", f"           (x {NEW})\n           (s2 ")
    other = token_in(refused(other_root, other_run).stderr)
    own = token_in(refused(root, run_root).stderr)

    refused(root, run_root, "resume_program_changed", "--accept-changes")
    stale = refused_with(root, run_root, "resume_program_changed", other).stderr

    assert other != own and token_in(stale) == own
    assert records(run_root, "rebased") == [] and artifacts(run_root) == []


def test_flag_before_the_run_id_is_a_usage_error_that_names_the_fix(completed, tmp_path):
    root, run_root = _copy(completed(serial), tmp_path)
    before = tree(root)

    done = fx.cli(root, "resume", "--accept-changes", run_root.name)

    assert done.returncode == 2, done.stderr
    assert "write the run id before --accept-changes" in done.stderr
    assert_unchanged(root, before)


def test_token_with_nothing_to_accept_is_refused(completed, tmp_path):
    root, run_root = _copy(completed(serial), tmp_path)

    refused_with(root, run_root, "resume_preflight_failed", TOKEN)


TOKEN_REFUSALS = {**{case: (code, edits) for case, (code, edits) in REFUSALS.items()}}


@pytest.mark.parametrize("case", TOKEN_REFUSALS)
def test_each_refusal_of_section_5_with_a_token(completed, tmp_path, case):
    """Decided before the gate: the code of the condition itself, never a plan accepted, no byte changed."""
    code, edits = TOKEN_REFUSALS[case]
    root, run_root = _copy(completed(serial), tmp_path)
    for name, old, new in edits:
        edit(root, old, new, name)

    refused_with(root, run_root, code, TOKEN)
