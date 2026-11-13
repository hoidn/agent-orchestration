"""Phase 3b T4: readers of a run whose journal switches program (`rebased` records, Edit And Continue §4, §8).

The view, `report`, the dashboard, the monitor, the REPL, `input get` and `input answer` read a run with several
programs; a reader without the writer lock that meets a record written after it loaded authority loads the lineage
again once, and none of them writes. Records are written by `tests/rebased_fixture.py` (no command writes one yet,
T7). Commands are local Python scripts; the metered cases use the suite's provider stand-ins on a closed PATH. No
model is called.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.memo import MemoError
from tests import rebased_fixture as fx
from tests.test_workflow_evaluated_lineage_resume import (  # noqa: F401  (`serial_base` is a fixture)
    GATE, GATE_ARGS, P, RENAMED, RUN_ARGS, SERIAL, _copy, _edit, _renamed, _resume, _workspace, cmd, serial_base,
    source,
)
from tests.workflow_inprocess_cli_helpers import cli_inprocess

FIXTURES = Path(__file__).parent / "fixtures"
RECORDED = sorted(path.parent for path in FIXTURES.rglob("memo.jsonl") if (path.parent / "state.json").exists())


def _view(run_root: Path) -> dict:
    from orchestrator.workflow.evaluated.views import load_evaluated_view
    return load_evaluated_view(run_root)


def _encoded(view: dict) -> bytes:
    """`state.json` bytes, as the writer encodes a view (`publish_evaluated_view`)."""
    return json.dumps(view, ensure_ascii=False, allow_nan=False).encode() + b"\n"


def _report(workspace: Path, run_root: Path, fmt: str = "json"):
    done = cli_inprocess(workspace, "report", "--run-id", run_root.name, "--format", fmt)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if fmt == "json" else done.stdout


def _short(identity: str) -> str:
    return identity.rsplit(" / ", 1)[-1]


def _files(run_root: Path) -> dict[str, tuple[bytes, int, int]]:
    """Each file's bytes, inode and modification time: a reader that rewrites a file with equal bytes (the view
    it derived, say) still changes this."""
    return {name: (data, (run_root / name).stat().st_ino, (run_root / name).stat().st_mtime_ns)
            for name, data in fx.tree(run_root).items()}


def _header(run_root: Path) -> dict:
    return json.loads((run_root / "run.json").read_bytes())


@pytest.mark.parametrize("recorded", RECORDED, ids=[path.parts[-3] for path in RECORDED])
def test_view_of_a_run_without_a_record_is_byte_identical(recorded, tmp_path):
    """The reader's view of a run recorded by an earlier build is the `state.json` that build wrote, byte for
    byte; only `status` differs where the writer published `running` and the reader finds no writer."""
    run_root = tmp_path / recorded.name
    shutil.copytree(recorded, run_root)
    for path in run_root.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
    view = _view(run_root)
    stored = json.loads((recorded / "state.json").read_bytes())
    if stored["status"] == "running":
        assert view["status"] == "interrupted"
        view["status"] = "running"
    assert _encoded(view) == (recorded / "state.json").read_bytes()


def test_fresh_view_and_report_of_a_run_without_a_record_carry_no_lineage_keys(serial_base, tmp_path):
    workspace, run_root = _copy(serial_base, tmp_path)
    assert _encoded(_view(run_root)) == (run_root / "state.json").read_bytes()
    report = _report(workspace, run_root)
    assert "programs" not in report["run"] and not any("program" in step for step in report["steps"])
    assert "Programs" not in _report(workspace, run_root, "md")


def test_a_start_a_range_retired_keeps_its_status_in_a_run_without_a_record(serial_base, tmp_path):
    """Only a run with a `rebased` record shows a retired start as `invalidated`; without one the view stays
    as earlier builds wrote it (`running`), so existing runs read byte for byte as before."""
    workspace, run_root = _copy(serial_base, tmp_path)
    journal = run_root / "memo.jsonl"
    journal.write_bytes(journal.read_bytes()[:fx.offset_of(run_root, "committed", "s4")])   # killed in s4
    assert cli_inprocess(workspace, "invalidate", run_root.name, P + "s3").returncode == 0
    rows = _view(run_root)["steps"]
    assert (rows[P + "s3"]["status"], rows[P + "s4"]["status"]) == ("invalidated", "running")
    assert not any("program" in row for row in rows.values())


def _two_programs(serial_base, tmp_path):
    """s3 renamed t3 under a second program cut at s3's commit, resumed to completion."""
    workspace, run_root = _renamed(serial_base, tmp_path)
    (record,) = [(at, row) for at, row in zip(fx.offsets(run_root), fx.rows(run_root)) if row["record"] == "rebased"]
    return workspace, run_root, record[1]


