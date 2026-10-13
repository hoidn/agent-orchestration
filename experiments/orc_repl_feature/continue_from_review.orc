(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule continue_from_review)
  (import repl_feature :only (Plan Feedback Execution revise-plan execute-plan))
  (export run)

  ;; Continues repl_feature.orc from its committed draft plan and review: the
  ;; first run was stopped before revision to change the executor's model, and
  ;; a changed program cannot resume the old memo. Inputs are the committed
  ;; `draft` and `feedback` values of run 20261013T012339Z-9azbib.
  ;;
  ;;   python -m orchestrator compile experiments/orc_repl_feature/continue_from_review.orc \
  ;;     --source-root experiments/orc_repl_feature \
  ;;     --provider-externs-file experiments/orc_repl_feature/providers.json

  (defworkflow run
    ((task String)
     (summary String)
     (decisions List[String])
     (steps List[String])
     (verification List[String])
     (blocking List[String])
     (notes List[String]))
    -> Execution
    (let* ((revised (provider-result providers.claude :model "claude-fable-5-1" :effort "high" :timeout-sec 3600
                      :prompt (revise-plan :task task :summary summary :decisions decisions
                                           :steps steps :verification verification
                                           :blocking blocking :notes notes))))
      (provider-result providers.codex :model "gpt-6.1-sol" :effort "high" :timeout-sec 14400
        :prompt (execute-plan :task task :summary revised.summary :decisions revised.decisions
                              :steps revised.steps :verification revised.verification))))
)
