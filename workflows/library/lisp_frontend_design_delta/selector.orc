(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/selector)
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc SteeringDoc TargetDesignDoc WorkReport))
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

  (defworkflow select-next-work
    ((steering SteeringDoc)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (manifest WorkReport)
     (progress_ledger WorkReport)
     (run_state WorkReport))
    -> SelectionDecision
    (let* ((inputs
             (record SelectorInputs
               :steering steering
               :target_design target_design
               :baseline_design baseline_design
               :manifest manifest
               :progress_ledger progress_ledger
               :run_state run_state)))
      (provider-result providers.selector
        :prompt prompts.selector.select-next-work
        :inputs (inputs.steering
                 inputs.target_design
                 inputs.baseline_design
                 inputs.manifest
                 inputs.progress_ledger
                 inputs.run_state)
        :returns SelectionDecision))))
