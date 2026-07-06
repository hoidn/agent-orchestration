(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defrecord Payload
    (item-id String))
  (defunion Selection
    (SELECTED
      (selection Payload))
    (EMPTY))
  (defrecord WorkflowOutput
    (status String))
  (defproc consume
    ((payload Payload))
    -> String
    :effects ()
    :lowering inline
    payload.item-id)
  (defproc pick-and-run-match
    :forall (SelectionT SelPayloadT)
    ((choice SelectionT)
     (run ProcRef[(SelPayloadT) -> String]))
    :where ((SelectionT is-union)
            (SelectionT has-union-variant SELECTED (selection SelPayloadT))
            (SelectionT has-union-variant EMPTY))
    -> WorkflowOutput
    :effects ((uses-command run_checks))
    :lowering inline
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py")
      :returns WorkflowOutput))
  (defworkflow entry
    ((item_id String))
    -> WorkflowOutput
    (pick-and-run-match
      (variant Selection SELECTED
        :selection (record Payload :item-id item_id))
      (proc-ref consume))))
