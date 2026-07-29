(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule review_revise_design_docs_judgment_panel)
  (import std/phase :only (ReviewReportPath))
  (import review_revise_design_docs :only
    (DesignDocPath ReviewReportTargetPath WorkReportPath review-design-doc))
  (export review-revise-design-docs-judgment-panel)

  (defrecord DesignDocPanelResult
    (reports List[ReviewReportPath])
    (synthesis ReviewReportPath))

  (defworkflow review-one
    ((lens String)
     (review_report_target_path ReviewReportTargetPath)
     (target_doc DesignDocPath)
     (context_docs List[DesignDocPath])
     (checks_report WorkReportPath)
     (review_model String)
     (review_effort String))
    -> ReviewReportPath
    (let* ((decision
             (provider-result providers.design-docs.review
               :prompt
                 (review-design-doc
                   :target_doc target_doc
                   :context_docs context_docs
                   :review_focus lens
                   :checks_report checks_report
                   :review_report_target_path
                     review_report_target_path)
               :delivery :composed
               :model review_model
               :effort review_effort
               :timeout-sec 3600)))
      (match decision
        ((APPROVE approved) approved.review_report)
        ((REVISE revised) revised.review_report)
        ((BLOCKED blocked) blocked.review_report))))

  ;; The checked fixture supplies a non-empty, path-safe, pairwise-distinct
  ;; lens set. Callers that replace it must preserve those properties because
  ;; cross-iteration output destinations are not deduplicated.
  (defworkflow review-revise-design-docs-judgment-panel
    ((target_doc DesignDocPath)
     (context_docs List[DesignDocPath])
     (lens_ids List[String])
     (checks_report WorkReportPath)
     (review_model String :default "gpt-5.5")
     (review_effort String :default "high")
     (synthesis_model String :default "gpt-5.5")
     (synthesis_effort String :default "high"))
    -> DesignDocPanelResult
    (let* ((reports
             (list/map-effect ((lens lens_ids)) :max 8
               (call review-one
                 :lens lens
                 :review_report_target_path
                   (path/join-under ReviewReportTargetPath lens)
                 :target_doc target_doc
                 :context_docs context_docs
                 :checks_report checks_report
                 :review_model review_model
                 :review_effort review_effort)))
           (synthesis
             (provider-result providers.design-docs.synthesize
               :prompt prompts.design-docs.synthesize
               :inputs (target_doc reports)
               :model synthesis_model
               :effort synthesis_effort
               :timeout-sec 3600
               :returns ReviewReportPath)))
      (record DesignDocPanelResult
        :reports reports
        :synthesis synthesis)))
)
