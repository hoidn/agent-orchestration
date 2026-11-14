(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule early_defun_rejection)
  (export orchestrate)
  (defproc increment
    ((value Int))
    -> Int
    (+ value 1))
  (defun twice
    ((value Int))
    -> Int
    (increment (increment value)))
  (defworkflow orchestrate
    ((value Int))
    -> Int
    (twice value)))
