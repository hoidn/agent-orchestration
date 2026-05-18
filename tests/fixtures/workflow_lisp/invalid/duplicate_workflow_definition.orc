(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defworkflow duplicate
    ((input ChecksResult))
    -> ImplementationState
    input)
  (defworkflow duplicate
    ((input ChecksResult))
    -> ImplementationState
    input))
