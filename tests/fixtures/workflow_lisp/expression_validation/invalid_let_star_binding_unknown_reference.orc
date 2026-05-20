(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defworkflow bad_binding
  ((design_path String))
  ->
  String
  (let* ((design missing))
    design_path))
