"""Kill a public CLI run right after its first committed effect, for resume tests.

`kill_after_first_commit` launches `python <gate> <args>` in `root`, where the gate wraps
`runtime.append_record` so that the first `committed` record writes its identity to a
marker and pauses the process; the whole process group is then killed. It returns the
committed identity.
"""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest


_COMMIT_GATE = '''\
import os
import signal
import sys
import time
from pathlib import Path

from orchestrator.workflow.evaluated import runtime

append_record = runtime.append_record
marker = Path(os.environ["ORCHESTRATOR_TEST_COMMIT_MARKER"])

def gate(*args, **kwargs):
    entry = append_record(*args, **kwargs)
    record = args[1] if len(args) > 1 else kwargs["record"]
    if record.get("record") == "committed" and not marker.exists():
        marker.parent.mkdir(parents=True, exist_ok=True)
        temporary_marker = marker.with_name(marker.name + ".tmp")
        with temporary_marker.open("w", encoding="utf-8") as stream:
            time.sleep(0.25)  # Widen the marker visibility window for this regression.
            stream.write(record["identity"])
        temporary_marker.replace(marker)
        signal.pause()
    return entry

runtime.append_record = gate
from orchestrator.cli import main
raise SystemExit(main())
'''


def kill_after_first_commit(root: Path, args: list[str], env: dict[str, str]) -> str:
    control = root / ".test-control"
    marker = control / "committed-identity"
    launcher = control / "cli_with_commit_gate.py"
    control.mkdir(parents=True)
    launcher.write_text(_COMMIT_GATE, encoding="utf-8")
    child_env = {**env, "ORCHESTRATOR_TEST_COMMIT_MARKER": str(marker)}
    process = subprocess.Popen(
        [sys.executable, str(launcher), *args], cwd=root, env=child_env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 15
        while process.poll() is None and not marker.is_file() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not marker.is_file():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"CLI did not reach a committed effect: {stdout}\n{stderr}")
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == -signal.SIGKILL, (stdout, stderr)
        return marker.read_text(encoding="utf-8")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
