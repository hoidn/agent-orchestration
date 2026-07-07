(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defproc orphan
    :forall (T)
    ((seed String))
    :where ((T is-record))
    -> String
    :effects ()
    :lowering inline
    seed))
