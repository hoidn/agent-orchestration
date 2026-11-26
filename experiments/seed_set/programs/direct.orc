(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule direct)
  (import common :only (Change Outcome))
  (export run)

  ;; One implementer call.

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. This call ends after 40 minutes of wall-clock time; work that is not finished and reported by then is lost. Implement this change there:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why.")

  (defworkflow run
    ((task String) (intent String) (repo String) (model String) (effort String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo)
                     :model model :effort effort :timeout-sec 2400)))
      (variant Outcome DONE :summary change.summary)))
)
