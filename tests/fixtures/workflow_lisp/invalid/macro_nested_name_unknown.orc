(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defrecord Out
    (value String))
  (emit-record-wrapper broken)
  (defmacro emit-record-wrapper (name)
    (emit-record-workflow name
      (record Out :value missing_name)))
  (defmacro emit-record-workflow (name body)
    (defworkflow name
      ()
      -> Out
      body)))
