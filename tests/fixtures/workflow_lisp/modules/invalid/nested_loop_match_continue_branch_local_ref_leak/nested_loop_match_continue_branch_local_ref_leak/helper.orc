(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule helper)
  (export GapPayload
          SelectionPayload
          SelectionResult
          GapDecision
          LoopState
          FinalResult
          select-selection
          draft-gap)
  (defrecord GapPayload
    (gap_id String))
  (defrecord SelectionPayload
    (selected_id String))
  (defunion SelectionResult
    (GAP
      (gap helper/GapPayload))
    (SELECTED
      (selection helper/SelectionPayload)))
  (defrecord GapDecision
    (next_run_id String))
  (defrecord LoopState
    (attempt Int))
  (defrecord FinalResult
    (carried_run_id String)
    (selected_id String))
  (defworkflow select-selection
    ((attempt Int))
    -> SelectionResult
    (if (< attempt 1)
      (variant helper/SelectionResult GAP
        :gap (record helper/GapPayload
               :gap_id "gap-1"))
      (variant helper/SelectionResult SELECTED
        :selection (record helper/SelectionPayload
                     :selected_id "selected-2"))))
  (defworkflow draft-gap
    ((gap helper/GapPayload))
    -> GapDecision
    (record GapDecision
      :next_run_id "gap-1-carried")))
