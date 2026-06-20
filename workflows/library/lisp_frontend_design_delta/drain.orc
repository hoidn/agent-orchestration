(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/drain)
  (import std/drain :only (DrainResult backlog-drain))
  (import std/resource :only (StateExisting))
  (import lisp_frontend_design_delta/design_gap_architect :only (ArchitectureTargets))
  (import lisp_frontend_design_delta/stdlib_adapters :only
    (draft-design-gap-stdlib project-drain-result-compat select-next-work-stdlib))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc DesignDeltaDrainCtx ProgressLedger StateFile
      StateFileExisting SteeringDoc TargetDesignDoc WorkReport))
  (import lisp_frontend_design_delta/work_item :only (run-selected-item-stdlib))
  (export drain)

  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))

  (defworkflow drain
    ((run RunCtx)
     (steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (manifest_path StateFileExisting)
     (progress_ledger_path ProgressLedger)
     (run_state_path StateExisting)
     (architecture_bundle_path StateFile)
     (architecture_targets ArchitectureTargets)
     (existing_architecture_index_path WorkReport))
    -> lisp_frontend_design_delta/types/DrainResult
    (:publish
      ((DONE :as drain-summary)
       (BLOCKED :as drain-summary)
       (EXHAUSTED :as drain-summary)))
    (let* ((ctx
             (record DesignDeltaDrainCtx
               :run run
               :state-root run.state-root
               :manifest manifest_path
               :ledger run.state-root
               :steering_path steering_path
               :target_design_path target_design_path
               :baseline_design_path baseline_design_path
               :progress_ledger_path progress_ledger_path
               :run_state_path run_state_path
               :existing_architecture_index_path existing_architecture_index_path))
           (terminal
             (backlog-drain design-delta
               :ctx ctx
               :selector select-next-work-stdlib
               :run-item run-selected-item-stdlib
               :gap-drafter draft-design-gap-stdlib
               :max-iterations 3))
           (projected
             (project-drain-result-compat
               ctx.run_state_path
               terminal)))
      projected)))
