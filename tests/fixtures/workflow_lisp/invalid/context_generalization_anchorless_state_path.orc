(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule context_generalization_anchorless_state_path)
  (export orchestrate)
  (defrecord AnchorlessCtx
    (state-root Path.state-root))
  (defrecord Result
    (label String))
  (defworkflow orchestrate
    ((ctx AnchorlessCtx))
    -> Result
    (command-result emit_state_root
      :argv ("python" "scripts/emit_state_root.py" ctx.state-root)
      :returns Result)))
