"""Fixtures for the public artifact handoff tests at 2.35.

The generic run watchdog is installed unchanged apart from its target header and
command closures (`tests.workflow_evaluated_consumer_sources.install`). Its target is
a real evaluated run in a separate workspace, so the copied probe reads evaluated
authority. `SHIM` answers as `codex` and `claude` and logs every request it receives,
including the full prompt; the copied probe and publisher log each execution's argv.
Small single-purpose programs (`small_program`) use the same shim and a command
manifest with explicit closures.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_consumers import EVIDENCE, PROBE, PUBLISHER
from tests.test_workflow_evaluated_invalidate import _cli
from tests.workflow_evaluated_consumer_sources import (
    PROGRAMS, ROOT, STOPPED, checked_run, compile_current, install, install_shims, jsonl, requests,
)


PACKAGE = str(ROOT / "orchestrator")  # imported by the copied probe (evaluated target views)
WATCH = "state/watchdog/watch.json"
WATCH_PART = f"dependency:{WATCH}"
PUBLISHED = "state/watchdog/watchdog-result.json"
REPORT = f"{EVIDENCE}/repair-report.md"
COMPAT = f"{EVIDENCE}/repair-result.json"
TARGET_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule watched_target) (export run)
  (defworkflow run ((divisor Float)) -> Float (/ 1.0 divisor)))
'''
STOP_AFTER_START = r'''import os, sys
from orchestrator.cli import main
from orchestrator.workflow.evaluated import attempts
append = attempts.append_record
def stop(path, record, **kwargs):
    entry = append(path, record, **kwargs)
    if record["record"] == "started" and os.environ["STOP_AFTER_START"] in record["identity"]:
        os._exit(75)
    return entry
attempts.append_record = stop
sys.argv = ["orchestrator", *sys.argv[1:]]
sys.exit(main())
'''


def evaluated_target(root: Path, *, failed: bool) -> str:
    """A real evaluated run in its own workspace, failed (division by zero) or completed; its run id."""
    root.mkdir(parents=True)
    (root / "watched_target.orc").write_text(TARGET_SOURCE, encoding="utf-8")
    result = _run_cli(root, "watched_target.orc", "--input", f"divisor={0 if failed else 2}")
    assert result.returncode == (1 if failed else 0), result.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return run_root.name


def install_watchdog(root: Path, target_workspace: Path, target: str, provider: str) -> list[str]:
    """The 2.35 watchdog copy; the probe's closure also declares the `orchestrator` package it imports."""
    inputs = {"target_run_id": target, "target_workspace": str(target_workspace),
              "state_root": "state/watchdog", "evidence_root": EVIDENCE,
              "repair_result_target_path": COMPAT, "repair_provider": provider}
    frontend = install(root, PROGRAMS["watchdog"], inputs, current=True)
    manifest = root / "manifests" / "commands.json"
    boundaries = json.loads(manifest.read_text(encoding="utf-8"))
    boundaries["probe_orchestrator_run"]["closure"].append(PACKAGE)
    manifest.write_text(json.dumps(boundaries), encoding="utf-8")
    return frontend


def watchdog_workspace(tmp_path: Path, monkeypatch, plan: dict, *, failed: bool = True,
                       provider: str = "codex") -> tuple[Path, list[str], str]:
    """Shims, an evaluated target and the compiled 2.35 watchdog; its root, frontend and the target run id."""
    install_shims(tmp_path / "bin", monkeypatch, plan)
    target = evaluated_target(tmp_path / "target", failed=failed)
    root = tmp_path / "watchdog"
    frontend = install_watchdog(root, tmp_path / "target", target, provider)
    compile_current(root, frontend)
    return root, frontend, target


def run_argv(frontend: list[str]) -> list[str]:
    return ["run", *frontend, "--input-file", "inputs.json"]


def stop_after_start(root: Path, argv: list[str], marker: str) -> None:
    """Run `orchestrator <argv>` and stop right after the first `started` whose identity has `marker`."""
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "STOP_AFTER_START": marker}
    stopped = subprocess.run([sys.executable, "-c", STOP_AFTER_START, *argv], cwd=root, env=env,
                             capture_output=True, text=True, check=False)
    assert stopped.returncode == STOPPED, stopped.stderr


def counts(root: Path) -> tuple[int, int, int]:
    """Probe executions, provider requests and publisher executions so far."""
    return (len(jsonl(root / f"{PROBE}.runs.jsonl")), len(requests(root)),
            len(jsonl(root / f"{PUBLISHER}.runs.jsonl")))


def dependency_block(prompt: str, path: str) -> bytes:
    """The complete bytes the prompt carries for the prepended dependency `path`."""
    raw = prompt.encode("utf-8")
    (match,) = re.finditer(rb"=== File: " + re.escape(path.encode()) + rb" \((\d+)/(\d+) bytes\) ===\n", raw)
    assert match.group(1) == match.group(2)
    return raw[match.end():match.end() + int(match.group(1))]


def attempt_files(authority, data: dict) -> dict[str, bytes]:
    """Bytes of every file in the attempt directory of a started or committed record."""
    attempt = authority.run_root / Path(data["result_path"]).parent
    return {path.name: path.read_bytes() for path in sorted(attempt.iterdir())}


def rows(root: Path, record: str, marker: str = "") -> list[dict]:
    """Memo records of one kind whose identity contains `marker`, in journal order."""
    _, snapshot = checked_run(root)
    return [entry.data for entry in snapshot.entries
            if entry.data["record"] == record and marker in entry.data.get("identity", "")]


def field_type(authority, record_type: str, field: str) -> dict:
    """The checked type of one field of a record type in the run's closed program."""
    fields = authority.program.tree["types"][f"generic_run_watchdog/watchdog::{record_type}"]["fields"]
    (row,) = [row for row in fields if row["name"] == field]
    return row["type"]


# Small single-purpose programs ------------------------------------------------------

HEAD = '(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule main) (export run)\n'
LOGGED = '''import json, os, sys
from pathlib import Path
with open(Path(sys.argv[0]).stem + ".log", "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
'''
PRODUCE = LOGGED + '''Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/note.md").write_text("NOTE v1\\n", encoding="utf-8")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("artifacts/note.md"), encoding="utf-8")
'''
LATER = LOGGED + '''note = Path("artifacts/note.md").read_text(encoding="utf-8")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(note), encoding="utf-8")
'''


def small_program(root: Path, monkeypatch, source: str, plan: dict) -> list[str]:
    """Write and compile `main.orc` with shims, a prompt asset and two logged commands; its frontend."""
    install_shims(root.parent / f"{root.name}-bin", monkeypatch, plan)
    root.mkdir(parents=True)
    files = {"main.orc": HEAD + source, "prompt.md": "Review the request.\n", "produce.py": PRODUCE,
             "later.py": LATER, "providers.json": json.dumps({"providers.review": "codex"}),
             "prompts.json": json.dumps({"prompts.base": {"asset_file": "prompt.md"}}),
             "commands.json": json.dumps({name: {"kind": "external_tool", "stable_command": ["python", f"{name}.py"],
                                                 "closure": [f"{name}.py"]} for name in ("produce", "later")})}
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    frontend = ["main.orc", "--entry-workflow", "main::run", "--source-root", ".",
                "--provider-externs-file", "providers.json", "--prompt-externs-file", "prompts.json",
                "--command-boundaries-file", "commands.json"]
    compiled = _cli(root, "compile", *frontend)
    assert compiled.returncode == 0, compiled.stderr
    return frontend
