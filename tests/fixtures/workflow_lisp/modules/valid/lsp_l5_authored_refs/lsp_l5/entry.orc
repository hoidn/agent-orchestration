(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.20")
  (defmodule lsp_l5/entry)
  (import lsp_l5/definitions :as defs
    :only (WorkReport SharedResult shared))
  (export exercise-prompts procedure-control workflow-control)

  (defprompt local-review
    (:fills
      (message :text))
    -> SharedResult
    "Review {message}")

  (defproc local-review
    ((report WorkReport))
    -> SharedResult
    :effects ()
    :lowering inline
    (record SharedResult :report report))

  (defworkflow local-review
    ((report WorkReport))
    -> SharedResult
    (record SharedResult :report report))

  (defworkflow exercise-prompts
    ((message String))
    -> SharedResult
    (let* ((local-ref
             (proc-ref local-review))
           (unqualified-ref
             (proc-ref shared))
           (alias-ref
             (proc-ref defs.shared))
           (canonical-ref
             (proc-ref lsp_l5/definitions/shared))
           (local-result
             (provider-result providers.review
               :prompt (local-review :message message)))
           (unqualified-result
             (provider-result providers.review
               :prompt (shared :message message)))
           (alias-result
             (provider-result providers.review
               :prompt (defs.shared :message message)))
           (canonical-result
             (provider-result providers.review
               :prompt
                 (lsp_l5/definitions/shared :message message))))
      canonical-result))

  (defworkflow procedure-control
    ((report WorkReport))
    -> SharedResult
    (local-review report))

  (defworkflow workflow-control
    ((report WorkReport))
    -> SharedResult
    (call local-review :report report)))
