"""External kills of the public invalidate command reduce to none or all of the suffix."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from orchestrator.workflow.evaluated.memo import memo_writer_lock
from tests.test_workflow_evaluated_invalidate import _cli, _fixture, _memo, _tree_bytes
from tests.workflow_evaluated_run_ref_helpers import _kill_own_group, _output, _wait_for_marker


NAMES = ("prefix", "writer", "reader", "later")

PROGRAM = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule invalidate_public) (export run)
  (defworkflow run () -> Int
    (let* ((prefix (command-result prefix :argv ("python" "prefix.py") :returns Int))
           (writer (command-result writer :argv ("python" "writer.py") :returns Int))
           (reader (command-result reader :argv ("python" "reader.py") :returns Int))
           (later (command-result later :argv ("python" "later.py") :returns Int)))
      reader)))
'''

LATER = (
    'from pathlib import Path\nimport os\n'
    'Path("dispatches.txt").open("a", encoding="utf-8").write("later\\n")\n'
    'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("7", encoding="utf-8")\n'
)

_GATE = r'''
import json, os, signal
from pathlib import Path

import orchestrator.cli.commands.invalidate as command
import orchestrator.workflow.evaluated.memo as memo

WINDOW = os.environ["INVALIDATE_WINDOW"]
CONTROL = Path(os.environ["INVALIDATE_CONTROL"])
JOURNAL = os.path.realpath(os.environ["INVALIDATE_JOURNAL"])
real_append, real_run, real_write, real_fsync = memo.append_record, command.invalidate_run, os.write, os.fsync


def pause(**facts):
    temporary = CONTROL / "marker.tmp"
    temporary.write_text(json.dumps({
        "window": WINDOW, "runner_pid": os.getpid(), "runner_pgid": os.getpgid(0),
        "journal_size": os.path.getsize(JOURNAL), **facts}), encoding="utf-8")
    os.replace(temporary, CONTROL / "marker.json")
    signal.pause()


def is_journal(fd):
    try:
        return os.readlink(f"/proc/self/fd/{fd}") == JOURNAL
    except OSError:
        return False


def journal_ends_with_range():
    with open(JOURNAL, "rb") as stream:
        raw = stream.read()
    return raw.endswith(b"\n") and json.loads(raw.splitlines()[-1]).get("record") == "invalidated"


def append_record(path, record, **kwargs):
    if WINDOW == "before-append" and record.get("record") == "invalidated":
        pause(record=record)
    return real_append(path, record, **kwargs)


def write(fd, data):
    if WINDOW == "torn-short-write" and is_journal(fd) and b'"record":"invalidated"' in bytes(data):
        written = real_write(fd, bytes(data)[: len(data) // 2])
        pause(written=written, intended=len(data))
    return real_write(fd, data)


def fsync(fd):
    if not (is_journal(fd) and journal_ends_with_range()):
        return real_fsync(fd)
    if WINDOW == "before-fsync":
        pause()
    if WINDOW == "fsync-error":
        raise OSError(5, "injected fsync failure")
    real_fsync(fd)
    if WINDOW == "after-fsync":
        pause()


def invalidate_run(*args, **kwargs):
    record = real_run(*args, **kwargs)
    if WINDOW == "lost-ack":
        pause(record=record)
    return record


memo.append_record, command.invalidate_run = append_record, invalidate_run
os.write, os.fsync = write, fsync
from orchestrator.cli import main
raise SystemExit(main())
'''

# Whether the killed command already left one complete range line in the journal.
_CANCELS = {"before-append": False, "torn-short-write": False, "before-fsync": True,
            "after-fsync": True, "lost-ack": True}

CELLS = [
    ("before-append", "sigkill"),
    ("torn-short-write", "sigkill"),
    ("before-fsync", "sigkill"),
    ("before-fsync", "unsynced-line-lost"),
    ("after-fsync", "sigkill"),
    ("lost-ack", "sigkill"),
]


def _completed(root: Path, value: int) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    source, boundaries = _fixture(root, value)
    source.write_text(PROGRAM, encoding="utf-8")
    (root / "later.py").write_text(LATER, encoding="utf-8")
    boundaries.write_text(json.dumps({
        name: {"stable_command": ["python", f"{name}.py"], "closure": [f"{name}.py"]} for name in NAMES
    }), encoding="utf-8")
    result = _cli(root, "run", str(source), "--command-boundaries-file", str(boundaries))
    assert result.returncode == 0, result.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return run_root


@pytest.fixture(scope="module")
def fresh_value(tmp_path_factory):
    root = tmp_path_factory.mktemp("fresh") / "ws"
    _rows, snapshot = _memo(_completed(root, 21))
    assert (root / "handoff.txt").read_bytes() == b"21"
    return snapshot.terminal.data["value"]


def _baseline(root: Path) -> dict:
    """Completed P, A (writes handoff.txt), B (reads it by name) and L; then A's script changes."""
    run_root = _completed(root, 20)
    _rows, snapshot = _memo(run_root)
    commits = [entry for entry in snapshot.entries if entry.data["record"] == "committed"]
    assert [entry.data["value"] for entry in commits] == [1, 20, 20, 7]
    assert [entry.data["depends_on"] for entry in commits] == [[], [], [], []]
    writer = root / "writer.py"
    writer.write_text(writer.read_text(encoding="utf-8").replace('"20"', '"21"'), encoding="utf-8")
    return {
        "root": root, "run_root": run_root, "journal": run_root / "memo.jsonl", "commits": commits,
        "identities": [entry.data["identity"] for entry in commits],
        "memo": (run_root / "memo.jsonl").read_bytes(), "tree": _tree_bytes(root / ".orchestrate"),
        "attempts": {path: path.read_bytes() for path in run_root.glob("effects/*/attempt-1/*")},
        "dispatches": (root / "dispatches.txt").read_text(encoding="utf-8").splitlines(),
    }


