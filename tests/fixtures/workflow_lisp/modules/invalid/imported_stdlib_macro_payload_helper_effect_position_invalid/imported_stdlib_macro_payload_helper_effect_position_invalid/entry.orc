(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_stdlib_macro_payload_helper_effect_position_invalid/entry)
  (import imported_stdlib_macro_payload_helper_effect_position_invalid/std_payload_helpers
    :only (SelectionPayload
           SelectionResult
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
  (emit-run-drain-like run-drain-like
    load-selected-selection-result))
