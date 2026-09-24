(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule map_short_circuit_and_proc_rejection)
  (export orchestrate)
  (defproc safe-false?
    ((path-child String))
    -> Bool
    :effects ()
    :lowering inline
    (and false
      (list/empty? (list (path/join-under Path.state-root path-child)))))
  (defworkflow orchestrate
    ((children List[String]))
    -> List[Bool]
    (list/map ((child children))
      (if (safe-false? child)
        true
        false))))
