(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry_publication_duplicate_row)
  (export entry-publication-duplicate-row)
  (defunion EntryPublicationResult
    (DONE
      (message String))
    (BLOCKED
      (reason String)))
  (defworkflow entry-publication-duplicate-row
    ()
    -> EntryPublicationResult
    (:publish
      ((DONE :as drain-summary)
       (DONE :as drain-summary)))
    (variant EntryPublicationResult DONE
      :message "duplicate-row")))
