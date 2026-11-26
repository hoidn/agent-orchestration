(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule implement_review_revise)
  (import common :only (Change Outcome))
  (export run)

  ;; Implement, one review, one revision if the review asks for changes.

  (defunion Review
    (APPROVE (notes List[String]))
    (REQUEST_CHANGES (findings List[String])))

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. This call ends after 40 minutes of wall-clock time; work that is not finished and reported by then is lost. Implement this change there:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why.")

  (defprompt review-prompt
    (:fills (repo :text) (intent :text) (account :text))
    -> Review
    "Review the uncommitted changes in the git repository at {repo}. Read the code; change nothing. This call ends after 40 minutes of wall-clock time; work that is not finished and reported by then is lost.\nIntended change: {intent}\nThe author's account: {account}\nAPPROVE if the change is correct and complete. REQUEST_CHANGES only for defects, each naming the input or scenario that goes wrong.")

  (defprompt revise-prompt
    (:fills (task :text) (repo :text) (findings :value List[String]))
    -> Change
    "Work in the git repository at {repo} and nowhere else. This call ends after 40 minutes of wall-clock time; work that is not finished and reported by then is lost. A reviewer asks for the changes below; fix each finding that is right.\n\nTask: {task}\n\nFindings:\n{findings}\n\nReport two things. `summary`: one sentence. `account`: the state of the whole change now.")

  (defworkflow run
    ((task String) (intent String) (repo String) (model String) (effort String))
    -> Outcome
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo)
                     :model model :effort effort :timeout-sec 2400))
           (review (provider-result providers.reviewer
                     :prompt (review-prompt :repo repo :intent intent :account change.account)
                     :model model :effort effort :timeout-sec 2400)))
      (match review
        ((APPROVE a) (variant Outcome DONE :summary change.summary))
        ((REQUEST_CHANGES r)
         (let* ((revision (provider-result providers.coder
                            :prompt (revise-prompt :task task :repo repo :findings r.findings)
                            :model model :effort effort :timeout-sec 2400)))
           (variant Outcome DONE :summary revision.summary))))))
)
