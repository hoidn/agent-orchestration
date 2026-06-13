(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_stdlib_macro_payload_helper_signature_mismatch/std_payload_helpers)
  (export SelectionPayload
          GapPayload
          SelectionResult
          MacroEvidence
          MacroTerminal
          selection-result-gap-payload
          selection-result-selection-payload
          emit-run-drain-like)
  (defrecord SelectionPayload
    (item-id String)
    (item-state-root String))
  (defrecord GapPayload
    (gap-id String))
  (defunion SelectionResult
    (EMPTY)
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload)))
  (defrecord MacroEvidence
    (gap-id String))
  (defunion MacroTerminal
    (SUCCESS
      (evidence MacroEvidence)))
  (defproc selection-result-gap-payload
    ((selection-result SelectionResult))
    -> GapPayload
    :effects ()
    :lowering inline
    (match selection-result
      ((EMPTY empty)
       (record imported_stdlib_macro_payload_helper_signature_mismatch/std_payload_helpers/GapPayload
         :gap-id ""))
      ((GAP gap-case)
       gap-case.gap)
      ((SELECTED selected)
       (record imported_stdlib_macro_payload_helper_signature_mismatch/std_payload_helpers/GapPayload
         :gap-id ""))))
  (defproc selection-result-selection-payload
    ((selection-result SelectionResult))
    -> SelectionPayload
    :effects ()
    :lowering inline
    (match selection-result
      ((EMPTY empty)
       (record imported_stdlib_macro_payload_helper_signature_mismatch/std_payload_helpers/SelectionPayload
         :item-id ""
         :item-state-root "state/none"))
      ((GAP gap-case)
       (record imported_stdlib_macro_payload_helper_signature_mismatch/std_payload_helpers/SelectionPayload
         :item-id ""
         :item-state-root "state/none"))
      ((SELECTED selected)
       selected.selection)))
  (defmacro emit-run-drain-like (name selector consumer)
    (defworkflow name
      ()
      -> MacroTerminal
      (let* ((selection-result
               (selector))
             (gap-payload
               (imported_stdlib_macro_payload_helper_signature_mismatch/std_payload_helpers/selection-result-gap-payload selection-result))
             (selection-payload
               (imported_stdlib_macro_payload_helper_signature_mismatch/std_payload_helpers/selection-result-selection-payload selection-result))
             (consumer-result
               (consumer gap-payload))
             (evidence
               (record imported_stdlib_macro_payload_helper_signature_mismatch/std_payload_helpers/MacroEvidence
                 :gap-id gap-payload.gap-id)))
        (variant imported_stdlib_macro_payload_helper_signature_mismatch/std_payload_helpers/MacroTerminal SUCCESS
          :evidence evidence)))))
