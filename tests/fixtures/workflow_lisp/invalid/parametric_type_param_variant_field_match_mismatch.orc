(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defrecord Payload
    (item-id String))
  (defrecord OtherPayload
    (item-id String))
  (defunion Selection
    (SELECTED
      (selection Payload))
    (EMPTY))
  (defrecord WorkflowOutput
    (status String))
  (defproc consume-other
    ((payload OtherPayload))
    -> String
    payload.item-id)
  (defproc pick-and-run-match
    :forall (SelectionT SelPayloadT)
    ((choice SelectionT)
     (run ProcRef[(SelPayloadT) -> String]))
    :where ((SelectionT is-union)
            (SelectionT has-union-variant SELECTED (selection SelPayloadT))
            (SelectionT has-union-variant EMPTY))
    -> WorkflowOutput
    (command-result run_checks
      :argv ("python" "scripts/run_checks.py")
      :returns WorkflowOutput))
  (defworkflow entry
    ((item_id String))
    -> WorkflowOutput
    (pick-and-run-match
      (variant Selection SELECTED
        :selection (record Payload :item-id item_id))
      (proc-ref consume-other))))
