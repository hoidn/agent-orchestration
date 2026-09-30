(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/decimal_arithmetic)
  (export run)
  (defworkflow run ((total Float) (visits Int) (all-visits Int)) -> Float
    (+ (/ total (int/to-float visits))
       (* 1.5 (float/sqrt (/ (float/log (int/to-float all-visits))
                            (int/to-float visits)))))))
