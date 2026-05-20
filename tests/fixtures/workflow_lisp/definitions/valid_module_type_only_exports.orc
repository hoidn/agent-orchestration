(defmodule neurips.types_only
  (:language workflow-lisp "0.1")
  (:target-dsl "2.14")

  (export SharedInput)

  (defrecord SharedInput
    (design_path PathRel))

  (defworkflow hidden_phase ((inputs SharedInput)) -> String
    "ok"))
