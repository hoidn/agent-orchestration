(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule map_short_circuit_or_proc_rejection)
  (export orchestrate)
  (defproc safe-true?
    ((path-child String))
    -> Bool
    :effects ()
    :lowering inline
    (or true
      (list/empty? (list (path/join-under Path.state-root path-child)))))
  (defworkflow orchestrate
    ((children List[String]))
    -> List[Bool]
    (list/map ((child children))
      (if (safe-true? child)
        true
        false))))
