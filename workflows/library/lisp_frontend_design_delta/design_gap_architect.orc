(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/design_gap_architect)
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc SelectionBundlePath SteeringDoc TargetDesignDoc WorkReport WorkReportTarget))
  (export
    ArchitectureDocTarget
    ArchitectureTargets
    ArchitectureValidationDecision
    DraftArchitectureDecision
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
     (progress_ledger SelectionBundlePath)
     (selection_bundle SelectionBundlePath)
     (architecture_targets ArchitectureTargets)
     (existing_architecture_index WorkReport))
    -> DraftArchitectureDecision
    (provider-result providers.architect.draft
      :prompt prompts.architect.draft
      :inputs (steering
               target_design
               baseline_design
               "docs/design/workflow_command_adapter_contract.md"
               progress_ledger
               selection_bundle
               architecture_targets.architecture_path
               architecture_targets.work_item_context_path
               architecture_targets.check_commands_path
               architecture_targets.plan_target_path
               existing_architecture_index
               "artifacts/work/draft_architecture_bundle.json")
      :returns DraftArchitectureDecision))

  (defworkflow validate-design-gap-architecture
    ((architecture_targets_bundle SelectionBundlePath))
    -> ArchitectureValidationDecision
    (command-result validate_lisp_frontend_design_gap_architecture
      :argv ("python"
             "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py"
             "--draft-bundle-path"
             "artifacts/work/draft_architecture_bundle.json"
             "--architecture-targets-path"
             architecture_targets_bundle
             "--output"
             "artifacts/work/architecture_validation_bundle.json")
      :returns ArchitectureValidationDecision)))
