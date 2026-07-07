(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
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
    :effects ()
    :lowering inline
    (let* ((item_id payload.item-id))
      item_id))
  (defproc pick-and-project
    :forall (SelectionT SelPayloadT)
    ((choice SelectionT)
     (fallback SelPayloadT)
     (run ProcRef[(SelPayloadT) -> String]))
    :where ((SelectionT is-union)
            (SelectionT has-union-variant SELECTED (selection SelPayloadT))
            (SelectionT has-union-variant EMPTY))
    -> String
    :effects ()
    :lowering inline
    (match choice
      ((SELECTED s)
       (run s.selection))
      ((EMPTY e)
       (run fallback))))
  (defworkflow entry
    ((item_id String))
    -> WorkflowOutput
    (let* ((choice
             (command-result run_checks
               :argv ("python" "scripts/run_checks.py" item_id)
               :returns Selection))
           (fallback
             (command-result run_checks
               :argv ("python" "scripts/run_checks.py" "fallback")
               :returns OtherPayload))
           (status
             (pick-and-project choice fallback (proc-ref consume-other))))
      (record WorkflowOutput
        :status status))))
