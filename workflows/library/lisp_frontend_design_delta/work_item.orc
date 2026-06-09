(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/work_item)
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc PlanDoc TargetDesignDoc WorkReport WorkReportTarget))
  (export classify-work-item-terminal classify-blocked-implementation-recovery)

  (defrecord WorkItemTerminalClassification
    (terminal_route String)
    (block_reason String))

  (defrecord BlockedImplementationRecoveryClassification
    (blocked_recovery_route String)
    (reason String)
    (summary String))

  (defworkflow classify-work-item-terminal
    ((plan_review_decision String)
     (implementation_state_bundle WorkReport)
     (implementation_review_decision_path WorkReport)
     (work_item_source String)
     (terminal_route_target WorkReportTarget))
    -> WorkItemTerminalClassification
    (command-result classify_lisp_frontend_work_item_terminal
      :argv ("python"
             "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py"
             "--plan-review-decision"
             plan_review_decision
             "--implementation-state-path"
             implementation_state_bundle
             "--implementation-review-decision-path"
             implementation_review_decision_path
             "--implementation-bundle-path"
             implementation_state_bundle
             "--work-item-source"
             work_item_source
             "--output"
             terminal_route_target)
      :returns WorkItemTerminalClassification))

  (defworkflow classify-blocked-implementation-recovery
    ((target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (work_item_context WorkReport)
     (approved_plan PlanDoc)
     (implementation_state_bundle WorkReport)
     (progress_report WorkReport))
    -> BlockedImplementationRecoveryClassification
    (provider-result providers.work-item.recovery-classifier
      :prompt prompts.work-item.classify-blocked-recovery
      :inputs (target_design
               baseline_design
               work_item_context
               approved_plan
               implementation_state_bundle
               progress_report)
      :returns BlockedImplementationRecoveryClassification)))
