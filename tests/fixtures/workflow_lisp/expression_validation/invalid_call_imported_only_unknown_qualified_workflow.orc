(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(import remote/workflows :only (run_phase))

(defworkflow run
  ()
  ->
  String
  (call remote/workflows/other_phase
    :returns String))
