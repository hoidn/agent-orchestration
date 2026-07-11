(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defenum ReviewDecision
    APPROVE
    REVISE)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defworkflow native-approval-flag
    ((report_path WorkReport))
    -> Bool
    (provider-result providers.execute
      :prompt prompts.implementation.execute
      :inputs (report_path)
      :returns Bool))
  (defworkflow native-review-decision
    ((report_path WorkReport))
    -> ReviewDecision
    (provider-result providers.execute
      :prompt prompts.implementation.execute
      :inputs (report_path)
      :returns ReviewDecision))
  (defworkflow native-confidence-score
    ((report_path WorkReport))
    -> Float
    (provider-result providers.execute
      :prompt prompts.implementation.execute
      :inputs (report_path)
      :returns Float))
  (defworkflow native-finding-count
    ((report_path WorkReport))
    -> Int
    (command-result count_findings
      :argv ("python" "scripts/count_findings.py" report_path)
      :returns Int))
  (defworkflow native-summary-line
    ((report_path WorkReport))
    -> String
    (command-result summarize_report
      :argv ("python" "scripts/summarize_report.py" report_path)
      :returns String))
  (defworkflow native-report-location
    ((report_path WorkReport))
    -> WorkReport
    (command-result locate_report
      :argv ("python" "scripts/locate_report.py" report_path)
      :returns WorkReport)))
