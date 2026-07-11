(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule native_bool_provider_branch)
  (export decide)
  (defpath SummaryTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord DecisionSummary
    (approved Bool))
  (defworkflow decide
    ((summary_target SummaryTarget))
    -> Bool
    (let* ((approved
             (provider-result providers.review
               :prompt prompts.review
               :inputs (summary_target)
               :returns Bool))
           (summary_path
             (materialize-view decision-summary
               :value (record DecisionSummary
                        :approved approved)
               :renderer canonical-json
               :renderer-version 1
               :target summary_target
               :returns SummaryTarget)))
      (if approved
          (command-result record_approved
            :argv ("python" "scripts/record_approved.py")
            :returns Bool)
          (command-result record_revise
            :argv ("python" "scripts/record_revise.py")
            :returns Bool)))))
