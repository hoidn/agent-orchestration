"""CF-1a executed check: `:on-exhausted state.current` with `S is-record`.

Compile and single-iteration execution pass. With `:max` >= 2 the runtime
exhaustion result carries the state after the penultimate `continue`, dropping
the final one; see docs/reports/2026-09-28-cf1a-exhaustion-projection-check.md
(root cause: `loops.py::_exhaustion_frame_artifacts` recognizes only
`*__continue__state` snapshots while this route persists `*__body__<arm>__state`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_workflow_lisp_generic_stdlib_composition import _execute_bundle

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


@pytest.mark.xfail(
    strict=True,
    reason="runtime exhaustion selector drops the final continue for :max >= 2; "
    "see docs/reports/2026-09-28-cf1a-exhaustion-projection-check.md",
)
def test_generic_record_state_exhaustion_returns_final_continue(tmp_path: Path) -> None:
    outputs = _run(tmp_path, max_iterations=3)

    assert (outputs["return__title"], outputs["return__score"]) == (
        "revised-revised-revised-seed",
        3,
    )
