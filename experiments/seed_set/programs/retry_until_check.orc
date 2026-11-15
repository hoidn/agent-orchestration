(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule retry_until_check)
  (import common :only (Change CheckReport Outcome))
  (export run)

  ;; Up to three fresh attempts: reset the clone, implement, run the visible
  ;; check; stop at the first pass.

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why.")

  (defworkflow run
    ((task String) (intent String) (repo String) (model String) (effort String))
    -> Outcome
    (loop/recur :max 3
      :state (loop-state (attempt Int 1))
      :on-exhausted (variant Outcome BLOCKED :reason "visible check failing after three attempts")
      (fn (state)
        (let* ((reset (command-result reset-clone :argv ("python" "reset_clone.py") :returns Bool))
               (change (provider-result providers.coder
                         :prompt (implement-prompt :task task :repo repo)
                         :model model :effort effort :timeout-sec 1200))
               (report (command-result dev-check :argv ("python" "dev_check.py") :returns CheckReport)))
          (if report.passed
            (done (variant Outcome DONE :summary change.summary))
            (continue (loop-state :like state :attempt (+ state.attempt 1))))))))
)
