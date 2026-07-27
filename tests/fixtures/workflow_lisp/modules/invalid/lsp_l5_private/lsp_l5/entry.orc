(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.20")
  (defmodule lsp_l5/entry)
  (import lsp_l5/private_definitions :as private)
  (export Output apply entry)

  (defrecord Output
    (value String))

  (defproc apply
    ((runner ProcRef[String -> String])
     (input String))
    -> String
    :effects ()
    :lowering inline
    input)

  (defworkflow entry
    ((input String))
    -> Output
    (record Output
      :value (apply
        (proc-ref private.hidden)
        input))))
