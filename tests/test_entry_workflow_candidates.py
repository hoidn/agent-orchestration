"""`entry_workflow_required` names the workflows `--entry-workflow` can select, in declaration order."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

REPO = Path(__file__).parents[1]
MESSAGE = "[entry_workflow_required] `--entry-workflow` is required when the entry module exports multiple workflows"


def module(names: list[str], exports: list[str]) -> str:
    workflows = "".join(f"\n  (defworkflow {name} () -> Int 1)" for name in names)
    return (f'(workflow-lisp (:language "0.1") (:target-dsl "2.39")\n  (defmodule pick) (export {" ".join(exports)})'
            f"{workflows})\n")


def test_compile_names_each_exported_workflow_in_declaration_order(tmp_path: Path) -> None:
    (tmp_path / "pick.orc").write_text(module(["zeta", "alpha"], ["alpha", "zeta"]), encoding="utf-8")

    result = subprocess.run([sys.executable, "-m", "orchestrator", "compile", "pick.orc"], cwd=tmp_path,
                            env={**os.environ, "PYTHONPATH": str(REPO)}, capture_output=True, text=True, check=False)

    lines = result.stderr.splitlines()
    assert (result.returncode, lines[0].endswith(MESSAGE)) == (2, True), result.stderr
    assert "note: workflows, in declaration order: zeta, alpha" in lines[1:]


def test_a_long_list_of_candidates_is_cut_after_twenty(tmp_path: Path) -> None:
    names = [f"w{index}" for index in range(25)]
    source = tmp_path / "pick.orc"
    source.write_text(module(names, names), encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as refused:
        build_closed_program_bundle(FrontendBuildRequest(source_path=source, source_roots=(tmp_path,),
                                                         workspace_root=tmp_path))

    (note,) = refused.value.diagnostics[0].notes
    assert note.endswith(", ".join(names[:20]) + " and 5 more")
