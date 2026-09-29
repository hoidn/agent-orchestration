(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/provider_review)
  (import std/improve :only (Decision))
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defrecord Notes (notes String))
  (defrecord Blocker (issue String) (severity Int))
  (defproc review ((draft String)) -> Decision[Notes Blocker]
    :effects ((uses-provider providers.review))
    :lowering inline
    (provider-result providers.review
      :prompt prompts.review
      :inputs (draft)
      :returns Decision[Notes Blocker]))
  (defworkflow run ((draft String)) -> Box
    (let* ((decision (review draft)))
      (match decision
        ((APPROVE a) (fetch 1))
        ((REVISE r) (fetch 2))
        ((BLOCKED b) (fetch b.reason.severity))))))
