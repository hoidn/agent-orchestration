(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule once_only_hygienic_arguments)
  (export orchestrate)
  (defrecord Result
    (duplicated Int)
    (ignored Int)
    (captured Int))
  (defproc duplicate
    ((value Int))
    -> Int
    :effects ()
    :lowering inline
    (+ value value))
  (defproc ignore-first
    ((ignored Int)
     (value Int))
    -> Int
    :effects ()
    :lowering inline
    value)
  (defproc select-second
    ((x Int)
     (y Int))
    -> Int
    :effects ()
    :lowering inline
    y)
  (defworkflow orchestrate
    ((x Int))
    -> Result
    (record Result
      :duplicated (duplicate (+ x 1))
      :ignored (ignore-first (+ x 2) x)
      :captured (select-second 2 x))))
