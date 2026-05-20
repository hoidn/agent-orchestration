(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defworkflow bad_body
  ((design_path String))
  ->
  String
  (let* ((design design_path))
    missing))
