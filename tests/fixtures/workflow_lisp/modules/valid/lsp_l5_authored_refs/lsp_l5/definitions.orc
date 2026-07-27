(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.20")
  (defmodule lsp_l5/definitions)
  (export WorkReport SharedResult shared)

  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defrecord SharedResult
    (report WorkReport))

  (defprompt shared
    (:fills
      (message :text))
    -> SharedResult
    "Review {message}")

  (defproc shared
    ((report WorkReport))
    -> SharedResult
    :effects ()
    :lowering inline
    (record SharedResult :report report))

  (defworkflow shared
    ((report WorkReport))
    -> SharedResult
    (record SharedResult :report report)))
