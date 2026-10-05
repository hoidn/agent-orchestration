; Complete caller-owned inline control for the imported-library comparison.
(workflow-lisp
  (:language "0.1")
  (:target-dsl "3.0")
  (:budget 1000)
  (defmodule dynamic_consumer/improve)
  (import std/improve :only (Decision Improvement))
  (import dynamic_consumer/types :only (Draft Feedback Blocker))
  (export run)

  (define (inline-improve initial review revise limit)
    (if (<= limit 0)
        (fail "invalid_limit")
        (inline-improve-loop initial review revise limit 0)))

  (define (inline-improve-loop current review revise limit iteration)
    (if (= iteration limit)
        (record (variant "EXHAUSTED") (value current))
        (let* ((decision (review current))
               (tag (field decision "variant")))
          (if (= tag "APPROVE")
              (record (variant "APPROVED") (value current)
                      (evidence (field decision "evidence")))
              (if (= tag "BLOCKED")
                  (record (variant "BLOCKED") (value current)
                          (reason (field decision "reason")))
                  (if (= tag "REVISE")
                      (inline-improve-loop (revise current (field decision "feedback"))
                                           review revise limit (+ iteration 1))
                      (fail "unknown_review_decision")))))))

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
      (inline-improve initial (review-for goal rubric) (revise-for goal) limit))))
