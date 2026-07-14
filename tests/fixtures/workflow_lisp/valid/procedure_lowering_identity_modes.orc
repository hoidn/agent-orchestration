(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule procedure_lowering_identity_modes)
  (export orchestrate)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ChecksResult
    (report WorkReport))
  (defunion PlanResult
    (APPROVE
      (report WorkReport))
    (REVISE
      (report WorkReport)))
  (defproc inline-plan
    ((report_path WorkReport))
    -> PlanResult
    :effects
      ((uses-provider providers.review)
       (uses-command run_checks))
    :lowering inline
    (let* ((attempt
             (provider-result providers.review
               :prompt prompts.review
               :inputs (report_path)
               :returns PlanResult))
           (checks
             (command-result run_checks
               :argv ("python" "scripts/run_checks.py" report_path)
               :returns ChecksResult)))
      (match attempt
        ((APPROVE approved)
         (variant PlanResult APPROVE
           :report checks.report))
        ((REVISE revise)
         (variant PlanResult REVISE
           :report checks.report)))))
  (defproc private-helper
    ((report_path WorkReport))
    -> ChecksResult
    :effects ((uses-command run_checks))
    :lowering private-workflow
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns ChecksResult))
  (defproc auto-helper
    ((report_path WorkReport))
    -> ChecksResult
    :effects ((uses-command run_checks))
    :lowering auto
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py" report_path)
      :returns ChecksResult))
  (defworkflow orchestrate
    ((report_path WorkReport))
    -> PlanResult
    (let* ((plan (inline-plan report_path))
           (private_result (private-helper report_path))
           (auto_first (auto-helper report_path))
           (auto_second (auto-helper report_path)))
      (loop/recur
        :max 1
        :state plan
        (fn (state)
          (match state
            ((APPROVE approved)
             (done state))
            ((REVISE revise)
             (done state))))))))
