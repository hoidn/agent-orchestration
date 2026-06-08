(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule review_revise_design_docs)
  (import std/phase :only
    (BlockerClass ReviewDecision ReviewFindings ReviewLoopResult ReviewReportPath review-revise-loop))
  (export review-revise-design-docs)

  (defpath DesignDocPath
    :kind relpath
    :under "docs/design"
    :must-exist true)

  (defpath ReviewReportTargetPath
    :kind relpath
    :under "artifacts/review"
    :must-exist false)

  (defpath WorkReportPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defpath WorkReportTargetPath
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defrecord DesignDocReviewSubject
    (target_doc DesignDocPath)
    (context_docs List[DesignDocPath]))

  (defrecord DesignDocReviewInputs
    (target_doc DesignDocPath)
    (context_docs List[DesignDocPath])
    (review_focus String)
    (checks_report WorkReportPath)
    (review_report_target_path ReviewReportTargetPath)
    (revision_report_target_path WorkReportTargetPath))

  (defrecord DesignDocRevisionResult
    (revision_report WorkReportPath))

  (defunion DesignDocReviewLoopResult
    (APPROVED
      (checks_report WorkReportPath)
      (review_report ReviewReportPath)
      (review_decision String)
      (findings ReviewFindings))
    (BLOCKED
      (progress_report ReviewReportPath)
      (blocker_class BlockerClass)
      (findings ReviewFindings))
    (EXHAUSTED
      (last_review_report ReviewReportPath)
      (reason String)
      (findings ReviewFindings)))

  (defproc review-design-docs
    ((completed DesignDocReviewSubject)
     (inputs DesignDocReviewInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.design-docs.review))
    :lowering inline
    (provider-result providers.design-docs.review
      :prompt prompts.design-docs.review
      :inputs (completed.target_doc
               completed.context_docs
               inputs.review_focus
               inputs.checks_report
               inputs.review_report_target_path)
      :returns ReviewDecision))

  (defproc fix-design-doc
    ((completed DesignDocReviewSubject)
     (inputs DesignDocReviewInputs)
     (findings ReviewFindings))
    -> DesignDocReviewSubject
    :effects ((uses-provider providers.design-docs.fix))
    :lowering inline
    (let* ((revision
             (provider-result providers.design-docs.fix
               :prompt prompts.design-docs.fix
               :inputs (completed.target_doc
                        completed.context_docs
                        inputs.review_focus
                        inputs.revision_report_target_path
                        findings.items_path)
               :returns DesignDocRevisionResult)))
      completed))

  (defworkflow review-revise-design-docs
    ((phase-ctx PhaseCtx)
     (target_doc DesignDocPath)
     (context_docs List[DesignDocPath])
     (review_focus String)
     (checks_report WorkReportPath)
     (review_report_target_path ReviewReportTargetPath)
     (revision_report_target_path WorkReportTargetPath))
    -> DesignDocReviewLoopResult
    (with-phase phase-ctx design-review
      (let* ((completed
               (record DesignDocReviewSubject
                 :target_doc target_doc
                 :context_docs context_docs))
             (inputs
               (record DesignDocReviewInputs
                 :target_doc target_doc
                 :context_docs context_docs
                 :review_focus review_focus
                 :checks_report checks_report
                 :review_report_target_path review_report_target_path
                 :revision_report_target_path revision_report_target_path))
             (review
               (review-revise-loop design-review
                 :ctx phase-ctx
                 :completed completed
                 :inputs inputs
                 :review (proc-ref review-design-docs)
                 :fix (proc-ref fix-design-doc)
                 :max 20
                 )))
        (match review
          ((APPROVED approved)
           (variant DesignDocReviewLoopResult APPROVED
             :checks_report inputs.checks_report
             :review_report approved.review_report
             :review_decision "APPROVE"
             :findings
               (record ReviewFindings
                 :schema_version approved.findings.schema_version
                 :items_path approved.findings.items_path)))
          ((BLOCKED blocked)
           (variant DesignDocReviewLoopResult BLOCKED
             :progress_report blocked.review_report
             :blocker_class blocked.blocker_class
             :findings
               (record ReviewFindings
                 :schema_version blocked.findings.schema_version
                 :items_path blocked.findings.items_path)))
          ((EXHAUSTED exhausted)
           (variant DesignDocReviewLoopResult EXHAUSTED
             :last_review_report exhausted.last_review_report
             :reason exhausted.reason
             :findings
               (record ReviewFindings
                 :schema_version exhausted.findings.schema_version
                 :items_path exhausted.findings.items_path))))))))
