(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule judgment_views/review_revise_design_docs_export_import)
  (import std/phase :only (ReviewDecision))
  (import review_revise_design_docs :only
    (DesignDocPath ReviewReportTargetPath WorkReportPath review-design-doc))
  (export imported-review)

  (defworkflow imported-review
    ((target_doc DesignDocPath)
     (context_docs List[DesignDocPath])
     (review_focus String)
     (checks_report WorkReportPath)
     (review_report_target_path ReviewReportTargetPath))
    -> ReviewDecision
    (provider-result providers.design-docs.review
      :prompt
        (review-design-doc
          :target_doc target_doc
          :context_docs context_docs
          :review_focus review_focus
          :checks_report checks_report
          :review_report_target_path review_report_target_path)
      :delivery :composed
      :model "fixture-model"
      :effort "high"
      :timeout-sec 3600))
)
