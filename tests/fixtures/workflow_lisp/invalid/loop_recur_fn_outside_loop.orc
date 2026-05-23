(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
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
  (defrecord ImplementationSummary
    (status String)
    (report WorkReport))
  (defworkflow loop-recur-fn-outside-loop
    ((summary ImplementationSummary))
    -> ImplementationSummary
    (fn (state) state)))
