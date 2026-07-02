(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/stdlib_payloads)
  (import lisp_frontend_design_delta/selector :only (SelectorPublicResult))
  (import lisp_frontend_design_delta/types :only
    (CheckCommandsValue DesignDeltaDrainCtx DesignDeltaGapPayload
      DesignDeltaSelectedItemPayload DesignDeltaSelectionResult WorkItemBootstrapSeed))
  (export
    project-selected-item-payload
    project-selection-result)

  (defworkflow project-selected-item-payload
    ((ctx DesignDeltaDrainCtx)
     (selected_item_state_root Path.state-root)
     (work_item_bootstrap WorkItemBootstrapSeed))
    -> DesignDeltaSelectedItemPayload
    (record DesignDeltaSelectedItemPayload
      :item-id work_item_bootstrap.work_item_id
      :item-state-root selected_item_state_root
      :work_item_bootstrap (record WorkItemBootstrapSeed
                             :work_item_source work_item_bootstrap.work_item_source
                             :work_item_id work_item_bootstrap.work_item_id
                             :plan_target_path work_item_bootstrap.plan_target_path
                             :check_commands (record CheckCommandsValue
                                               :commands work_item_bootstrap.check_commands.commands)
                             :architecture_path work_item_bootstrap.architecture_path)
      :steering_path ctx.steering_path
      :target_design_path ctx.target_design_path
      :baseline_design_path ctx.baseline_design_path
      :progress_ledger_path ctx.progress_ledger_path))

  (defworkflow project-selection-result
    ((ctx DesignDeltaDrainCtx)
     (selection SelectorPublicResult))
    -> DesignDeltaSelectionResult
    (let* ((selected-payload
             (record DesignDeltaSelectedItemPayload
               :item-id selection.work_item_bootstrap.work_item_id
               :item-state-root ctx.state-root
               :work_item_bootstrap (record WorkItemBootstrapSeed
                                      :work_item_source selection.work_item_bootstrap.work_item_source
                                      :work_item_id selection.work_item_bootstrap.work_item_id
                                      :plan_target_path selection.work_item_bootstrap.plan_target_path
                                      :check_commands (record CheckCommandsValue
                                                        :commands selection.work_item_bootstrap.check_commands.commands)
                                      :architecture_path selection.work_item_bootstrap.architecture_path)
               :steering_path ctx.steering_path
               :target_design_path ctx.target_design_path
               :baseline_design_path ctx.baseline_design_path
               :progress_ledger_path ctx.progress_ledger_path))
           (design-gap-payload
             (record DesignDeltaGapPayload
               :work_item_id selection.work_item_bootstrap.work_item_id
               :plan_target_path selection.work_item_bootstrap.plan_target_path
               :architecture_path selection.work_item_bootstrap.architecture_path)))
      (if selection.is_selected
        (variant DesignDeltaSelectionResult SELECTED
          :selection selected-payload)
        (if selection.is_design_gap
          (variant DesignDeltaSelectionResult GAP
            :gap design-gap-payload)
          (if selection.is_done
            (variant DesignDeltaSelectionResult EMPTY)
            (variant DesignDeltaSelectionResult BLOCKED
              :reason selection.blocked_reason))))))
)
