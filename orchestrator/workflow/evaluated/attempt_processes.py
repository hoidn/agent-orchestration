"""Whether any process an attempt of this run started is still alive (Linux `/proc`).

Each external attempt runs with `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` set to its own result locator under
`<run root>/effects/` (`commands.launch_command`, the provider launchers); every descendant inherits it unless
it starts with another environment. The run id makes `/<run id>/effects/` unique to this run. Only same-user
processes with a readable `/proc` entry are looked at.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROC = Path("/proc")
_VARIABLE = b"ORCHESTRATOR_OUTPUT_BUNDLE_PATH="


def run_process_alive(run_id: str) -> bool:
    """True when a live process carries a result locator of this run, or when this platform cannot tell.

    Any attempt counts, not only the failing one: a writer left by an earlier attempt of the same step, or by
    another step, can change a script after this attempt's rehash. A zombie's environment is unreadable.
    """
    if not os.access(_PROC / "self" / "environ", os.R_OK):
        return True
    needle, uid = f"/{run_id}/effects/".encode(), os.getuid()
    # ponytail: one pass over /proc; a process forked during the pass under a recycled lower pid by a parent
    # that exits before the pass reaches it is missed. Scan twice if that window ever matters.
    for entry in os.scandir(_PROC):
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            variables = (_PROC / entry.name / "environ").read_bytes().split(b"\0")
        except OSError:  # exited during the pass, or not readable: outside the check
            continue
        if any(value.startswith(_VARIABLE) and needle in value for value in variables):
            return True
    return False
