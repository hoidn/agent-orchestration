(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule imported_stdlib_macro_payload_helper_effect_position_invalid/std_payload_helpers)
  (export SummaryPath
          SelectionPayload
          SelectionResult
          MacroTerminal
          selection-result-selection-payload
          render-selection-summary-path
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
  (defunion MacroTerminal
    (SUCCESS
      (summary-path SummaryPath)))
  (defproc selection-result-selection-payload
    ((selection-result SelectionResult))
    -> SelectionPayload
    :effects ()
    :lowering inline
    (match selection-result
      ((SELECTED selected)
       selected.selection)))
  (defproc render-selection-summary-path
    ((selection SelectionPayload))
    -> SummaryPath
    :effects ((uses-command run_checks))
    :lowering inline
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" selection.item-id)
      :returns SummaryPath))
  (defmacro emit-run-drain-like (name selector)
    (defworkflow name
      ()
      -> MacroTerminal
      (let* ((selection-result
               (selector))
             (selection-payload
               (imported_stdlib_macro_payload_helper_effect_position_invalid/std_payload_helpers/selection-result-selection-payload selection-result)))
        (variant imported_stdlib_macro_payload_helper_effect_position_invalid/std_payload_helpers/MacroTerminal SUCCESS
          :summary-path (imported_stdlib_macro_payload_helper_effect_position_invalid/std_payload_helpers/render-selection-summary-path selection-payload))))))
