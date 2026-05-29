(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule cycle_guard_demo)
  (export cycle-guard-demo)

  (defrecord CycleGuardSummary
    (terminal_status String)
    (guard_cycles Int))

  (defworkflow cycle-guard-demo
    ((terminal_status String)
     (guard_cycles Int))
    -> CycleGuardSummary
    (command-result emit_cycle_guard_summary
      :argv ("python" "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py" terminal_status guard_cycles)
      :returns CycleGuardSummary)))
