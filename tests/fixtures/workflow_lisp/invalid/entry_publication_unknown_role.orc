(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry_publication_unknown_role)
  (export entry-publication-unknown-role)
  (defunion EntryPublicationResult
    (DONE
      (message String))
    (BLOCKED
      (reason String)))
  (defworkflow entry-publication-unknown-role
    ()
    -> EntryPublicationResult
    (:publish
      ((DONE :as missing-publication-role)))
    (variant EntryPublicationResult DONE
      :message "unknown-role")))
