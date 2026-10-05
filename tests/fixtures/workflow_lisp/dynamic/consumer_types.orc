(workflow-lisp
  (:language "0.1")
  (:target-dsl "3.0")
  (defmodule dynamic_consumer/types)
  (import std/improve :only (Decision Improvement))
  (export Draft Feedback Blocker Candidate Evaluation Trial SearchResult)
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
    (status String) (trace List[Trial])))
