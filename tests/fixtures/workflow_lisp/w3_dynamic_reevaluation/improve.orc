(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.36")
  (defmodule grt/entry)
  (import std/improve :only (Decision Improvement improve))
  (export run)

  (defrecord Draft (title String) (score Int))
  (defrecord Feedback (note String))
  (defrecord Blocker (why String))

  (defworkflow run
    ((seed String :default "draft")
     (goal String :default "tidy")
     (rubric String :default "clear")
     (limit Int :default 3))
    -> Improvement[Draft Feedback Blocker]
    (let* ((initial (record Draft :title seed :score 0)))
      (let-proc
        ((review
          (draft)
          (command-result probe_review
            :argv ("python" "probe_review.py" draft.title goal rubric)
            :returns Decision[Feedback Blocker]))
         (revise
          (draft feedback)
          (command-result probe_revise
            :argv ("python" "probe_revise.py" draft.title goal feedback.note)
            :returns Draft)))
        (improve initial
                 (proc-ref review)
                 (proc-ref revise)
                 limit)))))
