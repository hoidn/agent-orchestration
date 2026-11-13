"""Run the published Harbor CLI unchanged, except that its 10-second probes wait longer.

Harbor 0.25.0 gives `podman info`, `podman compose up --help` and the rootless probe a
fixed 10 s timeout. On a heavily loaded host `podman info` takes 10-15 s, so the
preflight aborts ("Podman is not responding") and the rootless probe silently answers
False. This wrapper raises exactly those 10 s timeouts to 180 s and changes nothing else.

Usage: <harbor venv>/bin/python -I harbor_patient.py run --path <task> --env podman ...
"""

import asyncio
import subprocess
import sys

_PROBE_TIMEOUT = 10
_PATIENT_TIMEOUT = 180

_run = subprocess.run
_wait_for = asyncio.wait_for


def _patient_run(*args, **kwargs):
    if kwargs.get("timeout") == _PROBE_TIMEOUT:
        kwargs["timeout"] = _PATIENT_TIMEOUT
    return _run(*args, **kwargs)


async def _patient_wait_for(fut, timeout):
    if timeout == _PROBE_TIMEOUT:
        timeout = _PATIENT_TIMEOUT
    return await _wait_for(fut, timeout)


subprocess.run = _patient_run
asyncio.wait_for = _patient_wait_for

from harbor.cli.main import app  # noqa: E402  (patch must precede Harbor's imports)

sys.argv[0] = "harbor"
sys.exit(app())
