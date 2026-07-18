(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule verified_iteration_drain/drain)
  (export drain)

  (defenum ProviderChoice codex claude)
  (defenum WorkerVerdict CONTINUE DONE BLOCKED_ON_USER)
  (defenum ProviderReviewDecision APPROVE FINDINGS)
  (defenum ReviewDecision APPROVE FINDINGS SKIPPED)
  (defenum DoneReviewDecision APPROVE REJECT)
  (defenum VerifyStatus GREEN RED)
  (defenum DrainStatus CONTINUE DONE BLOCKED_ON_USER STALLED)

  (defpath TargetDesignPath :kind relpath :under "docs/design" :must-exist true)
  (defpath CheckCommandsPath :kind relpath :under "workflows" :must-exist true)
  (defpath StatePath :kind relpath :under "state" :must-exist false)
  (defpath ProducedStatePath :kind relpath :under "state" :must-exist true)
  (defpath ArtifactWorkPath :kind relpath :under "artifacts/work" :must-exist false)
  (defpath DrainSummaryPath :kind relpath :under "artifacts/work" :must-exist true)

  (defrecord PrepareResult
    (base_sha String)
    (work_order_path ProducedStatePath))
  (defrecord ChecksResult
    (verify_status VerifyStatus)
    (commits_landed Bool)
    (checks_log_path ProducedStatePath)
    (review_package_path ProducedStatePath))
  (defrecord RecordResult
    (drain_status DrainStatus)
    (drain_summary_path DrainSummaryPath))
  (defrecord DrainLoopState
    (iteration Int)
    (drain_status DrainStatus)
    (drain_summary_path DrainSummaryPath)
    (ledger_path ArtifactWorkPath))
  (defrecord DrainOutput
    (drain_status DrainStatus)
    (drain_summary_path DrainSummaryPath))
  (defunion DrainLoopOutput
    (TERMINAL
      (drain_status DrainStatus)
      (drain_summary_path DrainSummaryPath))
    (EXHAUSTED
      (drain_status DrainStatus)
      (drain_summary_path DrainSummaryPath)
      (reason String)))

  (defworkflow invoke-worker
    ((provider_choice ProviderChoice)
     (model String)
     (effort String)
     (work_order_path ProducedStatePath)
     (target_design_path TargetDesignPath)
     (ledger_path ArtifactWorkPath))
    -> WorkerVerdict
    (let* ((use-codex
             (= provider_choice ProviderChoice.codex)))
      (if use-codex
        (provider-result providers.worker.codex
          :prompt prompts.verified-iteration.work
          :inputs ()
          :prompt-dependencies
            (:required (work_order_path target_design_path ledger_path)
             :position prepend)
          :model model
          :effort effort
          :timeout-sec 7200
          :returns WorkerVerdict)
        (provider-result providers.worker.claude
          :prompt prompts.verified-iteration.work
          :inputs ()
          :prompt-dependencies
            (:required (work_order_path target_design_path ledger_path)
             :position prepend)
          :model model
          :effort effort
          :timeout-sec 7200
          :returns WorkerVerdict))))

  (defworkflow invoke-iteration-review-provider
    ((provider_choice ProviderChoice)
     (model String)
     (effort String)
     (work_order_path ProducedStatePath)
     (review_package_path ProducedStatePath)
     (target_design_path TargetDesignPath)
     (ledger_path ArtifactWorkPath))
    -> ProviderReviewDecision
    (let* ((use-codex
             (= provider_choice ProviderChoice.codex)))
      (if use-codex
        (provider-result providers.reviewer.codex
          :prompt prompts.verified-iteration.review-iteration
          :inputs ()
          :prompt-dependencies
            (:required (work_order_path review_package_path target_design_path ledger_path)
             :position prepend)
          :model model
          :effort effort
          :timeout-sec 1800
          :returns ProviderReviewDecision)
        (provider-result providers.reviewer.claude
          :prompt prompts.verified-iteration.review-iteration
          :inputs ()
          :prompt-dependencies
            (:required (work_order_path review_package_path target_design_path ledger_path)
             :position prepend)
          :model model
          :effort effort
          :timeout-sec 1800
          :returns ProviderReviewDecision))))

  (defworkflow map-provider-review-decision
    ((provider_decision ProviderReviewDecision))
    -> ReviewDecision
    (let* ((approved
             (= provider_decision ProviderReviewDecision.APPROVE)))
      (if approved
        ReviewDecision.APPROVE
        ReviewDecision.FINDINGS)))

  (defworkflow invoke-and-map-iteration-review
    ((provider_choice ProviderChoice)
     (model String)
     (effort String)
     (work_order_path ProducedStatePath)
     (review_package_path ProducedStatePath)
     (target_design_path TargetDesignPath)
     (ledger_path ArtifactWorkPath))
    -> ReviewDecision
    (let* ((provider-decision
             (call invoke-iteration-review-provider
               :provider_choice provider_choice
               :model model
               :effort effort
               :work_order_path work_order_path
               :review_package_path review_package_path
               :target_design_path target_design_path
               :ledger_path ledger_path)))
      (call map-provider-review-decision
        :provider_decision provider-decision)))

  (defworkflow invoke-iteration-review
    ((provider_choice ProviderChoice)
     (model String)
     (effort String)
     (verify_status VerifyStatus)
     (commits_landed Bool)
     (work_order_path ProducedStatePath)
     (review_package_path ProducedStatePath)
     (target_design_path TargetDesignPath)
     (ledger_path ArtifactWorkPath))
    -> ReviewDecision
    (let* ((ready
             (and (= verify_status VerifyStatus.GREEN)
                  commits_landed)))
      (if ready
        (call invoke-and-map-iteration-review
          :provider_choice provider_choice
          :model model
          :effort effort
          :work_order_path work_order_path
          :review_package_path review_package_path
          :target_design_path target_design_path
          :ledger_path ledger_path)
        ReviewDecision.SKIPPED)))

  (defworkflow invoke-done-review-provider
    ((provider_choice ProviderChoice)
     (model String)
     (effort String)
     (work_order_path ProducedStatePath)
     (target_design_path TargetDesignPath))
    -> DoneReviewDecision
    (let* ((use-codex
             (= provider_choice ProviderChoice.codex)))
      (if use-codex
        (provider-result providers.reviewer.codex
          :prompt prompts.verified-iteration.review-done
          :inputs ()
          :prompt-dependencies
            (:required (work_order_path target_design_path)
             :position prepend)
          :model model
          :effort effort
          :timeout-sec 3600
          :returns DoneReviewDecision)
        (provider-result providers.reviewer.claude
          :prompt prompts.verified-iteration.review-done
          :inputs ()
          :prompt-dependencies
            (:required (work_order_path target_design_path)
             :position prepend)
          :model model
          :effort effort
          :timeout-sec 3600
          :returns DoneReviewDecision))))

  (defworkflow invoke-done-review
    ((provider_choice ProviderChoice)
     (model String)
     (effort String)
     (worker_verdict WorkerVerdict)
     (verify_status VerifyStatus)
     (work_order_path ProducedStatePath)
     (target_design_path TargetDesignPath))
    -> DoneReviewDecision
    (let* ((ready
             (and (= worker_verdict WorkerVerdict.DONE)
                  (= verify_status VerifyStatus.GREEN))))
      (if ready
        (call invoke-done-review-provider
          :provider_choice provider_choice
          :model model
          :effort effort
          :work_order_path work_order_path
          :target_design_path target_design_path)
        DoneReviewDecision.REJECT)))

  (defworkflow is-terminal
    ((drain_status DrainStatus))
    -> Bool
    (or (= drain_status DrainStatus.DONE)
        (= drain_status DrainStatus.BLOCKED_ON_USER)
        (= drain_status DrainStatus.STALLED)))

  (defworkflow drain
    ((target_design_path TargetDesignPath)
     (check_commands_path CheckCommandsPath)
     (drain_state_root StatePath :default "state/VERIFIED-ITERATION-DRAIN")
     (artifact_work_root ArtifactWorkPath :default "artifacts/work/VERIFIED-ITERATION-DRAIN")
     (stall_limit String :default "3")
     (worker_provider ProviderChoice :default codex)
     (worker_model String :default "gpt-5.5")
     (worker_effort String :default "high")
     (reviewer_provider ProviderChoice :default codex)
     (reviewer_model String :default "gpt-5.5")
     (reviewer_effort String :default "high"))
    -> DrainOutput
    (let* ((loop-result
             (loop/recur
               :max 40
               :state (record DrainLoopState
                        :iteration 0
                        :drain_status DrainStatus.CONTINUE
                        :drain_summary_path
                          (__generated-relpath-seed__
                            DrainSummaryPath
                            "${inputs.artifact_work_root}/drain-summary.json"
                            "verified_iteration_drain_summary_seed")
                        :ledger_path
                          (__generated-relpath-seed__
                            ArtifactWorkPath
                            "${inputs.artifact_work_root}/ledger.md"
                            "verified_iteration_ledger_seed"))
               :on-exhausted (variant DrainLoopOutput EXHAUSTED
                               :drain_status DrainStatus.STALLED
                               :drain_summary_path state.drain_summary_path
                               :reason "max_iterations_exhausted")
               (fn (state)
                 (let* ((prepared
                          (command-result prepare_verified_iteration
                            :argv ("python"
                                   "workflows/library/scripts/prepare_verified_iteration.py"
                                   "--drain-state-root" drain_state_root
                                   "--artifact-work-root" artifact_work_root
                                   "--target-design-path" target_design_path
                                   "--check-commands-path" check_commands_path
                                   "--iteration" state.iteration
                                   "--output" "${inputs.drain_state_root}/iterations/${loop.index}/work-order.json")
                            :returns PrepareResult))
                        (worker-verdict
                          (call invoke-worker
                            :provider_choice worker_provider
                            :model worker_model
                            :effort worker_effort
                            :work_order_path prepared.work_order_path
                            :target_design_path target_design_path
                            :ledger_path state.ledger_path))
                        (checks
                          (command-result run_verified_iteration_checks
                            :argv ("python"
                                   "workflows/library/scripts/run_verified_iteration_checks.py"
                                   "--check-commands-path" check_commands_path
                                   "--base-sha" prepared.base_sha
                                   "--iteration-dir" "${inputs.drain_state_root}/iterations/${loop.index}"
                                   "--output" "${inputs.drain_state_root}/iterations/${loop.index}/checks-result.json")
                            :returns ChecksResult))
                        (review-decision
                          (call invoke-iteration-review
                            :provider_choice reviewer_provider
                            :model reviewer_model
                            :effort reviewer_effort
                            :verify_status checks.verify_status
                            :commits_landed checks.commits_landed
                            :work_order_path prepared.work_order_path
                            :review_package_path checks.review_package_path
                            :target_design_path target_design_path
                            :ledger_path state.ledger_path))
                        (done-review-decision
                          (call invoke-done-review
                            :provider_choice reviewer_provider
                            :model reviewer_model
                            :effort reviewer_effort
                            :worker_verdict worker-verdict
                            :verify_status checks.verify_status
                            :work_order_path prepared.work_order_path
                            :target_design_path target_design_path))
                        (recorded
                          (command-result record_verified_iteration
                            :argv ("python"
                                   "workflows/library/scripts/record_verified_iteration.py"
                                   "--iteration" state.iteration
                                   "--base-sha" prepared.base_sha
                                   "--worker-verdict" worker-verdict
                                   "--review-decision" review-decision
                                   "--done-review-decision" done-review-decision
                                   "--checks-result-path" "${inputs.drain_state_root}/iterations/${loop.index}/checks-result.json"
                                   "--review-decision-path" "${inputs.drain_state_root}/iterations/${loop.index}/review-decision.txt"
                                   "--done-review-decision-path" "${inputs.drain_state_root}/iterations/${loop.index}/done-review-decision.txt"
                                   "--worker-verdict-path" "${inputs.drain_state_root}/iterations/${loop.index}/worker-verdict.txt"
                                   "--worker-note-path" "${inputs.drain_state_root}/iterations/${loop.index}/worker-note.txt"
                                   "--blocked-notes-dir" "${inputs.artifact_work_root}/blocked"
                                   "--ledger-path" state.ledger_path
                                   "--statuses-path" "${inputs.drain_state_root}/statuses.txt"
                                   "--stall-limit" stall_limit
                                   "--summary-path" "${inputs.artifact_work_root}/drain-summary.json"
                                   "--drain-status-path" "${inputs.drain_state_root}/iterations/${loop.index}/drain-status.txt")
                            :returns RecordResult))
                        (terminal
                          (call is-terminal
                            :drain_status recorded.drain_status)))
                   (if terminal
                     (done (variant DrainLoopOutput TERMINAL
                             :drain_status recorded.drain_status
                             :drain_summary_path recorded.drain_summary_path))
                     (continue (record DrainLoopState
                                 :iteration (+ state.iteration 1)
                                 :drain_status recorded.drain_status
                                 :drain_summary_path recorded.drain_summary_path
                                 :ledger_path state.ledger_path))))))))
      (match loop-result
        ((TERMINAL terminal)
         (record DrainOutput
           :drain_status terminal.drain_status
           :drain_summary_path terminal.drain_summary_path))
        ((EXHAUSTED exhausted)
         (record DrainOutput
           :drain_status exhausted.drain_status
           :drain_summary_path exhausted.drain_summary_path))))))
