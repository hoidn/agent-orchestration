(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_stdlib_macro_payload_helper_bad_field/entry)
  (import imported_stdlib_macro_payload_helper_bad_field/std_payload_helpers
    :only (SelectionPayload
           SelectionResult
           RenderedSummary
           MacroTerminal
           emit-run-drain-like))
  (export run-drain-like)
  (defrecord ConsumerResult
    (selected-id String)
    (summary-status String))
  (defproc load-selected-selection-result
    ()
    -> SelectionResult
    :effects ()
    :lowering private-workflow
    (variant SelectionResult SELECTED
      :selection (record SelectionPayload
                   :item-id "selected-1"
                   :item-state-root "state/selected-1.json")))
  (defworkflow consume-selection
    ((selection SelectionPayload)
     (summary RenderedSummary))
    -> ConsumerResult
    (record ConsumerResult
      :selected-id selection.item-id
      :summary-status summary.status))
  (emit-run-drain-like run-drain-like
    load-selected-selection-result
    consume-selection))
