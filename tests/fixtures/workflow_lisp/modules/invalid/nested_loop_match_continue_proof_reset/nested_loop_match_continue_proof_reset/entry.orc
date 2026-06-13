(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry)
  (import helper
    :only (FinalResult
           GapPayload
           SelectionResult
           select-selection
           draft-gap))
  (export run-proof-reset)
  (defworkflow run-proof-reset
    ()
    -> FinalResult
    (loop/recur
      :max 2
      :state (variant SelectionResult GAP
               :gap (record GapPayload
                      :gap_id "seed-gap"))
      (fn (state)
        (match (select-selection state)
          ((GAP gap_case)
           (match (draft-gap gap_case.gap)
             ((CONTINUE continued)
              (continue continued.remembered))
             ((STOP stopped)
              (done
                (record FinalResult
                  :selected_id stopped.selected_id)))))
          ((SELECTED selected)
           (done
             (record FinalResult
               :selected_id state.selection.selected_id))))))))
