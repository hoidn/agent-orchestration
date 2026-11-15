(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule cp/provider_review)
  (import std/improve :only (Decision))
  (export run)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defrecord Notes (notes String))
  (defrecord Blocker (issue String) (severity Int))
  (defproc review ((draft String)) -> Decision[Notes Blocker]
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