def test_report_and_dashboard_list_programs_and_each_row_program(serial_base, tmp_path):
    from orchestrator.dashboard.scanner import RunScanner
    from orchestrator.dashboard.server import DashboardApp

    workspace, run_root, record = _two_programs(serial_base, tmp_path)
    header = _header(run_root)
    before = _files(run_root)
    report = _report(workspace, run_root)
    programs = report["run"]["programs"]
    assert [(item["digest"], item["cut"]) for item in programs] == [
        (header["program_digest"], None), (record["program_digest"], record["from_offset"])]
    assert programs[0]["time"] == header["started_at"] and programs[1]["time"].startswith("20")
    assert {_short(step["identity"]): (step["program"], step["status"]) for step in report["steps"]} == {
        "s1": (0, "completed"), "s2": (0, "completed"), "s3": (0, "invalidated"), "t3": (1, "completed"),
        "s4": (1, "completed")}
    markdown = _report(workspace, run_root, "md")
    listed = markdown.split("## Programs", 1)[1].split("##", 1)[0]
    assert record["program_digest"] in listed and f"`{record['from_offset']}`" in listed and "None" not in listed
    assert "- program: `1`" in markdown.split("### " + P + "t3", 1)[1].split("###", 1)[0]
    page = DashboardApp(RunScanner([workspace])).handle("GET", f"/runs/w0/{run_root.name}").body.decode()
    section = page.split("<h2>Programs</h2>", 1)[1].split("</section>", 1)[0]
    assert record["program_digest"] in section and str(record["from_offset"]) in section and "None" not in section
    timeline = page.split("<h2>Step Timeline</h2>", 1)[1]
    assert "program 1" in timeline.split(P + "t3", 1)[1].split("</li>", 1)[0]
    assert "program 0" in timeline.split(P + "s1", 1)[1].split("</li>", 1)[0]
    assert _files(run_root) == before


def test_monitor_scanner_reads_a_rebased_run(serial_base, tmp_path):
    from orchestrator.monitor.config import load_monitor_config
    from orchestrator.monitor.scanner import scan_monitor_runs

    workspace, run_root, record = _two_programs(serial_base, tmp_path)
    config = tmp_path / "monitor.json"
    config.write_text(json.dumps({"workspaces": [{"name": "w", "path": str(workspace)}], "email": {
        "backend": "smtp", "from": "t@example.invalid", "to": ["t@example.invalid"], "smtp_host": "localhost"}}))
    (run,) = scan_monitor_runs(load_monitor_config(config))
    assert run.read_error is None and run.state["status"] == "completed"
    assert run.state["programs"][-1]["digest"] == record["program_digest"]


def test_rows_stay_for_steps_the_current_program_dropped(serial_base, tmp_path):
    """A cut at s3's commit cancels it and retires s4's pending start; the edit drops s4. Both rows stay."""
    workspace, run_root = _copy(serial_base, tmp_path)
    journal = run_root / "memo.jsonl"
    journal.write_bytes(journal.read_bytes()[:fx.offset_of(run_root, "committed", "s4")])   # killed in s4
    (run_root / "state.json").unlink()
    _edit(workspace, [*SERIAL[:2], cmd("s3", "(+ s2 10)")], "s3")
    fx.rebase(run_root, workspace, fx.offset_of(run_root, "committed", "s3"), RUN_ARGS)
    rows = _view(run_root)["steps"]
    assert {_short(identity): (row["status"], row["program"]) for identity, row in rows.items()} == {
        "s1": ("completed", 0), "s2": ("completed", 0), "s3": ("invalidated", 0), "s4": ("invalidated", 0)}
    code, started, stderr = _resume(workspace, run_root)
    assert (code, started) == (0, ["s3#3"]), stderr
    rows = _view(run_root)["steps"]
    assert {_short(identity): (row["status"], row["program"]) for identity, row in rows.items()} == {
        "s1": ("completed", 0), "s2": ("completed", 0), "s3": ("completed", 1), "s4": ("invalidated", 0)}


