(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.36")
  (defmodule agent_chess/chess)
  (export run)

  (defpath BoardPath :kind relpath :under "artifacts/agent_chess" :must-exist false)

  (defproc save-board ((board String) (path BoardPath)) -> Bool
    :effects ((uses-command write-board))
    (command-result write-board
      :argv ("python" "experiments/agent_chess/write_board.py")
      :inputs ((board board) (path path))
      :returns Bool))

  (defworkflow run
    ((board String)
     (path BoardPath)
     (rounds Int :default 100)
     (white_model String :default "gpt-6.1-sol")
     (black_model String :default "claude-fable-5-1"))
    -> String
    (let* ((initial-save (save-board board path)))
      (loop/recur
        :max rounds
        :state (loop-state (round Int 0) (position String board))
        :on-exhausted state.position
        (fn (state)
          (let* ((white-position
                   (provider-result providers.white
                     :prompt prompts.white
                     :inputs (state.position)
                     :model white_model
                     :effort "low"
                     :timeout-sec 300
                     :returns String))
                 (white-save (save-board white-position path))
                 (black-position
                   (provider-result providers.black
                     :prompt prompts.black
                     :inputs (white-position)
                     :model black_model
                     :effort "low"
                     :timeout-sec 300
                     :returns String))
                 (black-save (save-board black-position path)))
            (if (>= (+ state.round 1) rounds)
              (done black-position)
              (continue
                (loop-state :like state
                  :round (+ state.round 1)
                  :position black-position)))))))))
