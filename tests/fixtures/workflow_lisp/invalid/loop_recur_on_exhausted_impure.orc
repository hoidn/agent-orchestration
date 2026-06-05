(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord LoopState
    (status String)
    (report WorkReport)
    (done Bool))
  (defrecord ImplementationSummary
    (status String)
    (report WorkReport))
  (defworkflow loop-recur-on-exhausted-impure
    ((report_path WorkReport))
    -> ImplementationSummary
    (loop/recur
      :max 1
      :state (loop-state
               (status String "pending")
               (report WorkReport report_path)
               (done Bool false))
      :on-exhausted (provider-result providers.execute
                      :prompt prompts.implementation.execute
                      :inputs (report_path)
                      :returns ImplementationSummary)
      (fn (state)
        (if state.done
          (done
            (record ImplementationSummary
              :status state.status
              :report state.report))
          (continue state))))))
