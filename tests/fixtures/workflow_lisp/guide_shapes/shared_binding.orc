(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/shared_binding)
  (export run)
  (defworkflow run ((a Int) (b Int)) -> Int
    (let* ((x (* (+ a b) (- a b))))
      ; x is used 100 times
      (+
         x x x x x x x x x x
         x x x x x x x x x x
         x x x x x x x x x x
         x x x x x x x x x x
         x x x x x x x x x x
         x x x x x x x x x x
         x x x x x x x x x x
         x x x x x x x x x x
         x x x x x x x x x x
         x x x x x x x x x x))))