def test_repl_attaches_to_a_rebased_run_under_its_current_program(serial_base, tmp_path):
    workspace, run_root, _record = _two_programs(serial_base, tmp_path)
    before = _files(run_root)

    def repl(*lines: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "orchestrator", "repl", *RUN_ARGS, "--run-id", run_root.name],
                              input="\n".join((*lines, ":quit", "")), cwd=workspace, capture_output=True, text=True,
                              timeout=180, check=False, env={**os.environ, "PYTHONPATH": str(fx.ROOT)})

    attached = repl(":result", ":bindings", "t3")
    assert attached.returncode == 0, attached.stderr
    lines = attached.stdout.splitlines()
    assert "4" in lines and "t3 : Int" in lines and "position: halt" in lines, attached.stdout
    (workspace / "pipe.orc").write_text(source(SERIAL, "s4"))       # the first program, no longer in force
    refused = repl()
    assert "resume_program_changed" in refused.stdout + refused.stderr
    assert "current program" in refused.stdout + refused.stderr and "run header" not in refused.stdout + refused.stderr
    assert _files(run_root) == before


def test_a_long_lived_reader_checks_the_artifacts_again_at_each_read(serial_base, tmp_path):
    """The table cache of `read_memo` is never what verifies an artifact: the REPL and the dashboard load
    authority, which verifies every lineage artifact, at each attach and each scan."""
    from orchestrator.cli.commands.repl import ReplSession, _dispatch
    from orchestrator.dashboard.scanner import RunScanner

    workspace, run_root, record = _two_programs(serial_base, tmp_path)
    scanner = RunScanner([workspace])
    assert scanner.scan().runs[0].parse_error is None
    session = ReplSession(workspace=workspace, state_dir=None)
    with contextlib.chdir(workspace):
        _dispatch(session, f":load {' '.join(RUN_ARGS)}")
        _dispatch(session, f":attach {run_root.name}")
    artifact = run_root / f"closed_program.{record['program_digest'].removeprefix('sha256:')}.json"
    artifact.write_bytes(artifact.read_bytes()[:-40])
    (again,) = scanner.scan().runs
    assert again.parse_error.startswith("memo_inconsistent") and artifact.name in again.parse_error
    with contextlib.chdir(workspace), pytest.raises(ValueError, match=artifact.name):
        _dispatch(session, f":attach {run_root.name}")


def _gate_run(tmp_path: Path) -> tuple[Path, Path]:
    """`s1`, a host request (suspended), then `s2`."""
    workspace = _workspace(tmp_path / "ws", SERIAL, "s4")
    (workspace / "gate.orc").write_text(GATE.replace("S2_ARG", "s1"))
    fx.cli(workspace, "run", *GATE_ARGS)
    (run_root,) = (workspace / ".orchestrate" / "runs").iterdir()
    assert fx.rows(run_root)[-1]["record"] == "suspended"
    return workspace, run_root


GATE_WITH_S3 = GATE.replace(':returns Int)))\n      s2)))', ':returns Int))\n           (s3 (command-result step :argv '
                                                         '("python" "t.py" "s3" s2) :returns Int)))\n      s3)))')


def test_input_pending_and_answer_read_a_rebased_run(tmp_path):
    workspace, run_root = _gate_run(tmp_path)
    view = _files(run_root)["state.json"]
    request = json.loads(fx.cli(workspace, "input", "get", run_root.name).stdout)["request_id"]
    (workspace / "gate.orc").write_text(GATE_WITH_S3.replace("S2_ARG", "s1"))
    fx.rebase(run_root, workspace, None, GATE_ARGS)                 # the pending request is kept
    before = _files(run_root)
    assert before["state.json"] == view
    got = fx.cli(workspace, "input", "get", run_root.name)
    assert got.returncode == 0, got.stderr
    assert json.loads(got.stdout)["request_id"] == request
    assert _files(run_root) == before
    answered = fx.cli(workspace, "input", "answer", run_root.name, request, "--by", "operator", "--value", '"APPROVED"')
    assert answered.returncode == 0, answered.stderr
    assert cli_inprocess(workspace, "resume", run_root.name).returncode == 0
    assert fx.rows(run_root)[-1] == {"record": "terminal", "outcome": "completed", "value": 3}


