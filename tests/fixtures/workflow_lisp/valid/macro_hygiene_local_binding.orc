(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ImplementationSummary
    (report WorkReport))
  (defworkflow hygienic_summary
    ((outer_report WorkReport)
     (inner_report WorkReport))
    -> ImplementationSummary
    (let* ((tmp outer_report))
      (preserve-caller-tmp inner_report
        (record ImplementationSummary
          :report tmp))))
  (defmacro preserve-caller-tmp (value body)
    (let* ((tmp value)
           (macro_tmp tmp))
      body)))
