(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule proc_refs/private_entry)
  (import proc_refs/private_helper :as helper)
  (export Output forward entry)
  (defrecord Output
    (value String))
  (defproc forward
    ((runner ProcRef[String -> String])
     (input String))
    -> String
    input)
  (defworkflow entry
    ((input String))
    -> Output
    (record Output
      :value (forward
        (proc-ref helper.echo-helper)
        input))))
