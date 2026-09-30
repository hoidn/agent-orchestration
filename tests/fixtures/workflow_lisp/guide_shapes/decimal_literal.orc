(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/decimal_literal)
  (export run)
  (defworkflow run ((score Float)) -> Bool
    (let* ((threshold 0.5))
      (< score threshold))))
