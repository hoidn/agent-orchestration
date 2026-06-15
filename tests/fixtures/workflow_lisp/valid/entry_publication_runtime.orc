(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry_publication_runtime)
  (export call-entry-publication-runtime entry-publication-runtime)
  (defenum PublicationMode
    DONE
    BLOCKED
    SKIPPED)
  (defunion EntryPublicationResult
    (DONE
      (message String))
    (BLOCKED
      (reason String))
    (SKIPPED
      (note String)))
  (defworkflow entry-publication-runtime
    ((selected_variant String :default "DONE"))
    -> EntryPublicationResult
    (:publish
      ((DONE :as drain-summary)
       (BLOCKED :as drain-summary)))
    (if (= selected_variant "DONE")
      (variant EntryPublicationResult DONE
        :message "published-done")
      (if (= selected_variant "BLOCKED")
        (variant EntryPublicationResult BLOCKED
          :reason "published-blocked")
        (variant EntryPublicationResult SKIPPED
          :note "omitted-variant"))))
  (defworkflow call-entry-publication-runtime
    ((selected_variant String :default "DONE"))
    -> EntryPublicationResult
    (call entry-publication-runtime
      :selected_variant selected_variant)))
