(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std/phase)
  (export ReviewDecision ReviewFindingsJsonPath ReviewFindings review-revise-loop)
  (defenum ReviewDecision
    APPROVE
    REVISE
    BLOCKED)
  (defpath ReviewFindingsJsonPath
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defrecord ReviewFindings
    (schema_version String)
    (items_path ReviewFindingsJsonPath))
  (defmacro review-revise-loop (name &body args)
    (__stdlib-specialization__ phase-review-loop name
      (splice args))))
