"""A CLI start that validates no schema does not pay for importing jsonschema."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import orchestrator

_REPO_ROOT = Path(orchestrator.__file__).parents[1]

_COMMAND_WORKFLOW = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule entry)
  (export run)
  (defworkflow run () -> String
    (command-result probe
      :argv ("python" "probe.py")
      :returns String)))
"""


def _jsonschema_loaded_after(code: str, cwd: Path) -> bool:
    probe = f"import sys\n{code}\nprint('jsonschema' in sys.modules)\n"
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(_REPO_ROOT)},
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip().splitlines()[-1] == "True"


def test_cli_help_does_not_import_jsonschema(tmp_path):
    assert not _jsonschema_loaded_after("import orchestrator.cli.main", tmp_path)


def test_compiling_a_command_workflow_does_not_import_jsonschema(tmp_path):
    (tmp_path / "entry.orc").write_text(_COMMAND_WORKFLOW)
    (tmp_path / "probe.py").write_text("print('unused during compilation')\n")
    (tmp_path / "commands.json").write_text(json.dumps({"probe": {
        "kind": "external_tool", "stable_command": ["python", "probe.py"], "closure": ["probe.py"],
    }}))
    code = (
        "from orchestrator.cli.main import main\n"
        "assert main(['compile', 'entry.orc', '--command-boundaries-file', 'commands.json']) == 0"
    )
    assert not _jsonschema_loaded_after(code, tmp_path)
