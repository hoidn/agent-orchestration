(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule entry_publication_return_not_union)
  (export entry-publication-return-not-union)
  (defrecord PublishRecord
    (message String))
  (defworkflow entry-publication-return-not-union
    ()
    -> PublishRecord
    (:publish
      ((DONE :as drain-summary)))
    (record PublishRecord
      :message "record-result")))
