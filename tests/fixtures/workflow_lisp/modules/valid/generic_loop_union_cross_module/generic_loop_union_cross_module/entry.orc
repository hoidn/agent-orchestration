(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule generic_loop_union_cross_module/entry)
  (import generic_loop_union_cross_module/helper :only (LoopResult drain-generic))
  (export drain-status)
  (defrecord Ctx
    (manifest Path.state-root))
  (defunion Selection
    (EMPTY)
    (PROGRESS
      (note String))
    (BLOCKED
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
