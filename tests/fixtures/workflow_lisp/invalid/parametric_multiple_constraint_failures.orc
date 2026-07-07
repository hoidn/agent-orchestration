(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defrecord ActualCtx
    (other String))
  (defrecord ActualChoice
    (label String))
  (defrecord WorkflowOutput
    (status String))
  (defproc require-shapes
    :forall (CtxT ChoiceT)
    ((ctx CtxT)
     (choice ChoiceT))
    :where ((CtxT has-field a String)
            (CtxT has-field b Int)
            (ChoiceT has-union-variant DONE))
    -> WorkflowOutput
    :effects ((uses-command run_checks))
    :lowering inline
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py")
      :returns WorkflowOutput))
  (defworkflow entry
    ((ctx ActualCtx)
     (choice ActualChoice))
    -> WorkflowOutput
    (require-shapes ctx choice)))
