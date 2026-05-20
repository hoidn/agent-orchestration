(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(import remote/workflows :as remote)

(defworkflow run
  ((design_path String))
  ->
  String
  (call remote/run_phase
    :returns String
    :design_path missing))
