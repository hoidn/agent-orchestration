"""Public target-2.25 trial SDK and CLI contract tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_ordinary_cli_import_parse_and_dispatch_stay_trial_module_free(
    tmp_path: Path,
) -> None:
    code = r'''
import json
import importlib
import sys

cli_main = importlib.import_module("orchestrator.cli.main")
run_module = importlib.import_module("orchestrator.cli.commands.run")

names = (
    "orchestrator.cli.commands.trial",
    "orchestrator.workflow.trial.sdk",
)
after_import = [name for name in names if name in sys.modules]
cli_main.create_parser().parse_args(["run", "ordinary.orc"])
after_parse = [name for name in names if name in sys.modules]
import orchestrator.cli.commands as commands
commands.run_workflow = lambda _args: run_module.RunWorkflowResult(exit_code=0)
exit_code = cli_main.main(["run", "ordinary.orc"])
after_dispatch = [name for name in names if name in sys.modules]
print(json.dumps({
    "after_import": after_import,
    "after_parse": after_parse,
    "after_dispatch": after_dispatch,
    "exit_code": exit_code,
}))
'''

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "after_import": [],
        "after_parse": [],
        "after_dispatch": [],
        "exit_code": 0,
    }
