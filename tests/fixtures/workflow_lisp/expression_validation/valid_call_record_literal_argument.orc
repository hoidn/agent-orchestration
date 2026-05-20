(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14"))

(defrecord ImplementationInputs
  (plan PathRel)
  (attempts Int))

(defrecord Plan
  (path PathRel)
  (status String))

(defworkflow run_checks
  ((inputs ImplementationInputs))
  ->
  Plan
  (record Plan
    :path inputs.plan
    :status "ok"))

(defworkflow run
  ((plan_path PathRel)
   (attempt_count Int))
  ->
  Plan
  (call run_checks
    :inputs (record ImplementationInputs
              :plan plan_path
              :attempts attempt_count)))
