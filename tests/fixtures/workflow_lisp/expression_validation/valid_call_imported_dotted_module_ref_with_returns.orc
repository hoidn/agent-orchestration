(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(import remote.workflows :as remote)

(defworkflow run
  ()
  ->
  String
  (call remote/run_phase
    :returns String))
