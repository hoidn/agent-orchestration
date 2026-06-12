(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defenum BlockerClass
    missing_resource
    unavailable_hardware)
  (defrecord RecoverySummary
    (blocked Bool))
  (defworkflow invalid-enum-member-unknown
    ()
    -> RecoverySummary
    (record RecoverySummary
      :blocked (= BlockerClass.user_decision_required BlockerClass.missing_resource))))
