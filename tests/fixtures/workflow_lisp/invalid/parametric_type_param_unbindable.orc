(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defproc orphan
    :forall (T)
    ((seed String))
    :where ((T is-record))
    -> String
    seed))
