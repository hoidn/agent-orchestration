"""End-to-end acceptance for target-2.24 ``run-ref`` execution."""

from __future__ import annotations

from pathlib import Path

import pytest


from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


def test_target_224_rejects_run_ref_inside_loop_recur(tmp_path: Path) -> None:
    workspace = tmp_path / "loop-refusal"
    workspace.mkdir()
    source_path = workspace / "controller.orc"
    source_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule controller)
  (export orchestrate)
  (defworkflow child () -> Bool
    true)
  (defworkflow orchestrate () -> Bool
    (loop/recur :max 1 :state false
      (fn (state)
        (let* ((attempt
                 (run-ref
                   :source (:repo "file:///candidate"
                            :commit "0000000000000000000000000000000000000000")
                   :program (:bundle child)
                   :inputs ()
                   :policy (:setup ()))))
          (done attempt.value))))))
""",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(source_path, entry_workflow="orchestrate", workspace_root=workspace)

    assert excinfo.value.diagnostics[0].code == "run_ref_placement_invalid"

from orchestrator.workflow_lisp.compiler import compile_stage3_module
