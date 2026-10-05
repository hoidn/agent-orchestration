(workflow-lisp
  (:language "0.1")
  (:target-dsl "3.0")
  (:budget 1000)
  (defmodule dynamic_consumer/improve)
  (import std/improve :only (Decision Improvement))
  (import std/dynamic/improve :as dynamic :only (improve))
  (import dynamic_consumer/types :only (Draft Feedback Blocker))
  (export run)

  (define (review-for goal rubric)
    (fn (current)
      (command-result probe_review
        :argv ("python" "probe_review.py" (field current "title") goal rubric)
        :returns Decision[Feedback Blocker])))

  (define (revise-for goal)
    (fn (current feedback)
      (command-result probe_revise
        :argv ("python" "probe_revise.py" (field current "title") goal (field feedback "note"))
        :returns Draft)))

  (defworkflow run
    ((seed String :default "draft") (goal String :default "tidy")
     (rubric String :default "clear") (limit Int :default 3))
    -> Improvement[Draft Feedback Blocker]
    (let* ((initial (record (title seed) (score 0))))
      (improve initial (review-for goal rubric) (revise-for goal) limit))))
