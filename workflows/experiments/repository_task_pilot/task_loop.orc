(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.20")
  (defmodule task_loop)
  (export run-task)

  (defpath TaskPath
    :kind relpath
    :under ".pilot/runtime"
    :must-exist true)

  (defpath ControlPath
    :kind relpath
    :under ".pilot/runtime"
    :must-exist true)

  (defrecord DiscoveryResult
    (relevant_paths List[String])
    (constraints List[String])
    (risks List[String]))

  (defrecord PlanResult
    (steps List[String])
    (acceptance_checks List[String]))

  (defenum ReviewDecision
    APPROVE
    REVISE
    BLOCKED)

  (defrecord ReviewResult
    (decision ReviewDecision)
    (rationale String)
    (findings List[String])
    (reason String))

  (defrecord ImplementationResult
    (summary String)
    (changed_paths List[String])
    (checks_summary String))

  (defrecord ChecksResult
    (passed Bool)
    (exit_code Int))

  (defrecord GuardedDiscovery
    (unchanged Bool)
    (relevant_paths List[String])
    (constraints List[String])
    (risks List[String]))

  (defrecord GuardedPlan
    (unchanged Bool)
    (steps List[String])
    (acceptance_checks List[String]))

  (defrecord GuardedReview
    (unchanged Bool)
    (decision ReviewDecision)
    (rationale String)
    (findings List[String])
    (reason String))

  (defenum PilotOutcome
    COMPLETED
    BLOCKED
    EXHAUSTED
    PROTOCOL_FAILURE)

  (defworkflow guarded-discover
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (model String)
     (effort String))
    -> GuardedDiscovery
    (let* ((before
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "discover"
                      "--position"
                      "before")
               :returns String))
           (discovery
             (provider-result providers.repository-task.discover
               :prompt prompts.repository-task.discover
               :inputs (task_path)
               :model model
               :effort effort
               :timeout-sec 1800
               :returns DiscoveryResult))
           (after
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "discover"
                      "--position"
                      "after")
               :returns String)))
      (record GuardedDiscovery
        :unchanged (= before after)
        :relevant_paths discovery.relevant_paths
        :constraints discovery.constraints
        :risks discovery.risks)))

  (defworkflow guarded-plan
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (relevant_paths List[String])
     (constraints List[String])
     (risks List[String])
     (model String)
     (effort String))
    -> GuardedPlan
    (let* ((discovery
             (record DiscoveryResult
               :relevant_paths relevant_paths
               :constraints constraints
               :risks risks))
           (before
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "plan"
                      "--position"
                      "before")
               :returns String))
           (plan
             (provider-result providers.repository-task.plan
               :prompt prompts.repository-task.plan
               :inputs (task_path discovery control_path)
               :model model
               :effort effort
               :timeout-sec 1800
               :returns PlanResult))
           (after
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "plan"
                      "--position"
                      "after")
               :returns String)))
      (record GuardedPlan
        :unchanged (= before after)
        :steps plan.steps
        :acceptance_checks plan.acceptance_checks)))

  (defworkflow guarded-plan-review
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (relevant_paths List[String])
     (constraints List[String])
     (risks List[String])
     (steps List[String])
     (acceptance_checks List[String])
     (model String)
     (effort String))
    -> GuardedReview
    (let* ((discovery
             (record DiscoveryResult
               :relevant_paths relevant_paths
               :constraints constraints
               :risks risks))
           (plan
             (record PlanResult
               :steps steps
               :acceptance_checks acceptance_checks))
           (before
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "review_plan"
                      "--position"
                      "before")
               :returns String))
           (review
             (provider-result providers.repository-task.review-plan
               :prompt prompts.repository-task.review-plan
               :inputs (task_path discovery plan control_path)
               :model model
               :effort effort
               :timeout-sec 1800
               :returns ReviewResult))
           (after
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "review_plan"
                      "--position"
                      "after")
               :returns String)))
      (record GuardedReview
        :unchanged (= before after)
        :decision review.decision
        :rationale review.rationale
        :findings review.findings
        :reason review.reason)))

  (defworkflow guarded-revise-plan
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (relevant_paths List[String])
     (constraints List[String])
     (risks List[String])
     (steps List[String])
     (acceptance_checks List[String])
     (review_decision ReviewDecision)
     (review_rationale String)
     (review_findings List[String])
     (review_reason String)
     (model String)
     (effort String))
    -> GuardedPlan
    (let* ((discovery
             (record DiscoveryResult
               :relevant_paths relevant_paths
               :constraints constraints
               :risks risks))
           (plan
             (record PlanResult
               :steps steps
               :acceptance_checks acceptance_checks))
           (plan_review
             (record ReviewResult
               :decision review_decision
               :rationale review_rationale
               :findings review_findings
               :reason review_reason))
           (before
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "revise_plan"
                      "--position"
                      "before")
               :returns String))
           (revised_plan
             (provider-result providers.repository-task.revise-plan
               :prompt prompts.repository-task.revise-plan
               :inputs (task_path discovery plan plan_review control_path)
               :model model
               :effort effort
               :timeout-sec 1800
               :returns PlanResult))
           (after
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "revise_plan"
                      "--position"
                      "after")
               :returns String)))
      (record GuardedPlan
        :unchanged (= before after)
        :steps revised_plan.steps
        :acceptance_checks revised_plan.acceptance_checks)))

  (defworkflow guarded-implementation-review
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (steps List[String])
     (acceptance_checks List[String])
     (summary String)
     (changed_paths List[String])
     (checks_summary String)
     (checks_passed Bool)
     (checks_exit_code Int)
     (model String)
     (effort String))
    -> GuardedReview
    (let* ((plan
             (record PlanResult
               :steps steps
               :acceptance_checks acceptance_checks))
           (implementation
             (record ImplementationResult
               :summary summary
               :changed_paths changed_paths
               :checks_summary checks_summary))
           (checks
             (record ChecksResult
               :passed checks_passed
               :exit_code checks_exit_code))
           (before
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "review_implementation"
                      "--position"
                      "before")
               :returns String))
           (review
             (provider-result providers.repository-task.review-implementation
               :prompt prompts.repository-task.review-implementation
               :inputs (task_path plan implementation checks)
               :model model
               :effort effort
               :timeout-sec 1800
               :returns ReviewResult))
           (after
             (command-result pilot_product_manifest
               :argv ("python"
                      controller_script
                      "product-manifest"
                      "--control"
                      control_path
                      "--phase"
                      "review_implementation"
                      "--position"
                      "after")
               :returns String)))
      (record GuardedReview
        :unchanged (= before after)
        :decision review.decision
        :rationale review.rationale
        :findings review.findings
        :reason review.reason)))

  (defworkflow after-final-approval
    ((checks_passed Bool))
    -> PilotOutcome
    (if checks_passed
      PilotOutcome.COMPLETED
      PilotOutcome.EXHAUSTED))

  (defworkflow after-nonblocked-final-review
    ((review_decision ReviewDecision)
     (checks_passed Bool))
    -> PilotOutcome
    (let* ((is_revise
             (= review_decision ReviewDecision.REVISE)))
      (if is_revise
        PilotOutcome.EXHAUSTED
        (call after-final-approval
          :checks_passed checks_passed))))

  (defworkflow after-final-review
    ((review_decision ReviewDecision)
     (checks_passed Bool))
    -> PilotOutcome
    (let* ((is_blocked
             (= review_decision ReviewDecision.BLOCKED)))
      (if is_blocked
        PilotOutcome.BLOCKED
        (call after-nonblocked-final-review
          :review_decision review_decision
          :checks_passed checks_passed))))

  (defworkflow fix-stage
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (steps List[String])
     (acceptance_checks List[String])
     (summary String)
     (changed_paths List[String])
     (checks_summary String)
     (checks_passed Bool)
     (checks_exit_code Int)
     (review_decision ReviewDecision)
     (review_rationale String)
     (review_findings List[String])
     (review_reason String)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((plan
             (record PlanResult
               :steps steps
               :acceptance_checks acceptance_checks))
           (implementation
             (record ImplementationResult
               :summary summary
               :changed_paths changed_paths
               :checks_summary checks_summary))
           (checks
             (record ChecksResult
               :passed checks_passed
               :exit_code checks_exit_code))
           (implementation_review
             (record ReviewResult
               :decision review_decision
               :rationale review_rationale
               :findings review_findings
               :reason review_reason))
           (fixed_implementation
             (provider-result providers.repository-task.fix-implementation
               :prompt prompts.repository-task.fix-implementation
               :inputs (task_path
                        plan
                        implementation
                        checks
                        implementation_review)
               :model model
               :effort effort
               :timeout-sec 1800
               :returns ImplementationResult))
           (fixed_checks
             (command-result pilot_visible_check
               :argv ("python"
                      controller_script
                      "visible-check"
                      "--control"
                      control_path
                      "--attempt"
                      "2")
               :returns ChecksResult))
           (fixed_review
             (call guarded-implementation-review
               :task_path task_path
               :control_path control_path
               :controller_script controller_script
               :steps steps
               :acceptance_checks acceptance_checks
               :summary fixed_implementation.summary
               :changed_paths fixed_implementation.changed_paths
               :checks_summary fixed_implementation.checks_summary
               :checks_passed fixed_checks.passed
               :checks_exit_code fixed_checks.exit_code
               :model model
               :effort effort)))
      (if fixed_review.unchanged
        (call after-final-review
          :review_decision fixed_review.decision
          :checks_passed fixed_checks.passed)
        PilotOutcome.PROTOCOL_FAILURE)))

  (defworkflow after-initial-approval
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (steps List[String])
     (acceptance_checks List[String])
     (summary String)
     (changed_paths List[String])
     (checks_summary String)
     (checks_passed Bool)
     (checks_exit_code Int)
     (review_decision ReviewDecision)
     (review_rationale String)
     (review_findings List[String])
     (review_reason String)
     (model String)
     (effort String))
    -> PilotOutcome
    (if checks_passed
      PilotOutcome.COMPLETED
      (call fix-stage
        :task_path task_path
        :control_path control_path
        :controller_script controller_script
        :steps steps
        :acceptance_checks acceptance_checks
        :summary summary
        :changed_paths changed_paths
        :checks_summary checks_summary
        :checks_passed checks_passed
        :checks_exit_code checks_exit_code
        :review_decision review_decision
        :review_rationale review_rationale
        :review_findings review_findings
        :review_reason review_reason
        :model model
        :effort effort)))

  (defworkflow after-nonblocked-initial-review
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (steps List[String])
     (acceptance_checks List[String])
     (summary String)
     (changed_paths List[String])
     (checks_summary String)
     (checks_passed Bool)
     (checks_exit_code Int)
     (review_decision ReviewDecision)
     (review_rationale String)
     (review_findings List[String])
     (review_reason String)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((is_revise
             (= review_decision ReviewDecision.REVISE)))
      (if is_revise
        (call fix-stage
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :steps steps
          :acceptance_checks acceptance_checks
          :summary summary
          :changed_paths changed_paths
          :checks_summary checks_summary
          :checks_passed checks_passed
          :checks_exit_code checks_exit_code
          :review_decision review_decision
          :review_rationale review_rationale
          :review_findings review_findings
          :review_reason review_reason
          :model model
          :effort effort)
        (call after-initial-approval
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :steps steps
          :acceptance_checks acceptance_checks
          :summary summary
          :changed_paths changed_paths
          :checks_summary checks_summary
          :checks_passed checks_passed
          :checks_exit_code checks_exit_code
          :review_decision review_decision
          :review_rationale review_rationale
          :review_findings review_findings
          :review_reason review_reason
          :model model
          :effort effort))))

  (defworkflow after-initial-implementation-review
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (steps List[String])
     (acceptance_checks List[String])
     (summary String)
     (changed_paths List[String])
     (checks_summary String)
     (checks_passed Bool)
     (checks_exit_code Int)
     (review_decision ReviewDecision)
     (review_rationale String)
     (review_findings List[String])
     (review_reason String)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((is_blocked
             (= review_decision ReviewDecision.BLOCKED)))
      (if is_blocked
        PilotOutcome.BLOCKED
        (call after-nonblocked-initial-review
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :steps steps
          :acceptance_checks acceptance_checks
          :summary summary
          :changed_paths changed_paths
          :checks_summary checks_summary
          :checks_passed checks_passed
          :checks_exit_code checks_exit_code
          :review_decision review_decision
          :review_rationale review_rationale
          :review_findings review_findings
          :review_reason review_reason
          :model model
          :effort effort))))

  (defworkflow implementation-stage
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (steps List[String])
     (acceptance_checks List[String])
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((plan
             (record PlanResult
               :steps steps
               :acceptance_checks acceptance_checks))
           (implementation
             (provider-result providers.repository-task.implement
               :prompt prompts.repository-task.implement
               :inputs (task_path plan)
               :model model
               :effort effort
               :timeout-sec 1800
               :returns ImplementationResult))
           (checks
             (command-result pilot_visible_check
               :argv ("python"
                      controller_script
                      "visible-check"
                      "--control"
                      control_path
                      "--attempt"
                      "1")
               :returns ChecksResult))
           (review
             (call guarded-implementation-review
               :task_path task_path
               :control_path control_path
               :controller_script controller_script
               :steps steps
               :acceptance_checks acceptance_checks
               :summary implementation.summary
               :changed_paths implementation.changed_paths
               :checks_summary implementation.checks_summary
               :checks_passed checks.passed
               :checks_exit_code checks.exit_code
               :model model
               :effort effort)))
      (if review.unchanged
        (call after-initial-implementation-review
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :steps steps
          :acceptance_checks acceptance_checks
          :summary implementation.summary
          :changed_paths implementation.changed_paths
          :checks_summary implementation.checks_summary
          :checks_passed checks.passed
          :checks_exit_code checks.exit_code
          :review_decision review.decision
          :review_rationale review.rationale
          :review_findings review.findings
          :review_reason review.reason
          :model model
          :effort effort)
        PilotOutcome.PROTOCOL_FAILURE)))

  (defworkflow after-nonblocked-second-plan-review
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (steps List[String])
     (acceptance_checks List[String])
     (review_decision ReviewDecision)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((is_approved
             (= review_decision ReviewDecision.APPROVE)))
      (if is_approved
        (call implementation-stage
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :steps steps
          :acceptance_checks acceptance_checks
          :model model
          :effort effort)
        PilotOutcome.EXHAUSTED)))

  (defworkflow after-second-plan-review
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (steps List[String])
     (acceptance_checks List[String])
     (review_decision ReviewDecision)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((is_blocked
             (= review_decision ReviewDecision.BLOCKED)))
      (if is_blocked
        PilotOutcome.BLOCKED
        (call after-nonblocked-second-plan-review
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :steps steps
          :acceptance_checks acceptance_checks
          :review_decision review_decision
          :model model
          :effort effort))))

  (defworkflow second-plan-review-stage
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (relevant_paths List[String])
     (constraints List[String])
     (risks List[String])
     (steps List[String])
     (acceptance_checks List[String])
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((review
             (call guarded-plan-review
               :task_path task_path
               :control_path control_path
               :controller_script controller_script
               :relevant_paths relevant_paths
               :constraints constraints
               :risks risks
               :steps steps
               :acceptance_checks acceptance_checks
               :model model
               :effort effort)))
      (if review.unchanged
        (call after-second-plan-review
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :steps steps
          :acceptance_checks acceptance_checks
          :review_decision review.decision
          :model model
          :effort effort)
        PilotOutcome.PROTOCOL_FAILURE)))

  (defworkflow revision-stage
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (relevant_paths List[String])
     (constraints List[String])
     (risks List[String])
     (steps List[String])
     (acceptance_checks List[String])
     (review_decision ReviewDecision)
     (review_rationale String)
     (review_findings List[String])
     (review_reason String)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((revised
             (call guarded-revise-plan
               :task_path task_path
               :control_path control_path
               :controller_script controller_script
               :relevant_paths relevant_paths
               :constraints constraints
               :risks risks
               :steps steps
               :acceptance_checks acceptance_checks
               :review_decision review_decision
               :review_rationale review_rationale
               :review_findings review_findings
               :review_reason review_reason
               :model model
               :effort effort)))
      (if revised.unchanged
        (call second-plan-review-stage
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :relevant_paths relevant_paths
          :constraints constraints
          :risks risks
          :steps revised.steps
          :acceptance_checks revised.acceptance_checks
          :model model
          :effort effort)
        PilotOutcome.PROTOCOL_FAILURE)))

  (defworkflow after-nonblocked-first-plan-review
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (relevant_paths List[String])
     (constraints List[String])
     (risks List[String])
     (steps List[String])
     (acceptance_checks List[String])
     (review_decision ReviewDecision)
     (review_rationale String)
     (review_findings List[String])
     (review_reason String)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((is_approved
             (= review_decision ReviewDecision.APPROVE)))
      (if is_approved
        (call implementation-stage
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :steps steps
          :acceptance_checks acceptance_checks
          :model model
          :effort effort)
        (call revision-stage
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :relevant_paths relevant_paths
          :constraints constraints
          :risks risks
          :steps steps
          :acceptance_checks acceptance_checks
          :review_decision review_decision
          :review_rationale review_rationale
          :review_findings review_findings
          :review_reason review_reason
          :model model
          :effort effort))))

  (defworkflow after-first-plan-review
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (relevant_paths List[String])
     (constraints List[String])
     (risks List[String])
     (steps List[String])
     (acceptance_checks List[String])
     (review_decision ReviewDecision)
     (review_rationale String)
     (review_findings List[String])
     (review_reason String)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((is_blocked
             (= review_decision ReviewDecision.BLOCKED)))
      (if is_blocked
        PilotOutcome.BLOCKED
        (call after-nonblocked-first-plan-review
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :relevant_paths relevant_paths
          :constraints constraints
          :risks risks
          :steps steps
          :acceptance_checks acceptance_checks
          :review_decision review_decision
          :review_rationale review_rationale
          :review_findings review_findings
          :review_reason review_reason
          :model model
          :effort effort))))

  (defworkflow after-plan
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (relevant_paths List[String])
     (constraints List[String])
     (risks List[String])
     (steps List[String])
     (acceptance_checks List[String])
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((review
             (call guarded-plan-review
               :task_path task_path
               :control_path control_path
               :controller_script controller_script
               :relevant_paths relevant_paths
               :constraints constraints
               :risks risks
               :steps steps
               :acceptance_checks acceptance_checks
               :model model
               :effort effort)))
      (if review.unchanged
        (call after-first-plan-review
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :relevant_paths relevant_paths
          :constraints constraints
          :risks risks
          :steps steps
          :acceptance_checks acceptance_checks
          :review_decision review.decision
          :review_rationale review.rationale
          :review_findings review.findings
          :review_reason review.reason
          :model model
          :effort effort)
        PilotOutcome.PROTOCOL_FAILURE)))

  (defworkflow after-discovery
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (relevant_paths List[String])
     (constraints List[String])
     (risks List[String])
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((plan
             (call guarded-plan
               :task_path task_path
               :control_path control_path
               :controller_script controller_script
               :relevant_paths relevant_paths
               :constraints constraints
               :risks risks
               :model model
               :effort effort)))
      (if plan.unchanged
        (call after-plan
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :relevant_paths relevant_paths
          :constraints constraints
          :risks risks
          :steps plan.steps
          :acceptance_checks plan.acceptance_checks
          :model model
          :effort effort)
        PilotOutcome.PROTOCOL_FAILURE)))

  (defworkflow run-task
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((discovery
             (call guarded-discover
               :task_path task_path
               :control_path control_path
               :controller_script controller_script
               :model model
               :effort effort)))
      (if discovery.unchanged
        (call after-discovery
          :task_path task_path
          :control_path control_path
          :controller_script controller_script
          :relevant_paths discovery.relevant_paths
          :constraints discovery.constraints
          :risks discovery.risks
          :model model
          :effort effort)
        PilotOutcome.PROTOCOL_FAILURE))))
