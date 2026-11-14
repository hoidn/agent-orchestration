(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule main) (export run)
  (defworkflow run () -> List[Int]
    (list/map-effect ((x (list 1 2 3))) :max 2
      (command-result step :argv ("python" "step.py" x) :returns Int))))
