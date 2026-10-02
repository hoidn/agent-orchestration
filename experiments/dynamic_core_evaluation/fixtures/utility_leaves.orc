(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule utility_leaves)
  (import std/improve :only (Decision Improvement))
  (export Draft Feedback Blocker review-draft revise-draft)
  (defrecord Draft (title String) (score Int))
  (defrecord Feedback (note String))
  (defrecord Blocker (why String))
  (defworkflow review-draft ((draft Draft) (goal String))
    -> Decision[Feedback Blocker]
    (command-result probe_review
      :argv ("python" "PROBE_REVIEW" draft.title goal)
      :returns Decision[Feedback Blocker]))
  (defworkflow revise-draft ((draft Draft) (goal String) (feedback Feedback))
    -> Draft
    (command-result probe_revise
      :argv ("python" "PROBE_REVISE" draft.title goal feedback.note)
      :returns Draft)))
