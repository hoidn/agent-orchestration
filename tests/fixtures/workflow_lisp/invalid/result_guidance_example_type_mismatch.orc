(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defworkflow guidance-example-type-mismatch ()
    -> (result Bool :example "yes")
    true))
