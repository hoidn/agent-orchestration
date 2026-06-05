(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defunion LoopSignal
    (RETRY
      (report WorkReport))
    (READY
      (report WorkReport)))
  (defrecord LoopState
    (report WorkReport))
  (defunion LoopResult
    (COMPLETED
      (status String)
      (report WorkReport))
    (EXHAUSTED
      (reason String)
      (report WorkReport)))
  (defworkflow loop-recur-on-exhausted-non-scalar-override
    ((report_path WorkReport))
    -> LoopResult
    (loop/recur
      :max 1
      :state (record LoopState
               :report report_path)
      :on-exhausted (variant LoopResult EXHAUSTED
                      :reason "max_iterations_reached"
                      :report report_path)
      (fn (state)
        (let* ((signal
                 (provider-result providers.execute
                   :prompt prompts.implementation.execute
                   :inputs (report_path)
                   :returns LoopSignal)))
          (match signal
            ((READY ready)
             (done
               (variant LoopResult COMPLETED
                 :status "completed"
                 :report ready.report)))
            ((RETRY retry)
             (continue state))))))))
