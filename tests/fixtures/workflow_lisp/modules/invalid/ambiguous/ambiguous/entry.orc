(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule ambiguous/entry)
  (import alpha/one :only (Shared))
  (import beta/two :only (Shared))
  (export Root)
  (defworkflow Root
    ()
    -> Shared
    (record Shared
      :status "ok")))
