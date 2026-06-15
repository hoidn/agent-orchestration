(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry_publication_not_entrypoint)
  (export entry)
  (defunion EntryPublicationResult
    (DONE
      (message String))
    (BLOCKED
      (reason String)))
  (defworkflow publish-helper
    ()
    -> EntryPublicationResult
    (:publish
      ((DONE :as drain-summary)))
    (variant EntryPublicationResult DONE
      :message "helper-only"))
  (defworkflow entry
    ()
    -> EntryPublicationResult
    (call publish-helper)))
