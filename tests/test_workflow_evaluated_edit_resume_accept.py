"""Phase 3b T7: `resume RUN_ID --accept-changes=TOKEN` accepts the plan the token names, and nothing else.

The token is compared with the plan recomputed now, at one place, before any write (Edit And Continue §6). An
accepted plan stores the edited program, appends one `rebased` record (or, under the run's own program, the
`invalidated` range `invalidate` writes) and continues as a fresh `resume` would under the program in force. Every
refusal leaves the run tree byte for byte as it was. Commands are local Python stand-ins; no model is called.
"""
from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path

import pytest

from tests import rebased_fixture as fx
from tests.test_workflow_evaluated_edit_resume_plan import (
    COMMANDS, EDITS, NEW, P, REFUSALS, RUN_ARGS, SERIAL, STEP, S, _copy, class_change, assert_unchanged, body, cmd, completed, edit, host_base,  # noqa: F401
    manifest, own_tools, printed_plan, refused, repeat_workspace, run, serial, short, tree, workspace)
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


# ---- after acceptance the run continues as a fresh resume would ---------------------------------------------------

def test_must_not_repeat_refuses_until_invalidated_then_runs_once(tmp_path, declared_by):
    root, run_root = repeat_workspace(tmp_path / "ws", declared=declared_by == "the run's program")
    if declared_by == "the edit":
        manifest(root, True)
    edit(root, cmd("s2", "s1"), cmd("s2", "(+ s1 1)"))
    refused_with(root, run_root, "lexical_restore_pending_effect_unsafe", TOKEN)
    printed = refused(root, run_root).stderr
    (invalidate,) = [line.strip() for line in printed.splitlines() if line.startswith("    ") and " invalidate " in line]
    words = shlex.split(invalidate)
    assert cli_inprocess(root, *words[words.index("invalidate"):]).returncode == 0
    (root / "log.txt").write_text("")

    accepted(root, accept_command(refused(root, run_root).stderr))

    assert log(root) == ["s2", "s3", "s4"]
    assert cli_inprocess(root, "resume", run_root.name).returncode == 0 and log(root) == ["s2", "s3", "s4"]


@pytest.fixture(params=["the run's program", "the edit"])
def declared_by(request):
    return request.param


def provider_workspace(tmp_path: Path) -> Path:
    from tests.test_workflow_evaluated_spend_cap import TWO_CALLS, _capped, _run
    root = _capped(tmp_path, source=TWO_CALLS.replace('(:target-dsl "2.35")', '(:target-dsl "2.40")'))
    assert _run(root).returncode == 0
    return root


def provider_cli(root: Path, *argv: str):
    from tests.test_workflow_evaluated_provider_usage import _orchestrator
    return _orchestrator(root, *argv)


def provider_refused(root: Path, code: str):
    from tests.test_workflow_evaluated_spend_cap import _run_id
    before = tree(root)
    done = provider_cli(root, "resume", _run_id(root))
    assert done.returncode == 2 and done.stderr.startswith(f"[{code}] "), done.stderr
    assert_unchanged(root, before)
    return done


def test_comment_line_above_a_committed_provider_dispatches_nothing(tmp_path):
    from tests.test_workflow_evaluated_spend_cap import _calls
    root = provider_workspace(tmp_path)
    edit(root, "    (let* ((first", "    ;; a comment line moves every position below it\n    (let* ((first", "main.orc")
    edit(root, "      second)))", '      (let* ((after (command-result build :argv ("python" "command.py" "after") '
                                  ':returns String))) second))))', "main.orc")
    commands = (root / "commands.jsonl").read_text()

    done = provider_cli(root, *accept_command(provider_refused(root, "resume_program_changed").stderr))

    assert done.returncode == 0, done.stderr
    assert _calls(root) == 2 and (root / "commands.jsonl").read_text() == commands + "{}\n"


def journal_shape(root: Path) -> list[tuple]:
    from tests.test_workflow_evaluated_provider_usage import _memo
    return [(row["record"], row.get("identity"), row.get("attempt"), row.get("from_commit"), row.get("outcome"))
            for row in _memo(root)]


def test_committed_prompt_file_change_writes_the_journal_invalidate_would(tmp_path):
    from tests.test_workflow_evaluated_spend_cap import _calls, _run_id
    root = provider_workspace(tmp_path / "token")
    (root / "prompt.md").write_text("Answer again.\n")
    printed = provider_refused(root, "effect_input_diverged").stderr
    other = tmp_path / "two-commands"
    import shutil
    shutil.copytree(root, other, symlinks=True)
    (invalidate,) = [line.strip() for line in printed.splitlines() if line.startswith("    ") and " invalidate " in line]

    done = provider_cli(root, *accept_command(printed))
    words = shlex.split(invalidate)
    assert provider_cli(other, *words[words.index("invalidate"):]).returncode == 0
    assert provider_cli(other, "resume", _run_id(other)).returncode == 0

    assert done.returncode == 0, done.stderr
    assert journal_shape(root) == journal_shape(other) and _calls(root) == _calls(other) == 4


