(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_stdlib_macro_payload_helper_non_symbol_callee/std_payload_helpers)
  (export SelectionPayload
          SelectionResult
          RenderedSummary
          ConsumerResult
          MacroTerminal
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
  (defunion SelectionResult
    (SELECTED
      (selection SelectionPayload)))
  (defrecord RenderedSummary
    (status String)
    (summary-path SummaryPath))
  (defrecord ConsumerResult
    (selected-id String)
    (summary-status String))
  (defunion MacroTerminal
    (SUCCESS))
  (defproc selection-result-selection-payload
    ((selection-result SelectionResult))
    -> SelectionPayload
    :effects ()
    :lowering inline
    (match selection-result
      ((SELECTED selected)
       selected.selection)))
  (defproc render-selection-summary
    ((selection SelectionPayload))
    -> RenderedSummary
    :effects ()
    :lowering inline
    (record imported_stdlib_macro_payload_helper_non_symbol_callee/std_payload_helpers/RenderedSummary
      :status "SELECTED"
      :summary-path (__generated-relpath-seed__
                      SummaryPath
                      "artifacts/work/imported-stdlib-macro-payload-helper-non-symbol.json"
                      "imported_stdlib_macro_payload_helper_non_symbol_seed")))
  (defmacro emit-run-drain-like (name selector consumer)
    (defworkflow name
      ()
      -> MacroTerminal
      (let* ((selection-result
               (selector))
             (selection-payload
               (imported_stdlib_macro_payload_helper_non_symbol_callee/std_payload_helpers/selection-result-selection-payload selection-result))
             (rendered-summary
               (imported_stdlib_macro_payload_helper_non_symbol_callee/std_payload_helpers/render-selection-summary selection-payload))
             (consumer-result
               (call consumer
                 :selection selection-payload
                 :summary rendered-summary)))
        (variant imported_stdlib_macro_payload_helper_non_symbol_callee/std_payload_helpers/MacroTerminal SUCCESS)))))
