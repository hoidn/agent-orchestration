(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule control/review_once)
  (export review-once)

  (defpath ReviewReport
    :kind relpath
    :under "artifacts/review"
    :must-exist true)

  (defunion Review
    (APPROVE (report ReviewReport) (notes List[String]))
    (REQUEST_CHANGES (report ReviewReport) (summary String) (findings List[String]))
    (WRONG_APPROACH (report ReviewReport) (reason String))
    (NEEDS_HUMAN (question String)))

  (defprompt review-prompt
    (:fills (repo :text) (intent :text) (account :text) (replies :text))
    -> Review
    "Review the uncommitted changes in the git repository at {repo} for code and architecture quality. Read the code; change nothing except your report and result files.\nIntended change: {intent}\nThe author's account of the change, including what was tried and discarded: {account}\nThe author's replies to earlier findings: {replies}\nJudge four things: (1) the root cause is fixed, not the symptom silenced; (2) no existing validation or guarantee is weakened and nothing changes outside the intended scope; (3) the change holds beyond the reported case; (4) it sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones.\nAPPROVE if you would merge it as is, and list anything that does not block merging as notes. REQUEST_CHANGES only for defects that must be fixed before merging, each naming the input or scenario that goes wrong; drop a finding the author has answered. WRONG_APPROACH if the design itself must change. NEEDS_HUMAN if the decision is not yours. Write your review to a report file.")

  (defworkflow review-once
    ((repo String)
     (intent String)
     (account String)
     (replies String))
    -> Review
    (provider-result providers.reviewer
      :prompt (review-prompt
                :repo repo
                :intent intent
                :account account
                :replies replies)
      :model "gpt-5.6-terra"
      :effort "high"
      :timeout-sec 5400))
)
