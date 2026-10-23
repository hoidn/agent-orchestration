(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule score_functional)
  (export score)

  (defenum Score S0 S1 S2 S3 S4 S5 S6 S7 S8)

  (defrecord Rating
    (clone String)
    (quality Score)
    (reason String))

  (defrecord Batch
    (clones List[String]))

  (defprompt rate-batch
    (:fills (intent :text) (clones :value List[String]))
    -> List[Rating]
    "Each repository listed below holds one attempt at the intended change, as uncommitted changes. Rate each repository independently against the intent.\nIntended change: {intent}\nRepositories: {clones}\nRead the changes and surrounding code. Do not change files, run tests, or use recorded test results. Judge how much of the intended behavior works correctly through its normal entry points. Give one holistic functional quality score: S0 means none of the required behavior works; S2 means a small working part while most behavior is absent or broken; S4 means a substantial partial solution with major requirements still absent or broken; S6 means most required behavior works with meaningful gaps; S8 means the requested behavior is complete and credibly correct across the stated cases. Odd scores fall between neighboring anchors. Unused helpers and scaffolding do not count as working behavior. Organization, code size, and style earn no separate points; design or scope problems matter only when they cause a concrete functional defect or regression. Explain the main working behavior and the most consequential gap with code locations in one to three sentences.\nReturn one rating per listed repository in exactly the listed order, copying its path into `clone`.")

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
