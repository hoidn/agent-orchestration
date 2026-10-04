"""Observers around real public CLI calls, shared by E1 and external K4 tests."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


_CONTROL_RUNNER = r"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from orchestrator._common.io_atomic import durable_atomic_write
from orchestrator.workflow.evaluated import run_ref as evaluated_run_ref
from orchestrator.workflow.evaluated import runtime as evaluated_runtime
from orchestrator.workflow.run_ref import runtime as run_ref_runtime

control = Path(os.environ["TASK9G_CONTROL"])
gate = os.environ.get("TASK9G_GATE", "")

def append_log(name, record):
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with (control / name).open("ab", buffering=0) as stream:
        stream.write(payload)
        os.fsync(stream.fileno())

append_log("processes.jsonl", {
    "pid": os.getpid(), "pgid": os.getpgrp(),
    "argv": ["orchestrator", *sys.argv[1:]],
})

def pause_at_marker(record):
    record["runner_pid"] = os.getpid()
    record["runner_pgid"] = os.getpgrp()
    durable_atomic_write(control / "marker.json",
                         json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    while True:
        time.sleep(1)

real_popen = subprocess.Popen
launch_number = 0

def record_popen(*args, **kwargs):
    global launch_number
    process = real_popen(*args, **kwargs)
    command = args[0] if args else kwargs["args"]
    argv = [str(token) for token in command] if not isinstance(command, str) else [command]
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        pgid = None
    append_log("processes.jsonl", {
        "pid": process.pid, "pgid": pgid, "runner_pgid": os.getpgrp(), "argv": argv,
    })
    if "--path-request" in argv:
        launch_number += 1
        request_path = Path(argv[argv.index("--path-request") + 1])
        request_bytes = request_path.read_bytes()
        request = json.loads(request_bytes)
        append_log("launches.jsonl", {
            "number": launch_number,
            "pid": process.pid,
            "pgid": pgid,
            "runner_pgid": os.getpgrp(),
            "argv": argv,
            "request_path": str(request_path),
            "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
            "child_run_id": request["child_run_id"],
            "parent_authority": request["parent_authority"],
        })
    return process

subprocess.Popen = record_popen

real_persist = run_ref_runtime.persist_run_ref_lifecycle_event
pending_count = 0

def record_lifecycle(request, event):
    global pending_count
    acknowledgement = real_persist(request, event)
    if event.stage == "completed_pending_parent_commit":
        pending_count += 1
        append_log("lifecycle.jsonl", {
            "count": pending_count,
            "stage": event.stage,
            "identity": request.parent_identity,
            "parent_attempt": request.parent_attempt,
            "attempt_ordinal": event.attempt_ordinal,
            "visit": event.visit.record,
            "event_digest": event.event_digest,
        })
        if gate == "pending" and pending_count == 2:
            pause_at_marker({
                "gap": gate,
                "identity": request.parent_identity,
                "parent_attempt": request.parent_attempt,
                "attempt_ordinal": event.attempt_ordinal,
                "visit": event.visit.record,
                "event_digest": event.event_digest,
            })
    return acknowledgement

run_ref_runtime.persist_run_ref_lifecycle_event = record_lifecycle

real_append = evaluated_runtime.append_record
run_ref_commits = 0

def record_append(*args, **kwargs):
    global run_ref_commits
    record = args[1] if len(args) > 1 else kwargs["record"]
    entry = real_append(*args, **kwargs)
    if record.get("record") == "committed" and record.get("effect_class") == "run_ref":
        run_ref_commits += 1
        append_log("memo.jsonl", {
            "count": run_ref_commits,
            "identity": record["identity"],
            "attempt": record["attempt"],
            "proof": record["proof"],
        })
        if gate == "memo" and run_ref_commits == 2:
            pause_at_marker({
                "gap": gate,
                "identity": record["identity"],
                "parent_attempt": record["attempt"],
                "attempt_ordinal": record["proof"]["settled_result"]["attempt_ordinal"],
                "visit": record["proof"]["settled_result"]["visit"],
            })
    return entry

evaluated_runtime.append_record = record_append

real_finalize = evaluated_run_ref.finalize_run_ref_parent_commit

def record_finalize(request, *args, **kwargs):
    result = real_finalize(request, *args, **kwargs)
    append_log("finalize.jsonl", {
        "identity": request.parent_identity,
        "parent_attempt": request.parent_attempt,
        "visit": request.visit.record,
    })
    return result

evaluated_run_ref.finalize_run_ref_parent_commit = record_finalize

real_recover = evaluated_run_ref.recover_run_ref_settlement

def record_recover(request, *args, **kwargs):
    result = real_recover(request, *args, **kwargs)
    append_log("reconcile.jsonl", {
        "identity": request.parent_identity,
        "parent_attempt": request.parent_attempt,
        "visit": request.visit.record,
        "reconcile_pending": kwargs["reconcile_pending"],
    })
    return result

evaluated_run_ref.recover_run_ref_settlement = record_recover

from orchestrator.cli import main
raise SystemExit(main())
"""


