(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule review_revise_parametric_design_docs)
  (import std/phase :only (ReviewFindings review-revise-loop))
  (export review-revise-parametric-design-docs)

  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)

  (defenum ReviewDecision
    APPROVE
    REVISE
    BLOCKED)

  (defpath DesignDocPath
    :kind relpath
    :under "docs/design"
    :must-exist true)

  (defpath ReviewReportPath
    :kind relpath
    :under "artifacts/review"
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

  (defrecord ParametricDesignDocs
    (integration_doc DesignDocPath)
    (structural_constraints_doc DesignDocPath)
    (parametric_specialization_doc DesignDocPath))

  (defrecord ParametricDesignReviewInputs
    (integration_doc DesignDocPath)
    (structural_constraints_doc DesignDocPath)
    (parametric_specialization_doc DesignDocPath)
    (checks_report WorkReportPath)
    (review_report_target_path ReviewReportTargetPath)
    (revision_report_target_path WorkReportTargetPath))

  (defunion ParametricDesignReviewLoopResult
    (APPROVED
      (checks_report WorkReportPath)
      (review_report ReviewReportPath)
      (review_decision ReviewDecision)
      (findings ReviewFindings))
    (BLOCKED
      (progress_report WorkReportPath)
      (blocker_class BlockerClass)
      (findings ReviewFindings))
    (EXHAUSTED
      (last_review_report ReviewReportPath)
      (reason String)
      (findings ReviewFindings)))

  (defworkflow review-revise-parametric-design-docs
    ((phase-ctx PhaseCtx)
     (integration_doc DesignDocPath :default "workflow_lisp_review_revise_stdlib_parametric_integration.md")
     (structural_constraints_doc DesignDocPath :default "workflow_lisp_structural_parametric_constraints.md")
     (parametric_specialization_doc DesignDocPath :default "workflow_lisp_compile_time_parametric_specialization.md")
     (checks_report WorkReportPath :default "artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-parametric-design-docs-checks.md")
     (review_report_target_path ReviewReportTargetPath :default "artifacts/review/LISP-MIGRATION-PARITY-DRAIN/review-revise-parametric-design-docs-review.md")
     (revision_report_target_path WorkReportTargetPath :default "artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-parametric-design-docs-revision.md"))
    -> ParametricDesignReviewLoopResult
    (with-phase phase-ctx design-review
      (let* ((completed
               (record ParametricDesignDocs
                 :integration_doc integration_doc
                 :structural_constraints_doc structural_constraints_doc
                 :parametric_specialization_doc parametric_specialization_doc))
             (inputs
               (record ParametricDesignReviewInputs
                 :integration_doc integration_doc
                 :structural_constraints_doc structural_constraints_doc
                 :parametric_specialization_doc parametric_specialization_doc
                 :checks_report checks_report
                 :review_report_target_path review_report_target_path
                 :revision_report_target_path revision_report_target_path))
             (review
               (review-revise-loop design-review
                 :ctx phase-ctx
                 :completed completed
                 :inputs inputs
                 :review-provider providers.design-docs.review
                 :fix-provider providers.design-docs.fix
                 :review-prompt prompts.design-docs.review
                 :fix-prompt prompts.design-docs.fix
                 :max 3
                 :returns ParametricDesignReviewLoopResult)))
        (match review
          ((APPROVED approved)
           (variant ParametricDesignReviewLoopResult APPROVED
             :checks_report approved.checks_report
             :review_report approved.review_report
             :review_decision approved.review_decision
             :findings
               (record ReviewFindings
                 :schema_version approved.findings.schema_version
                 :items_path approved.findings.items_path)))
          ((BLOCKED blocked)
           (variant ParametricDesignReviewLoopResult BLOCKED
             :progress_report blocked.progress_report
             :blocker_class blocked.blocker_class
             :findings
               (record ReviewFindings
                 :schema_version blocked.findings.schema_version
                 :items_path blocked.findings.items_path)))
          ((EXHAUSTED exhausted)
           (variant ParametricDesignReviewLoopResult EXHAUSTED
             :last_review_report exhausted.last_review_report
             :reason exhausted.reason
             :findings
               (record ReviewFindings
                 :schema_version exhausted.findings.schema_version
                 :items_path exhausted.findings.items_path))))))))
