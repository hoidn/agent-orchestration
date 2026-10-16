"""End-to-end acceptance for target-2.24 ``run-ref`` execution."""

from __future__ import annotations

from pathlib import Path

import pytest


from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


def test_current_run_ref_inside_loop_recur_retains_child_value_and_effect(tmp_path: Path) -> None:
    workspace = tmp_path / "loop-refusal"
    workspace.mkdir()
    source_path = workspace / "controller.orc"
    source_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
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

    result = compile_stage3_module(source_path, entry_workflow="orchestrate", workspace_root=workspace)
    typed = result.typed_program.workflows["controller::orchestrate"]
    assert typed.typed_body.type_ref.name == "Bool"
    from orchestrator.workflow_lisp.effects import RunsRefEffect
    assert any(isinstance(effect, RunsRefEffect) for effect in typed.effect_summary.transitive_effects)

from orchestrator.workflow_lisp.compiler import compile_stage3_module
