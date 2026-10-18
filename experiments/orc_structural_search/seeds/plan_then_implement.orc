(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule plan_then_implement)
  (import common :only (Change Outcome))
  (export run)

  ;; The planner drafts a plan; the reviewer reviews it; the planner revises
  ;; it; the coder implements the revised plan (ported from
  ;; workflows/examples/plan_review_execute.orc).

  (defrecord Plan (steps List[String]))
  (defrecord Feedback (findings List[String]))

  (defprompt draft-plan (:fills (task :text) (repo :text)) -> Plan
    "Plan this task for the git repository at {repo} as ordered steps, naming the files each step touches. Change no files.\n\nTask: {task}")
  (defprompt review-plan (:fills (intent :text) (repo :text) (steps :value List[String])) -> Feedback
    "Review this plan for the git repository at {repo}: what would make it fail or leave the intended change's scope? Change nothing.\n\nIntended change: {intent}\nPlan: {steps}")
  (defprompt revise-plan (:fills (task :text) (steps :value List[String]) (findings :value List[String])) -> Plan
    "Revise the plan so that every finding is addressed. Change no files.\n\nTask: {task}\nPlan: {steps}\nFindings: {findings}")
  (defprompt execute-plan (:fills (task :text) (repo :text) (steps :value List[String])) -> Change
    "Work in the git repository at {repo} and nowhere else. Execute this plan there.\n\nTask: {task}\nPlan: {steps}\n\nReport two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or considered and why you discarded them, and what you did not cover.")

  (defworkflow run
    ((task String)
     (intent String)
     (repo String))
    -> Outcome
    (let* ((draft (provider-result providers.planner
                    :prompt (draft-plan :task task :repo repo)
                    :model "claude-opus-5-5" :effort "high" :timeout-sec 5400))
           (feedback (provider-result providers.reviewer
                       :prompt (review-plan :intent intent :repo repo :steps draft.steps)
                       :model "gpt-6-sol" :effort "high" :timeout-sec 5400))
           (revised (provider-result providers.planner
                      :prompt (revise-plan :task task :steps draft.steps :findings feedback.findings)
                      :model "claude-opus-5-5" :effort "high" :timeout-sec 5400))
           (change (provider-result providers.coder
                     :prompt (execute-plan :task task :repo repo :steps revised.steps)
                     :model "claude-sonnet-5-5" :effort "medium" :timeout-sec 5400)))
      (variant Outcome DONE :summary change.summary)))
)
