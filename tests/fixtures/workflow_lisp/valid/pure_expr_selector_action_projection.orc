(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule pure_expr_selector_action_projection)
  (export orchestrate)
  (defrecord SelectorSummary
    (status String)
    (ready Bool))
  (defworkflow orchestrate
    ((approved Bool)
     (status String))
    -> SelectorSummary
    (record-update
      (record SelectorSummary
        :status status
        :ready false)
      :ready (or approved (= status "READY")))))
