(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule pure_projection_binding_type_mismatch)
  (export ConsumerRoute Result project run)

  (defenum ConsumerRoute
    READY
    HOLD)

  (defrecord Result
    (status String))

  (defworkflow project
    ((route ConsumerRoute)
     (reason String))
    -> Result
    (record Result
      :status reason))

  (defworkflow run
    ((reason String))
    -> Result
    (let* ((wrong_route
             (string/concat reason "-route")))
      (call project
        :route wrong_route
        :reason reason))))
