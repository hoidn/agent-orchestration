(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/payload_split)
  (export run)
  (defun part ((a Int)) -> Int
    ; 150 operands
    (+
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a))
  (defworkflow run ((a Int)) -> Int
    (+ (part a) (part a))))
