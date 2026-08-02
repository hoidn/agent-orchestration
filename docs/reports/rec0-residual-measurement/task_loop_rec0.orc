; REC0 study artifact (non-executed): the lean-pilot ORC treatment topology
; rewritten at target 2.23 using currently supported forms.
; Companion report: docs/reports/2026-08-01-workflow-lisp-rec0-residual-measurement.md
; Original exemplar (frozen, unmodified):
;   workflows/experiments/repository_task_pilot/task_loop.orc
;   (977 lines by wc -l; 978 physical lines, final line lacks a newline; 2.20)
; Deliberate deltas, each measured in the report:
;   - product-manifest guard brackets dropped (instrumentation class; E1
;     workspace-delta evidence supersedes in-band guards);
;   - implementation review/fix cycle uses the stdlib review-revise-loop,
;     which imposes the stdlib artifact-backed review protocol
;     (ReviewDecision/ReviewFindings with report paths) on those prompts;
;   - the checks-pass requirement folds into the reviewer contract (the
;     original review_implementation prompt already required it), because
;     ReviewLoopResult does not return the final subject/checks values;
;   - the plan review/revise cycle stays hand-rolled: its subject is a
;     value-typed PlanResult consumed downstream, and the stdlib loop does
;     not return the final completed subject (control-flow residual,
;     attributed to REC1 in the report);
;   - PilotOutcome.PROTOCOL_FAILURE is retained for type-surface parity but
;     is unreachable here: only the dropped guard checks produced it;
;   - the stdlib loop is post-test: on the double-REVISE path it runs one
;     trailing fix + recheck before EXHAUSTED, where the original returned
;     EXHAUSTED directly from the second REVISE.
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.23")
  (defmodule task_loop_rec0)
  (import std/phase :only
    (BlockerClass ReviewDecision ReviewFindings ReviewLoopResult
     ReviewReportPath review-revise-loop))
  (export run-task)

  (defpath TaskPath
    :kind relpath
    :under ".pilot/runtime"
    :must-exist true)

  (defpath ControlPath
    :kind relpath
    :under ".pilot/runtime"
    :must-exist true)

  (defrecord DiscoveryResult
    (relevant_paths List[String])
    (constraints List[String])
    (risks List[String]))

  (defrecord PlanResult
    (steps List[String])
    (acceptance_checks List[String]))

  (defrecord ChecksResult
    (passed Bool)
    (exit_code Int))

  (defrecord ImplementationResult
    (summary String)
    (changed_paths List[String])
    (checks_summary String))

  (defenum PilotOutcome
    COMPLETED
    BLOCKED
    EXHAUSTED
    PROTOCOL_FAILURE)

  (defrecord TaskEnv
    (task_path TaskPath)
    (control_path ControlPath)
    (controller_script String)
    (model String)
    (effort String))

  (defrecord ImplSubject
    (implementation ImplementationResult)
    (checks ChecksResult))

  (defrecord ImplCycleInputs
    (env TaskEnv)
    (plan PlanResult))

  (defproc review-implementation
    ((completed ImplSubject)
     (inputs ImplCycleInputs))
    -> ReviewDecision
    :effects ((uses-provider providers.repository-task.review-implementation))
    :lowering inline
    (provider-result providers.repository-task.review-implementation
      :prompt prompts.repository-task.review-implementation
      :inputs (inputs.env.task_path
               inputs.plan
               completed.implementation
               completed.checks)
      :model inputs.env.model
      :effort inputs.env.effort
      :timeout-sec 1800
      :returns ReviewDecision))

  (defproc fix-implementation
    ((completed ImplSubject)
     (inputs ImplCycleInputs)
     (findings ReviewFindings))
    -> ImplSubject
    :effects ((uses-provider providers.repository-task.fix-implementation)
              (uses-command pilot_visible_check))
    :lowering inline
    (let* ((fixed
             (provider-result providers.repository-task.fix-implementation
               :prompt prompts.repository-task.fix-implementation
               :inputs (inputs.env.task_path
                        inputs.plan
                        completed.implementation
                        completed.checks
                        findings)
               :model inputs.env.model
               :effort inputs.env.effort
               :timeout-sec 1800
               :returns ImplementationResult))
           (rechecked
             (command-result pilot_visible_check
               :argv ("python"
                      inputs.env.controller_script
                      "visible-check"
                      "--control"
                      inputs.env.control_path
                      "--attempt"
                      "2")
               :returns ChecksResult)))
      ; nested-record returns must be rebuilt from nested record
      ; expressions (workflow_return_not_exportable otherwise) - measured
      ; dataflow residual, see report
      (record ImplSubject
        :implementation (record ImplementationResult
                          :summary fixed.summary
                          :changed_paths fixed.changed_paths
                          :checks_summary fixed.checks_summary)
        :checks (record ChecksResult
                  :passed rechecked.passed
                  :exit_code rechecked.exit_code))))

  (defworkflow implement-and-review
    ((env TaskEnv)
     (plan PlanResult))
    -> PilotOutcome
    (let* ((implementation
             (provider-result providers.repository-task.implement
               :prompt prompts.repository-task.implement
               :inputs (env.task_path plan)
               :model env.model
               :effort env.effort
               :timeout-sec 1800
               :returns ImplementationResult))
           (checks
             (command-result pilot_visible_check
               :argv ("python"
                      env.controller_script
                      "visible-check"
                      "--control"
                      env.control_path
                      "--attempt"
                      "1")
               :returns ChecksResult))
           (impl-review
             (review-revise-loop implementation-review
               :ctx env
               :completed (record ImplSubject
                            :implementation implementation
                            :checks checks)
               :inputs (record ImplCycleInputs
                         :env env
                         :plan plan)
               :review (proc-ref review-implementation)
               :fix (proc-ref fix-implementation)
               :max 2)))
      (match impl-review
        ((APPROVED approved) PilotOutcome.COMPLETED)
        ((BLOCKED blocked) PilotOutcome.BLOCKED)
        ((EXHAUSTED exhausted) PilotOutcome.EXHAUSTED))))

  (defworkflow plan-review-once
    ((env TaskEnv)
     (discovery DiscoveryResult)
     (plan PlanResult))
    -> ReviewDecision
    (provider-result providers.repository-task.review-plan
      :prompt prompts.repository-task.review-plan
      :inputs (env.task_path discovery plan env.control_path)
      :model env.model
      :effort env.effort
      :timeout-sec 1800
      :returns ReviewDecision))

  (defworkflow run-task
    ((task_path TaskPath)
     (control_path ControlPath)
     (controller_script String)
     (model String)
     (effort String))
    -> PilotOutcome
    (let* ((env
             (record TaskEnv
               :task_path task_path
               :control_path control_path
               :controller_script controller_script
               :model model
               :effort effort))
           (discovery
             (provider-result providers.repository-task.discover
               :prompt prompts.repository-task.discover
               :inputs (task_path)
               :model model
               :effort effort
               :timeout-sec 1800
               :returns DiscoveryResult))
           (draft-plan
             (provider-result providers.repository-task.plan
               :prompt prompts.repository-task.plan
               :inputs (task_path discovery control_path)
               :model model
               :effort effort
               :timeout-sec 1800
               :returns PlanResult))
           (first-review
             (call plan-review-once
               :env env
               :discovery discovery
               :plan draft-plan)))
      (match first-review
        ((BLOCKED first-blocked) PilotOutcome.BLOCKED)
        ((APPROVE first-approved)
         (call implement-and-review
           :env env
           :plan draft-plan))
        ((REVISE first-revise)
         (let* ((revised-plan
                  (provider-result providers.repository-task.revise-plan
                    :prompt prompts.repository-task.revise-plan
                    :inputs (task_path
                             discovery
                             draft-plan
                             first-revise.findings
                             control_path)
                    :model model
                    :effort effort
                    :timeout-sec 1800
                    :returns PlanResult))
                (second-review
                  (call plan-review-once
                    :env env
                    :discovery discovery
                    :plan revised-plan)))
           (match second-review
             ((BLOCKED second-blocked) PilotOutcome.BLOCKED)
             ((REVISE second-revise) PilotOutcome.EXHAUSTED)
             ((APPROVE second-approved)
              (call implement-and-review
                :env env
                :plan revised-plan))))))))
)
