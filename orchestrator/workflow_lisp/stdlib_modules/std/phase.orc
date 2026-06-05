(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std/phase)
  ; Keep the helper proc exported until imported macro expansion can resolve a
  ; same-file proc reference without routing through the std/phase public surface.
  (export BlockerClass ReviewReportPath ReviewDecision ReviewFindingsJsonPath ReviewFindings ReviewLoopResult review-revise-loop review-revise-loop-proc)
  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)
  (defpath ReviewReportPath
    :kind relpath
    :under "artifacts/review"
    :must-exist true)
  (defpath ReviewFindingsJsonPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ReviewFindings
    (schema_version String)
    (items_path ReviewFindingsJsonPath))
  (defunion ReviewDecision
    (APPROVE
      (review_report ReviewReportPath)
      (findings ReviewFindings))
    (REVISE
      (review_report ReviewReportPath)
      (findings ReviewFindings))
    (BLOCKED
      (review_report ReviewReportPath)
      (blocker_class BlockerClass)
      (findings ReviewFindings)))
  (defunion ReviewLoopResult
    (APPROVED
      (review_report ReviewReportPath)
      (findings ReviewFindings))
    (BLOCKED
      (review_report ReviewReportPath)
      (blocker_class BlockerClass)
      (findings ReviewFindings))
    (EXHAUSTED
      (last_review_report ReviewReportPath)
      (findings ReviewFindings)
      (reason String)))
  (defproc review-revise-loop-proc
    :forall (CtxT CompletedT InputsT)
    ((ctx CtxT)
     (completed CompletedT)
     (inputs InputsT)
     (initial_review_report std/phase/ReviewReportPath)
     (initial_findings std/phase/ReviewFindings)
     (review ProcRef[(CompletedT InputsT) -> std/phase/ReviewDecision])
     (fix ProcRef[(CompletedT InputsT std/phase/ReviewFindings) -> CompletedT])
     (max_iterations Int))
    :where ((CtxT is-record)
            (CompletedT is-record)
            (InputsT is-record))
    -> std/phase/ReviewLoopResult
    :effects ((uses-command validate_review_findings_v1))
    :lowering inline
    (loop/recur
      :max max_iterations
      :state (loop-state
               (completed CompletedT completed)
               (inputs InputsT inputs)
               (last_review_report std/phase/ReviewReportPath initial_review_report)
               (latest_findings std/phase/ReviewFindings initial_findings))
      :on-exhausted (variant std/phase/ReviewLoopResult EXHAUSTED
                      :last_review_report state.last_review_report
                      :findings (record std/phase/ReviewFindings
                                  :schema_version state.latest_findings.schema_version
                                  :items_path state.latest_findings.items_path)
                      :reason "max_iterations_reached")
      (fn (state)
        (let* ((review-decision
                 (review state.completed state.inputs)))
          (match review-decision
            ((APPROVE approved)
             (let* ((validated-findings
                      (command-result validate_review_findings_v1
                        :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" approved.findings.schema_version approved.findings.items_path)
                        :returns ReviewFindings)))
               (done
                 (variant std/phase/ReviewLoopResult APPROVED
                   :review_report approved.review_report
                   :findings (record std/phase/ReviewFindings
                               :schema_version validated-findings.schema_version
                               :items_path validated-findings.items_path)))))
            ((REVISE revised)
             (let* ((validated-findings
                      (command-result validate_review_findings_v1
                        :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" revised.findings.schema_version revised.findings.items_path)
                        :returns ReviewFindings))
                    (fixed-completed
                      (fix state.completed state.inputs validated-findings)))
               (continue
                 (loop-state :like state
                   :completed fixed-completed
                   :last_review_report revised.review_report
                   :latest_findings validated-findings))))
            ((BLOCKED blocked)
             (let* ((validated-findings
                      (command-result validate_review_findings_v1
                        :argv ("python" "-m" "orchestrator.workflow_lisp.adapters.validate_review_findings_v1" blocked.findings.schema_version blocked.findings.items_path)
                        :returns ReviewFindings)))
               (done
                 (variant std/phase/ReviewLoopResult BLOCKED
                   :review_report blocked.review_report
                   :blocker_class blocked.blocker_class
                   :findings (record std/phase/ReviewFindings
                               :schema_version validated-findings.schema_version
                               :items_path validated-findings.items_path))))))))))
  (defmacro review-revise-loop (name ctx-key ctx completed-key completed inputs-key inputs review-key review fix-key fix max-key max)
    (std/phase/review-revise-loop-proc
      ctx
      completed
      inputs
      (__generated-relpath-seed__
        std/phase/ReviewReportPath
        "artifacts/review/last-review-report.md"
        "review_loop_last_review_report_seed")
      (record std/phase/ReviewFindings
        :schema_version "ReviewFindings.v1"
        :items_path (__generated-relpath-seed__
                      std/phase/ReviewFindingsJsonPath
                      "artifacts/work/review-findings-seed.json"
                      "review_loop_findings_items_path_seed"))
      review
      fix
      max)))
