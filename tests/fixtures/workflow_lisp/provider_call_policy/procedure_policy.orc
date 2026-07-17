(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defunion ReviewResult
    (APPROVE
      (approved Bool))
    (REVISE
      (reason String)))
  (defproc invoke-provider
    ((model String)
     (effort String))
    -> ReviewResult
    :effects ((uses-provider providers.execute))
    :lowering inline
    (provider-result providers.execute
      :prompt prompts.execute
      :inputs ()
      :model model
      :effort effort
      :timeout-sec 7200
      :returns ReviewResult))
  (defworkflow procedure-policy
    ((model String)
     (effort String))
    -> ReviewResult
    (let* ((initial
             (provider-result providers.execute
               :prompt prompts.execute
               :inputs ()
               :returns ReviewResult)))
      (loop/recur
        :max 1
        :state initial
        (fn (state)
          (match state
            ((APPROVE approved)
             (done state))
            ((REVISE revise)
             (let* ((next (invoke-provider model effort)))
               (continue next)))))))))
