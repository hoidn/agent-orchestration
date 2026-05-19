(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ImplementationSummary
    (report WorkReport))
  (cyclic-workflow looping
    ((report_path WorkReport))
    ImplementationSummary
    (record ImplementationSummary
      :report report_path))
  (defmacro cyclic-workflow (name params return_type body)
    (looping-workflow name params return_type body))
  (defmacro looping-workflow (name params return_type body)
    (cyclic-workflow name params return_type body)))
