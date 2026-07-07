(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule minimal_caller_finalize_selected_item)
  (import std/resource :only (BlockerClass SelectedItemResult WorkReport finalize-selected-item-proc))
  (defunion MinimalPlan
    (APPROVED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defunion MinimalImplementation
    (COMPLETED
      (execution-report-path WorkReport))
    (BLOCKED
      (progress-report-path WorkReport)
      (blocker-class BlockerClass)))
  (defworkflow minimal-finalize-selected-item
    ((selected-active Bool)
     (queue-transition-id String)
     (roadmap-status String)
     (plan-approved Bool)
     (implementation-completed Bool)
     (plan-report WorkReport)
     (implementation-report WorkReport)
     (blocker-class BlockerClass))
    -> SelectedItemResult
    (let* ((plan
             (if plan-approved
               (variant MinimalPlan APPROVED
                 :execution-report-path plan-report)
               (variant MinimalPlan BLOCKED
                 :progress-report-path plan-report
                 :blocker-class blocker-class)))
           (implementation
             (if implementation-completed
               (variant MinimalImplementation COMPLETED
                 :execution-report-path implementation-report)
               (variant MinimalImplementation BLOCKED
                 :progress-report-path implementation-report
                 :blocker-class blocker-class))))
      (finalize-selected-item-proc
        selected-active
        queue-transition-id
        roadmap-status
        plan
        implementation))))
