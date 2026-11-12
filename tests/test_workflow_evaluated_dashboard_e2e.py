"""The dashboard's HTTP handlers follow one real evaluated run through a kill and a resume."""

import json
import os
import signal
import subprocess
import sys
import time

import pytest

from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp
from tests.test_workflow_evaluated_dashboard import _outputs, _timeline
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_resume_kills import _COMMAND_SOURCE, _cli, _env, _run_root


_PROBE = '''import json, os, sys, time
from pathlib import Path
kind = sys.argv[1]
Path("dispatches.jsonl").open("a", encoding="utf-8").write(json.dumps({"kind": kind}) + "\\n")
print("command stdout " + kind, flush=True)
if kind == "second":
    Path("waiting").touch()
    while not Path("release").exists():
        time.sleep(0.02)
value = 5 if kind == "first" else int(sys.argv[2]) + 1
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(value), encoding="utf-8")
'''


def _write_case(workspace):
    workspace.mkdir()
    (workspace / "main.orc").write_text(_COMMAND_SOURCE, encoding="utf-8")
    (workspace / "probe.py").write_text(_PROBE, encoding="utf-8")
    (workspace / "commands.json").write_text(json.dumps({
        name: {"stable_command": ["python", "probe.py"], "closure": ["probe.py"]} for name in ("first", "second")
    }), encoding="utf-8")


def _wait_for(process, marker):
    deadline = time.monotonic() + 15
    while not marker.exists():
        if process.poll() is not None:
            pytest.fail(f"run exited before {marker.name}: {process.communicate()}")
        if time.monotonic() >= deadline:
            pytest.fail(f"run did not reach {marker.name}")
        time.sleep(0.02)


def _read(workspace, run_root):
    """GET the list and the run page; assert the reads left the run tree byte-identical."""
    before = _tree_bytes(run_root)
    app = DashboardApp(RunScanner([workspace]))
    index, page = app.handle("GET", "/runs"), app.handle("GET", f"/runs/w0/{run_root.name}")
    assert index.status == page.status == 200
    assert _tree_bytes(run_root) == before
    rows = {row["name"].rsplit("/ ", 1)[1]: row for row in _timeline(page)}
    return app, index.body.decode(), page, rows


def _list_row(index, run_root):
    return next(line for line in index.splitlines() if f'href="/runs/w0/{run_root.name}"' in line)


def _cursor(page):
    return page.body.decode().split("<h2>Active Cursor</h2>", 1)[1].split("</section>", 1)[0]


def test_dashboard_handlers_follow_real_run_through_kill_and_resume(tmp_path):
    workspace = tmp_path / "workspace"
    _write_case(workspace)
    process = subprocess.Popen(
        [sys.executable, "-m", "orchestrator", "run", "main.orc", "--command-boundaries-file", "commands.json"],
        cwd=workspace, env=_env(workspace), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True)
    try:
        _wait_for(process, workspace / "waiting")
        run_root = _run_root(workspace)
        app, index, page, rows = _read(workspace, run_root)
        assert "<td>running</td>" in _list_row(index, run_root)
        assert (rows["first"]["status"], rows["first"]["attempt"]) == ("completed", 1)
        assert (rows["second"]["status"], rows["second"]["attempt"]) == ("running", 1)
        assert _outputs(page) is None
        stdout_href = next(href for href in rows["first"]["files"] if href.endswith("/stdout.txt"))
        assert "command stdout first" in app.handle("GET", stdout_href).body.decode()

        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)
        _app, index, page, rows = _read(workspace, run_root)
        body = page.body.decode()
        assert "<td>interrupted</td>" in _list_row(index, run_root)
        assert rows["second"]["name"] in _cursor(page)
        assert f"orchestrate resume {run_root.name}" in body
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)

    (workspace / "release").touch()
    resumed = _cli(workspace, ["resume", run_root.name], _env(workspace))
    assert resumed.returncode == 0, resumed.stderr
    _app, index, page, rows = _read(workspace, run_root)
    assert "<td>completed</td>" in _list_row(index, run_root)
    assert _outputs(page) == 6
    assert (rows["second"]["status"], rows["second"]["attempt"]) == ("completed", 2)
    assert rows["second"]["files"] and all("/attempt-2/" in href for href in rows["second"]["files"])
    assert (rows["first"]["status"], rows["first"]["attempt"]) == ("completed", 1)
    dispatches = [json.loads(line)["kind"] for line in (workspace / "dispatches.jsonl").read_text().splitlines()]
    assert dispatches.count("first") == 1
