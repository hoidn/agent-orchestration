(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.20")
  (defmodule prompt_q1_target_2_20_resume)
  (import std/phase :only
    (BlockerClass ReviewDecision ReviewFindings ReviewLoopResult ReviewReportPath review-revise-loop))
  (import std/context :only (RunCtx))
  (export review-revise-design-docs)

  (defpath DesignDocPath
    :kind relpath
    :under "docs"
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

  (defrecord ReviewRuntimeOwned
    (run RunCtx))

  (defworkflow build-review-runtime-owned
    ((run RunCtx))
    -> ReviewRuntimeOwned
    (record ReviewRuntimeOwned
      :run (record RunCtx
             :run-id run.run-id
             :state-root run.state-root
             :artifact-root run.artifact-root)))

  (defrecord DesignDocReviewSubject
    (target_doc DesignDocPath)
    (context_docs List[DesignDocPath]))

  (defrecord DesignDocReviewInputs
    (review_focus String)
    (checks_report WorkReportPath)
    (review_report_target_path ReviewReportTargetPath)
    (revision_report_target_path WorkReportTargetPath)
    (review_model String)
    (review_effort String)
    (fix_model String)
    (fix_effort String))

  (defrecord DesignDocRevisionResult
    (revision_report WorkReportPath))

  (defunion DesignDocReviewLoopResult
    (APPROVED
      (checks_report WorkReportPath)
      (review_report ReviewReportPath)
      (findings ReviewFindings))
    (BLOCKED
      (progress_report ReviewReportPath)
      (blocker_class BlockerClass)
      (findings ReviewFindings))
    (EXHAUSTED
      (last_review_report ReviewReportPath)
      (reason String)
      (findings ReviewFindings)))

  (defprompt review-design-doc
    (:fills
      (target_doc :doc DesignDocPath)
      (context_docs :value List[DesignDocPath])
      (review_focus :text)
      (checks_report :path WorkReportPath)
      (review_report_target_path :path ReviewReportTargetPath))
    -> ReviewDecision
    "Take the role of a principal engineer with strong PL, compiler, and agentic\nworkflow architecture judgment.\n\nReview the target design doc from the point of view described by the provided\nreview focus.\n\n{review_focus}\n\nUse the context docs as supporting context and authority.\n\n{context_docs}\n\nThe\ndesign may be considered implementation-ready only if it improves ergonomics\nand the long-term maintainability, extensibility, and internal architecture of\nthe implementation.\n\nRead the target doc from the provided target_doc input path. Read every path in\ncontext_docs when context docs are provided. Also read the provided checks\nreport if present.\n\n{checks_report}\n\nTreat structured inputs and artifact paths as authority; do\nnot infer success from prose summaries alone.\n\nDecide:\n\n- APPROVE when the target doc is consistent with its context docs, technically\n  sound, and ready to guide implementation under the supplied review focus.\n- REVISE when specific doc edits are required before implementation should\n  proceed.\n- BLOCKED only when the review cannot be completed from the available material\n  or a prerequisite decision outside the docs is required.\n\nFor REVISE or BLOCKED, make findings concrete enough for a reviser to act\nwithout another clarification pass.\n\n{review_report_target_path}\n\nThe structured findings carrier must use the exact schema expected by the\nworkflow. Use `schema_version` exactly `ReviewFindings.v1`. The referenced\nfindings JSON artifact must be an object with a top-level `items` array. Do not\nwrite `review_findings.v1`, `review-findings-v1`, or a top-level `findings`\narray.\n")

  (defproc review-design-docs
    ((completed DesignDocReviewSubject)
     (inputs DesignDocReviewInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.design-docs.review))
    :lowering inline
    (provider-result providers.design-docs.review
      :prompt
        (review-design-doc
          :target_doc completed.target_doc
          :context_docs completed.context_docs
          :review_focus inputs.review_focus
          :checks_report inputs.checks_report
          :review_report_target_path inputs.review_report_target_path)
      :model inputs.review_model
      :effort inputs.review_effort
      :timeout-sec 3600))

  (defproc fix-design-doc
    ((completed DesignDocReviewSubject)
     (inputs DesignDocReviewInputs)
     (findings ReviewFindings))
    -> DesignDocReviewSubject
    :effects ((uses-provider providers.design-docs.fix))
    :lowering inline
    ;; review-revise-loop's :fix contract requires returning the subject;
    ;; this binding exists to sequence the revision effect before that return.
    (let* ((revision
             (provider-result providers.design-docs.fix
               :prompt prompts.design-docs.fix
               :inputs (completed.target_doc
                        completed.context_docs
                        inputs.review_focus
                        inputs.revision_report_target_path
                        findings.items_path)
               :model inputs.fix_model
               :effort inputs.fix_effort
               :timeout-sec 7200
               :returns DesignDocRevisionResult)))
      completed))

  (defworkflow review-revise-design-docs
    ((target_doc DesignDocPath)
     (context_docs List[DesignDocPath])
     (review_focus String)
     (checks_report WorkReportPath)
     (review_report_target_path ReviewReportTargetPath)
     (revision_report_target_path WorkReportTargetPath)
     (review_model String :default "gpt-5.5")
     (review_effort String :default "high")
     (fix_model String :default "gpt-5.5")
     (fix_effort String :default "high"))
    -> DesignDocReviewLoopResult
    (let* ((runtime-owned
             (call build-review-runtime-owned))
           (completed
             (record DesignDocReviewSubject
               :target_doc target_doc
               :context_docs context_docs))
           (inputs
             (record DesignDocReviewInputs
               :review_focus review_focus
               :checks_report checks_report
               :review_report_target_path review_report_target_path
               :revision_report_target_path revision_report_target_path
               :review_model review_model
               :review_effort review_effort
               :fix_model fix_model
               :fix_effort fix_effort))
           (review
             (review-revise-loop design-review
               :ctx runtime-owned
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
               :items_path exhausted.findings.items_path))))))
)
