"""Run a Workflow Lisp module `m` with the CLI, beside the stand-in command `c LABEL VALUE`, which logs LABEL
and returns VALUE."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from tests.agent_session_shims import closed_path

REPO = Path(__file__).resolve().parents[1]
U = "(defunion U (A (n Int)) (B (why String)))"
COMMAND = """import os, sys
open("log.txt", "a").write(sys.argv[1] + "\\n")
open(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], "w").write(sys.argv[2])
"""
A_3 = '{"variant":"A","n":3}'


def cli_run(root: Path, run: str, *inputs: str, definitions: tuple[str, ...] = (U,)) -> subprocess.CompletedProcess:
    """`python -m orchestrator run` of workflow `run` of module `m`, beside the stand-in command `c`."""
    forms = "\n  ".join(definitions)
    source = f'(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n  (defmodule m) (export run)\n  {forms}\n  (defworkflow run {run}))\n'
    (root / "m.orc").write_text(source, encoding="utf-8")
    (root / "c.py").write_text(COMMAND, encoding="utf-8")
    (root / "commands.json").write_text(json.dumps({"c": {"stable_command": ["python", "c.py"], "closure": ["c.py"]}}))
    env = {**os.environ, "PATH": closed_path(REPO / "experiments" / "thread_m" / "no_provider"), "PYTHONPATH": str(REPO)}
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", "run", "m.orc", "--entry-workflow", "m::run",
        "--source-root", ".", "--command-boundaries-file", "commands.json",
        *(flag for item in inputs for flag in ("--input", item))], cwd=root, env=env, capture_output=True, text=True)


def command_log(root: Path) -> list[str]:
    return (root / "log.txt").read_text(encoding="utf-8").split() if (root / "log.txt").exists() else []


def run_workflow(root: Path, run: str, *inputs: str, definitions: tuple[str, ...] = (U,)) -> tuple[object, list[str]]:
    """The value the run prints, and the command log."""
    done = cli_run(root, run, *inputs, definitions=definitions)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.splitlines()[-1]), command_log(root)
