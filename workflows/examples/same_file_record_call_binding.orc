(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule same_file_record_call_binding)
  (export run-same-file-record-call-binding)

  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defrecord WorkflowInput
    (report WorkReport))

  (defrecord WorkflowOutput
    (report WorkReport))

  (defworkflow build-checks
    ((input WorkflowInput))
    -> WorkflowOutput
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" input.report)
      :returns WorkflowOutput))

  (defworkflow run-same-file-record-call-binding
    ((report_path WorkReport))
    -> WorkflowOutput
    (let* ((input (record WorkflowInput :report report_path)))
      (call build-checks :input input))))
