(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule aggregate_map_rejection)
  (export orchestrate)
  (defrecord Result
    (seed Int)
    (values List[Int]))
  (defproc increment
    ((value Int))
    -> Int
    :effects ()
    :lowering inline
    (+ value 1))
  (defworkflow orchestrate
    ((seed Int)
     (values List[Int]))
    -> Result
    (record Result
      :seed (increment seed)
      :values (list/map ((value values))
                (increment value)))))
