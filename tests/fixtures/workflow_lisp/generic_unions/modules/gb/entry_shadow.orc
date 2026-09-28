(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule gb/entry_shadow)
  (import gb/lib :only (run-review))
  (export decide)
  (defunion Decision :forall (F B)
    (APPROVE (evidence F))
    (REVISE (feedback F))
    (BLOCKED (reason B)))
  (defrecord MyFeedback
    (note String))
  (defrecord MyBlocker
    (why String))
  (defproc review-hook
    ((decision Decision[MyFeedback MyBlocker]))
    -> Decision[MyFeedback MyBlocker]
    :effects ()
    decision)
  (defproc decide
    ((decision Decision[MyFeedback MyBlocker]))
    -> Decision[MyFeedback MyBlocker]
    :effects ()
    (run-review decision
                (proc-ref review-hook))))
