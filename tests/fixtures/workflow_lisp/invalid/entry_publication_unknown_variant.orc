(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry_publication_unknown_variant)
  (export entry-publication-unknown-variant)
  (defunion EntryPublicationResult
    (DONE
      (message String))
    (BLOCKED
      (reason String)))
  (defworkflow entry-publication-unknown-variant
    ()
    -> EntryPublicationResult
    (:publish
      ((SKIPPED :as drain-summary)))
    (variant EntryPublicationResult DONE
      :message "done")))
