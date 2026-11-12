"""Phase 3b T3: a journal with `rebased` records is read row by row under the program that wrote each row.

No command writes the record yet (T7); `tests/rebased_fixture.py` writes it with the design's exact keys after
storing the edited program as an ordinary run of it writes it. Commands are local Python and shell scripts; the agent
cases use the suite's fake `codex` on a closed PATH. No model is called.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.memo import MemoError
from tests import rebased_fixture as fx
from tests.agent_session_shims import FAKE_CODEX, closed_path
from tests.workflow_inprocess_cli_helpers import cli_inprocess

P = "workflow:pipe::run / "
STEP = '''import json, os, sys
from pathlib import Path
Path("log.txt").open("a").write(sys.argv[1] + "\\n")
marker = Path("fail-" + sys.argv[1])
if marker.exists():
    marker.unlink()
    sys.exit(1)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(int(sys.argv[2]) + 1))
'''
SHELL_STEP = 'echo "$1" >> log.txt\necho $(( $2 + 1 )) > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n'
COMMANDS = {"step": {"stable_command": ["python", "t.py"], "closure": ["t.py"]},
            "shell": {"stable_command": ["sh", "s.sh"], "closure": ["s.sh"]}}
RUN_ARGS = ["pipe.orc", "--command-boundaries-file", "commands.json"]


def cmd(name: str, arg: str, tool: str = "step") -> str:
    argv = '"python" "t.py"' if tool == "step" else '"sh" "s.sh"'
    return f'({name} (command-result {tool} :argv ({argv} "{name}" {arg}) :returns Int))'


def source(lets: list[str], result: str) -> str:
    return ('(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n  (defmodule pipe) (export run)\n'
            '  (defworkflow run ((n Int :default 0)) -> Int\n    (let* (' + "\n           ".join(lets)
            + f')\n      {result})))\n')


SERIAL = [cmd("s1", "n"), cmd("s2", "s1"), cmd("s3", "s2"), cmd("s4", "s3")]


def _workspace(root: Path, lets: list[str], result: str) -> Path:
    root.mkdir(parents=True)
    (root / "t.py").write_text(STEP)
    (root / "s.sh").write_text(SHELL_STEP)
    (root / "commands.json").write_text(json.dumps(COMMANDS))
    (root / "pipe.orc").write_text(source(lets, result))
    return root


def _run(workspace: Path) -> Path:
    fx.cli(workspace, "run", *RUN_ARGS)
    (run_root,) = (workspace / ".orchestrate" / "runs").iterdir()
    return run_root


@pytest.fixture(scope="module")
def serial_base(tmp_path_factory):
    """`s1`..`s4`; `s3` fails once and the run is resumed to completion, so the journal has a `failed` row."""
    workspace = _workspace(tmp_path_factory.mktemp("serial") / "ws", SERIAL, "s4")
    (workspace / "fail-s3").write_text("")
    run_root = _run(workspace)
    assert fx.rows(run_root)[-1]["outcome"] == "failed"
    resumed = fx.cli(workspace, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert fx.rows(run_root)[-1] == {"record": "terminal", "outcome": "completed", "value": 4}
    return workspace


def _copy(base: Path, tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "ws"
    shutil.copytree(base, workspace, symlinks=True)
    (run_root,) = (workspace / ".orchestrate" / "runs").iterdir()
    return workspace, run_root


def _edit(workspace: Path, lets: list[str], result: str) -> None:
    (workspace / "pipe.orc").write_text(source(lets, result))


def _started(run_root: Path, since: int) -> list[str]:
    return [f"{row['identity'].removeprefix(P)}#{row['attempt']}" for row in fx.rows(run_root)[since:]
            if row["record"] == "started"]


def _resume(workspace: Path, run_root: Path) -> tuple[int, list[str], str]:
    """In-process, so the suite's fold and start-view guards check every reduction of the lineage."""
    before = len(fx.rows(run_root))
    done = cli_inprocess(workspace, "resume", run_root.name)
    return done.returncode, _started(run_root, before), done.stderr


def test_resume_continues_under_the_program_a_record_names(serial_base, tmp_path):
    workspace, run_root = _copy(serial_base, tmp_path)
    _edit(workspace, [*SERIAL[:2], cmd("s3", "(+ s2 10)"), SERIAL[3]], "s4")
    fx.rebase(run_root, workspace, fx.offset_of(run_root, "committed", "s3"), RUN_ARGS)
    code, started, stderr = _resume(workspace, run_root)
    assert (code, started) == (0, ["s3#3", "s4#2"]), stderr
    assert fx.rows(run_root)[-1] == {"record": "terminal", "outcome": "completed", "value": 14}
    assert _resume(workspace, run_root)[:2] == (0, [])


