(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defworkflow native-json-return
    ((report_path WorkReport))
    -> Bool
    (provider-result providers.execute
      :prompt prompts.implementation.execute
      :inputs (report_path)
      :returns Json)))
