(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule gb/entry_alias)
  (import gb/lib :as lib :only (Decision run-review))
  (export decide)
  (defrecord MyFeedback
    (note String))
  (defrecord MyBlocker
    (why String))
  (defproc review-hook
    ((decision lib.Decision[MyFeedback MyBlocker]))
    -> lib.Decision[MyFeedback MyBlocker]
    decision)
  (defproc decide
    ((decision lib.Decision[MyFeedback MyBlocker]))
    -> lib.Decision[MyFeedback MyBlocker]
    (run-review decision
                (proc-ref review-hook))))
