(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/selector)
  (import std/resource :only (StateExisting))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc ProgressLedger SelectionBundlePath SelectionStatus
      StateFileExisting SteeringDoc TargetDesignDoc WorkItemBootstrapSeed))
  (export SelectorPublicResult select-next-work)

  (defrecord SelectorInputs
    (steering SteeringDoc)
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (manifest StateFileExisting)
    (progress_ledger ProgressLedger)
    (run_state StateExisting))

  (defrecord SelectorPromptSubject
    (steering SteeringDoc)
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (manifest StateFileExisting)
    (progress_ledger ProgressLedger)
    (run_state StateExisting))

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
    ((steering SteeringDoc)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (manifest StateFileExisting)
     (progress_ledger ProgressLedger)
     (run_state StateExisting))
    -> SelectorPublicResult
    (let* ((inputs
             (record SelectorInputs
               :steering steering
               :target_design target_design
               :baseline_design baseline_design
               :manifest manifest
               :progress_ledger progress_ledger
               :run_state run_state))
           (subject
             (record SelectorPromptSubject
               :steering inputs.steering
               :target_design inputs.target_design
               :baseline_design inputs.baseline_design
               :manifest inputs.manifest
               :progress_ledger inputs.progress_ledger
               :run_state inputs.run_state))
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
        :work_item_bootstrap decision.work_item_bootstrap
        :is_selected decision.is_selected
        :is_design_gap decision.is_design_gap
        :is_done decision.is_done
        :is_blocked decision.is_blocked
        :blocked_reason decision.blocked_reason))))