def _start_gate(case: dict, window: str):
    control = case["root"].parent / "control"
    control.mkdir(exist_ok=True)
    runner = control / "invalidate_gate.py"
    runner.write_text(_GATE, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]), "PYTHONDONTWRITEBYTECODE": "1",
           "INVALIDATE_WINDOW": window, "INVALIDATE_CONTROL": str(control),
           "INVALIDATE_JOURNAL": str(case["journal"])}
    stdout_path, stderr_path = control / f"stdout-{window}.log", control / f"stderr-{window}.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            [sys.executable, str(runner), "invalidate", case["run_root"].name, case["identities"][1]],
            cwd=case["root"], env=env, stdout=stdout, stderr=stderr, start_new_session=True,
        )
    assert os.getpgid(process.pid) == process.pid
    return process, control, stdout_path, stderr_path


def _kill_invalidate(case: dict, window: str) -> dict:
    process, control, stdout_path, stderr_path = _start_gate(case, window)
    try:
        marker = _wait_for_marker(process, stdout_path, stderr_path, control)
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        assert process.returncode == -signal.SIGKILL, _output(stdout_path, stderr_path)
    finally:
        _kill_own_group(process, process.pid)
    assert marker["window"] == window
    return {**marker, "stdout": stdout_path.read_bytes()}


def _range_line(case: dict) -> bytes:
    journal = case["journal"].read_bytes()
    assert journal.startswith(case["memo"])
    line = journal[len(case["memo"]):]
    assert line.endswith(b"\n") and line.count(b"\n") == 1
    row = json.loads(line)
    assert row["record"] == "invalidated" and row["from_commit"] == case["commits"][1].offset
    return line


def _view_unchanged(case: dict) -> None:
    after = _tree_bytes(case["root"] / ".orchestrate", omit_memo=case["journal"])
    memo_key = case["journal"].relative_to(case["root"] / ".orchestrate").as_posix()
    assert after == {key: node for key, node in case["tree"].items() if key != memo_key}


