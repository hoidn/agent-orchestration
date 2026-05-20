(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defworkflow bad_body
  ((phase_ctx String))
  ->
  String
  (with-phase phase_ctx implementation
    missing))
