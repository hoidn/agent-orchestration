(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (report WorkReport))
  (defproc build-checks
    ((provider Provider)
     (prompt Prompt)
     (report_path WorkReport))
    -> ChecksResult
    :effects ()
    :lowering private-workflow
    (record ChecksResult
      :report report_path))
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> ChecksResult
    (build-checks providers.execute prompts.implementation.execute report_path)))
