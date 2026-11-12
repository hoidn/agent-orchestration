"""Run the public CLI in-process for test setup steps that are not the behavior under test."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from orchestrator.cli.main import main

_REPO = Path(__file__).resolve().parents[1]


def cli_inprocess(root: Path, *arguments: str, env: dict[str, str] | None = None
                  ) -> subprocess.CompletedProcess[str]:
    """Run `python -m orchestrator <arguments>` from `root` inside this interpreter.

    `env`, when given, replaces os.environ for the call, as a subprocess env would; otherwise the
    call sees os.environ plus the `PYTHONPATH`/`PYTHONDONTWRITEBYTECODE` the subprocess helpers set,
    so any child the step spawns imports this checkout. Error log records go to `stderr`, since
    under pytest `logging.basicConfig` in the run command installs no handler.
    """
    stdout, stderr = io.StringIO(), io.StringIO()
    handler = logging.StreamHandler(stderr)
    handler.setLevel(logging.ERROR)
    environment = env if env is not None else {"PYTHONPATH": str(_REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    logging.getLogger().addHandler(handler)
    try:
        with contextlib.chdir(root), patch.object(sys, "argv", ["orchestrator", *arguments]), \
                patch.dict(os.environ, environment, clear=env is not None), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            returncode = main(list(arguments))
    finally:
        logging.getLogger().removeHandler(handler)
    return subprocess.CompletedProcess(list(arguments), returncode, stdout.getvalue(), stderr.getvalue())


def compile_public_inprocess(files: dict[str, Path]) -> None:
    """In-process equivalent of `compile_public` (same flags, same recorded outputs)."""
    arguments = ["compile", str(files["source"]), "--source-root", str(files["source_root"]),
                 "--provider-externs-file", str(files["providers"]),
                 "--prompt-externs-file", str(files["prompts"]),
                 "--command-boundaries-file", str(files["commands"])]
    if "imports" in files:
        arguments += ["--imported-workflow-bundles-file", str(files["imports"])]
    result = cli_inprocess(files["workspace"], *arguments)
    workspace = files["workspace"]
    (workspace / "compile.stdout").write_text(result.stdout)
    (workspace / "compile.stderr").write_text(result.stderr)
    (workspace / "compile.argv.json").write_text(json.dumps(result.args))
    assert result.returncode == 0, result.stderr
