from __future__ import annotations

from pathlib import Path

from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.contracts.closed_program.program import ClosedProgram
from tests.workflow_lisp_closed_program_helpers import TARGET, install


def test_context_call_values_preserve_x1_and_x2_after_readback(tmp_path: Path) -> None:
    observed_fields = (
        "(run-id RunId) (run-state Path.state-root) "
        "(run-artifacts Path.artifact-root) (phase Symbol) "
        "(state Path.state-root) (artifacts Path.artifact-root) (payload Int)"
    )
    cases = (
        (
            "omitted",
            "(defworkflow entry ((payload Int)) -> Observed (call leaf :payload payload))",
            {"payload": 5},
            "runtime-x1",
            {
                "run-id": "runtime-x1",
                "run-state": "state/run",
                "run-artifacts": "artifacts/run",
                "phase": "plan-gate-wrapper",
                "state": "state/plan-gate-wrapper",
                "artifacts": "artifacts/plan-gate-wrapper",
                "payload": 5,
            },
        ),
        (
            "explicit",
            "(defworkflow entry ((phase-ctx PhaseCtx) (payload Int)) -> Observed (call leaf :phase-ctx phase-ctx :payload payload))",
            {
                "payload": 5,
                "phase-ctx": {
                    "run": {
                        "run-id": "explicit-run",
                        "state-root": "state/explicit-run",
                        "artifact-root": "artifacts/explicit-run",
                    },
                    "phase-name": "caller-phase",
                    "state-root": "state/caller-phase",
                    "artifact-root": "artifacts/caller-phase",
                }
            },
            "unused-runtime-id",
            {
                "run-id": "explicit-run",
                "run-state": "state/explicit-run",
                "run-artifacts": "artifacts/explicit-run",
                "phase": "caller-phase",
                "state": "state/caller-phase",
                "artifacts": "artifacts/caller-phase",
                "payload": 5,
            },
        ),
    )
    for mode, entry, inputs, run_id, expected in cases:
        root = tmp_path / mode
        source_path = install(
            root,
            f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
              (defmodule context_probe)
              (import std/context :only (RunCtx PhaseCtx))
              (import std/phase :only (with-phase))
              (export entry)
              (defrecord Observed {observed_fields})
              {entry}
              (defworkflow leaf ((phase-ctx PhaseCtx) (payload Int)) -> Observed
                (with-phase phase-ctx plan-gate-wrapper
                  (record Observed
                    :run-id phase-ctx.run.run-id
                    :run-state phase-ctx.run.state-root
                    :run-artifacts phase-ctx.run.artifact-root
                    :phase phase-ctx.phase-name
                    :state phase-ctx.state-root
                    :artifacts phase-ctx.artifact-root
                    :payload payload))))''',
        )
        typed = compile_typed_program(
            source_path,
            entry_workflow="context_probe::entry",
            source_roots=(root,),
            command_boundaries={},
            workspace_root=root,
        )
        source_path.unlink()
        program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())

        result = evaluate_closed_program(program, inputs, run_id=run_id)

        assert result.json_value() == expected
