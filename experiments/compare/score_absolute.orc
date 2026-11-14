(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")
  (defmodule score_absolute)
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
    (clones List[String]))

  (defprompt rate-batch
    (:fills (intent :text) (clones :value List[String]))
    -> List[Rating]
    "Each repository listed below holds one attempt at the intended change, as uncommitted changes. Rate every listed repository against the intent, independently of the other attempts.\nIntended change: {intent}\nRepositories: {clones}\nRead the changes and surrounding code in each repository. Change nothing, run no tests, and do not use test results or the amount written to assign scores.\nRate four criteria S0, S1 or S2: `completeness`: all intended behaviours implemented S2, part S1, none S0; an alternative implementation providing the required behaviours scores S2. `correctness`: implemented required behaviours hold for the cases the intent names, judged by reading the code (S2 holds, S1 real concern, S0 does not hold or no required behaviour is implemented). `scope`: no existing validation or guarantee is weakened and nothing changes outside the intended scope. `layering`: the change sits in the layer that owns the behaviour and reuses existing mechanisms instead of adding parallel ones. Score scope and layering independently of completeness and correctness; absent required behaviour does not by itself lower scope or layering.\nReturn one rating per listed repository in exactly the listed order, copying its path into `clone`. Give one or two sentences in `reason` to justify the four scores.")

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
