(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule common)
  (export Change CheckReport Outcome DocPath Spec Milestone Plan Verdict)

  ;; Shared result types of the long-horizon seed. Change, CheckReport and
  ;; Outcome are the seed catalog's, unchanged. The rest is what a staged
  ;; program branches on: target ids, the milestone list, a verdict. Documents
  ;; and code stay in the workspace; a result carries only their paths.

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

  (defpath DocPath :kind relpath :under "docs" :must-exist true)

  (defrecord Spec
    (doc DocPath)
    (targets List[String]))

  (defrecord Milestone
    (id String)
    (goal String)
    (targets List[String]))

  (defrecord Plan
    (doc DocPath)
    (milestones List[Milestone]))

  (defunion Verdict
    (MET (evidence List[String]))
    (NOT_MET (reasons List[String])))
)
