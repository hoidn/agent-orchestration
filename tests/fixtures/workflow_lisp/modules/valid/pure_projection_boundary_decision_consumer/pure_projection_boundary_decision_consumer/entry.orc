(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule pure_projection_boundary_decision_consumer/entry)
  (import pure_projection_boundary_decision_consumer/helper :only
    (project-path-decision project-shared-decision))
  (import pure_projection_boundary_decision_consumer/types :only
    (ConsumerPath ConsumerRoute PathDecision SharedDecision SummaryResult))
  (export run)

  (defproc project-selected-path
    ((decision PathDecision)
     (fallback_path ConsumerPath))
    -> ConsumerPath
    :effects ()
    :lowering inline
    (match decision
      ((READY ready)
       ready.bundle_path)
      ((HOLD hold)
       fallback_path)))

  (defproc project-path-detail
    ((decision PathDecision))
    -> String
    :effects ()
    :lowering inline
    (match decision
      ((READY ready)
       "READY")
      ((HOLD hold)
       hold.reason)))

  (defproc project-shared-detail
    ((decision SharedDecision))
    -> String
    :effects ()
    :lowering inline
    (match decision
      ((APPROVE approve)
       approve.reason)
      ((RETRY retry)
       retry.reason)))

  (defworkflow run
    ((bundle_path ConsumerPath)
     (reason String))
    -> SummaryResult
    (let* ((computed_reason
             (string/concat reason "-computed"))
           (path_decision
             (call project-path-decision
               :route ConsumerRoute.READY
               :bundle_path bundle_path
               :reason computed_reason))
           (shared_decision
             (call project-shared-decision
               :route ConsumerRoute.HOLD
               :reason computed_reason))
           (selected_path
             (project-selected-path path_decision bundle_path))
           (path_detail
             (project-path-detail path_decision))
           (shared_detail
             (project-shared-detail shared_decision)))
      (record SummaryResult
        :selected_path selected_path
        :path_detail path_detail
        :shared_detail shared_detail))))