def _json_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def _assert_no_child_resume(control: Path, child_run_ids: set[str]) -> None:
    calls = [row["argv"] for row in _json_lines(control / "processes.jsonl")]
    assert not [argv for argv in calls if "resume" in argv and any(
        child_id in arg for child_id in child_run_ids for arg in argv
    )]


def _environment(control: Path, gate: str | None) -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[1]
    return {
        **os.environ,
        "PYTHONPATH": str(repo_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TASK9G_CONTROL": str(control),
        "TASK9G_GATE": gate or "",
    }


def _start_cli(parent: Path, control: Path, arguments: list[str], *, gate: str | None = None):
    control.mkdir(parents=True, exist_ok=True)
    runner = control / "cli_with_run_ref_observer.py"
    if not runner.exists():
        runner.write_text(_CONTROL_RUNNER, encoding="utf-8")
    number = len(list(control.glob("stdout-*.log"))) + 1
    stdout_path = control / f"stdout-{number}.log"
    stderr_path = control / f"stderr-{number}.log"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            [sys.executable, str(runner), *arguments],
            cwd=parent,
            env=_environment(control, gate),
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
    pgid = os.getpgid(process.pid)
    assert pgid == process.pid
    return process, pgid, stdout_path, stderr_path


def _output(stdout_path: Path, stderr_path: Path) -> str:
    return (
        stdout_path.read_text(encoding="utf-8", errors="replace")
        + stderr_path.read_text(encoding="utf-8", errors="replace")
    )


def _kill_own_group(process: subprocess.Popen, pgid: int) -> None:
    assert pgid == process.pid
    if process.poll() is None:
        assert os.getpgid(process.pid) == pgid
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def _wait_for_marker(process, stdout_path: Path, stderr_path: Path, control: Path) -> dict:
    marker_path = control / "marker.json"
    deadline = time.monotonic() + 15
    while process.poll() is None and not marker_path.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not marker_path.is_file():
        _kill_own_group(process, process.pid)
        pytest.fail(f"runner missed the causal marker:\n{_output(stdout_path, stderr_path)}")
    marker = json.loads(marker_path.read_bytes())
    assert process.poll() is None, _output(stdout_path, stderr_path)
    assert marker["runner_pid"] == process.pid
    assert marker["runner_pgid"] == process.pid
    return marker


def _run_to_exit(parent: Path, control: Path, arguments: list[str]) -> str:
    process, pgid, stdout_path, stderr_path = _start_cli(parent, control, arguments)
    try:
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _kill_own_group(process, pgid)
            pytest.fail(f"public CLI timed out:\n{_output(stdout_path, stderr_path)}")
        output = _output(stdout_path, stderr_path)
        assert process.returncode == 0, output
        return output
    finally:
        _kill_own_group(process, pgid)
