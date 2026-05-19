(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ImplementationSummary
    (report WorkReport))
  (bad-splice summary
    ((report_path WorkReport))
    ImplementationSummary
    (record ImplementationSummary
      :report report_path))
  (defmacro bad-splice (name params return_type body)
    (defworkflow (splice name)
      params
      -> return_type
      body)))
