(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule best_of_n)
  (import common :only (Change Outcome))
  (export run)

  ;; The coder writes N=2 independent proposals as planning text (no edits);
  ;; the judge selects one; the coder implements the selected proposal in the
  ;; single repo (ported from experiments/orc_vs_single_call/workflows/best_of_n.orc,
  ;; which ran one implementation per repository copy).

  (defrecord Proposal (approach String))

  (defrecord Selection
    (winner Int)
    (reason String))

  (defprompt propose-prompt
    (:fills (task :text) (repo :text) (label :text))
    -> Proposal
    "You are writing proposal {label} of 2 for this change to the git repository at {repo}. Read the code; change no files. Describe one approach: the root cause, the files and functions to change, and how the change holds beyond the reported case.\n\nTask: {task}\n\nReport `approach`: the proposal as plain text.")

  (defprompt select-prompt
    (:fills (intent :text) (repo :text) (first :text) (second :text))
    -> Selection
    "Two engineers independently proposed how to make the same change in the git repository at {repo}. Read the code the proposals touch; change nothing. Choose the proposal to implement.\nIntended change: {intent}\nProposal 1:\n{first}\n\nProposal 2:\n{second}\n\nJudge four things: (1) the root cause is fixed, not the symptom silenced; (2) no existing validation or guarantee is weakened and nothing changes outside the intended scope; (3) the change holds beyond the reported case; (4) it sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones.\nReport `winner`: 1 or 2. `reason`: one paragraph.")

  (defprompt implement-prompt
    (:fills (task :text) (repo :text) (approach :text))
    -> Change
    "Work in the git repository at {repo} and nowhere else. Implement this change there following the selected proposal:\n\n{task}\n\nSelected proposal:\n{approach}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.")

  (defworkflow run
    ((task String)
     (intent String)
     (repo String))
    -> Outcome
    (let* ((proposals (list/map-effect ((label (list "1" "2"))) :max 2
                        (provider-result providers.coder
                          :prompt (propose-prompt :task task :repo repo :label label)
                          :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 5400)))
           (first (or-else (list/head proposals) (record Proposal :approach "")))
           (second (or-else (list/head (list/rest proposals)) (record Proposal :approach "")))
           (selection (provider-result providers.judge
                        :prompt (select-prompt :intent intent :repo repo
                                  :first first.approach :second second.approach)
                        :model "gpt-6-sol" :effort "high" :timeout-sec 5400))
           (chosen (if (= selection.winner 2) second first))
           (change (provider-result providers.coder
                     :prompt (implement-prompt :task task :repo repo :approach chosen.approach)
                     :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 5400)))
      (variant Outcome DONE :summary change.summary)))
)
