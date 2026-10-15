"""CF-1a executed check: `:on-exhausted state.current` with `S is-record`.

The exhausted result must carry the state after the final `continue`, also
with two or more iterations. The regression this pins is recorded in
docs/reports/2026-09-28-cf1a-exhaustion-projection-check.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_workflow_lisp_generic_stdlib_composition import _execute_bundle
from tests.workflow_bundle_helpers import bundle_context_dict
from tests.workflow_lisp_command_boundaries import validate_review_findings_v1_binding

PROBE = """import json, os, sys
from pathlib import Path
payload = {"variant": "REVISE", "note": "revised-" + sys.argv[1]}
bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    path = Path(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))
print(json.dumps(payload))
"""

PHASE_PROBE = """import json, os, sys
from pathlib import Path
revision = int(sys.argv[1])
report = Path(f"artifacts/review/review-{revision}.md")
findings = Path(f"artifacts/work/findings-{revision}.json")
report.parent.mkdir(parents=True, exist_ok=True)
findings.parent.mkdir(parents=True, exist_ok=True)
report.write_text(f"review {revision}\\n", encoding="utf-8")
findings.write_text(json.dumps({"items": [{"id": revision}]}), encoding="utf-8")
payload = {
    "variant": "REVISE",
    "review_report": report.as_posix(),
    "findings": {"schema_version": "ReviewFindings.v1", "items_path": findings.as_posix()},
}
bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    path = Path(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
print(json.dumps(payload))
"""

PHASE_FIX = """import json, os, sys
from pathlib import Path
payload = {"revision": int(sys.argv[1]) + 1}
bundle = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
if bundle:
    path = Path(bundle)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
print(json.dumps(payload))
"""

PHASE_SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.32")
  (defmodule phase_review)
  (import std/phase :only (ReviewDecision ReviewFindings ReviewLoopResult ReviewReportPath review-revise-loop-proc))
  (export run-review-demo)
  (defrecord RunContext (name String))
  (defrecord Candidate (revision Int))
  (defrecord ReviewInputs (name String))
  (defproc review-candidate
    ((candidate Candidate) (inputs ReviewInputs))
    -> ReviewDecision
    :effects ((uses-command probe_review))
    :lowering inline
    (command-result probe_review
      :argv ("python" "PROBE_PATH" candidate.revision)
      :returns ReviewDecision))
  (defproc revise-candidate
    ((candidate Candidate) (inputs ReviewInputs) (findings ReviewFindings))
    -> Candidate
    :effects ((uses-command probe_fix))
    :lowering inline
    (command-result probe_fix
      :argv ("python" "FIX_PATH" candidate.revision)
      :returns Candidate))
  (defproc run-review
    ((ctx RunContext) (candidate Candidate) (inputs ReviewInputs)
     (initial_review_report ReviewReportPath) (initial_findings ReviewFindings))
    -> ReviewLoopResult
    :effects ((uses-command probe_review) (uses-command probe_fix) (uses-command validate_review_findings_v1))
    :lowering inline
    (review-revise-loop-proc
      ctx
      candidate
      inputs
      initial_review_report
      initial_findings
      (proc-ref review-candidate)
      (proc-ref revise-candidate)
      3))
  (defworkflow run-review-demo
    ((initial_review_report ReviewReportPath) (initial_findings ReviewFindings))
    -> ReviewLoopResult
    (run-review
      (record RunContext :name "phase")
      (record Candidate :revision 0)
      (record ReviewInputs :name "test")
      initial_review_report
      initial_findings)))
"""


SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.32")
  (defrecord Candidate
    (title String)
    (score Int))
  (defunion Verdict
    (APPROVE)
    (REVISE
      (note String)))
  (defrecord WorkflowOutput
    (title String)
    (score Int))
  (defproc review-candidate
    ((candidate Candidate))
    -> Verdict
    :effects ((uses-command probe_review))
    :lowering inline
    (command-result probe_review
      :argv ("python" "PROBE_PATH" candidate.title)
      :returns Verdict))
  (defproc revise-candidate
    ((candidate Candidate)
     (note String))
    -> Candidate
    :effects ()
    :lowering inline
    (record Candidate
      :title note
      :score (+ candidate.score 1)))
  (defproc improve-generic
    :forall (S)
    ((initial S)
     (review ProcRef[(S) -> Verdict])
     (revise ProcRef[(S String) -> S])
     (max-iterations Int))
    :where ((S is-record))
    -> S
    :effects ()
    :lowering inline
    (loop/recur
      :max max-iterations
      :state (loop-state
               (current S initial))
      :on-exhausted state.current
      (fn (state)
        (match (review state.current)
          ((APPROVE a)
           (done state.current))
          ((REVISE r)
           (continue (loop-state :like state
                       :current (revise state.current r.note))))))))
  (defworkflow improve-status
    ()
    -> WorkflowOutput
    (let* ((result (improve-generic (record Candidate :title "seed" :score 0) (proc-ref review-candidate) (proc-ref revise-candidate) MAX_ITERATIONS)))
      (record WorkflowOutput
        :title result.title
        :score result.score))))
