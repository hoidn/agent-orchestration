(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_private_helper_exported_union_not_imported/consumer)
  (import imported_private_helper_exported_union_not_imported/helper :only
    (HelperInput PublicDecision run-helper))
  (export EntryResult run)

  (defunion EntryResult
    (ALLOW
      (detail String))
    (REJECT
      (detail String)))

  (defworkflow run
    ((input HelperInput))
    -> EntryResult
    (let* ((decision
             (call run-helper
               :input input)))
      (match decision
        ((ALLOW allow)
         (variant EntryResult ALLOW
           :detail allow.message))
        ((REJECT reject)
         (variant EntryResult REJECT
           :detail reject.message))))))
