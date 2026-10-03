(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule dynamic/modules/selected)
  (import std/improve :as improve :only (Decision Improvement))
    (export Selected ignored ProcedureBox PromptPath PromptWithTypes OldWorkflow)
  (defrecord Feedback (message String))
  (defrecord Blocker (reason String))
    (defrecord Selected
      (decision improve.Decision[Feedback Blocker])
      (improvement improve.Improvement[Feedback Feedback Blocker]))
    (defrecord ProcedureBox (callback ProcRef[(Int) -> Int]))
    (defpath PromptPath :kind relpath :under "artifacts/prompt" :must-exist false)
    (defprompt PromptWithTypes
      (:fills (feedback :value Feedback) (destination :path PromptPath))
      -> Feedback
      "Review {feedback} -> {destination}")
    (defworkflow OldWorkflow () -> String "unused")
    (defrecord Unused (value MissingType))
    (defmacro ignored (name)
      (defrecord name (value String))))
