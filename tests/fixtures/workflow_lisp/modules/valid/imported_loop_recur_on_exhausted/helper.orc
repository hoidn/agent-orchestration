(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule helper)
  (import types :only (WorkReport LoopSignal LoopState LoopResult))
  (export project-exhausted)
  (defworkflow project-exhausted
    ((report_path WorkReport))
    -> LoopResult
    (loop/recur
      :max 1
      :state (record LoopState
               :report report_path)
      :on-exhausted (variant LoopResult EXHAUSTED
                      :reason "max_iterations_reached"
                      :report state.report)
      (fn (state)
        (let* ((signal
                 (provider-result providers.execute
                   :prompt prompts.implementation.execute
                   :inputs (report_path)
                   :returns LoopSignal)))
          (match signal
            ((READY ready)
             (done
               (variant LoopResult COMPLETED
                 :status "completed"
                 :report ready.report)))
            ((RETRY retry)
             (continue state))))))))
