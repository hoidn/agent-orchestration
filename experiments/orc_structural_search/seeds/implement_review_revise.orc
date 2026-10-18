(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule implement_review_revise)
  (import common :only (Change Outcome))
  (export run)

  ;; The coder implements; the reviewer reviews; the coder revises or redoes
  ;; for at most three rounds (ported from
  ;; experiments/orc_vs_single_call/workflows/reviewed_change.orc; READY maps
  ;; to DONE, ESCALATED and UNRESOLVED map to BLOCKED).

  (defpath ReviewReport
    :kind relpath
    :under "artifacts/review"
    :must-exist true)

  (defrecord Revision
    (summary String)
    (account String)
    (replies String))

  (defunion Review
    (APPROVE (report ReviewReport) (notes List[String]))
    (REQUEST_CHANGES (report ReviewReport) (summary String) (findings List[String]))
    (WRONG_APPROACH (report ReviewReport) (reason String))
    (NEEDS_HUMAN (question String)))

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.")

  (defprompt review-prompt
    (:fills (repo :text) (intent :text) (account :text) (replies :text))
    -> Review
    "Review the uncommitted changes in the git repository at {repo} for code and architecture quality. Read the code; change nothing except your report and result files.\nIntended change: {intent}\nThe author's account of the change, including what was tried and discarded: {account}\nThe author's replies to earlier findings: {replies}\nJudge four things: (1) the root cause is fixed, not the symptom silenced; (2) no existing validation or guarantee is weakened and nothing changes outside the intended scope; (3) the change holds beyond the reported case; (4) it sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones.\nAPPROVE if you would merge it as is, and list anything that does not block merging as notes. REQUEST_CHANGES only for defects that must be fixed before merging, each naming the input or scenario that goes wrong; drop a finding the author has answered. WRONG_APPROACH if the design itself must change. NEEDS_HUMAN if the decision is not yours. Write your review to a report file.")

  (defprompt fix-prompt
    (:fills (task :text) (repo :text) (findings :value List[String]))
    -> Revision
    "Work in the git repository at {repo} and nowhere else. A reviewer asks for the changes below. For each finding, either fix it, or leave it and reply why it should not be fixed: a finding can be wrong. Replace code rather than adding a second mechanism beside the first.\n\nTask: {task}\n\nFindings:\n{findings}\n\nReport three things. `summary`: one sentence. `account`: the state of the whole change now, what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover. `replies`: one paragraph for each finding you did not fix, or the word none.")

  (defprompt redo-prompt
    (:fills (task :text) (repo :text) (reason :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. The reviewer rejected the approach. Discard the current changes and implement the task differently.\n\nTask: {task}\n\nWhy the approach was rejected: {reason}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.")

  (defworkflow run
    ((task String)
     (intent String)
     (repo String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo)
                     :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 5400)))
      (loop/recur :max 3
        :state (loop-state
                 (round Int 1)
                 (summary String change.summary)
                 (account String change.account)
                 (replies String "none"))
        :on-exhausted (variant Outcome BLOCKED :reason "round limit reached")
        (fn (state)
          (let* ((review (provider-result providers.reviewer
                           :prompt (review-prompt :repo repo :intent intent
                                     :account state.account :replies state.replies)
                           :model "gpt-6-sol" :effort "high" :timeout-sec 5400)))
            (match review
              ((APPROVE a)
               (done (variant Outcome DONE :summary state.summary)))
              ((REQUEST_CHANGES r)
               (if (= state.round 3)
                 (done (variant Outcome BLOCKED :reason r.summary))
                 (let* ((revision (provider-result providers.coder
                                    :prompt (fix-prompt :task task :repo repo :findings r.findings)
                                    :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 5400)))
                   (continue (loop-state :like state
                               :round (+ state.round 1)
                               :summary revision.summary
                               :account revision.account
                               :replies revision.replies)))))
              ((WRONG_APPROACH w)
               (if (= state.round 3)
                 (done (variant Outcome BLOCKED :reason w.reason))
                 (let* ((redo (provider-result providers.coder
                                :prompt (redo-prompt :task task :repo repo :reason w.reason)
                                :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 5400)))
                   (continue (loop-state :like state
                               :round (+ state.round 1)
                               :summary redo.summary
                               :account redo.account
                               :replies "none")))))
              ((NEEDS_HUMAN h)
               (done (variant Outcome BLOCKED :reason h.question)))))))))
)
