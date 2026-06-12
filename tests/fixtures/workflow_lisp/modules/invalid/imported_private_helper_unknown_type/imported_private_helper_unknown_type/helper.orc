(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule imported_private_helper_unknown_type/helper)
  (export HelperInput PublicDecision run-helper)

  (defrecord HelperInput
    (approved Bool))

  (defunion PublicDecision
    (ALLOW)
    (REJECT))

  (defproc route-decision
    ((input HelperInput))
    -> MissingDecision
    :effects ()
    :lowering private-workflow
    (if input.approved
      (variant MissingDecision ALLOW)
      (variant MissingDecision REJECT)))

  (defworkflow run-helper
    ((input HelperInput))
    -> PublicDecision
    (let* ((decision
             (route-decision input)))
      (match decision
        ((ALLOW allow)
         (variant PublicDecision ALLOW))
        ((REJECT reject)
         (variant PublicDecision REJECT))))))
