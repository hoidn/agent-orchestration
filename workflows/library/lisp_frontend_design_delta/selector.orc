(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/selector)
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc CheckCommandsValue DesignDeltaDrainCtx SelectionBundlePath
      SelectionStatus SteeringDoc TargetDesignDoc WorkItemBootstrapSeed))
  (export SelectorPublicResult select-next-work)

  (defrecord SelectorInputs
    (ctx DesignDeltaDrainCtx))

  (defrecord SelectorPromptSubject
    (steering SteeringDoc)
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc))

  (defrecord SelectorRequest
    (subject SelectorPromptSubject))

  (defrecord SelectorPublicResult
    (selection_status SelectionStatus)
    (selection_bundle_path SelectionBundlePath)
    (work_item_bootstrap WorkItemBootstrapSeed)
    (is_selected Bool)
    (is_design_gap Bool)
    (is_done Bool)
    (is_blocked Bool)
    (blocked_reason String))

  (defworkflow select-next-work
    ((ctx DesignDeltaDrainCtx))
    -> SelectorPublicResult
    (let* ((inputs
             (record SelectorInputs
               :ctx ctx))
           (subject
             (record SelectorPromptSubject
               :steering inputs.ctx.steering_path
               :target_design inputs.ctx.target_design_path
               :baseline_design inputs.ctx.baseline_design_path))
           (request
             (record SelectorRequest
               :subject subject))
           (decision
             (provider-result providers.selector
               :prompt prompts.selector.select-next-work
               :inputs (request)
               :returns SelectorPublicResult))
           (selection-bundle-path
             (provider-bundle-path decision :as SelectionBundlePath)))
      (record SelectorPublicResult
        :selection_status decision.selection_status
        :selection_bundle_path selection-bundle-path
        :work_item_bootstrap (record WorkItemBootstrapSeed
                               :work_item_source decision.work_item_bootstrap.work_item_source
                               :work_item_id decision.work_item_bootstrap.work_item_id
                               :plan_target_path decision.work_item_bootstrap.plan_target_path
                               :check_commands (record CheckCommandsValue
                                                 :commands decision.work_item_bootstrap.check_commands.commands)
                               :architecture_path decision.work_item_bootstrap.architecture_path)
        :is_selected decision.is_selected
        :is_design_gap decision.is_design_gap
        :is_done decision.is_done
        :is_blocked decision.is_blocked
        :blocked_reason decision.blocked_reason))))
