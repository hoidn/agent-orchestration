(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defschema ReportTargets
    (report WorkReport))
  (defrecord ImplementationSummary
    (:include ReportTargets)
    (report WorkReport)))
