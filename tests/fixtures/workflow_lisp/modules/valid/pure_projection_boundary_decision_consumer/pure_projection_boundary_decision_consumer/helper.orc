(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule pure_projection_boundary_decision_consumer/helper)
  (import pure_projection_boundary_decision_consumer/types :only
    (ConsumerPath ConsumerRoute PathDecision SharedDecision))
  (export project-path-decision project-shared-decision)

  (defworkflow project-path-decision
    ((route ConsumerRoute)
     (bundle_path ConsumerPath)
     (reason String))
    -> PathDecision
    (let* ((is-ready
             (= route ConsumerRoute.READY)))
      (if is-ready
        (variant PathDecision READY
          :bundle_path bundle_path)
        (variant PathDecision HOLD
          :reason reason))))

  (defworkflow project-shared-decision
    ((route ConsumerRoute)
     (reason String))
    -> SharedDecision
    (let* ((is-ready
             (= route ConsumerRoute.READY)))
      (if is-ready
        (variant SharedDecision APPROVE
          :reason reason)
        (variant SharedDecision RETRY
          :reason reason)))))
