(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule defun_argument_control)
  (export orchestrate)
  (defrecord Result
    (duplicated Int)
    (ignored Int)
    (captured Int))
  (defun duplicate
    ((value Int))
    -> Int
    (+ value value))
  (defun ignore-first
    ((ignored Int)
     (value Int))
    -> Int
    value)
  (defun select-second
    ((x Int)
     (y Int))
    -> Int
    y)
  (defworkflow orchestrate
    ((x Int))
    -> Result
    (record Result
      :duplicated (duplicate (+ x 1))
      :ignored (ignore-first (+ x 2) x)
      :captured (select-second 2 x))))
