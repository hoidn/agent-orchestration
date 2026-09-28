(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.28")
  (defmodule best_of_n)
  (export best-of-n select-only)

  (defpath SelectionReport
    :kind relpath
    :under "artifacts/review"
    :must-exist true)

  (defrecord Change
    (summary String)
    (account String))

  (defrecord Selection
    (winner String)
    (ranking List[String])
    (report SelectionReport))

  (defprompt implement-prompt
    (:fills (task :text) (repo :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.\n\nWhen you finish, write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH; that file is how your result is received.")

  (defprompt select-prompt
    (:fills (intent :text) (repos :value List[String]) (accounts :value List[String]))
    -> Selection
    "Several engineers independently wrote a fix for the same bug, each in their own copy of the repository. The copies are listed below, with each author's account in the same order. Choose the one to merge.\nIntended change: {intent}\nRepositories: {repos}\nAuthors' accounts: {accounts}\nIn each repository read the uncommitted changes and the code around them; change nothing in any repository and do not base your choice on test results or on how much was written. Rate every candidate 0, 1 or 2 on each of four criteria: (1) the root cause is fixed, not the symptom silenced; (2) no existing validation or guarantee is weakened and nothing changes outside the intended scope; (3) the change holds beyond the reported case; (4) it sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones.\nCompare the candidates with each other: where two differ, decide which is right by reading the code, and rate equal flaws equally.\nReport `winner`: the repository path of the best candidate, copied exactly from the list. `ranking`: every repository path, best first, each followed by a colon and its four ratings. Write your reasoning to a report file under artifacts/review/ in your current directory, then write the required JSON result to the file whose path is in the environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH.")

  (defworkflow implement-one
    ((task String)
     (repo String))
    -> String
    (let* ((change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo)
                     :model "claude-sonnet-5-5"
                     :effort "medium"
                     :timeout-sec 5400)))
      change.account))

  (defworkflow best-of-n
    ((task String)
     (intent String)
     (repos List[String]))
    -> Selection
    (let* ((accounts (list/map-effect ((repo repos)) :max 8
                       (call implement-one :task task :repo repo)))
           (selection (provider-result providers.judge
                        :prompt (select-prompt :intent intent :repos repos :accounts accounts)
                        :model "gpt-6-sol"
                        :effort "high"
                        :timeout-sec 5400)))
      selection))

  (defworkflow select-only
    ((intent String)
     (repos List[String])
     (accounts List[String]))
    -> Selection
    (provider-result providers.judge
      :prompt (select-prompt :intent intent :repos repos :accounts accounts)
      :model "gpt-6-sol"
      :effort "high"
      :timeout-sec 5400))
)
