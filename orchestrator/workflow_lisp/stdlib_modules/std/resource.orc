(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule std/resource)
  (export BlockerClass
          WorkReport
          StateExisting
          SelectedItemResult
          SelectedItemOutcomeState
          SelectedItemOutcomeRequest
          SelectedItemOutcomeResult
          SelectedItemOutcomeAudit
          SelectedItemSummaryValue
          selected-item-outcome
          record-selected-item-outcome
          finalize-selected-item
          finalize-selected-item-proc)
  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defpath StateExisting
    :kind relpath
    :under "state"
    :must-exist true)
  (defunion SelectedItemResult
    (CONTINUE
      (summary-path WorkReport))
    (BLOCKED
      (summary-path WorkReport)
      (blocker-class BlockerClass)))
  (defrecord SelectedItemOutcomeState
    (variant String)
    (summary_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool)
    (roadmap_status String)
    (queue_transition_id String))
  (defrecord SelectedItemOutcomeRequest
    (variant String)
    (summary_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool)
    (roadmap_status String)
    (queue_transition_id String))
  (defrecord SelectedItemOutcomeResult
    (variant String)
    (summary_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool)
    (roadmap_status String)
    (queue_transition_id String))
  (defrecord SelectedItemOutcomeAudit
    (variant String)
    (summary_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool)
    (roadmap_status String)
    (queue_transition_id String))
  (defrecord SelectedItemSummaryValue
    (variant String)
    (summary_path WorkReport)
    (blocker_class BlockerClass)
    (has_blocker Bool)
    (roadmap_status String)
    (queue_transition_id String))
  (defresource selected-item-outcome
    :state-type std/resource/SelectedItemOutcomeState
    :backing state-layout)
  (deftransition record-selected-item-outcome
    :resource selected-item-outcome
    :request-type std/resource/SelectedItemOutcomeRequest
    :result-type std/resource/SelectedItemOutcomeResult
    :preconditions ((!= request.variant ""))
    :updates ((set-field variant request.variant)
              (set-field summary_path request.summary_path)
              (set-field blocker_class request.blocker_class)
              (set-field has_blocker request.has_blocker)
              (set-field roadmap_status request.roadmap_status)
              (set-field queue_transition_id request.queue_transition_id))
    :write-set (variant summary_path blocker_class has_blocker roadmap_status queue_transition_id)
    :idempotency-fields (variant summary_path blocker_class has_blocker roadmap_status queue_transition_id)
    :result (record std/resource/SelectedItemOutcomeResult
      :variant request.variant
      :summary_path request.summary_path
      :blocker_class request.blocker_class
      :has_blocker request.has_blocker
      :roadmap_status request.roadmap_status
      :queue_transition_id request.queue_transition_id)
    :audit (record std/resource/SelectedItemOutcomeAudit
      :variant request.variant
      :summary_path request.summary_path
      :blocker_class request.blocker_class
      :has_blocker request.has_blocker
      :roadmap_status request.roadmap_status
      :queue_transition_id request.queue_transition_id)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defproc finalize-selected-item-proc
    :forall (PlanT ImplT)
    ((selected-active Bool)
     (queue-transition-id String)
     (roadmap-status String)
     (plan PlanT)
     (implementation ImplT))
    :where ((PlanT has-union-variant APPROVED (execution-report-path WorkReport))
            (PlanT has-union-variant BLOCKED (progress-report-path WorkReport) (blocker-class BlockerClass))
            (ImplT has-union-variant COMPLETED (execution-report-path WorkReport))
            (ImplT has-union-variant BLOCKED (progress-report-path WorkReport) (blocker-class BlockerClass)))
    -> SelectedItemResult
    :effects ((uses-command apply_resource_transition))
    :lowering inline
    (match plan
        ((APPROVED approved)
         (match implementation
           ((COMPLETED completed)
            (let* ((outcome
                     (resource-transition
                       :transition record-selected-item-outcome
                       :resource selected-item-outcome
                       :request (record std/resource/SelectedItemOutcomeRequest
                                  :variant "CONTINUE"
                                  :summary_path completed.execution-report-path
                                  :blocker_class BlockerClass.missing_resource
                                  :has_blocker false
                                  :roadmap_status roadmap-status
                                  :queue_transition_id queue-transition-id)))
                   (summary-path outcome.summary_path))
              (variant SelectedItemResult CONTINUE
                :summary-path summary-path)))
           ((BLOCKED blocked)
            (let* ((outcome
                     (resource-transition
                       :transition record-selected-item-outcome
                       :resource selected-item-outcome
                       :request (record std/resource/SelectedItemOutcomeRequest
                                  :variant "BLOCKED"
                                  :summary_path blocked.progress-report-path
                                  :blocker_class blocked.blocker-class
                                  :has_blocker true
                                  :roadmap_status roadmap-status
                                  :queue_transition_id queue-transition-id)))
                   (summary-path outcome.summary_path))
              (variant SelectedItemResult BLOCKED
                :summary-path summary-path
                :blocker-class blocked.blocker-class)))))
        ((BLOCKED blocked)
         (let* ((outcome
                  (resource-transition
                    :transition record-selected-item-outcome
                    :resource selected-item-outcome
                    :request (record std/resource/SelectedItemOutcomeRequest
                               :variant "BLOCKED"
                               :summary_path blocked.progress-report-path
                               :blocker_class blocked.blocker-class
                               :has_blocker true
                               :roadmap_status roadmap-status
                               :queue_transition_id queue-transition-id)))
                (summary-path outcome.summary_path))
           (variant SelectedItemResult BLOCKED
             :summary-path summary-path
             :blocker-class blocked.blocker-class)))))
  (defmacro finalize-selected-item (ctx-key ctx selected-key selected queue-transition-key queue-transition roadmap-key roadmap plan-key plan implementation-key implementation)
    (std/resource/finalize-selected-item-proc
      selected.is-active
      (if selected.is-active queue-transition.transition-id "")
      roadmap.status
      plan
      implementation)))
