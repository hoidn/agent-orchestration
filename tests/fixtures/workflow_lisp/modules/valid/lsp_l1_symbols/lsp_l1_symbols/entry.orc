(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
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
  (defresource review-state
    :state-type ReviewState
    :backing state-layout)
  (deftransition record-review
    :resource review-state
    :request-type ReviewState
    :result-type ReviewState
    :preconditions ((!= request.status ""))
    :updates ((set-field status request.status))
    :write-set (status)
    :idempotency-fields (status)
    :result (record ReviewState
      :status request.status)
    :audit (record ReviewState
      :status request.status)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defproc default-status
    ()
    -> String
    :effects ()
    :lowering inline
    "ready")
  (defproc normalize-status
    ((status String))
    -> String
    :effects ()
    :lowering inline
    status)
  (defproc render-and-preserve
    ((reports List[Optional[Map[String, ReportPath]]])
     (status String)
     (target ReportPath))
    -> List[Optional[Map[String, ReportPath]]]
    :effects ((writes status-view))
    :lowering inline
    (let* ((rendered
             (materialize-view status-view
               :value (record ReviewState
                        :status status)
               :renderer canonical-json
               :renderer-version 1
               :target target
               :returns ReportPath)))
      reports))
  (defworkflow default-review
    ()
    -> ReviewState
    (loop/recur
      :max 1
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
