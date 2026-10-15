(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.36")
  (defmodule agent_chess/chess)
  (export run)

  (defpath BoardPath :kind relpath :under "artifacts/agent_chess" :must-exist false)

  (defunion MoveOutcome
    (Moved (position String))
    (Blocked (reason String)))

  (defunion GameOutcome
    (Finished (position String))
    (Blocked (side String) (reason String)))

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
     (black_model String :default "claude-opus-5-5"))
    -> GameOutcome
    (let* ((initial-save (save-board board path)))
      (loop/recur
        :max rounds
        :state (loop-state (round Int 0) (position String board))
        :on-exhausted (variant GameOutcome Finished :position state.position)
        (fn (state)
          (let* ((white
                   (provider-result providers.white
                     :prompt prompts.white
                     :inputs (state.position)
                     :model white_model
                     :effort "low"
                     :timeout-sec 300
                     :returns MoveOutcome)))
            (match white
              ((Blocked w)
                (done (variant GameOutcome Blocked :side "White" :reason w.reason)))
              ((Moved w)
                (let* ((white-save (save-board w.position path))
                       (black
                         (provider-result providers.black
                           :prompt prompts.black
                           :inputs (w.position)
                           :model black_model
                           :effort "low"
                           :timeout-sec 300
                           :returns MoveOutcome)))
                  (match black
                    ((Blocked b)
                      (done (variant GameOutcome Blocked :side "Black" :reason b.reason)))
                    ((Moved b)
                      (let* ((black-save (save-board b.position path)))
                        (if (>= (+ state.round 1) rounds)
                          (done (variant GameOutcome Finished :position b.position))
                          (continue
                            (loop-state :like state
                              :round (+ state.round 1)
                              :position b.position)))))))))))))))
