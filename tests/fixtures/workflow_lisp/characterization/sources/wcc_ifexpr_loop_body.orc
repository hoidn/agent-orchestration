(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule wcc_ifexpr_loop_body)
  (export choose-summary)

  (defpath ReportPath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defrecord Summary
    (report ReportPath))

  (defworkflow choose-summary
    ((enabled Bool)
     (initial Summary))
    -> Summary
    (loop/recur
      :max 2
      :state initial
      (fn (state)
        (if enabled
          (done state)
          (continue state))))))
