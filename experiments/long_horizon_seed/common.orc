(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule common)
  (export Change CheckReport Outcome Built Cut Ending DocPath GuidePath Setup Spec Design Reviewed Milestone Plan
          Verdict)

  ;; Shared result types of the long-horizon seeds. Change and CheckReport are
  ;; the seed catalog's, unchanged; Outcome is the catalog's with the notes an
  ;; exhausted loop ended on. The rest is what a staged program branches on:
  ;; target ids, the milestone list, a verdict. Documents and code stay in the
  ;; workspace; a result carries only their paths, typed so that a step whose
  ;; file is missing fails.

  (defrecord Change
    (summary String)
    (account String))

  (defrecord CheckReport
    (passed Bool)
    (failing List[String])
    (excerpt String))

  (defunion Outcome
    (DONE (summary String))
    (BLOCKED (reason String) (notes List[String])))

  ;; For the seeds that build a plan milestone by milestone. Built: how one milestone ended, met or refused in
  ;; every attempt with the last refusal's notes. Cut: a plan that had more milestones than were built. Ending:
  ;; Outcome, with a Cut for each such plan and, when a milestone was refused, a Built for every milestone built.
  (defrecord Built
    (met Bool)
    (notes List[String]))

  (defrecord Cut
    (planned Int)
    (built Int))

  (defunion Ending
    (DONE (summary String) (cut List[Cut]))
    (BLOCKED (reason String) (notes List[String]) (built List[Built]) (cut List[Cut])))

  (defpath DocPath :kind relpath :under "docs" :must-exist true)
  (defpath GuidePath :kind relpath :under "." :must-exist true)

  (defrecord Setup
    (guide GuidePath)
    (index DocPath)
    (log DocPath))

  (defrecord Spec
    (doc DocPath)
    (targets List[String]))

  (defrecord Design
    (doc DocPath))

  (defunion Reviewed
    (ACCEPTED (design DocPath))
    (REFUSED (reasons List[String])))

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
