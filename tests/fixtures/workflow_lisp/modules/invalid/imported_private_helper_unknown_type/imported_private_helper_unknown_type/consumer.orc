(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_private_helper_unknown_type/consumer)
  (import imported_private_helper_unknown_type/helper :only
    (HelperInput PublicDecision run-helper))
  (export EntryResult run)

  (defrecord EntryResult
    (status String))

  (defworkflow run
    ((input HelperInput))
    -> EntryResult
    (let* ((decision
             (call run-helper
               :input input)))
      (match decision
        ((ALLOW allow)
         (record EntryResult
           :status "ALLOW"))
        ((REJECT reject)
         (record EntryResult
           :status "REJECT"))))))
