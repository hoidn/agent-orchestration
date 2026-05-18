(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum BlockerClass
    missing_resource
    roadmap_conflict)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (status String)
    (report WorkReport))
  (defunion ImplementationState
    (COMPLETED
      (execution_report WorkReport))
    (BLOCKED
      (progress_report WorkReport)
      (blocker_class BlockerClass))))
