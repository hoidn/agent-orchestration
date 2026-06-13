(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry)
  (import helper
    :as helper
    :only (FinalResult
           LoopState
           SelectionResult
           select-selection
           draft-gap))
  (export run-carriage)
  (defworkflow run-carriage
    ()
    -> FinalResult
    (loop/recur
      :max 2
      :state (record LoopState
               :attempt 0
               :carried_run_id "seed-run-id")
      (fn (state)
        (match (call helper.select-selection
                 :attempt state.attempt)
          ((GAP gap_case)
           (let* ((gap_decision
                    (call helper.draft-gap
                      :gap gap_case.gap)))
             (continue
               (record LoopState
                 :attempt (+ state.attempt 1)
                 :carried_run_id gap_decision.next_run_id))))
          ((SELECTED selected)
           (done
             (record FinalResult
               :carried_run_id state.carried_run_id
               :selected_id selected.selection.selected_id))))))))
