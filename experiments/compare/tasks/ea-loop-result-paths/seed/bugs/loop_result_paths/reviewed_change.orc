(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.32")
  (defmodule reviewed_change)
  (export reviewed-change)

  (defpath ReviewReport
    :kind relpath
    :under "artifacts/review"
    :must-exist true)

  (defrecord Change
    (summary String))

  (defunion Review
    (APPROVE (report ReviewReport))
    (REQUEST_CHANGES (report ReviewReport) (findings List[String]))
    (WRONG_APPROACH (report ReviewReport) (reason String))
    (NEEDS_HUMAN (question String)))

  (defunion Outcome
    (READY (report ReviewReport) (rounds Int))
    (ESCALATED (question String))
    (UNRESOLVED (rounds Int)))

  (defprompt implement-prompt
    (:fills (task :text))
    -> Change
    "Implement this change in the repository:\n\n{task}")

  (defprompt review-prompt
    (:fills (task :text))
    -> Review
    "Review the uncommitted changes in this repository against the task below. Write your review to a report file.\n\n{task}\n\nAPPROVE only if you would merge it as is. REQUEST_CHANGES for defects a fix can address. WRONG_APPROACH if the design itself must change. NEEDS_HUMAN if a decision is not yours to make.")

  (defprompt fix-prompt
    (:fills (task :text) (findings :value List[String]))
    -> Change
    "Address every review finding below without changing the approach.\n\nTask: {task}\n\nFindings:\n{findings}")

  (defprompt redo-prompt
    (:fills (task :text) (reason :text))
    -> Change
    "The reviewer rejected the approach. Discard the current changes and implement the task differently.\n\nTask: {task}\n\nWhy the approach was rejected: {reason}")

  (defworkflow reviewed-change
    ((task String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task))))
      (loop/recur :max 3
        :state (loop-state (round Int 1))
        :on-exhausted (variant Outcome UNRESOLVED :rounds state.round)
        (fn (state)
          (let* ((review (provider-result providers.reviewer
                           :prompt (review-prompt :task task))))
            (match review
              ((APPROVE a)
               (done (variant Outcome READY :report a.report :rounds state.round)))
              ((REQUEST_CHANGES r)
               (let* ((fix (provider-result providers.coder
                             :prompt (fix-prompt :task task :findings r.findings))))
                 (continue (loop-state :like state :round (+ state.round 1)))))
              ((WRONG_APPROACH w)
               (let* ((redo (provider-result providers.coder
                              :prompt (redo-prompt :task task :reason w.reason))))
                 (continue (loop-state :like state :round (+ state.round 1)))))
              ((NEEDS_HUMAN h)
               (done (variant Outcome ESCALATED :question h.question)))))))))
)