@pytest.mark.parametrize("torn", [False, True], ids=["artifact", "artifact-and-torn-record"])
def test_artifact_that_no_record_names_is_ignored(serial_base, tmp_path, torn):
    workspace, run_root = _copy(serial_base, tmp_path)
    original = (workspace / "pipe.orc").read_text()
    _edit(workspace, [*SERIAL[:3], cmd("s4", "(+ s3 1)")], "s4")
    digest = fx.store_program(run_root, workspace, RUN_ARGS)
    if torn:
        fx.append_rebased(run_root, digest, None)
        journal = run_root / "memo.jsonl"
        journal.write_bytes(journal.read_bytes()[:-1])          # W3: the record's line never ended
    (workspace / "pipe.orc").write_text(original)
    before = fx.tree(run_root)
    assert _resume(workspace, run_root)[:2] == (0, [])
    assert cli_inprocess(workspace, "report", "--run-id", run_root.name).returncode == 0
    assert fx.tree(run_root) == before
    _edit(workspace, [*SERIAL[:3], cmd("s4", "(+ s3 1)")], "s4")
    code, _, stderr = _resume(workspace, run_root)
    assert code == 2 and "resume_program_changed" in stderr
    assert fx.tree(run_root) == before


def _corrupt(path: Path, change: str, first: Path) -> None:
    if change == "missing":
        path.unlink()
    elif change == "other-program":
        path.write_bytes(first.read_bytes())                 # a valid program, not the one its name gives
    else:
        path.write_bytes(path.read_bytes()[:-40])


@pytest.mark.parametrize("change", ["missing", "other-program", "truncated"])
def test_missing_or_altered_artifact_is_memo_inconsistent(serial_base, tmp_path, change):
    workspace, run_root = _copy(serial_base, tmp_path)
    _edit(workspace, [*SERIAL[:3], cmd("s4", "(+ s3 1)")], "s4")
    digest = fx.rebase(run_root, workspace, fx.offset_of(run_root, "committed", "s4"), RUN_ARGS)
    name = f"closed_program.{digest.removeprefix('sha256:')}.json"
    _corrupt(run_root / name, change, run_root / "closed_program.json")
    before = fx.tree(run_root)
    resumed = cli_inprocess(workspace, "resume", run_root.name)
    invalidated = cli_inprocess(workspace, "invalidate", run_root.name, P + "s1")
    reported = cli_inprocess(workspace, "report", "--run-id", run_root.name)
    assert (resumed.returncode, invalidated.returncode, reported.returncode) == (2, 2, 1)
    for done in (resumed, invalidated, reported):
        assert "memo_inconsistent" in done.stderr + done.stdout and name in done.stderr + done.stdout
    assert fx.tree(run_root) == before


def _invalid_record(workspace: Path, run_root: Path, case: str) -> str:
    """Write the case's record; return the text its refusal names."""
    edited = [*SERIAL[:3], cmd("s4", "(+ s3 1)")]
    if case == "same-program":
        digest = json.loads((run_root / "run.json").read_bytes())["program_digest"]
        shutil.copyfile(run_root / "closed_program.json", run_root / f"closed_program.{digest[7:]}.json")
        fx.append_rebased(run_root, digest, None)
        return "already in force"
    if case == "kept-commit-not-a-site":
        _edit(workspace, SERIAL[:3], "s3")
        fx.rebase(run_root, workspace, None, RUN_ARGS)
        return f"{P}s4"
    _edit(workspace, edited, "s4")
    cut = {"start-of-a-committed-attempt": fx.offset_of(run_root, "started", "s2"),
           "failed-row": fx.offset_of(run_root, "failed", "s3"),
           "past-the-end": (run_root / "memo.jsonl").stat().st_size + 100}[case]
    fx.rebase(run_root, workspace, cut, RUN_ARGS)
    return "neither an active commit nor a pending start"


@pytest.mark.parametrize("case", ["same-program", "start-of-a-committed-attempt", "failed-row", "past-the-end",
                                  "kept-commit-not-a-site"])
def test_invalid_records_are_memo_inconsistent(serial_base, tmp_path, case):
    workspace, run_root = _copy(serial_base, tmp_path)
    reason = _invalid_record(workspace, run_root, case)
    before = fx.tree(run_root)
    reported = cli_inprocess(workspace, "report", "--run-id", run_root.name)
    resumed = cli_inprocess(workspace, "resume", run_root.name)
    assert (reported.returncode, resumed.returncode) == (1, 2)
    for done in (reported, resumed):
        assert "memo_inconsistent" in done.stdout + done.stderr and reason in done.stdout + done.stderr
    assert fx.tree(run_root) == before


