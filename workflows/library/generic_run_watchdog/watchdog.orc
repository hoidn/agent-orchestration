(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule generic_run_watchdog/watchdog)
  (export watchdog)

  (defenum RepairProvider codex claude_opus)
  (defenum RepairRequired YES NO)
  (defenum RecommendedRecovery NONE RESUME RELAUNCH INVESTIGATE)
  (defenum ProviderFixComplexity TRIVIAL NONTRIVIAL)
  (defenum ProviderRepairStatus
    FIXED_AND_RESUMED
    FIXED_AND_RELAUNCHED
    PLAN_WRITTEN
    BLOCKED)
  (defenum ProviderRecoveryAction RESUME RELAUNCH RESTART DECLINED)
  (defenum FixComplexity NOT_APPLICABLE TRIVIAL NONTRIVIAL)
  (defenum WatchStatus RUNNING_OK COMPLETED FAILED CRASHED STALLED UNKNOWN)
  (defenum RepairStatus
    NO_ACTION
    FIXED_AND_RESUMED
    FIXED_AND_RELAUNCHED
    PLAN_WRITTEN
    BLOCKED)
  (defenum RecoveryAction NONE RESUME RELAUNCH RESTART DECLINED)

  (defpath StateRoot :kind relpath :under "state" :must-exist false)
  (defpath ArtifactRoot :kind relpath :under "artifacts/work" :must-exist false)
  (defpath ArtifactOutputPath :kind relpath :under "artifacts/work" :must-exist false)
  (defpath ProducedStatePath :kind relpath :under "state" :must-exist true)
  (defpath ProducedArtifactPath :kind relpath :under "artifacts/work" :must-exist true)

  (defrecord WatchProbe
    (watch_bundle_path ProducedStatePath)
    (watch_status WatchStatus)
    (repair_required RepairRequired)
    (recommended_recovery RecommendedRecovery)
    (evidence_bundle_path ProducedArtifactPath)
    (repair_result_target_path ArtifactOutputPath))

  (defrecord ProviderRepairResult
    (repair_status ProviderRepairStatus)
    (fix_complexity ProviderFixComplexity)
    (recovery_action ProviderRecoveryAction)
    (repair_report_path ProducedArtifactPath)
    (plan_path String)
    (new_run_id String))

  (defunion RepairOutcome
    (NO_ACTION)
    (REPAIR
      (result ProviderRepairResult)))

  (defrecord WatchdogOutput
    (watch_status WatchStatus)
    (repair_status RepairStatus)
    (recovery_action RecoveryAction)
    (watchdog_result_path ProducedStatePath))

  (defworkflow invoke-repair
    ((repair_provider RepairProvider)
     (watch_bundle_path ProducedStatePath)
     (repair_result_target_path ArtifactOutputPath))
    -> ProviderRepairResult
    (let* ((use-codex (= repair_provider RepairProvider.codex))
           (result
             (if use-codex
               (provider-result providers.repair.codex
                 :prompt prompts.generic-run-watchdog.repair-run-failure
                 :inputs ()
                 :prompt-dependencies
                   (:required (watch_bundle_path)
                    :position prepend)
                 :model "gpt-5.4"
                 :effort "high"
                 :timeout-sec 7200
                 :returns ProviderRepairResult)
               (provider-result providers.repair.claude
                 :prompt prompts.generic-run-watchdog.repair-run-failure
                 :inputs ()
                 :prompt-dependencies
                   (:required (watch_bundle_path)
                    :position prepend)
                 :model "opus"
                 :effort "high"
                 :timeout-sec 7200
                 :returns ProviderRepairResult))))
      result))

  (defproc publish-repair-outcome
    ((outcome RepairOutcome)
     (target_run_id String)
     (state_root StateRoot)
     (repair_result_target_path ArtifactOutputPath)
     (watch_status WatchStatus)
     (repair_required RepairRequired)
     (recommended_recovery RecommendedRecovery)
     (evidence_bundle_path ProducedArtifactPath))
    -> WatchdogOutput
    :effects ((uses-command publish_run_watchdog_result))
    :lowering inline
    (match outcome
      ((NO_ACTION no-action)
       (command-result publish_run_watchdog_result
         :argv ("python"
                "workflows/library/scripts/publish_run_watchdog_result.py"
                "--repair-result-path" ""
                "--target-run-id" target_run_id
                "--watch-status" watch_status
                "--repair-required" repair_required
                "--recommended-recovery" recommended_recovery
                "--evidence-bundle-path" evidence_bundle_path
                "--repair-status" RepairStatus.NO_ACTION
                "--fix-complexity" FixComplexity.NOT_APPLICABLE
                "--recovery-action" RecoveryAction.NONE
                "--repair-report-path" ""
                "--plan-path" ""
                "--new-run-id" ""
                "--output" "${inputs.state_root}/watchdog-result.json")
         :returns WatchdogOutput))
      ((REPAIR repair)
       (let* ((provider-result repair.result)
              (status-resumed
                (= provider-result.repair_status
                   ProviderRepairStatus.FIXED_AND_RESUMED))
              (status-relaunched
                (= provider-result.repair_status
                   ProviderRepairStatus.FIXED_AND_RELAUNCHED))
              (status-plan-written
                (= provider-result.repair_status
                   ProviderRepairStatus.PLAN_WRITTEN))
              (complexity-trivial
                (= provider-result.fix_complexity
                   ProviderFixComplexity.TRIVIAL))
              (action-resume
                (= provider-result.recovery_action
                   ProviderRecoveryAction.RESUME))
              (action-relaunch
                (= provider-result.recovery_action
                   ProviderRecoveryAction.RELAUNCH))
              (action-restart
                (= provider-result.recovery_action
                   ProviderRecoveryAction.RESTART))
              (repair-status
                (if status-resumed
                  RepairStatus.FIXED_AND_RESUMED
                  (if status-relaunched
                    RepairStatus.FIXED_AND_RELAUNCHED
                    (if status-plan-written
                      RepairStatus.PLAN_WRITTEN
                      RepairStatus.BLOCKED))))
              (fix-complexity
                (if complexity-trivial
                  FixComplexity.TRIVIAL
                  FixComplexity.NONTRIVIAL))
              (recovery-action
                (if action-resume
                  RecoveryAction.RESUME
                  (if action-relaunch
                    RecoveryAction.RELAUNCH
                    (if action-restart
                      RecoveryAction.RESTART
                      RecoveryAction.DECLINED)))))
         (command-result publish_run_watchdog_result
           :argv ("python"
                  "workflows/library/scripts/publish_run_watchdog_result.py"
                  "--repair-result-path" repair_result_target_path
                  "--target-run-id" target_run_id
                  "--watch-status" watch_status
                  "--repair-required" repair_required
                  "--recommended-recovery" recommended_recovery
                  "--evidence-bundle-path" evidence_bundle_path
                  "--repair-status" repair-status
                  "--fix-complexity" fix-complexity
                  "--recovery-action" recovery-action
                  "--repair-report-path" provider-result.repair_report_path
                  "--plan-path" provider-result.plan_path
                  "--new-run-id" provider-result.new_run_id
                  "--output" "${inputs.state_root}/watchdog-result.json")
           :returns WatchdogOutput)))))

  (defworkflow watchdog
    ((target_run_id String)
     (state_root StateRoot :default "state/GENERIC-RUN-WATCHDOG")
     (evidence_root ArtifactRoot :default "artifacts/work/generic-run-watchdog")
     (repair_result_target_path ArtifactOutputPath
       :default "artifacts/work/generic-run-watchdog/repair-result.json")
     (max_stale_minutes Int :default 60)
     (repair_provider RepairProvider :default codex))
    -> WatchdogOutput
    (let* ((watch
             (command-result probe_orchestrator_run
               :argv ("python"
                      "workflows/library/scripts/probe_orchestrator_run.py"
                      "--run-id" target_run_id
                      "--output" "${inputs.state_root}/watch.json"
                      "--evidence-root" evidence_root
                      "--repair-result-target-path" repair_result_target_path
                      "--max-stale-minutes" max_stale_minutes)
               :returns WatchProbe))
           (repair-needed (= watch.repair_required RepairRequired.YES))
           (outcome
             (if repair-needed
               (let* ((repair-result
                        (call invoke-repair
                          :repair_provider repair_provider
                          :watch_bundle_path watch.watch_bundle_path
                          :repair_result_target_path repair_result_target_path)))
                 (variant RepairOutcome REPAIR
                   :result (record ProviderRepairResult
                             :repair_status repair-result.repair_status
                             :fix_complexity repair-result.fix_complexity
                             :recovery_action repair-result.recovery_action
                             :repair_report_path repair-result.repair_report_path
                             :plan_path repair-result.plan_path
                             :new_run_id repair-result.new_run_id)))
               (variant RepairOutcome NO_ACTION)))
           (published
             (publish-repair-outcome
               outcome
               target_run_id
               state_root
               repair_result_target_path
               watch.watch_status
               watch.repair_required
               watch.recommended_recovery
               watch.evidence_bundle_path)))
      published)))
