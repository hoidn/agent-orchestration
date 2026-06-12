(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_private_helper_local_union/helper)
  (export HelperInput PublicDecision run-helper)

  (defrecord HelperInput
    (approved Bool)
    (detail String))

  (defunion PublicDecision
    (ALLOW
      (message String))
    (REJECT
      (message String)))

  (defunion LocalDecision
    (ALLOW_LOCAL
      (message String))
    (REJECT_LOCAL
      (message String)))

  (defproc finalize-decision
    ((approved Bool)
     (detail String))
    -> LocalDecision
    :effects ()
    :lowering private-workflow
    (if approved
      (variant LocalDecision ALLOW_LOCAL
        :message detail)
      (variant LocalDecision REJECT_LOCAL
        :message detail)))

  (defproc route-decision
    ((input HelperInput))
    -> LocalDecision
    :effects ()
    :lowering private-workflow
    (finalize-decision input.approved input.detail))

  (defworkflow run-helper
    ((input HelperInput))
    -> PublicDecision
    (let* ((decision
             (route-decision input)))
      (match decision
        ((ALLOW_LOCAL allow)
         (variant PublicDecision ALLOW
           :message allow.message))
        ((REJECT_LOCAL reject)
         (variant PublicDecision REJECT
           :message reject.message))))))
