(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/design_gap_architect)
  (import std/resource :only (WorkReport))
  (import lisp_frontend_design_delta/types :only
    (BaselineDesignDoc CheckCommandsTargetPath DesignDeltaGapPayload PlanDocTarget
      ProgressLedger SteeringDoc TargetDesignDoc WorkItemBootstrapSeed
      WorkReportTarget))
  (export
    ArchitectureTargets
    ArchitectureValidationDecision
    DraftArchitectureDecision
    draft-design-gap-architecture
    draft-design-gap-architecture-stdlib
    project-design-gap-architecture-targets
    project-design-gap-architecture-targets-stdlib
    validate-design-gap-architecture
    validate-design-gap-architecture-stdlib)

  (defpath CommandAdapterContractDoc
    :kind relpath
    :under "docs/design"
    :must-exist true)

  (defpath DraftBundleTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defpath ArchitectureValidationBundleTarget
    :kind relpath
    :under "artifacts/work"
    :must-exist false)

  (defpath ArchitectureTargetsViewTarget
    :kind relpath
    :under "state"
    :must-exist false)

  (defrecord ArchitectureTargets
    (design_gap_id String)
    (architecture_path PlanDocTarget)
    (work_item_context_path WorkReportTarget)
    (check_commands_path CheckCommandsTargetPath)
    (plan_target_path PlanDocTarget))

  (defrecord DesignGapArchitecturePromptSubject
    (steering SteeringDoc)
    (target_design TargetDesignDoc)
    (baseline_design BaselineDesignDoc)
    (command_adapter_contract_doc String)
    (progress_ledger ProgressLedger)
    (design_gap_id String)
    (existing_architecture_index lisp_frontend_design_delta/types/WorkReport))

  (defrecord DesignGapArchitectureProviderTargets
    (architecture_path PlanDocTarget)
    (work_item_context_path WorkReportTarget)
    (check_commands_path CheckCommandsTargetPath)
    (plan_target_path PlanDocTarget)
    (draft_bundle_path String))

  (defrecord DesignGapArchitectureRequest
    (subject DesignGapArchitecturePromptSubject)
    (targets DesignGapArchitectureProviderTargets))

  (defrecord DraftArchitectureDecision
    (draft_status String))

  (defrecord ArchitectureValidationDecision
    (architecture_validation_status String)
    (work_item_bundle_path std/resource/WorkReport))

  (defworkflow project-design-gap-architecture-targets
    ((design_gap_bootstrap WorkItemBootstrapSeed))
    -> ArchitectureTargets
    (let* ((work-item-context-view-target
             (__generated-relpath-seed__
               WorkReportTarget
               "artifacts/work/runtime_work_item_context.md"
               "design_gap_work_item_context_view_target"))
           (check-commands-target
             (__generated-relpath-seed__
               CheckCommandsTargetPath
               "state/runtime_work_item/check_commands.json"
               "design_gap_check_commands_target")))
      (record ArchitectureTargets
        :design_gap_id design_gap_bootstrap.work_item_id
        :architecture_path design_gap_bootstrap.architecture_path
        :work_item_context_path work-item-context-view-target
        :check_commands_path check-commands-target
        :plan_target_path design_gap_bootstrap.plan_target_path)))

  (defworkflow project-design-gap-architecture-targets-stdlib
    ((gap DesignDeltaGapPayload))
    -> ArchitectureTargets
    (let* ((work-item-context-view-target
             (__generated-relpath-seed__
               WorkReportTarget
               "artifacts/work/runtime_work_item_context.md"
               "design_gap_work_item_context_view_target"))
           (check-commands-target
             (__generated-relpath-seed__
               CheckCommandsTargetPath
               "state/runtime_work_item/check_commands.json"
               "design_gap_check_commands_target")))
      (record ArchitectureTargets
        :design_gap_id gap.work_item_id
        :architecture_path gap.architecture_path
        :work_item_context_path work-item-context-view-target
        :check_commands_path check-commands-target
        :plan_target_path gap.plan_target_path)))

  (defworkflow draft-design-gap-architecture
    ((steering SteeringDoc)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (progress_ledger ProgressLedger)
     (design_gap_bootstrap WorkItemBootstrapSeed)
     (existing_architecture_index lisp_frontend_design_delta/types/WorkReport))
    -> DraftArchitectureDecision
    (let* ((architecture-targets
             (call project-design-gap-architecture-targets
               :design_gap_bootstrap design_gap_bootstrap))
           (subject
             (record DesignGapArchitecturePromptSubject
               :steering steering
               :target_design target_design
               :baseline_design baseline_design
               :command_adapter_contract_doc "docs/design/workflow_command_adapter_contract.md"
               :progress_ledger progress_ledger
               :design_gap_id design_gap_bootstrap.work_item_id
               :existing_architecture_index existing_architecture_index))
           (targets
             (record DesignGapArchitectureProviderTargets
               :architecture_path architecture-targets.architecture_path
               :work_item_context_path architecture-targets.work_item_context_path
               :check_commands_path architecture-targets.check_commands_path
               :plan_target_path architecture-targets.plan_target_path
               :draft_bundle_path "artifacts/work/draft_architecture_bundle.json"))
           (request
             (record DesignGapArchitectureRequest
               :subject subject
               :targets targets)))
      (provider-result providers.architect.draft
        :prompt prompts.architect.draft
        :inputs (request)
        :returns DraftArchitectureDecision)))

  (defworkflow draft-design-gap-architecture-stdlib
    ((steering SteeringDoc)
     (target_design TargetDesignDoc)
     (baseline_design BaselineDesignDoc)
     (progress_ledger ProgressLedger)
     (gap DesignDeltaGapPayload)
     (existing_architecture_index lisp_frontend_design_delta/types/WorkReport))
    -> DraftArchitectureDecision
    (let* ((architecture-targets
             (call project-design-gap-architecture-targets-stdlib
               :gap gap))
           (subject
             (record DesignGapArchitecturePromptSubject
               :steering steering
               :target_design target_design
               :baseline_design baseline_design
               :command_adapter_contract_doc "docs/design/workflow_command_adapter_contract.md"
               :progress_ledger progress_ledger
               :design_gap_id gap.work_item_id
               :existing_architecture_index existing_architecture_index))
           (targets
             (record DesignGapArchitectureProviderTargets
               :architecture_path architecture-targets.architecture_path
               :work_item_context_path architecture-targets.work_item_context_path
               :check_commands_path architecture-targets.check_commands_path
               :plan_target_path architecture-targets.plan_target_path
               :draft_bundle_path "artifacts/work/draft_architecture_bundle.json"))
           (request
             (record DesignGapArchitectureRequest
               :subject subject
               :targets targets)))
      (provider-result providers.architect.draft
        :prompt prompts.architect.draft
        :inputs (request)
        :returns DraftArchitectureDecision)))

  (defworkflow validate-design-gap-architecture
    ((design_gap_bootstrap WorkItemBootstrapSeed))
    -> ArchitectureValidationDecision
    (let* ((architecture-targets
             (call project-design-gap-architecture-targets
               :design_gap_bootstrap design_gap_bootstrap))
           (architecture-targets-view-target
             (__generated-relpath-seed__
               ArchitectureTargetsViewTarget
               "state/design_gap_architecture_targets.json"
               "design_gap_architecture_targets_view"))
           (architecture-targets-view
             (materialize-view design-gap-architecture-targets-view
               :value architecture-targets
               :renderer canonical-json
               :renderer-version 1
               :target architecture-targets-view-target
               :returns ArchitectureTargetsViewTarget)))
      (command-result validate_lisp_frontend_design_gap_architecture
        :argv ("python"
               "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py"
               "--draft-bundle-path"
               "artifacts/work/draft_architecture_bundle.json"
               "--architecture-targets-path"
               architecture-targets-view
               "--output"
               "artifacts/work/architecture_validation_bundle.json")
        :returns ArchitectureValidationDecision)))
  (defworkflow validate-design-gap-architecture-stdlib
    ((gap DesignDeltaGapPayload))
    -> ArchitectureValidationDecision
    (let* ((architecture-targets
             (call project-design-gap-architecture-targets-stdlib
               :gap gap))
           (architecture-targets-view-target
             (__generated-relpath-seed__
               ArchitectureTargetsViewTarget
               "state/design_gap_architecture_targets.json"
               "design_gap_architecture_targets_view"))
           (architecture-targets-view
             (materialize-view design-gap-architecture-targets-view
               :value architecture-targets
               :renderer canonical-json
               :renderer-version 1
               :target architecture-targets-view-target
               :returns ArchitectureTargetsViewTarget)))
      (command-result validate_lisp_frontend_design_gap_architecture
        :argv ("python"
               "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py"
               "--draft-bundle-path"
               "artifacts/work/draft_architecture_bundle.json"
               "--architecture-targets-path"
               architecture-targets-view
               "--output"
               "artifacts/work/architecture_validation_bundle.json")
        :returns ArchitectureValidationDecision)))
)
