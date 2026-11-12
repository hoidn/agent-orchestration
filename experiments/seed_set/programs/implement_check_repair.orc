(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule implement_check_repair)
  (import common :only (Change CheckReport Outcome))
  (export run)

  ;; Implement, run the visible check, and on failure repair in place with the
  ;; check output; at most two repairs.

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why.")

  (defprompt repair-prompt
    (:fills (task :text) (repo :text) (excerpt :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Your change for the task below fails its check. Fix the cause.\n\nTask: {task}\n\nCheck output:\n{excerpt}\n\nReport two things. `summary`: one sentence. `account`: the state of the whole change now.")

  (defworkflow run
    ((task String) (intent String) (repo String) (model String) (effort String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo)
                     :model model :effort effort :timeout-sec 1200)))
      (loop/recur :max 3
        :state (loop-state (round Int 1) (summary String change.summary))
        :on-exhausted (variant Outcome BLOCKED :reason "round limit reached")
        (fn (state)
          (let* ((report (command-result dev-check :argv ("python" "dev_check.py") :returns CheckReport)))
            (if report.passed
              (done (variant Outcome DONE :summary state.summary))
              (if (= state.round 3)
                (done (variant Outcome BLOCKED :reason "visible check failing after two repairs"))
                (let* ((repair (provider-result providers.coder
                                 :prompt (repair-prompt :task task :repo repo :excerpt report.excerpt)
                                 :model model :effort effort :timeout-sec 1200)))
                  (continue (loop-state :like state :round (+ state.round 1) :summary repair.summary))))))))))
)
