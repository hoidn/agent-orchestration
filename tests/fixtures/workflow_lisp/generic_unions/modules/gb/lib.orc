(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule gb/lib)
  (export Decision run-review)
  (defunion Decision :forall (F B)
    (APPROVE (evidence F))
    (REVISE (feedback F))
    (BLOCKED (reason B)))
  (defproc run-review
    :forall (S F B)
    ((subject S)
     (review ProcRef[(S) -> Decision[F B]]))
    -> Decision[F B]
    :effects ()
    (review subject)))
