(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule score_ref)
  (export score)

  (defenum Score S0 S1 S2)

  (defrecord Rating
    (clone String)
    (completeness Score)
    (correctness Score)
    (scope Score)
    (layering Score)
    (reason String))

  (defrecord Batch
    (clones List[String])
    (reference String))

  (defprompt rate-batch
    (:fills (intent :text) (reference :text) (clones :value List[String]))
    -> List[Rating]
    "Each repository listed below holds one attempt at the intended change, as uncommitted changes. Rate every listed repository against the intent and the disclosed accepted reference, independently of the other attempts.\nIntended change: {intent}\nAccepted reference: {reference}\nRepositories: {clones}\nRead the changes and surrounding code in each repository and the reference. The reference establishes the required behaviours, not how they must be implemented. Change nothing, run no tests, and do not use test results or the amount written to assign scores. The reference is not an attempt to rate.\nRate four criteria S0, S1 or S2: `completeness`: all intended behaviours implemented S2, part S1, none S0; an alternative implementation providing the required behaviours scores S2. `correctness`: implemented behaviours hold for the cases the intent names, judged by reading the code against the reference's behaviour (S2 holds, S1 real concern, S0 does not hold). `scope`: no existing validation or guarantee is weakened and nothing changes outside the intended scope. `layering`: the change sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones. A repository implementing none of the intended behaviours scores S0 on every criterion.\nReturn one rating per listed repository in exactly the listed order, copying its path into `clone`. Give one or two sentences in `reason` to justify the four scores.")

  (defworkflow score
    ((batches List[Batch])
     (intent String)
     (criterion_sha256 String)
     (judge_model String))
    -> List[List[Rating]]
    (list/map-effect ((batch batches)) :max 24
      (provider-result providers.judge
        :prompt (rate-batch :intent intent :reference batch.reference :clones batch.clones)
        :model judge_model
        :effort "high"
        :timeout-sec 3600)))
)
