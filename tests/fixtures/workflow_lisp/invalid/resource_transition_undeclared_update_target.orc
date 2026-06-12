(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defpath StateFile
    :kind relpath
    :under "state"
    :must-exist false)
  (defrecord DrainRunState
    (drain_status String))
  (defrecord DrainStatusRequest
    (status String))
  (defrecord DrainStatusResult
    (status String))
  (defrecord DrainStatusAudit
    (status String))
  (defresource drain-run-state
    :state-type DrainRunState
    :backing (bridge run_state_path))
  (deftransition write-drain-status
    :resource drain-run-state
    :request-type DrainStatusRequest
    :result-type DrainStatusResult
    :preconditions ((!= request.status ""))
    :updates ((set-field missing_field request.status))
    :write-set (missing_field)
    :idempotency-fields (status)
    :result (record DrainStatusResult
      :status request.status)
    :audit (record DrainStatusAudit
      :status request.status)
    :conflict-policy fail_closed
    :backend runtime_native)
  (defworkflow orchestrate
    ((run_state_path StateFile))
    -> DrainStatusResult
    (resource-transition
      :transition write-drain-status
      :resource drain-run-state
      :request (record DrainStatusRequest
        :status "BLOCKED"))))
