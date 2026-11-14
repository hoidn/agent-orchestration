(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
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
  (defworkflow loop-recur-on-exhausted-union
    ((report_path WorkReport))
    -> LoopResult
    (loop/recur ((state (record LoopState
                          :report report_path)))
      :max 1
      :on-exhausted (variant LoopResult EXHAUSTED
                      :reason "max_iterations_reached"
                      :report state.report)
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
           (continue state)))))))
