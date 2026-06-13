(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_stdlib_macro_payload_helper_composition/std_payload_helpers)
  (export SummaryPath
          SelectionPayload
          GapPayload
          SelectionResult
          SummaryValue
          RenderedSummary
          MacroEvidence
          MacroTerminal
          selection-result-gap-payload
          selection-result-selection-payload
          render-selection-summary
          emit-run-drain-like)
  (defpath SummaryPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
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
  (defrecord SummaryValue
    (selected-id String))
  (defrecord RenderedSummary
    (status String)
    (summary-path SummaryPath))
  (defrecord MacroEvidence
    (gap-id String)
    (call-selected-id String)
    (call-summary-status String))
  (defunion MacroTerminal
    (SUCCESS
      (selected-id String)
      (summary-path SummaryPath)
      (gap-id String)
      (call-selected-id String)
      (call-summary-status String)))
  (defproc selection-result-gap-payload
    ((selection-result SelectionResult))
    -> GapPayload
    :effects ()
    :lowering inline
    (match selection-result
      ((EMPTY empty)
       (record imported_stdlib_macro_payload_helper_composition/std_payload_helpers/GapPayload
         :gap-id ""))
      ((GAP gap-case)
       gap-case.gap)
      ((SELECTED selected)
       (record imported_stdlib_macro_payload_helper_composition/std_payload_helpers/GapPayload
         :gap-id ""))))
  (defproc selection-result-selection-payload
    ((selection-result SelectionResult))
    -> SelectionPayload
    :effects ()
    :lowering inline
    (match selection-result
      ((EMPTY empty)
       (record imported_stdlib_macro_payload_helper_composition/std_payload_helpers/SelectionPayload
         :item-id ""
         :item-state-root "state/none"))
      ((GAP gap-case)
       (record imported_stdlib_macro_payload_helper_composition/std_payload_helpers/SelectionPayload
         :item-id ""
         :item-state-root "state/none"))
      ((SELECTED selected)
       selected.selection)))
  (defproc render-selection-summary
    ((selection SelectionPayload))
    -> RenderedSummary
    :effects ((writes rendered-selection-summary))
    :lowering inline
    (let* ((summary-path
             (__generated-relpath-seed__
               SummaryPath
               "artifacts/work/imported-stdlib-macro-payload-helper-summary.json"
               "imported_stdlib_macro_payload_helper_summary_seed"))
           (rendered-path
             (materialize-view rendered-selection-summary
               :value (record imported_stdlib_macro_payload_helper_composition/std_payload_helpers/SummaryValue
                        :selected-id selection.item-id)
               :renderer canonical-json
               :renderer-version 1
               :target summary-path
               :returns SummaryPath)))
      (record imported_stdlib_macro_payload_helper_composition/std_payload_helpers/RenderedSummary
        :status "SELECTED"
        :summary-path rendered-path)))
  (defmacro emit-run-drain-like (name selector consumer)
    (defworkflow name
      ()
      -> MacroTerminal
      (let* ((selection-result
               (selector))
             (gap-payload
               (imported_stdlib_macro_payload_helper_composition/std_payload_helpers/selection-result-gap-payload selection-result))
             (selection-payload
               (imported_stdlib_macro_payload_helper_composition/std_payload_helpers/selection-result-selection-payload selection-result))
             (rendered-summary
               (imported_stdlib_macro_payload_helper_composition/std_payload_helpers/render-selection-summary selection-payload))
             (consumer-result
               (call consumer
                 :selection selection-payload
                 :summary rendered-summary))
             (evidence
               (record imported_stdlib_macro_payload_helper_composition/std_payload_helpers/MacroEvidence
                 :gap-id gap-payload.gap-id
                 :call-selected-id consumer-result.selected-id
                 :call-summary-status consumer-result.summary-status)))
        (variant imported_stdlib_macro_payload_helper_composition/std_payload_helpers/MacroTerminal SUCCESS
          :selected-id selection-payload.item-id
          :summary-path rendered-summary.summary-path
          :gap-id evidence.gap-id
          :call-selected-id evidence.call-selected-id
          :call-summary-status evidence.call-summary-status)))))
