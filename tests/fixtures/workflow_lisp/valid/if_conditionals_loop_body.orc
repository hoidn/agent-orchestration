(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord LoopState
    (ready Bool)
    (report WorkReport))
  (defrecord ImplementationSummary
    (report WorkReport))
  (defworkflow loop-report
    ((state LoopState)
     (fallback_path WorkReport))
    -> ImplementationSummary
    (loop/recur
      :max 2
      :state state
      (fn (current)
        (if current.ready
          (let* ((summary
                   (provider-result providers.execute
                     :prompt prompts.implementation.execute
                     :inputs (current.report fallback_path)
                     :returns ImplementationSummary)))
            (done summary))
          (continue current))))))
