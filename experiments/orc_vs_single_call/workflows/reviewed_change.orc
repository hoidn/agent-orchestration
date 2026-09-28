(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.28")
  (defmodule reviewed_change)
  (export reviewed-change)

  (defpath ReviewReport
    :kind relpath
    :under "artifacts/review"
    :must-exist true)

  (defrecord Change
    (summary String)
    (account String))

  (defrecord Revision
    (summary String)
    (account String)
    (replies String))

  (defunion Review
    (APPROVE (report ReviewReport) (notes List[String]))
    (REQUEST_CHANGES (report ReviewReport) (summary String) (findings List[String]))
    (WRONG_APPROACH (report ReviewReport) (reason String))
    (NEEDS_HUMAN (question String)))

  (defunion Outcome
    (READY (report ReviewReport) (rounds Int))
    (ESCALATED (question String))
    (UNRESOLVED (reason String) (rounds Int)))

  (defprompt implement-prompt
    (:fills (task :text))
    -> Change
    "Implement this change in the repository:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.\n\nWhen you finish, write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH; that file is how your result is received.")

  (defprompt review-prompt
    (:fills (repo :text) (intent :text) (account :text) (replies :text))
    -> Review
    "Review the uncommitted changes in the git repository at {repo} for code and architecture quality. Read the code; change nothing except your report and result files.\nIntended change: {intent}\nThe author's account of the change, including what was tried and discarded: {account}\nThe author's replies to earlier findings: {replies}\nJudge four things: (1) the root cause is fixed, not the symptom silenced; (2) no existing validation or guarantee is weakened and nothing changes outside the intended scope; (3) the change holds beyond the reported case; (4) it sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones.\nAPPROVE if you would merge it as is, and list anything that does not block merging as notes. REQUEST_CHANGES only for defects that must be fixed before merging, each naming the input or scenario that goes wrong; drop a finding the author has answered. WRONG_APPROACH if the design itself must change. NEEDS_HUMAN if the decision is not yours. Write your review to a report file, then write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH.")

  (defprompt fix-prompt
    (:fills (task :text) (findings :value List[String]))
    -> Revision
    "A reviewer asks for the changes below. For each finding, either fix it, or leave it and reply why it should not be fixed: a finding can be wrong. Replace code rather than adding a second mechanism beside the first.\n\nTask: {task}\n\nFindings:\n{findings}\n\nReport three things. `summary`: one sentence. `account`: the state of the whole change now, what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover. `replies`: one paragraph for each finding you did not fix, or the word none.\n\nWhen you finish, write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH; that file is how your result is received.")

  (defprompt redo-prompt
    (:fills (task :text) (reason :text))
    -> Change
    "The reviewer rejected the approach. Discard the current changes and implement the task differently.\n\nTask: {task}\n\nWhy the approach was rejected: {reason}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.\n\nWhen you finish, write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH; that file is how your result is received.")

  (defworkflow reviewed-change
    ((task String)
     (intent String)
     (repo String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task)
                     :model "claude-sonnet-5-5"
                     :effort "medium"
                     :timeout-sec 5400)))
      (loop/recur :max 3
        :state (loop-state
                 (round Int 1)
                 (account String change.account)
                 (replies String "none"))
        :on-exhausted (variant Outcome UNRESOLVED :reason "round limit reached" :rounds state.round)
        (fn (state)
          (let* ((review (provider-result providers.reviewer
                           :prompt (review-prompt
                                     :repo repo
                                     :intent intent
                                     :account state.account
                                     :replies state.replies)
                     :model "gpt-6-sol"
                     :effort "high"
                     :timeout-sec 5400)))
            (match review
              ((APPROVE a)
               (done (variant Outcome READY :report a.report :rounds state.round)))
              ((REQUEST_CHANGES r)
               (if (= state.round 3)
                 (done (variant Outcome UNRESOLVED :reason r.summary :rounds state.round))
                 (let* ((revision (provider-result providers.coder
                                    :prompt (fix-prompt :task task :findings r.findings)
                     :model "claude-sonnet-5-5"
                     :effort "medium"
                     :timeout-sec 5400)))
                   (continue (loop-state :like state
                               :round (+ state.round 1)
                               :account revision.account
                               :replies revision.replies)))))
              ((WRONG_APPROACH w)
               (if (= state.round 3)
                 (done (variant Outcome UNRESOLVED :reason w.reason :rounds state.round))
                 (let* ((redo (provider-result providers.coder
                                :prompt (redo-prompt :task task :reason w.reason)
                     :model "claude-sonnet-5-5"
                     :effort "medium"
                     :timeout-sec 5400)))
                   (continue (loop-state :like state
                               :round (+ state.round 1)
                               :account redo.account
                               :replies "none")))))
              ((NEEDS_HUMAN h)
               (done (variant Outcome ESCALATED :question h.question)))))))))
)
