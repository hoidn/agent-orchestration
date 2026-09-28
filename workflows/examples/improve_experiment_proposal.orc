(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule improve_experiment_proposal)
  (import std/improve :only (Decision improve))
  (export run-experiment)

  ;; Draft an experiment proposal, improve it with an agent reviewer and reviser
  ;; through `std/improve`, then hand the proposal it returns to the launcher.
  ;; Compile and dry-run from the repository root:
  ;;
  ;;   python -m orchestrator run workflows/examples/improve_experiment_proposal.orc \
  ;;     --entry-workflow improve_experiment_proposal::run-experiment \
  ;;     --provider-externs-file workflows/examples/inputs/improve_experiment_proposal/providers.json \
  ;;     --prompt-externs-file workflows/examples/inputs/improve_experiment_proposal/prompts.json \
  ;;     --command-boundaries-file workflows/examples/inputs/improve_experiment_proposal/commands.json \
  ;;     --input-file workflows/examples/inputs/improve_experiment_proposal/inputs.json \
  ;;     --dry-run

  (defrecord Parameter (name String) (value Int))
  (defrecord ExperimentProposal
    (hypothesis String)
    (parameters List[Parameter]))
  (defrecord ExperimentBrief (question String))
  (defrecord ReviewNotes (notes String))
  (defrecord ReviewBlocker (issue String))
  (defrecord ExperimentRun (status String))

  (defproc propose ((brief ExperimentBrief)) -> ExperimentProposal
    :effects ()
    :lowering inline
    (record ExperimentProposal
      :hypothesis brief.question
      :parameters (list (record Parameter :name "seed" :value 0))))

  (defproc review-proposal
    ((proposal ExperimentProposal) (brief ExperimentBrief))
    -> Decision[ReviewNotes ReviewBlocker]
    :effects ((uses-provider providers.proposal.review))
    :lowering inline
    (provider-result providers.proposal.review
      :prompt prompts.proposal.review
      :inputs (brief.question proposal.hypothesis proposal.parameters)
      :returns Decision[ReviewNotes ReviewBlocker]))

  (defproc revise-proposal
    ((proposal ExperimentProposal) (brief ExperimentBrief) (review ReviewNotes))
    -> ExperimentProposal
    :effects ((uses-provider providers.proposal.revise))
    :lowering inline
    (provider-result providers.proposal.revise
      :prompt prompts.proposal.revise
      :inputs (brief.question proposal.hypothesis proposal.parameters review.notes)
      :returns ExperimentProposal))

  ;; The workspace's launcher runs an approved proposal and records any other.
  (defproc execute
    ((proposal ExperimentProposal) (outcome String) (note String))
    -> ExperimentRun
    :effects ((uses-command launch_experiment))
    :lowering inline
    (command-result launch_experiment
      :argv ("python" "scripts/launch_experiment.py"
             "--outcome" outcome
             "--note" note
             "--hypothesis" proposal.hypothesis
             "--parameters" proposal.parameters)
      :returns ExperimentRun))

  (defworkflow run-experiment ((question String)) -> ExperimentRun
    (let* ((brief (record ExperimentBrief :question question))
           (result (improve (propose brief) brief
                            (proc-ref review-proposal)
                            (proc-ref revise-proposal)
                            3)))
      (match result
        ((APPROVED approved) (execute approved.value "approved" approved.evidence.notes))
        ((BLOCKED blocked) (execute blocked.value "blocked" blocked.reason.issue))
        ((EXHAUSTED exhausted) (execute exhausted.value "exhausted" ""))))))
