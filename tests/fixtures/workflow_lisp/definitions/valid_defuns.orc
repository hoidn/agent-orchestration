(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defrecord PlanInputs
  (design_path String))

(defun normalize_inputs ((inputs PlanInputs)) -> PlanInputs
  inputs)

(defun normalize_path ((path String)) -> String
  path)

(defworkflow run_phase ((inputs PlanInputs)) -> PlanInputs
  inputs)
