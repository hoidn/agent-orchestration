"""Run an orchestrator CLI command inside the test process, for setup steps only.

Saves the interpreter start and import cost of `python -m orchestrator`; a step that is
itself under test (kills, exit statuses of the process, terminal output) keeps the subprocess.
"""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from orchestrator.cli import main


def run_cli_in_process(root: Path, argv: list[str], env: dict[str, str] | None = None):
    """Return an object with `returncode`, `stdout` and `stderr` like `subprocess.CompletedProcess`.

    `env`, when given, replaces os.environ for the call (as a subprocess env would); the
    working directory is `root`. Both are restored afterwards.
    """
    cwd, out, err = os.getcwd(), io.StringIO(), io.StringIO()
    os.chdir(root)
    try:
        with (mock.patch.dict(os.environ, env, clear=True) if env is not None else contextlib.nullcontext(),
              contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
            returncode = main(argv)
    finally:
        os.chdir(cwd)
    return SimpleNamespace(returncode=returncode, stdout=out.getvalue(), stderr=err.getvalue())
