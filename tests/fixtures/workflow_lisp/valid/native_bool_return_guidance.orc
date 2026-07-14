(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.15")
  (defmodule native_bool_return_guidance)
  (export decide)
  (defworkflow decide
    ()
    -> (result Bool
         :description "Whether the reviewed change is approved."
         :format-hint "JSON boolean."
         :example true)
    (let* ((approved
            (provider-result providers.review
              :prompt prompts.review
              :inputs ()
              :returns (result Bool
                         :description "True only when the change has no blockers."
                         :format-hint "Write a JSON boolean."
                         :example true))))
      (if approved
          (command-result record_approved
            :argv ("python" "scripts/record_approved.py")
            :returns Bool)
          (command-result record_revise
            :argv ("python" "scripts/record_revise.py")
            :returns Bool)))))
