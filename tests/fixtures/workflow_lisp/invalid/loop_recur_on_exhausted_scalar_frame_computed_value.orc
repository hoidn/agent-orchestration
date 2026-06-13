(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defrecord LoopState
    (attempt_count Int)
    (exhaustion_reason String))
  (defunion LoopResult
    (COMPLETED
      (attempt_count Int)
      (reason String))
    (EXHAUSTED
      (attempt_count Int)
      (reason String)))
  (defworkflow loop-recur-on-exhausted-scalar-frame-computed-value
    ()
    -> LoopResult
    (loop/recur
      :max 2
      :state (record LoopState
               :attempt_count 0
               :exhaustion_reason "seed")
      :on-exhausted (variant LoopResult EXHAUSTED
                      :attempt_count (+ state.attempt_count 1)
                      :reason state.exhaustion_reason)
      (fn (state)
        (if (= state.attempt_count 99)
          (done
            (variant LoopResult COMPLETED
              :attempt_count state.attempt_count
              :reason state.exhaustion_reason))
          (continue
            (record LoopState
              :attempt_count (+ state.attempt_count 1)
              :exhaustion_reason "max_iterations_reached")))))))
