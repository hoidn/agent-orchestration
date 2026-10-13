(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule plan_review_execute)
  (export run)

  ;; Fable drafts a plan; Codex reviews it; Fable revises the plan with that
  ;; feedback; Codex executes the revised plan.
  ;;
  ;;   python -m orchestrator compile workflows/examples/plan_review_execute.orc \
  ;;     --provider-externs-file workflows/examples/inputs/plan_review_execute/providers.json

  (defrecord Plan (steps List[String]))
  (defrecord Feedback (findings List[String]))
  (defrecord Execution (summary String))

  (defprompt draft-plan (:fills (task :text)) -> Plan
    "Plan this task as ordered steps, naming the files each step touches. Change no files.\n\nTask: {task}")
  (defprompt review-plan (:fills (task :text) (steps :value List[String])) -> Feedback
    "Review this plan: what would make it fail or leave the task's scope? Change nothing.\n\nTask: {task}\nPlan: {steps}")
  (defprompt revise-plan (:fills (task :text) (steps :value List[String]) (findings :value List[String])) -> Plan
    "Revise the plan so that every finding is addressed. Change no files.\n\nTask: {task}\nPlan: {steps}\nFindings: {findings}")
  (defprompt execute-plan (:fills (task :text) (steps :value List[String])) -> Execution
    "Execute this plan in the current repository.\n\nTask: {task}\nPlan: {steps}")

  (defworkflow run ((task String)) -> Execution
    (let* ((draft (provider-result providers.claude :model "claude-fable-5-1" :effort "high"
                    :prompt (draft-plan :task task)))
           (feedback (provider-result providers.codex
                       :prompt (review-plan :task task :steps draft.steps)))
           (revised (provider-result providers.claude :model "claude-fable-5-1" :effort "high"
                      :prompt (revise-plan :task task :steps draft.steps :findings feedback.findings))))
      (provider-result providers.codex
        :prompt (execute-plan :task task :steps revised.steps))))
)
