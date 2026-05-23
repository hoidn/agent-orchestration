(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum BlockerClass
    missing_resource
    user_decision_required)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defschema ReportTargets
    (execution_report WorkReport))
  (defschema ReviewTargets
    (status String)
    (:include ReportTargets)
    (review_report WorkReport))
  (defrecord ImplementationSummary
    (:include ReviewTargets))
  (defunion ImplementationState
    (COMPLETED
      (:include ReportTargets))
    (BLOCKED
      (:include ReviewTargets)
      (blocker_class BlockerClass))))