"""


def _run(tmp_path: Path, max_iterations: int) -> dict[str, object]:
    probe = tmp_path / "probe_review.py"
    probe.write_text(PROBE, encoding="utf-8")
    source = tmp_path / "generic_state_exhaustion.orc"
    source.write_text(
        SOURCE.replace("PROBE_PATH", probe.as_posix()).replace(
            "MAX_ITERATIONS", str(max_iterations)
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    result = compile_stage3_module(
        source,
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "probe_review": ExternalToolBinding(
                name="probe_review", stable_command=("python", probe.as_posix())
            )
        },
        validate_shared=True,
        workspace_root=workspace,
        lowering_route=None,
    )
    bundle = result.validated_bundles["improve-status"]
    return _execute_bundle(
        bundle, workflow_path=source, workspace=workspace, run_id="exhaustion"
    )["workflow_outputs"]


def test_generic_record_state_is_projected_after_one_exhausted_iteration(
    tmp_path: Path,
) -> None:
    outputs = _run(tmp_path, max_iterations=1)

    assert (outputs["return__title"], outputs["return__score"]) == ("revised-seed", 1)


@pytest.mark.parametrize("max_iterations", [2, 3])
def test_generic_record_state_exhaustion_returns_final_continue(
    tmp_path: Path, max_iterations: int
) -> None:
    outputs = _run(tmp_path, max_iterations=max_iterations)

    assert (outputs["return__title"], outputs["return__score"]) == (
        "-".join(["revised"] * max_iterations) + "-seed",
        max_iterations,
    )


def test_imported_std_phase_loop_exhaustion_returns_final_review_metadata(
    tmp_path: Path,
) -> None:
    probe = tmp_path / "phase_review.py"
    probe.write_text(PHASE_PROBE, encoding="utf-8")
    fix = tmp_path / "phase_fix.py"
    fix.write_text(PHASE_FIX, encoding="utf-8")
    source = tmp_path / "phase_review.orc"
    source.write_text(
        PHASE_SOURCE.replace("PROBE_PATH", probe.as_posix()).replace(
            "FIX_PATH", fix.as_posix()
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "phase-workspace"
    workspace.mkdir()
    (workspace / "artifacts/review").mkdir(parents=True)
    (workspace / "artifacts/review/seed.md").write_text("seed\n", encoding="utf-8")
    (workspace / "artifacts/work").mkdir(parents=True)
    (workspace / "artifacts/work/seed.json").write_text('{"items": []}\n', encoding="utf-8")

    result = compile_stage3_module(
        source,
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            "probe_review": ExternalToolBinding(
                name="probe_review", stable_command=("python", probe.as_posix())
            ),
            "probe_fix": ExternalToolBinding(
                name="probe_fix", stable_command=("python", fix.as_posix())
            ),
            "validate_review_findings_v1": validate_review_findings_v1_binding(),
        },
        validate_shared=True,
        workspace_root=workspace,
        lowering_route=None,
    )
    bundle = result.validated_bundles["phase_review::run-review-demo"]
    input_specs = {
        name: spec
        for name, spec in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        input_specs,
        {
            "initial_review_report": "artifacts/review/seed.md",
            "initial_findings__schema_version": "ReviewFindings.v1",
            "initial_findings__items_path": "artifacts/work/seed.json",
        },
        workspace,
    )
    state_manager = StateManager(workspace=workspace, run_id="phase-review-exhaustion")
    state_manager.initialize(
        source.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    state = WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert state["status"] == "completed", state
    outputs = state["workflow_outputs"]
    assert outputs["return__variant"] == "EXHAUSTED"
    assert outputs["return__last_review_report"] == "artifacts/review/review-2.md"
    assert outputs["return__findings__items_path"] == "artifacts/work/findings-2.json"
    assert outputs["return__reason"] == "max_iterations_reached"
