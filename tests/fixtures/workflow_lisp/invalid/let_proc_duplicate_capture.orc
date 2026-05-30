(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord WorkflowInput
    (report WorkReport))
  (defrecord WorkflowOutput
    (report WorkReport))
  (defworkflow entry
    ((input WorkflowInput))
    -> WorkflowOutput
    (let* ((fixed input.report))
      (let-proc (run-local ((item WorkflowInput)) -> WorkflowOutput
                  :captures (fixed fixed)
                  (record WorkflowOutput :report item.report))
        (record WorkflowOutput :report input.report)))))
