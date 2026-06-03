(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule phase_stdlib_resume_or_start_promoted_entry_bootstrap)
  (import library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper
    :as bootstrap
    :only (ResumeInputs PlanGateWrapperSurfaceResult resume-plan-gate-wrapper))
  (export promoted-entry-resume-plan-gate-wrapper)

  (defworkflow promoted-entry-resume-plan-gate-wrapper
    ((inputs bootstrap.ResumeInputs))
    -> bootstrap.PlanGateWrapperSurfaceResult
    (call bootstrap.resume-plan-gate-wrapper
      :inputs inputs)))
