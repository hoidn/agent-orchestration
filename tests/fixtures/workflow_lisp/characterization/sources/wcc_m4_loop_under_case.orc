(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule wcc_m4_loop_under_case)
  (export run)
  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)
  (defunion AttemptResult
    (COMPLETED
      (report WorkReport))
    (BLOCKED
      (reason String)
      (report WorkReport)))
  (defrecord LoopState
    (report WorkReport))
  (defunion LoopResult
    (COMPLETED
      (status String)
      (report WorkReport)
      (reason String))
    (BLOCKED
      (status String)
      (reason String)
      (report WorkReport))
    (EXHAUSTED
      (status String)
      (reason String)
      (report WorkReport)))
  (defworkflow run
    ((report_path WorkReport))
    -> LoopResult
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (report_path)
               :returns AttemptResult)))
      (match attempt
        ((COMPLETED completed)
         (loop/recur
           :max 1
           :state (record LoopState
                    :report completed.report)
           :on-exhausted (variant LoopResult EXHAUSTED
                           :status "exhausted"
                           :reason "max_iterations_reached"
                           :report state.report)
           (fn (state)
             (done
               (variant LoopResult COMPLETED
                 :status "completed"
                 :report state.report
                 :reason "not_blocked")))))
        ((BLOCKED blocked)
         (variant LoopResult BLOCKED
           :status "blocked"
           :reason blocked.reason
           :report blocked.report))))))
