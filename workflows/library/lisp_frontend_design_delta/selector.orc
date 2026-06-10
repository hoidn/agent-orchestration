(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/selector)
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc SelectionBundlePath SteeringDoc TargetDesignDoc WorkReport))
  (export select-next-work)

  (defrecord SelectorInputs
    (steering SteeringDoc)
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (manifest WorkReport)
    (progress_ledger WorkReport)
    (run_state WorkReport))

  (defrecord SelectionDecision
    (selection_status String))

  (defrecord SelectorPublicResult
    (selection_status String)
    (selection_bundle_path SelectionBundlePath))

  (defworkflow select-next-work
    ((steering SteeringDoc)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (manifest WorkReport)
     (progress_ledger WorkReport)
     (run_state WorkReport))
    -> SelectorPublicResult
    (let* ((inputs
             (record SelectorInputs
               :steering steering
               :target_design target_design
               :baseline_design baseline_design
               :manifest manifest
               :progress_ledger progress_ledger
               :run_state run_state))
           (decision
             (provider-result providers.selector
               :prompt prompts.selector.select-next-work
               :inputs (inputs.steering
                        inputs.target_design
                        inputs.baseline_design
                        inputs.manifest
                        inputs.progress_ledger
                        inputs.run_state)
               :returns SelectionDecision))
           (selection-bundle-path
             (provider-bundle-path decision :as SelectionBundlePath)))
      (record SelectorPublicResult
        :selection_status decision.selection_status
        :selection_bundle_path selection-bundle-path))))