def test_edit_and_a_failed_steps_fixed_script_take_one_resume(tmp_path):
    root = own_tools(tmp_path / "ws")
    (root / "fail-s4").write_text("")
    run_root = run(root, code=1)
    (root / "fail-s4").unlink()
    (root / "t4.py").write_text(STEP + "# fixed\n")
    edit(root, "      s4))", "      " + cmd("x", "s4").replace("step", "t1").replace('"t.py"', '"t1.py"') + "))")
    (root / "log.txt").write_text("")

    done = accepted(root, accept_command(refused(root, run_root).stderr))

    assert log(root) == ["s4", "x"] and done.stdout.splitlines()[-1] == "5"
    assert [row["outcome"] for row in records(run_root, "terminal")] == ["failed", "completed"]


def test_asked_again_request_gets_a_new_id_and_the_old_one_is_stale(host_base, tmp_path):
    root, run_root = _copy(host_base, tmp_path)
    (old,) = {row["host_request"]["request_id"] for row in fx.rows(run_root) if "host_request" in row}
    edit(root, cmd("s1", "n"), cmd("s1", "(+ n 1)"))

    accepted(root, accept_command(refused(root, run_root).stderr))
    new = json.loads(cli_inprocess(root, "input", "get", run_root.name).stdout)["request_id"]
    stale = cli_inprocess(root, "input", "answer", run_root.name, old, "--value", '"APPROVED"', "--by", "t")

    assert new != old
    assert stale.returncode == 2 and "host_input_stale" in stale.stderr, stale.stderr
    answered = cli_inprocess(root, "input", "answer", run_root.name, new, "--value", '"APPROVED"', "--by", "t")
    assert answered.returncode == 0, answered.stderr


def test_coordinators_before_the_cut_are_kept_and_after_it_refuse(tmp_path):
    from tests.test_workflow_evaluated_edit_resume_plan import cli, refused_process, run_ref_run
    parent, run_root, refs = run_ref_run(tmp_path / "r")
    children = sorted(path for path in refs.rglob("memo.jsonl"))
    child_bytes = {path: path.read_bytes() for path in children}
    source = (parent / "controller.orc").read_text()
    edit(parent, cmd("b", "a"), cmd("b", "(+ a 1)"), "controller.orc")

    done = cli(parent, *accept_command(refused_process(parent, run_root).stderr))

    assert done.returncode == 0, done.stderr
    assert {path: path.read_bytes() for path in refs.rglob("memo.jsonl")} == child_bytes   # no child run, no record
    (parent / "controller.orc").write_text(source.replace(cmd("a", "0"), cmd("a", "1")))
    before = tree(parent)
    refused_by_coordinator = cli(parent, "resume", run_root.name, f"--accept-changes={TOKEN}")
    assert refused_by_coordinator.returncode == 2, refused_by_coordinator.stderr
    assert refused_by_coordinator.stderr.startswith("[invalidate_coordinator_committed] ")
    assert_unchanged(parent, before)


COMMAND_ONLY = [kind for kind in EDITS if EDITS[kind][0] is not class_change]     # a host request would wait


@pytest.mark.parametrize("kind", COMMAND_ONLY)
def test_each_edit_kind_accepted_ends_at_the_value_of_a_fresh_run(completed, tmp_path, kind):
    """Design §9, "Each edit kind": the accepted run's value equals a fresh run of the edited program in a clean
    clone, and only the cancelled steps and new steps were dispatched again."""
    fixture, edits, kept, cancelled = EDITS[kind]
    root, run_root = _copy(completed(fixture), tmp_path)
    for name, old, new in edits:
        edit(root, old, new, name)
    clean = tmp_path / "clean"
    shutil.copytree(root, clean, ignore=shutil.ignore_patterns(".orchestrate", "log.txt"))
    fresh = cli_inprocess(clean, "run", *RUN_ARGS)
    assert fresh.returncode == 0, fresh.stderr
    (root / "log.txt").write_text("")

    done = accepted(root, accept_command(refused(root, run_root).stderr))

    assert done.stdout.splitlines()[-1] == fresh.stdout.splitlines()[-1]
    tag = lambda name: name.split("#")[0].split("/")[-1]  # noqa: E731 - the step's logged tag
    only_kept = {tag(name) for name in kept} - {tag(name) for name in cancelled}
    assert not only_kept & set(log(root)), log(root)
