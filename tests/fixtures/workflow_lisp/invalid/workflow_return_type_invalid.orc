(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defworkflow invalid-return
    ((prompt Prompt))
    -> Provider
    prompt))
