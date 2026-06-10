(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule wcc_ifexpr_tail)
  (export choose-summary)

  (defpath ReportPath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defrecord Summary
    (report ReportPath))

  (defworkflow choose-summary
    ((enabled Bool)
     (approved_report ReportPath)
     (blocked_report ReportPath))
    -> Summary
    (if enabled
      (record Summary :report approved_report)
      (record Summary :report blocked_report))))
