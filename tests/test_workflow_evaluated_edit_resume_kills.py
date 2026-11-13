"""Phase 3b T7: an acceptance killed in each crash window of Edit And Continue §4 (W1 to W5).

A gated launcher runs the public CLI with one function wrapped per window; at the window it publishes a marker and
blocks, and the test kills its process group (no sleeps decide anything). Afterwards the run is entirely under the
old program or entirely under the new one with the cut applied, nothing was dispatched before the record was
durable, and the next `resume` does what the design's table says. Commands are local Python stand-ins.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time

import pytest

from orchestrator.workflow.evaluated.memo import current_digest
from tests import rebased_fixture as fx
from tests.test_workflow_evaluated_edit_resume_plan import NEW, cmd, edit, run, serial, tree
from tests.workflow_inprocess_cli_helpers import cli_inprocess

ROOT = Path(__file__).resolve().parents[1]

_GATE = '''\
import os, signal, sys
from pathlib import Path

window, marker = os.environ["ORC_TEST_WINDOW"], Path(os.environ["ORC_TEST_MARKER"])


def stop():
    temporary = marker.with_name(marker.name + ".tmp")
    temporary.write_text(window)
    temporary.replace(marker)
    signal.pause()


def rebased(row):
    return isinstance(row, dict) and row.get("record") in {"rebased", "invalidated"}


from orchestrator.workflow import workspace_files
from orchestrator.workflow.evaluated import memo, views, runtime

if window == "W1":                       # the temporary file is synced, its name not yet taken
    real_rename = workspace_files.rename_noreplace_at
    def rename(*args):
        if args[3].startswith("closed_program."):
            stop()
        return real_rename(*args)
    workspace_files.rename_noreplace_at = rename
elif window == "W2":                     # the artifact is durable, no record
    real_repair = memo.repair_torn_tail
    def repair(*args, **kwargs):
        stop()
    memo.repair_torn_tail = repair
elif window in {"W3", "W4"}:             # half a record; a complete record whose sync is not acknowledged
    real_append = memo.append_record
    def append(path, row, **kwargs):
        if not rebased(row):
            return real_append(path, row, **kwargs)
        encoded = memo._encode_record(row)
        with open(path, "ab") as journal:
            journal.write(encoded[: len(encoded) // 2] if window == "W3" else encoded)
        stop()
    memo.append_record = append
elif window == "W5":                     # the record is durable, the view is still the old program's
    real_publish = views.publish_evaluated_view
    def publish(authority, entry, **kwargs):
        if rebased(entry.data):
            stop()
        return real_publish(authority, entry, **kwargs)
    views.publish_evaluated_view = publish
elif window == "commit":                 # after each committed step: the kill suite's window
    real_runtime_append = runtime.append_record
    def committed(*args, **kwargs):
        entry = real_runtime_append(*args, **kwargs)
        if entry.data.get("record") == "committed":
            stop()
        return entry
    runtime.append_record = committed

from orchestrator.cli import main
raise SystemExit(main())
'''


def env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}


def killed(root: Path, window: str, *args: str) -> None:
    """Run `orchestrator ARGS` until it reaches `window`, then kill its process group."""
    control = root.parent / f"control-{window}-{time.monotonic_ns()}"
    control.mkdir()
    (control / "gate.py").write_text(_GATE)
    marker = control / "reached"
    process = subprocess.Popen([sys.executable, str(control / "gate.py"), *args], cwd=root,
                               env={**env(), "ORC_TEST_WINDOW": window, "ORC_TEST_MARKER": str(marker)},
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        deadline = time.monotonic() + 60
        while process.poll() is None and not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not marker.exists():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            pytest.fail(f"never reached {window}: {process.communicate(timeout=10)}")
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        shutil.rmtree(control)


def accept_words(stderr: str) -> list[str]:
    (line,) = [line.strip() for line in stderr.splitlines() if " --accept-changes=plan-" in line]
    words = shlex.split(line)
    return words[words.index("resume"):]


def log(root: Path) -> list[str]:
    return (root / "log.txt").read_text().split()


def records(run_root: Path, kind: str) -> list[dict]:
    return [row for row in fx.rows(run_root) if row["record"] == kind]


def edited(tmp_path: Path) -> tuple[Path, Path, str]:
    """A completed four-step run, `x` inserted before `s2`; (workspace, run root, the printed command's token)."""
    root = serial(tmp_path / "ws")
    run_root = run(root)
    edit(root, "           (s2 ", f"           (x {NEW})\n           (s2 ")
    refused = cli_inprocess(root, "resume", run_root.name)
    assert refused.returncode == 2, refused.stderr
    return root, run_root, accept_words(refused.stderr)[-1].removeprefix("--accept-changes=")


IN_FORCE = {"W1": "old", "W2": "old", "W3": "old", "W4": "new", "W5": "new"}


@pytest.mark.parametrize("window", list(IN_FORCE))
def test_kill_in_each_window_leaves_the_old_program_or_the_new_one(tmp_path, window):
    root, run_root, token = edited(tmp_path)
    header = json.loads((run_root / "run.json").read_text())["program_digest"]
    dispatched = log(root)

    killed(root, window, "resume", run_root.name, f"--accept-changes={token}")

    assert log(root) == dispatched                                    # nothing ran before the record was durable
    in_force = current_digest(run_root, header)
    assert (in_force == header) == (IN_FORCE[window] == "old")
    artifacts = sorted(run_root.glob("closed_program.*.json"))
    assert len(artifacts) == (0 if window == "W1" else 1)
    if IN_FORCE[window] == "new":
        assert artifacts[0].name == f"closed_program.{in_force.removeprefix('sha256:')}.json"
        resumed = cli_inprocess(root, "resume", run_root.name)
        assert resumed.returncode == 0, resumed.stderr
        assert log(root) == [*dispatched, "x", "s2", "s3", "s4"] and len(records(run_root, "rebased")) == 1
        stale = cli_inprocess(root, "resume", run_root.name, f"--accept-changes={token}")
        assert stale.returncode == 2 and stale.stderr.startswith("[resume_preflight_failed] "), stale.stderr
        return
    if window == "W2":                       # reformatted since: same digest, other bytes; the artifact is reused
        kept = artifacts[0].read_bytes()
        source = (root / "pipe.orc").read_text()
        (root / "pipe.orc").write_text(";; reformatted\n" + source.replace("(let* (", "(let*\n      ("))
    again = cli_inprocess(root, "resume", run_root.name)
    assert again.returncode == 2 and again.stderr.startswith("[resume_program_changed] "), again.stderr
    assert accept_words(again.stderr)[-1] == f"--accept-changes={token}"
    done = cli_inprocess(root, *accept_words(again.stderr))
    assert done.returncode == 0, done.stderr
    assert log(root) == [*dispatched, "x", "s2", "s3", "s4"] and len(records(run_root, "rebased")) == 1
    assert (run_root / "memo.jsonl").read_bytes().endswith(b"\n")    # a torn tail (W3) was repaired, not kept
    if window == "W2":
        assert artifacts[0].read_bytes() == kept


def test_failed_sync_exits_2_and_says_the_change_may_be_in_force(tmp_path, monkeypatch):
    root, run_root, token = edited(tmp_path)
    dispatched = log(root)
    real_fsync, failed = os.fsync, []

    def fsync(fd):
        if not failed and os.readlink(f"/proc/self/fd/{fd}").endswith("memo.jsonl"):
            failed.append(fd)
            raise OSError(5, "injected sync failure")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    done = cli_inprocess(root, "resume", run_root.name, f"--accept-changes={token}")
    monkeypatch.setattr(os, "fsync", real_fsync)

    assert done.returncode == 2, done.stderr
    assert done.stderr.startswith("[memo_sync_failed] "), done.stderr
    assert "the accepted change may be in force; nothing was dispatched" in done.stderr
    (report,) = [line.strip() for line in done.stderr.splitlines() if line.startswith("    ") and " report " in line]
    words = shlex.split(report)
    assert cli_inprocess(root, *words[words.index("report"):]).returncode == 0
    assert log(root) == dispatched
    resumed = cli_inprocess(root, "resume", run_root.name)        # the record survived: W5's outcome
    assert resumed.returncode == 0, resumed.stderr
    assert log(root) == [*dispatched, "x", "s2", "s3", "s4"]


def test_kills_under_an_edited_program_reach_the_uninterrupted_value(tmp_path):
    root = serial(tmp_path / "ws")
    (root / "fail-s3").write_text("")
    run_root = run(root, code=1)
    (root / "fail-s3").unlink()
    edit(root, "           (s3 ", f"           (x {cmd('x', 's2')})\n           (s3 ")
    clean = tmp_path / "clean"
    shutil.copytree(root, clean, ignore=shutil.ignore_patterns(".orchestrate", "log.txt"))
    expected = cli_inprocess(clean, "run", "pipe.orc", "--command-boundaries-file", "commands.json")
    assert expected.returncode == 0, expected.stderr
    refused = cli_inprocess(root, "resume", run_root.name)

    killed(root, "commit", *accept_words(refused.stderr))           # after x commits under the edited program
    while len(records(run_root, "committed")) < 5:                   # s1, s2, x, s3, s4: one kill after each commit
        killed(root, "commit", "resume", run_root.name)
    done = cli_inprocess(root, "resume", run_root.name)

    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[-1] == expected.stdout.splitlines()[-1]
    assert log(root) == ["s1", "s2", "s3", "x", "s3", "s4"]           # s1 and s2 kept, each new step once


def test_journal_with_a_record_reduced_without_the_kind_is_memo_inconsistent(tmp_path, monkeypatch):
    """An older build, which knows no `rebased` record: it refuses the run and writes nothing."""
    from orchestrator.workflow.evaluated import memo, memo_reducer
    root, run_root, token = edited(tmp_path)
    assert cli_inprocess(root, "resume", run_root.name, f"--accept-changes={token}").returncode == 0
    before = tree(root)
    older = memo_reducer._RECORDS - {"rebased"}
    monkeypatch.setattr(memo_reducer, "_RECORDS", older)
    monkeypatch.setattr(memo, "_RECORDS", older)
    monkeypatch.setattr(memo_reducer, "_LAST", None, raising=False)

    for words, code in ((("resume", run_root.name), 2), (("invalidate", run_root.name, "workflow:pipe::run / s4"), 2),
                        (("report", "--run-id", run_root.name), 1)):
        done = cli_inprocess(root, *words)
        assert done.returncode == code and "record kind is missing or unknown" in done.stderr + done.stdout, (
            words, done.stderr)
    monkeypatch.undo()                       # the suite's fold guard re-reads the journal with this build's kinds
    after = tree(root)
    assert {name: after[name] for name in before} == before


def test_view_failure_after_the_record_exits_2_and_says_the_change_is_in_force(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated import views
    root, run_root, token = edited(tmp_path)
    dispatched, real = log(root), views.publish_evaluated_view

    def publish(authority, entry, **kwargs):
        if entry.data["record"] == "rebased":
            raise views.ViewPublicationError("injected view failure")
        return real(authority, entry, **kwargs)

    monkeypatch.setattr(views, "publish_evaluated_view", publish)
    done = cli_inprocess(root, "resume", run_root.name, f"--accept-changes={token}")
    monkeypatch.undo()

    assert done.returncode == 2 and "the accepted change is in force; nothing was dispatched" in done.stderr
    assert log(root) == dispatched and len(records(run_root, "rebased")) == 1
    resumed = cli_inprocess(root, "resume", run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert log(root) == [*dispatched, "x", "s2", "s3", "s4"]
