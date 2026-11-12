(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule common)
  (export Change CheckReport Outcome)

  ;; Shared types of the structural-search seed catalog. Every seed exports
  ;; run ((task String) (intent String) (repo String)) -> Outcome.

  (defrecord Change
    (summary String)
    (account String))

  (defrecord CheckReport
    (passed Bool)
    (failing List[String])
    (excerpt String))

  (defunion Outcome
    (DONE (summary String))
    (BLOCKED (reason String)))
)
