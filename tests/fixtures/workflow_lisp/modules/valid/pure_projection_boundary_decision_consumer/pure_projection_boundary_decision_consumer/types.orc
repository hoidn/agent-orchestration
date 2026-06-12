(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule pure_projection_boundary_decision_consumer/types)
  (export ConsumerPath ConsumerRoute PathDecision SharedDecision SummaryResult)

  (defpath ConsumerPath
    :kind relpath
    :under "state"
    :must-exist false)

  (defenum ConsumerRoute
    READY
    HOLD)

  (defunion PathDecision
    (READY
      (bundle_path ConsumerPath))
    (HOLD
      (reason String)))

  (defunion SharedDecision
    (APPROVE
      (reason String))
    (RETRY
      (reason String)))

  (defrecord SummaryResult
    (selected_path ConsumerPath)
    (path_detail String)
    (shared_detail String)))
