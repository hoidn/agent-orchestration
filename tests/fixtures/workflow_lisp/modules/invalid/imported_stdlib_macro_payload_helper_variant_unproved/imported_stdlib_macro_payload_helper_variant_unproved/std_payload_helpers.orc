(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_stdlib_macro_payload_helper_variant_unproved/std_payload_helpers)
  (export SelectionPayload
          GapPayload
          SelectionResult
          MacroEvidence
          MacroTerminal
          emit-run-drain-like)
  (defrecord SelectionPayload
    (item-id String)
    (item-state-root String))
  (defrecord GapPayload
    (gap-id String))
  (defunion SelectionResult
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload)))
  (defrecord MacroEvidence
    (selected-id String))
  (defunion MacroTerminal
    (SUCCESS
      (evidence MacroEvidence)))
  (defmacro emit-run-drain-like (name selector)
    (defworkflow name
      ()
      -> MacroTerminal
      (let* ((selection-result
               (selector))
             (evidence
               (record imported_stdlib_macro_payload_helper_variant_unproved/std_payload_helpers/MacroEvidence
                 :selected-id selection-result.selection.item-id)))
        (variant imported_stdlib_macro_payload_helper_variant_unproved/std_payload_helpers/MacroTerminal SUCCESS
          :evidence evidence)))))
