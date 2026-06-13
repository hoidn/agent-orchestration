(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_stdlib_macro_payload_helper_non_symbol_callee/entry)
  (import imported_stdlib_macro_payload_helper_non_symbol_callee/std_payload_helpers
    :only (SelectionPayload
           SelectionResult
           RenderedSummary
           ConsumerResult
           MacroTerminal
           emit-run-drain-like))
  (export run-drain-like)
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
    (if true consume-selection consume-selection)))
