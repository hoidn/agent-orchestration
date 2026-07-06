(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule lisp_frontend_design_delta/branching_terminal_reprojection_support)
  (import std/resource :only (StateExisting))
  (export project-selected-compat)

  (defrecord BranchingSelectedCompat
    (item-id String)
    (is-active Bool)
    (final-plan-gate-state StateExisting))

  (defworkflow project-selected-compat
    ((item-id String))
    -> BranchingSelectedCompat
    (let* ((final-plan-gate-state
             (__generated-relpath-seed__
               StateExisting
               "state/branching_terminal_reprojection/final_plan_gate_state.json"
               "branching_terminal_reprojection_final_plan_gate_state")))
      (record BranchingSelectedCompat
        :item-id item-id
        :is-active false
        :final-plan-gate-state final-plan-gate-state))))
