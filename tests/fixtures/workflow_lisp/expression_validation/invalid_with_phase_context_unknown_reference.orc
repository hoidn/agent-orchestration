(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defworkflow bad_context
  ((phase_ctx String))
  ->
  String
  (with-phase missing implementation
    phase_ctx))
