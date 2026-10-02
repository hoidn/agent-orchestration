(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule leaf)
  (export review annotate check-inputs review-output forward-annotate)

  (defpath GoalDoc
    :kind relpath
    :under "docs"
    :must-exist true)

  (defpath ReportTarget
    :kind relpath
    :under "artifacts/review"
    :must-exist false)

  (defrecord Evidence
    (count Int))

  (defunion Decision
    (ACCEPTED (confidence Int))
    (REJECTED (reason String)))

  (defrecord ReviewResult
    (approved Bool)
    (feedback String)
    (score Int)
    (evidence Evidence)
    (decisions List[Decision]))

  (defprompt review-prompt
    (:fills
      (goal :value String)
      (rubric :value String)
      (target_doc :doc GoalDoc))
    -> ReviewResult
    "[{goal}, {rubric}]")

  (defprompt report-prompt
    (:fills
      (goal :value String)
      (rubric :value String)
      (target_doc :doc GoalDoc)
      (report :path :out ReportTarget))
    -> ReviewResult
    "[{goal}, {rubric}]\nOUT:{report}")

  (defworkflow review
    ((goal String)
     (rubric String)
     (target_doc GoalDoc))
    -> ReviewResult
    (provider-result providers.review
      :prompt (review-prompt
        :goal goal
        :rubric rubric
        :target_doc target_doc)))

  (defworkflow review-output
    ((goal String)
     (rubric String)
     (target_doc GoalDoc)
     (report ReportTarget))
    -> ReviewResult
    (provider-result providers.review
      :prompt (report-prompt
        :goal goal
        :rubric rubric
        :target_doc target_doc
        :report report)))

  (defworkflow annotate
    ((feedback String))
    -> ReviewResult
    (command-result annotate
      :argv ("python"
        "experiments/dynamic_core_evaluation/fixtures/scripted_leaf.py"
        "command"
        feedback)
      :returns ReviewResult))

  (defworkflow check-inputs
    ((flag Bool)
     (number Int)
     (ratio Float)
     (items List[Evidence])
     (decisions List[Decision]))
    -> ReviewResult
    (command-result annotate
      :argv ("python"
        "experiments/dynamic_core_evaluation/fixtures/scripted_leaf.py"
        "command"
        ratio)
      :returns ReviewResult))

  (defworkflow forward-annotate
    ((feedback String))
    -> ReviewResult
    (call annotate :feedback feedback)))
