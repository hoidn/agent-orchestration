(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/a)
  (export WorkReport SharedTargets)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defschema SharedTargets
    (report WorkReport)))
