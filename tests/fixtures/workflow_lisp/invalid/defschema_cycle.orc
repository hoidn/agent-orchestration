(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defschema ReportTargets
    (:include ReviewTargets)
    (execution_report WorkReport))
  (defschema ReviewTargets
    (:include ReportTargets)
    (review_report WorkReport))
  (defrecord ImplementationSummary
    (:include ReportTargets)))
