(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/decimal_default)
  (export run)
  (defworkflow run ((score Float) (threshold Float :default 0.5)) -> Bool
    (< score threshold)))
