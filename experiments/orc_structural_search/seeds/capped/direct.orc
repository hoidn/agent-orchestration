(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule direct)
  (import common :only (Change Outcome))
  (export run)

  ;; One coder call implements the task (ported from
  ;; experiments/compare/control/direct_task.orc).

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.")

  (defworkflow run
    ((task String)
     (intent String)
     (repo String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo)
                     :model "gpt-5.6-terra"
                     :effort "medium"
                     :timeout-sec 5400)))
      (variant Outcome DONE :summary change.summary)))
)
