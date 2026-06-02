(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std/phase)
  (export ReviewDecision review-revise-loop)
  (defenum ReviewDecision
    APPROVE
    REVISE
    BLOCKED)
  (defmacro review-revise-loop (name &body args)
    (__stdlib-specialization__ phase-review-loop name
      (splice args))))
