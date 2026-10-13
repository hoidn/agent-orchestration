"""`workflows/examples/design_review_execute.orc`: the file-based variant of the README example.

The example documents its own compile command in its header comment. This
check runs that exact command through the public CLI and asserts the closed
program it builds has one effect site per provider call in the source: draft, review, revise, execute.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "workflows" / "examples" / "design_review_execute.orc"


def test_documented_command_compiles_the_example_to_a_closed_program() -> None:
    header = EXAMPLE.read_text(encoding="utf-8").split("python -m orchestrator compile", 1)[1].split("\n\n", 1)[0]
    documented = "python -m orchestrator compile " + " ".join(line.strip(" ;\\") for line in header.splitlines())
    argv = shlex.split(documented)

    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, *argv[1:]], cwd=REPO_ROOT, env=env,
                            capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    built = json.loads(result.stdout)
    assert (built["entry_workflow"], built["sites"]) == ("design_review_execute::run", 4)
