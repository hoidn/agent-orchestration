(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule wcc_m4_implementation_phase_full_fixture)
  (import std/phase :only (BlockerClass ReviewDecision ReviewFindings ReviewLoopResult ReviewReportPath review-revise-loop with-phase))
  (export run)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord ChecksResult
    (checks_report_path WorkReport))
  (defrecord CompletedAttempt
    (execution_report_path WorkReport)
    (checks_report_path WorkReport))
  (defrecord ReviewInputs
    (design_review_prompt WorkReport)
    (fix_plan_prompt WorkReport))
	  (defunion ImplementationAttempt
	    (COMPLETED
	      (execution_report_path WorkReport))
	    (BLOCKED
	      (review_report ReviewReportPath)
	      (blocker_class BlockerClass)
	      (findings ReviewFindings)))
  (defproc run-review
    ((completed CompletedAttempt)
     (inputs ReviewInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.review))
    :lowering inline
    (provider-result providers.review
      :prompt prompts.implementation.review
      :inputs (completed.execution_report_path
               completed.checks_report_path
               inputs.design_review_prompt
               inputs.fix_plan_prompt)
      :returns ReviewDecision))
  (defproc apply-fix
    ((completed CompletedAttempt)
     (inputs ReviewInputs)
     (findings ReviewFindings))
    -> CompletedAttempt
    :effects ((uses-provider providers.fix))
    :lowering inline
    (provider-result providers.fix
      :prompt prompts.implementation.fix
      :inputs (completed.execution_report_path
               completed.checks_report_path
               inputs.design_review_prompt
               inputs.fix_plan_prompt
               findings.items_path)
      :returns CompletedAttempt))
	  (defworkflow run
	    ((phase-ctx PhaseCtx)
	     (plan_path WorkReport)
	     (inputs ReviewInputs))
	    -> ReviewLoopResult
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (plan_path)
               :returns ImplementationAttempt)))
      (match attempt
        ((COMPLETED completed)
         (let* ((checks
                  (command-result run_checks
                    :argv ("python" "scripts/run_checks.py" completed.execution_report_path)
                    :returns ChecksResult))
                (checked-completed
                  (record CompletedAttempt
                    :execution_report_path completed.execution_report_path
                    :checks_report_path checks.checks_report_path)))
	          (with-phase phase-ctx implementation-review
	            (review-revise-loop implementation-review
	              :ctx phase-ctx
	              :completed checked-completed
	              :inputs inputs
	              :review (proc-ref run-review)
	              :fix (proc-ref apply-fix)
	              :max 3))))
	        ((BLOCKED blocked)
	         (variant ReviewLoopResult BLOCKED
	           :review_report blocked.review_report
	           :blocker_class blocked.blocker_class
	           :findings (record ReviewFindings
	                       :schema_version blocked.findings.schema_version
	                       :items_path blocked.findings.items_path)))))))