def _killed_before_append(case: dict, marker: dict) -> None:
    assert marker["journal_size"] == len(case["memo"])
    assert _tree_bytes(case["root"] / ".orchestrate") == case["tree"]


def _killed_in_torn_line(case: dict, marker: dict) -> None:
    journal = case["journal"].read_bytes()
    assert 0 < marker["written"] < marker["intended"]
    assert journal.startswith(case["memo"]) and not journal.endswith(b"\n")
    assert marker["journal_size"] == len(journal) == len(case["memo"]) + marker["written"]
    _view_unchanged(case)


def _killed_before_view(case: dict, marker: dict) -> None:
    assert marker["journal_size"] == len(case["memo"]) + len(_range_line(case))
    _view_unchanged(case)


def _killed_before_acknowledgment(case: dict, marker: dict) -> None:
    line = _range_line(case)
    assert marker["journal_size"] == len(case["memo"]) + len(line)
    assert marker["record"] == json.loads(line)
    state = json.loads((case["run_root"] / "state.json").read_bytes())
    assert state["memo_offset"] == len(case["memo"]) + len(line)


_KILLED = {"before-append": _killed_before_append, "torn-short-write": _killed_in_torn_line,
           "before-fsync": _killed_before_view, "after-fsync": _killed_before_view,
           "lost-ack": _killed_before_acknowledgment}


def _assert_killed_state(case: dict, window: str, marker: dict) -> None:
    assert marker["stdout"] == b"", "a killed invalidate never acknowledges"
    _KILLED[window](case, marker)


def _lose_unsynced_line(case: dict, marker: dict) -> None:
    """Durable image of the before-fsync window: the one unsynchronized append disappears."""
    with case["journal"].open("r+b") as stream:
        stream.truncate(len(case["memo"]))
    assert marker["journal_size"] > len(case["memo"])
    assert case["journal"].read_bytes() == case["memo"]


def _assert_none_or_all(case: dict, canceled: bool) -> None:
    _rows, snapshot = _memo(case["run_root"])
    first, *suffix = case["identities"]
    assert set(snapshot.active_commits) == ({first} if canceled else {first, *suffix})
    ranges = [entry.data for entry in snapshot.entries if entry.data["record"] == "invalidated"]
    assert [row["from_commit"] for row in ranges] == ([case["commits"][1].offset] if canceled else [])


def _recover(case: dict, canceled: bool) -> None:
    root, run_id, identity = case["root"], case["run_root"].name, case["identities"][1]
    if not canceled:
        result = _cli(root, "invalidate", run_id, identity)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == json.loads(_range_line(case))
        _assert_none_or_all(case, True)
    before = _tree_bytes(root / ".orchestrate")
    repeat = _cli(root, "invalidate", run_id, identity)
    assert repeat.returncode == 2 and "invalidate_not_committed" in repeat.stderr
    assert _tree_bytes(root / ".orchestrate") == before


def _assert_resumed(case: dict, fresh_value: int) -> None:
    root = case["root"]
    result = _cli(root, "resume", case["run_root"].name)
    assert result.returncode == 0, result.stderr
    _rows, snapshot = _memo(case["run_root"])
    assert snapshot.terminal.data["value"] == fresh_value == 21
    assert (root / "handoff.txt").read_bytes() == b"21"
    dispatches = (root / "dispatches.txt").read_text(encoding="utf-8").splitlines()
    assert dispatches == case["dispatches"] + ["writer", "reader", "later"]
    (range_entry,) = [entry for entry in snapshot.entries if entry.data["record"] == "invalidated"]
    active = snapshot.active_commits
    first, *suffix = case["identities"]
    assert active[first].offset == case["commits"][0].offset and active[first].data["attempt"] == 1
    assert all(active[name].data["attempt"] == 2 and active[name].offset > range_entry.offset for name in suffix)
    assert {path: path.read_bytes() for path in case["attempts"]} == case["attempts"]


