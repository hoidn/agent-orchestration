(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule minimal_caller_review_revise_loop)
  (import std/phase :only (ReviewDecision ReviewFindings ReviewFindingsJsonPath ReviewLoopResult ReviewReportPath review-revise-loop-proc))
  (defrecord MinimalCompleted)
  (defrecord MinimalInputs)
  (defproc review-minimal
    ((completed MinimalCompleted)
     (inputs MinimalInputs))
    -> ReviewDecision
    :effects ((uses-command produce_review_decision))
    (command-result produce_review_decision
      :argv ("python" "scripts/produce_review_decision.py")
      :returns ReviewDecision))
  (defproc fix-minimal
    ((completed MinimalCompleted)
     (inputs MinimalInputs)
     (findings ReviewFindings))
    -> MinimalCompleted
    :effects ()
    completed)
  (defworkflow minimal-review-revise-loop
    ((completed MinimalCompleted)
     (inputs MinimalInputs))
    -> ReviewLoopResult
    (review-revise-loop-proc
      completed
      completed
      inputs
      (__generated-relpath-seed__
        ReviewReportPath
        "artifacts/review/minimal-initial-review-report.md"
        "minimal_review_revise_loop_initial_report")
      (record ReviewFindings
        :schema_version "ReviewFindings.v1"
        :items_path (__generated-relpath-seed__
                      ReviewFindingsJsonPath
                      "artifacts/work/minimal-initial-findings.json"
                      "minimal_review_revise_loop_initial_findings"))
      (proc-ref review-minimal)
      (proc-ref fix-minimal)
      1)))
