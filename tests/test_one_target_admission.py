"""One admitted source target (lane D stage 4, Task 4b, ruling R2).

A source at 2.35-2.39 is refused by every public entry point before it publishes a build or a run: an entry with
`workflow_execution_target_retired`, any other module (and an entry read first by an analysis pass: the REPL, the
LSP, the Python frontend) with `target_dsl_unsupported`, and the message names the migration section of the guide
and the release `v0.2.1` that still compiles it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.cli.commands import repl as repl_cli
from orchestrator.workflow_lisp import build
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_executor_retirement_cutoff import PROGRAM, cli

OLDER_TARGETS = ("2.35", "2.39")
MIGRATION = ("v0.2.1", "migrating-from-an-older-target")
PRODUCER = '''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
  (defmodule dep/dep) (export get)
  (defworkflow get () -> Bool true))
'''
CONSUMER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defworkflow run () -> Bool (call dep)))
'''
PYTHON = 'from orchestrator.py import workflow\nTARGET = "{target}"\n@workflow\ndef run() -> bool:\n    return True\n'


def _published(root: Path) -> list[str]:
    """Build and run directories under the workspace (and the run-reference root, when one is used)."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_dir() and p.name in {"build", "runs", "run-ref"} or p.name in {"run.json", "state.json"})


def _refused(text: str, code: str) -> bool:
    return f"[{code}]" in text and all(marker in text for marker in MIGRATION)


def _cli_refusal(root, target, command):
    source = root / "retired.orc"
    source.write_text(PROGRAM.format(target=target))
    argv = {"compile": ["compile", str(source)], "run": ["run", str(source)],
            "dry-run": ["run", str(source), "--dry-run"]}[command]
    result = cli(root, *argv)
    return result.returncode, result.stderr, "workflow_execution_target_retired"


def _typed_import_refusal(root, target, _command):
    (root / "dep").mkdir()
    (root / "dep" / "dep.orc").write_text(PRODUCER.format(target=target))
    (root / "main.orc").write_text(CONSUMER)
    (root / "imports.json").write_text(json.dumps(
        {"dep": {"kind": "compiled", "path": "dep/dep.orc", "entry_workflow": "get"}}))
    result = cli(root, "run", str(root / "main.orc"), "--imported-workflow-bundles-file", str(root / "imports.json"))
    return result.returncode, result.stderr, "target_dsl_unsupported"


def _python_refusal(root, target, _command):
    (root / "workflow.py").write_text(PYTHON.format(target=target))
    result = cli(root, "py", "run", str(root / "workflow.py"), "--entry-workflow", "run")
    return result.returncode, result.stderr, "target_dsl_unsupported"  # the frontend's type pass reads it first


def _in_process_refusal(root, target, command):
    source = root / "retired.orc"
    source.write_text(PROGRAM.format(target=target))
    with pytest.raises(LispFrontendCompileError) as caught:
        if command == "repl-load":
            repl_cli._dispatch(repl_cli.ReplSession(workspace=root, state_dir=None), f":load {source}")
        else:
            build.build_frontend_bundle_in_memory(build.FrontendBuildRequest(
                source_path=source, entry_workflow="run", workspace_root=root))
    (diagnostic,) = caught.value.diagnostics[:1]
    return 2, f"[{diagnostic.code}] {diagnostic.message}", "target_dsl_unsupported"


ENTRY_POINTS = {"compile": _cli_refusal, "run": _cli_refusal, "dry-run": _cli_refusal,
                "typed-import": _typed_import_refusal, "py-run": _python_refusal,
                "repl-load": _in_process_refusal, "lsp-analysis": _in_process_refusal}


@pytest.mark.parametrize("target", OLDER_TARGETS)
@pytest.mark.parametrize("entry_point", sorted(ENTRY_POINTS))
def test_older_target_refuses_at_each_public_entry_point_without_publishing(tmp_path, entry_point, target):
    returncode, text, code = ENTRY_POINTS[entry_point](tmp_path, target, entry_point)

    assert returncode == 2 and _refused(text, code), text
    assert _published(tmp_path) == []


@pytest.mark.parametrize("target", OLDER_TARGETS)
def test_older_target_run_ref_child_refuses_before_a_child_run_exists(tmp_path, target):
    from tests.test_workflow_evaluated_run_ref import _authority, _public_fixture

    parent, source, refs = _public_fixture(tmp_path, child_target=target)
    result = cli(parent, "run", str(source), "--run-ref-root", str(refs))

    assert result.returncode != 0
    _authority_, memo = _authority(parent)
    assert (memo.terminal.data["outcome"], memo.terminal.data["code"]) == ("failed", "trial_program_compile_rejected")
    assert not memo.active_commits
    assert not list(refs.rglob("state.json")) and not list(refs.rglob("run.json"))