RENAMED = [*SERIAL[:2], cmd("t3", "s2"), cmd("s4", "t3")]


def _renamed(serial_base, tmp_path):
    workspace, run_root = _copy(serial_base, tmp_path)
    _edit(workspace, RENAMED, "s4")
    fx.rebase(run_root, workspace, fx.offset_of(run_root, "committed", "s3"), RUN_ARGS)
    assert _resume(workspace, run_root)[:2] == (0, ["t3#1", "s4#2"])
    return workspace, run_root


def test_invalidate_reaches_back_past_a_record_after_a_rename(serial_base, tmp_path):
    workspace, run_root = _renamed(serial_base, tmp_path)
    done = cli_inprocess(workspace, "invalidate", run_root.name, P + "s2")
    assert done.returncode == 0, done.stderr
    code, started, stderr = _resume(workspace, run_root)
    assert (code, started) == (0, ["s2#2", "t3#2", "s4#3"]), stderr


def test_second_record_may_cut_before_the_first(serial_base, tmp_path):
    workspace, run_root = _renamed(serial_base, tmp_path)
    first_record = next(at for at, row in zip(fx.offsets(run_root), fx.rows(run_root)) if row["record"] == "rebased")
    _edit(workspace, [SERIAL[0], cmd("s2", "(+ s1 5)"), *RENAMED[2:]], "s4")
    cut = fx.offset_of(run_root, "committed", "s2")
    assert cut < first_record
    fx.rebase(run_root, workspace, cut, RUN_ARGS)
    code, started, stderr = _resume(workspace, run_root)
    assert (code, started) == (0, ["s2#2", "t3#2", "s4#3"]), stderr
    assert fx.rows(run_root)[-1]["value"] == 9


def test_three_programs_one_returning_to_the_first_resume_and_complete(serial_base, tmp_path):
    workspace, run_root = _copy(serial_base, tmp_path)
    first = (workspace / "pipe.orc").read_text()
    _edit(workspace, [*SERIAL[:3], cmd("s4", "(+ s3 1)")], "s4")
    fx.rebase(run_root, workspace, fx.offset_of(run_root, "committed", "s4"), RUN_ARGS)
    assert _resume(workspace, run_root)[:2] == (0, ["s4#2"])
    _edit(workspace, [*SERIAL[:2], cmd("s3", "(+ s2 1)"), cmd("s4", "(+ s3 1)")], "s4")
    fx.rebase(run_root, workspace, fx.offset_of(run_root, "committed", "s3"), RUN_ARGS)
    assert _resume(workspace, run_root)[:2] == (0, ["s3#3", "s4#3"])
    (workspace / "pipe.orc").write_text(first)
    header = json.loads((run_root / "run.json").read_bytes())["program_digest"]
    assert fx.rebase(run_root, workspace, fx.offset_of(run_root, "committed", "s3"), RUN_ARGS) == header
    assert _resume(workspace, run_root)[:2] == (0, ["s3#4", "s4#4"])
    assert fx.rows(run_root)[-1] == {"record": "terminal", "outcome": "completed", "value": 4}
    assert len(list(run_root.glob("closed_program.*.json"))) == 3
    assert cli_inprocess(workspace, "report", "--run-id", run_root.name).returncode == 0
    before = fx.tree(run_root)
    assert _resume(workspace, run_root)[:2] == (0, [])
    assert fx.tree(run_root) == before


def test_record_reopens_a_completed_terminal(serial_base, tmp_path):
    workspace, run_root = _copy(serial_base, tmp_path)
    _edit(workspace, SERIAL, "(+ s4 100)")
    fx.rebase(run_root, workspace, None, RUN_ARGS)
    code, started, stderr = _resume(workspace, run_root)
    assert (code, started) == (0, []), stderr
    assert [row["record"] for row in fx.rows(run_root)[-3:]] == ["terminal", "rebased", "terminal"]
    assert fx.rows(run_root)[-1]["value"] == 104


def test_edit_that_drops_a_pinned_interpreter_stays_readable(tmp_path):
    workspace = _workspace(tmp_path / "ws", [cmd("s1", "n"), cmd("s2", "s1", "shell"), cmd("s3", "s2")], "s3")
    run_root = _run(workspace)
    assert set(json.loads((run_root / "run.json").read_bytes())["interpreters"]) == {"python", "sh"}
    _edit(workspace, [cmd("s1", "n"), cmd("s3", "s1")], "s3")
    fx.rebase(run_root, workspace, fx.offset_of(run_root, "committed", "s2"), RUN_ARGS)
    code, started, stderr = _resume(workspace, run_root)
    assert (code, started) == (0, ["s3#2"]), stderr
    assert cli_inprocess(workspace, "report", "--run-id", run_root.name).returncode == 0


