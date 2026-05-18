(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defworkflow duplicate-param
    ((input ChecksResult)
     (input ChecksResult))
    -> ImplementationState
    input))
