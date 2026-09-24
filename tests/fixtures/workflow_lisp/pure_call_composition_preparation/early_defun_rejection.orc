(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule early_defun_rejection)
  (export orchestrate)
  (defproc increment
    ((value Int))
    -> Int
    :effects ()
    :lowering inline
    (+ value 1))
  (defun twice
    ((value Int))
    -> Int
    (increment (increment value)))
  (defworkflow orchestrate
    ((value Int))
    -> Int
    (twice value)))
