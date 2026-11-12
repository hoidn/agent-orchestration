"""Run the public CLI in-process for test setup steps that are not the behavior under test."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from orchestrator.cli.main import main


def cli_inprocess(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run `python -m orchestrator <arguments>` from `root` inside this interpreter."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.chdir(root), patch.object(sys, "argv", ["orchestrator", *arguments]), \
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        returncode = main(list(arguments))
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
