"""Test-only sources for `tests/test_workflow_lisp_improve_example_e2e.py`.

`LAUNCH_PROBE` stands in for the workspace-owned `scripts/launch_experiment.py`
that the example binds as its `launch_experiment` command. It appends what it
received (as JSON) to `launch_experiment.log` and returns an `ExperimentRun`.

`PANEL_HOOKS` is the substituted reviewer: two sequential reviews (the example's
own `review-proposal` and a statistics reviewer) and an adjudication in which
the stricter verdict wins, so an inner BLOCKED is never downgraded.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MAINTAINED_EXAMPLE = REPO_ROOT / "workflows" / "examples" / "improve_experiment_proposal.orc"
EXAMPLE = REPO_ROOT / "tests/fixtures/workflow_lisp/current_examples/improve_experiment_proposal.orc"
LEGACY_COMMANDS = REPO_ROOT / "tests/fixtures/workflow_lisp/improve_legacy/commands.json"
EXAMPLE_INPUTS = REPO_ROOT / "workflows" / "examples" / "inputs" / "improve_experiment_proposal"
EXAMPLE_PROMPTS = REPO_ROOT / "workflows" / "examples" / "prompts" / "workflows" / "improve_experiment_proposal"

QUESTION = "warmup"


SEED = {"name": "seed", "value": 0}


def _params(*notes: str) -> list[dict]:
    return [SEED, *({"name": note, "value": index} for index, note in enumerate(notes, start=1))]


APPROVED_LAUNCH = {
    "outcome": "approved", "note": "methods:ok:warmup+r", "hypothesis": "warmup+r", "parameters": _params("methods:add-1"),
}


EXHAUSTED_LAUNCH = {
    "outcome": "exhausted", "note": "", "hypothesis": "warmup+r+r+r",
    "parameters": _params("methods:add-1", "methods:add-2", "methods:add-3"),
}


LAUNCH_PROBE = """import argparse, json, os
from pathlib import Path
parser = argparse.ArgumentParser()
for flag in ("--outcome", "--note", "--hypothesis", "--parameters"):
    parser.add_argument(flag, required=True)
args = parser.parse_args()
received = {**vars(args), "parameters": json.loads(args.parameters)}
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(json.dumps(received) + "\\n")
payload = {"status": "launched" if args.outcome == "approved" else "held"}
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(payload), encoding="utf-8")
"""

PANEL_HOOKS = """  (defproc review-statistics
    ((proposal ExperimentProposal) (brief ExperimentBrief))
    -> Decision[ReviewNotes ReviewBlocker]
    :effects ((uses-provider providers.proposal.statistics-review))
    :lowering inline
    (provider-result providers.proposal.statistics-review
      :prompt prompts.proposal.review
      :inputs (brief.question proposal.hypothesis proposal.parameters)
      :returns Decision[ReviewNotes ReviewBlocker]))
  (defproc review-by-panel
    ((proposal ExperimentProposal) (brief ExperimentBrief))
    -> Decision[ReviewNotes ReviewBlocker]
    :effects ((uses-provider providers.proposal.review)
              (uses-provider providers.proposal.statistics-review))
    :lowering inline
    (let* ((methods (review-proposal proposal brief))
           (statistics (review-statistics proposal brief)))
      (match methods
        ((BLOCKED blocked) methods)
        ((REVISE revise)
         (match statistics
           ((BLOCKED blocked) statistics)
           ((REVISE other) methods)
           ((APPROVE approve) methods)))
        ((APPROVE approve) statistics))))
"""

SELECTED_REVIEW = "(proc-ref review-proposal)"
PANEL_REVIEW = "(proc-ref review-by-panel)"


def panel_source(example: str) -> str:
    """The example with the panel added and selected as the `review` hook; nothing else changes."""

    anchor = "  (defproc revise-proposal"
    assert example.count(anchor) == example.count(SELECTED_REVIEW) == 1
    return example.replace(anchor, PANEL_HOOKS + anchor).replace(SELECTED_REVIEW, PANEL_REVIEW)
