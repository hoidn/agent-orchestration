"""Whether any process a host command attempt started is still alive (Linux `/proc`).

Each command attempt runs with `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` set to its own result locator
(`commands.launch_command`), whose run id and attempt directory make it unique; every descendant inherits it
unless it scrubs its environment. Only same-user processes are readable, and only they are looked at.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROC = Path("/proc")
_VARIABLE = b"ORCHESTRATOR_OUTPUT_BUNDLE_PATH="


def attempt_process_alive(run_id: str, result_path: str) -> bool:
    """True when a live process carries the attempt's locator, or when this platform cannot tell (no `/proc`).

    `result_path` is the run-root-relative `effects/<digest>/attempt-<n>/result.json`; the variable's value is that
    path seen from the workspace, so it ends with `<run id>/<result_path>`. A zombie has an empty environment.
    """
    if not os.access(_PROC / "self" / "environ", os.R_OK):
        return True
    suffix, uid = f"/{run_id}/{result_path}".encode(), os.getuid()
    # ponytail: one pass over /proc; a process forked during the pass under a recycled lower pid by a parent
    # that exits before the pass reaches it is missed. Scan twice if that window ever matters.
    for entry in os.scandir(_PROC):
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            variables = (_PROC / entry.name / "environ").read_bytes().split(b"\0")
        except OSError:  # exited during the pass, or not readable: not a process of this attempt
            continue
        if any(value.startswith(_VARIABLE) and value.endswith(suffix) for value in variables):
            return True
    return False
