(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule helper)
  (export GapPayload
          SelectionPayload
          SelectionResult
          GapDecision
          FinalResult
          select-selection
          draft-gap)
  (defrecord GapPayload
    (gap_id String))
  (defrecord SelectionPayload
    (selected_id String))
  (defunion SelectionResult
    (GAP
      (gap GapPayload))
    (SELECTED
      (selection SelectionPayload)))
  (defunion GapDecision
    (CONTINUE
      (remembered SelectionResult))
    (STOP
      (selected_id String)))
  (defrecord FinalResult
    (selected_id String))
  (defproc select-selection
    ((state SelectionResult))
    -> SelectionResult
    :effects ()
    :lowering inline
    state)
  (defproc draft-gap
    ((gap GapPayload))
    -> GapDecision
    :effects ()
    :lowering inline
    (variant helper/GapDecision CONTINUE
      :remembered (variant helper/SelectionResult SELECTED
                    :selection (record helper/SelectionPayload
                                 :selected_id "gap-1-remembered")))))
