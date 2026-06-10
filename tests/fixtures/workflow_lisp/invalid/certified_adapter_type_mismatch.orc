(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord CompletedResult
    (execution_report WorkReport))
  (defrecord ImplementationSummary
    (report WorkReport))
  (defworkflow normalize-summary
    ((completed CompletedResult)
     (review_report String))
    -> ImplementationSummary
    (command-result normalize_result
      :adapter normalize_result
      :inputs
        ((execution_report completed.execution_report)
         (review_report review_report))
      :returns ImplementationSummary)))