@pytest.mark.parametrize("race", ["none", "new-table", "same-table", "second-record"])
def test_reader_racing_a_record_returns_old_or_new_or_says_rebasing(tmp_path, monkeypatch, race):
    """A record lands between `input get`'s authority load and its journal read: the reader loads the lineage
    again, once, and returns the new run; a second record during that reload is reported as a rebase in
    progress. The reader writes no byte in any case."""
    from orchestrator.workflow.evaluated import host_input

    workspace, run_root = _gate_run(tmp_path)
    view = _files(run_root)["state.json"]
    request = json.loads(fx.cli(workspace, "input", "get", run_root.name).stdout)["request_id"]
    assert _files(run_root)["state.json"] == view
    (workspace / "gate.orc").write_text((GATE if race == "same-table" else GATE_WITH_S3).replace("S2_ARG", "(+ s1 1)"))
    second = fx.store_program(run_root, workspace, GATE_ARGS)
    (workspace / "gate.orc").write_text(GATE.replace("S2_ARG", "(+ s1 2)"))
    third = fx.store_program(run_root, workspace, GATE_ARGS)
    records = {"none": [], "new-table": [second], "same-table": [second], "second-record": [second, third]}[race]
    calls, real = [], host_input._checked_snapshot

    def gated(authority):
        calls.append(authority.program.digest)
        if len(calls) <= len(records):
            fx.append_rebased(run_root, records[len(calls) - 1], None)     # the writer, between the two reads
        return real(authority)

    monkeypatch.setattr(host_input, "_checked_snapshot", gated)
    before = _files(run_root)
    done = cli_inprocess(workspace, "input", "get", run_root.name)
    assert len(calls) <= 2                                           # one reload at most, never a loop
    journal = run_root / "memo.jsonl"
    assert _files(run_root) == {**before, "memo.jsonl": (journal.read_bytes(), journal.stat().st_ino,
                                                          journal.stat().st_mtime_ns)}
    if race == "second-record":
        assert done.returncode != 0 and "memo_inconsistent" in done.stderr and "being rebased" in done.stderr
        return
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["request_id"] == request
    assert len(calls) == (2 if race == "new-table" else 1)


def test_a_corrupt_journal_without_a_record_is_not_blamed_on_a_rebase(tmp_path):
    """`input get` reloads only when the program in force changed: a corrupt row in a journal that never
    switched program is reported as it is, not as a rebase in progress."""
    workspace, run_root = _gate_run(tmp_path)
    journal = run_root / "memo.jsonl"
    journal.write_bytes(journal.read_bytes().replace(b'"attempt":1', b'"attempt":2', 1))   # s1's first start
    assert fx.rows(run_root)[0]["attempt"] == 2 and fx.rows(run_root)[0]["record"] == "started"
    before = _files(run_root)
    done = cli_inprocess(workspace, "input", "get", run_root.name)
    assert done.returncode != 0 and "memo_inconsistent" in done.stderr, done.stderr
    assert "being rebased" not in done.stderr
    assert _files(run_root) == before


METERED_FIRST = ('(first (provider-result providers.review :prompt prompts.base\n'
                 '                    :inputs (message) :model "claude-haiku-5-5" :effort "high" :returns Result))')
OK = 'import os\nfrom pathlib import Path\nPath(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(\'{"ok": true}\')\n'


@pytest.mark.parametrize("edit", ["same-class", "another-class"])
def test_cancelled_metered_attempts_stay_in_report_and_under_the_cap(tmp_path, edit):
    """A cut over two committed provider calls refunds nothing: `report` keeps both attempts in its total and the
    spend cap counts them, also when `first` becomes a command at the same identity."""
    from tests.test_workflow_evaluated_provider_usage import _env, _orchestrator
    from tests.test_workflow_evaluated_report_usage import ONE_CALL
    from tests.test_workflow_evaluated_spend_cap import BELOW_ONE_CALL, _calls, _capped, _run, _run_id

    root = _capped(tmp_path)
    (root / "ok.py").write_text(OK)
    boundaries = json.loads((root / "commands.json").read_text())
    (root / "commands.json").write_text(json.dumps(
        {**boundaries, "ok": {"stable_command": ["python", "ok.py"], "closure": ["ok.py"]}}))
    assert _run(root).returncode == 0 and _calls(root) == 2
    run_root = root / ".orchestrate" / "runs" / _run_id(root)
    first = '(first (command-result ok :argv ("python" "ok.py") :returns Result))' if edit == "another-class" \
        else METERED_FIRST.replace('"high"', '"low"')
    main = root / "main.orc"
    assert METERED_FIRST in main.read_text()
    main.write_text(main.read_text().replace(METERED_FIRST, first))
    args = ["main.orc", "--source-root", ".", "--provider-externs-file", "providers.json", "--prompt-externs-file",
            "prompts.json", "--command-boundaries-file", "commands.json", "--input", "message=hi"]
    fx.rebase(run_root, root, fx.offset_of(run_root, "committed", "first"), args, env=_env(root))
    assert _calls(root) == 2

    def total():
        done = _orchestrator(root, "report", "--format", "json")
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)["run"]["usage"]

    assert (total()["attempts"], total()["cost_usd"]) == (2, pytest.approx(2 * ONE_CALL))
    capped = _orchestrator(root, "resume", _run_id(root), "--max-cost-usd", BELOW_ONE_CALL)
    assert capped.returncode == 1 and "[spend_cap_reached]" in capped.stderr and _calls(root) == 2, capped.stderr
    assert total()["cost_usd"] == pytest.approx(2 * ONE_CALL)
    resumed = _orchestrator(root, "resume", _run_id(root), "--max-cost-usd", "100")
    assert resumed.returncode == 0, resumed.stderr
    calls = 3 if edit == "another-class" else 4
    assert _calls(root) == calls
    assert (total()["attempts"], total()["cost_usd"], total()["unknown_attempts"]) == (
        calls, pytest.approx(calls * ONE_CALL), 0)


