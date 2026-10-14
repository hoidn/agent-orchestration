"""Runtime X3 value parity and valid/refusing hidden PhaseCtx defaults."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import (
    EvaluatedValueError,
    coerce_evaluated_value,
)
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.contracts.closed_program.program import ClosedProgram
from tests.test_workflow_lisp_closed_program_elaboration import _GENERIC_PHASE_TARGET_SOURCE
from tests.workflow_lisp_closed_program_helpers import TARGET, build, install


# Source of test_compile_stage3_module_maps_phase_targets_by_name_not_position;
# only the target header is parameterized. Keep progress before execution.
_FIXED_PHASE_TARGET_SOURCE = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule phase_targets_swapped)
  (import std/phase :only (with-phase))
  (defenum BlockerClass
    missing_resource)
  (defenum ImplementationStateTag
    COMPLETED
    BLOCKED)
  (defpath DesignDocPath
    :kind relpath
    :under "docs/design"
    :must-exist true)
  (defpath PlanDocPath
    :kind relpath
    :under "docs/plans"
    :must-exist true)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath WorkReportTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defpath ImplementationStateBundlePath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defrecord ImplementationAttemptInputs
    (design DesignDocPath)
    (plan PlanDocPath))
  (defrecord ImplementationAttemptPhaseCtx
    (implementation_state_bundle_path ImplementationStateBundlePath)
    (execution_report_target WorkReportTarget)
    (progress_report_target WorkReportTarget))
  (defunion ImplementationAttempt
    (COMPLETED
      (implementation_state ImplementationStateTag)
      (execution_report_path WorkReport))
    (BLOCKED
      (implementation_state ImplementationStateTag)
      (progress_report_path WorkReport)
      (blocker_class BlockerClass)))
  (defrecord ImplementationAttemptSurfaceResult
    (implementation_state ImplementationStateTag)
    (implementation_state_bundle_path ImplementationStateBundlePath))
  (defworkflow run-implementation-attempt
    ((phase-ctx ImplementationAttemptPhaseCtx)
     (inputs ImplementationAttemptInputs))
    -> ImplementationAttemptSurfaceResult
    (with-phase phase-ctx implementation
      (let* ((attempt
               (provider-result providers.execute
                 :prompt prompts.implementation.execute
                 :inputs (inputs.design
                          inputs.plan
                          (phase-target progress-report)
                          (phase-target execution-report))
                 :returns ImplementationAttempt)))
        (match attempt
          ((COMPLETED completed)
           (record ImplementationAttemptSurfaceResult
             :implementation_state completed.implementation_state
             :implementation_state_bundle_path
               phase-ctx.implementation_state_bundle_path))
          ((BLOCKED blocked)
           (record ImplementationAttemptSurfaceResult
             :implementation_state blocked.implementation_state
             :implementation_state_bundle_path
               phase-ctx.implementation_state_bundle_path)))))))'''


def _write_phase_target_inputs(tmp_path, inputs, context):
    for relative in (*inputs.values(), context["execution_report_target"]):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence\n", encoding="utf-8")


def test_fixed_phase_target_values_follow_named_order_after_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = {
        "implementation_state_bundle_path": "artifacts/work/state.json",
        "execution_report_target": "artifacts/work/runtime-execution-report.md",
        "progress_report_target": "artifacts/work/runtime-progress-report.md",
    }
    inputs = {"design": "docs/design/design.md", "plan": "docs/plans/plan.md"}
    payload = {
        "variant": "COMPLETED",
        "implementation_state": "COMPLETED",
        "execution_report_path": context["execution_report_target"],
    }
    _write_phase_target_inputs(tmp_path, inputs, context)
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Return the supplied execution report target.\n", encoding="utf-8")
    configuration = {
        "provider_externs": {"providers.execute": "codex"},
        "prompt_externs": {"prompts.implementation.execute": "prompt.md"},
        "workspace_root": tmp_path,
    }
    source_path = install(tmp_path, _FIXED_PHASE_TARGET_SOURCE.replace("TARGET", TARGET))
    typed = compile_typed_program(
        source_path,
        entry_workflow="phase_targets_swapped::run-implementation-attempt",
        source_roots=(tmp_path,), command_boundaries={}, **configuration,
    )
    source_path.unlink()
    prompt_path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())
    new_targets = []

    def perform(node, operands, identity, _owner, _reader):
        assert node["class"] == "provider"
        new_targets.extend(value.json_value() for value in operands[-2:])
        return coerce_evaluated_value(payload, node["result"], dependencies={identity})

    result = evaluate_closed_program(
        program, {"phase-ctx": context, "inputs": inputs}, effect_handler=perform,
    )
    assert new_targets == [
        context["progress_report_target"], context["execution_report_target"],
    ]
    expected = {
        "implementation_state": "COMPLETED",
        "implementation_state_bundle_path": context["implementation_state_bundle_path"],
    }
    assert result.json_value() == expected



@pytest.mark.parametrize("phase", ["work", "implementation"])
def test_hidden_generic_phase_target_default_respects_result_refinement(
    tmp_path: Path, phase: str,
) -> None:
    source = _GENERIC_PHASE_TARGET_SOURCE.replace(
        "with-phase ctx implementation", f"with-phase ctx {phase}",
    )
    compiled = build(tmp_path, source, boundaries={}, providers={}, prompts={})
    (tmp_path / "cp" / "closed_elaboration.orc").unlink()
    program = ClosedProgram.from_artifact(compiled.artifact())
    assert program.tree["params"] == []
    if phase == "implementation":
        with pytest.raises(EvaluatedValueError) as excinfo:
            evaluate_closed_program(program, {}, run_id="x3-hidden")
        assert excinfo.value.code == "path_join_under_escape"
    else:
        result = evaluate_closed_program(program, {}, run_id="x3-hidden")
        assert result.json_value() == "artifacts/work/work/execution-report.md"
        assert result.descriptor["under"] == "artifacts/work"
