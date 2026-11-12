(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule lsp_l1_symbols/entry)
  (defenum ReviewDecision
    APPROVE
    REVISE)
  (defpath ReportPath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)
  (defschema CommonFields
    (status String))
  (defrecord ReviewState
    (status String))
  (defunion ReviewOutcome
    (DONE
      (status String)))
  (defproc default-status
    ()
    -> String
    :effects ()
    "ready")
  (defproc normalize-status
    ((status String))
    -> String
    :effects ()
    status)
  (defproc render-and-preserve
    ((reports List[Optional[Map[String, ReportPath]]])
     (status String)
     (target ReportPath))
    -> List[Optional[Map[String, ReportPath]]]
    :effects ((writes status-view))
    reports)
  (defworkflow default-review
    ()
    -> ReviewState
    (loop/recur
      :max 1 :on-exhausted state
      :state (record ReviewState
               :status "ready")
      (fn (state)
        (done state))))
  (defworkflow review
    ((status String))
    -> String
    (normalize-status status))
  (defworkflow review-many
    ((primary String)
     (secondary String)
     (fallback String))
    -> String
    (normalize-status primary)))
