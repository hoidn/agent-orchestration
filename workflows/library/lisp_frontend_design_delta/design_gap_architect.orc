(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/design_gap_architect)
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc SelectionBundlePath SteeringDoc TargetDesignDoc WorkReport WorkReportTarget))
  (export
    ArchitectureDocTarget
    ArchitectureTargets
    ArchitectureValidationBundleTarget
    ArchitectureValidationDecision
    CommandAdapterContractDoc
    DraftArchitectureDecision
    DraftBundleTarget
    PlanDocTarget
    draft-design-gap-architecture
    validate-design-gap-architecture)

  (defpath CommandAdapterContractDoc
    :kind relpath
    :under "docs/design"
    :must-exist true)

  (defpath ArchitectureDocTarget
    :kind relpath
    :under "docs/plans"
    :must-exist false)

  (defpath PlanDocTarget
    :kind relpath
    :under "docs/plans"
    :must-exist false)

  (defpath DraftBundleTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defpath ArchitectureValidationBundleTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defrecord ArchitectureTargets
    (design_gap_id String)
    (architecture_path ArchitectureDocTarget)
    (work_item_context_path WorkReportTarget)
    (check_commands_path WorkReportTarget)
    (plan_target_path PlanDocTarget))

  (defrecord DraftArchitectureDecision
    (draft_status String))

  (defrecord ArchitectureValidationDecision
    (architecture_validation_status String)
    (work_item_bundle_path WorkReport))

  (defworkflow draft-design-gap-architecture
    ((steering SteeringDoc)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (command_adapter_contract CommandAdapterContractDoc)
     (progress_ledger SelectionBundlePath)
     (selection_bundle SelectionBundlePath)
     (architecture_targets ArchitectureTargets)
     (existing_architecture_index WorkReport)
     (draft_bundle_target DraftBundleTarget))
    -> DraftArchitectureDecision
    (provider-result providers.architect.draft
      :prompt prompts.architect.draft
      :inputs (steering
               target_design
               baseline_design
               command_adapter_contract
               progress_ledger
               selection_bundle
               architecture_targets.architecture_path
               architecture_targets.work_item_context_path
               architecture_targets.check_commands_path
               architecture_targets.plan_target_path
               existing_architecture_index
               draft_bundle_target)
      :returns DraftArchitectureDecision))

  (defworkflow validate-design-gap-architecture
    ((draft_bundle DraftBundleTarget)
     (architecture_targets_bundle SelectionBundlePath)
     (validation_bundle_target ArchitectureValidationBundleTarget))
    -> ArchitectureValidationDecision
    (command-result validate_lisp_frontend_design_gap_architecture
      :argv ("python"
             "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py"
             "--draft-bundle-path"
             draft_bundle
             "--architecture-targets-path"
             architecture_targets_bundle
             "--output"
             validation_bundle_target)
      :returns ArchitectureValidationDecision)))
