(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.27")
  (defmodule map_short_circuit_or_control)
  (export orchestrate)
  (defun unsafe-path?
    ((path-child String))
    -> Bool
    (list/empty? (list (path/join-under Path.state-root path-child))))
  (defworkflow orchestrate
    ((children List[String]))
    -> List[Bool]
    (list/map ((child children))
      (if (or true (unsafe-path? child))
        true
        false))))
