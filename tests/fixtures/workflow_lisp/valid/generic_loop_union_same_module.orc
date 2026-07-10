(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defrecord Ctx
    (manifest Path.state-root))
  (defunion Selection
    (EMPTY)
    (PROGRESS
      (note String))
    (BLOCKED
      (reason String)))
  (defunion LoopResult
    (DRAINED
      (rounds Int))
    (STUCK
      (rounds Int)
      (reason String)))
  (defrecord WorkflowOutput
    (status String))
  (defproc pick
    ((ctx Ctx))
    -> Selection
    :effects ((uses-command probe_select))
    :lowering inline
    (command-result probe_select
      :argv ("python" "scripts/select_next_item.py" ctx.manifest)
      :returns Selection))
  (defproc drain-generic
    :forall (CtxT SelectionT)
    ((ctx CtxT)
     (selector ProcRef[(CtxT) -> SelectionT])
     (max-iterations Int))
    :where ((CtxT is-record)
            (SelectionT is-union)
            (SelectionT has-union-variant EMPTY)
            (SelectionT has-union-variant PROGRESS (note String))
            (SelectionT has-union-variant BLOCKED (reason String)))
    -> LoopResult
    :effects ()
    :lowering inline
    (loop/recur
      :max max-iterations
      :state (loop-state
               (rounds Int 0)
               (note String "seed"))
      :on-exhausted (variant LoopResult STUCK
                      :rounds state.rounds
                      :reason "exhausted")
      (fn (state)
        (match (selector ctx)
          ((EMPTY e)
           (done (variant LoopResult DRAINED
                   :rounds state.rounds)))
          ((PROGRESS p)
           (continue (loop-state :like state
                       :rounds (+ state.rounds 1)
                       :note p.note)))
          ((BLOCKED b)
           (done (variant LoopResult STUCK
                   :rounds state.rounds
                   :reason b.reason)))))))
  (defworkflow drain-status
    ((ctx Ctx))
    -> WorkflowOutput
    (let* ((result (drain-generic ctx (proc-ref pick) 3)))
      (match result
        ((DRAINED d)
         (record WorkflowOutput
           :status "drained"))
        ((STUCK s)
         (record WorkflowOutput
           :status s.reason))))))