def test_invalidate_on_a_rebased_run_never_changes_the_program(serial_base, tmp_path):
    workspace, run_root, record = _two_programs(serial_base, tmp_path)
    programs = sorted(run_root.glob("closed_program*.json"))
    authority = {path.name: path.read_bytes() for path in [run_root / "run.json", *programs]}
    journal = (run_root / "memo.jsonl").read_bytes()
    lineage = _view(run_root)["programs"]
    done = cli_inprocess(workspace, "invalidate", run_root.name, P + "t3")
    assert done.returncode == 0, done.stderr
    assert {path.name: path.read_bytes() for path in [run_root / "run.json", *programs]} == authority
    assert sorted(run_root.glob("closed_program*.json")) == programs
    appended = (run_root / "memo.jsonl").read_bytes()
    assert appended.startswith(journal) and [row["record"] for row in fx.rows(run_root)[-1:]] == ["invalidated"]
    assert appended.count(b"\n") == journal.count(b"\n") + 1
    assert _view(run_root)["programs"] == lineage
    code, started, stderr = _resume(workspace, run_root)
    assert (code, started) == (0, ["t3#2", "s4#3"]), stderr


def test_program_change_refusal_on_a_rebased_run_compares_with_its_current_program(serial_base, tmp_path):
    workspace, run_root, _record = _two_programs(serial_base, tmp_path)
    _edit(workspace, [*RENAMED[:3], cmd("s4", "(+ t3 1)")], "s4")
    before = _files(run_root)
    done = cli_inprocess(workspace, "resume", run_root.name)
    assert done.returncode == 2 and "resume_program_changed" in done.stderr
    changed = [line.strip() for line in done.stderr.splitlines() if line.startswith(("  added", "  removed", "  changed"))]
    assert changed == [f"changed {P}s4"], done.stderr
    assert _files(run_root) == before


@pytest.mark.parametrize("params", ['((n Int :default 0) (m Int))', '((n String :default "0"))'],
                         ids=["added-parameter", "changed-type"])
def test_a_later_program_that_cannot_bind_the_run_inputs_is_named_by_readers(serial_base, tmp_path, params):
    """Only a hand-written record can name such a program (T7 refuses the edit before writing); a reader says
    why it cannot read the run instead of showing it interrupted with nothing to run next."""
    workspace, run_root = _copy(serial_base, tmp_path)
    text = source([*SERIAL, cmd("s5", "s4")], "s5").replace("((n Int :default 0))", params)
    (workspace / "pipe.orc").write_text(text)
    cut = fx.offset_of(run_root, "committed", "s1")             # every commit cancelled: nothing to replay
    fx.rebase(run_root, workspace, cut, [*RUN_ARGS, "--input", "m=1"] if "(m Int)" in params else RUN_ARGS)
    before = _files(run_root)
    reported = cli_inprocess(workspace, "report", "--run-id", run_root.name)
    assert reported.returncode == 1 and "memo_inconsistent" in reported.stderr
    assert "cannot bind the run's inputs" in reported.stderr, reported.stderr
    with pytest.raises(ValueError, match="cannot bind the run's inputs"):
        _view(run_root)
    assert _files(run_root) == before