@pytest.mark.parametrize(("window", "image"), CELLS, ids=[f"{window}-{image}" for window, image in CELLS])
def test_public_invalidation_external_window_is_atomic(tmp_path, window, image, fresh_value):
    case = _baseline(tmp_path / "ws")
    marker = _kill_invalidate(case, window)
    _assert_killed_state(case, window, marker)
    if image == "unsynced-line-lost":
        _lose_unsynced_line(case, marker)
    canceled = _CANCELS[window] and image == "sigkill"
    _assert_none_or_all(case, canceled)
    _recover(case, canceled)
    _assert_resumed(case, fresh_value)


def test_public_invalidation_visible_fsync_failure_keeps_one_range(tmp_path, fresh_value):
    case = _baseline(tmp_path / "ws")
    process, _control, stdout_path, stderr_path = _start_gate(case, "fsync-error")
    try:
        process.wait(timeout=60)
    finally:
        _kill_own_group(process, process.pid)
    assert process.returncode == 2, _output(stdout_path, stderr_path)
    assert "memo_sync_failed" in stderr_path.read_text(encoding="utf-8")
    assert stdout_path.read_bytes() == b""
    _range_line(case)
    _assert_none_or_all(case, True)
    _recover(case, True)
    _assert_resumed(case, fresh_value)


def _tear_and_stale(run_root: Path) -> None:
    with (run_root / "memo.jsonl").open("ab") as stream:
        stream.write(b'{"record":"invalid')
    (run_root / "state.json").write_text('{"status":"stale"}', encoding="utf-8")


def test_public_invalidation_refuses_readonly_while_writer_lock_is_held(tmp_path):
    case = _baseline(tmp_path / "ws")
    _tear_and_stale(case["run_root"])
    before = _tree_bytes(case["root"])
    with memo_writer_lock(case["run_root"]):
        result = _cli(case["root"], "invalidate", case["run_root"].name, case["identities"][1])
    assert result.returncode == 2 and "memo_busy" in result.stderr
    assert _tree_bytes(case["root"]) == before


@pytest.mark.parametrize("position", ["first", "middle", "last"])
def test_public_invalidation_refuses_coordinator_anywhere_with_torn_tail(tmp_path, position):
    from tests.test_workflow_evaluated_cli import _run_cli
    from tests.test_workflow_evaluated_command_template_scopes import _write_boundaries, _write_probe
    from tests.test_workflow_evaluated_run_ref import _authority, _public_fixture
    command = '(command-result emit :argv ("python" "probe.py") :returns Int)'

    def body(call):
        before = f"(before {command})" if position != "first" else ""
        after = f"(after {command})" if position != "last" else ""
        return f"(let* ({before} (child {call}) {after}) child.value)"

    parent, source, refs = _public_fixture(tmp_path, body=body)
    _write_probe(parent)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs),
                      "--command-boundaries-file", str(_write_boundaries(parent)))
    assert result.returncode == 0, result.stderr
    authority, memo = _authority(parent)
    commits = list(memo.active_commits.values())
    classes = [row.data["effect_class"] for row in commits]
    assert classes == {"first": ["run_ref", "command"], "middle": ["command", "run_ref", "command"],
                       "last": ["command", "run_ref"]}[position]
    coordinator = commits[classes.index("run_ref")]
    _tear_and_stale(authority.run_root)
    before = _tree_bytes(parent), _tree_bytes(refs)
    for anchor in dict.fromkeys(row.data["identity"] for row in (commits[0], coordinator)):
        refused = _cli(parent, "invalidate", authority.run_root.name, anchor)
        assert refused.returncode == 2 and "invalidate_coordinator_committed" in refused.stderr
        assert (_tree_bytes(parent), _tree_bytes(refs)) == before
