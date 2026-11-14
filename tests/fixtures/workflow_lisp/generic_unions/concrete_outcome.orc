(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defunion Outcome :forall (T E)
    (OK (value T))
    (ERROR (error E)))
  (defrecord Summary
    (label String))
  (defrecord Report
    (outcome Outcome[Int String]))
  (defproc make-ok
    ((n Int))
    -> Outcome[Int String]
    (variant Outcome[Int String] OK :value n))
  (defproc run-check
    ((check ProcRef[(Int) -> Outcome[Int String]])
     (n Int))
    -> Outcome[Int String]
    (check n))
  (defproc summarize
    ((outcome Outcome[Int String]))
    -> Summary
    (match outcome
      ((OK ok) (record Summary :label "ok"))
      ((ERROR err) (record Summary :label err.error))))
  (defproc apply-summary
    ((summarizer ProcRef[(Outcome[Int String]) -> Summary])
     (outcome Outcome[Int String]))
    -> Summary
    (summarizer outcome))
  (defproc wrap-report
    ((outcome Outcome[Int String]))
    -> Report
    (record Report :outcome outcome))
  (defworkflow entry
    ((n Int))
    -> Outcome[Int String]
    (run-check (proc-ref make-ok) n)))
