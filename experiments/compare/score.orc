(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule score)
  (export score)

  ; Blind side-by-side scoring (docs/design/orc_effectiveness_comparison_harness.md D4, D6).
  ; Inputs come from `prepare.py pool`; `criterion_sha256` is bound in run.json for `summarize.py`.
  (defenum Score S0 S1 S2)

  (defrecord Rating
    (clone String)  ; copied back by the judge; cross-check only, ratings join to clones by position
    (root_cause Score)
    (scope Score)
    (generality Score)
    (layering Score)
    (reason String))

  (defrecord Batch
    (clones List[String]))

  (defprompt rate-batch
    (:fills (intent :text) (clones :value List[String]))
    -> List[Rating]
    "Each repository listed below holds one attempt at the same change, as uncommitted changes. Rate every one.\nIntended change: {intent}\nRepositories: {clones}\nIn each repository read the uncommitted changes and the code around them. Change nothing in any repository, do not run tests, and do not base a rating on test results or on how much was written.\nCompare the repositories with each other: where two differ, decide which is right by reading the code, and rate equal flaws equally.\nRate each repository on four criteria, each S0 (does not hold), S1 (holds with a real concern) or S2 (holds): `root_cause`: the root cause is fixed, not the symptom silenced; `scope`: no existing validation or guarantee is weakened and nothing changes outside the intended scope; `generality`: the change holds beyond the reported case; `layering`: it sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones.\nReturn one rating per repository, in exactly the listed order: `clone` is the repository path copied exactly from the list, `reason` one or two sentences that justify the four ratings.")

  (defworkflow score
    ((batches List[Batch])
     (intent String)
     (criterion_sha256 String)
     (judge_model String))
    -> List[List[Rating]]
    (list/map-effect ((batch batches)) :max 24
      (provider-result providers.judge
        :prompt (rate-batch :intent intent :clones batch.clones)
        :model judge_model
        :effort "high"
        :timeout-sec 3600)))
)