def test_later_program_with_an_unpinned_interpreter_is_refused(serial_base, tmp_path):
    workspace, run_root = _copy(serial_base, tmp_path)
    assert set(json.loads((run_root / "run.json").read_bytes())["interpreters"]) == {"python"}
    _edit(workspace, [*SERIAL, cmd("s5", "s4", "shell")], "s5")
    fx.rebase(run_root, workspace, None, RUN_ARGS)
    before = fx.tree(run_root)
    resumed = cli_inprocess(workspace, "resume", run_root.name)
    reported = cli_inprocess(workspace, "report", "--run-id", run_root.name)
    assert (resumed.returncode, reported.returncode) == (2, 1)
    for done in (resumed, reported):
        assert "memo_inconsistent" in done.stdout + done.stderr and "did not pin" in done.stdout + done.stderr
    assert fx.tree(run_root) == before
    assert not (workspace / "log.txt").read_text().count("s5")


GATE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule gate) (import std/host :only (HostReply)) (export run)
  (defenum Approval APPROVED DENIED)
  (defworkflow run ((question String :default "Approve?")) -> Int
    (let* ((s1 (command-result step :argv ("python" "t.py" "s1" 0) :returns Int))
           (reply (request-input question :returns Approval :timeout-sec 600))
           (s2 (command-result step :argv ("python" "t.py" "s2" S2_ARG) :returns Int)))
      s2)))
'''
GATE_ARGS = ["gate.orc", "--source-root", ".", "--command-boundaries-file", "commands.json"]


def test_host_reply_committed_before_a_record_is_kept(tmp_path):
    workspace = _workspace(tmp_path / "ws", SERIAL, "s4")
    (workspace / "gate.orc").write_text(GATE.replace("S2_ARG", "s1"))
    started = fx.cli(workspace, "run", *GATE_ARGS)
    (run_root,) = (workspace / ".orchestrate" / "runs").iterdir()
    request = next(row["host_request"] for row in fx.rows(run_root) if "host_request" in row)
    answered = fx.cli(workspace, "input", "answer", run_root.name, request["request_id"], "--by", "operator",
                      "--value", '"APPROVED"')
    assert answered.returncode == 0, started.stderr + answered.stderr
    assert fx.cli(workspace, "resume", run_root.name).returncode == 0
    (workspace / "gate.orc").write_text(GATE.replace("S2_ARG", "(+ s1 10)"))
    fx.rebase(run_root, workspace, fx.offset_of(run_root, "committed", "s2"), GATE_ARGS)
    before = len(fx.rows(run_root))
    done = cli_inprocess(workspace, "resume", run_root.name)
    assert done.returncode == 0, done.stderr
    assert [row["identity"].rsplit(" / ", 1)[-1] for row in fx.rows(run_root)[before:]
            if row["record"] == "started"] == ["s2"]
    assert fx.rows(run_root)[-1] == {"record": "terminal", "outcome": "completed", "value": 12}


AGENT = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defrecord Feedback (notes List[String]))
  (defprompt review (:fills (text :text)) -> Feedback "Review: {text}")
  (defworkflow run ((task String)) -> Int
    (let* ((reviewer (agent providers.codex :model "reviewer" :effort "high"))
           (b1 (provider-result reviewer :prompt (review :text task) :timeout-sec 60))
           (c (command-result step :argv ("python" "t.py" "c" 0) :returns Int))
           B2
           (d (command-result step :argv ("python" "t.py" "d" c) :returns Int)))
      d)))'''
B2_AGENT = '(b2 (provider-result reviewer :prompt (review :text task) :timeout-sec 60))'
B2_COMMAND = '(b2 (command-result step :argv ("python" "t.py" "b2" c) :returns Int))'
AGENT_ARGS = ["main.orc", "--source-root", ".", "--provider-externs-file", "providers.json",
              "--command-boundaries-file", "commands.json", "--input", "task=t"]


def _agent_env(root: Path, plan: list[dict]) -> dict[str, str]:
    """A fresh fake `codex` outside the workspace (its call counter must not be copied with the workspace)."""
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "codex").write_text(f"#!{sys.executable}\n" + FAKE_CODEX)
    (bin_dir / "codex").chmod(0o700)
    return {"PATH": closed_path(bin_dir), "CODEX_HOME": str(root / "codex"),
            "AGENT_SHIM_PLAN": json.dumps({"codex": plan})}


