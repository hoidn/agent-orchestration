(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord LoopState
    (report WorkReport))
  (defrecord WorkflowOutput
    (report WorkReport))
  (defunion ReviewGate
    (APPROVE
      (report WorkReport))
    (REVISE
      (report WorkReport)))
  (defworkflow entry
    ((report WorkReport))
    -> WorkflowOutput
    (loop/recur ((state (loop-state
                          (report WorkReport report))))
      :max 2
      :on-exhausted (record WorkflowOutput
                      :report state.report)
      (let* ((gate
               (provider-result providers.execute
                 :prompt prompts.implementation.execute
                 :inputs (state.report)
                 :returns ReviewGate)))
        (match gate
          ((APPROVE approved)
           (done
             (record WorkflowOutput
               :report approved.report)))
          ((REVISE revised)
           (continue
             (loop-state :like state
               :report revised.report))))))))
