(workflow-lisp
  (:language "0.1")
  (:target-dsl "3.0")
  (defmodule dynamic_consumer/feedback)
  (export feedback-to-revision-input)
  (define (feedback-to-revision-input feedback)
    (field feedback "note")))
