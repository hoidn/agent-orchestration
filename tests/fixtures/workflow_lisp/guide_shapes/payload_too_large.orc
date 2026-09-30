(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule guide_shapes/payload_too_large)
  (export run)
  (defworkflow run ((a Int)) -> Int
    ; one expression of 301 nodes: the operator and 300 operands
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
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a
       a a a a a a a a a a a a a a a)))
