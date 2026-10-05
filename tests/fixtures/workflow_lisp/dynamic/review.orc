(workflow-lisp
  (:language "0.1")
  (:target-dsl "3.0")
  (defmodule dynamic_consumer/review)
  (import std/improve :only (Decision))
  (import dynamic_consumer/types :only (Feedback Blocker))
  (export assess)
  (define (assess current goal rubric)
    (command-result probe_review
      :argv ("python" "probe_review.py" (field current "title") goal rubric)
      :returns Decision[Feedback Blocker])))
