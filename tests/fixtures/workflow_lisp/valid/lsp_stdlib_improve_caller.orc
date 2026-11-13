(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule lsp_stdlib_improve_caller)
  (import std/improve :only (Decision Improvement improve))
  (defrecord Draft (text String))
  (defproc review-draft ((draft Draft)) -> Decision[String String]
    (variant Decision[String String] APPROVE :evidence draft.text))
  (defproc revise-draft ((draft Draft) (feedback String)) -> Draft
    draft)
  (defworkflow polish ((draft Draft)) -> Improvement[Draft String String]
    (improve draft (proc-ref review-draft) (proc-ref revise-draft) 2)))