@pytest.fixture(scope="module")
def agent_base(tmp_path_factory):
    """`b2`'s agent turn attempt fails after dispatch (`provider_result_invalid` class); the run stops there."""
    root = tmp_path_factory.mktemp("agent")
    workspace = _workspace(root / "ws", SERIAL, "s4")
    (workspace / "main.orc").write_text(AGENT.replace("B2", B2_AGENT))
    (workspace / "providers.json").write_text('{"providers.codex": "codex"}')
    env = _agent_env(root / "run", [{"mode": "success", "result": {"notes": ["n"]}}, {"mode": "invalid-result"}])
    fx.cli(workspace, "run", *AGENT_ARGS, env=env)
    (run_root,) = (workspace / ".orchestrate" / "runs").iterdir()
    failed = [row for row in fx.rows(run_root) if row["record"] == "failed"]
    assert [row["identity"].rsplit(" / ", 1)[-1] for row in failed] == ["b2"]
    return root, env


def _agent_copy(agent_base, tmp_path):
    root, env = agent_base
    shutil.copytree(root, tmp_path / "agent", symlinks=True)
    workspace = tmp_path / "agent" / "ws"
    env = {**env, "PATH": closed_path(tmp_path / "agent" / "run" / "bin"), "CODEX_HOME": str(tmp_path / "agent" / "codex")}
    (run_root,) = (workspace / ".orchestrate" / "runs").iterdir()
    (workspace / "main.orc").write_text(AGENT.replace("B2", B2_COMMAND))
    edit_env = _agent_env(tmp_path / "edit", [{"mode": "success", "result": {"notes": ["n"]}}])
    return workspace, run_root, env, edit_env


def test_dispatched_agent_attempt_keeps_its_class_across_a_record(agent_base, tmp_path):
    workspace, run_root, env, edit_env = _agent_copy(agent_base, tmp_path)
    fx.rebase(run_root, workspace, None, AGENT_ARGS, env=edit_env)
    resumed = fx.cli(workspace, "resume", run_root.name, env=env)
    assert resumed.returncode == 0, resumed.stderr
    assert [f"{row['identity'].rsplit(' / ', 1)[-1]}#{row['attempt']}" for row in fx.rows(run_root)
            if row["record"] == "started"][-2:] == ["b2#2", "d#1"]
    before = fx.tree(run_root)
    refused = fx.cli(workspace, "invalidate", run_root.name, "workflow:main::run / c", env=env)
    assert refused.returncode == 2 and "invalidate_agent_session_advanced" in refused.stderr
    assert fx.tree(run_root) == before


@pytest.mark.parametrize("case", ["committed-coordinator", "dispatched-agent-attempt"])
def test_cut_over_an_agent_history_is_memo_inconsistent(agent_base, tmp_path, case):
    workspace, run_root, env, edit_env = _agent_copy(agent_base, tmp_path)
    cut = fx.offset_of(run_root, "committed", "b1" if case == "committed-coordinator" else "c")
    fx.rebase(run_root, workspace, cut, AGENT_ARGS, env=edit_env)
    before = fx.tree(run_root)
    reported = fx.cli(workspace, "report", "--run-id", run_root.name, env=env)
    resumed = fx.cli(workspace, "resume", run_root.name, env=env)
    reason = "committed coordinator" if case == "committed-coordinator" else "dispatched agent turn attempt"
    for done in (reported, resumed):
        assert done.returncode in (1, 2) and "memo_inconsistent" in done.stdout + done.stderr
        assert reason in done.stdout + done.stderr
    assert fx.tree(run_root) == before


def test_child_journal_with_a_record_fails_closed(tmp_path):
    from orchestrator.workflow.run_ref import evaluated_child
    from tests.test_workflow_evaluated_child_authority import _prepared_child

    other = next(Path(__file__).parent.glob("fixtures/declaration_pre_change/provider_committed/runs/*"))
    with _prepared_child(tmp_path) as (_request, _owner, _prepared, root, arguments):
        digest = json.loads((other / "run.json").read_bytes())["program_digest"]
        shutil.copyfile(other / "closed_program.json", root / f"closed_program.{digest[7:]}.json")
        memo = root / "memo.jsonl"
        terminal = memo.read_bytes()
        fx.append_rebased(root, digest, None)
        memo.write_bytes(memo.read_bytes() + terminal)
        with pytest.raises(MemoError, match="rebased record names a program whose site table was not supplied"):
            evaluated_child.validate_evaluated_child_terminal(**arguments)
