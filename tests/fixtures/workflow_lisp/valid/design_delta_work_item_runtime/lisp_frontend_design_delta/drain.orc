(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/drain)
  (import std/context :only (RunCtx))
  (import std/drain :only (DrainResult backlog-drain))
  (import std/resource :only (BlockerClass))
  (import lisp_frontend_design_delta/design_gap_architect :only (ArchitectureTargets))
  (import lisp_frontend_design_delta/projections :only
    (project-parent-drain-terminal project-parent-drain-terminal-status))
  (import lisp_frontend_design_delta/stdlib_adapters :only
    (draft-design-gap-stdlib select-next-work-stdlib))
  (import lisp_frontend_design_delta/transitions :only (record-drain-terminal-outcome-stdlib))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc DesignDeltaDrainCtx ProgressLedger StateFile StateFileExisting
      SteeringDoc TargetDesignDoc WorkReport))
  (import lisp_frontend_design_delta/work_item :only (run-selected-item-stdlib))
  (export drain)

  (defrecord DrainRuntimeOwned
    (run RunCtx))

  (defworkflow build-drain-runtime-owned
    ((run RunCtx))
    -> DrainRuntimeOwned
    (record DrainRuntimeOwned
      :run (record RunCtx
             :run-id run.run-id
             :state-root run.state-root
             :artifact-root run.artifact-root)))

  (defworkflow drain
    ((steering_path SteeringDoc)
     (target_design_path TargetDesignDoc)
     (baseline_design_path BaselineDesignDoc)
     (manifest_path StateFileExisting)
     (progress_ledger_path ProgressLedger)
     (architecture_bundle_path StateFile)
     (architecture_targets ArchitectureTargets)
     (existing_architecture_index_path WorkReport))
    -> lisp_frontend_design_delta/types/DrainResult
    (:publish
      ((DONE :as drain-summary)
       (BLOCKED :as drain-summary)
       (EXHAUSTED :as drain-summary)))
    (let* ((ignored-architecture-bundle-path
             architecture_bundle_path)
           (ignored-architecture-targets
             architecture_targets)
           (runtime-owned
             (call build-drain-runtime-owned))
           (ctx
             (record DesignDeltaDrainCtx
               :run runtime-owned.run
               :state-root runtime-owned.run.state-root
               :manifest manifest_path
               :ledger runtime-owned.run.state-root
               :steering_path steering_path
               :target_design_path target_design_path
               :baseline_design_path baseline_design_path
               :progress_ledger_path progress_ledger_path
               :existing_architecture_index_path existing_architecture_index_path))
           (terminal
             (backlog-drain design-delta
               :ctx ctx
               :selector select-next-work-stdlib
               :run-item run-selected-item-stdlib
               :gap-drafter draft-design-gap-stdlib
               :max-iterations 3))
           (terminal-status
             (project-parent-drain-terminal-status terminal))
           (recorded-summary
             (record-drain-terminal-outcome-stdlib
               terminal-status.status
               terminal-status.reason))
           (ignored recorded-summary)
           (projected
           (project-parent-drain-terminal terminal)))
      projected)))
