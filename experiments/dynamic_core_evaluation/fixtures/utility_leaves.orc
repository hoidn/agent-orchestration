(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule utility_leaves)
  (import std/improve :only (Decision Improvement))
  (export Draft Feedback Blocker Candidate Evaluation Trial SearchResult
          review-draft revise-draft propose-candidate evaluate-candidate)
  (defrecord Draft (title String) (score Int))
  (defrecord Feedback (note String))
  (defrecord Blocker (why String))
  (defrecord Candidate (a Int) (b Int))
  (defrecord Evaluation (valid Bool) (score Float) (error String))
  (defrecord Trial
    (action String) (branch String) (parents List[Candidate])
    (candidate Candidate) (evaluation Evaluation) (accepted Bool))
  (defrecord SearchResult
    (candidate Candidate) (evaluation Evaluation) (evaluations Int)
    (status String) (trace List[Trial]))
  (defworkflow review-draft ((draft Draft) (goal String))
    -> Decision[Feedback Blocker]
    (command-result probe_review
      :argv ("python" "PROBE_REVIEW" draft.title goal)
      :returns Decision[Feedback Blocker]))
  (defworkflow revise-draft ((draft Draft) (goal String) (feedback Feedback))
    -> Draft
    (command-result probe_revise
      :argv ("python" "PROBE_REVISE" draft.title goal feedback.note)
      :returns Draft))
  (defworkflow propose-candidate
    ((operation String) (branch String) (candidate_a Int) (candidate_b Int)
     (other_a Int) (other_b Int) (history_size Int))
    -> Candidate
    (command-result propose-branch-candidate
      :adapter propose_candidate
      :inputs ((operation operation) (branch branch)
               (candidate_a candidate_a) (candidate_b candidate_b)
               (other_a other_a) (other_b other_b) (history_size history_size))
      :returns Candidate))
  (defworkflow evaluate-candidate ((a Int) (b Int))
    -> Evaluation
    (command-result evaluate-branch-candidate
      :adapter evaluate_candidate
      :inputs ((a a) (b b))
      :returns Evaluation)))
